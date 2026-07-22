"""Frame-checked measurement calculations for animal surgery planning."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.domain.measurement_models import (
    AngularMeasurement,
    LinearMeasurement,
    LinearMeasurementKind,
    VesselDataRepresentation,
    VesselDistanceMeasurement,
    VesselGeometryProvenance,
    VesselGeometrySourceKind,
    VesselPolyline,
)
from mouse_brain_planner.domain.probe_models import NormalizedProbePlacement
from mouse_brain_planner.domain.surgery_common import (
    AnimalSurgeryContext,
    UnitDirectionAPMLDV,
)
from mouse_brain_planner.domain.transform_models import AnatomicalPoint


class MeasurementError(ValueError):
    """Raised when a measurement would mix frames or overstate its input data."""


def point_to_point_distance(
    *,
    context: AnimalSurgeryContext,
    first: AnatomicalPoint,
    second: AnatomicalPoint,
) -> LinearMeasurement:
    """Calculate Euclidean point-to-point distance in one named frame."""

    _same_frame(first, second)
    return LinearMeasurement(
        context=context,
        kind=LinearMeasurementKind.POINT_TO_POINT,
        value_um=float(np.linalg.norm(_array(second) - _array(first))),
        frame_id=first.frame_id,
        calculation_method="Euclidean norm of named AP/ML/DV point difference",
    )


def point_to_line_distance(
    *,
    context: AnimalSurgeryContext,
    point: AnatomicalPoint,
    line_start: AnatomicalPoint,
    line_end: AnatomicalPoint,
    finite_segment: bool,
) -> LinearMeasurement:
    """Calculate distance to either an infinite line or finite segment."""

    _same_frame(point, line_start, line_end)
    start = _array(line_start)
    end = _array(line_end)
    vector = end - start
    denominator = float(np.dot(vector, vector))
    if denominator <= 0:
        raise MeasurementError("line start and end must be distinct")
    parameter = float(np.dot(_array(point) - start, vector) / denominator)
    if finite_segment:
        parameter = min(1.0, max(0.0, parameter))
    nearest = start + parameter * vector
    return LinearMeasurement(
        context=context,
        kind=(
            LinearMeasurementKind.POINT_TO_SEGMENT
            if finite_segment
            else LinearMeasurementKind.POINT_TO_INFINITE_LINE
        ),
        value_um=float(np.linalg.norm(_array(point) - nearest)),
        frame_id=point.frame_id,
        calculation_method=(
            "Euclidean projection clamped to finite AP/ML/DV segment"
            if finite_segment
            else "Euclidean orthogonal projection onto infinite AP/ML/DV line"
        ),
    )


def path_length(
    *,
    context: AnimalSurgeryContext,
    points: Sequence[AnatomicalPoint],
) -> LinearMeasurement:
    """Sum finite segment lengths along an ordered path."""

    if len(points) < 2:
        raise MeasurementError("path length requires at least two points")
    _same_frame(*points)
    value = sum(
        float(np.linalg.norm(_array(second) - _array(first))) for first, second in pairwise(points)
    )
    return LinearMeasurement(
        context=context,
        kind=LinearMeasurementKind.PATH_LENGTH,
        value_um=value,
        frame_id=points[0].frame_id,
        calculation_method="sum of finite Euclidean AP/ML/DV path segments",
    )


def angle_between_directions(
    *,
    context: AnimalSurgeryContext,
    first: UnitDirectionAPMLDV,
    second: UnitDirectionAPMLDV,
) -> AngularMeasurement:
    """Calculate the unsigned 0..180 degree angle between directions."""

    if first.frame_id != second.frame_id:
        raise MeasurementError("direction-angle measurement requires one explicit frame")
    dot = sum(
        first_value * second_value
        for first_value, second_value in zip(
            first.as_ap_ml_dv(),
            second.as_ap_ml_dv(),
            strict=True,
        )
    )
    angle = math.degrees(math.acos(min(1.0, max(-1.0, dot))))
    return AngularMeasurement(context=context, value_deg=angle, frame_id=first.frame_id)


def distance_between_probe_centerlines(
    *,
    first: NormalizedProbePlacement,
    second: NormalizedProbePlacement,
) -> LinearMeasurement:
    """Return centerline distance, not physical-shank or surgical clearance."""

    if first.context != second.context:
        raise MeasurementError("probe centerline measurement requires the same animal context")
    _same_frame(first.entry, first.tip, second.entry, second.tip)
    distance, _, _ = _segment_closest_points(
        _array(first.entry),
        _array(first.tip),
        _array(second.entry),
        _array(second.tip),
    )
    return LinearMeasurement(
        context=first.context,
        kind=LinearMeasurementKind.PROBE_CENTERLINE_TO_CENTERLINE,
        value_um=distance,
        frame_id=first.entry.frame_id,
        calculation_method=(
            "exact minimum Euclidean distance between finite probe centerlines; "
            "does not subtract shank/body dimensions"
        ),
        model_based_estimate=True,
    )


def nearest_vessel_distance(
    *,
    placement: NormalizedProbePlacement,
    provenance: VesselGeometryProvenance,
    vessels: Sequence[VesselPolyline],
) -> VesselDistanceMeasurement:
    """Measure to distance-capable 3-D geometry without claiming safety.

    Population density and 2-D surface imagery are rejected: neither contains
    individual 3-D vessel paths, so a nearest-vessel or subject-clearance value
    cannot be inferred from them.
    """

    if provenance.source_kind is VesselGeometrySourceKind.POPULATION_REFERENCE_DENSITY:
        raise MeasurementError(
            "population vascular density contains no individual vessel paths; "
            "nearest-vessel or subject-clearance distance is undefined"
        )
    if provenance.source_kind is VesselGeometrySourceKind.SUBJECT_SURFACE_IMAGE_2D:
        raise MeasurementError(
            "a 2-D dorsal vessel image cannot determine 3-D probe-to-vessel distance"
        )
    if provenance.representation is not VesselDataRepresentation.POLYLINE_3D:
        raise MeasurementError("vessel distance requires registered 3-D polyline geometry")
    if not provenance.physical_scale_calibrated:
        raise MeasurementError("vessel distance requires calibrated physical scale")
    if not provenance.geometry_reviewed_by_user:
        raise MeasurementError("vessel distance requires explicit user review of vessel geometry")
    if not vessels:
        raise MeasurementError("vessel distance requires at least one vessel polyline")
    if placement.entry.frame_id != provenance.coordinate_frame_id:
        raise MeasurementError("probe placement frame does not match vessel geometry provenance")

    best: tuple[float, NDArray[np.float64], NDArray[np.float64], str] | None = None
    trajectory_start = _array(placement.entry)
    trajectory_end = _array(placement.tip)
    for vessel in vessels:
        if vessel.points[0].frame_id != provenance.coordinate_frame_id:
            raise MeasurementError(
                f"vessel {vessel.vessel_id!r} frame does not match vessel provenance"
            )
        for first, second in pairwise(vessel.points):
            distance, trajectory_point, vessel_point = _segment_closest_points(
                trajectory_start,
                trajectory_end,
                _array(first),
                _array(second),
            )
            if best is None or distance < best[0]:
                best = (distance, trajectory_point, vessel_point, vessel.vessel_id)
    if best is None:  # defensive; VesselPolyline enforces at least one segment
        raise MeasurementError("vessel geometry did not contain a measurable segment")

    subject_specific = (
        provenance.source_kind is VesselGeometrySourceKind.SUBJECT_REGISTERED_3D_SEGMENTATION
    )
    interpretation: Literal[
        "subject-specific geometry distance; not a safety determination",
        "reference-only geometry distance; not subject-specific and not a safety determination",
    ] = (
        "subject-specific geometry distance; not a safety determination"
        if subject_specific
        else "reference-only geometry distance; not subject-specific and not a safety determination"
    )
    return VesselDistanceMeasurement(
        context=placement.context,
        vessel_id=best[3],
        distance_um=best[0],
        trajectory_point=_point(placement.entry.frame_id, best[1]),
        vessel_point=_point(placement.entry.frame_id, best[2]),
        provenance=provenance,
        subject_specific=subject_specific,
        interpretation=interpretation,
    )


def _segment_closest_points(
    first_start: NDArray[np.float64],
    first_end: NDArray[np.float64],
    second_start: NDArray[np.float64],
    second_end: NDArray[np.float64],
) -> tuple[float, NDArray[np.float64], NDArray[np.float64]]:
    distance, first_point, second_point, _, _ = finite_segment_closest_points(
        first_start,
        first_end,
        second_start,
        second_end,
    )
    return distance, first_point, second_point


def finite_segment_closest_points(
    first_start: NDArray[np.float64],
    first_end: NDArray[np.float64],
    second_start: NDArray[np.float64],
    second_end: NDArray[np.float64],
) -> tuple[
    float,
    NDArray[np.float64],
    NDArray[np.float64],
    float,
    float,
]:
    """Return exact closest points and fractions for two finite 3-D segments.

    Fractions are measured from each corresponding start point and are always
    clamped to ``[0, 1]``.  This public kernel is shared by legacy centerline
    measurements and radius-aware vessel clearance so the two paths cannot
    silently diverge numerically.
    """

    first_start = _finite_vector(first_start, "first segment start")
    first_end = _finite_vector(first_end, "first segment end")
    second_start = _finite_vector(second_start, "second segment start")
    second_end = _finite_vector(second_end, "second segment end")
    first_vector = first_end - first_start
    second_vector = second_end - second_start
    between_starts = first_start - second_start
    first_squared = float(np.dot(first_vector, first_vector))
    second_squared = float(np.dot(second_vector, second_vector))
    if first_squared <= 0 or second_squared <= 0:
        raise MeasurementError("segment distance requires non-zero-length segments")
    cross_dot = float(np.dot(first_vector, second_vector))
    first_start_dot = float(np.dot(first_vector, between_starts))
    second_start_dot = float(np.dot(second_vector, between_starts))
    denominator = first_squared * second_squared - cross_dot * cross_dot
    if denominator > 1e-18 * first_squared * second_squared:
        first_parameter = (
            cross_dot * second_start_dot - second_squared * first_start_dot
        ) / denominator
    else:
        first_parameter = 0.0
    first_parameter = min(1.0, max(0.0, first_parameter))
    second_parameter = (cross_dot * first_parameter + second_start_dot) / second_squared
    if second_parameter < 0.0:
        second_parameter = 0.0
        first_parameter = min(1.0, max(0.0, -first_start_dot / first_squared))
    elif second_parameter > 1.0:
        second_parameter = 1.0
        first_parameter = min(
            1.0,
            max(0.0, (cross_dot - first_start_dot) / first_squared),
        )
    first_point = first_start + first_parameter * first_vector
    second_point = second_start + second_parameter * second_vector
    return (
        float(np.linalg.norm(first_point - second_point)),
        first_point,
        second_point,
        first_parameter,
        second_parameter,
    )


def _finite_vector(value: NDArray[np.float64], label: str) -> NDArray[np.float64]:
    vector = np.asarray(value, dtype=np.float64)
    if vector.shape != (3,) or not bool(np.isfinite(vector).all()):
        raise MeasurementError(f"{label} must contain three finite coordinates")
    return vector


def _same_frame(*points: AnatomicalPoint) -> None:
    if not points:
        raise MeasurementError("measurement requires at least one point")
    frame_id = points[0].frame_id
    if any(point.frame_id != frame_id for point in points):
        raise MeasurementError("measurement points must use one explicit coordinate frame")


def _array(point: AnatomicalPoint) -> NDArray[np.float64]:
    return np.asarray(point.as_ap_ml_dv(), dtype=np.float64)


def _point(frame_id: str, values: NDArray[np.float64]) -> AnatomicalPoint:
    return AnatomicalPoint(
        frame_id=frame_id,
        ap_um=float(values[0]),
        ml_um=float(values[1]),
        dv_um=float(values[2]),
    )
