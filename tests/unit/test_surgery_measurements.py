from __future__ import annotations

import pytest

from mouse_brain_planner.domain.measurement_models import (
    LinearMeasurementKind,
    VesselDataRepresentation,
    VesselGeometryProvenance,
    VesselGeometrySourceKind,
    VesselPolyline,
)
from mouse_brain_planner.domain.probe_models import (
    ProbeModelDefinition,
    ProbeModelVerification,
    ProbeShankDefinition,
    ProbeTipGeometry,
    ProbeVerificationStatus,
)
from mouse_brain_planner.domain.surgery_common import (
    AnimalSurgeryContext,
    UnitDirectionAPMLDV,
)
from mouse_brain_planner.domain.transform_models import AnatomicalPoint
from mouse_brain_planner.surgery.measurements import (
    MeasurementError,
    angle_between_directions,
    distance_between_probe_centerlines,
    nearest_vessel_distance,
    path_length,
    point_to_line_distance,
    point_to_point_distance,
)
from mouse_brain_planner.surgery.trajectory import placement_from_entry_target


def _point(ap: float, ml: float, dv: float, *, frame: str = "F") -> AnatomicalPoint:
    return AnatomicalPoint(frame_id=frame, ap_um=ap, ml_um=ml, dv_um=dv)


def _model() -> ProbeModelDefinition:
    return ProbeModelDefinition(
        model_id="test",
        model_version="1",
        display_name="Test custom probe",
        verification=ProbeModelVerification(status=ProbeVerificationStatus.USER_DEFINED_UNVERIFIED),
        declared_shank_count=1,
        expected_site_count=0,
        shanks=(
            ProbeShankDefinition(
                shank_id="A",
                length_um=2000,
                width_um=50,
                thickness_um=20,
                tip_geometry=ProbeTipGeometry.USER_DEFINED,
                tip_length_um=100,
                tip_geometry_notes="test fixture",
            ),
        ),
    )


def _placement(
    context: AnimalSurgeryContext,
    entry: AnatomicalPoint,
    tip: AnatomicalPoint,
):
    return placement_from_entry_target(
        context=context,
        model=_model(),
        name="test trajectory",
        entry=entry,
        target=tip,
    )


def test_basic_linear_and_angular_measurements_are_frame_checked() -> None:
    context = AnimalSurgeryContext()
    result = point_to_point_distance(
        context=context,
        first=_point(0, 0, 0),
        second=_point(3000, 4000, 0),
    )
    assert result.value_um == pytest.approx(5000)
    assert result.safety_determination is False

    infinite = point_to_line_distance(
        context=context,
        point=_point(2000, 1000, 0),
        line_start=_point(0, 0, 0),
        line_end=_point(1000, 0, 0),
        finite_segment=False,
    )
    segment = point_to_line_distance(
        context=context,
        point=_point(2000, 1000, 0),
        line_start=_point(0, 0, 0),
        line_end=_point(1000, 0, 0),
        finite_segment=True,
    )
    assert infinite.value_um == pytest.approx(1000)
    assert segment.value_um == pytest.approx(2**0.5 * 1000)
    assert segment.kind is LinearMeasurementKind.POINT_TO_SEGMENT

    path = path_length(
        context=context,
        points=(_point(0, 0, 0), _point(3000, 0, 0), _point(3000, 4000, 0)),
    )
    assert path.value_um == pytest.approx(7000)
    angle = angle_between_directions(
        context=context,
        first=UnitDirectionAPMLDV(frame_id="F", ap=1, ml=0, dv=0),
        second=UnitDirectionAPMLDV(frame_id="F", ap=0, ml=1, dv=0),
    )
    assert angle.value_deg == pytest.approx(90)

    with pytest.raises(MeasurementError, match="one explicit coordinate frame"):
        point_to_point_distance(
            context=context,
            first=_point(0, 0, 0, frame="A"),
            second=_point(0, 0, 0, frame="B"),
        )


def test_probe_centerline_distance_does_not_claim_hardware_clearance() -> None:
    context = AnimalSurgeryContext()
    first = _placement(context, _point(0, 0, 0), _point(0, 0, -1000))
    second = _placement(context, _point(0, 500, 0), _point(0, 500, -1000))
    result = distance_between_probe_centerlines(first=first, second=second)
    assert result.value_um == pytest.approx(500)
    assert "does not subtract" in result.calculation_method
    assert result.safety_determination is False


def test_population_density_and_2d_surface_image_cannot_produce_vessel_distance() -> None:
    context = AnimalSurgeryContext(subject_id="mouse")
    placement = _placement(context, _point(0, 0, 0), _point(0, 0, -1000))
    density = VesselGeometryProvenance(
        source_id="density-v1",
        source_kind=VesselGeometrySourceKind.POPULATION_REFERENCE_DENSITY,
        representation=VesselDataRepresentation.SCALAR_DENSITY_VOLUME,
        source_label="Population density, not individual vessels",
        coordinate_frame_id="F",
        physical_scale_calibrated=True,
        geometry_reviewed_by_user=True,
    )
    with pytest.raises(MeasurementError, match="no individual vessel paths"):
        nearest_vessel_distance(placement=placement, provenance=density, vessels=())

    image = VesselGeometryProvenance(
        source_id="dorsal-image",
        source_kind=VesselGeometrySourceKind.SUBJECT_SURFACE_IMAGE_2D,
        representation=VesselDataRepresentation.SURFACE_IMAGE_2D,
        source_label="Registered dorsal surface image",
        coordinate_frame_id="F",
        subject_id="mouse",
        registration_id="reg-1",
        registration_residual_um=25,
        physical_scale_calibrated=True,
        geometry_reviewed_by_user=True,
    )
    with pytest.raises(MeasurementError, match="cannot determine 3-D"):
        nearest_vessel_distance(placement=placement, provenance=image, vessels=())


