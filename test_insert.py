#!/usr/bin/env python3
import sqlite3
from datetime import datetime

conn = sqlite3.connect("/app/data/investment.db")
cursor = conn.cursor()

# 创建表
cursor.execute("""
CREATE TABLE IF NOT EXISTS ai_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    news_title TEXT,
    signal TEXT,
    confidence REAL,
    reason TEXT,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# 插入测试数据
test_data = [
    ("600276", "恒瑞医药获得FDA批准", "positive", 0.85, "公司创新药获批，长期利好", "利好消息"),
    ("600900", "长江电力业绩大增50%", "positive", 0.78, "Q4营收超预期", "业绩优秀"),
    ("600519", "贵州茅台股价创新高", "positive", 0.92, "市场需求旺盛", "白酒板块领涨"),
]

for data in test_data:
    cursor.execute("""
    INSERT INTO ai_signals (stock_code, news_title, signal, confidence, reason, summary, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (*data, datetime.now()))

conn.commit()
print(f"成功插入 {len(test_data)} 条测试数据!")

# 查询验证
cursor.execute("SELECT COUNT(*) FROM ai_signals")
count = cursor.fetchone()[0]
print(f"数据库中现在有 {count} 条信号")

conn.close()
