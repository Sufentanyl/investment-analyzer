# 🤖 AI量化交易助手

> **AI驱动的智能量化辅助系统** - 自动收集国际财经新闻，多LLM交叉验证分析，检测信息差套利机会，实时推送高价值信号到Telegram

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📋 项目简介

这是一个**AI驱动的个人量化辅助系统**，通过自动化流程收集国际财经新闻，使用多个大语言模型进行交叉验证分析，检测国内信息差，自动推送高价值投资信号到Telegram。

### 🎯 核心价值

- **信息差套利**：检测国际财经新闻在国内的报道情况，发现套利机会
- **多模型验证**：DeepSeek + Qwen + Gemini 交叉验证，降低AI幻觉风险
- **智能决策**：结合技术分析（RSI、MACD、布林带）和AI分析
- **实时推送**：高价值信号自动推送到Telegram，不错过任何机会

---

## ✨ 核心功能

### 1. 🌍 国际新闻收集
- **数据源**：Bloomberg、Reuters 国际财经新闻RSS
- **内容提取**：使用 newspaper3k 提取完整新闻内容
- **去重机制**：Redis缓存避免重复处理
- **覆盖范围**：美股、宏观经济、AI科技、半导体等行业

### 2. 🤖 多LLM交叉验证分析

#### 分析流程：
```
新闻收集
    ↓
Qwen: 股票实体识别 + 产业链联想
    ↓
DeepSeek: 逻辑分析（多空观点、风险因素）
    ↓
技术指标: RSI、MACD、布林带分析
    ↓
综合评分: 置信度计算 + 信号判断
    ↓
信息差检测: 搜索国内新闻验证
    ↓
Gemini: 生成"说人话"的最终报告
    ↓
Telegram推送: 高价值信号实时通知
```

#### LLM分工：
- **Qwen (通义千问)**：
  - 识别新闻中的股票代码
  - 产业链联想（如"AI芯片"→"英伟达产业链"）
  - 英文标题翻译成中文搜索词
  - 模型：`qwen-plus`（可通过环境变量配置）

- **DeepSeek (深度求索)**：
  - 主力分析模型
  - 多空观点辩论
  - 风险因素识别
  - 历史相似案例回溯

- **Gemini (Google)**：
  - 最终报告生成
  - 强制"说人话"模式（不用专业术语）
  - 多key轮询提高可用性
  - **Kimi替补机制**：Gemini异常时自动切换到Kimi API并发送Telegram通知

- **Kimi (月之暗面)** 🔥：
  -替补API（Gemini/DeepSeek/Qwen异常时启用）
  - 自动故障切换
  - 确保服务高可用性

### 3. 🔍 信息差检测

**检测逻辑**：
1. 提取新闻核心关键词（中文）
2. 调用SerpApi搜索国内新闻
3. 判断是否有报道：
   - 有报道 → 可能已被市场定价，降低优先级
   - 无报道 → 信息差确认，提高优先级

**缓存机制**：
- 同一条新闻4小时内不重复检测
- LRU缓存，最大1000条，防止内存溢出

### 4. 📊 技术分析集成

自动获取以下技术指标：
- **RSI (相对强弱指数)**：超买超卖判断
- **MACD (趋势指标)**：动量分析
- **布林带**：波动率判断
- **成交量分析**：资金流向验证

### 5. 📱 Telegram Bot 智能推送

**推送内容**：
- 📰 新闻标题 + 摘要
- 🤖 AI多空观点
- 📈 技术指标分析
- 💎 信息差确认
- 🎯 置信度评分
- 📊 K线图快照（可选）

**交互命令**：
- `/analyze` - 手动触发巡逻
- `/status` - 查看系统状态
- `/api` - 查看API使用情况（Gemini/Qwen/DeepSeek状态）🆕
- `/add <股票代码>` - 添加持仓（降低信号阈值）
- `/remove <股票代码>` - 移除持仓
- `/list` - 查看当前持仓
- `/bind <关键词> <股票代码>` - 绑定概念关联（支持多个关键词/股票）🆕
- `/chat <模型> <消息>` - 与AI对话
- `/backtest <天数> <策略>` - 运行回测（如：`/backtest 30 hold_3_days`）🆕

---

## 🏗️ 技术架构

### 技术栈
```
Frontend:  Streamlit (K线图 + AI信号回测仪表板)
Backend:   Python 3.11 + AsyncIO (异步高并发)
Database:  SQLite (信号存储) + ChromaDB (RAG历史记忆) + Redis (缓存去重)
APIs:      yfinance, akshare, DeepSeek, Qwen, Gemini, SerpApi
Deploy:    Docker Compose (3容器架构)
```

