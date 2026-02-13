"""
Crypto-Pilot 主应用程序。
Streamlit 入口文件，负责 UI 布局、状态管理与核心流程串联。
"""
import sys
import os

# 将项目根目录添加到 python path，确保能导入 src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import streamlit as st

from src.config import (
    DEFAULT_SYMBOL,
    DEFAULT_THRESHOLD,
    DEFAULT_STOP_LOSS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_SAMPLE_COUNT,
)
from src.data_feed import DataFeed
from src.model_engine import ModelEngine
from src.strategy import StrategyEngine, UserConfig, SamplingConfig, SignalResult
from src.chart_renderer import ChartRenderer
from src.exceptions import CryptoPilotError


# ──────────── 初始化与配置 ────────────

def setup_page():
    """配置页面基本信息。"""
    st.set_page_config(
        page_title="Crypto-Pilot",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    # 自定义简易 CSS 样式
    st.markdown("""
        <style>
        .stMetric {
            background-color: #1E1E1E;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #333;
        }
        </style>
    """, unsafe_allow_html=True)


def init_session_state():
    """初始化 Session State 变量。"""
    # 数据相关
    if "hist_df" not in st.session_state:
        st.session_state.hist_df = None
    if "pred_df" not in st.session_state:
        st.session_state.pred_df = None
    if "signal_result" not in st.session_state:
        st.session_state.signal_result = None  # type: SignalResult | None
    
    # 状态标记
    if "is_predicting" not in st.session_state:
        st.session_state.is_predicting = False


# ──────────── UI 组件渲染 ────────────

def render_sidebar() -> UserConfig:
    """渲染侧边栏并返回用户配置。"""
    st.sidebar.title("🚀 Crypto-Pilot")
    st.sidebar.markdown("---")

    # 基础配置
    st.sidebar.subheader("⚙️ 交易参数")
    symbol = st.sidebar.text_input("交易对 (Symbol)", value=DEFAULT_SYMBOL).upper()
    
    threshold = st.sidebar.slider(
        "信号阈值 (Threshold %)",
        min_value=0.5,
        max_value=10.0,
        value=DEFAULT_THRESHOLD,
        step=0.5,
        help="触发 Bullish/Bearish 信号的预期盈亏阈值"
    )
    
    stop_loss = st.sidebar.slider(
        "止损比例 (Stop Loss %)",
        min_value=1.0,
        max_value=10.0,
        value=DEFAULT_STOP_LOSS,
        step=0.5,
        help="建议的止损百分比"
    )

    # 高级配置 (模型参数)
    with st.sidebar.expander("🛠️ 高级模型设置 (Advanced)"):
        temperature = st.slider("Temperature", 0.1, 2.0, DEFAULT_TEMPERATURE, 0.1)
        top_p = st.slider("Top P", 0.1, 1.0, DEFAULT_TOP_P, 0.05)
        sample_count = st.number_input("采样次数 (Samples)", 1, 10, DEFAULT_SAMPLE_COUNT)

    # 组装配置对象
    sampling_config = SamplingConfig(
        temperature=temperature,
        top_p=top_p,
        sample_count=sample_count
    )
    
    user_config = UserConfig(
        symbol=symbol,
        threshold=threshold,
        stop_loss_pct=stop_loss,
        sampling=sampling_config
    )

    st.sidebar.markdown("---")
    
    # 行动按钮
    if st.sidebar.button("开始预测 (Start Prediction) 🚀", type="primary"):
        st.session_state.is_predicting = True
    
    return user_config


def render_kpi_cards(result: SignalResult):
    """渲染关键指标卡片。"""
    cols = st.columns(4)
    
    with cols[0]:
        st.metric(
            label="当前价格",
            value=f"${result.current_price:,.2f}"
        )
    
    with cols[1]:
        delta_color = "normal"
        if result.expected_return > 0:
            delta_color = "normal"  # Streamlit default green/red handled by sign? 
            # actually st.metric delta logic: green if +, red if -
        
        st.metric(
            label="预测价格 (24h)",
            value=f"${result.predicted_price:,.2f}",
            delta=f"{result.expected_return*100:+.2f}%"
        )
        
    with cols[2]:
        st.metric(
            label="交易信号",
            value=f"{result.signal} {result.signal_emoji}"
        )
        
    with cols[3]:
        sl_text = f"${result.stop_loss_price:,.2f}" if result.stop_loss_price else "N/A"
        st.metric(
            label="建议止损",
            value=sl_text
        )


def main():
    setup_page()
    init_session_state()
    
    user_config = render_sidebar()

    # 主区域
    st.title(f"📊 {user_config.symbol} 市场预测")

    # 处理预测逻辑
    if st.session_state.is_predicting:
        st.session_state.is_predicting = False  # Reset flag
        
        with st.spinner(f"正在分析 {user_config.symbol} 市场数据..."):
            try:
                # 1. 实例化引擎
                data_feed = DataFeed()
                model_engine = ModelEngine()
                
                # 2. 获取数据
                raw_df = data_feed.fetch_ohlcv(user_config.symbol)
                x_df, x_timestamp, y_timestamp = data_feed.preprocess(raw_df)
                
                # 3. 模型推理
                pred_df = model_engine.predict(
                    x_df, 
                    x_timestamp, 
                    y_timestamp, 
                    sampling=user_config.sampling
                )
                pred_df["timestamp"] = y_timestamp.values  # .values 避免 index 不对齐导致 NaN
                
                # 4. 策略分析
                current_price = x_df["close"].iloc[-1]
                
                # 重新构建用于图表显示的历史数据 (含 timestamp)
                # preprocess 返回的 x_df 没有 timestamp 列 (被分离了)，这里需要还原一下用于绘图
                # 或者直接使用 raw_df，但 raw_df 可能包含多余数据，且列名标准化是在 preprocess 中做的
                # 最简单是重新组合一下，或者直接用 preprocess 返回的部件
                viz_hist_df = x_df.copy()
                viz_hist_df["timestamp"] = x_timestamp.values  # .values 避免 index 不对齐
                
                result = StrategyEngine.analyze(current_price, pred_df, user_config)
                
                # 5. 更新 Session State
                st.session_state.hist_df = viz_hist_df
                st.session_state.pred_df = pred_df
                st.session_state.signal_result = result
                
                st.success("预测完成！")
                
            except CryptoPilotError as e:
                st.error(f"分析过程中发生错误: {e}")
            except Exception as e:
                st.error(f"未知错误: {e}")
                # 在开发阶段通过 st.exception 显示堆栈
                st.exception(e)

    # 渲染结果 (如果有)
    if st.session_state.signal_result is not None:
        st.markdown("### 📈 市场洞察")
        render_kpi_cards(st.session_state.signal_result)
        
        st.markdown("### 🕯️ 价格走势预测")
        if st.session_state.hist_df is not None and st.session_state.pred_df is not None:
            fig = ChartRenderer.render(
                st.session_state.hist_df,
                st.session_state.pred_df
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # 显示详细数据 Expander
            with st.expander("查看详细预测数据"):
                st.dataframe(st.session_state.pred_df)
    else:
        st.info("👈 请在侧边栏配置参数并点击 '开始预测' 按钮。")


if __name__ == "__main__":
    main()
