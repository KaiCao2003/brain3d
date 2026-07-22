from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from mouse_brain_planner.domain.craniotomy_models import (
    CircularOpening,
    CraniotomyPlan,
    EllipticalOpening,
    PlanarPoint,
    PlannedOpeningKind,
    PolygonalOpening,
    RectangularOpening,
    SkullIntersectionQuality,
    SurfacePlane,
    SurfaceSource,
)
from mouse_brain_planner.domain.surgery_common import (
    AnimalSurgeryContext,
    UnitDirectionAPMLDV,
)
from mouse_brain_planner.domain.transform_models import AnatomicalPoint
from mouse_brain_planner.surgery.craniotomy import (
    CraniotomyGeometryError,
    craniotomy_metrics,
    craniotomy_outline_points,
)


def _surface(*, subject_specific: bool = False) -> SurfacePlane:
    source = (
        SurfaceSource.SUBJECT_SKULL_MESH
        if subject_specific
        else SurfaceSource.USER_DEFINED_PLANAR_SKULL_APPROXIMATION
    )
    return SurfacePlane(
        plane_id="dorsal-skull-plane",
        source=source,
        source_asset_id="subject-skull.stl" if subject_specific else None,
        origin=AnatomicalPoint(frame_id="SUBJECT", ap_um=100, ml_um=200, dv_um=300),
        ap_axis=UnitDirectionAPMLDV(frame_id="SUBJECT", ap=1, ml=0, dv=0),
        ml_axis=UnitDirectionAPMLDV(frame_id="SUBJECT", ap=0, ml=1, dv=0),
        registration_residual_um=25 if subject_specific else None,
        provenance=("Registered subject skull" if subject_specific else "User-defined plane"),
    )


def _plan(geometry, *, subject_specific: bool = False) -> CraniotomyPlan:
    return CraniotomyPlan(
        context=AnimalSurgeryContext(subject_id="mouse-2"),
        name="left window",
        opening_kind=PlannedOpeningKind.CRANIOTOMY,
        surface=_surface(subject_specific=subject_specific),
        skull_intersection_quality=(
            SkullIntersectionQuality.SUBJECT_SPECIFIC_SURFACE
            if subject_specific
            else SkullIntersectionQuality.APPROXIMATION
        ),
        geometry=geometry,
    )


def test_circle_metrics_outline_and_serialization_keep_approximation_label() -> None:
    plan = _plan(CircularOpening(center=PlanarPoint(ap_um=0, ml_um=0), diameter_um=2000))
    metrics = craniotomy_metrics(plan)
    assert metrics.area_um2 == pytest.approx(math.pi * 1_000_000)
    assert metrics.perimeter_um == pytest.approx(math.tau * 1000)
    assert metrics.maximum_ap_span_um == pytest.approx(2000)
    assert plan.is_skull_approximation

    outline = craniotomy_outline_points(plan, curve_samples=24)
    assert len(outline) == 25
    assert outline[0] == outline[-1]
    assert outline[0].as_ap_ml_dv() == pytest.approx((1100, 200, 300))
    restored = CraniotomyPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan
    with pytest.raises(CraniotomyGeometryError, match="at least 12"):
        craniotomy_outline_points(plan, curve_samples=8)


def test_subject_surface_is_labelled_subject_specific_and_requires_registration() -> None:
    plan = _plan(
        RectangularOpening(
            center=PlanarPoint(ap_um=0, ml_um=0),
            ap_length_um=2000,
            ml_width_um=1000,
            rotation_deg=90,
        ),
        subject_specific=True,
    )
    metrics = craniotomy_metrics(plan)
    assert not plan.is_skull_approximation
    assert metrics.area_um2 == pytest.approx(2_000_000)
    assert metrics.maximum_ap_span_um == pytest.approx(1000)
    assert metrics.maximum_ml_span_um == pytest.approx(2000)

    with pytest.raises(ValidationError, match="source asset ID"):
        SurfacePlane(
            plane_id="bad",
            source=SurfaceSource.SUBJECT_SKULL_MESH,
            origin=plan.surface.origin,
            ap_axis=plan.surface.ap_axis,
            ml_axis=plan.surface.ml_axis,
            registration_residual_um=10,
            provenance="missing asset",
        )


def test_surface_quality_cannot_overstate_atlas_or_planar_geometry() -> None:
    with pytest.raises(ValidationError, match="requires skull quality"):
        CraniotomyPlan(
            context=AnimalSurgeryContext(),
            name="bad label",
            opening_kind=PlannedOpeningKind.BURR_HOLE,
            surface=_surface(),
            skull_intersection_quality=SkullIntersectionQuality.SUBJECT_SPECIFIC_SURFACE,
            geometry=CircularOpening(
                center=PlanarPoint(ap_um=0, ml_um=0),
                diameter_um=500,
            ),
        )


def test_rotated_ellipse_has_exact_bounding_spans_and_labelled_perimeter_approximation() -> None:
    plan = _plan(
        EllipticalOpening(
            center=PlanarPoint(ap_um=0, ml_um=0),
            ap_diameter_um=3000,
            ml_diameter_um=1000,
            rotation_deg=90,
        )
    )
    metrics = craniotomy_metrics(plan)
    assert metrics.maximum_ap_span_um == pytest.approx(1000)
    assert metrics.maximum_ml_span_um == pytest.approx(3000)
    assert "Ramanujan" in metrics.perimeter_method


def test_polygon_metrics_and_self_intersection_validation() -> None:
    triangle = PolygonalOpening(
        vertices=(
            PlanarPoint(ap_um=0, ml_um=0),
            PlanarPoint(ap_um=3000, ml_um=0),
            PlanarPoint(ap_um=0, ml_um=4000),
        )
    )
    metrics = craniotomy_metrics(_plan(triangle))
    assert metrics.area_um2 == pytest.approx(6_000_000)
    assert metrics.perimeter_um == pytest.approx(12_000)

    with pytest.raises(ValidationError, match="self-intersect"):
        PolygonalOpening(
            vertices=(
                PlanarPoint(ap_um=0, ml_um=0),
                PlanarPoint(ap_um=1000, ml_um=1000),
                PlanarPoint(ap_um=0, ml_um=1000),
                PlanarPoint(ap_um=1000, ml_um=0),
            )
        )


def test_surface_axes_must_be_orthonormal_and_share_frame() -> None:
    with pytest.raises(ValidationError, match="orthogonal"):
        SurfacePlane(
            plane_id="bad",
            source=SurfaceSource.USER_DEFINED_PLANAR_SKULL_APPROXIMATION,
            origin=AnatomicalPoint(frame_id="F", ap_um=0, ml_um=0, dv_um=0),
            ap_axis=UnitDirectionAPMLDV(frame_id="F", ap=1, ml=0, dv=0),
            ml_axis=UnitDirectionAPMLDV(
                frame_id="F",
                ap=math.sqrt(0.5),
                ml=math.sqrt(0.5),
                dv=0,
            ),
            provenance="test",
        )
