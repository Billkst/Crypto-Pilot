"""
Crypto-Pilot 主应用程序。
Streamlit 入口文件，负责 UI 布局、状态管理与核心流程串联。
"""
import sys
import os
import time

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
from src.metrics import MetricsTracker

# ──────────── 全局指标追踪器 ────────────

_metrics = MetricsTracker()


# ──────────── 初始化与配置 ────────────

def setup_page():
    """配置页面基本信息。"""
    st.set_page_config(
        page_title="Crypto-Pilot",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded",
    )
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
    if "hist_df" not in st.session_state:
        st.session_state.hist_df = None
    if "pred_df" not in st.session_state:
        st.session_state.pred_df = None
    if "signal_result" not in st.session_state:
        st.session_state.signal_result = None
    if "is_predicting" not in st.session_state:
        st.session_state.is_predicting = False

    # 首次加载时尝试回填到期记录 (静默)
    if "backfill_attempted" not in st.session_state:
        try:
            _metrics.backfill_actual_prices()
        except Exception:
            pass
        st.session_state.backfill_attempted = True


# ──────────── UI 组件渲染 ────────────

def render_sidebar() -> UserConfig:
    """渲染侧边栏并返回用户配置。"""
    st.sidebar.title("🚀 Crypto-Pilot")
    st.sidebar.markdown("---")

    st.sidebar.subheader("⚙️ 交易参数")
    symbol = st.sidebar.text_input("交易对 (Symbol)", value=DEFAULT_SYMBOL).upper()

    threshold = st.sidebar.slider(
        "信号阈值 (Threshold %)",
        min_value=0.5, max_value=10.0,
        value=DEFAULT_THRESHOLD, step=0.5,
        help="触发 Bullish/Bearish 信号的预期盈亏阈值"
    )

    stop_loss = st.sidebar.slider(
        "止损比例 (Stop Loss %)",
        min_value=1.0, max_value=10.0,
        value=DEFAULT_STOP_LOSS, step=0.5,
        help="建议的止损百分比"
    )

    with st.sidebar.expander("🛠️ 高级模型设置 (Advanced)"):
        temperature = st.slider("Temperature", 0.1, 2.0, DEFAULT_TEMPERATURE, 0.1)
        top_p = st.slider("Top P", 0.1, 1.0, DEFAULT_TOP_P, 0.05)
        sample_count = st.number_input("采样次数 (Samples)", 1, 10, DEFAULT_SAMPLE_COUNT)

    sampling_config = SamplingConfig(
        temperature=temperature, top_p=top_p, sample_count=sample_count
    )

    user_config = UserConfig(
        symbol=symbol, threshold=threshold,
        stop_loss_pct=stop_loss, sampling=sampling_config
    )

    st.sidebar.markdown("---")

    if st.sidebar.button("开始预测 (Start Prediction) 🚀", type="primary"):
        st.session_state.is_predicting = True

    return user_config


def render_kpi_cards(result: SignalResult):
    """渲染关键指标卡片。"""
    cols = st.columns(4)

    with cols[0]:
        st.metric(label="当前价格", value=f"${result.current_price:,.2f}")

    with cols[1]:
        st.metric(
            label="预测价格 (24h)",
            value=f"${result.predicted_price:,.2f}",
            delta=f"{result.expected_return*100:+.2f}%"
        )

    with cols[2]:
        st.metric(label="交易信号", value=f"{result.signal} {result.signal_emoji}")

    with cols[3]:
        sl_text = f"${result.stop_loss_price:,.2f}" if result.stop_loss_price else "N/A"
        st.metric(label="建议止损", value=sl_text)


# ──────────── Status Tab ────────────

