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


import re
import json
from datetime import datetime
import pandas as pd
import requests


def normalize_ashare_code(stock_code: str) -> str:
    """
    将任意格式的 A 股代码标准化为 6 位数字代码
    例如: '600519.SS' -> '600519', 'SH600519' -> '600519', '000858.SZ' -> '000858'
    """
    if not stock_code:
        return ""
    raw = str(stock_code).strip().upper()
    m = re.search(r"(\d{6})", raw)
    if m:
        return m.group(1)
    return raw


def get_eastmoney_secid(stock_code: str) -> str:
    """获取东方财富 secid (1.沪市, 0.深市/北交所)"""
    code = normalize_ashare_code(stock_code)
    if code.startswith(("6", "900")):
        return f"1.{code}"
    return f"0.{code}"


def get_ashare_board_info(stock_code: str, stock_name: str = "") -> dict:
    """
    识别 A 股板块属性与涨跌停幅度限制
    Returns:
        {
            "code": "600519",
            "board": "主板" / "创业板" / "科创板" / "北交所",
            "limit_pct": 0.10 / 0.20 / 0.30 / 0.05,
            "is_st": bool
        }
    """
    code = normalize_ashare_code(stock_code)
    name_upper = (stock_name or "").upper()
    is_st = "ST" in name_upper

    if code.startswith(("300", "301")):
        board = "创业板"
        limit_pct = 0.20
    elif code.startswith(("688", "689")):
        board = "科创板"
        limit_pct = 0.20
    elif code.startswith(("8", "4", "92")):
        board = "北交所"
        limit_pct = 0.30
    else:
        board = "主板"
        limit_pct = 0.05 if is_st else 0.10

    return {
        "code": code,
        "board": board,
        "limit_pct": limit_pct,
        "is_st": is_st,
    }


