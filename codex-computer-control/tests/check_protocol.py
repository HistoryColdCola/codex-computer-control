"""Real MCP handshake and schema check, without calling desktop APIs."""
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable,
                                  args=[str(Path(__file__).parents[1] / "server.py")])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.list_tools()
            names = {tool.name for tool in result.tools}
            assert names == {"desktop_screenshot", "desktop_status", "desktop_step"}, names
            # Validation runs before backend import, so this cannot move the mouse.
            error = await session.call_tool("desktop_step", {"actions": [{"action":"click","x":10,"y":10,"clicks":99}]})
            assert error.isError, error
            step_error = await session.call_tool("desktop_step", {"actions": [
                {"action": "press", "key": "enter", "presses": -1}]})
            assert step_error.isError, step_error
            print("MCP initialize/list_tools/action validation passed; 3 workflow-focused tools.")


if __name__ == "__main__":
    asyncio.run(main())
