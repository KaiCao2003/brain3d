"""Native application shell and Phase 1 scientific-viewer coordination."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import override

import pyvista as pv
from PySide6.QtCore import (
    QModelIndex,
    QObject,
    QSettings,
    QSignalBlocker,
    Qt,
    QThread,
    QTimer,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QIcon,
    QKeySequence,
    QPixmap,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mouse_brain_planner.atlas.brainglobe_adapter import (
    AtlasCatalogRecord,
    BrainGlobeAtlasRepository,
    LoadedAtlas,
)
from mouse_brain_planner.coordinates.atlas_space import (
    BrainGlobeAtlasSpace,
    CoordinateBoundsError,
)
from mouse_brain_planner.domain.atlas_models import AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import (
    BrainGlobePhysicalPoint,
    BrainGlobeVoxelIndex,
)
from mouse_brain_planner.domain.project_models import PlannerProject, RegionDisplayState
from mouse_brain_planner.gui.dialogs.atlas_selection import AtlasSelectionDialog
from mouse_brain_planner.gui.viewers.brain_3d_view import Brain3DView
from mouse_brain_planner.gui.viewers.orthogonal_view import OrthogonalSliceView
from mouse_brain_planner.gui.workers.atlas_worker import (
    AtlasCatalogWorker,
    AtlasLoadWorker,
    AtlasRepositoryProtocol,
    LoadedAtlasPayload,
    RegionMeshPayload,
    RegionMeshWorker,
)
from mouse_brain_planner.persistence.project_io import load_project, save_project
from mouse_brain_planner.rendering.slice_renderer import SliceOrientation, SliceRenderer

SCIENTIFIC_WARNING = (
    "Research planning tool — atlas coordinates are population-reference values "
    "and must be independently verified before surgery."
)

# Common experimental shorthand that differs from Allen's official acronyms.
# These terms affect search only; IDs, labels, hierarchy, and geometry still
# come exclusively from the loaded atlas.
REGION_SEARCH_ALIASES: dict[str, frozenset[str]] = {
    "ADN": frozenset({"AD"}),
    "RSC": frozenset({"RSP"}),
    "MEC": frozenset({"ENTm"}),
}

logger = logging.getLogger(__name__)


class _WorkerRelay(QObject):
    """Queue Python callbacks onto the GUI thread through QObject affinity."""

    def __init__(
        self,
        *,
        on_success: Callable[..., None],
        on_failure: Callable[..., None],
        on_cancelled: Callable[[str], None] | None,
        on_progress: Callable[[int, int], None] | None,
        parent: QObject,
    ) -> None:
        super().__init__(parent)
        self._on_success = on_success
        self._on_failure = on_failure
        self._on_cancelled = on_cancelled
        self._on_progress = on_progress

    @Slot(object)
    def success(self, payload: object) -> None:
        """Deliver one worker payload in the GUI thread."""

        self._on_success(payload)

    @Slot(str)
    def failure(self, message: str) -> None:
        """Deliver a one-argument failure in the GUI thread."""

        self._on_failure(message)

    @Slot(int, str)
    def indexed_failure(self, index: int, message: str) -> None:
        """Deliver a structure-specific failure in the GUI thread."""

        self._on_failure(index, message)

    @Slot(str)
    def cancelled(self, message: str) -> None:
        """Deliver cancellation in the GUI thread."""

        if self._on_cancelled is not None:
            self._on_cancelled(message)

    @Slot(int, int)
    def progress(self, completed: int, total: int) -> None:
        """Deliver progress in the GUI thread for the owning request only."""

        if self._on_progress is not None:
            self._on_progress(completed, total)


class MainWindow(QMainWindow):
    """Phase 1 main window with linked 2D/3D atlas navigation."""

    def __init__(
        self,
        *,
        no_download: bool = False,
        suppress_dialogs: bool = False,
        repository: AtlasRepositoryProtocol | None = None,
    ) -> None:
        super().__init__()
        self.no_download = no_download
        self.suppress_dialogs = suppress_dialogs
        self.project = PlannerProject()
        self.project_path: Path | None = None
        self._repository_instance = repository
        self._catalog_records: list[AtlasCatalogRecord] | None = None
        self._loaded_atlas: LoadedAtlas | None = None
        self._atlas_space: BrainGlobeAtlasSpace | None = None
        self._slice_renderer: SliceRenderer | None = None
        self._slice_views: list[OrthogonalSliceView] = []
        self._brain_views: list[Brain3DView] = []
        self._four_panel_brain: Brain3DView | None = None
        self._region_by_id: dict[int, RegionRecord] = {}
        self._region_items: dict[int, QTreeWidgetItem] = {}
        self._region_meshes: dict[int, pv.DataSet] = {}
        self._region_meshes_loading: set[int] = set()
        self._updating_region_tree = False
        self._updating_inspector = False
        self._active_threads: set[QThread] = set()
        self._worker_refs: dict[QThread, tuple[object, _WorkerRelay]] = {}
        self._load_worker: AtlasLoadWorker | None = None
        self._load_progress: QProgressDialog | None = None
        self._load_token = 0
        self._catalog_token = 0
        self._expected_atlas: AtlasMetadata | None = None
        self._close_pending = False
        self._closing = False
        self._dirty = False

        self.setObjectName("main-window")
        self.setWindowTitle("Mouse Brain Surgery Planner")
        self.resize(1440, 920)

        self._build_central_viewers()
        self._build_project_dock()
        self._build_inspector_dock()
        self._build_actions()
        self._build_status_bar()
        self._update_project_ui()

    def _build_central_viewers(self) -> None:
        self.viewer_tabs = QTabWidget(self)
        self.viewer_tabs.setObjectName("viewer-tabs")

        self.brain_3d_view = Brain3DView(self.viewer_tabs)
        self.brain_3d_view.setObjectName("viewer-3d")
        self.brain_3d_view.physical_point_picked.connect(self._on_physical_cursor_picked)
        self.viewer_tabs.addTab(self.brain_3d_view, "3D Brain")
        self._brain_views = [self.brain_3d_view]

        self._slice_pages: dict[SliceOrientation, QWidget] = {}
        self._slice_layouts: dict[SliceOrientation, QVBoxLayout] = {}
        for orientation, title in (
            (SliceOrientation.CORONAL, "Coronal"),
            (SliceOrientation.SAGITTAL, "Sagittal"),
            (SliceOrientation.HORIZONTAL, "Horizontal"),
        ):
            page = QWidget(self.viewer_tabs)
            page.setObjectName(f"viewer-{orientation.value}")
            layout = QVBoxLayout(page)
            self._add_empty_label(layout, f"viewer-{orientation.value}-empty-state")
            self._slice_pages[orientation] = page
            self._slice_layouts[orientation] = layout
            self.viewer_tabs.addTab(page, title)

        self.four_panel_page = QWidget(self.viewer_tabs)
        self.four_panel_page.setObjectName("viewer-four-panel")
        self._four_panel_layout = QGridLayout(self.four_panel_page)
        self._add_four_panel_empty_state()
        self.viewer_tabs.addTab(self.four_panel_page, "Four-panel")
        self.setCentralWidget(self.viewer_tabs)

    @staticmethod
    def _add_empty_label(layout: QVBoxLayout, object_name: str) -> None:
        message = QLabel("No atlas loaded")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setObjectName(object_name)
        layout.addWidget(message)

    def _add_four_panel_empty_state(self) -> None:
        message = QLabel("No atlas loaded", self.four_panel_page)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setObjectName("viewer-four-panel-empty-state")
        self._four_panel_layout.addWidget(message, 0, 0)

    def _build_project_dock(self) -> None:
        dock = QDockWidget("Project and anatomy", self)
        dock.setObjectName("project-anatomy-dock")
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        container = QWidget(dock)
        layout = QVBoxLayout(container)

        self.project_sections = QListWidget(container)
        self.project_sections.setObjectName("project-sections")
        self.project_sections.addItems(
            [
                "Project",
                "Atlas",
                "Brain regions",
                "Vasculature",
                "Skull landmarks",
                "Implants",
                "Measurements",
                "Exports",
            ]
        )
        layout.addWidget(self.project_sections)

        self.region_search = QLineEdit(container)
        self.region_search.setObjectName("region-search")
        self.region_search.setPlaceholderText("Search acronym, name, or structure ID…")
        self.region_search.textChanged.connect(self._filter_regions)
        layout.addWidget(self.region_search)

        self.region_tree = QTreeWidget(container)
        self.region_tree.setObjectName("region-tree")
        self.region_tree.setHeaderLabels(["Region", "Full name", "ID"])
        self.region_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.region_tree.itemChanged.connect(self._on_region_item_changed)
        self.region_tree.itemSelectionChanged.connect(self._on_region_selection_changed)
        self._show_no_atlas_region_item()
        layout.addWidget(self.region_tree, 1)

        dock.setWidget(container)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.project_dock = dock

    def _build_inspector_dock(self) -> None:
        dock = QDockWidget("Inspector", self)
        dock.setObjectName("inspector-dock")
        container = QWidget(dock)
        form = QFormLayout(container)
        self.inspector_type = QLabel("Nothing selected", container)
        self.inspector_atlas = QLabel("None", container)
        self.inspector_atlas.setWordWrap(True)
        self.inspector_coordinate = QLabel("—", container)
        self.inspector_coordinate.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.inspector_convention = QLabel(self.project.coordinate_convention, container)
        self.inspector_convention.setWordWrap(True)
        self.inspector_atlas_details = QLabel("No atlas loaded", container)
        self.inspector_atlas_details.setWordWrap(True)
        self.inspector_atlas_details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.region_opacity = QDoubleSpinBox(container)
        self.region_opacity.setObjectName("region-opacity")
        self.region_opacity.setRange(0.0, 1.0)
        self.region_opacity.setSingleStep(0.05)
        self.region_opacity.setValue(0.65)
        self.region_opacity.setEnabled(False)
        self.region_opacity.valueChanged.connect(self._on_region_opacity_changed)
        self.region_color = QPushButton("Source atlas color", container)
        self.region_color.setObjectName("region-color")
        self.region_color.setEnabled(False)
        self.region_color.clicked.connect(self._choose_region_color)
        form.addRow("Selection", self.inspector_type)
        form.addRow("Atlas", self.inspector_atlas)
        form.addRow("Coordinate", self.inspector_coordinate)
        form.addRow("Convention", self.inspector_convention)
        form.addRow("Atlas provenance", self.inspector_atlas_details)
        form.addRow("Region opacity", self.region_opacity)
        form.addRow("Region color", self.region_color)
        dock.setWidget(container)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.inspector_dock = dock

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        edit_menu = self.menuBar().addMenu("&Edit")
        atlas_menu = self.menuBar().addMenu("&Atlas")
        view_menu = self.menuBar().addMenu("&View")
        anatomy_menu = self.menuBar().addMenu("&Anatomy")

        self.new_action = QAction("New project", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_project)
        file_menu.addAction(self.new_action)

        self.open_action = QAction("Open…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_project_dialog)
        file_menu.addAction(self.open_action)

        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_project_action)
        file_menu.addAction(self.save_action)

        self.save_as_action = QAction("Save as…", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self.save_project_as_dialog)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        self.undo_stack = QUndoStack(self)
        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcuts(
            [
                QKeySequence(QKeySequence.StandardKey.Redo),
                QKeySequence("Meta+Shift+Z"),
            ]
        )
        edit_menu.addActions([self.undo_action, self.redo_action])

        self.select_atlas_action = QAction("Select atlas…", self)
        self.select_atlas_action.triggered.connect(self.select_atlas)
        atlas_menu.addAction(self.select_atlas_action)

        for index, (name, key) in enumerate(
            (
                ("3D view", "1"),
                ("Coronal view", "2"),
                ("Sagittal view", "3"),
                ("Horizontal view", "4"),
                ("Four-panel view", "5"),
            )
        ):
            action = QAction(name, self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(
                lambda checked=False, tab=index: self.viewer_tabs.setCurrentIndex(tab)
            )
            view_menu.addAction(action)

        self.reset_camera_action = QAction("Reset camera", self)
        self.reset_camera_action.setShortcut(QKeySequence("R"))
        self.reset_camera_action.triggered.connect(self._reset_cameras)
        view_menu.addAction(self.reset_camera_action)

        self.center_action = QAction("Center selected object", self)
        self.center_action.setShortcut(QKeySequence("C"))
        self.center_action.triggered.connect(self._reset_cameras)
        view_menu.addAction(self.center_action)

        camera_menu = view_menu.addMenu("Anatomical camera")
        for preset in ("anterior", "posterior", "dorsal", "ventral", "left", "right"):
            action = QAction(preset.title(), self)
            action.triggered.connect(lambda checked=False, name=preset: self._set_cameras(name))
            camera_menu.addAction(action)

        search_action = QAction("Search brain regions", self)
        search_action.setShortcut(QKeySequence.StandardKey.Find)
        search_action.triggered.connect(self.region_search.setFocus)
        anatomy_menu.addAction(search_action)

        toolbar = QToolBar("Project", self)
        toolbar.setObjectName("project-toolbar")
        toolbar.setMovable(False)
        toolbar.addActions(
            [self.new_action, self.open_action, self.save_action, self.select_atlas_action]
        )
        self.addToolBar(toolbar)

        warning_toolbar = QToolBar("Scientific limitation", self)
        warning_toolbar.setObjectName("scientific-warning-toolbar")
        warning_toolbar.setMovable(False)
        self.scientific_warning = QLabel(SCIENTIFIC_WARNING, warning_toolbar)
        self.scientific_warning.setWordWrap(True)
        warning_toolbar.addWidget(self.scientific_warning)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, warning_toolbar)

    def _build_status_bar(self) -> None:
        self.atlas_status = QLabel("Atlas: none")
        self.resolution_status = QLabel("Resolution: —")
        self.atlas_coordinate_status = QLabel("Atlas ASR: —")
        self.stereotaxic_status = QLabel("Stereotaxic: not calibrated")
        self.region_status = QLabel("Region: —")
        self.slice_status = QLabel("Slice: —")
        self.convention_status = QLabel("Convention: ASR [AP,DV,ML], A/S/R→P/I/L, µm")
        self.rendering_status = QLabel("Rendering: idle")
        self.atlas_coordinate_status.setToolTip(
            "Physical distance from the anterior, superior, right ASR origin; "
            "values increase posterior, inferior, and left."
        )
        for widget in (
            self.atlas_status,
            self.resolution_status,
            self.atlas_coordinate_status,
            self.stereotaxic_status,
            self.region_status,
            self.slice_status,
            self.convention_status,
            self.rendering_status,
        ):
            self.statusBar().addPermanentWidget(widget)
        self.statusBar().showMessage(SCIENTIFIC_WARNING)

    def new_project(self) -> bool:
        """Create a blank project and display a non-modal scientific limitation."""

        if not self._confirm_project_replacement("create a new project"):
            return False
        self._invalidate_async_callbacks()
        self._load_token += 1
        if self._load_worker is not None:
            self._load_worker.request_cancel()
        self._clear_loaded_atlas()
        self.project = PlannerProject()
        self.project_path = None
        self._set_dirty(False)
        self.undo_stack.clear()
        self._update_project_ui()
        self.scientific_warning.show()
        self.statusBar().showMessage(SCIENTIFIC_WARNING)
        return True

    def open_project_dialog(self) -> None:
        """Choose and open a ``.mouseplan`` package."""

        selected = QFileDialog.getExistingDirectory(self, "Open surgery plan")
        if selected:
            self.open_project(Path(selected))

    def open_project(self, path: Path) -> bool:
        """Open one verified project package and restore its cached exact atlas."""

        try:
            project = load_project(path)
        except Exception as error:
            self._show_error(
                "Open project failed",
                f"The current project was left unchanged. {type(error).__name__}: {error}",
            )
            return False
        if not self._confirm_project_replacement("open another project"):
            return False
        self._invalidate_async_callbacks()
        self._load_token += 1
        if self._load_worker is not None:
            self._load_worker.request_cancel()
        self._clear_loaded_atlas()
        self.project = project
        self.project_path = path.resolve()
        self._set_dirty(False)
        self.undo_stack.clear()
        self._update_project_ui()
        self.statusBar().showMessage(f"Opened {self.project_path}", 5000)
        if project.atlas is not None:
            self._begin_atlas_load(
                project.atlas.atlas_key,
                expected=project.atlas,
                allow_download=False,
            )
        return True

    def save_project_action(self) -> bool:
        """Save to the current path or ask for a new one."""

        if self.project_path is None:
            return self.save_project_as_dialog()
        return self._save_to(self.project_path)

    def save_project_as_dialog(self) -> bool:
        """Choose a path and save the current project."""

        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save surgery plan",
            f"{self.project.title}.mouseplan",
            "Mouse Brain Planner projects (*.mouseplan)",
        )
        if selected:
            return self._save_to(Path(selected))
        return False

    def _save_to(self, path: Path) -> bool:
        previous_project = self.project.model_copy(deep=True)
        previous_path = self.project_path
        was_dirty = self._dirty
        self.project.touch("project-saved")
        try:
            destination = save_project(self.project, path)
        except Exception as error:
            self.project = previous_project
            self.project_path = previous_path
            self._set_dirty(was_dirty)
            self._update_project_ui()
            self._show_error(
                "Save project failed",
                f"The current project was left unchanged. {type(error).__name__}: {error}",
            )
            return False
        self.project_path = destination
        self._set_dirty(False)
        self.statusBar().showMessage(f"Saved {self.project_path}", 5000)
        self._update_project_ui()
        return True

    def select_atlas(self) -> None:
        """Fetch the current catalog without blocking and present atlas choices."""

        if self._catalog_records is not None:
            self._show_atlas_selection(self._catalog_records)
            return
        self.select_atlas_action.setEnabled(False)
        self.rendering_status.setText("Rendering: fetching atlas catalog…")
        self._catalog_token += 1
        token = self._catalog_token
        worker = AtlasCatalogWorker(self._repository(), local_only=self.no_download)
        self._launch_worker(
            worker,
            on_success=lambda payload: self._on_catalog_loaded(payload, token),
            on_failure=lambda message: self._on_catalog_failed(message, token),
        )

    def _on_catalog_loaded(self, payload: object, token: int) -> None:
        if token != self._catalog_token or self._closing:
            return
        if not isinstance(payload, list):
            self._on_worker_error("Atlas catalog failed", "Catalog returned a non-list payload")
            return
        records = payload
        if not all(isinstance(record, AtlasCatalogRecord) for record in records):
            self._on_worker_error("Atlas catalog failed", "Catalog returned invalid records")
            return
        self._catalog_records = records
        self.select_atlas_action.setEnabled(True)
        self.rendering_status.setText("Rendering: idle")
        self._show_atlas_selection(records)

    def _on_catalog_failed(self, message: str, token: int) -> None:
        if token != self._catalog_token or self._closing:
            return
        self._on_worker_error("Atlas catalog failed", message)

    def _show_atlas_selection(self, records: list[AtlasCatalogRecord]) -> None:
        dialog = AtlasSelectionDialog(
            records,
            no_download=self.no_download,
            parent=self,
        )
        if dialog.exec() != AtlasSelectionDialog.DialogCode.Accepted:
            return
        record = dialog.selected_record
        if record is None:
            return
        if not record.downloaded and not self._confirm_atlas_download(record):
            return
        self._begin_atlas_load(record.name, package_version=record.latest_version)

    def _confirm_atlas_download(self, record: AtlasCatalogRecord) -> bool:
        if self.no_download:
            self._show_error(
                "Downloads disabled",
                f"{record.name} is not cached and --no-download is active.",
            )
            return False
        settings = QSettings()
        is_allen = record.name.startswith("allen_mouse_")
        acknowledgement_key = (
            "atlas/allen_terms_acknowledged"
            if is_allen
            else f"atlas/terms_acknowledged/{record.name}"
        )
        if settings.value(acknowledgement_key, False, type=bool):
            return True
        if self.suppress_dialogs:
            return False
        terms_name = "Allen Institute Terms of Use" if is_allen else "source data terms"
        answer = QMessageBox.question(
            self,
            "Confirm atlas data download",
            "BrainGlobe will download the selected atlas from its declared source. "
            "Atlas data have their own citation and usage terms. Continue after reviewing "
            f"the {terms_name} and the atlas citation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        accepted = answer is QMessageBox.StandardButton.Yes
        if accepted:
            settings.setValue(acknowledgement_key, True)
        return accepted

    def _begin_atlas_load(
        self,
        atlas_name: str,
        *,
        expected: AtlasMetadata | None = None,
        allow_download: bool | None = None,
        package_version: str | None = None,
    ) -> None:
        self._load_token += 1
        token = self._load_token
        if self._load_worker is not None:
            self._load_worker.request_cancel()
        self._finish_load_progress()
        self._expected_atlas = expected
        downloads_allowed = not self.no_download if allow_download is None else allow_download
        if expected is not None:
            downloads_allowed = False
        worker = AtlasLoadWorker(
            self._repository(),
            atlas_name,
            allow_download=downloads_allowed,
            package_version=(
                package_version if expected is None else expected.atlas_package_version
            ),
        )
        self._load_worker = worker
        self.select_atlas_action.setEnabled(False)
        progress = QProgressDialog(
            f"Opening {atlas_name} through BrainGlobe…",
            "Cancel",
            0,
            0,
            self,
        )
        progress.setObjectName("atlas-load-progress")
        progress.setWindowTitle("Atlas acquisition")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.canceled.connect(self._cancel_atlas_load)
        self._load_progress = progress
        self.rendering_status.setText(f"Rendering: loading {atlas_name}…")

        def loaded_callback(payload: object) -> None:
            self._on_atlas_loaded(payload, token)

        def failure_callback(message: str) -> None:
            self._on_atlas_load_failed(message, token)

        def cancelled_callback(message: str) -> None:
            self._on_atlas_cancelled(message, token)

        self._launch_worker(
            worker,
            on_success=loaded_callback,
            on_failure=failure_callback,
            on_cancelled=cancelled_callback,
            on_progress=lambda completed, total: self._on_atlas_progress(completed, total, token),
        )
        progress.show()

    def _cancel_atlas_load(self) -> None:
        if self._load_worker is not None:
            self._load_worker.request_cancel()
            self.rendering_status.setText("Rendering: cancelling atlas load…")

    def _on_atlas_progress(self, completed: int, total: int, token: int) -> None:
        if token != self._load_token or self._closing:
            return
        progress = self._load_progress
        if progress is None:
            return
        if total > 0:
            progress.setRange(0, total)
            progress.setValue(min(max(completed, 0), total))
        else:
            progress.setRange(0, 0)

    def _on_atlas_cancelled(self, message: str, token: int) -> None:
        if token != self._load_token:
            return
        self._finish_load_progress()
        self.rendering_status.setText("Rendering: atlas load cancelled")
        self.select_atlas_action.setEnabled(True)
        self.statusBar().showMessage(message, 5000)

    def _on_atlas_load_failed(self, message: str, token: int) -> None:
        if token != self._load_token:
            return
        self._finish_load_progress()
        self.rendering_status.setText("Rendering: atlas load failed")
        self.select_atlas_action.setEnabled(True)
        self._show_error("Atlas load failed", message)

    def _on_atlas_loaded(self, payload: object, token: int) -> None:
        if token != self._load_token:
            return
        if not isinstance(payload, LoadedAtlasPayload):
            self._on_atlas_load_failed("Worker returned an invalid atlas payload", token)
            return
        expected = self._expected_atlas
        actual = payload.atlas.metadata
        if expected is not None and not self._same_atlas_identity(expected, actual):
            self._on_atlas_load_failed(
                "Cached atlas identity differs from the project record: "
                f"expected {expected.atlas_key} v{expected.atlas_package_version} "
                f"{expected.resolution_um} µm; got {actual.atlas_key} "
                f"v{actual.atlas_package_version} {actual.resolution_um} µm.",
                token,
            )
            return
        self._finish_load_progress()
        try:
            self._install_loaded_atlas(payload, restoring=expected is not None)
        except Exception as error:
            self._clear_loaded_atlas()
            self.rendering_status.setText("Rendering: atlas setup failed")
            self._show_error("Atlas setup failed", f"{type(error).__name__}: {error}")

    @staticmethod
    def _same_atlas_identity(expected: AtlasMetadata, actual: AtlasMetadata) -> bool:
        return (
            expected.atlas_key,
            expected.atlas_package_version,
            expected.resolution_um,
            expected.shape_voxels,
            expected.standardized_orientation,
            expected.metadata_sha256,
        ) == (
            actual.atlas_key,
            actual.atlas_package_version,
            actual.resolution_um,
            actual.shape_voxels,
            actual.standardized_orientation,
            actual.metadata_sha256,
        )

    def _install_loaded_atlas(
        self,
        payload: LoadedAtlasPayload,
        *,
        restoring: bool,
    ) -> None:
        atlas = payload.atlas
        metadata = atlas.metadata
        space = BrainGlobeAtlasSpace(metadata)
        renderer = SliceRenderer(
            atlas.reference,
            atlas.annotation,
            resolution_um=metadata.resolution_um,
        )
        center_index = BrainGlobeVoxelIndex(
            atlas_key=metadata.atlas_key,
            atlas_version=metadata.atlas_package_version,
            ap=metadata.shape_voxels[0] // 2,
            dv=metadata.shape_voxels[1] // 2,
            ml=metadata.shape_voxels[2] // 2,
        )
        center = space.index_to_center(center_index)

        region_by_id = {region.structure_id: region for region in atlas.regions}
        restored_cursor = self.project.linked_cursor if restoring else None
        restored_selection = self.project.selected_region_id if restoring else None
        if restoring:
            persisted_ids = {state.structure_id for state in self.project.region_display}
            if restored_selection is not None:
                persisted_ids.add(restored_selection)
            missing_ids = sorted(persisted_ids.difference(region_by_id))
            if missing_ids:
                missing_text = ", ".join(str(structure_id) for structure_id in missing_ids)
                raise ValueError(
                    "Project references structure IDs that are not present in the exact "
                    f"loaded atlas ({metadata.atlas_key} "
                    f"v{metadata.atlas_package_version}): {missing_text}. "
                    "Verify the atlas package/version or repair the project region state."
                )

        previous_project = self.project.model_copy(deep=True)
        previous_dirty = self._dirty
        four_panel_brain: Brain3DView | None = None
        try:
            self._clear_loaded_atlas()
            if not restoring:
                # Do this before building the replacement tree so IDs shared by two
                # atlases cannot inherit stale visibility, color, or selection state.
                self.project.linked_cursor = None
                self.project.selected_region_id = None
                self.project.region_display = []
                self.project.atlas = None

            self._loaded_atlas = atlas
            self._atlas_space = space
            self._slice_renderer = renderer
            self._region_by_id = region_by_id
            self._populate_region_tree(atlas.regions)
            self._create_slice_views(renderer)

            self.brain_3d_view.load_atlas(space, payload.root_mesh, anchor=center)
            four_panel_brain = Brain3DView(self.four_panel_page)
            four_panel_brain.physical_point_picked.connect(self._on_physical_cursor_picked)
            four_panel_brain.load_atlas(space, payload.root_mesh, anchor=center)
            self._four_panel_layout.addWidget(four_panel_brain, 0, 0)
            self._four_panel_brain = four_panel_brain
            self._brain_views = [self.brain_3d_view, four_panel_brain]

            if restored_cursor is not None:
                try:
                    cursor_index = space.physical_to_index(restored_cursor)
                except (CoordinateBoundsError, ValueError):
                    cursor_index = center_index
            else:
                cursor_index = center_index

            self.project.atlas = metadata
            if not restoring:
                self._record_project_change(
                    "atlas-selected",
                    f"{metadata.atlas_key} v{metadata.atlas_package_version} "
                    f"at {metadata.resolution_um} µm ASR",
                )
            self._update_project_ui()
            self._set_cursor_voxel(
                cursor_index.ap,
                cursor_index.dv,
                cursor_index.ml,
                select_annotation_region=not restoring,
                record_change=False,
            )
            if restoring:
                restored_region = (
                    None if restored_selection is None else region_by_id[restored_selection]
                )
                self._select_region(restored_region, record_change=False)
            self._restore_region_visibility()
            self.rendering_status.setText("Rendering: ready")
            self.select_atlas_action.setEnabled(True)
            self.statusBar().showMessage(
                f"Loaded {metadata.atlas_key} v{metadata.atlas_package_version}", 5000
            )
        except Exception:
            # The second view is not in the layout until load succeeds, so it
            # needs explicit disposal in addition to the regular window reset.
            if four_panel_brain is not None and four_panel_brain is not self._four_panel_brain:
                four_panel_brain.dispose()
                four_panel_brain.deleteLater()
            self._clear_loaded_atlas()
            self.project = previous_project
            self._set_dirty(previous_dirty)
            self._update_project_ui()
            raise

    def _create_slice_views(self, renderer: SliceRenderer) -> None:
        self._slice_views.clear()
        for orientation, layout in self._slice_layouts.items():
            self._clear_layout(layout)
            view = OrthogonalSliceView(renderer, orientation, self._slice_pages[orientation])
            view.cursor_changed.connect(self._set_cursor_voxel)
            layout.addWidget(view)
            self._slice_views.append(view)

        self._clear_grid_layout(self._four_panel_layout)
        for orientation, title, row, column in (
            (SliceOrientation.CORONAL, "Coronal", 0, 1),
            (SliceOrientation.SAGITTAL, "Sagittal", 1, 0),
            (SliceOrientation.HORIZONTAL, "Horizontal", 1, 1),
        ):
            panel = QWidget(self.four_panel_page)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(title, panel)
            panel_layout.addWidget(label)
            view = OrthogonalSliceView(renderer, orientation, panel)
            view.cursor_changed.connect(self._set_cursor_voxel)
            panel_layout.addWidget(view, 1)
            self._four_panel_layout.addWidget(panel, row, column)
            self._slice_views.append(view)

    def _set_cursor_voxel(
        self,
        ap: int,
        dv: int,
        ml: int,
        *,
        select_annotation_region: bool = True,
        record_change: bool = True,
    ) -> None:
        atlas = self._loaded_atlas
        space = self._atlas_space
        if atlas is None or space is None:
            return
        index = BrainGlobeVoxelIndex(
            atlas_key=atlas.metadata.atlas_key,
            atlas_version=atlas.metadata.atlas_package_version,
            ap=ap,
            dv=dv,
            ml=ml,
        )
        physical = space.index_to_center(index)
        previous_cursor = self.project.linked_cursor
        self.project.linked_cursor = physical
        for slice_view in self._slice_views:
            slice_view.set_cursor(ap, dv, ml)
        for brain_view in self._brain_views:
            brain_view.set_crosshair(physical)
        region = atlas.region_at(physical)
        if select_annotation_region:
            self._select_region(region, record_change=False)
        self._update_coordinate_status(index, physical, region)
        if record_change and previous_cursor != physical:
            region_details = "outside annotation" if region is None else str(region.structure_id)
            self._record_project_change(
                "cursor-changed",
                f"voxel [{ap}, {dv}, {ml}], region {region_details}",
            )

    def _on_physical_cursor_picked(self, payload: object) -> None:
        space = self._atlas_space
        if space is None or not isinstance(payload, BrainGlobePhysicalPoint):
            return
        try:
            index = space.physical_to_index(payload)
        except CoordinateBoundsError as error:
            self.statusBar().showMessage(str(error), 5000)
            return
        self._set_cursor_voxel(index.ap, index.dv, index.ml)

    def _update_coordinate_status(
        self,
        index: BrainGlobeVoxelIndex,
        physical: BrainGlobePhysicalPoint,
        region: RegionRecord | None,
    ) -> None:
        self.atlas_coordinate_status.setText(
            "Atlas ASR µm: "
            f"A→P {physical.ap_um:.1f}, S→I {physical.dv_um:.1f}, "
            f"R→L {physical.ml_um:.1f}"
        )
        self.inspector_coordinate.setText(
            f"ASR µm [{physical.ap_um:.3f}, {physical.dv_um:.3f}, "
            f"{physical.ml_um:.3f}]\nvoxel-center index [{index.ap}, {index.dv}, {index.ml}]"
        )
        self.slice_status.setText(f"Slice index: AP {index.ap}, DV {index.dv}, ML {index.ml}")
        if region is None:
            self.region_status.setText("Region: outside annotation")
        else:
            self.region_status.setText(f"Region: {region.acronym} — {region.name}")

    def _populate_region_tree(self, regions: list[RegionRecord]) -> None:
        self._updating_region_tree = True
        try:
            self.region_tree.clear()
            self._region_items.clear()
            display_states = {state.structure_id: state for state in self.project.region_display}
            for region in regions:
                item = QTreeWidgetItem([region.acronym, region.name, str(region.structure_id)])
                item.setData(0, Qt.ItemDataRole.UserRole, region.structure_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                state = display_states.get(region.structure_id)
                item.setCheckState(
                    0,
                    Qt.CheckState.Checked
                    if state is not None and state.visible
                    else Qt.CheckState.Unchecked,
                )
                item.setIcon(0, self._color_icon(self._region_color(region, state)))
                item.setToolTip(
                    0,
                    f"{region.acronym} — {region.name}\n"
                    f"Structure path: {' / '.join(map(str, region.structure_id_path))}",
                )
                self._region_items[region.structure_id] = item
            for region in regions:
                item = self._region_items[region.structure_id]
                parent = self._region_items.get(region.parent_id or -1)
                if parent is None:
                    self.region_tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
            self.region_tree.resizeColumnToContents(0)
            self.region_tree.resizeColumnToContents(2)
        finally:
            self._updating_region_tree = False

    def _show_no_atlas_region_item(self) -> None:
        self.region_tree.clear()
        root = QTreeWidgetItem(["No atlas loaded", "", ""])
        root.setDisabled(True)
        self.region_tree.addTopLevelItem(root)

    def _filter_regions(self, query: str) -> None:
        normalized = query.strip().casefold()
        alias_targets = REGION_SEARCH_ALIASES.get(normalized.upper(), frozenset())

        def apply(item: QTreeWidgetItem) -> bool:
            child_matches = False
            for index in range(item.childCount()):
                child = item.child(index)
                if child is not None and apply(child):
                    child_matches = True
            own_text = " ".join(item.text(column) for column in range(3)).casefold()
            structure_id = item.data(0, Qt.ItemDataRole.UserRole)
            region = self._region_by_id.get(structure_id) if isinstance(structure_id, int) else None
            alias_match = region is not None and region.acronym in alias_targets
            own_match = not normalized or normalized in own_text or alias_match
            visible = own_match or child_matches
            item.setHidden(not visible)
            if normalized and child_matches:
                item.setExpanded(True)
            return visible

        for index in range(self.region_tree.topLevelItemCount()):
            item = self.region_tree.topLevelItem(index)
            if item is not None:
                apply(item)

    def _on_region_selection_changed(self) -> None:
        item = self.region_tree.currentItem()
        if item is None:
            return
        structure_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(structure_id, int):
            return
        region = self._region_by_id.get(structure_id)
        if region is not None:
            self._select_region(region, update_tree=False)

    def _select_region(
        self,
        region: RegionRecord | None,
        *,
        update_tree: bool = True,
        record_change: bool = True,
    ) -> None:
        previous_id = self.project.selected_region_id
        selected_id = None if region is None else region.structure_id
        self.project.selected_region_id = selected_id
        if update_tree:
            item = None if region is None else self._region_items.get(region.structure_id)
            if self.region_tree.currentItem() is not item:
                blocker = QSignalBlocker(self.region_tree)
                self.region_tree.clearSelection()
                if item is None:
                    self.region_tree.setCurrentIndex(QModelIndex())
                else:
                    self.region_tree.setCurrentItem(item)
                del blocker
        self._updating_inspector = True
        try:
            if region is None:
                self.inspector_type.setText("Nothing selected")
                self.region_opacity.setEnabled(False)
                self.region_color.setEnabled(False)
                selected_id = None
                selected_color = (0, 174, 239)
            else:
                state = self._region_display_state(region.structure_id)
                color = self._region_color(region, state)
                self.inspector_type.setText(
                    f"Brain region: {region.acronym} — {region.name} (ID {region.structure_id})"
                )
                self.region_opacity.setValue(state.opacity)
                self.region_opacity.setEnabled(True)
                self.region_color.setEnabled(True)
                self.region_color.setIcon(self._color_icon(color))
                self.region_color.setText(
                    "Custom display color" if state.custom_rgb is not None else "Source atlas color"
                )
                selected_id = region.structure_id
                selected_color = color
            for view in self._slice_views:
                view.set_selected_region(selected_id, color=selected_color)
        finally:
            self._updating_inspector = False
        if record_change and previous_id != selected_id:
            details = "background" if selected_id is None else str(selected_id)
            self._record_project_change("region-selected", details)

    def _on_region_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating_region_tree or column != 0:
            return
        structure_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(structure_id, int):
            return
        visible = item.checkState(0) is Qt.CheckState.Checked
        state = self._set_region_display(structure_id, visible=visible)
        if visible:
            self._show_or_load_region_mesh(structure_id)
        else:
            region = self._region_by_id.get(structure_id)
            if region is not None:
                for view in self._brain_views:
                    source = self._region_meshes.get(structure_id)
                    if source is not None:
                        view.set_region(
                            structure_id,
                            source,
                            rgb=self._region_color(region, state),
                            opacity=state.opacity,
                            visible=False,
                        )
        self._record_project_change("region-visibility-changed", f"{structure_id}: {visible}")

    def _show_or_load_region_mesh(self, structure_id: int) -> None:
        mesh = self._region_meshes.get(structure_id)
        if mesh is not None:
            self._apply_region_mesh(structure_id, mesh)
            return
        if structure_id in self._region_meshes_loading or self._loaded_atlas is None:
            return
        self._region_meshes_loading.add(structure_id)
        token = self._load_token
        self.rendering_status.setText(f"Rendering: loading region {structure_id}…")
        worker = RegionMeshWorker(self._loaded_atlas, structure_id)
        self._launch_worker(
            worker,
            on_success=lambda payload, request_token=token: self._on_region_mesh_loaded(
                payload, request_token
            ),
            on_failure=lambda region_id, message, request_token=token: self._on_region_mesh_failed(
                region_id, message, request_token
            ),
        )

    def _on_region_mesh_loaded(self, payload: object, token: int) -> None:
        if token != self._load_token or not isinstance(payload, RegionMeshPayload):
            return
        self._region_meshes_loading.discard(payload.structure_id)
        self._region_meshes[payload.structure_id] = payload.mesh
        state = self._region_display_state(payload.structure_id)
        if state.visible:
            self._apply_region_mesh(payload.structure_id, payload.mesh)
        self.rendering_status.setText("Rendering: ready")

    def _on_region_mesh_failed(self, structure_id: int, message: str, token: int) -> None:
        if token != self._load_token:
            return
        self._region_meshes_loading.discard(structure_id)
        self.rendering_status.setText("Rendering: region mesh failed")
        self._show_error("Region mesh failed", message)

    def _apply_region_mesh(self, structure_id: int, mesh: pv.DataSet) -> None:
        region = self._region_by_id[structure_id]
        state = self._region_display_state(structure_id)
        color = self._region_color(region, state)
        for view in self._brain_views:
            view.set_region(
                structure_id,
                mesh,
                rgb=color,
                opacity=state.opacity,
                visible=state.visible,
            )

    def _restore_region_visibility(self) -> None:
        for state in self.project.region_display:
            if state.visible and state.structure_id in self._region_by_id:
                self._show_or_load_region_mesh(state.structure_id)

    def _region_display_state(self, structure_id: int) -> RegionDisplayState:
        for state in self.project.region_display:
            if state.structure_id == structure_id:
                return state
        return RegionDisplayState(structure_id=structure_id)

    def _set_region_display(
        self,
        structure_id: int,
        *,
        visible: bool | None = None,
        opacity: float | None = None,
        custom_rgb: tuple[int, int, int] | None | object = ...,
    ) -> RegionDisplayState:
        previous = self._region_display_state(structure_id)
        changes: dict[str, object] = {}
        if visible is not None:
            changes["visible"] = visible
        if opacity is not None:
            changes["opacity"] = opacity
        if custom_rgb is not ...:
            changes["custom_rgb"] = custom_rgb
        updated = previous.model_copy(update=changes)
        states = [
            state for state in self.project.region_display if state.structure_id != structure_id
        ]
        states.append(updated)
        self.project.region_display = sorted(states, key=lambda state: state.structure_id)
        return updated

    def _on_region_opacity_changed(self, opacity: float) -> None:
        if self._updating_inspector or self.project.selected_region_id is None:
            return
        structure_id = self.project.selected_region_id
        self._set_region_display(structure_id, opacity=opacity)
        mesh = self._region_meshes.get(structure_id)
        if mesh is not None:
            self._apply_region_mesh(structure_id, mesh)
        self._record_project_change("region-opacity-changed", f"{structure_id}: {opacity:.3f}")

    def _choose_region_color(self) -> None:
        structure_id = self.project.selected_region_id
        region = self._region_by_id.get(structure_id or -1)
        if region is None:
            return
        current = self._region_color(region, self._region_display_state(region.structure_id))
        selected = QColorDialog.getColor(QColor(*current), self, "Region display color")
        if not selected.isValid():
            return
        rgb = (selected.red(), selected.green(), selected.blue())
        state = self._set_region_display(region.structure_id, custom_rgb=rgb)
        item = self._region_items.get(region.structure_id)
        if item is not None:
            item.setIcon(0, self._color_icon(rgb))
        self._select_region(region, update_tree=False)
        mesh = self._region_meshes.get(region.structure_id)
        if mesh is not None and state.visible:
            self._apply_region_mesh(region.structure_id, mesh)
        self._record_project_change("region-color-changed", f"{region.structure_id}: {rgb}")

    @staticmethod
    def _region_color(
        region: RegionRecord,
        state: RegionDisplayState | None,
    ) -> tuple[int, int, int]:
        if state is not None and state.custom_rgb is not None:
            return state.custom_rgb
        return region.rgb

    @staticmethod
    def _color_icon(rgb: tuple[int, int, int]) -> QIcon:
        swatch = QPixmap(14, 14)
        swatch.fill(QColor(*rgb))
        return QIcon(swatch)

    def _repository(self) -> AtlasRepositoryProtocol:
        if self._repository_instance is None:
            self._repository_instance = BrainGlobeAtlasRepository()
        return self._repository_instance

    def _launch_worker(
        self,
        worker: object,
        *,
        on_success: Callable[..., None],
        on_failure: Callable[..., None],
        on_cancelled: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        if not isinstance(worker, (AtlasCatalogWorker, AtlasLoadWorker, RegionMeshWorker)):
            raise TypeError(f"unsupported worker type: {type(worker).__name__}")
        thread = QThread(self)
        relay = _WorkerRelay(
            on_success=on_success,
            on_failure=on_failure,
            on_cancelled=on_cancelled,
            on_progress=on_progress,
            parent=self,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(relay.success)
        if isinstance(worker, RegionMeshWorker):
            worker.failed.connect(relay.indexed_failure)
        else:
            worker.failed.connect(relay.failure)
        if isinstance(worker, AtlasLoadWorker):
            worker.cancelled.connect(relay.cancelled)
            worker.progress.connect(relay.progress)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._active_threads.add(thread)
        self._worker_refs[thread] = (worker, relay)
        thread.start()

    @Slot()
    def _on_thread_finished(self) -> None:
        thread = self.sender()
        if isinstance(thread, QThread):
            self._worker_finished(thread)

    def _worker_finished(self, thread: QThread) -> None:
        entry = self._worker_refs.pop(thread, None)
        worker = None if entry is None else entry[0]
        if entry is not None:
            entry[1].deleteLater()
        if worker is self._load_worker:
            self._load_worker = None
        self._active_threads.discard(thread)
        if self._close_pending and not self._active_threads:
            QTimer.singleShot(0, self.close)

    def _finish_load_progress(self) -> None:
        if self._load_progress is not None:
            self._load_progress.blockSignals(True)
            self._load_progress.close()
            self._load_progress.deleteLater()
            self._load_progress = None
        self._expected_atlas = None

    def _on_worker_error(self, title: str, message: str) -> None:
        if self._closing:
            return
        self.select_atlas_action.setEnabled(True)
        self.rendering_status.setText("Rendering: idle")
        self._show_error(title, message)

    def _show_error(self, title: str, message: str) -> None:
        logger.error(
            "%s: %s",
            title,
            message,
            extra={"event": "user-visible-error"},
        )
        self.statusBar().showMessage(message, 10000)
        if not self.suppress_dialogs and not self._closing:
            QMessageBox.critical(self, title, message)

    def _record_project_change(self, action: str, details: str | None = None) -> None:
        """Record one user-visible project mutation and mark it unsaved."""

        self.project.touch(action, details)
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self.setWindowModified(dirty)

    def _confirm_project_replacement(self, action: str) -> bool:
        """Offer Save/Discard/Cancel before replacing unsaved state."""

        if not self._dirty:
            return True
        if self.suppress_dialogs:
            return True
        answer = QMessageBox.warning(
            self,
            "Unsaved project changes",
            f"Save changes to {self.project.title!r} before you {action}?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project_action()
        return answer == QMessageBox.StandardButton.Discard

    def _invalidate_async_callbacks(self) -> None:
        """Make all outstanding atlas and catalog callbacks stale."""

        self._catalog_token += 1
        self._load_token += 1
        for worker, _relay in self._worker_refs.values():
            if isinstance(worker, (AtlasCatalogWorker, AtlasLoadWorker)):
                worker.request_cancel()

    def _reset_cameras(self) -> None:
        for view in self._brain_views:
            view.reset_camera()

    def _set_cameras(self, preset: str) -> None:
        for view in self._brain_views:
            view.set_camera(preset)

    def _clear_loaded_atlas(self) -> None:
        self._load_token += 1
        self._finish_load_progress()
        self.brain_3d_view.dispose()
        for view in self._slice_views:
            view.deleteLater()
        self._slice_views.clear()
        for layout in self._slice_layouts.values():
            self._clear_layout(layout)
            self._add_empty_label(layout, "slice-empty-state")
        self._clear_grid_layout(self._four_panel_layout)
        self._add_four_panel_empty_state()
        self._four_panel_brain = None
        self._brain_views = [self.brain_3d_view]
        self._loaded_atlas = None
        self._atlas_space = None
        self._slice_renderer = None
        self._region_by_id.clear()
        self._region_items.clear()
        self._region_meshes.clear()
        self._region_meshes_loading.clear()
        self._show_no_atlas_region_item()
        self.inspector_type.setText("Nothing selected")
        self.region_opacity.setEnabled(False)
        self.region_color.setEnabled(False)
        self.region_color.setText("Source atlas color")
        self.atlas_coordinate_status.setText("Atlas ASR: —")
        self.stereotaxic_status.setText("Stereotaxic: not calibrated")
        self.region_status.setText("Region: —")
        self.slice_status.setText("Slice: —")
        self.rendering_status.setText("Rendering: idle")
        self.select_atlas_action.setEnabled(True)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _clear_grid_layout(layout: QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if isinstance(widget, Brain3DView):
                widget.dispose()
            if widget is not None:
                widget.deleteLater()

    def _update_project_ui(self) -> None:
        title = self.project.title
        suffix = f" — {self.project_path.name}" if self.project_path else ""
        self.setWindowTitle(f"{title}{suffix}[*] — Mouse Brain Surgery Planner")
        self.inspector_convention.setText(self.project.coordinate_convention)
        if self.project.atlas is None:
            self.inspector_atlas.setText("None")
            self.inspector_atlas_details.setText("No atlas loaded")
            self.atlas_status.setText("Atlas: none")
            self.resolution_status.setText("Resolution: —")
        else:
            atlas = self.project.atlas
            self.inspector_atlas.setText(f"{atlas.atlas_key} package {atlas.atlas_package_version}")
            self.atlas_status.setText(f"Atlas: {atlas.atlas_key} v{atlas.atlas_package_version}")
            resolution = " x ".join(f"{value:g}" for value in atlas.resolution_um)
            dimensions = " x ".join(f"{value / 1000.0:.3f}" for value in atlas.extent_um)
            self.resolution_status.setText(f"Resolution: {resolution} µm")
            self.inspector_atlas_details.setText(
                f"Species: {atlas.species}\n"
                f"Shape [AP,DV,ML]: {atlas.shape_voxels}\n"
                f"Physical extent [AP,DV,ML]: {dimensions} mm\n"
                "Orientation: BrainGlobe ASR; origin anterior/superior/right; "
                "increasing posterior/inferior/left\n"
                f"Framework: {atlas.framework_name}\n"
                f"Source annotation: {atlas.source_annotation or 'not declared'}\n"
                f"Citation: {atlas.citation}\n"
                f"Cache: {atlas.cache_path}\n"
                f"metadata.json SHA-256: {atlas.metadata_sha256}"
            )

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """Cancel workers before releasing Qt and VTK resources."""

        if not self._closing:
            if not self._confirm_project_replacement("close this window"):
                event.ignore()
                return
            self._closing = True
            self._invalidate_async_callbacks()
        if self._active_threads:
            self._close_pending = True
            if self._load_worker is not None:
                self._load_worker.request_cancel()
            if self._load_progress is not None:
                self._load_progress.hide()
            self.hide()
            event.ignore()
            return
        self._clear_loaded_atlas()
        event.accept()
        super().closeEvent(event)
