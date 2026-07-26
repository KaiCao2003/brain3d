"""External display-only VesSAP major-vessel geometry.

The optional derivative starts from the public BL6J-no1 whole-brain centerline
and radius volumes released with VesSAP.  Centerline voxels with a source
radius below five 3-micrometre voxels are removed, the retained skeleton is
mapped through the authors' published rigid plus B-spline Allen transform, and
source adjacency is reduced on a 50-micrometre display grid.

This module deliberately exposes geometry only.  The fixed, cleared reference
is not subject-specific and the source does not publish registration or tissue
distortion uncertainty bounds, so it cannot support clearance or safety
classification.
"""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.paths import app_paths

ASSET_SCHEMA_VERSION: Final = 1
ASSET_FILENAME: Final = "vessap_bl6j1_major_vessels_50um_v1.npz"
MANIFEST_FILENAME: Final = f"{ASSET_FILENAME}.manifest.json"
ASSET_SIZE_BYTES: Final = 1_853_131
ASSET_SHA256: Final = "9300dacf25ca57a5d23377ca0dc885e34ff0d18e8d21ef7590c6dcd156cf5db7"

SOURCE_ID: Final = "vessap-bl6j-no1-major-vessels-50um-v1"
SOURCE_RECORD_URL: Final = "https://www.discotechnologies.org/VesSAP/"
SOURCE_PAPER_DOI: Final = "10.1038/s41592-020-0792-1"
SOURCE_VERSION: Final = "VesSAP public repository release 2021.10.01"
SOURCE_LICENSE: Final = "CC BY-NC 4.0"
SOURCE_LICENSE_URL: Final = "https://creativecommons.org/licenses/by-nc/4.0/"
SOURCE_SPECIMEN_ID: Final = "BL6J-no1"
SOURCE_BUNDLE_SHA256: Final = "d0216b9f6fcec428845f8ecc24860b4838f27b6b69496a88d8b7ab0dcd1dbf8a"
SOURCE_SKELETON_SIZE_BYTES: Final = 114_305_865
SOURCE_SKELETON_SHA256: Final = "1ea1a489dfacfa509f60d984ee955e43107a579d181bb5e6f3df51da6b68beac"
SOURCE_RADIUS_SIZE_BYTES: Final = 136_114_699
SOURCE_RADIUS_SHA256: Final = "6a8728d4518957c0e84687b077a76e64362edc9644c6e2adce60c2c244d4b887"
SOURCE_TRANSFORM_ARCHIVE_SIZE_BYTES: Final = 38_472
SOURCE_TRANSFORM_ARCHIVE_SHA256: Final = (
    "ab2509e07dcab65f176b72337624fa2ccc38f9e32f17530964ed17af5e1e88ad"
)

ATLAS_IDENTIFIER: Final = "allen_mouse_25um"
ATLAS_VERSION: Final = "1.2"
ATLAS_SHAPE_ASR: Final = (528, 320, 456)
ATLAS_VOXEL_SIZE_UM: Final = 25.0
SOURCE_VOXEL_SIZE_UM: Final = 3.0
MINIMUM_SOURCE_RADIUS_VOXELS: Final = 5
MINIMUM_RADIUS_UM: Final = 15.0
MINIMUM_DIAMETER_UM: Final = 30.0
DISPLAY_CONNECTIVITY_GRID_UM: Final = 50.0
EXTRACTION_ALGORITHM_VERSION: Final = "vessap-bl6j1-major-skeleton-50um-v1"
REGISTRATION_TRANSFORM_ID: Final = (
    "vessap-bl6j-no1-rigid-bspline-fullres-"
    "sha256-ab2509e07dcab65f176b72337624fa2ccc38f9e32f17530964ed17af5e1e88ad"
)

EXPECTED_SOURCE_SKELETON_POINTS: Final = 58_313_813
EXPECTED_THRESHOLD_POINTS: Final = 1_262_706
EXPECTED_IN_BOUNDS_POINTS: Final = 1_258_140
EXPECTED_OCCUPIED_DISPLAY_VOXELS: Final = 198_262
EXPECTED_OMITTED_ISOLATED_VOXELS: Final = 63_320
EXPECTED_POINT_COUNT: Final = 196_377
EXPECTED_RUN_COUNT: Final = 76_622
EXPECTED_SEGMENT_COUNT: Final = 119_755
EXPECTED_PATH_LENGTH_UM: Final = 3_817_312.0853968207

