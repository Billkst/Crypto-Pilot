#!/usr/bin/env python3
"""
离线回溯模拟脚本。
对主流币种进行历史回溯，计算方向预测准确率和胜率，产出基准报告。

用法:
    python3 tools/backtest_simulate.py                    # 默认 4币种 × 30天
    python3 tools/backtest_simulate.py -s BTC/USDT        # 单币种
    python3 tools/backtest_simulate.py -d 15              # 15天回溯
    python3 tools/backtest_simulate.py -s BTC/USDT -d 60  # 单币种长周期
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock streamlit 避免 @st.cache_resource 在非 Streamlit 环境报错
from unittest.mock import MagicMock
_mock_st = MagicMock()
_mock_st.cache_resource = lambda func: func
_mock_st.cache_data = lambda func: func
sys.modules["streamlit"] = _mock_st

from src.data_feed import DataFeed
from src.model_engine import ModelEngine
from src.database import Database
from src.config import INPUT_WINDOW, OUTPUT_WINDOW

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT"]
DEFAULT_DAYS = 30


def simulate_single_symbol(
    symbol: str, data_feed: DataFeed, model_engine: ModelEngine,
    total_days: int,
) -> dict:
    """
    对单个币种进行回溯模拟。
    拉取 (total_days + 30天前置 + 24h后置) 数据，
    对每个回溯点进行推理并对比真实值。
    """
    needed_rows = total_days + 30 * 24 + 24
    fetch_limit = max(needed_rows, 500)
    try:
        raw_df = data_feed.fetch_ohlcv(symbol, limit=min(fetch_limit, 1000))
    except Exception as e:
        print(f"  ⚠️ 跳过 {symbol}: {e}")
        return None

    try:
        data_feed.preprocess(raw_df)
    except Exception:
        print(f"  ⚠️ {symbol} 预处理失败，可能数据不足")
        return None

    max_backtest = len(raw_df) - INPUT_WINDOW - OUTPUT_WINDOW
    if max_backtest <= 0:
        print(f"  ⚠️ {symbol} 可用数据不足以回溯")
        return None

    samples = min(total_days, max_backtest)
    results = []
    inference_times = []

    for i in tqdm(range(samples), desc=f"  {symbol}", unit="step"):
        window_df = raw_df.iloc[i:i + INPUT_WINDOW].copy()
        window_df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
        window_df["timestamp"] = pd.to_datetime(window_df["timestamp"], unit="ms")
        window_df["amount"] = window_df["close"] * window_df["volume"]

        current_price = float(window_df["close"].iloc[-1])

        actual_idx = i + INPUT_WINDOW + OUTPUT_WINDOW - 1
        actual_row = raw_df.iloc[actual_idx]
        actual_price = float(actual_row["close"])

        x_ts = window_df["timestamp"]
        last_ts = x_ts.iloc[-1]
        y_ts = pd.Series([
            last_ts + pd.Timedelta(hours=j + 1) for j in range(OUTPUT_WINDOW)
        ])

        x_data = window_df[["open", "high", "low", "close", "volume", "amount"]]

        t0 = time.time()
        try:
            pred_df = model_engine.predict(x_data, x_ts, y_ts)
        except Exception as e:
            if i == 0:
                print(f"\n  ⚠️ 预测失败 (仅显示首次): {e}")
                print(f"    后续同类错误将静默跳过")
            continue
        inference_times.append((time.time() - t0) * 1000)

        predicted_price = float(pred_df["close"].iloc[-1])

        pred_dir = 1 if predicted_price > current_price else -1
        actual_dir = 1 if actual_price > current_price else -1
        direction_correct = 1 if pred_dir == actual_dir else 0

        expected_return = (predicted_price - current_price) / current_price
        signal = "Neutral"
        if expected_return > 0.02:
            signal = "Bullish"
        elif expected_return < -0.02:
            signal = "Bearish"

        results.append({
            "current_price": current_price,
            "predicted_price": predicted_price,
            "actual_price": actual_price,
            "expected_return": expected_return,
            "direction_correct": direction_correct,
            "signal": signal,
        })

        time.sleep(0.3)

    if not results:
        print(f"  ⚠️ {symbol}: 无有效推理结果")
        return None

    n = len(results)
    correct = sum(r["direction_correct"] for r in results)
    accuracy = correct / n * 100

    signal_results = [
        r for r in results
        if (r["signal"] == "Bullish" and r["actual_price"] > r["current_price"])
        or (r["signal"] == "Bearish" and r["actual_price"] < r["current_price"])
    ]
    signal_total = sum(1 for r in results if r["signal"] != "Neutral")
    win_rate = len(signal_results) / signal_total * 100 if signal_total > 0 else 0

    mae = np.mean([
        abs(r["predicted_price"] - r["actual_price"]) for r in results
    ])

    avg_inference = int(np.mean(inference_times)) if inference_times else 0

    return {
        "symbol": symbol,
        "sample_count": n,
        "direction_accuracy": round(accuracy, 1),
        "win_rate": round(win_rate, 1),
        "mae": round(mae, 4),
        "avg_inference_ms": avg_inference,
        "avg_return": round(np.mean([r["expected_return"] for r in results]) * 100, 2),
    }


def generate_markdown_report(
    all_results: list[dict], run_at: str, total_days: int, report_path: Path,
) -> str:
    """生成 Markdown 基准报告。"""
    total_samples = sum(r["sample_count"] for r in all_results)
    weighted_acc = sum(
        r["direction_accuracy"] * r["sample_count"] for r in all_results
    ) / total_samples if total_samples > 0 else 0
    weighted_wr = sum(
        r["win_rate"] * r["sample_count"] for r in all_results
    ) / total_samples if total_samples > 0 else 0

    lines = [
        "# Crypto-Pilot 预测基准报告",
        "",
        f"> 评估时间: {run_at[:19]}",
        f"> 回溯范围: 最近 {total_days} 天",
        f"> 总样本数: {total_samples} 次推理 ({len(all_results)} 币种 × ~{total_days} 天)",
        "",
        "## 方向预测准确率",
        "",
        "| 币种 | 样本数 | 方向准确率 | 信号胜率 | MAE (USD) | 平均推理耗时 |",
        "|------|--------|-----------|---------|-----------|-------------|",
    ]

    for r in all_results:
        lines.append(
            f"| {r['symbol']} | {r['sample_count']} | {r['direction_accuracy']}% "
            f"| {r['win_rate']}% | ${r['mae']:.4f} | {r['avg_inference_ms']/1000:.1f}s |"
        )

    lines += [
        f"| **综合** | **{total_samples}** | **{weighted_acc:.1f}%** | **{weighted_wr:.1f}%** | — | — |",
        "",
        "## 说明",
        "",
        "- **方向准确率**: 预测涨跌方向与实际方向一致的比例",
        "- **信号胜率**: 在发出 Bullish/Bearish 信号时，实际方向与信号一致的比例 (Neutral 信号不计入)",
        "- **MAE**: 预测 24h 后价格与实际 24h 后价格的绝对误差均值",
        "- 阈值固定为 2.0% (对应 App 默认值)",
        "",
        "> ⚠️ 此为技术基准报告，不构成投资建议。回溯结果不代表未来表现。",
    ]

    content = "\n".join(lines) + "\n"
    report_path.write_text(content, encoding="utf-8")
    return content


def main():
    parser = argparse.ArgumentParser(description="Crypto-Pilot 离线回溯模拟")
    parser.add_argument("-s", "--symbols", nargs="+", default=DEFAULT_SYMBOLS,
                        help="目标币种列表")
    parser.add_argument("-d", "--days", type=int, default=DEFAULT_DAYS,
                        help="回溯天数 (默认 30)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Crypto-Pilot 离线回溯模拟")
    print("=" * 60)
    print(f"  币种: {', '.join(args.symbols)}")
    print(f"  回溯天数: {args.days}")
    print(f"  预估总推理次数: {len(args.symbols) * args.days}")
    print()

    data_feed = DataFeed()
    model_engine = ModelEngine()
    db = Database()
    run_at = datetime.now(timezone.utc).isoformat()

    all_results = []
    for symbol in args.symbols:
        print(f"\n[{symbol}]")
        result = simulate_single_symbol(
            symbol, data_feed, model_engine, args.days,
        )
        if result:
            all_results.append(result)
            db.insert_benchmark(
                run_at=run_at, symbol=symbol,
                sample_count=result["sample_count"],
                direction_accuracy=result["direction_accuracy"],
                avg_return=result["avg_return"],
                win_rate=result["win_rate"],
                mae=result["mae"],
                avg_inference_ms=result["avg_inference_ms"],
                report_path="docs/BENCHMARK.md",
            )
            print(f"    方向准确率: {result['direction_accuracy']}%")
            print(f"    信号胜率:   {result['win_rate']}%")
            print(f"    MAE:        ${result['mae']:.4f}")

    if not all_results:
        print("\n❌ 无有效结果，请检查网络和币种配置。")
        sys.exit(1)

    report_path = Path(__file__).parent.parent / "docs" / "BENCHMARK.md"
    generate_markdown_report(all_results, run_at, args.days, report_path)

    print(f"\n✅ 报告已生成: {report_path}")
    print(f"   Metrics DB 已更新: data/metrics.db")


if __name__ == "__main__":
    main()
