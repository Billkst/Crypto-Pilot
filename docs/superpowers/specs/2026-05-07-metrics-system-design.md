# Crypto-Pilot Metrics System — Design Spec

> **版本**：v1.0
> **日期**：2026-05-07
> **性质**：为 Crypto-Pilot 补充五类产品数据指标的设计文档
> **驱动**：方向预测准确率 / 回测收益率与胜率 / 冷启动与缓存后响应时间 / 覆盖币对数量 / 测试用例与 E2E 通过率

## 目标

从 AI 产品大师角度，为本项目补充**可验证、有产品意义、不堆砌**的数据指标。两条线并行：

- **基准线**（README 访客看的）：离线回溯脚本一次性产出基准报告
- **在线线**（App 用户看的）：SQLite 持久化 + 实时追踪 + Status Tab 展示

## 方案总览

**推荐方案：在线 + 离线分离**

| 组件 | 文件 | 用途 |
|------|------|------|
| 数据库层 | `src/database.py` | SQLite 管理、建表、CRUD |
| 在线指标 | `src/metrics.py` | 预测埋点、回填、聚合查询 |
| 离线脚本 | `tools/backtest_simulate.py` | 回溯模拟、产出基准报告 |
| 基准报告 | `docs/BENCHMARK.md` | 离线脚本生成的可读报告 |
| 测试记录 | `tools/record_test_run.py` | 跑测试并写入 test_runs 表 |
| Status Tab | `src/app.py` 内 `st.tabs` | UI 聚合展示五类指标 |

---

## Section 1: 数据库层 (`src/database.py`)

使用 Python 标准库 `sqlite3`，无额外依赖。数据库文件 `data/metrics.db`（gitignored）。

### 1.1 表结构

```sql
-- 预测记录（每次用户预测自动插入，24h 后回填实际价格）
CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    predicted_at    TEXT    NOT NULL,      -- ISO 8601 UTC
    target_at       TEXT    NOT NULL,      -- 预测目标时间 (predicted_at + 24h)
    current_price   REAL    NOT NULL,
    predicted_price REAL    NOT NULL,
    expected_return REAL    NOT NULL,
    signal          TEXT    NOT NULL,      -- Bullish / Bearish / Neutral
    actual_price    REAL,                  -- NULL 表示尚未回填
    actual_return   REAL,                  -- 回填后计算
    direction_correct INTEGER,            -- 1=正确, 0=错误, NULL=未回填
    cold_start_ms   INTEGER,              -- 本次会话首次模型加载耗时
    inference_ms    INTEGER,              -- 推理耗时
    data_fetch_ms   INTEGER               -- 数据拉取耗时
);

-- 基准测试快照（离线脚本写入，保留历史趋势）
CREATE TABLE IF NOT EXISTS benchmarks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at            TEXT    NOT NULL,
    symbol            TEXT    NOT NULL,
    sample_count      INTEGER,            -- 回溯样本数
    direction_accuracy REAL,              -- 方向准确率 %
    avg_return        REAL,               -- 平均信号收益率 %
    win_rate          REAL,               -- 胜率 %
    mae               REAL,               -- 平均绝对误差
    avg_inference_ms  INTEGER,            -- 平均推理耗时
    report_path       TEXT                -- Markdown 报告路径
);

-- 测试运行记录
CREATE TABLE IF NOT EXISTS test_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at      TEXT    NOT NULL,
    unit_passed INTEGER NOT NULL,
    unit_total  INTEGER NOT NULL,
    e2e_passed  INTEGER NOT NULL,
    e2e_total   INTEGER NOT NULL,
    success     INTEGER NOT NULL          -- 1=全部通过 0=有失败
);
```

### 1.2 API

```python
class Database:
    def __init__(self, db_path: str = "data/metrics.db"):
        """自动创建目录和表"""
    def insert_prediction(self, **kwargs) -> int: ...
    def backfill_prediction(self, pred_id: int, actual_price: float): ...
    def get_pending_backfills(self, symbol: str = None) -> list[dict]: ...
    def get_direction_accuracy(self, symbol: str = None, days: int = 30) -> dict: ...
    def get_avg_timing(self, days: int = 30) -> dict: ...
    def insert_benchmark(self, **kwargs) -> int: ...
    def get_latest_benchmark(self, symbol: str = None) -> list[dict]: ...
    def insert_test_run(self, **kwargs) -> int: ...
    def get_latest_test_run(self) -> dict | None: ...
```

### 1.3 关键决策

- `direction_correct` 只看涨跌方向，不看幅度 —— 策略层就是方向决策，这个指标更有产品意义
- 三列耗时拆开 (`cold_start_ms`, `inference_ms`, `data_fetch_ms`) —— 方便定位瓶颈
- `benchmarks` 表保留历史快照 —— 每次跑离线脚本追加一条，可追踪准确率趋势

---

## Section 2: 离线回溯脚本 (`tools/backtest_simulate.py`)

### 2.1 原理

