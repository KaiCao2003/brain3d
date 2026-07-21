"""Atlas selection with explicit cache and memory information."""

from __future__ import annotations

import os
from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mouse_brain_planner.atlas.brainglobe_adapter import AtlasCatalogRecord

ALLEN_RAW_VOLUME_BYTES = {
    "allen_mouse_10um": 7_223_040_000,
    "allen_mouse_25um": 462_274_560,
}


def system_memory_bytes() -> int | None:
    """Return physical memory on macOS/POSIX when the platform exposes it."""

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        page_count = int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    memory = page_size * page_count
    return memory if memory > 0 else None


def format_bytes(value: int) -> str:
    """Format a byte count using explicit binary units."""

    if value < 0:
        raise ValueError("byte count must be non-negative")
    gibibytes = value / 1024**3
    if gibibytes >= 1:
        return f"{gibibytes:.2f} GiB"
    return f"{value / 1024**2:.1f} MiB"


class AtlasSelectionDialog(QDialog):
    """Select one catalog entry without obscuring download or RAM costs."""

    def __init__(
        self,
        records: Sequence[AtlasCatalogRecord],
        *,
        no_download: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("atlas-selection-dialog")
        self.setWindowTitle("Select BrainGlobe atlas")
        self.resize(760, 430)
        self._records = {record.name: record for record in records}
        self._no_download = no_download

        layout = QVBoxLayout(self)
        introduction = QLabel(
            "Atlas packages are opened through BrainGlobe AtlasAPI. "
            "Coordinates remain in the exact selected package and resolution.",
            self,
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        self.atlas_tree = QTreeWidget(self)
        self.atlas_tree.setObjectName("atlas-catalog")
        self.atlas_tree.setHeaderLabels(
            ["Atlas key", "Package version", "Cache", "Raw reference + annotation"]
        )
        self.atlas_tree.setRootIsDecorated(False)
        for record in records:
            raw_bytes = ALLEN_RAW_VOLUME_BYTES.get(record.name)
            raw_text = format_bytes(raw_bytes) if raw_bytes is not None else "not precomputed"
            item = QTreeWidgetItem(
                [
                    record.name,
                    record.latest_version,
                    "cached" if record.downloaded else "download required",
                    raw_text,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, record.name)
            if no_download and not record.downloaded:
                item.setDisabled(True)
                item.setToolTip(0, "Downloads are disabled for this session")
            self.atlas_tree.addTopLevelItem(item)
        self.atlas_tree.resizeColumnToContents(0)
        self.atlas_tree.resizeColumnToContents(1)
        self.atlas_tree.resizeColumnToContents(2)
        layout.addWidget(self.atlas_tree, 1)

        memory = system_memory_bytes()
        memory_text = "unknown" if memory is None else format_bytes(memory)
        self.memory_warning = QLabel(
            "Estimated raw volume memory excludes VTK meshes and application overhead. "
            f"System physical memory: {memory_text}. Allen 10 µm requires about "
            f"{format_bytes(ALLEN_RAW_VOLUME_BYTES['allen_mouse_10um'])} for its two raw "
            "arrays alone; 25 µm is the lower-memory option. No automatic downgrade occurs.",
            self,
        )
        self.memory_warning.setObjectName("atlas-memory-warning")
        self.memory_warning.setWordWrap(True)
        layout.addWidget(self.memory_warning)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.atlas_tree.itemSelectionChanged.connect(self._update_open_button)
        self.atlas_tree.itemDoubleClicked.connect(self._open_selected)

        preferred = self._find_enabled_item("allen_mouse_10um")
        if preferred is None:
            preferred = self._first_enabled_item()
        if preferred is not None:
            self.atlas_tree.setCurrentItem(preferred)
        self._update_open_button()

    @property
    def selected_record(self) -> AtlasCatalogRecord | None:
        """Return the selected enabled catalog record."""

        item = self.atlas_tree.currentItem()
        if item is None or item.isDisabled():
            return None
        name = item.data(0, Qt.ItemDataRole.UserRole)
        return self._records.get(str(name))

    def _find_enabled_item(self, atlas_name: str) -> QTreeWidgetItem | None:
        for index in range(self.atlas_tree.topLevelItemCount()):
            item = self.atlas_tree.topLevelItem(index)
            if item is None:
                continue
            if item.data(0, Qt.ItemDataRole.UserRole) == atlas_name and not item.isDisabled():
                return item
        return None

    def _first_enabled_item(self) -> QTreeWidgetItem | None:
        for index in range(self.atlas_tree.topLevelItemCount()):
            item = self.atlas_tree.topLevelItem(index)
            if item is None:
                continue
            if not item.isDisabled():
                return item
        return None

    def _update_open_button(self) -> None:
        button = self.buttons.button(QDialogButtonBox.StandardButton.Open)
        button.setEnabled(self.selected_record is not None)

    def _open_selected(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        if not item.isDisabled():
            self.accept()
