from mcp.server.fastmcp import FastMCP

from server import registry
from server.registry import register_tool


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
