"""Landmark registration for subject-specific dorsal vascular images."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from skimage.transform import AffineTransform, SimilarityTransform

from mouse_brain_planner.domain.vessel_models import (
    DorsalRegistrationMethod,
    DorsalVascularLandmark,
    DorsalVascularRegistration,
    LandmarkResidual,
    SubjectVascularImage,
)


class VascularRegistrationError(ValueError):
    """Raised when a subject-image registration is scientifically invalid."""


def fit_dorsal_vascular_registration(
    *,
    image: SubjectVascularImage,
    atlas_key: str,
    atlas_version: str,
    atlas_extent_ap_um: float,
    atlas_extent_ml_um: float,
    landmarks: Sequence[DorsalVascularLandmark],
    method: DorsalRegistrationMethod = DorsalRegistrationMethod.SIMILARITY,
    version: int = 1,
    laterality_confirmed_by_user: bool = False,
) -> DorsalVascularRegistration:
    """Fit pixels to BrainGlobe ASR ``[AP, ML]`` and report exact residuals.

    Similarity registration models translation, rotation, and uniform scale.
    Affine registration additionally permits independent scaling and shear and
    therefore requires three non-collinear control points.  The matrix
    determinant is recorded but is not treated as a left/right test: image
    ``[column, row]`` and anatomical ``[AP, ML]`` bases can legitimately have
    opposite handedness. Laterality remains an explicit user confirmation gate.
    """

    if not atlas_key.strip() or not atlas_version.strip():
        raise VascularRegistrationError("exact atlas key and version are required")
    if version <= 0:
        raise VascularRegistrationError("registration version must be positive")
    for label, extent in (
        ("AP", atlas_extent_ap_um),
        ("ML", atlas_extent_ml_um),
    ):
        if not math.isfinite(extent) or extent <= 0:
            raise VascularRegistrationError(f"atlas {label} extent must be positive and finite")

    enabled = tuple(landmark for landmark in landmarks if landmark.enabled)
    minimum = 2 if method is DorsalRegistrationMethod.SIMILARITY else 3
    if len(enabled) < minimum:
        raise VascularRegistrationError(
            f"{method.value} registration requires at least {minimum} enabled landmarks"
        )
    enabled_ids = [landmark.landmark_uuid for landmark in enabled]
    if len(set(enabled_ids)) != len(enabled_ids):
        raise VascularRegistrationError("enabled landmarks must have unique UUIDs")

    source = np.asarray(
        [(item.image_column_px, item.image_row_px) for item in enabled],
        dtype=np.float64,
    )
    destination = np.asarray(
        [(item.atlas_ap_um, item.atlas_ml_um) for item in enabled],
        dtype=np.float64,
    )
    _validate_landmark_bounds(
        source,
        destination,
        image=image,
        atlas_extent_ap_um=atlas_extent_ap_um,
        atlas_extent_ml_um=atlas_extent_ml_um,
    )
    _validate_geometry(source, method=method, space="image")
    _validate_geometry(destination, method=method, space="atlas")

    if method is DorsalRegistrationMethod.SIMILARITY:
        estimate = SimilarityTransform.from_estimate(
            source,
            destination,
        )
    elif method is DorsalRegistrationMethod.AFFINE:
        estimate = AffineTransform.from_estimate(  # type: ignore[no-untyped-call]
            source,
            destination,
        )
    else:  # pragma: no cover - guarded by the enum, retained for defensive API use
        raise VascularRegistrationError(f"unsupported registration method: {method!r}")
    if not isinstance(estimate, (SimilarityTransform, AffineTransform)):
        raise VascularRegistrationError(
            f"{method.value} registration could not be estimated from these landmarks"
        )
    transform = estimate

    matrix = np.asarray(transform.params, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise VascularRegistrationError("estimated registration matrix is not finite 3-by-3")
    determinant = float(np.linalg.det(matrix[:2, :2]))
    if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
        raise VascularRegistrationError("registration is singular; check landmark geometry")

    predicted = np.asarray(transform(source), dtype=np.float64)
    errors = predicted - destination
    radial = np.linalg.norm(errors, axis=1)
    if not np.all(np.isfinite(radial)):
        raise VascularRegistrationError("registration residuals are not finite")
    rms = float(np.sqrt(np.mean(np.square(radial))))
    maximum = float(np.max(radial))
    residuals = tuple(
        LandmarkResidual(
            landmark_uuid=landmark.landmark_uuid,
            ap_error_um=float(error[0]),
            ml_error_um=float(error[1]),
            radial_error_um=float(distance),
        )
        for landmark, error, distance in zip(enabled, errors, radial, strict=True)
    )

    parameters = tuple(float(value) for value in matrix.reshape(-1))
    return DorsalVascularRegistration(
        version=version,
        image_uuid=image.image_uuid,
        atlas_key=atlas_key,
        atlas_version=atlas_version,
        method=method,
        matrix_row_major=parameters,  # type: ignore[arg-type]
        landmarks=tuple(landmarks),
        residuals=residuals,
        rms_residual_um=rms,
        max_residual_um=maximum,
        determinant=determinant,
        redundant_control_points=len(enabled) > minimum,
        laterality_confirmed_by_user=laterality_confirmed_by_user,
    )


def transform_image_pixels_to_atlas(
    registration: DorsalVascularRegistration,
    columns_rows_px: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Apply one stored mapping and return exact ASR ``[AP, ML]`` micrometres."""

    points = np.asarray(columns_rows_px, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise VascularRegistrationError("pixel points must have shape (N, 2) [column, row]")
    if not np.all(np.isfinite(points)):
        raise VascularRegistrationError("pixel points must be finite")
    matrix = np.asarray(registration.matrix_row_major, dtype=np.float64).reshape(3, 3)
    homogeneous = np.column_stack((points, np.ones(points.shape[0], dtype=np.float64)))
    mapped = (matrix @ homogeneous.T).T
    if np.any(np.abs(mapped[:, 2]) <= 1e-12):
        raise VascularRegistrationError("registration produced an invalid homogeneous scale")
    result = mapped[:, :2] / mapped[:, 2, np.newaxis]
    if not np.all(np.isfinite(result)):
        raise VascularRegistrationError("registration produced non-finite atlas coordinates")
    return result


def _validate_landmark_bounds(
    source: NDArray[np.float64],
    destination: NDArray[np.float64],
    *,
    image: SubjectVascularImage,
    atlas_extent_ap_um: float,
    atlas_extent_ml_um: float,
) -> None:
    if not np.all(np.isfinite(source)) or not np.all(np.isfinite(destination)):
        raise VascularRegistrationError("all enabled landmark coordinates must be finite")
    if np.any(source[:, 0] < 0) or np.any(source[:, 0] >= image.width_px):
        raise VascularRegistrationError(
            f"landmark image columns must be within [0, {image.width_px}) pixels"
        )
    if np.any(source[:, 1] < 0) or np.any(source[:, 1] >= image.height_px):
        raise VascularRegistrationError(
            f"landmark image rows must be within [0, {image.height_px}) pixels"
        )
    if np.any(destination[:, 0] < 0) or np.any(destination[:, 0] >= atlas_extent_ap_um):
        raise VascularRegistrationError(
            f"landmark atlas AP values must be within [0, {atlas_extent_ap_um:g}) µm"
        )
    if np.any(destination[:, 1] < 0) or np.any(destination[:, 1] >= atlas_extent_ml_um):
        raise VascularRegistrationError(
            f"landmark atlas ML values must be within [0, {atlas_extent_ml_um:g}) µm"
        )


def _validate_geometry(
    points: NDArray[np.float64],
    *,
    method: DorsalRegistrationMethod,
    space: str,
) -> None:
    centered = points - np.mean(points, axis=0)
    singular_values = np.linalg.svd(centered, compute_uv=False)
    scale = float(singular_values[0]) if singular_values.size else 0.0
    if scale <= 1e-9:
        raise VascularRegistrationError(f"{space} landmarks do not span two distinct points")
    if method is DorsalRegistrationMethod.AFFINE:
        second = float(singular_values[1]) if singular_values.size > 1 else 0.0
        if second <= max(scale * 1e-8, 1e-9):
            raise VascularRegistrationError(
                f"{space} landmarks are collinear; affine registration requires 2D spread"
            )
