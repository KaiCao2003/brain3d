"""Atlas selection with explicit cache and memory information."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from mouse_brain_planner.atlas.brainglobe_adapter import AtlasCatalogRecord

SUPPORTED_ATLAS_NAME = "allen_mouse_25um"
SUPPORTED_ATLAS_VERSION = "1.2"
SUPPORTED_ATLAS_RAW_VOLUME_BYTES = 462_274_560


def system_memory_bytes() -> int | None:
    """Return physical memory on macOS/POSIX when the platform exposes it."""

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        page_count = int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    memory = page_size * page_count
    return memory if memory > 0 else None


def system_available_memory_bytes() -> int | None:
    """Return a bounded best-effort estimate of memory currently available."""

    total = system_memory_bytes()
    if sys.platform == "darwin" and total is not None:
        try:
            result = subprocess.run(
                ["/usr/bin/memory_pressure", "-Q"],
                capture_output=True,
                check=False,
                text=True,
                timeout=1.0,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        else:
            match = re.search(
                r"System-wide memory free percentage:\s*([0-9]+(?:\.[0-9]+)?)%",
                result.stdout,
            )
            if result.returncode == 0 and match is not None:
                percentage = min(max(float(match.group(1)), 0.0), 100.0)
                return int(total * percentage / 100.0)

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    available = page_size * available_pages
    if available <= 0:
        return None
    return min(available, total) if total is not None else available


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
        self.resize(900, 500)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        supported_records = tuple(
            record
            for record in records
            if record.name == SUPPORTED_ATLAS_NAME
            and record.latest_version == SUPPORTED_ATLAS_VERSION
        )
        self._choice_record = supported_records[0] if supported_records else None
        self._accepted_record: AtlasCatalogRecord | None = None

        layout = QVBoxLayout(self)
        introduction = QLabel(
            f"Phase 1 opens only {SUPPORTED_ATLAS_NAME} v{SUPPORTED_ATLAS_VERSION} through "
            "BrainGlobe AtlasAPI. Coordinates remain in that exact package and 25 µm "
            "resolution.",
            self,
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        self.catalog_message = QLabel(self)
        self.catalog_message.setObjectName("atlas-catalog-empty-state")
        self.catalog_message.setWordWrap(True)
        if supported_records and (not no_download or any(r.downloaded for r in supported_records)):
            self.catalog_message.hide()
        elif no_download:
            self.catalog_message.setText(
                f"{SUPPORTED_ATLAS_NAME} v{SUPPORTED_ATLAS_VERSION} is not available in the "
                "local BrainGlobe cache. Downloads are disabled for this session; restart "
                "without --no-download to acquire this exact package."
            )
        else:
            self.catalog_message.setText(
                f"{SUPPORTED_ATLAS_NAME} v{SUPPORTED_ATLAS_VERSION} is not available from "
                "the BrainGlobe catalog. Check the network connection and try again."
            )
        layout.addWidget(self.catalog_message)

        # Phase 1 offers exactly one package.  Model/view widgets would expose one
        # accessible table cell per column, which enters Qt's crash-prone Cocoa
        # accessibilitySelectedChildren path when the dialog closes.  Use one
        # explicit non-item-view choice and ordinary labels instead.
        self.atlas_choice_panel = QWidget(self)
        self.atlas_choice_panel.setObjectName("atlas-choice-panel")
        choice_layout = QVBoxLayout(self.atlas_choice_panel)
        choice_layout.setContentsMargins(0, 0, 0, 0)
        self.atlas_choice = QRadioButton(
            f"Use {SUPPORTED_ATLAS_NAME} v{SUPPORTED_ATLAS_VERSION}",
            self.atlas_choice_panel,
        )
        self.atlas_choice.setObjectName("atlas-choice")
        self.atlas_choice.setAccessibleName("Allen mouse 25 micrometer atlas choice")
        choice_layout.addWidget(self.atlas_choice)

        details = QWidget(self.atlas_choice_panel)
        details.setObjectName("atlas-choice-details")
        details_layout = QFormLayout(details)
        details_layout.setContentsMargins(28, 0, 0, 0)
        record = self._choice_record
        self.atlas_key_value = QLabel(SUPPORTED_ATLAS_NAME, details)
        self.atlas_version_value = QLabel(SUPPORTED_ATLAS_VERSION, details)
        self.atlas_cache_value = QLabel(
            "cached" if record is not None and record.downloaded else "download required",
            details,
        )
        self.atlas_raw_size_value = QLabel(
            format_bytes(SUPPORTED_ATLAS_RAW_VOLUME_BYTES),
            details,
        )
        self.atlas_key_value.setAccessibleName("Atlas key")
        self.atlas_version_value.setAccessibleName("Atlas package version")
        self.atlas_cache_value.setAccessibleName("Atlas cache status")
        self.atlas_raw_size_value.setAccessibleName("Raw reference and annotation size")
        details_layout.addRow("Atlas key", self.atlas_key_value)
        details_layout.addRow("Package version", self.atlas_version_value)
        details_layout.addRow("Cache", self.atlas_cache_value)
        details_layout.addRow("Raw reference + annotation", self.atlas_raw_size_value)
        choice_layout.addWidget(details)

        choice_available = record is not None and (not no_download or record.downloaded)
        self.atlas_choice.setEnabled(choice_available)
        if record is not None and no_download and not record.downloaded:
            self.atlas_choice.setToolTip("Downloads are disabled for this session")
            details.setToolTip("Downloads are disabled for this session")
        self.atlas_choice_panel.setVisible(record is not None)
        layout.addWidget(self.atlas_choice_panel, 1)

        self._physical_memory_bytes = system_memory_bytes()
        self._available_memory_bytes = system_available_memory_bytes()
        self.memory_warning = QLabel(self)
        self.memory_warning.setObjectName("atlas-memory-warning")
        self.memory_warning.setAccessibleName("Atlas memory preflight")
        self.memory_warning.setWordWrap(True)
        layout.addWidget(self.memory_warning)

        self.download_context = QLabel(self)
        self.download_context.setObjectName("atlas-download-context")
        self.download_context.setAccessibleName("Atlas download source, citation, and terms")
        self.download_context.setTextFormat(Qt.TextFormat.RichText)
        self.download_context.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self.download_context.setOpenExternalLinks(True)
        self.download_context.setWordWrap(True)
        self.download_context.hide()
        layout.addWidget(self.download_context)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.atlas_choice.toggled.connect(self._update_open_button)
        # Requiring an explicit opt-in is safer for a multi-gigabyte download and
        # ensures merely opening the catalog can never start atlas acquisition.
        self._update_open_button()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt override
        """Keep the single catalog choice explicit whenever the dialog is shown."""

        self._accepted_record = None
        super().showEvent(event)
        self._clear_explicit_choice()
        QTimer.singleShot(0, self._clear_explicit_choice)

    def _clear_explicit_choice(self) -> None:
        self.atlas_choice.setChecked(False)
        self._update_open_button()

    def retire_accessibility_selection(self) -> None:
        """Reset the explicit choice before a native parent-window transition."""

        self._clear_explicit_choice()

    @property
    def selected_record(self) -> AtlasCatalogRecord | None:
        """Return the explicitly chosen enabled catalog record."""

        if not self.atlas_choice.isChecked() or not self.atlas_choice.isEnabled():
            return None
        return self._choice_record

    @property
    def accepted_record(self) -> AtlasCatalogRecord | None:
        """Return the choice committed before the native dialog was hidden."""

        return self._accepted_record

    def accept(self) -> None:
        """Commit and reset the explicit choice before the native dialog hides."""

        record = self.selected_record
        if record is None:
            return
        self._accepted_record = record
        # Preserve the committed record separately, then remove even the radio
        # button's checked state before AppKit observes the native window hiding.
        self.retire_accessibility_selection()
        super().accept()

    def reject(self) -> None:
        """Reset the explicit choice before cancelling or closing the dialog."""

        self._accepted_record = None
        self.retire_accessibility_selection()
        super().reject()

    def _update_open_button(self, *_args: object) -> None:
        button = self.buttons.button(QDialogButtonBox.StandardButton.Open)
        record = self.selected_record
        button.setEnabled(record is not None)
        self._update_memory_warning(record)
        self._update_download_context(record)

    def _update_memory_warning(self, record: AtlasCatalogRecord | None) -> None:
        physical = (
            "unknown"
            if self._physical_memory_bytes is None
            else format_bytes(self._physical_memory_bytes)
        )
        available = (
            "unknown"
            if self._available_memory_bytes is None
            else format_bytes(self._available_memory_bytes)
        )
        details = [
            f"Phase 1 supports only {SUPPORTED_ATLAS_NAME} v{SUPPORTED_ATLAS_VERSION}.",
            "Its raw reference and annotation arrays require about "
            f"{format_bytes(SUPPORTED_ATLAS_RAW_VOLUME_BYTES)}; this estimate excludes VTK "
            "meshes and application overhead.",
            f"System physical memory: {physical}; currently available estimate: {available}.",
            "No resolution fallback or automatic atlas substitution occurs.",
        ]
        if record is not None:
            details.append(f"Selected exact package: {record.name} v{record.latest_version}.")
        if (
            self._available_memory_bytes is not None
            and SUPPORTED_ATLAS_RAW_VOLUME_BYTES > self._available_memory_bytes
        ):
            deficit = SUPPORTED_ATLAS_RAW_VOLUME_BYTES - self._available_memory_bytes
            details.append(
                "WARNING: the required raw arrays exceed the currently available memory "
                f"estimate by about {format_bytes(deficit)}; opening may fail or cause "
                "severe memory pressure."
            )
        self.memory_warning.setText(" ".join(details))

    def _update_download_context(self, record: AtlasCatalogRecord | None) -> None:
        if record is None or record.downloaded:
            self.download_context.hide()
            self.download_context.clear()
            return
        self.download_context.setText(
            f"Opening <b>{record.name} v{record.latest_version}</b> will download an exact "
            "BrainGlobe package. Review the "
            '<a href="https://gin.g-node.org/brainglobe/atlases">BrainGlobe GIN source</a>, '
            '<a href="https://doi.org/10.1016/j.cell.2020.04.007">Allen CCFv3 citation</a>, '
            '<a href="https://alleninstitute.org/legal/citation-policy">citation policy</a>, '
            'and <a href="https://alleninstitute.org/legal/terms-of-use">license/terms of use</a>. '
            "The application grants no additional data rights."
        )
        self.download_context.show()
