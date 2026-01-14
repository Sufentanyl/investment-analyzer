# AI量化交易助手 - 项目状态摘要

> **最后更新**: 2026-01-14
> **当前分支**: pr-2
> **部署环境**: Unraid Local (192.168.3.110)

---

## 📋 项目与环境

### 基础信息
- **仓库名**: investment-analyzer
- **运行环境**: Unraid (本地) 192.168.3.110
- **部署路径**: /mnt/user/appdata/investment-analyzer
- **运行方式**: Docker Compose
- **服务架构**: 3容器
  - `investment-analyzer` - 主应用容器
  - `investment-dashboard` - Streamlit可视化界面
  - `investment-redis` - Redis缓存服务

### 访问地址
- **Dashboard**: http://192.168.3.110 (端口80)
- **配置文件**: `/app/config.yaml`
- **环境变量**: `.env` (不提交到Git)

---

## 🎯 核心功能模块

### 1. 新闻采集系统 (`news_collector.py`)
**功能**: 国际财经新闻自动收集与去重

**数据源**:
- Bloomberg RSS
- Reuters RSS
- 其他国际财经媒体

**核心特性**:
- ✅ RSS解析使用线程池，避免阻塞
- ✅ newspaper3k 抓取完整正文（带UA和重试）
- ✅ 三重去重机制：
  - URL哈希去重（72小时）
  - 标题归一化去重（36小时）
  - 事件簇签名去重（24小时窗口）
- ✅ 异常处理与超时控制

**可调参数**:
```bash
# 无需调整，自动运行
```

---

### 2. AI分析引擎 (`llm_analyzer.py`)
**功能**: 多模型交叉验证，降低AI幻觉

**LLM分工**:

| 模型 | 角色 | 用途 | 配置环境变量 |
|------|------|------|-------------|
| **DeepSeek** | 主力分析 | 多空观点辩论、逻辑分析 | `DEEPSEEK_API_KEY` |
| **Qwen** | 股票联想 | A股产业链联想、关键词提取 | `QWEN_API_KEY` |
| **Gemini** | 最终报告 | 生成"说人话"的总结报告 | `GEMINI_API_KEY` |
| **Kimi** | 备份替补 | 主力API异常时自动切换 | `KIMI_API_KEY` |

**工作流程**:
```
Buffett (多头) vs Munger (空头) 辩论
    ↓
Judge (裁判) 综合判断
    ↓
技术指标验证 (RSI/MACD/布林带)
    ↓
市场数据增强 (量价验证评分)
    ↓
生成最终报告
```

**核心创新**:
- ✅ **多智能体辩论**: 避免单一模型偏见
- ✅ **量价验证评分**: reaction_score (近1日量价异动)
- ✅ **自动故障切换**: Gemini 429 → Kimi替补 + Telegram通知
- ✅ **历史回测集成**: 技术指标附带历史胜率

**可调参数**:
```bash
# 置信度阈值
CONFIDENCE_THRESHOLD_HOLD=0.65    # 持仓股票阈值
CONFIDENCE_THRESHOLD_NORMAL=0.75  # 其他股票阈值

# Qwen模型切换
QWEN_MODEL=qwen-plus  # 可改为 qwen-max
```

---

### 3. 信息差检测器 (`information_gap_detector.py`)
**功能**: 检测国内新闻覆盖情况，发现信息差套利机会

**检测逻辑**:
1. 提取新闻核心关键词（中文）
2. SerpApi搜索国内新闻
3. 判断覆盖状态：
   - `covered` - 有国内报道
   - `not_covered` - 无国内报道（信息差确认）
   - `unknown` - 检测失败

**核心特性**:
- ✅ 并发限速（最多5个并发）
- ✅ 429/5xx自动重试
- ✅ 异常降级（失败→视为无信息差）
- ✅ 覆盖状态/来源/覆盖数写入news对象
- ✅ 生成gap_confidence（信息差置信度）

