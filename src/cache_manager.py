"""
缓存管理模块 — L2 磁盘缓存。
支持 OHLCV 数据缓存与预测结果缓存。
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import OHLCV_CACHE_DIR, PREDICTION_CACHE_DIR, OHLCV_CACHE_TTL


class CacheManager:
    """磁盘级缓存管理器（L2 缓存）。"""

    def __init__(
        self,
        ohlcv_dir: Path = OHLCV_CACHE_DIR,
        prediction_dir: Path = PREDICTION_CACHE_DIR,
        ttl_seconds: int = OHLCV_CACHE_TTL,
    ):
        self.ohlcv_dir = Path(ohlcv_dir)
        self.prediction_dir = Path(prediction_dir)
        self.ttl_seconds = ttl_seconds
        # 自动创建缓存目录
        self.ohlcv_dir.mkdir(parents=True, exist_ok=True)
        self.prediction_dir.mkdir(parents=True, exist_ok=True)

    # ──────────── OHLCV 缓存 ────────────

    def _cache_path(self, key: str) -> Path:
        """将缓存 key 转换为安全的文件路径。"""
        safe_key = key.replace("/", "_").replace(" ", "_")
        return self.ohlcv_dir / f"{safe_key}.json"

    def _is_expired(self, cache_path: Path) -> bool:
        """检查缓存文件是否过期。"""
        if not cache_path.exists():
            return True
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            fetched_at = meta.get("fetched_at", 0)
            return (time.time() - fetched_at) > self.ttl_seconds
        except (json.JSONDecodeError, KeyError, TypeError):
            return True

    def get(self, key: str) -> Optional[pd.DataFrame]:
        """
        从磁盘缓存读取 OHLCV 数据。

        Returns:
            DataFrame if cache hit and valid; None otherwise.
        """
        cache_path = self._cache_path(key)
        if self._is_expired(cache_path):
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            df = pd.DataFrame(meta["data"])
            return df
        except Exception:
            return None

    def set(self, key: str, df: pd.DataFrame) -> None:
        """
        将 OHLCV DataFrame 写入磁盘缓存。
        """
        cache_path = self._cache_path(key)
        payload = {
            "fetched_at": time.time(),
            "data": df.to_dict(orient="records"),
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)

    # ──────────── 预测结果缓存 ────────────

    def _prediction_path(self, symbol: str) -> Path:
        safe_symbol = symbol.replace("/", "_").replace(" ", "_")
        return self.prediction_dir / f"{safe_symbol}_latest.json"

    def save_prediction(self, symbol: str, data: dict) -> None:
        """保存最新一次预测结果到磁盘。"""
        path = self._prediction_path(symbol)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)

    def load_last_prediction(self, symbol: str) -> Optional[dict]:
        """加载上次的预测结果。"""
        path = self._prediction_path(symbol)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return None
