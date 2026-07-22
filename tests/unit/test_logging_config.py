"""Tests for privacy-preserving structured application logs."""

from __future__ import annotations

import json
import logging
import sys

from mouse_brain_planner.logging_config import (
    MAX_LOG_EXCEPTION_CHARS,
    MAX_LOG_MESSAGE_CHARS,
    JsonLineFormatter,
)


def test_formatter_redacts_paths_credentials_and_exception_text() -> None:
    logger = logging.getLogger("mouse_brain_planner.privacy-test")
    try:
        raise RuntimeError(
            "failed at /Users/tester/private/plan.mouseplan "
            "with token=token-value and Bearer bearer-value"
        )
    except RuntimeError:
        record = logger.makeRecord(
            logger.name,
            logging.ERROR,
            "/Users/tester/private/source.py",
            12,
            "request https://alice:password@example.invalid/data "
            "api_key=key-value path /private/tmp/project.mouseplan",
            (),
            sys.exc_info(),
            extra={"event": "open /Users/tester/private/plan.mouseplan"},
        )

    payload = json.loads(JsonLineFormatter().format(record))
    serialized = json.dumps(payload)

    for private_value in (
        "/Users/tester",
        "/private/tmp",
        "password",
        "token-value",
        "bearer-value",
        "key-value",
    ):
        assert private_value not in serialized
    assert payload["message"].startswith("request https://<redacted>@example.invalid/data")
    assert "api_key=<redacted>" in payload["message"]
    assert "<path>" in payload["message"]
    assert "<path>" in payload["exception"]
    assert payload["event"] == "open <path>"


def test_formatter_bounds_attacker_controlled_message_and_exception() -> None:
    logger = logging.getLogger("mouse_brain_planner.bounded-log-test")
    try:
        raise RuntimeError("x" * (MAX_LOG_EXCEPTION_CHARS * 2))
    except RuntimeError:
        record = logger.makeRecord(
            logger.name,
            logging.ERROR,
            __file__,
            1,
            "y" * (MAX_LOG_MESSAGE_CHARS * 2),
            (),
            sys.exc_info(),
        )

    payload = json.loads(JsonLineFormatter().format(record))

    assert len(payload["message"]) == MAX_LOG_MESSAGE_CHARS
    assert payload["message"].endswith("…<truncated>")
    assert len(payload["exception"]) == MAX_LOG_EXCEPTION_CHARS
    assert payload["exception"].endswith("…<truncated>")
