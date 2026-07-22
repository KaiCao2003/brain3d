from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError

from mouse_brain_planner.coordinates.transforms import transform_point
from mouse_brain_planner.domain.stereotaxy_models import (
    BregmaRelativeTargetMM,
    CalibrationQuality,
    CalibrationQualityLimits,
    DorsoventralReference,
    SkullLandmarkSet,
    StereotaxicCalibration,
)
from mouse_brain_planner.domain.surgery_common import AnimalSurgeryContext
from mouse_brain_planner.domain.transform_models import (
    AnatomicalFrameDefinition,
    AnatomicalPoint,
    CoordinateSystemKind,
)
from mouse_brain_planner.surgery.stereotaxy import (
    StereotaxicCalibrationError,
    bregma_relative_target_to_point,
    calibrate_skull_landmarks,
)


def _point(frame_id: str, ap: float, ml: float, dv: float) -> AnatomicalPoint:
    return AnatomicalPoint(frame_id=frame_id, ap_um=ap, ml_um=ml, dv_um=dv)


def _source_frame() -> AnatomicalFrameDefinition:
    return AnatomicalFrameDefinition(
        frame_id="MEASURED_SKULL_AP_ML_DV_UM",
        kind=CoordinateSystemKind.SKULL,
        origin_description="Micromanipulator origin recorded for this animal",
        ap_positive_direction="apparatus positive AP",
        ml_positive_direction="apparatus positive ML",
        dv_positive_direction="apparatus positive DV",
    )


def _limits() -> CalibrationQualityLimits:
    return CalibrationQualityLimits(
        minimum_axis_baseline_um=100,
        distance_warning_um=100,
        distance_failure_um=300,
        lateral_ap_warning_um=100,
        lateral_ap_failure_um=300,
        transform_rms_warning_um=100,
        transform_rms_failure_um=300,
    )


def _calibration(
    *,
    reported_distance_um: float = 4000,
    context: AnimalSurgeryContext | None = None,
) -> StereotaxicCalibration:
    frame = _source_frame()
    landmarks = SkullLandmarkSet(
        bregma=_point(frame.frame_id, 1000, 2000, 3000),
        lambda_point=_point(frame.frame_id, -3000, 2000, 3000),
        left_skull=_point(frame.frame_id, 1000, 0, 3000),
        right_skull=_point(frame.frame_id, 1000, 4000, 3000),
        reported_bregma_lambda_distance_um=reported_distance_um,
        laterality_confirmed_from_the_animal=True,
    )
    return calibrate_skull_landmarks(
        context=context or AnimalSurgeryContext(subject_id="mouse-17"),
        profile_id="mouse-17-session-1",
        source_frame=frame,
        landmarks=landmarks,
        dv_reference=DorsoventralReference.BREGMA,
        dv_reference_description="DV zero is user-measured bregma",
        quality_limits=_limits(),
        limits_source="Lab SOP stereotaxic QC revision 3",
    )


def test_animal_context_fails_closed_for_human_or_clinical_payloads() -> None:
    context = AnimalSurgeryContext(subject_id="mouse-17")
    assert context.species == "Mus musculus"
    assert context.certified_navigation_device is False
    assert context.independent_coordinate_verification_required is True

    payload = context.model_dump(mode="json")
    payload["species"] = "Homo sapiens"
    with pytest.raises(ValidationError, match="Mus musculus"):
        AnimalSurgeryContext.model_validate(payload)
    payload = context.model_dump(mode="json")
    payload["certified_navigation_device"] = True
    with pytest.raises(ValidationError):
        AnimalSurgeryContext.model_validate(payload)