ARRAY_DTYPES: Final[Mapping[str, np.dtype[np.generic]]] = {
    "points_asr_um_f32": np.dtype("<f4"),
    "radii_um_f32": np.dtype("<f4"),
    "run_offsets_i64": np.dtype("<i8"),
    "source_run_indices_i32": np.dtype("<i4"),
}

MANDATORY_LIMITATIONS: Final = (
    "Animal research use only; this population reference is not a medical device and is not "
    "validated for stereotaxic navigation.",
    "The source is one fixed, cleared adult C57BL/6J mouse brain, not the current animal and "
    "not live vasculature.",
    "Only source centerline voxels with radius at least 15 um are retained; capillaries and "
    "smaller vessels are intentionally omitted.",
    "The published specimen-to-Allen rigid plus B-spline transform is retained, but no numeric "
    "registration-error or clearing-distortion bound is published.",
    "Source skeleton adjacency is coalesced on a 50 um display grid; close paths can merge and "
    "isolated display voxels without a retained segment are omitted.",
    "Pial and choroidal coverage is not separately classified, and artery-versus-vein identity "
    "is unavailable.",
    "This layer is display-only: it cannot establish clearance, absence of a vessel, trajectory "
    "suitability, or safety for an individual animal.",
    "The derived data remain CC BY-NC 4.0 and may be used only under that license.",
)


class VesSAPMajorVesselError(ValueError):
    """Raised when the pinned asset or its provenance fails closed."""


@dataclass(frozen=True, slots=True)
class VesSAPMajorVesselProvenance:
    """Attribution and interpretation limits carried with the geometry."""

    dataset_title: str
    authors: tuple[str, ...]
    specimen_id: str
    record_doi: str
    record_url: str
    license: str
    license_url: str
    source_sha256: str
    asset_sha256: str
    extraction_algorithm_version: str
    registration_transform_id: str
    minimum_radius_um: float
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True, eq=False)
class VesSAPMajorVesselGraph:
    """Immutable physical BrainGlobe-ASR polylines."""

    points_asr_um: NDArray[np.float32]
    radii_um: NDArray[np.float32]
    run_offsets: NDArray[np.int64]
    source_edge_indices: NDArray[np.int32]
    provenance: VesSAPMajorVesselProvenance

    @property
    def run_count(self) -> int:
        return int(self.source_edge_indices.shape[0])

    def run_points_asr_um(self, run_index: int) -> NDArray[np.float32]:
        if isinstance(run_index, bool) or not isinstance(run_index, int):
            raise TypeError("run_index must be an integer")
        if not 0 <= run_index < self.run_count:
            raise IndexError("run_index is outside the vessel graph")
        start = int(self.run_offsets[run_index])
        end = int(self.run_offsets[run_index + 1])
        return self.points_asr_um[start:end]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise VesSAPMajorVesselError(f"{name} must be an object with string keys")
    return cast(Mapping[str, object], value)


def _expected_source() -> dict[str, object]:
    return {
        "dataset_title": "Machine learning analysis of whole mouse brain vasculature",
        "record_url": SOURCE_RECORD_URL,
        "paper_doi": SOURCE_PAPER_DOI,
        "version": SOURCE_VERSION,
        "license": SOURCE_LICENSE,
        "license_url": SOURCE_LICENSE_URL,
        "specimen_id": SOURCE_SPECIMEN_ID,
        "source_bundle_sha256": SOURCE_BUNDLE_SHA256,
        "files": {
            "BL6J-no1_iso3um_stitched_skeleton.nii.gz": {
                "size_bytes": SOURCE_SKELETON_SIZE_BYTES,
                "sha256": SOURCE_SKELETON_SHA256,
            },
            "BL6J-no1_iso3um_stitched_radius.nii.gz": {
                "size_bytes": SOURCE_RADIUS_SIZE_BYTES,
                "sha256": SOURCE_RADIUS_SHA256,
            },
            "elastix_atlas_registration_parameters.7z": {
                "size_bytes": SOURCE_TRANSFORM_ARCHIVE_SIZE_BYTES,
                "sha256": SOURCE_TRANSFORM_ARCHIVE_SHA256,
            },
        },
    }


