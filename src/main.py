import logging
import asyncio
import os
import json
import hashlib
import pytz
import time
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

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    handlers=[
        logging.StreamHandler(), 
        TimedRotatingFileHandler('/app/logs/app.log', when='midnight', backupCount=7, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 🔥 死前遗言发送函数
async def send_death_notification(token, chat_id, error_msg):
    try:
        if token and chat_id:
            # 创建临时 Bot 实例发送报警
            t_request = HTTPXRequest(connect_timeout=10.0, read_timeout=10.0)
            bot = Bot(token=token, request=t_request)
            await bot.send_message(chat_id=chat_id, text=f"☠️ **严重警告**：系统崩溃已停止运行！\n\n错误信息：{error_msg}")
    except Exception as e:
        logger.error(f"发送死亡通知失败: {e}") 

class AdvancedInvestmentAnalyzer:
    def __init__(self):
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not token: raise ValueError("TELEGRAM_BOT_TOKEN 缺失")
        
        # 增加超时宽容度
        t_request = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
        self.telegram_bot = Bot(token=token, request=t_request)
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        self.news_collector = AdvancedNewsCollector()
        self.llm_analyzer = LLMAnalyzer() 
        self.gap_detector = InformationGapDetector()
        self.futures_watcher = FuturesWatcher()
        
        self.redis_client = None
        self._connect_redis()
        
        self.cn_holidays = holidays.CN()
        self.last_manual_analysis = None

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

    async def run_analysis(self, update: Update = None, context: ContextTypes.DEFAULT_TYPE = None, is_manual: bool = False):
        try:
            chat_id = update.effective_chat.id if update else self.chat_id

            # 🔥 修复: 统一使用上海时区
            tz = pytz.timezone('Asia/Shanghai')
            now = datetime.now(tz)

            if is_manual and self.last_manual_analysis and now - self.last_manual_analysis < timedelta(minutes=1):
                await self.telegram_bot.send_message(chat_id=chat_id, text="⏳ 冷却中...请稍候再试")
                return

            if is_manual:
                self.last_manual_analysis = now  # 🔥 修复: 保存带时区的时间
                await self.telegram_bot.send_message(chat_id=chat_id, text="🚀 正在巡逻最新新闻...")

            news_list = await self.news_collector.collect_international_news()
            if not news_list:
                if is_manual: await self.telegram_bot.send_message(chat_id=chat_id, text="📊 暂无新内容")
                return

            # 🔥 双重去重逻辑 (URL + 标题)
            new_news_items = []
            seen_urls = set()   
            seen_titles = set() 

            for news in news_list:
                url = news['url']
                title = news.get('title', '').strip()

                if self.is_news_processed(url): continue
                if url in seen_urls: continue
                if title and title in seen_titles: continue
                
                new_news_items.append(news)
                seen_urls.add(url)
                if title: seen_titles.add(title)

            if not new_news_items:
                if is_manual: await self.telegram_bot.send_message(chat_id=chat_id, text="✅ 所有新闻都已分析过。")
                return

            logger.info(f"🔍 发现 {len(new_news_items)} 条新新闻，准备分析...")

            potentially_valuable_news = []
            for news in new_news_items:
                self.mark_news_as_processed(news['url']) 
                
                res = await self.llm_analyzer.analyze_cross_validate(news['title'], news.get('content', ''))
                if not res: continue

                confidence = res.get('confidence', 0)
                influence = res.get('stock_market_influence', 'neutral')
                
                # 从配置读取阈值
                threshold = self.llm_analyzer.threshold_normal
                if res.get('stock_data'):
                    for s in res['stock_data']:
                        if s.get('is_hold'): 
                            threshold = self.llm_analyzer.threshold_hold
                            break
                
                if confidence >= threshold and influence != 'neutral':
                    news['_analysis_result'] = res
                    potentially_valuable_news.append(news)
                else:
                    logger.info(f"🗑️ AI 过滤: 价值低 ({influence}, {confidence:.2f})")

            if not potentially_valuable_news:
                if is_manual: await self.telegram_bot.send_message(chat_id=chat_id, text="⚖️ 本轮新闻经 AI 研判无重大影响。")
                return

            logger.info(f"💎 筛选出 {len(potentially_valuable_news)} 条高价值新闻，检测信息差...")
            gap_news = await self.gap_detector.detect_information_gap(potentially_valuable_news)
            
            if not gap_news:
                if is_manual: await self.telegram_bot.send_message(chat_id=chat_id, text="🔍 高价值新闻国内均已有报道。")
                return

            final_results = []
            for news in gap_news:
                res = news.get('_analysis_result')
                if res: final_results.append((news, res))

            if final_results:
                await self.send_report(final_results, chat_id)

        except Exception as e:
            logger.error(f"流程出错: {e}", exc_info=True)
            if is_manual:
                await self.telegram_bot.send_message(chat_id=chat_id, text=f"❌ 运行出错: {str(e)}")

    # 🔥🔥 图文合一发送逻辑 🔥🔥
    async def send_report(self, results, chat_id):
        for i, (news, analysis) in enumerate(results, 1):
            processing_msg = None
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
            
            # 组装完整文案
            full_msg = f"{icon} **{news['title']}**\n🔥 **涉及概念**: {concept_str}\n\n{final_report}\n\n⏱️ {datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%H:%M')}"

            if processing_msg:
                try:
                    await self.telegram_bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
                except Exception as e:
                    logger.warning(f"删除处理消息失败: {e}")
            
            # 寻找可用的图片
            chart_to_send = None
            if analysis.get('stock_data'):
                for stock in analysis['stock_data']:
                    if stock.get('chart'):
                        chart_to_send = stock['chart']
                        break # 只发一张图
            
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
                logger.error(f"发送失败 (可能文本太长或Markdown错误): {e}")
                try:
                    await self.telegram_bot.send_message(chat_id=chat_id, text=full_msg)
                except Exception as e2:
                    logger.error(f"发送纯文本也失败: {e2}")

    async def report_futures(self):
        if not self.chat_id: return
        try:
            data = await asyncio.to_thread(self.futures_watcher.get_iron_ore_data)
            await self.telegram_bot.send_message(chat_id=self.chat_id, text=f"🌅 **早盘期货哨兵**\n{data}", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"期货播报错误: {e}")

    def start_scheduler(self):
        scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Shanghai'))
        # 🔥 修改为 45 分钟
        scheduler.add_job(self.run_analysis, trigger=IntervalTrigger(minutes=45), id='interval_monitor', max_instances=1)
        scheduler.add_job(self.report_futures, trigger=CronTrigger(hour=9, minute=15), id='futures_morning_report')
        scheduler.start()

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
    positions = ", ".join(config['my_positions'])
    keywords = ", ".join(list(config['concept_db'].keys())[:10]) + "..."
    msg = f"📋 **当前配置**\n\n🏦 **持仓监控**: {positions}\n\n🔑 **关键词库**: {keywords}"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def bind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ 用法: `/bind 关键词 股票代码`")
        return
    keyword, code = context.args[0], context.args[1]
    context.bot_data['analyzer'].llm_analyzer.bind_keyword(keyword, code)
    await update.message.reply_text(f"🔗 已绑定: '{keyword}' -> {code}")

async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dashboard_url = "https://streamlit.jingyibing.top"
    msg = f"""📊 **AI 量化指挥室 (Web)**

在这里查看：
✅ K线与技术指标
✅ AI 历史买卖点回测
✅ 账户分析

🔗 **点击访问**: {dashboard_url}"""
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 **AI 投资助理 (专业版)**

🧠 **Chat 模式**:
/deepseek [问题] - 问 DeepSeek
/gemini [问题] - 问 Gemini

🎮 **常用指令**：
/analyze - 手动巡逻
/dashboard - 打开网页指挥室 🔥
/status - 检查状态
/add `代码` - 监控持仓"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

# 封装 wrapper 以便 context 调用
async def chat_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot_data['analyzer'].chat_handler(update, context)

async def analyze_command(u, c): 
    asyncio.create_task(c.bot_data['analyzer'].run_analysis(update=u, context=c, is_manual=True))

async def futures_command(u, c): 
    data = await asyncio.to_thread(c.bot_data['analyzer'].futures_watcher.get_iron_ore_data)
    await u.message.reply_text(data)

async def status_command(u, c):
    analyzer = c.bot_data['analyzer']
    ds_status = "✅ 就绪" if analyzer.llm_analyzer.deepseek_key else "❌ 未配置"
    gemini_keys_count = len(analyzer.llm_analyzer.gemini_keys)
    gemini_status = f"✅ 就绪 ({gemini_keys_count} Keys)" if gemini_keys_count > 0 else "❌ 未配置"
    redis_status = "✅ 已连接" if analyzer.redis_client else "❌ 断开"
    msg = f"""🏥 **系统状态诊断**

🧠 **DeepSeek**: {ds_status}
⚖️ **Gemini**: {gemini_status}
💾 **Redis**: {redis_status}
📍 **Server**: Los Angeles (VPS)"""
    await u.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ================= 启动逻辑 =================
async def post_init(app):
    app.bot_data['analyzer'].start_scheduler()
    
    commands = [
        BotCommand("analyze", "👮 手动巡逻"),
        BotCommand("dashboard", "📊 量化指挥室"),
        BotCommand("status", "🏥 系统状态"),
        BotCommand("deepseek", "🧠 问DeepSeek"),
        BotCommand("gemini", "⚖️ 问Gemini"),
        BotCommand("list", "📋 配置列表"),
        BotCommand("start", "📖 说明书"),
    ]
    await app.bot.set_my_commands(commands)
    
    if app.bot_data['analyzer'].chat_id:
        try:
            await app.bot_data['analyzer'].telegram_bot.send_message(
                chat_id=app.bot_data['analyzer'].chat_id,
                text="🚀 机器人重启完成！\n✅ 系统已升级"
            )
        except Exception as e:
            logger.warning(f"发送重启通知失败: {e}")

def run_bot():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    while True:
        try:
            t_request = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
            
            analyzer = AdvancedInvestmentAnalyzer()
            app = ApplicationBuilder().token(token).request(t_request).post_init(post_init).build()
            app.bot_data['analyzer'] = analyzer
            
            app.add_handler(CommandHandler('start', start_command))
            app.add_handler(CommandHandler('analyze', analyze_command))
            app.add_handler(CommandHandler('status', status_command))
            app.add_handler(CommandHandler('futures', futures_command))
            app.add_handler(CommandHandler('dashboard', dashboard_command))
            app.add_handler(CommandHandler('add', add_stock_command))
            app.add_handler(CommandHandler('del', del_stock_command))
            app.add_handler(CommandHandler('list', list_config_command))
            app.add_handler(CommandHandler('bind', bind_command))
            app.add_handler(CommandHandler('deepseek', chat_handler_wrapper))
            app.add_handler(CommandHandler('qwen', chat_handler_wrapper))
            app.add_handler(CommandHandler('gemini', chat_handler_wrapper))
            
            logger.info("🤖 机器人主程序正在启动...")
            
            # 🔥 启动时清理一次旧数据 (保留90天)
            #analyzer.db.prune_old_data(days_to_keep=90)
            
            app.run_polling(drop_pending_updates=True, close_loop=False)
            
        except KeyboardInterrupt:
            logger.info("🛑 用户手动停止")
            break
        except Exception as e:
            logger.error(f"💥 主程序发生严重崩溃: {e}", exc_info=True)
            
            # 🔥 发送崩溃报警
            if token and chat_id:
                asyncio.run(send_death_notification(token, chat_id, str(e)))
            
            logger.info("🔄 10秒后尝试自动重启...")
            time.sleep(10)

if __name__ == "__main__":
    run_bot()