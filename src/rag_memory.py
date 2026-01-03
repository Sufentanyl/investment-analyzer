import os
import logging
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
import aiohttp
import asyncio
import json
from datetime import datetime

logger = logging.getLogger(__name__)

# 自定义 Gemini 向量化函数 (为了不占本地内存，调用 API)
class GeminiEmbeddingFunction(EmbeddingFunction):
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={self.api_key}"

    def __call__(self, input: Documents) -> Embeddings:
        # ChromaDB 是同步调用的，这里我们需要用同步方式请求，或者用 asyncio.run
        # 为了简单稳定，这里用 requests 或者 asyncio.run 包装
        return [self._get_embedding(text) for text in input]

    def _get_embedding(self, text):
        import requests # 局部引入，防止依赖问题
        headers = {'Content-Type': 'application/json'}
        data = {
            "model": "models/text-embedding-004",
            "content": {"parts": [{"text": text}]}
        }
        try:
            resp = requests.post(self.url, headers=headers, json=data, timeout=10)
            if resp.status_code == 200:
                return resp.json()['embedding']['values']
            else:
                logger.error(f"Embedding API Error: {resp.text}")
                return [0.0] * 768 # 返回空向量避免崩溃
        except Exception as e:
            logger.error(f"Embedding Failed: {e}")
            return [0.0] * 768

class RAGMemory:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        if not self.gemini_key:
            logger.warning("⚠️ 未配置 GEMINI_API_KEY，记忆模块无法使用向量化，将失效。")
            self.collection = None
            return

        # 初始化持久化数据库
        self.client = chromadb.PersistentClient(path="/app/data/chroma_db")
        
        # 使用 Gemini API 作为向量生成器 (云端计算，省 VPS 内存)
        self.embedding_fn = GeminiEmbeddingFunction(api_key=self.gemini_key)
        
        self.collection = self.client.get_or_create_collection(
            name="news_history",
            embedding_function=self.embedding_fn
        )
        logger.info(f"🧠 RAG 记忆模块已加载，当前历史记录: {self.collection.count()} 条")

    def add_memory(self, news_title: str, summary: str, influence: str, reason: str):
        """
        存入记忆：新闻 + 当时的判断
        """
        if not self.collection: return
        
        # 构造存入的内容：标题 + 简要 + 结论
        document = f"标题: {news_title}\n内容: {summary}"
        
        # 存入元数据
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "influence": influence,
            "reason": reason[:200] # 只存理由的前200字
        }
        
        try:
            self.collection.add(
                documents=[document],
                metadatas=[metadata],
                ids=[f"news_{datetime.now().timestamp()}"]
            )
            logger.info("💾 已将该事件存入长期记忆库")
        except Exception as e:
            logger.error(f"存储记忆失败: {e}")

    def recall_similar_events(self, current_news: str, n_results=2) -> str:
        """
        回溯历史：寻找最相似的 N 个事件
        """
        if not self.collection or self.collection.count() == 0:
            return "暂无历史参考数据。"

        try:
            results = self.collection.query(
                query_texts=[current_news],
                n_results=n_results
            )
            
            if not results['documents'][0]:
                return "未找到相似的历史事件。"

            # 格式化输出给 LLM 看
            history_text = ""
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i]
                history_text += f"""
--- 📜 历史案例 {i+1} ---
{doc}
【当时判断】: {meta.get('influence')}
【当时逻辑】: {meta.get('reason')}
-----------------------
"""
            return history_text

        except Exception as e:
            logger.error(f"记忆检索失败: {e}")
            return "记忆检索出错。"