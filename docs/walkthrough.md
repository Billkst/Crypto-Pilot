# Phase 2 UI Implementation Walkthrough

## 1. 核心图表组件 (`src/chart_renderer.py`)

实现了 `ChartRenderer` 类，使用 `plotly.graph_objects` 绘制专业的 K 线图。

- **功能特性**:
    - **历史数据**: 使用灰色 (`gray`) K 线展示，作为背景参考。
    - **预测数据**: 使用蓝色 (`#1f77b4`) K 线展示，高亮显示未来趋势。
    - **回测数据**: 支持传入昨日预测数据 (`backtest_df`)，使用橙色虚线叠加展示，用于验证准确性。
    - **视觉优化**: 
        - 隐藏 Rangeslider 以保持简洁。
        - 使用 `plotly_dark` 模板适配深色模式。
        - 添加垂直虚线标记当前时间分割点。

```python
# 示例用法
fig = ChartRenderer.render(hist_df, pred_df, backtest_df)
st.plotly_chart(fig)
```

## 2. Streamlit 主程序 (`src/app.py`)

实现了完整的 Streamlit 应用程序框架，串联了数据获取、模型推理和策略分析流程。

- **页面布局**:
    - **Sidebar**:
        - 交易对输入 (默认 `BTC/USDT`)
        - 信号阈值滑块 (Threshold)
        - 止损比例滑块 (Stop Loss)
        - 高级模型参数 (Temperature, Top P, Samples)
        - "开始预测" 按钮
    - **Main Area**:
        - **KPI 卡片**: 展示当前价格、预测价格、涨跌幅、交易信号 (🟢/🔴)、建议止损价。
        - **交互式图表**: 调用 `ChartRenderer` 展示预测结果。
        - **数据详情**: 提供折叠面板查看详细预测数据。

- **逻辑流程**:
    1. **初始化**: 设置页面配置，初始化 `session_state` (`hist_df`, `pred_df`, `signal_result`)。
    2. **用户交互**: 监听 Sidebar 参数调整。
    3. **预测执行**: 点击按钮后：
        - 调用 `DataFeed` 获取并预处理数据。
        - 调用 `ModelEngine` 进行推理 (CPU)。
        - 调用 `StrategyEngine` 生成交易信号。
        - 更新 `session_state` 并刷新页面。
    4. **异常处理**: 捕获网络错误、数据不足等异常并友好提示。

## 3. 验证与测试

- **代码检查**: 使用 `python -m py_compile` 验证了所有新文件的语法正确性。
- **依赖整合**: 确保 `app.py` 正确引用了 `src` 下的各个模块 (`config`, `data_feed`, `model_engine`, `strategy`)。

## 下一步计划 (Phase 3)

- 执行单元测试 (`tests/`) 覆盖新模块。
- 进行集成测试，确保前后端数据流稳定。
- 完善回测逻辑的数据加载部分。
