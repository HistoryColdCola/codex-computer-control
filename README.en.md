# Codex Computer Control

[中文说明](README.md) · [Bug audit](BUG_AUDIT.md)

Version **0.3.1**. A local macOS desktop automation plugin exposing screenshots, mouse input, keyboard shortcuts, Unicode typing and application activation through an MCP stdio server. It operates on the primary display and uses local Accessibility APIs and Apple Vision OCR for text targeting. It is a local Mac service and cannot run on Cloudflare Workers.

## Requirements and installation

You need macOS, Python 3.10 or newer, a Codex host with the plugin CLI commands used by the installer, and network access to install Python dependencies. This package has no extra API-key requirement. Windows and Linux desktop control are unsupported.

Clone or extract the repository, then run from its root:

```sh
python3 codex-computer-control/install.py
```

Alternatively, double-click the root `install.command`. The installer finds `codex` in PATH or common application bundle locations, creates a virtual environment under `~/.local/share/codex-computer-control/venv`, copies the server into `~/.local/share/codex-computer-control/app`, generates the local `.mcp.json`, registers the local marketplace and enables the plugin. Keep the checkout for updates and installation metadata. A direct remote-marketplace installation without running the installer is not supported by this package.

Restart the host and start a new chat. In **System Settings → Privacy & Security**, manually grant **Accessibility** and **Screen Recording** to the actual hosting application or Python process named by macOS. Use `desktop_status` to diagnose permissions. The plugin cannot grant these permissions itself.

To expose the optional individual legacy tools:

```sh
CODEX_COMPUTER_CONTROL_LEGACY_TOOLS=1 python3 codex-computer-control/install.py
```

Rerun the installer after changing source, then restart the host. Editing this checkout alone does not update an already installed copy.

## Tools and typical workflow

The default palette contains three tools:

| Tool | Purpose |
| --- | --- |
| `desktop_status` | Report permissions, display state, pointer coordinates and STOP state |
| `desktop_screenshot` | Capture the primary display at logical screen resolution; JPEG or PNG |
| `desktop_step` | Execute up to 32 actions with focus checks, then return one observation |

For example, ask your host: “Use Codex Computer Control to open Calculator, calculate 123 × 456, and verify the result.” Start with an observation. These examples are JSON tool arguments, not terminal commands:

```json
{"app":"Calculator","actions":[],"profile":"detail","include_text":true}
```

After confirming the application and layout:

```json
{"app":"Calculator","actions":[{"action":"press","key":"esc"},{"action":"type","text":"123*456"},{"action":"press","key":"enter"}],"profile":"detail"}
```

Application names must resolve on the local Mac. Observe the result before claiming success. For messaging tasks, verify the recipient in the chat header and the exact draft in the composer before sending. A matching name in a sidebar does not establish the active recipient. The plugin does not itself authorize messaging, purchases or unrelated destructive operations.

## `desktop_step` reference

| Parameter | Default | Behavior |
| --- | --- | --- |
| `actions` | Required | List of 0–32 actions; empty means observe |
| `app` | Omitted | Activate and guard the named application |
| `profile` | `ultra` | `ultra`: max width 512/Q20; `fast`: 768/Q30; `detail`: logical resolution/Q85 |
| `output` | `image` | `image`, `text` (AX/OCR), or `none` (skip successful observation) |
| `view_id` | Omitted | Map coordinates from a previous thumbnail or cropped image |
| `crop` | Omitted | `{x,y,width,height}` in logical screen pixels |
| `include_text` | `false` | Add extracted text to image output |
| `settle_ms` | `0` | Post-action wait, 0–500 ms |
| `budget_ms` | `8000` | Action budget, 100–20000 ms; parent hard deadline never exceeds 20 seconds |

| Action | Fields and limits |
| --- | --- |
| `click` | `x`, `y`; optional `button` (left/right/middle), `clicks` (1–3) |
| `move` | `x`, `y`; optional `duration` (0–1 second) |
| `drag` | `start_x`, `start_y`, `end_x`, `end_y`; `duration` (0.1–2 seconds), left/right `button` |
| `scroll` | `clicks` (-100–100); optional `horizontal`; positive means up/right |
| `hotkey` | `keys`, 1–6 supported key names such as command, shift, a |
| `press` | `key`; optional `presses` (1–50) |
| `type` | `text`, up to 10000 characters; Unicode events without clipboard changes |
| `wait` | `seconds` (0–1); explicit waits total at most 2 seconds per batch |
| `click_text` | `text`; optional screen `region`, `timeout_ms` (0–3000) |
| `assert_text` | Same fields; verify without clicking |

Text matching removes whitespace and requires a unique match. It is not byte-for-byte equality. Accessibility text is tried first, then local OCR. OCR may confuse similar glyphs; inspect a detailed crop instead of weakening a failed assertion.

### Coordinates and observations