**可调参数**:
```bash
GAP_DETECT_CONCURRENCY=5  # 并发数
```

---

### 4. 事件聚类系统 (`database.py` + `main.py`)
**功能**: 同一事件多源聚合，避免重复推送

**工作流程**:
1. 提取新闻标题 → 归一化 → 生成事件签名（MD5）
2. 查询24小时内是否有相同签名
3. 若存在 → 更新事件簇计数 + 冷却
4. 若不存在 → 创建新事件簇

**核心特性**:
- ✅ 事件簇签名生成（去除stopwords）
- ✅ 24小时聚合窗口
- ✅ 6小时冷却机制（避免重复推送）
- ✅ 事件簇数据库存储

**可调参数**:
```bash
CLUSTER_WINDOW_HOURS=24      # 聚合窗口（小时）
CLUSTER_COOLDOWN_HOURS=6     # 冷却时间（小时）
```

---

### 5. 量价验证系统 (`llm_analyzer.py`)
**功能**: 评估市场对新闻的实际反应

**评分逻辑**:
```python
# 量价验证评分 (reaction_score)
vol_ratio = 近1日成交量 / 过去20日平均成交量
price_move = 近1日价格变动幅度

reaction_score = 0.6 * min(vol_ratio/2.0, 1.0) + 0.4 * min(price_move/0.03, 1.0)
```

**应用**:
- ✅ 0.0-1.0评分，越高表示市场反应越强烈
- ✅ 用于二次过滤：低反应 + 低置信度 → 不推送
- ✅ 展示在Dashboard和Telegram报告

---

### 6. 回测引擎 (`backtest.py`)
**功能**: 轻量级历史信号回测

**支持策略**:
- `hold_3_days` - 持有3天
- `hold_5_days` - 持有5天
- `stop_loss_5` - 止损5%
- `target_profit_10` - 止盈10%

**核心特性**:
- ✅ 分批计算，避免内存溢出
- ✅ 线程池异步执行网络请求
- ✅ 生成详细报告：胜率、盈亏比、最大回撤
- ✅ 结果保存到数据库

**使用方法**:
```bash
# Telegram命令
/backtest 30 hold_3_days    # 回测最近30天，持有3天策略
/backtest_7d                # 快速回测7天
/backtest_30d               # 快速回测30天
/backtest_90d               # 快速回测90天
```

---

### 7. 数据库管理器 (`database.py`)
**功能**: SQLite信号存储与优化

**核心特性**:
- ✅ **WAL模式**: 支持并发读写
- ✅ **索引优化**: 8个关键索引，查询速度提升10倍
- ✅ **自动迁移**: 新字段自动添加（ALTER TABLE）
- ✅ **连接复用**: 单例连接，避免频繁开关
- ✅ **数据清理**: prune_old_data(90) 释放空间

**数据库表**:
```sql
signals              -- 交易信号
event_clusters      -- 事件簇
event_memos         -- 事件备忘录
backtest_results    -- 回测结果
```

---

## 📊 Telegram Bot 指令大全

### 🤖 核心命令
| 命令 | 功能 | 说明 |
|------|------|------|
| `/start` | 使用说明书 | 查看所有命令 |
| `/analyze` | 手动巡逻 | 立即触发新闻分析 |
| `/status` | 系统状态 | 查看各模块健康度 |
| `/api` | API使用情况 | 查询Gemini/Qwen/DeepSeek配额 |

### 📊 回测系统
| 命令 | 功能 |
|------|------|
| `/backtest [天数] [策略]` | 自定义回测 |
| `/backtest_7d` | 快速回测7天 |
| `/backtest_30d` | 快速回测30天 |
| `/backtest_90d` | 快速回测90天 |

### 🎮 持仓管理
| 命令 | 功能 |
|------|------|
| `/add <股票代码>` | 添加持仓（降低阈值） |
| `/del <股票代码>` | 删除持仓 |
| `/clear` | 清空所有持仓 |
| `/list` | 查看当前配置 |

