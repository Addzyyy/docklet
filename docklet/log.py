"""Structured logging for docklet.

Emits JSON-formatted log records with container_id correlation.
Uses only stdlib logging — zero dependencies.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "module": record.module,
            "message": record.getMessage(),
        }
        # Include extra context fields (e.g., container_id, image, layer)
        for key in ("container_id", "image", "tag", "layer", "duration_ms", "error"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry)


def setup_logging(level: int = logging.INFO, json_output: bool = True) -> None:
    """Configure root logger for docklet."""
    root = logging.getLogger("docklet")
    root.setLevel(level)

    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the docklet namespace."""
    return logging.getLogger(f"docklet.{name}")
