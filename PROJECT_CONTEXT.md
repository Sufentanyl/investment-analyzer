# Investment Analyzer 项目上下文

**最后更新**: 2026-01-24
**项目状态**: 🟢 运行正常 + ValueCell AI 集成
**VPS地址**: <YOUR_VPS_IP>
**作者背景**: 编程小白，在AI助手帮助下完成
**重大更新**: ValueCell 多智能体深度研究集成 (2026-01-24)

---

## 📋 项目概述

AI驱动的A股量化投资助手，通过分析国际新闻、检测信息差、技术指标回测，为投资决策提供支持。

**核心功能**:
- 🔍 国际新闻自动巡检（每45分钟）
- 🤖 AI多模型辩论分析（Buffett vs Munger模式）
- 📊 轻量级回测系统（4种策略）
- 🔗 关键词自动关联股票（80个精选A股关键词）
- 📈 实时技术指标分析
- 💬 Telegram Bot交互
- 🖥️ Streamlit可视化仪表板

**核心创新点**:
- ✅ **信息差检测**：搜索国内新闻判断套利机会
- ✅ **多模型交叉验证**：降低AI幻觉风险
- ✅ **"说人话"报告**：强制Gemini不用专业术语
- ✅ **持仓优先级**：持仓股票阈值0.7，其他0.8
- ✅ **A股关键词库**：80个核心概念一键导入

---

## 🏗️ 技术架构

### 部署环境
- **VPS**: Los Angeles (<YOUR_VPS_IP>)
- **配置**: 2.5GB RAM + 2GB Swap
- **系统**: Docker Compose (3容器)
  - `investment-analyzer`: 主应用
  - `investment-dashboard`: Streamlit可视化
  - `investment-redis`: 缓存和去重

### 核心技术栈
- **LLM**: DeepSeek (主分析)、Qwen (股票联想)、Gemini (审阅)
- **数据源**: SerpApi (国际新闻)、yfinance (行情)
- **数据库**: SQLite (WAL模式 + 索引优化)
- **缓存**: Redis (新闻去重)
- **框架**: Python Telegram Bot、APScheduler

### 关键文件结构
```
investment-analyzer/
├── src/
│   ├── main.py                  # Telegram Bot主程序
│   ├── llm_analyzer.py          # LLM分析引擎
│   ├── news_collector.py        # 新闻采集
│   ├── information_gap_detector.py  # 信息差检测
│   ├── technical_analysis.py    # 技术分析
│   ├── backtest.py             # 轻量级回测系统
│   ├── database.py             # 数据库管理
│   ├── dashboard.py            # Streamlit 可视化面板
│   └── valuecell_bridge/       # ⭐ ValueCell AI 集成 (2026-01-24)
│       ├── __init__.py
│       ├── config.py           # 模型配置管理
│       ├── research_adapter.py # 深度研究适配器
│       ├── news_adapter.py     # 智能新闻适配器
│       └── utils.py            # 工具函数（重试、多数据源、LLM降级）
├── vendor/
│   └── valuecell/              # ValueCell 源码（参考用）
├── initial_keywords.json        # A股核心关键词库 (2026-01-04)
├── config.yaml                  # 配置文件（不提交到Git）
├── .env                         # 环境变量（不提交到Git）
├── docker-compose.yml
├── PROJECT_CONTEXT.md           # 本文件
└── README.md                    # GitHub说明文档
```

---

## 🆕 ValueCell AI 集成 (2026-01-24)

### 功能概述

集成 ValueCell 多智能体平台，提供专业级深度研究和智能新闻分析。

**新增命令**:
- `/research <股票代码>` - 深度研究（公告 + 财务数据 + AI分析）
- `/deepnews <关键词>` - 智能新闻分析（突发/金融新闻 + A股影响预测）
- `/agent_status` - 查看 ValueCell Agent 状态

**核心特性**:
- ✅ **多数据源自动切换**: 东方财富 → 巨潮资讯
- ✅ **财务指标分析**: PE/PB/ROE/市值/北向资金
- ✅ **重试机制**: 自动重试 + 指数退避
- ✅ **LLM 降级**: DeepSeek → Qwen → Gemini → Kimi
- ✅ **并发获取**: 同时获取公告、财务、北向资金数据

