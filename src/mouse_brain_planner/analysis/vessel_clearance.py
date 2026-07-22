"""Radius-aware clearance against an audited reference vessel graph."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.domain.vessel_clearance_models import (
    MajorVesselSourceProvenance,
    PhysicalASRPoint,
    ProbeVesselAnalysis,
    ProbeVesselConflict,
    ProbeVesselResultStatus,
    VesselConflictClassification,
    VesselRiskProfile,
)

VESSEL_CLEARANCE_ALGORITHM_VERSION: Final = "major-vessel-aabb-tapered-surface-v3"
TAPERED_SEARCH_ITERATIONS: Final = 80
CLEARANCE_NUMERICAL_TOLERANCE_UM: Final = 1e-6
NO_CONFLICT_STATEMENT: Final = (
    "No conflict detected within the loaded geometry and stated uncertainty assumptions."
)
REFERENCE_GRAPH_WARNINGS: Final[tuple[str, ...]] = (
    "Reference morphology from one cleared mouse brain; it is not subject-specific anatomy.",
    "Pial and choroidal vessels were excluded by the source dataset.",
    "Only pointwise diameter >= 30 micrometres runs are loaded; smaller vessels are filtered "
    "without vascular-type classification.",
    "The source does not support artery-versus-vein classification.",
    "A reference-graph result is not surgical navigation or an individual-animal guarantee.",
)
UNBOUNDED_SOURCE_STATEMENT: Final = (
    "Clearance absence cannot be classified because the source provenance does not bound "
    "registration and tissue-distortion uncertainty."
)
UNDERSPECIFIED_UNCERTAINTY_STATEMENT: Final = (
    "Clearance absence cannot be classified because the stated uncertainty is below the "
    "reviewed source registration and tissue-distortion bound."
)


class VesselClearanceInputError(ValueError):
    """Raised when geometry/profile inputs cannot support a bounded result."""


@dataclass(frozen=True, slots=True)
class ProbeShankASR:
    """One finite shank centerline and conservative physical envelope."""

    shank_id: str
    entry_asr_um: NDArray[np.float64]
    tip_asr_um: NDArray[np.float64]
    envelope_radius_um: float

    def __post_init__(self) -> None:
        if not self.shank_id:
            raise VesselClearanceInputError("shank ID must be nonempty")
        entry = _finite_triplet(self.entry_asr_um, "shank entry")
        tip = _finite_triplet(self.tip_asr_um, "shank tip")
        if np.array_equal(entry, tip):
            raise VesselClearanceInputError("shank entry and tip must be distinct")
        radius = float(self.envelope_radius_um)
        if not math.isfinite(radius) or radius <= 0:
            raise VesselClearanceInputError("probe envelope radius must be positive and finite")
        entry.setflags(write=False)
        tip.setflags(write=False)
        object.__setattr__(self, "entry_asr_um", entry)
        object.__setattr__(self, "tip_asr_um", tip)
        object.__setattr__(self, "envelope_radius_um", radius)


@dataclass(frozen=True, slots=True)
class RadiusBearingVesselRuns:
    """Compact point/radius runs with source-edge traceability."""

    points_asr_um: NDArray[np.float64]
    radii_um: NDArray[np.float64]
    run_offsets: NDArray[np.int64]
    source_edge_indices: NDArray[np.int64]

    def __post_init__(self) -> None:
        points = np.array(self.points_asr_um, dtype=np.float64, copy=True)
        radii = np.array(self.radii_um, dtype=np.float64, copy=True)
        offsets = np.array(self.run_offsets, dtype=np.int64, copy=True)
        edges = np.array(self.source_edge_indices, dtype=np.int64, copy=True)
        if points.ndim != 2 or points.shape[1:] != (3,) or points.shape[0] < 2:
            raise VesselClearanceInputError("vessel points must have shape [N,3] with N >= 2")
        if radii.shape != (points.shape[0],):
            raise VesselClearanceInputError("vessel radii must contain one value per point")
        if not bool(np.isfinite(points).all()) or not bool(np.isfinite(radii).all()):
            raise VesselClearanceInputError("vessel coordinates and radii must be finite")
        if bool(np.any(radii <= 0)):
            raise VesselClearanceInputError("vessel radii must be positive")
        if offsets.ndim != 1 or offsets.size < 2 or offsets[0] != 0:
            raise VesselClearanceInputError("run offsets must begin at zero and contain a run")
        if offsets[-1] != points.shape[0] or bool(np.any(np.diff(offsets) < 2)):
            raise VesselClearanceInputError("every vessel run must contain at least two points")
        if edges.shape != (offsets.size - 1,) or bool(np.any(edges < 0)):
            raise VesselClearanceInputError("source edge indices must cover every run")
        for array in (points, radii, offsets, edges):
            array.setflags(write=False)
        object.__setattr__(self, "points_asr_um", points)
        object.__setattr__(self, "radii_um", radii)
        object.__setattr__(self, "run_offsets", offsets)
        object.__setattr__(self, "source_edge_indices", edges)

    @property
    def run_count(self) -> int:
        return int(self.run_offsets.size - 1)

    @property
    def point_count(self) -> int:
        return int(self.points_asr_um.shape[0])


@dataclass(frozen=True, slots=True)
class _Segments:
    start: NDArray[np.float64]
    end: NDArray[np.float64]
    start_radius: NDArray[np.float64]
    end_radius: NDArray[np.float64]
    run_index: NDArray[np.int64]
    segment_index_in_run: NDArray[np.int64]
    source_edge_index: NDArray[np.int64]


def analyze_probe_vessel_clearance(
    *,
    shanks: tuple[ProbeShankASR, ...],
    vessels: RadiusBearingVesselRuns,
    risk_profile: VesselRiskProfile,
    provenance: MajorVesselSourceProvenance,
    maximum_conflicts: int = 1_000,
) -> ProbeVesselAnalysis:
    """Measure every shank against explicit radius-bearing finite segments.

    A conservative AABB lower bound and feasible endpoint upper bounds first
    identify every segment that can contain the global centerline/surface minimum
    or violate the envelope + margin + uncertainty bound.  Exact finite-segment
    and tapered-surface calculations then run only on that candidate subset.
    """

    if not shanks:
        raise VesselClearanceInputError("clearance analysis requires at least one shank")
    if len({shank.shank_id for shank in shanks}) != len(shanks):
        raise VesselClearanceInputError("clearance analysis contains duplicate shank IDs")
    if (
        isinstance(maximum_conflicts, bool)
        or not isinstance(maximum_conflicts, int)
        or maximum_conflicts <= 0
    ):
        raise VesselClearanceInputError("maximum conflicts must be a positive integer")
    if not math.isclose(
        risk_profile.minimum_vessel_diameter_um,
        provenance.minimum_included_diameter_um,
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise VesselClearanceInputError(
            "risk-profile diameter must equal the pointwise threshold used by the bundled asset"
        )

    segments = _segments(vessels)
    if segments.start.shape[0] == 0:
        raise VesselClearanceInputError("vessel graph contains no finite segments")
    if bool(np.any(np.all(segments.start == segments.end, axis=1))):
        raise VesselClearanceInputError("vessel runs contain a zero-length segment")
    minimum_loaded_radius = provenance.minimum_included_diameter_um / 2.0
    if bool(np.any(segments.start_radius < minimum_loaded_radius - 1e-6)) or bool(
        np.any(segments.end_radius < minimum_loaded_radius - 1e-6)
    ):
        raise VesselClearanceInputError("vessel asset violates its minimum-diameter provenance")

    classifications_per_shank: list[tuple[ProbeShankASR, list[ProbeVesselConflict]]] = []
    all_nearest: list[float] = []
    all_minimum_geometric: list[float] = []
    all_minimum_adjusted: list[float] = []
    total_candidates = 0
    total_measured = 0
    profile_confirmed = (
        risk_profile.confirmed_by_user and risk_profile.reference_only_coverage_acknowledged
    )
    source_uncertainty_bound = provenance.minimum_spatial_uncertainty_bound_um
    source_uncertainty_qualified = (
        source_uncertainty_bound is not None
        and risk_profile.registration_uncertainty_um + CLEARANCE_NUMERICAL_TOLERANCE_UM
        >= source_uncertainty_bound
    )
    analysis_warnings = _analysis_warnings(
        provenance=provenance,
        risk_profile=risk_profile,
    )

    for shank in shanks:
        broad_phase = _broad_phase_mask(
            shank,
            segments,
            required_margin_um=risk_profile.required_margin_um,
            registration_uncertainty_um=risk_profile.registration_uncertainty_um,
        )
        candidate_count = int(np.count_nonzero(broad_phase))
        if candidate_count == 0:
            raise RuntimeError("vessel AABB broad phase produced no minimum candidate")
        candidate_segments = _take_segments(segments, broad_phase)
        centerline = _closest_probe_to_segments(
            shank.entry_asr_um,
            shank.tip_asr_um,
            candidate_segments,
        )
        tapered = _closest_probe_to_tapered_segments(
            shank.entry_asr_um,
            shank.tip_asr_um,
            candidate_segments,
        )
        all_nearest.append(float(centerline.distance.min()))
        geometric = tapered.distance - tapered.vessel_radius - shank.envelope_radius_um
        adjusted = (
            geometric - risk_profile.required_margin_um - risk_profile.registration_uncertainty_um
        )
        all_minimum_geometric.append(float(geometric.min()))
        all_minimum_adjusted.append(float(adjusted.min()))

        total_candidates += candidate_count
        total_measured += int(tapered.distance.size)
        conflict_mask = adjusted <= CLEARANCE_NUMERICAL_TOLERANCE_UM

        conflicts: list[ProbeVesselConflict] = []
        if profile_confirmed:
            for segment_index in np.flatnonzero(conflict_mask):
                index = int(segment_index)
                if geometric[index] <= CLEARANCE_NUMERICAL_TOLERANCE_UM:
                    classification = VesselConflictClassification.INTERSECTION
                elif (
                    geometric[index] - risk_profile.required_margin_um
                    <= CLEARANCE_NUMERICAL_TOLERANCE_UM
                ):
                    classification = VesselConflictClassification.MARGIN_VIOLATION
                else:
                    classification = VesselConflictClassification.UNCERTAINTY_VIOLATION
                run_index = int(candidate_segments.run_index[index])
                local_segment_index = int(candidate_segments.segment_index_in_run[index])
                edge_index = int(candidate_segments.source_edge_index[index])
                insertion_depth = tapered.first_fraction[index] * float(
                    np.linalg.norm(shank.tip_asr_um - shank.entry_asr_um)
                )
                conflicts.append(
                    ProbeVesselConflict(
                        conflict_id=(
                            f"{shank.shank_id}:edge-{edge_index}:"
                            f"run-{run_index}:segment-{local_segment_index}"
                        ),
                        shank_id=shank.shank_id,
                        vessel_source_edge_index=edge_index,
                        vessel_run_index=run_index,
                        vessel_segment_index_in_run=local_segment_index,
                        classification=classification,
                        vessel_diameter_um=float(2.0 * tapered.vessel_radius[index]),
                        probe_envelope_radius_um=shank.envelope_radius_um,
                        centerline_distance_um=float(tapered.distance[index]),
                        geometric_surface_clearance_um=float(geometric[index]),
                        required_margin_um=risk_profile.required_margin_um,
                        registration_uncertainty_um=risk_profile.registration_uncertainty_um,
                        uncertainty_adjusted_clearance_um=float(adjusted[index]),
                        probe_point=_point(tapered.first_point[index]),
                        vessel_point=_point(tapered.second_point[index]),
                        insertion_depth_um=float(insertion_depth),
                        warnings=analysis_warnings,
                    )
                )
        classifications_per_shank.append((shank, conflicts))

    all_conflicts = [
        conflict for _, shank_conflicts in classifications_per_shank for conflict in shank_conflicts
    ]
    all_conflicts.sort(
        key=lambda item: (
            item.uncertainty_adjusted_clearance_um,
            item.shank_id,
            item.vessel_source_edge_index,
            item.vessel_run_index,
            item.vessel_segment_index_in_run,
        )
    )
    truncated = len(all_conflicts) > maximum_conflicts
    published_conflicts = tuple(all_conflicts[:maximum_conflicts])

    if not profile_confirmed:
        status = ProbeVesselResultStatus.INSUFFICIENT_GEOMETRY
        statement = (
            "Clearance classification is unavailable until the risk profile and "
            "reference-only coverage limitations are explicitly confirmed."
        )
        published_conflicts = ()
        truncated = False
    elif any(
        conflict.classification is VesselConflictClassification.INTERSECTION
        for conflict in all_conflicts
    ):
        status = ProbeVesselResultStatus.INTERSECTION
        statement = "Intersection detected within the loaded reference vessel geometry."
    elif any(
        conflict.classification is VesselConflictClassification.MARGIN_VIOLATION
        for conflict in all_conflicts
    ):
        status = ProbeVesselResultStatus.MARGIN_VIOLATION
        statement = "Required geometric margin violation detected in the loaded reference geometry."
    elif all_conflicts:
        status = ProbeVesselResultStatus.UNCERTAINTY_VIOLATION
        statement = (
            "Registration-uncertainty-adjusted clearance violation detected in the loaded "
            "reference geometry."
        )
    elif source_uncertainty_bound is None:
        status = ProbeVesselResultStatus.INSUFFICIENT_GEOMETRY
        statement = UNBOUNDED_SOURCE_STATEMENT
    elif not source_uncertainty_qualified:
        status = ProbeVesselResultStatus.INSUFFICIENT_GEOMETRY
        statement = UNDERSPECIFIED_UNCERTAINTY_STATEMENT
    else:
        status = ProbeVesselResultStatus.NO_CONFLICT_DETECTED
        statement = NO_CONFLICT_STATEMENT

    input_sha256 = _analysis_input_sha256(shanks, risk_profile, provenance)
    return ProbeVesselAnalysis(
        input_sha256=input_sha256,
        result_status=status,
        nearest_centerline_distance_um=min(all_nearest),
        minimum_geometric_clearance_um=min(all_minimum_geometric),
        minimum_uncertainty_adjusted_clearance_um=min(all_minimum_adjusted),
        candidate_segment_count=total_candidates,
        measured_segment_count=total_measured,
        conflicts=published_conflicts,
        conflicts_truncated=truncated,
        risk_profile=risk_profile,
        provenance=provenance,
        statement=statement,
        warnings=analysis_warnings,
    )


@dataclass(frozen=True, slots=True)
class _ClosestBatch:
    distance: NDArray[np.float64]
    first_point: NDArray[np.float64]
    second_point: NDArray[np.float64]
    first_fraction: NDArray[np.float64]
    second_fraction: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class _TaperedClosestBatch:
    distance: NDArray[np.float64]
    vessel_radius: NDArray[np.float64]
    first_point: NDArray[np.float64]
    second_point: NDArray[np.float64]
    first_fraction: NDArray[np.float64]
    second_fraction: NDArray[np.float64]


def _closest_probe_to_tapered_segments(
    first_start: NDArray[np.float64],
    first_end: NDArray[np.float64],
    segments: _Segments,
) -> _TaperedClosestBatch:
    """Minimize centerline distance minus linearly varying radius per segment.

    Distance to a finite segment is convex.  Composing it with the vessel
    centerline and subtracting a linear radius leaves a convex one-dimensional
    objective on ``t in [0,1]``.  Fixed-iteration vectorized ternary search,
    followed by explicit endpoint comparison, provides deterministic bounded
    minimization without treating the centerline-closest point as the tapered
    surface-closest point.
    """

    direction = first_end - first_start
    squared_length = float(np.dot(direction, direction))
    if squared_length <= 0:
        raise VesselClearanceInputError("probe shank must have nonzero length")
    segment_count = segments.start.shape[0]
    low = np.zeros(segment_count, dtype=np.float64)
    high = np.ones(segment_count, dtype=np.float64)
    for _iteration in range(TAPERED_SEARCH_ITERATIONS):
        width = (high - low) / 3.0
        left = low + width
        right = high - width
        left_value = _tapered_surface_objective(
            first_start,
            direction,
            squared_length,
            segments,
            left,
        )
        right_value = _tapered_surface_objective(
            first_start,
            direction,
            squared_length,
            segments,
            right,
        )
        choose_left = left_value <= right_value
        high = np.where(choose_left, right, high)
        low = np.where(choose_left, low, left)

    midpoint = (low + high) / 2.0
    fractions = np.stack(
        (
            np.zeros(segment_count, dtype=np.float64),
            midpoint,
            np.ones(segment_count, dtype=np.float64),
        )
    )
    objectives = np.stack(
        [
            _tapered_surface_objective(
                first_start,
                direction,
                squared_length,
                segments,
                fractions[index],
            )
            for index in range(fractions.shape[0])
        ]
    )
    choice = np.argmin(objectives, axis=0)
    columns = np.arange(segment_count)
    second_fraction = fractions[choice, columns]
    second_point = segments.start + second_fraction[:, None] * (segments.end - segments.start)
    first_fraction = np.clip(
        ((second_point - first_start[None, :]) @ direction) / squared_length,
        0.0,
        1.0,
    )
    first_point = first_start[None, :] + first_fraction[:, None] * direction[None, :]
    distance = np.linalg.norm(first_point - second_point, axis=1)
    vessel_radius = segments.start_radius + second_fraction * (
        segments.end_radius - segments.start_radius
    )
    return _TaperedClosestBatch(
        distance=distance,
        vessel_radius=vessel_radius,
        first_point=first_point,
        second_point=second_point,
        first_fraction=first_fraction,
        second_fraction=second_fraction,
    )


def _tapered_surface_objective(
    first_start: NDArray[np.float64],
    first_direction: NDArray[np.float64],
    first_squared_length: float,
    segments: _Segments,
    second_fraction: NDArray[np.float64],
) -> NDArray[np.float64]:
    second_point = segments.start + second_fraction[:, None] * (segments.end - segments.start)
    first_fraction = np.clip(
        ((second_point - first_start[None, :]) @ first_direction) / first_squared_length,
        0.0,
        1.0,
    )
    first_point = first_start[None, :] + first_fraction[:, None] * first_direction[None, :]
    distance = np.linalg.norm(first_point - second_point, axis=1)
    vessel_radius = segments.start_radius + second_fraction * (
        segments.end_radius - segments.start_radius
    )
    return distance - vessel_radius


def _closest_probe_to_segments(
    first_start: NDArray[np.float64],
    first_end: NDArray[np.float64],
    segments: _Segments,
) -> _ClosestBatch:
    """Vectorized exact minimization over the finite segment-pair rectangle."""

    u = first_end - first_start
    a = float(np.dot(u, u))
    if a <= 0:
        raise VesselClearanceInputError("probe shank must have nonzero length")
    v = segments.end - segments.start
    c = np.einsum("ij,ij->i", v, v)
    if bool(np.any(c <= 0)):
        raise VesselClearanceInputError("vessel runs contain a zero-length segment")
    w = first_start[None, :] - segments.start
    b = v @ u
    d = w @ u
    e = np.einsum("ij,ij->i", v, w)
    count = segments.start.shape[0]

    first_parameters = np.empty((5, count), dtype=np.float64)
    second_parameters = np.empty((5, count), dtype=np.float64)

    # Four boundary-edge minimizers cover parallel and constrained cases.
    first_parameters[0] = 0.0
    second_parameters[0] = np.clip(e / c, 0.0, 1.0)
    first_parameters[1] = 1.0
    second_parameters[1] = np.clip((e + b) / c, 0.0, 1.0)
    first_parameters[2] = np.clip(-d / a, 0.0, 1.0)
    second_parameters[2] = 0.0
    first_parameters[3] = np.clip((b - d) / a, 0.0, 1.0)
    second_parameters[3] = 1.0

    denominator = a * c - b * b
    interior_valid = denominator > (1e-18 * a * c)
    interior_first = np.zeros(count, dtype=np.float64)
    interior_second = np.zeros(count, dtype=np.float64)
    np.divide(
        b * e - c * d,
        denominator,
        out=interior_first,
        where=interior_valid,
    )
    np.divide(
        a * e - b * d,
        denominator,
        out=interior_second,
        where=interior_valid,
    )
    interior_valid &= (interior_first >= 0) & (interior_first <= 1)
    interior_valid &= (interior_second >= 0) & (interior_second <= 1)
    first_parameters[4] = interior_first
    second_parameters[4] = interior_second

    delta = (
        w[None, :, :]
        + first_parameters[:, :, None] * u[None, None, :]
        - second_parameters[:, :, None] * v[None, :, :]
    )
    squared = np.einsum("kij,kij->ki", delta, delta)
    squared[4, ~interior_valid] = np.inf
    choice = np.argmin(squared, axis=0)
    columns = np.arange(count)
    first_fraction = first_parameters[choice, columns]
    second_fraction = second_parameters[choice, columns]
    distance = np.sqrt(squared[choice, columns])
    first_point = first_start[None, :] + first_fraction[:, None] * u[None, :]
    second_point = segments.start + second_fraction[:, None] * v
    return _ClosestBatch(
        distance=distance,
        first_point=first_point,
        second_point=second_point,
        first_fraction=first_fraction,
        second_fraction=second_fraction,
    )


def _broad_phase_mask(
    shank: ProbeShankASR,
    segments: _Segments,
    *,
    required_margin_um: float,
    registration_uncertainty_um: float,
) -> NDArray[np.bool_]:
    """Return a sound candidate set before any exact tapered narrow phase.

    AABB distance is a lower bound on finite-segment distance.  Subtracting
    the larger endpoint radius gives a lower bound on the tapered surface
    objective.  Feasible endpoint-pair distances provide global upper bounds,
    so segments unable to beat either global minimum can be discarded while
    every possible adjusted conflict remains included.
    """

    vessel_lower = np.minimum(segments.start, segments.end)
    vessel_upper = np.maximum(segments.start, segments.end)
    probe_lower = np.minimum(shank.entry_asr_um, shank.tip_asr_um)
    probe_upper = np.maximum(shank.entry_asr_um, shank.tip_asr_um)
    separation = np.maximum(
        np.maximum(vessel_lower - probe_upper, probe_lower - vessel_upper),
        0.0,
    )
    centerline_lower_bound = np.linalg.norm(separation, axis=1)

    endpoint_distances = np.stack(
        (
            np.linalg.norm(segments.start - shank.entry_asr_um, axis=1),
            np.linalg.norm(segments.start - shank.tip_asr_um, axis=1),
            np.linalg.norm(segments.end - shank.entry_asr_um, axis=1),
            np.linalg.norm(segments.end - shank.tip_asr_um, axis=1),
        )
    )
    centerline_upper_bound = float(endpoint_distances.min())
    endpoint_surface_values = (
        np.stack(
            (
                endpoint_distances[0] - segments.start_radius,
                endpoint_distances[1] - segments.start_radius,
                endpoint_distances[2] - segments.end_radius,
                endpoint_distances[3] - segments.end_radius,
            )
        )
        - shank.envelope_radius_um
    )
    surface_upper_bound = float(endpoint_surface_values.min())
    maximum_radius = np.maximum(segments.start_radius, segments.end_radius)
    surface_lower_bound = centerline_lower_bound - maximum_radius - shank.envelope_radius_um
    adjusted_conflict_limit = (
        required_margin_um + registration_uncertainty_um + CLEARANCE_NUMERICAL_TOLERANCE_UM
    )
    centerline_candidate = (
        centerline_lower_bound <= centerline_upper_bound + CLEARANCE_NUMERICAL_TOLERANCE_UM
    )
    surface_candidate = surface_lower_bound <= max(
        surface_upper_bound + CLEARANCE_NUMERICAL_TOLERANCE_UM,
        adjusted_conflict_limit,
    )
    return np.asarray(centerline_candidate | surface_candidate, dtype=np.bool_)


def _take_segments(segments: _Segments, mask: NDArray[np.bool_]) -> _Segments:
    """Return one metadata-preserving candidate subset."""

    return _Segments(
        start=segments.start[mask],
        end=segments.end[mask],
        start_radius=segments.start_radius[mask],
        end_radius=segments.end_radius[mask],
        run_index=segments.run_index[mask],
        segment_index_in_run=segments.segment_index_in_run[mask],
        source_edge_index=segments.source_edge_index[mask],
    )


def _segments(vessels: RadiusBearingVesselRuns) -> _Segments:
    start_indices = np.concatenate(
        [
            np.arange(start, stop - 1, dtype=np.int64)
            for start, stop in zip(
                vessels.run_offsets[:-1],
                vessels.run_offsets[1:],
                strict=True,
            )
        ]
    )
    run_index = np.concatenate(
        [
            np.full(int(stop - start - 1), index, dtype=np.int64)
            for index, (start, stop) in enumerate(
                zip(vessels.run_offsets[:-1], vessels.run_offsets[1:], strict=True)
            )
        ]
    )
    segment_index = np.concatenate(
        [
            np.arange(int(stop - start - 1), dtype=np.int64)
            for start, stop in zip(
                vessels.run_offsets[:-1],
                vessels.run_offsets[1:],
                strict=True,
            )
        ]
    )
    source_edge_index = vessels.source_edge_indices[run_index]
    return _Segments(
        start=vessels.points_asr_um[start_indices],
        end=vessels.points_asr_um[start_indices + 1],
        start_radius=vessels.radii_um[start_indices],
        end_radius=vessels.radii_um[start_indices + 1],
        run_index=run_index,
        segment_index_in_run=segment_index,
        source_edge_index=source_edge_index,
    )


def _analysis_warnings(
    *,
    provenance: MajorVesselSourceProvenance,
    risk_profile: VesselRiskProfile,
) -> tuple[str, ...]:
    source_bound = provenance.minimum_spatial_uncertainty_bound_um
    if source_bound is None:
        uncertainty_warning = (
            "Registration error and tissue distortion are not bounded by the source provenance; "
            "absence of loaded-geometry conflicts cannot be classified."
        )
    elif risk_profile.registration_uncertainty_um + CLEARANCE_NUMERICAL_TOLERANCE_UM < source_bound:
        uncertainty_warning = (
            "The stated uncertainty is below the reviewed combined source bound of "
            f"{source_bound:g} micrometres; absence of conflicts cannot be classified."
        )
    else:
        return REFERENCE_GRAPH_WARNINGS
    return (*REFERENCE_GRAPH_WARNINGS, uncertainty_warning)


def _analysis_input_sha256(
    shanks: tuple[ProbeShankASR, ...],
    profile: VesselRiskProfile,
    provenance: MajorVesselSourceProvenance,
) -> str:
    payload = {
        "algorithmVersion": VESSEL_CLEARANCE_ALGORITHM_VERSION,
        "shanks": [
            {
                "shankId": shank.shank_id,
                "entryASRUm": shank.entry_asr_um.tolist(),
                "tipASRUm": shank.tip_asr_um.tolist(),
                "envelopeRadiusUm": shank.envelope_radius_um,
            }
            for shank in shanks
        ],
        "riskProfile": profile.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite_triplet(value: NDArray[np.float64], label: str) -> NDArray[np.float64]:
    vector = np.asarray(value, dtype=np.float64)
    if vector.shape != (3,) or not bool(np.isfinite(vector).all()):
        raise VesselClearanceInputError(f"{label} must contain three finite ASR coordinates")
    return np.array(vector, dtype=np.float64, copy=True)


def _point(value: NDArray[np.float64]) -> PhysicalASRPoint:
    return PhysicalASRPoint(ap_um=float(value[0]), dv_um=float(value[1]), ml_um=float(value[2]))
