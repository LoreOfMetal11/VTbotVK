import logging
import queue
import re
import threading
import time
from collections import deque
from getpass import getpass
from urllib.parse import urljoin, urlparse

import requests
import vk_api
from bs4 import BeautifulSoup
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

VT_URL = "https://vt.pnzgu.ru/"
NEWS_URL = "https://vt.pnzgu.ru/news"
SCHEDULE_URL = "https://pnzgu.ru/schedule"
VUC_URL = "https://vuc.pnzgu.ru/studentam_postuplenie_v_vuc"
SCORES_URL = "https://pnzgu.ru/Abitur/admission/rezult_old"
ADMISSION_URL = "https://pnzgu.ru/Abitur/admission/contacts"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

WELCOME = (
    "Привет! Здесь можно познакомиться с кафедрой «Вычислительная техника» ПГУ.\n\n"
    "Расскажу о направлениях обучения, технологиях и работе после выпуска. "
    "Ещё здесь можно посмотреть новости и полезные ссылки.\n\n"
    "Выбирай, что интересно."
)
UNKNOWN_ANSWER = "[пусто]"
PROGRAMS_NOTE = (
    "Информацию о текущем наборе уточняй в приёмной комиссии.\n"
    + ADMISSION_URL
)

TOPICS = {
    "about": (
        "Кафедра «Вычислительная техника» ПГУ\n\n"
        "Здесь готовят специалистов в области программирования, компьютерных "
        "систем и сетей, разработки вычислительной техники и применения "
        "искусственного интеллекта.\n\n"
        "Заведующая кафедрой: Карамышева Надежда Сергеевна.\n\n"
        "Сайт кафедры:\n" + VT_URL
    ),
    "programs": "Выбери уровень обучения: бакалавриат, специалитет, магистратура или аспирантура.",
    "bachelor": (
        "Бакалавриат\n\n09.03.01 «Информатика и вычислительная техника»\n\n"
        "Профили:\n"
        "• «Прикладной искусственный интеллект»;\n"
        "• «Программное обеспечение средств ВТ и автоматизированных систем».\n\n"
        "Очная форма обучения, срок обучения - 4 года. " + PROGRAMS_NOTE
    ),
    "specialist": (
        "Специалитет\n\n09.05.01 «Применение и эксплуатация автоматизированных "
        "систем специального назначения»\n\n"
        "Специализация: «Применение, эксплуатация вычислительных машин, комплексов, "
        "систем и сетей специального назначения».\n\n"
        "Очная форма обучения, срок обучения - 5 лет. " + PROGRAMS_NOTE
    ),
    "master": (
        "Магистратура\n\n09.04.01 «Информатика и вычислительная техника»\n\n"
        "Магистерская программа «Прикладной искусственный интеллект».\n\n"
        "Очная форма обучения, срок обучения - 2 года. " + PROGRAMS_NOTE
    ),
    "postgraduate": (
        "Аспирантура\n\n2.3.2 «Вычислительные системы и их элементы». " + PROGRAMS_NOTE
    ),
    "skills": (
        "Чему можно научиться\n\n"
        "• Программировать и разрабатывать программное обеспечение.\n"
        "• Разбираться в устройстве компьютеров и компьютерных сетей.\n"
        "• Устанавливать и администрировать программное обеспечение.\n"
        "• Обслуживать компьютеры и сетевое оборудование.\n"
        "• Разрабатывать вычислительные системы на современной элементной базе.\n"
        "• Применять интеллектуальные технологии для решения прикладных задач."
    ),
    "technologies": (
        "Технологии из буклета кафедры\n\n"
        "Языки программирования: C, C++, Python, Java, C#, JavaScript.\n\n"
        "Веб-технологии: HTML и CSS.\n\n"
        "Работа с базами данных: SQL.\n\n"
        "Инструменты и фреймворки: Git, Qt, Flutter.\n\n"
        "Языки описания аппаратуры: Verilog и VHDL."
    ),
    "careers": (
        "Работа после выпуска\n\n"
        "В буклете кафедры приведены такие варианты:\n"
        "• Разработчик на Python, Java или C/C++.\n"
        "• Frontend-, backend- или full-stack-разработчик.\n"
        "• Мобильный разработчик.\n"
        "• Инженер-программист.\n"
        "• Сетевой инженер.\n"
        "• Системный администратор.\n"
        "• Аналитик.\n"
        "• Тестировщик или QA-инженер.\n\n"
        "Выбор специализации зависит от навыков и проектов, которые ты будешь "
        "развивать во время обучения."
    ),
    "brochure": "[пусто]",
    "admissions": "Здесь собраны ссылки для поступающих. Выбери нужный раздел.",
    "contacts": (
        "Приёмная комиссия ПГУ\n\n"
        "Телефон: 66-62-89.\n"
        "Адрес: г. Пенза, ул. Красная, 40, корпус 8, этаж 2, аудитория 206.\n\n" + ADMISSION_URL
    ),
    "links": "Выбери нужную ссылку: сайт кафедры, расписание, ВУЦ или баллы прошлых лет.",
    "department_contacts": (
        "Заведующая кафедрой: Карамышева Надежда Сергеевна.\n\n"
        "Контакты кафедры смотри на сайте:\n" + VT_URL
    ),
    "department_site": VT_URL,
    "schedule": SCHEDULE_URL,
    "vuc": VUC_URL,
    "past_scores": SCORES_URL,
}

