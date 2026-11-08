from rag_memory import RAGMemory
from technical_analysis import TechnicalAnalyzer
from database import DatabaseManager
from chart_generator import generate_snapshot
from event_templates import match_event_template, match_sectors, classify_alert_keywords
from valuecell_bridge.utils import (
    normalize_ashare_code,
    fetch_ashare_kline_sync,
)
import json
import logging
import os
import re
import asyncio
import aiohttp
import random
import yaml
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import pytz

try:
    from telegram.constants import ParseMode
except Exception:
    ParseMode = None

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


def retry_async(max_retries=3, delay=2):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if i == max_retries - 1:
                        logger.error(f"❌ {func.__name__} 最终失败: {e}")
                        return None
                    await asyncio.sleep(delay)
        return wrapper
    return decorator


DEFAULT_ASHARE_AGENTS = {
    "bull_agent": {
        "prompt": (
            "你是一位顶尖的A股游资与机构多头策略师（Bull Agent）。"
            "请从多头催化视角分析以下新闻：重点挖掘其属于哪个级别的催化剂（国策级/行业级/公司业绩级/海外科技映射），"
            "推导其在A股的一阶直接受益标的与二阶供应链传导方向，评估题材想象空间与资金审美契合度。简明扼要（150字内）。"
        )
    },
    "bear_agent": {
        "prompt": (
            "你是一位冷酷的A股风控官与空头狙击手（Bear Agent）。"
            "请专门对以下新闻挑刺：1) 是否属于“利好出尽是利空”或已被市场提前炒作透支（潜伏盘趁利好兑现出货）？"
            "2) 相关概念在A股是否纯属蹭热点、缺乏真实订单与业绩支撑？"
            "3) 若是海外新闻，是否存在A股映射断层或贸易摩擦反噬风险？简明扼要（150字内）。"
        )
    },
    "judge_agent": {
        "prompt": (
            "你是A股首席量化投资裁判（Judge Agent）。请综合多方与空方的辩论观点，"
            "结合A股T+1交易制度与“炒预期、防兑现”的特征，客观评判该新闻对A股的真实投资价值与预期差。"
        )
    },
}


