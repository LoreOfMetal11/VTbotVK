'''Для добавления информации в бота нужно 
создать папку knowledge/ и класть в неё .md или .txt, по одному файлу на тему 
(проходные баллы, документы, учебные планы, расписание). 
Абзацы короткие, через пустую строку, заголовок в первой строке, факты проверерять вручную.'''

import json
import logging
from pathlib import Path

import numpy as np
import requests

# RAG: настройки
EMBED_URL = "http://127.0.0.1:11434/api/embed"  # Ollama
EMBED_MODEL = "bge-m3"
EMBED_TIMEOUT = (5, 60)  # таймауты, сек
KNOWLEDGE_DIR = Path("knowledge")  # папка с .md/.txt
INDEX_DIR = Path("rag_index")  # папка индекса
CHUNK_WORDS = 200  # размер чанка, слов
TOP_K = 6  # число чанков в ответе
MIN_SCORE = 0.45  # порог релевантности. Можно понастраивать. 

_chunks = []
_vectors = None


# RAG: эмбеддинги через Ollama
def embed(texts):
    response = requests.post(
        EMBED_URL,
        json={"model": EMBED_MODEL, "input": texts, "keep_alive": -1},
        timeout=EMBED_TIMEOUT,
    )
    response.raise_for_status()
    vectors = np.array(response.json()["embeddings"], dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-9)


# RAG: разбиение текста на чанки
def split_text(title, text):
    chunks, current, words = [], [], 0
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        size = len(paragraph.split())
        if current and words + size > CHUNK_WORDS:
            chunks.append(f"{title}\n" + "\n\n".join(current))
            current, words = [], 0
        current.append(paragraph)
        words += size
    if current:
        chunks.append(f"{title}\n" + "\n\n".join(current))
    return chunks


# RAG: сбор документов из папки
def read_knowledge_dir():
    docs = []
    for path in sorted(KNOWLEDGE_DIR.glob("*")):
        if path.suffix.lower() in {".md", ".txt"}:
            docs.append((path.stem, path.read_text(encoding="utf-8")))
    return docs


# RAG: построение индекса
def build_index(extra_docs=()):
    docs = list(extra_docs) + read_knowledge_dir()
    chunks = [c for title, text in docs for c in split_text(title, text)]
    if not chunks:
        raise ValueError("Нет документов для индекса")
    vectors = np.vstack([embed(chunks[i:i + 16]) for i in range(0, len(chunks), 16)])
    INDEX_DIR.mkdir(exist_ok=True)
    (INDEX_DIR / "chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    np.save(INDEX_DIR / "vectors.npy", vectors)
    return len(chunks)


# RAG: загрузка индекса
def load_index():
    global _chunks, _vectors
    try:
        _chunks = json.loads((INDEX_DIR / "chunks.json").read_text(encoding="utf-8"))
        _vectors = np.load(INDEX_DIR / "vectors.npy")
        return True
    except (OSError, ValueError):
        logging.warning("RAG-индекс не найден. Запусти build_index.py")
        return False


# RAG: проверка готовности индекса
def is_ready():
    return _vectors is not None


# RAG: поиск релевантных чанков
def retrieve(question):
    if _vectors is None:
        return []
    query = embed([question])[0]
    scores = _vectors @ query
    best = np.argsort(scores)[::-1][:TOP_K]
    return [(float(scores[i]), _chunks[i]) for i in best if scores[i] >= MIN_SCORE]
