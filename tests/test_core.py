"""
Crypto-Pilot Phase 3 — 核心测试套件。

在不消耗真实 API 额度、不启动 Streamlit 的情况下，
验证 Data → Model → Strategy 后端链路是否畅通。

测试清单:
  Test 1: DataFeed 数据清洗 — 列名小写化 + amount 计算
  Test 2: StrategyEngine 信号判定 — 5% 涨幅 + 2% 阈值 → Bullish
  Test 3: ModelEngine 数据切片 — 500→488 输入切片 + 24 输出
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────
# 全局 Mock：必须在导入依赖 streamlit 的模块 **之前** 完成
# 使 @st.cache_resource 成为透传装饰器，不启动 Streamlit 运行时
# ─────────────────────────────────────────────────────────
_mock_st = MagicMock()
_mock_st.cache_resource = lambda func: func       # @st.cache_resource → 原样返回
_mock_st.cache_data = lambda func: func           # 同理 mock cache_data（如有）
sys.modules["streamlit"] = _mock_st

# 现在可以安全导入项目模块了
from src.config import INPUT_WINDOW, OUTPUT_WINDOW  # noqa: E402
from src.data_feed import DataFeed                  # noqa: E402
from src.model_engine import ModelEngine            # noqa: E402
from src.strategy import StrategyEngine, UserConfig # noqa: E402


# ══════════════════════════════════════════════════════════
# Test 1: 数据清洗 (DataFeed.preprocess)
# ══════════════════════════════════════════════════════════

class TestDataFeedPreprocess(unittest.TestCase):
    """验证 DataFeed.preprocess() 的列名标准化与 amount 计算。"""

    def setUp(self):
        """构造含大写列名、500 行的 Mock DataFrame。"""
        n = 500
        np.random.seed(42)
        # 使用大写列名模拟 ccxt 原始数据
        self.raw_df = pd.DataFrame({
            "Timestamp": (
                pd.date_range("2025-01-01", periods=n, freq="h")
                .astype(np.int64) // 10**6
            ),
            "Open":   np.random.uniform(40000, 50000, n),
            "High":   np.random.uniform(40000, 50000, n),
            "Low":    np.random.uniform(40000, 50000, n),
            "Close":  np.random.uniform(40000, 50000, n),
            "Volume": np.random.uniform(1, 100, n),
        })
        # Mock ccxt 避免网络请求
        with patch("src.data_feed.ccxt"):
            self.feed = DataFeed()

    def test_columns_are_lowercase(self):
        """列名应被标准化为全小写，且包含 amount。"""
        x_df, _, _ = self.feed.preprocess(self.raw_df)
        expected = ["open", "high", "low", "close", "volume", "amount"]
        self.assertListEqual(list(x_df.columns), expected)

    def test_amount_equals_close_times_volume(self):
        """amount 列应等于 close × volume。"""
        x_df, _, _ = self.feed.preprocess(self.raw_df)
        recomputed = x_df["close"] * x_df["volume"]
        pd.testing.assert_series_equal(
            x_df["amount"].reset_index(drop=True),
            recomputed.reset_index(drop=True),
            check_names=False,
        )


# ══════════════════════════════════════════════════════════
# Test 2: 策略逻辑 (StrategyEngine.analyze)
# ══════════════════════════════════════════════════════════

class TestStrategyEngine(unittest.TestCase):
    """验证策略引擎的信号判定逻辑。"""

    def test_bullish_on_5pct_with_2pct_threshold(self):
        """
        设定场景:
          - current_price  = 100.0
          - predicted_price = 105.0 → return_rate = 5%
          - threshold      = 2.0 (UI 百分比值)
        预期: signal == "Bullish"
        """
        current_price = 100.0
        predicted_price = 105.0  # (105 - 100) / 100 = 0.05 = 5%

        # 构造 24 行的预测 DataFrame（StrategyEngine 只取最后一行 close）
        pred_df = pd.DataFrame({
            "open":   [predicted_price] * 24,
            "high":   [predicted_price] * 24,
            "low":    [predicted_price] * 24,
            "close":  [predicted_price] * 24,
            "volume": [1.0] * 24,
            "amount": [predicted_price] * 24,
        })

        config = UserConfig(threshold=2.0, stop_loss_pct=2.0)
        result = StrategyEngine.analyze(current_price, pred_df, config)

        self.assertEqual(result.signal, "Bullish")
        self.assertEqual(result.signal_emoji, "🟢")
        self.assertAlmostEqual(result.expected_return, 0.05, places=4)


# ══════════════════════════════════════════════════════════
# Test 3: 模型张量形状 (ModelEngine — Mock 推理)
# ══════════════════════════════════════════════════════════

class TestModelEngineShape(unittest.TestCase):
    """
    验证模型输入切片到 488 行、输出 24 行。
    通过 Mock 模型对象避免真实下载 HuggingFace 权重。
    """

    def setUp(self):
        """构造 500 行 DataFrame 并通过 DataFeed.preprocess() 预处理。"""
        n = 500
        np.random.seed(42)
        raw_df = pd.DataFrame({
            "Timestamp": (
                pd.date_range("2025-01-01", periods=n, freq="h")
                .astype(np.int64) // 10**6
            ),
            "Open":   np.random.uniform(40000, 50000, n),
            "High":   np.random.uniform(40000, 50000, n),
            "Low":    np.random.uniform(40000, 50000, n),
            "Close":  np.random.uniform(40000, 50000, n),
            "Volume": np.random.uniform(1, 100, n),
        })
        with patch("src.data_feed.ccxt"):
            feed = DataFeed()
        self.x_df, self.x_ts, self.y_ts = feed.preprocess(raw_df)

    def test_input_sliced_to_488(self):
        """500 行原始数据 → 预处理后 x_df 应为 488 行。"""
        self.assertEqual(len(self.x_df), INPUT_WINDOW)   # 488
        self.assertEqual(len(self.x_ts), INPUT_WINDOW)   # 488

    def test_output_timestamps_length_is_24(self):
        """y_timestamp 长度应为 24 (OUTPUT_WINDOW)。"""
        self.assertEqual(len(self.y_ts), OUTPUT_WINDOW)  # 24

    @patch.object(ModelEngine, "_load_model")
    def test_model_receives_488_rows_and_returns_24(self, mock_load):
        """Mock 模型推理: 验证输入 488 行、输出 24 行。"""
        # 构造假预测输出 (24, 6)
        fake_pred = pd.DataFrame(
            np.random.uniform(40000, 50000, (OUTPUT_WINDOW, 6)),
            columns=["open", "high", "low", "close", "volume", "amount"],
        )
        mock_predictor = MagicMock()
        mock_predictor.predict.return_value = fake_pred
        mock_load.return_value = mock_predictor

        # 执行推理
        engine = ModelEngine()
        result = engine.predict(self.x_df, self.x_ts, self.y_ts)

        # 验证模型收到的输入确实是 488 行
        call_kwargs = mock_predictor.predict.call_args
        passed_df = call_kwargs.kwargs.get("df")
        self.assertEqual(len(passed_df), INPUT_WINDOW,
                         f"模型应收到 {INPUT_WINDOW} 行输入，实际收到 {len(passed_df)} 行")

        # 验证输出确实是 24 行
        self.assertEqual(len(result), OUTPUT_WINDOW,
                         f"模型应输出 {OUTPUT_WINDOW} 行预测，实际输出 {len(result)} 行")


# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
