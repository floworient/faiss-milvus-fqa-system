import json
import logging
from typing import Any


def configure_logging(level: str = "INFO") -> None:
    """Configure a minimal JSON-message logger without exposing application data."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
