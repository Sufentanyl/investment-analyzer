import sqlite3
import logging
from datetime import datetime, timedelta
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path='/app/data/investment.db'):
        self.db_path = db_path
        self._conn = None  # 🔥 修复: 复用连接
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """🔥 修复: 使用单例连接 + 上下文管理器"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row  # 方便按列名访问
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self):
        """🔥 新增: 关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_db(self):
        """初始化数据库结构、索引及优化设置"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        try:
            with self._get_conn() as conn:
                # 🔥 优化1：开启 WAL 模式，支持并发读写
                conn.execute("PRAGMA journal_mode=WAL;")
                
                cursor = conn.cursor()
                
                # 创建信号表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        stock_code TEXT NOT NULL,
                        signal_date TEXT NOT NULL,
                        signal_type TEXT,
                        confidence REAL,
                        reason TEXT,
                        price_at_signal REAL,
                        news_title TEXT,
                        summary TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 🔥 优化2：添加索引，大幅提升查询速度
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_code ON signals(stock_code);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON signals(created_at);')
                
                conn.commit()
                logger.info("✅ 数据库初始化完成 (WAL模式 + 索引)")
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")

    def save_signal(self, stock_code, news_title, signal, confidence, reason, price, summary):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO signals 
                    (stock_code, signal_date, signal_type, confidence, reason, price_at_signal, news_title, summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (stock_code, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                      signal, confidence, reason, price, news_title, summary))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ 信号存储失败: {e}")

    def get_signals(self, stock_code, limit=50):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM signals 
                    WHERE stock_code = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (stock_code, limit))
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"❌ 读取信号失败: {e}")
            return []

    # 🔥 优化3：数据清理策略 (保留最近 90 天)
    def prune_old_data(self, days_to_keep=90):
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d %H:%M:%S')
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM signals WHERE created_at < ?", (cutoff_date,))
                deleted_count = cursor.rowcount
                # 执行 VACUUM 释放磁盘空间
                if deleted_count > 0:
                    conn.execute("VACUUM;") 
                conn.commit()
                if deleted_count > 0:
                    logger.info(f"🧹 已清理 {days_to_keep} 天前的旧数据，释放 {deleted_count} 条记录")
        except Exception as e:
            logger.error(f"❌ 数据清理失败: {e}")