LAYOUTS = {
    "main": [
        ["О кафедре", "Направления обучения"],
        ["Чему научат", "Работа после выпуска"],
        ["Буклет кафедры", "Новости ВТ"],
        ["Поступление", "Полезные ссылки"],
    ],
    "about": [
        ["Чему научат", "Технологии"],
        ["Контакты кафедры", "Сайт кафедры"],
        ["Буклет кафедры", "Главное меню"],
    ],
    "programs": [
        ["Бакалавриат", "Специалитет"],
        ["Магистратура", "Аспирантура"],
        ["Главное меню"],
    ],
    "skills": [
        ["Технологии", "Работа после выпуска"],
        ["Направления обучения", "Главное меню"],
    ],
    "admissions": [
        ["Приёмная комиссия", "Баллы прошлых лет"],
        ["Направления обучения"],
        ["Главное меню"],
    ],
    "links": [
        ["Сайт кафедры", "Расписание"],
        ["Военный учебный центр", "Баллы прошлых лет"],
        ["Приёмная комиссия", "Главное меню"],
    ],
}

TOPIC_SECTIONS = {
    "about": "about", "department_contacts": "about", "department_site": "about",
    "brochure": "about",
    "programs": "programs", "bachelor": "programs", "specialist": "programs",
    "master": "programs", "postgraduate": "programs",
    "skills": "skills", "technologies": "skills", "careers": "skills",
    "admissions": "admissions", "contacts": "admissions", "past_scores": "admissions",
    "links": "links", "schedule": "links", "vuc": "links",
}

ALIASES = {
    "about": ["о кафедре", "о кафедре вт", "кафедра вт", "что такое кафедра вт"],
    "programs": ["направления обучения", "направления", "специальности", "какие есть направления"],
    "bachelor": ["бакалавриат"],
    "specialist": ["специалитет"],
    "master": ["магистратура"],
    "postgraduate": ["аспирантура"],
    "skills": ["чему научат", "чему учат", "знания и умения"],
    "technologies": ["технологии", "языки программирования", "какие языки"],
    "careers": ["работа после выпуска", "кем работать", "профессии", "работа"],
    "brochure": ["буклет кафедры", "буклет"],
    "admissions": ["поступление", "хочу поступить", "абитуриент"],
    "contacts": ["приёмная комиссия", "контакты приёмной комиссии", "как подать документы", "документы"],
    "links": ["полезные ссылки", "ссылки"],
    "department_contacts": ["контакты кафедры", "контакты", "заведующая", "заведующий", "кто заведует кафедрой"],
    "department_site": ["сайт кафедры", "сайт кафедры вт", "сайт"],
    "schedule": ["расписание", "расписание занятий", "расписание пар", "где посмотреть расписание"],
    "vuc": ["военный учебный центр", "вуц", "военка", "военная кафедра"],
    "past_scores": ["баллы прошлых лет", "баллы", "проходной балл", "проходные баллы",
                    "проходные баллы прошлых лет", "результаты прошлых лет"],
}

