# Crypto-Pilot 预测基准报告

> ⚠️ 基准报告尚未生成 — 需要完整依赖环境 (torch, transformers 等)。

## 如何生成

```bash
# 1. 安装完整依赖
pip install -r requirements.txt

# 2. 运行基准测试 (30天回溯, 约50分钟)
python3 tools/backtest_simulate.py -d 30

# 或快速验证 (5天, 约8分钟)
python3 tools/backtest_simulate.py -d 5
```

## 预期指标

基准测试在 4 个主流币种 (BTC/USDT, ETH/USDT, SOL/USDT, DOGE/USDT) 上运行 30 天历史回溯，
产出以下指标:

- **方向准确率**: 预测涨跌方向与实际方向一致的比例
- **信号胜率**: Bullish/Bearish 信号实际方向正确的比例
- **MAE**: 预测 24h 后价格与实际价格的绝对误差均值
- **平均推理耗时**: CPU 推理的单次平均耗时

> 回溯结果不代表未来表现。本报告仅为技术基准，
> 不构成任何投资建议。
