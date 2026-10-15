# Codex Computer Control · Codex 电脑控制

[English](README.en.md) · [架构](ARCHITECTURE.md) · [验证与已知限制](BUG_AUDIT.md)

**1.1.0：JavaScript 主控 + 平台原生后端。** Node.js 自动识别系统，通过统一 MCP 接口调度 macOS 的 Swift 或 Windows 的 C# 后端。日常运行不需要 Python，也不会把 Mac 的操作脚本直接套用在 Windows 上。

## 1.1.0：按实际耗时优化

同一本地六步流程从 8.113 秒降至三次中位数 0.745 秒；主屏截图中位数从 490 ms 降至 122 ms。均为本机小样本测试，排除模型推理和真实消息发送，详见 [性能记录](BENCHMARKS.md)。

新增控件 `element_id` 与 `invoke / set_value / focus_element` 操作。`click_text` 遇到支持原生执行的控件会直接调用，只有未提供该能力时才按坐标点击；一旦调用报错，不自动换方式重试。默认观察同时返回 AX/UIA 控件信息，不自动进入 OCR；显式 `include_text=true` 或 `output=text` 仍允许完整 OCR 回退。

Mac 14+ 在 Swift 5.9+ SDK 构建时使用 ScreenCaptureKit 单帧接口；本机 Mac 13 使用 Core Graphics 内存截图。旧 SDK / 新系统不具备相应接口时保留系统截图命令作为兼容路径。缩略图只进行一次缩放。

## 分工

| 层 | 技术 | 负责内容 |
| --- | --- | --- |
| 统一入口 | JavaScript / Node.js | 系统识别、MCP、参数校验、动作编排、坐标换算、时间预算、错误和急停状态 |
| macOS 后端 | Swift / AppKit / Core Graphics / Vision | 应用激活、前台和权限检查、键鼠事件、图片处理、辅助功能读取、本机 OCR |
| Windows 后端 | C# / Win32 / UI Automation | DPI 感知、应用窗口、SendInput、屏幕捕获、控件读取 |
| Windows 启动与 OCR 适配 | 系统自带 Windows PowerShell 5.1 / WinRT | 编译加载 C#、持久进程通信、Windows OCR 调用 |

JS 是默认运行入口。原生辅助进程按需启动并复用，使用 JSON 行协议；不开放远程控制端口。Linux 返回明确的不支持错误。

## 安装

两端均需要 **Node.js 22+（含 npm）和可用的 Codex CLI**。源码包第一次安装需要网络下载锁定的 npm 依赖。

### macOS

需要 Xcode Command Line Tools 中的 Swift 编译器；缺少时先运行 `xcode-select --install` 并完成系统安装。后端使用 macOS 10.15+ 的 API；本次本地编译环境为 Swift 5.8 / macOS 13 SDK，未验证所有系统版本。

在仓库根目录运行：

```sh
node codex-computer-control/scripts/install.js
```

也可双击 `install.command`。安装时构建本机架构的 Swift 可执行文件。辅助功能和屏幕录制权限需要用户在“系统设置 → 隐私与安全性”中手动授予实际宿主或辅助进程，编译成功不等于已经获得系统权限。

### Windows

面向 Windows 10/11 交互式桌面，使用系统自带的 **Windows PowerShell 5.1、.NET Framework 和桌面组件**。不要求另外安装 Python 或 .NET SDK。源码安装时使用系统 C# 编译能力校验后端。

在仓库根目录打开终端运行同一条命令，或双击 `install.cmd`：

```powershell
node codex-computer-control/scripts/install.js
```

安装器优先查找 `codex.exe`，也支持官方 npm 全局安装的 `@openai/codex/bin/codex.js`。找不到时用 `CODEX_CLI` 指定真实可执行文件路径。Node.js 使用官方 Windows 发行版的标准 npm 布局。企业 PowerShell 策略、下载文件标记或系统缺失的组件可能阻止加载；安装器不会放宽机器级执行策略。使用 `RemoteSigned` 启动系统 PowerShell。系统原生 ARM64 Windows 未做验证。

两端都在独立的个人目录安装副本，发布源码目录不会生成 `.mcp.json` 或 `node_modules`：

