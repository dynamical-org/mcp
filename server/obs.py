"""Better Stack observability: log streaming (Logtail) + error tracking (Sentry).

Mirrors dynamical-org/wxopticon's `obs.py`. Both helpers degrade to no-ops when
their Better Stack env vars are absent, so local dev (`uv run python -m server`)
and the test suite run without touching the network or needing the optional
`logtail-python` / `sentry-sdk` packages installed. In Modal, the env vars come
from the `betterstack-dynamical-mcp` secret.

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


def setup_logging() -> None:
    """Configure root logging once: always stream to stdout, and also stream to
    Better Stack when BETTERSTACK_SOURCE_TOKEN / _INGESTING_HOST are set.

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

    token = os.environ.get("BETTERSTACK_SOURCE_TOKEN")
    host = os.environ.get("BETTERSTACK_INGESTING_HOST")
    if token and host:
        from logtail import LogtailHandler

        root.addHandler(LogtailHandler(source_token=token, host=f"https://{host}"))


def init_sentry() -> None:
    """Initialize Sentry (Better Stack Errors) when BETTERSTACK_ERRORS_DSN is set.

    The Starlette integration auto-captures unhandled errors from the streamable
    HTTP ASGI app; the logging integration also turns ERROR-level log records
    into Sentry events.
    """
    dsn = os.environ.get("BETTERSTACK_ERRORS_DSN")
    if not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment="production",
        traces_sample_rate=0.0,
        integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)],
    )
