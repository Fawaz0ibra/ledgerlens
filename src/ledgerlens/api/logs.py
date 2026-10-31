"""JSON logs: one object per line, each tagged with the ID of the request that wrote it.

Never log invoice contents. Names, VAT numbers and amounts stay out of the logs.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Set by the request middleware. Every line logged while handling that request carries it.
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id.get(),
            # Structured fields, passed as log.info("...", extra={"fields": {...}}).
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure(level: str) -> None:
    """Send every log line, ours and Uvicorn's, to stdout as JSON."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Uvicorn installs its own plain-text handlers before it calls our app factory. Route them through ours.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_log = logging.getLogger(name)
        uvicorn_log.handlers = []
        uvicorn_log.propagate = True
        uvicorn_log.setLevel(level)
    # Our middleware writes one line per request, with its ID, so Uvicorn's access line would be a duplicate.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
