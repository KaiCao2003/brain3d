"""Exact finite-segment traversal through a BrainGlobe annotation volume.

The implementation clips in continuous voxel coordinates and then applies a
three-dimensional Amanatides--Woo walk.  It never samples an arbitrary number
of points, so one-voxel structures cannot disappear between samples.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral
from typing import Any, Final, Literal

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.analysis.atlas_axis_order import (
    brain_globe_physical_ap_dv_ml_to_domain_ap_ml_dv,
    domain_ap_ml_dv_to_brain_globe_physical_ap_dv_ml,
)
from mouse_brain_planner.domain.atlas_models import AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobeVoxelIndex
from mouse_brain_planner.domain.region_models import (
    AtlasPhysicalPointAPMLDV,
    AtlasRecordingSitePoint,
    CalibratedProbeShankSegment,
    ProbeRegionAnalysis,
    RecordingSiteRegionAssignment,
    RegionTraversalSegment,
    RegionTraversalVoxelInterval,
    TraversalHemisphere,
    TraversalLocation,
)

REGION_TRAVERSAL_ALGORITHM_VERSION: Final = "amanatides-woo-clipped-half-open-v1"
TIE_BREAK_RULE: Final[
    Literal[
        "half-open-lower-inclusive; negative crossings own following negative-side interval; "
        "simultaneous boundary crossings advance every tied axis"
    ]
] = (
    "half-open-lower-inclusive; negative crossings own following negative-side interval; "
    "simultaneous boundary crossings advance every tied axis"
)

_FLOAT_EPSILON = float(np.finfo(np.float64).eps)


class RegionTraversalInputError(ValueError):
    """Raised when scientific traversal input is ambiguous or inconsistent."""


@dataclass(frozen=True, slots=True)
class _RawVoxelInterval:
    index_ap_dv_ml: tuple[int, int, int]
    entry_t: float
    exit_t: float


def analyze_probe_regions(
    *,
    annotation: NDArray[np.integer[Any]],
    metadata: AtlasMetadata,
    annotation_sha256: str,
    annotation_version: str,
    segment: CalibratedProbeShankSegment,
    regions: Mapping[int, RegionRecord],
    recording_sites: Sequence[AtlasRecordingSitePoint] = (),
) -> ProbeRegionAnalysis:
    """Traverse one calibrated finite shank and assign its recording sites.

    The annotation array is interpreted only in BrainGlobe ``[AP, DV, ML]``
    order.  Public points remain in canonical domain ``AP, ML, DV`` order and
    cross the single explicit permutation boundary in :mod:`atlas_axis_order`.
    ID 0 is retained as ``outside-brain``; it is never discarded or replaced
    by a neighboring structure.
    """

    volume = _validate_inputs(
        annotation=annotation,
        metadata=metadata,
        annotation_sha256=annotation_sha256,
        annotation_version=annotation_version,
        segment=segment,
        regions=regions,
        recording_sites=recording_sites,
    )
    normalized_regions = _normalize_regions(regions)

    entry_physical_ap_dv_ml = np.asarray(
        domain_ap_ml_dv_to_brain_globe_physical_ap_dv_ml(segment.entry),
        dtype=np.float64,
    )
    tip_physical_ap_dv_ml = np.asarray(
        domain_ap_ml_dv_to_brain_globe_physical_ap_dv_ml(segment.tip),
        dtype=np.float64,
    )
    physical_delta = tip_physical_ap_dv_ml - entry_physical_ap_dv_ml
    total_length_um = float(np.linalg.norm(physical_delta))
    if not math.isfinite(total_length_um) or total_length_um <= 0:
        raise RegionTraversalInputError("probe entry-to-tip distance must be finite and positive")

    spacing_ap_dv_ml = np.asarray(metadata.resolution_um, dtype=np.float64)
    entry_voxel_ap_dv_ml = entry_physical_ap_dv_ml / spacing_ap_dv_ml
    tip_voxel_ap_dv_ml = tip_physical_ap_dv_ml / spacing_ap_dv_ml
    if not np.all(np.isfinite(entry_voxel_ap_dv_ml)) or not np.all(
        np.isfinite(tip_voxel_ap_dv_ml)
    ):
        raise RegionTraversalInputError("continuous voxel endpoints must be finite")

    shape_ap_dv_ml = metadata.shape_voxels
    clipped = _clip_segment_to_half_open_volume(
        entry_voxel_ap_dv_ml,
        tip_voxel_ap_dv_ml,
        shape_ap_dv_ml,
    )
    starts_outside = not _point_inside_half_open(entry_voxel_ap_dv_ml, shape_ap_dv_ml)
    ends_outside = not _point_inside_half_open(tip_voxel_ap_dv_ml, shape_ap_dv_ml)
    sites = _assign_sites(
        annotation=volume,
        metadata=metadata,
        segment=segment,
        regions=normalized_regions,
        recording_sites=recording_sites,
    )
    input_digest = _input_digest(
        metadata=metadata,
        annotation_sha256=annotation_sha256,
        annotation_version=annotation_version,
        segment=segment,
        regions=normalized_regions,
        recording_sites=recording_sites,
    )

    if clipped is None:
        return ProbeRegionAnalysis(
            placement_uuid=segment.placement_uuid,
            probe_model_id=segment.probe_model_id,
            probe_model_version=segment.probe_model_version,
            shank_id=segment.shank_id,
            atlas_key=metadata.atlas_key,
            atlas_version=metadata.atlas_package_version,
            atlas_metadata_sha256=metadata.metadata_sha256,
            annotation_sha256=annotation_sha256,
            annotation_version=annotation_version,
            algorithm_version=REGION_TRAVERSAL_ALGORITHM_VERSION,
            input_digest=input_digest,
            tie_break_rule=TIE_BREAK_RULE,
            total_path_length_um=total_length_um,
            intersects_atlas=False,
            starts_outside_atlas=starts_outside,
            ends_outside_atlas=ends_outside,
            clipped_entry_depth_um=None,
            clipped_exit_depth_um=None,
            clipped_path_length_um=0.0,
            outside_atlas_path_length_um=total_length_um,
            voxel_intervals=(),
            segments=(),
            site_assignments=sites,
        )

    clipped_entry_t, clipped_exit_t = clipped
    raw_intervals = _traverse_clipped_voxels(
        entry_voxel_ap_dv_ml,
        tip_voxel_ap_dv_ml,
        shape_ap_dv_ml,
        clipped_entry_t,
        clipped_exit_t,
    )
    if not raw_intervals:
        raise RuntimeError("positive-length atlas clip produced no voxel intervals")

    voxel_intervals = _materialize_voxel_intervals(
        raw_intervals=raw_intervals,
        annotation=volume,
        metadata=metadata,
        total_length_um=total_length_um,
    )
    region_segments = _run_length_encode_regions(
        voxel_intervals=voxel_intervals,
        metadata=metadata,
        segment=segment,
        regions=normalized_regions,
        entry_physical_ap_dv_ml=entry_physical_ap_dv_ml,
        physical_delta=physical_delta,
        total_length_um=total_length_um,
    )
    clipped_entry_depth_um = clipped_entry_t * total_length_um
    clipped_exit_depth_um = clipped_exit_t * total_length_um
    clipped_length_um = clipped_exit_depth_um - clipped_entry_depth_um
    outside_length_um = max(0.0, total_length_um - clipped_length_um)

    return ProbeRegionAnalysis(
        placement_uuid=segment.placement_uuid,
        probe_model_id=segment.probe_model_id,
        probe_model_version=segment.probe_model_version,
        shank_id=segment.shank_id,
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        atlas_metadata_sha256=metadata.metadata_sha256,
        annotation_sha256=annotation_sha256,
        annotation_version=annotation_version,
        algorithm_version=REGION_TRAVERSAL_ALGORITHM_VERSION,
        input_digest=input_digest,
        tie_break_rule=TIE_BREAK_RULE,
        total_path_length_um=total_length_um,
        intersects_atlas=True,
        starts_outside_atlas=starts_outside,
        ends_outside_atlas=ends_outside,
        clipped_entry_depth_um=clipped_entry_depth_um,
        clipped_exit_depth_um=clipped_exit_depth_um,
        clipped_path_length_um=clipped_length_um,
        outside_atlas_path_length_um=outside_length_um,
        voxel_intervals=voxel_intervals,
        segments=region_segments,
        site_assignments=sites,
    )


def _validate_inputs(
    *,
    annotation: object,
    metadata: object,
    annotation_sha256: object,
    annotation_version: object,
    segment: object,
    regions: object,
    recording_sites: object,
) -> NDArray[np.integer[Any]]:
    if not isinstance(metadata, AtlasMetadata):
        raise TypeError("metadata must be an AtlasMetadata")
    if not isinstance(segment, CalibratedProbeShankSegment):
        raise TypeError("segment must be a CalibratedProbeShankSegment")
    if not isinstance(annotation, np.ndarray):
        raise TypeError("annotation must be a NumPy array")
    if annotation.ndim != 3:
        raise RegionTraversalInputError(
            f"annotation volume must be three-dimensional [AP, DV, ML], got {annotation.shape}"
        )
    if annotation.shape != metadata.shape_voxels:
        raise RegionTraversalInputError(
            "annotation shape must equal atlas [AP, DV, ML] shape; "
            f"got {annotation.shape}, expected {metadata.shape_voxels}"
        )
    if np.issubdtype(annotation.dtype, np.bool_) or not np.issubdtype(
        annotation.dtype, np.integer
    ):
        raise TypeError("annotation labels must use a non-boolean integer NumPy dtype")
    expected_identity = (metadata.atlas_key, metadata.atlas_package_version)
    actual_identity = (segment.entry.atlas_key, segment.entry.atlas_version)
    if actual_identity != expected_identity:
        raise RegionTraversalInputError(
            f"segment atlas identity {actual_identity} does not match {expected_identity}"
        )
    if (
        not isinstance(annotation_sha256, str)
        or len(annotation_sha256) != 64
        or any(character not in "0123456789abcdef" for character in annotation_sha256)
    ):
        raise RegionTraversalInputError("annotation_sha256 must be 64 lowercase hexadecimal chars")
    if not isinstance(annotation_version, str) or not annotation_version.strip():
        raise RegionTraversalInputError("annotation_version must be non-empty text")
    if not isinstance(regions, Mapping):
        raise TypeError("regions must map structure IDs to RegionRecord values")
    if isinstance(recording_sites, (str, bytes)) or not isinstance(recording_sites, Sequence):
        raise TypeError("recording_sites must be a sequence of AtlasRecordingSitePoint values")
    for site in recording_sites:
        if not isinstance(site, AtlasRecordingSitePoint):
            raise TypeError("recording_sites must contain only AtlasRecordingSitePoint values")
    return annotation


def _normalize_regions(regions: Mapping[int, RegionRecord]) -> dict[int, RegionRecord]:
    normalized: dict[int, RegionRecord] = {}
    for raw_structure_id, region in regions.items():
        if isinstance(raw_structure_id, bool) or not isinstance(raw_structure_id, Integral):
            raise TypeError("region mapping keys must be non-boolean integers")
        structure_id = int(raw_structure_id)
        if structure_id <= 0:
            raise RegionTraversalInputError(
                "region metadata must contain only positive IDs; annotation ID 0 is reserved"
            )
        if not isinstance(region, RegionRecord):
            raise TypeError("region mapping values must be RegionRecord instances")
        if region.structure_id != structure_id:
            raise RegionTraversalInputError(
                f"region mapping key {structure_id} does not match record {region.structure_id}"
            )
        normalized[structure_id] = region
    return normalized


def _clip_segment_to_half_open_volume(
    entry_voxel: NDArray[np.float64],
    tip_voxel: NDArray[np.float64],
    shape: tuple[int, int, int],
) -> tuple[float, float] | None:
    """Liang--Barsky slab clip against the continuous voxel AABB.

    Lower faces are included and upper faces are excluded.  A segment lying on
    an upper face therefore has no in-volume length, while one lying on a lower
    face is owned by voxel index zero.
    """

    direction = tip_voxel - entry_voxel
    entry_t = 0.0
    exit_t = 1.0
    for axis, upper in enumerate(shape):
        start = float(entry_voxel[axis])
        delta = float(direction[axis])
        upper_float = float(upper)
        if delta == 0.0:
            if start < 0.0 or start >= upper_float:
                return None
            continue
        first = (0.0 - start) / delta
        second = (upper_float - start) / delta
        near = min(first, second)
        far = max(first, second)
        entry_t = max(entry_t, near)
        exit_t = min(exit_t, far)
        if not entry_t < exit_t:
            return None
    if exit_t <= 0.0 or entry_t >= 1.0:
        return None
    clipped_entry = max(0.0, entry_t)
    clipped_exit = min(1.0, exit_t)
    if not clipped_entry < clipped_exit:
        return None
    return (clipped_entry, clipped_exit)


def _traverse_clipped_voxels(
    entry_voxel: NDArray[np.float64],
    tip_voxel: NDArray[np.float64],
    shape: tuple[int, int, int],
    clipped_entry_t: float,
    clipped_exit_t: float,
) -> tuple[_RawVoxelInterval, ...]:
    direction = tip_voxel - entry_voxel
    clipped_entry = entry_voxel + clipped_entry_t * direction
    indices = [
        _initial_interval_index(
            coordinate=float(clipped_entry[axis]),
            direction=float(direction[axis]),
            size=shape[axis],
        )
        for axis in range(3)
    ]
    steps = [1 if value > 0 else (-1 if value < 0 else 0) for value in direction]
    next_crossing: list[float] = []
    crossing_delta: list[float] = []
    for axis in range(3):
        delta = float(direction[axis])
        if delta == 0.0:
            next_crossing.append(math.inf)
            crossing_delta.append(math.inf)
            continue
        coordinate = _snap_integer(float(clipped_entry[axis]))
        boundary = indices[axis] + 1 if delta > 0 else indices[axis]
        distance = abs(float(boundary) - coordinate)
        next_crossing.append(clipped_entry_t + distance / abs(delta))
        crossing_delta.append(1.0 / abs(delta))

    intervals: list[_RawVoxelInterval] = []
    current_t = clipped_entry_t
    maximum_iterations = sum(shape) + 3
    for _ in range(maximum_iterations):
        if not current_t < clipped_exit_t:
            break
        boundary_t = min(next_crossing)
        next_t = (
            clipped_exit_t
            if _same_boundary_time(boundary_t, clipped_exit_t)
            else min(boundary_t, clipped_exit_t)
        )
        if next_t > current_t:
            index = (indices[0], indices[1], indices[2])
            if any(value < 0 or value >= shape[axis] for axis, value in enumerate(index)):
                raise RuntimeError(f"DDA produced out-of-bounds voxel {index} for shape {shape}")
            intervals.append(
                _RawVoxelInterval(
                    index_ap_dv_ml=index,
                    entry_t=current_t,
                    exit_t=next_t,
                )
            )
        if next_t >= clipped_exit_t:
            break

        tied_axes = [
            axis
            for axis, value in enumerate(next_crossing)
            if _same_boundary_time(value, boundary_t)
        ]
        if not tied_axes:
            raise RuntimeError("DDA failed to identify the next crossed voxel boundary")
        for axis in tied_axes:
            indices[axis] += steps[axis]
            next_crossing[axis] += crossing_delta[axis]
        if next_t <= current_t and not any(
            0 <= indices[axis] < shape[axis] for axis in tied_axes
        ):
            raise RuntimeError("DDA made no positive-length progress")
        current_t = next_t
    else:
        raise RuntimeError("DDA exceeded the finite voxel-boundary iteration bound")

    if not intervals:
        return ()
    if not math.isclose(
        intervals[0].entry_t,
        clipped_entry_t,
        rel_tol=0.0,
        abs_tol=_time_tolerance(clipped_entry_t),
    ) or not math.isclose(
        intervals[-1].exit_t,
        clipped_exit_t,
        rel_tol=0.0,
        abs_tol=_time_tolerance(clipped_exit_t),
    ):
        raise RuntimeError("DDA intervals did not cover the complete clipped parameter range")
    return tuple(intervals)


def _initial_interval_index(*, coordinate: float, direction: float, size: int) -> int:
    snapped = _snap_integer(coordinate)
    nearest = round(snapped)
    on_boundary = snapped == float(nearest)
    if direction < 0 and on_boundary:
        index = nearest - 1
    else:
        index = math.floor(snapped)
    if index < 0 or index >= size:
        raise RuntimeError(
            f"clipped DDA entry coordinate {coordinate:g} resolved outside axis size {size}"
        )
    return index


def _snap_integer(value: float) -> float:
    nearest = float(round(value))
    if math.isclose(value, nearest, rel_tol=0.0, abs_tol=_time_tolerance(value)):
        return nearest
    return value


def _same_boundary_time(first: float, second: float) -> bool:
    return math.isclose(first, second, rel_tol=0.0, abs_tol=_time_tolerance(max(first, second)))


def _time_tolerance(value: float) -> float:
    return 64.0 * _FLOAT_EPSILON * max(1.0, abs(value))


def _materialize_voxel_intervals(
    *,
    raw_intervals: tuple[_RawVoxelInterval, ...],
    annotation: NDArray[np.integer[Any]],
    metadata: AtlasMetadata,
    total_length_um: float,
) -> tuple[RegionTraversalVoxelInterval, ...]:
    materialized: list[RegionTraversalVoxelInterval] = []
    for interval in raw_intervals:
        structure_id = _annotation_id(annotation, interval.index_ap_dv_ml)
        entry_depth_um = interval.entry_t * total_length_um
        exit_depth_um = interval.exit_t * total_length_um
        materialized.append(
            RegionTraversalVoxelInterval(
                voxel=BrainGlobeVoxelIndex(
                    atlas_key=metadata.atlas_key,
                    atlas_version=metadata.atlas_package_version,
                    ap=interval.index_ap_dv_ml[0],
                    dv=interval.index_ap_dv_ml[1],
                    ml=interval.index_ap_dv_ml[2],
                ),
                structure_id=structure_id,
                location=(
                    TraversalLocation.OUTSIDE_BRAIN
                    if structure_id == 0
                    else TraversalLocation.STRUCTURE
                ),
                entry_t=interval.entry_t,
                exit_t=interval.exit_t,
                entry_depth_um=entry_depth_um,
                exit_depth_um=exit_depth_um,
                length_um=exit_depth_um - entry_depth_um,
            )
        )
    return tuple(materialized)


def _run_length_encode_regions(
    *,
    voxel_intervals: tuple[RegionTraversalVoxelInterval, ...],
    metadata: AtlasMetadata,
    segment: CalibratedProbeShankSegment,
    regions: Mapping[int, RegionRecord],
    entry_physical_ap_dv_ml: NDArray[np.float64],
    physical_delta: NDArray[np.float64],
    total_length_um: float,
) -> tuple[RegionTraversalSegment, ...]:
    runs: list[RegionTraversalSegment] = []
    run_start = 0
    while run_start < len(voxel_intervals):
        structure_id = voxel_intervals[run_start].structure_id
        run_end = run_start + 1
        while (
            run_end < len(voxel_intervals)
            and voxel_intervals[run_end].structure_id == structure_id
        ):
            run_end += 1
        first = voxel_intervals[run_start]
        last = voxel_intervals[run_end - 1]
        region = _region_semantics(structure_id, regions)
        entry_point = _point_at_parameter(
            segment.entry,
            entry_physical_ap_dv_ml,
            physical_delta,
            first.entry_t,
        )
        exit_point = _point_at_parameter(
            segment.entry,
            entry_physical_ap_dv_ml,
            physical_delta,
            last.exit_t,
        )
        entry_depth_um = first.entry_t * total_length_um
        exit_depth_um = last.exit_t * total_length_um
        runs.append(
            RegionTraversalSegment(
                shank_id=segment.shank_id,
                structure_id=structure_id,
                acronym=region[0],
                name=region[1],
                structure_id_path=region[2],
                rgb=region[3],
                location=region[4],
                hemisphere=_segment_hemisphere(
                    entry_point.ml_um,
                    exit_point.ml_um,
                    metadata.midline_ml_um,
                ),
                entry_depth_um=entry_depth_um,
                exit_depth_um=exit_depth_um,
                length_um=exit_depth_um - entry_depth_um,
                entry_point=entry_point,
                exit_point=exit_point,
                voxel_count=run_end - run_start,
            )
        )
        run_start = run_end
    return tuple(runs)


def _assign_sites(
    *,
    annotation: NDArray[np.integer[Any]],
    metadata: AtlasMetadata,
    segment: CalibratedProbeShankSegment,
    regions: Mapping[int, RegionRecord],
    recording_sites: Sequence[AtlasRecordingSitePoint],
) -> tuple[RecordingSiteRegionAssignment, ...]:
    assignments: list[RecordingSiteRegionAssignment] = []
    seen: set[tuple[str, str]] = set()
    spacing = np.asarray(metadata.resolution_um, dtype=np.float64)
    expected_point_space = (
        segment.entry.atlas_key,
        segment.entry.atlas_version,
        segment.entry.frame_id,
        segment.entry.coordinate_transform_id,
    )
    for site in recording_sites:
        site_key = (site.shank_id, site.site_id)
        if site_key in seen:
            raise RegionTraversalInputError(
                f"duplicate recording site {site.site_id!r} on shank {site.shank_id!r}"
            )
        seen.add(site_key)
        actual_identity = (
            site.placement_uuid,
            site.probe_model_id,
            site.probe_model_version,
            site.shank_id,
        )
        expected_identity = (
            segment.placement_uuid,
            segment.probe_model_id,
            segment.probe_model_version,
            segment.shank_id,
        )
        if actual_identity != expected_identity:
            raise RegionTraversalInputError(
                f"recording site {site.site_id!r} does not belong to the analyzed placement/shank"
            )
        actual_point_space = (
            site.point.atlas_key,
            site.point.atlas_version,
            site.point.frame_id,
            site.point.coordinate_transform_id,
        )
        if actual_point_space != expected_point_space:
            raise RegionTraversalInputError(
                f"recording site {site.site_id!r} uses a different atlas coordinate transform"
            )

        physical = np.asarray(
            domain_ap_ml_dv_to_brain_globe_physical_ap_dv_ml(site.point),
            dtype=np.float64,
        )
        voxel_coordinate = physical / spacing
        if not _point_inside_half_open(voxel_coordinate, metadata.shape_voxels):
            assignments.append(
                RecordingSiteRegionAssignment(
                    shank_id=site.shank_id,
                    site_id=site.site_id,
                    point=site.point,
                    voxel=None,
                    structure_id=0,
                    acronym="outside-atlas",
                    name="Outside atlas volume",
                    structure_id_path=(),
                    rgb=(0, 0, 0),
                    location=TraversalLocation.OUTSIDE_ATLAS,
                    inside_atlas=False,
                    inside_brain=False,
                )
            )
            continue
        index = (
            math.floor(float(voxel_coordinate[0])),
            math.floor(float(voxel_coordinate[1])),
            math.floor(float(voxel_coordinate[2])),
        )
        structure_id = _annotation_id(annotation, index)
        region = _region_semantics(structure_id, regions)
        assignments.append(
            RecordingSiteRegionAssignment(
                shank_id=site.shank_id,
                site_id=site.site_id,
                point=site.point,
                voxel=BrainGlobeVoxelIndex(
                    atlas_key=metadata.atlas_key,
                    atlas_version=metadata.atlas_package_version,
                    ap=index[0],
                    dv=index[1],
                    ml=index[2],
                ),
                structure_id=structure_id,
                acronym=region[0],
                name=region[1],
                structure_id_path=region[2],
                rgb=region[3],
                location=region[4],
                inside_atlas=True,
                inside_brain=structure_id > 0,
            )
        )
    return tuple(assignments)


def _annotation_id(
    annotation: NDArray[np.integer[Any]],
    index_ap_dv_ml: tuple[int, int, int],
) -> int:
    raw = annotation[index_ap_dv_ml]
    if isinstance(raw, np.bool_) or not isinstance(raw, Integral):
        raise TypeError(f"annotation value at {index_ap_dv_ml} is not an integer")
    structure_id = int(raw)
    if structure_id < 0:
        raise RegionTraversalInputError(
            f"annotation value at {index_ap_dv_ml} must be non-negative, got {structure_id}"
        )
    return structure_id


def _region_semantics(
    structure_id: int,
    regions: Mapping[int, RegionRecord],
) -> tuple[str, str, tuple[int, ...], tuple[int, int, int], TraversalLocation]:
    if structure_id == 0:
        return (
            "outside-brain",
            "Outside annotated brain",
            (),
            (0, 0, 0),
            TraversalLocation.OUTSIDE_BRAIN,
        )
    try:
        region = regions[structure_id]
    except KeyError as error:
        raise RegionTraversalInputError(
            f"annotation references structure ID {structure_id} absent from region metadata"
        ) from error
    return (
        region.acronym,
        region.name,
        region.structure_id_path,
        region.rgb,
        TraversalLocation.STRUCTURE,
    )


def _point_at_parameter(
    template: AtlasPhysicalPointAPMLDV,
    entry_physical_ap_dv_ml: NDArray[np.float64],
    physical_delta_ap_dv_ml: NDArray[np.float64],
    parameter: float,
) -> AtlasPhysicalPointAPMLDV:
    values = entry_physical_ap_dv_ml + parameter * physical_delta_ap_dv_ml
    return brain_globe_physical_ap_dv_ml_to_domain_ap_ml_dv(
        ap_um=float(values[0]),
        dv_um=float(values[1]),
        ml_um=float(values[2]),
        atlas_key=template.atlas_key,
        atlas_version=template.atlas_version,
        coordinate_transform_id=template.coordinate_transform_id,
    )


def _segment_hemisphere(
    entry_ml_um: float,
    exit_ml_um: float,
    midline_ml_um: float,
) -> TraversalHemisphere:
    entry_delta = entry_ml_um - midline_ml_um
    exit_delta = exit_ml_um - midline_ml_um
    tolerance = 1e-9
    entry_midline = math.isclose(entry_delta, 0.0, rel_tol=0.0, abs_tol=tolerance)
    exit_midline = math.isclose(exit_delta, 0.0, rel_tol=0.0, abs_tol=tolerance)
    if entry_midline and exit_midline:
        return TraversalHemisphere.MIDLINE
    if not entry_midline and not exit_midline and entry_delta * exit_delta < 0:
        return TraversalHemisphere.UNKNOWN
    midpoint_delta = (entry_delta + exit_delta) / 2.0
    return TraversalHemisphere.RIGHT if midpoint_delta < 0 else TraversalHemisphere.LEFT


def _point_inside_half_open(
    point_ap_dv_ml: NDArray[np.float64],
    shape_ap_dv_ml: tuple[int, int, int],
) -> bool:
    return all(
        0.0 <= float(value) < float(shape_ap_dv_ml[axis])
        for axis, value in enumerate(point_ap_dv_ml)
    )


def _input_digest(
    *,
    metadata: AtlasMetadata,
    annotation_sha256: str,
    annotation_version: str,
    segment: CalibratedProbeShankSegment,
    regions: Mapping[int, RegionRecord],
    recording_sites: Sequence[AtlasRecordingSitePoint],
) -> str:
    payload = {
        "algorithmVersion": REGION_TRAVERSAL_ALGORITHM_VERSION,
        "atlas": {
            "key": metadata.atlas_key,
            "version": metadata.atlas_package_version,
            "metadataSha256": metadata.metadata_sha256,
            "shapeAPDVML": metadata.shape_voxels,
            "resolutionUmAPDVML": metadata.resolution_um,
        },
        "annotation": {
            "sha256": annotation_sha256,
            "version": annotation_version,
        },
        "segment": segment.model_dump(mode="json"),
        "recordingSites": [site.model_dump(mode="json") for site in recording_sites],
        "regions": [regions[key].model_dump(mode="json") for key in sorted(regions)],
        "tieBreakRule": TIE_BREAK_RULE,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
