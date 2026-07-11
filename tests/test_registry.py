from mcp.server.fastmcp import FastMCP

from server import registry
from server.registry import register_app_tool, register_tool


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


async def test_register_app_tool_attaches_ui_meta():
    """register_app_tool links the widget via both the short `ui` key and the
    fully-qualified extension key, plus the OpenAI output template, while
    keeping the tool's schema intact."""
    mcp = FastMCP(name="test")

    @register_app_tool(
        mcp,
        ui_resource_uri="ui://x/widget.html",
        openai_output_template="ui://x/widget.skybridge.html",
        title="Widget tool",
    )
    async def widget_tool(value: str) -> str:
        return value

    tool = next(t for t in await mcp.list_tools() if t.name == "widget_tool")
    assert tool.meta["ui"]["resourceUri"] == "ui://x/widget.html"
    assert tool.meta["io.modelcontextprotocol/ui"]["resourceUri"] == "ui://x/widget.html"
    assert tool.meta["openai/outputTemplate"] == "ui://x/widget.skybridge.html"
    # Schema still exposed; tool still callable.
    assert "value" in tool.inputSchema["properties"]
    assert await widget_tool("hi") == "hi"


async def test_register_app_tool_visibility_and_extra_meta():
    mcp = FastMCP(name="test")

    @register_app_tool(
        mcp,
        ui_resource_uri="ui://x/widget.html",
        ui_visibility=["app"],
        meta={"custom/key": 1},
    )
    async def app_only() -> str:
        return "ok"

    tool = next(t for t in await mcp.list_tools() if t.name == "app_only")
    assert tool.meta["ui"]["visibility"] == ["app"]
    assert tool.meta["custom/key"] == 1
    # No OpenAI template requested -> key absent.
    assert "openai/outputTemplate" not in tool.meta


async def test_register_app_tool_captures_exception(monkeypatch):
    """The Sentry capture path from register_tool still applies to app tools."""
    captured = []
    monkeypatch.setattr(registry.sentry_sdk, "capture_exception", lambda: captured.append(True))

    mcp = FastMCP(name="test")

    @register_app_tool(mcp, ui_resource_uri="ui://x/widget.html")
    async def boom() -> str:
        raise RuntimeError("kaboom")

    try:
        await boom()
        raise AssertionError("expected RuntimeError to propagate")
    except RuntimeError:
        pass
    assert captured == [True]
