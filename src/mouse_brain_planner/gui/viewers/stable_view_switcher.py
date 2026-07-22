"""Accessibility-stable switching between the planner's central views."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QEvent, QObject, Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class StableViewSwitcher(QWidget):
    """A fixed button header over pages, without Qt's tab accessibility API.

    ``QTabBar`` exposes a native selection interface on macOS. Accessibility
    clients can retain wrappers for its selected tab while an atlas transition
    updates the rest of the window, so the planner uses ordinary buttons and a
    stack instead. Pages and header buttons are append-only for the lifetime of
    this widget.
    """

    currentChanged = Signal(int)  # noqa: N815 - QTabWidget-compatible signal

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Brain atlas views")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(8)

        self.header = QWidget(self)
        self.header.setObjectName("viewer-switcher-header")
        self.header.setAccessibleName("View selector")
        self._header_layout = QHBoxLayout(self.header)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(4)
        outer_layout.addWidget(self.header)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName("viewer-stack")
        self.stack.setAccessibleName("Selected brain atlas view")
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer_layout.addWidget(self.stack, 1)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._button_group.idClicked.connect(self.setCurrentIndex)
        self._buttons: list[QPushButton] = []
        self._labels: list[str] = []
        self.stack.currentChanged.connect(self._on_stack_changed)

        # A restrained segmented-control treatment makes the active view
        # unambiguous while retaining native focus and keyboard behavior.
        self.header.setStyleSheet(
            """
            QPushButton[viewSwitcherButton="true"] {
                border: 1px solid transparent;
                border-radius: 7px;
                padding: 5px 10px;
            }
            QPushButton[viewSwitcherButton="true"]:hover {
                background-color: palette(midlight);
            }
            QPushButton[viewSwitcherButton="true"]:checked {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
            QPushButton[viewSwitcherButton="true"]:focus {
                border-color: palette(highlight);
            }
            """
        )

    @property
    def view_buttons(self) -> tuple[QPushButton, ...]:
        """Return the stable header buttons in page order."""

        return tuple(self._buttons)

    def addTab(self, widget: QWidget, label: str) -> int:  # noqa: N802 - QTabWidget API
        """Append one permanent page and its ordinary checkable button."""

        page_index = self.stack.count()
        button = QPushButton(label, self.header)
        button.setObjectName(f"viewer-switch-{page_index}")
        button.setAccessibleName(f"Show {label} view")
        button.setAccessibleDescription(
            f"Select the {label} mouse brain atlas view; shortcut {page_index + 1}"
        )
        button.setProperty("viewSwitcherButton", True)
        button.setCheckable(True)
        button.setAutoDefault(False)
        button.setDefault(False)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.installEventFilter(self)

        self._buttons.append(button)
        self._labels.append(label)
        self._button_group.addButton(button, page_index)
        self._header_layout.addWidget(button, 1)

        actual_index = self.stack.addWidget(widget)
        if actual_index != page_index:
            raise RuntimeError("view stack appended a page at an unexpected index")
        if page_index == 0:
            button.setChecked(True)
        return page_index

    def count(self) -> int:
        """Return the number of permanent view pages."""

        return self.stack.count()

    def widget(self, index: int) -> QWidget | None:
        """Return the page at ``index``, or ``None`` for an invalid index."""

        if 0 <= index < self.count():
            return self.stack.widget(index)
        return None

    def tabText(self, index: int) -> str:  # noqa: N802 - QTabWidget API
        """Return the label at ``index``, or an empty string when invalid."""

        if 0 <= index < len(self._labels):
            return self._labels[index]
        return ""

    def currentIndex(self) -> int:  # noqa: N802 - QTabWidget API
        """Return the visible page index."""

        return self.stack.currentIndex()

    def currentWidget(self) -> QWidget | None:  # noqa: N802 - QTabWidget API
        """Return the visible page widget."""

        return self.stack.currentWidget()

    @Slot(int)
    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 - QTabWidget API
        """Select one valid page while keeping exactly one button checked."""

        if not 0 <= index < self.count():
            return
        if index == self.stack.currentIndex():
            self._buttons[index].setChecked(True)
            return
        self.stack.setCurrentIndex(index)

    def setCurrentWidget(self, widget: QWidget) -> None:  # noqa: N802 - QTabWidget API
        """Select ``widget`` when it is one of this switcher's pages."""

        index = self.stack.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Move between adjacent views with arrow, Home, and End keys."""

        if (
            watched in self._buttons
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
        ):
            target: int | None = None
            current = self._buttons.index(watched)
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                target = (current - 1) % len(self._buttons)
            elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                target = (current + 1) % len(self._buttons)
            elif event.key() == Qt.Key.Key_Home:
                target = 0
            elif event.key() == Qt.Key.Key_End:
                target = len(self._buttons) - 1
            if target is not None:
                self.setCurrentIndex(target)
                self._buttons[target].setFocus(Qt.FocusReason.ShortcutFocusReason)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    @Slot(int)
    def _on_stack_changed(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
        self.currentChanged.emit(index)