### 技术架构

**适配器模式**: 不修改 ValueCell 源码，通过轻量级适配器调用核心功能

```python
from valuecell_bridge import ResearchAdapter, NewsAdapter

# 深度研究
adapter = ResearchAdapter()
result = await adapter.deep_research("投资价值分析", "600519")

# 智能新闻
news_adapter = NewsAdapter()
news = await news_adapter.get_smart_news("人工智能")
```

### 数据源优先级

| 数据类型 | 主数据源 | 备用数据源 | 说明 |
|---------|---------|----------|------|
| 公告 | 东方财富 | 巨潮资讯 | 自动切换 |
| 实时行情 | 东方财富 | - | 10秒超时 |
| 财务指标 | 东方财富 | - | PE/PB/ROE |
| 北向资金 | 东方财富 | - | 可选数据 |
| 新闻 | SerpApi | - | Google News/Search |

### Dashboard 集成

Streamlit 面板新增 "AI 助手" Tab:
- 明亮简约设计
- 双栏布局（深度研究 | 智能新闻）
- 实时显示财务指标卡片
- 北向资金持仓变化追踪

**访问地址**: https://streamlit.jingyibing.top

---

## 🎯 核心功能详解

### 1. 关键词系统 ⭐ (2026-01-04 新增)

**问题根源**: "系统的盈利能力取决于信息质量，信息质量取决于关键词。但没有初始关键词，怎么抓取新闻？"

**解决方案**:
- **初始关键词库**: 80个精选A股关键词
- **一键导入**: `/import_keywords` 命令
- **AI自动学习**: 分析新闻时自动提取并绑定关键词

**关键词分类**:
- **宏观经济** (15个): 美联储、Fed、加息、降息、CPI、非农数据、失业率等
- **科技/半导体** (20个): AI芯片、半导体、光刻机、HBM、中芯国际、北方华创等
- **新能源** (20个): 新能源汽车、锂电池、光伏、储能、比亚迪、宁德时代等
- **A股特色** (25个): 白酒、军工、医药、银行、券商、房地产、猪周期等

**使用方法**:
```bash
# Telegram Bot中
/import_keywords  # 导入80个核心关键词
/bind 关键词 股票代码  # 手动绑定
/list  # 查看所有关键词
/autobind_on  # 启用AI自动绑定
/autobind_off  # 禁用AI自动绑定
```

**配置保存**: `/app/data/user_config.json`

### 2. 轻量级回测系统

**设计目标**: VPS资源友好 (+100-200MB)

**4种策略**:
- `hold_3_days`: 持有3天
- `hold_5_days`: 持有5天
- `stop_loss_5`: 5%止损
- `target_profit_10`: 10%止盈

**快捷命令**:
- `/backtest_7d` - 回测7天
- `/backtest_30d` - 回测30天
- `/backtest_90d` - 回测90天
- `/backtest [天数] [策略]` - 自定义回测

**性能优化**:
- 批处理: 20个信号/批次
- 异步网络请求
- ThreadPoolExecutor并发

### 3. AI多智能体辩论

**Buffett vs Munger 模式**:
- **Bull Agent**: 多方观点（寻找机会）
- **Bear Agent**: 空方观点（提示风险）
- **Judge Agent**: 综合判断（最终决策）

**输出字段**:
```json
{
  "stock_market_influence": "positive/negative/neutral",
  "confidence": 0.0-1.0,
  "summary": "一句话总结",
  "reason": "综合逻辑",
  "concept": "核心概念",
  "bull_point": "多方理由",
  "bear_point": "空方理由",
  "related_tickers": ["股票代码"],
  "stock_data": [...]
}
```

**阈值机制**:
- 持仓股票: 0.7（更敏感）
- 非持仓: 0.8

### 4. 信息差检测

**原理**: 使用SerpApi检查新闻是否在国内有报道

**判断逻辑**:
- 无中文报道 → 信息差大 → 高优先级
- 有中文报道 → 信息差小 → 低优先级

---

## 🔧 重要配置

