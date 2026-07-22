"""Qt interaction tests for linked orthogonal slice views."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsView
from pytestqt.qtbot import QtBot

from mouse_brain_planner.gui.viewers.orthogonal_view import OrthogonalSliceView
from mouse_brain_planner.rendering.slice_renderer import SliceOrientation, SliceRenderer

pytestmark = pytest.mark.gui


def make_renderer_test_double() -> SliceRenderer:
    """Return small synthetic ASR arrays, never a generated production brain."""

    shape = (4, 5, 6)  # [AP, DV, ML]
    reference = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)
    annotation = np.zeros(shape, dtype=np.uint32)
    annotation[1, 1:4, 1:5] = 7
    return SliceRenderer(
        reference,
        annotation,
        resolution_um=(100.0, 200.0, 300.0),
    )


@pytest.mark.parametrize(
    ("orientation", "expected_slice", "expected_pixel", "expected_image_shape"),
    [
        (SliceOrientation.CORONAL, 1, (4, 3), (5, 6)),
        (SliceOrientation.SAGITTAL, 4, (1, 3), (5, 4)),
        (SliceOrientation.HORIZONTAL, 3, (4, 1), (4, 6)),
    ],
)
def test_set_cursor_obeys_asr_axes_without_reemitting(
    qtbot: QtBot,
    orientation: SliceOrientation,
    expected_slice: int,
    expected_pixel: tuple[int, int],
    expected_image_shape: tuple[int, int],
) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), orientation)
    qtbot.addWidget(widget)
    spy = QSignalSpy(widget.cursor_changed)

    widget.set_cursor(1, 3, 4)

    assert widget.cursor_voxel == (1, 3, 4)
    assert widget.slice_index == expected_slice
    assert widget.slice_slider.value() == expected_slice
    assert widget.crosshair_pixel == expected_pixel
    assert widget.current_frame.grayscale.shape == expected_image_shape
    assert spy.count() == 0


def test_slider_and_mm_entry_emit_linkable_asr_cursor(qtbot: QtBot) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), "coronal")
    qtbot.addWidget(widget)
    widget.show()

    with qtbot.waitSignal(widget.cursor_changed, timeout=1000) as slider_signal:
        widget.slice_slider.setValue(1)
    assert slider_signal.args == [1, 2, 3]
    assert widget.position_spinbox.value() == pytest.approx(0.15)

    with qtbot.waitSignal(widget.cursor_changed, timeout=1000) as mm_signal:
        widget.position_spinbox.setValue(0.35)
    assert mm_signal.args == [3, 2, 3]
    assert widget.slice_slider.value() == 3


@pytest.mark.parametrize("resolution_um", [10.0, 25.0])
@pytest.mark.parametrize(
    ("orientation", "slice_count"),
    [
        (SliceOrientation.CORONAL, 2),
        (SliceOrientation.SAGITTAL, 4),
        (SliceOrientation.HORIZONTAL, 3),
    ],
)
def test_mm_entry_range_contains_only_voxel_centers(
    qtbot: QtBot,
    resolution_um: float,
    orientation: SliceOrientation,
    slice_count: int,
) -> None:
    shape = (2, 3, 4)
    renderer = SliceRenderer(
        np.zeros(shape, dtype=np.uint16),
        np.zeros(shape, dtype=np.uint32),
        resolution_um=(resolution_um, resolution_um, resolution_um),
    )
    widget = OrthogonalSliceView(renderer, orientation)
    qtbot.addWidget(widget)

    resolution_mm = resolution_um / 1000.0
    assert widget.position_spinbox.minimum() == pytest.approx(0.5 * resolution_mm)
    assert widget.position_spinbox.maximum() == pytest.approx((slice_count - 0.5) * resolution_mm)

    widget.position_spinbox.setValue(0.0)
    assert widget.position_spinbox.value() == pytest.approx(0.5 * resolution_mm)
    assert widget.slice_slider.value() == 0
    assert "Voxel-center" in widget.position_spinbox.accessibleDescription()


def test_image_click_maps_pixel_to_asr_voxel_and_moves_crosshair(qtbot: QtBot) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), "sagittal")
    qtbot.addWidget(widget)
    widget.resize(640, 480)
    widget.show()
    widget.set_cursor(1, 2, 4)
    qtbot.wait(20)

    # Sagittal columns are AP and rows are DV. Click the center of col=2,row=1.
    viewport_position = widget.graphics_view.mapFromScene(QPointF(2.5, 1.5))
    with qtbot.waitSignal(widget.cursor_changed, timeout=1000) as signal:
        qtbot.mouseClick(
            widget.graphics_view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=viewport_position,
        )

    assert signal.args == [2, 1, 4]
    assert widget.cursor_voxel == (2, 1, 4)
    assert widget.crosshair_pixel == (2, 1)


def test_wheel_steps_slice_while_ctrl_wheel_is_reserved_for_zoom(qtbot: QtBot) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), "horizontal")
    qtbot.addWidget(widget)
    widget.resize(640, 480)
    widget.show()
    widget.set_cursor(1, 2, 3)
    qtbot.wait(20)

    viewport = widget.graphics_view.viewport()
    local_position = viewport.rect().center()
    global_position = viewport.mapToGlobal(local_position)
    event = QWheelEvent(
        QPointF(local_position),
        QPointF(global_position),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    with qtbot.waitSignal(widget.cursor_changed, timeout=1000) as signal:
        QApplication.sendEvent(viewport, event)

    assert signal.args == [1, 3, 3]
    assert widget.slice_index == 3


def test_zoom_controls_and_pan_mode_are_available(qtbot: QtBot) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), "coronal")
    qtbot.addWidget(widget)
    widget.resize(640, 480)
    widget.show()
    qtbot.wait(20)

    before = widget.graphics_view.transform().m11()
    qtbot.mouseClick(widget.zoom_in_button, Qt.MouseButton.LeftButton)

    assert widget.graphics_view.transform().m11() > before
    assert widget.graphics_view.dragMode() is QGraphicsView.DragMode.ScrollHandDrag


def test_first_visible_slice_fits_the_final_viewport(qtbot: QtBot) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), "coronal")
    qtbot.addWidget(widget)
    widget.resize(640, 480)
    widget.show()
    qtbot.waitUntil(lambda: not widget.graphics_view._needs_initial_fit)

    viewport = widget.graphics_view.viewport().rect()
    displayed = widget.graphics_view.mapFromScene(widget.graphics_view.sceneRect()).boundingRect()

    assert displayed.width() <= viewport.width() + 2
    assert displayed.height() <= viewport.height() + 2
    assert (
        displayed.width() >= viewport.width() * 0.8 or displayed.height() >= viewport.height() * 0.8
    )


def test_slice_controls_are_named_and_slider_remains_usable_when_narrow(
    qtbot: QtBot,
) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), "horizontal")
    qtbot.addWidget(widget)
    widget.resize(295, 420)
    widget.show()
    qtbot.wait(20)

    assert widget.slice_slider.width() >= 100
    assert widget.slice_slider.accessibleName() == "horizontal slice index"
    assert widget.position_spinbox.accessibleName() == "horizontal slice position"
    assert widget.graphics_view.accessibleName() == "horizontal atlas slice"


@pytest.mark.parametrize(
    ("orientation", "expected_labels", "expected_accessible_names"),
    [
        ("coronal", "SIRL", ("Superior", "Inferior", "Right", "Left")),
        ("sagittal", "SIAP", ("Superior", "Inferior", "Anterior", "Posterior")),
        ("horizontal", "APRL", ("Anterior", "Posterior", "Right", "Left")),
    ],
)
def test_anatomical_edge_labels_are_correct_legible_and_image_anchored(
    qtbot: QtBot,
    orientation: str,
    expected_labels: str,
    expected_accessible_names: tuple[str, str, str, str],
) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), orientation)
    qtbot.addWidget(widget)
    widget.resize(640, 480)
    widget.show()
    qtbot.waitUntil(lambda: not widget.graphics_view._needs_initial_fit)

    labels = widget.graphics_view._anatomical_labels
    ordered = [labels[edge] for edge in ("top", "bottom", "left", "right")]
    assert "".join(label.text() for label in ordered) == expected_labels
    assert tuple(label.accessibleName() for label in ordered) == tuple(
        f"{name} edge" for name in expected_accessible_names
    )
    assert all(label.isVisible() for label in ordered)
    assert all(label.font().bold() for label in ordered)
    assert all(
        label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) for label in ordered
    )

    description = widget.graphics_view.accessibleDescription()
    for edge, full_name in zip(
        ("top", "bottom", "left", "right"),
        expected_accessible_names,
        strict=True,
    ):
        assert f"{edge} {full_name}" in description

    label_sizes = [label.size() for label in ordered]
    widget.graphics_view.zoom_in()
    visible_image = (
        widget.graphics_view.mapFromScene(widget.graphics_view.sceneRect())
        .boundingRect()
        .intersected(widget.graphics_view.viewport().rect())
    )
    assert [label.size() for label in ordered] == label_sizes
    assert all(visible_image.contains(label.geometry()) for label in ordered)

    previous_viewport_width = widget.graphics_view.viewport().width()
    widget.resize(420, 340)
    qtbot.waitUntil(lambda: widget.graphics_view.viewport().width() < previous_viewport_width)
    resized_visible_image = (
        widget.graphics_view.mapFromScene(widget.graphics_view.sceneRect())
        .boundingRect()
        .intersected(widget.graphics_view.viewport().rect())
    )
    assert [label.size() for label in ordered] == label_sizes
    assert all(resized_visible_image.contains(label.geometry()) for label in ordered)


def test_crosshair_has_cosmetic_contrast_halo_and_constant_size_center_marker(
    qtbot: QtBot,
) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), "coronal")
    qtbot.addWidget(widget)
    widget.resize(640, 480)
    widget.show()
    qtbot.waitUntil(lambda: not widget.graphics_view._needs_initial_fit)
    view = widget.graphics_view

    halo_lines = (view._vertical_crosshair_halo, view._horizontal_crosshair_halo)
    core_lines = (view._vertical_crosshair, view._horizontal_crosshair)
    assert all(item.isVisible() for item in (*halo_lines, *core_lines))
    assert all(item.pen().isCosmetic() for item in (*halo_lines, *core_lines))
    assert all(item.pen().widthF() == pytest.approx(3.0) for item in halo_lines)
    assert all(item.pen().color() == QColor(0, 0, 0, 230) for item in halo_lines)
    assert all(item.pen().widthF() == pytest.approx(1.25) for item in core_lines)
    assert all(item.pen().color() == QColor(0, 255, 255, 245) for item in core_lines)
    assert halo_lines[0].line() == core_lines[0].line()
    assert halo_lines[1].line() == core_lines[1].line()

    center_items = (view._crosshair_center_halo, view._crosshair_center)
    ignore_transform = QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    assert all(item.isVisible() for item in center_items)
    assert all(item.flags() & ignore_transform for item in center_items)
    assert center_items[0].pos() == center_items[1].pos()
    before = (
        center_items[1].deviceTransform(view.viewportTransform()).mapRect(center_items[1].rect())
    )
    view.zoom_in()
    after = (
        center_items[1].deviceTransform(view.viewportTransform()).mapRect(center_items[1].rect())
    )
    assert after.width() == pytest.approx(before.width())
    assert after.height() == pytest.approx(before.height())


def test_selected_region_and_contrast_redraw_current_frame(qtbot: QtBot) -> None:
    widget = OrthogonalSliceView(make_renderer_test_double(), "coronal")
    qtbot.addWidget(widget)
    widget.set_cursor(1, 2, 2)

    widget.set_contrast(0.0, 238.0)
    widget.set_selected_region(7, color=(255, 0, 0))

    assert widget.current_frame.selected_region[2, 2]
    assert widget.current_frame.rgb.dtype == np.uint8


def test_parent_selection_highlights_child_labels_while_leaf_remains_exact(qtbot: QtBot) -> None:
    renderer = make_renderer_test_double()
    renderer.annotation[1, 2, 3] = 8
    widget = OrthogonalSliceView(renderer, "coronal")
    qtbot.addWidget(widget)
    widget.set_cursor(1, 2, 2)

    widget.set_selected_region(7, included_region_ids={7, 8})
    assert widget.current_frame.selected_region[2, 2]
    assert widget.current_frame.selected_region[2, 3]

    widget.set_selected_region(8)
    assert not widget.current_frame.selected_region[2, 2]
    assert widget.current_frame.selected_region[2, 3]
