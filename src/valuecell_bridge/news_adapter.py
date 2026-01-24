"""
News Adapter
封装 ValueCell 的智能新闻分析功能
"""

import os
import re
import json
import logging
import asyncio
import aiohttp
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    source: str
    published: str
    url: str
    summary: Optional[str] = None
    impact_analysis: Optional[str] = None


class NewsAdapter:
    """
    新闻代理适配器
    提供智能新闻分析功能，包括:
    - 突发新闻获取
    - 金融新闻获取
    - 新闻影响分析
    - A 股关联分析
    """
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        
        # 导入配置
        from .config import get_model_config, create_openai_client
        self.model_config = get_model_config("news_agent")
        self.client = create_openai_client(self.model_config)
        
        logger.info(f"📰 NewsAdapter 初始化完成，使用模型: {self.model_config.provider}/{self.model_config.model_id}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """关闭资源"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get_smart_news(self, keyword: str, limit: int = 10) -> Dict[str, Any]:
        """
        智能新闻获取与分析
        
        Args:
            keyword: 搜索关键词
            limit: 最大返回数量
        
        Returns:
            包含新闻和分析的字典
        """
        logger.info(f"📰 智能新闻分析: {keyword}")
        
        result = {
            "keyword": keyword,
            "news": [],
            "breaking_news": [],
            "financial_news": [],
            "summary": "",
            "a_share_impact": []
        }
        
        try:
            # 1. 获取突发新闻
            breaking = await self.get_breaking_news(keyword, limit=3)
            result["breaking_news"] = breaking
            
            # 2. 获取金融新闻
            financial = await self.get_financial_news(keyword, limit=5)
            result["financial_news"] = financial
            
            # 3. 合并所有新闻
            all_news = breaking + financial
            result["news"] = all_news[:limit]
            
            # 4. 生成综合分析
            if all_news:
                analysis = await self.analyze_news_impact(all_news)
                result["summary"] = analysis.get("summary", "")
                result["a_share_impact"] = analysis.get("a_share_impact", [])
            
        except Exception as e:
            logger.error(f"❌ 智能新闻分析失败: {e}")
            result["error"] = str(e)
        
        return result
    
    async def get_breaking_news(self, keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取突发新闻
        
        Args:
            keyword: 搜索关键词
            limit: 最大返回数量
        
        Returns:
            新闻列表
        """
        logger.info(f"🔴 获取突发新闻: {keyword}")
        
        news = []
        serpapi_key = os.getenv("SERPAPI_KEY")
        
        if not serpapi_key:
            logger.warning("⚠️ SERPAPI_KEY 未配置")
            return news
        
        try:
            session = await self._get_session()
            
            import random
            keys = [k.strip() for k in serpapi_key.split(",")]
            selected_key = random.choice(keys)
            
            # 使用 Google News 引擎
            params = {
                "engine": "google_news",
                "q": keyword,
                "api_key": selected_key,
                "hl": "en",
                "gl": "us"
            }
            
            async with session.get("https://serpapi.com/search", params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    for item in data.get("news_results", [])[:limit]:
                        news.append({
                            "title": item.get("title", ""),
                            "source": item.get("source", {}).get("name", "Unknown"),
                            "date": item.get("date", ""),
                            "link": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                            "type": "breaking"
                        })
                    
                    logger.info(f"✅ 获取到 {len(news)} 条突发新闻")
        
        except asyncio.TimeoutError:
            logger.warning("⚠️ 获取新闻超时")
        except Exception as e:
            logger.error(f"❌ 获取新闻异常: {e}")
        
        return news
    
    async def get_financial_news(self, keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取金融新闻
        
        Args:
            keyword: 搜索关键词
            limit: 最大返回数量
        
        Returns:
            新闻列表
        """
        logger.info(f"💰 获取金融新闻: {keyword}")
        
        news = []
        serpapi_key = os.getenv("SERPAPI_KEY")
        
        if not serpapi_key:
            logger.warning("⚠️ SERPAPI_KEY 未配置")
            return news
        
        try:
            session = await self._get_session()
            
            import random
            keys = [k.strip() for k in serpapi_key.split(",")]
            selected_key = random.choice(keys)
            
            # 使用 Google 搜索，限定财经网站
            params = {
                "engine": "google",
                "q": f"{keyword} (site:bloomberg.com OR site:reuters.com OR site:wsj.com OR site:ft.com)",
                "api_key": selected_key,
                "num": limit,
                "tbm": "nws"  # 新闻搜索
            }
            
            async with session.get("https://serpapi.com/search", params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    for item in data.get("news_results", [])[:limit]:
                        news.append({
                            "title": item.get("title", ""),
                            "source": item.get("source", "Unknown"),
                            "date": item.get("date", ""),
                            "link": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                            "type": "financial"
                        })
                    
                    logger.info(f"✅ 获取到 {len(news)} 条金融新闻")
        
        except asyncio.TimeoutError:
            logger.warning("⚠️ 获取新闻超时")
        except Exception as e:
            logger.error(f"❌ 获取新闻异常: {e}")
        
        return news
    
    async def analyze_news_impact(self, news_list: List[Dict]) -> Dict[str, Any]:
        """
        分析新闻对 A 股的影响
        
        Args:
            news_list: 新闻列表
        
        Returns:
            影响分析结果
        """
        if not self.client:
            return {"summary": "⚠️ LLM 客户端未初始化", "a_share_impact": []}
        
        if not news_list:
            return {"summary": "暂无新闻可分析", "a_share_impact": []}
        
        # 构建新闻摘要
        news_text = ""
        for i, n in enumerate(news_list[:8], 1):
            news_text += f"{i}. [{n.get('source', 'Unknown')}] {n.get('title', '')}\n"
            if n.get('snippet'):
                news_text += f"   {n['snippet'][:150]}...\n"
        
        prompt = f"""作为资深 A 股投资顾问，请分析以下国际新闻对 A 股市场的影响。

【今日新闻】
{news_text}

请输出 JSON 格式（不要 Markdown 代码块）:
{{
    "summary": "一段话总结今日主要新闻及其整体市场影响",
    "a_share_impact": [
        {{
            "sector": "受影响的 A 股板块",
            "direction": "利好/利空/中性",
            "reason": "简短理由",
            "stocks": ["相关股票代码"]
        }}
    ],
    "risk_alert": "需关注的风险点（如有）"
}}"""

        try:
            resp = await self.client.chat.completions.create(
                model=self.model_config.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1000
            )
            
            content = resp.choices[0].message.content
            
            # 尝试解析 JSON
            try:
                # 清理 Markdown 代码块
                cleaned = re.sub(r"```json|```", "", content).strip()
                return json.loads(cleaned)
            except json.JSONDecodeError:
                # 如果解析失败，尝试提取 JSON
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                return {"summary": content, "a_share_impact": []}
        
        except Exception as e:
            logger.error(f"❌ 新闻影响分析失败: {e}")
            return {"summary": f"分析失败: {e}", "a_share_impact": []}
    
    async def translate_title(self, title: str) -> str:
        """将英文标题翻译为中文"""
        if not self.client:
            return title
        
        # 检测是否为英文
        if all(ord(c) < 128 for c in title.replace(" ", "").replace(".", "").replace(",", "")):
            try:
                resp = await self.client.chat.completions.create(
                    model=self.model_config.model_id,
                    messages=[{"role": "user", "content": f"将以下新闻标题翻译为简洁的中文，只输出翻译结果:\n{title}"}],
                    temperature=0.3,
                    max_tokens=100
                )
                return resp.choices[0].message.content.strip()
            except Exception:
                return title
        
        return title
