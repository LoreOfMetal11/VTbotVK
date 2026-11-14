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


FVT_URL = "https://fvt.pnzgu.ru/"
DEAN_URL = "https://fvt.pnzgu.ru/history"
NEWS_URL = "https://pnzgu.ru/news"
SCHEDULE_URL = "https://pnzgu.ru/schedule"
VT_URL = "https://vt.pnzgu.ru/"
VUC_URL = "https://vuc.pnzgu.ru/studentam_postuplenie_v_vuc"
SCORES_URL = "https://pnzgu.ru/Abitur/admission/rezult_old"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

WELCOME = (
    "Привет! Здесь можно узнать о ФВТ и поступлении.\n\n"
    "Выбирай, что тебя интересует: направления, экзамены, "
    "документы или жизнь на факультете."
)

ADMISSIONS_MENU = (
    "С чего начнём?\n\n"
    "Выбери тему: направления, экзамены, документы, "
    "стоимость обучения или общежитие."
)

TOPICS = {
    "about": (
        "ФВТ - факультет вычислительной техники "
        "Пензенского государственного университета.\n\n"
        "Сайт факультета:\n"
        f"{FVT_URL}"
    ),

    "programs": (
        "Направления подготовки: [пусто]\n"
        "Профили: [пусто]\n"
        "Предметы и учебные проекты: [пусто]\n"
        "Практика: [пусто]\n"
        "Работа после выпуска: [пусто]"
    ),

    "exams": (
        "Год поступления: [пусто]\n"
        "Экзамены по направлениям: [пусто]\n"
        "Минимальные баллы: [пусто]\n"
        "Проходные баллы прошлых лет: [пусто]\n"
        f"{SCORES_URL}\n"
        "Баллы за индивидуальные достижения: [пусто]"
    ),

    "documents": (
        "Начало приёма документов: [пусто]\n"
        "Окончание приёма: [пусто]\n"
        "Список документов: [пусто]\n"
        "Как подать заявление: [пусто]\n"
        "Сроки зачисления: [пусто]"
    ),

    "fees": (
        "Учебный год: [пусто]\n"
        "Бюджетные места: [пусто]\n"
        "Платные места: [пусто]\n"
        "Стоимость обучения: [пусто]\n"
        "Порядок оплаты: [пусто]"
    ),

    "dorm": (
        "Условия предоставления общежития: [пусто]\n"
        "Как подать заявку: [пусто]\n"
        "Документы для заселения: [пусто]\n"
        "Стоимость проживания: [пусто]\n"
        "Контакт по вопросам заселения: [пусто]"
    ),

    "beginner": (
        "Нужно ли уметь программировать до поступления: [пусто]\n"
        "Что пригодится на первом курсе: [пусто]\n"
        "Материалы для подготовки: [пусто]\n"
        "Подготовительные занятия: [пусто]"
    ),

    "open_day": (
        "Ближайший день открытых дверей: [пусто]\n"
        "Время: [пусто]\n"
        "Место: [пусто]\n"
        "Программа: [пусто]\n"
        "Регистрация: [пусто]"
    ),

    "contacts": (
        "Приёмная комиссия\n\n"
        "Телефон: [пусто]\n"
        "Почта: [пусто]\n"
        "Часы работы: [пусто]\n"
        "Место подачи документов: [пусто]"
    ),

    "location": (
        "ФВТ находится по адресу: "
        "г. Пенза, ул. Красная, 40, корпус № 7.\n\n"
        "Кабинеты деканата: 7а-310 и 7а-312.\n\n"
        "Место подачи документов для поступления: [пусто]\n\n"
        f"{DEAN_URL}"
    ),

    "scholarships": (
        "Виды стипендий: [пусто]\n"
        "Условия назначения: [пусто]\n"
        "Размеры выплат: [пусто]\n"
        "Необходимые документы: [пусто]"
    ),

    "dean_office": (
        "Деканат ФВТ\n\n"
        "Г. Пенза, ул. Красная, 40, корпус № 7.\n"
        "Кабинеты: 7а-310 и 7а-312.\n\n"
        "Телефон: +7 (8412) 66-65-60\n"
        "Почта: fvt@pnzgu.ru\n\n"
        "Понедельник - четверг: 08:00-16:00.\n"
        "Пятница: [пусто]\n\n"
        "Заявки на справки принимаются "
        "во вторник и четверг.\n\n"
        f"{DEAN_URL}\n"
        "Информация на странице обновлена 12.03.2025."
    ),

    "certificate": (
        "Заявки на справки принимаются "
        "во вторник и четверг.\n\n"
        "Как подать заявку: [пусто]\n"
        "Срок изготовления: [пусто]\n\n"
        "Уточнить можно в деканате:\n"
        "+7 (8412) 66-65-60\n"
        "fvt@pnzgu.ru\n"
        "Кабинеты 7а-310 и 7а-312.\n\n"
        f"{DEAN_URL}\n"
        "Информация на странице обновлена 12.03.2025."
    ),
        "schedule": (
        "Расписание занятий ПГУ\n\n"
        "Актуальное расписание пар и сессии публикуется "
        "на официальном сайте университета.\n\n"
        "Выбери политехнический институт, факультет вычислительной техники и ваш курс "
        "чтобы получить расписание.\n\n"
        f"{SCHEDULE_URL}"
    ),
    "vt_department": (
        "Кафедра «Вычислительная техника» (ВТ)\n\n"
        "На сайте кафедры вы можете найти "
        "информацию о кафедре для абитуриентов "
        "и научной работе.\n\n"
        f"{VT_URL}"
    ),
    "vuc": (
        "Военный учебный центр ПГУ\n\n"
        "При университете работает военный учебный центр: "
        "студенты могут пройти военную подготовку "
        "параллельно с учёбой.\n\n"
        "Новости, условия отбора и сроки набора можно узнать по ссылке:\n\n "
        f"{VUC_URL}"
    ),
    "past_scores": (
        "Проходные баллы прошлых лет\n\n"
        "На странице опубликованы результаты приёма "
        "прошлых лет. Сравни свои баллы ЕГЭ с баллами "
        "зачисленных абитуриентов, чтобы оценить шансы "
        "на поступление.\n\n"
        f"{SCORES_URL}"
    ),
}

