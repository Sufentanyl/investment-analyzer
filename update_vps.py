#!/usr/bin/env python3
"""
在VPS上更新llm_analyzer.py添加Kimi替补机制
"""
import sys

# 读取原文件
with open('src/llm_analyzer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到插入位置（在gemini_model之后）
insert_idx = None
for i, line in enumerate(lines):
    if 'self.gemini_model = os.getenv("GEMINI_MODEL"' in line:
        insert_idx = i + 1
        break

if not insert_idx:
    print("未找到插入位置")
    sys.exit(1)

# 插入Kimi配置
kimi_config = [
    '\n',
    '        # 🔥 新增: Kimi API (替补)\n',
    '        self.kimi_key = os.getenv("KIMI_API_KEY")\n',
    '        self.kimi_base = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")\n',
    '        self.kimi_model = "moonshot-v1-8k"\n',
]

lines = lines[:insert_idx] + kimi_config + lines[insert_idx:]

# 修改client_qwen初始化部分（添加kimi client）
for i, line in enumerate(lines):
    if 'self.client_qwen = None' in line:
        lines.insert(i + 1, '        self.client_kimi = None  # 🔥 新增\n')
        break

# 修改__init__添加telegram bot
for i, line in enumerate(lines):
    if 'self._aiohttp_session = None' in line:
        lines.insert(i + 1, '\n')
        lines.insert(i + 2, '        # 🔥 新增: Telegram Bot (用于发送fallback通知)\n')
        lines.insert(i + 3, '        self.telegram_bot = None\n')
        lines.insert(i + 4, 'self.chat_id = None\n')
        break

# 添加set_telegram_bot方法
for i, line in enumerate(lines):
    if 'def _ensure_clients(self):' in line:
        # 在此方法前插入新方法
        indent = len(line) - len(line.lstrip())
        new_method = [
            '\n',
            '    def set_telegram_bot(self, bot, chat_id):\n',
            '        """🔥 新增: 设置Telegram Bot用于发送通知"""\n',
            '        self.telegram_bot = bot\n',
            '        self.chat_id = chat_id\n',
            '\n',
        ]
        lines = lines[:i] + new_method + lines[i:]
        break

# 写入新文件
with open('src/llm_analyzer.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✅ llm_analyzer.py 已更新")
