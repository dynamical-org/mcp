"""Modal deployment for the dynamical.org MCP server.

Mirrors the deployment shape used by wxopticon
(github.com/dynamical-org/wxopticon/blob/main/modal_app.py): a Modal App
wrapping a single ASGI function, kept warm with `min_containers=1` so a
Claude (or other MCP client) connection doesn't pay a cold start.

v1 has no secrets: every tool is a public, unauthenticated proxy over
dynamical.org's own public STAC catalog and status feed, and the Better Stack
telemetry config is hardcoded (private repo; see server/obs.py), so there's
nothing to inject. v2's planned GitHub OAuth gating would add a `modal.Secret`
here for the OAuth app's client id/secret, same pattern as wxopticon's
`wxopticon-pub` secret.

Setup:
    modal deploy modal_app.py

mcp.dynamical.org setup (one-time, manual): Modal provisions TLS for the
domain via the `custom_domains` arg on `mcp_app` below; create the CNAME
record per the Modal dashboard's instructions (DNS-only — not proxied
through Cloudflare, matching status.dynamical.org's setup).

Local dev (no Modal):
    uv run python -m server              # streamable-http on :8000
    uv run modal_app.py                  # same ASGI app via uvicorn
"""

from __future__ import annotations

import modal

app = modal.App("dynamical-mcp-server")

image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install(
        "mcp[cli]>=1.28.0",
        "httpx>=0.27",
        "logtail-python>=0.3.4",
        "sentry-sdk>=2.63.0",
    )
    .add_local_python_source("server")
    # `add_local_python_source` mounts only .py, but the MCP Apps UI widgets
    # (server/ui/*.html) are data files loaded via importlib.resources at
    # runtime, so mount them alongside the package or they'd be missing.
    .add_local_dir("server/ui", remote_path="/root/server/ui")
)


@app.function(
    image=image,
    # Kept warm: an MCP client's initialize/list_tools round trip shouldn't
    # pay a cold start, same rationale as wxopticon's pub_api.
    min_containers=1,
)
# Without this Modal assigns one input per container, so every concurrent
# request — including the long-lived SSE connections MCP clients hold open —
# pins its own container and Modal scales out to several, which then idle-exit
# and spew "background thread still running" / "cancellation signal" warnings.
# Every tool here is a stateless, fully-async I/O proxy over public HTTP APIs
# (shared httpx.AsyncClient, stateless_http=True), so one container can serve
# many concurrent requests. This collapses the fleet back to min_containers.
@modal.concurrent(max_inputs=100)
@modal.asgi_app(custom_domains=["mcp.dynamical.org"])
def mcp_app():
    from server import obs
    from server.app import mcp
    from server.web import (
        ContentSecurityPolicyMiddleware,
        RejectGetStreamMiddleware,
        RequestLoggingMiddleware,
    )

    # Long-running ASGI app: configure once at startup, no per-request flush.
    # The Logtail handler streams from its background thread; tool exceptions are
    # captured into Sentry at the registry choke point (see server/registry.py).
    obs.setup_logging()
    obs.init_sentry()

    # Wrap (don't add_middleware) so we stay a pure-ASGI passthrough that
    # doesn't buffer the streamable-HTTP SSE responses. Request logging is
    # outermost so its duration covers the whole stack; the GET-stream reject
    # is innermost so its 405 still gets logged and carries the CSP header.
    return RequestLoggingMiddleware(
        ContentSecurityPolicyMiddleware(RejectGetStreamMiddleware(mcp.streamable_http_app()))
    )


@app.local_entrypoint()
def main() -> None:
    """`modal run modal_app.py` — smoke-test the ASGI app locally via uvicorn."""
    import uvicorn

    from server.app import mcp

    uvicorn.run(mcp.streamable_http_app())
