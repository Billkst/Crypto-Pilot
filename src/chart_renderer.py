"""
图表渲染模块。
使用 Plotly 绘制专业 K 线图，展示历史数据、预测数据及回测对比。
"""
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class ChartRenderer:
    """K 线图渲染器。"""

    @staticmethod
    def render(
        hist_df: pd.DataFrame,
        pred_df: pd.DataFrame,
        backtest_df: Optional[pd.DataFrame] = None,
    ) -> go.Figure:
        """
        绘制混合 K 线图。

        Args:
            hist_df: 历史 OHLCV 数据 (DataFrame)
            pred_df: 预测 OHLCV 数据 (DataFrame)
            backtest_df: 回测/昨日预测数据 (可选, DataFrame)

        Returns:
            go.Figure: Plotly 图表对象
        """
        # 创建子图（未来可扩展成交量等）
        fig = make_subplots(
            rows=1,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
        )

        # 1. 绘制历史数据 (灰色)
        fig.add_trace(
            go.Candlestick(
                x=hist_df["timestamp"],
                open=hist_df["open"],
                high=hist_df["high"],
                low=hist_df["low"],
                close=hist_df["close"],
                name="历史数据",
                increasing_line_color="gray",
                decreasing_line_color="gray",
                increasing_fillcolor="gray",
                decreasing_fillcolor="gray",
                opacity=0.6,
            )
        )

        # 2. 绘制预测数据 (蓝色)
        # 确保预测线的第一个点与历史数据的最后一个点在视觉上连续
        # 注意: pred_df 的 timestamp 应该是未来的, 这里主要关注样式
        fig.add_trace(
            go.Candlestick(
                x=pred_df["timestamp"],
                open=pred_df["open"],
                high=pred_df["high"],
                low=pred_df["low"],
                close=pred_df["close"],
                name="预测数据",
                increasing_line_color="#1f77b4",  # 蓝色
                decreasing_line_color="#1f77b4",
                increasing_fillcolor="#1f77b4",
                decreasing_fillcolor="#1f77b4",
            )
        )

        # 3. 绘制预测连接线 (可选优化视觉)
        # 如果需要更强的连接感，可以添加一条线连接 History Last Close -> Pred First Open
        # 但标准 Candlestick 图通常不需要，除非时间轴不连续

        # 4. 绘制回测/昨日预测 (虚线框/透明度处理)
        if backtest_df is not None and not backtest_df.empty:
            fig.add_trace(
                go.Candlestick(
                    x=backtest_df["timestamp"],
                    open=backtest_df["open"],
                    high=backtest_df["high"],
                    low=backtest_df["low"],
                    close=backtest_df["close"],
                    name="昨日预测 (回测)",
                    increasing_line_color="orange",
                    decreasing_line_color="orange",
                    increasing_line_dash="dot",  # 虚线样式 (Plotly Candlestick 仅支持部分线条样式，这里主要靠颜色区分)
                    decreasing_line_dash="dot",
                    opacity=0.7,
                )
            )

        # 5. 布局美化
        fig.update_layout(
            title="Crypto-Pilot 趋势预测",
            yaxis_title="价格 (USDT)",
            xaxis_title="时间",
            template="plotly_dark",
            xaxis_rangeslider_visible=False,  # 隐藏下方滑动条
            hovermode="x unified",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            margin=dict(l=20, r=20, t=60, b=20),
        )

        # 添加垂直分割线 (当前时间)
        # 必须转为毫秒级 Unix 时间戳，避免 Pandas 2.x Timestamp 与整数运算的兼容性问题
        last_hist_ts = hist_df["timestamp"].iloc[-1]
        split_x = last_hist_ts.timestamp() * 1000
        fig.add_vline(
            x=split_x,
            line_width=1,
            line_dash="dash",
            line_color="white",
            annotation_text="Current Time",
            annotation_position="top left"
        )

        return fig
