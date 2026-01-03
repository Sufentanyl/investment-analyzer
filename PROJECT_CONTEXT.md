# 个人量化辅助系统 - 项目上下文

> **最后更新**: 2026-01-02
> **项目状态**: 🟡 调试阶段
> **作者背景**: 编程小白，在 Gemini 帮助下完成

---

## 📋 项目概述

### 功能简介
这是一个 **AI 驱动的个人量化辅助系统**，核心功能：
1. 收集国际财经新闻（Bloomberg、Reuters）
2. 多 LLM 交叉验证分析（DeepSeek + Qwen）
3. 检测信息差（国内是否已有报道）
4. 自动推送高价值信号到 Telegram
5. Streamlit 可视化仪表板

### 核心创新点
- ✅ **信息差检测**：搜索国内新闻判断套利机会
- ✅ **多模型交叉验证**：降低 AI 幻觉风险
- ✅ **"说人话"报告**：强制 Gemini 不用专业术语
- ✅ **持仓优先级**：持仓股票阈值 0.7，其他 0.8

---

## 🏗️ 技术架构

### 技术栈
```
Frontend:  Streamlit (K线图 + AI信号回测)
Backend:   Python 3.11 + AsyncIO
Database:  SQLite (信号存储) + ChromaDB (RAG记忆) + Redis (缓存)
APIs:      yfinance, akshare, DeepSeek, Qwen, Gemini, SerpApi
Deploy:    Docker Compose (3 容器)
```

### 容器结构
```yaml
investment-analyzer:  # 主应用 (800-1200MB)
  ├── 新闻收集 (news_collector.py)
  ├── AI 分析 (llm_analyzer.py)
  ├── 信息差检测 (information_gap_detector.py)
  ├── 技术分析 (technical_analysis.py)
  └── Telegram Bot (main.py)

dashboard:             # 可视化 (600-800MB)
  └── Streamlit 仪表板 (dashboard.py)

redis:                 # 缓存 (150-300MB)
  └── 新闻去重 + 会话缓存
```

### 核心文件说明
```
src/
├── main.py                    # 主入口，调度 + Telegram Bot
├── llm_analyzer.py            # AI 引擎，多模型交叉验证
├── news_collector.py          # 新闻收集（RSS + newspaper3k）
├── information_gap_detector.py # 信息差检测（SerpApi + Qwen翻译）
├── technical_analysis.py      # 技术指标（RSI, MACD, 布林带）
├── database.py                # SQLite 信号存储
├── rag_memory.py              # ChromaDB 历史记忆
├── futures_watcher.py         # 期货监控（铁矿石）
├── chart_generator.py         # K线图生成
└── dashboard.py               # Streamlit 仪表板
```

---

## 🖥️ VPS 配置

### 硬件信息
```
位置:     Los Angeles, USA
CPU:      2 vCPU
RAM:      2.5 GB + 2 GB Swap ✅
存储:     45 GB Pure SSD
流量:     3000 GB/月
```

### 网络优势
- ✅ 访问 yfinance 稳定（延迟 < 50ms）
- ✅ 访问国际 API 畅通无阻
- ✅ 不需要翻墙

### 性能评估
- CPU: ✅ 够用（主要是 IO 密集型）
- 内存: ✅ 已优化（Swap 避免了 OOM）
- 存储: ✅ 充足（项目 < 10GB）

---

## ⚙️ 已优化的配置

### 调度频率
```python
# 巡逻频率: 45 分钟/次 (已从 20 分钟优化)
# 成本节省: ~30%
```

### 容器配置
```yaml
Dashboard:  restart: unless-stopped (保持开启，内存占用不高)
Network:    host 模式（洛杉矶 VPS 访问美 API 优化）
时区:       Asia/Shanghai
```

### 成本估算（每月）
```
VPS:        $15-25 (¥100-180)     RackNerd
DeepSeek:   ¥15-20                 (45min频率)
Qwen:       ¥15-20
Gemini:     ¥5-10
SerpApi:    ¥15-20
─────────────────────────────────
总计:       ¥150-250/月
```

---

## 🔑 环境变量配置

### 必需的 API Keys
```bash
# .env 文件（权限 600）
TELEGRAM_BOT_TOKEN=xxxxx
TELEGRAM_CHAT_ID=xxxxx
DEEPSEEK_API_KEY=xxxxx
QWEN_API_KEY=xxxxx
GEMINI_API_KEY=key1,key2,key3  # 支持多 key 轮询
SERPAPI_KEY=xxxxx              # 信息差检测（可选）
DASHBOARD_PASSWORD=xxxxx       # 默认 123456
```

### API 用途
- **DeepSeek**: 新闻逻辑分析（主模型）
- **Qwen**: 产业链联想 + 英文标题转中文
- **Gemini**: 生成"说人话"的最终报告
- **SerpApi**: Google News 搜索（检测信息差）

---

## 🎯 当前调试状态

### ✅ 已完成
- [x] 基础功能开发完成
- [x] Docker 部署成功
- [x] 2GB Swap 添加
- [x] 巡逻频率优化为 45 分钟
- [x] Dashboard 正常运行
- [x] Telegram Bot 推送正常

