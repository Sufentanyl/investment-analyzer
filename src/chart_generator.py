import mplfinance as mpf
import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)

def generate_snapshot(df: pd.DataFrame, title: str) -> io.BytesIO:
    """
    生成 K 线快照图片 (A 股风格: 红涨绿跌)
    """
    try:
        if df.empty or len(df) < 5: return None

        # 1. 设置 A 股风格颜色 (Up=Red, Down=Green)
        mc = mpf.make_marketcolors(
            up='red', down='green', 
            edge='i', wick='i', 
            volume='in', inherit=True
        )
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

        # 2. 准备内存缓冲区
        buf = io.BytesIO()

        # 3. 画图
        # type='candle': 蜡烛图
        # mav=(5, 20): 显示 5日和 20日均线
        # volume=True: 显示成交量
        mpf.plot(
            df, 
            type='candle', 
            mav=(5, 20), 
            volume=True, 
            title=title, 
            style=s, 
            savefig=buf,
            figsize=(10, 6),
            datetime_format='%m-%d',
            tight_layout=True
        )
        
        buf.seek(0) # 指针回到开头
        return buf

    except Exception as e:
        logger.error(f"画图失败: {e}")
        return None