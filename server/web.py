"""ASGI middleware for the deployed streamable-HTTP app.

Kept as pure-ASGI wrappers (not Starlette's ``BaseHTTPMiddleware``, which
buffers the response body and would break MCP's SSE streaming).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# No UI / no iframes: this endpoint serves only JSON-RPC over HTTP/SSE, so the
# strictest policy is correct and satisfies the OpenAI app review's "CSP
# defined" check. `frame-ancestors 'none'` also blocks clickjacking framing.
DEFAULT_CSP = "default-src 'none'; frame-ancestors 'none'"

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

# A JSON-RPC MCP request body is small (a method name + a few params); cap how
# much we buffer to parse it so a malformed/oversized POST can't balloon memory.
_MAX_PARSED_BODY = 64 * 1024


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


def _summarize_jsonrpc(body: bytes) -> dict[str, Any]:
    """Pull the traffic-interesting fields out of a JSON-RPC request body.

    Returns ``mcp_method`` for every request, plus ``mcp_tool`` for
    ``tools/call`` and ``client_name``/``client_version`` for ``initialize``.
    Best-effort: a non-JSON body (or a JSON-RPC batch, which arrives as a list)
    yields ``{}`` so logging never breaks request handling.
    """
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}

    fields: dict[str, Any] = {}
    method = payload.get("method")
    if isinstance(method, str):
        fields["mcp_method"] = method
    params = payload.get("params")
    if isinstance(params, dict):
        if method == "tools/call" and isinstance(params.get("name"), str):
            fields["mcp_tool"] = params["name"]
        elif method == "initialize" and isinstance(params.get("clientInfo"), dict):
            info = params["clientInfo"]
            if isinstance(info.get("name"), str):
                fields["client_name"] = info["name"]
            if isinstance(info.get("version"), str):
                fields["client_version"] = info["version"]
    return fields


class RequestLoggingMiddleware:
    """Emit one structured log line per HTTP request for traffic metrics.

    Fields (``mcp_method``, ``mcp_tool``, ``client_name``/``client_version``,
    ``http_status``, ``duration_ms``) are passed via ``extra`` so the Logtail
    handler promotes each to a top-level field in the Better Stack ``mcp``
    source, which a dashboard charts by tool, by client, and over time.

    The request body is *observed* as the wrapped app reads it (a ``receive``
    tap) rather than buffered-and-replayed: fabricating messages would break
    MCP's long-lived SSE streaming, which watches ``receive`` for client
    disconnects. Only wired into the deployed ASGI app (see ``modal_app.py``),
    so local dev and the test suite log nothing here.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        size = 0

        async def tap_receive() -> Message:
            nonlocal size
            message = await receive()
            if message["type"] == "http.request" and size <= _MAX_PARSED_BODY:
                chunk = message.get("body", b"")
                chunks.append(chunk)
                size += len(chunk)
            return message

        fields: dict[str, Any] = {}
        started = time.monotonic()
        logged = False

        async def send_with_log(message: Message) -> None:
            nonlocal logged
            # Log on the first response.start — by then the app has read the
            # request body it cares about, so the tapped chunks are complete.
            if message["type"] == "http.response.start" and not logged:
                logged = True
                if size <= _MAX_PARSED_BODY:
                    fields.update(_summarize_jsonrpc(b"".join(chunks)))
                fields["http_status"] = message["status"]
                fields["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
                logger.info("mcp_request", extra=fields)
            await send(message)

        await self.app(scope, tap_receive, send_with_log)
