# Codex Computer Control

[中文](README.md) · [Architecture](ARCHITECTURE.md) · [Audit](BUG_AUDIT.md)

**1.1.0 uses JavaScript as its default entry point**, with native backends for macOS and Windows. Node.js detects the operating system, serves MCP, validates whole batches and dispatches native operations. Swift handles macOS; C# handles Windows with a system Windows PowerShell bridge. No Python runtime is required.

## 1.1.0 performance and capabilities

On the same dedicated Mac fixture, the six-action call decreased from one baseline sample of 8113 ms to an optimized median of 745 ms across three successful runs. Screenshot-call median decreased from 490 to 122 ms across five samples per version. These exclude model reasoning and real message delivery; see [benchmarks and limits](BENCHMARKS.md).

Observed controls expose `element_id` and supported actions. New actions are `invoke`, `set_value` and `focus_element`. `click_text` invokes a control when advertised; otherwise it uses coordinates. A native failure never triggers a second fallback click because the first call may have taken effect.

Default `include_text=auto` adds AX/UIA control data without invoking OCR. Explicit `true` and `output=text` retain OCR fallback. Mac captures use ScreenCaptureKit on macOS 14+ when compiled with Swift 5.9+ SDKs, Core Graphics memory capture on the locally tested older OS, or the command fallback when the build/system combination lacks those APIs. Thumbnails use one resize.

## Responsibilities

| Component | Language / APIs | Responsibility |
| --- | --- | --- |
| Coordinator | JavaScript / Node.js | OS detection, MCP, validation, batch execution, view coordinates, deadlines, STOP and structured results |
| macOS backend | Swift / AppKit / Core Graphics / Vision | Focus, native events, screenshots and image processing, Accessibility and OCR |
| Windows backend | C# / Win32 / UI Automation | DPI awareness, foreground windows, SendInput, screenshots and control text |
| Windows bridge | Windows PowerShell 5.1 / WinRT | Compile/load C#, persistent JSON-lines transport and Windows OCR |

Native workers start on demand and are reused. Only one desktop call runs at a time. Unsupported platforms, including Linux, produce explicit errors rather than pretending to support input.

## Requirements and installation

Both platforms require **Node.js 22+ including npm, a working Codex CLI and network access for npm installation**. Dependencies are locked in `package-lock.json`.

**macOS:** install Xcode Command Line Tools, including Swift (`xcode-select --install` if missing). The backend uses macOS 10.15+ APIs; local compilation was checked with Swift 5.8 and the macOS 13 SDK, not a complete OS matrix. Installation compiles a helper for the local architecture. Accessibility and Screen Recording must be granted manually to the actual host/helper identified by macOS.

**Windows:** intended for interactive Windows 10/11 desktops with built-in Windows PowerShell 5.1, .NET Framework and desktop assemblies. No Python or separate .NET SDK is needed. The installer checks compilation using the system C# compiler. Windows on ARM64 has not been tested. Enterprise execution policies, downloaded-file zone markers or missing components may prevent loading; the installer does not relax machine policy and uses `RemoteSigned`.

From the repository root on either OS:

```sh
node codex-computer-control/scripts/install.js
```

Alternatively, use `install.command` on Mac or `install.cmd` on Windows. The installer copies the project to a personal installation directory, installs dependencies there, builds/checks the native helper, generates `.mcp.json`, registers the marketplace and installs the plugin. The release checkout remains clean.

Personal installation locations:

