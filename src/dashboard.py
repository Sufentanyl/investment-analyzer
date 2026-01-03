import streamlit as st
import pandas as pd
import sqlite3
import os
import re
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import pytz

# ================= 1. 页面配置 =================
st.set_page_config(
    page_title="AI 量化指挥室 (Pro)",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="collapsed" # 默认收起侧边栏
)

# 注入 CSS 样式 (暗黑金融风)
st.markdown("""
<style>
    .big-font { font-size: 24px !important; font-weight: bold; }
    .win-rate-high { color: #00FF7F; font-weight: bold; }
    .win-rate-low { color: #FF4500; font-weight: bold; }
    .stMetric { background-color: #1E1E1E; padding: 10px; border-radius: 5px; }
    /* 隐藏 Streamlit 默认的菜单和页脚，看起来更像 App */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ================= 🔥 安全门卫模块 =================
def check_password():
    """如果不输入正确密码，程序就会在这里停止，不显示后面的内容"""
    
    # 如果已经登录成功，直接放行
    if st.session_state.get('password_correct', False):
        return True

    # 读取 .env 里的密码 (如果没设置，默认是 admin123)
    correct_password = os.getenv("DASHBOARD_PASSWORD", "admin123")

    # 显示登录框
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔒 AI 指挥室 - 身份验证")
        password_input = st.text_input("请输入访问密码", type="password")
        
        if password_input:
            if password_input == correct_password:
                st.session_state['password_correct'] = True
                st.success("验证成功！正在进入...")
                st.rerun()  # 刷新页面进入
            else:
                st.error("❌ 密码错误")
    
    # 停止运行后面的代码
    return False

# ================= 2. 核心逻辑函数 =================

def get_db_path():
    """智能寻找数据库文件"""
    possible_paths = [
        '/app/data/investment.db', # 修正后的正确路径
        'data/investment.db',
        'investment.db'
    ]
    for p in possible_paths:
        if os.path.exists(p): return p
    # 如果找不到，搜索 data 目录下最大的 .db 文件
    if os.path.exists('/app/data'):
        files = [f for f in os.listdir('/app/data') if f.endswith('.db')]
        if files: return os.path.join('/app/data', files[0])
    return None

def load_data():
    """读取信号数据"""
    db_path = get_db_path()
    if not db_path:
        st.error("❌ 未找到数据库文件 (investment.db)，请确保机器人已运行并产生数据。")
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(db_path)

        # 🔥 修复: 检查表是否存在，以及表名兼容性
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]

        # 兼容处理：如果存在 ai_signals 表，使用它；否则使用 signals 表
        table_name = 'ai_signals' if 'ai_signals' in tables else ('signals' if 'signals' in tables else None)

        if not table_name:
            st.error("❌ 数据库中未找到信号表")
            conn.close()
            return pd.DataFrame()

        # 读取最近 200 条信号
        query = f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT 200"
        df = pd.read_sql_query(query, conn)
        conn.close()

        # 数据清洗
        if not df.empty:
            df['created_at'] = pd.to_datetime(df['created_at'])
            # 提取胜率 (从 summary 字段正则提取 "胜率65%")
            df['win_rate_val'] = df['summary'].apply(extract_win_rate)
        return df
    except Exception as e:
        st.error(f"读取数据库失败: {e}")
        return pd.DataFrame()

def extract_win_rate(text):
    """从文本中提取胜率数值 (例如 '胜率65%' -> 65)"""
    if not isinstance(text, str): return 0
    match = re.search(r"胜率(\d+)%", text)
    if match:
        return int(match.group(1))
    return 0

# ================= 3. 主界面布局 =================

def show_main_dashboard():
    st.title("📈 ValueCell AI 作战指挥室")
    st.caption("多智能体辩论 | 历史回测 | 情绪监控")

    # 1. 加载数据
    df = load_data()
    
    if df.empty:
        st.info("⏳ 暂无信号数据，请等待 AI 巡逻...")
        if st.button("手动刷新"): st.rerun()
        return

    # 2. 顶部仪表盘 (KPIs)
    col1, col2, col3, col4 = st.columns(4)

    # 计算今日信号
    today = datetime.now(pytz.timezone('Asia/Shanghai')).date()
    df_today = df[df['created_at'].dt.date == today]

    # 🔥 修复: 列名兼容性处理
    signal_col = 'signal' if 'signal' in df.columns else ('signal_type' if 'signal_type' in df.columns else None)

    with col1:
        st.metric("今日情报", f"{len(df_today)} 条", delta=f"总计 {len(df)}")
    with col2:
        # 高胜率占比
        high_win_df = df[df['win_rate_val'] > 60]
        ratio = len(high_win_df) / len(df) * 100 if len(df) > 0 else 0
        st.metric("优质机会占比", f"{ratio:.1f}%", help="历史胜率 > 60% 的信号比例")
    with col3:
        # 多头情绪 (🔥 修复: 列名兼容)
        if signal_col:
            bull_count = len(df[df[signal_col] == 'positive'])
            bear_count = len(df[df[signal_col] == 'negative'])
        else:
            bull_count = bear_count = 0
        sentiment = "偏多头 🔥" if bull_count > bear_count else "偏空头 ❄️"
        st.metric("市场AI情绪", sentiment, f"多{bull_count} : 空{bear_count}")
    with col4:
        st.metric("最新更新", df['created_at'].iloc[0].strftime("%H:%M") if not df.empty else "--:--")

    st.divider()

    # 3. 核心功能区
    tab1, tab2 = st.tabs(["🚀 核心情报流", "📊 深度数据分析"])

    with tab1:
        # 过滤器
        filter_col1, filter_col2 = st.columns([1, 3])
        with filter_col1:
            min_win = st.slider("最低历史胜率要求 (%)", 0, 100, 50)
        
        # 筛选显示
        display_df = df[df['win_rate_val'] >= min_win]
        
        for index, row in display_df.iterrows():
            # 🔥 修复: 列名兼容
            signal_value = row[signal_col] if signal_col else 'neutral'
            card_color = "🟢" if signal_value == 'positive' else "🔴" if signal_value == 'negative' else "⚪"

            # 🔥 修复: 列名兼容
            stock_code_col = 'stock_code' if 'stock_code' in row.index else ('code' if 'code' in row.index else '未知')
            news_title_col = 'news_title' if 'news_title' in row.index else ('title' if 'title' in row.index else '未知')

            with st.expander(f"{card_color} {row[stock_code_col]} | {row[news_title_col]} ({row['created_at'].strftime('%m-%d %H:%M')})"):
                
                c1, c2 = st.columns([2, 1])
                
                with c1:
                    st.markdown("#### 🧠 AI 辩论结论")
                    st.info(row['reason'])
                    st.markdown("**摘要/技术面：**")
                    st.text(row['summary'])

                with c2:
                    st.markdown("#### ⚖️ 量化评分")
                    win_rate = row['win_rate_val']
                    if win_rate > 0:
                        st.progress(win_rate / 100, text=f"历史胜率: {win_rate}%")
                        if win_rate < 40:
                            st.warning("⚠️ 警告：历史骗线概率高")
                        elif win_rate > 70:
                            st.success("🔥 极佳：历史股性活跃")
                    else:
                        st.caption("暂无回测数据")

                    # 🔥 修复: 列名兼容
                    price_col = 'price_at_signal' if 'price_at_signal' in row.index else ('price' if 'price' in row.index else '现价')
                    price_value = row[price_col] if price_col in row.index else 0

                    st.metric("现价", f"¥{price_value}")
                    confidence_col = 'confidence' if 'confidence' in row.index else None
                    if confidence_col and confidence_col in row.index:
                        st.metric("AI置信度", f"{row[confidence_col] * 100:.0f}%")

    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("AI 关注板块热力图")
            if 'concept' in df.columns: 
                concept_counts = df['concept'].value_counts().head(10)
                fig = px.bar(concept_counts, orientation='h', title="热门概念 Top 10")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("需积累更多带'概念'字段的数据后显示")
                
        with c2:
            st.subheader("置信度分布")
            fig2 = px.histogram(df, x="confidence", nbins=20, title="AI 决策置信度分布")
            st.plotly_chart(fig2, use_container_width=True)

# ================= 4. 入口函数 =================
def main():
    # 🔥 核心：先检查密码，通过了才显示主界面
    if check_password():
        show_main_dashboard()

if __name__ == "__main__":
    main()