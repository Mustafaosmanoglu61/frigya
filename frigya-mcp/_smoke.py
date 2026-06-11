#!/usr/bin/env python3
"""Gerçek MCP stdio client handshake testi — Claude Desktop'ın gördüğünü taklit eder."""
import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable, args=["server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("TOOLS:", names)
            assert "frigya_sembol_analiz" in names, "ana tool eksik!"
            assert len(names) == 7, f"7 tool bekleniyordu, {len(names)} bulundu"

            # Bir okuma tool'unu gerçekten çağır
            res = await session.call_tool("frigya_portfoy_tara", {"params": {}})
            text = res.content[0].text if res.content else ""
            ok = '"open_count"' in text
            print("CALL frigya_portfoy_tara →", "OK" if ok else "FAIL", f"({len(text)} char)")
            assert ok
            print("HANDSHAKE OK ✅")


if __name__ == "__main__":
    asyncio.run(main())
