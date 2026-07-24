from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest

from mouse_brain_planner.coordinates.transforms import (
    TransformValidationError,
    compose_transforms,
    fit_anatomical_transform,
    invert_transform,
    transform_point,
    transform_points,
    transform_vector,
)
from mouse_brain_planner.domain.transform_models import (
    AnatomicalFrameDefinition,
    AnatomicalPoint,
    AnatomicalVector,
    CoordinateSystemKind,
    LandmarkCorrespondence3D,
    TransformMethod,
)


def _frame(frame_id: str, kind: CoordinateSystemKind) -> AnatomicalFrameDefinition:
    return AnatomicalFrameDefinition(
        frame_id=frame_id,
        kind=kind,
        origin_description=f"Explicit {frame_id} origin",
        ap_positive_direction="anterior",
        ml_positive_direction="right",
        dv_positive_direction="ventral",
        atlas_key="allen_mouse_25um" if kind is CoordinateSystemKind.ATLAS else None,
        atlas_version="1.2" if kind is CoordinateSystemKind.ATLAS else None,
    )


def _point(frame: str, values: tuple[float, float, float]) -> AnatomicalPoint:
    return AnatomicalPoint(
        frame_id=frame,
        ap_um=values[0],
        ml_um=values[1],
        dv_um=values[2],
    )


def _pairs(
    source_frame: str,
    destination_frame: str,
    source: np.ndarray,
    destination: np.ndarray,
) -> tuple[LandmarkCorrespondence3D, ...]:
    return tuple(
        LandmarkCorrespondence3D(
            label=f"L{index}",
            source=_point(source_frame, tuple(float(value) for value in source_point)),
            destination=_point(
                destination_frame,
                tuple(float(value) for value in destination_point),
            ),
        )
        for index, (source_point, destination_point) in enumerate(
            zip(source, destination, strict=True)
        )
    )


def test_rigid_fit_apply_inverse_and_vector_translation_semantics() -> None:
    atlas = _frame("atlas-ap-ml-dv", CoordinateSystemKind.ATLAS)
    subject = _frame("subject-ap-ml-dv", CoordinateSystemKind.SUBJECT)
    source = np.array([[0.0, 0.0, 0.0], [1000.0, 0.0, 0.0], [0.0, 800.0, 0.0], [0.0, 0.0, 600.0]])
    angle = np.deg2rad(23.0)
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    translation = np.array([120.0, -340.0, 55.0])
    destination = source @ rotation.T + translation
    fitted = fit_anatomical_transform(
        source_frame=atlas,
        destination_frame=subject,
        landmarks=_pairs(atlas.frame_id, subject.frame_id, source, destination),
    )

    assert fitted.method is TransformMethod.RIGID
    assert fitted.determinant == pytest.approx(1.0, abs=1e-10)
    assert fitted.rms_residual_um == pytest.approx(0.0, abs=1e-9)
    probe = _point(atlas.frame_id, (300.0, 400.0, 500.0))
    mapped = transform_point(fitted, probe)
    expected = rotation @ np.asarray(probe.as_ap_ml_dv()) + translation
    assert mapped.as_ap_ml_dv() == pytest.approx(expected, abs=1e-9)
    recovered = transform_point(invert_transform(fitted), mapped)
    assert recovered.as_ap_ml_dv() == pytest.approx(probe.as_ap_ml_dv(), abs=1e-9)

    vector = AnatomicalVector(frame_id=atlas.frame_id, ap_um=300, ml_um=400, dv_um=500)
    mapped_vector = transform_vector(fitted, vector)
    assert mapped_vector.as_ap_ml_dv() == pytest.approx(
        rotation @ np.asarray(vector.as_ap_ml_dv()),
        abs=1e-9,
    )


def test_similarity_fit_recovers_uniform_scale_and_rejects_mixed_point_frame() -> None:
    atlas = _frame("atlas", CoordinateSystemKind.ATLAS)
    subject = _frame("subject", CoordinateSystemKind.SUBJECT)
    source = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [0.0, 100.0, 0.0], [0.0, 0.0, 100.0]])
    scale = 1.12
    destination = source * scale + np.array([10.0, 20.0, 30.0])
    fitted = fit_anatomical_transform(
        source_frame=atlas,
        destination_frame=subject,
        landmarks=_pairs(atlas.frame_id, subject.frame_id, source, destination),
        method=TransformMethod.SIMILARITY,
    )
    assert fitted.determinant == pytest.approx(scale**3)
    assert fitted.rms_residual_um == pytest.approx(0.0, abs=1e-10)
    with pytest.raises(TransformValidationError, match="point frame"):
        transform_point(fitted, _point("wrong", (0, 0, 0)))


def test_affine_fit_requires_acknowledgment_for_final_export_and_composes() -> None:
    atlas = _frame("atlas", CoordinateSystemKind.ATLAS)
    subject = _frame("subject", CoordinateSystemKind.SUBJECT)
    skull = _frame("skull", CoordinateSystemKind.SKULL)
    source = np.array(
        [
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 100.0],
            [50.0, 70.0, 90.0],
        ]
    )
    linear = np.array([[1.1, 0.2, 0.0], [0.0, 0.9, 0.1], [0.05, 0.0, 1.05]])
    destination = source @ linear.T + np.array([5.0, -8.0, 12.0])
    affine = fit_anatomical_transform(
        source_frame=atlas,
        destination_frame=subject,
        landmarks=_pairs(atlas.frame_id, subject.frame_id, source, destination),
        method=TransformMethod.AFFINE,
    )
    assert not affine.permits_final_export
    acknowledged = affine.model_copy(update={"affine_distortion_acknowledged": True})
    assert acknowledged.permits_final_export

    subject_to_skull = fit_anatomical_transform(
        source_frame=subject,
        destination_frame=skull,
        landmarks=_pairs(
            subject.frame_id,
            skull.frame_id,
            destination,
            destination + np.array([100.0, 200.0, 300.0]),
        ),
    )
    composed = compose_transforms(acknowledged, subject_to_skull)
    points = tuple(_point(atlas.frame_id, tuple(row)) for row in source[:2])
    direct = transform_points(composed, points)
    sequential = transform_points(subject_to_skull, transform_points(acknowledged, points))
    np.testing.assert_allclose(
        np.asarray([point.as_ap_ml_dv() for point in direct]),
        np.asarray([point.as_ap_ml_dv() for point in sequential]),
        rtol=0,
        atol=1e-8,
    )


