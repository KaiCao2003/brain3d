"""Application-owned structured logging for terminal-less macOS launches."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

from mouse_brain_planner.paths import AppPaths, app_paths
from mouse_brain_planner.version import __version__

LOGGER_NAMESPACE = "mouse_brain_planner"
LOG_FILENAME = "application.jsonl"


class JsonLineFormatter(logging.Formatter):
    """Serialize one bounded application log event as a JSON object."""

    _extra_fields = ("event", "atlas_key", "atlas_version", "exit_code")

    def format(self, record: logging.LogRecord) -> str:
        """Return one UTF-8-safe JSON line without private process state."""

        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "application_version": __version__,
            "thread": record.threadName,
        }
        for field in self._extra_fields:
            if field in record.__dict__:
                payload[field] = record.__dict__[field]
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


class _PlannerFileHandler(RotatingFileHandler):
    """Marker type preventing duplicate application-owned handlers."""


class _PlannerFallbackHandler(logging.StreamHandler[TextIO]):
    """Marker type for a stderr fallback when the cache is unavailable."""


def configure_logging(paths: AppPaths | None = None) -> Path | None:
    """Configure one rotating JSON-lines handler and return its path.

    Logging failure must not prevent the scientific UI from opening. If the
    app-owned cache cannot be created, the same structured records go to
    standard error instead.
    """

    logger = logging.getLogger(LOGGER_NAMESPACE)
    for existing_handler in logger.handlers:
        if isinstance(existing_handler, _PlannerFileHandler):
            return Path(existing_handler.baseFilename)
        if isinstance(existing_handler, _PlannerFallbackHandler):
            return None

    resolved = paths or app_paths()
    formatter = JsonLineFormatter()
    log_path: Path | None = None
    try:
        log_directory = resolved.cache / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        log_path = log_directory / LOG_FILENAME
        output_handler: logging.Handler = _PlannerFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError:
        output_handler = _PlannerFallbackHandler()
    output_handler.setFormatter(formatter)
    logger.addHandler(output_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return log_path
