"""Opt-in LOCAL dummy chat test. Opens its own Tk window; sends no network messages."""
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def fixture(metadata):
    import os
    import tkinter as tk
    from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
    root = tk.Tk()
    root.title("Codex Computer Control LOCAL TEST - no network")
    root.geometry("760x400+330+220")
    header = tk.Label(root, text="爸爸", font=("Arial", 28))
    header.place(x=30, y=30, width=700, height=60)
    entry = tk.Entry(root, font=("Arial", 24))
    entry.place(x=30, y=130, width=700, height=60)
    bubble = tk.Label(root, text="", font=("Arial", 24))
    bubble.place(x=30, y=240, width=700, height=70)

    def send(_):
        bubble.config(text=entry.get())
        entry.delete(0, "end")
        return "break"

    entry.bind("<Return>", send)
    root.update()
    root.lift()
    entry.focus_set()
    NSRunningApplication.runningApplicationWithProcessIdentifier_(os.getpid()).activateWithOptions_(NSApplicationActivateIgnoringOtherApps)

    def region(widget):
        return dict(x=widget.winfo_rootx(), y=widget.winfo_rooty(),
                    width=widget.winfo_width(), height=widget.winfo_height())

    Path(metadata).write_text(json.dumps({"header": region(header), "input": region(entry),
                                         "bubble": region(bubble), "pid": os.getpid()}))
    root.mainloop()


async def run_test(metadata):
    from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    spec = json.loads(metadata.read_text())
    source = Path(__file__).parents[1] / "server.py"
    params = StdioServerParameters(command=sys.executable, args=[str(source)])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            NSRunningApplication.runningApplicationWithProcessIdentifier_(spec["pid"]).activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            await asyncio.sleep(0.1)
            actions = [
                {"action": "assert_text", "text": "爸爸", "region": spec["header"]},
                {"action": "click", "x": spec["input"]["x"] + 30, "y": spec["input"]["y"] + 30},
                {"action": "type", "text": "自测消息"},
                {"action": "assert_text", "text": "自测消息", "region": spec["input"], "timeout_ms": 1000},
                {"action": "press", "key": "enter"},
                {"action": "assert_text", "text": "自测消息", "region": spec["bubble"], "timeout_ms": 1000},
            ]
            started = time.perf_counter()
            result = await session.call_tool("desktop_step", {"actions": actions, "budget_ms": 20000, "profile": "ultra"})
            report = result.structuredContent or {}
            report["client_wall_ms"] = round((time.perf_counter() - started) * 1000, 1)
            report["test"] = "Local dummy messaging window. No external messages. Model latency excluded."
            Path("workflow-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if result.isError:
                raise RuntimeError("Workflow failed; inspect the recorded error. No automatic replay.")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--fixture":
        fixture(sys.argv[2])
    else:
        with tempfile.TemporaryDirectory(prefix="computer-control-local-test-") as temp:
            metadata = Path(temp) / "window.json"
            child = subprocess.Popen([sys.executable, __file__, "--fixture", str(metadata)])
            try:
                deadline = time.monotonic() + 10
                while not metadata.exists():
                    if child.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Local test window failed to start; Tkinter is required.")
                    time.sleep(0.05)
                asyncio.run(run_test(metadata))
            finally:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