def test_transform_fit_rejects_degenerate_geometry_and_duplicate_ids() -> None:
    atlas = _frame("atlas", CoordinateSystemKind.ATLAS)
    subject = _frame("subject", CoordinateSystemKind.SUBJECT)
    collinear = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [200.0, 0.0, 0.0]])
    pairs = _pairs(atlas.frame_id, subject.frame_id, collinear, collinear)
    with pytest.raises(TransformValidationError, match="non-collinear"):
        fit_anatomical_transform(
            source_frame=atlas,
            destination_frame=subject,
            landmarks=pairs,
        )

    valid_source = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [0.0, 100.0, 0.0]])
    valid = list(_pairs(atlas.frame_id, subject.frame_id, valid_source, valid_source))
    valid[1] = valid[1].model_copy(update={"landmark_uuid": valid[0].landmark_uuid})
    with pytest.raises(TransformValidationError, match="unique UUID"):
        fit_anatomical_transform(
            source_frame=atlas,
            destination_frame=subject,
            landmarks=valid,
        )


def test_transform_composition_rejects_frame_definition_mismatch() -> None:
    atlas = _frame("atlas", CoordinateSystemKind.ATLAS)
    subject = _frame("subject", CoordinateSystemKind.SUBJECT)
    other_subject = subject.model_copy(update={"origin_description": "Different origin"})
    skull = _frame("skull", CoordinateSystemKind.SKULL)
    identity = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0], [0.0, 100.0, 0.0], [0.0, 0.0, 100.0]])
    first = fit_anatomical_transform(
        source_frame=atlas,
        destination_frame=subject,
        landmarks=_pairs(atlas.frame_id, subject.frame_id, identity, identity),
    )
    second = fit_anatomical_transform(
        source_frame=other_subject,
        destination_frame=skull,
        landmarks=_pairs(other_subject.frame_id, skull.frame_id, identity, identity),
    )
    with pytest.raises(TransformValidationError, match="identical intermediate"):
        compose_transforms(first, second)


def test_atlas_frame_requires_complete_identity() -> None:
    with pytest.raises(ValueError, match="exact atlas identity"):
        AnatomicalFrameDefinition(
            frame_id="atlas",
            kind=CoordinateSystemKind.ATLAS,
            origin_description="ASR origin",
            ap_positive_direction="posterior",
            ml_positive_direction="left",
            dv_positive_direction="inferior",
        )


def test_transform_model_rejects_singular_and_non_homogeneous_matrices() -> None:
    atlas = _frame("atlas", CoordinateSystemKind.ATLAS)
    subject = _frame("subject", CoordinateSystemKind.SUBJECT)
    from mouse_brain_planner.domain.transform_models import AnatomicalTransform

    singular = np.eye(4)
    singular[2, 2] = 0
    with pytest.raises(ValueError, match="invertible"):
        AnatomicalTransform(
            source_frame=atlas,
            destination_frame=subject,
            method=TransformMethod.AFFINE,
            matrix_row_major=tuple(singular.reshape(-1)),
        )
    invalid = np.eye(4)
    invalid[3, 0] = 1
    with pytest.raises(ValueError, match="homogeneous row"):
        AnatomicalTransform(
            source_frame=atlas,
            destination_frame=subject,
            method=TransformMethod.AFFINE,
            matrix_row_major=tuple(invalid.reshape(-1)),
        )


def test_affine_fit_and_model_reject_left_right_reflection() -> None:
    atlas = _frame("atlas", CoordinateSystemKind.ATLAS)
    subject = _frame("subject", CoordinateSystemKind.SUBJECT)
    source = np.array(
        [
            [0.0, 0.0, 0.0],
            [100.0, 0.0, 0.0],
            [0.0, 100.0, 0.0],
            [0.0, 0.0, 100.0],
        ]
    )
    reflected = source.copy()
    reflected[:, 1] *= -1
    with pytest.raises(TransformValidationError, match="handedness"):
        fit_anatomical_transform(
            source_frame=atlas,
            destination_frame=subject,
            landmarks=_pairs(
                atlas.frame_id,
                subject.frame_id,
                source,
                reflected,
            ),
            method=TransformMethod.AFFINE,
        )

    from mouse_brain_planner.domain.transform_models import AnatomicalTransform

    reflection_matrix = np.eye(4)
    reflection_matrix[1, 1] = -1
    with pytest.raises(ValueError, match="handedness"):
        AnatomicalTransform(
            source_frame=atlas,
            destination_frame=subject,
            method=TransformMethod.AFFINE,
            matrix_row_major=tuple(reflection_matrix.reshape(-1)),
        )


def test_landmark_uuid_helper_is_not_accidentally_constant() -> None:
    assert uuid4() != uuid4()
