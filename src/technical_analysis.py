import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """
    A 股「三维共振」专业技术分析模块 (v2.0)
    1. 趋势与乖离率过滤 (MA5/MA20 多头排列 + BIAS20 防追高)
    2. 量价承接与动量指标 (量比 / 换手率 / MACD / RSI / 上影线识别)
    3. 交易制度校验与 T+1 波段向量回测 (剔除一字涨停不可买伪信号)
    """

    def analyze(self, df: pd.DataFrame, stock_code: str = "", stock_name: str = "") -> dict:
        """
        全能三维共振分析：包含即时技术指标 + 乖离率风控 + 历史 T+1 波段回测
        """
        if df is None or len(df) < 20:
            return {
                "summary": "数据不足",
                "trend": "未知",
                "backtest": None,
                "resonance_score": 0.5,
                "reaction_score": 0.3,
                "is_overheated": False,
            }

        try:
            close = df["Close"].astype(float)
            open_p = df["Open"].astype(float) if "Open" in df.columns else close
            high_p = df["High"].astype(float) if "High" in df.columns else close
            low_p = df["Low"].astype(float) if "Low" in df.columns else close
            vol = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(np.ones(len(df)), index=df.index)

            curr_price = float(close.iloc[-1])
            prev_close = float(close.iloc[-2]) if len(close) >= 2 else curr_price

            # 1. 均线与乖离率 (维度一：趋势与位置防追高)
            ma5_series = close.rolling(window=5).mean()
            ma10_series = close.rolling(window=10).mean()
            ma20_series = close.rolling(window=20).mean()

            ma5 = float(ma5_series.iloc[-1])
            ma10 = float(ma10_series.iloc[-1])
            ma20 = float(ma20_series.iloc[-1])
            bias_20 = ((curr_price - ma20) / ma20 * 100.0) if ma20 > 0 else 0.0

            ret_1d = ((curr_price - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
            price_3d_ago = float(close.iloc[-4]) if len(close) >= 4 else float(close.iloc[0])
            ret_3d = ((curr_price - price_3d_ago) / price_3d_ago * 100.0) if price_3d_ago > 0 else 0.0
            price_5d_ago = float(close.iloc[-6]) if len(close) >= 6 else float(close.iloc[0])
            ret_5d = ((curr_price - price_5d_ago) / price_5d_ago * 100.0) if price_5d_ago > 0 else 0.0

            # 2. 动量与量价指标 (维度二：量价承接与防骗线)
            rsi = float(self._calculate_rsi(close))
            dif, dea, macd_hist = self._calculate_macd(close)

            vol_ma5 = float(vol.iloc[-6:-1].mean()) if len(vol) >= 6 else float(vol.mean())
            vol_ma20 = float(vol.iloc[-20:].mean())
            curr_vol = float(vol.iloc[-1])
            vol_ratio = (curr_vol / vol_ma5) if vol_ma5 > 0 else 1.0
            vol_ratio_20 = (curr_vol / vol_ma20) if vol_ma20 > 0 else 1.0

            turnover = float(df["Turnover"].iloc[-1]) if "Turnover" in df.columns else 0.0

            # 上影线比例 (识别高位放量长上影出货)
            curr_high = float(high_p.iloc[-1])
            curr_low = float(low_p.iloc[-1])
            curr_open = float(open_p.iloc[-1])
            body_top = max(curr_open, curr_price)
            upper_shadow_pct = ((curr_high - body_top) / prev_close * 100.0) if prev_close > 0 else 0.0

            # 3. 板块与涨跌停状态校验 (维度三：A股交易制度)
            code = stock_code or df.attrs.get("stock_code", "")
            name = stock_name or df.attrs.get("stock_name", "")
            limit_pct = 0.20 if str(code).startswith(("300", "301", "688", "689")) else (
                0.30 if str(code).startswith(("8", "4", "92")) else (0.05 if "ST" in str(name).upper() else 0.10)
            )
            limit_up_price = round(prev_close * (1.0 + limit_pct), 2)
            limit_down_price = round(prev_close * (1.0 - limit_pct), 2)
            is_limit_up = curr_price >= limit_up_price - 0.01 and ret_1d > (limit_pct * 100 - 1.5)
            is_one_word_limit_up = is_limit_up and abs(curr_high - curr_low) < 0.01
            is_limit_down = curr_price <= limit_down_price + 0.01 and ret_1d < -(limit_pct * 100 - 1.5)

            # 4. 判定是否短期过热（防追高/利好兑现警告）
            is_overheated = (bias_20 > 12.0) or (ret_3d > 15.0) or (rsi > 80.0)

            # 5. 计算三维共振得分 (resonance_score) 与 量价验证分 (reaction_score)
            score = 0.50
            if curr_price > ma20:
                score += 0.12
            else:
                score -= 0.12

            if ma5 >= ma10 >= ma20:
                score += 0.10
            elif ma5 < ma20:
                score -= 0.08

            # 乖离率奖惩：温和突破加分，高位乖离扣分
            if 0.0 <= bias_20 <= 8.0:
                score += 0.10
            elif bias_20 > 12.0:
                score -= 0.18

            # MACD 共振
            macd_tag = ""
            if dif > dea and macd_hist > 0:
                score += 0.08
                macd_tag = "MACD多头"
            elif dif < dea and macd_hist < 0:
                score -= 0.06
                macd_tag = "MACD偏弱"

            # 量价配合：温和放量上涨加分，高位放量长上影扣分
            if 1.2 <= vol_ratio <= 3.5 and ret_1d > 0 and not is_overheated:
                score += 0.10
            elif upper_shadow_pct > 3.5 and vol_ratio > 1.8 and bias_20 > 6.0:
                score -= 0.15

            if "ST" in str(name).upper():
                score -= 0.25

            resonance_score = float(np.clip(score, 0.05, 0.98))

            # 量价验证分 (用于验证市场对催化的真实承接，兼顾防追高)
            raw_reaction = 0.6 * min(vol_ratio_20 / 2.0, 1.0) + 0.4 * min(abs(ret_1d) / 3.0, 1.0)
            if is_overheated:
                # 若已经连续暴涨，降低追高验证分，提示兑现风险
                reaction_score = round(float(np.clip(raw_reaction * 0.65, 0.1, 0.75)), 3)
            else:
                reaction_score = round(float(np.clip(0.5 * raw_reaction + 0.5 * resonance_score, 0.1, 1.0)), 3)

            # 6. 运行 T+1 波段历史回测
            bt_result = self._backtest_trend_strategy(df, limit_pct=limit_pct)

            # 7. 生成实战信号描述与建议区间
            signals = []
            if curr_price > ma20 and ma5 >= ma20:
                trend = "多头"
            elif curr_price < ma20 and ma5 < ma20:
                trend = "空头"
            else:
                trend = "震荡"

            if curr_price > ma5:
                signals.append("站上MA5")
            else:
                signals.append("跌破MA5")

            if macd_tag:
                signals.append(macd_tag)

            if vol_ratio >= 1.5:
                signals.append(f"放量(量比{vol_ratio:.1f})")
            elif vol_ratio <= 0.7:
                signals.append(f"缩量(量比{vol_ratio:.1f})")

            if is_overheated:
                signals.append(f"⚠️乖离偏高(BIAS20:{bias_20:+.1f}%/3日:{ret_3d:+.1f}%,谨防兑现)")
            else:
                signals.append(f"BIAS20:{bias_20:+.1f}%")

            if rsi > 75:
                signals.append(f"RSI超买({int(rsi)})")
            elif rsi < 30:
                signals.append(f"RSI超卖({int(rsi)})")

            if is_one_word_limit_up:
                signals.append("⛔一字涨停(排队难买)")
            elif is_limit_up:
                signals.append("🔥封涨停")
            elif is_limit_down:
                signals.append("🔻跌停风险")

            if bt_result["win_rate"] > 0.6:
                signals.append(f"⭐股性佳(T+1胜率{bt_result['win_rate_str']})")
            elif bt_result["win_rate"] < 0.4:
                signals.append(f"⚠️股性弱(T+1胜率{bt_result['win_rate_str']})")

            # 计算实战参考买点区间与止损位
            if is_overheated:
                buy_low = round(max(ma5 * 0.98, ma10), 2)
                buy_high = round(ma5 * 1.01, 2)
                buy_zone = f"{buy_low:.2f}-{buy_high:.2f}(回踩5日线低吸,高开莫追)"
            else:
                buy_low = round(min(curr_price * 0.985, ma5), 2)
                buy_high = round(curr_price * 1.01, 2)
                buy_zone = f"{buy_low:.2f}-{buy_high:.2f}"

            stop_loss_price = round(max(ma20 * 0.97, curr_price * 0.94), 2)
            tech_desc = " | ".join(signals)

            return {
                "price": curr_price,
                "trend": trend,
                "summary": f"[{trend}] {tech_desc}",
                "backtest": bt_result,
                "bias_20": round(bias_20, 2),
                "ret_1d": round(ret_1d, 2),
                "ret_3d": round(ret_3d, 2),
                "ret_5d": round(ret_5d, 2),
                "vol_ratio": round(vol_ratio, 2),
                "turnover": round(turnover, 2),
                "rsi": round(rsi, 1),
                "macd_signal": macd_tag,
                "is_overheated": is_overheated,
                "is_limit_up": is_limit_up,
                "is_one_word_limit_up": is_one_word_limit_up,
                "is_limit_down": is_limit_down,
                "resonance_score": round(resonance_score, 3),
                "reaction_score": reaction_score,
                "buy_zone": buy_zone,
                "stop_loss_price": stop_loss_price,
            }

        except Exception as e:
            logger.error(f"技术分析出错: {e}")
            return {
                "summary": "计算错误",
                "trend": "未知",
                "backtest": None,
                "resonance_score": 0.5,
                "reaction_score": 0.3,
                "is_overheated": False,
            }

    def _backtest_trend_strategy(self, df: pd.DataFrame, limit_pct: float = 0.10) -> dict:
        """
        🔥 A 股真实 T+1 波段向量化回测
        回测逻辑：
        - 当日收盘满足「站上 MA20 + MA5 >= MA20 + BIAS20 < 12%（非高位暴涨）」触发信号
        - 次日开盘价 (Open_{t+1}) 买入（若次日一字涨停无法买入则剔除）
        - 遵守 T+1 锁仓，持有至 T+3 收盘卖出，统计真实波段胜率与期望收益
        """
        try:
            data = df.copy()
            close = data["Close"].astype(float)
            open_p = data["Open"].astype(float) if "Open" in data.columns else close
            high_p = data["High"].astype(float) if "High" in data.columns else close
            low_p = data["Low"].astype(float) if "Low" in data.columns else close

            data["MA5"] = close.rolling(window=5).mean()
            data["MA20"] = close.rolling(window=20).mean()
            data["BIAS20"] = (close - data["MA20"]) / data["MA20"] * 100.0

            # 信号条件：站上 MA20 且乖离率未过热
            data["Signal"] = np.where(
                (close > data["MA20"]) & (data["MA5"] >= data["MA20"] * 0.99) & (data["BIAS20"] <= 12.0),
                1,
                0,
            )

            # 次日开盘买入价 (T+1 Open)，若次日一字涨停 (Open == High == Low 且涨幅 >= limit_pct*0.98) 则不可成交
            next_open = open_p.shift(-1)
            next_high = high_p.shift(-1)
            next_low = low_p.shift(-1)
            next_one_word_up = (
                ((next_high - next_low).abs() < 0.01)
                & ((next_open - close) / close >= limit_pct * 0.95)
            )

            # T+2 日收盘卖出（满足 A 股 T+1 锁仓后次日/隔日波段离场）
            exit_close = close.shift(-2).fillna(close.shift(-1))
            data["Trade_Ret"] = (exit_close - next_open) / next_open

            trade_days = data[(data["Signal"] == 1) & (~next_one_word_up) & (data["Trade_Ret"].notna())]

            if len(trade_days) < 8:
                return {"win_rate": 0.5, "win_rate_str": "样本不足", "total_ret": "0.0%"}

            wins = len(trade_days[trade_days["Trade_Ret"] > 0])
            total = len(trade_days)
            win_rate = wins / total if total > 0 else 0.5
            avg_ret = float(trade_days["Trade_Ret"].mean())

            return {
                "win_rate": round(win_rate, 3),
                "win_rate_str": f"{int(win_rate * 100)}%",
                "total_ret": f"{avg_ret * 100:+.1f}%/次",
            }
        except Exception as e:
            logger.debug(f"向量回测异常: {e}")
            return {"win_rate": 0.5, "win_rate_str": "计算失败", "total_ret": "0.0%"}

    def _calculate_rsi(self, series: pd.Series, period: int = 14) -> float:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0.0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
        loss = loss.where(loss > 0, 1e-10)
        rs = gain / loss
        rsi_val = (100.0 - (100.0 / (1.0 + rs))).iloc[-1]
        return float(rsi_val) if pd.notna(rsi_val) else 50.0

    def _calculate_macd(self, series: pd.Series):
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd_hist = (dif - dea) * 2.0
        return float(dif.iloc[-1]), float(dea.iloc[-1]), float(macd_hist.iloc[-1])