def _expected_registration() -> dict[str, object]:
    return {
        "transform_id": REGISTRATION_TRANSFORM_ID,
        "source_grid_order": ["x", "y", "z"],
        "source_voxel_size_um": [SOURCE_VOXEL_SIZE_UM] * 3,
        "published_transform_order": ["EulerTransform", "BSplineTransform"],
        "moving_grid_order": ["ML-left-to-right", "AP", "DV"],
        "output_frame": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "output_axis_order": ["AP", "DV", "ML-right-to-left"],
        "mapping": (
            "AP_um=30*T_y; DV_um=30*T_z; ML_um=11390-30*T_x, where T is transformix physical output"
        ),
        "atlas_identifier": ATLAS_IDENTIFIER,
        "atlas_version": ATLAS_VERSION,
        "atlas_shape_asr": list(ATLAS_SHAPE_ASR),
        "atlas_voxel_size_um": [ATLAS_VOXEL_SIZE_UM] * 3,
    }


def _expected_extraction() -> dict[str, object]:
    return {
        "algorithm_version": EXTRACTION_ALGORITHM_VERSION,
        "minimum_source_radius_voxels": MINIMUM_SOURCE_RADIUS_VOXELS,
        "minimum_radius_um": MINIMUM_RADIUS_UM,
        "minimum_diameter_um": MINIMUM_DIAMETER_UM,
        "display_connectivity_grid_um": DISPLAY_CONNECTIVITY_GRID_UM,
        "connectivity": (
            "retain only mapped edges induced by 26-neighbour adjacency in the thresholded "
            "source skeleton; never connect merely adjacent target bins"
        ),
        "target_point": (
            "mean continuous transformed coordinate of retained source points in each occupied "
            "50 um display bin"
        ),
        "target_radius": "maximum retained source EDT radius in each occupied display bin * 3 um",
        "statistics": {
            "source_skeleton_points": EXPECTED_SOURCE_SKELETON_POINTS,
            "threshold_points": EXPECTED_THRESHOLD_POINTS,
            "in_bounds_points": EXPECTED_IN_BOUNDS_POINTS,
            "occupied_display_voxels": EXPECTED_OCCUPIED_DISPLAY_VOXELS,
            "omitted_isolated_display_voxels": EXPECTED_OMITTED_ISOLATED_VOXELS,
            "output_points": EXPECTED_POINT_COUNT,
            "output_runs": EXPECTED_RUN_COUNT,
            "output_segments": EXPECTED_SEGMENT_COUNT,
            "output_path_length_um": EXPECTED_PATH_LENGTH_UM,
        },
    }


def _expected_validation() -> dict[str, object]:
    return {
        "node_sample_count": 20_000,
        "graph_node_count": 3_820_133,
        "within_atlas_bounds_fraction": 0.99705,
        "correct_axis_permutation": "[T_y,T_z,T_x] -> [AP,DV,ML]",
        "grouped_region_agreement_10um_excluding_background": {
            "matched": 18_664,
            "evaluated": 18_765,
            "fraction": 0.994618,
        },
        "grouped_region_agreement_10um_excluding_background_root_and_fiber_tracts": {
            "matched": 17_505,
            "evaluated": 17_585,
            "fraction": 0.995451,
        },
        "grouped_region_agreement_25um_excluding_background_fraction": 0.978524,
        "official_registered_label_group_agreement": {
            "matched": 18_761,
            "evaluated": 18_765,
            "fraction": 0.999787,
        },
        "laterality_midpoint_agreement": {
            "matched": 19_425,
            "evaluated": 19_429,
            "fraction": 0.999794,
            "maximum_discrepancy_distance_from_midline_um": 5.38,
        },
        "laterality_evidence": (
            "official registered atlas uses negative IDs for anatomical left; sampled signed "
            "labels prove moving ML increases left-to-right and therefore requires reversal "
            "for BrainGlobe ASR"
        ),
        "sampled_jacobian_determinant_range": [1.269, 2.451],
        "sampled_jacobian_singular_value_range": [0.672, 1.56],
        "sampled_jacobian_fold_count": 0,
        "uncertainty_bounds_published": False,
        "clearance_enabled": False,
    }


def default_asset_paths() -> tuple[Path, Path]:
    """Return the expected paths for the user-installed VesSAP data package."""

    asset_root = app_paths().data / "vasculature"
    return asset_root / ASSET_FILENAME, asset_root / MANIFEST_FILENAME


def default_asset_is_available() -> bool:
    """Return whether both external data files are regular, non-symlink files."""

    return all(path.is_file() and not path.is_symlink() for path in default_asset_paths())


