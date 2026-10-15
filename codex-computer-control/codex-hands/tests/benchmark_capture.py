"""Opt-in read-only screenshot benchmark over persistent MCP. No input/messages."""
import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def sample(path, tool, arguments, count):
    rows = []
    params = StdioServerParameters(command=sys.executable, args=[str(path)])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            for _ in range(count):
                started = time.perf_counter()
                result = await session.call_tool(tool, arguments)
                elapsed = round((time.perf_counter() - started) * 1000, 1)
                if result.isError:
                    raise RuntimeError(str(result.content))
                picture = next(c for c in result.content if c.type == "image")
                rows.append({"elapsed_ms": elapsed, "image_base64_bytes": len(picture.data),
                             "mime": picture.mimeType})
    warm = rows[1:] or rows
    return {"cold": rows[0], "warm_median_ms": statistics.median(r["elapsed_ms"] for r in warm),
            "warm_image_bytes": rows[-1]["image_base64_bytes"], "samples": rows}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, help="Previous server.py for comparison")
    parser.add_argument("--samples", type=int, default=4, choices=range(2, 21))
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    args = parser.parse_args()
    report = {}
    if args.baseline:
        report["baseline_full"] = await sample(args.baseline, "desktop_screenshot", {}, args.samples)
    for profile in ("ultra", "fast", "detail"):
        report[profile] = await sample(Path(__file__).parents[1] / "server.py", "desktop_step",
                                     {"actions": [], "settle_ms": 0, "profile": profile}, args.samples)
    report["note"] = "Read-only screenshot benchmark, persistent MCP, no messages sent. Model response latency not included."
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    args.output.write_text(encoded + "\n")
    print(encoded)


if __name__ == "__main__":
    asyncio.run(main())
