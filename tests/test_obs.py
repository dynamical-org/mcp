import logging

import pytest
import sentry_sdk
from mcp.server.fastmcp.exceptions import ToolError

from server import obs
from server.errors import ToolInputError
from server.obs import _drop_wrapped_tool_errors, _DropCancellationNoise


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("modal-client", logging.WARNING, __file__, 1, msg, args, None)


def test_drops_cancellation_signal_warning():
    f = _DropCancellationNoise()
    rec = _record("Received a cancellation signal while processing input (%r,)", "in-01ABC")
    assert f.filter(rec) is False


def test_keeps_background_thread_canary():
    f = _DropCancellationNoise()
    rec = _record("Detected 1 background thread(s) [Thread-2] still running after container exit.")
    assert f.filter(rec) is True


def test_keeps_ordinary_logs():
    f = _DropCancellationNoise()
    assert f.filter(_record("mcp_request")) is True


def _hint(exc: BaseException) -> dict:
    return {"exc_info": (type(exc), exc, exc.__traceback__)}


def _wrapped(original: BaseException) -> ToolError:
    """The exception the MCP SDK actually reports: `tool.run` re-raises every
    tool failure as `ToolError(...) from e`."""
    try:
        raise ToolError(f"Error executing tool t: {original}") from original
    except ToolError as exc:
        return exc


def test_drops_tool_error_wrapping_client_input_error():
    """A bad collection_id reaches the MCP integration as a ToolError wrapping
    ToolInputError. Dropping it keeps client-input errors out of Sentry, which
    is the whole point of ToolInputError."""
    assert _drop_wrapped_tool_errors({}, _hint(_wrapped(ToolInputError("unknown id")))) is None


def test_drops_tool_error_duplicating_a_registry_capture():
    """A genuine tool fault is captured twice: once by `register_tool` with its
    real type, once by the MCP integration as a ToolError wrapper. Keep the
    former, drop the latter."""
    assert _drop_wrapped_tool_errors({}, _hint(_wrapped(RuntimeError("boom")))) is None


def test_keeps_the_underlying_exception_event():
    event = {"exception": {"values": [{"type": "RuntimeError"}]}}
    assert _drop_wrapped_tool_errors(event, _hint(RuntimeError("boom"))) is event


def test_keeps_events_without_an_exception():
    """Log-record events (LoggingIntegration) carry no exc_info."""
    event = {"logentry": {"message": "mcp_request"}}
    assert _drop_wrapped_tool_errors(event, {}) is event


@pytest.fixture
def _sentry_client():
    """Initialize Sentry against a throwaway DSN, then tear the client back down
    so an initialized client can't leak into other tests."""
    yield
    sentry_sdk.init(dsn=None)


def test_init_sentry_wires_mcp_monitoring(monkeypatch, _sentry_client):
    monkeypatch.setattr(obs, "_SENTRY_DSN", "https://public@o0.ingest.us.sentry.io/1")
    obs.init_sentry()

    options = sentry_sdk.get_client().options
    assert "mcp" in sentry_sdk.get_client().integrations
    # Spans are what MCP monitoring is made of -- at 0.0 the integration sends nothing.
    assert options["traces_sample_rate"] == 0.1
    # Tool arguments and results are only attached to spans when PII is on.
    assert options["send_default_pii"] is True
    assert options["before_send"] is _drop_wrapped_tool_errors


def test_init_sentry_is_a_noop_without_a_dsn(monkeypatch):
    """Local dev and tests leave SENTRY_DSN unset, so no telemetry is sent."""
    monkeypatch.setattr(obs, "_SENTRY_DSN", None)
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: pytest.fail("initialized Sentry"))
    obs.init_sentry()