- macOS：`~/.local/share/codex-computer-control/marketplace/`
- Windows：`%LOCALAPPDATA%\codex-computer-control\marketplace\`

安装器注册 `codex-computer-control-local` 市场，安装 `codex-computer-control@codex-computer-control-local`。更新同样运行安装器，旧副本会保存在个人目录的 `marketplace-backup-*` 中，已有 STOP 不会被自动清除。然后重启 Codex 并开启新聊天。

源码尚未运行安装器时，不支持直接通过远程市场安装：本机 MCP 启动路径需要生成。仓库未指定开源许可证，发布者需要自行选择授权条款。

## 使用

默认仍提供三个工具：

| 工具 | 行为 |
| --- | --- |
| `desktop_status` | 系统、后端、主屏大小、前台标识、权限/可用性、急停状态 |
| `desktop_screenshot` | 主屏原分辨率截图；`format=jpeg` 或 `png` |
| `desktop_step` | 最多 32 个动作，一次结果；支持图像、文字或省略成功截图 |

例如：“用 Codex 电脑控制打开计算器，计算 123 × 456，并核对结果。”应用名称在两个系统上可能不同；Windows 启动新应用时使用 `notepad.exe` 这样的可执行文件名或 `.exe` 完整路径，不接受脚本/URL 作为启动目标。

先观察（这是 MCP 工具参数 JSON，不是终端命令）：

```json
{"app":"Calculator","actions":[],"profile":"detail","include_text":true}
```

Windows 示例先观察记事本：

```json
{"app":"notepad.exe","actions":[],"profile":"detail","include_text":true}
```

确认目标应用、布局和输入位置后再发送动作。例如当前输入框已正确聚焦：

```json
{"actions":[{"action":"type","text":"本地测试 / local test"}],"profile":"detail"}
```

消息发送任务必须先在聊天标题区域验证收件人，再在输入框区域验证完整草稿；侧栏联系人名字不代表当前收件人。失败后先检查 `completed`、`error`、`results` 和屏幕，不盲目重放。

## 参数

| `desktop_step` 参数 | 默认 | 含义 |
| --- | --- | --- |
| `actions` | 必填 | 0–32 项；空列表用于观察 |
| `app` | 无 | 激活目标并绑定前台进程；不填则绑定当前前台进程 |
| `profile` | `ultra` | 512px / JPEG Q20；`fast` 768px/Q30；`detail` 原屏幕坐标分辨率/Q85 |
| `output` | `image` | `image`、`text`、`none`；错误尽可能返回观察 |
| `include_text` | `auto` | 自动附带 AX/UIA，不做 OCR；`true` 允许 OCR；`false` 关闭附加文字 |
| `view_id` | 无 | 使用上一张图片的坐标，自动换算裁剪偏移和缩放 |
| `crop` | 无 | `{x,y,width,height}`，始终使用屏幕坐标 |
| `settle_ms` | `0` | 动作后等待 0–500 毫秒 |
| `budget_ms` | `8000` | 动作预算 100–20000 毫秒；含观察的硬期限最多 20 秒 |

支持动作：

| 动作 | 参数 |
| --- | --- |
| `click` | `x,y`；`button=left/right/middle`；`clicks=1..3` |
| `move` | `x,y`；`duration=0..1` 秒 |
| `drag` | `start_x,start_y,end_x,end_y`；`duration=0.1..2`；`button=left/right` |
| `scroll` | `clicks=-100..100`；可选 `horizontal`，正数向上/右 |
| `press` | `key`；`presses=1..50` |
| `hotkey` | `keys` 数组，1–6 个键 |
| `type` | `text`，最多 10000 个 UTF-16 单元；不修改剪贴板 |
| `invoke` | `element_id`，执行已观察到的控件 |
| `set_value` | `element_id,value`，设置支持写入的字段；需检查结果 |
| `focus_element` | `element_id`，聚焦支持该能力的控件 |
| `wait` | `seconds=0..1`，每批合计最多 2 秒 |
| `click_text` / `assert_text` | `text`；可选 `region`、`timeout_ms=0..3000` |

控件 ID 来自观察结果，30 秒过期，最多缓存 512 项，绑定当前前台进程；以后端实际返回的 `actions` 能力为准。安全输入框和禁用控件不支持这些操作。`set_value` 不是键盘事件，部分应用可能不触发相同业务回调，必须验证。

文本匹配去除空白后要求唯一匹配；不是字节级比较。macOS 先读取 AX，未找到目标再用 Apple Vision；Windows 先读取 UI Automation，未找到目标再尝试 Windows OCR。Windows OCR 需要系统支持及已安装的识别语言，不可用时会明确报错。

常用键名：`enter/return`、`esc/escape`、`tab`、`space`、`backspace`、`delete`、方向键、`home/end/pageup/pagedown`、`a..z`、`0..9`、`f1..f12`。`command/cmd/meta` 在 Mac 为 Command，在 Windows 为 Windows 键；Windows 还支持 `win/windows/insert`，Mac 会在执行前拒绝这些名称。快捷键的物理字母键映射以常见键盘布局为准；Unicode 输入用于文字内容。

## 坐标、急停与期限

仅支持主屏。macOS 是逻辑像素，Retina 图像会换算；Windows 使用启用 DPI 感知后的物理像素。二者数值不能直接复用。

从缩略图定位时传回 `view_id`。OCR/控件表格坐标、`crop` 和 `region` 始终是屏幕坐标，不要混用。最多保留 16 个视图、120 秒过期；前台进程变化、屏幕尺寸变化或后端重启后需要重新观察。同一进程内部窗口/布局变化无法自动完全识别，仍需模型检查。

鼠标移到主屏左上角，或运行 `codex-computer-control/stop.command`（Mac）/`stop.cmd`（Windows）即可阻止后续输入。STOP 也阻止截图和应用激活；状态查询仍可用。用户检查部分执行结果后，运行对应 `resume.command` / `resume.cmd` 才恢复。已经发出的事件可能完成。

JS 会在硬期限终止挂起的后端。可能已输入时设置 STOP，返回 `uncertain_action`，不自动恢复和重放。正常异常会尝试释放按键/鼠标，但强制结束进程不能保证释放。Windows 的释放事件是系统输入释放；Mac 键盘发回原目标进程，鼠标通过会话事件通道释放。用户应检查是否有键鼠残留状态再继续。

默认动作预算 8 秒、硬期限 10 秒，硬期限最多 20 秒。期限依赖主机进程被调度，不包含模型推理，也无法约束整机挂起。不能保证整个用户任务在 20 秒内完成。

## 测试与发布

开发环境在插件目录执行：

```sh
cd codex-computer-control
npm ci --ignore-scripts
npm test
npm run build:native
npm run check:protocol
node tests/protocol.js --native-status
```

单元测试用模拟后端验证 JS 调度和真实子进程通信；协议测试验证真实 MCP 初始化、三个工具和非法动作拒绝。`--native-status` 只查询真实系统状态，不执行键鼠动作。Mac 可选运行 `node tests/live-macos.js`，它只操作自己创建的本地测试窗口并关闭，不发送网络消息。CI 分别配置 macOS 编译 Swift、Windows 编译 C# 和 PowerShell 语法检查。配置 CI 不代表它已在远程通过。

性能原始数值见 [BENCHMARKS.md](BENCHMARKS.md)。返回结果提供 `native_calls` 分项耗时，可区分截图、控件读取和输入。

本次本机验证和未验证范围见 [BUG_AUDIT.md](BUG_AUDIT.md)。macOS 的本地测试窗口验证范围见检查记录；Windows 未做真机验证。请勿据此宣称两端所有应用都已兼容。

上传到 GitHub 时以本文件所在目录为仓库根目录，包含隐藏的 `.agents`、`.github`、`.codex-plugin` 和 `.gitignore`。不要上传 `node_modules`、`bin`、生成的 `.mcp.json`、本机截图或凭证。`package-lock.json` 应提交。

```text
.agents/plugins/marketplace.json
.github/workflows/ci.yml
README.md / README.en.md / ARCHITECTURE.md / BUG_AUDIT.md
install.command / install.cmd
codex-computer-control/
  package.json / package-lock.json
  .codex-plugin/plugin.json
  src/                   # JS 主控、MCP、进程桥接、参数和系统识别
  native/macos/          # Swift
  native/windows/        # C# + Windows PowerShell
  scripts/               # 安装、构建、测试和暂停/恢复
  tests/
  skills/computer-control/SKILL.md
  stop.command / stop.cmd / resume.command / resume.cmd
```

服务没有网络监听端口；OCR 由本机系统执行。但返回的屏幕和文本会进入 Codex 模型会话，宿主的数据处理政策仍然适用。依赖安装需要联网。系统权限、安全桌面和 Windows UIPI 限制仍然适用，本项目不会绕过它们。

卸载：

```sh
codex plugin remove codex-computer-control@codex-computer-control-local
```

卸载不删除发布源码、个人安装来源或备份目录。修改源码后需重新运行安装器，再重启 Codex。
