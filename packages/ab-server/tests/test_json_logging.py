from __future__ import annotations

import io
import json
import logging

from ab_server.config import Settings
from ab_server.logging_setup import JSONFormatter, configure_logging
from ab_server.main import create_app


def _capture_root_log(record_emit) -> list[str]:
    """Capture lines emitted by the current root logger handler."""
    buffer = io.StringIO()
    root = logging.getLogger()
    # Re-point the existing handler to our buffer.
    handler = root.handlers[0]
    original_stream = handler.stream  # type: ignore[attr-defined]
    handler.stream = buffer  # type: ignore[attr-defined]
    try:
        record_emit()
        handler.flush()
    finally:
        handler.stream = original_stream  # type: ignore[attr-defined]
    return [line for line in buffer.getvalue().splitlines() if line.strip()]


def test_json_logging_produces_parseable_records() -> None:
    configure_logging(log_format="json")
    logger = logging.getLogger("ab_server.test")

    def _emit() -> None:
        logger.info("hello world", extra={"request_id": "abc-123", "path": "/x"})

    lines = _capture_root_log(_emit)
    assert lines, "expected at least one log line"
    payload = json.loads(lines[-1])
    for key in ("ts", "level", "logger", "msg"):
        assert key in payload, f"missing key {key} in {payload}"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "ab_server.test"
    assert payload["msg"] == "hello world"
    assert payload["request_id"] == "abc-123"
    assert payload["path"] == "/x"


def test_json_formatter_handles_non_serializable_extras() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="x",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="boom",
        args=(),
        exc_info=None,
    )
    record.weird = object()  # not JSON-serializable
    line = formatter.format(record)
    payload = json.loads(line)
    assert payload["msg"] == "boom"
    assert "weird" in payload
    assert isinstance(payload["weird"], str)  # fell back to repr()


def test_text_logging_is_not_json() -> None:
    configure_logging(log_format="text")
    logger = logging.getLogger("ab_server.text")

    def _emit() -> None:
        logger.info("plain message")

    lines = _capture_root_log(_emit)
    assert lines
    # In text mode the line is not valid JSON.
    try:
        json.loads(lines[-1])
    except json.JSONDecodeError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError("text log line unexpectedly parsed as JSON")


def test_create_app_invokes_logging_configuration() -> None:
    # When create_app runs with log_format=json, the root handler must be
    # a JSONFormatter-backed StreamHandler.
    create_app(Settings(log_format="json"))
    root = logging.getLogger()
    assert root.handlers, "root logger has no handlers"
    assert isinstance(root.handlers[0].formatter, JSONFormatter)

    # And flipping back to text replaces it.
    create_app(Settings(log_format="text"))
    root = logging.getLogger()
    assert not isinstance(root.handlers[0].formatter, JSONFormatter)
