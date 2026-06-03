import pytest

pytest.importorskip("mcp")

from loglens import mcp_server  # noqa: E402


def test_dispatch_covers_tool_schemas():
    from loglens.tools import TOOL_SCHEMAS

    assert set(mcp_server.DISPATCH) == set(TOOL_SCHEMAS)
    assert all(callable(fn) for fn in mcp_server.DISPATCH.values())


def test_build_server_registers_tools():
    server = mcp_server.build_server()
    assert server.name == "loglens"


def test_list_tools_returns_all():
    import anyio

    server = mcp_server.build_server()
    # The list_tools handler is registered on the server's request handlers.
    import mcp.types as types

    handler = server.request_handlers[types.ListToolsRequest]

    async def _call():
        req = types.ListToolsRequest(method="tools/list")
        result = await handler(req)
        return result.root.tools

    tools = anyio.run(_call)
    names = {t.name for t in tools}
    assert names == {"parse_logs", "query_logs", "find_gaps", "check_expectations"}
