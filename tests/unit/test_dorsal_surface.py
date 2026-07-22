from __future__ import annotations

import numpy as np
import pytest

from mouse_brain_planner.rendering.dorsal_surface import render_dorsal_surface


def test_dorsal_surface_samples_first_annotated_dv_voxel() -> None:
    reference = np.zeros((3, 4, 3), dtype=np.uint16)
    annotation = np.zeros((3, 4, 3), dtype=np.uint32)
    annotation[0, 2, 0] = 10
    annotation[0, 3, 0] = 10
    reference[0, 2, 0] = 100
    reference[0, 3, 0] = 200
    annotation[1, 1, 1] = 20
    annotation[1, 2, 1] = 20
    reference[1, 1, 1] = 300
    reference[1, 2, 1] = 400

    frame = render_dorsal_surface(
        reference,
        annotation,
        resolution_um=(25.0, 25.0, 25.0),
    )

    assert frame.surface_dv_index[0, 0] == 2
    assert frame.surface_dv_index[1, 1] == 1
    assert frame.reference[0, 0] == 100
    assert frame.reference[1, 1] == 300
    assert frame.annotation[0, 0] == 10
    assert frame.annotation[1, 1] == 20
    assert frame.brain_mask[2, 2] == np.False_
    np.testing.assert_array_equal(frame.rgb[2, 2], (0, 0, 0))
    assert frame.rgb.flags.writeable is False
    assert frame.row_axis == "AP"
    assert frame.column_axis == "ML"


def test_dorsal_surface_uses_smallest_dv_when_labels_are_discontinuous() -> None:
    reference = np.arange(18, dtype=np.uint16).reshape(2, 3, 3)
    annotation = np.zeros((2, 3, 3), dtype=np.uint32)
    annotation[1, 0, 2] = 7
    annotation[1, 2, 2] = 9

    frame = render_dorsal_surface(
        reference,
        annotation,
        resolution_um=(1.0, 2.0, 3.0),
    )

    assert frame.surface_dv_index[1, 2] == 0
    assert frame.annotation[1, 2] == 7
    assert frame.dv_resolution_um == 2.0


@pytest.mark.parametrize(
    ("reference", "annotation", "message"),
    [
        (np.zeros((2, 2)), np.zeros((2, 2)), "three-dimensional"),
        (np.zeros((2, 2, 2)), np.zeros((2, 2, 3)), "same non-empty"),
        (
            np.zeros((2, 2, 2), dtype=np.uint16),
            np.zeros((2, 2, 2), dtype=np.float32),
            "integer dtype",
        ),
    ],
)
def test_dorsal_surface_rejects_invalid_volume_contracts(
    reference: np.ndarray,
    annotation: np.ndarray,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        render_dorsal_surface(
            reference,
            annotation,
            resolution_um=(25.0, 25.0, 25.0),
        )