FAQ = [
    ("О кафедре ВТ", "about"),
    ("Какие есть направления?", "programs"),
    ("Чему научат?", "skills"),
    ("Какие технологии представлены в буклете?", "technologies"),
    ("Кем работать после выпуска?", "careers"),
    ("Кто заведует кафедрой?", "department_contacts"),
    ("Как связаться с приёмной комиссией?", "contacts"),
    ("Где посмотреть расписание?", "schedule"),
    ("Есть ли военный учебный центр?", "vuc"),
    ("Какие проходные баллы были раньше?", "past_scores"),
    ("Где посмотреть буклет?", "brochure"),
]

# Защита от спама: настройки
SPAM_LIMIT = 10
SPAM_WINDOW = 60
SPAM_WARNING = "Слишком много сообщений. Подожди минуту и попробуй ещё раз."

# LLM: настройки
LLM_ENABLED = False  # вкл/выкл
LLM_URL = "http://127.0.0.1:11434/api/chat"  # Ollama
LLM_MODEL = "qwen3.5:4b" # альтернатива - gemma4:e4b
LLM_TIMEOUT = (5, 120)  # таймауты, сек
LLM_MAX_TOKENS = 300  # лимит длины ответа
LLM_NUM_CTX = 4096  # размер контекста
LLM_KEEP_ALIVE = -1  # модель остаётся в памяти
LLM_THINK = False  # без режима рассуждений
LLM_WORKERS = 1  # число worker-потоков
LLM_QUEUE_LIMIT = 5  # длина очереди
LLM_QUESTION_LIMIT = 1000  # лимит вопроса
LLM_ANSWER_LIMIT = 4000  # лимит ответа
LLM_ACK_ANSWER = "Принял вопрос, готовлю ответ. Он будет готов в течении минуты."
LLM_BUSY_ANSWER = "Готовится ответ на прошлый вопрос. Пожалуйста, подождите."
LLM_OVERLOAD_ANSWER = "Сейчас слишком много вопросов. Попробуй ещё раз через минуту."
LLM_FALLBACK_ANSWER = (
    "Не получилось получить ответ. Попробуй позже или выбери раздел в меню.\n\n"
    "Контакты кафедры:\n" + VT_URL
)
LLM_SYSTEM_PROMPT = (
    "Ты — помощник кафедры «Вычислительная техника» (ВТ) ПГУ во ВКонтакте. "
    "Отвечай кратко, по-русски и только по теме кафедры и поступления. "
    "Если точного ответа не знаешь — честно скажи об этом и предложи обратиться "
    "в приёмную комиссию (телефон 66-62-89) или на сайт кафедры. "
    "Не выдумывай даты, цифры и требования.\n\n"
    "Факты о кафедре:\n"
    + TOPICS["about"] + "\n\n"
    + TOPICS["bachelor"] + "\n\n"
    + TOPICS["specialist"] + "\n\n"
    + TOPICS["master"] + "\n\n"
    + TOPICS["postgraduate"] + "\n\n"
    + TOPICS["contacts"]
)


def normalize(text):
    text = (text or "").lower().replace("ё", "е")
    return " ".join(text.split()).strip(" !?.")


COMMANDS = {
    normalize(alias): topic
    for topic, aliases in ALIASES.items()
    for alias in aliases
}
for question, topic in FAQ:
    COMMANDS[normalize(question)] = topic


def make_keyboard(section):
    keyboard = VkKeyboard(one_time=False)
    for index, row in enumerate(LAYOUTS[section]):
        if index:
            keyboard.add_line()
        for label in row:
            keyboard.add_button(label, color=VkKeyboardColor.SECONDARY)
    return keyboard.get_keyboard()


news_cache = {"text": None, "expires": 0}


def save_news(text, seconds):
    news_cache["text"] = text
    news_cache["expires"] = time.monotonic() + seconds
    return text


