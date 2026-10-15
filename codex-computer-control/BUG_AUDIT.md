# BUG 检查 / Bug audit

检查日期 / Audit date: 2026-10-15 · Source version: 0.3.1

## 已修复 / Fixed

1. **急停阻止释放 / STOP blocked releases.** EventBridge 对所有事件执行 STOP/前台检查，导致 finally 中的 key-up/mouse-up 仍可能被拒绝。现在跟踪按下事件及原始 PID，仅允许对应释放绕过这些检查，并投递回原始进程。New input remains blocked; tracked releases target the original process even after focus changes.
2. **按下包装函数异常 / Exceptions after down events.** 拖拽 mouseDown 原本在 try 外；快捷键在 keyDown 返回后才记入释放列表。若原生事件已发出而包装函数抛错，释放会遗漏。现在将鼠标按下纳入 try，提前登记按键，并在某个释放失败时继续尝试其余释放。Cleanup now covers wrapper failures and attempts every key release.
3. **Unicode 输入缺少 finally / Unicode lacked guaranteed release attempt.** Unicode key-down 抛错时不会尝试 key-up。现在使用 finally 尝试释放。A release is attempted even when posting the down event raises.
4. **握手启动桌面进程 / Eager desktop worker startup.** 仅连接 MCP 和读取 schema 也会启动并导入桌面后端。现在首次实际 desktop_step 请求才初始化执行进程。Protocol-only connections no longer start a desktop worker.

## 验证 / Validation

- 34 项模拟桌面单元测试通过 / 34 mocked-desktop unit tests passed.
- 真实 MCP 初始化、默认三个工具发现、非法动作拒绝通过 / Real MCP initialization, three-tool discovery and invalid-action rejection passed.
- Python 源码编译、JSON 解析及发布内容扫描 / Python compilation, JSON parsing and release-content inspection.
- 新增回归覆盖 STOP 后原 PID 释放、新输入仍被阻止、Unicode 异常释放、mouseDown 异常释放和多个按键释放失败处理。New regressions exercise the fixes above.

## 验证边界与已知限制 / Limits

未运行真实应用键鼠端到端测试，未重新安装当前用户已启用的插件，未向联系人发送消息。No live application input, reinstall or real messaging was performed in this audit. Passing mocked tests does not prove every macOS version or application accepts process-directed events.

硬杀执行进程无法保证释放全部原生输入；超时仍需人工观察和恢复。A forcibly terminated worker cannot guarantee key/button cleanup. STOP must remain active until the user inspects the outcome.

仅支持主屏；OCR 可能误识别；文本匹配忽略空白；窗口内容变化不会自动使 view_id 过期。Only the primary display is supported; OCR and stale layouts require fresh observation.

依赖使用版本范围，未做所有依赖版本或全部 macOS 版本矩阵验证。Dependencies have bounded version ranges, but the full dependency/OS matrix has not been tested. The installer and real permission workflow were reviewed, not rerun.

本检查不是“无 BUG”保证。This audit is not a guarantee of bug-free behavior.
