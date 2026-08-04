"""Sentry error tracking and application logging.

Sentry is configured from ``SENTRY_DSN`` in the deployed Modal environment.
Local development and tests leave it unset, so no telemetry is sent.
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

_SENTRY_DSN = os.environ.get("SENTRY_DSN")


class _DropCancellationNoise(logging.Filter):
    """Drop modal-client's per-request cancellation-signal warnings.

    Modal logs ``Received a cancellation signal while processing input (<id>)``
    at WARNING on every request whose client disconnects — the normal end of an
    SSE response — so it's high-cardinality noise, not an actionable warning.
    The sibling ``background thread(s) still running after container exit``
    warning is deliberately left through to surface shutdown problems.
    """

    _PREFIX = "Received a cancellation signal while processing input"

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith(self._PREFIX)


def setup_logging() -> None:
    """Configure root logging once for stdout.

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


def init_sentry() -> None:
    """Initialize Sentry error tracking.

    The Starlette integration auto-captures unhandled errors from the streamable
    HTTP ASGI app; the logging integration also turns ERROR-level log records
    into Sentry events.
    """
    if not _SENTRY_DSN:
        return

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        environment="production",
        traces_sample_rate=0.0,
        integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)],
    )
