"""
A 股真实 T+1 仿真回测引擎 (v2.0)
- 原生东方财富前复权日 K 线 + 内存级行情缓存（彻底替代脆弱的 yfinance）
- 区分「盘中信号」与「盘后/隔夜信号（次日 Open 买入）」
- 严格遵守 A 股 T+1 锁仓制度（买入当日不可卖出，次日跳空按真实 Open 结算）
- 涨跌停约束校验（一字涨停排队不可买标记为 untradable，一字跌停不可卖顺延）
- 多空双向独立统计（看多信号算实盘收益，看空信号算避雷成功率）
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

from valuecell_bridge.utils import (
    normalize_ashare_code,
    get_ashare_board_info,
    fetch_ashare_kline_sync,
)

logger = logging.getLogger(__name__)


class LightweightBacktester:
    """A 股 T+1 仿真回测引擎"""

    def __init__(self, db_path: str = None):
        if hasattr(db_path, "db_path"):
            db_path = db_path.db_path
        if db_path is None:
            if os.path.exists("/app/data/investment.db") or os.path.exists("/app/data"):
                db_path = "/app/data/investment.db"
            else:
                db_path = os.path.join(os.getcwd(), "data", "investment.db")
        self.db_path = db_path
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._kline_cache: Dict[str, pd.DataFrame] = {}
        self.slippage = float(os.getenv("BACKTEST_SLIPPAGE", "0.0015"))  # 默认单边滑点+冲击成本 0.15%

    async def run_backtest(self, days: int = 30, strategy: str = 'hold_3_days') -> Dict[str, Any]:
        """
        运行 A 股 T+1 仿真回测

        Args:
            days: 回测最近多少天的信号
            strategy: 策略类型
                - 'hold_3_days': T+1 起持有3个交易日
                - 'hold_5_days': T+1 起持有5个交易日
                - 'stop_loss_5': T+1 起 5% 止损（含跳空低开真实滑点）
                - 'target_profit_10': T+1 起 10% 止盈（含跳空高开结算）

        Returns:
            回测报告字典
        """
        logger.info(f"🔬 开始 A 股 T+1 仿真回测: 最近{days}天, 策略={strategy}")
        self._kline_cache.clear()

        try:
            signals = await self._get_historical_signals(days)
            if not signals:
                return {"error": "没有找到历史信号"}

            logger.info(f"📊 找到 {len(signals)} 条信号，开始 T+1 仿真回测...")

            batch_size = 20
            results = []

            for i in range(0, len(signals), batch_size):
                batch = signals[i:i + batch_size]
                batch_results = await self._backtest_batch(batch, strategy, days=days)
                results.extend(batch_results)
                await asyncio.sleep(0.05)

            report = self._calculate_statistics(results, strategy=strategy)
            if "error" not in report:
                await self._save_backtest_results(report, strategy)
                logger.info(
                    f"✅ 回测完成: 胜率 {report['win_rate']:.1f}%, "
                    f"盈亏比 {report['profit_loss_ratio']:.2f}, "
                    f"一字板未成交 {report.get('untradable_count', 0)} 笔"
                )

            return report

        except Exception as e:
            logger.error(f"❌ 回测失败: {e}", exc_info=True)
            return {"error": str(e)}

    async def _get_historical_signals(self, days: int) -> List[Dict]:
        """从数据库读取历史信号"""
        try:
            if not os.path.exists(self.db_path):
                return []

            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT
                        id, stock_code, signal_type, price_at_signal,
                        created_at, confidence, news_title
                    FROM signals
                    WHERE created_at >= ?
                    AND price_at_signal IS NOT NULL
                    ORDER BY created_at DESC
                ''', (cutoff_date,))

                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"❌ 读取历史信号失败: {e}")
            return []

    def _get_kline(self, stock_code: str, days: int = 90) -> pd.DataFrame:
        """带缓存获取东方财富前复权日 K 线"""
        code = normalize_ashare_code(stock_code)
        if not code:
            return pd.DataFrame()
        if code in self._kline_cache:
            return self._kline_cache[code]

        limit = max(60, days + 30)
        df = fetch_ashare_kline_sync(code, limit=limit)
        if df is not None and not df.empty:
            self._kline_cache[code] = df
        return df

    async def _backtest_batch(self, signals: List[Dict], strategy: str, days: int = 30) -> List[Dict]:
        """批量回测信号"""
        results = []
        loop = asyncio.get_running_loop()

        for signal in signals:
            try:
                result = await loop.run_in_executor(
                    self.executor,
                    self._backtest_single_signal,
                    signal,
                    strategy,
                    days,
                )
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"⚠️ 回测信号失败 {signal.get('stock_code')}: {e}")

        return results

    def _parse_signal_datetime(self, raw_dt: str) -> datetime:
        """解析信号时间戳"""
        if not raw_dt:
            return datetime.now()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(raw_dt[:19], fmt)
            except Exception:
                continue
        return datetime.now()

    def _is_intraday_session(self, dt: datetime) -> bool:
        """判断信号是否处于 A 股交易日盘中时段 (周一至周五 09:25 - 14:57)"""
        if dt.weekday() >= 5:
            return False
        hm = dt.hour * 100 + dt.minute
        return 925 <= hm <= 1457

    def _resolve_ashare_entry(
        self,
        hist: pd.DataFrame,
        signal_dt: datetime,
        raw_entry_price: float,
        limit_pct: float,
        signal_type: str,
    ):
        """
        根据 A 股交易规则判定真实买入日 (T+0) 与买入价：
        - 盘中信号：按信号当日触发价 + 滑点买入（若当日一字涨停或已封死涨停，则标记 untradable）
        - 盘后/隔夜/周末信号：必须按下一交易日开盘价 (Open) + 滑点买入（若次日一字涨停，则标记 untradable）
        """
        signal_day = pd.Timestamp(signal_dt.strftime('%Y-%m-%d'))
        is_intraday = self._is_intraday_session(signal_dt) and (signal_day in hist.index)

        if is_intraday:
            loc = hist.index.get_loc(signal_day)
            if isinstance(loc, slice):
                loc = loc.start
            bar = hist.iloc[loc]
            prev_close = float(hist.iloc[loc - 1]['Close']) if loc > 0 else float(bar['Open'])
            limit_up = round(prev_close * (1.0 + limit_pct), 2)

            # 检查是否一字涨停或触发价已封涨停（做多信号无法买进）
            is_one_word_up = (abs(float(bar['High']) - float(bar['Low'])) < 0.01) and (
                float(bar['Close']) >= limit_up - 0.01
            )
            base_price = float(raw_entry_price) if (raw_entry_price and raw_entry_price > 0) else float(bar['Close'])
            is_sealed_up = base_price >= limit_up - 0.01

            if signal_type != 'negative' and (is_one_word_up or is_sealed_up):
                return None, None, "limit_up_untradable"

            entry_price = base_price * (1.0 + self.slippage) if signal_type != 'negative' else base_price
            return signal_day, float(entry_price), "intraday_entry"

        # 盘后 / 隔夜 / 休市日信号 -> 必须在下一交易日开盘 (Open) 成交
        future_bars = hist[hist.index > signal_day]
        if future_bars.empty:
            # 尚未到下一交易日开盘，若有当日数据且无后续交易日，返回未到期状态
            return None, None, "pending_next_open"

        entry_day = future_bars.index[0]
        loc = hist.index.get_loc(entry_day)
        if isinstance(loc, slice):
            loc = loc.start
        bar = hist.iloc[loc]
        prev_close = float(hist.iloc[loc - 1]['Close']) if loc > 0 else float(bar['Open'])
        limit_up = round(prev_close * (1.0 + limit_pct), 2)

        # 若次日开盘一字涨停 (Open == High == Low 且触及涨停价)，散户排队无法成交
        is_one_word_up = (abs(float(bar['High']) - float(bar['Low'])) < 0.01) and (
            float(bar['Open']) >= limit_up - 0.01
        )
        if signal_type != 'negative' and is_one_word_up:
            return None, None, "one_word_limit_up_untradable"

        open_price = float(bar['Open'])
        entry_price = open_price * (1.0 + self.slippage) if signal_type != 'negative' else open_price
        return entry_day, float(entry_price), "next_open_entry"

    def _backtest_single_signal(
        self,
        signal: Dict,
        strategy: str,
        days: int = 30,
        hist_override: Optional[pd.DataFrame] = None,
    ) -> Optional[Dict]:
        """回测单个信号（严格执行 A 股 T+1 锁仓与涨跌停约束）"""
        raw_code = signal.get('stock_code', '')
        stock_code = normalize_ashare_code(raw_code)
        raw_entry_price = float(signal.get('price_at_signal') or 0.0)
        signal_dt = self._parse_signal_datetime(signal.get('created_at', ''))
        signal_type = (signal.get('signal_type') or 'positive').lower()
        if signal_type == 'neutral':
            return None

        try:
            hist = hist_override if hist_override is not None else self._get_kline(stock_code, days=days)
            if hist is None or hist.empty:
                return None

            stock_name = hist.attrs.get("stock_name", stock_code)
            board_info = get_ashare_board_info(stock_code, stock_name)
            limit_pct = board_info["limit_pct"]

            entry_day, entry_price, entry_mode = self._resolve_ashare_entry(
                hist, signal_dt, raw_entry_price, limit_pct, signal_type
            )

            # 若次日尚未开盘，跳过统计
            if entry_mode == "pending_next_open":
                return None

            # 若涨停排队无法买进，单独标记为 untradable（不计入虚假盈利）
            if entry_day is None or entry_price is None:
                return {
                    'stock_code': stock_code,
                    'signal_date': signal_dt.strftime('%Y-%m-%d %H:%M'),
                    'entry_price': raw_entry_price,
                    'exit_price': raw_entry_price,
                    'profit_pct': 0.0,
                    'is_win': False,
                    'untradable': True,
                    'exit_reason': entry_mode,
                    'strategy': strategy,
                    'signal_type': signal_type,
                    'news_title': signal.get('news_title', ''),
                    'confidence': signal.get('confidence', 0.0),
                }

            # A 股 T+1 锁仓约束：买入当日 (entry_day) 不可卖出，只能从 entry_day 之后的交易日开始离场
            t_plus_1_bars = hist[hist.index > entry_day]
            if t_plus_1_bars.empty:
                # 刚在最新交易日买入，尚处于 T+0 锁仓期，以最新收盘价估算浮盈亏
                latest_close = float(hist.loc[entry_day, 'Close'])
                result = self._pack_trade_result(
                    entry_price=entry_price,
                    exit_price=latest_close,
                    signal_type=signal_type,
                    strategy=strategy,
                    exit_reason="t0_locked_floating",
                    entry_mode=entry_mode,
                )
            else:
                if strategy == 'hold_3_days':
                    result = self._strategy_hold_n_days(t_plus_1_bars, entry_price, 3, limit_pct, signal_type, entry_mode)
                elif strategy == 'hold_5_days':
                    result = self._strategy_hold_n_days(t_plus_1_bars, entry_price, 5, limit_pct, signal_type, entry_mode)
                elif strategy == 'stop_loss_5':
                    result = self._strategy_stop_loss(t_plus_1_bars, entry_price, 0.05, limit_pct, signal_type, entry_mode)
                elif strategy == 'target_profit_10':
                    result = self._strategy_target_profit(t_plus_1_bars, entry_price, 0.10, limit_pct, signal_type, entry_mode)
                else:
                    result = self._strategy_hold_n_days(t_plus_1_bars, entry_price, 3, limit_pct, signal_type, entry_mode)

            result.update({
                'stock_code': stock_code,
                'signal_date': signal_dt.strftime('%Y-%m-%d'),
                'entry_date': entry_day.strftime('%Y-%m-%d'),
                'entry_price': round(entry_price, 2),
                'signal_type': signal_type,
                'news_title': signal.get('news_title', ''),
                'confidence': signal.get('confidence', 0.0),
                'untradable': False,
            })
            return result

        except Exception as e:
            logger.warning(f"⚠️ 回测 {stock_code} 失败: {e}")
            return None

    def _is_one_word_limit_down(self, row: pd.Series, limit_pct: float) -> bool:
        """判断当日是否一字跌停（散户无法卖出，必须顺延至下一交易日）"""
        high_p = float(row.get('High', 0))
        low_p = float(row.get('Low', 0))
        pct_chg = float(row.get('PctChange', 0))
        return abs(high_p - low_p) < 0.01 and pct_chg <= -(limit_pct * 100.0 - 0.5)

    def _pack_trade_result(
        self,
        entry_price: float,
        exit_price: float,
        signal_type: str,
        strategy: str,
        exit_reason: str,
        entry_mode: str,
    ) -> Dict:
        """
        多空双向收益结算：
        - positive (看多信号): 计算做多真实收益率 (扣除卖出滑点+印花税)
        - negative (看空/避雷信号): 计算成功规避的下跌幅度 (下跌即代表看空避雷成功)
        """
        if signal_type == 'negative':
            profit_pct = (entry_price - exit_price) / entry_price * 100.0
            is_win = profit_pct > 0
        else:
            net_exit = exit_price * (1.0 - self.slippage)
            profit_pct = (net_exit - entry_price) / entry_price * 100.0
            is_win = profit_pct > 0

        return {
            'exit_price': round(float(exit_price), 2),
            'profit_pct': round(float(profit_pct), 2),
            'is_win': bool(is_win),
            'strategy': strategy,
            'exit_reason': exit_reason,
            'entry_mode': entry_mode,
        }

    def _strategy_hold_n_days(
        self,
        t_plus_1_bars: pd.DataFrame,
        entry_price: float,
        n_days: int,
        limit_pct: float,
        signal_type: str,
        entry_mode: str,
    ) -> Dict:
        """策略：从 T+1 起持有 N 个交易日（若到期日一字跌停无法卖出则顺延）"""
        target_idx = min(n_days - 1, len(t_plus_1_bars) - 1)
        exit_price = float(t_plus_1_bars['Close'].iloc[target_idx])
        exit_reason = f'hold_{n_days}_days'

        for idx in range(target_idx, len(t_plus_1_bars)):
            row = t_plus_1_bars.iloc[idx]
            if signal_type != 'negative' and self._is_one_word_limit_down(row, limit_pct):
                exit_reason = 'limit_down_delayed'
                continue
            exit_price = float(row['Close'])
            break

        return self._pack_trade_result(
            entry_price=entry_price,
            exit_price=exit_price,
            signal_type=signal_type,
            strategy=f'hold_{n_days}_days',
            exit_reason=exit_reason,
            entry_mode=entry_mode,
        )

    def _strategy_stop_loss(
        self,
        t_plus_1_bars: pd.DataFrame,
        entry_price: float,
        stop_loss: float,
        limit_pct: float,
        signal_type: str,
        entry_mode: str,
    ) -> Dict:
        """策略：T+1 起止损（含跳空低开按真实 Open 止损、一字跌停不可卖顺延）"""
        stop_loss_price = entry_price * (1.0 - stop_loss)

        for _, row in t_plus_1_bars.iterrows():
            if signal_type != 'negative' and self._is_one_word_limit_down(row, limit_pct):
                continue

            open_p = float(row['Open'])
            low_p = float(row['Low'])

            if open_p <= stop_loss_price:
                # 跳空低开直接跌破止损位，只能按开盘价割肉
                return self._pack_trade_result(
                    entry_price=entry_price,
                    exit_price=open_p,
                    signal_type=signal_type,
                    strategy=f'stop_loss_{int(stop_loss * 100)}',
                    exit_reason='gap_down_stop_loss',
                    entry_mode=entry_mode,
                )
            if low_p <= stop_loss_price:
                return self._pack_trade_result(
                    entry_price=entry_price,
                    exit_price=stop_loss_price,
                    signal_type=signal_type,
                    strategy=f'stop_loss_{int(stop_loss * 100)}',
                    exit_reason='stop_loss',
                    entry_mode=entry_mode,
                )

        current_price = float(t_plus_1_bars['Close'].iloc[-1])
        return self._pack_trade_result(
            entry_price=entry_price,
            exit_price=current_price,
            signal_type=signal_type,
            strategy=f'stop_loss_{int(stop_loss * 100)}',
            exit_reason='expired',
            entry_mode=entry_mode,
        )

    def _strategy_target_profit(
        self,
        t_plus_1_bars: pd.DataFrame,
        entry_price: float,
        target: float,
        limit_pct: float,
        signal_type: str,
        entry_mode: str,
    ) -> Dict:
        """策略：T+1 起止盈（含跳空高开按真实 Open 止盈）"""
        target_price = entry_price * (1.0 + target)

        for _, row in t_plus_1_bars.iterrows():
            open_p = float(row['Open'])
            high_p = float(row['High'])

            if open_p >= target_price:
                return self._pack_trade_result(
                    entry_price=entry_price,
                    exit_price=open_p,
                    signal_type=signal_type,
                    strategy=f'target_profit_{int(target * 100)}',
                    exit_reason='gap_up_target_profit',
                    entry_mode=entry_mode,
                )
            if high_p >= target_price:
                return self._pack_trade_result(
                    entry_price=entry_price,
                    exit_price=target_price,
                    signal_type=signal_type,
                    strategy=f'target_profit_{int(target * 100)}',
                    exit_reason='target_profit',
                    entry_mode=entry_mode,
                )

        current_price = float(t_plus_1_bars['Close'].iloc[-1])
        return self._pack_trade_result(
            entry_price=entry_price,
            exit_price=current_price,
            signal_type=signal_type,
            strategy=f'target_profit_{int(target * 100)}',
            exit_reason='expired',
            entry_mode=entry_mode,
        )

    def _calculate_statistics(self, results: List[Dict], strategy: str = 'hold_3_days') -> Dict[str, Any]:
        """计算统计数据（剔除一字涨停未成交信号，分开统计多空信号表现）"""
        if not results:
            return {"error": "没有回测结果"}

        all_items = [r for r in results if r is not None]
        if not all_items:
            return {"error": "没有有效的回测结果"}

        untradable_items = [r for r in all_items if r.get('untradable')]
        valid_results = [r for r in all_items if not r.get('untradable')]

        if not valid_results:
            return {"error": f"全部 {len(untradable_items)} 条信号均因涨停无法买入成交"}

        total_count = len(valid_results)
        win_count = sum(1 for r in valid_results if r.get('is_win', False))
        lose_count = total_count - win_count
        win_rate = (win_count / total_count * 100.0) if total_count > 0 else 0.0

        profits = [r['profit_pct'] for r in valid_results if r.get('is_win', False)]
        losses = [abs(r['profit_pct']) for r in valid_results if not r.get('is_win', True)]

        avg_profit = sum(profits) / len(profits) if profits else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        profit_loss_ratio = (avg_profit / avg_loss) if avg_loss > 0 else (avg_profit if avg_profit > 0 else 0.0)

        all_profits = [r['profit_pct'] for r in valid_results]
        max_drawdown = min(all_profits) if all_profits else 0.0
        total_profit = sum(all_profits)

        by_signal_type = {}
        for r in valid_results:
            s_type = r.get('signal_type', 'positive')
            if s_type not in by_signal_type:
                by_signal_type[s_type] = {'win': 0, 'total': 0, 'avg_pct': 0.0, '_sum': 0.0}
            by_signal_type[s_type]['total'] += 1
            by_signal_type[s_type]['_sum'] += r['profit_pct']
            if r.get('is_win', False):
                by_signal_type[s_type]['win'] += 1

        for s_type, st_data in by_signal_type.items():
            t = st_data['total']
            st_data['win_rate'] = round(st_data['win'] / t * 100.0, 1) if t > 0 else 0.0
            st_data['avg_pct'] = round(st_data.pop('_sum') / t, 2) if t > 0 else 0.0

        return {
            'total_signals': total_count,
            'untradable_count': len(untradable_items),
            'win_count': win_count,
            'lose_count': lose_count,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'profit_loss_ratio': profit_loss_ratio,
            'max_drawdown': max_drawdown,
            'total_profit': total_profit,
            'by_signal_type': by_signal_type,
            'strategy': strategy,
            'backtest_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'details': valid_results[:15],
        }

    async def _save_backtest_results(self, report: Dict, strategy: str):
        """保存回测结果到数据库"""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS backtest_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        backtest_date TEXT NOT NULL,
                        strategy TEXT NOT NULL,
                        total_signals INTEGER,
                        win_count INTEGER,
                        lose_count INTEGER,
                        win_rate REAL,
                        profit_loss_ratio REAL,
                        max_drawdown REAL,
                        total_profit REAL,
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    INSERT INTO backtest_results
                    (backtest_date, strategy, total_signals, win_count, lose_count,
                     win_rate, profit_loss_ratio, max_drawdown, total_profit, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    report['backtest_date'],
                    strategy,
                    report.get('total_signals', 0),
                    report.get('win_count', 0),
                    report.get('lose_count', 0),
                    report.get('win_rate', 0),
                    report.get('profit_loss_ratio', 0),
                    report.get('max_drawdown', 0),
                    report.get('total_profit', 0),
                    json.dumps(report.get('details', []), ensure_ascii=False)
                ))

                conn.commit()
                logger.info("✅ 回测结果已保存到数据库")

        except Exception as e:
            logger.error(f"❌ 保存回测结果失败: {e}")

    def get_backtest_history(self, limit: int = 10) -> List[Dict]:
        """获取历史回测记录"""
        try:
            if not os.path.exists(self.db_path):
                return []
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT * FROM backtest_results
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (limit,))

                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"❌ 读取回测历史失败: {e}")
            return []
