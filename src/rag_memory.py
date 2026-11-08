import os
import re
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb import Documents, EmbeddingFunction, Embeddings
    HAS_CHROMADB = True
except ImportError:
    chromadb = None
    HAS_CHROMADB = False


class RAGMemory:
    """
    轻量级事件记忆模块 (ARM64 友好版)
    - 默认使用 SQLite 本地持久化记忆库 + 关键词/Token 相似度检索（零额外内存开销，秒级启动）
    - 若环境安装了 chromadb 且显式开启 USE_CHROMADB=true，则兼容 ChromaDB
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            if os.path.exists("/app/data") or os.access("/app", os.W_OK):
                db_path = "/app/data/investment.db"
            else:
                db_path = os.path.join(os.getcwd(), "data", "investment.db")
        self.db_path = db_path
        self.collection = None
        self._init_sqlite_memory()

    def _init_sqlite_memory(self):
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rag_memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        news_title TEXT NOT NULL,
                        summary TEXT,
                        influence TEXT,
                        reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.commit()
            logger.info("🧠 轻量级 SQLite RAG 记忆模块已就绪")
        except Exception as e:
            logger.warning(f"初始化 SQLite 记忆表失败: {e}")

    def add_memory(self, news_title: str, summary: str, influence: str, reason: str):
        """存入记忆：新闻 + 当时的判断"""
        if not news_title:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO rag_memories (news_title, summary, influence, reason, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        news_title,
                        summary or "",
                        influence or "neutral",
                        (reason or "")[:300],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"存储记忆失败: {e}")

    def _tokenize(self, text: str) -> set:
        if not text:
            return set()
        en_tokens = set(re.findall(r"[a-z0-9]{2,}", text.lower()))
        zh_chars = [c for c in text if "\u4e00" <= c <= "\u9fa5"]
        zh_bigrams = {zh_chars[i] + zh_chars[i + 1] for i in range(len(zh_chars) - 1)} if len(zh_chars) >= 2 else set(zh_chars)
        return en_tokens | zh_bigrams

    def recall_similar_events(self, current_news: str, n_results: int = 2) -> str:
        """回溯历史：寻找最相似的 N 个历史事件"""
        query_tokens = self._tokenize(current_news)
        if not query_tokens:
            return "暂无历史参考数据。"

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT news_title, summary, influence, reason, created_at
                    FROM rag_memories
                    ORDER BY id DESC
                    LIMIT 200
                    """
                )
                rows = cursor.fetchall()

            if not rows:
                return "暂无历史参考数据。"

            scored = []
            for row in rows:
                doc_text = f"{row['news_title']} {row['summary']}"
                doc_tokens = self._tokenize(doc_text)
                if not doc_tokens:
                    continue
                overlap = len(query_tokens & doc_tokens)
                if overlap > 0:
                    sim = overlap / max(1, min(len(query_tokens), len(doc_tokens)))
                    scored.append((sim, row))

            if not scored:
                return "未找到相似的历史事件。"

            scored.sort(key=lambda x: x[0], reverse=True)
            top_items = scored[:n_results]

            history_text = ""
            for i, (_, meta) in enumerate(top_items, 1):
                history_text += (
                    f"\n--- 📜 历史案例 {i} ---\n"
                    f"标题: {meta['news_title']}\n"
                    f"内容: {meta['summary']}\n"
                    f"【当时判断】: {meta['influence']}\n"
                    f"【当时逻辑】: {meta['reason']}\n"
                    f"-----------------------\n"
                )
            return history_text
        except Exception as e:
            logger.error(f"记忆检索失败: {e}")
            return "记忆检索出错。"