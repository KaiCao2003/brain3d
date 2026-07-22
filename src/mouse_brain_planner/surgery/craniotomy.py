"""Pure metrics and outline calculations for craniotomy geometry."""

from __future__ import annotations

import math

import numpy as np

from mouse_brain_planner.domain.craniotomy_models import (
    CircularOpening,
    CraniotomyMetrics,
    CraniotomyPlan,
    EllipticalOpening,
    PlanarPoint,
    RectangularOpening,
)
from mouse_brain_planner.domain.transform_models import AnatomicalPoint


class CraniotomyGeometryError(ValueError):
    """Raised when a requested outline sampling operation is invalid."""


def craniotomy_metrics(plan: CraniotomyPlan) -> CraniotomyMetrics:
    """Calculate dimensions with an explicit perimeter method."""

    geometry = plan.geometry
    if isinstance(geometry, CircularOpening):
        radius = geometry.diameter_um / 2.0
        area = math.pi * radius * radius
        perimeter = math.tau * radius
        ap_span = geometry.diameter_um
        ml_span = geometry.diameter_um
        method = "analytic circle circumference"
    elif isinstance(geometry, EllipticalOpening):
        ap_radius = geometry.ap_diameter_um / 2.0
        ml_radius = geometry.ml_diameter_um / 2.0
        area = math.pi * ap_radius * ml_radius
        difference = ap_radius - ml_radius
        total = ap_radius + ml_radius
        h = difference * difference / (total * total)
        perimeter = math.pi * total * (1.0 + 3.0 * h / (10.0 + math.sqrt(4.0 - 3.0 * h)))
        ap_span, ml_span = _rotated_ellipse_extents(
            geometry.ap_diameter_um,
            geometry.ml_diameter_um,
            geometry.rotation_deg,
        )
        method = "Ramanujan second ellipse-perimeter approximation"
    elif isinstance(geometry, RectangularOpening):
        area = geometry.ap_length_um * geometry.ml_width_um
        perimeter = 2.0 * (geometry.ap_length_um + geometry.ml_width_um)
        ap_span, ml_span = _rotated_extents(
            geometry.ap_length_um,
            geometry.ml_width_um,
            geometry.rotation_deg,
        )
        method = "analytic rectangle perimeter"
    else:
        values = tuple(vertex.as_ap_ml() for vertex in geometry.vertices)
        closed_pairs = tuple(zip(values, values[1:] + values[:1], strict=True))
        area = (
            abs(sum(first[0] * second[1] - second[0] * first[1] for first, second in closed_pairs))
            / 2.0
        )
        perimeter = sum(math.dist(first, second) for first, second in closed_pairs)
        ap_values = tuple(value[0] for value in values)
        ml_values = tuple(value[1] for value in values)
        ap_span = max(ap_values) - min(ap_values)
        ml_span = max(ml_values) - min(ml_values)
        method = "exact simple-polygon edge sum"
    return CraniotomyMetrics(
        plan_uuid=plan.plan_uuid,
        area_um2=area,
        perimeter_um=perimeter,
        maximum_ap_span_um=ap_span,
        maximum_ml_span_um=ml_span,
        perimeter_method=method,
        skull_intersection_quality=plan.skull_intersection_quality,
    )


def craniotomy_outline_points(
    plan: CraniotomyPlan,
    *,
    curve_samples: int = 96,
) -> tuple[AnatomicalPoint, ...]:
    """Return a closed 3-D boundary suitable for either UI shell."""

    geometry = plan.geometry
    if isinstance(geometry, CircularOpening):
        _validate_curve_samples(curve_samples)
        radius = geometry.diameter_um / 2.0
        local = tuple(
            PlanarPoint(
                ap_um=geometry.center.ap_um + radius * math.cos(angle),
                ml_um=geometry.center.ml_um + radius * math.sin(angle),
            )
            for angle in np.linspace(0.0, math.tau, curve_samples, endpoint=False)
        )
    elif isinstance(geometry, EllipticalOpening):
        _validate_curve_samples(curve_samples)
        ap_radius = geometry.ap_diameter_um / 2.0
        ml_radius = geometry.ml_diameter_um / 2.0
        local = tuple(
            _rotated_point(
                center=geometry.center,
                ap=ap_radius * math.cos(angle),
                ml=ml_radius * math.sin(angle),
                rotation_deg=geometry.rotation_deg,
            )
            for angle in np.linspace(0.0, math.tau, curve_samples, endpoint=False)
        )
    elif isinstance(geometry, RectangularOpening):
        ap_half = geometry.ap_length_um / 2.0
        ml_half = geometry.ml_width_um / 2.0
        local = tuple(
            _rotated_point(
                center=geometry.center,
                ap=ap,
                ml=ml,
                rotation_deg=geometry.rotation_deg,
            )
            for ap, ml in (
                (-ap_half, -ml_half),
                (ap_half, -ml_half),
                (ap_half, ml_half),
                (-ap_half, ml_half),
            )
        )
    else:
        local = geometry.vertices
    mapped = tuple(_map_to_surface(plan, point) for point in local)
    return (*mapped, mapped[0])


def _map_to_surface(plan: CraniotomyPlan, point: PlanarPoint) -> AnatomicalPoint:
    origin = np.asarray(plan.surface.origin.as_ap_ml_dv(), dtype=np.float64)
    ap_axis = np.asarray(plan.surface.ap_axis.as_ap_ml_dv(), dtype=np.float64)
    ml_axis = np.asarray(plan.surface.ml_axis.as_ap_ml_dv(), dtype=np.float64)
    mapped = origin + ap_axis * point.ap_um + ml_axis * point.ml_um
    return AnatomicalPoint(
        frame_id=plan.surface.origin.frame_id,
        ap_um=float(mapped[0]),
        ml_um=float(mapped[1]),
        dv_um=float(mapped[2]),
    )


def _rotated_point(
    *,
    center: PlanarPoint,
    ap: float,
    ml: float,
    rotation_deg: float,
) -> PlanarPoint:
    angle = math.radians(rotation_deg)
    return PlanarPoint(
        ap_um=center.ap_um + ap * math.cos(angle) - ml * math.sin(angle),
        ml_um=center.ml_um + ap * math.sin(angle) + ml * math.cos(angle),
    )


def _rotated_extents(ap_length: float, ml_width: float, rotation_deg: float) -> tuple[float, float]:
    angle = math.radians(rotation_deg)
    cosine = abs(math.cos(angle))
    sine = abs(math.sin(angle))
    return (
        ap_length * cosine + ml_width * sine,
        ap_length * sine + ml_width * cosine,
    )


def _rotated_ellipse_extents(
    ap_diameter: float,
    ml_diameter: float,
    rotation_deg: float,
) -> tuple[float, float]:
    angle = math.radians(rotation_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (
        math.sqrt((ap_diameter * cosine) ** 2 + (ml_diameter * sine) ** 2),
        math.sqrt((ap_diameter * sine) ** 2 + (ml_diameter * cosine) ** 2),
    )


def _validate_curve_samples(curve_samples: int) -> None:
    if curve_samples < 12:
        raise CraniotomyGeometryError("curved craniotomy outline requires at least 12 samples")
