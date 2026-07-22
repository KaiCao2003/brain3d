"""Subprocess verification of protocol-only bridge standard output."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _line(request_id: str, method: str, params: dict[str, object]) -> str:
    return json.dumps({"id": request_id, "method": method, "params": params}) + "\n"


@pytest.mark.parametrize(
    "command",
    (
        (sys.executable, "-m", "mouse_brain_planner.bridge.server"),
        (sys.executable, "-m", "mouse_brain_planner", "bridge"),
    ),
    ids=("swift-direct-module", "explicit-cli-command"),
)
def test_bridge_entrypoints_keep_stdout_protocol_only_and_recover_after_bad_json(
    command: tuple[str, ...],
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository_root / "src")
    payload = "".join(
        (
            _line(
                "hello",
                "hello",
                {"protocolVersion": 1, "client": "Brain3DSwiftUI"},
            ),
            "not-json\n",
            _line("state", "state.get", {"protocolVersion": 1}),
            _line("shutdown", "shutdown", {"protocolVersion": 1}),
        )
    )

    completed = subprocess.run(
        command,
        cwd=repository_root,
        env=environment,
        input=payload,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    stdout_lines = completed.stdout.splitlines()
    assert len(stdout_lines) == 4
    responses = [json.loads(line) for line in stdout_lines]
    assert [response["id"] for response in responses] == ["hello", None, "state", "shutdown"]
    assert responses[0]["result"]["capabilities"]["animalOnly"] is True
    assert responses[1]["error"]["code"] == "PARSE_ERROR"
    assert responses[2]["result"]["atlas"]["version"] == "1.2"
    assert responses[3]["result"]["status"] == "shuttingDown"
    assert "bridge request rejected: PARSE_ERROR" in completed.stderr
