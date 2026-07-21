"""Main-window layout and project-state tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QDockWidget, QMessageBox, QTabWidget

import mouse_brain_planner.gui.main_window as main_window_module
from mouse_brain_planner.gui.main_window import SCIENTIFIC_WARNING, MainWindow

pytestmark = pytest.mark.gui


def test_main_window_exposes_required_phase_one_layout(qtbot: object) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.show()

    tabs = window.findChild(QTabWidget, "viewer-tabs")
    assert tabs is not None
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "3D Brain",
        "Coronal",
        "Sagittal",
        "Horizontal",
        "Four-panel",
    ]
    assert window.findChild(QDockWidget, "project-anatomy-dock") is not None
    assert window.findChild(QDockWidget, "inspector-dock") is not None
    assert window.statusBar().currentMessage() == SCIENTIFIC_WARNING


def test_main_window_save_and_reopen(qtbot: object, tmp_path: Path) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.project.title = "GUI round trip"
    path = tmp_path / "gui.mouseplan"

    window._save_to(path)
    window.new_project()
    window.open_project(path)

    assert window.project.title == "GUI round trip"
    assert window.project_path == path.resolve()


def test_new_project_cancel_preserves_dirty_state(
    qtbot: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=False)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.project.title = "Unsaved work"
    window._record_project_change("test-change")
    before = window.project.model_dump()
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    assert not window.new_project()
    assert window.project.model_dump() == before
    assert window._dirty

    window.suppress_dialogs = True
    window.close()


def test_new_project_discard_replaces_dirty_state(
    qtbot: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=False)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.project.title = "Unsaved work"
    window._record_project_change("test-change")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )

    assert window.new_project()
    assert window.project.title == "Untitled surgery plan"
    assert not window._dirty


def test_open_error_preserves_current_project(
    qtbot: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.project.title = "Keep me"
    window._record_project_change("test-change")
    before = window.project.model_dump()
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module,
        "load_project",
        lambda path: (_ for _ in ()).throw(OSError(f"cannot read {path}")),
    )
    monkeypatch.setattr(
        window,
        "_show_error",
        lambda title, message: errors.append((title, message)),
    )

    assert not window.open_project(tmp_path / "broken.mouseplan")
    assert window.project.model_dump() == before
    assert window.project_path is None
    assert window._dirty
    assert errors and "left unchanged" in errors[0][1]


def test_save_error_rolls_back_touch_path_and_dirty_state(
    qtbot: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.project.title = "Keep me"
    window._record_project_change("test-change")
    before = window.project.model_dump()
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module,
        "save_project",
        lambda project, path: (_ for _ in ()).throw(OSError(f"cannot write {path}")),
    )
    monkeypatch.setattr(
        window,
        "_show_error",
        lambda title, message: errors.append((title, message)),
    )

    assert not window._save_to(tmp_path / "broken.mouseplan")
    assert window.project.model_dump() == before
    assert window.project_path is None
    assert window._dirty
    assert errors and "left unchanged" in errors[0][1]


def test_close_cancel_keeps_window_open_and_invalidated_catalog_is_silent(
    qtbot: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=False)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.show()
    window._record_project_change("test-change")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    assert not window.close()
    assert window.isVisible()
    assert not window._closing

    shown: list[object] = []
    monkeypatch.setattr(window, "_show_atlas_selection", shown.append)
    token = window._catalog_token
    window._closing = True
    window._on_catalog_loaded([], token)
    assert shown == []

    critical_calls: list[object] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: critical_calls.append(args),
    )
    window._show_error("late failure", "must remain non-modal")
    assert critical_calls == []

    window.suppress_dialogs = True
    window._dirty = False
    window.close()
