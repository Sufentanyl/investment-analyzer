import aiohttp
import feedparser
import logging
from datetime import datetime
import os
from typing import List, Dict, Any
import newspaper # 使用 newspaper3k 替代 Chrome
import hashlib

logger = logging.getLogger(__name__)

class AdvancedNewsCollector:
    def __init__(self):
        self.newsapi_key = os.getenv('NEWSAPI_KEY')
        self.serpapi_key = os.getenv('SERPAPI_KEY')
        
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
        
        # 3. 去重
        unique_news = self._deduplicate_news(all_news)
        latest_news = unique_news[:8]
        
        # 4. 补充正文 (使用 newspaper3k)
        final_news = []
        for news in latest_news:
            # 如果内容太短，尝试抓取全文
            if len(news.get('content', '')) < 200:
                full_text = await self._fetch_content_no_browser(news['url'])
                if full_text:
                    news['content'] = full_text
            final_news.append(news)

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

        try:
            import aiohttp
            for query in search_queries:
                params = {
                    "engine": "google",
                    "q": query,
                    "tbm": "nws",  # 新闻搜索
                    "api_key": self.serpapi_key,
                    "num": 5
                }

                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get("https://serpapi.com/search", params=params, timeout=15) as response:
                            if response.status == 200:
                                data = await response.json()
                                if "news_results" in data:
                                    for item in data["news_results"][:3]:
                                        results.append({
                                            'source': 'serpapi',
                                            'title': item.get('title', ''),
                                            'url': item.get('link', ''),
                                            'content': item.get('snippet', ''),
                                            'published': datetime.now().isoformat()
                                        })
                except Exception as e:
                    logger.warning(f"SerpApi 搜索 '{query}' 失败: {e}")

        except Exception as e:
            logger.error(f"SerpApi 收集失败: {e}")

        return results

    async def _collect_from_rss(self) -> List[Dict[str, Any]]:
        all_news = []
        for source, url in self.rss_sources.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    is_hit = self._check_relevance(entry.title, entry.get('summary', ''))
                    if is_hit:
                        all_news.append({
                            'source': f"rss_{source}",
                            'title': entry.title,
                            'url': entry.link,
                            'content': entry.get('summary', ''),
                            'published': datetime.now().isoformat()
                        })
            except Exception as e:
                logger.error(f"RSS {source} 失败: {e}")
        return all_news

    async def _fetch_content_no_browser(self, url: str) -> str:
        """🚀 纯代码抓取，不依赖 Chrome"""
        try:
            logger.info(f"🌍 正在抓取正文: {url[:30]}...")
            article = newspaper.Article(url)
            article.download()
            article.parse()
            if len(article.text) > 50:
                return article.text[:3000]
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
            key = n.get('url') or n['title']
            if key not in seen:
                seen.add(key)
                unique.append(n)
        return unique