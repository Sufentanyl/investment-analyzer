"""
工具模块
包含重试装饰器、备用数据源等通用工具
"""

import asyncio
import logging
import functools
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


def async_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    异步重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟秒数
        backoff: 延迟倍增因子
        exceptions: 需要重试的异常类型
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} 失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}"
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"{func.__name__} 最终失败: {e}")
            
            raise last_exception
        return wrapper
    return decorator


class AShareDataSource:
    """
    A 股数据源封装
    支持多数据源自动切换
    """
    
    def __init__(self, session):
        self.session = session
    
    async def get_stock_filings(self, stock_code: str, limit: int = 10) -> list:
        """
        获取 A 股公告，自动尝试多个数据源
        """
        # 数据源列表，按优先级排序
        sources = [
            self._get_filings_eastmoney,
            self._get_filings_cninfo,
        ]
        
        for source in sources:
            try:
                result = await source(stock_code, limit)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"数据源 {source.__name__} 失败: {e}")
                continue
        
        return []
    
    async def _get_filings_eastmoney(self, stock_code: str, limit: int) -> list:
        """东方财富公告接口"""
        import json
        
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
        
        async with self.session.get(url, params=params, timeout=10) as resp:
            if resp.status == 200:
                text = await resp.text()
                data = json.loads(text)
                items = data.get("data", {}).get("list", [])
                
                return [
                    {
                        "title": item.get("title", ""),
                        "date": item.get("notice_date", ""),
                        "type": item.get("columns", [{}])[0].get("column_name", "公告") if item.get("columns") else "公告",
                        "url": f"https://data.eastmoney.com/notices/detail/{stock_code}/{item.get('art_code', '')}.html",
                        "source": "eastmoney"
                    }
                    for item in items[:limit]
                ]
        
        return []
    
    async def _get_filings_cninfo(self, stock_code: str, limit: int) -> list:
        """巨潮资讯公告接口 (备用)"""
        import json
        
        # 判断市场
        if stock_code.startswith("6"):
            org_id = f"gssh{stock_code}"
            plate = "sh"
        else:
            org_id = f"gssz{stock_code}"
            plate = "sz"
        
        url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
        data = {
            "pageNum": 1,
            "pageSize": limit,
            "column": plate,
            "tabName": "fulltext",
            "plate": plate,
            "stock": stock_code,
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": ""
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        try:
            async with self.session.post(url, data=data, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    announcements = result.get("announcements", [])
                    
                    return [
                        {
                            "title": ann.get("announcementTitle", ""),
                            "date": ann.get("announcementTime", "")[:10] if ann.get("announcementTime") else "",
                            "type": ann.get("announcementTypeName", "公告"),
                            "url": f"http://www.cninfo.com.cn/new/disclosure/detail?announcementId={ann.get('announcementId', '')}",
                            "source": "cninfo"
                        }
                        for ann in announcements[:limit]
                    ]
        except Exception as e:
            logger.debug(f"巨潮资讯接口异常: {e}")
        
        return []
    
    async def get_stock_info(self, stock_code: str) -> dict:
        """
        获取股票基本信息
        """
        try:
            # 使用东方财富快照接口
            if stock_code.startswith("6"):
                secid = f"1.{stock_code}"
            else:
                secid = f"0.{stock_code}"
            
            url = f"https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f57,f58,f43,f44,f45,f46,f47,f48,f60,f170,f171"
            }
            
            async with self.session.get(url, params=params, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    info = data.get("data", {})
                    
                    return {
                        "code": info.get("f57", stock_code),
                        "name": info.get("f58", ""),
                        "price": info.get("f43", 0) / 100 if info.get("f43") else 0,
                        "change_pct": info.get("f170", 0) / 100 if info.get("f170") else 0,
                        "high": info.get("f44", 0) / 100 if info.get("f44") else 0,
                        "low": info.get("f45", 0) / 100 if info.get("f45") else 0,
                        "open": info.get("f46", 0) / 100 if info.get("f46") else 0,
                        "volume": info.get("f47", 0),
                        "amount": info.get("f48", 0),
                        "pre_close": info.get("f60", 0) / 100 if info.get("f60") else 0,
                    }
        except Exception as e:
            logger.warning(f"获取股票信息失败: {e}")
        
        return {"code": stock_code, "name": stock_code}


class LLMFallback:
    """
    LLM 降级处理器
    当主模型失败时自动切换到备用模型
    """
    
    def __init__(self):
        self.clients = {}
        self._init_clients()
    
    def _init_clients(self):
        """初始化所有可用的 LLM 客户端"""
        import os
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.warning("openai 未安装")
            return
        
        # DeepSeek
        if os.getenv("DEEPSEEK_API_KEY"):
            self.clients["deepseek"] = {
                "client": AsyncOpenAI(
                    api_key=os.getenv("DEEPSEEK_API_KEY"),
                    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                ),
                "model": "deepseek-chat"
            }
        
        # Qwen
        if os.getenv("QWEN_API_KEY"):
            self.clients["qwen"] = {
                "client": AsyncOpenAI(
                    api_key=os.getenv("QWEN_API_KEY"),
                    base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
                ),
                "model": os.getenv("QWEN_MODEL", "qwen-plus")
            }
        
        # Gemini
        gemini_keys = os.getenv("GEMINI_API_KEY", "")
        if gemini_keys:
            first_key = gemini_keys.split(",")[0].strip()
            self.clients["gemini"] = {
                "client": AsyncOpenAI(
                    api_key=first_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                ),
                "model": os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            }
        
        # Kimi
        if os.getenv("KIMI_API_KEY"):
            self.clients["kimi"] = {
                "client": AsyncOpenAI(
                    api_key=os.getenv("KIMI_API_KEY"),
                    base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
                ),
                "model": "moonshot-v1-8k"
            }
        
        logger.info(f"LLM 降级处理器初始化完成，可用模型: {list(self.clients.keys())}")
    
    async def chat(
        self,
        prompt: str,
        preferred_models: list = None,
        temperature: float = 0.7,
        max_tokens: int = 1500
    ) -> str:
        """
        发送聊天请求，自动降级到备用模型
        
        Args:
            prompt: 用户提示
            preferred_models: 优先使用的模型列表
            temperature: 温度参数
            max_tokens: 最大 token 数
        
        Returns:
            模型响应
        """
        if not self.clients:
            return "LLM 客户端未初始化"
        
        # 确定模型优先级
        if preferred_models:
            models = [m for m in preferred_models if m in self.clients]
            models += [m for m in self.clients.keys() if m not in models]
        else:
            models = list(self.clients.keys())
        
        last_error = None
        
        for model_name in models:
            try:
                config = self.clients[model_name]
                
                resp = await config["client"].chat.completions.create(
                    model=config["model"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                logger.debug(f"使用 {model_name} 成功响应")
                return resp.choices[0].message.content
                
            except Exception as e:
                logger.warning(f"{model_name} 调用失败: {e}")
                last_error = e
                continue
        
        return f"所有模型调用失败: {last_error}"
