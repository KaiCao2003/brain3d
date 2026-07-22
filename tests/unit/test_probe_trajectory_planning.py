from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from mouse_brain_planner.domain.probe_models import (
    NormalizedProbePlacement,
    ProbeLocalPoint,
    ProbeModelDefinition,
    ProbeModelVerification,
    ProbeShankDefinition,
    ProbeSiteRole,
    ProbeSourceArtifact,
    ProbeTipGeometry,
    ProbeVerificationStatus,
    RecordingSiteDefinition,
)
from mouse_brain_planner.domain.stereotaxy_models import (
    BregmaRelativeTargetMM,
    CalibrationQualityLimits,
    DorsoventralReference,
    SkullLandmarkSet,
)
from mouse_brain_planner.domain.surgery_common import AnimalSurgeryContext
from mouse_brain_planner.domain.transform_models import (
    AnatomicalFrameDefinition,
    AnatomicalPoint,
    CoordinateSystemKind,
)
from mouse_brain_planner.surgery.stereotaxy import calibrate_skull_landmarks
from mouse_brain_planner.surgery.trajectory import (
    ProbePlacementError,
    angles_from_direction,
    attach_surface_entries,
    direction_from_angles,
    placed_recording_sites,
    placement_from_bregma_relative_mm,
    placement_from_entry_angles_depth,
    placement_from_entry_target,
    placement_from_target_angles_depth,
    placement_permits_final_export,
)


def _point(frame: str, ap: float, ml: float, dv: float) -> AnatomicalPoint:
    return AnatomicalPoint(frame_id=frame, ap_um=ap, ml_um=ml, dv_um=dv)


def _custom_model(*, acknowledged_source: bool = False) -> ProbeModelDefinition:
    verification = ProbeModelVerification(
        status=ProbeVerificationStatus.USER_DEFINED_UNVERIFIED,
        review_notes="Test-only user-entered geometry",
    )
    return ProbeModelDefinition(
        model_id="user:test-linear",
        model_version="1",
        display_name="Test-only custom linear probe",
        verification=verification,
        declared_shank_count=1,
        expected_site_count=2,
        shanks=(
            ProbeShankDefinition(
                shank_id="A",
                length_um=4000,
                width_um=70,
                thickness_um=24,
                tip_geometry=ProbeTipGeometry.USER_DEFINED,
                tip_length_um=100,
                tip_geometry_notes="Explicit test fixture; not a device specification",
                sites=(
                    RecordingSiteDefinition(
                        site_id="A-001",
                        local=ProbeLocalPoint(axial_from_tip_um=100),
                        bank="0",
                    ),
                    RecordingSiteDefinition(
                        site_id="A-ref",
                        local=ProbeLocalPoint(axial_from_tip_um=1000),
                        role=ProbeSiteRole.REFERENCE,
                    ),
                ),
            ),
        ),
        geometry_notes=("acknowledged" if acknowledged_source else "unverified test geometry"),
    )


def _calibration(context: AnimalSurgeryContext):
    frame = AnatomicalFrameDefinition(
        frame_id="SKULL",
        kind=CoordinateSystemKind.SKULL,
        origin_description="test rig",
        ap_positive_direction="anterior",
        ml_positive_direction="right",
        dv_positive_direction="dorsal",
    )
    landmarks = SkullLandmarkSet(
        bregma=_point(frame.frame_id, 0, 0, 0),
        lambda_point=_point(frame.frame_id, -4000, 0, 0),
        left_skull=_point(frame.frame_id, 0, -2000, 0),
        right_skull=_point(frame.frame_id, 0, 2000, 0),
        reported_bregma_lambda_distance_um=4000,
        laterality_confirmed_from_the_animal=True,
    )
    return calibrate_skull_landmarks(
        context=context,
        profile_id="mouse-cal",
        source_frame=frame,
        landmarks=landmarks,
        dv_reference=DorsoventralReference.BREGMA,
        dv_reference_description="bregma",
        quality_limits=CalibrationQualityLimits(
            minimum_axis_baseline_um=100,
            distance_warning_um=100,
            distance_failure_um=300,
            lateral_ap_warning_um=100,
            lateral_ap_failure_um=300,
            transform_rms_warning_um=100,
            transform_rms_failure_um=300,
        ),
        limits_source="test fixture",
    )


