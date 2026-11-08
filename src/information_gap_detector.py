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

        # 2. 多模型路由器 (告别 Qwen 单一依赖，支持 DeepSeek / GPT / Gemini / Kimi / Qwen)
        self._llm_router = None

        # 3. 缓存 (OrderedDict 限制大小，防止内存泄漏)
        self.cache = OrderedDict()
        self.max_cache_size = 1000
        self.cache_lock = asyncio.Lock()

        # 4. 复用 aiohttp ClientSession
        self._session = None
        
        if not self.api_keys:
            logger.warning("⚠️ 未配置 SERPAPI_KEY，海外信息差检测将基于盘面预期差评估")

    def _get_llm_router(self):
        if self._llm_router is None:
            try:
                from valuecell_bridge.utils import LLMFallback
                self._llm_router = LLMFallback()
            except Exception as e:
                logger.debug(f"LLMFallback 初始化失败: {e}")
        return self._llm_router

    def _get_api_key(self):
        if not self.api_keys:
            return None
        key = self.api_keys[self.current_key_idx]
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        return key

    async def _get_session(self):
        """复用 ClientSession"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """清理资源"""
        if self._session and not self._session.closed:
            await self._session.close()

    def _evaluate_price_expectation_gap(self, news: dict) -> float:
        """
        评估 A 股盘面预期差：
        结合新闻催化级别与关联个股短期涨幅/乖离率，区分「首次催化先手」与「高位潜伏盘兑现」
        """
        analysis = news.get("_analysis_result") or {}
        stock_data = analysis.get("stock_data") or []
        base_gap = 0.72 if news.get("is_domestic_fast") else 0.65

        if stock_data:
            # 检查关联个股是否已经连续大涨（潜伏盘提前抢跑，预期差降低）
            overheated_count = sum(1 for s in stock_data if s.get("is_overheated"))
            if overheated_count == len(stock_data):
                return 0.35
            elif overheated_count > 0:
                return 0.52
            else:
                return min(0.85, base_gap + 0.08)
        return base_gap

    async def detect_information_gap(self, news_list: list) -> list:
        """
        核心入口：
        - 本土 7x24 快讯/公告：直接进行「A股预期差（是否高位透支）」评估并放行先手催化
        - 海外新闻：检测国内媒体覆盖度 + 盘面预期差
        """
        if not news_list:
            return []

        if not self.api_keys:
            for news in news_list:
                news['coverage_status'] = "first_hand_cn" if news.get("is_domestic_fast") else "unverified"
                news['coverage_sources'] = []
                news['coverage_count'] = 0
                news['gap_confidence'] = self._evaluate_price_expectation_gap(news)
            return news_list

        gap_news = []
        concurrency = int(os.getenv("GAP_DETECT_CONCURRENCY", "5"))
        sem = asyncio.Semaphore(concurrency)
        tasks = [self._check_single_news_with_sem(sem, news) for news in news_list]
        results = await asyncio.gather(*tasks)
        
        for news, is_gap in zip(news_list, results):
            if is_gap:
                gap_news.append(news)

        return gap_news

    async def _check_single_news_with_sem(self, sem: asyncio.Semaphore, news) -> bool:
        async with sem:
            return await self._check_single_news(news)

    async def _check_single_news(self, news) -> bool:
        """
        检测单条新闻的信息差 / 预期差
        """
        title = news.get('title', '')
        if not title:
            return False

        # 本土 7x24 实时快讯/突发公告属于一手催化，按盘面位置评估预期差
        if news.get("is_domestic_fast") or str(news.get("source", "")).startswith("cn_"):
            gap_conf = self._evaluate_price_expectation_gap(news)
            news['coverage_status'] = "first_hand_cn"
            news['coverage_sources'] = [news.get("source", "cn_7x24")]
            news['coverage_count'] = 1
            news['gap_confidence'] = gap_conf
            # 只要不是全部关联股都严重高位透支且低置信度，均放行交由后续有效置信度阈值判断
            return gap_conf >= 0.35

        # 1. 查缓存
        url = news.get("url", "")
        news_hash = hashlib.md5(f"{title}|{url}".encode("utf-8")).hexdigest()

        async with self.cache_lock:
            if news_hash in self.cache:
                entry = self.cache[news_hash]
                self.cache.move_to_end(news_hash)
                if datetime.now() - entry['timestamp'] < timedelta(hours=4):
                    news['gap_confidence'] = entry.get('gap_confidence', 0.65)
                    news['coverage_status'] = entry.get('coverage_status', 'not_covered')
                    return entry['has_gap']

        # 2. 获取中文搜索词 (多模型自动路由，不再强依赖 Qwen)
        search_query = title
        if not self._is_mostly_chinese(title):
            cn_keywords = await self._get_chinese_keywords(title)
            if cn_keywords:
                search_query = cn_keywords
                logger.info(f"🔀 关键词转换: '{title[:20]}...' -> '{search_query}'")

        # 3. 执行搜索
        for attempt in range(2):
            api_key = self._get_api_key()
            if not api_key:
                return False

            params = {
                "engine": "google_news",
                "q": search_query,
                "gl": "cn",
                "hl": "zh-cn",
                "api_key": api_key,
                "num": 5
            }

            try:
                session = await self._get_session()
                async with session.get("https://serpapi.com/search", params=params, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()

                        has_coverage = False
                        coverage_sources = []
                        if "news_results" in data and len(data["news_results"]) > 0:
                            for item in data["news_results"][:3]:
                                source = item.get('source', {}).get('title', '国内媒体')
                                if source:
                                    coverage_sources.append(source)
                            min_coverage = int(os.getenv("GAP_COVERAGE_MIN", "2"))
                            has_coverage = len(coverage_sources) >= min_coverage
                            logger.info(
                                f"📰 覆盖检测: {search_query} -> 来源: {', '.join(coverage_sources) or '无'} | count={len(coverage_sources)}"
                            )
                        else:
                            logger.info(f"💎 发现信息差: {search_query} (国内未见广泛报道)")

                        news['coverage_status'] = "covered" if has_coverage else "not_covered"
                        news['coverage_sources'] = coverage_sources
                        news['coverage_count'] = len(coverage_sources)
                        price_gap = self._evaluate_price_expectation_gap(news)
                        if has_coverage:
                            news['gap_confidence'] = 0.25
                        else:
                            news['gap_confidence'] = max(price_gap, 0.65 if coverage_sources else 0.78)

                        async with self.cache_lock:
                            if len(self.cache) >= self.max_cache_size:
                                self.cache.popitem(last=False)
                            self.cache[news_hash] = {
                                'has_gap': not has_coverage,
                                'gap_confidence': news['gap_confidence'],
                                'coverage_status': news['coverage_status'],
                                'timestamp': datetime.now()
                            }

                        return not has_coverage

                    if response.status in (429, 500, 502, 503, 504) and attempt == 0:
                        await asyncio.sleep(1.5)
                        continue

                    news['coverage_status'] = "unknown"
                    news['coverage_sources'] = []
                    news['coverage_count'] = 0
                    news['gap_confidence'] = self._evaluate_price_expectation_gap(news)
                    logger.warning(f"SerpApi 异常: {response.status}，降级使用盘面预期差评估")
                    return True
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(1.5)
                    continue
                news['coverage_status'] = "unknown"
                news['coverage_sources'] = []
                news['coverage_count'] = 0
                news['gap_confidence'] = self._evaluate_price_expectation_gap(news)
                logger.error(f"信息差检测出错: {e}，降级使用盘面预期差评估")
                return True
        return True

    async def _get_chinese_keywords(self, english_title: str) -> str:
        """
        调用可用模型 (DeepSeek / GPT / Gemini / Kimi / Qwen) 将英文标题提取为中文搜索关键词
        """
        prompt = f"""请将以下财经新闻标题提取为能在中文新闻搜索到的【中文搜索关键词】。
要求：
1. 只保留核心实体（公司名、人名）和核心事件。
2. 不要直译，要用中国财经媒体常用的表述。
3. 只返回关键词（空格分隔，3-4个词以内），不要任何解释或标点符号。

标题: "{english_title}"
关键词:"""
        router = self._get_llm_router()
        if router and router.clients:
            try:
                res = await router.chat(
                    prompt,
                    preferred_models=["deepseek", "openai", "gemini", "kimi", "qwen"],
                    temperature=0.2,
                    max_tokens=50,
                )
                if res and not res.startswith("所有模型调用失败") and not res.startswith("LLM"):
                    return res.strip().replace('"', '').replace("'", "").split("\n")[0].strip()
            except Exception as e:
                logger.warning(f"多模型关键词提取失败: {e}")
        return english_title

    def _is_mostly_chinese(self, text):
        if not text:
            return False
        zh_count = len([c for c in text if '\u4e00' <= c <= '\u9fa5'])
        return zh_count > len(text) * 0.3

