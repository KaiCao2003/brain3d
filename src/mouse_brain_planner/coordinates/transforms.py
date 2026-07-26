"""Fit, apply, compose, and invert explicit anatomical transforms."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.domain.transform_models import (
    AnatomicalFrameDefinition,
    AnatomicalPoint,
    AnatomicalTransform,
    AnatomicalVector,
    LandmarkCorrespondence3D,
    TransformLandmarkResidual,
    TransformMethod,
)


class TransformValidationError(ValueError):
    """Raised when a transform operation would guess or lose frame semantics."""


def fit_anatomical_transform(
    *,
    source_frame: AnatomicalFrameDefinition,
    destination_frame: AnatomicalFrameDefinition,
    landmarks: Sequence[LandmarkCorrespondence3D],
    method: TransformMethod = TransformMethod.RIGID,
    version: int = 1,
    affine_distortion_acknowledged: bool = False,
    notes: str = "",
) -> AnatomicalTransform:
    """Fit a proper rigid, similarity, or full affine 3D landmark transform."""

    if method not in {TransformMethod.RIGID, TransformMethod.SIMILARITY, TransformMethod.AFFINE}:
        raise TransformValidationError("only rigid, similarity, and affine transforms can be fit")
    if version <= 0:
        raise TransformValidationError("transform version must be positive")
    enabled = tuple(item for item in landmarks if item.enabled)
    minimum = 4 if method is TransformMethod.AFFINE else 3
    if len(enabled) < minimum:
        raise TransformValidationError(
            f"{method.value} transform requires at least {minimum} enabled landmarks"
        )
    landmark_ids = [item.landmark_uuid for item in enabled]
    if len(set(landmark_ids)) != len(landmark_ids):
        raise TransformValidationError("enabled landmarks must have unique UUIDs")
    for item in enabled:
        if item.source.frame_id != source_frame.frame_id:
            raise TransformValidationError("landmark source frame does not match fit source")
        if item.destination.frame_id != destination_frame.frame_id:
            raise TransformValidationError(
                "landmark destination frame does not match fit destination"
            )

    source = np.asarray([item.source.as_ap_ml_dv() for item in enabled], dtype=np.float64)
    destination = np.asarray(
        [item.destination.as_ap_ml_dv() for item in enabled],
        dtype=np.float64,
    )
    _validate_landmark_geometry(source, method=method, label="source")
    _validate_landmark_geometry(destination, method=method, label="destination")

    if method is TransformMethod.RIGID:
        linear, translation = _fit_rigid_or_similarity(source, destination, similarity=False)
    elif method is TransformMethod.SIMILARITY:
        linear, translation = _fit_rigid_or_similarity(source, destination, similarity=True)
    else:
        linear, translation = _fit_affine(source, destination)

    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = linear
    matrix[:3, 3] = translation
    predicted = _apply_matrix(matrix, source)
    residuals, rms, maximum = _residuals(enabled, predicted, destination)
    return AnatomicalTransform(
        version=version,
        source_frame=source_frame,
        destination_frame=destination_frame,
        method=method,
        matrix_row_major=_matrix_tuple(matrix),
        landmarks=tuple(landmarks),
        residuals=residuals,
        rms_residual_um=rms,
        max_residual_um=maximum,
        affine_distortion_acknowledged=affine_distortion_acknowledged,
        notes=notes,
    )


def transform_point(transform: AnatomicalTransform, point: AnatomicalPoint) -> AnatomicalPoint:
    """Apply translation and the linear component to one frame-checked point."""

    if point.frame_id != transform.source_frame.frame_id:
        raise TransformValidationError(
            f"point frame {point.frame_id!r} does not match {transform.source_frame.frame_id!r}"
        )
    values = np.asarray([point.as_ap_ml_dv()], dtype=np.float64)
    mapped = _apply_matrix(_matrix(transform), values)[0]
    return AnatomicalPoint(
        frame_id=transform.destination_frame.frame_id,
        ap_um=float(mapped[0]),
        ml_um=float(mapped[1]),
        dv_um=float(mapped[2]),
    )


def transform_points(
    transform: AnatomicalTransform,
    points: Sequence[AnatomicalPoint],
) -> tuple[AnatomicalPoint, ...]:
    """Apply a transform to a frame-homogeneous point sequence."""

    for point in points:
        if point.frame_id != transform.source_frame.frame_id:
            raise TransformValidationError(
                f"point frame {point.frame_id!r} does not match {transform.source_frame.frame_id!r}"
            )
    if not points:
        return ()
    values = np.asarray([point.as_ap_ml_dv() for point in points], dtype=np.float64)
    mapped = _apply_matrix(_matrix(transform), values)
    return tuple(
        AnatomicalPoint(
            frame_id=transform.destination_frame.frame_id,
            ap_um=float(value[0]),
            ml_um=float(value[1]),
            dv_um=float(value[2]),
        )
        for value in mapped
    )


def transform_vector(
    transform: AnatomicalTransform,
    vector: AnatomicalVector,
) -> AnatomicalVector:
    """Apply only the linear component to a direction or displacement."""

    if vector.frame_id != transform.source_frame.frame_id:
        raise TransformValidationError(
            f"vector frame {vector.frame_id!r} does not match {transform.source_frame.frame_id!r}"
        )
    mapped = _matrix(transform)[:3, :3] @ np.asarray(vector.as_ap_ml_dv(), dtype=np.float64)
    return AnatomicalVector(
        frame_id=transform.destination_frame.frame_id,
        ap_um=float(mapped[0]),
        ml_um=float(mapped[1]),
        dv_um=float(mapped[2]),
    )


def invert_transform(transform: AnatomicalTransform, *, version: int = 1) -> AnatomicalTransform:
    """Return an exact inverse with swapped frame definitions."""

    inverse = np.linalg.inv(_matrix(transform))
    return AnatomicalTransform(
        version=version,
        source_frame=transform.destination_frame,
        destination_frame=transform.source_frame,
        method=TransformMethod.INVERSE,
        matrix_row_major=_matrix_tuple(inverse),
        rms_residual_um=0,
        max_residual_um=0,
        derived_from_transform_uuids=(transform.transform_uuid,),
        notes=f"Inverse of {transform.transform_uuid}",
    )


def compose_transforms(
    first: AnatomicalTransform,
    second: AnatomicalTransform,
    *,
    version: int = 1,
) -> AnatomicalTransform:
    """Return ``second(first(point))`` after exact intermediate-frame validation."""

    if first.destination_frame != second.source_frame:
        raise TransformValidationError(
            "transform composition requires identical intermediate frame definitions"
        )
    composed = _matrix(second) @ _matrix(first)
    return AnatomicalTransform(
        version=version,
        source_frame=first.source_frame,
        destination_frame=second.destination_frame,
        method=TransformMethod.COMPOSED,
        matrix_row_major=_matrix_tuple(composed),
        rms_residual_um=0,
        max_residual_um=0,
        derived_from_transform_uuids=(first.transform_uuid, second.transform_uuid),
        notes=f"Composition of {first.transform_uuid} then {second.transform_uuid}",
    )


def _fit_rigid_or_similarity(
    source: NDArray[np.float64],
    destination: NDArray[np.float64],
    *,
    similarity: bool,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    source_mean = np.mean(source, axis=0)
    destination_mean = np.mean(destination, axis=0)
    source_centered = source - source_mean
    destination_centered = destination - destination_mean
    covariance = source_centered.T @ destination_centered
    left, singular_values, right_transposed = np.linalg.svd(covariance)
    correction = np.eye(3, dtype=np.float64)
    if np.linalg.det(right_transposed.T @ left.T) < 0:
        correction[-1, -1] = -1.0
    rotation = right_transposed.T @ correction @ left.T
    scale = 1.0
    if similarity:
        source_energy = float(np.sum(np.square(source_centered)))
        if source_energy <= 1e-12:
            raise TransformValidationError("source landmarks have zero scale")
        scale = float(np.sum(singular_values * np.diag(correction)) / source_energy)
        if not math.isfinite(scale) or scale <= 1e-12:
            raise TransformValidationError("similarity fit produced a non-positive scale")
    linear = rotation * scale
    translation = destination_mean - linear @ source_mean
    return linear, translation


def _fit_affine(
    source: NDArray[np.float64],
    destination: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    design = np.column_stack((source, np.ones(source.shape[0], dtype=np.float64)))
    coefficients, _, rank, _ = np.linalg.lstsq(design, destination, rcond=None)
    if rank != 4:
        raise TransformValidationError("affine landmarks do not span three dimensions")
    linear = coefficients[:3, :].T
    translation = coefficients[3, :]
    determinant = float(np.linalg.det(linear))
    if not math.isfinite(determinant) or determinant <= 1e-12:
        raise TransformValidationError(
            "affine fit must preserve anatomical handedness and cannot contain a reflection"
        )
    return linear, translation


def _validate_landmark_geometry(
    points: NDArray[np.float64],
    *,
    method: TransformMethod,
    label: str,
) -> None:
    if points.ndim != 2 or points.shape[1] != 3 or not np.all(np.isfinite(points)):
        raise TransformValidationError(f"{label} landmarks must be finite 3D points")
    centered = points - np.mean(points, axis=0)
    singular_values = np.linalg.svd(centered, compute_uv=False)
    if singular_values[0] <= 1e-9:
        raise TransformValidationError(f"{label} landmarks do not span distinct points")
    required_rank = 3 if method is TransformMethod.AFFINE else 2
    tolerance = max(float(singular_values[0]) * 1e-8, 1e-9)
    rank = int(np.count_nonzero(singular_values > tolerance))
    if rank < required_rank:
        description = "three dimensions" if required_rank == 3 else "a non-collinear plane"
        raise TransformValidationError(f"{label} landmarks do not span {description}")


def _residuals(
    landmarks: Sequence[LandmarkCorrespondence3D],
    predicted: NDArray[np.float64],
    destination: NDArray[np.float64],
) -> tuple[tuple[TransformLandmarkResidual, ...], float, float]:
    errors = predicted - destination
    radial = np.linalg.norm(errors, axis=1)
    if not np.all(np.isfinite(radial)):
        raise TransformValidationError("transform residuals are not finite")
    residuals = tuple(
        TransformLandmarkResidual(
            landmark_uuid=landmark.landmark_uuid,
            ap_error_um=float(error[0]),
            ml_error_um=float(error[1]),
            dv_error_um=float(error[2]),
            radial_error_um=float(distance),
        )
        for landmark, error, distance in zip(landmarks, errors, radial, strict=True)
    )
    rms = float(np.sqrt(np.mean(np.square(radial))))
    maximum = float(np.max(radial))
    return residuals, rms, maximum


def _matrix(transform: AnatomicalTransform) -> NDArray[np.float64]:
    return np.asarray(transform.matrix_row_major, dtype=np.float64).reshape(4, 4)


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
    values = np.asarray(matrix, dtype=np.float64).reshape(16)
    return (
        float(values[0]),
        float(values[1]),
        float(values[2]),
        float(values[3]),
        float(values[4]),
        float(values[5]),
        float(values[6]),
        float(values[7]),
        float(values[8]),
        float(values[9]),
        float(values[10]),
        float(values[11]),
        float(values[12]),
        float(values[13]),
        float(values[14]),
        float(values[15]),
    )


def _apply_matrix(
    matrix: NDArray[np.float64],
    points: NDArray[np.float64],
) -> NDArray[np.float64]:
    homogeneous = np.column_stack((points, np.ones(points.shape[0], dtype=np.float64)))
    mapped = (matrix @ homogeneous.T).T
    if not np.allclose(mapped[:, 3], 1.0, rtol=0, atol=1e-10):
        raise TransformValidationError("affine transform produced an invalid homogeneous scale")
    result = mapped[:, :3]
    if not np.all(np.isfinite(result)):
        raise TransformValidationError("transform produced non-finite coordinates")
    return result