不与未来信息接触。选取过去 N 天的同一时刻作为 "伪预测点"，用当时的前 488 小时数据跑推理，对比 24 小时后的真实价格。

### 2.2 流程

```
输入: 币种列表, 回溯天数 (默认 30), 每币种最多 30 个样本点

对每个币种:
  拉取 (回溯天数 + 20天前置 + 24h后置) 的 1h OHLCV 数据

  对每个回溯点 i (= 0..回溯天数-1):
    1. 截取 [i, i+488) 行作为输入窗口
    2. 最后一行 close → current_price
    3. 第 [i+488+24] 行 close → actual_price (24h后真实价格)
    4. 调用 KronosPredictor 推理得到 predicted_price
    5. 对比方向: sign(pred - curr) == sign(actual - curr) → direction_correct
    6. 记录: 方向正确/错误, 预期收益率, 实际收益率, 耗时

汇总:
  - 方向准确率 (按币种 和 全局)
  - 信号胜率 (Bullish 且实际涨 / Bearish 且实际跌)
  - MAE (平均绝对误差)
  - 平均推理耗时 (按冷启动/热缓存分)
```

### 2.3 输出

1. **终端报告**：彩色表格，含每个币种的准确率和全局汇总
2. **写入 `data/metrics.db` → benchmarks 表**
3. **生成 `docs/BENCHMARK.md`**：

```markdown
# Crypto-Pilot 预测基准报告

> 评估时间: 2026-05-07 14:30 UTC
> 回溯范围: 2026-04-07 ~ 2026-05-07 (30天)
> 总样本数: 120 次推理 (4币种 × 30天)

## 方向预测准确率

| 币种 | 样本数 | 方向准确率 | 信号胜率 | MAE (USD) |
|------|--------|-----------|---------|-----------|
| BTC/USDT | 30 | 63.3% | 60.0% | $1,245 |
| ETH/USDT | 30 | 58.0% | 55.6% | $42.3 |
| SOL/USDT | 30 | 55.0% | 52.0% | $5.12 |
| DOGE/USDT | 30 | 51.7% | 48.0% | $0.023 |
| **综合** | **120** | **57.0%** | **53.9%** | — |

## 响应时间 (CPU, 热缓存)

| 指标 | 平均值 | P50 | P95 |
|------|--------|-----|-----|
| 模型推理 | 24.7s | 23.1s | 38.2s |
| 数据拉取 | 1.3s | 1.2s | 2.1s |
```

### 2.4 约束

- 可指定币种 (-s) 和回溯天数 (-d)，默认 4 币种 × 30 天 = 120 次推理
- 每次推理间 `time.sleep(0.5)` 保护 CPU
- `tqdm` 进度条
- 预估总耗时: 120 × 25s = 约 50 分钟

---

## Section 3: 在线指标模块 (`src/metrics.py`)

### 3.1 API

```python
class MetricsTracker:
    def __init__(self, db: Database = None):
        """依赖注入 Database 实例"""

    # ── 写入 ──
    def record_prediction(
        self, symbol, current_price, predicted_price,
        expected_return, signal,
        cold_start_ms, inference_ms, data_fetch_ms
    ) -> int:
        """插入 predictions 表，返回 id"""

    def backfill_actual_prices(self, symbol: str = None) -> int:
        """查找 target_at 已过期的 pending 记录，
        从 Binance 拉取真实价格回填，返回回填数量"""

    # ── 查询 ──
    def get_direction_accuracy(
        self, symbol: str = None, days: int = 30
    ) -> dict:
        """返回 {sample_count, correct_count, accuracy_pct}。
        若自有数据不足 10 条，fallback 到 benchmarks 表"""

    def get_win_rate(
        self, symbol: str = None, days: int = 30
    ) -> dict:
        """返回 {sample_count, win_count, win_rate_pct}
        条件: signal=Bullish且actual正 / signal=Bearish且actual负"""

    def get_avg_timing(self) -> dict:
        """返回 {cold_start_ms, inference_ms, data_fetch_ms, sample_count}"""

    def get_prediction_stats(self) -> dict:
        """返回 {total, backfilled, pending}"""

    def get_benchmark_history(self, symbol: str = None) -> list[dict]:
        """返回 benchmarks 表记录"""

    # ── 测试 ──
    def record_test_run(
        self, unit_passed, unit_total, e2e_passed, e2e_total, success
    ) -> int: ...
    def get_latest_test_run(self) -> dict | None: ...
```

### 3.2 埋点方式（`app.py` 中）

```python
# 预测流程前
t0 = time.time()
data_feed.fetch_ohlcv(symbol)
t1 = time.time()

model_engine.predict(...)
t2 = time.time()

# 计算各阶段耗时
cold_start_ms = ModelEngine.get_last_cold_start_ms()  # 首次有值, 后续为 0
data_fetch_ms = int((t1 - t0) * 1000)
inference_ms = int((t2 - t1) * 1000) - (cold_start_ms or 0)

# 记录预测
metrics.record_prediction(
    symbol=symbol, current_price=current_price,
    predicted_price=result.predicted_price,
    expected_return=result.expected_return,
    signal=result.signal,
    cold_start_ms=cold_start_ms, inference_ms=inference_ms,
    data_fetch_ms=data_fetch_ms,
)

# 回填到期记录
metrics.backfill_actual_prices()
```