def _read_and_validate_manifest(manifest_path: Path, asset_path: Path) -> None:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise VesSAPMajorVesselError("VesSAP vessel manifest must be a regular file")
    if manifest_path.stat().st_size > 128 * 1024:
        raise VesSAPMajorVesselError("VesSAP vessel manifest is unexpectedly large")
    try:
        manifest = _mapping(json.loads(manifest_path.read_text(encoding="utf-8")), name="manifest")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VesSAPMajorVesselError("VesSAP vessel manifest could not be parsed") from error
    if set(manifest) != {
        "schema_version",
        "asset",
        "source",
        "registration",
        "extraction",
        "validation",
        "limitations",
    }:
        raise VesSAPMajorVesselError("VesSAP vessel manifest fields changed")
    if manifest["schema_version"] != ASSET_SCHEMA_VERSION:
        raise VesSAPMajorVesselError("VesSAP vessel manifest schema changed")
    if manifest["source"] != _expected_source():
        raise VesSAPMajorVesselError("VesSAP source provenance changed")
    if manifest["registration"] != _expected_registration():
        raise VesSAPMajorVesselError("VesSAP registration evidence changed")
    if manifest["extraction"] != _expected_extraction():
        raise VesSAPMajorVesselError("VesSAP extraction evidence changed")
    if manifest["validation"] != _expected_validation():
        raise VesSAPMajorVesselError("VesSAP validation evidence changed")
    if manifest["limitations"] != list(MANDATORY_LIMITATIONS):
        raise VesSAPMajorVesselError("VesSAP mandatory limitations changed")
    expected_asset = {
        "filename": ASSET_FILENAME,
        "size_bytes": ASSET_SIZE_BYTES,
        "sha256": ASSET_SHA256,
        "arrays": {
            "points_asr_um_f32": {"dtype": "float32", "shape": [EXPECTED_POINT_COUNT, 3]},
            "radii_um_f32": {"dtype": "float32", "shape": [EXPECTED_POINT_COUNT]},
            "run_offsets_i64": {"dtype": "int64", "shape": [EXPECTED_RUN_COUNT + 1]},
            "source_run_indices_i32": {"dtype": "int32", "shape": [EXPECTED_RUN_COUNT]},
        },
    }
    if manifest["asset"] != expected_asset:
        raise VesSAPMajorVesselError("VesSAP vessel asset identity changed")
    if asset_path.is_symlink() or not asset_path.is_file():
        raise VesSAPMajorVesselError("VesSAP vessel asset must be a regular file")
    if asset_path.stat().st_size != ASSET_SIZE_BYTES:
        raise VesSAPMajorVesselError("VesSAP vessel asset byte count changed")
    if _hash_file(asset_path) != ASSET_SHA256:
        raise VesSAPMajorVesselError("VesSAP vessel asset SHA-256 changed")


def _validate_zip_members(asset_path: Path) -> None:
    expected = {f"{name}.npy" for name in ARRAY_DTYPES}
    try:
        with zipfile.ZipFile(asset_path) as archive:
            infos = archive.infolist()
            if len(infos) != len(expected) or {item.filename for item in infos} != expected:
                raise VesSAPMajorVesselError("VesSAP NPZ member inventory changed")
            if sum(item.file_size for item in infos) > 10 * 1024 * 1024:
                raise VesSAPMajorVesselError("VesSAP NPZ expands beyond its reviewed bound")
    except (OSError, zipfile.BadZipFile) as error:
        raise VesSAPMajorVesselError("VesSAP vessel asset is not a valid NPZ") from error


def _polyline_length(points: NDArray[np.float32], offsets: NDArray[np.int64]) -> float:
    deltas = points[1:].astype(np.float64) - points[:-1].astype(np.float64)
    keep = np.ones(deltas.shape[0], dtype=np.bool_)
    keep[offsets[1:-1] - 1] = False
    return float(np.linalg.norm(deltas[keep], axis=1).sum(dtype=np.float64))


