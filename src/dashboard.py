import streamlit as st
import pandas as pd
import sqlite3
import os
import re
import sys
import json
import asyncio
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import pytz

# 确保 src 目录在 Python 路径中
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)
if '/app' not in sys.path and os.path.exists('/app'):
    sys.path.insert(0, '/app')

from notifier import UnifiedNotifier
from valuecell_bridge.utils import normalize_ashare_code

# ================= 1. 页面配置 =================
st.set_page_config(
    page_title="ValueCell A股量化指挥室 v2.0",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 注入 CSS 样式 (明亮简约风格)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --bg-1: #FAFBFC;
  --bg-2: #FFFFFF;
  --card: #FFFFFF;
  --accent: #2563EB;
  --accent-2: #10B981;
  --text: #1F2937;
  --muted: #6B7280;
  --border: #E5E7EB;
}

html, body, [class*="css"] {
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  color: var(--text);
}

.stApp {
  background: var(--bg-1);
}

.hero {
  background: linear-gradient(135deg, #EFF6FF, #F0FDF4);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px 28px;
  margin-bottom: 18px;
}

.hero-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 4px 0;
  color: var(--text);
}

.hero-sub {
  color: var(--muted);
  margin: 0;
  font-size: 14px;
}

.stTabs [data-baseweb="tab-list"] {
  gap: 6px;
  background: transparent;
}

.stTabs [data-baseweb="tab"] {
  background: transparent;
  border-radius: 8px;
  padding: 8px 14px;
  font-weight: 500;
}

.stTabs [aria-selected="true"] {
  background: var(--accent) !important;
  color: white !important;
}

