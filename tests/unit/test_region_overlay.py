from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from mouse_brain_planner.rendering.region_overlay import (
    REGION_OVERLAY_FILL_ALPHA,
    REGION_OVERLAY_OUTLINE_ALPHA,
    dorsal_surface_annotation,
    render_region_overlay,
)


def test_parent_overlay_includes_exact_descendant_annotation_ids() -> None:
    annotation = np.array(
        [
            [0, 7, 7, 0],
            [0, 8, 11, 0],
            [0, 0, 0, 0],
        ],
        dtype=np.uint32,
    )

    frame = render_region_overlay(
        annotation,
        included_structure_ids={7, 8},
        color=(10, 80, 220),
    )

    assert_array_equal(
        frame.selected,
        np.array(
            [
                [False, True, True, False],
                [False, True, False, False],
                [False, False, False, False],
            ]
        ),
    )
    assert not frame.selected[1, 2]
    assert np.all(frame.rgba[frame.selected, 3] >= REGION_OVERLAY_FILL_ALPHA)
    assert np.all(frame.rgba[frame.outline, 3] == REGION_OVERLAY_OUTLINE_ALPHA)
    assert np.all(frame.rgba[~(frame.selected | frame.outline)] == 0)
    assert not frame.rgba.flags.writeable


def test_single_voxel_region_remains_visible_as_an_outline() -> None:
    annotation = np.zeros((3, 3), dtype=np.uint16)
    annotation[1, 1] = 42

    frame = render_region_overlay(
        annotation,
        included_structure_ids=[42],
        color=(1, 2, 3),
    )

    assert frame.selected.sum() == 1
    assert frame.outline.sum() == 5
    assert frame.rgba[1, 1, 3] == REGION_OVERLAY_OUTLINE_ALPHA


def test_dorsal_projection_matches_first_nonzero_dv_annotation_in_chunks() -> None:
    annotation = np.zeros((3, 5, 4), dtype=np.int32)
    annotation[0, 3, 0] = 7
    annotation[0, 1, 1] = 8
    annotation[0, 4, 1] = 9
    annotation[1, 0, 2] = 11
    annotation[2, 2, 3] = 13

    projected = dorsal_surface_annotation(annotation, ap_chunk_size=1)

    assert_array_equal(
        projected,
        np.array(
            [
                [7, 8, 0, 0],
                [0, 0, 11, 0],
                [0, 0, 0, 13],
            ],
            dtype=np.int32,
        ),
    )
    assert not projected.flags.writeable


@pytest.mark.parametrize(
    ("annotation", "error"),
    [
        (np.zeros((2, 2, 2), dtype=np.float32), TypeError),
        (np.zeros((2, 2, 2, 2), dtype=np.int32), ValueError),
    ],
)
def test_dorsal_projection_rejects_non_annotation_volumes(
    annotation: np.ndarray,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        dorsal_surface_annotation(annotation)


def test_region_overlay_rejects_empty_or_invalid_id_sets() -> None:
    annotation = np.zeros((2, 2), dtype=np.uint16)
    with pytest.raises(ValueError, match="must not be empty"):
        render_region_overlay(
            annotation,
            included_structure_ids=[],
            color=(1, 2, 3),
        )
    with pytest.raises(ValueError, match="positive"):
        render_region_overlay(
            annotation,
            included_structure_ids=[0],
            color=(1, 2, 3),
        )
