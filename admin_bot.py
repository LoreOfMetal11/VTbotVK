"""Закрытая панель: python admin_bot.py. Основной vkbot.py не изменяется."""
import logging
import re
import threading
import time
from getpass import getpass
import vkbot as bot
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

TOPICS = bot.TOPICS
LAYOUTS = bot.LAYOUTS
ALIASES = bot.ALIASES
FAQ = bot.FAQ
COMMANDS = bot.COMMANDS
WELCOME = bot.WELCOME
normalize = bot.normalize
get_news = bot.get_news

# Динамическое меню и редактор. Исходные словари используются только при миграции.
import json
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import urlsplit

DB_PATH = Path(__file__).resolve().with_name("bot.db")
ADMIN_FILE = Path(__file__).resolve().with_name("admin_ids.txt")
ADMIN_SESSIONS = {}
USER_SESSIONS = {}
PAGE_SIZE = 6
ADMIN_PAGE_SIZE = 10
RESERVED = {
    "главное меню", "назад", "дальше", "предыдущая", "отмена", "сохранить",
    "да", "нет", "привет", "начать", "старт", "помощь", "здравствуйте",
    "меню", "вопросы", "частые вопросы", "faq", "задать вопрос",
}
ADMIN_ACTIONS = [
    ["Добавить кнопку", "Изменить кнопку"],
    ["Скрыть / показать", "Удалить кнопку"],
    ["Порядок кнопок", "Предпросмотр"],
    ["Выйти из панели"],
]


