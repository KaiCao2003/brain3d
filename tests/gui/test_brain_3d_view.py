"""Failure-path tests for lazy 3D renderer ownership."""

from __future__ import annotations

from typing import ClassVar

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot
from tests.fixtures import make_allen_metadata_test_double

from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.gui.viewers import brain_3d_view as view_module
from mouse_brain_planner.gui.viewers.brain_3d_view import Brain3DView

pytestmark = pytest.mark.gui


class FakeInteractor:
    """Qt-backed interactor double with observable cleanup."""

    instances: ClassVar[list[FakeInteractor]] = []

    def __init__(self, parent: QWidget, *, off_screen: bool) -> None:
        del off_screen
        self.interactor = QWidget(parent)
        self.closed = False
        self.deleted = False
        self.instances.append(self)

    def setObjectName(self, name: str) -> None:  # noqa: N802 - Qt-compatible double
        self.interactor.setObjectName(name)

    def close(self) -> None:
        self.closed = True

    def deleteLater(self) -> None:  # noqa: N802 - Qt-compatible double
        self.deleted = True
        self.interactor.deleteLater()


class FailingScene:
    """Scene double that fails after allocation and records disposal."""

    instances: ClassVar[list[FailingScene]] = []

    def __init__(self, *args: object) -> None:
        self.plotter = args[0]
        self.disposed = False
        self.instances.append(self)

    def load_root_mesh(self, root_mesh: object) -> None:
        del root_mesh
        raise RuntimeError("synthetic second-stage renderer failure")

    def enable_physical_picking(self, callback: object) -> None:
        del callback

    def dispose(self) -> None:
        self.disposed = True
        self.plotter.close()  # type: ignore[attr-defined]


def test_load_failure_releases_partial_renderer_and_returns_to_empty_state(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeInteractor.instances.clear()
    FailingScene.instances.clear()
    monkeypatch.setattr(view_module, "QtInteractor", FakeInteractor)
    monkeypatch.setattr(view_module, "SceneController", FailingScene)
    metadata = make_allen_metadata_test_double(25)
    space = BrainGlobeAtlasSpace(metadata)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=100.0,
        dv_um=100.0,
        ml_um=100.0,
    )
    view = Brain3DView()
    qtbot.addWidget(view)

    with pytest.raises(RuntimeError, match="synthetic second-stage"):
        view.load_atlas(space, object(), anchor=anchor)

    assert view._scene is None
    assert view._plotter is None
    assert view._empty_label.isVisibleTo(view)
    assert FailingScene.instances[0].disposed is True
    assert FakeInteractor.instances[0].closed is True
    assert FakeInteractor.instances[0].deleted is True

    view.dispose()
