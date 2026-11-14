import logging
import re
import time
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
ADMISSION_URL = "https://pnzgu.ru/Abitur/admission"

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
PROGRAMS_NOTE = (
    "\n\nНаправления и профили приведены по буклету кафедры 2025 года. "
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
        "Очная форма обучения, срок обучения - 4 года." + PROGRAMS_NOTE
    ),
    "specialist": (
        "Специалитет\n\n09.05.01 «Применение и эксплуатация автоматизированных "
        "систем специального назначения»\n\n"
        "Специализация: «Применение, эксплуатация вычислительных машин, комплексов, "
        "систем и сетей специального назначения».\n\n"
        "Очная форма обучения, срок обучения - 5 лет." + PROGRAMS_NOTE
    ),
    "master": (
        "Магистратура\n\n09.04.01 «Информатика и вычислительная техника»\n\n"
        "Магистерская программа «Прикладной искусственный интеллект».\n\n"
        "Очная форма обучения, срок обучения - 2 года." + PROGRAMS_NOTE
    ),
    "postgraduate": (
        "Аспирантура\n\n2.3.2 «Вычислительные системы и их элементы»." + PROGRAMS_NOTE
    ),
    "skills": (
        "Чему можно научиться\n\n"
        "• Программировать и разрабатывать программное обеспечение.\n"
        "• Разбираться в устройстве компьютеров и компьютерных сетей.\n"
        "• Устанавливать и администрировать программное обеспечение.\n"
        "• Обслуживать компьютеры и сетевое оборудование.\n"
        "• Разрабатывать вычислительные системы на современной элементной базе.\n"
        "• Применять интеллектуальные технологии для решения прикладных задач.\n\n"
        "По материалам буклета кафедры 2025 года."
    ),
    "technologies": (
        "Технологии из буклета кафедры\n\n"
        "Языки программирования: C, C++, Python, Java, C#, JavaScript.\n\n"
        "Веб-технологии: HTML и CSS.\n\n"
        "Работа с базами данных: SQL.\n\n"
        "Инструменты и фреймворки: Git, Qt, Flutter.\n\n"
        "Языки описания аппаратуры: Verilog и VHDL.\n\n"
        "Это перечень из буклета 2025 года, а не учебный план каждого профиля."
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
        "Адрес: г. Пенза, ул. Красная, 40, корпус 8, этаж 2, аудитория 206.\n\n"
        "Контакты приведены по буклету 2025 года.\n\n" + ADMISSION_URL
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
    "past_scores": ["баллы прошлых лет", "баллы", "проходной балл", "проходные баллы", "проходные баллы прошлых лет", "результаты прошлых лет"],
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
        return "[пусто]", "main"
    topic = COMMANDS.get(text)
    if topic:
        return answer_topic(topic)
    return "[пусто]", "main"


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
    print("Бот запущен. Для остановки нажми Ctrl+C.")
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
                answer, section = make_answer(message.get("text"))
                try:
                    send_answer(vk, message["peer_id"], answer, keyboards[section])
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
