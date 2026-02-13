# Crypto-Pilot V1.0 — 项目现状与未来迭代指南

> **版本号**：V1.0.0 (Beta)  
> **撰写日期**：2026-02-12  
> **文档性质**：第一阶段收官总结 & V2 迭代路线图

---

## 1. 项目概述 (Project Overview)

**Crypto-Pilot** 是一款基于 [NeoQuasar/Kronos-base](https://huggingface.co/NeoQuasar/Kronos-base) 时序基础模型的**本地加密货币量化预测终端**。它通过 ccxt 实时拉取 Binance 1 小时级 K 线数据，利用 Kronos 模型完成未来 24 小时价格预测，并结合用户可配置的动态阈值策略给出交易信号（看多 / 看空 / 观望），全程本地 CPU 推理，无需 GPU 与云端 API。

**当前版本号：`V1.0.0 (Beta)`**

---

## 2. 核心已实现功能 (Completed Features)

### 2.1 数据层 (`src/data_feed.py` + `src/cache_manager.py`)

| 功能点 | 实现详情 | 状态 |
|--------|----------|------|
| **OHLCV 数据拉取** | 通过 `ccxt` 动态拉取 Binance 1h K 线数据，默认获取最近 500 条，`enableRateLimit: True` 防限流 | ✅ 已完成 |
| **指数退避重试** | 网络异常时最多重试 3 次，延迟按 `2^attempt` 递增 (1s → 2s → 4s) | ✅ 已完成 |
| **L2 磁盘缓存** | JSON 格式缓存到 `data/cache/ohlcv/`，TTL = 300 秒 (5 分钟)，避免高频重复请求 | ✅ 已完成 |
| **列名标准化** | 无论原始列名大小写如何，统一重命名为 `['timestamp', 'open', 'high', 'low', 'close', 'volume']` | ✅ 已完成 |
| **amount 字段填充** | ccxt 不返回 `amount` 列，预处理中自动计算 `amount = close × volume` | ✅ 已完成 |
| **NaN 处理** | `ffill().bfill()` 双向填充，确保无缺失值 | ✅ 已完成 |
| **数据量校验** | 不足 488 行时主动抛出 `DataFeedError`，避免模型接收不完整输入 | ✅ 已完成 |
| **时间戳分离** | 预处理后分离 `x_timestamp` (488,) 与 `y_timestamp` (24,)，供模型与图表使用 | ✅ 已完成 |

### 2.2 模型层 (`src/model_engine.py` + `model/`)

| 功能点 | 实现详情 | 状态 |
|--------|----------|------|
| **模型懒加载** | 使用 `@st.cache_resource` 装饰器，首次推理时从 HuggingFace Hub 下载权重，后续 rerun 复用同一实例 | ✅ 已完成 |
| **512 上下文严格遵守** | 输入窗口 `INPUT_WINDOW = 488` + 输出窗口 `OUTPUT_WINDOW = 24` = 512，恰好等于 `MAX_CONTEXT`，**严禁溢出** | ✅ 已完成 |
| **Token 切片逻辑** | `DataFeed.preprocess()` 从 500 行原始数据中截取最近 488 行，确保模型输入精确为 `(488, 6)` | ✅ 已完成 |
| **强制 CPU 推理** | `KronosPredictor(model, tokenizer, device="cpu", max_context=512)`，杜绝 CUDA 依赖 | ✅ 已完成 |
| **采样参数透传** | Temperature / Top-P / Sample Count 三项参数从 UI 侧边栏 → `UserConfig.sampling` → `ModelEngine.predict()` → `predictor.predict()` 全链路透传 | ✅ 已完成 |
| **时间戳传递** | 严格传入 `x_timestamp` 与 `y_timestamp`，Kronos 模型内部通过 `calc_time_stamps()` 提取 (minute, hour, weekday, day, month) 5 维时间特征 | ✅ 已完成 |

### 2.3 策略层 (`src/strategy.py`)

| 功能点 | 实现详情 | 状态 |
|--------|----------|------|
| **动态阈值判定** | 阈值由 UI 滑块实时传入 `UserConfig.threshold`，非硬编码。Streamlit rerun 机制保证每次分析使用最新值 | ✅ 已完成 |
| **三级信号体系** | `expected_return > +threshold` → 🟢 Bullish；`< -threshold` → 🔴 Bearish；其余 → 🟡 Neutral | ✅ 已完成 |
| **止损价位计算** | Bullish: `current_price × (1 - stop_loss_pct%)`；Bearish: `current_price × (1 + stop_loss_pct%)`；Neutral: `None` | ✅ 已完成 |
| **数据类封装** | `UserConfig` / `SamplingConfig` / `SignalResult` 三个 `@dataclass`，类型安全、结构清晰 | ✅ 已完成 |

### 2.4 UI/UX (`src/app.py` + `src/chart_renderer.py`)

| 功能点 | 实现详情 | 状态 |
|--------|----------|------|
| **Streamlit 主入口** | `app.py` 作为单文件入口，`streamlit run src/app.py` 即可启动 | ✅ 已完成 |
| **Session State 持久化** | `hist_df` / `pred_df` / `signal_result` / `is_predicting` 四个状态键跨 rerun 保持 | ✅ 已完成 |
| **侧边栏交互** | 交易对输入 / 信号阈值滑块 / 止损比例滑块 / 高级模型设置 (折叠面板) / "开始预测 🚀" 按钮 | ✅ 已完成 |
| **KPI 指标卡** | 4 列 `st.metric`：当前价格、预测价格 (含 delta %)、交易信号 (含 Emoji)、建议止损 | ✅ 已完成 |
| **Plotly K 线图** | 历史数据灰色 K 线 + 预测数据蓝色 K 线拼接，`plotly_dark` 暗色主题，白色虚线分界线标注 "Current Time" | ✅ 已完成 |
| **详细数据展开** | `st.expander` 可查看预测 DataFrame 的完整 24 行数据 | ✅ 已完成 |
| **自定义 CSS** | `.stMetric` 暗色背景 + 圆角边框，提升视觉质感 | ✅ 已完成 |
| **错误处理 UI** | `CryptoPilotError` → `st.error()`，未知异常 → `st.error()` + `st.exception()` 堆栈展示 | ✅ 已完成 |

### 2.5 测试体系

| 测试类型 | 文件 | 覆盖内容 | 状态 |
|----------|------|----------|------|
| **单元测试** | `tests/test_core.py` | 数据清洗 (列名标准化 + amount 计算)、策略信号判定 (Bullish)、模型 I/O 形状 (488→24) | ✅ 已完成 |
| **E2E 测试** | `tests/e2e_test.py` | Playwright 自动化：页面加载 → 侧边栏检查 → 输入交易对 → 点击预测 → K 线图渲染 → KPI 卡片验证 | ✅ 已完成 |
| **调试脚本** | `tests/debug_pred_data.py` | 全链路数据追踪：raw_df → preprocess → predict → timestamp 赋值 → OHLC 值域检查 | ✅ 已完成 |
| **一键运行** | `run_tests.py` | `unittest` 自动发现 `tests/test_*.py` 并执行，带彩色结果摘要 | ✅ 已完成 |

---

## 3. 当前目录结构与模块职责 (Architecture & File Tree)

### 3.1 项目文件树

```
Crypto-Pilot/
├── model/                          # Kronos 模型框架 (第三方)
│   ├── __init__.py                 # 导出 Kronos, KronosTokenizer, KronosPredictor
│   ├── kronos.py                   # 模型定义 + 推理 + Token 采样逻辑 (663 行)
│   └── module.py                   # Transformer 组件 (RMSNorm, BSQuantizer 等) (571 行)
│
├── src/                            # 应用核心代码
│   ├── __init__.py
│   ├── app.py                      # Streamlit 主入口 (241 行)
│   ├── cache_manager.py            # L2 磁盘缓存管理 (103 行)
│   ├── chart_renderer.py           # Plotly K 线图渲染 (129 行)
│   ├── config.py                   # 全局配置常量 (52 行)
│   ├── data_feed.py                # 数据采集与预处理 (146 行)
│   ├── exceptions.py               # 自定义异常层级 (22 行)
│   ├── model_engine.py             # 模型推理引擎封装 (97 行)
│   └── strategy.py                 # 策略分析引擎 (116 行)
│
├── tests/                          # 测试套件
│   ├── __init__.py
│   ├── test_core.py                # 核心单元测试 (185 行)
│   ├── e2e_test.py                 # Playwright E2E 测试 (368 行)
│   └── debug_pred_data.py          # 数据调试脚本 (91 行)
│
├── data/                           # 运行时数据 (gitignored)
│   └── cache/
│       └── ohlcv/                  # OHLCV JSON 缓存
│
├── docs/                           # 项目文档
│   ├── PRD.md                      # 产品需求文档
│   ├── DESIGN.md                   # 系统设计文档
│   ├── TASK.md                     # 开发任务清单
│   └── V1_SUMMARY.md              # 本文档
│
├── test_screenshots/               # E2E 测试截图
├── requirements.txt                # Python 依赖清单
└── run_tests.py                    # 一键测试脚本入口
```

### 3.2 模块职责一览

| 模块 | 文件 | 核心职责 |
|------|------|----------|
| **主入口** | `app.py` | Streamlit 页面配置、Session State 管理、侧边栏 UI 渲染、核心预测流程编排 (Data → Model → Strategy → Chart) |
| **数据采集** | `data_feed.py` | 通过 ccxt 拉取 Binance OHLCV 数据，实施 L2 磁盘缓存与指数退避重试，执行数据预处理流水线 (标准化 → 填充 → 校验 → 截取 → 分离) |
| **模型推理** | `model_engine.py` | 封装 Kronos 模型的懒加载 (`@st.cache_resource`) 与推理流程，提供统一的 `predict()` 接口，透传采样参数 |
| **策略计算** | `strategy.py` | 根据预测终点价格与当前价格计算预期收益率，基于动态阈值判定交易信号 (Bullish / Bearish / Neutral)，计算止损价位 |
| **图表渲染** | `chart_renderer.py` | 使用 Plotly 绘制历史 (灰色) + 预测 (蓝色) 双色 K 线图，暗色主题，垂直分界线标注当前时间 |

---

## 4. 关键技术备忘录 (Technical Memos)

> 📝 以下内容是留给未来开发者的**必读注意事项**，违反任何一条都可能导致运行时错误。

### 4.1 ⚠️ Conda 环境：必须使用 `kronos`

```bash
conda activate kronos
```

项目依赖 PyTorch、Transformers、ccxt 等库的特定版本组合。**严禁在 base 环境或其他虚拟环境中运行**，否则可能遭遇以下问题：
- `ModuleNotFoundError: No module named 'einops'`
- `torch` 版本与 Kronos 模型权重不兼容
- `ccxt` 版本过低导致 Binance API 签名失败

### 4.2 ⚠️ `model/` 文件夹的本地依赖关系

Kronos 模型代码位于项目根目录的 `model/` 文件夹下，**不是** pip 安装的第三方包。关键依赖链：

```
model/__init__.py
  └── from .kronos import KronosTokenizer, Kronos, KronosPredictor
        └── from model.module import *  (kronos.py 第 10 行, 使用 sys.path.append)
```

- `model_engine.py` 中通过 `from model import Kronos, KronosPredictor, KronosTokenizer` 导入
- `kronos.py` 内部使用 `sys.path.append("../")` 来解析 `model.module` 的导入路径
- **如果移动 `model/` 目录的位置**，必须同步修改 `kronos.py` 中的 `sys.path.append` 路径
- HuggingFace Hub 的模型权重 (`NeoQuasar/Kronos-base` 和 `NeoQuasar/Kronos-Tokenizer-base`) 会在首次推理时自动下载到本地 `.cache`

### 4.3 ⚠️ Pandas Timestamp 与 Plotly 的兼容性 Bug

**问题根因**：Pandas 2.x 的 `Timestamp` 对象不再支持与整数的直接算术运算。当 Plotly 内部尝试将 `pd.Timestamp` 与数字做运算时，会抛出 `TypeError`。

**当前解决方案**（`chart_renderer.py` 第 116-118 行）：

```python
# 必须转为毫秒级 Unix 时间戳，避免 Pandas 2.x Timestamp 与整数运算的兼容性问题
last_hist_ts = hist_df["timestamp"].iloc[-1]
split_x = last_hist_ts.timestamp() * 1000
```

在添加垂直分界线 (`fig.add_vline`) 时，将 `pd.Timestamp` 转换为 Unix 毫秒时间戳 (float)。**如果直接传入 `pd.Timestamp` 对象，`add_vline` 会报错**。

### 4.4 ⚠️ `pred_df["timestamp"]` 的 Index 对齐陷阱

**问题根因**：`ModelEngine.predict()` 返回的 `pred_df` 使用 `y_timestamp` 作为 DataFrame 的 **index**（见 `kronos.py` 第 558 行），而 `y_timestamp` 是一个独立创建的 `pd.Series`（index 从 0 开始）。如果直接赋值 `pred_df["timestamp"] = y_timestamp`，Pandas 会尝试按 **index** 对齐，导致 NaN。

**当前解决方案**（`app.py` 第 191 行和 201 行）：

```python
pred_df["timestamp"] = y_timestamp.values      # .values 取出 numpy 数组，绕过 index 对齐
viz_hist_df["timestamp"] = x_timestamp.values   # 同理
```

### 4.5 ⚠️ 单元测试中 Mock Streamlit 的方式

由于 `model_engine.py` 使用了 `@st.cache_resource` 装饰器，在非 Streamlit 运行时环境下直接导入会报错。单元测试 (`test_core.py`) 通过在 **导入项目模块之前** 注入全局 Mock 来解决：

```python
_mock_st = MagicMock()
_mock_st.cache_resource = lambda func: func  # @st.cache_resource → 透传
sys.modules["streamlit"] = _mock_st
# 之后再 import src.model_engine 等模块
```

**注意**：这种 Mock 方式必须在所有项目模块 import 之前执行，否则无效。

---

## 5. V2 版本迭代路线图 (Future Roadmap)

> 🏗️ 以下建议由架构师基于 V1 实际代码状态提出，按优先级排列。

### 5.1 🚀 功能增强：多时间粒度支持 (Multi-Timeframe)

**现状**：当前硬编码使用 `1h` 时间粒度，`TIMEFRAME = "1h"`。

**升级方案**：

1. **UI 扩展**：在侧边栏添加 `st.selectbox("时间粒度", ["15m", "1h", "4h", "1d"])`

2. **关键挑战 — 512 上下文限制的绕行策略**：
   - **方案 A (推荐)：动态调整 I/O 窗口比例**
     - 15 分钟粒度：输入 480 行 + 输出 32 行 = 512（预测未来 8 小时）
     - 4 小时粒度：输入 488 行 + 输出 24 行 = 512（预测未来 96 小时 = 4 天）
     - 在 `config.py` 中增加 `WINDOW_PROFILES` 字典映射
   - **方案 B：滑动窗口预测**
     - 对于超长预测需求，分段预测，每段将前一段的输出追加到输入末尾
     - 需注意误差累积问题，每跨一段误差放大

3. **数据层适配**：`DataFeed.fetch_ohlcv()` 已支持 `timeframe` 参数，只需调整 `FETCH_LIMIT` 以确保拉取足够数据

4. **配置变更**：将 `INPUT_WINDOW` 和 `OUTPUT_WINDOW` 从常量改为根据 timeframe 动态计算

### 5.2 📊 策略升级：多币种投资组合优化 (Portfolio Optimization)

**现状**：当前仅支持单币种的简单阈值判断。

**升级方案（分三阶段）**：

**阶段 1 — 多币种并行预测**：
- 利用 `KronosPredictor.predict_batch()` 方法（`kronos.py` 第 562-661 行已实现），支持批量输入多个时间序列
- UI 改造：`st.multiselect` 替换 `st.text_input`，支持同时选择 `["BTC/USDT", "ETH/USDT", "SOL/USDT"]`
- 结果面板从单卡片改为多行比较表格

**阶段 2 — 辅助技术指标整合**：
- 在预测结果上叠加移动平均线 (MA5 / MA20 / MA60)，辅助交叉验证
- 在 `strategy.py` 中加入 RSI (相对强弱指数) 与 MACD 指标，形成多因子综合评分
- 信号判定从单一阈值升级为**加权评分体系**：
  ```
  综合得分 = 0.5 × 模型预测信号 + 0.3 × MA 交叉信号 + 0.2 × RSI 信号
  ```

**阶段 3 — 投资组合优化 (Markowitz / Risk Parity)**：
- 基于多币种预测收益率与协方差矩阵，使用 `scipy.optimize` 计算最优资产权重
- 输出从"单币种买卖信号"升级为"推荐仓位分配比例"
- 新增 `src/portfolio.py` 模块

### 5.3 🗄️ 工程优化：持久化存储与回测打分系统

**现状**：预测结果仅以 JSON 文件缓存最新一次 (`data/cache/predictions/{symbol}_latest.json`)，无法进行长期回测分析。

**升级方案**：

1. **引入 SQLite 持久化存储**：
   - 新增 `src/database.py`，使用 `sqlite3` 标准库（无需额外依赖）
   - 表结构设计：
     ```sql
     CREATE TABLE predictions (
         id            INTEGER PRIMARY KEY AUTOINCREMENT,
         symbol        TEXT NOT NULL,
         timeframe     TEXT NOT NULL,
         predicted_at  DATETIME NOT NULL,     -- 预测发起时间
         target_time   DATETIME NOT NULL,     -- 预测目标终点时间
         current_price REAL NOT NULL,
         predicted_price REAL NOT NULL,
         signal        TEXT NOT NULL,          -- Bullish/Bearish/Neutral
         actual_price  REAL,                   -- [后填] 到达目标时间后回填
         accuracy_pct  REAL,                   -- [后填] |actual - predicted| / actual × 100
         created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
     );
     ```

2. **自动回测评分调度**：
   - 当用户发起新预测时，自动查找 24 小时前的历史预测
   - 用当前真实价格回填 `actual_price`，计算 `accuracy_pct`
   - 在 UI 中展示"模型历史准确率"仪表盘

3. **长期数据分析看板**：
   - 新增 Streamlit 页面 `pages/backtest.py`（多页面应用架构）
   - 展示模型预测历史表现走势图、平均误差率 (MAPE)、信号召回率

### 5.4 🔒 其他工程化建议

| 优化项 | 说明 | 优先级 |
|--------|------|--------|
| **日志系统** | 引入 Python `logging` 模块替代 `print`，分级记录 (DEBUG / INFO / WARNING / ERROR)，输出到 `data/logs/` | 🟡 中 |
| **配置文件外部化** | 将 `config.py` 中的常量迁移到 `config.yaml` 或 `.env` 文件，支持不修改代码即可调参 | 🟡 中 |
| **Docker 容器化** | 提供 `Dockerfile` + `docker-compose.yml`，实现一键部署，解决环境依赖问题 | 🟢 低 |
| **WebSocket 实时订阅** | 替换当前的轮询式 `fetch_ohlcv()` 为 `ccxt.pro` 的 WebSocket 实时推流，降低延迟 | 🟢 低 |
| **CI/CD 流水线** | GitHub Actions 配置自动化测试与代码质量检查 (`pytest` + `flake8` + `mypy`) | 🟡 中 |
| **用户认证与多用户** | 如需公开部署，引入 `streamlit-authenticator` 或 OAuth 认证 | 🔴 高 (仅限公开部署场景) |

---

## 6. 依赖清单快照 (Dependencies)

```
# Core
streamlit>=1.30.0
plotly>=5.18.0
pandas>=2.1.0
numpy>=1.24.0
watchdog

# Data Source
ccxt>=4.0.0

# ML / Model
torch
transformers>=4.36.0
safetensors
einops
scipy
huggingface_hub

# Testing
pytest>=7.0.0
```

**环境要求**：
- Python >= 3.10
- Conda 环境名：`kronos`
- 操作系统：Windows / macOS / Linux
- 硬件：无 GPU 要求，纯 CPU 推理

---

## 7. 快速启动指南 (Quick Start)

```bash
# 1. 激活 Conda 环境
conda activate kronos

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行单元测试 (验证环境)
python run_tests.py

# 4. 启动应用
streamlit run src/app.py

# 5. (可选) 运行 E2E 测试 (需先安装 Playwright)
pip install playwright
playwright install chromium
python tests/e2e_test.py
```

---

## 8. 已知限制与风险提示 (Known Limitations)

| 限制 | 影响 | 缓解措施 |
|------|------|----------|
| **单币种预测** | 一次只能分析一个交易对 | V2 计划支持多币种批量预测 |
| **固定 1h 粒度** | 无法分析 15 分钟或日线级别行情 | V2 计划支持多时间粒度 |
| **无历史回测** | 无法评估模型长期预测准确率 | V2 计划引入 SQLite + 自动评分 |
| **首次推理延迟** | 首次运行需下载 ~500MB 模型权重，耗时 2-10 分钟 (取决于网络) | 模型缓存到本地后无此问题 |
| **CPU 推理速度** | 单次 24 步自回归推理约 20-40 秒 | 可考虑 ONNX Runtime 加速或 GPU 支持 |
| **回测线未联通** | `backtest_df` 接口已预留但尚未在主流程中调用 | V2 实现预测结果存储后即可启用 |

> ⚠️ **投资风险声明**：Crypto-Pilot 是技术研究项目，所有预测仅供参考，**不构成任何投资建议**。加密货币市场波动剧烈，请谨慎决策。

---

*文档撰写者：Crypto-Pilot V1.0 技术团队*  
*最后更新：2026-02-12*
