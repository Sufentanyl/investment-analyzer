from rag_memory import RAGMemory
from technical_analysis import TechnicalAnalyzer
from database import DatabaseManager
from chart_generator import generate_snapshot
from event_templates import match_event_template, match_sectors, classify_alert_keywords
import json
import logging
import os
import re
import asyncio
import aiohttp
import random
import yaml
from datetime import datetime
from typing import Any, Dict, List, Optional
import yfinance as yf
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
        self.qwen_model = os.getenv("QWEN_MODEL", "qwen-plus")

        keys_str = os.getenv("GEMINI_API_KEY", "")
        self.gemini_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

        # 🔥 新增: Kimi API (替补)
        self.kimi_key = os.getenv("KIMI_API_KEY")
        self.kimi_base = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
        self.kimi_model = "moonshot-v1-8k"

        # 2. 核心组件
        self.ta = TechnicalAnalyzer()
        self.db = DatabaseManager()
        self.client_ds = None
        self.client_qwen = None
        self.client_kimi = None  # 🔥 新增

        # 🔥 修复: aiohttp session 复用
        self._aiohttp_session = None

        # 🔥 新增: Telegram Bot (用于发送fallback通知)
        self.telegram_bot = None
        self.chat_id = None

        try:
            self.memory = RAGMemory()
        except Exception as e:
            logger.warning(f"RAGMemory 初始化失败: {e}")
            self.memory = None

        # 3. 加载配置文件
        self.config_path = '/app/config.yaml'
        self.config = self._load_yaml_config()

        self.threshold_hold = float(os.getenv("CONFIDENCE_THRESHOLD_HOLD", "0.65"))
        self.threshold_normal = float(os.getenv("CONFIDENCE_THRESHOLD_NORMAL", "0.75"))

    def set_telegram_bot(self, bot, chat_id):
        """🔥 新增: 设置Telegram Bot用于发送通知"""
        self.telegram_bot = bot
        self.chat_id = chat_id

    def _ensure_clients(self):
        if not self.client_ds and self.deepseek_key:
            self.client_ds = AsyncOpenAI(api_key=self.deepseek_key, base_url=self.deepseek_base)
        if not self.client_qwen and self.qwen_key:
            self.client_qwen = AsyncOpenAI(api_key=self.qwen_key, base_url=self.qwen_base)
        if not self.client_kimi and self.kimi_key:
            self.client_kimi = AsyncOpenAI(api_key=self.kimi_key, base_url=self.kimi_base)

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
            "agents": {},
            "auto_bind_keywords": True,  # 默认启用AI自动绑定关键词
            "alert_levels_to_push": ["strong", "normal"]  # 默认过滤 info
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

    def auto_bind_keywords(self, keywords: list, stock_code: str):
        """AI自动绑定关键词到股票"""
        if 'concept_db' not in self.config:
            self.config['concept_db'] = {}

        for keyword in keywords:
            keyword_lower = keyword.lower().strip()
            if keyword_lower and len(keyword_lower) >= 2:  # 至少2个字符
                self.config['concept_db'].setdefault(keyword_lower, [])
                if stock_code not in self.config['concept_db'][keyword_lower]:
                    self.config['concept_db'][keyword_lower].append(stock_code)
                    logger.info(f"🔗 AI自动绑定: '{keyword}' -> {stock_code}")

        self.save_config()
        return True

    async def analyze_cross_validate(self, title: str, content: str) -> Dict[str, Any]:
        """Buffett vs Munger 辩论模式"""
        self._ensure_clients()
        agents = self.config.get('agents', {})
        if not agents or 'bull_agent' not in agents:
            result = await self._analyze_legacy(title, content)
            return self._attach_event_context(title, content, result)

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
            if final_decision.get('stock_data'):
                max_reaction = max([s.get('reaction_score', 0) for s in final_decision['stock_data']])
                final_decision['validation_score'] = max_reaction
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

        return self._attach_event_context(title, content, final_decision)

    async def _analyze_legacy(self, title, content):
        self._ensure_clients()
        if not self.client_ds: return {}
        prompt = self._build_deep_logic_prompt(title, content)
        return await self._call_llm_json_async(self.client_ds, self.deepseek_model, prompt, "DeepSeek")

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
                stocks_context += f"股票：{s['name']} ({s['code']}) | 现价：{s['price']} | 技术：{s.get('tech')}\n"

        event_memo = bot_result.get("event_memo", {})
        template_label = bot_result.get("event_template", {}).get("label", "未匹配模板")
        prompt = f"""
你是一名投资顾问。请根据以下“大师辩论”结果，写一份幽默总结。
【新闻】{news_title}
【模板】{template_label}
【传导路径】{event_memo.get('transmission_path', '待确认')}
【多头】{bull_point}
【空头】{bear_point}
【结论】{bot_result.get('reason')}
【盘面】{stocks_context}
【二次验证】{event_memo.get('verification', '量价匹配/板块扩散/关键数据节点')}
请输出：1.大师分歧 2.操作建议 3.避坑指南
"""
        return await self._call_gemini_text(prompt)

    @retry_async()
    async def _get_related_stocks_by_ai(self, title, concept, reason):
        self._ensure_clients()
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
        """调用Gemini API（支持联网搜索），失败时fallback到Kimi"""
        if not self.gemini_keys:
            logger.warning("Gemini Key缺失，使用Kimi替补")
            return await self._call_kimi_text(prompt)

        key = random.choice(self.gemini_keys)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={key}"

        # 🔥 声明 Google Search 工具
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

            # 第一次调用：可能触发 function call
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": tools
            }

            async with session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # 检查是否有 function call
                    candidate = data.get('candidates', [{}])[0]
                    content_parts = candidate.get('content', {}).get('parts', [])

                    for part in content_parts:
                        if 'functionCall' in part:
                            # 模型要求搜索
                            function_call = part['functionCall']
                            function_name = function_call.get('name')
                            args = function_call.get('args', {})

                            logger.info(f"🔍 Gemini 请求搜索: {function_name}({args})")

                            if function_name == 'google_search':
                                # 调用 SerpApi 搜索
                                search_results = await self._google_search(args['query'])

                                # 构建函数响应
                                function_response = {
                                    "functionResponse": {
                                        "name": function_name,
                                        "response": search_results
                                    }
                                }

                                # 第二次调用：提供搜索结果
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
                                        return await self._call_kimi_text(prompt)

                    # 如果没有 function call，直接返回文本
                    if 'text' in content_parts[0]:
                        return content_parts[0]['text']

                    return "抱歉，无法生成回复。"

                elif resp.status == 429:
                    logger.warning(f"Gemini API 配额用尽 (HTTP 429)，切换到Kimi替补")
                    await self._send_fallback_notification("Gemini", "配额用尽")
                    return await self._call_kimi_text(prompt)
                else:
                    logger.warning(f"Gemini API 错误: {resp.status}")
                    await self._send_fallback_notification("Gemini", f"HTTP {resp.status}")
                    return await self._call_kimi_text(prompt)
        except Exception as e:
            logger.error(f"Gemini 调用异常: {e}")
            await self._send_fallback_notification("Gemini", str(e))
            return await self._call_kimi_text(prompt)

    async def _google_search(self, query: str) -> str:
        """使用 SerpApi 进行 Google 搜索"""
        serpapi_key = os.getenv('SERPAPI_KEY')
        if not serpapi_key:
            logger.warning("SerpApi Key缺失，无法搜索")
            return "搜索服务暂时不可用"

        # 从逗号分隔的keys中随机选择一个
        keys = [k.strip() for k in serpapi_key.split(',')]
        selected_key = random.choice(keys)

        try:
            session = await self._get_aiohttp_session()
            params = {
                "engine": "google",
                "q": query,
                "api_key": selected_key,
                "num": 5  # 限制结果数量
            }

            async with session.get("https://serpapi.com/search", params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # 格式化搜索结果
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
        """🔥 新增: 调用Kimi API作为替补"""
        if not self.kimi_key:
            logger.error("Kimi API Key缺失，无法替补")
            return ""

        self._ensure_clients()
        if not self.client_kimi:
            logger.error("Kimi客户端初始化失败")
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
        """🔥 新增: 发送API切换通知到Telegram"""
        if not self.telegram_bot or not self.chat_id:
            return

        try:
            msg = f"⚠️ **API切换通知**\n\n"
            msg += f"🔴 {api_name} API异常\n"
            msg += f"📝 原因: {reason}\n"
            msg += f"✅ 已自动切换到Kimi替补\n"
            msg += f"⏰ {datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%H:%M')}"

            if ParseMode:
                await self.telegram_bot.send_message(
                    chat_id=self.chat_id,
                    text=msg,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await self.telegram_bot.send_message(
                    chat_id=self.chat_id,
                    text=msg
                )
            logger.info(f"已发送API切换通知: {api_name} -> Kimi")
        except Exception as e:
            logger.error(f"发送Telegram通知失败: {e}")

    async def _call_gemini_json(self, prompt: str) -> Dict:
        text = await self._call_gemini_text(prompt + "\n请务必只输出 JSON，不要 Markdown。")
        try:
            cleaned = re.sub(r"```json|```", "", text).strip()
            return json.loads(cleaned)
        except Exception as e:
            # 尝试从文本中截取 JSON
            try:
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
            except Exception as e2:
                logger.error(f"Gemini JSON 解析失败: {e2}")
            logger.error(f"Gemini JSON 解析失败: {e}")
            return {}
    
    async def chat_with_model(self, model_alias: str, text: str) -> str:
        """🤖 多模型聊天路由"""
        self._ensure_clients()

        # 获取当前日期
        from datetime import datetime
        current_date = datetime.now().strftime("%Y年%m月%d日 %A")

        # 构建带日期的 prompt
        enhanced_prompt = f"【当前日期】{current_date}\n\n【用户问题】{text}\n\n请基于当前日期回答问题。"

        if model_alias == 'deepseek' and self.client_ds:
            return await self._call_llm_text_async(self.client_ds, self.deepseek_model, enhanced_prompt)
        elif model_alias == 'qwen' and self.client_qwen:
            return await self._call_llm_text_async(self.client_qwen, self.qwen_model, enhanced_prompt)
        elif model_alias == 'gemini':
            return await self._call_gemini_text(enhanced_prompt)
        else:
            # 默认使用 Gemini
            return await self._call_gemini_text(enhanced_prompt)

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

                    # 量价验证评分（近1日量价异动）
                    recent = hist.iloc[-1]
                    prev = hist.iloc[-2]
                    vol_mean = hist['Volume'].iloc[-20:].mean()
                    vol_ratio = (recent['Volume'] / vol_mean) if vol_mean else 0
                    price_move = abs(recent['Close'] - prev['Close']) / prev['Close'] if prev['Close'] else 0
                    reaction_score = min(1.0, 0.6 * min(vol_ratio / 2.0, 1.0) + 0.4 * min(price_move / 0.03, 1.0))
                    
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
                        "win_rate": bt.get('win_rate', 0) if bt else 0,
                        "reaction_score": round(reaction_score, 3)
                    })
            except Exception as e:
                logger.error(f"行情获取失败 {code}: {e}")
        return results

    def _build_deep_logic_prompt(self, title, content):
        return f"分析新闻：{title}\n输出JSON: {{ 'stock_market_influence': 'positive/neutral', 'confidence': 0.8, 'reason': '...' }}"