Without `view_id`, positions are primary-display logical pixels. With `view_id`, click/move/drag positions are image pixels and are mapped back to screen coordinates, including crop offsets. Text extraction positions and `crop`/`region` rectangles always use logical screen pixels. Do not mix text-table positions and image positions in one batch with a `view_id`.

Views expire after 120 seconds, and only the latest 16 are retained. Worker restarts invalidate them. Observe again whenever the layout changes. Retina captures are resized to logical resolution. Move target windows to the primary display; other displays are unsupported.

Results include `completed`, `requested`, `results`, `error`, timings and optional image/text metadata. `completed` counts actions that fully returned, not every native event delivered. A failed action can have partially taken effect even when `completed` is zero. Never automatically replay failed input.

## Emergency stop and timeouts

Move the pointer to the primary display's upper-left corner to trigger the PyAutoGUI failsafe, or run `codex-computer-control/stop.command`. The STOP file blocks subsequent input, screenshots and app launches. Short events already sent may finish. Releases of inputs tracked by the event bridge are allowed through STOP and sent to the original process to avoid leaving keys/buttons held.

Only the user should run `codex-computer-control/resume.command` after inspecting the desktop; also move the pointer away from the corner. Recovery is never automatic.

Execution uses a persistent worker process. With the default budget, the parent enforces a 10-second hard deadline, capped at 20 seconds for larger budgets. A blocked native call can cause the worker to be terminated; the response reports `uncertain_action` and activates STOP if input may have occurred. Forced termination cannot guarantee native key/button cleanup. Inspect the desktop and release any held inputs before resuming. Sleeping, inactive or locked desktops reject input and require manual wake/unlock.

These deadlines depend on the host being scheduled and do not bound model reasoning, whole-machine suspension or end-to-end task latency. No 20-second user-task guarantee is made.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| CLI not found | Install/locate the Codex CLI and make it available in PATH |
| Missing tools | Confirm installer success and plugin enablement, restart host, start a new chat |
| Permission error | Grant Accessibility and Screen Recording to the process identified by macOS |
| STOP active | Inspect partial results, then manually run `resume.command` |
| Focus changed / expired view | Observe the intended application again; do not replay completed actions |
| Missing/ambiguous OCR target | Use a smaller region and detailed image; check occlusion and glyph confusion |
| Input ignored | Some apps reject process-directed Unicode input; inspect before retrying |
| Screen asleep or locked | Manually wake and unlock the Mac |

## Tests and validation

After installing dependencies, run from the repository root:

```sh
~/.local/share/codex-computer-control/venv/bin/python -m unittest discover -s codex-computer-control/tests -v
~/.local/share/codex-computer-control/venv/bin/python codex-computer-control/tests/check_protocol.py
```

Unit tests use a mocked desktop. The protocol test starts a real MCP connection and checks initialization, tool discovery and invalid-action errors without sending desktop input. See [BUG_AUDIT.md](BUG_AUDIT.md) for this release's verified results and limits.

Optional live checks, requiring relevant permissions:

```sh
~/.local/share/codex-computer-control/venv/bin/python codex-computer-control/tests/live_workflow.py
~/.local/share/codex-computer-control/venv/bin/python codex-computer-control/tests/benchmark_capture.py
```

The live workflow requires Tkinter and operates its own local mock chat window, not a real contact. The benchmark reads screenshots; `--baseline /path/to/old/server.py` compares an older implementation and `--output` chooses the report path. Generated reports are local artifacts excluded from the release. Benchmarks do not establish message delivery or model latency.

## Privacy, publishing and removal

The server listens on no network control port. OCR runs locally, but returned screenshots and extracted text enter the hosting model conversation and may leave the machine under the host's data policies. Dependency installation requires network access. Protect visible private data accordingly.

Repository layout:

```text
README.md / README.en.md / BUG_AUDIT.md
.gitignore
.agents/plugins/marketplace.json
install.command
codex-computer-control/
  .codex-plugin/plugin.json
  server.py / install.py / requirements.txt
  install.command / stop.command / resume.command
  skills/computer-control/SKILL.md
  tests/
```

Upload this repository directory only, not its parent workspace. Include hidden `.agents`, `.codex-plugin` and `.gitignore` files. Never upload generated `.mcp.json`, environments, credentials, screenshots or personal test reports. Git ignores these local artifacts; manually created archives must exclude them too.

```sh
git init -b main
git add .
git commit -m "Initial Codex Computer Control plugin"
```

Create an empty GitHub repository and follow its remote/push instructions. No open-source license has been selected in this package; public upload alone does not grant an open-source license. The publisher should choose appropriate licensing terms.

To remove the default local-marketplace installation:

```sh
codex plugin remove codex-computer-control@codex-computer-control-local
```

This leaves the checkout and `~/.local/share/codex-computer-control/` in place. If installed under a different marketplace name, use that installation's identifier. Remove leftover files manually only when no longer needed.