def get_news():
    if news_cache["text"] is not None and time.monotonic() < news_cache["expires"]:
        return news_cache["text"]
    fallback = "Новости кафедры ВТ\n\n[пусто]\n\n" + NEWS_URL
    try:
        response = requests.get(
            NEWS_URL, timeout=(5, 15),
            headers={"User-Agent": "VTApplicantBot/0.4"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        for element in soup.select("script, style, nav, header, footer"):
            element.decompose()
        content = soup.find("main") or soup
        items = []
        seen = set()
        for link in content.find_all("a", href=True):
            url = urlparse(urljoin(response.url, link["href"]))
            if url.scheme not in {"http", "https"}:
                continue
            if url.hostname != urlparse(NEWS_URL).hostname:
                continue
            if not re.fullmatch(r"/news/\d{4}/\d{1,2}/\d{1,2}/\d+/?", url.path):
                continue
            title = " ".join(link.stripped_strings)
            if not title or title.lower() in {"подробнее", "читать", "читать далее"}:
                continue
            clean_url = url._replace(query="", fragment="").geturl()
            if clean_url in seen:
                continue
            seen.add(clean_url)
            items.append(f"{title[:350]}\n{clean_url}")
            if len(items) == 3:
                break
        if not items:
            logging.warning("Не найдены публикации в ленте: %s", NEWS_URL)
            return save_news(fallback, 60)
        return save_news(
            "Первые публикации в ленте кафедры ВТ\n\n" + "\n\n".join(items), 300,
        )
    except requests.RequestException as error:
        status = error.response.status_code if error.response is not None else None
        logging.warning("Ошибка загрузки новостей: %s, HTTP: %s", type(error).__name__, status)
        return save_news(fallback, 60)


def answer_topic(topic):
    return TOPICS[topic], TOPIC_SECTIONS.get(topic, "main")


def make_answer(text):
    text = normalize(text)
    if text in {"привет", "здравствуйте", "начать", "старт", "меню", "главное меню", "помощь", "/start"}:
        return WELCOME, "main"
    if text in {"новости", "новости вт", "новости кафедры", "новости кафедры вт", "новости пгу", "последние новости"}:
        return get_news(), "main"
    if text in {"вопросы", "частые вопросы", "часто задаваемые вопросы", "faq", "задать вопрос"}:
        lines = ["Что тебя интересует?\n"]
        lines.extend(f"{number}. {question}" for number, (question, _) in enumerate(FAQ, start=1))
        lines.append("\nНапиши, например, «вопрос 1».")
        return "\n".join(lines), "main"
    match = re.fullmatch(r"(?:вопрос|faq)\s+(\d+)", text)
    if match:
        number = int(match.group(1))
        if 1 <= number <= len(FAQ):
            return answer_topic(FAQ[number - 1][1])
        return UNKNOWN_ANSWER, "main"
    topic = COMMANDS.get(text)
    if topic:
        return answer_topic(topic)
    if not text:
        return UNKNOWN_ANSWER, "main"
    # Свободный текст -> LLM
    return None, "main"


def send_answer(vk, peer_id, text, keyboard):
    params = {
        "peer_id": peer_id, "message": text,
        "keyboard": keyboard, "random_id": get_random_id(),
    }
    try:
        vk.messages.send(**params)
    except vk_api.exceptions.ApiError as error:
        if error.code != 912:
            raise
        logging.warning("Клавиатура отключена в настройках сообщества.")
        params.pop("keyboard")
        params["random_id"] = get_random_id()
        vk.messages.send(**params)


# Защита от спама: учёт сообщений
spam_log = {}  # время сообщений
spam_warned = {}  # время предупреждений


def is_spam(peer_id):
    now = time.monotonic()
    times = spam_log.setdefault(peer_id, deque())
    while times and now - times[0] >= SPAM_WINDOW:
        times.popleft()
    if len(times) >= SPAM_LIMIT:
        return True
    times.append(now)
    return False


def spam_warning_needed(peer_id):
    now = time.monotonic()
    last = spam_warned.get(peer_id)
    if last is None or now - last >= SPAM_WINDOW:
        spam_warned[peer_id] = now
        return True
    return False


# LLM: очередь и учёт занятых пользователей
llm_queue = queue.Queue(maxsize=LLM_QUEUE_LIMIT)
llm_lock = threading.Lock()
llm_busy_users = set()


# LLM: запрос к модели
def ask_llm(question):
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": question[:LLM_QUESTION_LIMIT]},
        ],
        "stream": False,
        "think": LLM_THINK,
        "keep_alive": LLM_KEEP_ALIVE,
        "options": {
            "temperature": 0.3,
            "num_predict": LLM_MAX_TOKENS,
            "num_ctx": LLM_NUM_CTX,
        },
    }
    try:
        response = requests.post(LLM_URL, json=payload, timeout=LLM_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        answer = data["message"]["content"].strip()
        return answer or None
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as error:
        logging.warning("LLM недоступна или ответ некорректен: %s", type(error).__name__)
        return None


# LLM: постановка вопроса в очередь
def handle_llm_request(vk, peer_id, question, keyboards):
    if not LLM_ENABLED:
        send_answer(vk, peer_id, UNKNOWN_ANSWER, keyboards["main"])
        return
    with llm_lock:
        if peer_id in llm_busy_users:
            reply = LLM_BUSY_ANSWER  # ответ на прошлый вопрос ещё готовится
        else:
            try:
                llm_queue.put_nowait((peer_id, question))
            except queue.Full:
                reply = LLM_OVERLOAD_ANSWER
            else:
                llm_busy_users.add(peer_id)
                reply = LLM_ACK_ANSWER
    send_answer(vk, peer_id, reply, keyboards["main"])


# LLM: worker-поток
def llm_worker(vk, keyboards):
    while True:
        peer_id, question = llm_queue.get()
        try:
            answer = ask_llm(question) or LLM_FALLBACK_ANSWER
            send_answer(vk, peer_id, answer[:LLM_ANSWER_LIMIT], keyboards["main"])
        except vk_api.exceptions.ApiError as error:
            logging.warning("Не удалось отправить ответ LLM. Код VK: %s", error.code)
        except requests.RequestException:
            logging.warning("Ошибка соединения при отправке ответа LLM.")
        finally:
            with llm_lock:
                llm_busy_users.discard(peer_id)
            llm_queue.task_done()


def main():
    token = getpass("Ключ сообщества: ").strip()
    if not token:
        print("Ключ не введён.")
        return
    try:
        group_id = int(input("ID сообщества: ").strip())
    except ValueError:
        print("Введи числовой ID сообщества.")
        return
    if group_id <= 0:
        print("ID должен быть положительным числом.")
        return

    session = vk_api.VkApi(token=token)
    vk = session.get_api()
    keyboards = {name: make_keyboard(name) for name in LAYOUTS}

    # Запуск LLM-worker потоков
    for _ in range(LLM_WORKERS):
        threading.Thread(target=llm_worker, args=(vk, keyboards), daemon=True).start()

    print("Бот запущен. Для остановки нажми Ctrl+C.")
    print("LLM:", "включена" if LLM_ENABLED else "выключена (задел готов)")
    while True:
        try:
            longpoll = VkBotLongPoll(session, group_id)
            for event in longpoll.listen():
                if event.type != VkBotEventType.MESSAGE_NEW:
                    continue
                message = event.object.message
                if message.get("out"):
                    continue
                if message["peer_id"] != message["from_id"]:
                    continue
                peer_id = message["peer_id"]

                if is_spam(peer_id):
                    if spam_warning_needed(peer_id):
                        logging.warning("Флуд от пользователя %s", peer_id)
                        try:
                            send_answer(vk, peer_id, SPAM_WARNING, keyboards["main"])
                        except vk_api.exceptions.ApiError as error:
                            logging.warning("Не удалось отправить предупреждение. Код VK: %s", error.code)
                        except requests.RequestException:
                            logging.warning("Ошибка соединения при отправке предупреждения.")
                    continue

                answer, section = make_answer(message.get("text"))
                try:
                    if answer is None:
                        handle_llm_request(vk, peer_id, message.get("text"), keyboards)
                    else:
                        send_answer(vk, peer_id, answer, keyboards[section])
                except vk_api.exceptions.ApiError as error:
                    logging.warning("Не удалось отправить ответ. Код VK: %s", error.code)
                except requests.RequestException:
                    logging.warning("Ошибка соединения при отправке ответа.")
        except requests.RequestException:
            logging.warning("Соединение прервано. Повторное подключение через 5 секунд.")
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nБот остановлен.")
    except vk_api.exceptions.ApiError as error:
        print(f"Ошибка VK. Код: {error.code}")
