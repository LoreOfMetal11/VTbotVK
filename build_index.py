'''Перез запуском файл нужно привязать к окружению бота с помощью:
 pip install vk_api requests beautifulsoup4 numpy '''

import rag
from vkbot import TOPICS  # имя файла бота без .py

# RAG: тексты из TOPICS (без коротких меню)
topic_docs = [(text.split("\n")[0], text) for text in TOPICS.values() if len(text) > 80]

# RAG: сборка индекса
count = rag.build_index(topic_docs)
print(f"Готово. Чанков в индексе: {count}")
