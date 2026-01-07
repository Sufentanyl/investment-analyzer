#!/usr/bin/env python3
"""
在VPS上应用所有更新：Kimi替补机制 + Dashboard持仓功能
"""
import os
import re

print("🚀 开始应用更新...")

# ==================== 1. 修改 llm_analyzer.py ====================
print("\n📝 更新 llm_analyzer.py...")

with open('src/llm_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1.1 添加Kimi配置（在gemini_model之后）
if 'self.kimi_key' not in content:
    content = re.sub(
        r'(self\.gemini_model = os\.getenv\("GEMINI_MODEL"[^\n]+\n)',
        r'\1\n        # 🔥 新增: Kimi API (替补)\n        self.kimi_key = os.getenv("KIMI_API_KEY")\n        self.kimi_base = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")\n        self.kimi_model = "moonshot-v1-8k"\n',
        content
    )

# 1.2 添加client_kimi
content = re.sub(
    r'(self\.client_qwen = None\n)',
    r'\1        self.client_kimi = None  # 🔥 新增\n',
    content
)

# 1.3 添加Telegram Bot支持
if 'self.telegram_bot = None' not in content:
    content = re.sub(
        r'(self\._aiohttp_session = None\n)',
    r'\1\n        # 🔥 新增: Telegram Bot (用于发送fallback通知)\n        self.telegram_bot = None\n        self.chat_id = None\n',
    content
)

# 1.4 添加set_telegram_bot方法（在_ensure_clients之前）
if 'def set_telegram_bot' not in content:
    content = re.sub(
        r'(    def _ensure_clients\(self\):)',
        r'    def set_telegram_bot(self, bot, chat_id):\n        """🔥 新增: 设置Telegram Bot用于发送通知"""\n        self.telegram_bot = bot\n        self.chat_id = chat_id\n\n    \1',
        content
    )

# 1.5 在_ensure_clients中添加kimi client初始化
content = re.sub(
    r'(if not self\.client_qwen and self\.qwen_key:\n            self\.client_qwen = AsyncOpenAI\(api_key=self\.qwen_key, base_url=self\.qwen_base\))',
    r'\1\n        if not self.client_kimi and self.kimi_key:\n            self.client_kimi = AsyncOpenAI(api_key=self.kimi_key, base_url=self.kimi_base)',
    content
)

# 1.6 修改_call_gemini_text添加fallback机制
if 'await self._call_kimi_text(prompt)' not in content:
    old_gemini = '''    @retry_async()
    async def _call_gemini_text(self, prompt: str) -> str:
        if not self.gemini_keys: return "Gemini Key缺失"
        key = random.choice(self.gemini_keys)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={key}"
        try:
            # 🔥 修复: 使用复用的 session
            session = await self._get_aiohttp_session()
            async with session.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
                else:
                    logger.warning(f"Gemini API 错误: {resp.status}")
        except Exception as e:
            logger.error(f"Gemini 调用异常: {e}")
        return ""'''

    new_gemini = '''    @retry_async()
    async def _call_gemini_text(self, prompt: str) -> str:
        """调用Gemini API，失败时fallback到Kimi"""
        if not self.gemini_keys:
            logger.warning("Gemini Key缺失，使用Kimi替补")
            return await self._call_kimi_text(prompt)

        key = random.choice(self.gemini_keys)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={key}"
        try:
            # 🔥 修复: 使用复用的 session
            session = await self._get_aiohttp_session()
            async with session.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
                elif resp.status == 429:
                    logger.warning(f"Gemini API 配额用尽 (HTTP 429)，切换到Kimi替补")
                    await self._send_fallback_notification("Gemini", "配额用尽")
                    return await self._call_kimi_text(prompt)
                else:
                    logger.warning(f"Gemini API 错误: {resp.status}")
                    await self._send_fallback_notification("Gemini", f"HTTP {resp.status}")
                    return await self._call_kimi_text(prompt)
        except Exception as e:
            logger.error(f"Gemini 调用异常: {e}")
            await self._send_fallback_notification("Gemini", str(e))
            return await self._call_kimi_text(prompt)'''

    content = content.replace(old_gemini, new_gemini)

# 1.7 添加_call_kimi_text和_send_fallback_notification方法
if 'async def _call_kimi_text' not in content:
    content = re.sub(
        r'(    async def _call_gemini_json\(self, prompt: str\) -> Dict:)',
        '''    async def _call_kimi_text(self, prompt: str) -> str:
        """🔥 新增: 调用Kimi API作为替补"""
        if not self.kimi_key:
            logger.error("Kimi API Key缺失，无法替补")
            return ""

        self._ensure_clients()
        if not self.client_kimi:
            logger.error("Kimi客户端初始化失败")
            return ""

        try:
            resp = await self.client_kimi.chat.completions.create(
                model=self.kimi_model,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"Kimi替补调用也失败: {e}")
            return ""

    async def _send_fallback_notification(self, api_name: str, reason: str):
        """🔥 新增: 发送API切换通知到Telegram"""
        if not self.telegram_bot or not self.chat_id:
            return

        try:
            from telegram import Bot
            from datetime import datetime
            import pytz

            msg = f"⚠️ **API切换通知**\\n\\n"
            msg += f"🔴 {api_name} API异常\\n"
            msg += f"📝 原因: {reason}\\n"
            msg += f"✅ 已自动切换到Kimi替补\\n"
            msg += f"⏰ {datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%H:%M')}"

            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text=msg,
                parse_mode="Markdown"
            )
            logger.info(f"已发送API切换通知: {api_name} -> Kimi")
        except Exception as e:
            logger.error(f"发送Telegram通知失败: {e}")

    \\1''',
        content
    )

with open('src/llm_analyzer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ llm_analyzer.py 已更新")

# ==================== 2. 修改 main.py ====================
print("\n📝 更新 main.py...")

with open('src/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 2.1 添加HTTPXRequest导入（检查是否已存在）
if 'from telegram.request import HTTPXRequest' not in content:
    content = re.sub(
        r'(from telegram\.ext import Application, CommandHandler, ContextTypes, ApplicationBuilder)',
        r'\1\nfrom telegram.request import HTTPXRequest',
        content
    )

# 2.2 设置Telegram Bot给LLMAnalyzer
if 'set_telegram_bot' not in content:
    content = re.sub(
        r'(self\.llm_analyzer = LLMAnalyzer\(\)\n)',
        r'\1        # 🔥 新增: 设置Telegram Bot用于发送API切换通知\n        self.llm_analyzer.set_telegram_bot(self.telegram_bot, self.chat_id)\n',
        content
    )

with open('src/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ main.py 已更新")

# ==================== 3. 修改 dashboard.py ====================
print("\n📝 更新 dashboard.py...")

with open('src/dashboard.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 3.1 添加load_user_config函数
if 'def load_user_config' not in content:
    content = re.sub(
        r'(    except Exception as e:\n        st\.error\(f"❌ 数据读取失败: \{e\}"\)\n        return pd\.DataFrame\(\)\n\n\ndef load_backtest_results\(\):)',
        r'''    except Exception as e:
        st.error(f"❌ 数据读取失败: {e}")
        return pd.DataFrame()

def load_user_config():
    """🔥 新增: 读取用户配置（持仓、关键词等）"""
    config_path = '/app/data/user_config.json'
    if not os.path.exists(config_path):
        return {"my_positions": [], "concept_db": {}}

    try:
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"❌ 配置读取失败: {e}")
        return {"my_positions": [], "concept_db": {}}

\\1''',
        content
    )

# 3.2 修改tab结构，添加持仓tab
content = re.sub(
    r'tab1, tab2, tab3 = st\.tabs\(\["🚀 核心情报流", "📊 深度数据分析", "🔬 回测结果"\]\)',
    'tab1, tab2, tab3, tab4 = st.tabs(["📈 我的持仓", "🚀 核心情报流", "📊 深度数据分析", "🔬 回测结果"])',
    content
)

# 3.3 添加持仓页面内容（在tab1之前）
if '我的持仓监控' not in content:
    content = re.sub(
        r'(    with tab1:\n)',
        '''    # ================= 📈 我的持仓 (新增) =================
    with tab4:
        st.markdown("## 📈 我的持仓监控")

        # 读取配置
        config = load_user_config()
        my_positions = config.get('my_positions', [])

        if not my_positions:
            st.info("📭 暂无持仓股票，请在Telegram中使用 `/add 股票代码` 添加持仓")
            st.caption("例如: `/add 600519` 添加贵州茅台")
        else:
            # 持仓概览卡片
            st.markdown("### 📊 持仓概览")

            # 过滤持仓信号
            position_signals = df[df['stock_code'].isin(my_positions)] if not df.empty else pd.DataFrame()

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("持仓数量", f"{len(my_positions)} 只")
            with col2:
                today_pos_signals = position_signals[position_signals['created_at'].dt.date == today] if not position_signals.empty else pd.DataFrame()
                st.metric("今日持仓信号", f"{len(today_pos_signals)} 条")
            with col3:
                if not position_signals.empty and 'win_rate_val' in position_signals.columns:
                    avg_win_rate = position_signals['win_rate_val'].mean()
                    st.metric("持仓平均胜率", f"{avg_win_rate:.1f}%")
                else:
                    st.metric("持仓平均胜率", "--")
            with col4:
                st.metric("最新更新", df['created_at'].iloc[0].strftime("%H:%M") if not df.empty else "--:--")

            st.divider()

            # 持仓列表
            st.markdown("### 🎯 持仓详情")

            for stock_code in my_positions:
                with st.expander(f"📌 {stock_code}"):
                    # 获取该股票的信号
                    stock_signals = position_signals[position_signals['stock_code'] == stock_code] if not position_signals.empty else pd.DataFrame()

                    if not stock_signals.empty:
                        # 显示最新信号
                        latest_signal = stock_signals.iloc[0]
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            signal_icon = "🔥" if latest_signal.get('signal') == 'positive' else "🔻" if latest_signal.get('signal') == 'negative' else "⚪"
                            st.markdown(f"**最新信号**: {signal_icon} {latest_signal.get('signal', 'N/A').upper()}")

                        with col2:
                            confidence = latest_signal.get('confidence', 0)
                            st.markdown(f"**AI信心**: {confidence:.2f}")

                        with col3:
                            created_at = latest_signal.get('created_at')
                            if isinstance(created_at, str):
                                created_at = pd.to_datetime(created_at)
                            st.markdown(f"**时间**: {created_at.strftime('%m-%d %H:%M')}")

                        # 显示理由
                        with st.container():
                            st.markdown("**AI分析理由**:")
                            st.info(latest_signal.get('reason', '暂无分析'))

                        # 显示历史信号
                        if len(stock_signals) > 1:
                            st.markdown("**历史信号**:")
                            for idx, signal in stock_signals.iloc[1:min(4, len(stock_signals))].iterrows():
                                sig_emoji = "🔥" if signal.get('signal') == 'positive' else "🔻" if signal.get('signal') == 'negative' else "⚪"
                                created_at = pd.to_datetime(signal.get('created_at'))
                                st.caption(f"{sig_emoji} {created_at.strftime('%m-%d %H:%M')} - 信心:{signal.get('confidence', 0):.2f}")
                    else:
                        st.info("📭 暂无该股票的信号数据")

    \\1''',
        content
    )

with open('src/dashboard.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ dashboard.py 已更新")

print("\n" + "="*60)
print("🎉 所有更新已应用成功！")
print("="*60)
print("\n下一步：重启服务")
print("docker compose restart")