def _load_arrays(
    asset_path: Path,
) -> tuple[
    NDArray[np.float32],
    NDArray[np.float32],
    NDArray[np.int64],
    NDArray[np.int32],
]:
    try:
        with np.load(asset_path, allow_pickle=False) as archive:
            if set(archive.files) != set(ARRAY_DTYPES):
                raise VesSAPMajorVesselError("VesSAP loaded array inventory changed")
            arrays = {name: np.asarray(archive[name]) for name in archive.files}
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise VesSAPMajorVesselError("VesSAP vessel arrays could not be loaded") from error
    for name, expected_dtype in ARRAY_DTYPES.items():
        value = arrays[name]
        if value.dtype != expected_dtype or not value.flags.c_contiguous:
            raise VesSAPMajorVesselError(f"VesSAP vessel array {name} changed")
    points = cast(NDArray[np.float32], arrays["points_asr_um_f32"])
    radii = cast(NDArray[np.float32], arrays["radii_um_f32"])
    offsets = cast(NDArray[np.int64], arrays["run_offsets_i64"])
    source_runs = cast(NDArray[np.int32], arrays["source_run_indices_i32"])
    if points.shape != (EXPECTED_POINT_COUNT, 3) or radii.shape != (EXPECTED_POINT_COUNT,):
        raise VesSAPMajorVesselError("VesSAP point arrays have the wrong shape")
    if offsets.shape != (EXPECTED_RUN_COUNT + 1,) or source_runs.shape != (EXPECTED_RUN_COUNT,):
        raise VesSAPMajorVesselError("VesSAP run arrays have the wrong shape")
    if not bool(np.all(np.isfinite(points))) or not bool(np.all(np.isfinite(radii))):
        raise VesSAPMajorVesselError("VesSAP vessel geometry is non-finite")
    maxima = np.asarray(ATLAS_SHAPE_ASR, dtype=np.float32) * np.float32(ATLAS_VOXEL_SIZE_UM)
    if bool(np.any(points < 0)) or bool(np.any(points >= maxima)):
        raise VesSAPMajorVesselError("VesSAP vessel point is outside the reviewed atlas")
    if bool(np.any(radii < np.float32(MINIMUM_RADIUS_UM))):
        raise VesSAPMajorVesselError("VesSAP vessel point is below the diameter threshold")
    if (
        int(offsets[0]) != 0
        or int(offsets[-1]) != EXPECTED_POINT_COUNT
        or not bool(np.all(np.diff(offsets) >= 2))
    ):
        raise VesSAPMajorVesselError("VesSAP run offsets are inconsistent")
    if bool(np.any(source_runs < 0)) or bool(np.any(source_runs[1:] < source_runs[:-1])):
        raise VesSAPMajorVesselError("VesSAP source run indices are inconsistent")
    observed_length = _polyline_length(points, offsets)
    if not math.isclose(observed_length, EXPECTED_PATH_LENGTH_UM, rel_tol=0, abs_tol=1e-3):
        raise VesSAPMajorVesselError("VesSAP path length changed")
    return points, radii, offsets, source_runs


def load_vessap_major_vessels(
    asset_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> VesSAPMajorVesselGraph:
    """Load and freeze the exact externally installed display derivative."""

    default_asset, default_manifest = default_asset_paths()
    asset = default_asset if asset_path is None else Path(asset_path)
    manifest = default_manifest if manifest_path is None else Path(manifest_path)
    _read_and_validate_manifest(manifest, asset)
    _validate_zip_members(asset)
    points, radii, offsets, source_runs = _load_arrays(asset)
    for value in (points, radii, offsets, source_runs):
        value.setflags(write=False)
    return VesSAPMajorVesselGraph(
        points_asr_um=points,
        radii_um=radii,
        run_offsets=offsets,
        source_edge_indices=source_runs,
        provenance=VesSAPMajorVesselProvenance(
            dataset_title="Machine learning analysis of whole mouse brain vasculature",
            authors=(
                "Mihail I. Todorov",
                "Johannes C. Paetzold",
                "Oliver Schoppe",
                "Giles Tetteh",
                "Suprosanna Shit",
                "Velizar Efremov",
                "Katalin Todorov-Völgyi",
                "Marco Düring",
                "Martin Dichgans",
                "Marie Piraud",
                "Bjoern Menze",
                "Ali Ertürk",
            ),
            specimen_id=SOURCE_SPECIMEN_ID,
            record_doi=SOURCE_PAPER_DOI,
            record_url=SOURCE_RECORD_URL,
            license=SOURCE_LICENSE,
            license_url=SOURCE_LICENSE_URL,
            source_sha256=SOURCE_BUNDLE_SHA256,
            asset_sha256=ASSET_SHA256,
            extraction_algorithm_version=EXTRACTION_ALGORITHM_VERSION,
            registration_transform_id=REGISTRATION_TRANSFORM_ID,
            minimum_radius_um=MINIMUM_RADIUS_UM,
            limitations=MANDATORY_LIMITATIONS,
        ),
    )
