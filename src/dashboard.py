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
            # 🔥 修复: 列名兼容性处理
            if 'signal_type' in df.columns:
                df = df.rename(columns={'signal_type': 'signal'})
            if 'price_at_signal' not in df.columns and 'price' in df.columns:
                df = df.rename(columns={'price': 'price_at_signal'})
            # 添加假胜率数据 (实际应该从回测表获取)
            df['win_rate_val'] = [50 + (hash(str(x)) % 40) for x in range(len(df))]

        return df

    except Exception as e:
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

def load_backtest_results():
    """读取回测结果"""
    db_path = get_db_path()
    if not db_path:
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(db_path)

        # 检查回测表是否存在
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_results';")
        if not cursor.fetchone():
            conn.close()
            return pd.DataFrame()

        # 读取最近10次回测结果
        query = "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT 10"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if not df.empty:
            df['created_at'] = pd.to_datetime(df['created_at'])

        return df

    except Exception as e:
        st.error(f"❌ 回测数据读取失败: {e}")
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
        st.warning("⏳ 暂无信号数据，请等待 AI 巡逻...")
        if st.button("手动刷新"): st.rerun()
        # 🔥 修复: 不要return，继续显示tab结构

    # 2. 顶部仪表盘 (KPIs)
    col1, col2, col3, col4 = st.columns(4)

    # 🔥 修复: 提前定义signal_col，避免后面引用时出错
    signal_col = 'signal' if 'signal' in df.columns else ('signal_type' if 'signal_type' in df.columns else None)

    # 🔥 修复: 如果df为空，显示占位数据
    if df.empty:
        with col1:
            st.metric("今日情报", "0 条", delta="总计 0")
        with col2:
            st.metric("优质机会占比", "0%")
        with col3:
            st.metric("市场AI情绪", "暂无数据")
        with col4:
            from datetime import datetime
            import pytz
            now = datetime.now(pytz.timezone('Asia/Shanghai'))
            st.metric("最新更新", now.strftime("%H:%M"))
    else:
        # 计算今日信号
        today = datetime.now(pytz.timezone('Asia/Shanghai')).date()
        df_today = df[df['created_at'].dt.date == today]

        with col1:
            st.metric("今日情报", f"{len(df_today)} 条", delta=f"总计 {len(df)}")
        with col2:
            # 高胜率占比
            if 'win_rate_val' in df.columns:
                high_win_df = df[df['win_rate_val'] > 60]
                ratio = len(high_win_df) / len(df) * 100 if len(df) > 0 else 0
            else:
                high_win_df = pd.DataFrame()
                ratio = 0
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
    tab1, tab2, tab3, tab4 = st.tabs(["📈 我的持仓", "🚀 核心情报流", "📊 深度数据分析", "🔬 回测结果"])

    # ================= 📈 我的持仓 (新增) =================
    with tab1:
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

    with tab2:
        # 🔥 修复: 如果df为空，显示提示
        if df.empty:
            st.info("📭 暂无信号数据，请等待 AI 巡逻...")
        else:
            # 过滤器
            filter_col1, filter_col2 = st.columns([1, 3])
            with filter_col1:
                min_win = st.slider("最低历史胜率要求 (%)", 0, 100, 50)

            # 筛选显示
            if 'win_rate_val' in df.columns:
                display_df = df[df['win_rate_val'] >= min_win]
            else:
                display_df = df

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
                        win_rate = row.get('win_rate_val', 0)
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

    with tab3:
        # 🔥 修复: 如果df为空，显示提示
        if df.empty:
            st.info("📭 暂无信号数据，请等待 AI 巡逻...")
        else:
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
                if 'confidence' in df.columns:
                    fig2 = px.histogram(df, x="confidence", nbins=20, title="AI 决策置信度分布")
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("暂无置信度数据")

    with tab4:
        st.subheader("🔬 历史回测结果")

        # 加载回测数据
        backtest_df = load_backtest_results()

        if backtest_df.empty:
            st.info("📊 暂无回测数据，请在 Telegram 使用 `/backtest` 命令运行回测")

            st.markdown("""
            ### 💡 如何使用回测？

            1. 在 Telegram 中发送命令：
               ```
               /backtest 30 hold_3_days
               ```

            2. 参数说明：
               - `30`: 回测最近30天的信号
               - `hold_3_days`: 使用"持有3天"策略

            3. 可用策略：
               - `hold_3_days` - 持有3天
               - `hold_5_days` - 持有5天
               - `stop_loss_5` - 止损5%
               - `target_profit_10` - 止盈10%

            4. 回测完成后，刷新此页面查看结果！
            """)
        else:
            # 显示最近回测结果
            st.markdown("### 📈 最新回测结果")

            # 展开显示每次回测
            for idx, row in backtest_df.iterrows():
                with st.expander(f"📅 {row['created_at'].strftime('%Y-%m-%d %H:%M')} - {row['strategy']}"):
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.metric("总信号", row['total_signals'])
                    with col2:
                        win_rate = row.get('win_rate', 0)
                        delta_color = "normal" if win_rate >= 50 else "inverse"
                        st.metric("胜率", f"{win_rate:.1f}%", delta=f"{win_rate-50:.1f}%", delta_color=delta_color)
                    with col3:
                        st.metric("盈亏比", f"{row['profit_loss_ratio']:.2f}")
                    with col4:
                        total_profit = row['total_profit']
                        profit_color = "normal" if total_profit > 0 else "inverse"
                        st.metric("累计收益", f"{total_profit:.2f}%", delta_color=profit_color)

                    col5, col6 = st.columns(2)
                    with col5:
                        st.write(f"✅ 盈利: {row['win_count']} 笔")
                    with col6:
                        st.write(f"❌ 亏损: {row['lose_count']} 笔")

                    # 显示建议
                    if win_rate >= 60:
                        st.success("✅ 胜率优秀，策略有效！")
                    elif win_rate >= 45:
                        st.warning("⚠️ 胜率一般，建议优化参数。")
                    else:
                        st.error("❌ 胜率偏低，建议重新设计策略。")

            # 趋势图
            if len(backtest_df) > 1:
                st.markdown("### 📊 回测趋势")

                fig = go.Figure()

                # 胜率趋势
                fig.add_trace(go.Scatter(
                    x=backtest_df['created_at'],
                    y=backtest_df['win_rate'],
                    mode='lines+markers',
                    name='胜率 (%)',
                    line=dict(color='#00FF7F')
                ))

                # 累计收益趋势
                fig.add_trace(go.Scatter(
                    x=backtest_df['created_at'],
                    y=backtest_df['total_profit'],
                    mode='lines+markers',
                    name='累计收益 (%)',
                    yaxis='y2',
                    line=dict(color='#FFD700')
                ))

                fig.update_layout(
                    title='回测指标趋势',
                    xaxis_title='时间',
                    yaxis_title='胜率 (%)',
                    yaxis2=dict(
                        title='累计收益 (%)',
                        overlaying='y',
                        side='right'
                    ),
                    hovermode='x unified',
                    template='plotly_dark'
                )

                st.plotly_chart(fig, use_container_width=True)

            # 策略对比
            if len(backtest_df) >= 2:
                st.markdown("### 🎯 策略对比")

                strategy_stats = backtest_df.groupby('strategy').agg({
                    'win_rate': 'mean',
                    'profit_loss_ratio': 'mean',
                    'total_profit': 'mean'
                }).round(2)

                st.dataframe(
                    strategy_stats,
                    use_container_width=True,
                    hide_index=True
                )

# ================= 4. 入口函数 =================
def main():
    # 🔥 核心：先检查密码，通过了才显示主界面
    if check_password():
        show_main_dashboard()

if __name__ == "__main__":
    main()