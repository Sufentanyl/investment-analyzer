import sqlite3
import logging
from datetime import datetime, timedelta
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            if os.path.exists('/app/data') or os.access('/app', os.W_OK):
                db_path = '/app/data/investment.db'
            else:
                db_path = os.path.join(os.getcwd(), 'data', 'investment.db')
        self.db_path = db_path
        self._conn = None  # 🔥 修复: 复用连接
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """🔥 修复: 使用单例连接 + 上下文管理器"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row  # 方便按列名访问
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    get_connection = _get_conn

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
                        confidence_effective REAL,
                        reason TEXT,
                        price_at_signal REAL,
                        news_title TEXT,
                        summary TEXT,
                        event_cluster_id INTEGER,
                        event_signature TEXT,
                        gap_confidence REAL,
                        validation_score REAL,
                        coverage_status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS event_clusters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        signature TEXT NOT NULL,
                        sample_title TEXT,
                        first_seen TIMESTAMP,
                        last_seen TIMESTAMP,
                        count INTEGER DEFAULT 1
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS event_memos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        news_title TEXT NOT NULL,
                        template_label TEXT,
                        sectors TEXT,
                        market_first_reaction TEXT,
                        transmission_path TEXT,
                        a_share_mapping TEXT,
                        hedge_leg TEXT,
                        failure_conditions TEXT,
                        verification TEXT,
                        alert_level TEXT,
                        alert_keywords TEXT,
                        review_status TEXT,
                        review_notes TEXT,
                        outcome TEXT,
                        event_cluster_id INTEGER,
                        event_signature TEXT,
                        updated_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 🔥 优化2：添加索引，大幅提升查询速度
                self._ensure_signal_columns(cursor)
                self._ensure_event_memo_columns(cursor)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_code ON signals(stock_code);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON signals(created_at);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_cluster_id ON signals(event_cluster_id);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_clusters_sig ON event_clusters(signature);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_clusters_seen ON event_clusters(last_seen);')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_memos_created_at ON event_memos(created_at);')
                
                conn.commit()
                logger.info("✅ 数据库初始化完成 (WAL模式 + 索引)")
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")

    def save_signal(
        self,
        stock_code,
        news_title,
        signal,
        confidence,
        reason,
        price,
        summary,
        confidence_effective=None,
        event_cluster_id=None,
        event_signature=None,
        gap_confidence=None,
        validation_score=None,
        coverage_status=None,
    ):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO signals 
                    (stock_code, signal_date, signal_type, confidence, confidence_effective, reason,
                     price_at_signal, news_title, summary, event_cluster_id, event_signature,
                     gap_confidence, validation_score, coverage_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (stock_code, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                      signal, confidence, confidence_effective, reason, price, news_title, summary,
                      event_cluster_id, event_signature, gap_confidence, validation_score, coverage_status))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ 信号存储失败: {e}")

    def save_event_memo(self, news_title, template_label, sectors, memo):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO event_memos
                    (news_title, template_label, sectors, market_first_reaction, transmission_path,
                     a_share_mapping, hedge_leg, failure_conditions, verification, alert_level,
                     alert_keywords, review_status, review_notes, outcome, event_cluster_id, event_signature, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    news_title,
                    template_label,
                    sectors,
                    memo.get('market_first_reaction'),
                    memo.get('transmission_path'),
                    memo.get('a_share_mapping'),
                    memo.get('hedge_leg'),
                    memo.get('failure_conditions'),
                    memo.get('verification'),
                    memo.get('alert_level'),
                    memo.get('alert_keywords'),
                    memo.get('review_status'),
                    memo.get('review_notes'),
                    memo.get('outcome'),
                    memo.get('event_cluster_id'),
                    memo.get('event_signature'),
                    memo.get('updated_at'),
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ 事件模板存储失败: {e}")

    def _ensure_signal_columns(self, cursor):
        cursor.execute("PRAGMA table_info(signals)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        missing_columns = {
            "confidence_effective": "REAL",
            "event_cluster_id": "INTEGER",
            "event_signature": "TEXT",
            "gap_confidence": "REAL",
            "validation_score": "REAL",
            "coverage_status": "TEXT",
        }
        for column_name, column_type in missing_columns.items():
            if column_name not in existing_columns:
                cursor.execute(f"ALTER TABLE signals ADD COLUMN {column_name} {column_type}")

    def _ensure_event_memo_columns(self, cursor):
        cursor.execute("PRAGMA table_info(event_memos)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        missing_columns = {
            "alert_level": "TEXT",
            "alert_keywords": "TEXT",
            "review_status": "TEXT",
            "review_notes": "TEXT",
            "outcome": "TEXT",
            "event_cluster_id": "INTEGER",
            "event_signature": "TEXT",
            "updated_at": "TIMESTAMP",
        }
        for column_name, column_type in missing_columns.items():
            if column_name not in existing_columns:
                cursor.execute(f"ALTER TABLE event_memos ADD COLUMN {column_name} {column_type}")

    def get_or_create_event_cluster(self, signature, sample_title, window_hours=24):
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cutoff = (datetime.now() - timedelta(hours=window_hours)).strftime('%Y-%m-%d %H:%M:%S')
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT id, count
                    FROM event_clusters
                    WHERE signature = ?
                    AND last_seen >= ?
                    ORDER BY last_seen DESC
                    LIMIT 1
                    ''',
                    (signature, cutoff),
                )
                row = cursor.fetchone()
                if row:
                    cluster_id = row[0]
                    count = row[1] or 0
                    cursor.execute(
                        '''
                        UPDATE event_clusters
                        SET last_seen = ?, count = ?
                        WHERE id = ?
                        ''',
                        (now_str, count + 1, cluster_id),
                    )
                    return cluster_id, False

                cursor.execute(
                    '''
                    INSERT INTO event_clusters
                    (signature, sample_title, first_seen, last_seen, count)
                    VALUES (?, ?, ?, ?, ?)
                    ''',
                    (signature, sample_title, now_str, now_str, 1),
                )
                return cursor.lastrowid, True
        except Exception as e:
            logger.error(f"❌ 事件簇处理失败: {e}")
            return None, False

    def update_signals_by_news_title(self, news_title, **fields):
        if not news_title:
            return
        allowed = {
            "confidence_effective",
            "event_cluster_id",
            "event_signature",
            "gap_confidence",
            "validation_score",
            "coverage_status",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        sets = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [news_title]
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f'''
                    UPDATE signals
                    SET {sets}
                    WHERE news_title = ?
                    ''',
                    values,
                )
                conn.commit()
        except Exception as e:
            logger.error(f"❌ 信号更新失败: {e}")

    def update_event_memo_review(self, memo_id, review_status, review_notes, outcome):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    UPDATE event_memos
                    SET review_status = ?,
                        review_notes = ?,
                        outcome = ?,
                        updated_at = ?
                    WHERE id = ?
                    ''',
                    (
                        review_status,
                        review_notes,
                        outcome,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        memo_id,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"❌ 事件备忘录更新失败: {e}")

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
