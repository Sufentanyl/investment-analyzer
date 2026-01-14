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
import json
from bs4 import BeautifulSoup

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
            'reuters_world': 'https://www.reuters.com/world/rss',
            'reuters_business': 'https://www.reuters.com/business/rss',
            'reuters_markets': 'https://www.reuters.com/markets/rss',
            'reuters_technology': 'https://www.reuters.com/technology/rss',
            'reuters_legal': 'https://www.reuters.com/legal/rss',
            'ft_markets': 'https://www.ft.com/markets?format=rss',
            'ft_world': 'https://www.ft.com/world?format=rss',
            'ft_companies': 'https://www.ft.com/companies?format=rss',
            'ft_global_economy': 'https://www.ft.com/global-economy?format=rss',
            'wsj_markets': 'https://feeds.a.dj.com/rss/RSSMarketsMain.xml',
            'wsj_world': 'https://feeds.a.dj.com/rss/RSSWorldNews.xml',
            'economist_world': 'https://www.economist.com/the-world-this-week/rss.xml',
            'economist_economics': 'https://www.economist.com/finance-and-economics/rss.xml',
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

        # 2. NewsAPI (optional)
        if self.newsapi_key:
            all_news.extend(await self._collect_from_newsapi())

        # 3. RSS
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
            source = news.get('source', '')
            skip_fulltext = source.startswith("rss_bloomberg")
            if len(news.get('content', '')) < 200 and not skip_fulltext:
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

    async def _collect_from_newsapi(self) -> List[Dict[str, Any]]:
        results = []
        if not self.newsapi_key:
            return results

        query_terms = [
            "china OR chinese",
            "federal reserve OR fed OR inflation",
            "semiconductor OR chip OR ai",
            "oil OR gold OR copper",
            "banking OR property OR liquidity",
        ]
        query = " OR ".join(query_terms)

        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 20,
            "apiKey": self.newsapi_key,
        }

        session = await self._get_session()
        try:
            async with session.get("https://newsapi.org/v2/everything", params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    for item in data.get("articles", [])[:20]:
                        published_dt = datetime.now()
                        if item.get("publishedAt"):
                            try:
                                published_dt = datetime.fromisoformat(item["publishedAt"].replace("Z", "+00:00"))
                            except Exception:
                                published_dt = datetime.now()
                        results.append({
                            "source": "newsapi",
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "content": item.get("description", "") or "",
                            "published": published_dt.isoformat(),
                            "published_ts": published_dt.timestamp(),
                        })
        except Exception as e:
            logger.warning(f"NewsAPI fetch failed: {e}")

        return results

    async def _collect_from_rss(self) -> List[Dict[str, Any]]:
        all_news = []
        reuters_html_map = {
            "reuters_world": "https://www.reuters.com/world/",
            "reuters_business": "https://www.reuters.com/business/",
            "reuters_markets": "https://www.reuters.com/markets/",
            "reuters_technology": "https://www.reuters.com/technology/",
            "reuters_legal": "https://www.reuters.com/legal/",
        }
        for source, url in self.rss_sources.items():
            try:
                feed = await self._parse_feed(url)
                if source.startswith("reuters_") and getattr(feed, "bozo", False):
                    logger.warning(f"RSS parse error: {source} | {getattr(feed, 'bozo_exception', None)}")
                logger.info(f"RSS parsed: {source} | entries={len(getattr(feed, 'entries', []) or [])}")
                if source.startswith("reuters_") and not getattr(feed, "entries", []):
                    html_url = reuters_html_map.get(source)
                    if html_url:
                        all_news.extend(await self._collect_reuters_html(html_url, source))
                    continue
                for entry in feed.entries[:10]:
                    is_hit = self._check_relevance(entry.title, entry.get('summary', ''))
                    is_high_quality = (
                        source.startswith("ft_")
                        or source.startswith("reuters_")
                        or source.startswith("wsj_")
                        or source.startswith("economist_")
                        or source == "bloomberg"
                    )
                    if is_hit or is_high_quality:
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

    async def _collect_reuters_html(self, category_url: str, source: str) -> List[Dict[str, Any]]:
        browserless_ws = os.getenv("BROWSERLESS_WS")
        if not browserless_ws:
            logger.warning(f"Reuters HTML skipped (no BROWSERLESS_WS): {category_url}")
            return []

        try:
            from playwright.async_api import async_playwright
        except Exception as e:
            logger.warning(f"Playwright unavailable: {e}")
            return []

        results: List[Dict[str, Any]] = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(browserless_ws)
                context = browser.contexts[0] if browser.contexts else await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()
                await page.goto(category_url, wait_until="networkidle", timeout=60000)
                try:
                    await page.wait_for_selector('[data-testid="Heading"]', timeout=20000)
                except Exception:
                    logger.warning(f"Reuters HTML wait timeout: {category_url}")
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(2)
                html = await page.content()
                await page.close()
                await browser.close()

            if not html:
                logger.warning(f"Reuters HTML empty: {category_url}")
                return results

            soup = BeautifulSoup(html, "html.parser")
            headings = soup.find_all(attrs={"data-testid": "Heading"})
            for h in headings:
                if len(results) >= 10:
                    break
                link_tag = h.find("a") if h.name != "a" else h
                if not link_tag:
                    link_tag = h.find_parent("a")
                if not link_tag:
                    continue
                title = link_tag.get_text().strip()
                href = link_tag.get("href")
                if not title or not href:
                    continue
                if href.startswith("/"):
                    href = "https://www.reuters.com" + href
                results.append({
                    "source": f"reuters_html_{source}",
                    "title": title,
                    "url": href,
                    "content": "",
                    "published": datetime.now().isoformat(),
                    "published_ts": datetime.now().timestamp(),
                })
            logger.info(f"Reuters HTML parsed: {source} | items={len(results)}")
            return results
        except Exception as e:
            logger.warning(f"Reuters HTML exception: {e} | {category_url}")
            return results

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
        if "reuters.com" in url:
            fetched = await self._fetch_feed_with_fallback(url)
            if fetched:
                return feedparser.parse(fetched)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, feedparser.parse, url)

    async def _fetch_feed_with_fallback(self, url: str) -> str:
        session = await self._get_session()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
        }

        browserless_ws = os.getenv("BROWSERLESS_WS")
        if browserless_ws and "reuters.com" in url:
            try:
                from playwright.async_api import async_playwright
            except Exception as e:
                logger.warning(f"Playwright unavailable: {e}")
            else:
                try:
                    async with async_playwright() as p:
                        browser = await p.chromium.connect_over_cdp(browserless_ws)
                        context = browser.contexts[0] if browser.contexts else await browser.new_context()
                        page = await context.new_page()
                        await page.goto(url, wait_until="networkidle", timeout=15000)
                        content = await page.content()
                        await page.close()
                        await browser.close()

                    if content:
                        if "<rss" in content or "<feed" in content:
                            logger.info(f"Browserless response ok: {url} | size={len(content)}")
                            return content
                        logger.warning(f"Browserless non-RSS response: {url} | size={len(content)}")
                    else:
                        logger.warning(f"Browserless empty response: {url}")
                except Exception as e:
                    logger.warning(f"Browserless exception: {e} | {url}")

        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    return await response.text()
                logger.warning(f"Reuters fetch failed: {response.status} | {url}")
        except Exception as e:
            logger.warning(f"Reuters fetch exception: {e} | {url}")

        return ""

    def _extract_published(self, entry) -> datetime:
        for key in ("published_parsed", "updated_parsed"):
            if entry.get(key):
                return datetime.fromtimestamp(time.mktime(entry.get(key)))
        return datetime.now()