def test_bregma_lambda_calibration_has_explicit_signs_residuals_and_round_trip() -> None:
    calibration = _calibration()

    assert calibration.qc.quality is CalibrationQuality.PASS
    assert calibration.transform.determinant == pytest.approx(1.0)
    assert calibration.transform.rms_residual_um == pytest.approx(0.0)
    assert calibration.stereotaxic_frame.ap_positive_direction.startswith("anterior")
    assert calibration.stereotaxic_frame.ml_positive_direction.startswith("animal right")
    assert calibration.stereotaxic_frame.dv_positive_direction.startswith("dorsal/up")
    mapped_bregma = transform_point(calibration.transform, calibration.landmarks.bregma)
    mapped_lambda = transform_point(calibration.transform, calibration.landmarks.lambda_point)
    assert mapped_bregma.as_ap_ml_dv() == pytest.approx((0, 0, 0), abs=1e-9)
    assert mapped_lambda.as_ap_ml_dv() == pytest.approx((-4000, 0, 0), abs=1e-9)
    assert calibration.leveling_angles.pitch_deg == pytest.approx(0)
    assert calibration.leveling_angles.roll_deg == pytest.approx(0)
    assert calibration.leveling_angles.yaw_deg == pytest.approx(0)

    restored = StereotaxicCalibration.model_validate_json(calibration.model_dump_json())
    assert restored == calibration


def test_direct_bregma_relative_mm_preserves_user_sign_convention_exactly() -> None:
    calibration = _calibration()
    target = BregmaRelativeTargetMM(
        context_uuid=calibration.context.context_uuid,
        calibration_uuid=calibration.calibration_uuid,
        profile_id=calibration.profile_id,
        stereotaxic_frame_id=calibration.stereotaxic_frame.frame_id,
        ap_mm=-1.25,
        ml_mm=-0.7,
        dv_mm=-2.4,
    )

    point = bregma_relative_target_to_point(target=target, calibration=calibration)
    assert point.as_ap_ml_dv() == pytest.approx((-1250, -700, -2400))
    assert target.ap_negative_direction == "posterior/back"
    assert target.ml_negative_direction == "left"
    assert target.dv_negative_direction == "deep/ventral"
    assert target.ap_positive_direction == "anterior"
    assert target.ml_positive_direction == "right"
    assert target.dv_positive_direction == "dorsal/up"


def test_direct_target_requires_exact_calibration_identity_and_passing_qc() -> None:
    calibration = _calibration()
    target = BregmaRelativeTargetMM(
        context_uuid=calibration.context.context_uuid,
        calibration_uuid=uuid4(),
        profile_id=calibration.profile_id,
        stereotaxic_frame_id=calibration.stereotaxic_frame.frame_id,
        ap_mm=0,
        ml_mm=0,
        dv_mm=-1,
    )
    with pytest.raises(StereotaxicCalibrationError, match="UUID"):
        bregma_relative_target_to_point(target=target, calibration=calibration)

    failed = _calibration(reported_distance_um=5000)
    assert failed.qc.quality is CalibrationQuality.FAIL
    assert not failed.permits_planning
    failed_target = target.model_copy(
        update={
            "context_uuid": failed.context.context_uuid,
            "calibration_uuid": failed.calibration_uuid,
            "profile_id": failed.profile_id,
            "stereotaxic_frame_id": failed.stereotaxic_frame.frame_id,
        }
    )
    with pytest.raises(StereotaxicCalibrationError, match="failed calibration"):
        bregma_relative_target_to_point(target=failed_target, calibration=failed)


def test_calibration_recovers_rotated_translated_landmarks() -> None:
    frame = _source_frame()
    angle = np.deg2rad(20)
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0],
            [np.sin(angle), np.cos(angle), 0],
            [0, 0, 1],
        ]
    )
    canonical = np.array(
        [[0, 0, 0], [-4000, 0, 0], [0, -2000, 0], [0, 2000, 0]],
        dtype=float,
    )
    raw = canonical @ rotation.T + np.array([700, -900, 250])
    landmarks = SkullLandmarkSet(
        bregma=_point(frame.frame_id, *raw[0]),
        lambda_point=_point(frame.frame_id, *raw[1]),
        left_skull=_point(frame.frame_id, *raw[2]),
        right_skull=_point(frame.frame_id, *raw[3]),
        reported_bregma_lambda_distance_um=4000,
        laterality_confirmed_from_the_animal=True,
    )
    calibration = calibrate_skull_landmarks(
        context=AnimalSurgeryContext(),
        profile_id="rotated",
        source_frame=frame,
        landmarks=landmarks,
        dv_reference=DorsoventralReference.BREGMA,
        dv_reference_description="bregma",
        quality_limits=_limits(),
        limits_source="test fixture thresholds",
    )
    mapped = tuple(
        transform_point(calibration.transform, point).as_ap_ml_dv()
        for point in (landmarks.bregma, landmarks.lambda_point)
    )
    assert mapped[0] == pytest.approx((0, 0, 0), abs=1e-9)
    assert mapped[1] == pytest.approx((-4000, 0, 0), abs=1e-9)
    assert calibration.leveling_angles.yaw_deg == pytest.approx(-20)


