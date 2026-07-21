"""Tests for vectorized BrainGlobe ASR orthogonal rendering."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from mouse_brain_planner.rendering.slice_renderer import (
    SliceOrientation,
    SliceRenderer,
    annotation_outline,
    normalize_grayscale,
)


def make_asr_array_test_double() -> tuple[np.ndarray, np.ndarray]:
    """Return small, asymmetric arrays that are explicitly not production brain data."""

    shape = (4, 5, 6)  # [AP, DV, ML]
    reference = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)
    annotation = np.zeros(shape, dtype=np.uint32)
    annotation[1, 1:4, 1:5] = 7
    annotation[2, 2:5, 3:6] = 11
    return reference, annotation


def make_renderer_test_double() -> SliceRenderer:
    reference, annotation = make_asr_array_test_double()
    return SliceRenderer(
        reference,
        annotation,
        resolution_um=(100.0, 200.0, 300.0),
    )


def test_extracts_each_orientation_with_documented_display_axes() -> None:
    reference, annotation = make_asr_array_test_double()
    renderer = make_renderer_test_double()

    assert_array_equal(renderer.reference_slice("coronal", 1), reference[1, :, :])
    assert_array_equal(renderer.annotation_slice("coronal", 1), annotation[1, :, :])
    assert renderer.image_shape("coronal") == (5, 6)  # rows DV, columns ML

    assert_array_equal(renderer.reference_slice("sagittal", 4), reference[:, :, 4].T)
    assert_array_equal(renderer.annotation_slice("sagittal", 4), annotation[:, :, 4].T)
    assert renderer.image_shape("sagittal") == (5, 4)  # rows DV, columns AP

    assert_array_equal(renderer.reference_slice("horizontal", 3), reference[:, 3, :])
    assert_array_equal(renderer.annotation_slice("horizontal", 3), annotation[:, 3, :])
    assert renderer.image_shape("horizontal") == (4, 6)  # rows AP, columns ML


@pytest.mark.parametrize(
    ("orientation", "slice_index", "column", "row", "expected_voxel"),
    [
        (SliceOrientation.CORONAL, 1, 4, 3, (1, 3, 4)),
        (SliceOrientation.SAGITTAL, 4, 2, 3, (2, 3, 4)),
        (SliceOrientation.HORIZONTAL, 3, 4, 2, (2, 3, 4)),
    ],
)
def test_pixel_voxel_mapping_round_trips_for_all_views(
    orientation: SliceOrientation,
    slice_index: int,
    column: int,
    row: int,
    expected_voxel: tuple[int, int, int],
) -> None:
    renderer = make_renderer_test_double()

    voxel = renderer.pixel_to_voxel(orientation, slice_index, column, row)

    assert voxel == expected_voxel
    assert renderer.voxel_to_pixel(orientation, voxel) == (column, row)
    assert renderer.slice_index_for_voxel(orientation, voxel) == slice_index


def test_pixel_and_slice_bounds_fail_before_numpy_indexing() -> None:
    renderer = make_renderer_test_double()

    with pytest.raises(IndexError, match="outside"):
        renderer.reference_slice("coronal", -1)
    with pytest.raises(IndexError, match="pixel column"):
        renderer.pixel_to_voxel("coronal", 0, 6, 0)
    with pytest.raises(IndexError, match="ASR axis 0"):
        renderer.voxel_to_pixel("sagittal", (4, 0, 0))


def test_mm_mapping_uses_voxel_centers_and_half_open_lookup() -> None:
    renderer = make_renderer_test_double()

    assert renderer.slice_center_mm("coronal", 2) == pytest.approx(0.25)
    assert renderer.slice_index_from_mm("coronal", 0.0) == 0
    assert renderer.slice_index_from_mm("coronal", 0.1) == 1
    assert renderer.slice_index_from_mm("coronal", 0.3999) == 3
    with pytest.raises(IndexError, match=r"\[0, 0.4\)"):
        renderer.slice_index_from_mm("coronal", 0.4)


def test_grayscale_contrast_is_vectorized_clipped_and_nan_safe() -> None:
    image = np.array([[0.0, 50.0, 100.0, np.nan]], dtype=np.float32)

    grayscale = normalize_grayscale(image, low=0.0, high=100.0)

    assert grayscale.dtype == np.uint8
    assert_array_equal(grayscale, np.array([[0, 128, 255, 0]], dtype=np.uint8))


def test_annotation_outline_marks_both_sides_of_label_transitions() -> None:
    labels = np.array(
        [
            [0, 0, 0],
            [0, 7, 7],
            [0, 7, 7],
        ],
        dtype=np.uint32,
    )
    expected = np.array(
        [
            [False, True, True],
            [True, True, True],
            [True, True, False],
        ]
    )

    result = annotation_outline(labels)

    assert result.dtype == np.bool_
    assert_array_equal(result, expected)


def test_render_composes_selected_region_below_annotation_outline() -> None:
    renderer = make_renderer_test_double()

    frame = renderer.render_slice(
        "coronal",
        1,
        contrast_low=0.0,
        contrast_high=238.0,
        selected_region_id=7,
        selected_color=(255, 0, 0),
        selected_alpha=0.5,
        outline_color=(255, 170, 0),
    )

    assert frame.rgb.shape == (5, 6, 3)
    assert frame.rgb.dtype == np.uint8
    assert_array_equal(frame.selected_region, frame.annotation == 7)
    assert_array_equal(frame.annotation_outline, annotation_outline(frame.annotation))
    # The interior receives the translucent region color; boundaries are then
    # painted with the exact outline color.
    interior_gray = int(frame.grayscale[2, 2])
    expected_interior = np.rint(
        np.array([interior_gray, interior_gray, interior_gray]) * 0.5 + np.array([255, 0, 0]) * 0.5
    ).astype(np.uint8)
    assert_array_equal(frame.rgb[2, 2], expected_interior)
    assert_array_equal(frame.rgb[0, 1], np.array([255, 170, 0], dtype=np.uint8))


def test_renderer_rejects_mismatched_or_non_integer_test_double_arrays() -> None:
    with pytest.raises(ValueError, match="same"):
        SliceRenderer(
            np.zeros((2, 3, 4), dtype=np.uint16),
            np.zeros((2, 3, 5), dtype=np.uint32),
            resolution_um=(10.0, 10.0, 10.0),
        )
    with pytest.raises(TypeError, match="integer"):
        SliceRenderer(
            np.zeros((2, 3, 4), dtype=np.uint16),
            np.zeros((2, 3, 4), dtype=np.float32),
            resolution_um=(10.0, 10.0, 10.0),
        )
