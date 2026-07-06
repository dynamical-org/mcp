"""Better Stack observability: log streaming (Logtail) + error tracking (Sentry).

Mirrors dynamical-org/wxopticon's `obs.py`, but the Better Stack config is
hardcoded below (this is a private repo) rather than injected via a Modal
secret — matching how wxopticon hardcodes its Better Stack heartbeat URLs. Env
vars still override the defaults, so a token can be rotated without a redeploy.

These helpers are only ever called from the deployed Modal ASGI app (see
`modal_app.py`); local `uv run python -m server` and the test suite never invoke
them, so nothing streams to Better Stack from dev or CI.

Better Stack resources (team dynamical.org):
- log source "mcp" (id 2576601) — Logtail log streaming
- errors application "mcp" (id 2576604) — Sentry error tracking

This server is a single long-running ASGI app (no cron containers), so unlike
wxopticon there's no per-invocation `flush()` — the Logtail handler streams from
its background thread for the lifetime of the container, and Sentry's Starlette
integration captures unhandled request errors automatically.
"""

from __future__ import annotations

import logging
import os

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# httpx/httpcore emit a line per upstream request at INFO. Every tool call fans
# out to the STAC catalog + collections, so at a root level of INFO these would
# dominate the log volume with expected 200s; pin them to WARNING.
_NOISY_LOGGERS = ("httpx", "httpcore")

# Better Stack "mcp" log source (Logtail) + "mcp" errors application (Sentry).
# Hardcoded (private repo); an env var overrides its default so a token can be
# rotated via a Modal secret later without a code change.
_SOURCE_TOKEN = os.environ.get("BETTERSTACK_SOURCE_TOKEN", "KQpfnFTeGLGJAXL3mcHeZJqu")
_INGESTING_HOST = os.environ.get(
    "BETTERSTACK_INGESTING_HOST", "s2576601.us-east-9.betterstackdata.com"
)
_ERRORS_DSN = os.environ.get(
    "BETTERSTACK_ERRORS_DSN",
    "https://SpXcqR6387N4ApqEerrU374r@s2576604.us-east-9.betterstackdata.com/2576604",
)


def setup_logging() -> None:
    """Configure root logging once: stream to stdout, and also stream to the
    Better Stack "mcp" log source via Logtail.

    Idempotent — safe to call more than once (e.g. on a reused warm container).
    """
    root = logging.getLogger()
    if getattr(root, "_dynamical_mcp_configured", False):
        return
    root._dynamical_mcp_configured = True  # type: ignore[attr-defined]

    root.setLevel(logging.INFO)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    formatter = logging.Formatter(_LOG_FORMAT)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if _SOURCE_TOKEN and _INGESTING_HOST:
        from logtail import LogtailHandler

        root.addHandler(
            LogtailHandler(source_token=_SOURCE_TOKEN, host=f"https://{_INGESTING_HOST}")
        )


def init_sentry() -> None:
    """Initialize Sentry (the Better Stack "mcp" errors application).

    The Starlette integration auto-captures unhandled errors from the streamable
    HTTP ASGI app; the logging integration also turns ERROR-level log records
    into Sentry events.
    """
    if not _ERRORS_DSN:
        return

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=_ERRORS_DSN,
        environment="production",
        traces_sample_rate=0.0,
        integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)],
    )
