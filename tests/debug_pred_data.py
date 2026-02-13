"""
调试脚本：检查 pred_df 的实际内容和 timestamp 列。
"""
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from src.data_feed import DataFeed
from src.model_engine import ModelEngine

# 模拟 st.cache_resource (避免 Streamlit 依赖)
import unittest.mock as mock
import streamlit as st

def main():
    print("=" * 60)
    print("  调试 pred_df 数据内容")
    print("=" * 60)

    # 1. 获取数据
    print("\n[1] 获取 ETH/USDT 数据...")
    data_feed = DataFeed()
    raw_df = data_feed.fetch_ohlcv("ETH/USDT")
    print(f"  raw_df shape: {raw_df.shape}")
    print(f"  raw_df columns: {list(raw_df.columns)}")

    # 2. 预处理
    print("\n[2] 预处理...")
    x_df, x_timestamp, y_timestamp = data_feed.preprocess(raw_df)
    print(f"  x_df shape: {x_df.shape}")
    print(f"  x_df columns: {list(x_df.columns)}")
    print(f"  x_timestamp shape: {x_timestamp.shape}")
    print(f"  x_timestamp 前3个: {x_timestamp.head(3).tolist()}")
    print(f"  x_timestamp 后3个: {x_timestamp.tail(3).tolist()}")
    print(f"  y_timestamp shape: {y_timestamp.shape}")
    print(f"  y_timestamp 前3个: {y_timestamp.head(3).tolist()}")
    print(f"  y_timestamp 后3个: {y_timestamp.tail(3).tolist()}")

    # 3. 模型推理
    print("\n[3] 模型推理...")
    model_engine = ModelEngine()
    pred_df = model_engine.predict(x_df, x_timestamp, y_timestamp)
    print(f"  pred_df shape: {pred_df.shape}")
    print(f"  pred_df columns: {list(pred_df.columns)}")
    print(f"  pred_df dtypes:\n{pred_df.dtypes}")
    print(f"\n  pred_df 完整内容:")
    print(pred_df.to_string())

    # 4. 模拟 app.py 中的 timestamp 赋值
    pred_df["timestamp"] = y_timestamp
    print(f"\n[4] 赋值 timestamp 后:")
    print(f"  pred_df columns: {list(pred_df.columns)}")
    print(f"  pred_df['timestamp'] dtype: {pred_df['timestamp'].dtype}")
    print(f"  pred_df['timestamp'] 内容:")
    print(pred_df["timestamp"].tolist())

    # 5. 比较历史和预测的时间范围
    print(f"\n[5] 时间范围对比:")
    print(f"  历史数据: {x_timestamp.iloc[0]} ~ {x_timestamp.iloc[-1]}")
    print(f"  预测数据: {pred_df['timestamp'].iloc[0]} ~ {pred_df['timestamp'].iloc[-1]}")

    # 6. 模拟 chart_renderer 中的 hist_df 构建
    viz_hist_df = x_df.copy()
    viz_hist_df["timestamp"] = x_timestamp
    print(f"\n[6] viz_hist_df 构建:")
    print(f"  viz_hist_df shape: {viz_hist_df.shape}")
    print(f"  viz_hist_df columns: {list(viz_hist_df.columns)}")
    print(f"  viz_hist_df['timestamp'] 后3个: {viz_hist_df['timestamp'].tail(3).tolist()}")

    # 7. 检查 pred_df 的 OHLC 值是否合理
    print(f"\n[7] pred_df OHLC 值范围:")
    for col in ["open", "high", "low", "close"]:
        if col in pred_df.columns:
            print(f"  {col}: min={pred_df[col].min():.4f}, max={pred_df[col].max():.4f}, mean={pred_df[col].mean():.4f}")
        else:
            print(f"  ❌ 列 '{col}' 不存在!")

    # 8. 检查 pred_df 的 index 是否与 y_timestamp 的 index 对齐
    print(f"\n[8] Index 对齐检查:")
    print(f"  pred_df.index: {pred_df.index.tolist()}")
    print(f"  y_timestamp.index: {y_timestamp.index.tolist()}")
    print(f"  对齐: {(pred_df.index == y_timestamp.index).all()}")

    # 9. 检查是否有 NaN
    print(f"\n[9] NaN 检查:")
    nan_count = pred_df.isna().sum()
    print(nan_count)

if __name__ == "__main__":
    main()
