"""GUI integration tests for truthful population density slice overlays."""

from __future__ import annotations

import numpy as np
import pytest
from pytestqt.qtbot import QtBot
from tests.fixtures.reference_density_overlay_factory import (
    make_reference_density_overlay_test_double,
)

from mouse_brain_planner.gui.viewers.orthogonal_view import OrthogonalSliceView
from mouse_brain_planner.rendering.slice_renderer import SliceOrientation, SliceRenderer
from mouse_brain_planner.vasculature.density_overlay import (
    REFERENCE_DENSITY_DISCLOSURE_LABEL,
    ReferenceDensityOverlayError,
)

pytestmark = pytest.mark.gui


def _renderer() -> SliceRenderer:
    shape = (4, 6, 8)
    reference = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)
    annotation = np.zeros(shape, dtype=np.uint32)
    return SliceRenderer(
        reference,
        annotation,
        resolution_um=(50.0, 50.0, 50.0),
    )


def test_density_label_is_truthful_persistent_across_rerenders_and_clear_restores_base(
    qtbot: QtBot,
) -> None:
    widget = OrthogonalSliceView(_renderer(), SliceOrientation.CORONAL)
    qtbot.addWidget(widget)
    widget.resize(680, 520)
    widget.show()
    density = make_reference_density_overlay_test_double()
    assert widget.reference_density_label.isHidden()
    base = widget.displayed_rgb.copy()

    widget.set_reference_vascular_density(
        density,
        opacity=0.6,
        window_low=0.0,
        window_high=23.0,
    )

    assert widget.reference_density_label.text() == REFERENCE_DENSITY_DISCLOSURE_LABEL
    assert not widget.reference_density_label.isHidden()
    assert "Symmetrized population reference vascular length density" in (
        widget.reference_density_label.text()
    )
    assert "four adult mice" in widget.reference_density_label.text()
    assert "100 µm local window" in widget.reference_density_label.text()
    assert "not subject-specific" in widget.reference_density_label.text()
    assert "not vessel paths" in widget.reference_density_label.text()
    assert "nearest" not in widget.reference_density_label.text().casefold()
    assert "clearance" not in widget.reference_density_label.text().casefold()
    assert not np.array_equal(widget.displayed_rgb, base)

    first_overlay = widget.displayed_rgb.copy()
    widget.set_slice_index(3)
    assert not widget.reference_density_label.isHidden()
    assert not np.array_equal(widget.displayed_rgb, first_overlay)
    widget.set_contrast(0.0, 200.0)
    assert widget.reference_density_label.isVisible()
    assert not np.array_equal(widget.displayed_rgb, widget.current_frame.rgb)

    widget.clear_reference_vascular_density()

    assert widget.reference_density_label.isHidden()
    np.testing.assert_array_equal(widget.displayed_rgb, widget.current_frame.rgb)
    widget.set_slice_index(1)
    np.testing.assert_array_equal(widget.displayed_rgb, widget.current_frame.rgb)


def test_zero_density_changes_no_pixels_but_keeps_the_population_disclosure_visible(
    qtbot: QtBot,
) -> None:
    widget = OrthogonalSliceView(_renderer(), SliceOrientation.HORIZONTAL)
    qtbot.addWidget(widget)
    zero_density = make_reference_density_overlay_test_double(np.zeros((2, 3, 4), dtype=np.float32))
    base = widget.displayed_rgb.copy()

    widget.set_reference_vascular_density(
        zero_density,
        opacity=1.0,
        window_low=0.0,
        window_high=1.0,
    )

    np.testing.assert_array_equal(widget.displayed_rgb, base)
    assert not widget.reference_density_label.isHidden()


def test_set_density_rejects_grid_or_style_misuse_without_replacing_current_overlay(
    qtbot: QtBot,
) -> None:
    widget = OrthogonalSliceView(_renderer(), SliceOrientation.SAGITTAL)
    qtbot.addWidget(widget)
    valid = make_reference_density_overlay_test_double()
    widget.set_reference_vascular_density(
        valid,
        opacity=0.5,
        window_low=0.0,
        window_high=23.0,
    )
    before = widget.displayed_rgb.copy()

    wrong_grid = make_reference_density_overlay_test_double(
        density_shape_asr=(2, 2, 2),
    )
    with pytest.raises(ReferenceDensityOverlayError, match="target shape"):
        widget.set_reference_vascular_density(
            wrong_grid,
            opacity=0.5,
            window_low=0.0,
            window_high=7.0,
        )
    np.testing.assert_array_equal(widget.displayed_rgb, before)
    assert not widget.reference_density_label.isHidden()

    with pytest.raises(ReferenceDensityOverlayError, match="opacity"):
        widget.set_reference_vascular_density(
            valid,
            opacity=2.0,
            window_low=0.0,
            window_high=23.0,
        )
    np.testing.assert_array_equal(widget.displayed_rgb, before)


def test_density_overlay_rerenders_on_native_slider_change(qtbot: QtBot) -> None:
    widget = OrthogonalSliceView(_renderer(), SliceOrientation.CORONAL)
    qtbot.addWidget(widget)
    widget.set_reference_vascular_density(
        make_reference_density_overlay_test_double(),
        opacity=0.7,
        window_low=0.0,
        window_high=23.0,
    )
    before = widget.displayed_rgb.copy()

    widget.slice_slider.setValue(3)

    assert widget.slice_index == 3
    assert not np.array_equal(widget.displayed_rgb, before)
    assert widget.reference_density_label.text() == REFERENCE_DENSITY_DISCLOSURE_LABEL
