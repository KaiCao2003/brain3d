#!/usr/bin/env python3
"""Write stable release-build provenance into the application bundle."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path


def _command(*arguments: str) -> str:
    return subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--application-version", required=True)
    parser.add_argument("--declared-minimum-macos", required=True)
    parser.add_argument("--maximum-bundled-deployment-target", required=True)
    parser.add_argument("--surgery-atlas-sha256")
    arguments = parser.parse_args()

    repository = arguments.repository.resolve()
    source_status = _command("git", "-C", str(repository), "status", "--porcelain")
    payload = {
        "applicationVersion": arguments.application_version,
        "architecture": platform.machine(),
        "declaredMinimumMacOS": arguments.declared_minimum_macos,
        "macOSBuildVersion": platform.mac_ver()[0],
        "maximumBundledDeploymentTarget": arguments.maximum_bundled_deployment_target,
        "pyInstallerVersion": version("pyinstaller"),
        "pythonVersion": platform.python_version(),
        "sourceCommit": _command("git", "-C", str(repository), "rev-parse", "HEAD"),
        "sourceWorktreeDirty": bool(source_status),
        "surgeryAtlas": {
            "bundled": arguments.surgery_atlas_sha256 is not None,
            "distributionScope": (
                "local-user-supplied"
                if arguments.surgery_atlas_sha256 is not None
                else "external-user-supplied"
            ),
            "sha256": arguments.surgery_atlas_sha256,
        },
        "swiftVersion": _command("swift", "--version").splitlines()[0],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
