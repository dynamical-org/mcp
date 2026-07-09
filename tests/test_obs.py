import logging

from server.obs import _DropCancellationNoise


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