def test_verified_model_label_requires_complete_source_and_independent_review() -> None:
    with pytest.raises(ValidationError, match="primary source"):
        ProbeModelVerification(
            status=ProbeVerificationStatus.VERIFIED,
            complete_geometry_transcribed=True,
            independent_transcription_review_completed=True,
            transcribed_by="A",
            independently_reviewed_by="B",
        )

    source = ProbeSourceArtifact(
        title="Test-only manufacturer data sheet",
        source_url="https://example.invalid/test-probe.pdf",
        document_revision="rev-test",
        retrieved_on=date(2026, 7, 21),
        sha256="a" * 64,
        citation="Test fixture only; no production model dimensions",
    )
    verification = ProbeModelVerification(
        status=ProbeVerificationStatus.VERIFIED,
        primary_sources=(source,),
        complete_geometry_transcribed=True,
        independent_transcription_review_completed=True,
        transcribed_by="Transcriber",
        independently_reviewed_by="Independent reviewer",
    )
    base = _custom_model()
    verified = base.model_copy(
        update={
            "model_id": "test:verified-fixture",
            "manufacturer": "Fixture manufacturer",
            "product_code": "FIXTURE-ONLY",
            "hardware_revision": "test",
            "verification": verification,
        }
    )
    verified = ProbeModelDefinition.model_validate(verified.model_dump(mode="python"))
    assert verified.permits_verified_device_label


def test_probe_model_rejects_sites_outside_declared_geometry() -> None:
    with pytest.raises(ValidationError, match="beyond declared shank length"):
        ProbeShankDefinition(
            shank_id="bad",
            length_um=100,
            width_um=20,
            thickness_um=10,
            tip_geometry=ProbeTipGeometry.FLAT,
            tip_length_um=10,
            tip_geometry_notes="fixture",
            sites=(
                RecordingSiteDefinition(
                    site_id="outside",
                    local=ProbeLocalPoint(axial_from_tip_um=101),
                ),
            ),
        )


def test_four_trajectory_inputs_normalize_to_same_deep_vertical_geometry() -> None:
    context = AnimalSurgeryContext(subject_id="m1")
    model = _custom_model()
    frame = "STEREOTAXIC:mouse-cal"
    entry = _point(frame, -1000, -500, 0)
    target = _point(frame, -1000, -500, -2000)

    from_points = placement_from_entry_target(
        context=context,
        model=model,
        name="points",
        entry=entry,
        target=target,
    )
    from_entry_angles = placement_from_entry_angles_depth(
        context=context,
        model=model,
        name="entry angles",
        entry=entry,
        azimuth_deg=0,
        elevation_deg=-90,
        insertion_depth_um=2000,
    )
    from_target_angles = placement_from_target_angles_depth(
        context=context,
        model=model,
        name="target angles",
        target=target,
        azimuth_deg=0,
        elevation_deg=-90,
        insertion_depth_um=2000,
    )
    calibration = _calibration(context)
    direct_mm = BregmaRelativeTargetMM(
        context_uuid=context.context_uuid,
        calibration_uuid=calibration.calibration_uuid,
        profile_id=calibration.profile_id,
        stereotaxic_frame_id=calibration.stereotaxic_frame.frame_id,
        ap_mm=-1,
        ml_mm=-0.5,
        dv_mm=-2,
    )
    from_bregma_mm = placement_from_bregma_relative_mm(
        calibration=calibration,
        model=model,
        name="direct mm",
        target=direct_mm,
        manipulator_azimuth_deg=0,
        manipulator_elevation_deg=-90,
        insertion_depth_um=2000,
    )

    for placement in (from_points, from_entry_angles, from_target_angles, from_bregma_mm):
        assert placement.entry.as_ap_ml_dv() == pytest.approx(entry.as_ap_ml_dv())
        assert placement.tip.as_ap_ml_dv() == pytest.approx(target.as_ap_ml_dv())
        assert placement.inward_direction.as_ap_ml_dv() == pytest.approx((0, 0, -1))
        assert placement.elevation_deg == pytest.approx(-90)
        assert placement.azimuth_deg == pytest.approx(0)


