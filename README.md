# Qwen3.6-35B-A3B-FP8 × RTX PRO 6000：单卡与双卡 vLLM 实测

这是一份可复现的本地推理基准分析：在相同的 300 请求、20 最大请求并发、每请求 4,096 输入 token + 1,024 输出 token 负载下，对比 1× 与 2× RTX PRO 6000 部署 Qwen3.6-35B-A3B-FP8 的吞吐、首 token 延迟、逐 token 延迟与投机解码表现。

> 核心结论：双卡把输出吞吐从 **1,451.64 tok/s** 提升到 **2,009.36 tok/s（+38.4%）**，平均 TTFT 降低 **56.7%**，P99 TTFT 降低 **70.6%**；代价是按 GPU·秒计的单位输出成本上升约 **44.5%**。双卡的主要价值是容量与尾延迟，而不是最佳算力成本。

![吞吐与完成时间对比](assets/throughput.svg)

## 阅读报告

- [完整中文实验报告](report.md)
- [结构化原始数据](data/benchmark.csv)
- [单卡原始输出](data/raw/pro6000-1x.txt)
- [双卡原始输出](data/raw/pro6000-2x.txt)

## 复现图表

图表生成器仅使用 Python 标准库：

```bash
python3 scripts/generate_charts.py
```

生成结果位于 `assets/`。图表画布固定为纯白 `#FFFFFF`，适合 GitHub、博客和演示文稿引用。

## 数据边界

当前结果没有记录 vLLM 版本、双卡并行策略、推理参数、GPU 功耗/频率与重复试验方差，因此报告只描述“这两次运行的观测差异”，不把全部差异归因于 GPU 数量。报告还单独标注了两个需要核查的统计口径：`Peak concurrent requests` 高于配置并发 20，以及 `Peak output token throughput` 低于全程平均输出吞吐。

## License

[MIT](LICENSE)