### Telegram Bot命令列表
```
📖 **使用帮助**
/start          - 📖 使用说明书

👮 **巡逻功能**
/analyze        - 👮 手动巡逻

📊 **回测系统**
/backtest       - 🔬 自定义回测
/backtest_7d    - 📊 回测7天
/backtest_30d   - 📊 回测30天
/backtest_90d   - 📊 回测90天

🏥 **系统管理**
/status         - 🏥 系统状态
/dashboard      - 🖥️ 量化指挥室

🎮 **持仓管理**
/add 代码       - ➕ 添加持仓
/del 代码       - ➖ 删除持仓
/clear          - 🗑️ 清空持仓
/list           - 📋 配置列表

🤖 **AI智能功能**
/autobind_on    - ✅ 启用AI自动绑定
/autobind_off   - ❌ 禁用AI自动绑定

📦 **关键词管理** ⭐
/import_keywords - 📦 导入A股关键词库
/bind           - 🔗 绑定关键词

🧠 **AI对话**
/deepseek 问题   - 🧠 问DeepSeek
/gemini 问题     - ⚖️ 问Gemini
/qwen 问题      - 💭 问Qwen
```

### VPS部署命令
```bash
# 进入项目目录
cd ~/investment-analyzer

# 拉取最新代码
git pull origin main

# 重启服务（注意：使用 docker compose 不是 docker-compose）
docker compose down
docker compose up -d

# 查看日志
docker compose logs -f investment-analyzer
```

### Git工作流程
```bash
# 1. 查看状态
git status

# 2. 添加文件
git add .

# 3. 提交（使用HEREDOC格式）
git commit -m "$(cat <<'EOF'
feat: 简短描述

详细说明...

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"

# 4. 推送
git push origin main
```

---

## 🔑 环境变量配置

### 必需的 API Keys
```bash
# .env 文件（权限 600，绝不能删除！）
TELEGRAM_BOT_TOKEN=xxxxx
TELEGRAM_CHAT_ID=xxxxx
DEEPSEEK_API_KEY=xxxxx
QWEN_API_KEY=xxxxx
GEMINI_API_KEY=key1,key2,key3  # 支持多 key 轮询
SERPAPI_KEY=xxxxx              # 信息差检测（可选）
DASHBOARD_PASSWORD=xxxxx       # 请设置强密码
REDIS_HOST=127.0.0.1
```

### API 用途
- **DeepSeek**: 新闻逻辑分析（主模型）
- **Qwen**: 产业链联想 + 英文标题转中文
- **Gemini**: 生成"说人话"的最终报告
- **SerpApi**: Google News 搜索（检测信息差）

---

## 📊 当前数据状态

### 关键词库状态 ⭐
- **总数**: 80个核心关键词
- **来源**: initial_keywords.json
- **功能状态**: ✅ 已部署，待测试
- **首次导入**: 待用户执行 `/import_keywords`

### 用户持仓
- **当前**: 空白（用户主要战场在A股）
- **推荐代码**: 600519(茅台)、300750(宁德时代)、002594(比亚迪)等

### 定时任务
- **新闻巡逻**: 每45分钟
- **期货播报**: 每天09:15

### 容器状态
- **investment-analyzer**: ✅ 运行中
- **investment-dashboard**: ✅ 运行中
- **investment-redis**: ✅ 运行中

---

## ⚠️ 重要注意事项（从错误中学习）

### 🔴 安全问题（深刻教训）

1. **.env文件绝不能删除**
   - 包含所有API密钥
   - 删除后果：系统完全瘫痪
   - 历史教训：差点因清理脚本删除

2. **代码必须先确认再推送**
   - 用户要求："改完代码问一下我觉得没问题再push到github"
   - 工作流程：展示代码 → 用户确认 → 推送 → 部署

3. **清理脚本要安全**
   - 必须先检查关键文件存在（.env、docker-compose.yml）
   - 不能用通配符删除（如 `rm -f *.md`）
   - 只删除明确指定的文件

### 🟡 Git配置教训

1. **不要用 `git reset --hard` 盲目重置**
   - 会丢失本地修改
   - 应该先备份重要文件

