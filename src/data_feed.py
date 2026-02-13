"""
数据采集与预处理模块。
通过 ccxt 获取 Binance OHLCV 数据，实施缓存策略，执行数据预处理流水线。
"""
import time
from datetime import timedelta
from typing import Tuple

import ccxt
import pandas as pd

from src.cache_manager import CacheManager
from src.config import (
    EXCHANGE_ID,
    FETCH_LIMIT,
    INPUT_WINDOW,
    MAX_RETRIES,
    OUTPUT_WINDOW,
    TIMEFRAME,
)
from src.exceptions import DataFeedError


class DataFeed:
    """数据采集与预处理引擎。"""

    def __init__(self, cache_manager: CacheManager | None = None):
        self.exchange = getattr(ccxt, EXCHANGE_ID)({"enableRateLimit": True})
        self.cache_manager = cache_manager or CacheManager()

    # ──────────── 数据拉取 ────────────

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = TIMEFRAME,
        limit: int = FETCH_LIMIT,
    ) -> pd.DataFrame:
        """
        带指数退避重试与 L2 磁盘缓存的 OHLCV 数据拉取。

        Args:
            symbol: 交易对, e.g. "BTC/USDT"
            timeframe: K 线周期, 默认 "1h"
            limit: 拉取条数上限, 默认 500

        Returns:
            原始 OHLCV DataFrame (列: timestamp, open, high, low, close, volume)

        Raises:
            DataFeedError: 无效的交易对 / 网络/API 错误
        """
        cache_key = f"{symbol}_{timeframe}"

        # L2 缓存检查
        cached_df = self.cache_manager.get(cache_key)
        if cached_df is not None:
            return cached_df

        # 网络请求（指数退避重试）
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                df = pd.DataFrame(
                    ohlcv,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )
                # 写入 L2 缓存
                self.cache_manager.set(cache_key, df)
                return df

            except ccxt.BadSymbol as e:
                raise DataFeedError(f"无效的交易对: {symbol}") from e
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2**attempt)  # 1s, 2s, 4s

        raise DataFeedError(f"无法获取 {symbol} 数据（重试 {MAX_RETRIES} 次后失败）: {last_error}")

    # ──────────── 数据预处理 ────────────

    def preprocess(
        self, raw_df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
        """
        数据预处理流水线。

        Steps:
            1. 列名标准化
            2. 时间戳类型转换
            3. amount 字段填充
            4. NaN 处理 (ffill + bfill)
            5. 数据量校验 (>= INPUT_WINDOW)
            6. 截取最近 488 行
            7. 分离 x_timestamp 与 x_df
            8. 生成 y_timestamp (未来 24h)

        Args:
            raw_df: fetch_ohlcv() 返回的原始 DataFrame

        Returns:
            (x_df, x_timestamp, y_timestamp):
                x_df       — (488, 6) DataFrame [open, high, low, close, volume, amount]
                x_timestamp — (488,) Datetime Series
                y_timestamp — (24,) Datetime Series

        Raises:
            DataFeedError: 数据量不足 488 行
        """
        df = raw_df.copy()

        # Step 1: 列名标准化
        df.columns = ["timestamp", "open", "high", "low", "close", "volume"]

        # Step 2: 时间戳类型转换
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # Step 3: amount 字段填充
        df["amount"] = df["close"] * df["volume"]

        # Step 4: NaN 处理
        df = df.ffill().bfill()

        # Step 5: 数据量校验
        if len(df) < INPUT_WINDOW:
            raise DataFeedError(
                f"数据量不足: 需要 {INPUT_WINDOW} 行, 实际 {len(df)} 行"
            )

        # Step 6: 截取最近 488 行
        df = df.tail(INPUT_WINDOW).reset_index(drop=True)

        # Step 7: 分离 timestamp 与特征列
        x_timestamp = df["timestamp"]
        x_df = df[["open", "high", "low", "close", "volume", "amount"]]

        # Step 8: 生成未来 24h 时间戳
        last_ts = x_timestamp.iloc[-1]
        y_timestamp = pd.Series(
            [last_ts + timedelta(hours=i + 1) for i in range(OUTPUT_WINDOW)]
        )

        return x_df, x_timestamp, y_timestamp