def test_angle_round_trip_and_serialized_geometry_tamper_are_fail_closed() -> None:
    direction = direction_from_angles(frame_id="F", azimuth_deg=35, elevation_deg=-42)
    assert angles_from_direction(direction) == pytest.approx((35, -42))

    placement = placement_from_entry_angles_depth(
        context=AnimalSurgeryContext(),
        model=_custom_model(),
        name="p",
        entry=_point("F", 0, 0, 0),
        azimuth_deg=35,
        elevation_deg=-42,
        insertion_depth_um=2000,
    )
    payload = placement.model_dump(mode="python")
    payload["insertion_depth_um"] = 2100
    with pytest.raises(ValidationError, match="does not match entry-tip"):
        NormalizedProbePlacement.model_validate(payload)


def test_recording_sites_map_from_tip_toward_base_and_custom_export_is_acknowledged() -> None:
    model = _custom_model()
    placement = placement_from_entry_angles_depth(
        context=AnimalSurgeryContext(),
        model=model,
        name="p",
        entry=_point("F", 0, 0, 0),
        azimuth_deg=0,
        elevation_deg=-90,
        insertion_depth_um=2000,
        selected_site_ids=("A-001",),
    )
    sites = placed_recording_sites(model, placement)
    assert [site.site_id for site in sites] == ["A-001", "A-ref"]
    assert sites[0].point.as_ap_ml_dv() == pytest.approx((0, 0, -1900))
    assert sites[1].point.as_ap_ml_dv() == pytest.approx((0, 0, -1000))
    selected = placed_recording_sites(model, placement, selected_only=True)
    assert [site.site_id for site in selected] == ["A-001"]
    assert not placement_permits_final_export(model, placement)
    acknowledged = placement.model_copy(update={"custom_geometry_acknowledged": True})
    assert placement_permits_final_export(model, acknowledged)


def test_surface_intersections_must_be_collinear_and_ordered() -> None:
    placement = placement_from_entry_angles_depth(
        context=AnimalSurgeryContext(),
        model=_custom_model(),
        name="p",
        entry=_point("F", 0, 0, 0),
        azimuth_deg=0,
        elevation_deg=-90,
        insertion_depth_um=2000,
    )
    attached = attach_surface_entries(
        placement,
        skull_entry=_point("F", 0, 0, 100),
        brain_entry=_point("F", 0, 0, 0),
    )
    assert attached.skull_entry is not None
    with pytest.raises(ValidationError, match="off the normalized trajectory"):
        attach_surface_entries(
            placement,
            skull_entry=_point("F", 10, 0, 100),
            brain_entry=_point("F", 0, 0, 0),
        )
    with pytest.raises(ValidationError, match="skull entry must occur before"):
        attach_surface_entries(
            placement,
            skull_entry=_point("F", 0, 0, -500),
            brain_entry=_point("F", 0, 0, 0),
        )


def test_entry_target_frame_mismatch_and_unknown_sites_are_rejected() -> None:
    context = AnimalSurgeryContext()
    model = _custom_model()
    with pytest.raises(ProbePlacementError, match="one explicit coordinate frame"):
        placement_from_entry_target(
            context=context,
            model=model,
            name="bad",
            entry=_point("A", 0, 0, 0),
            target=_point("B", 0, 0, -1000),
        )
    placement = placement_from_entry_angles_depth(
        context=context,
        model=model,
        name="bad site",
        entry=_point("A", 0, 0, 0),
        azimuth_deg=0,
        elevation_deg=-90,
        insertion_depth_um=1000,
        selected_site_ids=("not-a-site",),
    )
    with pytest.raises(ProbePlacementError, match="unknown recording sites"):
        placed_recording_sites(model, placement)
