"""Modal deployment for the dynamical.org MCP server.

Mirrors the deployment shape used by wxopticon
(github.com/dynamical-org/wxopticon/blob/main/modal_app.py): a Modal App
wrapping a single ASGI function, kept warm with `min_containers=1` so a
Claude (or other MCP client) connection doesn't pay a cold start.

The only secret is `betterstack-dynamical-mcp` (log streaming + error
tracking, from the Better Stack `dynamical-mcp` source/errors app; see
server/obs.py). Every tool itself is a public, unauthenticated proxy over
dynamical.org's own public STAC catalog and status feed, so there's nothing
else to inject. v2's planned GitHub OAuth gating would add a second
`modal.Secret` here for the OAuth app's client id/secret, same pattern as
wxopticon's `wxopticon-pub` secret.

Setup:
    modal secret create betterstack-dynamical-mcp (keys: BETTERSTACK_SOURCE_TOKEN,
        BETTERSTACK_INGESTING_HOST, BETTERSTACK_ERRORS_DSN — the first two from
        the Better Stack `dynamical-mcp` log source; the DSN from a Better Stack
        Errors app, optional and no-op if omitted; see server/obs.py)
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
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("betterstack-dynamical-mcp")],
    # Kept warm: an MCP client's initialize/list_tools round trip shouldn't
    # pay a cold start, same rationale as wxopticon's pub_api.
    min_containers=1,
)
@modal.asgi_app(custom_domains=["mcp.dynamical.org"])
def mcp_app():
    from server import obs
    from server.app import mcp

    # Long-running ASGI app: configure once at startup, no per-request flush.
    # The Logtail handler streams from its background thread; Sentry's Starlette
    # integration auto-captures unhandled request errors.
    obs.setup_logging()
    obs.init_sentry()

    return mcp.streamable_http_app()


@app.local_entrypoint()
def main() -> None:
    """`modal run modal_app.py` — smoke-test the ASGI app locally via uvicorn."""
    import uvicorn

    from server.app import mcp

    uvicorn.run(mcp.streamable_http_app())
