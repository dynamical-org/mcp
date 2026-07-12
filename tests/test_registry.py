from mcp.server.fastmcp import FastMCP

from server import registry
from server.errors import ToolInputError
from server.registry import register_tool


async def test_tool_input_error_is_reraised_but_not_captured(monkeypatch):
    """A ToolInputError is a client-input (4xx) error: it must still propagate
    so the SDK builds the client error result, but it is NOT a server fault and
    must not be reported to Sentry/Better Stack (otherwise bad ids like 'test'
    become error noise)."""
    captured = []
    monkeypatch.setattr(registry.sentry_sdk, "capture_exception", lambda: captured.append(True))

    mcp = FastMCP(name="test")

    @register_tool(mcp)
    async def bad_input() -> str:
        raise ToolInputError("unknown id")

    try:
        await bad_input()
        raise AssertionError("expected ToolInputError to propagate")
    except ToolInputError as exc:
        assert str(exc) == "unknown id"

    assert captured == []


async def test_tool_exception_is_captured_and_reraised(monkeypatch):
    """A raising tool still propagates its exception (so the SDK builds the
    client error result), and Sentry.capture_exception is invoked so the failure
    reaches Better Stack — which it otherwise never would (the SDK swallows tool
    exceptions into HTTP 200 isError results)."""
    captured = []
    monkeypatch.setattr(registry.sentry_sdk, "capture_exception", lambda: captured.append(True))

    mcp = FastMCP(name="test")

    @register_tool(mcp)
    async def boom() -> str:
        raise RuntimeError("kaboom")

    try:
        await boom()
        raise AssertionError("expected RuntimeError to propagate")
    except RuntimeError as exc:
        assert str(exc) == "kaboom"

    assert captured == [True]


async def test_tool_registers_and_preserves_signature():
    """The error-capture wrapper must not hide the tool's schema from FastMCP."""
    mcp = FastMCP(name="test")

    @register_tool(mcp, title="Echo")
    async def echo(value: str) -> str:
        return value

    tools = await mcp.list_tools()
    tool = next(t for t in tools if t.name == "echo")
    assert "value" in tool.inputSchema["properties"]
    assert await echo("hi") == "hi"
