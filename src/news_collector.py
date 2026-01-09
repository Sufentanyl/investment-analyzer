import aiohttp
import asyncio
import feedparser
import logging
from datetime import datetime
import os
import time
from typing import List, Dict, Any
import newspaper # 使用 newspaper3k 替代 Chrome
import hashlib

logger = logging.getLogger(__name__)

class AdvancedNewsCollector:
    def __init__(self):
        self.newsapi_key = os.getenv('NEWSAPI_KEY')
        self.serpapi_key = os.getenv('SERPAPI_KEY')
        self._session = None
        self._newspaper_config = newspaper.Config()
        self._newspaper_config.browser_user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        self._newspaper_config.request_timeout = 10
        
        # 移除 browser_ws，不再需要
        
        self.rss_sources = {
            'bloomberg': 'https://feeds.bloomberg.com/markets/news.rss',
            'reuters_biz': 'http://feeds.reuters.com/reuters/businessNews',
        }
        
        self.investment_keywords = {
            'china_related': ['china', 'chinese', 'beijing', 'shanghai', 'hk', 'hong kong', 'taiwan'],
            'global_macro': ['fed', 'federal reserve', 'rate cut', 'rate hike', 'inflation', 'cpi', 'oil', 'gold'],
            'key_sectors': ['semiconductor', 'chip', 'ai', 'nvidia', 'tesla', 'ev', 'battery']
        }

    async def collect_international_news(self) -> List[Dict[str, Any]]:
        all_news = []
        
        # 1. SerpApi
        if self.serpapi_key:
            all_news.extend(await self._collect_from_serpapi())
        
        # 2. RSS
        all_news.extend(await self._collect_from_rss())
        
        # 3. 去重 + 按发布时间排序
        unique_news = self._deduplicate_news(all_news)
        unique_news.sort(key=lambda n: n.get("published_ts", 0), reverse=True)
        latest_news = unique_news[:8]
        
        # 4. 补充正文 (使用 newspaper3k)
        final_news = []
        sem = asyncio.Semaphore(3)
        tasks = []
        for news in latest_news:
            if len(news.get('content', '')) < 200:
                tasks.append(self._fill_content(news, sem))
            else:
                final_news.append(news)

        if tasks:
            await asyncio.gather(*tasks)
            for news in latest_news:
                if news not in final_news:
                    final_news.append(news)

        for news in final_news:
            if "published_ts" in news:
                news.pop("published_ts", None)

        logger.info(f"总共收集到 {len(final_news)} 条国际新闻")
        return final_news

    async def _collect_from_serpapi(self) -> List[Dict[str, Any]]:
        """🔥 修复: 实现 SerpApi 新闻收集"""
        results = []
        if not self.serpapi_key:
            return results

        # 定义搜索关键词
        search_queries = [
            "china stock market",
            "chinese economy news",
            "federal reserve interest rate",
            "AI technology news",
            "semiconductor industry"
        ]

        session = await self._get_session()
        for query in search_queries:
            params = {
                "engine": "google",
                "q": query,
                "tbm": "nws",  # 新闻搜索
                "api_key": self.serpapi_key,
                "num": 5
            }

            try:
                async with session.get("https://serpapi.com/search", params=params, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "news_results" in data:
                            for item in data["news_results"][:3]:
                                published_dt = datetime.now()
                                results.append({
                                    'source': 'serpapi',
                                    'title': item.get('title', ''),
                                    'url': item.get('link', ''),
                                    'content': item.get('snippet', ''),
                                    'published': published_dt.isoformat(),
                                    'published_ts': published_dt.timestamp()
                                })
            except Exception as e:
                logger.warning(f"SerpApi 搜索 '{query}' 失败: {e}")

        return results

    async def _collect_from_rss(self) -> List[Dict[str, Any]]:
        all_news = []
        for source, url in self.rss_sources.items():
            try:
                feed = await self._parse_feed(url)
                for entry in feed.entries[:5]:
                    is_hit = self._check_relevance(entry.title, entry.get('summary', ''))
                    if is_hit:
                        published_dt = self._extract_published(entry)
                        all_news.append({
                            'source': f"rss_{source}",
                            'title': entry.title,
                            'url': entry.link,
                            'content': entry.get('summary', ''),
                            'published': published_dt.isoformat(),
                            'published_ts': published_dt.timestamp()
                        })
            except Exception as e:
                logger.error(f"RSS {source} 失败: {e}")
        return all_news

    async def _fetch_content_no_browser(self, url: str) -> str:
        """🚀 纯代码抓取，不依赖 Chrome"""
        try:
            logger.info(f"🌍 正在抓取正文: {url[:30]}...")
            for attempt in range(2):
                text = await asyncio.to_thread(self._fetch_content_sync, url)
                if len(text) > 50:
                    return text[:3000]
                if attempt == 0:
                    await asyncio.sleep(1)
            return ""
        except Exception as e:
            logger.warning(f"全文抓取失败: {e}")
            return ""

    def _check_relevance(self, title, content):
        text = f"{title} {content}".lower()
        # 简单合并所有关键词进行检查
        all_keywords = [k for cat in self.investment_keywords.values() for k in cat]
        return any(k in text for k in all_keywords)

    def _deduplicate_news(self, news_items):
        seen = set()
        unique = []
        for n in news_items:
            # 使用 URL 或 标题哈希 去重
            raw_key = (n.get('url') or n.get('title', '')).strip().lower()
            key = hashlib.md5(raw_key.encode("utf-8")).hexdigest()
            if key not in seen:
                seen.add(key)
                unique.append(n)
        return unique

    async def _fill_content(self, news: Dict[str, Any], sem: asyncio.Semaphore):
        async with sem:
            url = news.get("url", "")
            if not url:
                return
            full_text = await self._fetch_content_no_browser(url)
            if full_text:
                news['content'] = full_text

    def _fetch_content_sync(self, url: str) -> str:
        article = newspaper.Article(url, config=self._newspaper_config)
        article.download()
        article.parse()
        return article.text or ""

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _parse_feed(self, url: str):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, feedparser.parse, url)

    def _extract_published(self, entry) -> datetime:
        for key in ("published_parsed", "updated_parsed"):
            if entry.get(key):
                return datetime.fromtimestamp(time.mktime(entry.get(key)))
        return datetime.now()
