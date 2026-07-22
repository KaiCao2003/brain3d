"""Application-owned structured logging for terminal-less macOS launches."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

from mouse_brain_planner.paths import AppPaths, app_paths
from mouse_brain_planner.version import __version__

LOGGER_NAMESPACE = "mouse_brain_planner"
LOG_FILENAME = "application.jsonl"
MAX_LOG_MESSAGE_CHARS = 4_000
MAX_LOG_EXCEPTION_CHARS = 8_000

_URL_USERINFO = re.compile(
    r"(?P<scheme>\b[a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?P<key>\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?token|authorization)\b)"
    r"(?P<separator>\s*[:=]\s*)(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
_BEARER_TOKEN = re.compile(r"\bBearer\s+[^\s,;]+", re.IGNORECASE)
_ABSOLUTE_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9_.:/-])/(?:[^/\s:]+/)*[^/\s:,;\]\[(){}]+")


def _redact_private_text(value: str, *, max_chars: int) -> str:
    """Remove credentials and private filesystem locations from one log field."""

    redacted = _URL_USERINFO.sub(r"\g<scheme><redacted>@", value)
    redacted = _SECRET_ASSIGNMENT.sub(
        r"\g<key>\g<separator><redacted>",
        redacted,
    )
    redacted = _BEARER_TOKEN.sub("Bearer <redacted>", redacted)
    redacted = _ABSOLUTE_POSIX_PATH.sub("<path>", redacted)
    if len(redacted) <= max_chars:
        return redacted
    suffix = "…<truncated>"
    return redacted[: max_chars - len(suffix)] + suffix


class JsonLineFormatter(logging.Formatter):
    """Serialize one bounded application log event as a JSON object."""

    _extra_fields = ("event", "atlas_key", "atlas_version", "exit_code")

    def format(self, record: logging.LogRecord) -> str:
        """Return one UTF-8-safe JSON line without private process state."""

        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_private_text(
                record.getMessage(),
                max_chars=MAX_LOG_MESSAGE_CHARS,
            ),
            "application_version": __version__,
            "thread": record.threadName,
        }
        for field in self._extra_fields:
            if field in record.__dict__:
                field_value = record.__dict__[field]
                payload[field] = (
                    _redact_private_text(field_value, max_chars=MAX_LOG_MESSAGE_CHARS)
                    if isinstance(field_value, str)
                    else field_value
                )
        if record.exc_info is not None:
            payload["exception"] = _redact_private_text(
                self.formatException(record.exc_info),
                max_chars=MAX_LOG_EXCEPTION_CHARS,
            )
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
