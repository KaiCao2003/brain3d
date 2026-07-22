"""Bounded project I/O, atomic replacement, and explicit backup recovery."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.domain.vessel_models import SubjectVascularImage
from mouse_brain_planner.persistence.migrations import migrate_project_payload
from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION

PROJECT_SUFFIX = ".mouseplan"
BACKUP_SUFFIX = f"{PROJECT_SUFFIX}.bak"
PROJECT_FILENAME = "project.json"
ATLAS_FILENAME = "atlas.json"
REGIONS_FILENAME = "regions.json"
VASCULATURE_FILENAME = "vasculature.json"
CHECKSUMS_FILENAME = "checksums.json"

LEGACY_CHECKSUMMED_FILENAMES = (PROJECT_FILENAME, ATLAS_FILENAME, REGIONS_FILENAME)
CHECKSUMMED_FILENAMES = (*LEGACY_CHECKSUMMED_FILENAMES, VASCULATURE_FILENAME)
VASCULAR_PROJECT_FIELDS = (
    "subject_vascular_images",
    "dorsal_vascular_registrations",
    "subject_vascular_overlays",
    "reference_vascular_density",
)
MAX_PROJECT_IMAGE_BYTES = 512 * 1024 * 1024
PROJECT_MEMBER_MAX_BYTES: dict[str, int] = {
    CHECKSUMS_FILENAME: 256 * 1024,
    PROJECT_FILENAME: 4 * 1024 * 1024,
    ATLAS_FILENAME: 2 * 1024 * 1024,
    REGIONS_FILENAME: 64 * 1024 * 1024,
    VASCULATURE_FILENAME: 16 * 1024 * 1024,
}


class ProjectIntegrityError(ValueError):
    """Raised when project checksums, members, or package structure are invalid."""


class ProjectRecoveryError(ProjectIntegrityError):
    """Raised when both the requested package and its recovery backup are invalid."""


@dataclass(frozen=True, slots=True)
class ProjectLoadResult:
    """A verified project together with the exact package that supplied it.

    A backup source is deliberately read-only. Callers should leave their normal
    save path unset and require Save As instead of writing back to ``.mouseplan.bak``.
    """

    project: PlannerProject
    requested_path: Path
    source_path: Path
    recovered_from_backup: bool

    @property
    def is_backup_source(self) -> bool:
        """Return whether bytes came from a reserved backup package."""

        return _is_backup_path(self.source_path)

    @property
    def requires_save_as(self) -> bool:
        """Return whether the loaded project must be saved to a new primary path."""

        return self.is_backup_source

    @property
    def writable_path(self) -> Path | None:
        """Return the normal save target, or ``None`` for read-only recovery sources."""

        return None if self.requires_save_as else self.source_path


def normalize_project_path(path: str | Path) -> Path:
    """Return an absolute package path without following the final path entry.

    Resolving only the parent keeps a final package symlink observable so the
    verification boundary can reject it instead of silently opening its target.
    """

    expanded = Path(path).expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    parent = expanded.parent.resolve(strict=False)
    name = expanded.name
    if not name.endswith(PROJECT_SUFFIX) and not name.endswith(BACKUP_SUFFIX):
        name += PROJECT_SUFFIX
    return parent / name


def save_project(
    project: PlannerProject,
    path: str | Path,
    *,
    asset_source_package: str | Path | None = None,
) -> Path:
    """Durably replace a primary project while retaining a recoverable backup.

    Backup packages are reserved, read-only recovery inputs. Existing backups
    are staged rather than deleted before rotation, so a rename failure cannot
    remove the only known-good recovery copy.  Subject image bytes are copied
    from ``asset_source_package``.  A normal save may infer the current
    destination as its source; Save As must pass the verified package returned
    by :func:`load_project_with_provenance`. Missing source context fails closed
    before replacement.
    """

    # Assignment validation cannot observe in-place list mutation. Revalidate
    # the complete graph before deriving package members and asset paths.
    project = PlannerProject.model_validate(project.model_dump(mode="python"))
    destination = normalize_project_path(path)
    if _is_backup_path(destination):
        raise ProjectIntegrityError(
            f"backup packages are read-only; choose a {PROJECT_SUFFIX} Save As path: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ProjectIntegrityError(f"refusing to replace project symlink: {destination}")
    if _entry_exists(destination) and not destination.is_dir():
        raise ProjectIntegrityError(
            f"project destination must be a directory package: {destination}"
        )

    asset_source = _resolve_asset_source(
        project,
        destination=destination,
        explicit_source=asset_source_package,
    )

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.new.", dir=destination.parent))
    backup = _backup_path(destination)

    try:
        payload = project.model_dump(mode="json")
        atlas_payload = payload.pop("atlas")
        regions_payload = payload.pop("region_display")
        vasculature_payload = {field: payload.pop(field) for field in VASCULAR_PROJECT_FIELDS}
        _write_json(temporary / PROJECT_FILENAME, payload)
        _write_json(temporary / ATLAS_FILENAME, atlas_payload)
        _write_json(temporary / REGIONS_FILENAME, regions_payload)
        _write_json(temporary / VASCULATURE_FILENAME, vasculature_payload)
        checksums = {
            filename: _sha256_file(temporary / filename) for filename in CHECKSUMMED_FILENAMES
        }
        if asset_source is not None:
            checksums.update(
                _copy_verified_subject_assets(
                    project.subject_vascular_images,
                    source_package=asset_source,
                    destination_package=temporary,
                )
            )
        _write_json(temporary / CHECKSUMS_FILENAME, checksums)
        _fsync_directory(temporary)

        # Exercise the exact load boundary before rotating any existing package.
        prepared = _load_verified(temporary)
        if prepared.model_dump(mode="json") != project.model_dump(mode="json"):
            raise ProjectIntegrityError("prepared project changed during serialization")

        _commit_project_directory(temporary, destination, backup)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def _resolve_asset_source(
    project: PlannerProject,
    *,
    destination: Path,
    explicit_source: str | Path | None,
) -> Path | None:
    """Resolve required subject-image bytes without guessing a Save As source."""

    if not project.subject_vascular_images:
        return None
    if explicit_source is not None:
        source = _normalize_package_root(explicit_source)
    elif _entry_exists(destination):
        source = destination
    else:
        raise ProjectIntegrityError(
            "subject vascular images require asset_source_package for a new or Save As package"
        )
    _validated_package_root(source)
    return source


def _normalize_package_root(path: str | Path) -> Path:
    """Normalize a package-like directory while preserving its final entry."""

    expanded = Path(path).expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return expanded.parent.resolve(strict=False) / expanded.name


def _copy_verified_subject_assets(
    images: list[SubjectVascularImage],
    *,
    source_package: Path,
    destination_package: Path,
) -> dict[str, str]:
    """Copy exact verified subject bytes into a private prepared package."""

    source, source_stat = _validated_package_root(source_package)
    source_fd = _open_package_directory(source, source_stat)
    source_images_fd: int | None = None
    destination_images_fd: int | None = None
    checksums: dict[str, str] = {}
    try:
        source_images_fd = _open_images_directory(source, source_fd)
        destination_images = destination_package / "images"
        destination_images.mkdir(mode=0o700)
        destination_images_fd = os.open(
            destination_images,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        for image in sorted(images, key=lambda item: item.project_relative_path):
            relative_path, digest = _copy_one_verified_subject_asset(
                image,
                source_package=source,
                source_images_fd=source_images_fd,
                destination_images_fd=destination_images_fd,
            )
            checksums[relative_path] = digest
        _fsync_directory(destination_images)
    finally:
        if destination_images_fd is not None:
            os.close(destination_images_fd)
        if source_images_fd is not None:
            os.close(source_images_fd)
        os.close(source_fd)
    return checksums


def _open_images_directory(package: Path, package_fd: int) -> int:
    candidate = package / "images"
    try:
        expected = candidate.lstat()
    except FileNotFoundError as error:
        raise ProjectIntegrityError("subject image source has no images directory") from error
    if stat.S_ISLNK(expected.st_mode) or not stat.S_ISDIR(expected.st_mode):
        raise ProjectIntegrityError("subject image source images entry must be a directory")
    if candidate.resolve(strict=True) != candidate:
        raise ProjectIntegrityError("subject image source images directory escapes its package")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open("images", flags, dir_fd=package_fd)
    opened = os.fstat(directory_fd)
    if not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
        expected.st_dev,
        expected.st_ino,
    ):
        os.close(directory_fd)
        raise ProjectIntegrityError("subject image source images directory changed while opening")
    return directory_fd


def _copy_one_verified_subject_asset(
    image: SubjectVascularImage,
    *,
    source_package: Path,
    source_images_fd: int,
    destination_images_fd: int,
) -> tuple[str, str]:
    parts = image.project_relative_path.split("/")
    if len(parts) != 2 or parts[0] != "images":
        raise ProjectIntegrityError(
            f"invalid subject image package path: {image.project_relative_path!r}"
        )
    filename = parts[1]
    candidate = source_package / "images" / filename
    try:
        expected = candidate.lstat()
    except FileNotFoundError as error:
        raise ProjectIntegrityError(
            f"subject image asset does not exist: {image.project_relative_path}"
        ) from error
    if stat.S_ISLNK(expected.st_mode) or not stat.S_ISREG(expected.st_mode):
        raise ProjectIntegrityError(
            f"subject image asset must be a regular file: {image.project_relative_path}"
        )
    if expected.st_size != image.byte_size:
        raise ProjectIntegrityError(
            f"subject image size mismatch for {image.project_relative_path}: "
            f"expected {image.byte_size}, got {expected.st_size}"
        )
    if expected.st_size > MAX_PROJECT_IMAGE_BYTES:
        raise ProjectIntegrityError(
            f"subject image exceeds {MAX_PROJECT_IMAGE_BYTES} bytes: {image.project_relative_path}"
        )

    read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    source_fd = os.open(filename, read_flags, dir_fd=source_images_fd)
    destination_fd: int | None = None
    digest = hashlib.sha256()
    copied = 0
    try:
        opened = os.fstat(source_fd)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            expected.st_dev,
            expected.st_ino,
        ):
            raise ProjectIntegrityError(
                f"subject image changed while opening: {image.project_relative_path}"
            )
        write_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        destination_fd = os.open(filename, write_flags, 0o600, dir_fd=destination_images_fd)
        with (
            os.fdopen(source_fd, "rb", closefd=False) as input_stream,
            os.fdopen(destination_fd, "wb", closefd=False) as output_stream,
        ):
            for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                copied += len(chunk)
                if copied > image.byte_size:
                    raise ProjectIntegrityError(
                        f"subject image grew during copy: {image.project_relative_path}"
                    )
                digest.update(chunk)
                output_stream.write(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
    finally:
        if destination_fd is not None:
            os.close(destination_fd)
        os.close(source_fd)

    actual = digest.hexdigest()
    if copied != image.byte_size:
        raise ProjectIntegrityError(
            f"subject image size mismatch for {image.project_relative_path}: "
            f"expected {image.byte_size}, copied {copied}"
        )
    if actual != image.source_sha256:
        raise ProjectIntegrityError(
            f"subject image checksum mismatch for {image.project_relative_path}: "
            f"expected {image.source_sha256}, got {actual}"
        )
    return image.project_relative_path, actual


def load_project_with_provenance(
    path: str | Path,
    *,
    recover_backup: bool = True,
) -> ProjectLoadResult:
    """Load a verified project and expose backup/recovery provenance.

    Direct backup opens never fall through to a ``.bak.bak`` path. Both direct
    backup opens and automatic fallback recoveries require Save As.
    """

    requested = normalize_project_path(path)
    if _is_backup_path(requested):
        project = _load_verified(requested)
        return ProjectLoadResult(
            project=project,
            requested_path=requested,
            source_path=requested,
            recovered_from_backup=False,
        )

    try:
        project = _load_verified(requested)
    except (OSError, ProjectIntegrityError, ValidationError, ValueError) as primary_error:
        backup = _backup_path(requested)
        if not recover_backup or not _entry_exists(backup):
            raise
        try:
            recovered = _load_verified(backup)
        except (OSError, ProjectIntegrityError, ValidationError, ValueError) as backup_error:
            raise ProjectRecoveryError(
                f"requested project is invalid ({primary_error}); backup recovery also "
                f"failed at {backup} ({backup_error})"
            ) from backup_error
        return ProjectLoadResult(
            project=recovered,
            requested_path=requested,
            source_path=backup,
            recovered_from_backup=True,
        )

    return ProjectLoadResult(
        project=project,
        requested_path=requested,
        source_path=requested,
        recovered_from_backup=False,
    )


def load_project(path: str | Path, *, recover_backup: bool = True) -> PlannerProject:
    """Compatibility wrapper returning only the verified project model.

    New GUI callers should use :func:`load_project_with_provenance` so backup
    sources remain read-only and recovery can be surfaced to the user.
    """

    return load_project_with_provenance(path, recover_backup=recover_backup).project


def validate_project(path: str | Path) -> list[str]:
    """Return human-readable validation errors for the exact requested package."""

    try:
        _load_verified(normalize_project_path(path))
    except (OSError, ProjectIntegrityError, ValidationError, ValueError) as exc:
        return [str(exc)]
    return []


def _load_verified(path: Path) -> PlannerProject:
    package, package_stat = _validated_package_root(path)
    directory_fd = _open_package_directory(package, package_stat)
    try:
        encoded_members = {
            filename: _read_bounded_member(package, directory_fd, filename)
            for filename in (CHECKSUMS_FILENAME, *LEGACY_CHECKSUMMED_FILENAMES)
        }
        checksums = _decode_json(CHECKSUMS_FILENAME, encoded_members[CHECKSUMS_FILENAME])
        if not isinstance(checksums, dict):
            raise ProjectIntegrityError("checksums.json must contain an object")
        for filename in LEGACY_CHECKSUMMED_FILENAMES:
            _verify_encoded_checksum(filename, encoded_members[filename], checksums)

        project_payload = _decode_json(PROJECT_FILENAME, encoded_members[PROJECT_FILENAME])
        atlas_payload = _decode_json(ATLAS_FILENAME, encoded_members[ATLAS_FILENAME])
        regions_payload = _decode_json(REGIONS_FILENAME, encoded_members[REGIONS_FILENAME])
        if not isinstance(project_payload, dict):
            raise ProjectIntegrityError("project.json must contain an object")
        raw_schema_version = project_payload.get("schema_version")
        project_payload["atlas"] = atlas_payload
        project_payload["region_display"] = regions_payload

        if raw_schema_version in {3, PROJECT_SCHEMA_VERSION}:
            vascular_encoded = _read_bounded_member(
                package,
                directory_fd,
                VASCULATURE_FILENAME,
            )
            _verify_encoded_checksum(VASCULATURE_FILENAME, vascular_encoded, checksums)
            vasculature_payload = _decode_json(VASCULATURE_FILENAME, vascular_encoded)
            if not isinstance(vasculature_payload, dict):
                raise ProjectIntegrityError("vasculature.json must contain an object")
            if set(vasculature_payload) != set(VASCULAR_PROJECT_FIELDS):
                raise ProjectIntegrityError(
                    "vasculature.json must contain exactly: " + ", ".join(VASCULAR_PROJECT_FIELDS)
                )
            project_payload.update(vasculature_payload)
        elif raw_schema_version in {1, 2}:
            _require_exact_checksum_names(checksums, set(LEGACY_CHECKSUMMED_FILENAMES))
            if _entry_exists(package / VASCULATURE_FILENAME):
                raise ProjectIntegrityError(
                    f"schema {raw_schema_version} package must not contain "
                    f"unchecksummed {VASCULATURE_FILENAME}"
                )

        migrated = migrate_project_payload(project_payload)
        project = PlannerProject.model_validate(migrated)
        if raw_schema_version in {3, PROJECT_SCHEMA_VERSION}:
            expected_names = set(CHECKSUMMED_FILENAMES) | {
                image.project_relative_path for image in project.subject_vascular_images
            }
            _require_exact_checksum_names(checksums, expected_names)
            _verify_subject_assets(
                project.subject_vascular_images,
                package=package,
                package_fd=directory_fd,
                checksums=checksums,
            )
        return project
    finally:
        os.close(directory_fd)


def _verify_encoded_checksum(filename: str, encoded: bytes, checksums: dict[Any, Any]) -> None:
    expected = checksums.get(filename)
    if not _is_sha256(expected):
        raise ProjectIntegrityError(
            f"checksums.json has an invalid SHA-256 for {filename}: {expected!r}"
        )
    actual = hashlib.sha256(encoded).hexdigest()
    if expected != actual:
        raise ProjectIntegrityError(
            f"checksum mismatch for {filename}: expected {expected!r}, got {actual}"
        )


def _require_exact_checksum_names(checksums: dict[Any, Any], expected_names: set[str]) -> None:
    if set(checksums) != expected_names:
        raise ProjectIntegrityError(
            "checksums.json must contain exactly: " + ", ".join(sorted(expected_names))
        )


def _verify_subject_assets(
    images: list[SubjectVascularImage],
    *,
    package: Path,
    package_fd: int,
    checksums: dict[Any, Any],
) -> None:
    if not images:
        return
    images_fd = _open_images_directory(package, package_fd)
    try:
        for image in images:
            actual = _hash_verified_subject_asset(
                image,
                package=package,
                images_fd=images_fd,
            )
            expected = checksums.get(image.project_relative_path)
            if not _is_sha256(expected):
                raise ProjectIntegrityError(
                    "checksums.json has an invalid SHA-256 for "
                    f"{image.project_relative_path}: {expected!r}"
                )
            if expected != actual:
                raise ProjectIntegrityError(
                    f"checksum mismatch for {image.project_relative_path}: "
                    f"expected {expected!r}, got {actual}"
                )
    finally:
        os.close(images_fd)


def _hash_verified_subject_asset(
    image: SubjectVascularImage,
    *,
    package: Path,
    images_fd: int,
) -> str:
    parts = image.project_relative_path.split("/")
    if len(parts) != 2 or parts[0] != "images":
        raise ProjectIntegrityError(
            f"invalid subject image package path: {image.project_relative_path!r}"
        )
    filename = parts[1]
    candidate = package / "images" / filename
    try:
        expected = candidate.lstat()
    except FileNotFoundError as error:
        raise ProjectIntegrityError(
            f"subject image asset does not exist: {image.project_relative_path}"
        ) from error
    if stat.S_ISLNK(expected.st_mode) or not stat.S_ISREG(expected.st_mode):
        raise ProjectIntegrityError(
            f"subject image asset must be a regular file: {image.project_relative_path}"
        )
    if expected.st_size != image.byte_size:
        raise ProjectIntegrityError(
            f"subject image size mismatch for {image.project_relative_path}: "
            f"expected {image.byte_size}, got {expected.st_size}"
        )
    if expected.st_size > MAX_PROJECT_IMAGE_BYTES:
        raise ProjectIntegrityError(
            f"subject image exceeds {MAX_PROJECT_IMAGE_BYTES} bytes: {image.project_relative_path}"
        )

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    asset_fd = os.open(filename, flags, dir_fd=images_fd)
    digest = hashlib.sha256()
    size = 0
    try:
        opened = os.fstat(asset_fd)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            expected.st_dev,
            expected.st_ino,
        ):
            raise ProjectIntegrityError(
                f"subject image changed while opening: {image.project_relative_path}"
            )
        with os.fdopen(asset_fd, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                if size > image.byte_size:
                    raise ProjectIntegrityError(
                        f"subject image grew while verifying: {image.project_relative_path}"
                    )
                digest.update(chunk)
    finally:
        os.close(asset_fd)
    actual = digest.hexdigest()
    if size != image.byte_size:
        raise ProjectIntegrityError(
            f"subject image size mismatch for {image.project_relative_path}: "
            f"expected {image.byte_size}, read {size}"
        )
    if actual != image.source_sha256:
        raise ProjectIntegrityError(
            f"subject image metadata checksum mismatch for {image.project_relative_path}: "
            f"expected {image.source_sha256}, got {actual}"
        )
    return actual


def _validated_package_root(path: Path) -> tuple[Path, os.stat_result]:
    try:
        package_stat = path.lstat()
    except FileNotFoundError as error:
        raise ProjectIntegrityError(f"project package does not exist: {path}") from error
    if stat.S_ISLNK(package_stat.st_mode):
        raise ProjectIntegrityError(f"project package must not be a symbolic link: {path}")
    if not stat.S_ISDIR(package_stat.st_mode):
        raise ProjectIntegrityError(f"project package is not a directory: {path}")
    package = path.resolve(strict=True)
    if package != path:
        raise ProjectIntegrityError(
            f"project package resolved outside its normalized location: {path} -> {package}"
        )
    return package, package_stat


def _open_package_directory(package: Path, expected: os.stat_result) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(package, flags)
    opened = os.fstat(directory_fd)
    if not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
        expected.st_dev,
        expected.st_ino,
    ):
        os.close(directory_fd)
        raise ProjectIntegrityError(f"project package changed while opening: {package}")
    return directory_fd


def _read_bounded_member(package: Path, directory_fd: int, filename: str) -> bytes:
    maximum = PROJECT_MEMBER_MAX_BYTES[filename]
    candidate = package / filename
    try:
        member_stat = candidate.lstat()
    except FileNotFoundError as error:
        raise ProjectIntegrityError(f"project member does not exist: {filename}") from error
    if stat.S_ISLNK(member_stat.st_mode):
        raise ProjectIntegrityError(f"project member must not be a symbolic link: {filename}")
    if not stat.S_ISREG(member_stat.st_mode):
        raise ProjectIntegrityError(f"project member must be a regular file: {filename}")
    resolved = candidate.resolve(strict=True)
    if resolved.parent != package or resolved.name != filename:
        raise ProjectIntegrityError(
            f"project member resolves outside its package: {filename} -> {resolved}"
        )
    if member_stat.st_size > maximum:
        raise ProjectIntegrityError(
            f"project member {filename} exceeds {maximum} bytes: {member_stat.st_size}"
        )

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    file_fd = os.open(filename, flags, dir_fd=directory_fd)
    try:
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ProjectIntegrityError(f"project member must be a regular file: {filename}")
        if (opened.st_dev, opened.st_ino) != (member_stat.st_dev, member_stat.st_ino):
            raise ProjectIntegrityError(f"project member changed while opening: {filename}")
        if opened.st_size > maximum:
            raise ProjectIntegrityError(
                f"project member {filename} exceeds {maximum} bytes: {opened.st_size}"
            )
        with os.fdopen(file_fd, "rb", closefd=False) as stream:
            encoded = stream.read(maximum + 1)
    finally:
        os.close(file_fd)
    if len(encoded) > maximum:
        raise ProjectIntegrityError(f"project member {filename} exceeds {maximum} bytes")
    return encoded


def _decode_json(filename: str, encoded: bytes) -> Any:
    try:
        return json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectIntegrityError(f"invalid UTF-8 JSON in {filename}: {error}") from error


def _write_json(path: Path, payload: Any) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    encoded_size = len(encoded.encode("utf-8"))
    maximum = PROJECT_MEMBER_MAX_BYTES.get(path.name)
    if maximum is not None and encoded_size > maximum:
        raise ProjectIntegrityError(
            f"project member {path.name} exceeds {maximum} bytes: {encoded_size}"
        )
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _commit_project_directory(temporary: Path, destination: Path, backup: Path) -> None:
    if not _entry_exists(destination):
        _rename(temporary, destination)
        return

    # A symlink or non-directory could redirect or broaden later removal.
    if destination.is_symlink() or not destination.is_dir():
        raise ProjectIntegrityError(f"refusing to rotate invalid destination: {destination}")
    current_is_verified = not validate_project(destination)
    rotation_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.rotation.", dir=destination.parent)
    )
    cleanup_is_safe = False
    try:
        if current_is_verified:
            cleanup_is_safe = _replace_verified_destination(
                temporary,
                destination,
                backup,
                rotation_root,
            )
        else:
            cleanup_is_safe = _replace_invalid_destination(
                temporary,
                destination,
                rotation_root,
            )
    finally:
        rotation_is_empty = rotation_root.exists() and not any(rotation_root.iterdir())
        if (cleanup_is_safe or rotation_is_empty) and rotation_root.exists():
            shutil.rmtree(rotation_root)
            _fsync_directory(destination.parent)


def _replace_verified_destination(
    temporary: Path,
    destination: Path,
    backup: Path,
    rotation_root: Path,
) -> bool:
    preserved_backup = rotation_root / f"previous{BACKUP_SUFFIX}"
    backup_staged = False
    if _entry_exists(backup):
        if backup.is_symlink() or not backup.is_dir():
            raise ProjectIntegrityError(f"refusing to rotate invalid backup path: {backup}")
        _rename(backup, preserved_backup)
        backup_staged = True

    try:
        _rename(destination, backup)
    except Exception as rotation_error:
        if backup_staged:
            try:
                _rename(preserved_backup, backup)
            except Exception as restore_error:
                raise ProjectRecoveryError(
                    "backup rotation failed and the prior recovery copy could not be "
                    f"restored; it remains at {preserved_backup}: {restore_error}"
                ) from rotation_error
        raise

    try:
        _rename(temporary, destination)
    except Exception as install_error:
        rollback_errors: list[str] = []
        try:
            _rename(backup, destination)
        except Exception as error:
            rollback_errors.append(f"current project remains at {backup}: {error}")
        if backup_staged:
            if _entry_exists(backup):
                rollback_errors.append(f"prior backup remains at {preserved_backup}")
            else:
                try:
                    _rename(preserved_backup, backup)
                except Exception as error:
                    rollback_errors.append(f"prior backup remains at {preserved_backup}: {error}")
        if rollback_errors:
            raise ProjectRecoveryError(
                "project replacement failed and rollback was incomplete; "
                + "; ".join(rollback_errors)
            ) from install_error
        raise
    return True


def _replace_invalid_destination(
    temporary: Path,
    destination: Path,
    rotation_root: Path,
) -> bool:
    displaced = rotation_root / f"invalid{PROJECT_SUFFIX}"
    _rename(destination, displaced)
    try:
        _rename(temporary, destination)
    except Exception as install_error:
        try:
            _rename(displaced, destination)
        except Exception as restore_error:
            raise ProjectRecoveryError(
                "project replacement failed and the displaced package could not be "
                f"restored; it remains at {displaced}: {restore_error}"
            ) from install_error
        raise
    return True


def _rename(source: Path, destination: Path) -> None:
    """Rename one exact path and durably record both directory entries."""

    source_parent = source.parent
    destination_parent = destination.parent
    source.replace(destination)
    _fsync_directory(destination_parent)
    if source_parent != destination_parent:
        _fsync_directory(source_parent)


def _fsync_directory(path: Path) -> None:
    """Persist directory entries where the host filesystem supports it."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    except OSError as error:
        if error.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF}:
            raise
    finally:
        os.close(descriptor)


def _backup_path(destination: Path) -> Path:
    return destination.with_name(destination.name + ".bak")


def _is_backup_path(path: Path) -> bool:
    return path.name.endswith(BACKUP_SUFFIX)


def _entry_exists(path: Path) -> bool:
    return os.path.lexists(path)
