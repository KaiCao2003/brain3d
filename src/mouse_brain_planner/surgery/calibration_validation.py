"""Reproduce persisted subject calibration fits from their measured inputs."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Final

import numpy as np

from mouse_brain_planner.coordinates.transforms import (
    fit_anatomical_transform,
    transform_point,
)
from mouse_brain_planner.domain.stereotaxy_models import (
    AtlasRegisteredCalibration,
    CalibrationQCResult,
    SkullLevelingAngles,
)
from mouse_brain_planner.domain.transform_models import (
    AnatomicalPoint,
    AnatomicalTransform,
    LandmarkCorrespondence3D,
    TransformLandmarkResidual,
)
from mouse_brain_planner.surgery.stereotaxy import calibrate_skull_landmarks

_FIT_RELATIVE_TOLERANCE: Final = 1e-12
_FIT_ABSOLUTE_TOLERANCE: Final = 1e-8


class CalibrationReproducibilityError(ValueError):
    """Raised when persisted derived calibration data cannot be reproduced."""


def validate_atlas_registered_calibration_reproducibility(
    calibration: AtlasRegisteredCalibration,
) -> None:
    """Fail closed unless both persisted fits reproduce from stored landmarks.

    Stable identity fields such as calibration and transform UUIDs are not
    regenerated. Every geometric or QC-relevant value is regenerated through
    the same production fit functions used at creation, then compared with a
    tolerance far below one micrometre.
    """

    skull = calibration.skull_calibration
    rebuilt_skull = calibrate_skull_landmarks(
        context=skull.context,
        profile_id=skull.profile_id,
        source_frame=skull.source_frame,
        landmarks=skull.landmarks,
        dv_reference=skull.dv_reference,
        dv_reference_description=skull.dv_reference_description,
        quality_limits=skull.quality_limits,
        limits_source=skull.qc.limits_source,
        version=calibration.calibration_version,
        notes=skull.notes,
    )
    if rebuilt_skull.stereotaxic_frame != skull.stereotaxic_frame:
        raise CalibrationReproducibilityError(
            "skull stereotaxic frame does not reproduce from stored landmarks"
        )
    _compare_transform(
        rebuilt_skull.transform,
        skull.transform,
        label="skull transform",
        regenerated_landmark_ids=True,
    )
    _compare_leveling_angles(rebuilt_skull.leveling_angles, skull.leveling_angles)
    _compare_skull_qc(rebuilt_skull.qc, skull.qc)

    transform = calibration.atlas_transform
    _validate_required_atlas_sources(
        calibration=calibration,
        rebuilt_skull_transform=rebuilt_skull.transform,
    )
    rebuilt_atlas = fit_anatomical_transform(
        source_frame=transform.source_frame,
        destination_frame=transform.destination_frame,
        landmarks=transform.landmarks,
        method=transform.method,
        version=transform.version,
        affine_distortion_acknowledged=transform.affine_distortion_acknowledged,
        notes=transform.notes,
    )
    _compare_transform(
        rebuilt_atlas,
        transform,
        label="atlas transform",
        regenerated_landmark_ids=False,
    )


def _validate_required_atlas_sources(
    *,
    calibration: AtlasRegisteredCalibration,
    rebuilt_skull_transform: AnatomicalTransform,
) -> None:
    """Bind persisted required atlas sources to the measured skull landmarks."""

    skull_landmarks = calibration.skull_calibration.landmarks
    required_skull_points = (
        ("bregma", skull_landmarks.bregma),
        ("lambda", skull_landmarks.lambda_point),
        ("left-skull", skull_landmarks.left_skull),
        ("right-skull", skull_landmarks.right_skull),
    )
    atlas_landmarks = calibration.atlas_transform.landmarks
    for label, skull_point in required_skull_points:
        matches = tuple(item for item in atlas_landmarks if item.enabled and item.label == label)
        if len(matches) != 1:
            raise CalibrationReproducibilityError(
                "atlas transform must contain exactly one enabled "
                f"{label} landmark for skull-source reproduction"
            )
        expected_source = transform_point(rebuilt_skull_transform, skull_point)
        actual_source = matches[0].source
        if (
            actual_source.frame_id != expected_source.frame_id
            or actual_source.component_order != expected_source.component_order
            or actual_source.units != expected_source.units
            or not np.allclose(
                np.asarray(actual_source.as_ap_ml_dv(), dtype=np.float64),
                np.asarray(expected_source.as_ap_ml_dv(), dtype=np.float64),
                rtol=_FIT_RELATIVE_TOLERANCE,
                atol=_FIT_ABSOLUTE_TOLERANCE,
            )
        ):
            raise CalibrationReproducibilityError(
                f"atlas transform required {label} source does not derive "
                "from the stored skull landmark and skull transform"
            )


def _compare_transform(
    actual: AnatomicalTransform,
    expected: AnatomicalTransform,
    *,
    label: str,
    regenerated_landmark_ids: bool,
) -> None:
    exact_fields = (
        "version",
        "source_frame",
        "destination_frame",
        "method",
        "affine_distortion_acknowledged",
        "derived_from_transform_uuids",
        "notes",
        "component_order",
        "units",
    )
    for field in exact_fields:
        if getattr(actual, field) != getattr(expected, field):
            raise CalibrationReproducibilityError(
                f"{label} {field.replace('_', ' ')} does not reproduce from stored landmarks"
            )
    _require_close_sequence(
        actual.matrix_row_major,
        expected.matrix_row_major,
        f"{label} matrix",
    )
    _compare_correspondences(
        actual.landmarks,
        expected.landmarks,
        label=label,
        regenerated_landmark_ids=regenerated_landmark_ids,
    )
    _compare_residuals(
        actual,
        expected,
        label=label,
        regenerated_landmark_ids=regenerated_landmark_ids,
    )
    _require_close(
        actual.rms_residual_um,
        expected.rms_residual_um,
        f"{label} RMS residual",
    )
    _require_close(
        actual.max_residual_um,
        expected.max_residual_um,
        f"{label} maximum residual",
    )


def _compare_correspondences(
    actual: Sequence[LandmarkCorrespondence3D],
    expected: Sequence[LandmarkCorrespondence3D],
    *,
    label: str,
    regenerated_landmark_ids: bool,
) -> None:
    if regenerated_landmark_ids:
        actual_by_key = _skull_landmarks_by_label(actual, label)
        expected_by_key = _skull_landmarks_by_label(expected, label)
    else:
        actual_by_key = {str(item.landmark_uuid): item for item in actual}
        expected_by_key = {str(item.landmark_uuid): item for item in expected}
    if actual_by_key.keys() != expected_by_key.keys():
        raise CalibrationReproducibilityError(
            f"{label} landmark identities do not reproduce from stored landmarks"
        )
    for key, actual_item in actual_by_key.items():
        expected_item = expected_by_key[key]
        if actual_item.label != expected_item.label or actual_item.enabled != expected_item.enabled:
            raise CalibrationReproducibilityError(
                f"{label} landmark metadata does not reproduce from stored landmarks"
            )
        _compare_point(
            actual_item.source,
            expected_item.source,
            f"{label} landmark {actual_item.label!r} source",
        )
        _compare_point(
            actual_item.destination,
            expected_item.destination,
            f"{label} landmark {actual_item.label!r} destination",
        )


def _skull_landmarks_by_label(
    landmarks: Sequence[LandmarkCorrespondence3D],
    label: str,
) -> Mapping[str, LandmarkCorrespondence3D]:
    by_label = {item.label: item for item in landmarks}
    if len(by_label) != len(landmarks):
        raise CalibrationReproducibilityError(f"{label} contains duplicate stored landmark labels")
    return by_label


def _compare_residuals(
    actual: AnatomicalTransform,
    expected: AnatomicalTransform,
    *,
    label: str,
    regenerated_landmark_ids: bool,
) -> None:
    if regenerated_landmark_ids:
        actual_residuals = _residuals_by_landmark_label(actual, label)
        expected_residuals = _residuals_by_landmark_label(expected, label)
    else:
        actual_residuals = {str(item.landmark_uuid): item for item in actual.residuals}
        expected_residuals = {str(item.landmark_uuid): item for item in expected.residuals}
    if actual_residuals.keys() != expected_residuals.keys():
        raise CalibrationReproducibilityError(
            f"{label} residual landmark identities do not reproduce from stored landmarks"
        )
    for key, actual_item in actual_residuals.items():
        expected_item = expected_residuals[key]
        for field in (
            "ap_error_um",
            "ml_error_um",
            "dv_error_um",
            "radial_error_um",
        ):
            _require_close(
                getattr(actual_item, field),
                getattr(expected_item, field),
                f"{label} residual {field.replace('_', ' ')}",
            )


def _residuals_by_landmark_label(
    transform: AnatomicalTransform,
    label: str,
) -> Mapping[str, TransformLandmarkResidual]:
    labels_by_uuid = {item.landmark_uuid: item.label for item in transform.landmarks}
    if len(labels_by_uuid) != len(transform.landmarks):
        raise CalibrationReproducibilityError(f"{label} contains duplicate landmark UUIDs")
    by_label: dict[str, TransformLandmarkResidual] = {}
    for residual in transform.residuals:
        landmark_label = labels_by_uuid.get(residual.landmark_uuid)
        if landmark_label is None or landmark_label in by_label:
            raise CalibrationReproducibilityError(
                f"{label} residual identities do not map uniquely to stored landmarks"
            )
        by_label[landmark_label] = residual
    return by_label


def _compare_point(actual: AnatomicalPoint, expected: AnatomicalPoint, label: str) -> None:
    if (
        actual.frame_id != expected.frame_id
        or actual.component_order != expected.component_order
        or actual.units != expected.units
    ):
        raise CalibrationReproducibilityError(
            f"{label} frame semantics do not reproduce from stored landmarks"
        )
    _require_close_sequence(actual.as_ap_ml_dv(), expected.as_ap_ml_dv(), label)


def _compare_leveling_angles(
    actual: SkullLevelingAngles,
    expected: SkullLevelingAngles,
) -> None:
    if actual.convention != expected.convention:
        raise CalibrationReproducibilityError(
            "skull leveling angle convention does not reproduce from stored landmarks"
        )
    for field in ("pitch_deg", "roll_deg", "yaw_deg"):
        _require_close(
            getattr(actual, field),
            getattr(expected, field),
            f"skull leveling {field.replace('_', ' ')}",
        )


def _compare_skull_qc(actual: CalibrationQCResult, expected: CalibrationQCResult) -> None:
    for field in ("quality", "messages", "limits_source"):
        if getattr(actual, field) != getattr(expected, field):
            raise CalibrationReproducibilityError(
                f"skull calibration QC {field.replace('_', ' ')} "
                "does not reproduce from stored landmarks"
            )
    for field in (
        "geometric_bregma_lambda_distance_um",
        "reported_bregma_lambda_distance_um",
        "bregma_lambda_distance_error_um",
        "lateral_landmark_ap_mismatch_um",
        "lateral_landmark_dv_mismatch_um",
        "transform_rms_residual_um",
        "transform_max_residual_um",
    ):
        _require_close(
            getattr(actual, field),
            getattr(expected, field),
            f"skull calibration QC {field.replace('_', ' ')}",
        )


def _require_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(
        actual,
        expected,
        rel_tol=_FIT_RELATIVE_TOLERANCE,
        abs_tol=_FIT_ABSOLUTE_TOLERANCE,
    ):
        raise CalibrationReproducibilityError(f"{label} does not reproduce from stored landmarks")


def _require_close_sequence(
    actual: Sequence[float],
    expected: Sequence[float],
    label: str,
) -> None:
    if not np.allclose(
        np.asarray(actual, dtype=np.float64),
        np.asarray(expected, dtype=np.float64),
        rtol=_FIT_RELATIVE_TOLERANCE,
        atol=_FIT_ABSOLUTE_TOLERANCE,
    ):
        raise CalibrationReproducibilityError(f"{label} does not reproduce from stored landmarks")