def render_status_tab():
    """渲染系统状态 Tab 的全部内容。"""

    # ── 预测准确率 ──
    st.subheader("🎯 预测准确率")
    acc = _metrics.get_direction_accuracy()
    wr = _metrics.get_win_rate()
    stats = _metrics.get_prediction_stats()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        acc_val = f"{acc['accuracy_pct']}%" if acc["accuracy_pct"] is not None else "—"
        st.metric("方向准确率", acc_val, help="预测涨跌方向正确的比例")
    with c2:
        wr_val = f"{wr['win_rate_pct']}%" if wr["win_rate_pct"] is not None else "—"
        st.metric("信号胜率", wr_val, help="Bullish 且实际涨 / Bearish 且实际跌")
    with c3:
        st.metric("预测总次数", str(stats["total"]) if stats["total"] > 0 else "—")
    with c4:
        st.metric("待回填", str(stats["pending"]) if stats["total"] > 0 else "—")

    acc_source = acc.get("source")
    if acc_source == "benchmark":
        st.caption("数据来源: 基准报告 (自有数据积累中，满 10 条后自动切换)")
    elif acc_source is None:
        st.info("数据将随着使用自动积累。运行 `python tools/backtest_simulate.py` 可生成基准报告。")
    else:
        st.caption(f"基于最近 {acc['sample_count']} 条自有预测记录")

    st.markdown("---")

    # ── 响应时间 ──
    st.subheader("⏱️ 响应时间")
    timing = _metrics.get_avg_timing()

    c1, c2, c3 = st.columns(3)
    with c1:
        cold_val = f"{timing['cold_start_ms']/1000:.1f}s" if timing["cold_start_ms"] else "—"
        st.metric("模型加载 (冷启动)", cold_val)
    with c2:
        inf_val = f"{timing['inference_ms']/1000:.1f}s" if timing["inference_ms"] else "—"
        helper = f"平均 (N={timing['sample_count']})" if timing["sample_count"] > 0 else ""
        st.metric("推理 (热缓存)", inf_val, help=helper)
    with c3:
        fetch_val = f"{timing['data_fetch_ms']/1000:.1f}s" if timing["data_fetch_ms"] else "—"
        st.metric("数据拉取", fetch_val)

    if timing["sample_count"] == 0:
        st.caption("尚未采集到计时数据，完成一次预测后自动记录。")

    st.markdown("---")

    # ── 覆盖币对 ──
    st.subheader("🪙 覆盖币对")
    benchmarks = _metrics.get_benchmark_history()
    if benchmarks:
        tested = sorted(set(b["symbol"] for b in benchmarks))
        st.markdown(f"**已测试**: {', '.join(tested)}")
    else:
        st.markdown("**已测试**: 尚未运行基准测试 (`tools/backtest_simulate.py`)")
    st.caption("**支持**: 所有 Binance 现货交易对 (动态，无固定上限)")

    latest_bench = benchmarks[0] if benchmarks else None
    if latest_bench:
        st.caption(f"基准报告: `docs/BENCHMARK.md` ({latest_bench['run_at'][:10]})")

    st.markdown("---")

    # ── 测试状态 ──
    st.subheader("🧪 测试状态")
    tr = _metrics.get_latest_test_run()

    c1, c2, c3 = st.columns(3)
    if tr:
        unit_icon = "✅" if tr["unit_passed"] == tr["unit_total"] else "❌"
        with c1:
            st.metric("单元测试", f"{tr['unit_passed']}/{tr['unit_total']} {unit_icon}")
        e2e_icon = "✅" if tr["e2e_passed"] == tr["e2e_total"] else ("⬜" if tr["e2e_passed"] < 0 else "❌")
        with c2:
            e2e_label = "跳过" if tr["e2e_passed"] < 0 else f"{tr['e2e_passed']}/{tr['e2e_total']}"
            st.metric("E2E 测试", f"{e2e_label} {e2e_icon}")
        with c3:
            st.metric("最后运行", tr["run_at"][:10])
    else:
        with c1:
            st.metric("单元测试", "—")
        with c2:
            st.metric("E2E 测试", "—")
        with c3:
            st.metric("最后运行", "—")
        st.caption("运行 `python tools/record_test_run.py` 记录测试状态。")


# ──────────── 主入口 ────────────

def main():
    setup_page()
    init_session_state()

    user_config = render_sidebar()

    tab1, tab2 = st.tabs(["📊 市场预测", "📈 系统状态"])

    with tab1:
        st.header(f"📊 {user_config.symbol} 市场预测")

        if st.session_state.is_predicting:
            st.session_state.is_predicting = False

            with st.spinner(f"正在分析 {user_config.symbol} 市场数据..."):
                try:
                    # 1. 实例化引擎
                    data_feed = DataFeed()
                    model_engine = ModelEngine()

                    # 2. 获取数据 (计时)
                    t0 = time.time()
                    raw_df = data_feed.fetch_ohlcv(user_config.symbol)
                    x_df, x_timestamp, y_timestamp = data_feed.preprocess(raw_df)
                    t1 = time.time()

                    # 3. 模型推理 (计时)
                    pred_df = model_engine.predict(
                        x_df, x_timestamp, y_timestamp,
                        sampling=user_config.sampling
                    )
                    pred_df["timestamp"] = y_timestamp.values
                    t2 = time.time()

                    # 4. 策略分析
                    current_price = x_df["close"].iloc[-1]
                    viz_hist_df = x_df.copy()
                    viz_hist_df["timestamp"] = x_timestamp.values

                    result = StrategyEngine.analyze(current_price, pred_df, user_config)

                    # 5. 记录指标
                    cold_start_ms = ModelEngine.get_last_cold_start_ms()
                    data_fetch_ms = int((t1 - t0) * 1000)
                    inference_ms = int((t2 - t1) * 1000) - cold_start_ms

                    _metrics.record_prediction(
                        symbol=user_config.symbol,
                        current_price=current_price,
                        predicted_price=result.predicted_price,
                        expected_return=result.expected_return,
                        signal=result.signal,
                        cold_start_ms=cold_start_ms,
                        inference_ms=max(inference_ms, 0),
                        data_fetch_ms=data_fetch_ms,
                    )

                    # 6. 更新 Session State
                    st.session_state.hist_df = viz_hist_df
                    st.session_state.pred_df = pred_df
                    st.session_state.signal_result = result

                    st.success("预测完成！")

                except CryptoPilotError as e:
                    st.error(f"分析过程中发生错误: {e}")
                except Exception as e:
                    st.error(f"未知错误: {e}")
                    st.exception(e)

        # 渲染结果
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

                with st.expander("查看详细预测数据"):
                    st.dataframe(st.session_state.pred_df)
        else:
            st.info("👈 请在侧边栏配置参数并点击 '开始预测' 按钮。")

    with tab2:
        render_status_tab()


if __name__ == "__main__":
    main()
