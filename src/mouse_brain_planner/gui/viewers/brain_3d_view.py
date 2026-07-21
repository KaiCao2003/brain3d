"""Lazy PyVistaQt 3D atlas viewer."""

from __future__ import annotations

import logging
import os
from typing import cast, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.rendering.scene_controller import (
    MeshSource,
    PlotterProtocol,
    SceneController,
)

logger = logging.getLogger(__name__)


class Brain3DView(QWidget):
    """3D view that creates VTK resources only after an atlas is selected."""

    physical_point_picked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("brain-3d-view")
        self._layout = QVBoxLayout(self)
        self._empty_label = QLabel("No atlas loaded", self)
        self._empty_label.setObjectName("brain-3d-empty-state")
        self._empty_label.setStyleSheet("color: palette(mid);")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._empty_label)
        self._plotter: QtInteractor | None = None
        self._scene: SceneController | None = None

    def load_atlas(
        self,
        space: BrainGlobeAtlasSpace,
        root_mesh: MeshSource,
        *,
        anchor: BrainGlobePhysicalPoint,
    ) -> None:
        """Create the embedded renderer and show real atlas geometry."""

        self.dispose()
        self._empty_label.hide()
        try:
            off_screen = os.environ.get("PYVISTA_OFF_SCREEN", "").lower() in {
                "1",
                "true",
                "yes",
            }
            self._plotter = QtInteractor(self, off_screen=off_screen)
            self._plotter.setObjectName("pyvista-interactor")
            self._layout.addWidget(self._plotter.interactor, 1)
            self._scene = SceneController(cast(PlotterProtocol, self._plotter), space, anchor)
            self._scene.load_root_mesh(root_mesh)
            self._scene.enable_physical_picking(self.physical_point_picked.emit)
        except Exception:
            self.dispose()
            raise

    def set_crosshair(self, point: BrainGlobePhysicalPoint) -> None:
        """Move the 3D crosshair if an atlas is active."""

        if self._scene is not None:
            self._scene.set_crosshair(point)

    def set_region(
        self,
        structure_id: int,
        source: MeshSource,
        *,
        rgb: tuple[int, int, int],
        opacity: float,
        visible: bool,
    ) -> None:
        """Update one region actor."""

        if self._scene is not None:
            self._scene.set_region(
                structure_id,
                source,
                rgb=rgb,
                opacity=opacity,
                visible=visible,
            )

    def reset_camera(self) -> None:
        """Reset the active 3D camera."""

        if self._scene is not None:
            self._scene.reset_camera()

    def set_camera(self, preset: str) -> None:
        """Apply an anatomical camera preset."""

        if self._scene is not None:
            self._scene.set_camera(preset)

    def dispose(self) -> None:
        """Release any active VTK renderer and return to empty state."""

        scene = self._scene
        plotter = self._plotter
        self._scene = None
        self._plotter = None
        scene_disposed = False
        if scene is not None:
            try:
                scene.dispose()
                scene_disposed = True
            except Exception:
                logger.exception("failed to dispose the 3D scene")
        if plotter is not None:
            try:
                self._layout.removeWidget(plotter.interactor)
                if not scene_disposed:
                    plotter.close()
            except Exception:
                logger.exception("failed to close the embedded 3D plotter")
            finally:
                plotter.deleteLater()
        self._empty_label.show()

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """Dispose native resources before Qt destroys the widget."""

        self.dispose()
        super().closeEvent(event)
