import os
import logging
import aiohttp
import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from collections import OrderedDict

logger = logging.getLogger(__name__)

class InformationGapDetector:
    def __init__(self):
        # 1. 加载 SerpApi Keys
        keys_str = os.getenv('SERPAPI_KEY', '')
        self.api_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
        self.current_key_idx = 0

        # 2. 加载 Qwen 配置 (用于把英文标题转成中文搜索词)
        self.qwen_key = os.getenv("QWEN_API_KEY")
        self.qwen_base = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.qwen_model = "qwen-max" # 用 Max 保证理解准确，或者 plus 也可以

        # 3. 缓存 (🔥 修复: 改用 OrderedDict 限制大小，防止内存泄漏)
        self.cache = OrderedDict()
        self.max_cache_size = 1000  # 最大缓存 1000 条
        self.cache_lock = asyncio.Lock()  # 🔥 修复: 并发安全

        # 4. 🔥 修复: 复用 aiohttp ClientSession
        self._session = None
        
        if not self.api_keys:
            logger.warning("⚠️ 未配置 SERPAPI_KEY，信息差检测将默认全部通过")

    def _get_api_key(self):
        if not self.api_keys: return None
        key = self.api_keys[self.current_key_idx]
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        return key

    async def _get_session(self):
        """🔥 修复: 复用 ClientSession"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """🔥 新增: 清理资源"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def detect_information_gap(self, news_list: list) -> list:
        """
        核心入口：检测新闻是否在国内已有报道
        """
        if not self.api_keys or not news_list:
            return news_list

        gap_news = []
        tasks = []
        for news in news_list:
            tasks.append(self._check_single_news(news))
        
        results = await asyncio.gather(*tasks)
        
        for news, is_gap in zip(news_list, results):
            if is_gap:
                gap_news.append(news)
        
        return gap_news

    async def _check_single_news(self, news) -> bool:
        """
        流程：
        1. 查缓存
        2. 将英文标题转化为中文搜索关键词 (调用 Qwen)
        3. 去 Google News (中国区) 搜索这些中文词
        4. 有结果 -> 无信息差；无结果 -> 有信息差
        """
        title = news.get('title', '')
        if not title: return False

        # 1. 查缓存 (🔥 修复: 添加并发安全)
        news_hash = hashlib.md5(title.encode()).hexdigest()

        async with self.cache_lock:
            if news_hash in self.cache:
                entry = self.cache[news_hash]
                # 🔥 修复: 移动到末尾（LRU）
                self.cache.move_to_end(news_hash)
                if datetime.now() - entry['timestamp'] < timedelta(hours=4):
                    return entry['has_gap']

        # 2. 获取中文搜索词 (关键步骤!)
        # 如果标题里本身就有中文，直接用；如果是英文，找 Qwen 翻译出核心词
        search_query = title
        if not self._is_mostly_chinese(title):
            cn_keywords = await self._get_chinese_keywords(title)
            if cn_keywords:
                search_query = cn_keywords
                logger.info(f"🔀 关键词转换: '{title[:20]}...' -> '{search_query}'")

        # 3. 执行搜索
        api_key = self._get_api_key()
        if not api_key: return True

        params = {
            "engine": "google_news",
            "q": search_query,       # 搜中文词！
            "gl": "cn",              # 地区：中国
            "hl": "zh-cn",           # 语言：简体中文
            "api_key": api_key,
            "num": 5
        }

        try:
            # 🔥 修复: 使用复用的 session
            session = await self._get_session()
            async with session.get("https://serpapi.com/search", params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()

                    # 判断逻辑：只要有结果，就说明国内报了
                    has_coverage = False
                    if "news_results" in data and len(data["news_results"]) > 0:
                        has_coverage = True
                        source = data['news_results'][0].get('source', {}).get('title', '未知媒体')
                        logger.info(f"⚖️ 国内已报道: {search_query} -> 来源: {source}")
                    else:
                        logger.info(f"💎 确认信息差: {search_query} (国内暂无)")

                    # 🔥 修复: 限制缓存大小，防止内存泄漏
                    async with self.cache_lock:
                        if len(self.cache) >= self.max_cache_size:
                            self.cache.popitem(last=False)  # 删除最旧的
                        self.cache[news_hash] = {'has_gap': not has_coverage, 'timestamp': datetime.now()}

                    return not has_coverage
                else:
                    logger.warning(f"SerpApi 异常: {response.status}")
                    return True
        except Exception as e:
            logger.error(f"信息差检测出错: {e}")
            return True

    async def _get_chinese_keywords(self, english_title: str) -> str:
        """
        调用 Qwen 将英文标题提取为中文搜索关键词
        例如: "DeepSeek Debuts New AI Models" -> "DeepSeek 新模型"
        """
        if not self.qwen_key: return english_title

        prompt = f"""
请将以下财经新闻标题提取为能在百度/谷歌新闻搜索到的【中文搜索关键词】。
要求：
1. 只保留核心实体（公司名、人名）和核心事件。
2. 不要直译，要用中国媒体常用的表述。
3. 只要返回关键词，不要其他废话。
4. 长度控制在 3-4 个词以内。

标题: "{english_title}"
关键词:
"""
        try:
            url = f"{self.qwen_base}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.qwen_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.qwen_model,
                "messages": [{"role": "user", "content": prompt}]
            }
            # 🔥 修复: 使用复用的 session
            session = await self._get_session()
            async with session.post(url, headers=headers, json=data, timeout=10) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    return res['choices'][0]['message']['content'].strip().replace('"', '')
        except Exception as e:
            logger.warning(f"Qwen 翻译失败: {e}")
        return english_title

    def _is_mostly_chinese(self, text):
        zh_count = len([c for c in text if '\u4e00' <= c <= '\u9fa5'])
        return zh_count > len(text) * 0.3