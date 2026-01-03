import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class TechnicalAnalyzer:
    """
    专业技术分析模块 (含回测引擎)
    """
    
    def analyze(self, df: pd.DataFrame) -> dict:
        """
        全能分析：包含即时指标 + 历史回测
        """
        if df is None or len(df) < 20:
            return {"summary": "数据不足", "trend": "未知", "backtest": None}

        try:
            # 1. 基础数据
            close = df['Close']
            curr_price = close.iloc[-1]
            
            # 2. 计算核心指标
            ma5 = close.rolling(window=5).mean().iloc[-1]
            ma20 = close.rolling(window=20).mean().iloc[-1]
            rsi = self._calculate_rsi(close)
            
            # 3. 运行“时光机”回测 (核心升级 🔥)
            # 策略：简单的趋势跟随 (站上 MA20 做多)
            bt_result = self._backtest_trend_strategy(df)

            # 4. 生成信号描述
            signals = []
            trend = "多头" if curr_price > ma20 else "空头"
            
            if curr_price > ma5: signals.append("站上MA5")
            if curr_price < ma5: signals.append("跌破MA5")
            
            if rsi > 75: signals.append(f"RSI超买({int(rsi)})")
            elif rsi < 30: signals.append(f"RSI超卖({int(rsi)})")

            # 结合回测结论
            if bt_result['win_rate'] > 0.6:
                signals.append(f"🔥股性活跃(胜率{bt_result['win_rate_str']})")
            elif bt_result['win_rate'] < 0.4:
                signals.append(f"⚠️股性坑爹(胜率{bt_result['win_rate_str']})")

            tech_desc = " ".join(signals)
            
            return {
                "price": curr_price,
                "trend": trend,
                "summary": f"[{trend}] {tech_desc}",
                "backtest": bt_result  # 把回测数据传出去
            }

        except Exception as e:
            logger.error(f"技术分析出错: {e}")
            return {"summary": "计算错误", "trend": "未知", "backtest": None}

    def _backtest_trend_strategy(self, df: pd.DataFrame) -> dict:
        """
        🔥 向量化极速回测
        回测逻辑：如果过去 1 年，每次“收盘价站上 MA20”时买入，持有 1 天，胜率如何？
        """
        try:
            data = df.copy()
            data['MA20'] = data['Close'].rolling(window=20).mean()
            
            # 信号：今天收盘 > MA20
            data['Signal'] = np.where(data['Close'] > data['MA20'], 1, 0)
            
            # 计算次日收益 (Shift(-1) 因为今天的信号决定明天的持仓)
            data['Next_Ret'] = data['Close'].pct_change().shift(-1)
            
            # 筛选出有持仓的日子
            trade_days = data[data['Signal'] == 1]
            
            if len(trade_days) < 10:
                return {"win_rate": 0.5, "win_rate_str": "样本不足", "total_ret": 0}

            # 1. 胜率 (赚钱天数 / 总持仓天数)
            wins = len(trade_days[trade_days['Next_Ret'] > 0])
            total = len(trade_days)
            win_rate = wins / total if total > 0 else 0

            # 2. 策略总回报 (复利)
            # 简单估算：累加对数收益
            total_ret = trade_days['Next_Ret'].sum()

            return {
                "win_rate": win_rate,
                "win_rate_str": f"{int(win_rate*100)}%",
                "total_ret": f"{total_ret*100:.1f}%"
            }
        except Exception:
            return {"win_rate": 0.5, "win_rate_str": "计算失败", "total_ret": 0}

    def _calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        # 🔥 修复: 防止除零
        loss = loss.where(loss > 0, 1e-10)

        rs = gain / loss
        return 100 - (100 / (1 + rs)).iloc[-1]
    
    def _calculate_macd(self, series):
        # 保留接口备用
        pass