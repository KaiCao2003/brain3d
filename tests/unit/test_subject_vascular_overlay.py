from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata
from mouse_brain_planner.domain.vessel_models import (
    DorsalRegistrationMethod,
    DorsalVascularLandmark,
)
from mouse_brain_planner.vasculature.registration import fit_dorsal_vascular_registration
from mouse_brain_planner.vasculature.subject_image import import_subject_vascular_image
from mouse_brain_planner.vasculature.subject_overlay import (
    SubjectOverlayRenderError,
    render_registered_dorsal_overlay,
)


def _atlas() -> AtlasMetadata:
    return AtlasMetadata(
        atlas_key="allen_mouse_25um",
        atlas_package_version="1.2",
        species="Mus musculus",
        citation="Allen CCFv3",
        source_url="https://example.invalid/atlas",
        cache_path="/verified/cache",
        metadata_sha256="a" * 64,
        resolution_um=(1.0, 1.0, 1.0),
        shape_voxels=(4, 2, 4),
        symmetric=True,
        midline_ml_um=2.0,
        axes=(
            AtlasAxis(
                array_axis=0,
                anatomical_axis="AP",
                origin_direction="anterior",
                positive_direction="posterior",
                voxel_size_um=1.0,
            ),
            AtlasAxis(
                array_axis=1,
                anatomical_axis="DV",
                origin_direction="superior",
                positive_direction="inferior",
                voxel_size_um=1.0,
            ),
            AtlasAxis(
                array_axis=2,
                anatomical_axis="ML",
                origin_direction="right",
                positive_direction="left",
                voxel_size_um=1.0,
            ),
        ),
    )


def _registered_fixture(tmp_path: Path):  # type: ignore[no-untyped-def]
    source = tmp_path / "source.png"
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    for row in range(4):
        for column in range(4):
            pixels[row, column] = (row * 40, column * 50, 10, 255)
    Image.fromarray(pixels, mode="RGBA").save(source)
    package = tmp_path / "staging.mouseplan"
    image = import_subject_vascular_image(source, package_root=package)
    landmarks = (
        DorsalVascularLandmark(
            label="anterior-right",
            kind="custom",
            image_column_px=0,
            image_row_px=0,
            atlas_ap_um=0.5,
            atlas_ml_um=3.5,
        ),
        DorsalVascularLandmark(
            label="anterior-left",
            kind="custom",
            image_column_px=3,
            image_row_px=0,
            atlas_ap_um=0.5,
            atlas_ml_um=0.5,
        ),
        DorsalVascularLandmark(
            label="posterior-right",
            kind="custom",
            image_column_px=0,
            image_row_px=3,
            atlas_ap_um=3.5,
            atlas_ml_um=3.5,
        ),
    )
    registration = fit_dorsal_vascular_registration(
        image=image,
        atlas_key="allen_mouse_25um",
        atlas_version="1.2",
        atlas_extent_ap_um=4.0,
        atlas_extent_ml_um=4.0,
        landmarks=landmarks,
        method=DorsalRegistrationMethod.SIMILARITY,
        laterality_confirmed_by_user=True,
    )
    return package, image, registration, pixels


def test_registered_overlay_maps_exact_atlas_centres_and_applies_opacity(tmp_path: Path) -> None:
    package, image, registration, pixels = _registered_fixture(tmp_path)

    overlay = render_registered_dorsal_overlay(
        image=image,
        registration=registration,
        package_root=package,
        atlas=_atlas(),
        opacity=0.5,
    )

    expected = pixels[:, ::-1].copy()
    expected[..., 3] = 128
    np.testing.assert_array_equal(overlay.rgba, expected)
    assert overlay.rgba.flags.writeable is False
    assert overlay.row_axis == "AP"
    assert overlay.column_axis == "ML"
    assert overlay.subject_specific is True


def test_registered_overlay_requires_explicit_laterality_confirmation(tmp_path: Path) -> None:
    package, image, registration, _ = _registered_fixture(tmp_path)
    unconfirmed = registration.model_copy(update={"laterality_confirmed_by_user": False})

    with pytest.raises(SubjectOverlayRenderError, match="laterality must be confirmed"):
        render_registered_dorsal_overlay(
            image=image,
            registration=unconfirmed,
            package_root=package,
            atlas=_atlas(),
        )


def test_registered_overlay_rejects_mixed_atlas_identity(tmp_path: Path) -> None:
    package, image, registration, _ = _registered_fixture(tmp_path)
    wrong_atlas = _atlas().model_copy(update={"atlas_package_version": "9.9"})

    with pytest.raises(SubjectOverlayRenderError, match="does not match loaded atlas"):
        render_registered_dorsal_overlay(
            image=image,
            registration=registration,
            package_root=package,
            atlas=wrong_atlas,
        )


def test_registered_overlay_keeps_genuinely_out_of_bounds_pixels_transparent(
    tmp_path: Path,
) -> None:
    package, image, registration, _ = _registered_fixture(tmp_path)
    shifted = np.asarray(registration.matrix_row_major, dtype=np.float64).reshape(3, 3).copy()
    shifted[0, 2] += 10.0
    off_atlas = registration.model_copy(
        update={"matrix_row_major": tuple(float(value) for value in shifted.reshape(-1))}
    )

    overlay = render_registered_dorsal_overlay(
        image=image,
        registration=off_atlas,
        package_root=package,
        atlas=_atlas(),
    )

    assert np.count_nonzero(overlay.rgba) == 0


@pytest.mark.parametrize("opacity", [-0.01, 1.01, float("nan")])
def test_registered_overlay_rejects_invalid_opacity(tmp_path: Path, opacity: float) -> None:
    package, image, registration, _ = _registered_fixture(tmp_path)

    with pytest.raises(SubjectOverlayRenderError, match="opacity"):
        render_registered_dorsal_overlay(
            image=image,
            registration=registration,
            package_root=package,
            atlas=_atlas(),
            opacity=opacity,
        )
