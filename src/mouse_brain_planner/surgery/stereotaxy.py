"""Rigid bregma/lambda skull leveling with explicit residuals and QC."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.domain.stereotaxy_models import (
    BregmaRelativeTargetMM,
    CalibrationQCResult,
    CalibrationQuality,
    CalibrationQualityLimits,
    DorsoventralReference,
    SkullLandmarkSet,
    SkullLevelingAngles,
    StereotaxicCalibration,
)
from mouse_brain_planner.domain.surgery_common import AnimalSurgeryContext
from mouse_brain_planner.domain.transform_models import (
    AnatomicalFrameDefinition,
    AnatomicalPoint,
    AnatomicalTransform,
    CoordinateSystemKind,
    LandmarkCorrespondence3D,
    TransformLandmarkResidual,
    TransformMethod,
)


class StereotaxicCalibrationError(ValueError):
    """Raised when landmarks cannot define a trustworthy rigid frame."""


def calibrate_skull_landmarks(
    *,
    context: AnimalSurgeryContext,
    profile_id: str,
    source_frame: AnatomicalFrameDefinition,
    landmarks: SkullLandmarkSet,
    dv_reference: DorsoventralReference,
    dv_reference_description: str,
    quality_limits: CalibrationQualityLimits,
    limits_source: str,
    version: int = 1,
    notes: str = "",
) -> StereotaxicCalibration:
    """Create a right-handed bregma-origin stereotaxic frame.

    Positive AP points from lambda toward bregma, positive ML points from the
    confirmed left landmark toward the right landmark, and positive DV is the
    cross product ``AP cross ML``, labelled dorsal/up in the explicit calibrated
    AP/ML/DV component convention.  A full 3-D frame is rejected when either measured
    baseline is shorter than the caller's documented QC minimum.
    """

    if source_frame.kind is not CoordinateSystemKind.SKULL:
        raise StereotaxicCalibrationError("source frame must be explicitly classified as skull")
    if dv_reference is not DorsoventralReference.BREGMA:
        raise StereotaxicCalibrationError(
            "this bregma-origin calibration requires DV reference 'bregma'; "
            "surface or user-plane DV references require a separately measured plane transform"
        )
    if landmarks.bregma.frame_id != source_frame.frame_id:
        raise StereotaxicCalibrationError("landmark frame does not match source skull frame")
    if version <= 0:
        raise StereotaxicCalibrationError("calibration transform version must be positive")

    bregma = _point_array(landmarks.bregma)
    lambda_point = _point_array(landmarks.lambda_point)
    left = _point_array(landmarks.left_skull)
    right = _point_array(landmarks.right_skull)

    ap_seed = bregma - lambda_point
    ap_length = float(np.linalg.norm(ap_seed))
    if ap_length < quality_limits.minimum_axis_baseline_um:
        raise StereotaxicCalibrationError(
            "bregma-lambda baseline is shorter than the configured minimum "
            f"({ap_length:g} < {quality_limits.minimum_axis_baseline_um:g} micrometres)"
        )
    ap_axis = ap_seed / ap_length

    lateral_seed = right - left
    lateral_projected = lateral_seed - float(np.dot(lateral_seed, ap_axis)) * ap_axis
    lateral_length = float(np.linalg.norm(lateral_projected))
    if lateral_length < quality_limits.minimum_axis_baseline_um:
        raise StereotaxicCalibrationError(
            "left-right baseline does not independently define ML after AP projection "
            f"({lateral_length:g} < {quality_limits.minimum_axis_baseline_um:g} micrometres)"
        )
    ml_axis = lateral_projected / lateral_length
    dv_axis = np.cross(ap_axis, ml_axis)
    dv_axis /= np.linalg.norm(dv_axis)
    ml_axis = np.cross(dv_axis, ap_axis)
    ml_axis /= np.linalg.norm(ml_axis)

    rotation = np.stack((ap_axis, ml_axis, dv_axis), axis=0)
    determinant = float(np.linalg.det(rotation))
    if not math.isclose(determinant, 1.0, rel_tol=0, abs_tol=1e-10):
        raise StereotaxicCalibrationError(
            f"skull leveling did not produce a proper right-handed rotation ({determinant:g})"
        )
    translation = -(rotation @ bregma)
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation

    destination_frame = AnatomicalFrameDefinition(
        frame_id=f"STEREOTAXIC:{profile_id}",
        kind=CoordinateSystemKind.STEREOTAXIC,
        origin_description="User-measured bregma; AP=0, ML=0, and DV=0",
        ap_positive_direction="anterior (lambda toward bregma)",
        ml_positive_direction="animal right (confirmed left-skull toward right-skull)",
        dv_positive_direction="dorsal/up (AP cross ML in calibrated AP/ML/DV components)",
    )

    source_points = (bregma, lambda_point, left, right)
    mapped = _apply(matrix, source_points)
    pair_distance = float(np.linalg.norm(right - left))
    lateral_midpoint = (mapped[2] + mapped[3]) / 2.0
    targets = np.asarray(
        [
            (0.0, 0.0, 0.0),
            (-landmarks.reported_bregma_lambda_distance_um, 0.0, 0.0),
            (
                lateral_midpoint[0],
                lateral_midpoint[1] - pair_distance / 2.0,
                lateral_midpoint[2],
            ),
            (
                lateral_midpoint[0],
                lateral_midpoint[1] + pair_distance / 2.0,
                lateral_midpoint[2],
            ),
        ],
        dtype=np.float64,
    )
    labels = ("bregma", "lambda", "left-skull", "right-skull")
    source_models = (
        landmarks.bregma,
        landmarks.lambda_point,
        landmarks.left_skull,
        landmarks.right_skull,
    )
    correspondences = tuple(
        LandmarkCorrespondence3D(
            label=label,
            source=source,
            destination=_point(destination_frame.frame_id, target),
        )
        for label, source, target in zip(labels, source_models, targets, strict=True)
    )
    errors = mapped - targets
    radial = np.linalg.norm(errors, axis=1)
    residuals = tuple(
        TransformLandmarkResidual(
            landmark_uuid=correspondence.landmark_uuid,
            ap_error_um=float(error[0]),
            ml_error_um=float(error[1]),
            dv_error_um=float(error[2]),
            radial_error_um=float(distance),
        )
        for correspondence, error, distance in zip(
            correspondences,
            errors,
            radial,
            strict=True,
        )
    )
    rms = float(np.sqrt(np.mean(np.square(radial))))
    maximum = float(np.max(radial))
    transform = AnatomicalTransform(
        version=version,
        source_frame=source_frame,
        destination_frame=destination_frame,
        method=TransformMethod.RIGID,
        matrix_row_major=_matrix_tuple(matrix),
        landmarks=correspondences,
        residuals=residuals,
        rms_residual_um=rms,
        max_residual_um=maximum,
        notes=notes,
    )

    distance_error = abs(ap_length - landmarks.reported_bregma_lambda_distance_um)
    lateral_ap_mismatch = abs(float(mapped[3, 0] - mapped[2, 0]))
    lateral_dv_mismatch = abs(float(mapped[3, 2] - mapped[2, 2]))
    quality, messages = _quality(
        distance_error=distance_error,
        lateral_ap_mismatch=lateral_ap_mismatch,
        rms=rms,
        limits=quality_limits,
    )
    qc = CalibrationQCResult(
        quality=quality,
        geometric_bregma_lambda_distance_um=ap_length,
        reported_bregma_lambda_distance_um=landmarks.reported_bregma_lambda_distance_um,
        bregma_lambda_distance_error_um=distance_error,
        lateral_landmark_ap_mismatch_um=lateral_ap_mismatch,
        lateral_landmark_dv_mismatch_um=lateral_dv_mismatch,
        transform_rms_residual_um=rms,
        transform_max_residual_um=maximum,
        messages=messages,
        limits_source=limits_source,
    )
    return StereotaxicCalibration(
        profile_id=profile_id,
        context=context,
        source_frame=source_frame,
        stereotaxic_frame=destination_frame,
        landmarks=landmarks,
        dv_reference=dv_reference,
        dv_reference_description=dv_reference_description,
        transform=transform,
        leveling_angles=_rotation_angles(rotation),
        quality_limits=quality_limits,
        qc=qc,
        notes=notes,
    )


def bregma_relative_target_to_point(
    *,
    target: BregmaRelativeTargetMM,
    calibration: StereotaxicCalibration,
) -> AnatomicalPoint:
    """Convert calibrated bregma-relative millimetres to internal micrometres.

    Signs are preserved exactly: negative AP is posterior/back, negative ML is
    left, and negative DV is deep/ventral.  This operation intentionally has no
    overload without a calibration.
    """

    if target.context_uuid != calibration.context.context_uuid:
        raise StereotaxicCalibrationError("target animal context does not match calibration")
    if target.calibration_uuid != calibration.calibration_uuid:
        raise StereotaxicCalibrationError("target calibration UUID does not match calibration")
    if target.profile_id != calibration.profile_id:
        raise StereotaxicCalibrationError("target profile ID does not match calibration")
    if target.stereotaxic_frame_id != calibration.stereotaxic_frame.frame_id:
        raise StereotaxicCalibrationError("target frame does not match calibration frame")
    if not calibration.permits_planning:
        raise StereotaxicCalibrationError("failed calibration cannot convert an implant target")
    return AnatomicalPoint(
        frame_id=calibration.stereotaxic_frame.frame_id,
        ap_um=target.ap_mm * 1000.0,
        ml_um=target.ml_mm * 1000.0,
        dv_um=target.dv_mm * 1000.0,
    )


def _quality(
    *,
    distance_error: float,
    lateral_ap_mismatch: float,
    rms: float,
    limits: CalibrationQualityLimits,
) -> tuple[CalibrationQuality, tuple[str, ...]]:
    values = (
        (
            "bregma-lambda distance error",
            distance_error,
            limits.distance_warning_um,
            limits.distance_failure_um,
        ),
        (
            "left-right AP mismatch",
            lateral_ap_mismatch,
            limits.lateral_ap_warning_um,
            limits.lateral_ap_failure_um,
        ),
        (
            "transform landmark RMS residual",
            rms,
            limits.transform_rms_warning_um,
            limits.transform_rms_failure_um,
        ),
    )
    quality = CalibrationQuality.PASS
    messages: list[str] = []
    for label, value, warning, failure in values:
        if value >= failure:
            quality = CalibrationQuality.FAIL
            messages.append(
                f"FAIL: {label} {value:g} micrometres is at or above configured "
                f"failure limit {failure:g}"
            )
        elif value >= warning:
            if quality is CalibrationQuality.PASS:
                quality = CalibrationQuality.WARNING
            messages.append(
                f"WARNING: {label} {value:g} micrometres is at or above configured "
                f"warning limit {warning:g}"
            )
    if not messages:
        messages.append(
            "PASS: all configured numerical calibration checks are below warning limits"
        )
    return quality, tuple(messages)


def _rotation_angles(rotation: NDArray[np.float64]) -> SkullLevelingAngles:
    pitch = math.asin(float(np.clip(-rotation[2, 0], -1.0, 1.0)))
    cosine_pitch = math.cos(pitch)
    if abs(cosine_pitch) > 1e-12:
        roll = math.atan2(float(rotation[2, 1]), float(rotation[2, 2]))
        yaw = math.atan2(float(rotation[1, 0]), float(rotation[0, 0]))
    else:
        roll = 0.0
        yaw = math.atan2(float(-rotation[0, 1]), float(rotation[1, 1]))
    return SkullLevelingAngles(
        pitch_deg=math.degrees(pitch),
        roll_deg=math.degrees(roll),
        yaw_deg=math.degrees(yaw),
    )


def _point_array(point: AnatomicalPoint) -> NDArray[np.float64]:
    return np.asarray(point.as_ap_ml_dv(), dtype=np.float64)


def _point(frame_id: str, values: NDArray[np.float64]) -> AnatomicalPoint:
    return AnatomicalPoint(
        frame_id=frame_id,
        ap_um=float(values[0]),
        ml_um=float(values[1]),
        dv_um=float(values[2]),
    )


def _apply(
    matrix: NDArray[np.float64],
    points: tuple[NDArray[np.float64], ...],
) -> NDArray[np.float64]:
    values = np.asarray(points, dtype=np.float64)
    homogeneous = np.column_stack((values, np.ones(values.shape[0], dtype=np.float64)))
    return (matrix @ homogeneous.T).T[:, :3]


def _matrix_tuple(
    matrix: NDArray[np.float64],
) -> tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
]:
    values = matrix.reshape(16)
    return tuple(float(value) for value in values)  # type: ignore[return-value]
