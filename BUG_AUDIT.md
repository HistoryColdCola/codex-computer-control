# 验证与已知限制 / Validation and limits

2026-10-15 · Version 1.1.0

## 本次变更 / Changes

- JS 仍是统一入口，负责 MCP、系统选择、整批校验、前台绑定、截止时间和 STOP。
- Swift：内存截图、一次缩放、批量 AX 属性读取、控件就绪等待、复用 OCR 请求，以及 invoke / set_value / focus_element。
- C# / PowerShell：UIA 缓存属性、控件 ID 与 InvokePattern / ValuePattern / focus、OCR 前的短暂 UIA 就绪等待。
- 默认图像观察附带 AX/UIA 控件信息，不自动 OCR；显式请求仍可使用 OCR。
- 不确定原生动作不换方式重试，不清除用户急停。

## 验证证据 / Evidence

23 项 JS 单元/子进程测试通过，包括原生 invoke 选择、执行失败不再补点、控件动作整批校验、自动文字模式不做 OCR、输出 none 保持无观察开销，以及原有超时、前台、坐标和 STOP 检查。真实 MCP 握手和默认三个工具验证通过。

Swift 在本机 Swift 5.8 / macOS 13 SDK 上编译通过；实际捕获后端为 coregraphics-memory。相同六步窗口测试三次全部 6/6 成功，分别 766、745、739 ms；新的五步控件路径也通过，含控件发现的墙钟时间为 722 ms。最终图像和结果断言均包含在六步调用中。

[完整性能记录](BENCHMARKS.md) 与 [原始数值](benchmarks/macos-2026-10-15.json) 可复核。没有真实消息发送，不包含模型推理时间。基线完整流程只有一次，不能视为广泛统计结论。OCR 回退本身未测得加速。

A dedicated local AppKit fixture verifies actual Chinese/emoji input and button callback results. It does not establish QQ/WeChat delivery, all-app compatibility or end-to-end model latency.

## 修复和防回归 / Corrections

原生控件调用可能在较短的消息超时内返回 cannotComplete，即使请求可能已生效。现在为动作使用独立的 1 秒原生消息超时；错误仍保留 uncertain_action 和 STOP，绝不补发坐标点击。控制 ID 有 30 秒有效期和 512 项上限，绑定前台进程；禁用和安全字段拒绝操作。

AX 初次启动或刚更新时可能短暂无目标。现在在有界时间内重新读取 AX，之后才 OCR。读取字段优先使用 AXValue；控件信息不通过长期缓存冒充新观察。测试窗口使用独立数据目录，结束销毁，避免在后续测试中恢复/清除个人插件的 STOP。

保留 1.0.0 中的整批参数校验、异常释放和不确定输入保护；依赖锁文件使用可移植 node_modules 路径，并由回归测试验证。

## 未验证与限制 / Not verified and limits

- Windows C#/PowerShell 实现已随包提供，但没有在这台 Mac 上编译或运行 Windows 原生后端。Windows CI 配置仍不代表远程通过；UIPI、DPI、UIA、WinRT OCR 和语言包需要 Windows 真机验证。
- ScreenCaptureKit 分支只在新 Swift/SDK 上编译；本机旧 SDK 无法验证该分支。旧系统动态 Core Graphics 与当前截图路径已实际测量。新系统配旧 SDK 时使用命令兼容路径。
- 仅支持主屏；Mac 使用逻辑像素，Windows 使用 DPI 感知物理像素。Windows 独立显示器休眠检测尚未实现，锁定/安全桌面和 UIPI 仍受系统限制。
- Mac 的应用名解析使用当前 SDK 仍支持的已弃用 fullPath(forApplication:)；编译有弃用警告。
- 同进程内布局变化无法全部自动检测。OCR、长文本、非标准控件、键盘布局及应用事件处理存在差异。set_value 可能不产生相同的业务回调，必须验证。
- 正常异常尝试释放输入；强制终止辅助进程无法保证清理所有键鼠状态。STOP 需要用户观察后恢复。
- 没有以减少检查、弱化断言、模糊匹配或重复发送换取速度。

This is a measured optimization on a small local workload, not a bug-free, universal compatibility or hard real-world latency guarantee.
