# Codex Hands · Codex 双手

[English documentation](README.en.md) · [BUG 检查记录 / Bug audit](BUG_AUDIT.md)

面向 macOS 的本机桌面操作插件。当前源码版本：**0.3.1**。

通过本机 MCP，让 Codex 读取 macOS 主屏截图、点击/双击/右键、拖拽、滚动、按快捷键、输入中文，并打开桌面应用。无需额外 API 密钥，不开放网络控制端口。截图会提供给当前 Codex 模型。

## 0.3.0：极速工作流

`desktop_step` 一次最多执行 32 个相关动作，结束后直接返回截图和执行耗时。默认只提供三个核心工具，鼓励本机脚本执行完整的确定流程。使用持久 MCP 连接，避免每次启动 Python、保存截图再读取。指定 `app` 会激活目标应用，并在动作和输入分段之间检查前台应用。

默认 `ultra` 使用 512 像素宽、JPEG 质量 20；`fast` 为 768 像素/质量 30，`detail` 为完整逻辑分辨率/质量 85。默认零等待，键鼠固定间隔为 5 ms，单击取消额外 120 ms 等待。macOS 15 之前优先使用 Core Graphics 内存截图，不可用时回退系统截图命令。

根据缩略图定位时，在下一次 `desktop_step` 传回 `view_id`，服务会把图片坐标映射到屏幕。OCR/辅助功能 x/y 和 `crop`/`region` 永远是逻辑屏幕坐标，不应与缩略图坐标混用。局部细查用 `crop` 和 `profile="detail"`，无损全屏仍可用 `desktop_screenshot(format="png")`。

新增 `click_text` 和 `assert_text` 动作，读取当前应用辅助功能信息，不支持时用本机 Apple Vision OCR。精确唯一匹配，可指定屏幕 `region` 和 `timeout_ms`，供脚本自行等待界面变化和验证条件。条件失败立即停下，不自动重放。`output="text"` 不返回图片，`include_text=true` 返回图文，`output="none"` 成功时跳过截图；一般失败返回画面，休眠、急停和硬超时可能只有状态。

已知布局尽量只需一次观察、一次本地执行：选择联系人，断言聊天标题，输入，断言输入框草稿，发送，再断言结果。发送前必须核对聊天标题区域和草稿区域，侧栏联系人名字不能证明当前收件人。未知布局先观察，不猜测。