def test_reference_vessel_distance_is_never_labelled_subject_specific_or_safe() -> None:
    context = AnimalSurgeryContext(subject_id="mouse")
    placement = _placement(context, _point(0, 0, 0), _point(0, 0, -1000))
    provenance = VesselGeometryProvenance(
        source_id="reference-graph-v1",
        source_kind=VesselGeometrySourceKind.REFERENCE_INDIVIDUAL_VESSEL_GRAPH,
        representation=VesselDataRepresentation.POLYLINE_3D,
        source_label="Reference individual-animal vessel graph",
        coordinate_frame_id="F",
        registration_id="atlas-registration-v1",
        registration_residual_um=50,
        physical_scale_calibrated=True,
        geometry_reviewed_by_user=True,
    )
    vessels = (
        VesselPolyline(
            vessel_id="v1",
            points=(_point(-1000, 300, -500), _point(1000, 300, -500)),
        ),
    )
    result = nearest_vessel_distance(
        placement=placement,
        provenance=provenance,
        vessels=vessels,
    )
    assert result.distance_um == pytest.approx(300)
    assert result.subject_specific is False
    assert result.safety_determination is False
    assert result.interpretation.startswith("reference-only")


def test_reviewed_subject_3d_geometry_distance_remains_non_safety_measurement() -> None:
    context = AnimalSurgeryContext(subject_id="mouse")
    placement = _placement(context, _point(0, 0, 0), _point(0, 0, -1000))
    provenance = VesselGeometryProvenance(
        source_id="subject-vessels",
        source_kind=VesselGeometrySourceKind.SUBJECT_REGISTERED_3D_SEGMENTATION,
        representation=VesselDataRepresentation.POLYLINE_3D,
        source_label="Reviewed registered 3-D vessel segmentation",
        coordinate_frame_id="F",
        subject_id="mouse",
        registration_id="reg-1",
        registration_residual_um=20,
        physical_scale_calibrated=True,
        geometry_reviewed_by_user=True,
    )
    result = nearest_vessel_distance(
        placement=placement,
        provenance=provenance,
        vessels=(
            VesselPolyline(
                vessel_id="v",
                points=(_point(-500, 100, -500), _point(500, 100, -500)),
            ),
        ),
    )
    assert result.distance_um == pytest.approx(100)
    assert result.subject_specific is True
    assert result.interpretation.endswith("not a safety determination")
    assert result.safety_determination is False


def test_vessel_distance_requires_scale_review_and_matching_frame() -> None:
    context = AnimalSurgeryContext()
    placement = _placement(context, _point(0, 0, 0), _point(0, 0, -1000))
    base = VesselGeometryProvenance(
        source_id="ref",
        source_kind=VesselGeometrySourceKind.REFERENCE_INDIVIDUAL_VESSEL_GRAPH,
        representation=VesselDataRepresentation.POLYLINE_3D,
        source_label="reference",
        coordinate_frame_id="F",
        registration_id="reg",
        registration_residual_um=10,
        physical_scale_calibrated=False,
        geometry_reviewed_by_user=True,
    )
    vessel = VesselPolyline(vessel_id="v", points=(_point(0, 100, 0), _point(0, 100, -1)))
    with pytest.raises(MeasurementError, match="physical scale"):
        nearest_vessel_distance(placement=placement, provenance=base, vessels=(vessel,))
    wrong_frame = base.model_copy(
        update={"physical_scale_calibrated": True, "coordinate_frame_id": "OTHER"}
    )
    with pytest.raises(MeasurementError, match="frame does not match"):
        nearest_vessel_distance(
            placement=placement,
            provenance=wrong_frame,
            vessels=(vessel,),
        )


def test_subject_vessel_geometry_must_match_planned_animal_identity() -> None:
    context = AnimalSurgeryContext(subject_id="mouse-a")
    placement = _placement(context, _point(0, 0, 0), _point(0, 0, -1000))
    provenance = VesselGeometryProvenance(
        source_id="subject-vessels",
        source_kind=VesselGeometrySourceKind.SUBJECT_REGISTERED_3D_SEGMENTATION,
        representation=VesselDataRepresentation.POLYLINE_3D,
        source_label="Different animal's vessel geometry",
        coordinate_frame_id="F",
        subject_id="mouse-b",
        registration_id="reg",
        registration_residual_um=10,
        physical_scale_calibrated=True,
        geometry_reviewed_by_user=True,
    )
    with pytest.raises(ValueError, match="does not match animal context"):
        nearest_vessel_distance(
            placement=placement,
            provenance=provenance,
            vessels=(
                VesselPolyline(
                    vessel_id="v",
                    points=(_point(0, 100, 0), _point(0, 100, -1000)),
                ),
            ),
        )