### 🔑 关键词管理
| 命令 | 功能 |
|------|------|
| `/import_keywords` | 导入A股核心关键词库 |
| `/bind <关键词> <股票>` | 绑定关键词（支持多个） |
| `/alert_levels <strong,normal,info>` | 设置推送等级过滤 |
| `/autobind_on` | 启用AI自动绑定 |
| `/autobind_off` | 禁用AI自动绑定 |

### 🧠 AI对话
| 命令 | 功能 |
|------|------|
| `/deepseek [问题]` | 问DeepSeek |
| `/gemini [问题]` | 问Gemini |
| `/qwen [问题]` | 问Qwen |

---

## 📈 Dashboard 功能清单

访问地址: http://192.168.3.110

### 页面结构

#### 1️⃣ 我的持仓
- 实时监控持仓股票信号
- 查看历史分析记录
- 股票名称显示（如：600276 恒瑞医药）

#### 2️⃣ 核心情报流
- 所有AI分析信号
- 筛选高胜率机会
- 显示有效置信度、信息差、量价验证

#### 3️⃣ 深度数据分析
- 板块热力图（AI关注热门概念Top 10）
- 置信度分布
- 多空情绪分析

#### 4️⃣ 事件簇视图 🆕
- 事件聚合展示
- 评分指标
- 覆盖状态

#### 5️⃣ 回测结果 🆕
- 历史回测数据
- 策略对比
- 收益曲线

---

## 🔧 系统配置与优化

### 环境变量配置 (.env)

**必需配置**:
```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=你的Bot_Token
TELEGRAM_CHAT_ID=你的Chat_ID

# DeepSeek (主力分析)
DEEPSEEK_API_KEY=你的DeepSeek_Key
DEEPSEEK_DAILY_LIMIT=20

# Qwen (股票联想)
QWEN_API_KEY=你的Qwen_Key
QWEN_MODEL=qwen-plus

# Gemini (最终报告)
GEMINI_API_KEY=key1,key2,key3

# Kimi (替补)
KIMI_API_KEY=你的Kimi_Key
KIMI_DAILY_LIMIT=15

# SerpApi (信息差检测)
SERPAPI_KEY=你的SerpApi_Key

# Streamlit Dashboard
DASHBOARD_PASSWORD=123456

# 服务器标签
SERVER_LABEL=Unraid (Local 192.168.3.110)
```

**可选配置**:
```bash
# 置信度阈值
CONFIDENCE_THRESHOLD_HOLD=0.65
CONFIDENCE_THRESHOLD_NORMAL=0.75

# 事件聚类
CLUSTER_WINDOW_HOURS=24
CLUSTER_COOLDOWN_HOURS=6

# 信息差检测
GAP_DETECT_CONCURRENCY=5

# 推送过滤
INFO_CONFIDENCE_MIN=0.7      # info等级最低置信度
NEUTRAL_CONFIDENCE_MIN=0.7   # neutral信号最低置信度
```

---

## 🛠️ 运维与重启

### 重启服务
```bash
cd /mnt/user/appdata/investment-analyzer

# 重启所有服务
docker compose restart

# 仅重启主应用
docker compose restart investment-analyzer

# 仅重启Dashboard
docker compose restart dashboard
```

### 查看日志
```bash
# 主应用日志
docker logs -f investment-analyzer --tail 100

# Dashboard日志
docker logs -f investment-dashboard --tail 100

# Redis日志
docker logs -f investment-redis
```

### 数据备份
```bash
# 备份数据库
cp ./data/investment.db ./data/backup/investment_$(date +%Y%m%d).db

# 备份配置
cp ./config.yaml ./data/backup/config_$(date +%Y%m%d).yaml
```

---

## 🐛 常见问题与解决方案

### 1. API配额用尽
**现象**: `/api` 显示配额用尽
**原因**: Gemini免费版每日限制
**解决**:
- 等待太平洋时间午夜重置
- 或自动切换到Kimi替补
- 收到Telegram通知