执行放在持续复用的隔离进程中，不会每步重新启动；父进程负责硬期限。默认 `budget_ms=8000` 对应 10 秒硬期限，最大 20 秒。阻塞系统调用会终止执行进程并返回 `uncertain_action`；输入可能已生效时设置 STOP，必须人工恢复和观察，不能重发。休眠/锁定时立即拒绝输入，需要人工唤醒。模型推理和整台主机暂停运行不受脚本控制。输入采用 Apple 的 [CGEventPostToPid](https://developer.apple.com/documentation/coregraphics/cgevent/posttopid%28_%3A%29?language=objc) 投递到前台应用，避免旧 HID 通道。

性能取决于机器、应用、系统权限、OCR 和模型延迟。本发布包不附带开发机器的历史测试结果，也不保证用户任务在 20 秒内完成。

## 安装

需要 macOS、Python 3.10+ 和 Codex。下载或克隆仓库，在仓库根目录运行：

```sh
python3 codex-hands/install.py
```

也可以双击根目录的 `install.command`。安装器会查找 PATH 中的 `codex` 及常见应用内 CLI 路径，创建独立 Python 环境，注册 `codex-hands-local` 本地市场并启用插件。

安装后重启 Codex，开启新聊天。在 **系统设置 → 隐私与安全性** 中，给运行服务的 Codex/ChatGPT 或 Python 开启 **辅助功能** 和 **屏幕录制** 权限。以 macOS 实际显示的授权对象及 `desktop_status` 的结果为准。这些系统权限需要用户手动开启。

运行环境和服务位于 `~/.local/share/codex-hands/`。安装后保留仓库目录；更新时需从这里重新运行安装器。`.mcp.json` 按本机路径生成，已被 Git 忽略。其他电脑需要重新运行安装脚本，本版本不支持跳过脚本直接从远程插件市场安装。

## 使用

例如：“用 Codex 双手打开计算器，计算 123 × 456，并核对结果。”

默认三个工具：`desktop_step`、`desktop_status`、`desktop_screenshot`。`desktop_step` 支持 click、move、drag、scroll、hotkey、press、type、wait、click_text、assert_text 动作。兼容旧独立工具可使用 `CODEX_HANDS_LEGACY_TOOLS=1 python3 codex-hands/install.py` 安装。

当前只支持主屏，Retina 截图换算成鼠标逻辑坐标。把窗口移到主屏后操作。中文通过 Unicode 键盘事件输入，不修改剪贴板；个别应用可能忽略这些事件。插件不能绕过系统权限，受保护界面和安全输入框不保证可操作，并仍受宿主执行权限和用户任务授权约束。

## 暂停与卸载

鼠标移到主屏左上角会触发键鼠紧急中止。双击 `codex-hands/stop.command`，阻止后续截图、键鼠操作和应用启动；已发出的短操作可能完成。恢复时运行 `codex-hands/resume.command`，并将鼠标移离左上角。

```sh
codex plugin remove codex-hands@codex-hands-local
```

卸载不会删除源码和 `~/.local/share/codex-hands/`，需要时自行清理。

## 测试和更新

安装后在仓库根目录运行：

```sh
~/.local/share/codex-hands/venv/bin/python -m unittest discover -s codex-hands/tests -v
~/.local/share/codex-hands/venv/bin/python codex-hands/tests/check_protocol.py
```

单元测试使用模拟桌面，覆盖参数、暂停、Retina 坐标、Unicode 和异常时的键鼠释放。协议测试验证真实 MCP 初始化、工具发现和错误返回，不操作真实桌面。真实桌面操作需在授权的宿主中验证。修改源码后重新运行安装器，再重启宿主。

可选完整本机流程测试（需要 Tkinter）：

```sh
~/.local/share/codex-hands/venv/bin/python codex-hands/tests/live_workflow.py
```

只操作自己创建的模拟聊天窗口，不联网、不向真实联系人发送消息，结束时关闭窗口。OCR 可能把 `I` 和 `l` 等相似字形混淆；严格断言会停止，需要局部细查，不能把失败当成功。

可选只读截图基准（需要屏幕录制权限，不发送消息）：

```sh
~/.local/share/codex-hands/venv/bin/python codex-hands/tests/benchmark_capture.py
```

使用 `--baseline /path/to/old/server.py` 比较旧版；`--output` 指定结果文件。测试连接保持打开，第一帧单列为冷调用，其余帧计算中位数。

## 文件结构

```text
README.md
.gitignore
install.command
.agents/plugins/marketplace.json
codex-hands/
  .codex-plugin/plugin.json
  .gitignore
  server.py
  install.py
  install.command
  requirements.txt
  stop.command
  resume.command
  skills/desktop-hands/SKILL.md
  tests/
```

## 上传到 GitHub

将本文件所在文件夹的内容作为仓库根目录提交。建议用 Git 上传，确保隐藏的 `.agents`、`.codex-plugin` 和 `.gitignore` 也被包含：

```sh
git init -b main
git add .
git commit -m "Initial Codex Hands plugin"
```

在 GitHub 创建空仓库，再按页面说明添加远程地址并推送。本文件夹不包含虚拟环境、机器专属 MCP 配置、API 密钥或 Cloudflare 凭证。

插件结构参考 [OpenAI 插件打包文档](https://developers.openai.com/plugins/build/plugins)，本机接入见 [MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。此服务在 Mac 本机运行，不部署到 Cloudflare Workers。

## 参数与返回值

`desktop_step` 的 `actions` 必填，空列表用于观察，最多 32 项。下表中的坐标默认是主屏逻辑像素。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `app` | 空 | 应用名；激活并在执行中检查前台应用 |
| `profile` | `ultra` | `ultra` 512px / Q20；`fast` 768px / Q30；`detail` 不缩小 / Q85 |
| `output` | `image` | `image` 返回图像；`text` 返回 AX/OCR；`none` 成功时省略观察 |
| `view_id` | 空 | 使用先前截图的图片坐标；最多缓存 16 帧，120 秒过期 |
| `crop` | 空 | `{x,y,width,height}`，主屏逻辑坐标裁剪区域 |
| `include_text` | `false` | 图像模式同时提取可访问文本或 OCR |
| `settle_ms` | `0` | 动作后等待 0–500 毫秒 |
| `budget_ms` | `8000` | 动作预算 100–20000 毫秒；父进程硬期限最多 20 秒 |

动作示例（JSON 工具参数，不是 shell 命令）：

```json
{"app":"Calculator","actions":[],"profile":"detail","include_text":true}
```

观察目标后再执行，例如输入计算式；应用名称必须能在本机解析：

```json
{"app":"Calculator","actions":[{"action":"press","key":"esc"},{"action":"type","text":"123*456"},{"action":"press","key":"enter"}],"profile":"detail"}
```

`click` 需要 `x/y`，可选 `button`、`clicks`（1–3）；`move` 需要 `x/y` 和可选 `duration`（0–1 秒）；`drag` 使用 `start_x/start_y/end_x/end_y` 和 `duration`（0.1–2 秒）。`scroll` 的 `clicks` 为 -100 到 100，可选 `horizontal`。`press` 使用 `key` 和 `presses`（1–50），`hotkey` 使用 1–6 个 `keys`。`type` 最多 10000 个字符。`wait` 的 `seconds` 为 0–1 秒，每批累计最多 2 秒。`click_text/assert_text` 使用 `text`、可选 `region` 和 `timeout_ms`（0–3000）。文本匹配忽略空白，需要唯一匹配，不是逐字节比较。

返回 `completed/requested`、每步 `results`、`error`、耗时及可选截图/文本。`completed` 只统计完整返回的动作；失败动作仍可能部分生效。硬超时或执行进程退出会报告 `uncertain_action`，可能已经输入时写入 STOP。不能依据 `completed=0` 推断完全没有输入，也不能盲目重放。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 找不到 `codex` | 在安装了 Codex CLI 的终端运行，确认 `codex` 位于 PATH |
| 找不到三个核心工具 | 安装器成功后重启宿主并开启新聊天；检查插件是否启用 |
| 权限错误 | 手动开启辅助功能/屏幕录制；授权主体以系统提示为准 |
| STOP 生效 | 先检查界面及部分执行结果，用户运行 `resume.command` 后才恢复 |
| 前台改变或旧 `view_id` | 重新观察目标，使用新截图；不要重放已经执行的批次 |
| OCR 找不到/多个目标 | 缩小区域并用 detail 图检查；遮挡、相似字形和应用 AX 支持均会影响结果 |
| 锁屏或休眠 | 用户手动唤醒解锁，不支持绕过锁屏 |
| 输入未生效 | 某些应用不接受进程定向 Unicode 事件；检查画面，避免重复发送 |

## 隐私、发布与维护

截图和提取的文本会进入当前宿主的模型会话；本地 OCR 不等于截图不会离开机器。服务本身使用 stdio，不监听网络端口，不需要额外 API 密钥。依赖安装需要网络；宿主自身的数据处理规则仍适用。源码没有自动上传屏幕或自动恢复急停的功能。

发布目录不包含 `.mcp.json`、虚拟环境、日志、截图、个人基准结果或凭证。请只上传本目录，勿把上一级工作目录作为仓库上传。安装后会生成本机 `.mcp.json`，Git 已忽略它；手动打 ZIP 时也必须排除。仓库未指定开源许可证，公开上传并不自动授予第三方开源使用权；发布者应自行选择许可证。

BUG 检查范围、修复和剩余限制见 [BUG_AUDIT.md](BUG_AUDIT.md)。本次检查没有重新安装已启用的插件；要使用修复后的版本，请重新运行安装器。
