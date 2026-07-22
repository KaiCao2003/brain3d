"""Exact disk-backed sagittal layout for the reviewed 10 µm Allen atlas.

BrainGlobe volumes are authoritative C-order ``[AP, DV, ML]`` arrays. Reading
one fixed-ML plane from a disk-backed 10 µm volume otherwise faults pages across
the entire multi-gigabyte file. This module derives an exact ``[ML, DV, AP]``
layout once, using bounded tiles, so a displayed sagittal plane is contiguous.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import math
import os
import shutil
import stat
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import tifffile
from numpy.lib.format import open_memmap
from numpy.typing import NDArray

from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.paths import app_paths

SAGITTAL_CACHE_STAGE_TEXT = "Preparing exact sagittal display cache…"
SAGITTAL_CACHE_FINALIZE_STAGE_TEXT = "Finalizing exact sagittal display cache…"
SAGITTAL_CACHE_FORMAT_VERSION = 1
SAGITTAL_CACHE_DIRECTORY = "sagittal-volumes-v1"
SAGITTAL_CACHE_BYTES_10UM = 7_223_040_000
SAGITTAL_CACHE_MAX_ARTIFACT_BYTES = 8 * 1024**3

_REVIEWED_ATLAS_KEY = "allen_mouse_10um"
_REVIEWED_PACKAGE_VERSION = "1.2"
_REVIEWED_SHAPE = (1320, 800, 1140)
_REVIEWED_RESOLUTION_UM = (10.0, 10.0, 10.0)
_REFERENCE_FILENAME = "reference-ml-dv-ap.npy"
_ANNOTATION_FILENAME = "annotation-ml-dv-ap.npy"
_MANIFEST_FILENAME = "manifest.json"
_MANIFEST_MAX_BYTES = 64 * 1024
_TILE_EDGE = 64
_DISK_SAFETY_BYTES = 256 * 1024**2

type ProgressCallback = Callable[[int, int], None]
type CancellationCheck = Callable[[], bool]
type StageCallback = Callable[[str], None]


class SagittalCacheError(RuntimeError):
    """Raised when an exact derived cache cannot be safely prepared or opened."""


class SagittalCacheCancelledError(SagittalCacheError):
    """Raised when cache construction is cancelled before atomic promotion."""


@dataclass(frozen=True, slots=True)
class SagittalVolumeCache:
    """Read-only exact sagittal arrays in displayed ``[ML, DV, AP]`` order."""

    reference: NDArray[np.generic]
    annotation: NDArray[np.generic]
    path: Path
    cache_key: str


@dataclass(frozen=True, slots=True)
class _SourceFile:
    name: str
    path: Path
    size: int
    mtime_ns: int
    device: int
    inode: int

    def manifest_value(self) -> dict[str, int | str]:
        return {
            "name": self.name,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
        }


def reviewed_10um_requires_sagittal_cache(metadata: AtlasMetadata) -> bool:
    """Return whether metadata is the one reviewed contract eligible for derivation."""

    return (
        metadata.atlas_key == _REVIEWED_ATLAS_KEY
        and metadata.atlas_package_version == _REVIEWED_PACKAGE_VERSION
        and metadata.shape_voxels == _REVIEWED_SHAPE
        and metadata.resolution_um == _REVIEWED_RESOLUTION_UM
    )


def default_sagittal_cache_root() -> Path:
    """Return the application-owned derived-cache root."""

    return app_paths().cache / SAGITTAL_CACHE_DIRECTORY


def prepare_sagittal_cache(
    metadata: AtlasMetadata,
    reference: NDArray[Any],
    annotation: NDArray[Any],
    *,
    cache_root: Path | None = None,
    progress: ProgressCallback | None = None,
    cancel: CancellationCheck | None = None,
    stage: StageCallback | None = None,
) -> SagittalVolumeCache:
    """Open or atomically build one exact source-bound sagittal cache.

    The caller owns policy about which atlas is eligible. Production invokes
    this only for :func:`reviewed_10um_requires_sagittal_cache`; keeping the
    storage primitive shape-generic permits small deterministic tests.
    """

    _raise_if_cancelled(cancel)
    reference_values = np.asarray(reference)
    annotation_values = np.asarray(annotation)
    _validate_source_arrays(metadata, reference_values, annotation_values)
    sources = _validated_source_files(metadata, reference_values, annotation_values)
    manifest = _expected_manifest(metadata, reference_values, annotation_values, sources)

    root = _validated_cache_root(cache_root or default_sagittal_cache_root())
    target_name = _target_name(metadata)
    final = root / target_name
    with _exclusive_cache_lock(root, target_name, cancel):
        _raise_if_cancelled(cancel)
        existing = _try_open_cache(final, manifest)
        if existing is not None:
            return existing

        _remove_stale_transients(root, target_name)
        required_bytes = _derived_raw_bytes(reference_values, annotation_values)
        if required_bytes > SAGITTAL_CACHE_MAX_ARTIFACT_BYTES:
            raise SagittalCacheError(
                f"exact sagittal cache would exceed its 8 GiB safety bound: {required_bytes} bytes"
            )
        free_bytes = shutil.disk_usage(root).free
        minimum_free = required_bytes + _DISK_SAFETY_BYTES
        if free_bytes < minimum_free:
            raise SagittalCacheError(
                "insufficient free disk for the exact sagittal display cache: "
                f"need at least {minimum_free} bytes including safety margin, "
                f"available {free_bytes} bytes"
            )

        staging = Path(tempfile.mkdtemp(prefix=f".{target_name}.stage.", dir=root))
        try:
            _build_cache(
                staging,
                reference_values,
                annotation_values,
                progress=progress,
                cancel=cancel,
            )
            if _validated_source_files(metadata, reference_values, annotation_values) != sources:
                raise SagittalCacheError("source TIFF changed while sagittal cache was built")
            if stage is not None:
                stage(SAGITTAL_CACHE_FINALIZE_STAGE_TEXT)
            _write_manifest(staging / _MANIFEST_FILENAME, manifest)
            _fsync_directory(staging)
            staged = _open_cache(staging, manifest)
            del staged
            _raise_if_cancelled(cancel)
            _promote_cache(staging, final)
            return _open_cache(final, manifest)
        finally:
            if _entry_exists(staging):
                _remove_entry(staging)
                _fsync_directory(root)


def _validate_source_arrays(
    metadata: AtlasMetadata,
    reference: NDArray[Any],
    annotation: NDArray[Any],
) -> None:
    expected_shape = metadata.shape_voxels
    if reference.shape != expected_shape or annotation.shape != expected_shape:
        raise SagittalCacheError(
            "source arrays must match atlas [AP,DV,ML] shape: "
            f"expected {expected_shape}, reference {reference.shape}, "
            f"annotation {annotation.shape}"
        )
    if reference.ndim != 3 or annotation.ndim != 3:
        raise SagittalCacheError("source arrays must be three-dimensional [AP,DV,ML]")
    if not np.issubdtype(annotation.dtype, np.integer):
        raise SagittalCacheError("annotation source must have an integer dtype")


def _validated_source_files(
    metadata: AtlasMetadata,
    reference: NDArray[Any],
    annotation: NDArray[Any],
) -> tuple[_SourceFile, _SourceFile]:
    raw_root = Path(metadata.cache_path).expanduser()
    try:
        root_stat = raw_root.lstat()
    except FileNotFoundError as error:
        raise SagittalCacheError(f"atlas cache directory does not exist: {raw_root}") from error
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise SagittalCacheError(f"atlas cache must be a non-symlink directory: {raw_root}")
    root = raw_root.resolve(strict=True)
    reference_source = _validated_source_file(root, "reference.tiff", reference)
    annotation_source = _validated_source_file(root, "annotation.tiff", annotation)
    return (reference_source, annotation_source)


def _validated_source_file(
    root: Path,
    filename: str,
    expected_array: NDArray[Any],
) -> _SourceFile:
    path = root / filename
    try:
        source_stat = path.lstat()
    except FileNotFoundError as error:
        raise SagittalCacheError(f"source TIFF does not exist: {path}") from error
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        raise SagittalCacheError(f"source TIFF must be a regular non-symlink file: {path}")
    if source_stat.st_size <= 0:
        raise SagittalCacheError(f"source TIFF is empty: {path}")
    resolved = path.resolve(strict=True)
    if resolved.parent != root or resolved.name != filename:
        raise SagittalCacheError(f"source TIFF resolves outside the atlas cache: {path}")
    try:
        with tifffile.TiffFile(resolved) as tiff:
            if len(tiff.series) != 1:
                raise SagittalCacheError(f"source TIFF must contain one series: {path}")
            series = tiff.series[0]
            source_shape = tuple(int(value) for value in series.shape)
            source_dtype = np.dtype(series.dtype)
    except tifffile.TiffFileError as error:
        raise SagittalCacheError(f"source TIFF is invalid: {path}") from error
    if source_shape != expected_array.shape or source_dtype != expected_array.dtype:
        raise SagittalCacheError(
            f"source TIFF contract changed for {filename}: "
            f"header {source_shape}/{source_dtype}, array "
            f"{expected_array.shape}/{expected_array.dtype}"
        )
    return _SourceFile(
        name=filename,
        path=resolved,
        size=source_stat.st_size,
        mtime_ns=source_stat.st_mtime_ns,
        device=source_stat.st_dev,
        inode=source_stat.st_ino,
    )


def _expected_manifest(
    metadata: AtlasMetadata,
    reference: NDArray[Any],
    annotation: NDArray[Any],
    sources: tuple[_SourceFile, _SourceFile],
) -> dict[str, object]:
    ap, dv, ml = metadata.shape_voxels
    identity: dict[str, object] = {
        "format_version": SAGITTAL_CACHE_FORMAT_VERSION,
        "atlas_key": metadata.atlas_key,
        "atlas_package_version": metadata.atlas_package_version,
        "metadata_sha256": metadata.metadata_sha256,
        "shape_asr": [ap, dv, ml],
        "resolution_um_asr": list(metadata.resolution_um),
        "source": [source.manifest_value() for source in sources],
        "reference_dtype": reference.dtype.str,
        "annotation_dtype": annotation.dtype.str,
        "output_shape_ml_dv_ap": [ml, dv, ap],
        "reference_output_bytes": int(reference.size * reference.dtype.itemsize),
        "annotation_output_bytes": int(annotation.size * annotation.dtype.itemsize),
        "total_output_bytes": _derived_raw_bytes(reference, annotation),
        "reference_file": _REFERENCE_FILENAME,
        "annotation_file": _ANNOTATION_FILENAME,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity["cache_key"] = hashlib.sha256(encoded).hexdigest()
    return identity


def _target_name(metadata: AtlasMetadata) -> str:
    identity = f"{metadata.atlas_key}\0{metadata.atlas_package_version}".encode()
    return f"atlas-{hashlib.sha256(identity).hexdigest()[:24]}"


def _validated_cache_root(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    root_stat = path.lstat()
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise SagittalCacheError(f"derived cache root must be a non-symlink directory: {path}")
    return path.resolve(strict=True)


@contextmanager
def _exclusive_cache_lock(
    root: Path,
    target_name: str,
    cancel: CancellationCheck | None,
) -> Iterator[None]:
    lock_path = root / f".{target_name}.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                _raise_if_cancelled(cancel)
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _build_cache(
    staging: Path,
    reference: NDArray[Any],
    annotation: NDArray[Any],
    *,
    progress: ProgressCallback | None,
    cancel: CancellationCheck | None,
) -> None:
    ap, dv, ml = (int(value) for value in reference.shape)
    output_shape = (ml, dv, ap)
    total_tiles = 2 * math.prod(math.ceil(size / _TILE_EDGE) for size in (ap, dv, ml))
    completed = 0
    if progress is not None:
        progress(0, total_tiles)

    for source, filename in (
        (reference, _REFERENCE_FILENAME),
        (annotation, _ANNOTATION_FILENAME),
    ):
        destination = open_memmap(
            staging / filename,
            mode="w+",
            dtype=source.dtype,
            shape=output_shape,
        )
        try:
            for ml_start in range(0, ml, _TILE_EDGE):
                ml_stop = min(ml_start + _TILE_EDGE, ml)
                for dv_start in range(0, dv, _TILE_EDGE):
                    dv_stop = min(dv_start + _TILE_EDGE, dv)
                    for ap_start in range(0, ap, _TILE_EDGE):
                        _raise_if_cancelled(cancel)
                        ap_stop = min(ap_start + _TILE_EDGE, ap)
                        tile = np.ascontiguousarray(
                            source[
                                ap_start:ap_stop,
                                dv_start:dv_stop,
                                ml_start:ml_stop,
                            ]
                        )
                        destination[
                            ml_start:ml_stop,
                            dv_start:dv_stop,
                            ap_start:ap_stop,
                        ] = tile.transpose(2, 1, 0)
                        completed += 1
                        if progress is not None and (
                            completed % 32 == 0 or completed == total_tiles
                        ):
                            progress(completed, total_tiles)
            destination.flush()
        finally:
            del destination
        _fsync_file(staging / filename)
    _raise_if_cancelled(cancel)


def _derived_raw_bytes(reference: NDArray[Any], annotation: NDArray[Any]) -> int:
    return int(
        reference.size * reference.dtype.itemsize + annotation.size * annotation.dtype.itemsize
    )


def _write_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > _MANIFEST_MAX_BYTES:
        raise SagittalCacheError("sagittal cache manifest exceeds its 64 KiB bound")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _try_open_cache(
    path: Path,
    expected_manifest: Mapping[str, object],
) -> SagittalVolumeCache | None:
    if not _entry_exists(path):
        return None
    try:
        return _open_cache(path, expected_manifest)
    except (OSError, SagittalCacheError, ValueError):
        return None


def _open_cache(
    path: Path,
    expected_manifest: Mapping[str, object],
) -> SagittalVolumeCache:
    directory_stat = path.lstat()
    if stat.S_ISLNK(directory_stat.st_mode) or not stat.S_ISDIR(directory_stat.st_mode):
        raise SagittalCacheError(f"sagittal cache is not a regular directory: {path}")
    directory = path.resolve(strict=True)
    manifest = _read_manifest(directory / _MANIFEST_FILENAME, directory)
    if manifest != dict(expected_manifest):
        raise SagittalCacheError("sagittal cache manifest does not match the exact source atlas")
    shape_value = expected_manifest["output_shape_ml_dv_ap"]
    if not isinstance(shape_value, list) or len(shape_value) != 3:
        raise SagittalCacheError("invalid expected sagittal output shape")
    shape = cast(tuple[int, int, int], tuple(int(value) for value in shape_value))
    reference_bytes = (
        math.prod(shape) * np.dtype(cast(str, expected_manifest["reference_dtype"])).itemsize
    )
    annotation_bytes = (
        math.prod(shape) * np.dtype(cast(str, expected_manifest["annotation_dtype"])).itemsize
    )
    if (
        expected_manifest.get("reference_output_bytes") != reference_bytes
        or expected_manifest.get("annotation_output_bytes") != annotation_bytes
        or expected_manifest.get("total_output_bytes") != reference_bytes + annotation_bytes
    ):
        raise SagittalCacheError("sagittal cache manifest output byte contract is invalid")
    reference = _open_read_only_npy(
        directory / _REFERENCE_FILENAME,
        directory,
        shape=shape,
        dtype=np.dtype(cast(str, expected_manifest["reference_dtype"])),
    )
    annotation = _open_read_only_npy(
        directory / _ANNOTATION_FILENAME,
        directory,
        shape=shape,
        dtype=np.dtype(cast(str, expected_manifest["annotation_dtype"])),
    )
    return SagittalVolumeCache(
        reference=reference,
        annotation=annotation,
        path=directory,
        cache_key=cast(str, expected_manifest["cache_key"]),
    )


def _read_manifest(path: Path, root: Path) -> object:
    member_stat = path.lstat()
    if stat.S_ISLNK(member_stat.st_mode) or not stat.S_ISREG(member_stat.st_mode):
        raise SagittalCacheError("sagittal cache manifest must be a regular file")
    if path.resolve(strict=True).parent != root:
        raise SagittalCacheError("sagittal cache manifest resolves outside its directory")
    if member_stat.st_size > _MANIFEST_MAX_BYTES:
        raise SagittalCacheError("sagittal cache manifest exceeds its 64 KiB bound")
    with path.open("rb") as stream:
        encoded = stream.read(_MANIFEST_MAX_BYTES + 1)
    if len(encoded) > _MANIFEST_MAX_BYTES:
        raise SagittalCacheError("sagittal cache manifest exceeds its 64 KiB bound")
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SagittalCacheError("sagittal cache manifest is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise SagittalCacheError("sagittal cache manifest must be an object")
    return value


def _open_read_only_npy(
    path: Path,
    root: Path,
    *,
    shape: tuple[int, int, int],
    dtype: np.dtype[np.generic],
) -> NDArray[np.generic]:
    member_stat = path.lstat()
    if stat.S_ISLNK(member_stat.st_mode) or not stat.S_ISREG(member_stat.st_mode):
        raise SagittalCacheError(f"sagittal array must be a regular file: {path.name}")
    if path.resolve(strict=True).parent != root:
        raise SagittalCacheError(f"sagittal array resolves outside its cache: {path.name}")
    array = open_memmap(path, mode="r")
    if array.mode != "r" or array.flags.writeable:
        raise SagittalCacheError(f"sagittal array was not opened read-only: {path.name}")
    if array.shape != shape or array.dtype != dtype:
        raise SagittalCacheError(
            f"sagittal array contract mismatch for {path.name}: "
            f"expected {shape}/{dtype}, got {array.shape}/{array.dtype}"
        )
    expected_file_size = int(array.offset + array.nbytes)
    if member_stat.st_size != expected_file_size:
        raise SagittalCacheError(
            f"sagittal array has the wrong exact size for {path.name}: "
            f"expected {expected_file_size}, got {member_stat.st_size}"
        )
    return cast(NDArray[np.generic], array)


def _promote_cache(staging: Path, final: Path) -> None:
    root = final.parent
    displaced: Path | None = None
    if _entry_exists(final):
        displaced = root / f".{final.name}.old.{time.time_ns()}"
        final.replace(displaced)
        _fsync_directory(root)
    try:
        staging.replace(final)
        _fsync_directory(root)
    except Exception as install_error:
        if displaced is not None and _entry_exists(displaced):
            try:
                displaced.replace(final)
                _fsync_directory(root)
            except Exception as restore_error:
                raise SagittalCacheError(
                    f"cache promotion failed and prior cache remains at {displaced}: "
                    f"{restore_error}"
                ) from install_error
        raise
    if displaced is not None and _entry_exists(displaced):
        _remove_entry(displaced)
        _fsync_directory(root)


def _remove_stale_transients(root: Path, target_name: str) -> None:
    prefixes = (f".{target_name}.stage.", f".{target_name}.old.")
    for candidate in root.iterdir():
        if candidate.name.startswith(prefixes):
            _remove_entry(candidate)
    _fsync_directory(root)


def _remove_entry(path: Path) -> None:
    entry_stat = path.lstat()
    if stat.S_ISDIR(entry_stat.st_mode) and not stat.S_ISLNK(entry_stat.st_mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    except OSError as error:
        if error.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF}:
            raise
    finally:
        os.close(descriptor)


def _raise_if_cancelled(cancel: CancellationCheck | None) -> None:
    if cancel is not None and cancel():
        raise SagittalCacheCancelledError("exact sagittal cache preparation cancelled")


def _entry_exists(path: Path) -> bool:
    return os.path.lexists(path)