FAQ = [
    ("Что такое ФВТ?", "about"),
    ("Какие есть направления?", "programs"),
    ("Какие экзамены нужны?", "exams"),
    ("Как подать документы?", "documents"),
    ("Сколько стоит обучение?", "fees"),
    ("Есть ли общежитие?", "dorm"),
    ("Нужно ли уметь программировать?", "beginner"),
    ("Когда день открытых дверей?", "open_day"),
    ("Как связаться с приёмной комиссией?", "contacts"),
    ("Где находится факультет?", "location"),
    ("Какие есть стипендии?", "scholarships"),
    ("Как связаться с деканатом?", "dean_office"),
    ("Как получить справку?", "certificate"),
    ("Где посмотреть расписание?", "schedule"),
    ("Что такое кафедра ВТ?", "vt_department"),
    ("Есть ли военный учебный центр?", "vuc"),
    ("Какие проходные баллы были раньше?", "past_scores"),

]

ALIASES = {
    "about": [
        "о факультете", "о фвт", "знакомство с фвт",
        "что такое фвт", "сайт", "сайт фвт",
    ],
    "programs": [
        "направления", "специальности", "чему учат",
    ],
    "exams": [
        "экзамены", "экзамены и баллы", "егэ",
        "баллы", "проходной балл", "какие экзамены",
    ],
    "documents": [
        "документы", "сроки", "сроки и документы",
        "как подать документы",
    ],
    "fees": [
        "бюджет", "стоимость", "бюджет и стоимость",
        "цена", "платное обучение",
    ],
    "dorm": [
        "общежитие", "общага", "жильё",
        "есть ли общежитие",
    ],
    "beginner": [
        "без опыта", "без опыта в it",
        "не умею программировать",
        "нужно ли уметь программировать",
    ],
    "open_day": [
        "день открытых дверей", "открытые двери",
    ],
    "contacts": [
        "приёмная комиссия", "контакты приёмной комиссии",
    ],
    "location": [
        "как нас найти", "адрес", "адрес фвт",
        "где находится фвт", "как добраться",
    ],
    "scholarships": [
        "стипендия", "стипендии",
    ],
    "dean_office": [
        "деканат", "деканат фвт", "где деканат",
        "телефон", "телефон фвт", "телефон деканата",
        "контакты", "почта деканата",
        "часы работы деканата",
    ],
    "certificate": [
        "справка", "справки", "справка об обучении",
        "как получить справку", "заказать справку",
    ],
    "schedule": [
        "расписание", "расписание занятий", "расписание пар",
        "расписание фвт", "где посмотреть расписание",
    ],
    "vt_department": [
        "кафедра вт", "кафедра вычислительная техника",
        "сайт кафедры", "сайт кафедры вт",
    ],
    "vuc": [
        "вуц", "военный учебный центр", "военная кафедра",
        "военка", "информация вуц",
    ],
    "past_scores": [
        "баллы прошлых лет", "проходные баллы",
        "проходные баллы прошлых лет", "результаты прошлых лет",
    ],
}


