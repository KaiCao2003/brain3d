#!/usr/bin/env python3
"""Verify the default install and explicit bridge entry point without test extras."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import import_module, util


def _request(request_id: str, method: str, params: dict[str, object]) -> str:
    return json.dumps({"id": request_id, "method": method, "params": params}) + "\n"


def main() -> int:
    forbidden = ("PySide6", "pyvista", "pyvistaqt", "vtk", "vtkmodules")
    available = [name for name in forbidden if util.find_spec(name) is not None]
    if available:
        raise RuntimeError(f"removed desktop dependencies remain importable: {available}")

    # Import the two supported Python entry modules before spawning a real exchange. This catches
    # accidental import-time coupling even if the executable path below is later refactored.
    import_module("mouse_brain_planner.bridge.server")
    import_module("mouse_brain_planner.cli")

    payload = "".join(
        (
            _request(
                "hello",
                "hello",
                {"protocolVersion": 1, "client": "minimal-runtime-verifier"},
            ),
            _request("shutdown", "shutdown", {"protocolVersion": 1}),
        )
    )
    completed = subprocess.run(
        [sys.executable, "-m", "mouse_brain_planner", "bridge"],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"bridge exited {completed.returncode}: {completed.stderr.strip()}")
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    if len(responses) != 2:
        raise RuntimeError(f"expected 2 bridge responses, received {len(responses)}")
    if responses[0].get("id") != "hello":
        raise RuntimeError("bridge hello response id mismatch")
    hello = responses[0].get("result")
    if not isinstance(hello, dict) or hello.get("protocolVersion") != 1:
        raise RuntimeError("bridge hello response violated protocol v1")
    if responses[1] != {
        "id": "shutdown",
        "result": {"protocolVersion": 1, "status": "shuttingDown"},
    }:
        raise RuntimeError("bridge shutdown response violated protocol v1")
    if completed.stderr:
        raise RuntimeError(f"clean bridge handshake wrote diagnostics: {completed.stderr!r}")

    print("minimal runtime verified: no Qt/VTK imports; bridge hello/shutdown passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