### 2. 新闻不去重
**现象**: 收到重复新闻推送
**原因**: Redis连接失败
**解决**:
```bash
docker exec investment-redis redis-cli FLUSHDB
docker compose restart investment-analyzer
```

### 3. Dashboard无法访问
**现象**: http://192.168.3.110 打不开
**原因**: 端口冲突或容器未启动
**解决**:
```bash
docker ps | grep investment-dashboard
docker logs investment-dashboard
```

### 4. 回测失败
**现象**: `/backtest` 返回错误
**原因**: 历史信号不足或yfinance超时
**解决**:
- 先运行一周收集信号
- 或使用 `/backtest_90d` 增加时间范围

---

## 📊 最近完成的关键改动

### v1.2.1 (2026-01-09) 🆕

#### 采集与去重优化
- ✅ RSS解析移至线程池
- ✅ SerpApi复用session
- ✅ 抓取正文加UA/重试
- ✅ 时间排序
- ✅ 去重使用hash
- ✅ 并发限制抓取正文

#### 事件级聚类
- ✅ URL + 标题双重去重
- ✅ Redis标题去重（36小时）
- ✅ 事件簇签名与冷却
- ✅ 避免重复推送

#### 信息差与评分
- ✅ SerpApi并发限速
- ✅ 429/5xx自动重试
- ✅ 覆盖状态/来源/覆盖数写入news
- ✅ gap_confidence生成
- ✅ 异常降级为无信息差

#### 量价验证
- ✅ enrich_market_data增加reaction_score（近1日量价）
- ✅ validation_score计算
- ✅ 保存到分析结果

#### 数据库优化
- ✅ signals增加字段：confidence_effective, event_cluster_id, event_signature, gap_confidence, validation_score, coverage_status
- ✅ 新增event_clusters表
- ✅ event_memos增加event_cluster_id, event_signature
- ✅ 新增get_or_create_event_cluster与update_signals_by_news_title

#### 报告增强
- ✅ Telegram文案新增事件簇ID、验证分、信息差信心、有效置信度
- ✅ Dashboard事件簇标签页

### v1.2.0 (2026-01-07)

#### API高可用性
- ✅ Kimi替补API机制
- ✅ Gemini/DeepSeek/Qwen异常时自动切换
- ✅ Telegram通知API切换

#### Dashboard升级
- ✅ 新增"我的持仓"页面
- ✅ 股票名称显示
- ✅ 回测功能可视化

#### 功能增强
- ✅ `/api`命令查看API使用情况
- ✅ Qwen模型可配置（qwen-plus/qwen-max）
- ✅ 批量关键词绑定

---

## 🚀 性能优化总结

### 内存优化（VPS 2.5GB场景）
- ✅ LRU缓存限制（最大1000条）
- ✅ SQLite WAL模式 + 连接复用
- ✅ Redis连接复用
- ✅ 回测分批计算（每批20条）

### CPU优化
- ✅ 异步并发处理
- ✅ 线程池执行网络请求
- ✅ 批量API调用

### 网络优化
- ✅ aiohttp session复用
- ✅ 超时控制（15-30秒）
- ✅ 并发限速

---

## 📝 待办/可选后续

### 短期优化
- [ ] 事件聚类相似度升级（embedding聚类）
- [ ] 信息差评分模型化与A/B日志
- [ ] 量价验证使用分钟级数据源

### 中期规划
- [ ] WebSocket实时行情推送
- [ ] 多语言支持（英文/繁体中文）
- [ ] 自定义策略编辑器

### 长期愿景
- [ ] Prometheus + Grafana监控
- [ ] 分布式部署支持
- [ ] 机器学习模型训练

---

## 📞 技术支持

**作者**: Sufentanyl
**GitHub**: https://github.com/Sufentanyl/investment-analyzer
**问题反馈**: 提交Issue

---

**免责声明**: 本系统仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。
