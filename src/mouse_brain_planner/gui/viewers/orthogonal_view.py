"""Interactive Qt widget for one orthogonal BrainGlobe ASR slice."""

from __future__ import annotations

import math
from collections.abc import Collection
from typing import cast, overload

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QGraphicsEllipseItem,
    QGraphicsItem,
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
from mouse_brain_planner.vasculature.density_overlay import (
    REFERENCE_DENSITY_DISCLOSURE_LABEL,
    ReferenceDensityAtlasBinding,
    ReferenceDensityHeatmapStyle,
    composite_reference_density_heatmap,
    sample_reference_density_plane,
)
from mouse_brain_planner.vasculature.reference_density import ReferenceVascularDensity

_ANATOMICAL_EDGE_LABELS: dict[
    SliceOrientation,
    dict[str, tuple[str, str]],
] = {
    SliceOrientation.CORONAL: {
        "top": ("S", "Superior"),
        "bottom": ("I", "Inferior"),
        "left": ("R", "Right"),
        "right": ("L", "Left"),
    },
    SliceOrientation.SAGITTAL: {
        "top": ("S", "Superior"),
        "bottom": ("I", "Inferior"),
        "left": ("A", "Anterior"),
        "right": ("P", "Posterior"),
    },
    SliceOrientation.HORIZONTAL: {
        "top": ("A", "Anterior"),
        "bottom": ("P", "Posterior"),
        "left": ("R", "Right"),
        "right": ("L", "Left"),
    },
}


