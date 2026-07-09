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

# Loggers pinned to WARNING to keep the log source signal-dense — their INFO
# output is per-request/per-container chatter we don't need, and errors still
# surface because WARNING/ERROR/exception records pass through unchanged.
#
# - httpx/httpcore emit a line per upstream request; every tool call fans out to
#   the STAC catalog + collections, so at INFO they'd dominate with expected 200s.
# - The MCP SDK transport logs per stateless request ("Terminating session",
#   "Processing request of type ...") and per container lifecycle ("session
#   manager started/shutting down") at INFO. Our own `mcp_request` line
#   (server.web) already captures request traffic in a structured, queryable
#   form, so this SDK chatter is pure noise.
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "mcp.server.streamable_http",
    "mcp.server.streamable_http_manager",
    "mcp.server.lowlevel.server",
)

# Better Stack "mcp" log source (Logtail) + "mcp" errors application (Sentry).
# Hardcoded (private repo); an env var overrides its default so a token can be
# rotated via a Modal secret later without a code change.
_SOURCE_TOKEN = os.environ.get("BETTERSTACK_SOURCE_TOKEN", "[REDACTED]")
_INGESTING_HOST = os.environ.get(
    "BETTERSTACK_INGESTING_HOST", "s2576601.us-east-9.betterstackdata.com"
)
_ERRORS_DSN = os.environ.get(
    "BETTERSTACK_ERRORS_DSN",
    "https://SpXcqR6387N4ApqEerrU374r@s2576604.us-east-9.betterstackdata.com/2576604",
)


class _DropCancellationNoise(logging.Filter):
    """Drop modal-client's per-request cancellation-signal warnings.

    Modal logs ``Received a cancellation signal while processing input (<id>)``
    at WARNING on every request whose client disconnects — the normal end of an
    SSE response — so it's high-cardinality noise, not an actionable warning.
    The sibling ``background thread(s) still running after container exit``
    warning is deliberately left through: it's the Logtail FlushWorker canary we
    watch for in case container recycles ever get frequent.
    """

    _PREFIX = "Received a cancellation signal while processing input"

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith(self._PREFIX)


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

    # Attach the noise filter to each handler (not a logger): modal-client's
    # records reach our handlers by propagation, and a logger-level filter only
    # sees records logged directly to that logger, not propagated ones.
    noise_filter = _DropCancellationNoise()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(noise_filter)
    root.addHandler(stream)

    if _SOURCE_TOKEN and _INGESTING_HOST:
        from logtail import LogtailHandler

        handler = LogtailHandler(source_token=_SOURCE_TOKEN, host=f"https://{_INGESTING_HOST}")
        handler.addFilter(noise_filter)
        root.addHandler(handler)


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
