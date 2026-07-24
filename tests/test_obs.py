import logging

from server.obs import _before_send, _before_send_log, _DropCancellationNoise


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


def test_before_send_drops_client_disconnect_exception():
    event = {"exception": {"values": [{"type": "ClientDisconnect", "value": ""}]}}
    assert _before_send(event, {}) is None


def test_before_send_drops_stream_exception_log():
    event = {
        "logger": "mcp.server.lowlevel.server",
        "logentry": {"message": "Received exception from stream: "},
    }
    assert _before_send(event, {}) is None


def test_before_send_keeps_unrelated_errors():
    event = {"exception": {"values": [{"type": "ValueError", "value": "boom"}]}}
    assert _before_send(event, {}) is event


def test_before_send_keeps_unrelated_logger_messages():
    event = {"logger": "server.web", "logentry": {"message": "mcp_request"}}
    assert _before_send(event, {}) is event


def test_before_send_log_drops_cancellation_signal():
    log = {"body": "Received a cancellation signal while processing input (in-01ABC)"}
    assert _before_send_log(log, {}) is None


def test_before_send_log_keeps_ordinary_logs():
    log = {"body": "mcp_request"}
    assert _before_send_log(log, {}) is log