2. **GitHub Token认证**
   - 解决403错误
   - 配置 `git remote set-url origin`

3. **VPS IP地址**: `<YOUR_VPS_IP>`
   - 不是 `<YOUR_VPS_IP>`（历史错误）
   - 不是 `emergency-fix.bat` 中的地址

### 🟢 A股市场适配

1. **股票代码格式**:
   - 6开头 → 上海: `.SS` (600519.SS)
   - 0/3开头 → 深圳: `.SZ` (300750.SZ)

2. **主要市场**: A股，不是美股
   - 之前示例都是TSLA、AAPL、NVDA
   - 已全部改为A股代码

3. **特色板块**: 白酒、军工、医药、金融

### 🔵 VPS资源限制

1. **总内存**: 2.5GB RAM + 2GB Swap
2. **回测策略**: 必须用轻量级版本
3. **Docker命令**: 使用 `docker compose` 不是 `docker-compose`

---

## 🐛 常见调试命令

### SSH 登录 VPS
```bash
ssh root@<YOUR_VPS_IP>
cd ~/investment-analyzer
```

### 查看日志
```bash
# 实时日志（主应用）
docker logs -f investment-analyzer

# Dashboard 日志
docker logs -f investment-dashboard

# 最近错误
docker logs investment-analyzer | grep -i "error" | tail -20

# 查看最近30行
docker logs --tail 30 investment-analyzer
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

---

## 🔄 近期更新历史

### 2026-01-04: 关键词系统 ⭐
- ✅ 创建80个精选A股关键词库 (`initial_keywords.json`)
- ✅ 实现 `/import_keywords` 一键导入命令
- ✅ AI自动绑定功能（默认启用）
- ✅ 推送并部署到VPS (commit: 7a1e511)
- ✅ 更新Bot菜单和帮助文档
- ✅ 纠正VPS地址为 <YOUR_VPS_IP>

### 2025-xx-xx: 轻量级回测
- ✅ 4种回测策略
- ✅ 批处理优化（+100-200MB）
- ✅ 快捷命令（7d/30d/90d）

### 2025-xx-xx: A股适配
- ✅ 所有示例改为A股
- ✅ 股票代码格式适配
- ✅ 添加A股特色板块

---

## 📝 待办事项

### 短期（本周）
- [ ] 测试 `/import_keywords` 命令
- [ ] 验证关键词抓取效果
- [ ] 监控AI自动学习情况
- [ ] 观察信号质量

### 中期（本月）
- [ ] 根据使用反馈优化关键词库
- [ ] 调整回测策略参数
- [ ] 优化技术指标算法
- [ ] 评估信号质量

### 长期（未来）
- [ ] 添加更多数据源
- [ ] 实现组合回测
- [ ] 开发风险管理模块
- [ ] 优化Prompt提高准确率

---

## 🔗 快速恢复上下文

**下次对话时说**:
> "继续 investment-analyzer 项目"

**我会做的**:
1. 读取 `PROJECT_CONTEXT.md` (本文件)
2. 读取 `src/main.py` 了解最新功能
3. 读取 `initial_keywords.json` 了解关键词库
4. 检查 Git log 查看最近提交

**然后我会**: 快速了解项目状态并继续工作。

---

## 💡 项目背景故事

> 我是编程小白，在AI助手的帮助下完成了这个项目。
> 从零基础学会Python、Docker、异步编程，历时约2个月。
>
> **核心理念**: 系统的盈利能力取决于信息质量，信息质量取决于关键词。
> **关键突破**: 2026-01-04 实现80个A股核心关键词库，解决"无关键词无法抓新闻"的根本问题。
>
> 现在在调试阶段，希望能通过AI辅助提升投资决策质量。
>
> —— 2026-01-04

---

**文件路径**: `C:\Users\Jing\Desktop\CC\investment-analyzer\PROJECT_CONTEXT.md`
**重要提醒**: 每次有重大更新后都更新此文件！

**记住**:
- VPS地址: <YOUR_VPS_IP>
- Docker命令: `docker compose` (不是 docker-compose)
- 工作流程: 改代码 → 问用户 → 推送 → 部署
