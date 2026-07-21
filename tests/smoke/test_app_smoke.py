"""Headless first-frame application smoke test."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gui


def test_application_enters_and_exits_qt_event_loop(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["PYVISTA_OFF_SCREEN"] = "true"
    environment["MOUSE_BRAIN_PLANNER_CONFIG_DIR"] = str(tmp_path / "config")
    environment["MOUSE_BRAIN_PLANNER_DATA_DIR"] = str(tmp_path / "data")
    environment["MOUSE_BRAIN_PLANNER_CACHE_DIR"] = str(tmp_path / "cache")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mouse_brain_planner",
            "--smoke-test",
            "--no-download",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    log_path = tmp_path / "cache" / "logs" / "application.jsonl"
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == [
        "application-starting",
        "application-stopped",
    ]
    assert all(record["application_version"] for record in records)
