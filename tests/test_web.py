from server.web import DEFAULT_CSP, ContentSecurityPolicyMiddleware


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