### 3.3 冷启动检测

`ModelEngine._load_model()` 是 `@st.cache_resource` 单例。在 `ModelEngine` 中增加：

```python
class ModelEngine:
    _cold_start_ms: float | None = None  # 类变量, 全局一份

    @staticmethod
    @st.cache_resource
    def _load_model():
        t0 = time.time()
        # ... 原有加载逻辑 ...
        ModelEngine._cold_start_ms = (time.time() - t0) * 1000
        return predictor
```

### 3.4 回填触发时机

- 用户每次打开 App 时在 `init_session_state` 后调用一次
- 不阻塞主流程（失败静默）
- 只在有 pending 记录时才发起网络请求（查 Binance 历史价格）

### 3.5 准确率数据优先级

```
Status Tab 查询方向准确率:
  1. 自有 predictions 表中回填完成的记录 >= 10 条 → 使用自有数据
  2. 自有数据不足 → 使用 benchmarks 表最新快照
  3. benchmarks 也为空 → 显示 "数据积累中..."
```

---

## Section 4: App 内 Status Tab UI

### 4.1 布局

`app.py` 主区域改用 `st.tabs` 分为两个 Tab：

```
Tab 1: [📊 市场预测]  — 现有功能，不变
Tab 2: [📈 系统状态]  — 新增
```

### 4.2 Status Tab 内容

```
🎯 预测准确率
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ 方向准确率     │ 信号胜率       │ 预测总次数     │ 待回填        │
│  62.5%       │  58.3%       │   120        │   18         │
│ (最近30天)    │ (B>0/A<0)    │ (自有+基准)    │ (pending)    │
└──────────────┴──────────────┴──────────────┴──────────────┘

⏱️ 响应时间
┌──────────────────┬──────────────────┬──────────────────┐
│ 模型加载 (冷启动)   │ 推理 (热缓存)      │ 数据拉取           │
│     18.2s        │     24.7s        │      1.3s        │
│   (最近1次)       │   (平均 N=120)    │   (平均 N=120)    │
└──────────────────┴──────────────────┴──────────────────┘

🪙 覆盖币对
┌──────────────────────────────────────────────────────────┐
│ 已测试: BTC/USDT, ETH/USDT, SOL/USDT, DOGE/USDT          │
│ 支持: 所有 Binance 现货交易对                              │
│ 基准报告: docs/BENCHMARK.md (2026-05-07)                  │
└──────────────────────────────────────────────────────────┘

🧪 测试状态
┌──────────────┬──────────────┬──────────────┐
│ 单元测试       │ E2E 测试      │ 最后运行       │
│  5/5 ✅      │  7/7 ✅      │ 2026-05-07   │
└──────────────┴──────────────┴──────────────┘
```

### 4.3 边缘状态

| 状态 | 展示方式 |
|------|----------|
| 无任何数据 (首次启动) | 所有数值显示 "—"，加 `st.info("数据将随着使用自动积累")` |
| 自有数据 < 10 条 | 显示 benchmark 数据 + `st.caption("数据来源: 基准报告 (自有数据积累中)")` |
| 冷启动未发生 | 显示 "尚未测量" |
| 基准报告未运行 | 覆盖币对区域只显示 "支持所有 Binance 现货对"，不显示已测试列表 |

---

## Section 5: 测试状态记录

### 5.1 `tools/record_test_run.py`

```python
"""运行测试并记录结果到 metrics.db"""
# 1. 执行 python run_tests.py → 解析输出
# 2. 统计通过/失败数
# 3. 写入 test_runs 表
# 4. 打印摘要
# 若 E2E 测试未配置 (无 Playwright / 服务未启动)，e2e_* 字段填 -1 表示跳过
```

### 5.2 使用方式

```bash
# 手动运行
python tools/record_test_run.py

# 或 CI/定时触发
python tools/record_test_run.py && streamlit run src/app.py
```

---

## 文件清单

```
新增文件:
  src/database.py                    # SQLite 管理层
  src/metrics.py                     # 指标采集与查询
  tools/backtest_simulate.py         # 离线回溯脚本
  tools/record_test_run.py           # 测试状态记录
  docs/BENCHMARK.md                  # 基准报告 (脚本生成)

修改文件:
  src/app.py                         # 增加 st.tabs + Status Tab
  src/model_engine.py                # 增加冷启动耗时记录
  README.md                          # 引用基准报告关键数字
```

## 不做的

- 不引入第三方仪表盘库 (Grafana / Streamlit dashboard 插件)
- 不计算复杂的金融指标 (夏普比率、最大回撤、卡玛比率)
- 不实现自动化定时回填 (用用户打开 App 的时机自然触发)
- 不回填离线回溯脚本的 predictions 记录 (离线样本不进入在线准确率统计)
