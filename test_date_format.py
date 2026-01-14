#!/usr/bin/env python3
from datetime import datetime

# 测试中文日期格式
weekdays = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
current_date = datetime.now().strftime(f"%Y年%m月%d日 {weekdays[datetime.now().weekday()]}")

print(f"Current date (Chinese format): {current_date}")
print(f"Weekday index: {datetime.now().weekday()}")
print(f"Weekday name: {weekdays[datetime.now().weekday()]}")

# 验证容器时区
import os
print(f"\nTZ environment variable: {os.getenv('TZ', 'Not set')}")
