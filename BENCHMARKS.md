# Performance / 性能记录

2026-10-15 · macOS x64 · 本地独立测试窗口 · 1.0.0 → 1.1.0

| 项目 / Measurement | 1.0.0 | 1.1.0 | 样本 / Samples |
| --- | --- | --- | --- |
| 主屏 ultra 截图调用中位数 / Screenshot call median | 490 ms | 122 ms | 每版 5 次 / five per version |
| 相同六步操作 / Same six-action workflow | 8113 ms | 745 ms median | 基线 1 次，优化版 3 次 / baseline one, optimized three |
| 新增控件操作链 / New semantic workflow | 无 / unavailable | 589 ms tool, 722 ms including discovery | 五步 + 观察，1 次 / five actions plus observation, one sample |

截图样本中位数减少 75.1%；相同六步调用中位数减少 90.8%，约 10.9 倍。优化版六步样本为 766、745、739 ms，全部 6/6 成功。

The six-action test verifies the header, shortcut, Chinese/emoji typing, exact draft, button activation and actual result callback. Timings include final image/text observation but exclude fixture compilation, MCP startup/status warmup, model reasoning and real network messaging. The semantic sample includes field discovery only in the reported 722 ms wall time, not the 589 ms tool time. It is a different workflow and must not be treated as the identical six-action comparison.

OCR 并未被证明更快。未找到目标时的 OCR 回退中位数，基线为 1489 ms、优化版为 1587 ms；冷调用为 2914 与 3912 ms。主要收益来自避免不必要的 OCR、减少 AX IPC、控件操作及内存截图，不是声称 OCR 引擎本身加速。

OCR fallback itself did not improve in these samples. The successful six-action optimized runs used zero OCR time. Native capture used `coregraphics-memory` on this machine; the modern ScreenCaptureKit branch and Windows backend were not benchmarked here.

样本量小，基线只有一次完整流程，机器负载和画面不同也会影响结果。截图编码后的 payload 大小随屏幕内容变化。以上数据不是所有应用、所有系统、真实消息发送或完整模型任务的速度保证。没有为了速度降低精确断言或在不确定输入后重放。

原始数值 / Raw measurements: [macos-2026-10-15.json](benchmarks/macos-2026-10-15.json)。不含屏幕图像、识别文字、用户路径或账号信息。

复测 / Reproduce:

```sh
cd codex-computer-control
npm ci --ignore-scripts
npm run build:native
node tests/benchmark-native.js
node tests/live-macos.js
node tests/live-macos.js --semantic
```

截图基准只返回耗时、大小、来源和识别条数。两个 live 脚本模式仅操作各自创建的本地测试窗口。每次使用独立数据目录，测试结束销毁；不会清除个人插件的 STOP。
