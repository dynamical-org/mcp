"""Sentry error tracking and application logging.

Sentry is configured from ``SENTRY_DSN`` in the deployed Modal environment.
Local development and tests leave it unset, so no telemetry is sent.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

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


def _drop_wrapped_tool_errors(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Keep SDK-wrapped client-input errors and duplicate tool reports out.

    The registry captures unexpected failures with their original exception type.
    """
    exc_info = hint.get("exc_info")
    if exc_info and isinstance(exc_info[1], ToolError):
        return None
    return event


def init_sentry() -> None:
    """Capture unhandled HTTP errors, error logs and registry tool failures."""
    if not _SENTRY_DSN:
        return

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        environment="production",
        # Prevent the auto-enabled MCP integration from recording usage.
        auto_enabling_integrations=False,
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            StarletteIntegration(),
        ],
        before_send=_drop_wrapped_tool_errors,
    )
