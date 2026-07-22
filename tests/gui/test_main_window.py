"""Main-window layout and project-state tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible, QAccessibleInterface
from PySide6.QtWidgets import QDockWidget, QMessageBox, QWidget
from pytestqt.qtbot import QtBot

import mouse_brain_planner.gui.main_window as main_window_module
from mouse_brain_planner.gui.main_window import SCIENTIFIC_WARNING, MainWindow
from mouse_brain_planner.gui.viewers.stable_view_switcher import StableViewSwitcher

pytestmark = pytest.mark.gui


def test_main_window_exposes_required_phase_one_layout(qtbot: object) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.show()

    tabs = window.findChild(StableViewSwitcher, "viewer-tabs")
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
    assert "Mouse animal-research" in window.scientific_warning.text()
    assert "never human or clinical use" in window.scientific_warning.text()
    assert "before every surgery" in window.scientific_warning.text()
    assert not window.reset_camera_action.isEnabled()
    assert not window.center_action.isEnabled()
    assert all(not action.isEnabled() for action in window.camera_preset_actions)


def _accessible_descendants(root: QAccessibleInterface) -> list[QAccessibleInterface]:
    descendants: list[QAccessibleInterface] = []
    pending = [root]
    while pending:
        interface = pending.pop()
        descendants.append(interface)
        for index in range(interface.childCount()):
            child = interface.child(index)
            if child is not None:
                pending.append(child)
    return descendants


def test_view_switcher_changes_exact_pages_by_button_keyboard_and_shortcut(
    qtbot: QtBot,
) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()

    switcher = window.viewer_tabs
    expected_pages = [
        window.brain_3d_view,
        window._slice_pages[main_window_module.SliceOrientation.CORONAL],
        window._slice_pages[main_window_module.SliceOrientation.SAGITTAL],
        window._slice_pages[main_window_module.SliceOrientation.HORIZONTAL],
        window.four_panel_page,
    ]
    buttons = switcher.view_buttons

    assert [switcher.widget(index) for index in range(switcher.count())] == expected_pages
    assert switcher.currentIndex() == 0
    assert [button.isChecked() for button in buttons] == [True, False, False, False, False]

    for index, button in enumerate(buttons):
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert switcher.currentIndex() == index
        assert switcher.currentWidget() is expected_pages[index]
        assert [candidate.isChecked() for candidate in buttons] == [
            candidate_index == index for candidate_index in range(len(buttons))
        ]

    buttons[0].setFocus()
    qtbot.keyClick(buttons[0], Qt.Key.Key_Right)
    qtbot.wait(1)
    assert switcher.currentIndex() == 1
    assert buttons[1].hasFocus()
    assert sum(button.isChecked() for button in buttons) == 1

    shortcut_keys = (
        Qt.Key.Key_1,
        Qt.Key.Key_2,
        Qt.Key.Key_3,
        Qt.Key.Key_4,
        Qt.Key.Key_5,
    )
    for index, key in enumerate(shortcut_keys):
        qtbot.keyClick(window, key)
        assert switcher.currentIndex() == index
        assert switcher.currentWidget() is expected_pages[index]
        assert sum(button.isChecked() for button in buttons) == 1


def test_view_switcher_accessibility_has_no_tab_or_selection_interface(qtbot: QtBot) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window.show()

    accessible = QAccessible.queryAccessibleInterface(window.viewer_tabs)
    interfaces = _accessible_descendants(accessible)
    forbidden_roles = {QAccessible.Role.PageTabList, QAccessible.Role.PageTab}

    assert not any(interface.role() in forbidden_roles for interface in interfaces)
    assert all(interface.selectionInterface() is None for interface in interfaces)
    assert all(
        interface.interface_cast(QAccessible.InterfaceType.SelectionInterface) is None
        for interface in interfaces
    )


def test_warning_is_not_user_hideable_and_state_replacement_restores_it(qtbot: QtBot) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window.show()

    assert not window.warning_toolbar.toggleViewAction().isEnabled()
    window.warning_toolbar.hide()
    assert not window.warning_toolbar.isVisibleTo(window)

    assert window.new_project()
    assert window.warning_toolbar.isVisibleTo(window)
    assert window.scientific_warning.isVisibleTo(window)


def test_status_fields_reserve_message_space_and_expose_exact_elided_values(
    qtbot: QtBot,
) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window.resize(1440, 720)
    window.show()
    qtbot.wait(1)

    assert window.atlas_status.geometry().x() >= 240
    full_value = "Region: CA1 — a deliberately long exact atlas region label for accessibility"
    window.region_status.setText(full_value)
    qtbot.wait(1)

    assert window.region_status.text() == full_value
    assert window.region_status.toolTip() == full_value
    assert window.region_status.accessibleDescription() == full_value
    assert "…" in window.region_status.displayed_text()


def test_main_window_has_compact_inspector_and_persistent_project_dock(
    qtbot: QtBot,
) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window.resize(1024, 720)
    window.show()
    qtbot.wait(1)

    assert window.minimumSizeHint().width() <= 1024
    assert window.inspector_dock.minimumSizeHint().width() < 360
    assert window.findChild(QWidget, "project-sections") is None
    accessible_names = {
        window.region_search.accessibleName(),
        window.region_tree.accessibleName(),
        window.inspector_coordinate.accessibleName(),
        window.region_opacity.accessibleName(),
        window.region_color.accessibleName(),
        window.reset_region_color.accessibleName(),
    }
    assert "" not in accessible_names
    assert len(accessible_names) == 6

    project_features = window.project_dock.features()
    assert project_features & QDockWidget.DockWidgetFeature.DockWidgetMovable
    assert not project_features & QDockWidget.DockWidgetFeature.DockWidgetClosable
    assert not project_features & QDockWidget.DockWidgetFeature.DockWidgetFloatable
    assert not window.project_dock_action.isEnabled()
    assert not window.project_dock_action.isVisible()
    assert window.inspector_dock_action.isCheckable()

    # Even a programmatic/native state perturbation is repaired before the
    # user is returned to an atlas workflow.
    window.project_dock.setFloating(True)
    window.project_dock.hide()
    window._ensure_project_dock_visible()
    assert not window.project_dock.isFloating()
    assert window.dockWidgetArea(window.project_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.project_dock.isVisibleTo(window)


def test_main_window_save_and_reopen(qtbot: object, tmp_path: Path) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.project.title = "GUI round trip"
    path = tmp_path / "gui.mouseplan"

    window._save_to(path)
    window.new_project()
    window.warning_toolbar.hide()
    window.open_project(path)

    assert window.project.title == "GUI round trip"
    assert window.project_path == path.resolve()
    assert not window.warning_toolbar.isHidden()


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
        "load_project_with_provenance",
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


def test_backup_recovery_has_no_writable_path_and_requires_save_as(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    writer = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(writer)
    path = tmp_path / "recover.mouseplan"
    writer.project.title = "Known good backup"
    assert writer._save_to(path)
    writer.project.title = "Primary to corrupt"
    assert writer._save_to(path)
    (path / "project.json").write_text("{}", encoding="utf-8")

    reader = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(reader)
    assert reader.open_project(path)
    backup = path.with_name(f"{path.name}.bak")

    assert reader.project.title == "Known good backup"
    assert reader.project_path is None
    assert reader._project_source_path == backup
    assert str(backup) in reader.statusBar().currentMessage()
    assert "Save As is required" in reader.statusBar().currentMessage()
    assert "backup; Save As required" in reader.windowTitle()


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