.stButton > button {
  border-radius: 8px;
  font-weight: 500;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ================= 🔥 安全门卫模块 =================
def check_password():
    """如果不输入正确密码，程序就会在这里停止，不显示后面的内容"""
    if st.session_state.get('password_correct', False):
        return True

    correct_password = os.getenv("DASHBOARD_PASSWORD", "admin123")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔒 AI 量化指挥室 - 身份验证")
        password_input = st.text_input("请输入访问密码", type="password")
        
        if password_input:
            if password_input == correct_password:
                st.session_state['password_correct'] = True
                st.success("验证成功！正在进入...")
                st.rerun()
            else:
                st.error("❌ 密码错误")
    return False


# ================= 2. 核心逻辑与存储函数 =================

def _run_async(coro):
    """在 Streamlit 同步上下文中安全执行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def get_db_path():
    """智能寻找数据库文件"""
    possible_paths = [
        '/app/data/investment.db',
        os.path.join(os.getcwd(), 'data', 'investment.db'),
        'data/investment.db',
        'investment.db'
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    if os.path.exists('/app/data'):
        files = [f for f in os.listdir('/app/data') if f.endswith('.db')]
        if files:
            return os.path.join('/app/data', files[0])
    # 若尚未创建，返回默认路径并初始化
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        return db.db_path
    except Exception:
        return None


def get_user_config_path() -> str:
    if os.path.exists('/app/data') or os.access('/app', os.W_OK):
        return '/app/data/user_config.json'
    return os.path.join(os.getcwd(), 'data', 'user_config.json')


def load_user_config() -> dict:
    """读取用户配置（持仓、关键词、推送通道设置等）"""
    default_cfg = {
        "my_positions": [],
        "concept_db": {},
        "auto_bind_keywords": True,
        "alert_levels_to_push": ["strong", "normal"],
        "notify_config": {},
    }
    config_path = get_user_config_path()
    if not os.path.exists(config_path):
        return default_cfg

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
            default_cfg.update(data)
            return default_cfg
    except Exception as e:
        st.error(f"❌ 配置读取失败: {e}")
        return default_cfg


def save_user_config(config: dict) -> bool:
    """保存用户配置到 user_config.json"""
    config_path = get_user_config_path()
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"❌ 保存配置失败: {e}")
        return False


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_name(stock_code: str) -> str:
    """获取 A 股真实中文名称（带缓存）"""
    code = normalize_ashare_code(stock_code)
    stock_names = {
        '600276': '恒瑞医药',
        '600900': '长江电力',
        '600519': '贵州茅台',
        '000858': '五粮液',
        '601318': '中国平安',
        '600036': '招商银行',
        '000001': '平安银行',
        '601012': '隆基绿能',
        '300750': '宁德时代',
        '688981': '中芯国际',
        '002594': '比亚迪',
        '601899': '紫金矿业',
    }
    if code in stock_names:
        return stock_names[code]
    try:
        secid = f"1.{code}" if code.startswith(('6', '900')) else f"0.{code}"
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={"secid": secid, "fields": "f57,f58"},
            timeout=3,
        )
        if resp.status_code == 200:
            name = (resp.json().get("data") or {}).get("f58")
            if name and name != "-":
                return str(name)
    except Exception:
        pass
    return code


def load_data():
    """读取信号数据"""
    db_path = get_db_path()
    if not db_path or not os.path.exists(db_path):
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]

        table_name = None
        if 'signals' in tables:
            cursor.execute("SELECT COUNT(*) FROM signals")
            if cursor.fetchone()[0] > 0:
                table_name = 'signals'
            elif 'ai_signals' in tables:
                table_name = 'ai_signals'
            else:
                table_name = 'signals'
        elif 'ai_signals' in tables:
            table_name = 'ai_signals'

        if not table_name:
            conn.close()
            return pd.DataFrame()

        query = f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT 200"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if not df.empty:
            df['created_at'] = pd.to_datetime(df['created_at'])
            if 'signal_type' in df.columns:
                df = df.rename(columns={'signal_type': 'signal'})
            if 'price_at_signal' not in df.columns and 'price' in df.columns:
                df = df.rename(columns={'price': 'price_at_signal'})
            if 'validation_score' in df.columns:
                df['win_rate_val'] = (
                    df['validation_score'].fillna(0.55).clip(0.3, 0.95) * 100
                ).astype(int)
            else:
                df['win_rate_val'] = 60

        return df

    except Exception as e:
        st.error(f"❌ 数据读取失败: {e}")
        return pd.DataFrame()


def load_backtest_results():
    """读取回测结果"""
    db_path = get_db_path()
    if not db_path or not os.path.exists(db_path):
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_results';")
        if not cursor.fetchone():
            conn.close()
            return pd.DataFrame()

        query = "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT 15"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if not df.empty:
            df['created_at'] = pd.to_datetime(df['created_at'])

        return df
    except Exception as e:
        st.error(f"❌ 回测数据读取失败: {e}")
        return pd.DataFrame()


def load_event_memos(limit: int = 200) -> pd.DataFrame:
    """读取事件备忘录"""
    db_path = get_db_path()
    if not db_path or not os.path.exists(db_path):
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_memos';")
        if not cursor.fetchone():
            conn.close()
            return pd.DataFrame()

        query = f"SELECT * FROM event_memos ORDER BY created_at DESC LIMIT {limit}"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if not df.empty:
            df['created_at'] = pd.to_datetime(df['created_at'])

        return df
    except Exception as e:
        st.error(f"❌ 事件备忘录读取失败: {e}")
        return pd.DataFrame()


# ================= 3. 主界面布局 =================

def show_main_dashboard():
    notifier = UnifiedNotifier()
    notify_status = notifier.get_status_summary()
    channels_badge = " · ".join(notify_status["active_channels"]) if notify_status["active_channels"] else "未配置外部推送 (请在『推送与系统设置』中绑定 Bark)"

    st.markdown(f"""
    <div class="hero">
      <div class="hero-title">ValueCell A股事件驱动量化平台 v2.0</div>
      <p class="hero-sub">本土7x24快讯 + 海外映射 · 三维量价共振 · A股 T+1 仿真回测 · 当前活跃推送: <b>{channels_badge}</b></p>
    </div>
    """, unsafe_allow_html=True)

    today = datetime.now(pytz.timezone('Asia/Shanghai')).date()
    df = load_data()
    signal_col = 'signal' if 'signal' in df.columns else ('signal_type' if 'signal_type' in df.columns else None)

    # 顶部 KPI 栏
    col1, col2, col3, col4 = st.columns(4)
    if df.empty:
        with col1:
            st.metric("今日情报", "0 条", delta="总计 0")
        with col2:
            st.metric("高共振机会占比", "0%")
        with col3:
            st.metric("市场 AI 情绪", "暂无数据")
        with col4:
            now = datetime.now(pytz.timezone('Asia/Shanghai'))
            st.metric("当前时间", now.strftime("%H:%M"))
    else:
        df_today = df[df['created_at'].dt.date == today]
        with col1:
            st.metric("今日情报", f"{len(df_today)} 条", delta=f"总计 {len(df)}")
        with col2:
            high_win_df = df[df['win_rate_val'] >= 60] if 'win_rate_val' in df.columns else pd.DataFrame()
            ratio = len(high_win_df) / len(df) * 100 if len(df) > 0 else 0
            st.metric("高共振机会占比", f"{ratio:.1f}%", help="量价验证评分 >= 0.60 的信号比例")
        with col3:
            if signal_col:
                bull_count = len(df[df[signal_col] == 'positive'])
                bear_count = len(df[df[signal_col] == 'negative'])
            else:
                bull_count = bear_count = 0
            sentiment = "偏多头" if bull_count >= bear_count else "偏空头"
            st.metric("市场 AI 情绪", sentiment, f"多{bull_count} : 空{bear_count}")
        with col4:
            st.metric("最新信号时间", df['created_at'].iloc[0].strftime("%m-%d %H:%M"))

    st.divider()

    # 8 个核心功能标签页 (含全新 Bark 推送与系统设置中心)
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "🤖 AI 助手 & 巡逻",
        "📊 持仓监控与管理",
        "📡 核心情报流",
        "📈 数据分析",
        "🔬 T+1 仿真回测",
        "🧾 事件备忘录",
        "🧩 事件簇",
        "📲 推送与系统设置",
    ])

    # ================= Tab 1: AI 助手 & 手动巡逻 =================
    with tab1:
        st.markdown("### 🚀 手动触发新闻巡逻 (替代 `/analyze`)")
        patrol_col1, patrol_col2 = st.columns([3, 1])
        with patrol_col1:
            st.caption("立即采集东方财富/新浪 7x24 快讯与海外主流财经 RSS，执行预期差过滤、多智能体多空辩论与三维量价验证，并自动推送到您的 iPhone Bark。")
        with patrol_col2:
            if st.button("🔍 立即巡逻分析新闻", type="primary", use_container_width=True):
                with st.spinner("正在采集 7x24 快讯与海外新闻并执行 AI 多空辩论，请稍候..."):
                    try:
                        from main import AdvancedInvestmentAnalyzer
                        analyzer = AdvancedInvestmentAnalyzer()
                        results = _run_async(analyzer.run_analysis(is_manual=True))
                        if results:
                            st.success(f"✅ 巡逻完成！发现 {len(results)} 条高价值投资机会，已推送到您的消息通道。")
                            st.rerun()
                        else:
                            st.info("✅ 巡逻完成：当前未发现超过置信度阈值的新催化机会（或最新快讯已分析过）。")
                    except Exception as e:
                        st.error(f"❌ 巡逻执行失败: {e}")

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🔬 个股深度研究 (替代 `/research`)")
            st.caption("输入 6 位 A 股代码，获取东方财富实时估值、巨潮公告与 AI 深度研报")
            stock_code_input = st.text_input("股票代码", placeholder="例如: 600519 或 300750", key="research_stock")
            push_research_to_bark = st.checkbox("同时将研究结论推送到 Bark 手机端", value=True, key="chk_push_research")

            if st.button("开始深度研究", key="btn_research", type="primary"):
                if stock_code_input:
                    code = normalize_ashare_code(stock_code_input)
                    with st.spinner(f"正在深度研究 {code}..."):
                        try:
                            from valuecell_bridge import ResearchAdapter
                            adapter = ResearchAdapter()
                            result = _run_async(adapter.deep_research(f"{code} 投资价值分析", code))
                            _run_async(adapter.close())

                            if result.get('error'):
                                st.error(f"研究失败: {result['error']}")
                            else:
                                st.success("研究完成")
                                stock_info = result.get('stock_info', {})
                                name = stock_info.get('name', code)
                                price = stock_info.get('price', 0)
                                change = stock_info.get('change_pct', 0)
                                fin = stock_info.get('financial', {})
                                pe = fin.get('pe_dynamic')
                                pb = fin.get('pb')

                                c1, c2, c3, c4 = st.columns(4)
                                c1.metric("股票", f"{name} ({code})")
                                c2.metric("现价", f"¥{price:.2f}" if price else "N/A", f"{change:+.2f}%" if change else None)
                                c3.metric("动态 PE", f"{pe:.1f}" if pe else "N/A")
                                c4.metric("PB", f"{pb:.2f}" if pb else "N/A")

                                filings = result.get('filings', [])
                                if filings:
                                    st.markdown("#### 📄 最新公告")
                                    for f in filings[:5]:
                                        st.caption(f"• {f.get('date', '')}: {f.get('title', '')}")

                                st.markdown("#### 🧠 AI 深度分析")
                                st.info(result.get('analysis', '暂无分析'))

                                if result.get('recommendation'):
                                    st.markdown("#### 💡 投资建议")
                                    st.success(result.get('recommendation'))

                                if push_research_to_bark:
                                    push_msg = (
                                        f"🔬 {name}({code}) 深度研究\n"
                                        f"现价: ¥{price:.2f} ({change:+.2f}%)\n"
                                        f"建议: {result.get('recommendation', '观望')}\n\n"
                                        f"{result.get('analysis', '')[:600]}"
                                    )
                                    _run_async(notifier.send(push_msg, title=f"🔬 深度研究: {name}({code})"))
                        except Exception as e:
                            st.error(f"研究失败: {e}")
                else:
                    st.warning("请输入股票代码")

        with col2:
            st.markdown("### 📰 智能新闻与产业链映射 (替代 `/deepnews`)")
            st.caption("输入概念或事件关键词，获取突发快讯及 A 股受益板块推演")
            keyword = st.text_input("搜索关键词", placeholder="例如: 固态电池 / 光刻机 / 算力", key="news_keyword")

            if st.button("分析热点新闻", key="btn_news", type="primary"):
                if keyword:
                    with st.spinner(f"正在分析 {keyword} 相关新闻..."):
                        try:
                            from valuecell_bridge import NewsAdapter
                            adapter = NewsAdapter()
                            result = _run_async(adapter.get_smart_news(keyword))
                            _run_async(adapter.close())

                            if result.get('error'):
                                st.error(f"分析失败: {result['error']}")
                            else:
                                st.success("分析完成")
                                breaking = result.get('breaking_news', [])
                                if breaking:
                                    st.markdown("#### ⚡ 突发快讯")
                                    for n in breaking[:4]:
                                        st.caption(f"• [{n.get('source', '')}] {n.get('title', '')}")

                                st.markdown("#### 🧠 综合研判")
                                st.info(result.get('summary', '暂无分析'))

                                impacts = result.get('a_share_impact', [])
                                if impacts:
                                    st.markdown("#### 🎯 A 股板块映射")
                                    for imp in impacts[:5]:
                                        direction = imp.get('direction', '中性')
                                        icon = "🔥" if direction == '利好' else "🔻" if direction == '利空' else "⚪"
                                        st.markdown(f"{icon} **{imp.get('sector', '')}**: {imp.get('reason', '')}")
                        except Exception as e:
                            st.error(f"分析失败: {e}")
                else:
                    st.warning("请输入搜索关键词")

        st.divider()
        st.markdown("### 💬 多模型 AI 投研对话 (替代 `/deepseek` `/gpt` `/gemini` `/kimi`)")
        chat_col1, chat_col2 = st.columns([1, 4])
        with chat_col1:
            selected_model = st.selectbox(
                "选择对话模型",
                options=["deepseek", "gpt", "gemini", "kimi"],
                format_func=lambda x: {
                    "deepseek": "🧠 DeepSeek (深度推理)",
                    "gpt": "🤖 OpenAI GPT (逻辑映射)",
                    "gemini": "⚖️ Gemini (首席总结)",
                    "kimi": "🌙 Kimi (中文长文本)",
                }.get(x, x),
            )
        with chat_col2:
            user_question = st.text_input("向 AI 提问 A 股逻辑、板块催化或个股问题", placeholder="例如: 近期低空经济板块的核心催化剂和龙头标的是什么？")

        if st.button("发送提问", key="btn_ask_llm"):
            if user_question.strip():
                with st.spinner(f"正在请求 {selected_model.upper()} 思考..."):
                    try:
                        from llm_analyzer import LLMAnalyzer
                        llm = LLMAnalyzer()
                        reply = _run_async(llm.chat_with_model(selected_model, user_question.strip()))
                        st.markdown(f"#### 🤖 {selected_model.upper()} 回复：")
                        st.write(reply or "未获取到回复，请检查对应模型的 API Key 配置。")
                    except Exception as e:
                        st.error(f"调用失败: {e}")
            else:
                st.warning("请输入问题内容")

    # ================= Tab 2: 持仓监控与管理 =================
    with tab2:
        st.markdown("## 📊 持仓监控与管理 (替代 `/add` `/del` `/clear` `/holdings`)")

        config = load_user_config()
        my_positions = [normalize_ashare_code(c) for c in config.get('my_positions', []) if normalize_ashare_code(c)]

        # 持仓管理操作栏
        manage_col1, manage_col2, manage_col3, manage_col4 = st.columns([3, 1, 1, 2])
        with manage_col1:
            new_codes_input = st.text_input(
                "添加持仓股票代码（支持输入多个，用逗号或空格分隔）",
                placeholder="例如: 600519, 300750, 688981",
                label_visibility="collapsed",
            )
        with manage_col2:
            if st.button("➕ 添加持仓", type="primary", use_container_width=True):
                raw_tokens = re.split(r"[,，\s]+", new_codes_input.strip())
                added = []
                for tok in raw_tokens:
                    code = normalize_ashare_code(tok)
                    if re.fullmatch(r"\d{6}", code) and code not in my_positions:
                        my_positions.append(code)
                        added.append(f"{code}({get_stock_name(code)})")
                if added:
                    config['my_positions'] = my_positions
                    save_user_config(config)
                    st.success(f"已添加持仓: {', '.join(added)}")
                    st.rerun()
                else:
                    st.warning("请输入有效的 6 位 A 股代码（或该股票已在持仓中）")
        with manage_col3:
            if st.button("🗑️ 清空持仓", use_container_width=True):
                config['my_positions'] = []
                save_user_config(config)
                st.success("已清空所有持仓")
                st.rerun()
        with manage_col4:
            diagnose_clicked = st.button("🩺 立即会诊全部持仓 (并推送到 Bark)", type="primary", use_container_width=True)

        if diagnose_clicked:
            if not my_positions:
                st.warning("请先添加至少一只持仓股票")
            else:
                with st.spinner(f"正在调用东方财富前复权行情与多模型会诊 {len(my_positions)} 只持仓股..."):
                    try:
                        from main import AdvancedInvestmentAnalyzer
                        analyzer = AdvancedInvestmentAnalyzer()
                        diag_results = _run_async(analyzer.analyze_holdings(is_manual=True))
                        if diag_results:
                            st.session_state["latest_holdings_diag"] = diag_results
                            st.success(f"✅ 持仓会诊完成（共 {len(diag_results)} 只），报告已同步推送至您的 Bark！")
                        else:
                            st.error("❌ 持仓会诊未返回结果，请检查网络或 API Key。")
                    except Exception as e:
                        st.error(f"❌ 持仓会诊异常: {e}")

        # 展示刚执行的实时持仓会诊结果
        if st.session_state.get("latest_holdings_diag"):
            st.markdown("### 🩺 最新实时持仓会诊报告")
            diag_cols = st.columns(min(3, len(st.session_state["latest_holdings_diag"])))
            for idx, r in enumerate(st.session_state["latest_holdings_diag"]):
                with diag_cols[idx % len(diag_cols)]:
                    trend_icon = "📈" if r['trend'] == '上涨' else ("📉" if r['trend'] == '下跌' else "〰️")
                    st.markdown(f"#### {trend_icon} {r.get('name')} ({r['code']}) — `{r.get('action', '观望')}`")
                    st.metric("当前价", f"¥{r['current_price']:.2f}", f"5日 {r.get('change_5d', 0):+.2f}% | 量比 {r.get('volume_ratio', 1):.2f}")
                    st.info(f"**AI 建议**: {r.get('reason', '')}")
                    st.caption(f"🛡️ 安全区间: `{r.get('safe_range', 'N/A')}` | ⚠️ 风险线: `{r.get('risk_alert', 'N/A')}`")
                    st.caption(f"📐 支撑: `{r.get('support', 'N/A')}` | 压力: `{r.get('resistance', 'N/A')}` | 形态: `{r.get('pattern', 'N/A')}`")
            st.divider()

        if not my_positions:
            st.info("📭 暂无持仓股票，请在上方输入框输入 6 位股票代码（如 `600519`）点击【➕ 添加持仓】。")
        else:
            position_signals = df[df['stock_code'].isin(my_positions)] if not df.empty else pd.DataFrame()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("当前持仓数量", f"{len(my_positions)} 只")
            today_pos_signals = position_signals[position_signals['created_at'].dt.date == today] if not position_signals.empty else pd.DataFrame()
            c2.metric("今日持仓关联信号", f"{len(today_pos_signals)} 条")
            c3.metric("持仓专属置信度阈值", os.getenv("CONFIDENCE_THRESHOLD_HOLD", "0.65"), help="持仓股票享受更灵敏的告警阈值")
            c4.metric("非持仓常规阈值", os.getenv("CONFIDENCE_THRESHOLD_NORMAL", "0.75"))

            st.markdown("### 🎯 持仓明细与信号追踪")
            for stock_code in my_positions:
                stock_name = get_stock_name(stock_code)
                with st.expander(f"📌 {stock_code} {stock_name}", expanded=True):
                    top_c1, top_c2 = st.columns([5, 1])
                    with top_c2:
                        if st.button("➖ 移除此股", key=f"del_{stock_code}"):
                            my_positions.remove(stock_code)
                            config['my_positions'] = my_positions
                            save_user_config(config)
                            st.rerun()

                    stock_signals = position_signals[position_signals['stock_code'] == stock_code] if not position_signals.empty else pd.DataFrame()
                    if not stock_signals.empty:
                        latest_signal = stock_signals.iloc[0]
                        sc1, sc2, sc3 = st.columns(3)
                        sig_val = latest_signal.get('signal', 'neutral')
                        sig_icon = "🔥" if sig_val == 'positive' else "🔻" if sig_val == 'negative' else "⚪"
                        sc1.markdown(f"**最新信号**: {sig_icon} `{str(sig_val).upper()}`")
                        sc2.markdown(f"**AI 有效置信度**: `{latest_signal.get('confidence_effective') or latest_signal.get('confidence', 0):.2f}`")
                        created_at = pd.to_datetime(latest_signal.get('created_at'))
                        sc3.markdown(f"**触发时间**: `{created_at.strftime('%m-%d %H:%M')}`")
                        st.info(latest_signal.get('reason', '暂无分析'))
                    else:
                        st.caption("📭 近期暂无该股票的事件/会诊记录，可点击上方【🩺 立即会诊全部持仓】生成最新诊断。")

    # ================= Tab 3: 核心情报流 =================
    with tab3:
        if df.empty:
            st.info("📭 暂无信号数据，您可以切到【🤖 AI 助手 & 巡逻】点击【立即巡逻分析新闻】。")
        else:
            filter_col1, filter_col2 = st.columns([1, 3])
            with filter_col1:
                min_win = st.slider("最低量价验证评分要求 (%)", 0, 100, 45)

            display_df = df[df['win_rate_val'] >= min_win] if 'win_rate_val' in df.columns else df

            for _, row in display_df.iterrows():
                signal_value = row[signal_col] if signal_col else 'neutral'
                card_color = "🟢" if signal_value == 'positive' else "🔴" if signal_value == 'negative' else "⚪"
                stock_code_val = row.get('stock_code', '未知')
                stock_name_val = get_stock_name(str(stock_code_val))
                news_title_val = row.get('news_title', '未知')

                with st.expander(f"{card_color} {stock_code_val} {stock_name_val} | {news_title_val} ({row['created_at'].strftime('%m-%d %H:%M')})"):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown("#### 🧠 AI 辩论与会诊结论")
                        st.info(row.get('reason', ''))
                        st.markdown("**摘要 / 技术面点位：**")
                        st.text(row.get('summary', ''))

                    with c2:
                        st.markdown("#### ⚖️ 三维量化评分")
                        price_value = row.get('price_at_signal', 0)
                        st.metric("触发时现价", f"¥{price_value}")
                        if 'confidence_effective' in row.index and not pd.isna(row.get('confidence_effective')):
                            st.metric("有效置信度", f"{row['confidence_effective'] * 100:.0f}%")
                        elif 'confidence' in row.index and not pd.isna(row.get('confidence')):
                            st.metric("AI 置信度", f"{row['confidence'] * 100:.0f}%")

                        gap_conf = row.get('gap_confidence') if not pd.isna(row.get('gap_confidence')) else 0
                        val_score = row.get('validation_score') if not pd.isna(row.get('validation_score')) else 0
                        st.caption(f"预期差评分: `{gap_conf:.2f}` | 量价共振分: `{val_score:.2f}`")
                        if 'coverage_status' in row.index:
                            st.caption(f"信源类型: `{row.get('coverage_status', 'unknown')}`")

    # ================= Tab 4: 数据分析 =================
    with tab4:
        if df.empty:
            st.info("📭 暂无信号数据")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("热门信号标的 Top 10")
                if 'stock_code' in df.columns:
                    stock_counts = df['stock_code'].apply(lambda c: f"{c} {get_stock_name(str(c))}").value_counts().head(10)
                    fig = px.bar(stock_counts, orientation='h', title="高频触发 A 股标的 Top 10")
                    st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.subheader("置信度分布")
                if 'confidence' in df.columns:
                    fig2 = px.histogram(df, x="confidence", nbins=20, title="AI 决策置信度分布")
                    st.plotly_chart(fig2, use_container_width=True)

    # ================= Tab 5: A股 T+1 仿真回测 =================
    with tab5:
        st.subheader("🔬 A 股 T+1 仿真回测系统 (替代 `/backtest` `/backtest_30d`)")
        st.caption("严格遵循 A 股真实交易制度：盘后信号按次日开盘价(Open)+滑点买入、T+0 当日锁仓不可卖出、一字涨停排板无法买入单独统计、跳空低开按真实开盘价止损。")

        bt_col1, bt_col2, bt_col3, bt_col4 = st.columns([1, 2, 1, 1])
        with bt_col1:
            bt_days = st.selectbox("回测时间范围", options=[7, 15, 30, 60, 90], index=2, format_func=lambda d: f"最近 {d} 天")
        with bt_col2:
            bt_strategy = st.selectbox(
                "回测出场策略",
                options=["hold_3_days", "hold_5_days", "stop_loss_5", "target_profit_10"],
                format_func=lambda s: {
                    "hold_3_days": "hold_3_days (T+1起持有3个交易日)",
                    "hold_5_days": "hold_5_days (T+1起持有5个交易日)",
                    "stop_loss_5": "stop_loss_5 (5%止损 / 含跳空低开滑点)",
                    "target_profit_10": "target_profit_10 (10%止盈目标)",
                }.get(s, s),
            )
        with bt_col3:
            push_bt_to_bark = st.checkbox("推送回测报告到 Bark", value=False)
        with bt_col4:
            run_bt_clicked = st.button("▶️ 立即运行回测", type="primary", use_container_width=True)

        if run_bt_clicked:
            with st.spinner(f"正在通过东方财富前复权日K线回测最近 {bt_days} 天信号 ({bt_strategy})..."):
                try:
                    from backtest import LightweightBacktester
                    bt_engine = LightweightBacktester()
                    bt_res = _run_async(bt_engine.run_backtest(days=bt_days, strategy=bt_strategy))
                    if 'error' in bt_res:
                        st.warning(f"⚠️ {bt_res['error']}")
                    else:
                        st.success(f"✅ 回测完成！共回测 {bt_res.get('total_signals', 0)} 笔可成交信号（另有 {bt_res.get('untradable_count', 0)} 笔因一字涨停无法买入已剔除）。")
                        if push_bt_to_bark:
                            bt_msg = (
                                f"📊 A股T+1回测 ({bt_days}天 | {bt_strategy})\n"
                                f"可成交信号: {bt_res.get('total_signals', 0)}笔 (一字板不可买: {bt_res.get('untradable_count', 0)}笔)\n"
                                f"胜率: {bt_res.get('win_rate', 0):.1f}% | 盈亏比: {bt_res.get('profit_loss_ratio', 0):.2f}\n"
                                f"累计收益: {bt_res.get('total_profit', 0):+.2f}% | 最大回撤: {bt_res.get('max_drawdown', 0):.2f}%"
                            )
                            _run_async(notifier.send(bt_msg, title="📊 A股T+1回测报告"))
                except Exception as e:
                    st.error(f"❌ 回测执行失败: {e}")

        st.divider()
        backtest_df = load_backtest_results()
        if backtest_df.empty:
            st.info("📊 暂无历史回测记录，请点击上方【▶️ 立即运行回测】按钮生成。")
        else:
            st.markdown("### 📈 历史回测记录")
            for _, row in backtest_df.iterrows():
                with st.expander(f"📅 {row['created_at'].strftime('%Y-%m-%d %H:%M')} — 策略: `{row['strategy']}` | 胜率: {row.get('win_rate', 0):.1f}%", expanded=False):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("有效成交信号", row['total_signals'])
                    win_rate = row.get('win_rate', 0)
                    c2.metric("真实胜率", f"{win_rate:.1f}%", delta=f"{win_rate-50:.1f}%")
                    c3.metric("盈亏比", f"{row['profit_loss_ratio']:.2f}")
                    c4.metric("累计收益", f"{row['total_profit']:+.2f}%")

                    details_raw = row.get('details')
                    if details_raw:
                        try:
                            details_list = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
                            if details_list:
                                st.markdown("#### 📋 信号回测明细")
                                st.dataframe(pd.DataFrame(details_list), use_container_width=True, hide_index=True)
                        except Exception:
                            pass

    # ================= Tab 6: 事件备忘录 =================
    with tab6:
        st.subheader("🧾 事件备忘录")
        load_limit = st.slider("加载条数", min_value=50, max_value=500, value=200, step=50)
        memo_df = load_event_memos(load_limit)

        if memo_df.empty:
            st.info("📭 暂无事件备忘录，请等待 AI 巡逻生成事件模板")
        else:
            for _, row in memo_df.head(50).iterrows():
                with st.expander(f"📝 {row['news_title']} ({row['created_at'].strftime('%m-%d %H:%M')})"):
                    st.markdown(f"**模板**: `{row.get('template_label', 'N/A')}` | **方向**: `{row.get('sectors', 'N/A')}` | **等级**: `{row.get('alert_level', 'N/A')}`")
                    st.markdown(f"**先反应市场**: {row.get('market_first_reaction', 'N/A')}")
                    st.markdown(f"**A股映射池**: {row.get('a_share_mapping', 'N/A')}")
                    st.markdown(f"**失效条件**: {row.get('failure_conditions', 'N/A')}")

    # ================= Tab 7: 事件簇 =================
    with tab7:
        st.subheader("🧩 事件簇聚合")
        if df.empty or 'event_cluster_id' not in df.columns:
            st.info("📭 暂无事件簇数据")
        else:
            cluster_df = df.dropna(subset=['event_cluster_id']).copy()
            if cluster_df.empty:
                st.info("📭 暂无事件簇数据")
            else:
                cluster_df['event_cluster_id'] = cluster_df['event_cluster_id'].astype(int)
                agg = cluster_df.groupby('event_cluster_id').agg({
                    'news_title': 'first',
                    'created_at': 'max',
                    'confidence': 'mean',
                    'stock_code': 'count'
                }).rename(columns={'stock_code': 'signals'}).reset_index().sort_values('created_at', ascending=False)

                for _, row in agg.head(50).iterrows():
                    with st.expander(f"🧩 簇 #{int(row['event_cluster_id'])} | {row['news_title']} (关联信号 {int(row['signals'])} 条)"):
                        st.caption(f"最近更新: {row['created_at'].strftime('%Y-%m-%d %H:%M')} | 平均置信度: {row['confidence']:.2f}")

    # ================= Tab 8: 推送与系统设置 (Bark / Webhook / 关键词 / 状态) =================
    with tab8:
        st.markdown("## 📲 消息推送通道设置 (Bark iOS / Webhook)")
        st.caption("无需再配置繁琐的 Telegram Bot！直接填入 iPhone 上的 Bark 推送地址或 Key，点击保存即可享受原生锁屏/横幅推送。")

        current_notify_cfg = notify_status["config"]

        with st.form("bark_config_form"):
            st.markdown("### 🍎 1. Bark (iOS 苹果原生推送) 配置")
            f_col1, f_col2 = st.columns([3, 1])
            with f_col1:
                bark_url_input = st.text_input(
                    "Bark Key 或完整推送地址 (BARK_URL)",
                    value=current_notify_cfg.get("bark_url", ""),
                    placeholder="例如: https://api.day.app/你的BarkKey 或直接填 你的BarkKey",
                    help="在 iPhone App Store 下载免费的「Bark」App，打开即可复制专属 Key 或 URL",
                )
            with f_col2:
                bark_enabled_input = st.checkbox("启用 Bark 推送", value=current_notify_cfg.get("bark_enabled", True))

            b_col1, b_col2, b_col3, b_col4 = st.columns(4)
            with b_col1:
                bark_group_input = st.text_input("通知分组名 (Group)", value=current_notify_cfg.get("bark_group", "A股量化哨兵"))
            with b_col2:
                level_options = ["timeSensitive", "active", "critical", "passive"]
                curr_level = current_notify_cfg.get("bark_level", "timeSensitive")
                bark_level_input = st.selectbox(
                    "通知优先级 (Level)",
                    options=level_options,
                    index=level_options.index(curr_level) if curr_level in level_options else 0,
                    format_func=lambda x: {
                        "timeSensitive": "timeSensitive (时效性通知·可穿透专注模式)",
                        "active": "active (默认亮屏通知)",
                        "critical": "critical (重要紧急告警)",
                        "passive": "passive (静默通知·不亮屏)",
                    }.get(x, x),
                )
            with b_col3:
                sound_options = ["glass", "bell", "alarm", "birdsong", "bloom", "calypso", "chime", "electronic", "fanfare", "noir"]
                curr_sound = current_notify_cfg.get("bark_sound", "glass")
                bark_sound_input = st.selectbox(
                    "推送提示音 (Sound)",
                    options=sound_options,
                    index=sound_options.index(curr_sound) if curr_sound in sound_options else 0,
                )
            with b_col4:
                dashboard_url_input = st.text_input(
                    "点击通知跳转控制台地址 (可选)",
                    value=current_notify_cfg.get("dashboard_url", ""),
                    placeholder="例如: http://你的服务器IP",
                )

            st.markdown("### 🌐 2. 扩展 Webhook 通道 (可选：Discord / 飞书 / 企微 / 钉钉 / Slack)")
            webhook_url_input = st.text_input(
                "Webhook URL (留空则不启用，系统会自动根据域名适配格式)",
                value=current_notify_cfg.get("webhook_url", ""),
                placeholder="例如: https://discord.com/api/webhooks/... 或 https://open.feishu.cn/open-apis/bot/v2/hook/...",
            )

            tg_enabled_input = st.checkbox(
                "兼容启用旧版 Telegram Bot (如已停用 Telegram 请保持取消勾选)",
                value=False if not current_notify_cfg.get("telegram_token") else current_notify_cfg.get("telegram_enabled", False),
            )

            submitted = st.form_submit_button("💾 保存推送通道设置", type="primary")
            if submitted:
                ok = notifier.save_notify_config({
                    "bark_enabled": bark_enabled_input,
                    "bark_url": bark_url_input.strip(),
                    "bark_group": bark_group_input.strip() or "A股量化哨兵",
                    "bark_level": bark_level_input,
                    "bark_sound": bark_sound_input,
                    "dashboard_url": dashboard_url_input.strip(),
                    "webhook_url": webhook_url_input.strip(),
                    "telegram_enabled": tg_enabled_input,
                })
                if ok:
                    st.success("✅ 推送配置已保存并立即生效！您可以点击下方【🔔 发送测试推送】验证手机是否收到通知。")
                    st.rerun()

        if st.button("🔔 立即发送一条 Bark / Webhook 测试推送"):
            test_msg = (
                "🎉 **恭喜！您的 A 股量化哨兵 v2.0 推送通道已连通！**\n\n"
                "• 东方财富前复权行情底座：正常\n"
                "• 本土 7x24 快讯 + 海外映射：正常\n"
                "• A 股三维量价共振与 T+1 回测：正常"
            )
            ok = _run_async(notifier.send(
                test_msg,
                title="🔔 A股量化哨兵 - 通道连通测试",
                subtitle="Bark iOS 原生推送已就绪",
                level="timeSensitive",
            ))
            if ok:
                st.success("✅ 测试推送发送成功！请查看您的 iPhone Bark 通知。")
            else:
                st.error("❌ 推送未成功，请确认已填写正确的 Bark Key / URL 并点击了【💾 保存推送通道设置】。")

        st.divider()

        # 关键词与推送过滤管理 (替代 /bind, /import_keywords, /alert_levels, /autobind_on)
        st.markdown("## 🔑 关键词库与推送过滤管理")
        user_cfg = load_user_config()
        kw_col1, kw_col2 = st.columns(2)

        with kw_col1:
            st.markdown("#### 🎚️ 信号推送过滤与自动绑定")
            curr_levels = user_cfg.get("alert_levels_to_push", ["strong", "normal"])
            new_levels = st.multiselect(
                "允许推送的催化等级 (Alert Levels)",
                options=["strong", "normal", "info"],
                default=[x for x in curr_levels if x in ["strong", "normal", "info"]] or ["strong", "normal"],
            )
            auto_bind_val = st.checkbox("启用 AI 自动绑定概念关键词到股票", value=user_cfg.get("auto_bind_keywords", True))
            if st.button("保存过滤设置"):
                user_cfg["alert_levels_to_push"] = new_levels
                user_cfg["auto_bind_keywords"] = auto_bind_val
                save_user_config(user_cfg)
                st.success("✅ 过滤与自动绑定设置已更新")

        with kw_col2:
            st.markdown("#### 🔗 手动绑定关键词 / 导入核心词库")
            bind_kw = st.text_input("概念/产品关键词", placeholder="例如: HBM / 固态电池 / 涨价")
            bind_codes = st.text_input("关联 A 股代码（多个用逗号分隔）", placeholder="例如: 688981, 002371")
            b_btn1, b_btn2 = st.columns(2)
            with b_btn1:
                if st.button("🔗 绑定关键词"):
                    if bind_kw.strip() and bind_codes.strip():
                        concept_db = user_cfg.setdefault("concept_db", {})
                        kw_key = bind_kw.strip().lower()
                        kw_list = concept_db.setdefault(kw_key, [])
                        for raw_c in re.split(r"[,，\s]+", bind_codes.strip()):
                            c = normalize_ashare_code(raw_c)
                            if re.fullmatch(r"\d{6}", c) and c not in kw_list:
                                kw_list.append(c)
                        save_user_config(user_cfg)
                        st.success(f"已绑定 '{bind_kw}' -> {kw_list}")
                    else:
                        st.warning("请填写关键词和股票代码")
            with b_btn2:
                if st.button("📥 一键导入 A 股核心概念词库"):
                    possible_kw_files = [
                        '/app/initial_keywords.json',
                        os.path.join(os.getcwd(), 'initial_keywords.json'),
                    ]
                    kw_file = next((p for p in possible_kw_files if os.path.exists(p)), None)
                    if kw_file:
                        with open(kw_file, 'r', encoding='utf-8') as f:
                            init_data = json.load(f)
                        concept_db = user_cfg.setdefault("concept_db", {})
                        imported = 0
                        for k, stocks in (init_data.get("keywords") or {}).items():
                            kw_list = concept_db.setdefault(k.lower(), [])
                            for s in stocks:
                                norm_s = normalize_ashare_code(s)
                                if norm_s not in kw_list:
                                    kw_list.append(norm_s)
                                    imported += 1
                        save_user_config(user_cfg)
                        st.success(f"✅ 成功导入 {imported} 条 A 股产业链映射关系（当前共 {len(concept_db)} 个关键词）！")
                    else:
                        st.error("未找到 initial_keywords.json 文件")

        st.divider()
        st.markdown("## 💊 系统状态诊断 (替代 `/status`)")
        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        s_col1.metric("🧠 DeepSeek", "✅ 已配置" if os.getenv("DEEPSEEK_API_KEY") else "❌ 未配置")
        s_col2.metric("🤖 OpenAI (GPT)", "✅ 已配置" if os.getenv("OPENAI_API_KEY") else "❌ 未配置")
        gemini_cnt = len([k for k in (os.getenv("GEMINI_API_KEY") or "").split(",") if k.strip()])
        s_col3.metric("⚖️ Gemini", f"✅ 已配置 ({gemini_cnt} Keys)" if gemini_cnt > 0 else "❌ 未配置")
        s_col4.metric("🌙 Kimi", "✅ 已配置" if os.getenv("KIMI_API_KEY") else "❌ 未配置")


# ================= 4. 入口函数 =================
def main():
    if check_password():
        show_main_dashboard()


if __name__ == "__main__":
    main()