def test_calibration_rejects_degenerate_or_frame_mixed_landmarks() -> None:
    frame = _source_frame()
    other = "OTHER_SKULL_FRAME"
    with pytest.raises(ValidationError, match="same explicit source frame"):
        SkullLandmarkSet(
            bregma=_point(frame.frame_id, 0, 0, 0),
            lambda_point=_point(frame.frame_id, -4000, 0, 0),
            left_skull=_point(other, 0, -2000, 0),
            right_skull=_point(frame.frame_id, 0, 2000, 0),
            reported_bregma_lambda_distance_um=4000,
            laterality_confirmed_from_the_animal=True,
        )

    collinear = SkullLandmarkSet(
        bregma=_point(frame.frame_id, 0, 0, 0),
        lambda_point=_point(frame.frame_id, -4000, 0, 0),
        left_skull=_point(frame.frame_id, -1000, 0, 0),
        right_skull=_point(frame.frame_id, 1000, 0, 0),
        reported_bregma_lambda_distance_um=4000,
        laterality_confirmed_from_the_animal=True,
    )
    with pytest.raises(StereotaxicCalibrationError, match="does not independently define ML"):
        calibrate_skull_landmarks(
            context=AnimalSurgeryContext(),
            profile_id="invalid",
            source_frame=frame,
            landmarks=collinear,
            dv_reference=DorsoventralReference.BREGMA,
            dv_reference_description="bregma",
            quality_limits=_limits(),
            limits_source="test fixture thresholds",
        )


def test_bregma_builder_rejects_unmeasured_surface_dv_reference() -> None:
    frame = _source_frame()
    landmarks = SkullLandmarkSet(
        bregma=_point(frame.frame_id, 0, 0, 0),
        lambda_point=_point(frame.frame_id, -4000, 0, 0),
        left_skull=_point(frame.frame_id, 0, -2000, 0),
        right_skull=_point(frame.frame_id, 0, 2000, 0),
        reported_bregma_lambda_distance_um=4000,
        laterality_confirmed_from_the_animal=True,
    )
    with pytest.raises(StereotaxicCalibrationError, match="separately measured plane transform"):
        calibrate_skull_landmarks(
            context=AnimalSurgeryContext(),
            profile_id="invalid-dv-reference",
            source_frame=frame,
            landmarks=landmarks,
            dv_reference=DorsoventralReference.SKULL_SURFACE_AT_INSERTION,
            dv_reference_description="not actually measured",
            quality_limits=_limits(),
            limits_source="test fixture thresholds",
        )


@pytest.mark.parametrize("invalid", [True, float("nan"), float("inf"), float("-inf")])
def test_calibration_domain_rejects_boolean_or_nonfinite_scientific_numbers(
    invalid: object,
) -> None:
    with pytest.raises(ValidationError):
        AnatomicalPoint(
            frame_id="explicit",
            ap_um=invalid,
            ml_um=0,
            dv_um=0,
        )
    with pytest.raises(ValidationError):
        CalibrationQualityLimits(
            minimum_axis_baseline_um=invalid,
            distance_warning_um=100,
            distance_failure_um=300,
            lateral_ap_warning_um=100,
            lateral_ap_failure_um=300,
            transform_rms_warning_um=100,
            transform_rms_failure_um=300,
        )


def test_calibrated_target_domain_rejects_boolean_coordinate() -> None:
    calibration = _calibration()

    with pytest.raises(ValidationError, match="must not be booleans"):
        BregmaRelativeTargetMM(
            context_uuid=calibration.context.context_uuid,
            calibration_uuid=calibration.calibration_uuid,
            profile_id=calibration.profile_id,
            stereotaxic_frame_id=calibration.stereotaxic_frame.frame_id,
            ap_mm=True,
            ml_mm=0,
            dv_mm=-1,
        )
