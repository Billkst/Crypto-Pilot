"""
Crypto-Pilot 全局配置常量。
所有默认值均可在 UI 侧边栏中由用户动态覆盖。
"""
from pathlib import Path

# ──────────────── 路径配置 ────────────────
PROJECT_ROOT = Path(__file__).parent.parent  # Crypto-Pilot/
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OHLCV_CACHE_DIR = CACHE_DIR / "ohlcv"
PREDICTION_CACHE_DIR = CACHE_DIR / "predictions"
LOG_DIR = DATA_DIR / "logs"

# ──────────────── 模型配置 ────────────────
MODEL_NAME = "NeoQuasar/Kronos-base"
TOKENIZER_NAME = "NeoQuasar/Kronos-Tokenizer-base"
INPUT_WINDOW = 488          # 历史数据行数
OUTPUT_WINDOW = 24          # 预测数据行数 (24 小时)
MAX_CONTEXT = 512           # Kronos 最大上下文 token 长度

# ──────────────── 采样参数 ────────────────
DEFAULT_TEMPERATURE = 1.0   # 采样温度
DEFAULT_TOP_P = 0.9         # 核采样概率
DEFAULT_SAMPLE_COUNT = 1    # 生成路径数 (1 = 单次确定性预测)
TEMPERATURE_MIN = 0.1
TEMPERATURE_MAX = 2.0
TOP_P_MIN = 0.1
TOP_P_MAX = 1.0

# ──────────────── 数据源配置 ────────────────
DEFAULT_SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"
EXCHANGE_ID = "binance"
FETCH_LIMIT = 500           # 每次拉取的 K 线条数上限

# ──────────────── 网络与重试 ────────────────
MAX_RETRIES = 3             # API 最大重试次数
RETRY_BASE_DELAY = 1        # 重试基础延迟 (秒), 实际 = 2^attempt

# ──────────────── 缓存配置 ────────────────
OHLCV_CACHE_TTL = 300       # OHLCV 缓存有效期 (秒), 5 分钟

# ──────────────── UI 默认参数 ────────────────
DEFAULT_THRESHOLD = 2.0     # 信号触发阈值 (%)
DEFAULT_STOP_LOSS = 2.0     # 止损百分比 (%)
THRESHOLD_MIN = 0.5         # 阈值滑块最小值 (%)
THRESHOLD_MAX = 10.0        # 阈值滑块最大值 (%)
STOP_LOSS_MIN = 1.0         # 止损滑块最小值 (%)
STOP_LOSS_MAX = 10.0        # 止损滑块最大值 (%)
SLIDER_STEP = 0.5           # 滑块步长 (%)
