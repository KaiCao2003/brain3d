"""Native Qt canvas for exact dorsal-image raster landmark placement."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


@dataclass(frozen=True, slots=True)
class VascularCanvasMarker:
    """One landmark marker rendered over the stored raster."""

    column_px: float
    row_px: float
    label: str
    enabled: bool = True
    active: bool = False


class VascularImageCanvas(QWidget):
    """Aspect-fit an image and map logical Qt positions to stored samples.

    Qt paints widgets and reports pointer events in device-independent logical
    coordinates.  The canvas therefore uses one shared logical target rectangle
    for both operations and normalizes the image DPR to one: metadata such as an
    ``@2x`` filename can never reinterpret stored raster columns or rows.
    """

    raster_clicked = Signal(int, int)

    def __init__(self, image: QImage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if image.isNull() or image.width() <= 0 or image.height() <= 0:
            raise ValueError("vascular canvas requires a non-empty raster image")
        self._image = image.copy()
        self._image.setDevicePixelRatio(1.0)
        self._markers: tuple[VascularCanvasMarker, ...] = ()
        self.setObjectName("vascular-image-canvas")
        self.setAccessibleName("Subject dorsal vascular image")
        self.setAccessibleDescription(
            "Click the displayed image to set the active landmark pixel column and row"
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)

    @property
    def raster_size(self) -> QSize:
        """Return the underlying stored-sample dimensions, independent of DPR."""

        return self._image.size()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        """Prefer the raster aspect ratio without forcing a huge dialog."""

        width = min(max(self._image.width(), 640), 960)
        height = max(360, round(width * self._image.height() / self._image.width()))
        return QSize(width, min(height, 720))

    def image_target_rect(self) -> QRectF:
        """Return the exact logical-coordinate rectangle used for image painting."""

        available = QRectF(self.contentsRect()).adjusted(1.0, 1.0, -1.0, -1.0)
        if available.width() <= 0 or available.height() <= 0:
            return QRectF()
        scale = min(
            available.width() / self._image.width(),
            available.height() / self._image.height(),
        )
        width = self._image.width() * scale
        height = self._image.height() * scale
        return QRectF(
            available.left() + (available.width() - width) / 2.0,
            available.top() + (available.height() - height) / 2.0,
            width,
            height,
        )

    def widget_position_to_raster(self, position: QPointF) -> tuple[int, int] | None:
        """Map one logical widget position to an exact stored ``(column, row)``.

        The displayed image is treated as a grid of half-open pixel cells.  A
        position on the target's right or bottom border is outside the raster.
        """

        target = self.image_target_rect()
        if target.isEmpty():
            return None
        if not (
            target.left() <= position.x() < target.right()
            and target.top() <= position.y() < target.bottom()
        ):
            return None
        column = math.floor((position.x() - target.left()) * self._image.width() / target.width())
        row = math.floor((position.y() - target.top()) * self._image.height() / target.height())
        return (
            min(max(column, 0), self._image.width() - 1),
            min(max(row, 0), self._image.height() - 1),
        )

    def raster_sample_center(self, column_px: int, row_px: int) -> QPointF:
        """Return the logical display position at one stored sample's center."""

        if not 0 <= column_px < self._image.width():
            raise ValueError(f"column must be within [0, {self._image.width()})")
        if not 0 <= row_px < self._image.height():
            raise ValueError(f"row must be within [0, {self._image.height()})")
        target = self.image_target_rect()
        if target.isEmpty():
            raise ValueError("canvas has no drawable image rectangle")
        return QPointF(
            target.left() + (column_px + 0.5) * target.width() / self._image.width(),
            target.top() + (row_px + 0.5) * target.height() / self._image.height(),
        )

    def set_markers(self, markers: tuple[VascularCanvasMarker, ...]) -> None:
        """Replace the immutable marker snapshot and schedule a repaint."""

        self._markers = markers
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        """Paint the real raster and ordinary vector marker overlays."""

        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(26, 28, 32))
        target = self.image_target_rect()
        if target.isEmpty():
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(target, self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(225, 225, 225), 1.0))
        painter.drawRect(target)
        for index, marker in enumerate(self._markers, start=1):
            if not (
                math.isfinite(marker.column_px)
                and math.isfinite(marker.row_px)
                and 0 <= marker.column_px < self._image.width()
                and 0 <= marker.row_px < self._image.height()
            ):
                continue
            center = QPointF(
                target.left() + (marker.column_px + 0.5) * target.width() / self._image.width(),
                target.top() + (marker.row_px + 0.5) * target.height() / self._image.height(),
            )
            color = (
                QColor(255, 196, 42)
                if marker.active
                else QColor(0, 220, 255)
                if marker.enabled
                else QColor(170, 170, 170)
            )
            painter.setPen(QPen(color, 2.0))
            radius = 6.0 if marker.active else 5.0
            painter.drawEllipse(center, radius, radius)
            painter.drawLine(
                QPointF(center.x() - radius - 3.0, center.y()),
                QPointF(center.x() + radius + 3.0, center.y()),
            )
            painter.drawLine(
                QPointF(center.x(), center.y() - radius - 3.0),
                QPointF(center.x(), center.y() + radius + 3.0),
            )
            painter.drawText(QPointF(center.x() + 9.0, center.y() - 7.0), str(index))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        """Emit exact stored indices for primary-button clicks inside the image."""

        if event.button() is Qt.MouseButton.LeftButton:
            mapped = self.widget_position_to_raster(event.position())
            if mapped is not None:
                self.raster_clicked.emit(*mapped)
                event.accept()
                return
        super().mousePressEvent(event)
