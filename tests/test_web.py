import json

from server.web import (
    DEFAULT_CSP,
    ContentSecurityPolicyMiddleware,
    RejectGetStreamMiddleware,
    RequestLoggingMiddleware,
    _summarize_jsonrpc,
)


async def _drive(app, scope):
    """Run an ASGI app once, capturing the http.response.start headers."""
    captured: dict = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["headers"] = message.get("headers", [])

    await app(scope, receive, send)
    return captured


async def _ok_app(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": b"{}"})


async def test_csp_header_added_to_http_responses():
    app = ContentSecurityPolicyMiddleware(_ok_app)
    captured = await _drive(app, {"type": "http"})
    assert (b"content-security-policy", DEFAULT_CSP.encode("latin-1")) in captured["headers"]
    # Existing headers are preserved, not clobbered.
    assert (b"content-type", b"application/json") in captured["headers"]


async def test_csp_passthrough_for_non_http_scopes():
    """Lifespan/websocket scopes pass through untouched (no header injection)."""
    seen = {}

    async def lifespan_app(scope, receive, send):
        seen["type"] = scope["type"]

    app = ContentSecurityPolicyMiddleware(lifespan_app)
    await app({"type": "lifespan"}, None, None)
    assert seen["type"] == "lifespan"


def test_summarize_jsonrpc_tool_call():
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_catalog"}}
    ).encode()
    assert _summarize_jsonrpc(body) == {"mcp_method": "tools/call", "mcp_tool": "search_catalog"}


def test_summarize_jsonrpc_initialize_captures_client():
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "claude", "version": "1.2.3"}},
        }
    ).encode()
    assert _summarize_jsonrpc(body) == {
        "mcp_method": "initialize",
        "client_name": "claude",
        "client_version": "1.2.3",
    }


def test_summarize_jsonrpc_non_json_is_empty():
    assert _summarize_jsonrpc(b"not json") == {}
    # A JSON-RPC batch (list) is not summarized rather than crashing.
    assert _summarize_jsonrpc(b"[]") == {}


async def test_reject_get_stream_returns_405():
    """A GET (the standalone SSE stream) is short-circuited with 405, never
    reaching the wrapped app."""
    reached = {"app": False}

    async def app(scope, receive, send):
        reached["app"] = True

    sent = {}

    async def send(message):
        if message["type"] == "http.response.start":
            sent["status"] = message["status"]
            sent["headers"] = message["headers"]

    await RejectGetStreamMiddleware(app)({"type": "http", "method": "GET"}, None, send)

    assert sent["status"] == 405
    assert (b"allow", b"POST") in sent["headers"]
    assert reached["app"] is False


async def test_reject_get_stream_passes_post_through():
    """POST (JSON-RPC) is untouched by the GET-reject shim."""
    status = await _drive_post(RejectGetStreamMiddleware(_reading_app), b"{}", method="POST")
    assert status["status"] == 200


async def test_reject_get_stream_passthrough_for_non_http_scopes():
    seen = {}

    async def lifespan_app(scope, receive, send):
        seen["type"] = scope["type"]

    await RejectGetStreamMiddleware(lifespan_app)({"type": "lifespan"}, None, None)
    assert seen["type"] == "lifespan"


async def _drive_post(app, body, method="POST"):
    """Drive an ASGI app for one POST request, returning the captured send log."""
    scope = {"type": "http", "method": method}
    sent_body = {}

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            sent_body["status"] = message["status"]

    await app(scope, receive, send)
    return sent_body


async def _reading_app(scope, receive, send):
    """An ASGI app that reads its request body (as the real MCP app does)
    before responding, so the logging tap can observe the body."""
    await receive()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


async def test_request_logging_logs_tool_and_status(caplog):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_recent_runs"}}
    ).encode()
    app = RequestLoggingMiddleware(_reading_app)

    with caplog.at_level("INFO", logger="server.web"):
        await _drive_post(app, body)

    record = next(r for r in caplog.records if r.message == "mcp_request")
    assert record.mcp_method == "tools/call"
    assert record.mcp_tool == "list_recent_runs"
    assert record.http_status == 200
    assert record.duration_ms >= 0


async def test_request_logging_passes_body_through_unchanged():
    """The tap observes the body without consuming it from the wrapped app."""
    seen = {}

    async def echo_app(scope, receive, send):
        message = await receive()
        seen["body"] = message["body"]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    body = json.dumps({"jsonrpc": "2.0", "method": "ping"}).encode()
    await _drive_post(RequestLoggingMiddleware(echo_app), body)
    assert seen["body"] == body


async def test_request_logging_passthrough_for_non_http_scopes():
    seen = {}

    async def lifespan_app(scope, receive, send):
        seen["type"] = scope["type"]

    await RequestLoggingMiddleware(lifespan_app)({"type": "lifespan"}, None, None)
    assert seen["type"] == "lifespan"
