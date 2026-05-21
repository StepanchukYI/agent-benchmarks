"""Logging configuration for ab-server.

Two formats:
- ``text``: stdlib default ``Formatter`` with a human-readable layout.
- ``json``: one-line JSON per log record. Useful behind a log aggregator
  (Loki/Promtail, journald-json, ELK, etc.) on the homelab.

``configure_logging`` is invoked once from ``ab_server.main.create_app``.
Calling it again replaces the root handler in-place so tests can reconfigure.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

# Attributes that every ``LogRecord`` always carries. We strip them when
# collecting ``extra`` so the JSON output stays compact.
_STD_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
        "taskName",
    }
)


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record on a single line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Capture any structured fields the caller passed via ``extra=``.
        for key, value in record.__dict__.items():
            if key in _STD_RECORD_ATTRS or key.startswith("_"):
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                value = repr(value)
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_format: str = "text", level: int = logging.INFO) -> None:
    """Configure the root logger.

    Safe to call multiple times — existing handlers on the root logger are
    removed first so tests can flip formats between calls.
    """
    root = logging.getLogger()
    # Drop any prior handlers (idempotent reconfigure).
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    root.addHandler(handler)
    root.setLevel(level)
