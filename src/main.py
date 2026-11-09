import logging
import asyncio
import os
import json
import hashlib
import pytz
import time
import aiohttp
import re
from telegram import Bot, Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, ApplicationBuilder
from telegram.request import HTTPXRequest
from datetime import datetime, timedelta
import redis
import holidays
from logging.handlers import TimedRotatingFileHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# 引入自定义模块
from llm_analyzer import LLMAnalyzer
from news_collector import AdvancedNewsCollector
from information_gap_detector import InformationGapDetector
from futures_watcher import FuturesWatcher
from backtest import LightweightBacktester
from notifier import UnifiedNotifier

# 配置日志 (兼容容器内 /app/logs 与本地 ./logs)
_log_dir = '/app/logs' if (os.path.exists('/app/logs') or os.access('/app', os.W_OK)) else os.path.join(os.getcwd(), 'logs')
os.makedirs(_log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    handlers=[
        logging.StreamHandler(), 
        TimedRotatingFileHandler(os.path.join(_log_dir, 'app.log'), when='midnight', backupCount=7, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 🔥 全局标志：防止重复发送启动通知
_startup_notification_sent = False

# 🔥 死前遗言发送函数 (支持 Bark / Webhook / Telegram)
async def send_death_notification(token, chat_id, error_msg):
    try:
        notifier = UnifiedNotifier()
        await notifier.send(
            f"☠️ **严重警告**：系统崩溃已停止运行！\n\n错误信息：{error_msg}",
            title="☠️ A股量化系统严重告警",
            level="critical",
        )
    except Exception as e:
        logger.error(f"发送死亡通知失败: {e}") 

class AdvancedInvestmentAnalyzer:
    def __init__(self):
        token = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
        disable_tg = os.getenv('DISABLE_TELEGRAM', '0') == '1'
        self.chat_id = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
        self.notifier = UnifiedNotifier()

        if token and token != "your_telegram_bot_token_here" and not disable_tg:
            t_request = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
            self.telegram_bot = Bot(token=token, request=t_request)
        else:
            self.telegram_bot = None
        
        self.news_collector = AdvancedNewsCollector()
        self.llm_analyzer = LLMAnalyzer()
        self.llm_analyzer.set_telegram_bot(self.telegram_bot, self.chat_id)
        self.gap_detector = InformationGapDetector()
        self.futures_watcher = FuturesWatcher()
        self.backtester = LightweightBacktester()  # 回测引擎
        
        self.redis_client = None
        self._connect_redis()
        
        self.cn_holidays = holidays.CN()
        self.last_manual_analysis = None

    async def _notify_text(
        self,
        text: str,
        chat_id=None,
        title: str = None,
        subtitle: str = None,
        level: str = None,
        click_url: str = None,
        parse_mode=None,
    ):
        """统一发送通知：优先推送至 Bark (iOS) / Webhook，若启用了 Telegram 则同步发送"""
        await self.notifier.send(
            text=text,
            title=title,
            subtitle=subtitle,
            level=level,
            click_url=click_url,
        )
        target_chat_id = chat_id or self.chat_id
        if self.telegram_bot and target_chat_id:
            try:
                await self.telegram_bot.send_message(
                    chat_id=target_chat_id,
                    text=text,
                    parse_mode=parse_mode,
                )
            except Exception:
                try:
                    await self.telegram_bot.send_message(chat_id=target_chat_id, text=text)
                except Exception as e2:
                    logger.debug(f"Telegram 附加发送失败: {e2}")

    def _connect_redis(self):
        try:
            redis_host = os.getenv('REDIS_HOST', '127.0.0.1')
            self.redis_client = redis.Redis(host=redis_host, port=6379, decode_responses=True)
            self.redis_client.ping()
            logger.info("✅ Redis 连接成功")
        except Exception as e:
            logger.error(f"❌ Redis 连接失败: {e}")
            self.redis_client = None

    def is_news_processed(self, news_url: str) -> bool:
        if not self.redis_client: return False
        news_id = f"processed_news:{hashlib.md5(news_url.encode()).hexdigest()}"
        return self.redis_client.exists(news_id)

    def mark_news_as_processed(self, news_url: str):
        if not self.redis_client: return
        news_id = f"processed_news:{hashlib.md5(news_url.encode()).hexdigest()}"
        self.redis_client.setex(news_id, 259200, "1")

    def is_cluster_processed(self, cluster_id: int) -> bool:
        if not self.redis_client or not cluster_id:
            return False
        cluster_key = f"processed_cluster:{cluster_id}"
        return self.redis_client.exists(cluster_key)

    def mark_cluster_as_processed(self, cluster_id: int):
        if not self.redis_client or not cluster_id:
            return
        cooldown_hours = int(os.getenv("CLUSTER_COOLDOWN_HOURS", "6"))
        cluster_key = f"processed_cluster:{cluster_id}"
        self.redis_client.setex(cluster_key, cooldown_hours * 3600, "1")

    def _normalize_title(self, title: str) -> str:
        if not title:
            return ""
        text = title.lower()
        text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
        text = re.sub(r"\b(update|breaking|exclusive|analysis)\b", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _build_event_signature(self, title: str) -> str:
        normalized = self._normalize_title(title)
        tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", normalized)
        stopwords = {
            "the", "and", "for", "with", "from", "this", "that", "into", "over", "after",
            "china", "chinese", "global", "market", "markets", "stocks", "stock", "news",
            "report", "reports", "say", "says", "saying", "update",
        }
        filtered = [t for t in tokens if t not in stopwords and len(t) > 1]
        key_tokens = filtered[:6]
        signature_raw = " ".join(key_tokens) if key_tokens else normalized
        return hashlib.md5(signature_raw.encode()).hexdigest()

    def is_title_processed(self, title: str) -> bool:
        if not self.redis_client:
            return False
        normalized = self._normalize_title(title)
        if not normalized:
            return False
        title_id = f"processed_title:{hashlib.md5(normalized.encode()).hexdigest()}"
        return self.redis_client.exists(title_id)

    def mark_title_as_processed(self, title: str):
        if not self.redis_client:
            return
        normalized = self._normalize_title(title)
        if not normalized:
            return
        title_id = f"processed_title:{hashlib.md5(normalized.encode()).hexdigest()}"
        self.redis_client.setex(title_id, 129600, "1")

    async def run_analysis(self, update: Update = None, context: ContextTypes.DEFAULT_TYPE = None, is_manual: bool = False):
        try:
            chat_id = update.effective_chat.id if update else self.chat_id
            # 每次巡检前同步读取 Web 控制台最新保存的持仓与推送配置
            self.llm_analyzer.reload_config()

            # 🔥 修复: 统一使用上海时区
            tz = pytz.timezone('Asia/Shanghai')
            now = datetime.now(tz)

            if is_manual and self.last_manual_analysis and now - self.last_manual_analysis < timedelta(minutes=1):
                await self._notify_text("⏳ 冷却中...请稍候再试", chat_id=chat_id, title="⏳ 巡逻冷却中")
                return []

            if is_manual:
                self.last_manual_analysis = now
                if self.telegram_bot and chat_id:
                    await self.telegram_bot.send_message(chat_id=chat_id, text="🚀 正在巡逻最新新闻...")

            news_list = await self.news_collector.collect_international_news()
            if not news_list:
                if is_manual:
                    await self._notify_text("📊 暂无新内容", chat_id=chat_id, title="📊 巡逻完成")
                return []

            # 🔥 双重去重逻辑 (URL + 标题)
            new_news_items = []
            seen_urls = set()   
            seen_titles = set() 

            for news in news_list:
                url = news['url']
                title = news.get('title', '').strip()

                if self.is_news_processed(url): continue
                if title and self.is_title_processed(title): continue
                if url in seen_urls: continue
                if title and title in seen_titles: continue

                if title:
                    signature = self._build_event_signature(title)
                    window_hours = int(os.getenv("CLUSTER_WINDOW_HOURS", "24"))
                    cluster_id, _ = self.llm_analyzer.db.get_or_create_event_cluster(signature, title, window_hours=window_hours)
                    news['_event_signature'] = signature
                    news['_cluster_id'] = cluster_id
                    if cluster_id and self.is_cluster_processed(cluster_id):
                        continue
                
                new_news_items.append(news)
                seen_urls.add(url)
                if title: seen_titles.add(title)

            if not new_news_items:
                if is_manual:
                    await self._notify_text("✅ 所有新闻都已分析过。", chat_id=chat_id, title="✅ 巡逻完成")
                return []

            logger.info(f"🔍 发现 {len(new_news_items)} 条新新闻，准备分析...")

            potentially_valuable_news = []
            for news in new_news_items:
                self.mark_news_as_processed(news['url']) 
                if news.get('title'):
                    self.mark_title_as_processed(news['title'])
                if news.get('_cluster_id'):
                    self.mark_cluster_as_processed(news['_cluster_id'])
                
                res = await self.llm_analyzer.analyze_cross_validate(news['title'], news.get('content', ''))
                if not res:
                    continue

                allowed_levels = set(self.llm_analyzer.config.get('alert_levels_to_push', ['strong', 'normal']))
                alert_level = res.get('event_memo', {}).get('alert_level', 'info')
                if alert_level not in allowed_levels:
                    info_min = float(os.getenv("INFO_CONFIDENCE_MIN", "0.7"))
                    confidence = res.get('confidence', 0)
                    allow_info = alert_level == "info" and confidence >= info_min
                    if not allow_info:
                        logger.info(f"INFO level filtered: {alert_level} | {news['title']}")
                        continue

                influence = res.get('stock_market_influence', 'neutral')
                confidence = res.get('confidence', 0)
                neutral_min = float(os.getenv("NEUTRAL_CONFIDENCE_MIN", "0.7"))
                if influence != 'neutral' or confidence >= neutral_min:
                    news['_analysis_result'] = res
                    potentially_valuable_news.append(news)
                else:
                    logger.info(f"Neutral filtered: {influence} | {news['title']}")

            if not potentially_valuable_news:
                if is_manual:
                    await self._notify_text("⚖️ 本轮新闻经 AI 研判无重大影响。", chat_id=chat_id, title="⚖️ 巡逻完成")
                return []

            logger.info(f"💎 筛选出 {len(potentially_valuable_news)} 条高价值新闻，检测信息差...")
            gap_news = await self.gap_detector.detect_information_gap(potentially_valuable_news)
            
            if not gap_news:
                if is_manual:
                    await self._notify_text("🔍 高价值新闻国内均已有报道。", chat_id=chat_id, title="🔍 巡逻完成")
                return []

            final_results = []
            for news in gap_news:
                res = news.get('_analysis_result')
                if not res:
                    continue

                base_conf = res.get('confidence', 0)
                gap_conf = news.get('gap_confidence', 0.5)
                validation_score = res.get('validation_score', 0)

                confidence_effective = base_conf + (gap_conf - 0.5) * 0.2 + (validation_score - 0.5) * 0.2
                confidence_effective = max(0.0, min(1.0, confidence_effective))

                res['confidence_effective'] = confidence_effective
                res['gap_confidence'] = gap_conf
                res['coverage_status'] = news.get('coverage_status', 'unknown')
                res['event_cluster_id'] = news.get('_cluster_id')
                res['event_signature'] = news.get('_event_signature')
                res['validation_score'] = validation_score

                # 从配置读取阈值
                threshold = self.llm_analyzer.threshold_normal
                if res.get('stock_data'):
                    for s in res['stock_data']:
                        if s.get('is_hold'): 
                            threshold = self.llm_analyzer.threshold_hold
                            break

                self.llm_analyzer.db.update_signals_by_news_title(
                    news.get('title'),
                    confidence_effective=confidence_effective,
                    event_cluster_id=res.get('event_cluster_id'),
                    event_signature=res.get('event_signature'),
                    gap_confidence=gap_conf,
                    validation_score=validation_score,
                    coverage_status=res.get('coverage_status'),
                )

                if confidence_effective >= threshold:
                    final_results.append((news, res))
                else:
                    logger.info(f"🗑️ 二次过滤: 价值低 ({confidence_effective:.2f})")

            if final_results:
                await self.send_report(final_results, chat_id)
            elif is_manual:
                await self._notify_text(
                    "🤷‍♂️ 本次巡逻未发现高价值投资机会\n\n所有新闻的AI评估置信度均低于阈值，暂不推荐。",
                    chat_id=chat_id,
                    title="🤷‍♂️ 未发现高确定性机会",
                )
            return final_results

        except Exception as e:
            logger.error(f"流程出错: {e}", exc_info=True)
            if is_manual:
                await self._notify_text(f"❌ 运行出错: {str(e)}", chat_id=chat_id, title="❌ 巡逻运行异常")
            return []

    # 🔥🔥 多通道战报推送逻辑 (Bark iOS + Webhook + 可选 Telegram) 🔥🔥
    async def send_report(self, results, chat_id=None):
        for i, (news, analysis) in enumerate(results, 1):
            processing_msg = None
            if self.telegram_bot and chat_id:
                try:
                    processing_msg = await self.telegram_bot.send_message(
                        chat_id=chat_id,
                        text=f"🤔 正在邀请 Gemini 首席审阅: {news['title'][:20]}..."
                    )
                except Exception as e:
                    logger.warning(f"发送处理消息失败: {e}")

            final_report = await self.llm_analyzer.generate_gemini_review(news['title'], analysis)
            
            icon = "🚨"
            if analysis.get('stock_market_influence') == 'positive': icon = "🔥"
            elif analysis.get('stock_market_influence') == 'negative': icon = "🔻"
            
            concept_str = analysis.get('concept', '热点事件')
            event_memo = analysis.get('event_memo', {})
            template_info = analysis.get('event_template', {})
            event_cluster_id = analysis.get('event_cluster_id')
            event_signature = analysis.get('event_signature')

            if event_memo:
                try:
                    event_memo['event_cluster_id'] = event_cluster_id
                    event_memo['event_signature'] = event_signature
                    self.llm_analyzer.db.save_event_memo(
                        news_title=news['title'],
                        template_label=template_info.get('label'),
                        sectors=event_memo.get('sectors'),
                        memo=event_memo,
                    )
                except Exception as e:
                    logger.warning(f"保存事件模板失败: {e}")

            # 🔥 AI自动绑定关键词（可开关）
            if self.llm_analyzer.config.get('auto_bind_keywords', True):
                if analysis.get('stock_data'):
                    for stock in analysis['stock_data']:
                        stock_code = stock.get('code', '')
                        if stock_code and concept_str:
                            keywords = [k.strip() for k in concept_str.split(',') if k.strip()]
                            self.llm_analyzer.auto_bind_keywords(keywords, stock_code)

            alert_keywords = event_memo.get('alert_keywords', '') if isinstance(event_memo, dict) else ''

            # 量化评分与实战点位卡片
            confidence_effective = analysis.get('confidence_effective', 0)
            gap_confidence = analysis.get('gap_confidence', 0.5)
            validation_score = analysis.get('validation_score', 0)
            quant_info = (
                f"\n📊 **有效置信度**: `{confidence_effective:.2f}` | "
                f"💎 **预期差**: `{gap_confidence:.2f}` | "
                f"📈 **量价共振**: `{validation_score:.2f}`\n"
            )

            stock_trade_lines = []
            subtitle_stocks = []
            has_hold = False
            if analysis.get('stock_data'):
                for s in analysis['stock_data'][:3]:
                    if s.get('is_hold'):
                        has_hold = True
                    hold_badge = " `[持仓]`" if s.get('is_hold') else ""
                    subtitle_stocks.append(f"{s.get('name', '')}({s.get('code', '')})")
                    stock_trade_lines.append(
                        f"• **{s.get('name', '')}({s.get('code', '')})**{hold_badge}: "
                        f"现价 `{s.get('price', '')}` | 低吸 `{s.get('buy_zone', 'N/A')}` | 止损 `{s.get('stop_loss_price', 'N/A')}`"
                    )
            stock_trade_block = ("\n🎯 **实战点位参考**:\n" + "\n".join(stock_trade_lines) + "\n") if stock_trade_lines else ""

            alert_keywords_str = ""
            if alert_keywords:
                alert_keywords_str = f"\n🔔 **命中关键词**: {alert_keywords}"

            full_msg = (
                f"{icon} **{news['title']}**\n\n"
                f"{final_report}\n"
                f"{stock_trade_block}"
                f"{quant_info}"
                f"{alert_keywords_str}\n"
                f"⏱️ {datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%H:%M')}"
            )

            # 1. 发送至 Bark (iOS) / Webhook
            bark_title = f"{icon} {'[持仓告警] ' if has_hold else ''}{news['title'][:36]}"
            bark_subtitle = f"板块: {concept_str} | 标的: {', '.join(subtitle_stocks)}" if subtitle_stocks else f"板块: {concept_str} | 置信度 {confidence_effective:.0%}"
            bark_level = "timeSensitive" if (has_hold or confidence_effective >= 0.78) else "active"
            await self.notifier.send(
                text=full_msg,
                title=bark_title,
                subtitle=bark_subtitle,
                level=bark_level,
                click_url=news.get('url'),
            )

            # 2. 若启用了 Telegram，发送图文卡片
            if processing_msg and self.telegram_bot and chat_id:
                try:
                    await self.telegram_bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
                except Exception as e:
                    logger.warning(f"删除处理消息失败: {e}")

            if self.telegram_bot and chat_id:
                chart_to_send = None
                if analysis.get('stock_data'):
                    for stock in analysis['stock_data']:
                        if stock.get('chart'):
                            chart_to_send = stock['chart']
                            break
                try:
                    if chart_to_send:
                        chart_to_send.seek(0)
                        await self.telegram_bot.send_photo(
                            chat_id=chat_id,
                            photo=chart_to_send,
                            caption=full_msg,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    else:
                        await self.telegram_bot.send_message(chat_id=chat_id, text=full_msg, parse_mode=ParseMode.MARKDOWN)
                except Exception as e:
                    logger.error(f"Telegram 发送失败: {e}")
                    try:
                        await self.telegram_bot.send_message(chat_id=chat_id, text=full_msg)
                    except Exception:
                        pass

    async def report_futures(self):
        try:
            data = await asyncio.to_thread(self.futures_watcher.get_iron_ore_data)
            await self._notify_text(
                f"🌅 **早盘期货哨兵**\n{data}",
                chat_id=self.chat_id,
                title="🌅 早盘期货哨兵",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error(f"期货播报错误: {e}")

    def start_scheduler(self):
        scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Shanghai'))
        # 每 15 分钟双轨巡检（本土 7x24 快讯 + 海外映射）
        scheduler.add_job(self.run_analysis, trigger=IntervalTrigger(minutes=15), id='interval_monitor', max_instances=1)
        # 每个交易日早盘集合竞价前 08:45 触发隔夜海外映射巡检
        scheduler.add_job(self.run_analysis, trigger=CronTrigger(day_of_week='mon-fri', hour=8, minute=45), id='pre_market_morning_patrol', max_instances=1)
        scheduler.add_job(self.report_futures, trigger=CronTrigger(day_of_week='mon-fri', hour=9, minute=15), id='futures_morning_report')
        # 每天10点和15点分析持仓股票走势
        scheduler.add_job(self.analyze_holdings, trigger=CronTrigger(day_of_week='mon-fri', hour='10,15', minute=0), id='holdings_monitor', max_instances=1)
        scheduler.start()

    async def analyze_holdings(self, update: Update = None, context: ContextTypes.DEFAULT_TYPE = None, is_manual: bool = False):
        """📊 分析持仓股票走势"""
        try:
            chat_id = update.effective_chat.id if update else self.chat_id
            self.llm_analyzer.reload_config()

            if is_manual and self.telegram_bot and chat_id:
                await self.telegram_bot.send_message(chat_id=chat_id, text="📊 正在分析持仓股票走势...")

            # 获取持仓列表
            my_positions = self.llm_analyzer.config.get('my_positions', [])

            if not my_positions:
                if is_manual:
                    await self._notify_text("📭 暂无持仓股票，请先在 Web 控制台添加持仓", chat_id=chat_id, title="📭 暂无持仓")
                return []

            # 调用分析
            results = await self.llm_analyzer.analyze_holdings_trend(my_positions)

            if not results:
                if is_manual:
                    await self._notify_text("❌ 持仓股票分析失败，请查看日志", chat_id=chat_id, title="❌ 持仓分析失败")
                return []

            # 构建报告
            report_lines = ["📊 **持仓股票走势分析**\n"]

            for r in results:
                code = r['code']
                name = r.get('name', code)
                trend = r['trend']
                price = r['current_price']
                
                action = r.get('action', '观望')
                reason = r.get('reason', '暂无分析')
                safe_range = r.get('safe_range', 'N/A')
                risk_alert = r.get('risk_alert', 'N/A')
                support = r.get('support', 'N/A')
                resistance = r.get('resistance', 'N/A')
                pattern = r.get('pattern', 'N/A')

                trend_icons = {'上涨': '📈', '下跌': '📉', '震荡': '〰️'}
                icon = trend_icons.get(trend, '❓')

                report_lines.append(f"{icon} **{name}({code}) {action}** | {trend}")
                report_lines.append(f"   💡 **建议**: {reason}")
                report_lines.append(f"   🛡️ **安全**: {safe_range} | ⚠️ **警惕**: {risk_alert}")
                report_lines.append(f"   📐 **点位**: 支撑{support} | 压力{resistance}")
                if pattern != 'N/A':
                    report_lines.append(f"   🧠 **形态**: {pattern}")
                report_lines.append(f"   💰 **现价**: {price:.2f}")
                report_lines.append("")

            full_msg = "\n".join(report_lines)

            await self._notify_text(
                full_msg,
                chat_id=chat_id,
                title=f"📊 持仓走势会诊 ({len(results)}只)",
                level="timeSensitive",
                parse_mode=ParseMode.MARKDOWN,
            )

            logger.info(f"✅ 持仓分析完成，分析 {len(results)} 只股票")
            return results

        except Exception as e:
            logger.error(f"持仓分析任务失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    async def chat_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ 请在指令后输入内容。")
            return
        model_name = update.effective_message.text.split()[0][1:].lower()
        user_text = " ".join(context.args)
        msg = await update.message.reply_text(f"⏳ {model_name} 正在思考...")
        response = await self.llm_analyzer.chat_with_model(model_name, user_text)
        try:
            await msg.edit_text(f"🤖 **{model_name.upper()} 回复:**\n\n{response}", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"Markdown 解析失败，使用纯文本: {e}")
            await msg.edit_text(f"🤖 **{model_name.upper()} 回复:**\n\n{response}")

    async def backtest_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, days=None, strategy=None):
        """处理回测命令 (修复命令行参数覆盖逻辑 + 展示 A 股 T+1 仿真详情)"""
        try:
            # 优先解析命令行参数（仅在未通过快捷指令固定传入时覆盖）
            if context and getattr(context, 'args', None):
                for arg in context.args:
                    if arg.isdigit() and days is None:
                        days = int(arg)
                    elif arg in ['hold_3_days', 'hold_5_days', 'stop_loss_5', 'target_profit_10'] and strategy is None:
                        strategy = arg

            if days is None:
                days = 30
            if strategy is None:
                strategy = 'hold_3_days'

            msg = await update.message.reply_text(
                f"🔬 **开始 A 股 T+1 仿真回测**\n\n"
                f"📅 时间范围: 最近 {days} 天\n"
                f"📊 策略: `{strategy}` (含次日开盘滑点 + T+1锁仓 + 涨跌停校验)\n\n"
                f"⏳ 正在通过东方财富高速行情计算，请稍候...",
                parse_mode=ParseMode.MARKDOWN
            )

            result = await self.backtester.run_backtest(days=days, strategy=strategy)

            if 'error' in result:
                await msg.edit_text(f"❌ 回测失败: {result['error']}")
                return

            by_type = result.get('by_signal_type', {})
            bull_info = by_type.get('positive', {})
            bear_info = by_type.get('negative', {})
            type_lines = ""
            if bull_info:
                type_lines += f"🚀 看多信号(做多): {bull_info.get('total', 0)}笔 | 胜率 {bull_info.get('win_rate', 0):.1f}% | 均益 {bull_info.get('avg_pct', 0):+.2f}%\n"
            if bear_info:
                type_lines += f"🔻 看空信号(避雷): {bear_info.get('total', 0)}笔 | 避雷率 {bear_info.get('win_rate', 0):.1f}% | 规避 {bear_info.get('avg_pct', 0):+.2f}%\n"

            report = f"""📊 **A 股 T+1 仿真回测报告**

📅 回测时间: {result['backtest_date']}
📈 策略: `{result['strategy']}`

━━━━━━━━━━━━━━━
📊 **核心指标 (已扣除滑点与一字板)**
━━━━━━━━━━━━━━━
✅ 有效成交信号: {result['total_signals']} 笔
⛔ 涨停排队未成交: {result.get('untradable_count', 0)} 笔
🎯 综合胜率: {result['win_rate']:.1f}%
💰 盈亏比: {result['profit_loss_ratio']:.2f}
📉 单笔最大回撤: {result['max_drawdown']:.2f}%
📈 累计收益: {result['total_profit']:.2f}%

━━━━━━━━━━━━━━━
🎲 **详细统计**
━━━━━━━━━━━━━━━
✅ 盈利/有效笔数: {result['win_count']}
❌ 亏损/失效笔数: {result['lose_count']}
📊 平均盈利: {result['avg_profit']:.2f}%
📊 平均亏损: {result['avg_loss']:.2f}%
{type_lines}
━━━━━━━━━━━━━━━
💡 **建议**
━━━━━━━━━━━━━━━
"""

            if result['win_rate'] >= 60:
                report += "✅ 胜率优秀，策略在 A 股 T+1 下表现稳健！"
            elif result['win_rate'] >= 45:
                report += "⚠️ 胜率一般，建议结合乖离率进一步严控追高。"
            else:
                report += "❌ 胜率偏低，建议提高置信度阈值或缩短持仓周期。"

            if result['profit_loss_ratio'] >= 1.5:
                report += "\n✅ 盈亏比健康，风险收益结构良好。"
            elif result['profit_loss_ratio'] >= 1.0:
                report += "\n⚠️ 盈亏比一般，注意严格执行止损位。"
            else:
                report += "\n❌ 盈亏比过低，谨防高开低走兑现行情。"

            await msg.edit_text(report, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"回测命令执行失败: {e}")
            await update.message.reply_text(f"❌ 回测失败: {str(e)}")

    async def clear_positions_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理清空持仓命令"""
        config = self.llm_analyzer.config

        if not config['my_positions']:
            await update.message.reply_text("⚠️ 持仓列表已经是空的")
            return

        cleared_positions = ", ".join(config['my_positions'])
        config['my_positions'] = []
        self.llm_analyzer.save_config()

        await update.message.reply_text(
            f"🗑️ 已清空持仓列表：{cleared_positions}\n\n"
            f"💡 现在可以添加A股代码了\n"
            f"例如：`/add 600519`（贵州茅台）",
            parse_mode=ParseMode.MARKDOWN
        )

    async def autobind_on_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理启用AI自动绑定"""
        config = self.llm_analyzer.config
        config['auto_bind_keywords'] = True
        self.llm_analyzer.save_config()
        await update.message.reply_text(
            "✅ **AI自动绑定关键词已启用**\n\n"
            "🔗 现在AI分析新闻时会自动将概念关键词关联到股票\n"
            "例如：看到'AI芯片'会自动关联到相关股票\n\n"
            "💡 使用 `/list` 查看所有关键词绑定",
            parse_mode=ParseMode.MARKDOWN
        )

    async def autobind_off_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理禁用AI自动绑定"""
        config = self.llm_analyzer.config
        config['auto_bind_keywords'] = False
        self.llm_analyzer.save_config()
        await update.message.reply_text(
            "❌ **AI自动绑定关键词已禁用**\n\n"
            "💡 你仍然可以手动使用 `/bind 关键词 股票代码` 来绑定\n"
            "💡 使用 `/autobind_on` 重新启用",
            parse_mode=ParseMode.MARKDOWN
        )

    async def check_api_usage_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """检查API使用情况 (DeepSeek / OpenAI-GPT / Gemini / Kimi / Qwen)"""
        await update.message.reply_text("🔍 正在查询多模型 API 状态...", parse_mode=ParseMode.MARKDOWN)

        gemini_keys = self.llm_analyzer.gemini_keys[:5]
        openai_key = self.llm_analyzer.openai_key
        deepseek_key = self.llm_analyzer.deepseek_key
        kimi_key = self.llm_analyzer.kimi_key
        qwen_key = self.llm_analyzer.qwen_key

        tz = pytz.timezone('Asia/Shanghai')
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

        msg = f"📊 **多模型路由器 API 状态 (v2.0)**\n\n"
        msg += f"⏰ 查询时间: {now}\n\n"

        # 1. 检查 DeepSeek
        msg += "🔮 **DeepSeek API (主力推理)**\n"
        if deepseek_key:
            try:
                url = f"{self.llm_analyzer.deepseek_base.rstrip('/')}/chat/completions"
                headers = {"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"}
                payload = {
                    "model": self.llm_analyzer.deepseek_model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers, timeout=6) as resp:
                        if resp.status == 200:
                            msg += "✅ 正常工作\n"
                        elif resp.status == 429:
                            msg += "⚠️ 配额/并发受限 (HTTP 429)\n"
                        else:
                            msg += f"❌ HTTP {resp.status}\n"
            except Exception as e:
                msg += f"❌ 错误: {str(e)[:40]}\n"
        else:
            msg += "⚪ 未配置\n"

        # 2. 检查 OpenAI / GPT
        msg += f"\n🧠 **OpenAI / GPT API ({self.llm_analyzer.openai_model})**\n"
        if openai_key:
            try:
                url = f"{self.llm_analyzer.openai_base.rstrip('/')}/chat/completions"
                headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
                payload = {
                    "model": self.llm_analyzer.openai_model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers, timeout=6) as resp:
                        if resp.status == 200:
                            msg += "✅ 正常工作\n"
                        elif resp.status == 429:
                            msg += "⚠️ 配额受限 (HTTP 429)\n"
                        else:
                            msg += f"❌ HTTP {resp.status}\n"
            except Exception as e:
                msg += f"❌ 错误: {str(e)[:40]}\n"
        else:
            msg += "⚪ 未配置\n"

        # 3. 检查 Gemini
        msg += "\n🤖 **Gemini API (研报审阅 & 联网)**\n"
        if gemini_keys:
            gemini_working = 0
            for key in gemini_keys:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=5) as resp:
                            if resp.status == 200:
                                gemini_working += 1
                except Exception:
                    pass
            if gemini_working > 0:
                msg += f"✅ 可用: {gemini_working}/{len(gemini_keys)} Keys\n"
            else:
                msg += "❌ 所有 Keys 配额用尽或不可达\n"
        else:
            msg += "⚪ 未配置\n"

        # 4. 检查 Kimi
        msg += "\n🛰️ **Kimi API (高速替补)**\n"
        if kimi_key:
            msg += "✅ 已配置就绪\n"
        else:
            msg += "⚪ 未配置\n"

        # 5. 检查 Qwen (可选)
        if qwen_key:
            msg += "\n🌐 **Qwen API (可选扩展)**: ✅ 已配置\n"

        msg += "\n💡 **路由策略**: DeepSeek ↔ GPT ↔ Gemini ↔ Kimi 全链路自动故障切换"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)



# ================= 指令函数 =================

async def add_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = context.args[0] if context.args else ""
    if not code:
        await update.message.reply_text("❌ 用法: `/add 股票代码`")
        return
    if context.bot_data['analyzer'].llm_analyzer.add_position(code):
        await update.message.reply_text(f"✅ 已添加持仓监控: {code}")
    else:
        await update.message.reply_text(f"⚠️ {code} 已存在")

async def del_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = context.args[0] if context.args else ""
    if not code:
        await update.message.reply_text("❌ 用法: `/del 股票代码`")
        return
    if context.bot_data['analyzer'].llm_analyzer.remove_position(code):
        await update.message.reply_text(f"🗑️ 已移除持仓: {code}")
    else:
        await update.message.reply_text(f"⚠️ {code} 不在列表中")

async def list_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = context.bot_data['analyzer'].llm_analyzer.config
    positions = ", ".join(config['my_positions']) if config['my_positions'] else "（空）"
    keywords = ", ".join(list(config['concept_db'].keys())[:10]) if config['concept_db'] else "（空）"
    alert_levels = ", ".join(config.get('alert_levels_to_push', ['strong', 'normal']))
    msg = (
        f"📋 **当前配置**\n\n"
        f"🏦 **持仓监控**: {positions}\n\n"
        f"🔑 **关键词库**: {keywords}\n\n"
        f"🔔 **推送等级**: {alert_levels}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def bind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """绑定关键词到股票，支持多种用法"""
    if not context.args:
        await update.message.reply_text(
            "❌ 用法错误\n\n"
            "📌 **支持的用法：**\n"
            "• `/bind 关键词 股票代码` - 绑定单个关键词\n"
            "• `/bind 关键词1,关键词2 股票代码` - 绑定多个关键词到一只股票\n"
            "• `/bind 关键词 股票1,股票2,股票3` - 绑定一个关键词到多只股票\n\n"
            "💡 **示例：**\n"
            "`/bind AI芯片 600030` - AI芯片→中科曙光\n"
            "`/bind AI芯片,半导体 600030` - AI芯片和半导体→中科曙光\n"
            "`/bind AI芯片 600030,688981` - AI芯片→中科曙光+中芯国际",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    analyzer = context.bot_data['analyzer']
    args = list(context.args)
    last_arg = args[-1]

    if ',' in last_arg:
        keywords = args[:-1]
        stock_codes = last_arg.split(',')

        if len(keywords) == 1:
            keyword = keywords[0]
            bound_stocks = []
            for code in stock_codes:
                code = code.strip()
                analyzer.llm_analyzer.bind_keyword(keyword, code)
                bound_stocks.append(code)

            await update.message.reply_text(
                f"🔗 **已绑定关键词到多只股票**\n\n"
                f"🔑 关键词: `{keyword}`\n"
                f"📊 股票: {', '.join(bound_stocks)}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ 参数错误：多个关键词只能绑定到一只股票", parse_mode=ParseMode.MARKDOWN)
        return

    if ',' in args[0]:
        keywords = args[0].split(',')
        stock_code = args[1]

        bound_keywords = []
        for keyword in keywords:
            keyword = keyword.strip()
            analyzer.llm_analyzer.bind_keyword(keyword, stock_code)
            bound_keywords.append(keyword)

        await update.message.reply_text(
            f"🔗 **已绑定多个关键词到股票**\n\n"
            f"📊 股票代码: `{stock_code}`\n"
            f"🔑 关键词: {', '.join([f'`{k}`' for k in bound_keywords])}",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    keyword, code = args[0], args[1]
    analyzer.llm_analyzer.bind_keyword(keyword, code)
    await update.message.reply_text(f"🔗 已绑定: `{keyword}` → `{code}`", parse_mode=ParseMode.MARKDOWN)

async def alert_levels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置或查看推送等级过滤"""
    analyzer = context.bot_data['analyzer']
    config = analyzer.llm_analyzer.config
    valid_levels = {"strong", "normal", "info"}

    if not context.args:
        current_levels = ", ".join(config.get('alert_levels_to_push', ['strong', 'normal']))
        await update.message.reply_text(
            "🔔 **当前推送等级**\n\n"
            f"{current_levels}\n\n"
            "💡 用法: `/alert_levels strong,normal` 或 `/alert_levels strong,normal,info`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    raw_levels = ",".join(context.args).replace(" ", "")
    requested_levels = [lvl for lvl in raw_levels.split(',') if lvl]
    if not requested_levels:
        await update.message.reply_text("❌ 未识别推送等级，请输入 strong/normal/info", parse_mode=ParseMode.MARKDOWN)
        return

    invalid_levels = [lvl for lvl in requested_levels if lvl not in valid_levels]
    if invalid_levels:
        await update.message.reply_text(
            "❌ 推送等级无效: " + ", ".join(invalid_levels) + "\n\n"
            "✅ 可选: strong, normal, info",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    config['alert_levels_to_push'] = requested_levels
    analyzer.llm_analyzer.save_config()
    await update.message.reply_text(
        "✅ **推送等级已更新**\n\n"
        f"当前推送: {', '.join(requested_levels)}",
        parse_mode=ParseMode.MARKDOWN,
    )

async def import_keywords_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """导入A股核心关键词库"""
    try:
        initial_keywords_path = '/app/initial_keywords.json' if os.path.exists('/app/initial_keywords.json') else 'initial_keywords.json'
        if not os.path.exists(initial_keywords_path):
            await update.message.reply_text(
                "❌ 初始关键词文件不存在\n\n"
                "💡 请确保 `initial_keywords.json` 文件存在于项目根目录",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        with open(initial_keywords_path, 'r', encoding='utf-8') as f:
            initial_data = json.load(f)

        analyzer = context.bot_data['analyzer']
        config = analyzer.llm_analyzer.config

        # 统计导入前后的数量
        before_count = len(config.get('concept_db', {}))
        imported_count = 0
        new_keywords = []

        # 合并关键词
        for keyword, stock_codes in initial_data.get('concept_db', {}).items():
            if keyword not in config.get('concept_db', {}):
                config['concept_db'][keyword] = stock_codes
                imported_count += 1
                new_keywords.append(keyword)
            else:
                # 关键词已存在，合并股票代码
                existing_stocks = set(config['concept_db'][keyword])
                new_stocks = set(stock_codes)
                merged_stocks = list(existing_stocks | new_stocks)
                if merged_stocks != list(existing_stocks):
                    config['concept_db'][keyword] = merged_stocks
                    new_keywords.append(f"{keyword} (更新)")

        # 保存配置
        analyzer.llm_analyzer.save_config()

        # 统计分类
        macro = ["美联储", "Fed", "加息", "降息", "利率决议", "通胀", "CPI", "非农数据", "失业率", "经济衰退", "美债收益率", "美元指数", "人民币汇率", "存款准备金", "LPR利率"]
        tech = ["AI芯片", "半导体", "光刻机", "封装测试", "先进制程", "GPU", "HBM", "存储芯片", "芯片设计", "晶圆制造", "设备材料", "封测", "英伟达", "台积电", "中芯国际", "北方华创", "韦尔股份", "兆易创新", "紫光国微", "长电科技"]
        new_energy = ["新能源汽车", "锂电池", "光伏", "储能", "充电桩", "特斯拉", "比亚迪", "宁德时代", "理想汽车", "蔚来汽车", "小鹏汽车", "碳酸锂", "磷酸铁锂", "固态电池", "钠离子电池", "正极材料", "负极材料", "电解液", "隔膜", "科创板"]
        a_share = ["白酒", "贵州茅台", "五粮液", "泸州老窖", "剑南春", "酒鬼酒", "军工", "航母", "军机", "导弹", "中航沈飞", "中航西飞", "创新药", "医疗器械", "恒瑞医药", "迈瑞医疗", "药明康德", "银行", "券商", "工商银行", "招商银行", "中信证券", "东方财富", "房地产", "万科A", "保利发展", "券商股", "猪周期", "煤炭", "有色"]

        # 生成报告
        report = f"""✅ **A股核心关键词库导入成功！**

━━━━━━━━━━━━━━━
📊 **导入统计**
━━━━━━━━━━━━━━━
• 导入前: {before_count} 个关键词
• 导入后: {len(config['concept_db'])} 个关键词
• 新增: {imported_count} 个关键词

━━━━━━━━━━━━━━━
📂 **分类统计**
━━━━━━━━━━━━━━━
• 宏观经济: 15 个
• 科技/半导体: 20 个
• 新能源: 20 个
• A股特色: 25 个

━━━━━━━━━━━━━━━
💡 **新增关键词**
━━━━━━━━━━━━━━━
{', '.join([f'`{k}`' for k in new_keywords[:10]])}
{'...' if len(new_keywords) > 10 else ''}

━━━━━━━━━━━━━━━
🎯 **使用方法**
━━━━━━━━━━━━━━━
• `/list` - 查看所有关键词
• `/bind` - 手动添加关键词
• `/analyze` - 开始巡逻（AI会参考这些关键词）
"""

        await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await update.message.reply_text(
            f"❌ 导入失败: {str(e)}\n\n"
            f"💡 请检查 `initial_keywords.json` 文件格式是否正确",
            parse_mode=ParseMode.MARKDOWN
        )

async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dashboard_url = "https://streamlit.jingyibing.top"
    msg = f"""📊 **AI 量化指挥室 (Web)**

在这里查看：
✅ K线与技术指标
✅ AI 历史买卖点回测
✅ 账户分析

🔗 **点击访问**: {dashboard_url}"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def backtest_command(u, c):
    """回测命令包装函数"""
    await c.bot_data['analyzer'].backtest_handler(update=u, context=c)

# 快捷回测命令
async def backtest_7d_command(u, c):
    """回测最近7天"""
    await c.bot_data['analyzer'].backtest_handler(update=u, context=c, days=7, strategy='hold_3_days')

async def backtest_30d_command(u, c):
    """回测最近30天"""
    await c.bot_data['analyzer'].backtest_handler(update=u, context=c, days=30, strategy='hold_3_days')

async def backtest_90d_command(u, c):
    """回测最近90天"""
    await c.bot_data['analyzer'].backtest_handler(update=u, context=c, days=90, strategy='hold_3_days')

async def clear_command(u, c):
    """清空持仓命令包装函数"""
    await c.bot_data['analyzer'].clear_positions_handler(update=u, context=c)

async def autobind_on_command(u, c):
    """启用AI自动绑定"""
    await c.bot_data['analyzer'].autobind_on_handler(update=u, context=c)

async def autobind_off_command(u, c):
    """禁用AI自动绑定"""
    await c.bot_data['analyzer'].autobind_off_handler(update=u, context=c)

async def api_usage_command(u, c):
    """查询API使用情况"""
    await c.bot_data['analyzer'].check_api_usage_handler(update=u, context=c)

# 🆕 ValueCell 深度研究命令
async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /research 600519 - 深度研究贵州茅台
    使用 ValueCell ResearchAdapter 进行深度分析
    """
    if not context.args:
        await update.message.reply_text(
            "❌ **用法**: `/research 股票代码`\n\n"
            "💡 **示例**:\n"
            "• `/research 600519` - 深度研究茅台\n"
            "• `/research 300750` - 深度研究宁德时代",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    stock_code = context.args[0].strip()
    
    # 发送处理中消息
    msg = await update.message.reply_text(
        f"🔬 **深度研究中**: {stock_code}\n\n"
        f"⏳ 正在获取公告、搜索信息、生成分析...\n"
        f"预计需要 15-30 秒...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        analyzer = context.bot_data['analyzer']
        result = await analyzer.llm_analyzer.deep_research(stock_code)
        
        if result.get('error'):
            await msg.edit_text(f"❌ 研究失败: {result['error']}")
            return
        
        # 构建报告
        stock_name = result.get('stock_name', stock_code)
        report = f"""🔬 **{stock_name} ({stock_code}) 深度研究报告**

━━━━━━━━━━━━━━━
📄 **最新公告** ({len(result.get('filings', []))} 条)
━━━━━━━━━━━━━━━
"""
        for f in result.get('filings', [])[:3]:
            report += f"• {f.get('date', '')}: {f.get('title', '')[:40]}...\n"
        
        if not result.get('filings'):
            report += "暂无公告\n"
        
        report += f"""
━━━━━━━━━━━━━━━
🔍 **AI 深度分析**
━━━━━━━━━━━━━━━
{result.get('analysis', '分析生成失败')[:1500]}
"""
        
        if result.get('recommendation'):
            report += f"""
━━━━━━━━━━━━━━━
💡 **投资建议**
━━━━━━━━━━━━━━━
{result.get('recommendation')}
"""
        
        await msg.edit_text(report, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"深度研究命令失败: {e}")
        await msg.edit_text(f"❌ 研究失败: {str(e)[:100]}")

# 🆕 ValueCell 智能新闻分析命令
async def deepnews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /deepnews AI芯片 - 智能分析 AI 芯片相关新闻
    使用 ValueCell NewsAdapter 进行智能新闻分析
    """
    if not context.args:
        await update.message.reply_text(
            "❌ **用法**: `/deepnews 关键词`\n\n"
            "💡 **示例**:\n"
            "• `/deepnews 人工智能` - 分析 AI 相关新闻\n"
            "• `/deepnews 芯片` - 分析半导体新闻\n"
            "• `/deepnews Tesla` - 分析特斯拉新闻",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    keyword = " ".join(context.args)
    
    # 发送处理中消息
    msg = await update.message.reply_text(
        f"📰 **智能新闻分析中**: {keyword}\n\n"
        f"⏳ 正在获取突发新闻、金融新闻，分析对 A 股影响...\n"
        f"预计需要 20-40 秒...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        analyzer = context.bot_data['analyzer']
        result = await analyzer.llm_analyzer.smart_news_analysis(keyword)
        
        if result.get('error'):
            await msg.edit_text(f"❌ 分析失败: {result['error']}")
            return
        
        # 构建报告
        news_count = len(result.get('news', []))
        report = f"""📰 **{keyword} 智能新闻分析**

━━━━━━━━━━━━━━━
🔴 **突发新闻** ({len(result.get('breaking_news', []))} 条)
━━━━━━━━━━━━━━━
"""
        for n in result.get('breaking_news', [])[:3]:
            report += f"• [{n.get('source', '')}] {n.get('title', '')[:50]}...\n"
        
        if not result.get('breaking_news'):
            report += "暂无突发新闻\n"
        
        report += f"""
━━━━━━━━━━━━━━━
💰 **金融新闻** ({len(result.get('financial_news', []))} 条)
━━━━━━━━━━━━━━━
"""
        for n in result.get('financial_news', [])[:3]:
            report += f"• [{n.get('source', '')}] {n.get('title', '')[:50]}...\n"
        
        if not result.get('financial_news'):
            report += "暂无金融新闻\n"
        
        # 综合分析
        report += f"""
━━━━━━━━━━━━━━━
🧠 **AI 综合分析**
━━━━━━━━━━━━━━━
{result.get('summary', '综合分析生成失败')[:800]}
"""
        
        # A股影响
        if result.get('a_share_impact'):
            report += """
━━━━━━━━━━━━━━━
📊 **A股影响预测**
━━━━━━━━━━━━━━━
"""
            for impact in result.get('a_share_impact', [])[:3]:
                direction_icon = "🚀" if impact.get('direction') == '利好' else ("🔻" if impact.get('direction') == '利空' else "➡️")
                report += f"{direction_icon} **{impact.get('sector', '')}**: {impact.get('reason', '')}\n"
        
        await msg.edit_text(report, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"智能新闻分析命令失败: {e}")
        await msg.edit_text(f"❌ 分析失败: {str(e)[:100]}")

# 🆕 ValueCell Agent 状态命令
async def agent_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /agent_status - 查看 ValueCell Agent 状态
    """
    try:
        analyzer = context.bot_data['analyzer']
        status = analyzer.llm_analyzer.get_valuecell_status()
        
        research_status = "✅ 已初始化" if status['research_adapter']['initialized'] else "⏳ 未初始化"
        research_model = status['research_adapter']['model'] or "N/A"
        news_status = "✅ 已初始化" if status['news_adapter']['initialized'] else "⏳ 未初始化"
        news_model = status['news_adapter']['model'] or "N/A"
        
        msg = f"""🤖 **ValueCell Agent 状态**

━━━━━━━━━━━━━━━
🔬 **ResearchAdapter**
━━━━━━━━━━━━━━━
状态: {research_status}
模型: `{research_model}`

━━━━━━━━━━━━━━━
📰 **NewsAdapter**
━━━━━━━━━━━━━━━
状态: {news_status}
模型: `{news_model}`

━━━━━━━━━━━━━━━
💡 **使用方法**
━━━━━━━━━━━━━━━
• `/research 600519` - 深度研究股票
• `/deepnews 芯片` - 智能新闻分析
"""
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Agent 状态查询失败: {e}")
        await update.message.reply_text(f"❌ 查询失败: {str(e)[:100]}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 **AI 投资助理**

━━━━━━━━━━━━━━━
📊 **核心功能**
━━━━━━━━━━━━━━━
`/analyze` - 🔍 分析持仓走势（AI多模型会诊）
`/add 代码` - ➕ 添加持仓股票
`/del 代码` - ➖ 删除持仓股票
`/list` - 📋 查看当前配置

━━━━━━━━━━━━━━━
📊 **回测系统**
━━━━━━━━━━━━━━━
`/backtest` - 自定义回测
`/backtest_7d` - 快速回测7天
`/backtest_30d` - 快速回测30天

━━━━━━━━━━━━━━━
🔧 **系统管理**
━━━━━━━━━━━━━━━
`/status` - 💊 系统运行状态
`/dashboard` - 🖥️ 打开网页控制台
`/api` - 📈 API用量统计

━━━━━━━━━━━━━━━
🧠 **AI对话**
━━━━━━━━━━━━━━━
`/deepseek [问题]` - 问DeepSeek
`/gpt [问题]` - 问OpenAI (GPT)
`/gemini [问题]` - 问Gemini
`/kimi [问题]` - 问Kimi

━━━━━━━━━━━━━━━
⚙️ **高级功能** (隐藏命令)
━━━━━━━━━━━━━━━
`/clear` - 清空所有持仓
`/bind 关键词 股票` - 绑定关键词
`/autobind_on/off` - AI自动绑定开关
`/alert_levels` - 推送等级过滤
`/import_keywords` - 导入A股关键词库

━━━━━━━━━━━━━━━
💡 **快速上手**
━━━━━━━━━━━━━━━
1. `/add 600519` (添加茅台)
2. `/analyze` (巡逻分析新闻)
3. `/holdings` (诊断持仓走势)
4. `/backtest_30d` (A股T+1回测30天)
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

# 封装 wrapper 以便 context 调用
async def chat_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot_data['analyzer'].chat_handler(update, context)

async def analyze_command(u, c):
    asyncio.create_task(c.bot_data['analyzer'].run_analysis(update=u, context=c, is_manual=True))

async def analyze_holdings_command(u, c):
    """📊 手动触发持仓股票走势分析"""
    asyncio.create_task(c.bot_data['analyzer'].analyze_holdings(update=u, context=c, is_manual=True))

async def futures_command(u, c): 
    data = await asyncio.to_thread(c.bot_data['analyzer'].futures_watcher.get_iron_ore_data)
    await u.message.reply_text(data)

async def status_command(u, c):
    analyzer = c.bot_data['analyzer']
    ds_status = "✅ 就绪" if analyzer.llm_analyzer.deepseek_key else "❌ 未配置"
    gpt_status = "✅ 就绪" if analyzer.llm_analyzer.openai_key else "❌ 未配置"
    gemini_keys_count = len(analyzer.llm_analyzer.gemini_keys)
    gemini_status = f"✅ 就绪 ({gemini_keys_count} Keys)" if gemini_keys_count > 0 else "❌ 未配置"
    kimi_status = "✅ 就绪" if analyzer.llm_analyzer.kimi_key else "❌ 未配置"
    redis_status = "✅ 已连接" if analyzer.redis_client else "❌ 断开"
    server_label = os.getenv("SERVER_LABEL", "Oracle Cloud ARM64")
    msg = f"""🏥 **系统状态诊断 (v2.0)**

🧠 **DeepSeek**: {ds_status}
🤖 **OpenAI (GPT)**: {gpt_status}
⚖️ **Gemini**: {gemini_status}
🌙 **Kimi**: {kimi_status}
💾 **Redis**: {redis_status}
📍 **Server**: {server_label}"""
    await u.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ================= 启动逻辑 =================
async def post_init(app):
    app.bot_data['analyzer'].start_scheduler()

    # 🔥 菜单 (含 ValueCell 新功能)
    commands = [
        BotCommand("start", "📖 使用说明"),
        BotCommand("analyze", "🔍 巡逻分析新闻"),
        BotCommand("holdings", "📊 持仓走势会诊"),
        BotCommand("research", "🔬 深度研究"),
        BotCommand("deepnews", "📰 智能新闻"),
        BotCommand("add", "➕ 添加持仓"),
        BotCommand("del", "➖ 删除持仓"),
        BotCommand("list", "📋 查看配置"),
        BotCommand("backtest", "📊 T+1回测系统"),
        BotCommand("status", "💊 系统状态"),
        BotCommand("deepseek", "🧠 AI对话"),
    ]
    await app.bot.set_my_commands(commands)

    # 🔥 防止重复发送启动通知
    global _startup_notification_sent
    if not _startup_notification_sent:
        try:
            await app.bot_data['analyzer']._notify_text(
                "🚀 机器人重启完成！\n✅ A股事件驱动量化系统 v2.0 已就绪",
                title="🚀 A股量化哨兵已启动",
                level="active",
            )
            _startup_notification_sent = True
        except Exception as e:
            logger.warning(f"发送重启通知失败: {e}")


async def _run_standalone_daemon():
    """
    独立后台守护模式（无需 Telegram Bot）：
    运行定时巡逻、盘前海外映射、早盘期货播报与持仓走势会诊，通过 Bark (iOS) / Webhook 推送结果，
    所有交互操作由 Streamlit Web 控制台 (dashboard.py) 完成。
    """
    global _startup_notification_sent
    analyzer = AdvancedInvestmentAnalyzer()
    analyzer.start_scheduler()
    status = analyzer.notifier.get_status_summary()
    channels_str = ", ".join(status["active_channels"]) if status["active_channels"] else "仅 Web 控制台 (可在网页『推送与系统设置』中绑定 Bark)"
    logger.info(f"🚀 独立量化守护进程已启动 | 活跃推送通道: {channels_str}")

    if not _startup_notification_sent:
        try:
            await analyzer.notifier.send(
                f"🚀 A股事件驱动量化系统 v2.0 已启动\n📲 推送通道: {channels_str}\n🖥️ 请通过 Web 控制台管理持仓、手动巡逻与回测",
                title="🚀 A股量化哨兵已就绪",
                level="active",
            )
            _startup_notification_sent = True
        except Exception as e:
            logger.warning(f"发送启动通知失败: {e}")

    # 保持事件循环常驻
    stop_event = asyncio.Event()
    await stop_event.wait()


def run_bot():
    token = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
    chat_id = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
    disable_tg = os.getenv('DISABLE_TELEGRAM', '0') == '1'

    while True:
        try:
            # 检查 Web 控制台是否显式关闭了 Telegram
            notifier = UnifiedNotifier()
            notify_cfg = notifier._load_notify_config()
            tg_enabled_in_cfg = notify_cfg.get("telegram_enabled", True)

            use_telegram_bot = (
                bool(token)
                and token != "your_telegram_bot_token_here"
                and not disable_tg
                and tg_enabled_in_cfg
            )

            if not use_telegram_bot:
                logger.info("📲 未启用 Telegram Bot，进入【Bark / Webhook 推送 + Web 控制台】独立守护模式...")
                asyncio.run(_run_standalone_daemon())
                break

            t_request = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
            
            analyzer = AdvancedInvestmentAnalyzer()
            app = ApplicationBuilder().token(token).request(t_request).post_init(post_init).build()
            app.bot_data['analyzer'] = analyzer
            
            app.add_handler(CommandHandler('start', start_command))
            app.add_handler(CommandHandler('analyze', analyze_command))
            app.add_handler(CommandHandler('holdings', analyze_holdings_command))
            app.add_handler(CommandHandler('backtest', backtest_command))
            app.add_handler(CommandHandler('backtest_7d', backtest_7d_command))
            app.add_handler(CommandHandler('backtest_30d', backtest_30d_command))
            app.add_handler(CommandHandler('backtest_90d', backtest_90d_command))
            app.add_handler(CommandHandler('status', status_command))
            app.add_handler(CommandHandler('api', api_usage_command))
            app.add_handler(CommandHandler('futures', futures_command))
            app.add_handler(CommandHandler('dashboard', dashboard_command))
            app.add_handler(CommandHandler('add', add_stock_command))
            app.add_handler(CommandHandler('del', del_stock_command))
            app.add_handler(CommandHandler('clear', clear_command))
            app.add_handler(CommandHandler('autobind_on', autobind_on_command))
            app.add_handler(CommandHandler('autobind_off', autobind_off_command))
            app.add_handler(CommandHandler('import_keywords', import_keywords_command))
            app.add_handler(CommandHandler('list', list_config_command))
            app.add_handler(CommandHandler('alert_levels', alert_levels_command))
            app.add_handler(CommandHandler('bind', bind_command))
            app.add_handler(CommandHandler('deepseek', chat_handler_wrapper))
            app.add_handler(CommandHandler('gpt', chat_handler_wrapper))
            app.add_handler(CommandHandler('openai', chat_handler_wrapper))
            app.add_handler(CommandHandler('kimi', chat_handler_wrapper))
            app.add_handler(CommandHandler('qwen', chat_handler_wrapper))
            app.add_handler(CommandHandler('gemini', chat_handler_wrapper))
            
            # 🆕 ValueCell 集成命令
            app.add_handler(CommandHandler('research', research_command))
            app.add_handler(CommandHandler('deepnews', deepnews_command))
            app.add_handler(CommandHandler('agent_status', agent_status_command))
            
            logger.info("🤖 机器人主程序正在启动...")
            
            app.run_polling(drop_pending_updates=True, close_loop=False)
            
        except KeyboardInterrupt:
            logger.info("🛑 用户手动停止")
            break
        except Exception as e:
            logger.error(f"💥 主程序发生严重崩溃: {e}", exc_info=True)
            asyncio.run(send_death_notification(token, chat_id, str(e)))
            logger.info("🔄 10秒后尝试自动重启...")
            time.sleep(10)

if __name__ == "__main__":
    run_bot()