def _parse_eastmoney_klines_to_df(data: dict, fallback_code: str = "") -> pd.DataFrame:
    """将东方财富 kline JSON 转换为标准 DataFrame (同时兼容中英文列名)"""
    payload = (data or {}).get("data") or {}
    klines = payload.get("klines") or []
    if not klines:
        return pd.DataFrame()

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        try:
            dt_str = parts[0]
            open_p = float(parts[1])
            close_p = float(parts[2])
            high_p = float(parts[3])
            low_p = float(parts[4])
            vol = float(parts[5])
            amt = float(parts[6])
            amp = float(parts[7])
            pct_chg = float(parts[8])
            chg = float(parts[9])
            turnover = float(parts[10])
            rows.append({
                "Date": pd.to_datetime(dt_str),
                "日期": dt_str,
                "Open": open_p,
                "High": high_p,
                "Low": low_p,
                "Close": close_p,
                "Volume": vol,
                "Amount": amt,
                "Amplitude": amp,
                "PctChange": pct_chg,
                "Change": chg,
                "Turnover": turnover,
                "开盘": open_p,
                "收盘": close_p,
                "最高": high_p,
                "最低": low_p,
                "成交量": vol,
                "成交额": amt,
                "涨跌幅": pct_chg,
                "换手率": turnover,
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    df.attrs["stock_code"] = payload.get("code") or normalize_ashare_code(fallback_code)
    df.attrs["stock_name"] = payload.get("name") or df.attrs["stock_code"]
    return df


def fetch_ashare_kline_sync(
    stock_code: str,
    limit: int = 120,
    start_date: str = None,
    end_date: str = "20500101",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    同步获取 A 股前复权日 K 线 (优先使用东方财富原生高速接口，失败回退 akshare)
    """
    code = normalize_ashare_code(stock_code)
    if not code:
        return pd.DataFrame()

    fqt_map = {"": 0, "qfq": 1, "hfq": 2}
    fqt = fqt_map.get(adjust, 1)
    secid = get_eastmoney_secid(code)

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": 101,
        "fqt": fqt,
        "end": end_date or "20500101",
        "lmt": limit,
    }
    if start_date:
        params["beg"] = start_date.replace("-", "")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/",
    }

    for attempt in range(2):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                df = _parse_eastmoney_klines_to_df(data, fallback_code=code)
                if not df.empty:
                    return df
        except Exception as e:
            if attempt == 1:
                logger.debug(f"东方财富日K线请求异常 {code}: {e}")

    # 备用1：腾讯财经前复权日K线接口 (极高可用性)
    try:
        prefix = "sh" if code.startswith(("6", "900")) else ("bj" if code.startswith(("8", "4", "92")) else "sz")
        symbol = f"{prefix}{code}"
        adj_tag = "qfq" if adjust == "qfq" else ("hfq" if adjust == "hfq" else "")
        tc_url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{limit},{adj_tag}"
        resp = requests.get(tc_url, headers={"User-Agent": headers["User-Agent"]}, timeout=8)
        if resp.status_code == 200:
            tc_data = (resp.json().get("data") or {}).get(symbol) or {}
            klines = tc_data.get("qfqday") or tc_data.get("hfqday") or tc_data.get("day") or []
            rows = []
            prev_c = None
            for item in klines:
                if len(item) < 6:
                    continue
                dt_str = str(item[0])
                open_p = float(item[1])
                close_p = float(item[2])
                high_p = float(item[3])
                low_p = float(item[4])
                vol = float(item[5])
                pct_chg = ((close_p - prev_c) / prev_c * 100.0) if prev_c and prev_c > 0 else 0.0
                prev_c = close_p
                rows.append({
                    "Date": pd.to_datetime(dt_str),
                    "日期": dt_str,
                    "Open": open_p,
                    "High": high_p,
                    "Low": low_p,
                    "Close": close_p,
                    "Volume": vol,
                    "Amount": 0.0,
                    "Amplitude": ((high_p - low_p) / close_p * 100.0) if close_p > 0 else 0.0,
                    "PctChange": round(pct_chg, 2),
                    "Change": 0.0,
                    "Turnover": 0.0,
                    "开盘": open_p,
                    "收盘": close_p,
                    "最高": high_p,
                    "最低": low_p,
                    "成交量": vol,
                    "成交额": 0.0,
                    "涨跌幅": round(pct_chg, 2),
                    "换手率": 0.0,
                })
            if rows:
                tc_df = pd.DataFrame(rows)
                tc_df.set_index("Date", inplace=True)
                tc_df.sort_index(inplace=True)
                tc_df.attrs["stock_code"] = code
                tc_df.attrs["stock_name"] = code
                return tc_df
    except Exception as e:
        logger.debug(f"腾讯财经日K线备用接口异常 {code}: {e}")

    # 备用2：akshare
    try:
        import akshare as ak
        beg = (start_date or "20240101").replace("-", "")
        end = (end_date if end_date and end_date != "20500101" else datetime.now().strftime("%Y%m%d")).replace("-", "")
        ak_df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=beg, end_date=end, adjust=adjust)
        if ak_df is not None and not ak_df.empty:
            ak_df = ak_df.tail(limit).copy()
            ak_df["Date"] = pd.to_datetime(ak_df["日期"])
            ak_df["Open"] = ak_df["开盘"].astype(float)
            ak_df["High"] = ak_df["最高"].astype(float)
            ak_df["Low"] = ak_df["最低"].astype(float)
            ak_df["Close"] = ak_df["收盘"].astype(float)
            ak_df["Volume"] = ak_df["成交量"].astype(float)
            ak_df["Amount"] = ak_df.get("成交额", 0.0)
            ak_df["PctChange"] = ak_df.get("涨跌幅", 0.0)
            ak_df["Turnover"] = ak_df.get("换手率", 0.0)
            ak_df.set_index("Date", inplace=True)
            ak_df.attrs["stock_code"] = code
            ak_df.attrs["stock_name"] = code
            return ak_df
    except Exception as e:
        logger.warning(f"备用数据源获取 K 线失败 {code}: {e}")

    return pd.DataFrame()


class AShareDataSource:
    """
    A 股数据源封装
    支持多数据源自动切换 (东方财富原生接口 + 腾讯财经 + 巨潮资讯 + 新浪7x24)
    """
    
    def __init__(self, session=None):
        self.session = session

    async def get_kline_df(
        self,
        stock_code: str,
        limit: int = 120,
        start_date: str = None,
        end_date: str = "20500101",
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """异步获取 A 股前复权日 K 线 DataFrame"""
        code = normalize_ashare_code(stock_code)
        if not code:
            return pd.DataFrame()

        fqt_map = {"": 0, "qfq": 1, "hfq": 2}
        fqt = fqt_map.get(adjust, 1)
        secid = get_eastmoney_secid(code)

        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": 101,
            "fqt": fqt,
            "end": end_date or "20500101",
            "lmt": limit,
        }
        if start_date:
            params["beg"] = start_date.replace("-", "")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://quote.eastmoney.com/",
        }

        try:
            async with self.session.get(url, params=params, headers=headers, timeout=8) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    data = json.loads(text)
                    df = _parse_eastmoney_klines_to_df(data, fallback_code=code)
                    if not df.empty:
                        return df
        except Exception as e:
            logger.debug(f"异步获取东方财富K线失败 {code}: {e}")

        return await asyncio.to_thread(
            fetch_ashare_kline_sync, code, limit, start_date, end_date, adjust
        )

    async def get_7x24_fast_news(self, limit: int = 20) -> list:
        """
        获取本土 7x24 小时财经快讯与公司核心公告催化 (东方财富快讯 + 新浪财经电报双源)
        """
        news_items = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://kuaixun.eastmoney.com/",
        }

        # 1. 东方财富 7x24 全球财经快讯 (含 A 股公司突发公告速递)
        em_url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
        em_params = {
            "client": "web",
            "biz": "web_news_col",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": limit,
            "req_trace": "1",
        }
        try:
            async with self.session.get(em_url, params=em_params, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    data = json.loads(text)
                    fast_list = (data.get("data") or {}).get("fastNewsList") or []
                    for item in fast_list:
                        title = (item.get("title") or "").strip()
                        summary = (item.get("summary") or title).strip()
                        code_str = item.get("code") or ""
                        show_time = item.get("showTime") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        try:
                            pub_dt = datetime.strptime(show_time, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            pub_dt = datetime.now()
                        if not title:
                            continue
                        news_items.append({
                            "source": "cn_eastmoney_7x24",
                            "title": title,
                            "url": f"https://kuaixun.eastmoney.com/ss/{code_str}.html" if code_str else f"https://kuaixun.eastmoney.com/#{hash(title)}",
                            "content": summary,
                            "published": pub_dt.isoformat(),
                            "published_ts": pub_dt.timestamp(),
                            "stock_list": item.get("stockList") or [],
                            "is_domestic_fast": True,
                        })
        except Exception as e:
            logger.debug(f"东方财富 7x24 快讯获取异常: {e}")

        # 2. 新浪财经 7x24 实时电报 (补充宏观与行业突发)
        sina_url = "https://zhibo.sina.com.cn/api/zhibo/feed"
        sina_params = {
            "page": 1,
            "page_size": min(limit, 20),
            "zhibo_id": 152,
        }
        try:
            async with self.session.get(sina_url, params=sina_params, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    data = json.loads(text)
                    feed_list = (((data.get("result") or {}).get("data") or {}).get("feed") or {}).get("list") or []
                    for item in feed_list:
                        rich_text = (item.get("rich_text") or "").strip()
                        if not rich_text:
                            continue
                        # 提取【标题】
                        m = re.match(r"^【([^】]+)】(.*)$", rich_text, re.DOTALL)
                        if m:
                            title = m.group(1).strip()
                            content = rich_text
                        else:
                            title = rich_text[:50]
                            content = rich_text
                        create_time = item.get("create_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        try:
                            pub_dt = datetime.strptime(create_time, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            pub_dt = datetime.now()
                        doc_url = item.get("docurl") or f"https://finance.sina.com.cn/7x24/#{item.get('id', hash(title))}"
                        news_items.append({
                            "source": "cn_sina_7x24",
                            "title": title,
                            "url": doc_url,
                            "content": content,
                            "published": pub_dt.isoformat(),
                            "published_ts": pub_dt.timestamp(),
                            "is_domestic_fast": True,
                        })
        except Exception as e:
            logger.debug(f"新浪 7x24 快讯获取异常: {e}")

        return news_items
    
    async def get_stock_filings(self, stock_code: str, limit: int = 10) -> list:
        """
        获取 A 股公告，自动尝试多个数据源
        """
        code = normalize_ashare_code(stock_code)
        sources = [
            self._get_filings_eastmoney,
            self._get_filings_cninfo,
        ]
        
        for source in sources:
            try:
                result = await source(code, limit)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"数据源 {source.__name__} 失败: {e}")
                continue
        
        return []
    
    async def _get_filings_eastmoney(self, stock_code: str, limit: int) -> list:
        """东方财富公告接口"""
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
                items = (data.get("data") or {}).get("list") or []
                
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
        if stock_code.startswith("6"):
            plate = "sh"
        else:
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
                    announcements = result.get("announcements") or []
                    
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
        code = normalize_ashare_code(stock_code)
        try:
            secid = get_eastmoney_secid(code)
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f57,f58,f43,f44,f45,f46,f47,f48,f60,f168,f170,f171"
            }
            
            async with self.session.get(url, params=params, timeout=5) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    data = json.loads(text)
                    info = data.get("data") or {}
                    
                    def _safe_num(v, div=100.0):
                        if v is None or v == "-":
                            return 0.0
                        try:
                            return float(v) / div
                        except Exception:
                            return 0.0

                    return {
                        "code": info.get("f57", code),
                        "name": info.get("f58", code),
                        "price": _safe_num(info.get("f43")),
                        "change_pct": _safe_num(info.get("f170")),
                        "high": _safe_num(info.get("f44")),
                        "low": _safe_num(info.get("f45")),
                        "open": _safe_num(info.get("f46")),
                        "volume": info.get("f47", 0) if info.get("f47") != "-" else 0,
                        "amount": info.get("f48", 0) if info.get("f48") != "-" else 0,
                        "pre_close": _safe_num(info.get("f60")),
                        "turnover": _safe_num(info.get("f168")),
                    }
        except Exception as e:
            logger.warning(f"获取股票信息失败: {e}")
        
        return {"code": code, "name": code}
    
    async def get_financial_metrics(self, stock_code: str) -> dict:
        """
        获取股票财务指标 (PE/PB/ROE/市值等)
        """
        code = normalize_ashare_code(stock_code)
        try:
            secid = get_eastmoney_secid(code)
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f9,f23,f20,f21,f115,f116,f117,f162,f163"
            }
            
            async with self.session.get(url, params=params, timeout=5) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    data = json.loads(text)
                    info = data.get("data") or {}
                    
                    def safe_divide(val, divisor=100):
                        if val and val != "-":
                            try:
                                return float(val) / divisor
                            except Exception:
                                pass
                        return None
                    
                    return {
                        "pe_dynamic": safe_divide(info.get("f9"), 100),
                        "pb": safe_divide(info.get("f23"), 100),
                        "total_mv": info.get("f20", 0) if info.get("f20") != "-" else 0,
                        "circ_mv": info.get("f21", 0) if info.get("f21") != "-" else 0,
                        "pe_static": safe_divide(info.get("f115"), 100),
                        "roe": safe_divide(info.get("f162"), 100),
                        "gross_margin": safe_divide(info.get("f163"), 100),
                    }
        except Exception as e:
            logger.warning(f"获取财务指标失败: {e}")
        
        return {}
    
    async def get_northbound_flow(self, stock_code: str) -> dict:
        """
        获取北向资金持仓变化
        """
        code = normalize_ashare_code(stock_code)
        try:
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "reportName": "RPT_MUTUAL_STOCK_NORTHSTA",
                "columns": "SECURITY_CODE,SECURITY_NAME,HOLD_SHARES,HOLD_MARKET_CAP,HOLD_SHARES_RATIO,ADD_SHARES_AMP",
                "filter": f'(SECURITY_CODE="{code}")',
                "pageSize": 1,
                "sortColumns": "TRADE_DATE",
                "sortTypes": -1,
                "source": "WEB",
                "client": "WEB"
            }
            
            async with self.session.get(url, params=params, timeout=8) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    data = json.loads(text)
                    result = data.get("result") or {}
                    items = result.get("data") or []
                    
                    if items:
                        item = items[0]
                        return {
                            "hold_shares": item.get("HOLD_SHARES", 0),
                            "hold_market_cap": item.get("HOLD_MARKET_CAP", 0),
                            "hold_ratio": item.get("HOLD_SHARES_RATIO", 0),
                            "add_shares_pct": item.get("ADD_SHARES_AMP", 0),
                        }
        except Exception as e:
            logger.debug(f"获取北向资金数据失败: {e}")
        
        return {}
    
    async def get_full_stock_data(self, stock_code: str) -> dict:
        """
        获取完整股票数据 (基本信息 + 财务指标 + 北向资金)
        """
        basic_task = self.get_stock_info(stock_code)
        financial_task = self.get_financial_metrics(stock_code)
        northbound_task = self.get_northbound_flow(stock_code)
        
        basic, financial, northbound = await asyncio.gather(
            basic_task, financial_task, northbound_task,
            return_exceptions=True
        )
        
        result = {}
        
        if isinstance(basic, dict):
            result.update(basic)
        
        if isinstance(financial, dict):
            result["financial"] = financial
        
        if isinstance(northbound, dict) and northbound:
            result["northbound"] = northbound
        
        return result


class LLMFallback:
    """
    LLM 降级路由器
    支持 DeepSeek -> OpenAI (GPT) -> Gemini -> Kimi -> Qwen 自动无感切换
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
        
        # 1. DeepSeek
        if os.getenv("DEEPSEEK_API_KEY"):
            self.clients["deepseek"] = {
                "client": AsyncOpenAI(
                    api_key=os.getenv("DEEPSEEK_API_KEY"),
                    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                ),
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            }

        # 2. OpenAI (GPT)
        if os.getenv("OPENAI_API_KEY"):
            self.clients["openai"] = {
                "client": AsyncOpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
                ),
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            }
        
        # 3. Gemini
        gemini_keys = os.getenv("GEMINI_API_KEY", "")
        if gemini_keys:
            first_key = gemini_keys.split(",")[0].strip()
            self.clients["gemini"] = {
                "client": AsyncOpenAI(
                    api_key=first_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                ),
                "model": os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
            }
        
        # 4. Kimi
        if os.getenv("KIMI_API_KEY"):
            self.clients["kimi"] = {
                "client": AsyncOpenAI(
                    api_key=os.getenv("KIMI_API_KEY"),
                    base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
                ),
                "model": os.getenv("KIMI_MODEL", "moonshot-v1-8k")
            }

        # 5. Qwen (可选兼容)
        if os.getenv("QWEN_API_KEY"):
            self.clients["qwen"] = {
                "client": AsyncOpenAI(
                    api_key=os.getenv("QWEN_API_KEY"),
                    base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
                ),
                "model": os.getenv("QWEN_MODEL", "qwen-plus")
            }
        
        logger.info(f"LLM 降级路由器初始化完成，可用模型: {list(self.clients.keys())}")
    
    async def chat(
        self,
        prompt: str,
        preferred_models: list = None,
        temperature: float = 0.7,
        max_tokens: int = 1500
    ) -> str:
        """
        发送聊天请求，自动降级到备用模型
        """
        if not self.clients:
            return "LLM 客户端未初始化"
        
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

