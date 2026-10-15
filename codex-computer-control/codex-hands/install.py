"""Install dependencies, register a local plugin marketplace and enable the plugin."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path.home() / ".local/share/codex-hands"


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def main():
    if sys.platform != "darwin":
        raise SystemExit("当前版本需要 macOS。")
    if sys.version_info < (3, 10):
        raise SystemExit("需要 Python 3.10 或更新版本，请安装后重试。")
    codex = shutil.which("codex")
    if not codex:
        candidates = [
            Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"),
            Path("/Applications/Codex.app/Contents/Resources/codex"),
        ]
        codex = next((str(path) for path in candidates if path.is_file()), None)
    if not codex:
        raise SystemExit("找不到 codex CLI，请在 Codex 的终端中运行安装脚本。")
    DATA.mkdir(parents=True, exist_ok=True)
    python = DATA / "venv/bin/python"
    if not python.exists():
        run(sys.executable, "-m", "venv", DATA / "venv")
    run(python, "-m", "pip", "install", "--only-binary=cryptography", "-r", ROOT / "requirements.txt")
    app = DATA / "app"
    app.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "server.py", app / "server.py")
    config = {"mcpServers": {"codex_hands": {
        "command": str(python), "args": [str(app / "server.py")],
        "env": {"CODEX_HANDS_LEGACY_TOOLS": "1" if os.environ.get("CODEX_HANDS_LEGACY_TOOLS") == "1" else "0"}
    }}}
    (ROOT / ".mcp.json").write_text(json.dumps(config, indent=2) + "\n")
    market_dir = ROOT.parent / ".agents/plugins"
    market_dir.mkdir(parents=True, exist_ok=True)
    market_path = market_dir / "marketplace.json"
    if market_path.exists():
        market = json.loads(market_path.read_text())
    else:
        market = {"name": "codex-hands-local", "interface": {"displayName": "Codex Hands Local"}, "plugins": []}
    entry = {"name": "codex-hands", "source": {"source": "local", "path": "./codex-hands"},
             "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
             "category": "Productivity"}
    market["plugins"] = [p for p in market.get("plugins", []) if p.get("name") != entry["name"]] + [entry]
    market_path.write_text(json.dumps(market, ensure_ascii=False, indent=2) + "\n")
    run(codex, "plugin", "marketplace", "add", ROOT.parent, "--json")
    run(codex, "plugin", "add", "codex-hands@" + market["name"], "--json")
    print("安装完成。重启 Codex，开启辅助功能和屏幕录制权限，再在新聊天中使用 Codex 双手。")


if __name__ == "__main__":
    main()