class LLMAnalyzer:
    def __init__(self, **kwargs):
        # 1. 多模型 API 初始化 (DeepSeek + OpenAI/GPT + Gemini + Kimi + Qwen可选)
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.openai_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self.qwen_key = os.getenv("QWEN_API_KEY")
        self.qwen_base = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.qwen_model = os.getenv("QWEN_MODEL", "qwen-plus")

        keys_str = os.getenv("GEMINI_API_KEY", "")
        self.gemini_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

        self.kimi_key = os.getenv("KIMI_API_KEY")
        self.kimi_base = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
        self.kimi_model = os.getenv("KIMI_MODEL", "moonshot-v1-8k")

        # 2. 核心组件
        self.ta = TechnicalAnalyzer()
        self.db = DatabaseManager()
        self.client_ds = None
        self.client_openai = None
        self.client_qwen = None
        self.client_kimi = None
        self.client_gemini = None

        self._aiohttp_session = None

        # Telegram Bot (用于发送 fallback 通知)
        self.telegram_bot = None
        self.chat_id = None

        # ValueCell 集成 (懒加载)
        self._research_adapter = None
        self._news_adapter = None

        try:
            self.memory = RAGMemory()
        except Exception as e:
            logger.warning(f"RAGMemory 初始化失败: {e}")
            self.memory = None

        # 3. 加载配置文件
        self.config_path = '/app/config.yaml' if os.path.exists('/app/config.yaml') else 'config.yaml'
        self.config = self._load_yaml_config()

        self.threshold_hold = float(os.getenv("CONFIDENCE_THRESHOLD_HOLD", "0.65"))
        self.threshold_normal = float(os.getenv("CONFIDENCE_THRESHOLD_NORMAL", "0.75"))

    def set_telegram_bot(self, bot, chat_id):
        """设置 Telegram Bot 用于发送通知"""
        self.telegram_bot = bot
        self.chat_id = chat_id

    def _ensure_clients(self):
        if AsyncOpenAI is None:
            return
        if not self.client_ds and self.deepseek_key:
            self.client_ds = AsyncOpenAI(api_key=self.deepseek_key, base_url=self.deepseek_base)
        if not self.client_openai and self.openai_key:
            self.client_openai = AsyncOpenAI(api_key=self.openai_key, base_url=self.openai_base)
        if not self.client_qwen and self.qwen_key:
            self.client_qwen = AsyncOpenAI(api_key=self.qwen_key, base_url=self.qwen_base)
        if not self.client_kimi and self.kimi_key:
            self.client_kimi = AsyncOpenAI(api_key=self.kimi_key, base_url=self.kimi_base)
        if not self.client_gemini and self.gemini_keys:
            self.client_gemini = AsyncOpenAI(
                api_key=self.gemini_keys[0],
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )

    def _get_ordered_openai_compatible_clients(self, preferred: Optional[List[str]] = None):
        """
        获取按优先级排序的可用模型列表
        默认优先级: deepseek -> openai -> gemini -> kimi -> qwen
        """
        self._ensure_clients()
        registry = {
            "deepseek": (self.client_ds, self.deepseek_model, "DeepSeek"),
            "openai": (self.client_openai, self.openai_model, "OpenAI-GPT"),
            "gemini": (self.client_gemini, self.gemini_model, "Gemini"),
            "kimi": (self.client_kimi, self.kimi_model, "Kimi"),
            "qwen": (self.client_qwen, self.qwen_model, "Qwen"),
        }
        order = preferred or ["deepseek", "openai", "gemini", "kimi", "qwen"]
        for k in registry:
            if k not in order:
                order.append(k)

        available = []
        for k in order:
            entry = registry.get(k)
            if entry and entry[0] is not None:
                available.append((k, entry[0], entry[1], entry[2]))
        return available

    async def _call_routed_text(
        self,
        prompt: str,
        preferred: Optional[List[str]] = None,
        temperature: float = 0.6,
    ) -> str:
        """
        统一多模型文本生成路由器：
        按 preferred 顺序调用，若遇限流/报错自动无缝切换到下一可用模型
        """
        candidates = self._get_ordered_openai_compatible_clients(preferred)
        for alias, client, model, display_name in candidates:
            try:
                if alias == "gemini":
                    res = await self._call_gemini_text(prompt)
                    if res:
                        return res
                    continue
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                )
                text = resp.choices[0].message.content
                if text:
                    return text
            except Exception as e:
                logger.warning(f"⚠️ 路由模型 {display_name} 调用失败，尝试切换下一模型: {e}")
                continue

        # 最后兜底尝试原生 Gemini HTTP 调用
        if self.gemini_keys:
            return await self._call_gemini_text(prompt)
        return ""

    async def _call_routed_json(
        self,
        prompt: str,
        preferred: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        统一多模型 JSON 生成路由器：
        支持 DeepSeek / GPT / Gemini / Kimi / Qwen 自动故障切换与 JSON 提取
        """
        json_prompt = prompt if "JSON" in prompt.upper() else (prompt + "\n请严格只输出合法的 JSON 对象，不要包含 Markdown 代码块。")
        candidates = self._get_ordered_openai_compatible_clients(preferred)

        for alias, client, model, display_name in candidates:
            try:
                if alias == "gemini":
                    parsed = await self._call_gemini_json(json_prompt)
                    if parsed:
                        return parsed
                    continue

                kwargs = {
                    "model": model,
                    "messages": [{"role": "user", "content": json_prompt}],
                    "temperature": 0.4,
                }
                if alias in ("deepseek", "openai", "qwen"):
                    kwargs["response_format"] = {"type": "json_object"}

                resp = await client.chat.completions.create(**kwargs)
                raw_text = resp.choices[0].message.content or ""
                parsed = self._parse_json_safely(raw_text)
                if parsed:
                    return parsed
            except Exception as e:
                logger.warning(f"⚠️ 路由 JSON 模型 {display_name} 失败，自动切换替补: {e}")
                continue

        if self.gemini_keys:
            return await self._call_gemini_json(json_prompt)
        return {}

    def _parse_json_safely(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}
        cleaned = re.sub(r"```json|```", "", text).strip()
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else {}
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    return data if isinstance(data, dict) else {}
                except Exception:
                    pass
        return {}

    async def _get_aiohttp_session(self):
        """复用 aiohttp.ClientSession"""
        if self._aiohttp_session is None or self._aiohttp_session.closed:
            self._aiohttp_session = aiohttp.ClientSession()
        return self._aiohttp_session

    async def close(self):
        """清理资源"""
        if self._aiohttp_session and not self._aiohttp_session.closed:
            await self._aiohttp_session.close()
        if self._research_adapter:
            await self._research_adapter.close()
        if self._news_adapter:
            await self._news_adapter.close()

    def _init_valuecell_adapters(self):
        """懒加载 ValueCell 适配器"""
        if self._research_adapter is None:
            try:
                from valuecell_bridge import ResearchAdapter
                self._research_adapter = ResearchAdapter()
                logger.info("✅ ResearchAdapter 初始化成功")
            except Exception as e:
                logger.warning(f"⚠️ ResearchAdapter 初始化失败: {e}")
        
        if self._news_adapter is None:
            try:
                from valuecell_bridge import NewsAdapter
                self._news_adapter = NewsAdapter()
                logger.info("✅ NewsAdapter 初始化成功")
            except Exception as e:
                logger.warning(f"⚠️ NewsAdapter 初始化失败: {e}")

    async def deep_research(self, stock_code: str) -> Dict[str, Any]:
        """深度研究 A 股 (使用 ValueCell ResearchAdapter)"""
        self._init_valuecell_adapters()
        if not self._research_adapter:
            return {"error": "ResearchAdapter 未初始化"}
        
        try:
            stock_name = await self._research_adapter.get_stock_name(stock_code)
            query = f"{stock_name}({stock_code}) 投资价值分析"
            result = await self._research_adapter.deep_research(query, stock_code)
            result["stock_name"] = stock_name
            return result
        except Exception as e:
            logger.error(f"❌ 深度研究失败: {e}")
            return {"error": str(e)}

    async def smart_news_analysis(self, keyword: str) -> Dict[str, Any]:
        """智能新闻分析 (使用 ValueCell NewsAdapter)"""
        self._init_valuecell_adapters()
        if not self._news_adapter:
            return {"error": "NewsAdapter 未初始化"}
        
        try:
            return await self._news_adapter.get_smart_news(keyword)
        except Exception as e:
            logger.error(f"❌ 智能新闻分析失败: {e}")
            return {"error": str(e)}

    def get_valuecell_status(self) -> Dict[str, Any]:
        """获取 ValueCell Agent 状态"""
        return {
            "research_adapter": {
                "initialized": self._research_adapter is not None,
                "model": self._research_adapter.model_config.model_id if self._research_adapter else None
            },
            "news_adapter": {
                "initialized": self._news_adapter is not None,
                "model": self._news_adapter.model_config.model_id if self._news_adapter else None
            }
        }

    def _get_user_config_json_path(self) -> str:
        if os.path.exists('/app/data') or os.access('/app', os.W_OK):
            return '/app/data/user_config.json'
        return os.path.join(os.getcwd(), 'data', 'user_config.json')

    def _load_yaml_config(self):
        default_conf = {
            "my_positions": [],
            "concept_db": {},
            "agents": DEFAULT_ASHARE_AGENTS.copy(),
            "auto_bind_keywords": True,
            "alert_levels_to_push": ["strong", "normal"]
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    if 'positions' in data:
                        data['my_positions'] = data['positions'].get('watching', [])
                        data['concept_db'] = data['positions'].get('keywords', {})
                    if not data.get('agents') or 'bull_agent' not in data.get('agents', {}):
                        data['agents'] = DEFAULT_ASHARE_AGENTS.copy()
                    return data
            except Exception as e:
                logger.error(f"❌ 读取 config.yaml 失败: {e}")

        json_path = self._get_user_config_json_path()
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f) or {}
                    if not data.get('agents') or 'bull_agent' not in data.get('agents', {}):
                        data['agents'] = DEFAULT_ASHARE_AGENTS.copy()
                    return data
            except Exception as e:
                logger.warning(f"读取 JSON 配置失败: {e}")
        return default_conf

    def save_config(self, config=None):
        """保存用户配置"""
        if config is None:
            config = self.config

        json_path = self._get_user_config_json_path()
        try:
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            logger.info("✅ 配置已保存")
            return True
        except Exception as e:
            logger.error(f"❌ 保存配置失败: {e}")
            return False 

    def add_position(self, code):
        norm_code = normalize_ashare_code(code)
        if norm_code not in self.config.get('my_positions', []):
            self.config.setdefault('my_positions', []).append(norm_code)
            self.save_config()
            return True
        return False

    def remove_position(self, code):
        norm_code = normalize_ashare_code(code)
        positions = self.config.get('my_positions', [])
        if norm_code in positions:
            positions.remove(norm_code)
            self.save_config()
            return True
        if code in positions:
            positions.remove(code)
            self.save_config()
            return True
        return False

    def bind_keyword(self, keyword, code):
        if 'concept_db' not in self.config:
            self.config['concept_db'] = {}
        norm_code = normalize_ashare_code(code)
        kw_list = self.config['concept_db'].setdefault(keyword.lower(), [])
        if norm_code not in kw_list:
            kw_list.append(norm_code)
        self.save_config()
        return True

    def auto_bind_keywords(self, keywords: list, stock_code: str):
        """AI自动绑定关键词到股票"""
        if 'concept_db' not in self.config:
            self.config['concept_db'] = {}

        norm_code = normalize_ashare_code(stock_code)
        for keyword in keywords:
            keyword_lower = keyword.lower().strip()
            if keyword_lower and len(keyword_lower) >= 2:
                self.config['concept_db'].setdefault(keyword_lower, [])
                if norm_code not in self.config['concept_db'][keyword_lower]:
                    self.config['concept_db'][keyword_lower].append(norm_code)
                    logger.info(f"🔗 AI自动绑定: '{keyword}' -> {norm_code}")

        self.save_config()
        return True

    def _extract_explicit_ashare_codes(self, text: str) -> List[Dict[str, str]]:
        """从新闻标题/正文中直接提取显式出现的 A 股代码（如 603920.SH 或 (300750)）"""
        if not text:
            return []
        matches = re.findall(r"(?:SH|SZ|\(|\[|\b)((?:60\d|688|00\d|300|301)\d{3})(?:\.SH|\.SZ|\)|\]|\b)", text, re.IGNORECASE)
        seen = set()
        out = []
        for code in matches:
            if code not in seen:
                seen.add(code)
                out.append({"code": code})
        return out

    async def analyze_cross_validate(self, title: str, content: str) -> Dict[str, Any]:
        """
        v2.0 多模型交叉辩论引擎 (Bull vs Bear -> Judge -> 产业链关联 -> 东方财富三维量价共振)
        主力路由: DeepSeek / GPT / Gemini / Kimi 自动无缝切换，彻底解除对 Qwen 的强依赖
        """
        self._ensure_clients()
        agents = self.config.get('agents') or DEFAULT_ASHARE_AGENTS
        if 'bull_agent' not in agents:
            agents = DEFAULT_ASHARE_AGENTS

        logger.info(f"🎭 启动 A 股多空博弈辩论: {title[:40]}")
        
        bull_prompt = f"{agents['bull_agent']['prompt']}\n\n【新闻标题】{title}\n【新闻内容】{(content or '')[:1000]}"
        bear_prompt = f"{agents['bear_agent']['prompt']}\n\n【新闻标题】{title}\n【新闻内容】{(content or '')[:1000]}"
        
        task_bull = self._call_routed_text(bull_prompt, preferred=["deepseek", "openai", "gemini", "kimi"])
        task_bear = self._call_routed_text(bear_prompt, preferred=["openai", "deepseek", "gemini", "kimi"])
        bull_view, bear_view = await asyncio.gather(task_bull, task_bear)

        if not bull_view and not bear_view:
            result = await self._analyze_legacy(title, content)
            return self._attach_event_context(title, content, result)
        
        judge_prompt = f"""
{agents['judge_agent']['prompt']}

【新闻标题】{title}
【多方观点 (Bull)】{bull_view}
【空方观点 (Bear)】{bear_view}

请严格输出以下 JSON 格式:
{{
  "stock_market_influence": "positive" 或 "negative" 或 "neutral",
  "confidence": 0.0到1.0之间的浮点数,
  "summary": "一句话辩论总结（指出核心预期差）",
  "reason": "综合多空双方观点的最终研判逻辑",
  "concept": "核心受益/受损A股概念板块（逗号分隔，如：算力芯片,光模块）",
  "bull_point": "多方核心催化理由（简练）",
  "bear_point": "空方核心风险/兑现警告（简练）",
  "a_share_stocks": [
    {{"code": "6位A股代码如600519", "name": "股票简称"}}
  ]
}}
"""
        final_decision = await self._call_routed_json(
            judge_prompt, preferred=["deepseek", "openai", "gemini", "kimi"]
        )
        
        if not final_decision:
            return {}

        # 统一字段兼容 (stock_market_influence <-> signal)
        influence = final_decision.get("stock_market_influence") or final_decision.get("signal") or "neutral"
        final_decision["stock_market_influence"] = influence
        final_decision["signal"] = influence

        if float(final_decision.get('confidence', 0) or 0) < 0.4:
            return {}

        # 收集关联 A 股标的 (1. 新闻内显式代码 -> 2. 关键词库匹配 -> 3. Judge 模型直接推荐 -> 4. AI 产业链二阶联想)
        related_tickers = []
        seen_codes = set()

        def _add_ticker(c_str: str, n_str: str = ""):
            norm = normalize_ashare_code(c_str)
            if re.fullmatch(r"\d{6}", norm) and norm not in seen_codes:
                seen_codes.add(norm)
                related_tickers.append({"code": norm, "name": n_str or ""})

        # 1) 新闻正文中显式出现的 A 股代码（如公告快讯）
        for item in self._extract_explicit_ashare_codes(f"{title} {content}"):
            _add_ticker(item["code"])

        # 2) 配置关键词库匹配
        concept = final_decision.get('concept', '')
        db = self.config.get('concept_db', {})
        for kw, code in db.items():
            if kw in title.lower() or kw in concept.lower():
                if isinstance(code, list):
                    for c in code:
                        _add_ticker(c)
                else:
                    _add_ticker(code)

        # 3) Judge Agent 直接给出的 A 股标的
        for item in final_decision.get("a_share_stocks", []) or []:
            if isinstance(item, dict):
                _add_ticker(item.get("code", ""), item.get("name", ""))
            elif isinstance(item, str):
                _add_ticker(item)

        # 4) 若仍无关联标的，调用多模型 AI 进行产业链二阶映射联想 (不再受限于 Qwen)
        if not related_tickers:
            ai_stocks = await self._get_related_stocks_by_ai(
                title, concept, final_decision.get("reason", "")
            )
            for item in ai_stocks:
                if isinstance(item, dict):
                    _add_ticker(item.get("code", ""), item.get("name", ""))

        final_decision['related_tickers'] = related_tickers[:5]

        if final_decision['related_tickers']:
            final_decision['stock_data'] = await asyncio.to_thread(
                self._enrich_market_data, final_decision['related_tickers']
            )
            if final_decision.get('stock_data'):
                max_reaction = max([s.get('reaction_score', 0) for s in final_decision['stock_data']])
                final_decision['validation_score'] = max_reaction

                # 如果做多信号关联个股全部处于严重高位过热状态，自动下调初始置信度以防高位接盘
                if influence == "positive" and all(s.get("is_overheated") for s in final_decision["stock_data"]):
                    orig_conf = float(final_decision.get("confidence", 0.5))
                    final_decision["confidence"] = round(max(0.4, orig_conf - 0.12), 2)
                    final_decision["summary"] = f"[⚠️高位防兑现] {final_decision.get('summary', '')}"
            else:
                final_decision['validation_score'] = 0

            for stock in final_decision['stock_data']:
                try:
                    self.db.save_signal(
                        stock_code=stock['code'],
                        news_title=title,
                        signal=final_decision.get('stock_market_influence'),
                        confidence=final_decision.get('confidence', 0),
                        reason=final_decision.get('reason', ''),
                        price=float(stock['price']) if stock.get('price') else 0.0,
                        summary=f"[辩论] {final_decision.get('summary', '')}"
                    )
                except Exception as e:
                    logger.error(f"保存信号失败: {e}")
        else:
            final_decision['validation_score'] = 0

        # 存入长期记忆库
        if self.memory:
            try:
                self.memory.add_memory(
                    news_title=title,
                    summary=final_decision.get('summary', ''),
                    influence=influence,
                    reason=final_decision.get('reason', '')
                )
            except Exception as e:
                logger.debug(f"写入记忆库跳过: {e}")

        return self._attach_event_context(title, content, final_decision)

    def _build_deep_logic_prompt(self, title: str, content: str) -> str:
        """构建深度逻辑分析提示词"""
        return f"""你是一位资深A股投资分析师。请分析以下新闻对A股市场的影响。

【新闻标题】{title}
【新闻内容】{content or '无详细内容'}

请以JSON格式返回分析结果，包含以下字段：
{{
  "stock_market_influence": "positive/negative/neutral",
  "signal": "positive/negative/neutral",
  "confidence": 0.0-1.0,
  "reason": "简要说明判断理由",
  "concept": "相关A股概念板块",
  "a_share_stocks": [{{"code": "600xxx", "name": "股票名称"}}],
  "summary": "一句话总结"
}}
"""

    async def _analyze_legacy(self, title, content):
        prompt = self._build_deep_logic_prompt(title, content)
        res = await self._call_routed_json(prompt, preferred=["deepseek", "openai", "gemini", "kimi"])
        if res:
            inf = res.get("stock_market_influence") or res.get("signal") or "neutral"
            res["stock_market_influence"] = inf
            res["signal"] = inf
        return res

    def _attach_event_context(self, title: str, content: str, result: Dict[str, Any]) -> Dict[str, Any]:
        if not result:
            return result

        text = f"{title}\n{content}"
        template = match_event_template(text) or {
            "label": "未匹配模板",
            "fastest_source": "待人工确认",
            "transmission_path": "待人工确认",
            "hedge_leg": "仅A股交易，暂不对冲",
            "failure_conditions": "待人工确认",
        }

        sector_profiles = match_sectors(text)
        sector_names = [p["name"] for p in sector_profiles] or ["未分类"]
        mapping_layers = []
        verification_points = []
        for profile in sector_profiles:
            mapping_layers.extend(profile["mapping"])
            verification_points.extend(profile["verification"])

        alert_info = classify_alert_keywords(text)
        alert_level = alert_info["level"]
        alert_keywords = alert_info["keywords"]

        if not mapping_layers:
            mapping_layers = ["直接受益/受损", "间接受益/受损", "主题扩散"]
        if not verification_points:
            verification_points = ["量价匹配", "板块扩散度", "关键数据节点"]

        result["event_template"] = template
        result["sector_profiles"] = sector_profiles
        result["event_memo"] = {
            "event_original": title,
            "market_first_reaction": template["fastest_source"],
            "transmission_path": template["transmission_path"],
            "a_share_mapping": " / ".join(mapping_layers),
            "hedge_leg": template["hedge_leg"],
            "failure_conditions": template["failure_conditions"],
            "verification": "；".join(verification_points),
            "sectors": "、".join(sector_names),
            "alert_level": alert_level,
            "alert_keywords": "、".join(alert_keywords),
        }
        return result

    async def generate_gemini_review(self, news_title: str, bot_result: Dict) -> str:
        bull_point = bot_result.get('bull_point', '')
        bear_point = bot_result.get('bear_point', '')
        stocks_context = ""
        if bot_result.get('stock_data'):
            for s in bot_result['stock_data']:
                hold_tag = " [🌟我的持仓]" if s.get("is_hold") else ""
                stocks_context += (
                    f"股票：{s.get('name', '')} ({s['code']}){hold_tag} | 现价：{s['price']} | "
                    f"技术面：{s.get('tech', '')} | 参考买点：{s.get('buy_zone', 'N/A')} | 止损位：{s.get('stop_loss_price', 'N/A')}\n"
                )

        template_label = bot_result.get("event_template", {}).get("label", "通用商业/宏观事件")
        
        prompt = f"""
你是一名专业、客观的A股实战派投资顾问。请结合多空辩论与三维量价数据，推导以下事件对A股市场的具体操作策略。不要使用废话。

【新闻标题】{news_title}
【事件类型】{template_label}
【多方逻辑】{bull_point}
【空方风控】{bear_point}
【关联标的与三维量价】
{stocks_context or '暂无直接关联个股'}

请严格按以下格式输出（不要Markdown代码块）：

【事件解读】
(1-2句话简述新闻核心内容与预期差，英文需翻译成流畅中文)

【A股影响】
🚀 **利好方向**：
- (列出受益板块/股票、传导逻辑及技术面位置评价，如无则写"无")

🔻 **风险/兑现警告**：
- (指出空方担忧点、潜伏盘兑现风险或受损板块)

💡 **实战操作建议**：
(结合T+1制度、乖离率与参考买点/止损位，给出1-2条明确的波段执行建议，严禁盲目追高)
"""
        return await self._call_routed_text(
            prompt, preferred=["gemini", "deepseek", "openai", "kimi"]
        )

    @retry_async()
    async def _get_related_stocks_by_ai(self, title: str, concept: str, reason: str) -> List[Dict]:
        """多模型 A 股产业链二阶联想（支持 DeepSeek / GPT / Gemini / Kimi / Qwen）"""
        prompt = f"""任务：作为A股产业研究员，根据以下新闻和概念联想最正宗的1-3只A股上市公司（6位数字代码）。
新闻：{title}
概念：{concept}
逻辑：{reason}
请严格只输出 JSON 格式：
{{
  "stocks": [
    {{"code": "600xxx", "name": "股票中文简称"}}
  ]
}}"""
        res = await self._call_routed_json(
            prompt, preferred=["deepseek", "openai", "gemini", "kimi", "qwen"]
        )
        stocks = res.get("stocks", []) if isinstance(res, dict) else []
        return stocks if isinstance(stocks, list) else []

    @retry_async()
    async def _call_llm_json_async(self, client, model, prompt, name):
        try:
            if client is None:
                return await self._call_routed_json(prompt)
            resp = await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}
            )
            return self._parse_json_safely(resp.choices[0].message.content)
        except Exception as e:
            logger.error(f"{name} API 调用失败，走自动替补路由: {e}")
            return await self._call_routed_json(prompt)

    @retry_async()
    async def _call_gemini_text(self, prompt: str) -> str:
        """调用Gemini API（支持联网搜索），失败时自动fallback到Kimi/DeepSeek/GPT"""
        if not self.gemini_keys:
            logger.info("Gemini Key未配置，自动使用备用模型")
            return await self._call_fallback_text(prompt)

        key = random.choice(self.gemini_keys)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={key}"

        tools = [
            {
                "function_declarations": [
                    {
                        "name": "google_search",
                        "description": "搜索实时信息（新闻、股价、天气等）",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "搜索查询"
                                }
                            },
                            "required": ["query"]
                        }
                    }
                ]
            }
        ]

        try:
            session = await self._get_aiohttp_session()
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": tools
            }

            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidate = data.get('candidates', [{}])[0]
                    content_parts = candidate.get('content', {}).get('parts', [])

                    for part in content_parts:
                        if 'functionCall' in part:
                            function_call = part['functionCall']
                            function_name = function_call.get('name')
                            args = function_call.get('args', {})

                            logger.info(f"🔍 Gemini 请求搜索: {function_name}({args})")

                            if function_name == 'google_search':
                                search_results = await self._google_search(args['query'])
                                function_response = {
                                    "functionResponse": {
                                        "name": function_name,
                                        "response": search_results
                                    }
                                }
                                payload2 = {
                                    "contents": [
                                        {"parts": [{"text": prompt}]},
                                        {"parts": [{"functionResponse": function_response}]}
                                    ]
                                }
                                async with session.post(url, json=payload2, timeout=30) as resp2:
                                    if resp2.status == 200:
                                        data2 = await resp2.json()
                                        return data2['candidates'][0]['content']['parts'][0]['text']
                                    else:
                                        logger.warning(f"Gemini 搜索后响应错误: {resp2.status}")
                                        return await self._call_fallback_text(prompt)

                    if content_parts and 'text' in content_parts[0]:
                        return content_parts[0]['text']

                    return "抱歉，无法生成回复。"

                elif resp.status == 429:
                    logger.warning("Gemini API 配额用尽 (HTTP 429)，切换到替补模型")
                    await self._send_fallback_notification("Gemini", "配额用尽")
                    return await self._call_fallback_text(prompt)
                else:
                    logger.warning(f"Gemini API 错误: {resp.status}")
                    await self._send_fallback_notification("Gemini", f"HTTP {resp.status}")
                    return await self._call_fallback_text(prompt)
        except Exception as e:
            error_detail = f"{type(e).__name__}: {str(e)}" if str(e) else f"{type(e).__name__}"
            logger.error(f"Gemini 调用异常: {error_detail}")
            await self._send_fallback_notification("Gemini", error_detail)
            return await self._call_fallback_text(prompt)

    async def _call_fallback_text(self, prompt: str) -> str:
        """当 Gemini 不可用时，按 Kimi -> DeepSeek -> OpenAI -> Qwen 顺序替补"""
        if self.kimi_key:
            res = await self._call_kimi_text(prompt)
            if res:
                return res
        self._ensure_clients()
        for client, model in [
            (self.client_ds, self.deepseek_model),
            (self.client_openai, self.openai_model),
            (self.client_qwen, self.qwen_model),
        ]:
            if client:
                try:
                    resp = await client.chat.completions.create(
                        model=model, messages=[{"role": "user", "content": prompt}]
                    )
                    return resp.choices[0].message.content
                except Exception:
                    continue
        return ""

    async def _google_search(self, query: str) -> str:
        """使用 SerpApi 进行 Google 搜索"""
        serpapi_key = os.getenv('SERPAPI_KEY')
        if not serpapi_key:
            logger.warning("SerpApi Key缺失，无法搜索")
            return "搜索服务暂时不可用"

        keys = [k.strip() for k in serpapi_key.split(',') if k.strip()]
        selected_key = random.choice(keys)

        try:
            session = await self._get_aiohttp_session()
            params = {
                "engine": "google",
                "q": query,
                "api_key": selected_key,
                "num": 5
            }

            async with session.get("https://serpapi.com/search", params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []
                    for item in data.get('organic_results', [])[:3]:
                        results.append(f"标题: {item.get('title', '')}\n链接: {item.get('link', '')}\n摘要: {item.get('snippet', '')}")
                    return "\n\n".join(results)
                else:
                    logger.warning(f"SerpApi 搜索失败: HTTP {resp.status}")
                    return "搜索失败"
        except Exception as e:
            logger.error(f"Google 搜索异常: {e}")
            return "搜索异常"

    async def _call_kimi_text(self, prompt: str) -> str:
        """调用Kimi API作为替补"""
        if not self.kimi_key:
            return ""

        self._ensure_clients()
        if not self.client_kimi:
            return ""

        try:
            resp = await self.client_kimi.chat.completions.create(
                model=self.kimi_model,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"Kimi替补调用也失败: {e}")
            return ""

    async def _send_fallback_notification(self, api_name: str, reason: str):
        """发送API切换通知到Telegram"""
        if not self.telegram_bot or not self.chat_id:
            return

        try:
            msg = (
                f"⚠️ **API切换通知**\n\n"
                f"🔴 {api_name} API异常\n"
                f"📝 原因: {reason}\n"
                f"✅ 已自动切换到备用模型\n"
                f"⏰ {datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%H:%M')}"
            )
            if ParseMode:
                await self.telegram_bot.send_message(
                    chat_id=self.chat_id, text=msg, parse_mode=ParseMode.MARKDOWN
                )
            else:
                await self.telegram_bot.send_message(chat_id=self.chat_id, text=msg)
        except Exception as e:
            logger.error(f"发送Telegram通知失败: {e}")

    async def _call_gemini_json(self, prompt: str) -> Dict:
        text = await self._call_gemini_text(prompt + "\n请务必只输出 JSON，不要 Markdown。")
        return self._parse_json_safely(text)
    
    async def chat_with_model(self, model_alias: str, text: str) -> str:
        """多模型聊天路由 (支持 deepseek / gpt / gemini / kimi / qwen)"""
        self._ensure_clients()

        weekdays = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
        now_cn = datetime.now(pytz.timezone('Asia/Shanghai'))
        current_date = now_cn.strftime(f"%Y年%m月%d日 {weekdays[now_cn.weekday()]}")
        enhanced_prompt = f"【当前日期】{current_date}\n\n【用户问题】{text}\n\n请基于当前日期回答问题。"

        alias = model_alias.lower()
        if alias == 'deepseek' and self.client_ds:
            return await self._call_llm_text_async(self.client_ds, self.deepseek_model, enhanced_prompt)
        elif alias in ('gpt', 'openai') and self.client_openai:
            return await self._call_llm_text_async(self.client_openai, self.openai_model, enhanced_prompt)
        elif alias == 'kimi' and self.client_kimi:
            return await self._call_llm_text_async(self.client_kimi, self.kimi_model, enhanced_prompt)
        elif alias == 'qwen' and self.client_qwen:
            return await self._call_llm_text_async(self.client_qwen, self.qwen_model, enhanced_prompt)
        elif alias == 'gemini':
            return await self._call_gemini_text(enhanced_prompt)
        else:
            return await self._call_routed_text(enhanced_prompt)

    @retry_async()
    async def _call_llm_text_async(self, client, model, prompt):
        resp = await client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
        return resp.choices[0].message.content

    def _enrich_market_data(self, tickers: List[Dict]) -> List[Dict]:
        """
        v2.0 市场数据与三维量价验证增强：
        使用东方财富原生高速前复权日K线替代脆弱的 yfinance，并自动标记持仓状态 is_hold
        """
        results = []
        held_codes = {normalize_ashare_code(c) for c in self.config.get('my_positions', [])}

        for item in tickers:
            raw_code = item.get("code", "").strip()
            code = normalize_ashare_code(raw_code)
            if not code:
                continue
            
            try:
                hist = fetch_ashare_kline_sync(code, limit=120)
                if hist is not None and not hist.empty and len(hist) >= 20:
                    stock_name = item.get("name") or hist.attrs.get("stock_name") or code
                    ta_res = self.ta.analyze(hist, stock_code=code, stock_name=stock_name)
                    chart = generate_snapshot(hist.tail(60), f"{stock_name} ({code})")

                    reaction_score = ta_res.get("reaction_score", 0.5)
                    tech_summary = ta_res.get("summary", "数据不足")
                    bt = ta_res.get("backtest")

                    results.append({
                        "code": code,
                        "name": stock_name,
                        "is_hold": code in held_codes,
                        "price": f"{float(hist['Close'].iloc[-1]):.2f}",
                        "tech": tech_summary,
                        "chart": chart,
                        "win_rate": bt.get('win_rate', 0) if bt else 0,
                        "reaction_score": round(float(reaction_score), 3),
                        "resonance_score": ta_res.get("resonance_score", 0.5),
                        "bias_20": ta_res.get("bias_20", 0.0),
                        "ret_3d": ta_res.get("ret_3d", 0.0),
                        "is_overheated": ta_res.get("is_overheated", False),
                        "is_limit_up": ta_res.get("is_limit_up", False),
                        "buy_zone": ta_res.get("buy_zone", "N/A"),
                        "stop_loss_price": ta_res.get("stop_loss_price", "N/A"),
                    })
            except Exception as e:
                logger.error(f"行情获取失败 {code}: {e}")
        return results

    async def _analyze_technical_deepseek(self, code, df) -> Dict:
        """技术派指标结构分析 (路由优先级: DeepSeek -> GPT -> Gemini -> Kimi)"""
        latest = df.iloc[-1]
        base_idx = -10 if len(df) >= 10 else 0
        chg_10d = (latest['收盘'] - df.iloc[base_idx]['收盘']) / df.iloc[base_idx]['收盘'] * 100
        prompt = f"""角色：资深A股技术派操盘手。分析【{code}】。
数据：现价{latest['收盘']:.2f}，10日涨跌{chg_10d:.1f}%。
近10日收盘：{', '.join([f'{x:.2f}' for x in df['收盘'].tail(10)])}。
请输出JSON：
{{
    "trend": "上涨/下跌/震荡",
    "support": 12.34,
    "resistance": 15.67,
    "ma_signal": "5日线上穿10日线"
}}"""
        return await self._call_routed_json(prompt, preferred=["deepseek", "openai", "gemini", "kimi"])

    async def _analyze_pattern_qwen(self, code, df) -> Dict:
        """K线形态与主力意图识别 (支持全模型自动路由，不再依赖 Qwen)"""
        tail_cols = [c for c in ['日期', '开盘', '收盘', '最高', '最低', '成交量', '涨跌幅', '换手率'] if c in df.columns]
        records_json = df[tail_cols].tail(10).to_json(orient='records', force_ascii=False)
        prompt = f"""角色：A股短线游资。分析【{code}】的K线形态与量价承接。
数据：{records_json}
请输出JSON：
{{
    "pattern": "老鸭头/出水芙蓉/温和放量突破/高位缩量回调/断头铡刀...",
    "bull_strength": 7,
    "intent": "主力洗盘/吸筹/拉升/出货"
}}"""
        return await self._call_routed_json(prompt, preferred=["openai", "deepseek", "gemini", "kimi", "qwen"])

    async def _synthesize_holdings_advice(self, code, price, tech, pattern) -> Dict:
        """综合会诊操作建议"""
        prompt = f"""
你是一名实战派A股老股民，请根据以下技术面与形态面分析，给出明确、接地气的T+1波段操作建议。

【技术面分析】
趋势：{tech.get('trend')}
支撑：{tech.get('support')}
压力：{tech.get('resistance')}
信号：{tech.get('ma_signal') or tech.get(' ma_signal')}

【形态与资金面分析】
形态：{pattern.get('pattern')}
主力意图：{pattern.get('intent')}
多头力度：{pattern.get('bull_strength')}/10

【当前信息】
股票：{code}
现价：{price}

请输出JSON（严格格式）：
{{
    "action": "安心持有 / 逢低加仓 / 分批减仓 / 止损离场",
    "safe_range": "安全的持股/低吸价格区间",
    "risk_alert": "明确跌破多少元止损离场",
    "reason": "一句话大白话理由",
    "trend": "{tech.get('trend', '震荡')}"
}}
"""
        return await self._call_routed_json(prompt, preferred=["gemini", "deepseek", "openai", "kimi"])

    async def analyze_holdings_trend(self, stock_codes: List[str]) -> List[Dict]:
        """📊 分析持仓股票走势（使用东方财富高速前复权日K线 + 多模型会诊）"""
        results = []

        for raw_code in stock_codes:
            code = normalize_ashare_code(raw_code)
            try:
                df = await asyncio.to_thread(fetch_ashare_kline_sync, code, 40)
                if df is None or df.empty or len(df) < 10:
                    logger.warning(f"股票 {code} 数据不足，跳过分析")
                    continue

                stock_name = df.attrs.get("stock_name", code)
                latest = df.iloc[-1]
                prev_5 = df.iloc[-5] if len(df) >= 5 else df.iloc[0]
                prev_10 = df.iloc[-10] if len(df) >= 10 else df.iloc[0]

                current_price = float(latest['收盘'])
                ma5 = float(df['收盘'].tail(5).mean())
                ma10 = float(df['收盘'].tail(10).mean())
                ma20 = float(df['收盘'].tail(20).mean()) if len(df) >= 20 else ma10

                change_5d = (current_price - float(prev_5['收盘'])) / float(prev_5['收盘']) * 100
                change_10d = (current_price - float(prev_10['收盘'])) / float(prev_10['收盘']) * 100

                volume_latest = float(latest['成交量'])
                volume_avg = float(df['成交量'].tail(10).mean())
                volume_ratio = volume_latest / volume_avg if volume_avg > 0 else 1.0

                task_tech = self._analyze_technical_deepseek(code, df)
                task_pattern = self._analyze_pattern_qwen(code, df)
                tech_res, pattern_res = await asyncio.gather(task_tech, task_pattern, return_exceptions=True)

                if isinstance(tech_res, Exception) or not isinstance(tech_res, dict):
                    tech_res = {}
                if isinstance(pattern_res, Exception) or not isinstance(pattern_res, dict):
                    pattern_res = {}

                if not tech_res and not pattern_res:
                    analysis_result = self._fallback_trend_analysis(
                        current_price, ma5, ma10, change_5d, change_10d, volume_ratio
                    )
                    final_advice = {
                        "action": "观望",
                        "safe_range": f"{analysis_result['support']} - {analysis_result['resistance']}",
                        "risk_alert": f"跌破 {analysis_result['support']}",
                        "reason": analysis_result['reason'],
                        "trend": analysis_result.get('trend', '震荡')
                    }
                else:
                    final_advice = await self._synthesize_holdings_advice(
                        f"{stock_name}({code})", current_price, tech_res, pattern_res
                    )

                trend = final_advice.get('trend', '震荡')
                confidence = 0.8

                trend_to_signal = {
                    '上涨': 'positive',
                    '下跌': 'negative',
                    '震荡': 'neutral'
                }
                signal_type = trend_to_signal.get(trend, 'neutral')

                self.db.save_signal(
                    stock_code=code,
                    news_title=f"[持仓会诊] {stock_name}({code}) {final_advice.get('action')}",
                    signal=signal_type,
                    confidence=confidence,
                    reason=final_advice.get('reason'),
                    price=float(current_price),
                    summary=f"安全区: {final_advice.get('safe_range')} | 警惕: {final_advice.get('risk_alert')}",
                    confidence_effective=confidence
                )

                results.append({
                    'code': code,
                    'name': stock_name,
                    'trend': trend,
                    'signal': signal_type,
                    'confidence': confidence,
                    'reason': final_advice.get('reason'),
                    'action': final_advice.get('action'),
                    'safe_range': final_advice.get('safe_range'),
                    'risk_alert': final_advice.get('risk_alert'),
                    'current_price': current_price,
                    'support': tech_res.get('support', 'N/A'),
                    'resistance': tech_res.get('resistance', 'N/A'),
                    'pattern': pattern_res.get('pattern', 'N/A'),
                    'change_5d': change_5d,
                    'change_10d': change_10d,
                    'volume_ratio': volume_ratio,
                    'analyzed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })

                logger.info(f"✅ {stock_name}({code}) 走势分析完成: {trend}")

            except Exception as e:
                logger.error(f"❌ 股票 {code} 趋势分析失败: {e}", exc_info=True)

        return results

    def _fallback_trend_analysis(self, price, ma5, ma10, change_5d, change_10d, volume_ratio):
        """基础规则分析（当AI不可用时）"""
        if price > ma5 > ma10 and change_5d > 2:
            return {
                'trend': '上涨',
                'confidence': 0.7,
                'reason': f'价格{price:.2f}站上均线多头，5日涨幅{change_5d:+.1f}%',
                'support': round(ma5 * 0.98, 2),
                'resistance': round(price * 1.03, 2)
            }
        elif price < ma5 < ma10 and change_5d < -2:
            return {
                'trend': '下跌',
                'confidence': 0.7,
                'reason': f'价格{price:.2f}跌破短期均线，5日跌幅{change_5d:+.1f}%',
                'support': round(price * 0.97, 2),
                'resistance': round(ma5 * 1.01, 2)
            }
        else:
            return {
                'trend': '震荡',
                'confidence': 0.5,
                'reason': f'价格在均线附近整理，5日涨跌{change_5d:+.1f}%',
                'support': round(min(price, ma5) * 0.98, 2),
                'resistance': round(max(price, ma5) * 1.02, 2)
            }
