"""
模型推理引擎。
封装 Kronos 模型的加载与推理流程，提供统一的 predict() 接口。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import streamlit as st

from src.config import (
    INPUT_WINDOW,
    MAX_CONTEXT,
    MODEL_NAME,
    OUTPUT_WINDOW,
    TOKENIZER_NAME,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_SAMPLE_COUNT,
)
from src.exceptions import ModelError


class ModelEngine:
    """Kronos 模型推理引擎（全局单例，基于 st.cache_resource）。"""

    _cold_start_ms: float | None = None

    @classmethod
    def get_last_cold_start_ms(cls) -> int:
        """返回最近一次冷启动耗时 (ms)，若尚未加载则返回 0。"""
        return int(cls._cold_start_ms) if cls._cold_start_ms is not None else 0

    @staticmethod
    @st.cache_resource
    def _load_model():
        import time as _time

        _t0 = _time.time()
        try:
            from model import Kronos, KronosPredictor, KronosTokenizer

            tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_NAME)
            model = Kronos.from_pretrained(MODEL_NAME)
            predictor = KronosPredictor(
                model,
                tokenizer,
                device="cpu",               # 强制 CPU (PRD §2.3.3)
                max_context=MAX_CONTEXT,     # 512
            )
            ModelEngine._cold_start_ms = (_time.time() - _t0) * 1000
            return predictor
        except Exception as e:
            raise ModelError(f"模型加载失败: {e}") from e

    def predict(
        self,
        x_df: pd.DataFrame,
        x_timestamp: pd.Series,
        y_timestamp: pd.Series,
        sampling=None,
    ) -> pd.DataFrame:
        """
        执行价格预测。

        Args:
            x_df: 预处理后的 (488, 6) DataFrame
            x_timestamp: 历史时间戳 Series (488,)
            y_timestamp: 未来时间戳 Series (24,)
            sampling: SamplingConfig 对象 (可选, 使用默认值)

        Returns:
            pred_df: (24, 6) DataFrame [open, high, low, close, volume, amount]

        Raises:
            ModelError: 推理过程异常
        """
        predictor = self._load_model()

        # 采样参数
        temperature = DEFAULT_TEMPERATURE
        top_p = DEFAULT_TOP_P
        sample_count = DEFAULT_SAMPLE_COUNT
        if sampling is not None:
            temperature = getattr(sampling, "temperature", DEFAULT_TEMPERATURE)
            top_p = getattr(sampling, "top_p", DEFAULT_TOP_P)
            sample_count = getattr(sampling, "sample_count", DEFAULT_SAMPLE_COUNT)

        try:
            pred_df = predictor.predict(
                df=x_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=OUTPUT_WINDOW,         # 24
                T=temperature,
                top_p=top_p,
                sample_count=sample_count,
            )
            return pred_df
        except Exception as e:
            raise ModelError(f"模型推理失败: {e}") from e
