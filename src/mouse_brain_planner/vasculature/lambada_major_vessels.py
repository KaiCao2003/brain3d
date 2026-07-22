"""Pinned LAMBADA P60 vessel geometry and its reproducible compact extractor.

The bundled asset is intentionally a small, display-only derivative of one
atlas-registered, fixed-tissue graph.  It contains maximal consecutive runs
whose point radii are at least 15 micrometres and whose coordinates are inside
the reviewed Allen 25 micrometre array bounds.  It is not a clearance map and
must not be interpreted as subject-specific surgical vasculature.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Final, cast

import numpy as np
from numpy.typing import NDArray

ASSET_SCHEMA_VERSION: Final = 1
EXTRACTION_ALGORITHM_VERSION: Final = "lambada-p60-606-major-runs-v1"
ASSET_FILENAME: Final = "lambada_p60_606_major_vessels_v1.npz"
MANIFEST_FILENAME: Final = f"{ASSET_FILENAME}.manifest.json"
ASSET_SIZE_BYTES: Final = 814_393
ASSET_SHA256: Final = "fb2344e845e604be3424bd63f4222d273eafba34db0df2eaff32f4400fa9afec"

SOURCE_FILENAME: Final = "606_graph_2024-12-03.gt"
SOURCE_SIZE_BYTES: Final = 12_282_574_483
SOURCE_SHA256: Final = "c2568cfbecd3f3eb720519be9d042f0cb41606741b8dd2f018bad1c54d36ef85"
SOURCE_MD5: Final = "b0bedc97ed2c6e00a41565649b3dd86b"
SOURCE_ARCHIVE_FILENAME: Final = "P60_606_graph_2024-12-03.gt.7z"
SOURCE_ARCHIVE_SIZE_BYTES: Final = 5_050_194_723
SOURCE_ARCHIVE_SHA256: Final = "cc6d252ee57154f5bc0f06605a703253470a57c210d76e075831effa2098d66f"
SOURCE_ARCHIVE_MD5: Final = "218ed346c6d7dc501301204f811be37f"
SOURCE_RECORD_DOI: Final = "10.5281/zenodo.18876865"
SOURCE_CONCEPT_DOI: Final = "10.5281/zenodo.18876864"
SOURCE_RECORD_URL: Final = "https://zenodo.org/records/18876865"
SOURCE_LICENSE: Final = "CC BY 4.0"
SOURCE_LICENSE_URL: Final = "https://creativecommons.org/licenses/by/4.0/"
SOURCE_PAPER_DOI: Final = "10.1016/j.cell.2026.03.013"
SOURCE_PAPER_URL: Final = "https://www.cell.com/cell/fulltext/S0092-8674(26)00280-1"

ATLAS_IDENTIFIER: Final = "allen_mouse_25um"
ATLAS_VERSION: Final = "1.2"
ATLAS_SHAPE_CLEARMAP: Final = (320, 528, 456)
ATLAS_SHAPE_ASR: Final = (528, 320, 456)
ATLAS_VOXEL_SIZE_UM: Final = 25.0
MINIMUM_RADIUS_UM: Final = 15.0
MINIMUM_DIAMETER_UM: Final = 30.0
MINIMUM_RADIUS_ATLAS_VOXEL: Final = MINIMUM_RADIUS_UM / ATLAS_VOXEL_SIZE_UM

# Exact graph-tool property layout for the one SHA-256-pinned extracted source.
# These offsets are never accepted for a file whose byte count and digest differ.
SOURCE_VERTEX_COUNT: Final = 2_231_019
SOURCE_EDGE_COUNT: Final = 3_301_619
SOURCE_GEOMETRY_POINT_COUNT: Final = 76_980_908
COORDINATES_ATLAS_RAW_OFFSET: Final = 2_494_444_615
RADII_ATLAS_RAW_OFFSET: Final = 4_341_986_607
ANNOTATIONS_RAW_OFFSET: Final = 4_957_834_070
EDGE_GEOMETRY_INDICES_PAYLOAD_OFFSET: Final = 12_124_096_701
EDGE_RADII_ATLAS_RAW_OFFSET: Final = 12_203_335_578

EXPECTED_CANDIDATE_EDGE_COUNT: Final = 16_156
EXPECTED_QUALIFYING_IN_BOUNDS_POINT_COUNT: Final = 78_048
EXPECTED_RUN_POINT_COUNT: Final = 71_313
EXPECTED_SEGMENT_COUNT: Final = 59_495
EXPECTED_RUN_COUNT: Final = 11_818
EXPECTED_SOURCE_EDGES_WITH_RUNS: Final = 10_907

ARRAY_DTYPES: Final[Mapping[str, np.dtype[np.generic]]] = {
    "points_asr_voxel_f32": np.dtype("<f4"),
    "radii_um_f32": np.dtype("<f4"),
    "source_annotation_ids_i32": np.dtype("<i4"),
    "run_offsets_i64": np.dtype("<i8"),
    "source_edge_indices_i32": np.dtype("<i4"),
}

MANDATORY_LIMITATIONS: Final = (
    "Animal research use only; this derivative is not a medical device and is not validated "
    "for surgery.",
    "The source is an atlas-registered fixed and cleared P60 mouse-brain reference, not live "
    "or subject-specific vasculature.",
    "Pial and choroidal vessels were removed by the source workflow, and this derivative also "
    "suppresses points below a 15 um radius; missing vessels are expected.",
    "This graph cannot establish subject-specific clearance or trajectory suitability; "
    "registration error, tissue distortion, biological variation, and omitted vessels are not "
    "bounded here.",
    "The exact sex and sampled side of specimen P60_606 are unpublished, and the graph does "
    "not identify arteries versus veins.",
    "The source workflow corrected endpoints, linearly reconnected nearby endpoints, and "
    "removed short terminal offshoots, so some paths are reconstructed rather than observed.",
    "Displayed radii use the source's mean atlas-resampling scale and are not locally "
    "Jacobian-corrected lumen measurements.",
    "Out-of-bounds source points split runs and are dropped without clipping or interpolation.",
)


class LambadaMajorVesselError(ValueError):
    """Raised when source or runtime vessel data fail a trust boundary."""


@dataclass(frozen=True, slots=True, eq=False)
class LambadaMajorVesselAssetData:
    """Canonical arrays stored in the compact NPZ derivative."""

    points_asr_voxel_f32: NDArray[np.float32]
    radii_um_f32: NDArray[np.float32]
    source_annotation_ids_i32: NDArray[np.int32]
    run_offsets_i64: NDArray[np.int64]
    source_edge_indices_i32: NDArray[np.int32]

    def arrays(self) -> dict[str, NDArray[np.generic]]:
        """Return the fixed on-disk array mapping."""

        return {
            "points_asr_voxel_f32": self.points_asr_voxel_f32,
            "radii_um_f32": self.radii_um_f32,
            "source_annotation_ids_i32": self.source_annotation_ids_i32,
            "run_offsets_i64": self.run_offsets_i64,
            "source_edge_indices_i32": self.source_edge_indices_i32,
        }


@dataclass(frozen=True, slots=True)
class LambadaExtractionReport:
    """Deterministic statistics recorded beside the derived asset."""

    candidate_edges_by_source_edge_max: int
    qualifying_in_bounds_points: int
    output_points: int
    output_segments: int
    output_runs: int
    source_edges_with_runs: int
    selected_path_length_um_source_f64: float
    asset_path_length_um_f32: float


@dataclass(frozen=True, slots=True)
class LambadaMajorVesselProvenance:
    """Attribution and mandatory interpretation limits carried at runtime."""

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
    minimum_radius_um: float
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True, eq=False)
class LambadaMajorVesselGraph:
    """Immutable display graph in BrainGlobe physical ASR ``[AP,DV,ML]`` micrometres."""

    points_asr_um: NDArray[np.float32]
    radii_um: NDArray[np.float32]
    source_annotation_ids: NDArray[np.int32]
    run_offsets: NDArray[np.int64]
    source_edge_indices: NDArray[np.int32]
    provenance: LambadaMajorVesselProvenance

    @property
    def run_count(self) -> int:
        """Number of independent polylines."""

        return int(self.source_edge_indices.shape[0])

    def run_points_asr_um(self, run_index: int) -> NDArray[np.float32]:
        """Return one immutable physical-ASR polyline view."""

        if isinstance(run_index, bool) or not isinstance(run_index, int):
            raise TypeError("run_index must be an integer")
        if not 0 <= run_index < self.run_count:
            raise IndexError("run_index is outside the vessel graph")
        start = int(self.run_offsets[run_index])
        end = int(self.run_offsets[run_index + 1])
        return self.points_asr_um[start:end]


def _as_numeric_array(
    value: NDArray[np.generic],
    *,
    name: str,
    ndim: int,
) -> NDArray[np.generic]:
    array = np.asarray(value)
    if array.ndim != ndim:
        raise LambadaMajorVesselError(f"{name} must be {ndim}-dimensional")
    if array.dtype.kind not in "fiu":
        raise LambadaMajorVesselError(f"{name} must be numeric")
    return array


def extract_major_vessel_runs(
    coordinates_clearmap_voxel: NDArray[np.generic],
    radii_atlas_voxel: NDArray[np.generic],
    source_annotation_ids: NDArray[np.generic],
    edge_geometry_indices: NDArray[np.generic],
    *,
    atlas_shape_clearmap: tuple[int, int, int] = ATLAS_SHAPE_CLEARMAP,
    atlas_voxel_size_um: float = ATLAS_VOXEL_SIZE_UM,
    minimum_radius_um: float = MINIMUM_RADIUS_UM,
) -> LambadaMajorVesselAssetData:
    """Extract maximal in-bounds pointwise-radius runs from graph geometry.

    Each edge range is end-exclusive.  Runs shorter than two points have no
    drawable segment and are omitted.  ClearMap ``[c0,c1,c2]`` coordinates are
    permuted to BrainGlobe ASR ``[c1,c0,c2]`` without a half-voxel shift.
    """

    coordinates = _as_numeric_array(
        coordinates_clearmap_voxel,
        name="coordinates_clearmap_voxel",
        ndim=2,
    )
    radii = _as_numeric_array(radii_atlas_voxel, name="radii_atlas_voxel", ndim=1)
    annotations = _as_numeric_array(
        source_annotation_ids,
        name="source_annotation_ids",
        ndim=1,
    )
    edge_indices = _as_numeric_array(
        edge_geometry_indices,
        name="edge_geometry_indices",
        ndim=2,
    )
    if coordinates.shape[1:] != (3,):
        raise LambadaMajorVesselError("coordinates_clearmap_voxel must have shape [N,3]")
    point_count = coordinates.shape[0]
    if radii.shape != (point_count,) or annotations.shape != (point_count,):
        raise LambadaMajorVesselError("point radii and annotations must have shape [N]")
    if edge_indices.shape[1:] != (2,):
        raise LambadaMajorVesselError("edge_geometry_indices must have shape [E,2]")
    if any(
        isinstance(size, bool) or not isinstance(size, int) or size <= 0
        for size in atlas_shape_clearmap
    ):
        raise LambadaMajorVesselError("atlas_shape_clearmap must contain three positive integers")
    if len(atlas_shape_clearmap) != 3:
        raise LambadaMajorVesselError("atlas_shape_clearmap must contain exactly three values")
    if not math.isfinite(atlas_voxel_size_um) or atlas_voxel_size_um <= 0.0:
        raise LambadaMajorVesselError("atlas_voxel_size_um must be finite and positive")
    if not math.isfinite(minimum_radius_um) or minimum_radius_um <= 0.0:
        raise LambadaMajorVesselError("minimum_radius_um must be finite and positive")
    if edge_indices.dtype.kind not in "iu":
        raise LambadaMajorVesselError("edge_geometry_indices must contain integers")
    if annotations.dtype.kind not in "iu":
        raise LambadaMajorVesselError("source_annotation_ids must contain integers")
    annotations_i64 = np.asarray(annotations, dtype=np.int64)
    if annotations_i64.size and (
        int(np.min(annotations_i64)) < 0 or int(np.max(annotations_i64)) > np.iinfo(np.int32).max
    ):
        raise LambadaMajorVesselError("source annotation IDs do not fit int32")

    edge_indices_i64 = np.asarray(edge_indices, dtype=np.int64)
    if edge_indices_i64.size:
        starts = edge_indices_i64[:, 0]
        ends = edge_indices_i64[:, 1]
        if bool(np.any(starts < 0)) or bool(np.any(ends > point_count)):
            raise LambadaMajorVesselError("edge geometry range is outside the point arrays")
        if bool(np.any(ends <= starts)):
            raise LambadaMajorVesselError("edge geometry ranges must be non-empty")

    point_chunks: list[NDArray[np.float32]] = []
    radius_chunks: list[NDArray[np.float32]] = []
    annotation_chunks: list[NDArray[np.int32]] = []
    source_edges: list[int] = []
    run_offsets = [0]
    radius_threshold_voxel = minimum_radius_um / atlas_voxel_size_um
    shape = np.asarray(atlas_shape_clearmap, dtype=np.float64)

    for edge_index, (edge_start, edge_end) in enumerate(edge_indices_i64):
        start = int(edge_start)
        end = int(edge_end)
        edge_coordinates = np.asarray(coordinates[start:end], dtype=np.float64)
        edge_radii = np.asarray(radii[start:end], dtype=np.float64)
        qualifying = np.all(np.isfinite(edge_coordinates), axis=1)
        qualifying &= np.isfinite(edge_radii)
        qualifying &= np.all(edge_coordinates >= 0.0, axis=1)
        qualifying &= np.all(edge_coordinates < shape, axis=1)
        qualifying &= edge_radii >= radius_threshold_voxel
        for block_start, block_end in _true_blocks(qualifying):
            if block_end - block_start < 2:
                continue
            source_slice = slice(start + block_start, start + block_end)
            clearmap_points = np.asarray(coordinates[source_slice], dtype=np.float32)
            point_chunks.append(np.ascontiguousarray(clearmap_points[:, (1, 0, 2)]))
            radius_chunks.append(
                np.ascontiguousarray(
                    (
                        np.asarray(radii[source_slice], dtype=np.float64) * atlas_voxel_size_um
                    ).astype(np.float32)
                )
            )
            annotation_chunks.append(
                np.ascontiguousarray(np.asarray(annotations_i64[source_slice], dtype=np.int32))
            )
            source_edges.append(edge_index)
            run_offsets.append(run_offsets[-1] + block_end - block_start)

    if point_chunks:
        output_points = np.concatenate(point_chunks).astype(np.float32, copy=False)
        output_radii = np.concatenate(radius_chunks).astype(np.float32, copy=False)
        output_annotations = np.concatenate(annotation_chunks).astype(np.int32, copy=False)
    else:
        output_points = np.empty((0, 3), dtype=np.float32)
        output_radii = np.empty((0,), dtype=np.float32)
        output_annotations = np.empty((0,), dtype=np.int32)
    return LambadaMajorVesselAssetData(
        points_asr_voxel_f32=np.ascontiguousarray(output_points),
        radii_um_f32=np.ascontiguousarray(output_radii),
        source_annotation_ids_i32=np.ascontiguousarray(output_annotations),
        run_offsets_i64=np.asarray(run_offsets, dtype=np.int64),
        source_edge_indices_i32=np.asarray(source_edges, dtype=np.int32),
    )


def _true_blocks(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    padded = np.empty(mask.size + 2, dtype=np.bool_)
    padded[0] = False
    padded[-1] = False
    padded[1:-1] = mask
    transitions = np.diff(padded.astype(np.int8, copy=False))
    starts = np.flatnonzero(transitions == 1)
    ends = np.flatnonzero(transitions == -1)
    return [(int(start), int(end)) for start, end in zip(starts, ends, strict=True)]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_pinned_source(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise LambadaMajorVesselError("source graph must be a regular non-symlink file")
    if path.stat().st_size != SOURCE_SIZE_BYTES:
        raise LambadaMajorVesselError("source graph byte count does not match the pinned file")
    if _hash_file(path) != SOURCE_SHA256:
        raise LambadaMajorVesselError("source graph SHA-256 does not match the pinned file")
    with path.open("rb") as stream:
        if stream.read(6) != b"\xe2\x9b\xbe gt":
            raise LambadaMajorVesselError("pinned source does not have the graph-tool magic")


def extract_pinned_lambada_major_vessels(
    source_path: str | Path,
) -> tuple[LambadaMajorVesselAssetData, LambadaExtractionReport]:
    """Extract the audited derivative from the exact 12 GB P60_606 graph."""

    path = Path(source_path).expanduser()
    _verify_pinned_source(path)

    coordinates = np.memmap(
        path,
        mode="r",
        dtype="<f8",
        offset=COORDINATES_ATLAS_RAW_OFFSET,
        shape=(SOURCE_GEOMETRY_POINT_COUNT, 3),
    )
    radii = np.memmap(
        path,
        mode="r",
        dtype="<f8",
        offset=RADII_ATLAS_RAW_OFFSET,
        shape=(SOURCE_GEOMETRY_POINT_COUNT,),
    )
    annotations = np.memmap(
        path,
        mode="r",
        dtype="<i8",
        offset=ANNOTATIONS_RAW_OFFSET,
        shape=(SOURCE_GEOMETRY_POINT_COUNT,),
    )
    index_record_dtype = np.dtype([("length", "<u8"), ("values", "<i8", (2,))])
    index_records = np.memmap(
        path,
        mode="r",
        dtype=index_record_dtype,
        offset=EDGE_GEOMETRY_INDICES_PAYLOAD_OFFSET,
        shape=(SOURCE_EDGE_COUNT,),
    )
    if not bool(np.all(index_records["length"] == 2)):
        raise LambadaMajorVesselError("pinned edge_geometry_indices vector widths changed")
    edge_indices = index_records["values"]
    if (
        int(edge_indices[0, 0]) != 0
        or int(edge_indices[-1, 1]) != SOURCE_GEOMETRY_POINT_COUNT
        or not bool(np.all(edge_indices[:, 1] > edge_indices[:, 0]))
        or not bool(np.all(edge_indices[1:, 0] == edge_indices[:-1, 1]))
    ):
        raise LambadaMajorVesselError("pinned edge geometry ranges are not contiguous")
    edge_radii = np.memmap(
        path,
        mode="r",
        dtype="<f8",
        offset=EDGE_RADII_ATLAS_RAW_OFFSET,
        shape=(SOURCE_EDGE_COUNT,),
    )
    candidate_edges = np.flatnonzero(edge_radii >= MINIMUM_RADIUS_ATLAS_VOXEL)
    if candidate_edges.size != EXPECTED_CANDIDATE_EDGE_COUNT:
        raise LambadaMajorVesselError("pinned candidate edge count changed")

    point_chunks: list[NDArray[np.float32]] = []
    radius_chunks: list[NDArray[np.float32]] = []
    annotation_chunks: list[NDArray[np.int32]] = []
    source_edge_chunks: list[int] = []
    run_offsets = [0]
    qualifying_in_bounds_points = 0
    selected_path_length_f64 = 0.0
    edges_with_runs: set[int] = set()
    shape = np.asarray(ATLAS_SHAPE_CLEARMAP, dtype=np.float64)

    for edge_value in candidate_edges:
        edge_index = int(edge_value)
        start = int(edge_indices[edge_index, 0])
        end = int(edge_indices[edge_index, 1])
        edge_coordinates = np.asarray(coordinates[start:end])
        edge_radii_values = np.asarray(radii[start:end])
        qualifying = np.all(np.isfinite(edge_coordinates), axis=1)
        qualifying &= np.isfinite(edge_radii_values)
        qualifying &= np.all(edge_coordinates >= 0.0, axis=1)
        qualifying &= np.all(edge_coordinates < shape, axis=1)
        qualifying &= edge_radii_values >= MINIMUM_RADIUS_ATLAS_VOXEL
        qualifying_in_bounds_points += int(np.count_nonzero(qualifying))
        for block_start, block_end in _true_blocks(qualifying):
            if block_end - block_start < 2:
                continue
            source_slice = slice(start + block_start, start + block_end)
            clearmap_points_f64 = np.asarray(coordinates[source_slice])
            deltas = np.diff(clearmap_points_f64, axis=0)
            selected_path_length_f64 += float(
                np.sum(np.linalg.norm(deltas, axis=1), dtype=np.float64) * ATLAS_VOXEL_SIZE_UM
            )
            points_f32 = np.asarray(clearmap_points_f64, dtype=np.float32)
            point_chunks.append(np.ascontiguousarray(points_f32[:, (1, 0, 2)]))
            radius_chunks.append(
                np.ascontiguousarray(
                    (
                        np.asarray(radii[source_slice], dtype=np.float64) * ATLAS_VOXEL_SIZE_UM
                    ).astype(np.float32)
                )
            )
            annotation_values = np.asarray(annotations[source_slice])
            if annotation_values.size and (
                int(np.min(annotation_values)) < np.iinfo(np.int32).min
                or int(np.max(annotation_values)) > np.iinfo(np.int32).max
            ):
                raise LambadaMajorVesselError("source annotation ID does not fit int32")
            annotation_chunks.append(
                np.ascontiguousarray(annotation_values.astype(np.int32, copy=False))
            )
            source_edge_chunks.append(edge_index)
            edges_with_runs.add(edge_index)
            run_offsets.append(run_offsets[-1] + block_end - block_start)

    data = LambadaMajorVesselAssetData(
        points_asr_voxel_f32=np.ascontiguousarray(np.concatenate(point_chunks)),
        radii_um_f32=np.ascontiguousarray(np.concatenate(radius_chunks)),
        source_annotation_ids_i32=np.ascontiguousarray(np.concatenate(annotation_chunks)),
        run_offsets_i64=np.asarray(run_offsets, dtype=np.int64),
        source_edge_indices_i32=np.asarray(source_edge_chunks, dtype=np.int32),
    )
    asset_length_f32 = _polyline_length_um(
        data.points_asr_voxel_f32 * np.float32(ATLAS_VOXEL_SIZE_UM),
        data.run_offsets_i64,
    )
    report = LambadaExtractionReport(
        candidate_edges_by_source_edge_max=int(candidate_edges.size),
        qualifying_in_bounds_points=qualifying_in_bounds_points,
        output_points=int(data.points_asr_voxel_f32.shape[0]),
        output_segments=int(data.points_asr_voxel_f32.shape[0] - len(source_edge_chunks)),
        output_runs=len(source_edge_chunks),
        source_edges_with_runs=len(edges_with_runs),
        selected_path_length_um_source_f64=selected_path_length_f64,
        asset_path_length_um_f32=asset_length_f32,
    )
    _validate_expected_report(report)
    return data, report


def _validate_expected_report(report: LambadaExtractionReport) -> None:
    expected = (
        EXPECTED_CANDIDATE_EDGE_COUNT,
        EXPECTED_QUALIFYING_IN_BOUNDS_POINT_COUNT,
        EXPECTED_RUN_POINT_COUNT,
        EXPECTED_SEGMENT_COUNT,
        EXPECTED_RUN_COUNT,
        EXPECTED_SOURCE_EDGES_WITH_RUNS,
    )
    observed = (
        report.candidate_edges_by_source_edge_max,
        report.qualifying_in_bounds_points,
        report.output_points,
        report.output_segments,
        report.output_runs,
        report.source_edges_with_runs,
    )
    if observed != expected:
        raise LambadaMajorVesselError(
            f"extraction statistics changed: expected {expected}, observed {observed}"
        )


def _polyline_length_um(
    points_asr_um: NDArray[np.generic],
    run_offsets: NDArray[np.generic],
) -> float:
    points = np.asarray(points_asr_um, dtype=np.float64)
    offsets = np.asarray(run_offsets, dtype=np.int64)
    total = 0.0
    for start_value, end_value in pairwise(offsets):
        start = int(start_value)
        end = int(end_value)
        total += float(np.sum(np.linalg.norm(np.diff(points[start:end], axis=0), axis=1)))
    return total


def write_deterministic_npz(
    output_path: str | Path,
    data: LambadaMajorVesselAssetData,
) -> tuple[str, int]:
    """Write fixed-timestamp, fixed-order compressed NPY members atomically."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    arrays = data.arrays()
    unknown = set(arrays) - set(ARRAY_DTYPES)
    if unknown:
        raise LambadaMajorVesselError(f"unexpected output arrays: {sorted(unknown)}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
            strict_timestamps=True,
        ) as archive:
            for name in sorted(ARRAY_DTYPES):
                expected_dtype = ARRAY_DTYPES[name]
                array = np.ascontiguousarray(arrays[name], dtype=expected_dtype)
                buffer = io.BytesIO()
                np.save(buffer, array, allow_pickle=False)
                info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(
                    info,
                    buffer.getvalue(),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
        temporary.chmod(0o644)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return _hash_file(output), output.stat().st_size


def build_asset_manifest(
    *,
    asset_sha256: str,
    asset_size_bytes: int,
    data: LambadaMajorVesselAssetData,
    report: LambadaExtractionReport,
) -> dict[str, object]:
    """Build the canonical attribution, schema, and extraction manifest."""

    _validate_expected_report(report)
    if (asset_sha256, asset_size_bytes) != (ASSET_SHA256, ASSET_SIZE_BYTES):
        raise LambadaMajorVesselError(
            "derived asset bytes differ from the reviewed reproducible build"
        )
    arrays = {
        name: {
            "dtype": str(ARRAY_DTYPES[name]),
            "shape": list(data.arrays()[name].shape),
        }
        for name in sorted(ARRAY_DTYPES)
    }
    return {
        "schema_version": ASSET_SCHEMA_VERSION,
        "asset": {
            "filename": ASSET_FILENAME,
            "sha256": asset_sha256,
            "size_bytes": asset_size_bytes,
            "arrays": arrays,
        },
        "source": _expected_source_manifest(),
        "extraction": {
            "algorithm_version": EXTRACTION_ALGORITHM_VERSION,
            "atlas_identifier": ATLAS_IDENTIFIER,
            "atlas_version": ATLAS_VERSION,
            "source_coordinate_order": ["ClearMap axis 0", "ClearMap axis 1", "ClearMap axis 2"],
            "output_frame": "BRAINGLOBE_VOXEL_ASR",
            "output_axis_order": ["AP", "DV", "ML"],
            "atlas_shape_asr": list(ATLAS_SHAPE_ASR),
            "atlas_voxel_size_um": [ATLAS_VOXEL_SIZE_UM] * 3,
            "voxel_anchor": (
                "index anchor: physical_um = continuous_voxel * 25; no half-voxel shift"
            ),
            "minimum_radius_um": MINIMUM_RADIUS_UM,
            "minimum_diameter_um": MINIMUM_DIAMETER_UM,
            "run_rule": (
                "maximal consecutive blocks of at least two source edge-geometry points for "
                "which every point is finite, in bounds, and radius >= 15 um"
            ),
            "out_of_bounds_rule": "split and drop; never clip or interpolate",
            "source_annotation_semantics": (
                "coarse source ancestor IDs; use the installed atlas annotation at display or "
                "interaction coordinates for current region identity"
            ),
            "radius_semantics": (
                "source radii_atlas * 25 um; source used a mean resampling scale, not a local "
                "Jacobian correction"
            ),
            "statistics": {
                "candidate_edges_by_source_edge_max": report.candidate_edges_by_source_edge_max,
                "qualifying_in_bounds_points": report.qualifying_in_bounds_points,
                "output_points": report.output_points,
                "output_segments": report.output_segments,
                "output_runs": report.output_runs,
                "source_edges_with_runs": report.source_edges_with_runs,
                "selected_path_length_um_source_f64": (report.selected_path_length_um_source_f64),
                "asset_path_length_um_f32": report.asset_path_length_um_f32,
            },
        },
        "limitations": list(MANDATORY_LIMITATIONS),
    }


def _expected_source_manifest() -> dict[str, object]:
    return {
        "dataset_title": "Vascular graphs of the developing post-natal mouse brain",
        "authors": ["Nicolas Renier", "Elisa de Launoit", "Sophie Skriabine"],
        "specimen_id": "P60_606",
        "specimen_age": "P60",
        "specimen_sex": "unpublished",
        "specimen_side": "unpublished",
        "record_doi": SOURCE_RECORD_DOI,
        "concept_doi": SOURCE_CONCEPT_DOI,
        "record_url": SOURCE_RECORD_URL,
        "license": SOURCE_LICENSE,
        "license_url": SOURCE_LICENSE_URL,
        "paper_doi": SOURCE_PAPER_DOI,
        "paper_url": SOURCE_PAPER_URL,
        "distributed_archive": {
            "filename": SOURCE_ARCHIVE_FILENAME,
            "size_bytes": SOURCE_ARCHIVE_SIZE_BYTES,
            "sha256": SOURCE_ARCHIVE_SHA256,
            "md5": SOURCE_ARCHIVE_MD5,
        },
        "extracted_graph": {
            "filename": SOURCE_FILENAME,
            "size_bytes": SOURCE_SIZE_BYTES,
            "sha256": SOURCE_SHA256,
            "md5": SOURCE_MD5,
        },
    }


def write_asset_manifest(output_path: str | Path, manifest: Mapping[str, object]) -> None:
    """Write canonical JSON atomically."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _reject_duplicate_json_keys(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LambadaMajorVesselError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def _read_manifest(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise LambadaMajorVesselError("vessel manifest must be a regular non-symlink file")
    if path.stat().st_size > 128 * 1024:
        raise LambadaMajorVesselError("vessel manifest is unexpectedly large")
    try:
        parsed = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LambadaMajorVesselError("vessel manifest is not valid UTF-8 JSON") from error
    if not isinstance(parsed, dict):
        raise LambadaMajorVesselError("vessel manifest root must be an object")
    return cast(dict[str, object], parsed)


def _mapping(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise LambadaMajorVesselError(f"manifest {name} must be an object")
    return cast(dict[str, object], value)


def _integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LambadaMajorVesselError(f"manifest {name} must be an integer")
    return value


def _number(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LambadaMajorVesselError(f"manifest {name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise LambadaMajorVesselError(f"manifest {name} must be finite")
    return result


def _validate_manifest(manifest: dict[str, object], asset_path: Path) -> tuple[str, float]:
    if set(manifest) != {"schema_version", "asset", "source", "extraction", "limitations"}:
        raise LambadaMajorVesselError("vessel manifest root fields changed")
    if _integer(manifest["schema_version"], name="schema_version") != ASSET_SCHEMA_VERSION:
        raise LambadaMajorVesselError("vessel manifest schema version is unsupported")
    if manifest["source"] != _expected_source_manifest():
        raise LambadaMajorVesselError("vessel source provenance does not match the reviewed source")
    limitations = manifest["limitations"]
    if limitations != list(MANDATORY_LIMITATIONS):
        raise LambadaMajorVesselError("mandatory vessel limitations are missing or changed")

    asset = _mapping(manifest["asset"], name="asset")
    if set(asset) != {"filename", "sha256", "size_bytes", "arrays"}:
        raise LambadaMajorVesselError("vessel asset manifest fields changed")
    if asset["filename"] != ASSET_FILENAME:
        raise LambadaMajorVesselError("vessel asset filename is not the reviewed filename")
    expected_size = _integer(asset["size_bytes"], name="asset.size_bytes")
    expected_hash = asset["sha256"]
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise LambadaMajorVesselError("vessel asset SHA-256 is invalid")
    if (expected_hash, expected_size) != (ASSET_SHA256, ASSET_SIZE_BYTES):
        raise LambadaMajorVesselError("vessel asset identity is not the reviewed build")
    if asset_path.is_symlink() or not asset_path.is_file():
        raise LambadaMajorVesselError("vessel asset must be a regular non-symlink file")
    if asset_path.stat().st_size != expected_size or expected_size > 32 * 1024 * 1024:
        raise LambadaMajorVesselError("vessel asset byte count is invalid")
    if _hash_file(asset_path) != expected_hash:
        raise LambadaMajorVesselError("vessel asset SHA-256 does not match its manifest")

    extraction = _mapping(manifest["extraction"], name="extraction")
    required_exact = {
        "algorithm_version": EXTRACTION_ALGORITHM_VERSION,
        "atlas_identifier": ATLAS_IDENTIFIER,
        "atlas_version": ATLAS_VERSION,
        "source_coordinate_order": ["ClearMap axis 0", "ClearMap axis 1", "ClearMap axis 2"],
        "output_frame": "BRAINGLOBE_VOXEL_ASR",
        "output_axis_order": ["AP", "DV", "ML"],
        "atlas_shape_asr": list(ATLAS_SHAPE_ASR),
        "atlas_voxel_size_um": [ATLAS_VOXEL_SIZE_UM] * 3,
        "voxel_anchor": "index anchor: physical_um = continuous_voxel * 25; no half-voxel shift",
        "minimum_radius_um": MINIMUM_RADIUS_UM,
        "minimum_diameter_um": MINIMUM_DIAMETER_UM,
        "run_rule": (
            "maximal consecutive blocks of at least two source edge-geometry points for which "
            "every point is finite, in bounds, and radius >= 15 um"
        ),
        "out_of_bounds_rule": "split and drop; never clip or interpolate",
        "source_annotation_semantics": (
            "coarse source ancestor IDs; use the installed atlas annotation at display or "
            "interaction coordinates for current region identity"
        ),
        "radius_semantics": (
            "source radii_atlas * 25 um; source used a mean resampling scale, not a local "
            "Jacobian correction"
        ),
    }
    if set(extraction) != set(required_exact) | {"statistics"}:
        raise LambadaMajorVesselError("vessel extraction manifest fields changed")
    for key, expected in required_exact.items():
        if extraction[key] != expected:
            raise LambadaMajorVesselError(f"vessel extraction field {key} changed")
    statistics = _mapping(extraction["statistics"], name="extraction.statistics")
    expected_counts = {
        "candidate_edges_by_source_edge_max": EXPECTED_CANDIDATE_EDGE_COUNT,
        "qualifying_in_bounds_points": EXPECTED_QUALIFYING_IN_BOUNDS_POINT_COUNT,
        "output_points": EXPECTED_RUN_POINT_COUNT,
        "output_segments": EXPECTED_SEGMENT_COUNT,
        "output_runs": EXPECTED_RUN_COUNT,
        "source_edges_with_runs": EXPECTED_SOURCE_EDGES_WITH_RUNS,
    }
    if set(statistics) != set(expected_counts) | {
        "selected_path_length_um_source_f64",
        "asset_path_length_um_f32",
    }:
        raise LambadaMajorVesselError("vessel extraction statistics fields changed")
    for key, expected in expected_counts.items():
        if _integer(statistics[key], name=f"statistics.{key}") != expected:
            raise LambadaMajorVesselError(f"vessel extraction statistic {key} changed")
    asset_path_length = _number(
        statistics["asset_path_length_um_f32"], name="statistics.asset_path_length_um_f32"
    )
    _number(
        statistics["selected_path_length_um_source_f64"],
        name="statistics.selected_path_length_um_source_f64",
    )

    arrays = _mapping(asset["arrays"], name="asset.arrays")
    expected_shapes = {
        "points_asr_voxel_f32": [EXPECTED_RUN_POINT_COUNT, 3],
        "radii_um_f32": [EXPECTED_RUN_POINT_COUNT],
        "source_annotation_ids_i32": [EXPECTED_RUN_POINT_COUNT],
        "run_offsets_i64": [EXPECTED_RUN_COUNT + 1],
        "source_edge_indices_i32": [EXPECTED_RUN_COUNT],
    }
    if set(arrays) != set(ARRAY_DTYPES):
        raise LambadaMajorVesselError("vessel asset array inventory changed")
    for name, expected_shape in expected_shapes.items():
        descriptor = _mapping(arrays[name], name=f"asset.arrays.{name}")
        if descriptor != {"dtype": str(ARRAY_DTYPES[name]), "shape": expected_shape}:
            raise LambadaMajorVesselError(f"vessel array descriptor {name} changed")
    return expected_hash, asset_path_length


def _validate_zip_members(asset_path: Path) -> None:
    expected_names = {f"{name}.npy" for name in ARRAY_DTYPES}
    try:
        with zipfile.ZipFile(asset_path) as archive:
            infos = archive.infolist()
            if {info.filename for info in infos} != expected_names or len(infos) != len(
                expected_names
            ):
                raise LambadaMajorVesselError("vessel NPZ member inventory changed")
            if any(info.file_size > 4 * 1024 * 1024 for info in infos):
                raise LambadaMajorVesselError("vessel NPZ member is unexpectedly large")
            if sum(info.file_size for info in infos) > 8 * 1024 * 1024:
                raise LambadaMajorVesselError("vessel NPZ expands beyond its reviewed bound")
    except (OSError, zipfile.BadZipFile) as error:
        raise LambadaMajorVesselError("vessel asset is not a valid NPZ archive") from error


def _validate_loaded_asset(
    arrays: Mapping[str, NDArray[np.generic]],
    *,
    expected_path_length_um: float,
) -> LambadaMajorVesselAssetData:
    if set(arrays) != set(ARRAY_DTYPES):
        raise LambadaMajorVesselError("loaded vessel array inventory changed")
    for name, expected_dtype in ARRAY_DTYPES.items():
        if arrays[name].dtype != expected_dtype:
            raise LambadaMajorVesselError(f"loaded vessel array {name} has the wrong dtype")
        if not arrays[name].flags.c_contiguous:
            raise LambadaMajorVesselError(f"loaded vessel array {name} is not C-contiguous")
    points = cast(NDArray[np.float32], arrays["points_asr_voxel_f32"])
    radii = cast(NDArray[np.float32], arrays["radii_um_f32"])
    annotations = cast(NDArray[np.int32], arrays["source_annotation_ids_i32"])
    offsets = cast(NDArray[np.int64], arrays["run_offsets_i64"])
    source_edges = cast(NDArray[np.int32], arrays["source_edge_indices_i32"])
    if points.shape != (EXPECTED_RUN_POINT_COUNT, 3):
        raise LambadaMajorVesselError("loaded vessel points have the wrong shape")
    if radii.shape != (EXPECTED_RUN_POINT_COUNT,) or annotations.shape != radii.shape:
        raise LambadaMajorVesselError("loaded vessel point attributes have the wrong shape")
    if offsets.shape != (EXPECTED_RUN_COUNT + 1,) or source_edges.shape != (EXPECTED_RUN_COUNT,):
        raise LambadaMajorVesselError("loaded vessel run arrays have the wrong shape")
    if not bool(np.all(np.isfinite(points))) or not bool(np.all(np.isfinite(radii))):
        raise LambadaMajorVesselError("loaded vessel geometry contains non-finite values")
    shape = np.asarray(ATLAS_SHAPE_ASR, dtype=np.float32)
    if bool(np.any(points < 0.0)) or bool(np.any(points >= shape)):
        raise LambadaMajorVesselError("loaded vessel point is outside the atlas")
    if bool(np.any(radii < np.float32(MINIMUM_RADIUS_UM))):
        raise LambadaMajorVesselError("loaded vessel point is below the radius threshold")
    if bool(np.any(annotations < 0)):
        raise LambadaMajorVesselError("loaded vessel source annotation ID is negative")
    if int(offsets[0]) != 0 or int(offsets[-1]) != EXPECTED_RUN_POINT_COUNT:
        raise LambadaMajorVesselError("loaded vessel run offsets do not span the point array")
    if not bool(np.all(np.diff(offsets) >= 2)):
        raise LambadaMajorVesselError("loaded vessel run is shorter than one segment")
    if bool(np.any(source_edges < 0)) or bool(np.any(source_edges >= SOURCE_EDGE_COUNT)):
        raise LambadaMajorVesselError("loaded vessel source edge index is invalid")
    if bool(np.any(source_edges[1:] < source_edges[:-1])):
        raise LambadaMajorVesselError("loaded vessel source edge order is not deterministic")
    observed_length = _polyline_length_um(points * np.float32(ATLAS_VOXEL_SIZE_UM), offsets)
    if not math.isclose(observed_length, expected_path_length_um, rel_tol=0.0, abs_tol=1e-4):
        raise LambadaMajorVesselError("loaded vessel path length does not match its manifest")
    return LambadaMajorVesselAssetData(points, radii, annotations, offsets, source_edges)


def bundled_asset_paths() -> tuple[Path, Path]:
    """Return the installed compact asset and adjacent manifest paths."""

    asset_root = Path(__file__).resolve().parent.parent / "assets" / "vasculature"
    return asset_root / ASSET_FILENAME, asset_root / MANIFEST_FILENAME


def load_lambada_major_vessels(
    asset_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> LambadaMajorVesselGraph:
    """Load, verify, physically scale, and freeze the compact display graph."""

    bundled_asset, bundled_manifest = bundled_asset_paths()
    asset = bundled_asset if asset_path is None else Path(asset_path)
    manifest = bundled_manifest if manifest_path is None else Path(manifest_path)
    parsed_manifest = _read_manifest(manifest)
    asset_sha256, expected_path_length = _validate_manifest(parsed_manifest, asset)
    _validate_zip_members(asset)
    try:
        with np.load(asset, allow_pickle=False) as archive:
            loaded_arrays = {name: np.asarray(archive[name]) for name in archive.files}
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise LambadaMajorVesselError("vessel asset arrays could not be loaded") from error
    disk_data = _validate_loaded_asset(
        loaded_arrays,
        expected_path_length_um=expected_path_length,
    )
    points_asr_um = np.ascontiguousarray(
        disk_data.points_asr_voxel_f32 * np.float32(ATLAS_VOXEL_SIZE_UM)
    )
    arrays_to_freeze: tuple[NDArray[np.generic], ...] = (
        points_asr_um,
        disk_data.radii_um_f32,
        disk_data.source_annotation_ids_i32,
        disk_data.run_offsets_i64,
        disk_data.source_edge_indices_i32,
    )
    for array in arrays_to_freeze:
        array.setflags(write=False)
    source = _expected_source_manifest()
    authors = cast(list[str], source["authors"])
    provenance = LambadaMajorVesselProvenance(
        dataset_title=cast(str, source["dataset_title"]),
        authors=tuple(authors),
        specimen_id=cast(str, source["specimen_id"]),
        record_doi=SOURCE_RECORD_DOI,
        record_url=SOURCE_RECORD_URL,
        license=SOURCE_LICENSE,
        license_url=SOURCE_LICENSE_URL,
        source_sha256=SOURCE_SHA256,
        asset_sha256=asset_sha256,
        extraction_algorithm_version=EXTRACTION_ALGORITHM_VERSION,
        minimum_radius_um=MINIMUM_RADIUS_UM,
        limitations=MANDATORY_LIMITATIONS,
    )
    return LambadaMajorVesselGraph(
        points_asr_um=points_asr_um,
        radii_um=disk_data.radii_um_f32,
        source_annotation_ids=disk_data.source_annotation_ids_i32,
        run_offsets=disk_data.run_offsets_i64,
        source_edge_indices=disk_data.source_edge_indices_i32,
        provenance=provenance,
    )