def normalize(text):
    text = (text or "").lower()
    text = text.translate(str.maketrans({"ё": "е"}))
    return " ".join(text.split()).strip(" !?.")


COMMANDS = {
    normalize(alias): topic
    for topic, aliases in ALIASES.items()
    for alias in aliases
}

for question, topic in FAQ:
    COMMANDS[normalize(question)] = topic


def make_keyboard(section):
    layouts = {
        "main": [
            ["О факультете", "Хочу поступить"],
            ["Частые вопросы", "Новости ПГУ"],
            ["Деканат", "Задать вопрос"],
        ],
        "admissions": [
            ["Направления", "Экзамены и баллы"],
            ["Сроки и документы", "Бюджет и стоимость"],
            ["Общежитие", "Приёмная комиссия"],
            ["Баллы прошлых лет", "Военный учебный центр"],
            ["Главное меню"],
        ],
        "faq": [
            ["Без опыта в IT", "День открытых дверей"],
            ["Как нас найти", "Стипендии"],
            ["Деканат", "Справка об обучении"],
            ["Расписание", "Кафедра ВТ"],
            ["Главное меню"],
        ],
        "dean": [
            ["Деканат", "Справка об обучении"],
            ["Как нас найти", "Главное меню"],
        ],
    }

    keyboard = VkKeyboard(one_time=False)

    for index, row in enumerate(layouts[section]):
        if index:
            keyboard.add_line()

        for label in row:
            keyboard.add_button(
                label,
                color=VkKeyboardColor.SECONDARY,
            )

    return keyboard.get_keyboard()


news_cache = {"text": None, "expires": 0}


def save_news(text, seconds):
    news_cache["text"] = text
    news_cache["expires"] = time.monotonic() + seconds
    return text


