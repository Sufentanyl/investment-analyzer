from rag_memory import RAGMemory
from technical_analysis import TechnicalAnalyzer
from database import DatabaseManager
from chart_generator import generate_snapshot
import json
import logging
import os
import re
import asyncio
import aiohttp
import random
import yaml
from typing import Any, Dict, List, Optional
import yfinance as yf

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# 简单的异步重试装饰器
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

class LLMAnalyzer:
    def __init__(self, **kwargs):
        # 1. API 初始化
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.deepseek_model = "deepseek-chat"

        self.qwen_key = os.getenv("QWEN_API_KEY")
        self.qwen_base = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.qwen_model = "qwen-max"

        keys_str = os.getenv("GEMINI_API_KEY", "")
        self.gemini_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

        # 2. 核心组件
        self.ta = TechnicalAnalyzer()
        self.db = DatabaseManager()
        self.client_ds = None
        self.client_qwen = None

        # 🔥 修复: aiohttp session 复用
        self._aiohttp_session = None

        try:
            self.memory = RAGMemory()
        except Exception as e:
            logger.warning(f"RAGMemory 初始化失败: {e}")
            self.memory = None

        # 3. 加载配置文件
        self.config_path = '/app/config.yaml'
        self.config = self._load_yaml_config()

        self.threshold_hold = 0.7
        self.threshold_normal = 0.8

    def _ensure_clients(self):
        if not self.client_ds and self.deepseek_key:
            self.client_ds = AsyncOpenAI(api_key=self.deepseek_key, base_url=self.deepseek_base)
        if not self.client_qwen and self.qwen_key:
            self.client_qwen = AsyncOpenAI(api_key=self.qwen_key, base_url=self.qwen_base)

    async def _get_aiohttp_session(self):
        """🔥 修复: 复用 aiohttp.ClientSession"""
        if self._aiohttp_session is None or self._aiohttp_session.closed:
            self._aiohttp_session = aiohttp.ClientSession()
        return self._aiohttp_session

    async def close(self):
        """🔥 新增: 清理资源"""
        if self._aiohttp_session and not self._aiohttp_session.closed:
            await self._aiohttp_session.close()

    def _load_yaml_config(self):
        default_conf = {
            "my_positions": [],
            "concept_db": {},
            "agents": {}
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if 'positions' in data:
                        data['my_positions'] = data['positions'].get('watching', [])
                        data['concept_db'] = data['positions'].get('keywords', {})
                    return data
            except Exception as e:
                logger.error(f"❌ 读取 config.yaml 失败: {e}")

        # 回退到 JSON
        json_path = '/app/data/user_config.json'
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"读取 JSON 配置失败: {e}")
        return default_conf

    def save_config(self, config=None):
        """🔥 修复: 实现配置保存"""
        if config is None:
            config = self.config

        json_path = '/app/data/user_config.json'
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
        if code not in self.config.get('my_positions', []):
            self.config.setdefault('my_positions', []).append(code)
            self.save_config()  # 🔥 修复: 自动保存
            return True
        return False

    def remove_position(self, code):
        if code in self.config.get('my_positions', []):
            self.config['my_positions'].remove(code)
            self.save_config()  # 🔥 修复: 自动保存
            return True
        return False

    def bind_keyword(self, keyword, code):
        if 'concept_db' not in self.config:
            self.config['concept_db'] = {}
        self.config['concept_db'].setdefault(keyword.lower(), []).append(code)
        self.save_config()  # 🔥 修复: 自动保存
        return True

    async def analyze_cross_validate(self, title: str, content: str) -> Dict[str, Any]:
        """Buffett vs Munger 辩论模式"""
        agents = self.config.get('agents', {})
        if not agents or 'bull_agent' not in agents:
            return await self._analyze_legacy(title, content)

        logger.info(f"🎭 启动多智能体辩论: {title}")
        
        bull_prompt = f"{agents['bull_agent']['prompt']}\n\n【新闻】{title}\n{content[:800]}"
        bear_prompt = f"{agents['bear_agent']['prompt']}\n\n【新闻】{title}\n{content[:800]}"
        
        task_bull = self._call_gemini_text(bull_prompt)
        task_bear = self._call_gemini_text(bear_prompt)
        bull_view, bear_view = await asyncio.gather(task_bull, task_bear)
        
        judge_prompt = f"""
{agents['judge_agent']['prompt']}

【多方观点】{bull_view}
【空方观点】{bear_view}

请输出 JSON:
{{
  "stock_market_influence": "positive"/"negative"/"neutral",
  "confidence": 0.0-1.0,
  "summary": "一句话辩论总结",
  "reason": "综合两方观点的最终逻辑",
  "concept": "核心概念",
  "bull_point": "多方理由",
  "bear_point": "空方理由"
}}
"""
        final_decision = await self._call_gemini_json(judge_prompt)
        
        if not final_decision or final_decision.get('confidence', 0) < 0.4:
            return {}

        related_tickers = []
        concept = final_decision.get('concept', '')
        
        db = self.config.get('concept_db', {})
        for kw, code in db.items():
            if kw in title or kw in concept:
                if isinstance(code, list):
                    for c in code: related_tickers.append({"code": c})
                else:
                    related_tickers.append({"code": code})
        
        if not related_tickers and self.client_qwen:
            ai_stocks = await self._get_related_stocks_by_ai(title, concept, "")
            related_tickers.extend(ai_stocks)

        final_decision['related_tickers'] = related_tickers

        if related_tickers:
            final_decision['stock_data'] = self._enrich_market_data(related_tickers)
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

        return final_decision

    async def _analyze_legacy(self, title, content):
        if not self.client_ds: return {}
        prompt = self._build_deep_logic_prompt(title, content)
        return await self._call_llm_json_async(self.client_ds, self.deepseek_model, prompt, "DeepSeek")

    async def generate_gemini_review(self, news_title: str, bot_result: Dict) -> str:
        bull_point = bot_result.get('bull_point', '')
        bear_point = bot_result.get('bear_point', '')
        stocks_context = ""
        if bot_result.get('stock_data'):
            for s in bot_result['stock_data']:
                stocks_context += f"股票：{s['name']} ({s['code']}) | 现价：{s['price']} | 技术：{s.get('tech')}\n"

        prompt = f"""
你是一名投资顾问。请根据以下“大师辩论”结果，写一份幽默总结。
【新闻】{news_title}
【多头】{bull_point}
【空头】{bear_point}
【结论】{bot_result.get('reason')}
【盘面】{stocks_context}
请输出：1.大师分歧 2.操作建议 3.避坑指南
"""
        return await self._call_gemini_text(prompt)

    @retry_async()
    async def _get_related_stocks_by_ai(self, title, concept, reason):
        if not self.client_qwen: return []
        prompt = f"任务：A股产业链联想\n新闻：{title}\n概念：{concept}\n输出JSON Only：{{ \"stocks\": [ {{ \"code\": \"600xxx\", \"name\": \"中文名\" }} ] }}"
        try:
            resp = await self.client_qwen.chat.completions.create(
                model=self.qwen_model, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}
            )
            return json.loads(re.sub(r"```json|```", "", resp.choices[0].message.content).strip()).get("stocks", [])
        except Exception as e:
            logger.error(f"AI 股票联想失败: {e}")
            return []

    @retry_async()
    async def _call_llm_json_async(self, client, model, prompt, name):
        try:
            resp = await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}
            )
            return json.loads(re.sub(r"```json|```", "", resp.choices[0].message.content).strip())
        except Exception as e:
            logger.error(f"{name} API 调用失败: {e}")
            return {}

    @retry_async()
    async def _call_gemini_text(self, prompt: str) -> str:
        if not self.gemini_keys: return "Gemini Key缺失"
        key = random.choice(self.gemini_keys)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={key}"
        try:
            # 🔥 修复: 使用复用的 session
            session = await self._get_aiohttp_session()
            async with session.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
                else:
                    logger.warning(f"Gemini API 错误: {resp.status}")
        except Exception as e:
            logger.error(f"Gemini 调用异常: {e}")
        return ""

    async def _call_gemini_json(self, prompt: str) -> Dict:
        text = await self._call_gemini_text(prompt + "\n请务必只输出 JSON，不要 Markdown。")
        try:
            return json.loads(re.sub(r"```json|```", "", text).strip())
        except Exception as e:
            logger.error(f"Gemini JSON 解析失败: {e}")
            return {}
    
    async def chat_with_model(self, model_alias: str, text: str) -> str:
        self._ensure_clients()
        if model_alias == 'deepseek' and self.client_ds:
            return await self._call_llm_text_async(self.client_ds, self.deepseek_model, text)
        return await self._call_gemini_text(text)

    @retry_async()
    async def _call_llm_text_async(self, client, model, prompt):
        resp = await client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
        return resp.choices[0].message.content

    def _enrich_market_data(self, tickers: List[Dict]) -> List[Dict]:
        results = []
        for item in tickers:
            code = item.get("code", "").strip()
            if code.isdigit():
                if code.startswith("6"): code += ".SS"
                else: code += ".SZ"
            
            try:
                hist = yf.Ticker(code).history(period="6mo")
                if not hist.empty and len(hist) > 20:
                    ta_res = self.ta.analyze(hist)
                    chart = generate_snapshot(hist, item.get('name', code))
                    
                    tech_summary = ta_res.get("summary", "数据不足")
                    bt = ta_res.get("backtest")
                    if bt and bt.get('win_rate', 0) > 0.65:
                        tech_summary += " | ⭐历史表现优异"
                    elif bt and bt.get('win_rate', 0) < 0.35:
                        tech_summary += " | 💀历史表现极差"

                    results.append({
                        "code": code, 
                        "name": item.get("name", ""), 
                        "price": f"{hist['Close'].iloc[-1]:.2f}", 
                        "tech": tech_summary, 
                        "chart": chart,
                        "win_rate": bt.get('win_rate', 0) if bt else 0
                    })
            except Exception as e:
                logger.error(f"行情获取失败 {code}: {e}")
        return results

    def _build_deep_logic_prompt(self, title, content):
        return f"分析新闻：{title}\n输出JSON: {{ 'stock_market_influence': 'positive/neutral', 'confidence': 0.8, 'reason': '...' }}"