### 🟡 调试中
- [ ] 信号质量验证（观察期第 1-2 周）
- [ ] API 成本控制
- [ ] 信息差检测准确率
- [ ] 技术指标计算准确性

### 📅 待办事项
- [ ] 添加回测系统（验证历史信号）
- [ ] 优化 Prompt（提高 AI 准确率）
- [ ] 添加风控模块（止损、仓位管理）
- [ ] 部署监控告警（Server酱）

---

## 🐛 常见调试命令

### SSH 登录 VPS
```bash
ssh root@your-vps-ip
cd /path/to/investment-analyzer
```

### 查看日志
```bash
# 实时日志（主应用）
docker logs -f investment-analyzer

# Dashboard 日志
docker logs -f investment-dashboard

# 最近错误
docker logs investment-analyzer | grep -i "error" | tail -20
```

### 容器管理
```bash
# 查看所有容器
docker ps -a

# 重启主应用
docker restart investment-analyzer

# 查看资源占用
docker stats

# 进入容器调试
docker exec -it investment-analyzer bash
```

### 数据库查询
```bash
docker exec -it investment-analyzer sqlite3 /app/data/investment.db

# SQLite 命令
SELECT * FROM ai_signals ORDER BY timestamp DESC LIMIT 10;
SELECT signal, COUNT(*) FROM ai_signals GROUP BY signal;
.quit
```

### 测试功能
```bash
# 测试 yfinance
docker exec -it investment-analyzer python -c "import yfinance as yf; print(yf.Ticker('AAPL').history(period='1d').tail())"

# 测试 Redis
docker exec -it investment-analyzer python -c "import redis; r = redis.Redis(host='redis', port=6379); print(r.ping())"
```

---

## ⚠️ 注意事项

### 安全相关
1. ⚠️ `.env` 文件权限必须是 `600`（已设置）
2. ⚠️ 不要将 `.env` 提交到 Git（已加 .gitignore）
3. ⚠️ Dashboard 密码已修改（默认 123456）
4. ⚠️ API Key 泄露会损失惨重，定期轮换

### 性能相关
1. ⚠️ 内存紧张（2.5GB + 2GB Swap），监控 Swap 使用率
2. ⚠️ SQLite 单机够用，并发性能差（后续可改 PostgreSQL）
3. ⚠️ 日志文件会增长，定期清理 `/app/logs/`

### 成本相关
1. ⚠️ API 调用成本 ~¥150-250/月，设置预算告警
2. ⚠️ SerpApi 贡献 ~20% 成本，如不需要可禁用
3. ⚠️ 频率越低成本越低，但时效性变差

---

## 📊 策略评估计划

### 阶段一：观察期（第 1-2 周）
- **目标**: 不实盘，只记录信号
- **评估**:
  - AI 分析是否合理？
  - 推送时机是否准确？
  - 信息差检测有效吗？
- **决策点**: 信号质量 > 70% 继续，否则优化 Prompt

### 阶段二：轻仓测试（第 3-4 周）
- **目标**: 小额实盘（< ¥5000）
- **风控**:
  - 单笔 < 10% 仓位
  - 严格止损 -5%
  - 盈亏比 > 2:1
- **决策点**: 盈利继续，亏损止损

### 阶段三：长期决策（第 2 个月）
- **计算指标**:
  - 胜率 = 盈利笔数 / 总笔数
  - 盈亏比 = 平均盈利 / 平均亏损
  - 最大回撤 = (最高点 - 最低点) / 最高点
- **判断标准**:
  - 胜率 > 45% 且盈亏比 > 1.5 → 继续
  - 月收益 > 5% → 加仓
  - 月收益 < 0% → 及时止损

---

## 💡 下次对话快速开始

### 给 Claude 的提示词模板
```
你好！我在调试一个量化项目，请先阅读 PROJECT_CONTEXT.md 了解背景。

我的问题是：[填写你的问题]

当前状态：
- VPS 在洛杉矶，已加 2GB Swap
- 巡逻频率 45 分钟
- Dashboard 正常运行
- [描述你遇到的问题或想优化的点]
```

### 推荐的工作流
1. 每次有重大更新，修改 `PROJECT_CONTEXT.md` 的"最后更新"和"当前调试状态"
2. 遇到问题时，先说"看 PROJECT_CONTEXT.md，帮我..."
3. 每周记录一次策略表现（胜率、盈亏比、最大回撤）
4. 每月评估一次是否继续运行

---

## 📞 项目背景故事

> 我是编程小白，在 Gemini 的帮助下完成了这个项目。
> 从零基础学会 Python、Docker、异步编程，历时约 2 个月。
> 现在在调试阶段，希望能通过 AI 辅助提升投资决策质量。
>
> 如果你在用这个项目，欢迎交流！
> —— 2026-01-02

---

**文件路径**: `C:\Users\Jing\Desktop\CC\investment-analyzer\PROJECT_CONTEXT.md`
**记得**: 每次有重要变化都更新这个文件！
