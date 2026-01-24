"""
Research Adapter
封装 ValueCell 的深度研究功能，用于 A 股公司研究
"""

import os
import re
import json
import logging
import asyncio
import aiohttp
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    """研究结果"""
    stock_code: str
    stock_name: str
    summary: str
    filings: List[Dict[str, Any]]
    financial_analysis: Optional[str] = None
    news_analysis: Optional[str] = None
    recommendation: Optional[str] = None


class ResearchAdapter:
    """
    研究代理适配器
    提供深度研究功能，包括:
    - A 股公告获取
    - 公司财务分析
    - 网页搜索
    - 综合研究报告生成
    """
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
        
        # 导入配置
        from .config import get_model_config, create_openai_client
        self.model_config = get_model_config("research_agent")
        self.client = create_openai_client(self.model_config)
        
        logger.info(f"🔬 ResearchAdapter 初始化完成，使用模型: {self.model_config.provider}/{self.model_config.model_id}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """关闭资源"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def deep_research(self, query: str, stock_code: str = None) -> Dict[str, Any]:
        """
        执行深度研究
        
        Args:
            query: 研究主题/问题
            stock_code: 可选的股票代码，如 "600519"
        
        Returns:
            包含研究结果的字典
        """
        logger.info(f"🔍 开始深度研究: {query}, 股票代码: {stock_code}")
        
        results = {
            "query": query,
            "stock_code": stock_code,
            "filings": [],
            "web_search": [],
            "analysis": "",
            "recommendation": ""
        }
        
        try:
            # 1. 如果提供了股票代码，获取公告
            if stock_code:
                filings = await self.get_ashare_filings(stock_code)
                results["filings"] = filings[:5]  # 最多5条
            
            # 2. 网页搜索相关信息
            search_results = await self.web_search(query)
            results["web_search"] = search_results[:3]  # 最多3条
            
            # 3. 使用 LLM 生成综合分析
            analysis = await self._generate_analysis(query, stock_code, results)
            results["analysis"] = analysis
            
            # 4. 生成投资建议
            recommendation = await self._generate_recommendation(stock_code, analysis)
            results["recommendation"] = recommendation
            
        except Exception as e:
            logger.error(f"❌ 深度研究失败: {e}")
            results["error"] = str(e)
        
        return results
    
    async def get_ashare_filings(self, stock_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取 A 股公告
        
        Args:
            stock_code: 股票代码，如 "600519"
            limit: 最大返回数量
        
        Returns:
            公告列表
        """
        logger.info(f"📄 获取 A 股公告: {stock_code}")
        
        filings = []
        
        try:
            # 使用东方财富公告接口
            session = await self._get_session()
            
            # 构建请求
            url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
            params = {
                "sr": -1,
                "page_size": limit,
                "page_index": 1,
                "ann_type": "A",
                "stock_list": stock_code,
                "f_node": 0,
                "s_node": 0
            }
            
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    # 东方财富 API 返回 text/plain，需要手动解析 JSON
                    text = await resp.text()
                    data = json.loads(text)
                    items = data.get("data", {}).get("list", [])
                    
                    for item in items[:limit]:
                        filings.append({
                            "title": item.get("title", ""),
                            "date": item.get("notice_date", ""),
                            "type": item.get("columns", [{}])[0].get("column_name", "公告") if item.get("columns") else "公告",
                            "url": f"https://data.eastmoney.com/notices/detail/{stock_code}/{item.get('art_code', '')}.html"
                        })
                    
                    logger.info(f"✅ 获取到 {len(filings)} 条公告")
                else:
                    logger.warning(f"⚠️ 获取公告失败: HTTP {resp.status}")
        
        except asyncio.TimeoutError:
            logger.warning("⚠️ 获取公告超时")
        except json.JSONDecodeError as e:
            logger.error(f"❌ 公告 JSON 解析失败: {e}")
        except Exception as e:
            logger.error(f"❌ 获取公告异常: {e}")
        
        return filings
    
    async def web_search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        网页搜索
        
        Args:
            query: 搜索关键词
            num_results: 结果数量
        
        Returns:
            搜索结果列表
        """
        logger.info(f"🌐 网页搜索: {query}")
        
        results = []
        serpapi_key = os.getenv("SERPAPI_KEY")
        
        if not serpapi_key:
            logger.warning("⚠️ SERPAPI_KEY 未配置，跳过网页搜索")
            return results
        
        try:
            session = await self._get_session()
            
            # 随机选择一个 key
            import random
            keys = [k.strip() for k in serpapi_key.split(",")]
            selected_key = random.choice(keys)
            
            params = {
                "engine": "google",
                "q": query,
                "api_key": selected_key,
                "num": num_results,
                "hl": "zh-CN"
            }
            
            async with session.get("https://serpapi.com/search", params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    for item in data.get("organic_results", [])[:num_results]:
                        results.append({
                            "title": item.get("title", ""),
                            "link": item.get("link", ""),
                            "snippet": item.get("snippet", "")
                        })
                    
                    logger.info(f"✅ 搜索到 {len(results)} 条结果")
                else:
                    logger.warning(f"⚠️ 搜索失败: HTTP {resp.status}")
        
        except asyncio.TimeoutError:
            logger.warning("⚠️ 搜索超时")
        except Exception as e:
            logger.error(f"❌ 搜索异常: {e}")
        
        return results
    
    async def _generate_analysis(self, query: str, stock_code: str, context: Dict) -> str:
        """使用 LLM 生成综合分析"""
        if not self.client:
            return "⚠️ LLM 客户端未初始化"
        
        # 构建上下文
        filings_text = ""
        if context.get("filings"):
            filings_text = "\n".join([f"- {f['date']}: {f['title']}" for f in context["filings"][:5]])
        
        search_text = ""
        if context.get("web_search"):
            search_text = "\n".join([f"- {s['title']}: {s['snippet'][:100]}..." for s in context["web_search"][:3]])
        
        prompt = f"""作为资深 A 股分析师，请分析以下信息并提供深度研究报告。

【研究主题】{query}
【股票代码】{stock_code or '未指定'}

【最新公告】
{filings_text or '暂无公告'}

【相关新闻】
{search_text or '暂无新闻'}

请输出结构化的研究报告，包含:
1. 公司/行业概况 (2-3句)
2. 最新动态分析 (基于公告和新闻)
3. 投资机会与风险
4. 关键指标监控建议

使用简洁专业的语言，直接输出，不要 Markdown 代码块。"""

        try:
            resp = await self.client.chat.completions.create(
                model=self.model_config.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1500
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ LLM 分析生成失败: {e}")
            return f"分析生成失败: {e}"
    
    async def _generate_recommendation(self, stock_code: str, analysis: str) -> str:
        """生成投资建议"""
        if not self.client or not stock_code:
            return ""
        
        prompt = f"""基于以下分析，给出简明的操作建议（一句话）:

{analysis[:1000]}

格式: [建议类型] 具体建议
建议类型: 观望 / 关注 / 逢低买入 / 持有 / 减仓"""

        try:
            resp = await self.client.chat.completions.create(
                model=self.model_config.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=100
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ 建议生成失败: {e}")
            return ""
    
    async def get_stock_name(self, stock_code: str) -> str:
        """获取股票名称"""
        try:
            import yfinance as yf
            
            # 转换为 yfinance 格式
            if stock_code.isdigit():
                if stock_code.startswith("6"):
                    code = f"{stock_code}.SS"
                else:
                    code = f"{stock_code}.SZ"
            else:
                code = stock_code
            
            ticker = yf.Ticker(code)
            info = ticker.info
            return info.get("shortName", info.get("longName", stock_code))
        except Exception:
            return stock_code
