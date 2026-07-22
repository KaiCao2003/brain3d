"""Regression tests for repository construction outside the GUI thread."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event, get_ident

import pytest
from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot

import mouse_brain_planner.gui.main_window as main_window_module
from mouse_brain_planner.atlas.brainglobe_adapter import AtlasCatalogRecord, LoadedAtlas
from mouse_brain_planner.gui.main_window import MainWindow

pytestmark = pytest.mark.gui


class _Repository:
    """Small repository double whose load path stops after factory resolution."""

    def list_atlases(
        self,
        *,
        local_only: bool = False,
        cancel: Callable[[], bool] | None = None,
    ) -> list[AtlasCatalogRecord]:
        del local_only, cancel
        return []

    def is_cached(self, atlas_name: str, package_version: str | None = None) -> bool:
        del atlas_name, package_version
        return False

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> LoadedAtlas:
        del atlas_name, package_version, allow_download, progress, cancel
        raise RuntimeError("synthetic stop after repository construction")


def _release_factory_from_gui(
    factory_entered: Event,
    release_factory: Event,
    heartbeat_threads: list[int],
) -> QTimer:
    """Release a blocked factory only after a GUI event-loop heartbeat."""

    timer = QTimer()
    timer.setInterval(1)

    def heartbeat() -> None:
        if factory_entered.is_set():
            heartbeat_threads.append(get_ident())
            release_factory.set()
            timer.stop()

    timer.timeout.connect(heartbeat)
    timer.start()
    return timer


def test_select_atlas_constructs_production_repository_on_worker_thread(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gui_thread = get_ident()
    factory_entered = Event()
    release_factory = Event()
    factory_threads: list[int] = []
    heartbeat_threads: list[int] = []

    def repository_factory() -> _Repository:
        factory_threads.append(get_ident())
        factory_entered.set()
        if not release_factory.wait(timeout=1.0):
            raise RuntimeError("GUI event loop did not release repository factory")
        return _Repository()

    monkeypatch.setattr(main_window_module, "BrainGlobeAtlasRepository", repository_factory)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_show_atlas_selection", lambda records: None)
    timer = _release_factory_from_gui(factory_entered, release_factory, heartbeat_threads)

    window.select_atlas()

    qtbot.waitUntil(lambda: not window._active_threads, timeout=2000)
    timer.stop()
    assert factory_threads and all(thread != gui_thread for thread in factory_threads)
    assert heartbeat_threads == [gui_thread]


def test_begin_atlas_load_constructs_production_repository_on_worker_thread(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gui_thread = get_ident()
    factory_entered = Event()
    release_factory = Event()
    factory_threads: list[int] = []
    heartbeat_threads: list[int] = []

    def repository_factory() -> _Repository:
        factory_threads.append(get_ident())
        factory_entered.set()
        if not release_factory.wait(timeout=1.0):
            raise RuntimeError("GUI event loop did not release repository factory")
        return _Repository()

    monkeypatch.setattr(main_window_module, "BrainGlobeAtlasRepository", repository_factory)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    timer = _release_factory_from_gui(factory_entered, release_factory, heartbeat_threads)

    window._begin_atlas_load("allen_mouse_25um")

    qtbot.waitUntil(lambda: not window._active_threads, timeout=2000)
    timer.stop()
    assert factory_threads and all(thread != gui_thread for thread in factory_threads)
    assert heartbeat_threads == [gui_thread]
    assert window.rendering_status.text() == "Rendering: atlas load failed"
