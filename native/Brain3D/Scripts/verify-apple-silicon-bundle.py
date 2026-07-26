#!/usr/bin/env python3
"""Fail unless every Mach-O in an application bundle is portable arm64 code."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

_RELOCATABLE_PREFIXES = ("@rpath/", "@loader_path/", "@executable_path/")
_SYSTEM_PREFIXES = ("/System/Library/", "/usr/lib/")
_ALLOWED_RPATHS = ("/usr/lib/swift",)


def _command(*arguments: str) -> str:
    return subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _version_tuple(value: str) -> tuple[int, int, int]:
    components = value.split(".")
    if not components or len(components) > 3 or not all(part.isdigit() for part in components):
        raise SystemExit(f"invalid macOS deployment version reported by otool: {value!r}")
    return tuple(int(part) for part in components) + (0,) * (3 - len(components))


def _load_command_values(path: Path) -> tuple[str, list[str]]:
    active_command = ""
    versions: list[str] = []
    rpaths: list[str] = []
    for raw_line in _command("otool", "-l", str(path)).splitlines():
        line = raw_line.strip()
        if line.startswith("cmd "):
            active_command = line.removeprefix("cmd ")
        elif active_command == "LC_BUILD_VERSION" and line.startswith("minos "):
            versions.append(line.removeprefix("minos ").split()[0])
        elif active_command == "LC_VERSION_MIN_MACOSX" and line.startswith("version "):
            versions.append(line.removeprefix("version ").split()[0])
        elif active_command == "LC_RPATH" and line.startswith("path "):
            rpaths.append(line.removeprefix("path ").split()[0])
    if not versions:
        raise SystemExit(f"Mach-O has no macOS deployment target: {path}")
    return max(versions, key=_version_tuple), rpaths


def _verify_dependencies(path: Path, output: str) -> None:
    for raw_line in output.splitlines()[1:]:
        dependency = raw_line.strip().split(" (", maxsplit=1)[0]
        if not dependency:
            continue
        if dependency.startswith((*_RELOCATABLE_PREFIXES, *_SYSTEM_PREFIXES)):
            continue
        raise SystemExit(f"Mach-O has a host-only or relative dependency: {path}: {dependency}")


def _verify_rpaths(path: Path, rpaths: list[str]) -> None:
    for rpath in rpaths:
        if rpath in _ALLOWED_RPATHS or rpath.startswith(
            ("@loader_path", "@executable_path", "@rpath")
        ):
            continue
        raise SystemExit(f"Mach-O has a host-only runpath: {path}: {rpath}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--maximum-macos", default="14.0")
    parser.add_argument("--forbidden-prefix", action="append", default=[])
    arguments = parser.parse_args()

    bundle = arguments.bundle.resolve(strict=True)
    if not bundle.is_dir() or bundle.suffix != ".app":
        raise SystemExit(f"bundle is not an application directory: {bundle}")
    maximum = _version_tuple(arguments.maximum_macos)

    macho_count = 0
    maximum_observed = "0.0"
    for candidate in sorted(bundle.rglob("*"), key=lambda path: str(path).casefold()):
        if candidate.is_symlink():
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(bundle):
                raise SystemExit(
                    f"bundle symlink escapes the application: {candidate} -> {resolved}"
                )
            continue
        if not candidate.is_file():
            continue
        kind = _command("file", "-b", str(candidate)).strip()
        if not kind.startswith("Mach-O"):
            continue
        architectures = _command("lipo", "-archs", str(candidate)).split()
        if architectures != ["arm64"]:
            raise SystemExit(f"Mach-O is not arm64-only: {candidate}: {architectures}")
        dependencies = _command("otool", "-L", str(candidate))
        _verify_dependencies(candidate, dependencies)
        for forbidden in [*arguments.forbidden_prefix, ".venv"]:
            if forbidden and forbidden in dependencies:
                raise SystemExit(f"Mach-O links to forbidden path {forbidden!r}: {candidate}")
        minimum, rpaths = _load_command_values(candidate)
        _verify_rpaths(candidate, rpaths)
        if _version_tuple(minimum) > maximum:
            raise SystemExit(
                f"Mach-O requires macOS {minimum}, above {arguments.maximum_macos}: {candidate}"
            )
        if _version_tuple(minimum) > _version_tuple(maximum_observed):
            maximum_observed = minimum
        macho_count += 1

    if macho_count < 2:
        raise SystemExit("expected both Swift and bundled Python Mach-O files")
    print(
        json.dumps(
            {
                "architecture": "arm64",
                "machOCount": macho_count,
                "maximumDeploymentTarget": maximum_observed,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
