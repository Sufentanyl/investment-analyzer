# 🤖 AI量化交易助手

> **AI驱动的智能量化辅助系统** - 自动收集国际财经新闻，多LLM交叉验证分析，检测信息差套利机会，实时推送高价值信号到Telegram

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.2.1-orange.svg)](https://github.com/Sufentanyl/investment-analyzer)

---

## 📋 项目简介

这是一个**AI驱动的个人量化辅助系统**，通过自动化流程收集国际财经新闻，使用多个大语言模型进行交叉验证分析，检测国内信息差，自动推送高价值投资信号到Telegram。

### 🎯 核心价值

- **信息差套利**：检测国际财经新闻在国内的报道情况，发现套利机会
- **多模型验证**：DeepSeek + Qwen + Gemini 交叉验证，降低AI幻觉风险
- **智能决策**：结合技术分析（RSI、MACD、布林带）和AI分析
- **实时推送**：高价值信号自动推送到Telegram，不错过任何机会
- **事件聚合**：同一事件多源聚合，避免重复推送
- **量价验证**：评估市场对新闻的实际反应，过滤无效信号

---

## ✨ 核心功能

### 1. 🌍 国际新闻收集

**数据源**：
- Bloomberg RSS
- Reuters RSS
- 其他国际财经媒体

**核心特性**：
- ✅ 自动提取完整新闻内容（newspaper3k）
- ✅ 三重去重机制（URL + 标题 + 事件簇）
- ✅ Redis缓存，避免重复处理
- ✅ 覆盖美股、宏观经济、AI科技、半导体等行业

### 2. 🤖 多LLM交叉验证分析

#### 分析流程

```
新闻收集 → 多重去重 → AI多智能体辩论 → 技术指标验证 → 量价分析 → 信息差检测 → Gemini总结 → Telegram推送
```

#### LLM分工

| 模型 | 角色 | 职责 | 配置变量 |
|------|------|------|---------|
| **DeepSeek** | 主力分析 | 多空观点辩论、逻辑分析、风险评估 | `DEEPSEEK_API_KEY` |
| **Qwen (通义千问)** | 股票联想 | A股产业链联想、关键词提取、实体识别 | `QWEN_API_KEY` |
| **Gemini (Google)** | 最终报告 | 生成"说人话"的总结报告 | `GEMINI_API_KEY` |
| **Kimi (月之暗面)** | 备份替补 | 主力API异常时自动切换，确保高可用 | `KIMI_API_KEY` |

**核心创新**：
- ✅ **Buffett vs Munger 辩论模式**：避免单一模型偏见
- ✅ **量价验证评分**：评估市场对新闻的实际反应
- ✅ **自动故障切换**：Gemini 429 → Kimi替补 + Telegram通知
- ✅ **历史回测集成**：技术指标附带历史胜率

### 3. 🔍 信息差检测

**检测逻辑**：
1. 提取新闻核心关键词（中文）
2. 调用SerpApi搜索国内新闻
3. 判断覆盖状态：
   - `covered` - 有国内报道 → 市场可能已定价
   - `not_covered` - 无国内报道 → 信息差确认，提高优先级
   - `unknown` - 检测失败

**核心特性**：
- ✅ 并发限速（最多5个并发）
- ✅ 429/5xx自动重试
- ✅ 异常降级（失败→视为无信息差）
- ✅ 生成gap_confidence（信息差置信度）

### 4. 📊 技术分析集成

自动获取以下技术指标：
- **RSI (相对强弱指数)**：超买超卖判断
- **MACD (趋势指标)**：动量分析
- **布林带**：波动率判断
- **成交量分析**：资金流向验证
- **历史回测**：每个信号附带历史胜率

### 5. 🎯 事件聚类系统

**功能**：同一事件多源聚合，避免重复推送

**工作流程**：
1. 提取新闻标题 → 归一化 → 生成事件签名（MD5）
2. 查询24小时内是否有相同签名
3. 若存在 → 更新事件簇计数 + 冷却6小时
4. 若不存在 → 创建新事件簇

**核心特性**：
- ✅ 事件簇签名生成（去除stopwords）
- ✅ 24小时聚合窗口
- ✅ 6小时冷却机制（避免重复推送）
- ✅ 事件簇数据库存储

### 6. 📱 Telegram Bot 智能推送

**推送内容**：
- 📰 新闻标题 + 摘要
- 🤖 AI多空观点（Buffett vs Munger辩论）
- 📈 技术指标分析（RSI/MACD/布林带）
- 💎 信息差确认
- 🎯 置信度评分（基础置信度 + 信息差修正 + 量价验证）
- 🧭 套利模板标签（传导路径/对冲腿/失效条件）
- 🔔 告警等级与命中关键词
- 🧾 事件备忘录复盘（状态/备注/结论）
- 📊 K线图快照（可选）
- 🧩 事件簇ID与验证分

**核心命令**：
- `/analyze` - 手动触发巡逻
- `/status` - 查看系统状态
- `/api` - 查看API使用情况
- `/backtest` - 运行回测
- `/add` - 添加持仓（降低阈值）
- `/bind` - 绑定关键词

### 7. 🔬 轻量级回测引擎

**支持策略**：
- `hold_3_days` - 持有3天
- `hold_5_days` - 持有5天
- `stop_loss_5` - 止损5%
- `target_profit_10` - 止盈10%

**核心特性**：
- ✅ 分批计算，避免内存溢出
- ✅ 线程池异步执行网络请求
- ✅ 生成详细报告：胜率、盈亏比、最大回撤
- ✅ 结果保存到数据库

### 8. 🖥️ Streamlit Dashboard

**访问地址**：http://your-vps-ip:80

**功能页面**：
- 📈 **我的持仓**：实时监控持仓股票信号，查看历史分析
- 🚀 **核心情报流**：查看所有AI分析信号，支持筛选高胜率机会
- 📊 **深度数据分析**：板块热力图、置信度分布、多空情绪
- 🧩 **事件簇视图**：事件聚合展示，评分指标
- 🔬 **回测结果**：历史回测数据、策略对比、收益曲线

---

## 🏗️ 技术架构

### 技术栈

```
Frontend:  Streamlit (K线图 + AI信号回测仪表板)
Backend:   Python 3.11 + AsyncIO (异步高并发)
Database:  SQLite (WAL模式 + 索引优化) + Redis (缓存去重)
APIs:      yfinance, akshare, DeepSeek, Qwen, Gemini, Kimi, SerpApi
Deploy:    Docker Compose (3容器架构)
```

### 容器架构

```yaml
investment-analyzer:  # 主应用容器
  ├── 新闻收集模块 (news_collector.py)
  ├── AI分析引擎 (llm_analyzer.py)
  ├── 信息差检测器 (information_gap_detector.py)
  ├── 技术分析器 (technical_analysis.py)
  ├── 回测引擎 (backtest.py)
  ├── Telegram Bot (main.py)
  └── 期货监控 (futures_watcher.py)

dashboard:             # 可视化仪表板
  └── Streamlit Dashboard (dashboard.py)
      ├── 我的持仓
      ├── 核心情报流
      ├── 深度数据分析
      ├── 事件簇视图
      └── 回测结果

redis:                 # 缓存容器
  ├── 新闻去重
  └── 会话缓存
```

### 核心文件说明

```
src/
├── main.py                    # 主入口，调度 + Telegram Bot
├── llm_analyzer.py            # AI引擎，多模型交叉验证
├── news_collector.py          # 新闻收集（RSS + newspaper3k）
├── information_gap_detector.py # 信息差检测（SerpApi + Qwen翻译）
├── technical_analysis.py      # 技术指标（RSI, MACD, 布林带）
├── backtest.py                # 轻量级回测引擎
├── database.py                # SQLite信号存储（WAL模式 + 索引优化）
├── chart_generator.py         # K线图生成
├── event_templates.py         # 套利模板、行业映射、告警关键词
├── rag_memory.py              # ChromaDB历史记忆
├── futures_watcher.py         # 期货监控（铁矿石等）
└── dashboard.py               # Streamlit仪表板
```

---

## 🚀 快速开始

### 环境要求

- Docker & Docker Compose
- 2GB+ RAM（推荐2.5GB + 2GB Swap）
- 10GB+ 磁盘空间
- Python 3.11+（本地开发）

### API密钥准备

**必需的API Keys**：

#### 1. Telegram Bot ⭐
- 访问：https://t.me/BotFather
- 创建Bot，获取Token
- 获取你的Chat ID：发消息给 @userinfobot

#### 2. DeepSeek API ⭐ 主力分析模型
- 访问：https://platform.deepseek.com/
- 注册并获取API Key

#### 3. Qwen API (通义千问) ⭐
- 访问：https://dashscope.aliyuncs.com/
- 获取API Key
- 默认模型：`qwen-plus`（可通过环境变量修改为qwen-max等）

#### 4. Gemini API (Google) ⭐
- 访问：https://makersuite.google.com/app/apikey
- 创建API Key（建议创建多个，用逗号分隔）

#### 5. Kimi API (月之暗面) 🆕
- 访问：https://platform.moonshot.cn/
- 注册获取API Key
- 用途：替补API（当其他API异常时自动切换）

#### 6. SerpApi (可选，用于信息差检测)
- 访问：https://serpapi.com/
- 注册获取API Key

### 部署步骤

#### 1. 克隆项目

```bash
git clone https://github.com/Sufentanyl/investment-analyzer.git
cd investment-analyzer
```

#### 2. 创建环境变量文件

```bash
cp .env.example .env
nano .env
```

#### 3. 填写API密钥

```bash
# .env 文件示例
TELEGRAM_BOT_TOKEN=你的Bot_Token
TELEGRAM_CHAT_ID=你的Chat_ID

# DeepSeek API（主力分析模型）
DEEPSEEK_API_KEY=你的DeepSeek_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_DAILY_LIMIT=20  # 每日请求限制

# Qwen API（实体识别 + 产业链联想）
QWEN_API_KEY=你的Qwen_Key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus  # 默认模型，可改为qwen-max等

# Gemini API（最终报告生成）
GEMINI_API_KEY=key1,key2,key3  # 支持多key轮询
GEMINI_MODEL=gemini-1.5-flash

# Kimi API（替补API）🆕
KIMI_API_KEY=你的Kimi_Key
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_DAILY_LIMIT=15  # 每日请求限制

# SerpApi（可选，用于信息差检测）
SERPAPI_KEY=你的SerpApi_Key

# Streamlit Dashboard
DASHBOARD_PASSWORD=change_me_to_a_strong_password  # Dashboard访问密码

# 服务器标签
SERVER_LABEL=Unraid (Local 192.168.3.110)
```

#### 4. 启动容器

```bash
docker compose up -d --build
```

#### 5. 查看日志

```bash
# 主应用日志
docker logs -f investment-analyzer

# Dashboard日志
docker logs -f investment-dashboard
```

#### 6. 访问Dashboard

```
http://your-vps-ip:80
```

---

## 📊 量化逻辑详解

### 1. 信号生成流程

#### 步骤1：新闻收集与预处理
```python
1. 从RSS源收集最新新闻
2. 提取标题、正文、发布时间
3. 三重去重（URL + 标题 + 事件簇）
4. Redis缓存避免重复处理
```

#### 步骤2：事件聚合
```python
1. 标题归一化（去除stopwords）
2. 生成事件签名（MD5）
3. 查询24小时内是否有相同签名
4. 若存在 → 更新事件簇 + 冷却6小时
5. 若不存在 → 创建新事件簇
```

#### 步骤3：AI多智能体辩论
```python
1. Buffett (多头) 分析：
   - 利好消息是什么？
   - 影响程度多大？
   - 持续时间预期？

2. Munger (空头) 分析：
   - 潜在风险是什么？
   - 市场是否已反应？
   - 反向因素有哪些？

3. Judge (裁判) 综合判断：
   - 综合多空观点
   - 给出最终决策
   - 计算置信度
```

#### 步骤4：股票识别与联想
```python
1. Qwen提取新闻中的股票代码
2. 产业链联想（如"英伟达发布新GPU" → "台积电、SK海力士"）
3. 映射到可交易的市场代码（美股、A股等）
4. AI自动绑定关键词
```

#### 步骤5：技术指标验证
```python
1. 获取股票实时数据（yfinance）
2. 计算技术指标：
   - RSI > 70 → 超买，谨慎追高
   - RSI < 30 → 超卖，可能反弹
   - MACD金叉 → 看涨信号
   - MACD死叉 → 看跌信号
   - 价格突破布林带 → 波动加剧

3. 历史回测验证：
   - 查找类似历史信号
   - 计算历史胜率
   - 标注历史表现

4. 综合判断：
   - 技术面 + 消息面一致性
   - 出现矛盾时降低置信度
```

#### 步骤6：量价验证
```python
1. 计算量价验证评分 (reaction_score)：
   vol_ratio = 近1日成交量 / 过去20日平均成交量
   price_move = 近1日价格变动幅度
   reaction_score = 0.6 * min(vol_ratio/2.0, 1.0) + 0.4 * min(price_move/0.03, 1.0)

2. 评分含义：
   - 0.0-0.3 → 市场无明显反应
   - 0.3-0.6 → 市场有一定反应
   - 0.6-1.0 → 市场强烈反应
```

#### 步骤7：信息差检测
```python
1. Qwen将英文标题翻译为中文关键词
2. SerpApi搜索国内新闻
3. 判断逻辑：
   - 有国内报道 → 市场可能已定价 → 降低优先级
   - 无国内报道 → 信息差确认 → 提高优先级
4. 生成gap_confidence（信息差置信度）
```

#### 步骤8：置信度评分

```python
# 有效置信度计算
confidence_effective = base_conf + (gap_conf-0.5)*0.2 + (validation_score-0.5)*0.2

# 最终阈值
持仓股票: confidence_effective ≥ 0.65 → 推送
其他股票: confidence_effective ≥ 0.75 → 推送
```

#### 步骤9：报告生成与推送
```python
1. Gemini生成"说人话"报告：
   - 避免专业术语
   - 清晰的多空观点
   - 可操作的建议

2. 生成K线图快照（可选）

3. Telegram推送：
   - 高价值信号立即推送
   - 中等信号批量推送
   - 低质量信号不推送
```

### 2. 风险控制机制

#### 持仓优先级
- 已持仓股票的信号阈值降低到0.65（更敏感）
- 帮助及时减仓或加仓

#### 冷却机制
- 手动触发：1分钟冷却
- 自动巡逻：45分钟间隔
- 事件簇冷却：6小时避免重复推送

#### 多模型验证
- 至少2个LLM观点一致才推送
- 降低单一模型幻觉风险

#### 历史学习
- SQLite存储历史信号
- 持续优化预测准确率

---

## 💡 使用技巧

### 1. 优化持仓管理

**添加持仓**（降低信号阈值）：
```
/add 600519  # 贵州茅台
/add NVDA     # 英伟达
/add TSLA     # 特斯拉
```

**移除持仓**：
```
/del 600519
```

**查看持仓列表**：
```
/list
```

### 2. 自定义概念关联

**绑定关键词到股票**：
```
/bind AI芯片 600030
/bind 新能源 BYD
```

**批量绑定**（支持多个关键词/股票）：
```
/bind 半导体,芯片 600030
/bind 新能源,光伏,储能 300750
/bind AI芯片 600030,688981  # 一个关键词绑定多只股票
```

这样当新闻提到"AI芯片"时，会自动关联到600030。

### 3. 与AI对话

```
/deepseek 分析一下英伟达的最新财报
/gemini 总结今天的财经新闻
/qwen 翻译这段英文新闻
```

### 4. 运行回测

```
/backtest 30 hold_3_days     # 回测最近30天，持有3天策略
/backtest_7d                 # 快速回测7天
/backtest_30d                # 快速回测30天
/backtest_90d                # 快速回测90天
```

### 5. 查看历史信号

访问Dashboard：`http://your-vps-ip:80`

**功能清单**：
- **持仓监控**：查看你的持仓股票及其最新AI分析
- **信号历史**：每个股票的历史信号记录
- **回测功能**：运行回测并查看结果
- **板块热力图**：AI关注的热门概念Top 10
- **多空情绪**：市场整体AI情绪分析
- **置信度分布**：AI决策置信度统计

---

## ⚙️ 配置说明

### 巡逻频率调整

编辑 `.env` 文件：
```bash
# 默认45分钟巡逻一次（在main.py中修改）
SCHEDULER_MINUTES=45  # 可调整为20-120分钟
```

**建议**：
- 频率越高（20分钟）→ 时效性强但成本高
- 频率越低（60分钟）→ 成本低但可能错过机会

### 阈值调整

编辑 `.env` 文件：
```bash
CONFIDENCE_THRESHOLD_HOLD=0.65    # 持仓股票阈值
CONFIDENCE_THRESHOLD_NORMAL=0.75  # 其他股票阈值
```

**建议**：
- 保守策略：提高到 0.8/0.85（更少但更准的信号）
- 激进策略：降低到 0.6/0.7（更多信号但噪音增加）

### 事件聚类调整

编辑 `.env` 文件：
```bash
CLUSTER_WINDOW_HOURS=24      # 聚合窗口（小时）
CLUSTER_COOLDOWN_HOURS=6     # 冷却时间（小时）
```

### API成本控制

**每月成本估算**（45分钟频率）：
- DeepSeek: ¥15-20
- Qwen (qwen-plus): ¥15-20
- Gemini: ¥5-10（免费版）
- Kimi (替补): ¥5-10
- SerpApi: ¥15-20
- **总计: ¥55-85/月**

**省钱技巧**：
1. 延长巡逻间隔到60分钟
2. 关闭SerpApi（不检测信息差）
3. 设置每日API请求限制（DEEPSEEK_DAILY_LIMIT, KIMI_DAILY_LIMIT）
4. 利用Kimi替补机制避免主API超额收费

---

## 📈 性能优化

### 内存优化（VPS 2.5GB场景）
- ✅ LRU缓存限制（最大1000条）
- ✅ Redis连接复用
- ✅ SQLite WAL模式 + 连接复用
- ✅ 2GB Swap防止OOM
- ✅ 回测分批计算（每批20条）

### CPU优化
- ✅ 异步并发处理
- ✅ 线程池执行网络请求
- ✅ 智能去重减少计算
- ✅ 批量API调用

### 网络优化
- ✅ 使用洛杉矶VPS（访问美API延迟<50ms）
- ✅ HTTP连接复用（aiohttp session）
- ✅ 超时控制（15-30秒）
- ✅ 并发限速（信息差检测）

### 数据库优化
- ✅ WAL模式（支持并发读写）
- ✅ 8个关键索引，查询速度提升10倍
- ✅ 自动迁移（新字段自动添加）
- ✅ 定期清理（保留90天数据）

---

## 🐛 故障排查

### 1. 容器无法启动

```bash
# 查看日志
docker compose logs investment-analyzer

# 常见原因：
- .env 文件未创建
- API Key无效
- 端口被占用
```

### 2. Telegram Bot无响应

```bash
# 检查Bot Token
docker compose exec investment-analyzer env | grep TELEGRAM

# 测试连接
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

### 3. API调用失败

```bash
# 查看错误日志
docker logs investment-analyzer | grep -i "error"

# 常见原因：
- API Key过期
- 额度用尽
- 网络问题

# 解决方案：
- 使用 /api 命令查看API状态
- 等待配额重置或自动切换到Kimi
```

### 4. 内存不足

```bash
# 查看资源占用
docker stats investment-analyzer

# 添加Swap（如果还没有）
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### 5. Dashboard无法访问

```bash
# 检查容器状态
docker ps | grep investment-dashboard

# 查看日志
docker logs investment-dashboard

# 检查端口
netstat -tlnp | grep 80
```

---

## 🔒 安全注意事项

### ⚠️ 必须遵守

1. **永远不要提交敏感文件到Git**：
   - `.env` 文件
   - `config.yaml`
   - `data/` 目录
   - `logs/` 目录

2. **定期轮换API密钥**（建议每90天）

3. **限制Dashboard访问**：
   - 使用强密码
   - 部署在VPN后（可选）

4. **监控API成本**：
   - 设置预算告警
   - 定期检查账单

---

## 📊 策略评估

### 当前阶段：观察期（第1-2周）

**目标**：
- 不实盘，只记录信号
- 验证AI分析准确性
- 评估推送时机

**评估指标**：
- 信号频率是否合理？
- AI分析是否准确？
- 信息差检测有效吗？
- 技术指标准确性如何？

**决策点**：
- 信号质量 > 70% → 进入轻仓测试
- 信号质量 < 50% → 优化Prompt

### 后续阶段

详见 `PROJECT_CONTEXT.md` 中的完整评估计划。

---

## 🛠️ 开发与贡献

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
nano .env

# 运行主程序
python src/main.py

# 运行Dashboard
streamlit run src/dashboard.py
```

### 代码结构
- `src/` - 源代码
- `data/` - 数据文件（不提交到Git）
- `logs/` - 日志文件（不提交到Git）
- `docs/` - 文档

### 提交规范
```bash
git commit -m "feat: 添加新功能"
git commit -m "fix: 修复bug"
git commit -m "docs: 更新文档"
git commit -m "chore: 清理代码"
```

---

## 📝 更新日志

### v1.2.1 (2026-01-09) 🆕
- ✅ **事件级聚类**：同一事件多源聚合，冷却去重避免重复推送
- ✅ **信息差置信度**：引入覆盖状态与置信度，异常降级减少误报
- ✅ **量价验证评分**：用量价反应评分做二次过滤与展示
- ✅ **Dashboard升级**：新增事件簇视图与更清晰的评分指标
- ✅ **性能优化**：三重去重机制、并发限速、异常降级

### v1.2.0 (2026-01-07) 🆕
- ✅ **Kimi替补API机制**：Gemini/DeepSeek/Qwen异常时自动切换到Kimi
- ✅ **Dashboard持仓功能**：新增"我的持仓"页面，实时监控持仓股票信号
- ✅ **API状态查询**：新增`/api`命令查看API使用情况
- ✅ **Qwen模型切换**：默认模型改为qwen-plus（环境变量可配置）
- ✅ **批量关键词绑定**：`/bind`命令支持多个关键词和股票
- ✅ **股票名称显示**：持仓页面显示股票名称（如：600276 恒瑞医药）
- ✅ **回测功能**：支持多种回测策略并可视化结果
- ✅ **高可用性**：API异常自动切换并发送Telegram通知

### v1.1.0 (2026-01-05)
- ✅ 添加A股核心关键词库
- ✅ 优化新闻过滤机制
- ✅ 改进多空观点分析
- ✅ 添加技术指标权重

### v1.0.0 (2026-01-03)
- ✅ 基础功能开发完成
- ✅ Docker部署成功
- ✅ 修复42个bug和内存泄漏
- ✅ 清理GitHub仓库
- ✅ 完善文档

### 已知问题
- [ ] 优化LLM Prompt（降低幻觉）
- [ ] 添加更多回测策略
- [ ] 实时行情推送（WebSocket）
- [ ] 部署监控告警（Prometheus + Grafana）

---

## 📞 联系方式

- **作者**: Sufentanyl
- **GitHub**: https://github.com/Sufentanyl/investment-analyzer
- **问题反馈**: 提交Issue

---

## 📄 许可证

MIT License

---

## 🙏 致谢

感谢以下AI工具的帮助：
- **DeepSeek** - 强大的逻辑分析能力
- **Qwen (通义千问)** - 优秀的实体识别
- **Gemini** - 自然语言生成
- **Kimi** - 可靠的替补服务
- **Claude** - 代码开发和优化

特别感谢Gemini和Claude在项目开发过程中的大量帮助！

---

## ⚠️ 免责声明

**本系统仅供学习和研究使用，不构成任何投资建议。**

- 股市有风险，投资需谨慎
- AI分析可能存在错误和幻觉
- 请结合自身判断做出投资决策
- 作者不对任何投资损失负责

使用本系统即表示您同意以上条款。

---

**🎯 祝您投资顺利！**
