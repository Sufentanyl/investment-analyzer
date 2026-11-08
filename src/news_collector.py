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
            'google_china_macro': 'https://news.google.com/rss/search?q=China+economy+OR+PBOC+OR+stimulus+when:1d&hl=en-US&gl=US&ceid=US:en',
            'google_ai_semi': 'https://news.google.com/rss/search?q=NVIDIA+OR+TSMC+OR+semiconductor+OR+OpenAI+when:1d&hl=en-US&gl=US&ceid=US:en',
            'google_fed_commodities': 'https://news.google.com/rss/search?q=Federal+Reserve+OR+gold+price+OR+copper+OR+crude+oil+when:1d&hl=en-US&gl=US&ceid=US:en',
            'google_ev_tech': 'https://news.google.com/rss/search?q=Tesla+OR+BYD+OR+CATL+OR+humanoid+robot+when:1d&hl=en-US&gl=US&ceid=US:en',
            'cnbc_world': 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362',
            'cnbc_tech': 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910',
            'bloomberg': 'https://feeds.bloomberg.com/markets/news.rss',
            'wsj_markets': 'https://feeds.a.dj.com/rss/RSSMarketsMain.xml',
            'ft_markets': 'https://www.ft.com/markets?format=rss',
        }
        
        self.investment_keywords = {
            'china_related': ['china', 'chinese', 'beijing', 'shanghai', 'hk', 'hong kong', 'taiwan', 'pboc', 'stimulus', 'tariff'],
            'global_macro': ['fed', 'federal reserve', 'rate cut', 'rate hike', 'inflation', 'cpi', 'oil', 'gold', 'copper', 'treasury'],
            'key_sectors': ['semiconductor', 'chip', 'ai', 'nvidia', 'tsmc', 'openai', 'tesla', 'byd', 'catl', 'ev', 'battery', 'robot', 'quantum', 'biotech'],
            'cn_catalysts': [
                '央行', '证监会', '发改委', '工信部', '财政部', '国务院', '政治局', '国常会',
                '降准', '降息', '社融', 'LPR', '新质生产力', '低空经济', '算力', '人工智能',
                '半导体', '光刻机', '芯片', '人形机器人', '固态电池', '储能', '光伏', '创新药',
                '业绩', '预增', '扭亏', '大幅增长', '中标', '大单', '合同', '回购', '增持',
                '并购', '重组', '突破', '量产', '涨价', '提价', '英伟达', '特斯拉', '苹果'
            ]
        }

    async def collect_international_news(self) -> List[Dict[str, Any]]:
        """
        v2.0 双轨情报采集：
        1. 本土催化轨：东方财富 7x24 快讯 + 新浪财经 7x24 电报 + A股核心公告
        2. 海外映射轨：Google News 专题 RSS + CNBC/Bloomberg/WSJ + SerpApi/NewsAPI
        """
        all_news = []
        
        # 1. 本土 7x24 财经快讯与公告轨 (优先采集，无需付费 Key)
        enable_domestic = os.getenv("ENABLE_DOMESTIC_7X24", "true").lower() != "false"
        if enable_domestic:
            domestic_news = await self._collect_from_domestic_7x24()
            all_news.extend(domestic_news)

        # 2. SerpApi (可选)
        if self.serpapi_key:
            all_news.extend(await self._collect_from_serpapi())

        # 3. NewsAPI (可选)
        if self.newsapi_key:
            all_news.extend(await self._collect_from_newsapi())

        # 4. 海外财经 RSS (并发采集)
        all_news.extend(await self._collect_from_rss())
        
        # 5. 去重 + 双轨均衡筛选
        unique_news = self._deduplicate_news(all_news)
        unique_news.sort(key=lambda n: n.get("published_ts", 0), reverse=True)

        max_total = int(os.getenv("MAX_NEWS_PER_RUN", "10"))
        domestic_items = [n for n in unique_news if n.get("is_domestic_fast")]
        global_items = [n for n in unique_news if not n.get("is_domestic_fast")]

        # 均衡组合：最多取 6 条本土核心催化 + 4 条海外重磅映射（若某一方不足则由另一方补齐）
        selected_domestic = domestic_items[:6]
        selected_global = global_items[:max(4, max_total - len(selected_domestic))]
        if len(selected_domestic) + len(selected_global) < max_total:
            remaining = max_total - (len(selected_domestic) + len(selected_global))
            selected_domestic = domestic_items[:6 + remaining]

        latest_news = selected_domestic + selected_global
        latest_news.sort(key=lambda n: n.get("published_ts", 0), reverse=True)
        latest_news = latest_news[:max_total]
        
        # 6. 补充正文 (本土7x24快讯自带完整内容，跳过newspaper3k抓取以提高速度)
        final_news = []
        sem = asyncio.Semaphore(3)
        tasks = []
        for news in latest_news:
            source = news.get('source', '')
            skip_fulltext = (
                news.get('is_domestic_fast')
                or source.startswith("cn_")
                or source.startswith("rss_bloomberg")
                or source.startswith("rss_google_")
            )
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

        logger.info(
            f"总共收集到 {len(final_news)} 条双轨情报 "
            f"(本土快讯: {sum(1 for n in final_news if n.get('is_domestic_fast'))}, "
            f"海外映射: {sum(1 for n in final_news if not n.get('is_domestic_fast'))})"
        )
        return final_news

    async def _collect_from_domestic_7x24(self) -> List[Dict[str, Any]]:
        """采集本土 7x24 小时财经快讯与公司核心公告催化"""
        try:
            from valuecell_bridge.utils import AShareDataSource
            session = await self._get_session()
            ds = AShareDataSource(session)
            raw_items = await ds.get_7x24_fast_news(limit=25)
            filtered = []
            for item in raw_items:
                title = item.get("title", "")
                content = item.get("content", "")
                # 如果带有明确的A股关联列表，或命中核心催化词，则纳入分析
                if item.get("stock_list") or self._check_relevance(title, content):
                    filtered.append(item)
            logger.info(f"🇨🇳 本土 7x24 快讯采集完成: 原始 {len(raw_items)} 条 -> 精选催化 {len(filtered)} 条")
            return filtered
        except Exception as e:
            logger.warning(f"本土 7x24 快讯采集失败: {e}")
            return []

    async def _collect_from_serpapi(self) -> List[Dict[str, Any]]:
        """🔥 修复: 实现 SerpApi 新闻收集"""
        results = []
        if not self.serpapi_key:
            return results

        search_queries = [
            "china stock market policy",
            "NVIDIA AI semiconductor supply chain",
            "federal reserve interest rate",
        ]

        session = await self._get_session()
        keys = [k.strip() for k in self.serpapi_key.split(',') if k.strip()]
        api_key = keys[0] if keys else self.serpapi_key
        for query in search_queries:
            params = {
                "engine": "google",
                "q": query,
                "tbm": "nws",
                "api_key": api_key,
                "num": 5
            }

            try:
                async with session.get("https://serpapi.com/search", params=params, timeout=12) as response:
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

    async def _collect_single_rss(self, source: str, url: str) -> List[Dict[str, Any]]:
        items = []
        try:
            feed = await asyncio.wait_for(self._parse_feed(url), timeout=12)
            entries = getattr(feed, "entries", []) or []
            logger.info(f"RSS parsed: {source} | entries={len(entries)}")
            for entry in entries[:8]:
                title = getattr(entry, 'title', '') or ''
                summary = entry.get('summary', '') if hasattr(entry, 'get') else ''
                # 清理 HTML 标签
                if summary and '<' in summary:
                    try:
                        summary = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
                    except Exception:
                        pass
                is_hit = self._check_relevance(title, summary)
                is_high_quality = source.startswith("google_") or source == "bloomberg"
                if is_hit or is_high_quality:
                    published_dt = self._extract_published(entry)
                    items.append({
                        'source': f"rss_{source}",
                        'title': title,
                        'url': getattr(entry, 'link', ''),
                        'content': summary or title,
                        'published': published_dt.isoformat(),
                        'published_ts': published_dt.timestamp()
                    })
        except Exception as e:
            logger.warning(f"RSS {source} 采集跳过: {e}")
        return items

    async def _collect_from_rss(self) -> List[Dict[str, Any]]:
        tasks = [
            self._collect_single_rss(source, url)
            for source, url in self.rss_sources.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_news = []
        for res in results:
            if isinstance(res, list):
                all_news.extend(res)
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
