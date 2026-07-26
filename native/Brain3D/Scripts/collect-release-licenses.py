#!/usr/bin/env python3
"""Copy exact runtime dependency notices from a clean release environment."""

from __future__ import annotations

import argparse
import json
import shutil
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

_NOTICE_NAMES = ("LICENSE", "LICENCE", "COPYING", "NOTICE")


def _runtime_distributions(root_name: str) -> dict[str, Distribution]:
    environment = default_environment()
    environment["extra"] = ""
    pending = [root_name]
    resolved: dict[str, Distribution] = {}
    while pending:
        name = pending.pop()
        canonical = canonicalize_name(name)
        if canonical in resolved:
            continue
        try:
            package = distribution(name)
        except PackageNotFoundError as error:
            raise SystemExit(f"release dependency is not installed: {name}") from error
        resolved[canonical] = package
        for raw_requirement in package.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker is None or requirement.marker.evaluate(environment):
                pending.append(requirement.name)
    return resolved


def _notice_files(package: Distribution) -> list[Path]:
    notices: list[Path] = []
    for installed_file in package.files or ():
        if not any(token in Path(str(installed_file)).name.upper() for token in _NOTICE_NAMES):
            continue
        source = Path(package.locate_file(installed_file))
        if source.is_file():
            notices.append(source)
    return sorted(set(notices), key=lambda path: str(path).casefold())


def _safe_notice_name(index: int, source: Path) -> str:
    clean_name = "".join(
        character if character.isalnum() or character in ".-_" else "_" for character in source.name
    )
    return f"{index:02d}-{clean_name}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root-distribution", default="mouse-brain-planner")
    parser.add_argument("--packager-distribution", default="pyinstaller")
    arguments = parser.parse_args()

    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    licenses = output / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)

    runtime = _runtime_distributions(arguments.root_distribution)
    packager = distribution(arguments.packager_distribution)
    records: list[dict[str, object]] = []
    for canonical, package in sorted(runtime.items()):
        package_output = licenses / canonical
        package_output.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        notices = _notice_files(package)
        for index, source in enumerate(notices, start=1):
            destination = package_output / _safe_notice_name(index, source)
            shutil.copyfile(source, destination)
            copied.append(str(destination.relative_to(output)))
        if not copied:
            fallback = package_output / "LICENSE-METADATA.txt"
            fallback.write_text(
                (
                    package.metadata.get("License-Expression")
                    or package.metadata.get("License")
                    or ""
                )
                + "\n",
                encoding="utf-8",
            )
            copied.append(str(fallback.relative_to(output)))
        records.append(
            {
                "name": package.metadata["Name"],
                "version": package.version,
                "licenseExpression": package.metadata.get("License-Expression"),
                "licenseMetadata": package.metadata.get("License"),
                "noticeFiles": copied,
                "role": "runtime",
            }
        )

    packager_output = licenses / f"{canonicalize_name(packager.metadata['Name'])}-packager"
    packager_output.mkdir(parents=True, exist_ok=True)
    packager_notices: list[str] = []
    for index, source in enumerate(_notice_files(packager), start=1):
        destination = packager_output / _safe_notice_name(index, source)
        shutil.copyfile(source, destination)
        packager_notices.append(str(destination.relative_to(output)))
    records.append(
        {
            "name": packager.metadata["Name"],
            "version": packager.version,
            "licenseExpression": packager.metadata.get("License-Expression"),
            "licenseMetadata": packager.metadata.get("License"),
            "noticeFiles": packager_notices,
            "role": "packager (bootloader exception applies)",
        }
    )
    (output / "dependency-licenses.json").write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
