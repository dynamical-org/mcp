"""Sentry observability: error tracking + log streaming (Sentry Logs).

The Sentry DSN is hardcoded below rather than injected via a Modal secret: a DSN
is a client-side identifier (Sentry designs them to be embedded in client code),
not a secret, so exposing it is an accepted tradeoff. An env var still overrides
the default, so it can be rotated — or migrated to a Modal secret — without a
code change.

These helpers are only ever called from the deployed Modal ASGI app (see
`modal_app.py`); local `uv run python -m server` and the test suite never invoke
them, so nothing streams to Sentry from dev or CI.

Sentry project "mcp" (org dynamical): the Starlette integration auto-captures
unhandled request errors, the logging integration turns ERROR-level records into
issue events, and Sentry Logs (``enable_logs``) makes every INFO+ log record
queryable.

This server is a single long-running ASGI app (no cron containers), so there's
no per-invocation `flush()` — Sentry's background worker streams events and logs
for the lifetime of the container.
"""

from __future__ import annotations

import logging
import os
from typing import Any

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Loggers pinned to WARNING to keep the logs signal-dense — their INFO output is
# per-request/per-container chatter we don't need, and errors still surface
# because WARNING/ERROR/exception records pass through unchanged. Pinning here
# also keeps this chatter out of Sentry Logs, since a record below its logger's
# level never reaches the handlers Sentry hooks.
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

# Sentry project "mcp" (org dynamical). Hardcoded default (a DSN is a client-side
# identifier); the env var overrides it so it can be rotated via a Modal secret
# without a code change.
_SENTRY_DSN = os.environ.get(
    "SENTRY_DSN",
    "https://585916969d49a68c1ca79671abd06e3e@o4508761427804160.ingest.us.sentry.io/4511790929739776",
)
_ENVIRONMENT = os.environ.get("SENTRY_ENVIRONMENT", "production")

# Modal logs this at WARNING on every request whose client disconnects — the
# normal end of an SSE response — so it's high-cardinality noise, not an
# actionable warning. Dropped from both stdout and Sentry Logs.
_CANCELLATION_SIGNAL_PREFIX = "Received a cancellation signal while processing input"


class _DropCancellationNoise(logging.Filter):
    """Drop modal-client's per-request cancellation-signal warnings.

    The sibling ``background thread(s) still running after container exit``
    warning is deliberately left through: it's the canary that Sentry's
    background worker didn't flush before the container exited, which we watch
    for in case container recycles ever get frequent.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith(_CANCELLATION_SIGNAL_PREFIX)


def setup_logging() -> None:
    """Configure root logging once: stream to stdout (which Modal captures) and
    suppress the noisy per-request loggers. Sentry Logs forwarding is wired up
    separately in `init_sentry`.

    Idempotent — safe to call more than once (e.g. on a reused warm container).
    """
    root = logging.getLogger()
    if getattr(root, "_dynamical_mcp_configured", False):
        return
    root._dynamical_mcp_configured = True  # type: ignore[attr-defined]

    root.setLevel(logging.INFO)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Attach the noise filter to the handler (not a logger): modal-client's
    # records reach our handler by propagation, and a logger-level filter only
    # sees records logged directly to that logger, not propagated ones.
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter(_LOG_FORMAT))
    stream.addFilter(_DropCancellationNoise())
    root.addHandler(stream)


def _is_client_disconnect_noise(event: dict[str, Any]) -> bool:
    """A client hanging up mid-request (bots/crawlers probing the stateless
    endpoint) is expected, not a server fault, but the MCP SDK logs it at ERROR
    in two places the logging integration turns into events: once as a
    ``ClientDisconnect`` raised from reading the request body, and again as a
    bare "Received exception from stream" log with no exception attached.
    """
    for value in event.get("exception", {}).get("values", ()):
        if value.get("type") == "ClientDisconnect":
            return True
    message = event.get("logentry", {}).get("message", "")
    return event.get("logger") == "mcp.server.lowlevel.server" and message.startswith(
        "Received exception from stream"
    )


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    return None if _is_client_disconnect_noise(event) else event


def _before_send_log(log: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    # The logging integration forwards records to Sentry Logs by patching
    # logging.Logger.callHandlers, bypassing the stdout handler's noise filter,
    # so the cancellation-signal noise is dropped here instead.
    return None if log["body"].startswith(_CANCELLATION_SIGNAL_PREFIX) else log


def init_sentry() -> None:
    """Initialize Sentry error tracking and log streaming.

    The Starlette integration (auto-enabled) captures unhandled errors from the
    streamable HTTP ASGI app; the logging integration turns ERROR-level records
    into issue events and, with `enable_logs`, forwards INFO+ records to Sentry
    Logs.
    """
    if not _SENTRY_DSN:
        return

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        environment=_ENVIRONMENT,
        traces_sample_rate=0.0,
        enable_logs=True,
        integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)],
        before_send=_before_send,
        before_send_log=_before_send_log,
    )
