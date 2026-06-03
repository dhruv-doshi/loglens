"""Optional MCP wrapper exposing the tools.py functions as Model Context Protocol
tools. Behind the [mcp] extra. Thin adapter only — no business logic here."""

from __future__ import annotations

import json

from . import tools

# name -> callable, derived from the tool surface in tools.py.
DISPATCH = {
    "parse_logs": tools.parse_logs,
    "query_logs": tools.query_logs,
    "find_gaps": tools.find_gaps,
    "check_expectations": tools.check_expectations,
}

_MCP_HINT = (
    "The MCP server requires the 'mcp' extra. "
    "Install it with: pip install loglens[mcp]"
)


def build_server():
    """Build (but don't start) the MCP Server with the loglens tools registered."""
    try:
        from mcp.server import Server
        import mcp.types as types
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(_MCP_HINT) from e

    server = Server("loglens")

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name=name,
                description=(DISPATCH[name].__doc__ or name).strip(),
                inputSchema=schema,
            )
            for name, schema in tools.TOOL_SCHEMAS.items()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        fn = DISPATCH[name]
        result = fn(**arguments)
        return [types.TextContent(type="text", text=json.dumps(result))]

    return server


def main() -> None:
    """Console-script entry point: start the stdio MCP server."""
    import anyio
    from mcp.server.stdio import stdio_server

    server = build_server()

    async def _run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(_run)


if __name__ == "__main__":
    main()