def get_news():
    if (
        news_cache["text"] is not None
        and time.monotonic() < news_cache["expires"]
    ):
        return news_cache["text"]

    fallback = (
        "Новости ПГУ\n\n"
        "[пусто]\n\n"
        f"{NEWS_URL}"
    )

    try:
        response = requests.get(
            NEWS_URL,
            timeout=(5, 15),
            headers={"User-Agent": "FVTApplicantBot/0.3"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        for element in soup.select(
            "script, style, nav, header, footer"
        ):
            element.decompose()

        content = soup.find("main") or soup
        items = []
        seen = set()

        for link in content.find_all("a", href=True):
            url = urlparse(urljoin(response.url, link["href"]))

            if url.scheme not in {"http", "https"}:
                continue

            if url.hostname not in {"pnzgu.ru", "www.pnzgu.ru"}:
                continue

            if not re.fullmatch(
                r"/news/\d{4}/\d{1,2}/\d{1,2}/\d+/?",
                url.path,
            ):
                continue

            title = " ".join(link.stripped_strings)

            if not title or title.lower() in {
                "подробнее", "читать", "читать далее",
            }:
                continue

            clean_url = url._replace(
                query="", fragment=""
            ).geturl()

            if clean_url in seen:
                continue

            seen.add(clean_url)
            items.append(f"{title[:350]}\n{clean_url}")

            if len(items) == 3:
                break

        if not items:
            return save_news(fallback, 60)

        return save_news(
            "Первые публикации в ленте ПГУ\n\n"
            + "\n\n".join(items),
            300,
        )

    except requests.RequestException as error:
        status = (
            error.response.status_code
            if error.response is not None
            else None
        )
        logging.warning(
            "Ошибка загрузки новостей: %s, HTTP: %s",
            type(error).__name__,
            status,
        )
        return save_news(fallback, 60)


def answer_topic(topic):
    section = "admissions"

    if topic in {"dean_office", "certificate", "location"}:
        section = "dean"
    elif topic in {"about", "scholarships", "schedule", "vt_department"}:
        section = "faq"

    return TOPICS[topic], section


def make_answer(text):
    text = normalize(text)

    if text in {
        "привет", "здравствуйте", "начать", "старт",
        "меню", "главное меню", "помощь", "/start",
    }:
        return WELCOME, "main"

    if text in {"хочу поступить", "поступление", "абитуриент"}:
        return ADMISSIONS_MENU, "admissions"

    if text in {
        "вопросы", "частые вопросы",
        "часто задаваемые вопросы", "faq",
    }:
        lines = ["Что тебя интересует?\n"]

        for number, (question, _) in enumerate(FAQ, start=1):
            lines.append(f"{number}. {question}")

        lines.append("\nНапиши, например, «вопрос 12».")

        return "\n".join(lines), "faq"

    if text in {"новости", "новости пгу", "последние новости"}:
        return get_news(), "main"

    if text == "задать вопрос":
        return "Что хочешь узнать?", "faq"

    match = re.fullmatch(r"(?:вопрос|faq)\s+(\d+)", text)

    if match:
        number = int(match.group(1))

        if 1 <= number <= len(FAQ):
            return answer_topic(FAQ[number - 1][1])

        return "[пусто]", "faq"

    topic = COMMANDS.get(text)

    if topic:
        return answer_topic(topic)

    return "[пусто]", "main"


def send_answer(vk, peer_id, text, keyboard):
    params = {
        "peer_id": peer_id,
        "message": text,
        "keyboard": keyboard,
        "random_id": get_random_id(),
    }

    try:
        vk.messages.send(**params)

    except vk_api.exceptions.ApiError as error:
        if error.code != 912:
            raise

        logging.warning(
            "Клавиатура отключена в настройках сообщества."
        )

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

    keyboards = {
        name: make_keyboard(name)
        for name in ("main", "admissions", "faq", "dean")
    }

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

                answer, section = make_answer(
                    message.get("text")
                )

                try:
                    send_answer(
                        vk,
                        message["peer_id"],
                        answer,
                        keyboards[section],
                    )

                except vk_api.exceptions.ApiError as error:
                    logging.warning(
                        "Не удалось отправить ответ. Код VK: %s",
                        error.code,
                    )

                except requests.RequestException:
                    logging.warning(
                        "Ошибка соединения при отправке ответа."
                    )

        except requests.RequestException:
            logging.warning(
                "Соединение прервано. "
                "Повторное подключение через 5 секунд."
            )
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nБот остановлен.")
    except vk_api.exceptions.ApiError as error:
        print(f"Ошибка VK. Код: {error.code}")