### 容器架构
```yaml
investment-analyzer:  # 主应用容器 (800-1200MB)
  ├── 新闻收集模块 (news_collector.py)
  ├── AI分析引擎 (llm_analyzer.py)
  ├── 信息差检测器 (information_gap_detector.py)
  ├── 技术分析器 (technical_analysis.py)
  ├── Telegram Bot (main.py)
  └── 期货监控 (futures_watcher.py)

dashboard:             # 可视化仪表板 (600-800MB)
  └── Streamlit Dashboard (dashboard.py)
      ├── 📈 我的持仓（持仓监控、信号历史）🆕
      ├── 🚀 核心情报流
      ├── 📊 深度数据分析（板块热力图、置信度分布）
      └── 🔬 回测结果（历史回测、策略对比）🆕

redis:                 # 缓存容器 (150-300MB)
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
├── database.py                # SQLite信号存储
├── rag_memory.py              # ChromaDB历史记忆
├── futures_watcher.py         # 期货监控（铁矿石等）
├── chart_generator.py         # K线图生成
└── dashboard.py               # Streamlit仪表板
```

---

## 🚀 快速开始

### 环境要求
- Docker & Docker Compose
- 2GB+ RAM（推荐2.5GB + 2GB Swap）
- 10GB+ 磁盘空间

### API密钥准备

**必需的API Keys**：

1. **Telegram Bot**
   - 访问：https://t.me/BotFather
   - 创建Bot，获取Token
   - 获取你的Chat ID：发消息给 @userinfobot

2. **DeepSeek API** ⭐ 主力分析模型
   - 访问：https://platform.deepseek.com/
   - 注册并获取API Key

3. **Qwen API** (通义千问)
   - 访问：https://dashscope.aliyuncs.com/
   - 获取API Key
   - 默认模型：`qwen-plus`（可通过环境变量修改为qwen-max等）🆕

4. **Gemini API** (Google)
   - 访问：https://makersuite.google.com/app/apikey
   - 创建API Key（建议创建多个，用逗号分隔）

5. **Kimi API** (月之暗面) 🆕
   - 访问：https://platform.moonshot.cn/
   - 注册获取API Key
   - 用途：替补API（当其他API异常时自动切换）

6. **SerpApi** (可选，用于信息差检测)
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
DASHBOARD_PASSWORD=123456  # Dashboard访问密码
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
http://your-vps-ip:8501
```

**Dashboard功能** 🆕：
- 📈 **我的持仓**：实时监控持仓股票信号，查看历史分析
- 🚀 **核心情报流**：查看所有AI分析信号，支持筛选高胜率机会
- 📊 **深度数据分析**：板块热力图、置信度分布、多空情绪
- 🔬 **回测结果**：历史回测数据、策略对比、收益曲线

---

## 📊 量化逻辑详解

### 1. 信号生成流程

#### 步骤1：新闻收集与预处理
```python
1. 从RSS源收集最新新闻
2. 提取标题、正文、发布时间
3. Redis去重（避免重复处理）
```

#### 步骤2：股票实体识别
```python
1. Qwen提取新闻中的股票代码
2. 产业链联想（如"英伟达发布新GPU" → "台积电、SK海力士"）
3. 映射到可交易的市场代码（美股、A股等）
```

#### 步骤3：多空逻辑分析
```python
1. DeepSeek分析多头观点：
   - 利好消息是什么？
   - 影响程度多大？
   - 持续时间预期？

2. DeepSeek分析空头观点：
   - 潜在风险是什么？
   - 市场是否已反应？
   - 反向因素有哪些？

3. 历史案例回溯（ChromaDB）：
   - 查找类似历史新闻
   - 当时的市场表现
   - 参考历史胜率
```

#### 步骤4：技术指标验证
```python
1. 获取股票实时数据（yfinance）
2. 计算技术指标：
   - RSI > 70 → 超买，谨慎追高
   - RSI < 30 → 超卖，可能反弹
   - MACD金叉 → 看涨信号
   - MACD死叉 → 看跌信号
   - 价格突破布林带 → 波动加剧

3. 综合判断：
   - 技术面 + 消息面一致性
   - 出现矛盾时降低置信度
```

#### 步骤5：信息差检测
```python
1. Qwen将英文标题翻译为中文关键词
2. SerpApi搜索国内新闻
3. 判断逻辑：
   - 有国内报道 → 市场可能已定价 → 降低优先级
   - 无国内报道 → 确认信息差 → 提高优先级
```

#### 步骤6：置信度评分
```python
置信度 = 基础分(0.5) + 加分项 - 减分项

