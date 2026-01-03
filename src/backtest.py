"""
轻量级回测引擎
- 资源占用小: 分批计算，不一次性加载所有数据
- 简单策略模拟: 持有N天、止盈止损
- 生成报告: 胜率、盈亏比、最大回撤
"""

import sqlite3
import logging
from datetime import datetime, timedelta
import yfinance as yf
from typing import List, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class LightweightBacktester:
    """轻量级回测引擎"""

    def __init__(self, db_path='/app/data/investment.db'):
        self.db_path = db_path
        self.executor = ThreadPoolExecutor(max_workers=2)  # 限制并发数，降低CPU占用

    async def run_backtest(self, days: int = 30, strategy: str = 'hold_3_days') -> Dict[str, Any]:
        """
        运行回测

        Args:
            days: 回测最近多少天的信号
            strategy: 策略类型
                - 'hold_3_days': 持有3天
                - 'hold_5_days': 持有5天
                - 'stop_loss_5': 止损5%
                - 'target_profit_10': 止盈10%

        Returns:
            回测报告字典
        """
        logger.info(f"🔬 开始回测: 最近{days}天, 策略={strategy}")

        try:
            # 1. 从数据库读取历史信号（分批读取，避免内存占用过大）
            signals = await self._get_historical_signals(days)

            if not signals:
                return {"error": "没有找到历史信号"}

            logger.info(f"📊 找到 {len(signals)} 条信号，开始回测...")

            # 2. 分批回测（每批20条，避免一次性计算太多）
            batch_size = 20
            results = []

            for i in range(0, len(signals), batch_size):
                batch = signals[i:i + batch_size]
                batch_results = await self._backtest_batch(batch, strategy)
                results.extend(batch_results)

                # 🔥 优化：每批处理后短暂休息，避免CPU占用过高
                await asyncio.sleep(0.1)

            # 3. 统计结果
            report = self._calculate_statistics(results)

            # 4. 保存回测结果到数据库
            await self._save_backtest_results(report, strategy)

            logger.info(f"✅ 回测完成: 胜率 {report['win_rate']:.1f}%, 盈亏比 {report['profit_loss_ratio']:.2f}")

            return report

        except Exception as e:
            logger.error(f"❌ 回测失败: {e}")
            return {"error": str(e)}

    async def _get_historical_signals(self, days: int) -> List[Dict]:
        """从数据库读取历史信号"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

            loop = asyncio.get_event_loop()
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # 🔥 优化：只读取需要的字段，减少内存占用
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

    async def _backtest_batch(self, signals: List[Dict], strategy: str) -> List[Dict]:
        """批量回测信号"""
        results = []

        for signal in signals:
            try:
                # 🔥 关键：使用线程池执行网络请求，避免阻塞
                result = await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self._backtest_single_signal,
                    signal,
                    strategy
                )
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"⚠️ 回测信号失败 {signal.get('stock_code')}: {e}")

        return results

    def _backtest_single_signal(self, signal: Dict, strategy: str) -> Dict:
        """回测单个信号"""
        stock_code = signal['stock_code']
        entry_price = signal['price_at_signal']
        signal_date = datetime.strptime(signal['created_at'], '%Y-%m-%d %H:%M:%S')

        try:
            # 获取当前价格
            ticker = yf.Ticker(stock_code)
            hist = ticker.history(period='1mo')

            if hist.empty:
                return None

            current_price = hist['Close'].iloc[-1]

            # 根据策略计算结果
            if strategy == 'hold_3_days':
                result = self._strategy_hold_n_days(hist, signal_date, entry_price, 3)
            elif strategy == 'hold_5_days':
                result = self._strategy_hold_n_days(hist, signal_date, entry_price, 5)
            elif strategy == 'stop_loss_5':
                result = self._strategy_stop_loss(hist, signal_date, entry_price, stop_loss=0.05)
            elif strategy == 'target_profit_10':
                result = self._strategy_target_profit(hist, signal_date, entry_price, target=0.10)
            else:
                result = self._strategy_hold_n_days(hist, signal_date, entry_price, 3)

            # 添加信号信息
            result.update({
                'stock_code': stock_code,
                'signal_date': signal_date.strftime('%Y-%m-%d'),
                'entry_price': entry_price,
                'signal_type': signal.get('signal_type', 'unknown'),
                'news_title': signal.get('news_title', ''),
                'confidence': signal.get('confidence', 0.0)
            })

            return result

        except Exception as e:
            logger.warning(f"⚠️ 回测 {stock_code} 失败: {e}")
            return None

    def _strategy_hold_n_days(self, hist, signal_date, entry_price, n_days: int) -> Dict:
        """策略：持有N天"""
        # 找到信号日期后的第N天
        target_date = signal_date + timedelta(days=n_days)

        # 获取N天后的价格（如果是周末，使用下一个交易日）
        if target_date.strftime('%Y-%m-%d') in hist.index.strftime('%Y-%m-%d').values:
            exit_price = hist.loc[target_date.strftime('%Y-%m-%d'), 'Close']
        else:
            # 找最近的交易日
            future_dates = hist[hist.index >= signal_date]
            if len(future_dates) > min(n_days, len(future_dates) - 1):
                exit_price = future_dates['Close'].iloc[min(n_days, len(future_dates) - 1)]
            else:
                exit_price = hist['Close'].iloc[-1]

        # 计算盈亏
        profit_pct = (exit_price - entry_price) / entry_price * 100

        return {
            'exit_price': exit_price,
            'profit_pct': profit_pct,
            'is_win': profit_pct > 0,
            'strategy': f'hold_{n_days}_days'
        }

    def _strategy_stop_loss(self, hist, signal_date, entry_price, stop_loss: float) -> Dict:
        """策略：止损"""
        # 获取信号日期后的所有价格
        future_hist = hist[hist.index >= signal_date]

        if future_hist.empty:
            return {
                'exit_price': entry_price,
                'profit_pct': 0,
                'is_win': False,
                'strategy': f'stop_loss_{int(stop_loss*100)}'
            }

        # 检查是否触发止损
        stop_loss_price = entry_price * (1 - stop_loss)

        for date, row in future_hist.iterrows():
            if row['Low'] <= stop_loss_price:
                # 触发止损
                return {
                    'exit_price': stop_loss_price,
                    'profit_pct': -stop_loss * 100,
                    'is_win': False,
                    'strategy': f'stop_loss_{int(stop_loss*100)}',
                    'exit_reason': 'stop_loss'
                }

        # 没有触发止损，使用最新价格
        current_price = future_hist['Close'].iloc[-1]
        profit_pct = (current_price - entry_price) / entry_price * 100

        return {
            'exit_price': current_price,
            'profit_pct': profit_pct,
            'is_win': profit_pct > 0,
            'strategy': f'stop_loss_{int(stop_loss*100)}',
            'exit_reason': 'expired'
        }

    def _strategy_target_profit(self, hist, signal_date, entry_price, target: float) -> Dict:
        """策略：止盈"""
        # 获取信号日期后的所有价格
        future_hist = hist[hist.index >= signal_date]

        if future_hist.empty:
            return {
                'exit_price': entry_price,
                'profit_pct': 0,
                'is_win': False,
                'strategy': f'target_profit_{int(target*100)}'
            }

        # 检查是否触发止盈
        target_price = entry_price * (1 + target)

        for date, row in future_hist.iterrows():
            if row['High'] >= target_price:
                # 触发止盈
                return {
                    'exit_price': target_price,
                    'profit_pct': target * 100,
                    'is_win': True,
                    'strategy': f'target_profit_{int(target*100)}',
                    'exit_reason': 'target_profit'
                }

        # 没有触发止盈，使用最新价格
        current_price = future_hist['Close'].iloc[-1]
        profit_pct = (current_price - entry_price) / entry_price * 100

        return {
            'exit_price': current_price,
            'profit_pct': profit_pct,
            'is_win': profit_pct > 0,
            'strategy': f'target_profit_{int(target*100)}',
            'exit_reason': 'expired'
        }

    def _calculate_statistics(self, results: List[Dict]) -> Dict[str, Any]:
        """计算统计数据"""
        if not results:
            return {"error": "没有回测结果"}

        # 过滤掉None
        valid_results = [r for r in results if r is not None]

        if not valid_results:
            return {"error": "没有有效的回测结果"}

        # 计算基本统计
        total_count = len(valid_results)
        win_count = sum(1 for r in valid_results if r.get('is_win', False))
        lose_count = total_count - win_count

        # 胜率
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0

        # 盈亏比
        profits = [r['profit_pct'] for r in valid_results if r.get('is_win', False)]
        losses = [abs(r['profit_pct']) for r in valid_results if not r.get('is_win', True)]

        avg_profit = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        profit_loss_ratio = (avg_profit / avg_loss) if avg_loss > 0 else 0

        # 最大回撤
        all_profits = [r['profit_pct'] for r in valid_results]
        max_drawdown = min(all_profits) if all_profits else 0

        # 累计收益
        total_profit = sum(all_profits)

        # 按信号类型统计
        by_signal_type = {}
        for r in valid_results:
            signal_type = r.get('signal_type', 'unknown')
            if signal_type not in by_signal_type:
                by_signal_type[signal_type] = {'win': 0, 'total': 0}
            by_signal_type[signal_type]['total'] += 1
            if r.get('is_win', False):
                by_signal_type[signal_type]['win'] += 1

        return {
            'total_signals': total_count,
            'win_count': win_count,
            'lose_count': lose_count,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'profit_loss_ratio': profit_loss_ratio,
            'max_drawdown': max_drawdown,
            'total_profit': total_profit,
            'by_signal_type': by_signal_type,
            'strategy': valid_results[0].get('strategy', 'unknown') if valid_results else 'unknown',
            'backtest_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'details': valid_results[:10]  # 只保存前10条详细记录
        }

    async def _save_backtest_results(self, report: Dict, strategy: str):
        """保存回测结果到数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 创建回测结果表
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

                # 保存结果
                import json
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
