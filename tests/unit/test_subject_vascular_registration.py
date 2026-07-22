from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest

from mouse_brain_planner.domain.vessel_models import (
    DorsalRegistrationMethod,
    DorsalVascularLandmark,
    SubjectImageFormat,
    SubjectVascularImage,
    VascularLandmarkKind,
)
from mouse_brain_planner.vasculature.registration import (
    VascularRegistrationError,
    fit_dorsal_vascular_registration,
    transform_image_pixels_to_atlas,
)


def _image() -> SubjectVascularImage:
    return SubjectVascularImage(
        original_name="mouse-dorsal.tif",
        project_relative_path="images/subject.tif",
        source_sha256="a" * 64,
        byte_size=4096,
        image_format=SubjectImageFormat.TIFF,
        width_px=800,
        height_px=600,
    )


def _landmark(
    column: float,
    row: float,
    ap_um: float,
    ml_um: float,
    *,
    kind: VascularLandmarkKind = VascularLandmarkKind.VESSEL_BIFURCATION,
) -> DorsalVascularLandmark:
    return DorsalVascularLandmark(
        label=f"{column},{row}",
        kind=kind,
        image_column_px=column,
        image_row_px=row,
        atlas_ap_um=ap_um,
        atlas_ml_um=ml_um,
    )


def test_similarity_registration_round_trips_known_transform_and_reports_residuals() -> None:
    source = np.array([[100.0, 100.0], [600.0, 120.0], [250.0, 500.0], [500.0, 420.0]])
    angle = np.deg2rad(17.0)
    scale = 8.5
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    destination = source @ (scale * rotation).T + np.array([1200.0, 3100.0])
    landmarks = tuple(
        _landmark(column, row, ap, ml)
        for (column, row), (ap, ml) in zip(source, destination, strict=True)
    )

    registration = fit_dorsal_vascular_registration(
        image=_image(),
        atlas_key="allen_mouse_25um",
        atlas_version="1.2",
        atlas_extent_ap_um=20_000,
        atlas_extent_ml_um=20_000,
        landmarks=landmarks,
    )

    mapped = transform_image_pixels_to_atlas(registration, source)
    assert mapped == pytest.approx(destination, abs=1e-8)
    assert registration.rms_residual_um == pytest.approx(0.0, abs=1e-8)
    assert registration.max_residual_um == pytest.approx(0.0, abs=1e-8)
    assert registration.redundant_control_points
    assert registration.subject_specific is True
    assert "AP increases posterior" in registration.coordinate_note


def test_similarity_registration_reports_nonzero_overdetermined_residual() -> None:
    landmarks = (
        _landmark(10, 10, 1000, 1000, kind=VascularLandmarkKind.BREGMA),
        _landmark(100, 10, 1900, 1000, kind=VascularLandmarkKind.LAMBDA),
        _landmark(10, 100, 1000, 1900),
        _landmark(100, 100, 1940, 1880),
    )
    registration = fit_dorsal_vascular_registration(
        image=_image(),
        atlas_key="allen_mouse_25um",
        atlas_version="1.2",
        atlas_extent_ap_um=20_000,
        atlas_extent_ml_um=20_000,
        landmarks=landmarks,
    )
    assert registration.rms_residual_um > 0
    assert registration.max_residual_um == max(
        residual.radial_error_um for residual in registration.residuals
    )


def test_affine_registration_rejects_collinear_control_points() -> None:
    landmarks = (
        _landmark(10, 10, 1000, 1000),
        _landmark(20, 20, 1100, 1100),
        _landmark(30, 30, 1200, 1200),
    )
    with pytest.raises(VascularRegistrationError, match="collinear"):
        fit_dorsal_vascular_registration(
            image=_image(),
            atlas_key="allen_mouse_25um",
            atlas_version="1.2",
            atlas_extent_ap_um=20_000,
            atlas_extent_ml_um=20_000,
            landmarks=landmarks,
            method=DorsalRegistrationMethod.AFFINE,
        )


def test_registration_records_handedness_without_guessing_image_laterality() -> None:
    landmarks = (
        _landmark(10, 10, 1000, 2000),
        _landmark(110, 10, 1000, 3000),
        _landmark(10, 110, 2000, 2000),
    )
    registration = fit_dorsal_vascular_registration(
        image=_image(),
        atlas_key="allen_mouse_25um",
        atlas_version="1.2",
        atlas_extent_ap_um=20_000,
        atlas_extent_ml_um=20_000,
        landmarks=landmarks,
        method=DorsalRegistrationMethod.AFFINE,
    )
    assert registration.determinant < 0
    assert not registration.laterality_confirmed_by_user
    assert not registration.permits_final_export

    confirmed = fit_dorsal_vascular_registration(
        image=_image(),
        atlas_key="allen_mouse_25um",
        atlas_version="1.2",
        atlas_extent_ap_um=20_000,
        atlas_extent_ml_um=20_000,
        landmarks=landmarks,
        method=DorsalRegistrationMethod.AFFINE,
        laterality_confirmed_by_user=True,
    )
    assert confirmed.permits_final_export


@pytest.mark.parametrize(
    ("landmark", "message"),
    [
        (_landmark(-1, 20, 1000, 1000), "image columns"),
        (_landmark(20, 600, 1000, 1000), "image rows"),
        (_landmark(20, 20, 20_000, 1000), "atlas AP"),
        (_landmark(20, 20, 1000, 20_000), "atlas ML"),
    ],
)
def test_registration_rejects_out_of_bounds_landmarks(
    landmark: DorsalVascularLandmark,
    message: str,
) -> None:
    valid = _landmark(100, 100, 2000, 2000)
    with pytest.raises(VascularRegistrationError, match=message):
        fit_dorsal_vascular_registration(
            image=_image(),
            atlas_key="allen_mouse_25um",
            atlas_version="1.2",
            atlas_extent_ap_um=20_000,
            atlas_extent_ml_um=20_000,
            landmarks=(landmark, valid),
        )


def test_registration_model_rejects_duplicate_landmark_ids() -> None:
    duplicate_id = uuid4()
    first = _landmark(10, 10, 1000, 1000).model_copy(update={"landmark_uuid": duplicate_id})
    second = _landmark(100, 100, 2000, 2000).model_copy(update={"landmark_uuid": duplicate_id})
    with pytest.raises(VascularRegistrationError, match="unique UUID"):
        fit_dorsal_vascular_registration(
            image=_image(),
            atlas_key="allen_mouse_25um",
            atlas_version="1.2",
            atlas_extent_ap_um=20_000,
            atlas_extent_ml_um=20_000,
            landmarks=(first, second),
        )
