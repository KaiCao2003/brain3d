"""Tests for vectorized BrainGlobe ASR orthogonal rendering."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_array_equal

import mouse_brain_planner.rendering.slice_renderer as slice_renderer_module
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


@pytest.mark.parametrize(
    ("low", "high"),
    [
        (None, None),
        (0.0, 65535.0),
        (123.5, 40_000.75),
        (-50.0, 70_000.0),
    ],
)
def test_uint16_lookup_normalization_is_exactly_the_float64_contract(
    low: float | None,
    high: float | None,
) -> None:
    image = np.random.default_rng(20260721).integers(
        0,
        1 << 16,
        size=(73, 91),
        dtype=np.uint16,
    )
    values = image.astype(np.float64)
    resolved_low = float(values.min()) if low is None else low
    resolved_high = float(values.max()) if high is None else high
    expected = values - resolved_low
    expected /= resolved_high - resolved_low
    np.clip(expected, 0.0, 1.0, out=expected)
    expected = np.rint(expected * 255.0).astype(np.uint8)

    assert_array_equal(normalize_grayscale(image, low=low, high=high), expected)


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


def test_mask_bounded_composition_preserves_sequential_float32_blending() -> None:
    renderer = make_renderer_test_double()
    frame = renderer.render_slice(
        "coronal",
        1,
        contrast_low=0.0,
        contrast_high=238.0,
        selected_region_id=7,
        selected_color=(17, 93, 241),
        selected_alpha=0.37,
        outline_color=(243, 121, 9),
        outline_alpha=0.42,
    )
    expected = np.repeat(frame.grayscale[:, :, np.newaxis], 3, axis=2).astype(np.float32)
    selected_rgb = np.asarray((17, 93, 241), dtype=np.float32)
    outline_rgb = np.asarray((243, 121, 9), dtype=np.float32)
    expected[frame.selected_region] = (
        expected[frame.selected_region] * (1.0 - 0.37) + selected_rgb * 0.37
    )
    expected[frame.annotation_outline] = (
        expected[frame.annotation_outline] * (1.0 - 0.42) + outline_rgb * 0.42
    )
    expected = np.rint(np.clip(expected, 0.0, 255.0)).astype(np.uint8)

    assert_array_equal(frame.rgb, expected)


def test_render_selected_hierarchy_includes_parent_and_child_annotation_ids() -> None:
    reference = np.arange(6, dtype=np.uint16).reshape((1, 2, 3))
    annotation = np.array([[[7, 8, 0], [8, 7, 0]]], dtype=np.uint32)
    renderer = SliceRenderer(
        reference,
        annotation,
        resolution_um=(25.0, 25.0, 25.0),
    )

    parent = renderer.render_slice("coronal", 0, selected_region_ids={7, 8})
    leaf = renderer.render_slice("coronal", 0, selected_region_ids={8})

    assert_array_equal(parent.selected_region, np.isin(annotation[0], (7, 8)))
    assert_array_equal(leaf.selected_region, annotation[0] == 8)


def test_paired_view_second_render_reuses_composed_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second view must not repeat slice-wide normalization or outlining."""

    renderer = make_renderer_test_double()
    calls = {"normalize": 0, "outline": 0}
    original_normalize = slice_renderer_module.normalize_grayscale
    original_outline = slice_renderer_module.annotation_outline

    def counted_normalize(*args: object, **kwargs: object) -> np.ndarray:
        calls["normalize"] += 1
        return original_normalize(*args, **kwargs)  # type: ignore[arg-type]

    def counted_outline(*args: object, **kwargs: object) -> np.ndarray:
        calls["outline"] += 1
        return original_outline(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(slice_renderer_module, "normalize_grayscale", counted_normalize)
    monkeypatch.setattr(slice_renderer_module, "annotation_outline", counted_outline)

    first = renderer.render_slice(
        "coronal",
        1,
        selected_region_ids={7, 11},
        selected_color=(1, 2, 3),
    )
    second = renderer.render_slice(
        SliceOrientation.CORONAL,
        np.int64(1),
        selected_region_ids=(11, 7, 7),
        selected_color=(1, 2, 3),
    )

    assert second is first
    assert calls == {"normalize": 1, "outline": 1}


@pytest.mark.parametrize(
    ("changed_field", "changed_value"),
    [
        ("orientation", "sagittal"),
        ("slice_index", 2),
        ("contrast_low", 10.0),
        ("contrast_high", 100.0),
        ("selected_region_id", 8),
        ("selected_region_ids", {8}),
        ("selected_color", (4, 5, 6)),
        ("selected_alpha", 0.5),
        ("outline_color", (7, 8, 9)),
        ("outline_alpha", 0.5),
    ],
)
def test_render_cache_invalidates_for_every_output_input(
    monkeypatch: pytest.MonkeyPatch,
    changed_field: str,
    changed_value: object,
) -> None:
    renderer = make_renderer_test_double()
    calls = 0
    original_normalize = slice_renderer_module.normalize_grayscale

    def counted_normalize(*args: object, **kwargs: object) -> np.ndarray:
        nonlocal calls
        calls += 1
        return original_normalize(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(slice_renderer_module, "normalize_grayscale", counted_normalize)
    baseline: dict[str, object] = {
        "orientation": "coronal",
        "slice_index": 1,
        "contrast_low": 0.0,
        "contrast_high": 119.0,
        "selected_region_id": 7,
        "selected_region_ids": {11},
        "selected_color": (1, 2, 3),
        "selected_alpha": 0.25,
        "outline_color": (250, 200, 150),
        "outline_alpha": 0.75,
    }
    changed = baseline | {changed_field: changed_value}

    renderer.render_slice(**baseline)  # type: ignore[arg-type]
    renderer.render_slice(**changed)  # type: ignore[arg-type]

    assert calls == 2, f"{changed_field} was omitted from the cache key"


def test_render_cache_is_lru_bounded_per_orientation_and_by_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = make_renderer_test_double()
    calls = 0
    original_normalize = slice_renderer_module.normalize_grayscale

    def counted_normalize(*args: object, **kwargs: object) -> np.ndarray:
        nonlocal calls
        calls += 1
        return original_normalize(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(slice_renderer_module, "normalize_grayscale", counted_normalize)
    for slice_index in (0, 1, 2):
        renderer.render_slice("coronal", slice_index)

    coronal_keys = [
        key for key in renderer._frame_cache if key.orientation is SliceOrientation.CORONAL
    ]
    assert len(coronal_keys) == renderer._CACHE_FRAMES_PER_ORIENTATION
    renderer.render_slice("coronal", 0)
    assert calls == 4

    byte_bounded = make_renderer_test_double()
    monkeypatch.setattr(byte_bounded, "_CACHE_MAX_BYTES", 300)
    byte_bounded.render_slice("coronal", 0)
    byte_bounded.render_slice("coronal", 1)

    assert len(byte_bounded._frame_cache) == 1
    assert 0 < byte_bounded._frame_cache_bytes <= 300


def test_cached_frame_arrays_are_read_only() -> None:
    renderer = make_renderer_test_double()
    frame = renderer.render_slice("coronal", 1, selected_region_ids={7})

    for array in (
        frame.reference,
        frame.annotation,
        frame.grayscale,
        frame.annotation_outline,
        frame.selected_region,
        frame.rgb,
    ):
        assert not array.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            array.flat[0] = 0

    assert renderer.render_slice("coronal", 1, selected_region_ids={7}) is frame


def test_optimized_sagittal_layout_is_pixel_exact_for_every_ml_index() -> None:
    reference, annotation = make_asr_array_test_double()
    sagittal_reference = np.ascontiguousarray(reference.transpose(2, 1, 0))
    sagittal_annotation = np.ascontiguousarray(annotation.transpose(2, 1, 0))
    optimized = SliceRenderer(
        reference,
        annotation,
        resolution_um=(100.0, 200.0, 300.0),
        sagittal_reference=sagittal_reference,
        sagittal_annotation=sagittal_annotation,
    )
    authoritative = make_renderer_test_double()

    for ml_index in range(reference.shape[2]):
        assert_array_equal(
            optimized.reference_slice("sagittal", ml_index), reference[:, :, ml_index].T
        )
        assert_array_equal(
            optimized.annotation_slice("sagittal", ml_index),
            annotation[:, :, ml_index].T,
        )
        optimized_frame = optimized.render_slice(
            "sagittal",
            ml_index,
            contrast_low=0.0,
            contrast_high=119.0,
            selected_region_ids={7, 11},
        )
        authoritative_frame = authoritative.render_slice(
            "sagittal",
            ml_index,
            contrast_low=0.0,
            contrast_high=119.0,
            selected_region_ids={7, 11},
        )
        assert_array_equal(optimized_frame.rgb, authoritative_frame.rgb)
        assert_array_equal(
            optimized_frame.annotation_outline,
            authoritative_frame.annotation_outline,
        )
        assert_array_equal(optimized_frame.selected_region, authoritative_frame.selected_region)


def test_optimized_sagittal_arrays_require_complete_matching_contract() -> None:
    reference, annotation = make_asr_array_test_double()
    sagittal_reference = np.ascontiguousarray(reference.transpose(2, 1, 0))
    sagittal_annotation = np.ascontiguousarray(annotation.transpose(2, 1, 0))

    with pytest.raises(ValueError, match="provided together"):
        SliceRenderer(
            reference,
            annotation,
            resolution_um=(100.0, 200.0, 300.0),
            sagittal_reference=sagittal_reference,
        )
    with pytest.raises(ValueError, match=r"\[ML,DV,AP\]"):
        SliceRenderer(
            reference,
            annotation,
            resolution_um=(100.0, 200.0, 300.0),
            sagittal_reference=sagittal_reference[:, :, :-1],
            sagittal_annotation=sagittal_annotation[:, :, :-1],
        )
    with pytest.raises(TypeError, match="annotation dtype"):
        SliceRenderer(
            reference,
            annotation,
            resolution_um=(100.0, 200.0, 300.0),
            sagittal_reference=sagittal_reference,
            sagittal_annotation=sagittal_annotation.astype(np.int64),
        )


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