- Mac: `~/.local/share/codex-computer-control/marketplace/`
- Windows: `%LOCALAPPDATA%\codex-computer-control\marketplace\`

Windows CLI discovery supports `codex.exe` and the standard official npm global `@openai/codex/bin/codex.js` layout. Set `CODEX_CLI` to an executable path if discovery fails. The installer expects the standard npm layout included with the official Windows Node.js distribution.

Updates use the same installation command. Existing STOP markers are preserved; previous installation files are kept in `marketplace-backup-*`. Restart Codex and start a new chat afterward. Direct remote-marketplace installation without generating the local configuration is not supported by this source package.

## Tools and workflow

The default palette remains:

| Tool | Purpose |
| --- | --- |
| `desktop_status` | OS/backend, primary display, foreground identity, permissions/availability and STOP |
| `desktop_screenshot` | Primary display at screen-coordinate resolution, JPEG or PNG |
| `desktop_step` | Up to 32 actions with native guards and a single result |

Observe first, for example with JSON tool arguments:

```json
{"app":"Calculator","actions":[],"profile":"detail","include_text":true}
```

On Windows an application selector might be `notepad.exe`. Launching new Windows apps accepts executable names or `.exe` paths, not scripts or URLs. Multiple matching windows/processes can require manual focus; Windows may reject foreground activation.

Once the correct field is visibly focused:

```json
{"actions":[{"action":"type","text":"本地测试 / local test"}],"profile":"detail"}
```

For messaging, assert the recipient in the chat header and the exact draft in the composer before the send action. A sidebar label is not proof of the active recipient. Installing this plugin does not authorize messages, purchases or unrelated destructive operations.

## `desktop_step` options

| Parameter | Default | Meaning |
| --- | --- | --- |
| `actions` | Required | 0–32 actions; empty observes |
| `app` | Omitted | Activate and guard application; otherwise use current foreground process |
| `profile` | `ultra` | 512px/Q20; `fast` 768px/Q30; `detail` screen-coordinate resolution/Q85 |
| `output` | `image` | `image`, `text`, or `none`; errors attempt observation when safe |
| `include_text` | `auto` | AX/UIA only by default; `true` permits OCR; `false` omits attached text |
| `view_id` | Omitted | Map positions from a previous image into screen coordinates |
| `crop` | Omitted | `{x,y,width,height}` in screen coordinates |
| `settle_ms` | `0` | Post-action wait, 0–500 ms |
| `budget_ms` | `8000` | Action budget, 100–20000 ms; hard workflow deadline capped at 20 seconds |

Actions:

| Action | Fields |
| --- | --- |
| `click` | `x,y`; optional `button` left/right/middle; `clicks` 1–3 |
| `move` | `x,y`; `duration` 0–1 second |
| `drag` | `start_x,start_y,end_x,end_y`; `duration` 0.1–2; `button` left/right |
| `scroll` | `clicks` -100–100; optional `horizontal`; positive is up/right |
| `press` | `key`; `presses` 1–50 |
| `hotkey` | `keys`, 1–6 names |
| `type` | `text`, up to 10000 UTF-16 code units, no clipboard mutation |
| `invoke` | `element_id`, execute an observed control |
| `set_value` | `element_id,value`, write a supported field and verify its result |
| `focus_element` | `element_id`, focus a supported control |
| `wait` | `seconds` 0–1; total explicit waits at most 2 seconds |
| `click_text` / `assert_text` | `text`; optional `region`, `timeout_ms` 0–3000 |

Control IDs expire after 30 seconds, are bounded to 512 cached entries and are tied to the foreground process. Use only capabilities advertised in each row. Secure fields and disabled controls are rejected. Setting a value is not keyboard typing and may not trigger the same application callbacks; verify the result.

Text matching removes whitespace and requires a unique target. Mac tries Accessibility then Vision OCR; Windows tries UI Automation then Windows OCR when available. Windows OCR depends on installed recognition languages and WinRT support; failure is reported explicitly.

Keys include letters, digits, F1–F12, enter/return, esc/escape, tab, space, backspace, delete, arrows, home/end/pageup/pagedown and modifiers. `command/cmd/meta` maps to Command on Mac and Windows key on Windows. `win/windows/insert` is Windows-only and rejected before execution on Mac. Shortcut letter positions assume common keyboard layouts; use Unicode typing for text content.

## Coordinates and safety behavior

Only the primary display is supported. Mac coordinates are logical pixels, with Retina screenshots normalized. Windows coordinates are DPI-aware physical pixels. Do not reuse numerical coordinates across systems.

Use `view_id` only for positions derived from an image. Text-table coordinates and all crop/region rectangles always use screen pixels. Views expire after 120 seconds; at most 16 are retained. Backend restart, display-size change or foreground-process change requires fresh observation. Layout changes inside the same process cannot always be detected automatically.

Move the pointer to the primary display's top-left corner or run the platform `stop.command` / `stop.cmd` to stop subsequent input. STOP also blocks captures and application activation; status queries remain available. Only the user should run `resume.command` / `resume.cmd` after inspecting partial results and moving away from the corner.

Normal failures attempt to release held inputs. Forced termination of a stuck backend cannot guarantee cleanup. Windows release events release system input state; Mac keyboard releases target the original process, while mouse releases use the session event tap. If native input may have occurred, JS activates STOP and returns `uncertain_action`. Never automatically retry partial input, even if `completed` is zero.

Default action budget is 8 seconds and hard deadline is 10 seconds, capped at 20 seconds for larger budgets. The bound depends on the host being scheduled, excludes model reasoning and cannot bound whole-machine suspension. This is not an end-to-end task speed guarantee.

Windows UIPI prevents injection into higher-integrity applications. The plugin does not elevate itself or bypass secure desktops. Windows display sleep is not separately detected by the current backend. Mac rejects locked, asleep or inactive displays. Screenshots/text enter the hosting model conversation; local OCR does not mean all image data stays on the machine.

## Development and verification

```sh
cd codex-computer-control
npm ci --ignore-scripts
npm test
npm run build:native
npm run check:protocol
node tests/protocol.js --native-status
```

Unit tests use injected native doubles plus real subprocess transport. Protocol checks perform a real MCP handshake and verify validation without sending input. `--native-status` reads native status only. On Mac, the optional `node tests/live-macos.js` controls and closes its own local test window, with no network messaging. CI is configured for Swift compilation on macOS and C# compilation/PowerShell syntax on Windows; configuration alone is not evidence of a completed remote CI run.

See [BUG_AUDIT.md](BUG_AUDIT.md) for this release's evidence. See the audit for the macOS local-fixture validation scope. Windows has not undergone a real-device test. Do not claim all applications or OS versions are supported by these checks.

Repository layout:

```text
.agents/plugins/marketplace.json
.github/workflows/ci.yml
README.md / README.en.md / ARCHITECTURE.md / BUG_AUDIT.md
install.command / install.cmd
codex-computer-control/
  package.json / package-lock.json
  .codex-plugin/plugin.json
  src/
  native/macos/       # Swift
  native/windows/     # C# and Windows PowerShell
  scripts/
  tests/
  skills/computer-control/SKILL.md
  stop.command / stop.cmd / resume.command / resume.cmd
```

Publish this repository root with hidden metadata. Commit `package-lock.json`; exclude `node_modules`, native `bin` outputs, generated `.mcp.json`, screenshots and credentials. There is no network control listener. Network is needed for dependency installation and the hosting Codex service. No open-source license has been chosen; the publisher must select licensing terms.

Remove the installed plugin with:

```sh
codex plugin remove codex-computer-control@codex-computer-control-local
```

This does not remove the source checkout, personal marketplace source or installation backups. Source edits require rerunning the installer and restarting Codex.
