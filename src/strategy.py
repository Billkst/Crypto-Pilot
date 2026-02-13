"""
策略分析引擎。
根据模型预测结果与用户配置，生成交易信号和止损价位。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.config import (
    DEFAULT_SAMPLE_COUNT,
    DEFAULT_STOP_LOSS,
    DEFAULT_SYMBOL,
    DEFAULT_TEMPERATURE,
    DEFAULT_THRESHOLD,
    DEFAULT_TOP_P,
)


# ──────────── 数据类定义 ────────────


@dataclass
class SamplingConfig:
    """模型采样参数。"""

    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    sample_count: int = DEFAULT_SAMPLE_COUNT


@dataclass
class UserConfig:
    """用户配置（Sidebar 所有参数的聚合）。"""

    symbol: str = DEFAULT_SYMBOL
    threshold: float = DEFAULT_THRESHOLD       # 信号触发阈值 (%)
    stop_loss_pct: float = DEFAULT_STOP_LOSS   # 止损百分比 (%)
    sampling: SamplingConfig = field(default_factory=SamplingConfig)


@dataclass
class SignalResult:
    """策略分析结果。"""

    current_price: float
    predicted_price: float
    expected_return: float
    signal: str            # "Bullish" | "Bearish" | "Neutral"
    signal_emoji: str      # "🟢" | "🔴" | "🟡"
    stop_loss_price: Optional[float]


# ──────────── 策略引擎 ────────────


class StrategyEngine:
    """策略计算引擎。"""

    @staticmethod
    def analyze(
        current_price: float,
        pred_df: pd.DataFrame,
        config: UserConfig,
    ) -> SignalResult:
        """
        策略分析主逻辑。

        Args:
            current_price: 历史数据最后一行的 close 价格
            pred_df: 模型输出的 24 行预测 DataFrame
            config: 用户配置 (含 threshold, stop_loss_pct)

        Returns:
            SignalResult: 完整的信号分析结果
        """
        # Step 1: 提取预测终点价格
        predicted_price = float(pred_df["close"].iloc[-1])

        # Step 2: 计算预期收益率
        expected_return = (predicted_price - current_price) / current_price

        # Step 3: 信号判定（阈值从百分比转小数）
        threshold = config.threshold / 100.0

        if expected_return > threshold:
            signal = "Bullish"
            signal_emoji = "🟢"
        elif expected_return < -threshold:
            signal = "Bearish"
            signal_emoji = "🔴"
        else:
            signal = "Neutral"
            signal_emoji = "🟡"

        # Step 4: 止损价位计算
        stop_loss_pct = config.stop_loss_pct / 100.0

        if signal == "Bullish":
            stop_loss_price = current_price * (1 - stop_loss_pct)
        elif signal == "Bearish":
            stop_loss_price = current_price * (1 + stop_loss_pct)
        else:
            stop_loss_price = None

        return SignalResult(
            current_price=current_price,
            predicted_price=predicted_price,
            expected_return=expected_return,
            signal=signal,
            signal_emoji=signal_emoji,
            stop_loss_price=stop_loss_price,
        )
