"""Anonymous MCP usage in PostHog; errors and alerting stay in Sentry."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from posthog import Posthog
from posthog.mcp import instrument
from posthog.mcp.types import MCPAnalyticsOptions
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)
# Headerless calls get a per-request id in _before_send, so the SDK's
# once-per-container "no session id" warning describes a case already handled.
logging.getLogger("posthog.mcp").addFilter(lambda r: "no session id" not in r.getMessage())

_request_id: ContextVar[str | None] = ContextVar("analytics_request_id", default=None)
# Explicit allowlist: never forward IPs, raw user agents, results or error messages.
_PROPERTIES = {
    "$session_id",
    "$mcp_source",
    "$mcp_tool_name",
    "$mcp_parameters",
    "$mcp_duration_ms",
    "$mcp_is_error",
    "$mcp_error_type",
    "$mcp_client_name",
    "$mcp_client_version",
    "$mcp_protocol_version",
    "$mcp_server_name",
    "$mcp_server_version",
    "$mcp_listed_tool_names",
}


def _before_send(event: dict[str, Any]) -> dict[str, Any]:
    props = {k: v for k, v in event["properties"].items() if k in _PROPERTIES}
    if (request_id := _request_id.get()) and event["event"] != "$mcp_initialize":
        # The SDK otherwise groups headerless traffic under a container-wide id.
        event["distinct_id"] = props["$session_id"] = request_id
    props.update({"$process_person_profile": False, "$geoip_disable": True})
    event["properties"] = props
    return event


def http_app(server: FastMCP) -> ASGIApp:
    """Build once per container; enqueue usage and drain only at ASGI shutdown."""
    token = os.getenv("POSTHOG_PROJECT_TOKEN")
    if not token:
        return server.streamable_http_app()
    try:
        client = Posthog(
            token,
            host=os.getenv("POSTHOG_HOST", "https://us.i.posthog.com"),
            enable_exception_autocapture=False,
            disable_geoip=True,
        )
        analytics = instrument(
            server,
            client,
            MCPAnalyticsOptions(
                context=False,
                capture_model=False,
                enable_conversation_id=False,
                enable_exception_autocapture=False,
                before_send=_before_send,
            ),
        )
    except Exception:
        logger.exception("usage analytics disabled: setup failed")
        return server.streamable_http_app()
    app = server.streamable_http_app()

    async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
        headers = dict(scope.get("headers", []))
        fallback = str(uuid4()) if b"mcp-session-id" not in headers else None
        context = _request_id.set(fallback)
        try:
            await app(scope, receive, send)
        finally:
            _request_id.reset(context)
            if scope["type"] == "lifespan":
                with suppress(Exception):
                    await analytics.flush()
                with suppress(Exception):
                    await asyncio.to_thread(client.shutdown)

    return wrapped
