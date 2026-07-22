"""Verified acquisition and disk cache for the pinned population density.

Only one reviewed Mendeley archive is accepted.  The outer archive and both
scientific members have hard-pinned byte counts and SHA-256 identities.  The
archive is never generically unpacked: ``bsdtar`` streams only the two exact
member names into an application-owned temporary generation, which becomes
visible atomically after both members pass their pinned hashes.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Final, Protocol, cast
from uuid import uuid4

import nibabel as nib
import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.paths import app_paths
from mouse_brain_planner.vasculature.density_overlay import ReferenceDensityAtlasBinding
from mouse_brain_planner.vasculature.reference_density import (
    BRAINGLOBE_ASR_FRAME_AP_DV_ML,
    DEFAULT_MINIMUM_TEMPLATE_CORRELATION,
    DEFAULT_REFERENCE_DENSITY_RESOLUTION_UM,
    STXVN5SV44_V1_SOURCE,
    NiftiHeaderEvidence,
    ReferenceDensityProvenance,
    ReferenceVascularDensity,
    TemplateAlignmentEvidence,
    prepare_reference_vascular_density,
    validate_source_nifti_header,
)

PINNED_REFERENCE_DOWNLOAD_URL: Final = (
    "https://data.mendeley.com/public-files/datasets/stxvn5sv44/files/"
    "10accc6f-e41f-4c0f-b6d5-9ca2af9db74a/file_downloaded"
)
PINNED_DENSITY_MEMBER_SIZE_BYTES: Final = 601_920_352
PINNED_DENSITY_MEMBER_SHA256: Final = (
    "0a0cbdf62068783259a7f11f1e6f2992c57ff1678d0481c2ea36d64899ed4484"
)
PINNED_TEMPLATE_MEMBER_SIZE_BYTES: Final = 300_960_352
PINNED_TEMPLATE_MEMBER_SHA256: Final = (
    "3d3004f0de9410f6cadfd93ac08d78aaf4a2c504fd2c07275bd5064b6b0a7e0a"
)
REFERENCE_PREPARATION_ALGORITHM: Final = "stxvn5sv44-v1-asr-50um-linear-ml-sym-v1"
PREPARED_CACHE_SCHEMA_VERSION: Final = 1
MAX_MANIFEST_BYTES: Final = 128 * 1024
MAX_PREPARED_DENSITY_FILE_BYTES: Final = 64 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS: Final = 60.0
SUPPORTED_REFERENCE_ATLAS_IDENTIFIER: Final = "allen_mouse_25um"
SUPPORTED_REFERENCE_ATLAS_VERSION: Final = "1.2"


class ReferenceDensityCacheError(ValueError):
    """Raised when source or derived density bytes fail a trust boundary."""


@dataclass(frozen=True, slots=True)
class PinnedArchiveMember:
    """Exact identity of one permitted regular archive member."""

    member_path: str
    cached_filename: str
    size_bytes: int
    sha256: str
    kind: str


PINNED_DENSITY_MEMBER = PinnedArchiveMember(
    member_path=STXVN5SV44_V1_SOURCE.density_member_path,
    cached_filename="density.nii",
    size_bytes=PINNED_DENSITY_MEMBER_SIZE_BYTES,
    sha256=PINNED_DENSITY_MEMBER_SHA256,
    kind="density",
)
PINNED_TEMPLATE_MEMBER = PinnedArchiveMember(
    member_path=STXVN5SV44_V1_SOURCE.template_member_path,
    cached_filename="template.nii",
    size_bytes=PINNED_TEMPLATE_MEMBER_SIZE_BYTES,
    sha256=PINNED_TEMPLATE_MEMBER_SHA256,
    kind="template",
)
PINNED_ARCHIVE_MEMBERS: Final = (PINNED_DENSITY_MEMBER, PINNED_TEMPLATE_MEMBER)


@dataclass(frozen=True, slots=True, eq=False)
class CachedReferenceDensity:
    """One immutable prepared array with its verified cache evidence."""

    density: ReferenceVascularDensity
    prepared_density_sha256: str
    atlas_metadata_sha256: str
    atlas_reference_sha256: str
    archive_sha256_verified: bool
    reused_prepared_cache: bool


class ReferenceDensityStoreProtocol(Protocol):
    """Bridge-facing service surface, injectable for bounded tests."""

    def prepare(
        self,
        *,
        atlas: AtlasMetadata,
        atlas_reference_asr: NDArray[np.generic],
        archive_path: Path | None,
        download_if_missing: bool,
    ) -> CachedReferenceDensity: ...

    def load_cached(
        self,
        *,
        atlas: AtlasMetadata,
        atlas_reference_asr: NDArray[np.generic],
    ) -> CachedReferenceDensity | None: ...


class ReferenceDensityStore:
    """Application-owned store for the only approved population source."""

    def __init__(
        self,
        cache_root: str | Path | None = None,
        *,
        bsdtar_path: str | Path = "/usr/bin/bsdtar",
    ) -> None:
        root = (
            Path(cache_root).expanduser()
            if cache_root is not None
            else app_paths().cache / "vascular-reference" / "stxvn5sv44-v1"
        )
        self._cache_root = root
        self._bsdtar_path = Path(bsdtar_path)

    def prepare(
        self,
        *,
        atlas: AtlasMetadata,
        atlas_reference_asr: NDArray[np.generic],
        archive_path: Path | None,
        download_if_missing: bool,
    ) -> CachedReferenceDensity:
        """Acquire, validate, prepare, and atomically cache the 50 µm field."""

        _validate_supported_atlas(atlas, atlas_reference_asr)
        with self._locked_cache():
            archive = self._acquire_archive(
                archive_path=archive_path,
                download_if_missing=download_if_missing,
            )
            _verify_regular_file(
                archive,
                expected_size=STXVN5SV44_V1_SOURCE.archive_size_bytes,
                expected_sha256=STXVN5SV44_V1_SOURCE.archive_sha256,
                label="pinned vascular archive",
            )
            try:
                cached = self._load_prepared_locked(
                    atlas=atlas,
                    atlas_reference_asr=atlas_reference_asr,
                )
            except ReferenceDensityCacheError:
                self._quarantine_directory(self._prepared_directory(atlas))
                cached = None
            if cached is not None:
                return cached

            members = self._extract_members(archive)
            density_values = _load_pinned_nifti(
                members[PINNED_DENSITY_MEMBER.kind],
                member=PINNED_DENSITY_MEMBER,
            )
            template_values = _load_pinned_nifti(
                members[PINNED_TEMPLATE_MEMBER.kind],
                member=PINNED_TEMPLATE_MEMBER,
            )
            reference_before = _hash_array_c_order(atlas_reference_asr)
            try:
                prepared = prepare_reference_vascular_density(
                    density_values,
                    density_header=STXVN5SV44_V1_SOURCE.density_header,
                    source_template_mldvpa=template_values,
                    template_header=STXVN5SV44_V1_SOURCE.template_header,
                    target_atlas_reference_asr=atlas_reference_asr,
                    target_atlas_voxel_size_um=atlas.resolution_um[0],
                    output_voxel_size_um=DEFAULT_REFERENCE_DENSITY_RESOLUTION_UM,
                    minimum_template_correlation=DEFAULT_MINIMUM_TEMPLATE_CORRELATION,
                )
            except (TypeError, ValueError, MemoryError) as error:
                raise ReferenceDensityCacheError(
                    "the pinned vascular density could not be prepared against the loaded atlas"
                ) from error
            reference_after = _hash_array_c_order(atlas_reference_asr)
            if reference_after != reference_before:
                raise ReferenceDensityCacheError(
                    "the loaded atlas reference changed during density preparation"
                )
            ReferenceDensityAtlasBinding(
                density=prepared,
                atlas_shape_asr=atlas.shape_voxels,
                atlas_resolution_um=atlas.resolution_um,
            )
            self._write_prepared_cache(
                prepared,
                atlas=atlas,
                atlas_reference_sha256=reference_before,
            )
            loaded = self._load_prepared_locked(
                atlas=atlas,
                atlas_reference_asr=atlas_reference_asr,
            )
            if loaded is None:  # pragma: no cover - guarded by the atomic writer
                raise ReferenceDensityCacheError("prepared density cache was not installed")
            return replace(loaded, reused_prepared_cache=False)

    def load_cached(
        self,
        *,
        atlas: AtlasMetadata,
        atlas_reference_asr: NDArray[np.generic],
    ) -> CachedReferenceDensity | None:
        """Load a cache only while its pinned source archive remains verified."""

        _validate_supported_atlas(atlas, atlas_reference_asr)
        with self._locked_cache():
            archive = self._archive_path
            if not os.path.lexists(archive):
                return None
            _verify_regular_file(
                archive,
                expected_size=STXVN5SV44_V1_SOURCE.archive_size_bytes,
                expected_sha256=STXVN5SV44_V1_SOURCE.archive_sha256,
                label="cached pinned vascular archive",
            )
            return self._load_prepared_locked(
                atlas=atlas,
                atlas_reference_asr=atlas_reference_asr,
            )

    @property
    def _archive_path(self) -> Path:
        return self._cache_root / "source" / STXVN5SV44_V1_SOURCE.archive_filename

    def _prepared_directory(self, atlas: AtlasMetadata) -> Path:
        safe_identity = f"{atlas.atlas_key}_v{atlas.atlas_package_version}"
        return self._cache_root / "prepared" / f"{safe_identity}_{atlas.metadata_sha256}"

    @contextlib.contextmanager
    def _locked_cache(self) -> Iterator[None]:
        _ensure_private_directory(self._cache_root)
        lock_path = self._cache_root / ".lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _acquire_archive(
        self,
        *,
        archive_path: Path | None,
        download_if_missing: bool,
    ) -> Path:
        source_directory = self._archive_path.parent
        _ensure_private_directory(source_directory)
        if archive_path is not None:
            explicit = archive_path.expanduser()
            _verify_regular_file(
                explicit,
                expected_size=STXVN5SV44_V1_SOURCE.archive_size_bytes,
                expected_sha256=STXVN5SV44_V1_SOURCE.archive_sha256,
                label="selected vascular archive",
            )
            if _same_file_if_present(explicit, self._archive_path):
                return self._archive_path
            _copy_verified_file(
                explicit,
                self._archive_path,
                expected_size=STXVN5SV44_V1_SOURCE.archive_size_bytes,
                expected_sha256=STXVN5SV44_V1_SOURCE.archive_sha256,
            )
            return self._archive_path

        if os.path.lexists(self._archive_path):
            try:
                _verify_regular_file(
                    self._archive_path,
                    expected_size=STXVN5SV44_V1_SOURCE.archive_size_bytes,
                    expected_sha256=STXVN5SV44_V1_SOURCE.archive_sha256,
                    label="cached pinned vascular archive",
                )
                return self._archive_path
            except ReferenceDensityCacheError:
                if not download_if_missing:
                    raise

        if not download_if_missing:
            raise ReferenceDensityCacheError(
                "the pinned vascular archive is not cached; provide archivePath or set "
                "downloadIfMissing true"
            )
        _download_verified_archive(self._archive_path)
        return self._archive_path

    def _extract_members(self, archive: Path) -> dict[str, Path]:
        destination = self._cache_root / "members" / STXVN5SV44_V1_SOURCE.archive_sha256
        if os.path.lexists(destination):
            try:
                return _verified_member_paths(destination)
            except ReferenceDensityCacheError:
                self._quarantine_directory(destination)

        _ensure_private_directory(destination.parent)
        generation = Path(tempfile.mkdtemp(prefix=".members.", dir=destination.parent))
        try:
            for member in PINNED_ARCHIVE_MEMBERS:
                _stream_archive_member(
                    bsdtar_path=self._bsdtar_path,
                    archive=archive,
                    member=member,
                    destination=generation / member.cached_filename,
                )
            _fsync_directory(generation)
            generation.replace(destination)
            _fsync_directory(destination.parent)
        except Exception:
            if generation.exists():
                shutil.rmtree(generation)
            raise
        return _verified_member_paths(destination)

    def _write_prepared_cache(
        self,
        density: ReferenceVascularDensity,
        *,
        atlas: AtlasMetadata,
        atlas_reference_sha256: str,
    ) -> None:
        destination = self._prepared_directory(atlas)
        _ensure_private_directory(destination.parent)
        generation = Path(tempfile.mkdtemp(prefix=".prepared.", dir=destination.parent))
        try:
            array_path = generation / "density-50um.npy"
            np.save(array_path, density.values_asr, allow_pickle=False)
            _fsync_file(array_path)
            array_size = array_path.stat().st_size
            if array_size <= 0 or array_size > MAX_PREPARED_DENSITY_FILE_BYTES:
                raise ReferenceDensityCacheError(
                    f"prepared density cache size is outside its bound: {array_size}"
                )
            array_sha256 = _sha256_path(array_path)
            provenance = density.provenance
            manifest = {
                "schemaVersion": PREPARED_CACHE_SCHEMA_VERSION,
                "algorithm": REFERENCE_PREPARATION_ALGORITHM,
                "source": _source_manifest(),
                "atlas": {
                    "identifier": atlas.atlas_key,
                    "version": atlas.atlas_package_version,
                    "metadataSha256": atlas.metadata_sha256,
                    "referenceSha256": atlas_reference_sha256,
                    "shapeASR": list(atlas.shape_voxels),
                    "resolutionMicrometres": list(atlas.resolution_um),
                    "orientation": atlas.standardized_orientation,
                },
                "preparation": {
                    "outputFrame": list(provenance.output_frame),
                    "outputShapeASR": list(provenance.output_shape_asr),
                    "outputVoxelSizeMicrometres": provenance.output_voxel_size_um,
                    "outputExtentMicrometresASR": list(provenance.output_extent_um_asr),
                    "templateCorrelation": provenance.template_alignment.correlation,
                    "minimumTemplateCorrelation": (
                        provenance.template_alignment.minimum_correlation
                    ),
                    "apAxisReversed": provenance.ap_axis_reversed,
                    "mlSymmetrized": provenance.ml_symmetrized,
                    "mlSymmetrizationReason": provenance.ml_symmetrization_reason,
                    "resamplingMethod": provenance.resampling_method,
                },
                "densityFile": {
                    "filename": array_path.name,
                    "sizeBytes": array_size,
                    "sha256": array_sha256,
                    "dtype": "float32",
                },
            }
            _write_json_fsync(generation / "manifest.json", manifest)
            _fsync_directory(generation)
            if os.path.lexists(destination):
                self._quarantine_directory(destination)
            generation.replace(destination)
            _fsync_directory(destination.parent)
        except Exception:
            if generation.exists():
                shutil.rmtree(generation)
            raise

    def _load_prepared_locked(
        self,
        *,
        atlas: AtlasMetadata,
        atlas_reference_asr: NDArray[np.generic],
    ) -> CachedReferenceDensity | None:
        directory = self._prepared_directory(atlas)
        if not os.path.lexists(directory):
            return None
        if directory.is_symlink() or not directory.is_dir():
            raise ReferenceDensityCacheError("prepared density cache must be a real directory")
        manifest = _read_manifest(directory / "manifest.json")
        _validate_manifest_source(manifest)
        atlas_payload = _mapping_field(manifest, "atlas")
        reference_sha256 = _hash_array_c_order(atlas_reference_asr)
        expected_atlas = {
            "identifier": atlas.atlas_key,
            "version": atlas.atlas_package_version,
            "metadataSha256": atlas.metadata_sha256,
            "referenceSha256": reference_sha256,
            "shapeASR": list(atlas.shape_voxels),
            "resolutionMicrometres": list(atlas.resolution_um),
            "orientation": atlas.standardized_orientation,
        }
        if atlas_payload != expected_atlas:
            raise ReferenceDensityCacheError(
                "prepared density cache is not bound to the exact loaded atlas"
            )
        if manifest.get("schemaVersion") != PREPARED_CACHE_SCHEMA_VERSION:
            raise ReferenceDensityCacheError("prepared density cache schema is unsupported")
        if manifest.get("algorithm") != REFERENCE_PREPARATION_ALGORITHM:
            raise ReferenceDensityCacheError("prepared density algorithm identity changed")

        preparation = _mapping_field(manifest, "preparation")
        expected_keys = {
            "outputFrame",
            "outputShapeASR",
            "outputVoxelSizeMicrometres",
            "outputExtentMicrometresASR",
            "templateCorrelation",
            "minimumTemplateCorrelation",
            "apAxisReversed",
            "mlSymmetrized",
            "mlSymmetrizationReason",
            "resamplingMethod",
        }
        if set(preparation) != expected_keys:
            raise ReferenceDensityCacheError("prepared density provenance fields changed")
        output_shape = _integer_triplet(preparation["outputShapeASR"], "outputShapeASR")
        output_frame = tuple(_string_list(preparation["outputFrame"], "outputFrame"))
        if output_frame != BRAINGLOBE_ASR_FRAME_AP_DV_ML:
            raise ReferenceDensityCacheError("prepared density output frame is not ASR")
        output_resolution = _finite_number(
            preparation["outputVoxelSizeMicrometres"],
            "outputVoxelSizeMicrometres",
        )
        if output_resolution != DEFAULT_REFERENCE_DENSITY_RESOLUTION_UM:
            raise ReferenceDensityCacheError("prepared density resolution is not pinned at 50 µm")
        output_extent = _number_triplet(
            preparation["outputExtentMicrometresASR"],
            "outputExtentMicrometresASR",
        )
        correlation = _finite_number(preparation["templateCorrelation"], "templateCorrelation")
        minimum = _finite_number(
            preparation["minimumTemplateCorrelation"],
            "minimumTemplateCorrelation",
        )
        if minimum != DEFAULT_MINIMUM_TEMPLATE_CORRELATION or not minimum <= correlation <= 1.0:
            raise ReferenceDensityCacheError("prepared density template correlation is invalid")
        if preparation["apAxisReversed"] is not True or preparation["mlSymmetrized"] is not True:
            raise ReferenceDensityCacheError("prepared density axis safety transforms are missing")
        if preparation["mlSymmetrizationReason"] != "source ML polarity is not documented":
            raise ReferenceDensityCacheError("prepared density ML safety provenance changed")
        if preparation["resamplingMethod"] != (
            "linear interpolation at voxel centres with exact extents"
        ):
            raise ReferenceDensityCacheError("prepared density resampling provenance changed")

        density_file = _mapping_field(manifest, "densityFile")
        if set(density_file) != {"filename", "sizeBytes", "sha256", "dtype"}:
            raise ReferenceDensityCacheError("prepared density file manifest fields changed")
        if density_file["filename"] != "density-50um.npy" or density_file["dtype"] != "float32":
            raise ReferenceDensityCacheError("prepared density file identity changed")
        file_size = _positive_integer(density_file["sizeBytes"], "densityFile.sizeBytes")
        if file_size > MAX_PREPARED_DENSITY_FILE_BYTES:
            raise ReferenceDensityCacheError("prepared density file exceeds its size bound")
        file_sha256 = _sha256_value(density_file["sha256"], "densityFile.sha256")
        array_path = directory / "density-50um.npy"
        _verify_regular_file(
            array_path,
            expected_size=file_size,
            expected_sha256=file_sha256,
            label="prepared density array",
        )
        try:
            loaded = np.load(array_path, mmap_mode="r", allow_pickle=False)
        except (OSError, ValueError) as error:
            raise ReferenceDensityCacheError(
                "prepared density array is not a safe NPY file"
            ) from error
        values = cast(NDArray[np.float32], loaded)
        if values.shape != output_shape or values.dtype != np.dtype(np.float32):
            raise ReferenceDensityCacheError(
                "prepared density array shape or dtype differs from its manifest"
            )
        alignment = TemplateAlignmentEvidence(
            correlation=correlation,
            minimum_correlation=minimum,
            source_shape_mldvpa=STXVN5SV44_V1_SOURCE.source_shape_mldvpa,
            target_shape_asr=atlas.shape_voxels,
            source_voxel_size_um=STXVN5SV44_V1_SOURCE.source_voxel_size_um,
            target_voxel_size_um=atlas.resolution_um[0],
        )
        provenance = ReferenceDensityProvenance(
            source=STXVN5SV44_V1_SOURCE,
            output_frame=BRAINGLOBE_ASR_FRAME_AP_DV_ML,
            output_shape_asr=output_shape,
            output_voxel_size_um=output_resolution,
            output_extent_um_asr=output_extent,
            template_alignment=alignment,
        )
        density = ReferenceVascularDensity(values_asr=values, provenance=provenance)
        ReferenceDensityAtlasBinding(
            density=density,
            atlas_shape_asr=atlas.shape_voxels,
            atlas_resolution_um=atlas.resolution_um,
        )
        return CachedReferenceDensity(
            density=density,
            prepared_density_sha256=file_sha256,
            atlas_metadata_sha256=atlas.metadata_sha256,
            atlas_reference_sha256=reference_sha256,
            archive_sha256_verified=True,
            reused_prepared_cache=True,
        )

    def _quarantine_directory(self, path: Path) -> None:
        if not os.path.lexists(path):
            return
        if path.is_symlink() or not path.is_dir():
            raise ReferenceDensityCacheError(
                f"refusing to replace non-directory cache entry: {path.name}"
            )
        quarantine = path.with_name(f".{path.name}.invalid-{uuid4().hex}")
        path.replace(quarantine)
        _fsync_directory(path.parent)


def _validate_supported_atlas(
    atlas: AtlasMetadata,
    reference: NDArray[np.generic],
) -> None:
    expected_shape = (528, 320, 456)
    if (
        atlas.atlas_key != SUPPORTED_REFERENCE_ATLAS_IDENTIFIER
        or atlas.atlas_package_version != SUPPORTED_REFERENCE_ATLAS_VERSION
        or atlas.resolution_um != (25.0, 25.0, 25.0)
        or atlas.shape_voxels != expected_shape
        or atlas.standardized_orientation != "asr"
    ):
        raise ReferenceDensityCacheError(
            "population density preparation requires exact allen_mouse_25um v1.2 metadata"
        )
    array = np.asanyarray(reference)
    if array.shape != atlas.shape_voxels or not np.issubdtype(array.dtype, np.number):
        raise ReferenceDensityCacheError(
            "loaded atlas reference array does not match its exact metadata"
        )


def _source_manifest() -> dict[str, object]:
    return {
        "doi": STXVN5SV44_V1_SOURCE.doi,
        "version": STXVN5SV44_V1_SOURCE.version,
        "landingPageUrl": STXVN5SV44_V1_SOURCE.landing_page_url,
        "downloadUrl": PINNED_REFERENCE_DOWNLOAD_URL,
        "archiveFilename": STXVN5SV44_V1_SOURCE.archive_filename,
        "archiveSizeBytes": STXVN5SV44_V1_SOURCE.archive_size_bytes,
        "archiveSha256": STXVN5SV44_V1_SOURCE.archive_sha256,
        "densityMember": asdict(PINNED_DENSITY_MEMBER),
        "templateMember": asdict(PINNED_TEMPLATE_MEMBER),
    }


def _validate_manifest_source(manifest: Mapping[str, object]) -> None:
    expected_fields = {
        "schemaVersion",
        "algorithm",
        "source",
        "atlas",
        "preparation",
        "densityFile",
    }
    if set(manifest) != expected_fields:
        raise ReferenceDensityCacheError("prepared density manifest fields changed")
    if _mapping_field(manifest, "source") != _source_manifest():
        raise ReferenceDensityCacheError("prepared density source identity changed")


def _load_pinned_nifti(
    path: Path,
    *,
    member: PinnedArchiveMember,
) -> NDArray[Any]:
    _verify_regular_file(
        path,
        expected_size=member.size_bytes,
        expected_sha256=member.sha256,
        label=f"pinned {member.kind} NIfTI",
    )
    try:
        loaded_image = nib.load(str(path), mmap="r", keep_file_open=False)
        if not isinstance(loaded_image, nib.Nifti1Image):
            raise ReferenceDensityCacheError(
                f"pinned {member.kind} member is not a single-file NIfTI-1 image"
            )
        image = loaded_image
        header = image.header
        spatial_unit = str(header.get_xyzt_units()[0] or "unknown")  # type: ignore[no-untyped-call]
        evidence = NiftiHeaderEvidence(
            shape=tuple(int(size) for size in image.shape),
            spatial_zooms=cast(
                tuple[float, float, float],
                tuple(float(value) for value in header.get_zooms()[:3]),  # type: ignore[no-untyped-call]
            ),
            space_unit=spatial_unit,
            qform_code=int(np.asarray(header["qform_code"]).item()),
            sform_code=int(np.asarray(header["sform_code"]).item()),
            dtype_name=np.dtype(header.get_data_dtype()).name,  # type: ignore[no-untyped-call]
        )
        validate_source_nifti_header(
            evidence,
            kind=cast(Any, member.kind),
        )
        values = np.asanyarray(image.dataobj)
    except ReferenceDensityCacheError:
        raise
    except Exception as error:
        raise ReferenceDensityCacheError(
            f"pinned {member.kind} NIfTI could not be decoded safely"
        ) from error
    return values


def _verified_member_paths(directory: Path) -> dict[str, Path]:
    if directory.is_symlink() or not directory.is_dir():
        raise ReferenceDensityCacheError("extracted member cache must be a real directory")
    expected_names = {member.cached_filename for member in PINNED_ARCHIVE_MEMBERS}
    actual_names = {entry.name for entry in directory.iterdir()}
    if actual_names != expected_names:
        raise ReferenceDensityCacheError("extracted member cache contains unexpected entries")
    result: dict[str, Path] = {}
    for member in PINNED_ARCHIVE_MEMBERS:
        path = directory / member.cached_filename
        _verify_regular_file(
            path,
            expected_size=member.size_bytes,
            expected_sha256=member.sha256,
            label=f"cached {member.kind} NIfTI",
        )
        result[member.kind] = path
    return result


def _stream_archive_member(
    *,
    bsdtar_path: Path,
    archive: Path,
    member: PinnedArchiveMember,
    destination: Path,
) -> None:
    try:
        executable_stat = bsdtar_path.stat()
    except OSError as error:
        raise ReferenceDensityCacheError(
            "the system bsdtar executable is unavailable for controlled 7z extraction"
        ) from error
    if not stat.S_ISREG(executable_stat.st_mode) or not os.access(bsdtar_path, os.X_OK):
        raise ReferenceDensityCacheError(
            "the configured bsdtar path is not an executable regular file"
        )
    stderr_file = tempfile.TemporaryFile()
    process = subprocess.Popen(
        [str(bsdtar_path), "-xOf", str(archive), member.member_path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        close_fds=True,
    )
    digest = hashlib.sha256()
    count = 0
    try:
        if process.stdout is None:  # pragma: no cover - guaranteed by stdout=PIPE
            raise ReferenceDensityCacheError("bsdtar did not expose its extraction stream")
        with destination.open("xb") as output:
            while chunk := process.stdout.read(1024 * 1024):
                count += len(chunk)
                if count > member.size_bytes:
                    process.terminate()
                    raise ReferenceDensityCacheError(
                        f"archive member {member.member_path} exceeds its pinned size"
                    )
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        return_code = process.wait()
        stderr_file.seek(0)
        stderr_text = stderr_file.read(8192).decode("utf-8", errors="replace").strip()
        if return_code != 0:
            raise ReferenceDensityCacheError(
                f"controlled extraction failed for {member.member_path}: "
                f"{stderr_text or f'bsdtar exit {return_code}'}"
            )
        if count != member.size_bytes or digest.hexdigest() != member.sha256:
            raise ReferenceDensityCacheError(
                f"archive member identity mismatch for {member.member_path}"
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if process.stdout is not None:
            process.stdout.close()
        stderr_file.close()


def _download_verified_archive(destination: Path) -> None:
    _ensure_private_directory(destination.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".vascular-download.",
        suffix=".7z",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    count = 0
    try:
        request = urllib.request.Request(
            PINNED_REFERENCE_DOWNLOAD_URL,
            headers={"User-Agent": "Mouse-Brain-Surgery-Planner/0.1"},
        )
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            if urllib.parse.urlparse(final_url).scheme.casefold() != "https":
                raise ReferenceDensityCacheError("vascular source download left HTTPS")
            declared_length = response.headers.get("Content-Length")
            if declared_length is not None:
                try:
                    parsed_length = int(declared_length)
                except ValueError as error:
                    raise ReferenceDensityCacheError(
                        "vascular source returned an invalid Content-Length"
                    ) from error
                if parsed_length != STXVN5SV44_V1_SOURCE.archive_size_bytes:
                    raise ReferenceDensityCacheError(
                        "vascular source Content-Length does not match the pinned archive"
                    )
            output_stream = os.fdopen(descriptor, "wb")
            descriptor = -1
            with output_stream as output:
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > STXVN5SV44_V1_SOURCE.archive_size_bytes:
                        raise ReferenceDensityCacheError(
                            "vascular source download exceeds the pinned archive size"
                        )
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        if (
            count != STXVN5SV44_V1_SOURCE.archive_size_bytes
            or digest.hexdigest() != STXVN5SV44_V1_SOURCE.archive_sha256
        ):
            raise ReferenceDensityCacheError(
                "downloaded vascular archive does not match its pinned size and SHA-256"
            )
        _install_file(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _copy_verified_file(
    source: Path,
    destination: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> None:
    _ensure_private_directory(destination.parent)
    source_stat = _regular_lstat(source, "selected vascular archive")
    source_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    source_fd = os.open(source, source_flags)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=".vascular-copy.",
        suffix=".7z",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    count = 0
    try:
        opened = os.fstat(source_fd)
        if (opened.st_dev, opened.st_ino) != (source_stat.st_dev, source_stat.st_ino):
            raise ReferenceDensityCacheError("selected vascular archive changed while opening")
        output_stream = os.fdopen(temporary_fd, "wb")
        temporary_fd = -1
        with os.fdopen(source_fd, "rb", closefd=False) as input_stream, output_stream as output:
            while chunk := input_stream.read(1024 * 1024):
                count += len(chunk)
                if count > expected_size:
                    raise ReferenceDensityCacheError(
                        "selected vascular archive exceeds its pinned size"
                    )
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if count != expected_size or digest.hexdigest() != expected_sha256:
            raise ReferenceDensityCacheError(
                "selected vascular archive does not match its pinned size and SHA-256"
            )
        _install_file(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        os.close(source_fd)
        if temporary_fd >= 0:
            os.close(temporary_fd)


def _install_file(temporary: Path, destination: Path) -> None:
    if os.path.lexists(destination):
        existing = destination.lstat()
        if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
            raise ReferenceDensityCacheError(
                f"refusing to replace non-regular cache entry: {destination.name}"
            )
    temporary.replace(destination)
    destination.chmod(0o600)
    _fsync_directory(destination.parent)


def _verify_regular_file(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    label: str,
) -> None:
    member_stat = _regular_lstat(path, label)
    if member_stat.st_size != expected_size:
        raise ReferenceDensityCacheError(
            f"{label} size mismatch: expected {expected_size}, got {member_stat.st_size}"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    count = 0
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            member_stat.st_dev,
            member_stat.st_ino,
        ):
            raise ReferenceDensityCacheError(f"{label} changed while opening")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while chunk := stream.read(1024 * 1024):
                count += len(chunk)
                if count > expected_size:
                    raise ReferenceDensityCacheError(f"{label} grew while hashing")
                digest.update(chunk)
    finally:
        os.close(descriptor)
    if count != expected_size or digest.hexdigest() != expected_sha256:
        raise ReferenceDensityCacheError(f"{label} SHA-256 mismatch")


def _regular_lstat(path: Path, label: str) -> os.stat_result:
    try:
        result = path.lstat()
    except OSError as error:
        raise ReferenceDensityCacheError(f"{label} is unavailable") from error
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISREG(result.st_mode):
        raise ReferenceDensityCacheError(f"{label} must be a regular file, not a symlink")
    return result


def _same_file_if_present(first: Path, second: Path) -> bool:
    try:
        return first.samefile(second)
    except FileNotFoundError:
        return False


def _hash_array_c_order(values: NDArray[np.generic]) -> str:
    array = np.asanyarray(values)
    if array.ndim != 3 or not np.issubdtype(array.dtype, np.number):
        raise ReferenceDensityCacheError("atlas reference must be a numeric 3-D array")
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    for axis_zero in range(array.shape[0]):
        plane = np.ascontiguousarray(array[axis_zero])
        digest.update(memoryview(plane).cast("B"))
    return digest.hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(path: Path) -> dict[str, object]:
    member_stat = _regular_lstat(path, "prepared density manifest")
    if member_stat.st_size > MAX_MANIFEST_BYTES:
        raise ReferenceDensityCacheError("prepared density manifest exceeds its size bound")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReferenceDensityCacheError("prepared density manifest is invalid JSON") from error
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise ReferenceDensityCacheError("prepared density manifest must be a JSON object")
    return cast(dict[str, object], payload)


def _write_json_fsync(path: Path, payload: Mapping[str, object]) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    if len(encoded.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ReferenceDensityCacheError("prepared density manifest exceeds its size bound")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _mapping_field(payload: Mapping[str, object], field: str) -> dict[str, object]:
    value = payload.get(field)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ReferenceDensityCacheError(f"prepared density manifest {field} must be an object")
    return cast(dict[str, object], value)


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReferenceDensityCacheError(f"{field} must be a positive integer")
    return value


def _integer_triplet(value: object, field: str) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3:
        raise ReferenceDensityCacheError(f"{field} must contain three integers")
    converted = tuple(_positive_integer(item, field) for item in value)
    return cast(tuple[int, int, int], converted)


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReferenceDensityCacheError(f"{field} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise ReferenceDensityCacheError(f"{field} must be finite")
    return result


def _number_triplet(value: object, field: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ReferenceDensityCacheError(f"{field} must contain three numbers")
    return cast(tuple[float, float, float], tuple(_finite_number(item, field) for item in value))


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReferenceDensityCacheError(f"{field} must contain strings")
    return cast(list[str], value)


def _sha256_value(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ReferenceDensityCacheError(f"{field} must be a lowercase SHA-256")
    return value


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    result = path.lstat()
    if stat.S_ISLNK(result.st_mode) or not stat.S_ISDIR(result.st_mode):
        raise ReferenceDensityCacheError(f"cache path must be a real directory: {path}")
    path.chmod(0o700)


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
