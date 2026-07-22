"""Pure sampling and composition tests for reference vascular density."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from tests.fixtures.reference_density_overlay_factory import (
    make_reference_density_overlay_test_double,
)

from mouse_brain_planner.rendering.slice_renderer import SliceOrientation, extract_asr_slice
from mouse_brain_planner.vasculature.density_overlay import (
    REFERENCE_DENSITY_PROJECTION_DISCLOSURE,
    REFERENCE_DENSITY_PROJECTION_OPACITY,
    ReferenceDensityAtlasBinding,
    ReferenceDensityHeatmapStyle,
    ReferenceDensityOverlayError,
    composite_reference_density_heatmap,
    render_reference_density_dv_maximum_projection,
    sample_reference_density_plane,
)
from mouse_brain_planner.vasculature.reference_density import ReferenceVascularDensity


def _linear_physical_density() -> ReferenceVascularDensity:
    ap, dv, ml = np.indices((2, 3, 4), dtype=np.float32)
    values = (
        (ap + np.float32(0.5)) * np.float32(100.0)
        + (dv + np.float32(0.5)) * np.float32(1000.0)
        + (ml + np.float32(0.5)) * np.float32(10_000.0)
    )
    return make_reference_density_overlay_test_double(values)


@pytest.mark.parametrize(
    ("orientation", "slice_index"),
    [
        (SliceOrientation.CORONAL, 1),
        (SliceOrientation.SAGITTAL, 3),
        (SliceOrientation.HORIZONTAL, 2),
    ],
)
def test_all_orientations_sample_exact_atlas_voxel_centres_with_bounded_linear_interpolation(
    orientation: SliceOrientation,
    slice_index: int,
) -> None:
    density = _linear_physical_density()
    binding = ReferenceDensityAtlasBinding(
        density,
        atlas_shape_asr=(4, 6, 8),
        atlas_resolution_um=(50.0, 50.0, 50.0),
    )

    actual = sample_reference_density_plane(binding, orientation, slice_index)

    ap_centres = np.clip((np.arange(4) + 0.5) * 50.0, 50.0, 150.0)
    dv_centres = np.clip((np.arange(6) + 0.5) * 50.0, 50.0, 250.0)
    ml_centres = np.clip((np.arange(8) + 0.5) * 50.0, 50.0, 350.0)
    expected_volume = (
        ap_centres[:, np.newaxis, np.newaxis]
        + dv_centres[np.newaxis, :, np.newaxis] * 10.0
        + ml_centres[np.newaxis, np.newaxis, :] * 100.0
    )
    expected = extract_asr_slice(expected_volume, orientation, slice_index)
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-3)
    assert actual.shape == (
        binding.atlas_shape_asr[orientation.row_axis],
        binding.atlas_shape_asr[orientation.column_axis],
    )
    assert actual.dtype == np.dtype(np.float32)
    assert not actual.flags.writeable


def test_heatmap_uses_explicit_red_magenta_window_and_alpha_while_zero_is_transparent() -> None:
    base = np.full((1, 4, 3), 100, dtype=np.uint8)
    density = np.asarray([[0.0, 1.0, 2.0, 3.0]], dtype=np.float32)
    style = ReferenceDensityHeatmapStyle(opacity=0.5, window_low=1.0, window_high=3.0)

    actual = composite_reference_density_heatmap(base, density, style)

    expected = np.asarray(
        [[[100, 100, 100], [178, 50, 50], [178, 50, 114], [178, 50, 178]]],
        dtype=np.uint8,
    )
    np.testing.assert_array_equal(actual, expected)
    wider_window = composite_reference_density_heatmap(
        base,
        density,
        ReferenceDensityHeatmapStyle(opacity=0.5, window_low=0.0, window_high=6.0),
    )
    assert tuple(wider_window[0, 3]) == (178, 50, 114)
    transparent = composite_reference_density_heatmap(
        base,
        density,
        ReferenceDensityHeatmapStyle(opacity=0.0, window_low=0.0, window_high=3.0),
    )
    np.testing.assert_array_equal(transparent, base)


@pytest.mark.parametrize(
    ("opacity", "low", "high", "message"),
    [
        (1.1, 0.0, 1.0, "opacity"),
        (0.5, -1.0, 1.0, "non-negative"),
        (0.5, 1.0, 1.0, "greater"),
        (0.5, 0.0, np.inf, "finite"),
    ],
)
def test_heatmap_rejects_invalid_explicit_style(
    opacity: float,
    low: float,
    high: float,
    message: str,
) -> None:
    with pytest.raises(ReferenceDensityOverlayError, match=message):
        ReferenceDensityHeatmapStyle(opacity=opacity, window_low=low, window_high=high)


@pytest.mark.parametrize("invalid_value", [np.nan, np.inf, -1.0])
def test_heatmap_rejects_invalid_scalar_data_without_producing_color(
    invalid_value: float,
) -> None:
    density = np.asarray([[invalid_value]], dtype=np.float32)
    with pytest.raises(ReferenceDensityOverlayError, match=r"non-finite|negative"):
        composite_reference_density_heatmap(
            np.zeros((1, 1, 3), dtype=np.uint8),
            density,
            ReferenceDensityHeatmapStyle(opacity=0.5, window_low=0.0, window_high=1.0),
        )


def test_binding_fails_closed_on_loaded_atlas_shape_resolution_and_extent_mismatch() -> None:
    density = _linear_physical_density()
    with pytest.raises(ReferenceDensityOverlayError, match="target shape"):
        ReferenceDensityAtlasBinding(
            density,
            atlas_shape_asr=(5, 6, 8),
            atlas_resolution_um=(50.0, 50.0, 50.0),
        )
    with pytest.raises(ReferenceDensityOverlayError, match="target resolution"):
        ReferenceDensityAtlasBinding(
            density,
            atlas_shape_asr=(4, 6, 8),
            atlas_resolution_um=(25.0, 25.0, 25.0),
        )

    invalid_provenance = replace(
        density.provenance,
        output_extent_um_asr=(201.0, 300.0, 400.0),
    )
    invalid_extent = ReferenceVascularDensity(
        values_asr=density.values_asr,
        provenance=invalid_provenance,
    )
    with pytest.raises(ReferenceDensityOverlayError, match="recorded provenance"):
        ReferenceDensityAtlasBinding(
            invalid_extent,
            atlas_shape_asr=(4, 6, 8),
            atlas_resolution_um=(50.0, 50.0, 50.0),
        )


def test_binding_rejects_nonfinite_volume_and_sampler_rejects_bad_slice() -> None:
    density = _linear_physical_density()
    values = density.values_asr.copy()
    values[0, 0, 0] = np.nan
    values.setflags(write=False)
    invalid = ReferenceVascularDensity(values_asr=values, provenance=density.provenance)
    with pytest.raises(ReferenceDensityOverlayError, match="non-finite"):
        ReferenceDensityAtlasBinding(
            invalid,
            atlas_shape_asr=(4, 6, 8),
            atlas_resolution_um=(50.0, 50.0, 50.0),
        )

    binding = ReferenceDensityAtlasBinding(
        density,
        atlas_shape_asr=(4, 6, 8),
        atlas_resolution_um=(50.0, 50.0, 50.0),
    )
    with pytest.raises(ReferenceDensityOverlayError, match="outside"):
        sample_reference_density_plane(binding, SliceOrientation.CORONAL, 4)
    with pytest.raises(ReferenceDensityOverlayError, match="integer"):
        sample_reference_density_plane(binding, SliceOrientation.CORONAL, 1.5)  # type: ignore[arg-type]


def test_dv_maximum_projection_is_transparent_immutable_and_atlas_grid_aligned() -> None:
    values = np.zeros((2, 3, 4), dtype=np.float32)
    values[0, 1, 0] = 1.25
    values[1, 2, 3] = 2.5
    density = make_reference_density_overlay_test_double(values)
    binding = ReferenceDensityAtlasBinding(
        density,
        atlas_shape_asr=(4, 6, 8),
        atlas_resolution_um=(50.0, 50.0, 50.0),
    )

    brain_mask = np.ones((4, 8), dtype=np.bool_)
    brain_mask[1, -1] = False
    projection = render_reference_density_dv_maximum_projection(
        binding,
        brain_mask_ap_ml=brain_mask,
    )

    assert projection.rgba.shape == (4, 8, 4)
    assert projection.rgba.dtype == np.dtype(np.uint8)
    assert not projection.rgba.flags.writeable
    assert projection.row_axis == "AP"
    assert projection.column_axis == "ML"
    assert projection.projection_axis == "DV"
    assert projection.projection_method == "maximum"
    assert int(projection.rgba[..., 3].max()) == round(REFERENCE_DENSITY_PROJECTION_OPACITY * 255)
    assert int(projection.rgba[..., 3].min()) == 0
    assert int(projection.rgba[1, -1, 3]) == 0
    assert 0 < int(projection.rgba[0, 0, 3]) < int(projection.rgba[..., 3].max())
    assert "not subject-specific" in REFERENCE_DENSITY_PROJECTION_DISCLOSURE
    assert "not individual vessel paths" in REFERENCE_DENSITY_PROJECTION_DISCLOSURE
    assert "not usable for vessel clearance" in REFERENCE_DENSITY_PROJECTION_DISCLOSURE


@pytest.mark.parametrize(
    "mask",
    [
        np.ones((4, 8), dtype=np.uint8),
        np.ones((4, 7), dtype=np.bool_),
    ],
)
def test_dv_projection_rejects_nonboolean_or_mismatched_brain_mask(mask: np.ndarray) -> None:
    density = make_reference_density_overlay_test_double(np.ones((2, 3, 4), dtype=np.float32))
    binding = ReferenceDensityAtlasBinding(
        density,
        atlas_shape_asr=(4, 6, 8),
        atlas_resolution_um=(50.0, 50.0, 50.0),
    )

    with pytest.raises(ReferenceDensityOverlayError, match="exact atlas AP/ML shape"):
        render_reference_density_dv_maximum_projection(
            binding,
            brain_mask_ap_ml=mask,  # type: ignore[arg-type]
        )