def db_connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def init_storage():
    with db_connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sections (
                id TEXT PRIMARY KEY, title TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section TEXT NOT NULL, label TEXT NOT NULL,
                kind TEXT NOT NULL, value TEXT NOT NULL DEFAULT '',
                target TEXT, aliases TEXT NOT NULL DEFAULT '[]',
                position INTEGER NOT NULL, visible INTEGER NOT NULL DEFAULT 1,
                deleted INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actor INTEGER NOT NULL, action TEXT NOT NULL,
                item_id INTEGER, before_json TEXT, after_json TEXT
            );
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
        """)
        if db.execute("SELECT 1 FROM metadata WHERE key='seeded'").fetchone():
            return
        titles = {'main':'Главное меню','about':'О кафедре','programs':'Направления обучения','skills':'Навыки и технологии','admissions':'Поступление','links':'Полезные ссылки'}
        for section in LAYOUTS:
            db.execute("INSERT OR IGNORE INTO sections VALUES (?, ?)", (section, titles.get(section,section)))
        for section, rows in LAYOUTS.items():
            for pos, label in enumerate(label for row in rows for label in row):
                if normalize(label) == 'главное меню':
                    continue
                topic = COMMANDS.get(normalize(label))
                target = None
                if normalize(label) == 'новости вт':
                    kind, value = 'news', ''
                elif topic in {'about', 'skills', 'programs', 'admissions', 'links'}:
                    kind, value, target = 'submenu', TOPICS[topic], topic
                else:
                    if topic is None:
                        raise ValueError(f'Нет обработчика исходной кнопки: {label}')
                    value = TOPICS[topic]
                    kind = 'link' if value.startswith(('https://', 'http://')) and '\n' not in value else 'text'
                aliases = list(ALIASES.get(topic, []))
                aliases.extend(question for question, key in FAQ if key == topic)
                db.execute(
                    'INSERT INTO items(section,label,kind,value,target,aliases,position) VALUES (?,?,?,?,?,?,?)',
                    (section,label,kind,value,target,json.dumps(aliases,ensure_ascii=False),pos),
                )
        db.execute("INSERT INTO metadata VALUES ('seeded', '1')")


def read_items(section=None, public=False):
    sql = 'SELECT * FROM items WHERE deleted=0'
    args = []
    if section is not None:
        sql += ' AND section=?'
        args.append(section)
    if public:
        sql += ' AND visible=1'
    sql += ' ORDER BY section,position,id' if section is None else ' ORDER BY position,id'
    with db_connect() as db:
        return [dict(r) for r in db.execute(sql, args)]


def sections():
    with db_connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM sections ORDER BY rowid')]


def keyboard_rows(rows):
    k = VkKeyboard(one_time=False)
    for index, row in enumerate(rows):
        if index:
            k.add_line()
        for label in row:
            k.add_button(label, color=VkKeyboardColor.SECONDARY)
    return k.get_keyboard()


def public_keyboard(user_id):
    state = USER_SESSIONS.setdefault(user_id, {'section': 'main', 'page': 0})
    items = read_items(state['section'], public=True)
    last = max(0, (len(items)-1)//PAGE_SIZE)
    state['page'] = max(0, min(state['page'], last))
    chunk = items[state['page']*PAGE_SIZE:(state['page']+1)*PAGE_SIZE]
    labels = [i['label'] for i in chunk]
    rows = [labels[i:i+2] for i in range(0, len(labels), 2)]
    nav = []
    if state['page']:
        nav.append('Предыдущая')
    if state['page'] < last:
        nav.append('Дальше')
    if nav:
        rows.append(nav)
    if state['section'] != 'main':
        rows.append(['Главное меню'])
    return keyboard_rows(rows or [['Главное меню']])


def is_reachable(section):
    reachable = {'main'}
    active = read_items(public=True)
    while True:
        found = reachable | {i['target'] for i in active if i['kind']=='submenu' and i['section'] in reachable}
        if found == reachable:
            return section in reachable
        reachable = found


def public_answer(user_id, text):
    command = normalize(text)
    state = USER_SESSIONS.setdefault(user_id, {'section':'main','page':0})
    if not is_reachable(state['section']):
        state.update(section='main',page=0)
    if command in {'привет','здравствуйте','начать','старт','меню','главное меню','помощь','/start'}:
        state.update(section='main',page=0)
        return WELCOME, public_keyboard(user_id)
    if command in {'дальше','предыдущая'}:
        state['page'] += 1 if command == 'дальше' else -1
        return 'Выбери нужный пункт.', public_keyboard(user_id)
    if command in {'faq','вопросы','частые вопросы','задать вопрос','часто задаваемые вопросы'}:
        available = [i['label'] for i in read_items(state['section'], public=True)]
        return 'Выбери тему на кнопках:\n\n'+'\n'.join(available), public_keyboard(user_id)
    candidates = [i for i in read_items(state['section'],public=True)
                  if command == normalize(i['label']) or command in [normalize(a) for a in json.loads(i['aliases'])]]
    if not candidates:
        candidates = [i for i in read_items(public=True) if is_reachable(i['section']) and
                      (command == normalize(i['label']) or command in [normalize(a) for a in json.loads(i['aliases'])])]
    if not candidates:
        return '[пусто]', public_keyboard(user_id)
    unique = {(i['kind'],i['value'],i['target']) for i in candidates}
    if len(unique) > 1:
        return 'Открой нужный раздел и выбери кнопку в нём.', public_keyboard(user_id)
    item = candidates[0]
    if item['kind'] == 'news':
        answer = get_news()
    else:
        answer = item['value'] or 'Выбери нужный пункт.'
    if item['kind']=='submenu':
        state.update(section=item['target'],page=0)
    return answer, public_keyboard(user_id)


def admin_reply(text, rows=None):
    return text, keyboard_rows(rows or [['Отмена']])


def admin_home(user_id, message='Панель управления. Выбери действие.'):
    ADMIN_SESSIONS[user_id] = {'mode':'home'}
    return admin_reply(message, ADMIN_ACTIONS)


def choose_sections(user_id, next_mode):
    state = ADMIN_SESSIONS[user_id]
    state.update(mode=next_mode, choices=sections())
    lines = [f"{n}. {s['title']} ({s['id']})" for n,s in enumerate(state['choices'],1)]
    return admin_reply('Введи номер раздела:\n\n'+'\n'.join(lines))


def show_admin_items(user_id):
    state = ADMIN_SESSIONS[user_id]
    items = read_items()
    last = max(0,(len(items)-1)//ADMIN_PAGE_SIZE)
    state['page'] = max(0,min(state.get('page',0),last))
    start = state['page']*ADMIN_PAGE_SIZE
    state['choices'] = items[start:start+ADMIN_PAGE_SIZE]
    lines = [f"{n}. {i['label']} / {i['section']}" + (' [скрыта]' if not i['visible'] else '')
             for n,i in enumerate(state['choices'],1)]
    return admin_reply('Введи номер кнопки:\n\n'+'\n'.join(lines)+f"\n\nСтраница {state['page']+1} из {last+1}",
                       [['Предыдущая','Дальше'],['Отмена']])


def get_choice(state, text):
    try:
        number = int(text)
        if not 1 <= number <= len(state['choices']):
            return None
        return state['choices'][number-1]
    except ValueError:
        return None


def valid_label(label):
    normalized = normalize(label)
    if not 1 <= len(label) <= 40 or not normalized:
        return 'Название должно содержать от 1 до 40 символов.'
    if '\n' in label or normalized in RESERVED or label.startswith('/'):
        return 'Это название зарезервировано или содержит перенос строки.'
    return None


def valid_value(kind,value):
    if not value.strip() or len(value)>3500:
        return 'Ответ должен содержать от 1 до 3500 символов.'
    if kind=='link':
        try:
            parsed = urlsplit(value)
            if parsed.scheme not in {'http','https'} or not parsed.hostname or any(c.isspace() for c in value):
                return 'Нужна одна ссылка, начинающаяся с https:// или http://.'
        except ValueError:
            return 'Некорректная ссылка.'
    return None


def creates_cycle(target,parent):
    reachable = {target}
    all_items = read_items()
    while True:
        found = reachable | {i['target'] for i in all_items if i['kind']=='submenu' and i['section'] in reachable}
        if found == reachable:
            return parent in reachable
        reachable = found


def preview_draft(user_id):
    state = ADMIN_SESSIONS[user_id]
    draft = state['draft']
    state['mode'] = 'confirm'
    text = (f"Действие: {state['operation']}\nНазвание: {draft['label']}\n"
            f"Раздел: {draft['section']}\nТип: {draft['kind']}\n"
            f"Позиция: {draft['position']}\nВидимость: {'да' if draft['visible'] else 'нет'}\n\n"
            + (draft['value'] if draft['kind']!='news' else 'Специальное действие: загрузка новостей.'))
    return admin_reply(text+'\n\nСохранить изменения?', [['Сохранить','Отмена']])


def commit_draft(user_id):
    if not is_admin(user_id):
        raise PermissionError('Нет доступа')
    state = ADMIN_SESSIONS[user_id]
    draft = state['draft']
    with db_connect() as db:
        db.execute('BEGIN IMMEDIATE')
        before = None
        if draft.get('id') is not None:
            row = db.execute('SELECT * FROM items WHERE id=? AND deleted=0',(draft['id'],)).fetchone()
            if row is None or row['version'] != draft['version']:
                return 'Кнопка уже изменена другим администратором. Начни действие заново.'
            before = dict(row)
        if draft['deleted'] and draft['kind']=='submenu':
            if db.execute('SELECT 1 FROM items WHERE section=? AND deleted=0',(draft['target'],)).fetchone():
                return 'В подменю есть кнопки. Сначала перемести или удали их либо просто скрой подменю.'
        error = valid_label(draft['label'])
        if error:
            return error
        if not draft['deleted']:
            duplicates = db.execute('SELECT id,label FROM items WHERE section=? AND deleted=0',(draft['section'],)).fetchall()
            if any(r['id']!=draft.get('id') and normalize(r['label'])==normalize(draft['label']) for r in duplicates):
                return 'В этом разделе уже есть кнопка с таким названием.'
        if draft['kind']=='submenu' and draft.get('target') and creates_cycle(draft['target'],draft['section']):
            return 'Нельзя переместить подменю внутрь самого себя или его дочернего раздела.'
        if draft.get('id') is None:
            if draft['kind']=='submenu':
                draft['target'] = 'custom_'+uuid.uuid4().hex
                db.execute('INSERT INTO sections VALUES (?,?)',(draft['target'],draft['label']))
            cursor = db.execute('INSERT INTO items(section,label,kind,value,target,aliases,position,visible,deleted) VALUES (?,?,?,?,?,?,?,?,?)',
                tuple(draft.get(k) for k in ['section','label','kind','value','target','aliases','position','visible','deleted']))
            draft['id'] = cursor.lastrowid
        else:
            db.execute('UPDATE items SET section=?,label=?,value=?,position=?,visible=?,deleted=?,version=version+1 WHERE id=?',
                       tuple(draft[k] for k in ['section','label','value','position','visible','deleted','id']))
            if draft['kind']=='submenu':
                db.execute('UPDATE sections SET title=? WHERE id=?',(draft['label'],draft['target']))
        after = dict(db.execute('SELECT * FROM items WHERE id=?',(draft['id'],)).fetchone())
        db.execute('INSERT INTO audit(actor,action,item_id,before_json,after_json) VALUES (?,?,?,?,?)',
                   (user_id,state['operation'],draft['id'],json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False)))
    return 'Изменения сохранены. Они появятся в следующих ответах бота.'


def admin_answer(user_id,text):
    if not is_admin(user_id):
        ADMIN_SESSIONS.pop(user_id, None)
        return '[пусто]', public_keyboard(user_id)
    command = normalize(text)
    state = ADMIN_SESSIONS.get(user_id)
    if command in {'/админ','/admin'} or command=='отмена':
        return admin_home(user_id)
    if command=='выйти из панели':
        ADMIN_SESSIONS.pop(user_id,None)
        USER_SESSIONS[user_id]={'section':'main','page':0}
        return WELCOME,public_keyboard(user_id)
    if state is None:
        return admin_home(user_id)
    mode = state['mode']
    if mode=='home':
        actions = {'изменить кнопку':'edit','скрыть / показать':'visibility','удалить кнопку':'delete','порядок кнопок':'order'}
        if command=='добавить кнопку':
            state['operation']='add'
            return choose_sections(user_id,'add_section')
        if command in actions:
            state.update(mode='select_item',operation=actions[command],page=0)
            return show_admin_items(user_id)
        if command=='предпросмотр':
            ADMIN_SESSIONS.pop(user_id,None)
            USER_SESSIONS[user_id]={'section':'main','page':0}
            return 'Пользовательское меню. Вернуться в редактор: /админ',public_keyboard(user_id)
        return admin_home(user_id,'Выбери действие на кнопках.')
    if mode in {'add_section','move_section'}:
        chosen = get_choice(state,text)
        if chosen is None:
            return admin_reply('Введи номер раздела из списка или нажми «Отмена».')
        if mode=='add_section':
            state['draft']={'section':chosen['id'],'value':'','target':None,'aliases':'[]','position':len(read_items(chosen['id'])),'visible':1,'deleted':0}
            state['mode']='add_label'
            return admin_reply('Напиши название кнопки (до 40 символов).')
        state['draft']['section']=chosen['id']
        return preview_draft(user_id)
    if mode=='add_label' or mode=='rename':
        error = valid_label(text)
        if error:
            return admin_reply(error)
        state['draft']['label']=text
        if mode=='rename':
            return preview_draft(user_id)
        state['mode']='add_kind'
        return admin_reply('Выбери тип кнопки.',[['Текст','Ссылка','Подменю'],['Отмена']])
    if mode=='add_kind':
        kind = {'текст':'text','ссылка':'link','подменю':'submenu'}.get(command)
        if kind is None:
            return admin_reply('Выбери: Текст, Ссылка или Подменю.',[['Текст','Ссылка','Подменю'],['Отмена']])
        state['draft']['kind']=kind
        state['mode']='value'
        return admin_reply('Пришли ссылку.' if kind=='link' else 'Пришли текст ответа.' if kind=='text' else 'Пришли приветственный текст для нового подменю.')
    if mode=='value':
        error=valid_value(state['draft']['kind'],text)
        if error:
            return admin_reply(error)
        state['draft']['value']=text
        return preview_draft(user_id)
    if mode=='select_item':
        if command in {'дальше','предыдущая'}:
            state['page'] += 1 if command=='дальше' else -1
            return show_admin_items(user_id)
        chosen=get_choice(state,text)
        if chosen is None:
            return admin_reply('Введи номер кнопки из списка или нажми «Отмена».')
        state['draft']=chosen.copy()
        operation=state['operation']
        if operation=='visibility':
            state['draft']['visible']=1-chosen['visible']
            return preview_draft(user_id)
        if operation=='delete':
            state['draft']['deleted']=1
            return preview_draft(user_id)
        if operation=='order':
            state['mode']='position'
            return admin_reply('Введи позицию: целое число от 0 до 10000. Меньшие позиции идут раньше; при совпадении - по ID.')
        state['mode']='edit_field'
        return admin_reply('Что изменить?', [['Название','Ответ'],['Переместить'],['Отмена']])
    if mode=='edit_field':
        if command=='название':
            state['mode']='rename'
            return admin_reply('Напиши новое название.')
        if command=='ответ':
            if state['draft']['kind']=='news':
                return admin_reply('Новости - специальное действие. Можно менять только название, положение и видимость.')
            state['mode']='value'
            return admin_reply('Пришли новый текст или ссылку.')
        if command=='переместить':
            return choose_sections(user_id,'move_section')
        return admin_reply('Выбери поле.',[['Название','Ответ'],['Переместить'],['Отмена']])
    if mode=='position':
        if not text.isdecimal() or not 0<=int(text)<=10000:
            return admin_reply('Нужна позиция от 0 до 10000.')
        state['draft']['position']=int(text)
        return preview_draft(user_id)
    if mode=='confirm':
        if command!='сохранить':
            return admin_reply('Нажми «Сохранить» или «Отмена».',[['Сохранить','Отмена']])
        return admin_home(user_id,commit_draft(user_id))
    return admin_home(user_id)


def route_message(user_id, text):
    try:
        text = (text or '').strip()
        command = normalize(text)
        allowed = is_admin(user_id)
        if not allowed:
            ADMIN_SESSIONS.pop(user_id, None)
        if allowed and (command in {'/админ', '/admin'} or user_id in ADMIN_SESSIONS):
            return admin_answer(user_id, text)
        if command in {'/админ', '/admin'}:
            return '[пусто]', public_keyboard(user_id)
        answer, kb = public_answer(user_id, text)
        if answer == '[пусто]' and text and not text.startswith('/'):
            # Скрытые и удалённые кнопки не отправляем в LLM.
            with db_connect() as db:
                known = [dict(r) for r in db.execute('SELECT label,aliases FROM items')]
            blocked = command in COMMANDS or any(
                command == normalize(i['label']) or command in [normalize(a) for a in json.loads(i['aliases'])]
                for i in known
            )
            if not blocked:
                answer = None
        return answer, kb
    except PermissionError:
        ADMIN_SESSIONS.pop(user_id, None)
        return '[пусто]', public_keyboard(user_id)
    except sqlite3.Error:
        logging.exception('Ошибка базы данных')
        ADMIN_SESSIONS.pop(user_id, None)
        return 'Не удалось сохранить или прочитать данные. Попробуй позже.', keyboard_rows([['Главное меню']])


def is_admin(user_id):
    try:
        ids = set()
        for line in ADMIN_FILE.read_text(encoding="utf-8-sig").splitlines():
            value = line.split("#", 1)[0].strip()
            if not value:
                continue
            if not value.isascii() or not value.isdecimal() or int(value) <= 0:
                logging.warning("Некорректный файл доступа: панель отключена.")
                return False
            ids.add(int(value))
        return user_id in ids
    except (OSError, UnicodeError):
        return False

def main():
    init_storage()
    if bot.RAG_ENABLED:
        bot.rag.load_index()
    token = getpass("Ключ сообщества: ").strip()
    if not token:
        print("Ключ не введён.")
        return
    try:
        group_id = int(input("ID сообщества: ").strip())
        if group_id <= 0:
            raise ValueError
    except ValueError:
        print("Введи положительный числовой ID сообщества.")
        return
    session = bot.vk_api.VkApi(token=token)
    vk = session.get_api()
    keyboards = {name: bot.make_keyboard(name) for name in bot.LAYOUTS}
    original_send = bot.send_answer
    def send(vk, peer_id, text, keyboard):
        if threading.current_thread() is not threading.main_thread():
            # Поздний ответ LLM не меняет текущую клавиатуру пользователя.
            return vk.messages.send(peer_id=peer_id, message=text, random_id=bot.get_random_id())
        return original_send(vk, peer_id, text, keyboard)
    bot.send_answer = send
    for _ in range(bot.LLM_WORKERS):
        threading.Thread(target=bot.llm_worker, args=(vk, keyboards), daemon=True).start()
    print("Бот запущен. Для остановки нажми Ctrl+C.")
    while True:
        try:
            for event in bot.VkBotLongPoll(session, group_id).listen():
                if event.type != bot.VkBotEventType.MESSAGE_NEW:
                    continue
                msg = event.object.message
                if msg.get("out") or msg["peer_id"] != msg["from_id"]:
                    continue
                uid = msg["from_id"]
                try:
                    if bot.is_spam(uid):
                        if bot.spam_warning_needed(uid):
                            send(vk, uid, bot.SPAM_WARNING, public_keyboard(uid))
                        continue
                    answer, kb = route_message(uid, msg.get("text"))
                    if answer is None:
                        bot.handle_llm_request(vk, uid, msg.get("text"), {"main": kb})
                    else:
                        send(vk, uid, answer, kb)
                except bot.vk_api.exceptions.ApiError as error:
                    logging.warning("Ошибка отправки VK: %s", error.code)
                except bot.requests.RequestException:
                    logging.warning("Ошибка соединения при отправке ответа.")
        except bot.requests.RequestException:
            logging.warning("Соединение прервано. Повтор через 5 секунд.")
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nБот остановлен.")
    except bot.vk_api.exceptions.ApiError as error:
        print(f"Ошибка VK: {error.code}")

