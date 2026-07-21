"""Interactive Qt widget for one orthogonal BrainGlobe ASR slice."""

from __future__ import annotations

import math
from typing import overload

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mouse_brain_planner.rendering.slice_renderer import (
    RGBColor,
    SliceFrame,
    SliceOrientation,
    SliceRenderer,
    VoxelIndex,
)


class _SliceGraphicsView(QGraphicsView):
    """Pixmap view with click picking, hand pan, zoom, and slice-wheel signals."""

    scene_clicked = Signal(QPointF)
    slice_step = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._slice_scene = QGraphicsScene(self)
        self.setScene(self._slice_scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self._slice_scene.addItem(self._pixmap_item)

        pen = QPen(QColor(0, 255, 255, 230))
        pen.setWidthF(1.0)
        pen.setCosmetic(True)
        self._vertical_crosshair = QGraphicsLineItem()
        self._horizontal_crosshair = QGraphicsLineItem()
        for item in (self._vertical_crosshair, self._horizontal_crosshair):
            item.setPen(pen)
            item.setZValue(10.0)
            item.hide()
            self._slice_scene.addItem(item)

        self._image_width = 0
        self._image_height = 0
        self._has_fitted_image = False
        self._press_position: QPoint | None = None

        self.setObjectName("orthogonal-slice-canvas")
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_rgb_image(self, rgb: NDArray[np.uint8]) -> None:
        """Display a contiguous RGB image and detach it from the NumPy buffer."""

        values = np.ascontiguousarray(rgb, dtype=np.uint8)
        if values.ndim != 3 or values.shape[2] != 3:
            raise ValueError("slice display requires an RGB array with shape (rows, columns, 3)")
        height, width, _ = values.shape
        bytes_per_line = int(values.strides[0])
        image = QImage(
            values.data,
            int(width),
            int(height),
            bytes_per_line,
            QImage.Format.Format_RGB888,
        ).copy()
        self._pixmap_item.setPixmap(QPixmap.fromImage(image))
        self._image_width = int(width)
        self._image_height = int(height)
        self._slice_scene.setSceneRect(QRectF(0.0, 0.0, float(width), float(height)))
        if not self._has_fitted_image:
            self.fit_image()
            self._has_fitted_image = True

    def set_crosshair(self, column: int, row: int) -> None:
        """Place crosshair lines through the center of one displayed pixel."""

        if not 0 <= column < self._image_width or not 0 <= row < self._image_height:
            raise IndexError("crosshair pixel lies outside the displayed image")
        x = float(column) + 0.5
        y = float(row) + 0.5
        self._vertical_crosshair.setLine(x, 0.0, x, float(self._image_height))
        self._horizontal_crosshair.setLine(0.0, y, float(self._image_width), y)
        self._vertical_crosshair.show()
        self._horizontal_crosshair.show()

    def fit_image(self) -> None:
        """Fit the complete slice in the viewport."""

        if self._image_width and self._image_height:
            self.fitInView(self._slice_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_by(self, factor: float) -> None:
        """Zoom around the pointer while keeping a bounded useful scale."""

        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("zoom factor must be positive and finite")
        current = abs(float(self.transform().m11()))
        target = current * factor
        if 0.02 <= target <= 100.0:
            self.scale(factor, factor)

    def zoom_in(self) -> None:
        """Increase magnification by one UI step."""

        self.zoom_by(1.25)

    def zoom_out(self) -> None:
        """Decrease magnification by one UI step."""

        self.zoom_by(0.8)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() is Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        release_position = event.position().toPoint()
        scene_position = self.mapToScene(release_position)
        press_position = self._press_position
        self._press_position = None
        super().mouseReleaseEvent(event)
        if (
            event.button() is Qt.MouseButton.LeftButton
            and press_position is not None
            and (release_position - press_position).manhattanLength() <= 3
            and 0.0 <= scene_position.x() < self._image_width
            and 0.0 <= scene_position.y() < self._image_height
        ):
            self.scene_clicked.emit(scene_position)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        zoom_modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        if event.modifiers() & zoom_modifiers:
            self.zoom_by(1.2 if delta > 0 else 1.0 / 1.2)
        else:
            self.slice_step.emit(1 if delta > 0 else -1)
        event.accept()


class OrthogonalSliceView(QWidget):
    """One linked coronal, sagittal, or horizontal ASR slice viewer.

    ``cursor_changed`` and ``crosshair_changed`` carry discrete ``(AP, DV, ML)``
    indices after user interaction. ``set_cursor`` updates a linked view without
    re-emitting the signals, preventing feedback loops between multiple views.
    """

    cursor_changed = Signal(int, int, int)
    crosshair_changed = Signal(int, int, int)
    slice_changed = Signal(int)

    def __init__(
        self,
        renderer: SliceRenderer,
        orientation: SliceOrientation | str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.renderer = renderer
        self.orientation = SliceOrientation.coerce(orientation)
        self._cursor: VoxelIndex = tuple(size // 2 for size in renderer.shape)  # type: ignore[assignment]
        self._contrast_low: float | None = None
        self._contrast_high: float | None = None
        self._selected_region_id: int | None = None
        self._selected_color: RGBColor = (0, 174, 239)
        self._syncing_controls = False
        self._current_frame: SliceFrame | None = None

        self.setObjectName(f"{self.orientation.value}-slice-view")
        self._build_ui()
        self._connect_signals()
        self._sync_controls()
        self._render()

    @property
    def cursor_voxel(self) -> VoxelIndex:
        """Current discrete crosshair position in ``(AP, DV, ML)`` order."""

        return self._cursor

    @property
    def slice_index(self) -> int:
        """Current fixed-axis array index."""

        return self.renderer.slice_index_for_voxel(self.orientation, self._cursor)

    @property
    def current_frame(self) -> SliceFrame:
        """Most recently displayed vectorized render result."""

        if self._current_frame is None:
            raise RuntimeError("slice has not been rendered")
        return self._current_frame

    @property
    def crosshair_pixel(self) -> tuple[int, int]:
        """Current displayed crosshair as ``(column, row)``."""

        return self.renderer.voxel_to_pixel(self.orientation, self._cursor)

    @overload
    def set_cursor(self, voxel: VoxelIndex, /) -> None: ...

    @overload
    def set_cursor(self, ap: int, dv: int, ml: int, /) -> None: ...

    def set_cursor(
        self,
        ap_or_voxel: int | VoxelIndex,
        dv: int | None = None,
        ml: int | None = None,
    ) -> None:
        """Set a linked ASR crosshair without emitting user-interaction signals."""

        if isinstance(ap_or_voxel, tuple):
            if dv is not None or ml is not None:
                raise TypeError("pass either an ASR tuple or three integer components")
            voxel = ap_or_voxel
        else:
            if dv is None or ml is None:
                raise TypeError("AP, DV, and ML are all required")
            voxel = (ap_or_voxel, dv, ml)
        self._apply_cursor(voxel, emit=False)

    def set_slice_index(self, slice_index: int) -> None:
        """Set the fixed-axis slice without emitting user-interaction signals."""

        voxel = list(self._cursor)
        voxel[self.orientation.fixed_axis] = slice_index
        self._apply_cursor((voxel[0], voxel[1], voxel[2]), emit=False)

    def set_contrast(self, low: float | None, high: float | None) -> None:
        """Set the grayscale contrast window and redraw."""

        if low is not None and not math.isfinite(float(low)):
            raise ValueError("contrast low limit must be finite")
        if high is not None and not math.isfinite(float(high)):
            raise ValueError("contrast high limit must be finite")
        if low is not None and high is not None and float(high) < float(low):
            raise ValueError("contrast high limit must not be below the low limit")
        self._contrast_low = None if low is None else float(low)
        self._contrast_high = None if high is None else float(high)
        self._render()

    def set_selected_region(
        self,
        region_id: int | None,
        *,
        color: RGBColor = (0, 174, 239),
    ) -> None:
        """Select an annotation ID for a translucent overlay and redraw."""

        if self._selected_region_id == region_id and self._selected_color == color:
            return
        self._selected_region_id = region_id
        self._selected_color = color
        self._render()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        axis_label = QLabel(f"{self.orientation.fixed_axis_name} slice", self)
        axis_label.setObjectName("slice-axis-label")
        controls.addWidget(axis_label)

        self.slice_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slice_slider.setObjectName("slice-index-slider")
        self.slice_slider.setRange(0, self.renderer.slice_count(self.orientation) - 1)
        self.slice_slider.setSingleStep(1)
        self.slice_slider.setPageStep(10)
        controls.addWidget(self.slice_slider, 1)

        fixed_axis = self.orientation.fixed_axis
        resolution_mm = self.renderer.resolution_um[fixed_axis] / 1000.0
        final_center_mm = (self.renderer.slice_count(self.orientation) - 0.5) * resolution_mm
        self.position_spinbox = QDoubleSpinBox(self)
        self.position_spinbox.setObjectName("slice-position-mm")
        self.position_spinbox.setDecimals(4)
        self.position_spinbox.setRange(0.0, final_center_mm)
        self.position_spinbox.setSingleStep(resolution_mm)
        self.position_spinbox.setSuffix(" mm ASR")
        self.position_spinbox.setKeyboardTracking(False)
        controls.addWidget(self.position_spinbox)

        self.zoom_out_button = QToolButton(self)
        self.zoom_out_button.setObjectName("slice-zoom-out")
        self.zoom_out_button.setText("-")
        self.zoom_out_button.setToolTip("Zoom out")
        controls.addWidget(self.zoom_out_button)

        self.zoom_in_button = QToolButton(self)
        self.zoom_in_button.setObjectName("slice-zoom-in")
        self.zoom_in_button.setText("+")
        self.zoom_in_button.setToolTip("Zoom in")
        controls.addWidget(self.zoom_in_button)

        self.fit_button = QToolButton(self)
        self.fit_button.setObjectName("slice-fit-image")
        self.fit_button.setText("Fit")
        self.fit_button.setToolTip("Fit complete slice")
        controls.addWidget(self.fit_button)
        layout.addLayout(controls)

        self.graphics_view = _SliceGraphicsView(self)
        self.graphics_view.setMinimumSize(240, 180)
        layout.addWidget(self.graphics_view, 1)

    def _connect_signals(self) -> None:
        self.slice_slider.valueChanged.connect(self._on_slider_changed)
        self.position_spinbox.valueChanged.connect(self._on_position_changed)
        self.graphics_view.scene_clicked.connect(self._on_scene_clicked)
        self.graphics_view.slice_step.connect(self._on_slice_step)
        self.zoom_in_button.clicked.connect(self.graphics_view.zoom_in)
        self.zoom_out_button.clicked.connect(self.graphics_view.zoom_out)
        self.fit_button.clicked.connect(self.graphics_view.fit_image)

    def _sync_controls(self) -> None:
        self._syncing_controls = True
        try:
            self.slice_slider.setValue(self.slice_index)
            self.position_spinbox.setValue(
                self.renderer.slice_center_mm(self.orientation, self.slice_index)
            )
        finally:
            self._syncing_controls = False

    def _render(self) -> None:
        self._current_frame = self.renderer.render_slice(
            self.orientation,
            self.slice_index,
            contrast_low=self._contrast_low,
            contrast_high=self._contrast_high,
            selected_region_id=self._selected_region_id,
            selected_color=self._selected_color,
        )
        self.graphics_view.set_rgb_image(self._current_frame.rgb)
        self._update_crosshair()

    def _update_crosshair(self) -> None:
        column, row = self.crosshair_pixel
        self.graphics_view.set_crosshair(column, row)

    def _apply_cursor(self, voxel: VoxelIndex, *, emit: bool) -> None:
        validated = self.renderer.validate_voxel(voxel)
        previous_slice = self.slice_index
        self._cursor = validated
        new_slice = self.slice_index
        self._sync_controls()
        if new_slice != previous_slice:
            self._render()
        else:
            self._update_crosshair()
        if emit:
            if new_slice != previous_slice:
                self.slice_changed.emit(new_slice)
            ap, dv, ml = validated
            self.cursor_changed.emit(ap, dv, ml)
            self.crosshair_changed.emit(ap, dv, ml)

    def _on_slider_changed(self, value: int) -> None:
        if self._syncing_controls:
            return
        voxel = list(self._cursor)
        voxel[self.orientation.fixed_axis] = value
        self._apply_cursor((voxel[0], voxel[1], voxel[2]), emit=True)

    def _on_position_changed(self, position_mm: float) -> None:
        if self._syncing_controls:
            return
        index = self.renderer.slice_index_from_mm(self.orientation, position_mm)
        voxel = list(self._cursor)
        voxel[self.orientation.fixed_axis] = index
        self._apply_cursor((voxel[0], voxel[1], voxel[2]), emit=True)

    def _on_scene_clicked(self, position: QPointF) -> None:
        column = math.floor(position.x())
        row = math.floor(position.y())
        voxel = self.renderer.pixel_to_voxel(
            self.orientation,
            self.slice_index,
            column,
            row,
        )
        self._apply_cursor(voxel, emit=True)

    def _on_slice_step(self, step: int) -> None:
        maximum = self.renderer.slice_count(self.orientation) - 1
        target = min(max(self.slice_index + step, 0), maximum)
        if target == self.slice_index:
            return
        voxel = list(self._cursor)
        voxel[self.orientation.fixed_axis] = target
        self._apply_cursor((voxel[0], voxel[1], voxel[2]), emit=True)