class _SliceGraphicsView(QGraphicsView):
    """Pixmap view with click picking, hand pan, zoom, and slice-wheel signals."""

    scene_clicked = Signal(QPointF)
    slice_step = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._anatomical_labels: dict[str, QLabel] = {}
        self._image_width = 0
        self._image_height = 0

        self._slice_scene = QGraphicsScene(self)
        self.setScene(self._slice_scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self._slice_scene.addItem(self._pixmap_item)

        halo_pen = QPen(QColor(0, 0, 0, 230))
        halo_pen.setWidthF(3.0)
        halo_pen.setCosmetic(True)
        core_pen = QPen(QColor(0, 255, 255, 245))
        core_pen.setWidthF(1.25)
        core_pen.setCosmetic(True)

        self._vertical_crosshair_halo = QGraphicsLineItem()
        self._horizontal_crosshair_halo = QGraphicsLineItem()
        self._vertical_crosshair = QGraphicsLineItem()
        self._horizontal_crosshair = QGraphicsLineItem()
        for item in (self._vertical_crosshair_halo, self._horizontal_crosshair_halo):
            item.setPen(halo_pen)
            item.setZValue(10.0)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.hide()
            self._slice_scene.addItem(item)
        for item in (self._vertical_crosshair, self._horizontal_crosshair):
            item.setPen(core_pen)
            item.setZValue(11.0)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.hide()
            self._slice_scene.addItem(item)

        self._crosshair_center_halo = QGraphicsEllipseItem(-4.0, -4.0, 8.0, 8.0)
        self._crosshair_center = QGraphicsEllipseItem(-4.0, -4.0, 8.0, 8.0)
        for center_item, pen, z_value in (
            (self._crosshair_center_halo, halo_pen, 12.0),
            (self._crosshair_center, core_pen, 13.0),
        ):
            center_item.setPen(pen)
            center_item.setZValue(z_value)
            center_item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            center_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            center_item.hide()
            self._slice_scene.addItem(center_item)

        self._needs_initial_fit = True
        self._press_position: QPoint | None = None
        self._initial_fit_timer = QTimer(self)
        self._initial_fit_timer.setSingleShot(True)
        self._initial_fit_timer.timeout.connect(self._fit_initial_image)

        self.setObjectName("orthogonal-slice-canvas")
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_anatomical_edge_labels(
        self,
        labels: dict[str, tuple[str, str]],
    ) -> None:
        """Show restrained, constant-size anatomical labels at the image edges."""

        expected_edges = {"top", "bottom", "left", "right"}
        if set(labels) != expected_edges:
            raise ValueError("anatomical labels require top, bottom, left, and right edges")
        for label in self._anatomical_labels.values():
            label.deleteLater()
        self._anatomical_labels.clear()

        for edge in ("top", "bottom", "left", "right"):
            abbreviation, full_name = labels[edge]
            label = QLabel(abbreviation, self.viewport())
            label.setObjectName(f"anatomical-{edge}-label")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            label.setAccessibleName(f"{full_name} edge")
            label.setToolTip(full_name)
            font = label.font()
            font.setBold(True)
            if font.pointSizeF() > 0:
                font.setPointSizeF(max(10.0, font.pointSizeF()))
            label.setFont(font)
            label.setStyleSheet(
                "QLabel {"
                " color: rgba(255, 255, 255, 245);"
                " background-color: rgba(0, 0, 0, 178);"
                " border: 1px solid rgba(255, 255, 255, 100);"
                " border-radius: 9px;"
                " padding: 0px;"
                "}"
            )
            size = max(20, label.sizeHint().width() + 8, label.sizeHint().height() + 4)
            label.setFixedSize(size, size)
            label.hide()
            self._anatomical_labels[edge] = label
        self._position_anatomical_labels()

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
        self._position_anatomical_labels()
        if self._needs_initial_fit:
            self._initial_fit_timer.start(0)

    def set_crosshair(self, column: int, row: int) -> None:
        """Place crosshair lines through the center of one displayed pixel."""

        if not 0 <= column < self._image_width or not 0 <= row < self._image_height:
            raise IndexError("crosshair pixel lies outside the displayed image")
        x = float(column) + 0.5
        y = float(row) + 0.5
        for item in (self._vertical_crosshair_halo, self._vertical_crosshair):
            item.setLine(x, 0.0, x, float(self._image_height))
            item.show()
        for item in (self._horizontal_crosshair_halo, self._horizontal_crosshair):
            item.setLine(0.0, y, float(self._image_width), y)
            item.show()
        for center_item in (self._crosshair_center_halo, self._crosshair_center):
            center_item.setPos(x, y)
            center_item.show()

    def fit_image(self) -> None:
        """Fit the complete slice in the viewport."""

        if self._image_width and self._image_height:
            self.fitInView(self._slice_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._needs_initial_fit = False
            self._position_anatomical_labels()

    def _fit_initial_image(self) -> None:
        """Fit once the hidden tab has a real, laid-out viewport."""

        if (
            self._needs_initial_fit
            and self.isVisible()
            and self.viewport().width() > 1
            and self.viewport().height() > 1
        ):
            self.fit_image()

    def zoom_by(self, factor: float) -> None:
        """Zoom around the pointer while keeping a bounded useful scale."""

        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("zoom factor must be positive and finite")
        current = abs(float(self.transform().m11()))
        target = current * factor
        if 0.02 <= target <= 1000.0:
            self._needs_initial_fit = False
            self.scale(factor, factor)
            self._position_anatomical_labels()

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
            and (release_position - press_position).manhattanLength()
            <= QApplication.startDragDistance()
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

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Defer the first fit until Qt has laid out a formerly hidden tab."""

        super().showEvent(event)
        if self._needs_initial_fit:
            self._initial_fit_timer.start(0)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """Use the final viewport geometry for the pending initial fit."""

        super().resizeEvent(event)
        self._position_anatomical_labels()
        if self._needs_initial_fit:
            self._initial_fit_timer.start(0)

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        """Keep anatomical labels attached while the user pans the image."""

        super().scrollContentsBy(dx, dy)
        self._position_anatomical_labels()

    def _position_anatomical_labels(self) -> None:
        """Anchor labels inside the currently visible part of the atlas image."""

        if not self._anatomical_labels or not self._image_width or not self._image_height:
            return
        image_rect = self.mapFromScene(self._slice_scene.sceneRect()).boundingRect()
        visible_rect = image_rect.intersected(self.viewport().rect())
        if visible_rect.width() <= 0 or visible_rect.height() <= 0:
            for label in self._anatomical_labels.values():
                label.hide()
            return

        margin = 6
        top = self._anatomical_labels["top"]
        bottom = self._anatomical_labels["bottom"]
        left = self._anatomical_labels["left"]
        right = self._anatomical_labels["right"]
        center_x = visible_rect.center().x()
        center_y = visible_rect.center().y()
        top.move(center_x - top.width() // 2, visible_rect.top() + margin)
        bottom.move(
            center_x - bottom.width() // 2,
            visible_rect.bottom() - bottom.height() - margin + 1,
        )
        left.move(visible_rect.left() + margin, center_y - left.height() // 2)
        right.move(
            visible_rect.right() - right.width() - margin + 1,
            center_y - right.height() // 2,
        )
        for label in self._anatomical_labels.values():
            label.show()


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
        self._selected_region_ids: frozenset[int] = frozenset()
        self._selected_color: RGBColor = (0, 174, 239)
        self._reference_density_binding: ReferenceDensityAtlasBinding | None = None
        self._reference_density_style: ReferenceDensityHeatmapStyle | None = None
        self._syncing_controls = False
        self._current_frame: SliceFrame | None = None
        self._displayed_rgb: NDArray[np.uint8] | None = None

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
    def displayed_rgb(self) -> NDArray[np.uint8]:
        """Return the exact RGB image most recently sent to the Qt canvas."""

        if self._displayed_rgb is None:
            raise RuntimeError("slice has not been displayed")
        return self._displayed_rgb

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
        included_region_ids: Collection[int] | None = None,
        color: RGBColor = (0, 174, 239),
    ) -> None:
        """Select a region hierarchy for one consistent translucent overlay."""

        region_ids = (
            frozenset()
            if region_id is None
            else frozenset(included_region_ids or (region_id,)) | {region_id}
        )
        if self._selected_region_ids == region_ids and self._selected_color == color:
            return
        self._selected_region_ids = region_ids
        self._selected_color = color
        self._render()

    def set_reference_vascular_density(
        self,
        density: ReferenceVascularDensity,
        *,
        opacity: float,
        window_low: float,
        window_high: float,
    ) -> None:
        """Validate, display, and truthfully label population reference density."""

        binding = ReferenceDensityAtlasBinding(
            density=density,
            atlas_shape_asr=self.renderer.shape,
            atlas_resolution_um=cast(
                tuple[float, float, float],
                self.renderer.resolution_um,
            ),
        )
        style = ReferenceDensityHeatmapStyle(
            opacity=opacity,
            window_low=window_low,
            window_high=window_high,
        )
        self._reference_density_binding = binding
        self._reference_density_style = style
        self.reference_density_label.show()
        self._render()

    def clear_reference_vascular_density(self) -> None:
        """Remove only the population scalar overlay and redraw the base slice."""

        self._reference_density_binding = None
        self._reference_density_style = None
        self.reference_density_label.hide()
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
        self.slice_slider.setMinimumWidth(100)
        self.slice_slider.setAccessibleName(f"{self.orientation.value} slice index")
        self.slice_slider.setAccessibleDescription(
            f"Move through {self.orientation.value} atlas slices"
        )
        axis_label.setBuddy(self.slice_slider)
        controls.addWidget(self.slice_slider, 1)
        layout.addLayout(controls)

        fixed_axis = self.orientation.fixed_axis
        resolution_mm = self.renderer.resolution_um[fixed_axis] / 1000.0
        first_center_mm = 0.5 * resolution_mm
        final_center_mm = (self.renderer.slice_count(self.orientation) - 0.5) * resolution_mm
        secondary_controls = QHBoxLayout()
        position_label = QLabel("Position", self)
        position_label.setObjectName("slice-position-label")
        secondary_controls.addWidget(position_label)
        self.position_spinbox = QDoubleSpinBox(self)
        self.position_spinbox.setObjectName("slice-position-mm")
        self.position_spinbox.setDecimals(4)
        self.position_spinbox.setRange(first_center_mm, final_center_mm)
        self.position_spinbox.setSingleStep(resolution_mm)
        self.position_spinbox.setSuffix(" mm ASR")
        self.position_spinbox.setKeyboardTracking(False)
        self.position_spinbox.setAccessibleName(f"{self.orientation.value} slice position")
        self.position_spinbox.setAccessibleDescription(
            "Voxel-center position in millimeters in BrainGlobe ASR coordinates"
        )
        position_label.setBuddy(self.position_spinbox)
        secondary_controls.addWidget(self.position_spinbox)
        secondary_controls.addStretch(1)

        self.zoom_out_button = QToolButton(self)
        self.zoom_out_button.setObjectName("slice-zoom-out")
        self.zoom_out_button.setText("-")
        self.zoom_out_button.setToolTip("Zoom out")
        self.zoom_out_button.setAccessibleName(f"Zoom out {self.orientation.value} slice")
        secondary_controls.addWidget(self.zoom_out_button)

        self.zoom_in_button = QToolButton(self)
        self.zoom_in_button.setObjectName("slice-zoom-in")
        self.zoom_in_button.setText("+")
        self.zoom_in_button.setToolTip("Zoom in")
        self.zoom_in_button.setAccessibleName(f"Zoom in {self.orientation.value} slice")
        secondary_controls.addWidget(self.zoom_in_button)

        self.fit_button = QToolButton(self)
        self.fit_button.setObjectName("slice-fit-image")
        self.fit_button.setText("Fit")
        self.fit_button.setToolTip("Fit complete slice")
        self.fit_button.setAccessibleName(f"Fit complete {self.orientation.value} slice")
        secondary_controls.addWidget(self.fit_button)
        layout.addLayout(secondary_controls)

        self.reference_density_label = QLabel(REFERENCE_DENSITY_DISCLOSURE_LABEL, self)
        self.reference_density_label.setObjectName("reference-vascular-density-disclosure")
        self.reference_density_label.setAccessibleName(
            "Population reference vascular density disclosure"
        )
        self.reference_density_label.setWordWrap(True)
        self.reference_density_label.setStyleSheet(
            "QLabel { color: #8a004f; background: #fff0f8; border: 1px solid #c84c91; "
            "border-radius: 4px; padding: 4px; }"
        )
        self.reference_density_label.hide()
        layout.addWidget(self.reference_density_label)

        self.graphics_view = _SliceGraphicsView(self)
        self.graphics_view.setMinimumSize(240, 180)
        anatomical_labels = _ANATOMICAL_EDGE_LABELS[self.orientation]
        self.graphics_view.set_anatomical_edge_labels(anatomical_labels)
        self.graphics_view.setAccessibleName(f"{self.orientation.value} atlas slice")
        edge_description = ", ".join(
            f"{edge} {full_name}" for edge, (_, full_name) in anatomical_labels.items()
        )
        self.graphics_view.setAccessibleDescription(
            f"Interactive atlas image; anatomical edges: {edge_description}; "
            "click to move the linked crosshair, drag to pan, and use the wheel "
            "to change slices"
        )
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
            selected_region_ids=self._selected_region_ids,
            selected_color=self._selected_color,
        )
        displayed = self._current_frame.rgb
        binding = self._reference_density_binding
        if binding is not None:
            style = self._reference_density_style
            if style is None:  # pragma: no cover - guarded by the public setters
                raise RuntimeError("reference density binding has no heatmap style")
            density_plane = sample_reference_density_plane(
                binding,
                self.orientation,
                self.slice_index,
            )
            displayed = composite_reference_density_heatmap(displayed, density_plane, style)
        self._displayed_rgb = np.ascontiguousarray(displayed, dtype=np.uint8).copy()
        self._displayed_rgb.setflags(write=False)
        self.graphics_view.set_rgb_image(self._displayed_rgb)
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
