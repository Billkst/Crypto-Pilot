"""
指标追踪模块。
提供预测埋点、实际价格回填和聚合查询功能。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.config import EXCHANGE_ID, TIMEFRAME, FETCH_LIMIT
from src.database import Database


class MetricsTracker:
    """指标采集与查询器。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    # ── 写入 ──

    def record_prediction(
        self, symbol: str, current_price: float,
        predicted_price: float, expected_return: float, signal: str,
        cold_start_ms: int, inference_ms: int, data_fetch_ms: int,
    ) -> int:
        now = datetime.now(timezone.utc)
        predicted_at = now.isoformat()
        target_at = (now + pd.Timedelta(hours=24)).isoformat()
        return self.db.insert_prediction(
            symbol=symbol, predicted_at=predicted_at, target_at=target_at,
            current_price=current_price, predicted_price=predicted_price,
            expected_return=expected_return, signal=signal,
            cold_start_ms=cold_start_ms, inference_ms=inference_ms,
            data_fetch_ms=data_fetch_ms,
        )

    def backfill_actual_prices(self, symbol: str | None = None) -> int:
        """
        回填已到期的预测记录。
        从 Binance 拉取 target_at 时刻的真实 close 价格回填。
        返回回填数量。
        """
        pending = self.db.get_pending_backfills(symbol)
        if not pending:
            return 0

        import ccxt
        exchange = getattr(ccxt, EXCHANGE_ID)({"enableRateLimit": True})
        count = 0

        symbols = set(p["symbol"] for p in pending)
        for sym in symbols:
            try:
                ohlcv = exchange.fetch_ohlcv(sym, TIMEFRAME, limit=FETCH_LIMIT)
                df = pd.DataFrame(
                    ohlcv,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            except Exception:
                continue

            sym_pending = [p for p in pending if p["symbol"] == sym]
            for p in sym_pending:
                target_at = pd.Timestamp(p["target_at"])
                match = df[df["timestamp"] == target_at]
                if not match.empty:
                    actual_price = float(match.iloc[0]["close"])
                    self.db.backfill_prediction(p["id"], actual_price)
                    count += 1

        return count

    # ── 查询 ──

    def get_direction_accuracy(
        self, symbol: str | None = None, days: int = 30
    ) -> dict:
        result = self.db.get_direction_accuracy(symbol, days)
        if result["sample_count"] >= 10:
            result["source"] = "live"
            return result
        benchmarks = self.db.get_latest_benchmark(symbol)
        if benchmarks:
            total_samples = sum(b["sample_count"] for b in benchmarks)
            if total_samples > 0:
                weighted_acc = sum(
                    b["direction_accuracy"] * b["sample_count"]
                    for b in benchmarks
                ) / total_samples
                return {
                    "sample_count": total_samples,
                    "correct_count": round(weighted_acc / 100 * total_samples),
                    "accuracy_pct": round(weighted_acc, 1),
                    "source": "benchmark",
                }
        return {"sample_count": 0, "correct_count": 0, "accuracy_pct": None, "source": None}

    def get_win_rate(
        self, symbol: str | None = None, days: int = 30
    ) -> dict:
        result = self.db.get_win_rate(symbol, days)
        if result["sample_count"] >= 10:
            result["source"] = "live"
            return result
        benchmarks = self.db.get_latest_benchmark(symbol)
        if benchmarks:
            total_samples = sum(b["sample_count"] for b in benchmarks)
            if total_samples > 0:
                weighted_wr = sum(
                    b["win_rate"] * b["sample_count"]
                    for b in benchmarks
                ) / total_samples
                return {
                    "sample_count": total_samples,
                    "win_count": round(weighted_wr / 100 * total_samples),
                    "win_rate_pct": round(weighted_wr, 1),
                    "source": "benchmark",
                }
        return {"sample_count": 0, "win_count": 0, "win_rate_pct": None, "source": None}

    def get_avg_timing(self) -> dict:
        return self.db.get_avg_timing()

    def get_prediction_stats(self) -> dict:
        return self.db.get_prediction_stats()

    def get_benchmark_history(self, symbol: str | None = None) -> list[dict]:
        return self.db.get_latest_benchmark(symbol)

    def get_latest_test_run(self) -> dict | None:
        return self.db.get_latest_test_run()
