"""Atomic save, checksum validation, and backup recovery for projects."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.persistence.migrations import migrate_project_payload

PROJECT_SUFFIX = ".mouseplan"
PROJECT_FILENAME = "project.json"
ATLAS_FILENAME = "atlas.json"
REGIONS_FILENAME = "regions.json"
CHECKSUMS_FILENAME = "checksums.json"


class ProjectIntegrityError(ValueError):
    """Raised when project checksums or structure are invalid."""


def normalize_project_path(path: str | Path) -> Path:
    """Return an absolute project-package path with the required suffix."""

    resolved = Path(path).expanduser().resolve()
    if resolved.suffix != PROJECT_SUFFIX and not resolved.name.endswith(f"{PROJECT_SUFFIX}.bak"):
        resolved = resolved.with_name(resolved.name + PROJECT_SUFFIX)
    return resolved


def save_project(project: PlannerProject, path: str | Path) -> Path:
    """Atomically replace a human-readable project directory.

    The previous valid package remains at ``<name>.mouseplan.bak``. A failed
    replacement restores it before propagating the error.
    """

    destination = normalize_project_path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    backup = destination.with_name(destination.name + ".bak")

    try:
        payload = project.model_dump(mode="json")
        atlas_payload = payload.pop("atlas")
        regions_payload = payload.pop("region_display")
        _write_json(temporary / PROJECT_FILENAME, payload)
        _write_json(temporary / ATLAS_FILENAME, atlas_payload)
        _write_json(temporary / REGIONS_FILENAME, regions_payload)
        checksums = {
            filename: _sha256(temporary / filename)
            for filename in (PROJECT_FILENAME, ATLAS_FILENAME, REGIONS_FILENAME)
        }
        _write_json(temporary / CHECKSUMS_FILENAME, checksums)

        if backup.exists():
            _remove_exact_package(backup)
        if destination.exists():
            destination.replace(backup)
        try:
            temporary.replace(destination)
        except OSError:
            if backup.exists() and not destination.exists():
                backup.replace(destination)
            raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def load_project(path: str | Path, *, recover_backup: bool = True) -> PlannerProject:
    """Load and verify a project, optionally falling back to its backup."""

    destination = normalize_project_path(path)
    try:
        return _load_verified(destination)
    except (OSError, ProjectIntegrityError, ValidationError, ValueError):
        backup = destination.with_name(destination.name + ".bak")
        if not recover_backup or not backup.exists():
            raise
        return _load_verified(backup)


def validate_project(path: str | Path) -> list[str]:
    """Return human-readable validation errors without raising."""

    try:
        _load_verified(normalize_project_path(path))
    except (OSError, ProjectIntegrityError, ValidationError, ValueError) as exc:
        return [str(exc)]
    return []


def _load_verified(path: Path) -> PlannerProject:
    if not path.is_dir():
        raise ProjectIntegrityError(f"project package does not exist: {path}")
    checksum_path = path / CHECKSUMS_FILENAME
    checksums = _read_json(checksum_path)
    if not isinstance(checksums, dict):
        raise ProjectIntegrityError("checksums.json must contain an object")
    for filename in (PROJECT_FILENAME, ATLAS_FILENAME, REGIONS_FILENAME):
        expected = checksums.get(filename)
        actual = _sha256(path / filename)
        if expected != actual:
            raise ProjectIntegrityError(
                f"checksum mismatch for {filename}: expected {expected!r}, got {actual}"
            )

    project_payload = _read_json(path / PROJECT_FILENAME)
    atlas_payload = _read_json(path / ATLAS_FILENAME)
    regions_payload = _read_json(path / REGIONS_FILENAME)
    if not isinstance(project_payload, dict):
        raise ProjectIntegrityError("project.json must contain an object")
    project_payload["atlas"] = atlas_payload
    project_payload["region_display"] = regions_payload
    migrated = migrate_project_payload(project_payload)
    return PlannerProject.model_validate(migrated)


def _write_json(path: Path, payload: Any) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_exact_package(path: Path) -> None:
    if path.is_symlink() or not path.is_dir() or not path.name.endswith(f"{PROJECT_SUFFIX}.bak"):
        raise ProjectIntegrityError(f"refusing to remove unexpected backup path: {path}")
    shutil.rmtree(path)