加分项：
- 信息差确认: +0.15
- 技术面支持: +0.10
- 历史胜率高: +0.10
- 多个LLM一致: +0.10

减分项：
- 技术面背离: -0.10
- 市场已反应: -0.15
- 风险因素多: -0.10

最终阈值：
- 持仓股票: 置信度 ≥ 0.7 → 推送
- 其他股票: 置信度 ≥ 0.8 → 推送
```

#### 步骤7：报告生成与推送
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
- 已持仓股票的信号阈值降低到0.7（更敏感）
- 帮助及时减仓或加仓

#### 冷却机制
- 手动触发：1分钟冷却
- 自动巡逻：45分钟间隔
- 避免过度交易

#### 多模型验证
- 至少2个LLM观点一致才推送
- 降低单一模型幻觉风险

#### 历史学习
- ChromaDB存储历史信号
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
/remove 600519
```

**查看持仓列表**：
```
/list
```

### 2. 自定义概念关联

绑定关键词到股票：
```
/bind AI芯片 600030
/bind 新能源 BYD
```

这样当新闻提到"AI芯片"时，会自动关联到600030。

### 3. 与AI对话

```
/chat deepseek 分析一下英伟达的最新财报
/chat gemini 总结今天的财经新闻
/chat qwen 翻译这段英文新闻
```

### 4. 查看历史信号

访问Dashboard：`http://your-vps-ip:8501`

**新增功能** 🆕：
- **持仓监控**：查看你的持仓股票及其最新AI分析
- **信号历史**：每个股票的历史信号记录
- **回测功能**：运行回测并查看结果
  - `/backtest 30 hold_3_days` - 回测最近30天，持有3天策略
  - 可用策略：hold_3_days, hold_5_days, stop_loss_5, target_profit_10
- **板块热力图**：AI关注的热门概念Top 10
- **多空情绪**：市场整体AI情绪分析
- **置信度分布**：AI决策置信度统计

---

## ⚙️ 配置说明

### 巡逻频率调整

编辑 `src/main.py`:
```python
# 默认45分钟巡逻一次
SCHEDULER_MINUTES = 45  # 可调整为20-120分钟
```

**建议**：
- 频率越高（20分钟）→ 时效性强但成本高
- 频率越低（60分钟）→ 成本低但可能错过机会

### 阈值调整

编辑 `src/llm_analyzer.py`:
```python
threshold_hold = 0.7    # 持仓股票阈值
threshold_normal = 0.8  # 其他股票阈值
```

**建议**：
- 保守策略：提高到 0.85（更少但更准的信号）
- 激进策略：降低到 0.75（更多信号但噪音增加）

### API成本控制

**每月成本估算**（45分钟频率）：
- DeepSeek: ¥15-20
- Qwen (qwen-plus): ¥15-20
- Gemini: ¥5-10
- Kimi (替补): ¥5-10 🆕
- SerpApi: ¥15-20
- **总计: ¥150-300/月**

**省钱技巧**：
1. 延长巡逻间隔到60分钟
2. 关闭SerpApi（不检测信息差）
3. 设置每日API请求限制（DEEPSEEK_DAILY_LIMIT, KIMI_DAILY_LIMIT）🆕
4. 利用Kimi替补机制避免主API超额收费 🆕

---

## 📈 性能优化

### 内存优化（VPS 2.5GB场景）
- ✅ LRU缓存限制（最大1000条）
- ✅ Redis连接复用
- ✅ 数据库连接复用
- ✅ 2GB Swap防止OOM

### CPU优化
- 异步并发处理
- 批量API调用
- 智能去重减少计算

### 网络优化
- 使用洛杉矶VPS（访问美API延迟<50ms）
- HTTP连接复用（aiohttp session）
- 超时控制（15秒）

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

### v1.2.0 (2026-01-07) 🆕
- ✅ **Kimi替补API机制**：Gemini/DeepSeek/Qwen异常时自动切换到Kimi
- ✅ **Dashboard持仓功能**：新增"我的持仓"页面，实时监控持仓股票信号
- ✅ **API状态查询**：新增`/api`命令查看API使用情况
- ✅ **Qwen模型切换**：默认模型改为qwen-plus（环境变量可配置）
- ✅ **批量关键词绑定**：`/bind`命令支持多个关键词和股票
- ✅ **股票名称显示**：持仓页面显示股票名称（如：600276 恒瑞医药）
- ✅ **回测功能**：支持多种回测策略并可视化结果
- ✅ **高可用性**：API异常自动切换并发送Telegram通知
- ✅ **修复多个bug**：空数据处理、缩进错误、KeyError等

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
- **Claude** - 代码开发和优化

特别感谢Gemini在项目初期的大量帮助！

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
