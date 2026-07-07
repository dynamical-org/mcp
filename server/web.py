"""ASGI middleware for the deployed streamable-HTTP app.

Kept as a pure-ASGI wrapper (not Starlette's ``BaseHTTPMiddleware``, which
buffers the response body and would break MCP's SSE streaming) — it only
appends a response header, so it never touches the body.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# No UI / no iframes: this endpoint serves only JSON-RPC over HTTP/SSE, so the
# strictest policy is correct and satisfies the OpenAI app review's "CSP
# defined" check. `frame-ancestors 'none'` also blocks clickjacking framing.
DEFAULT_CSP = "default-src 'none'; frame-ancestors 'none'"

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class ContentSecurityPolicyMiddleware:
    """Append a ``Content-Security-Policy`` header to every HTTP response."""

    def __init__(self, app: Any, policy: str = DEFAULT_CSP) -> None:
        self.app = app
        self._header = (b"content-security-policy", policy.encode("latin-1"))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_csp(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(self._header)
            await send(message)

        await self.app(scope, receive, send_with_csp)
