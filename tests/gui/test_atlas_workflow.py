"""Phase 1 atlas-selection, worker, and linked-view integration tests."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import pyvista as pv
from PySide6.QtCore import QItemSelectionModel, QModelIndex, QPersistentModelIndex, Qt, QTimer
from PySide6.QtGui import QAccessible, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QProgressDialog,
    QRadioButton,
    QTreeView,
)
from pytestqt.qtbot import QtBot

import mouse_brain_planner.gui.dialogs.atlas_selection as atlas_selection_module
from mouse_brain_planner.atlas.brainglobe_adapter import (
    AtlasCatalogRecord,
    AtlasDownloadCancelledError,
    LoadedAtlas,
)
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import (
    BrainGlobePhysicalPoint,
    BrainGlobeVoxelIndex,
)
from mouse_brain_planner.domain.project_models import PlannerProject, RegionDisplayState
from mouse_brain_planner.gui.dialogs.atlas_selection import (
    SUPPORTED_ATLAS_NAME,
    SUPPORTED_ATLAS_RAW_VOLUME_BYTES,
    SUPPORTED_ATLAS_VERSION,
    AtlasSelectionDialog,
    format_bytes,
)
from mouse_brain_planner.gui.main_window import MainWindow
from mouse_brain_planner.gui.viewers.brain_3d_view import Brain3DView
from mouse_brain_planner.gui.workers.atlas_worker import (
    ATLAS_SURFACE_STAGE_TEXT,
    AtlasCatalogWorker,
    AtlasLoadWorker,
    AtlasRepositoryProtocol,
    LoadedAtlasPayload,
    RegionMeshPayload,
    RegionMeshWorker,
    center_voxel_anchor,
)
from mouse_brain_planner.rendering.scene_controller import (
    PreparedWorldMesh,
    prepare_world_mesh,
)

pytestmark = pytest.mark.gui


def make_small_asr_metadata(
    cache_path: Path,
    *,
    isotropic_resolution_um: float | None = None,
) -> AtlasMetadata:
    """Return explicit small metadata for orchestration tests only."""

    resolution = (
        (100.0, 200.0, 300.0) if isotropic_resolution_um is None else (isotropic_resolution_um,) * 3
    )
    atlas_key = (
        "allen_mouse_25um"
        if isotropic_resolution_um is None
        else f"allen_mouse_{isotropic_resolution_um:g}um"
    )
    return AtlasMetadata(
        atlas_key=atlas_key,
        atlas_package_version="1.2",
        species="Mus musculus",
        citation="GUI orchestration test double; not anatomical evidence",
        source_url="https://example.invalid/test-double",
        cache_path=str(cache_path),
        metadata_sha256="a" * 64,
        resolution_um=resolution,
        shape_voxels=(4, 5, 6),
        source_annotation="test-double",
        symmetric=True,
        midline_ml_um=3.0 * resolution[2],
        axes=(
            AtlasAxis(
                array_axis=0,
                anatomical_axis="AP",
                origin_direction="anterior",
                positive_direction="posterior",
                voxel_size_um=resolution[0],
            ),
            AtlasAxis(
                array_axis=1,
                anatomical_axis="DV",
                origin_direction="superior",
                positive_direction="inferior",
                voxel_size_um=resolution[1],
            ),
            AtlasAxis(
                array_axis=2,
                anatomical_axis="ML",
                origin_direction="right",
                positive_direction="left",
                voxel_size_um=resolution[2],
            ),
        ),
    )


class FakeLoadedAtlas:
    """Small ASR test double for GUI orchestration, not atlas anatomy."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        isotropic_resolution_um: float | None = None,
    ) -> None:
        self.metadata = make_small_asr_metadata(
            tmp_path,
            isotropic_resolution_um=isotropic_resolution_um,
        )
        self.reference = np.arange(120, dtype=np.uint16).reshape((4, 5, 6))
        self.annotation = np.full((4, 5, 6), 2, dtype=np.uint32)
        self.regions = [
            RegionRecord(
                structure_id=1,
                acronym="root",
                name="Root structure",
                structure_id_path=(1,),
                rgb=(220, 220, 220),
            ),
            RegionRecord(
                structure_id=2,
                acronym="CA1",
                name="Field CA1",
                structure_id_path=(1, 2),
                rgb=(10, 80, 200),
            ),
            RegionRecord(
                structure_id=3,
                acronym="AD",
                name="Anterodorsal nucleus",
                structure_id_path=(1, 3),
                rgb=(80, 120, 200),
            ),
            RegionRecord(
                structure_id=4,
                acronym="RSP",
                name="Retrosplenial area",
                structure_id_path=(1, 4),
                rgb=(120, 80, 200),
            ),
            RegionRecord(
                structure_id=5,
                acronym="ENTm",
                name="Entorhinal area, medial part",
                structure_id_path=(1, 5),
                rgb=(200, 120, 80),
            ),
        ]
        self.mesh_path = tmp_path / "root.vtp"
        pv.Sphere(theta_resolution=8, phi_resolution=8).save(self.mesh_path)

    def root_mesh_file(self) -> Path:
        return self.mesh_path

    def mesh_file_for_region(self, region: int | str | RegionRecord) -> Path:
        del region
        return self.mesh_path

    def region_at(self, point: BrainGlobePhysicalPoint) -> RegionRecord:
        BrainGlobeAtlasSpace(self.metadata).physical_to_index(point)
        return self.regions[1]


class FakeRepository:
    """Deterministic repository accepted by the GUI worker protocol."""

    def __init__(self, atlas: FakeLoadedAtlas) -> None:
        self.atlas = atlas
        self.open_calls = 0
        self.last_package_version: str | None = None
        self.last_allow_download: bool | None = None
        self.last_catalog_local_only: bool | None = None

    def list_atlases(
        self,
        *,
        local_only: bool = False,
        cancel: Callable[[], bool] | None = None,
    ) -> list[AtlasCatalogRecord]:
        self.last_catalog_local_only = local_only
        if cancel is not None and cancel():
            raise AtlasDownloadCancelledError("cancelled test catalog")
        return [AtlasCatalogRecord(self.atlas.metadata.atlas_key, "1.2", True)]

    def is_cached(self, atlas_name: str, package_version: str | None = None) -> bool:
        return atlas_name == self.atlas.metadata.atlas_key and package_version in {None, "1.2"}

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> LoadedAtlas:
        assert atlas_name == self.atlas.metadata.atlas_key
        self.open_calls += 1
        self.last_package_version = package_version
        self.last_allow_download = allow_download
        if not allow_download and not self.is_cached(atlas_name, package_version):
            raise FileNotFoundError(
                f"{atlas_name} v{package_version} is not cached and downloads are disabled"
            )
        if cancel is not None and cancel():
            raise AtlasDownloadCancelledError("cancelled test atlas")
        if progress is not None:
            progress(1, 1)
        return cast(LoadedAtlas, self.atlas)


class RecoveryRepository(FakeRepository):
    """Record exact recovery policy and optionally make the cached reload fail."""

    def __init__(self, atlas: FakeLoadedAtlas, *, fail_open: bool = False) -> None:
        super().__init__(atlas)
        self.fail_open = fail_open
        self.open_requests: list[tuple[str, str | None, bool]] = []

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> LoadedAtlas:
        self.open_requests.append((atlas_name, package_version, allow_download))
        if self.fail_open:
            self.open_calls += 1
            self.last_package_version = package_version
            self.last_allow_download = allow_download
            raise FileNotFoundError("synthetic missing cached recovery atlas")
        return super().open(
            atlas_name,
            package_version=package_version,
            allow_download=allow_download,
            progress=progress,
            cancel=cancel,
        )


class SlowRecoveryRepository(RecoveryRepository):
    """Keep a recovery open until the GUI cancellation event reaches the worker."""

    def __init__(self, atlas: FakeLoadedAtlas) -> None:
        super().__init__(atlas)
        self.started = False

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> LoadedAtlas:
        self.open_requests.append((atlas_name, package_version, allow_download))
        self.open_calls += 1
        self.started = True
        for completed in range(1, 1001):
            if cancel is not None and cancel():
                raise AtlasDownloadCancelledError("cancelled recovery atlas")
            if progress is not None:
                progress(completed, 1000)
            time.sleep(0.001)
        return cast(LoadedAtlas, self.atlas)


class SlowCancelableRepository(FakeRepository):
    """Worker test double that stays active until cancellation is observed."""

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> LoadedAtlas:
        assert atlas_name == self.atlas.metadata.atlas_key
        self.last_package_version = package_version
        self.last_allow_download = allow_download
        for completed in range(1, 501):
            if cancel is not None and cancel():
                raise AtlasDownloadCancelledError("cancelled test atlas")
            if progress is not None:
                progress(completed, 500)
            time.sleep(0.001)
        return cast(LoadedAtlas, self.atlas)


def prepare_test_mesh(
    atlas: FakeLoadedAtlas,
    mesh: pv.DataSet | None = None,
    *,
    anchor: BrainGlobePhysicalPoint | None = None,
) -> PreparedWorldMesh:
    """Prepare deterministic test geometry through the production handoff."""

    space = BrainGlobeAtlasSpace(atlas.metadata)
    renderer_anchor = anchor or center_voxel_anchor(space)
    return prepare_world_mesh(
        mesh if mesh is not None else pv.Sphere(theta_resolution=8, phi_resolution=8),
        space,
        renderer_anchor,
    )


def make_loaded_payload(
    atlas: FakeLoadedAtlas,
    *,
    anchor: BrainGlobePhysicalPoint | None = None,
) -> LoadedAtlasPayload:
    return LoadedAtlasPayload(
        atlas=cast(LoadedAtlas, atlas),
        root_mesh=prepare_test_mesh(atlas, anchor=anchor),
    )


def install_fake_atlas_window(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> MainWindow:
    """Install the deterministic atlas without allocating a native VTK window."""

    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    atlas = FakeLoadedAtlas(tmp_path)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window._install_loaded_atlas(make_loaded_payload(atlas), restoring=False)
    return window


def non_center_point(
    atlas: FakeLoadedAtlas,
    voxel_coordinates: tuple[float, float, float],
) -> BrainGlobePhysicalPoint:
    """Return an exact physical point that is deliberately not a voxel center."""

    resolution = atlas.metadata.resolution_um
    return BrainGlobePhysicalPoint(
        atlas_key=atlas.metadata.atlas_key,
        atlas_version=atlas.metadata.atlas_package_version,
        ap_um=voxel_coordinates[0] * resolution[0],
        dv_um=voxel_coordinates[1] * resolution[1],
        ml_um=voxel_coordinates[2] * resolution[2],
    )


def active_atlas_replacement_fixture(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_recovery: bool,
) -> tuple[
    MainWindow,
    FakeLoadedAtlas,
    FakeLoadedAtlas,
    RecoveryRepository,
    PlannerProject,
    Path,
    Path,
]:
    """Build a dirty atlas-A workspace and a distinct replacement payload source."""

    atlas_a_dir = tmp_path / "atlas-a"
    atlas_b_dir = tmp_path / "atlas-b"
    atlas_a_dir.mkdir()
    atlas_b_dir.mkdir()
    atlas_a = FakeLoadedAtlas(atlas_a_dir, isotropic_resolution_um=25.0)
    atlas_b = FakeLoadedAtlas(atlas_b_dir, isotropic_resolution_um=25.0)
    repository = RecoveryRepository(atlas_a, fail_open=fail_recovery)
    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    window = MainWindow(
        no_download=False,
        suppress_dialogs=True,
        repository=repository,
    )
    qtbot.addWidget(window)
    window._install_loaded_atlas(make_loaded_payload(atlas_a), restoring=False)

    exact_cursor = non_center_point(atlas_a, (1.2, 2.3, 3.4))
    cursor_index = BrainGlobeAtlasSpace(atlas_a.metadata).physical_to_index(exact_cursor)
    window._set_cursor_voxel(
        cursor_index.ap,
        cursor_index.dv,
        cursor_index.ml,
        exact_physical=exact_cursor,
        record_change=False,
    )
    window._set_region_display(3, opacity=0.42, custom_rgb=(7, 8, 9))
    window._select_region(window._region_by_id[3], record_change=False)
    project_path = tmp_path / "working.mouseplan"
    source_path = tmp_path / "source.mouseplan"
    window.project_path = project_path
    window._project_source_path = source_path
    window._set_dirty(True)
    window._update_project_ui()
    return (
        window,
        atlas_a,
        atlas_b,
        repository,
        window.project.model_copy(deep=True),
        project_path,
        source_path,
    )


def test_atlas_dialog_only_exposes_supported_25um_v1_2_in_no_download_mode(
    qtbot: QtBot,
) -> None:
    records = [
        AtlasCatalogRecord("allen_mouse_10um", "1.2", True),
        AtlasCatalogRecord("allen_mouse_25um", "1.1", True),
        AtlasCatalogRecord(SUPPORTED_ATLAS_NAME, SUPPORTED_ATLAS_VERSION, False),
    ]
    dialog = AtlasSelectionDialog(records, no_download=True)
    qtbot.addWidget(dialog)

    assert isinstance(dialog.atlas_choice, QRadioButton)
    assert not hasattr(dialog, "atlas_tree")
    assert not hasattr(dialog, "atlas_model")
    assert SUPPORTED_ATLAS_NAME in dialog.atlas_choice.text()
    assert SUPPORTED_ATLAS_VERSION in dialog.atlas_choice.text()
    assert not dialog.atlas_choice.isEnabled()
    assert not dialog.atlas_choice.isChecked()
    assert dialog.atlas_key_value.text() == SUPPORTED_ATLAS_NAME
    assert dialog.atlas_version_value.text() == SUPPORTED_ATLAS_VERSION
    assert dialog.atlas_cache_value.text() == "download required"
    assert dialog.atlas_raw_size_value.text() == format_bytes(SUPPORTED_ATLAS_RAW_VOLUME_BYTES)
    assert dialog.selected_record is None
    assert "not available in the local BrainGlobe cache" in dialog.catalog_message.text()
    assert "10 µm" not in dialog.memory_warning.text()
    assert dialog.download_context.isHidden()


def test_atlas_dialog_requires_explicit_choice_after_native_show(qtbot: QtBot) -> None:
    record = AtlasCatalogRecord("allen_mouse_25um", "1.2", True)
    dialog = AtlasSelectionDialog([record], no_download=True)
    qtbot.addWidget(dialog)

    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    qtbot.wait(10)

    open_button = dialog.buttons.button(QDialogButtonBox.StandardButton.Open)
    assert dialog.selected_record is None
    assert not dialog.atlas_choice.isChecked()
    assert open_button is not None and not open_button.isEnabled()


def test_atlas_dialog_shows_25um_only_memory_warning_and_links_terms(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(atlas_selection_module, "system_memory_bytes", lambda: 16 * 1024**3)
    monkeypatch.setattr(
        atlas_selection_module,
        "system_available_memory_bytes",
        lambda: 256 * 1024**2,
    )
    record = AtlasCatalogRecord(SUPPORTED_ATLAS_NAME, SUPPORTED_ATLAS_VERSION, False)
    dialog = AtlasSelectionDialog([record], no_download=False)
    qtbot.addWidget(dialog)

    dialog.atlas_choice.setChecked(True)

    warning = dialog.memory_warning.text()
    assert f"{SUPPORTED_ATLAS_NAME} v{SUPPORTED_ATLAS_VERSION}" in warning
    assert format_bytes(SUPPORTED_ATLAS_RAW_VOLUME_BYTES) in warning
    assert "required raw arrays exceed the currently available memory estimate" in warning
    assert "256.0 MiB" in warning
    assert "10 µm" not in warning
    assert "sagittal" not in warning.casefold()
    assert not hasattr(dialog, "atlas_tree")
    assert not hasattr(dialog, "atlas_model")
    assert dialog.atlas_key_value.text() == SUPPORTED_ATLAS_NAME
    assert dialog.atlas_version_value.text() == SUPPORTED_ATLAS_VERSION
    assert dialog.atlas_cache_value.text() == "download required"
    assert dialog.atlas_raw_size_value.text() == format_bytes(SUPPORTED_ATLAS_RAW_VOLUME_BYTES)
    assert not hasattr(dialog, "disk_cache_warning")
    assert not dialog.download_context.isHidden()
    assert dialog.download_context.openExternalLinks()
    context = dialog.download_context.text()
    assert "https://gin.g-node.org/brainglobe/atlases" in context
    assert "https://doi.org/10.1016/j.cell.2020.04.007" in context
    assert "https://alleninstitute.org/legal/citation-policy" in context
    assert "https://alleninstitute.org/legal/terms-of-use" in context


def test_available_memory_estimate_uses_bounded_macos_pressure_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        commands.append(command)
        assert kwargs["timeout"] == 1.0
        return atlas_selection_module.subprocess.CompletedProcess(
            command,
            0,
            "System-wide memory free percentage: 25%\n",
            "",
        )

    monkeypatch.setattr(atlas_selection_module.sys, "platform", "darwin")
    monkeypatch.setattr(atlas_selection_module, "system_memory_bytes", lambda: 16 * 1024**3)
    monkeypatch.setattr(atlas_selection_module.subprocess, "run", fake_run)

    assert atlas_selection_module.system_available_memory_bytes() == 4 * 1024**3
    assert commands == [["/usr/bin/memory_pressure", "-Q"]]


def test_empty_no_download_catalog_explains_how_to_continue(qtbot: QtBot) -> None:
    dialog = AtlasSelectionDialog([], no_download=True)
    qtbot.addWidget(dialog)

    assert isinstance(dialog.atlas_choice, QRadioButton)
    assert dialog.atlas_choice_panel.isHidden()
    assert not dialog.atlas_choice.isEnabled()
    assert not dialog.atlas_choice.isChecked()
    assert f"{SUPPORTED_ATLAS_NAME} v{SUPPORTED_ATLAS_VERSION}" in (dialog.catalog_message.text())
    assert "not available in the local BrainGlobe cache" in dialog.catalog_message.text()
    assert "--no-download" in dialog.catalog_message.text()
    assert dialog.atlas_choice.accessibleName() == "Allen mouse 25 micrometer atlas choice"


def test_catalog_selection_preserves_exact_advertised_package_version(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = AtlasCatalogRecord("allen_mouse_25um", "1.2", True)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    begin_calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        window,
        "_begin_atlas_load",
        lambda name, **kwargs: begin_calls.append((name, kwargs.get("package_version"))),
    )

    window._show_atlas_selection([record])
    dialog = window._atlas_selection_dialog
    assert dialog is not None
    dialog.atlas_choice.setChecked(True)
    accessible = QAccessible.queryAccessibleInterface(dialog.atlas_choice)
    assert accessible.role() is QAccessible.Role.RadioButton
    assert accessible.childCount() == 0
    assert accessible.selectionInterface() is None
    assert accessible.interface_cast(QAccessible.InterfaceType.TableInterface) is None
    assert accessible.tableCellInterface() is None
    pending_accessible = [QAccessible.queryAccessibleInterface(dialog)]
    dialog_roles: list[QAccessible.Role] = []
    while pending_accessible:
        current_accessible = pending_accessible.pop()
        dialog_roles.append(current_accessible.role())
        for child_index in range(current_accessible.childCount()):
            child_accessible = current_accessible.child(child_index)
            if child_accessible is not None:
                pending_accessible.append(child_accessible)
    assert QAccessible.Role.Table not in dialog_roles
    assert QAccessible.Role.Cell not in dialog_roles
    dialog.accept()
    qtbot.waitUntil(lambda: window._atlas_selection_dialog is None)

    assert begin_calls == [("allen_mouse_25um", "1.2")]
    assert dialog in window._retired_atlas_dialogs
    assert dialog.isHidden()
    assert dialog.parent() is window
    assert dialog.accepted_record == record
    assert dialog.selected_record is None
    assert not dialog.atlas_choice.isChecked()
    retired_accessible = QAccessible.queryAccessibleInterface(dialog.atlas_choice)
    assert retired_accessible.selectionInterface() is None
    assert retired_accessible.interface_cast(QAccessible.InterfaceType.TableInterface) is None
    assert retired_accessible.tableCellInterface() is None


def test_atlas_restore_identity_is_fail_closed_over_scientific_metadata(tmp_path: Path) -> None:
    expected = make_small_asr_metadata(tmp_path / "original-cache")
    relocated = expected.model_copy(update={"cache_path": str(tmp_path / "relocated-cache")})
    changed_midline = expected.model_copy(
        update={
            "symmetric": False,
            "midline_ml_um": 800.0,
        }
    )

    assert MainWindow._same_atlas_identity(expected, relocated)
    assert not MainWindow._same_atlas_identity(expected, changed_midline)
    assert not MainWindow._same_atlas_identity(
        expected,
        expected.model_copy(update={"source_annotation": "different-framework"}),
    )


def test_catalog_dialog_rejection_is_nonblocking_and_clears_ownership(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = AtlasCatalogRecord("allen_mouse_25um", "1.2", True)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    begin_calls: list[str] = []
    monkeypatch.setattr(
        window,
        "_begin_atlas_load",
        lambda name, **kwargs: begin_calls.append(name),
    )

    window._show_atlas_selection([record])
    dialog = window._atlas_selection_dialog
    assert dialog is not None
    dialog.atlas_choice.setChecked(True)
    dialog.reject()
    qtbot.waitUntil(lambda: window._atlas_selection_dialog is None)

    assert begin_calls == []
    assert dialog.accepted_record is None
    assert dialog.selected_record is None
    assert not dialog.atlas_choice.isChecked()


def test_workers_return_validated_mesh_payloads(qtbot: QtBot, tmp_path: Path) -> None:
    atlas = FakeLoadedAtlas(tmp_path)
    repository = FakeRepository(atlas)
    catalog_worker = AtlasCatalogWorker(repository)
    load_worker = AtlasLoadWorker(repository, "allen_mouse_25um")
    region_worker = RegionMeshWorker(
        cast(LoadedAtlas, atlas),
        2,
        renderer_anchor=center_voxel_anchor(BrainGlobeAtlasSpace(atlas.metadata)),
    )

    with qtbot.waitSignal(catalog_worker.succeeded, timeout=1000) as catalog_signal:
        catalog_worker.run()
    with qtbot.waitSignal(load_worker.succeeded, timeout=1000) as load_signal:
        load_worker.run()
    with qtbot.waitSignal(region_worker.succeeded, timeout=1000) as region_signal:
        region_worker.run()

    assert catalog_signal.args == [repository.list_atlases()]
    loaded_payload = load_signal.args[0]
    assert isinstance(loaded_payload, LoadedAtlasPayload)
    assert loaded_payload.root_mesh.mesh.n_points > 0
    region_payload = region_signal.args[0]
    assert isinstance(region_payload, RegionMeshPayload)
    assert region_payload.structure_id == 2
    assert region_payload.mesh.mesh.n_cells > 0


def test_main_window_no_download_catalog_is_local_only(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeRepository(FakeLoadedAtlas(tmp_path))
    window = MainWindow(
        no_download=True,
        suppress_dialogs=True,
        repository=repository,
    )
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_show_atlas_selection", lambda records: None)

    window.select_atlas()
    qtbot.waitUntil(lambda: not window._active_threads, timeout=2000)

    assert repository.last_catalog_local_only is True


def test_worker_passes_no_download_policy_to_repository_open_boundary(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    repository = FakeRepository(FakeLoadedAtlas(tmp_path))
    worker = AtlasLoadWorker(
        repository,
        "allen_mouse_25um",
        allow_download=False,
        package_version="9.9",
    )

    with qtbot.waitSignal(worker.failed, timeout=1000) as failed_signal:
        worker.run()

    assert "downloads are disabled" in failed_signal.args[0]
    assert repository.open_calls == 1
    assert repository.last_package_version == "9.9"
    assert repository.last_allow_download is False


def test_loaded_atlas_installs_linked_views_and_region_tree(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_anchors: list[BrainGlobePhysicalPoint] = []

    def capture_anchor(
        view: Brain3DView,
        *args: object,
        anchor: BrainGlobePhysicalPoint,
        **kwargs: object,
    ) -> None:
        del view, args, kwargs
        loaded_anchors.append(anchor)

    monkeypatch.setattr(Brain3DView, "load_atlas", capture_anchor)
    atlas = FakeLoadedAtlas(tmp_path)
    window = MainWindow(
        no_download=True,
        suppress_dialogs=True,
        repository=FakeRepository(atlas),
    )
    qtbot.addWidget(window)
    payload = make_loaded_payload(atlas)

    window.project_dock.setFloating(True)
    window.project_dock.hide()
    window._install_loaded_atlas(payload, restoring=False)
    window.show()

    assert not window.project_dock.isFloating()
    assert window.dockWidgetArea(window.project_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.project_dock.isVisibleTo(window)
    assert len(window._slice_views) == 6
    assert all(view.cursor_voxel == (2, 2, 3) for view in window._slice_views)
    window._slice_views[0].slice_slider.setValue(1)
    assert all(view.cursor_voxel == (1, 2, 3) for view in window._slice_views)
    assert "A→P 150.0" in window.atlas_coordinate_status.text()
    assert window.project.selected_region_id == 2
    assert window._region_items[2].text() == "CA1"
    assert window.project.renderer_anchor is not None
    assert loaded_anchors[:2] == [window.project.renderer_anchor] * 2

    window.region_search.setText("field ca1")
    assert not window._region_item_is_hidden(window._region_items[2])
    assert not window._region_item_is_hidden(window._region_items[1])
    for query, structure_id in (("ADN", 3), ("RSC", 4), ("MEC", 5)):
        window.region_search.setText(query)
        assert not window._region_item_is_hidden(window._region_items[structure_id])

    saved_cursor = window.project.linked_cursor
    saved_anchor = window.project.renderer_anchor
    window._select_region(window._region_by_id[3])
    saved_selection = window.project.selected_region_id
    project_path = tmp_path / "linked-view-round-trip.mouseplan"
    window._save_to(project_path)
    window.new_project()
    window.open_project(project_path)
    qtbot.waitUntil(
        lambda: window._loaded_atlas is not None and not window._active_threads,
        timeout=3000,
    )
    assert window.project.linked_cursor == saved_cursor
    assert window.project.renderer_anchor == saved_anchor
    assert loaded_anchors[-2:] == [saved_anchor] * 2
    assert window.project.selected_region_id == saved_selection == 3
    assert window._current_region_item() is window._region_items[3]
    assert all(view.cursor_voxel == (1, 2, 3) for view in window._slice_views)


def test_replacement_clears_stale_atlas_region_state_before_building_tree(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    atlas = FakeLoadedAtlas(tmp_path)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    payload = make_loaded_payload(atlas)

    window._install_loaded_atlas(payload, restoring=False)
    window._set_region_display(3, visible=True, custom_rgb=(1, 2, 3))
    window._install_loaded_atlas(payload, restoring=False)

    assert window.project.region_display == []
    assert window._region_items[3].checkState() == window._region_items[2].checkState()
    assert window._region_items[3].checkState() is Qt.CheckState.Unchecked


def test_restore_uses_one_persisted_renderer_anchor_for_both_3d_views(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    atlas = FakeLoadedAtlas(tmp_path)
    loaded_anchors: list[BrainGlobePhysicalPoint] = []

    def capture_anchor(
        view: Brain3DView,
        *args: object,
        anchor: BrainGlobePhysicalPoint,
        **kwargs: object,
    ) -> None:
        del view, args, kwargs
        loaded_anchors.append(anchor)

    monkeypatch.setattr(Brain3DView, "load_atlas", capture_anchor)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    persisted_anchor = BrainGlobePhysicalPoint(
        atlas_key=atlas.metadata.atlas_key,
        atlas_version=atlas.metadata.atlas_package_version,
        ap_um=50.0,
        dv_um=100.0,
        ml_um=150.0,
    )
    window.project = PlannerProject(
        atlas=atlas.metadata,
        renderer_anchor=persisted_anchor,
    )

    window._install_loaded_atlas(
        make_loaded_payload(atlas, anchor=persisted_anchor),
        restoring=True,
    )

    assert window.project.renderer_anchor == persisted_anchor
    assert loaded_anchors == [persisted_anchor] * 2
    assert (
        "Renderer/world origin: ASR µm [50, 100, 150] (not bregma)"
        in window.inspector_atlas_details.toPlainText()
    )
    assert not window._dirty


def test_restore_rejects_unknown_structure_ids_with_actionable_error(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    atlas = FakeLoadedAtlas(tmp_path)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window.project = PlannerProject(
        atlas=atlas.metadata,
        renderer_anchor=BrainGlobePhysicalPoint(
            atlas_key=atlas.metadata.atlas_key,
            atlas_version=atlas.metadata.atlas_package_version,
            ap_um=50.0,
            dv_um=100.0,
            ml_um=150.0,
        ),
        selected_region_id=999,
        region_display=[RegionDisplayState(structure_id=888, visible=True)],
    )
    window._expected_atlas = atlas.metadata
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        window,
        "_show_error",
        lambda title, message: errors.append((title, message)),
    )
    payload = make_loaded_payload(atlas, anchor=window.project.renderer_anchor)

    window._on_atlas_loaded(payload, window._load_token)

    assert window._loaded_atlas is None
    assert errors and errors[0][0] == "Atlas setup failed"
    assert "structure IDs" in errors[0][1]
    assert "888, 999" in errors[0][1]
    assert "Verify the atlas package/version" in errors[0][1]
    assert window._atlas_recovery is None
    assert window._atlas_recovery_load_token is None
    assert window.atlas_status.text().startswith("Atlas unavailable:")
    assert window.rendering_status.text() == "Rendering: atlas setup failed"
    assert window.select_atlas_action.isEnabled()


def test_background_selection_clears_tree_and_records_project_change(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    atlas = FakeLoadedAtlas(tmp_path)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window._install_loaded_atlas(make_loaded_payload(atlas), restoring=False)
    window._set_dirty(False)

    window._select_region(None)

    assert window.project.selected_region_id is None
    assert not window.region_tree.currentIndex().isValid()
    selection_model = window.region_tree.selectionModel()
    assert selection_model is not None and selection_model.selectedRows() == []
    assert window._dirty
    assert window.project.event_log[-1].action == "region-selected"


def test_non_center_3d_picks_preserve_exact_physical_cursor_for_25um(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crosshairs: list[BrainGlobePhysicalPoint] = []

    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        Brain3DView,
        "set_crosshair",
        lambda _view, point: crosshairs.append(point),
    )
    atlas = FakeLoadedAtlas(tmp_path, isotropic_resolution_um=25.0)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window._install_loaded_atlas(make_loaded_payload(atlas), restoring=False)
    crosshairs.clear()
    space = BrainGlobeAtlasSpace(atlas.metadata)

    root_point = non_center_point(atlas, (1.23, 2.34, 3.45))
    window.brain_3d_view.physical_point_picked.emit(root_point)

    assert window.project.linked_cursor == root_point
    assert all(view.cursor_voxel == (1, 2, 3) for view in window._slice_views)
    assert crosshairs == [root_point, root_point]
    assert window.atlas_coordinate_status.text() == (
        "Atlas ASR µm: "
        f"A→P {root_point.ap_um:.1f}, S→I {root_point.dv_um:.1f}, "
        f"R→L {root_point.ml_um:.1f}"
    )
    assert window.inspector_coordinate.text() == (
        f"ASR µm [{root_point.ap_um:.3f}, {root_point.dv_um:.3f}, "
        f"{root_point.ml_um:.3f}]\ncontaining voxel index [1, 2, 3]"
    )
    assert window.project.event_log[-1].details == (
        f"ASR µm [{root_point.ap_um}, {root_point.dv_um}, {root_point.ml_um}], "
        "containing voxel [1, 2, 3], region 2"
    )
    assert root_point != space.index_to_center(space.physical_to_index(root_point))

    actor_point = non_center_point(atlas, (2.37, 1.11, 4.73))
    crosshairs.clear()
    window.brain_3d_view.region_picked.emit(1, actor_point)

    assert window.project.linked_cursor == actor_point
    assert window.project.selected_region_id == 1
    assert all(view.cursor_voxel == (2, 1, 4) for view in window._slice_views)
    assert crosshairs == [actor_point, actor_point]
    assert window.region_status.text() == "Region: root — Root structure"
    assert "containing voxel index [2, 1, 4]" in window.inspector_coordinate.text()

    window._slice_views[0].slice_slider.setValue(1)
    expected_center = space.index_to_center(
        BrainGlobeVoxelIndex(
            atlas_key=atlas.metadata.atlas_key,
            atlas_version=atlas.metadata.atlas_package_version,
            ap=1,
            dv=1,
            ml=4,
        )
    )
    assert window.project.linked_cursor == expected_center
    assert all(view.cursor_voxel == (1, 1, 4) for view in window._slice_views)


def test_non_center_cursor_survives_25um_project_save_and_reopen_without_drift(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crosshairs: list[BrainGlobePhysicalPoint] = []

    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        Brain3DView,
        "set_crosshair",
        lambda _view, point: crosshairs.append(point),
    )
    atlas = FakeLoadedAtlas(tmp_path, isotropic_resolution_um=25.0)
    window = MainWindow(
        no_download=True,
        suppress_dialogs=True,
        repository=FakeRepository(atlas),
    )
    qtbot.addWidget(window)
    window._install_loaded_atlas(make_loaded_payload(atlas), restoring=False)
    exact_point = non_center_point(atlas, (1.23456789, 2.34567891, 3.45678912))
    window.brain_3d_view.physical_point_picked.emit(exact_point)
    project_path = tmp_path / "non-center-25.mouseplan"

    assert window._save_to(project_path)
    assert window.new_project()
    crosshairs.clear()
    assert window.open_project(project_path)
    qtbot.waitUntil(
        lambda: window._loaded_atlas is not None and not window._active_threads,
        timeout=3000,
    )

    assert window.project.linked_cursor == exact_point
    assert window.project.linked_cursor is not None
    assert window.project.linked_cursor.as_tuple() == exact_point.as_tuple()
    assert all(view.cursor_voxel == (1, 2, 3) for view in window._slice_views)
    assert crosshairs[-2:] == [exact_point, exact_point]
    assert window.atlas_coordinate_status.text() == (
        "Atlas ASR µm: "
        f"A→P {exact_point.ap_um:.1f}, S→I {exact_point.dv_um:.1f}, "
        f"R→L {exact_point.ml_um:.1f}"
    )
    assert window.inspector_coordinate.text() == (
        f"ASR µm [{exact_point.ap_um:.3f}, {exact_point.dv_um:.3f}, "
        f"{exact_point.ml_um:.3f}]\ncontaining voxel index [1, 2, 3]"
    )


def test_invalid_defensively_constructed_restored_cursor_uses_center_fallback(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    atlas = FakeLoadedAtlas(tmp_path, isotropic_resolution_um=25.0)
    space = BrainGlobeAtlasSpace(atlas.metadata)
    center = center_voxel_anchor(space)
    project = PlannerProject(
        atlas=atlas.metadata,
        linked_cursor=center,
        renderer_anchor=center,
    )
    invalid = BrainGlobePhysicalPoint.model_construct(
        atlas_key=atlas.metadata.atlas_key,
        atlas_version=atlas.metadata.atlas_package_version,
        ap_um=atlas.metadata.extent_um[0],
        dv_um=0.0,
        ml_um=0.0,
        frame_id="BRAINGLOBE_PHYSICAL_ASR_UM",
    )
    object.__setattr__(project, "linked_cursor", invalid)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window.project = project

    window._install_loaded_atlas(
        make_loaded_payload(atlas, anchor=center),
        restoring=True,
    )

    assert window.project.linked_cursor == center
    expected_index = space.physical_to_index(center)
    assert all(view.cursor_voxel == expected_index.as_tuple() for view in window._slice_views)


def test_region_actor_pick_preserves_parent_identity_over_leaf_annotation(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = install_fake_atlas_window(qtbot, tmp_path, monkeypatch)
    metadata = window.project.atlas
    assert metadata is not None
    point = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=250.0,
        dv_um=500.0,
        ml_um=1050.0,
    )

    window.brain_3d_view.region_picked.emit(1, point)

    assert window.project.selected_region_id == 1
    assert window.project.linked_cursor == point
    assert window._current_region_item() is window._region_items[1]
    assert window.region_status.text() == "Region: root — Root structure"
    assert all(view._selected_region_ids == {1, 2, 3, 4, 5} for view in window._slice_views)


def test_region_tree_is_single_selection_model_view_and_color_can_reset(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = install_fake_atlas_window(qtbot, tmp_path, monkeypatch)

    assert isinstance(window.region_tree, QTreeView)
    assert isinstance(window.region_model, QStandardItemModel)
    assert window.region_tree.selectionMode() is QAbstractItemView.SelectionMode.SingleSelection
    assert window.region_tree.accessibleName() == "Atlas brain region hierarchy"
    window._select_region(window._region_by_id[1])
    assert all(view._selected_region_ids == {1, 2, 3, 4, 5} for view in window._slice_views)
    window._select_region(window._region_by_id[3])
    selection_model = window.region_tree.selectionModel()
    assert selection_model is not None
    assert len(selection_model.selectedRows()) == 1

    window._set_region_display(3, custom_rgb=(1, 2, 3))
    window._select_region(window._region_by_id[3], update_tree=False, record_change=False)
    assert window.reset_region_color.isEnabled()
    window.reset_region_color.click()

    assert window._region_display_state(3).custom_rgb is None
    assert not window.reset_region_color.isEnabled()
    assert window.region_color.text() == "Source atlas color"
    assert window.project.event_log[-1].action == "region-color-reset"


def test_region_model_and_persistent_indices_survive_load_clear_and_reload(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window.show()
    initial_model = window.region_model
    initial_selection_model = window.region_tree.selectionModel()
    initial_view_buttons = window.viewer_tabs.view_buttons
    initial_view_pages = tuple(
        window.viewer_tabs.widget(index) for index in range(window.viewer_tabs.count())
    )

    def assert_stable_viewer_hierarchy() -> None:
        current_buttons = window.viewer_tabs.view_buttons
        current_pages = tuple(
            window.viewer_tabs.widget(index) for index in range(window.viewer_tabs.count())
        )
        assert len(current_buttons) == len(initial_view_buttons)
        assert len(current_pages) == len(initial_view_pages)
        assert all(
            current is initial
            for current, initial in zip(current_buttons, initial_view_buttons, strict=True)
        )
        assert all(
            current is initial
            for current, initial in zip(current_pages, initial_view_pages, strict=True)
        )

    placeholder = initial_model.item(0, 0)
    assert initial_model.rowCount() == 1
    assert placeholder is not None and placeholder.text() == "No atlas loaded"
    placeholder_index = QPersistentModelIndex(placeholder.index())

    atlas = FakeLoadedAtlas(tmp_path)
    payload = make_loaded_payload(atlas)
    window._install_loaded_atlas(payload, restoring=False)

    assert window.region_model is initial_model
    assert window.region_tree.selectionModel() is initial_selection_model
    assert_stable_viewer_hierarchy()
    assert initial_model.rowCount() == 2
    assert placeholder_index.isValid()
    assert initial_model.item(0, 0) is placeholder
    assert window.region_tree.isRowHidden(placeholder.row(), QModelIndex())
    assert window._current_region_item() is window._region_items[2]

    atlas_root = window._region_items[1]
    selected_item = window._region_items[3]
    selected_index = QPersistentModelIndex(selected_item.index())
    assert initial_selection_model is not None
    initial_selection_model.setCurrentIndex(
        selected_item.index(),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert window.project.selected_region_id == 3
    assert initial_selection_model.selectedRows()
    accessible = QAccessible.queryAccessibleInterface(window.region_tree)
    accessible_selection = accessible.selectionInterface()
    assert accessible_selection is not None
    assert len(accessible_selection.selectedItems()) == initial_model.columnCount()
    window._set_region_display(3, visible=True, custom_rgb=(1, 2, 3))
    event_count = len(window.project.event_log)

    window._clear_loaded_atlas()

    assert window.region_model is initial_model
    assert window.region_tree.selectionModel() is initial_selection_model
    assert_stable_viewer_hierarchy()
    assert initial_model.rowCount() == 2
    assert placeholder_index.isValid()
    assert selected_index.isValid()
    assert selected_index.data() == "AD"
    assert not window.region_tree.isRowHidden(placeholder.row(), QModelIndex())
    assert window.region_tree.isRowHidden(atlas_root.row(), QModelIndex())
    assert initial_selection_model.selectedRows() == []
    assert not initial_selection_model.currentIndex().isValid()
    selected_item.setCheckState(Qt.CheckState.Unchecked)
    initial_selection_model.setCurrentIndex(
        selected_item.index(),
        QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )
    assert window.project.selected_region_id == 3
    assert window._region_display_state(3).visible
    assert len(window.project.event_log) == event_count

    window._install_loaded_atlas(payload, restoring=True)

    assert window.region_model is initial_model
    assert window.region_tree.selectionModel() is initial_selection_model
    assert_stable_viewer_hierarchy()
    assert initial_model.rowCount() == 2
    assert placeholder_index.isValid()
    assert selected_index.isValid()
    assert window._region_items[3] is selected_item
    assert selected_index == QPersistentModelIndex(selected_item.index())
    assert selected_item.checkState() is Qt.CheckState.Checked
    assert window.project.selected_region_id == 3
    assert window._current_region_item() is selected_item
    assert window.region_tree.isRowHidden(placeholder.row(), QModelIndex())


def test_parent_hide_retires_accessibility_state_without_project_mutation(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = install_fake_atlas_window(qtbot, tmp_path, monkeypatch)
    region = window._region_by_id[3]
    window._select_region(region, record_change=False)
    selected_region_id = window.project.selected_region_id

    record = AtlasCatalogRecord("allen_mouse_25um", "1.2", True)
    window._show_atlas_selection([record])
    dialog = window._atlas_selection_dialog
    assert dialog is not None
    dialog.atlas_choice.setChecked(True)

    region_accessible = QAccessible.queryAccessibleInterface(window.region_tree)
    dialog_accessible = QAccessible.queryAccessibleInterface(dialog.atlas_choice)
    assert region_accessible.selectionInterface().selectedItems()
    assert dialog.selected_record == record
    assert dialog_accessible.selectionInterface() is None
    assert dialog_accessible.interface_cast(QAccessible.InterfaceType.TableInterface) is None
    assert dialog_accessible.tableCellInterface() is None

    window._retire_accessibility_selections()

    assert window.project.selected_region_id == selected_region_id
    assert region_accessible.selectionInterface().selectedItems() == []
    assert dialog_accessible.selectionInterface() is None
    assert not window.region_tree.currentIndex().isValid()
    assert not dialog.atlas_choice.isChecked()
    assert dialog.selected_record is None


def test_concurrent_region_mesh_status_failure_rollback_and_center_action(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = install_fake_atlas_window(qtbot, tmp_path, monkeypatch)
    monkeypatch.setattr(window, "_launch_worker", lambda *args, **kwargs: None)
    centered: list[tuple[Brain3DView, int]] = []

    def center(view: Brain3DView, structure_id: int) -> bool:
        centered.append((view, structure_id))
        return True

    monkeypatch.setattr(Brain3DView, "center_region", center)
    item_2 = window._region_items[2]
    item_3 = window._region_items[3]

    item_2.setCheckState(Qt.CheckState.Checked)
    item_3.setCheckState(Qt.CheckState.Checked)
    assert window._region_meshes_loading == {2, 3}
    assert window.rendering_status.text() == "Rendering: loading 2 region meshes…"

    window._on_region_mesh_loaded(
        RegionMeshPayload(2, prepare_test_mesh(cast(FakeLoadedAtlas, window._loaded_atlas))),
        window._load_token,
    )
    assert window._region_meshes_loading == {3}
    assert window.rendering_status.text() == "Rendering: loading 1 region mesh…"
    assert window.center_action.isEnabled()
    window.center_action.trigger()
    assert centered == [(window.brain_3d_view, 2)]

    window._on_region_mesh_failed(3, "synthetic region failure", window._load_token)
    assert window._region_meshes_loading == set()
    assert item_3.checkState() is Qt.CheckState.Unchecked
    assert not window._region_display_state(3).visible
    assert "region 3 mesh failed" in window.rendering_status.text()
    assert window.project.event_log[-1].action == "region-visibility-rollback"

    item_2.setCheckState(Qt.CheckState.Unchecked)
    assert not window.center_action.isEnabled()
    assert 2 not in window._region_meshes

    item_2.setCheckState(Qt.CheckState.Checked)
    item_2.setCheckState(Qt.CheckState.Unchecked)
    assert 2 in window._region_meshes_loading
    window._on_region_mesh_loaded(
        RegionMeshPayload(2, prepare_test_mesh(cast(FakeLoadedAtlas, window._loaded_atlas))),
        window._load_token,
    )
    assert 2 not in window._region_meshes
    assert window._region_meshes_loading == set()


def test_camera_commands_target_only_the_active_3d_tab(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = install_fake_atlas_window(qtbot, tmp_path, monkeypatch)
    reset_calls: list[Brain3DView] = []
    center_calls: list[tuple[Brain3DView, int]] = []
    preset_calls: list[tuple[Brain3DView, str]] = []
    monkeypatch.setattr(Brain3DView, "reset_camera", lambda view: reset_calls.append(view))
    monkeypatch.setattr(
        Brain3DView,
        "center_region",
        lambda view, structure_id: center_calls.append((view, structure_id)) or True,
    )
    monkeypatch.setattr(
        Brain3DView,
        "set_camera",
        lambda view, preset: preset_calls.append((view, preset)),
    )
    loaded_atlas = cast(FakeLoadedAtlas, window._loaded_atlas)
    window._region_meshes[2] = prepare_test_mesh(loaded_atlas)
    window._set_region_display(2, visible=True)
    window._select_region(window._region_by_id[2], record_change=False)

    window.viewer_tabs.setCurrentWidget(window.brain_3d_view)
    assert window.reset_camera_action.isEnabled()
    assert window.center_action.isEnabled()
    window.reset_camera_action.trigger()
    window.center_action.trigger()
    window.camera_preset_actions[0].trigger()

    four_panel = window._four_panel_brain
    assert four_panel is not None
    window.viewer_tabs.setCurrentWidget(window.four_panel_page)
    assert window.reset_camera_action.isEnabled()
    assert window.center_action.isEnabled()
    window.reset_camera_action.trigger()
    window.center_action.trigger()
    window.camera_preset_actions[0].trigger()

    window.viewer_tabs.setCurrentIndex(1)
    assert not window.reset_camera_action.isEnabled()
    assert not window.center_action.isEnabled()
    assert all(not action.isEnabled() for action in window.camera_preset_actions)
    window._reset_cameras()
    window._center_selected_region()
    window._set_cameras("anterior")

    assert reset_calls == [window.brain_3d_view, four_panel]
    assert center_calls == [(window.brain_3d_view, 2), (four_panel, 2)]
    assert preset_calls == [(window.brain_3d_view, "anterior"), (four_panel, "anterior")]


def test_second_3d_view_failure_disposes_transient_view_and_rolls_back(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    atlas = FakeLoadedAtlas(tmp_path)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    loaded_views: list[Brain3DView] = []
    disposed_views: list[Brain3DView] = []

    def fail_second_view(view: Brain3DView, *args: object, **kwargs: object) -> None:
        del args, kwargs
        loaded_views.append(view)
        if len(loaded_views) == 2:
            raise RuntimeError("synthetic second-view failure")

    monkeypatch.setattr(Brain3DView, "load_atlas", fail_second_view)
    monkeypatch.setattr(
        Brain3DView,
        "dispose",
        lambda view: disposed_views.append(view),
    )

    with pytest.raises(RuntimeError, match="second-view failure"):
        window._install_loaded_atlas(
            make_loaded_payload(atlas),
            restoring=False,
        )

    assert len(loaded_views) == 2
    assert loaded_views[1] in disposed_views
    assert window._loaded_atlas is None
    assert window._four_panel_brain is None
    assert window.project.atlas is None


def test_failed_active_atlas_replacement_restores_exact_previous_workspace_once(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        window,
        atlas_a,
        atlas_b,
        repository,
        previous_project,
        project_path,
        source_path,
    ) = active_atlas_replacement_fixture(
        qtbot,
        tmp_path,
        monkeypatch,
        fail_recovery=False,
    )
    previous_anchor = previous_project.renderer_anchor
    setup_calls: list[Brain3DView] = []
    failures = 0
    progress = QProgressDialog(window)
    progress.show()
    window._load_progress = progress

    def fail_replacement_once(
        view: Brain3DView,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal failures
        del args, kwargs
        setup_calls.append(view)
        if len(setup_calls) == 1:
            assert window._load_progress is None
            assert not progress.isVisible()
            assert progress in window._retired_load_progress
        if len(setup_calls) == 2:
            failures += 1
            raise RuntimeError("synthetic replacement setup failure")

    monkeypatch.setattr(Brain3DView, "load_atlas", fail_replacement_once)
    modal_errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        window,
        "_show_error",
        lambda title, message: modal_errors.append((title, message)),
    )

    window._on_atlas_loaded(make_loaded_payload(atlas_b), window._load_token)

    assert window._atlas_recovery is not None
    assert not window.select_atlas_action.isEnabled()
    assert window.atlas_status.text().startswith("Atlas: restoring")
    assert "Runtime state: restoring" in window.inspector_atlas_details.toPlainText()
    assert modal_errors == []
    qtbot.waitUntil(
        lambda: (
            window._atlas_recovery is None
            and window._loaded_atlas is atlas_a
            and not window._active_threads
        ),
        timeout=5000,
    )

    assert failures == 1
    assert len(setup_calls) == 4
    assert modal_errors == []
    assert repository.open_requests == [
        (atlas_a.metadata.atlas_key, atlas_a.metadata.atlas_package_version, False)
    ]
    assert repository.open_calls == 1
    assert window._loaded_atlas is atlas_a
    assert window._atlas_space is not None
    assert window._atlas_space.metadata == atlas_a.metadata
    assert window._slice_renderer is not None
    assert window._slice_renderer.shape == atlas_a.reference.shape
    assert len(window._slice_views) == 6
    assert len(window._brain_views) == 2
    assert window._four_panel_brain is not None
    assert set(window._region_items) == {1, 2, 3, 4, 5}
    assert window.region_model.rowCount() == 2
    assert window.project == previous_project
    assert window.project.project_uuid == previous_project.project_uuid
    assert window.project.atlas == atlas_a.metadata
    assert window.project.linked_cursor == previous_project.linked_cursor
    assert window.project.renderer_anchor == previous_anchor
    assert window.project.region_display == previous_project.region_display
    assert window.project.selected_region_id == 3
    assert window.project_path == project_path
    assert window._project_source_path == source_path
    assert window._dirty and window.isWindowModified()
    assert window.select_atlas_action.isEnabled()
    assert window.rendering_status.text() == "Rendering: ready"
    assert window._atlas_unavailable_reason is None


def test_failed_previous_atlas_compensation_stops_unavailable_without_retry(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        window,
        atlas_a,
        atlas_b,
        repository,
        previous_project,
        project_path,
        source_path,
    ) = active_atlas_replacement_fixture(
        qtbot,
        tmp_path,
        monkeypatch,
        fail_recovery=True,
    )
    setup_calls = 0

    def fail_replacement_once(
        _view: Brain3DView,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal setup_calls
        del args, kwargs
        setup_calls += 1
        if setup_calls == 2:
            raise RuntimeError("synthetic replacement setup failure")

    monkeypatch.setattr(Brain3DView, "load_atlas", fail_replacement_once)
    modal_errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        window,
        "_show_error",
        lambda title, message: modal_errors.append((title, message)),
    )

    window._on_atlas_loaded(make_loaded_payload(atlas_b), window._load_token)
    qtbot.waitUntil(
        lambda: window._atlas_recovery is None and not window._active_threads,
        timeout=5000,
    )

    assert setup_calls == 2
    assert repository.open_requests == [
        (atlas_a.metadata.atlas_key, atlas_a.metadata.atlas_package_version, False)
    ]
    assert repository.open_calls == 1
    qtbot.wait(50)
    assert repository.open_calls == 1
    assert modal_errors == []
    assert window._loaded_atlas is None
    assert window._atlas_space is None
    assert window._slice_renderer is None
    assert window._slice_views == []
    assert window._four_panel_brain is None
    assert window._brain_views == [window.brain_3d_view]
    no_atlas_item = window.region_model.item(0, 0)
    assert no_atlas_item is not None and no_atlas_item.text() == "No atlas loaded"
    assert window.project == previous_project
    assert window.project.atlas == atlas_a.metadata
    assert window.project_path == project_path
    assert window._project_source_path == source_path
    assert window._dirty and window.isWindowModified()
    assert window.atlas_status.text().startswith("Atlas unavailable:")
    assert window.inspector_atlas.text().endswith("— unavailable")
    assert "Runtime state: unavailable" in window.inspector_atlas_details.toPlainText()
    assert window.rendering_status.text() == "Rendering: previous atlas unavailable"
    assert window.select_atlas_action.isEnabled()
    assert window._atlas_recovery_load_token is None


def test_invalidation_between_recovery_schedule_and_start_cannot_reload(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, _atlas_a, atlas_b, repository, *_rest = active_atlas_replacement_fixture(
        qtbot,
        tmp_path,
        monkeypatch,
        fail_recovery=False,
    )
    setup_calls = 0

    def fail_replacement_once(*args: object, **kwargs: object) -> None:
        nonlocal setup_calls
        del args, kwargs
        setup_calls += 1
        if setup_calls == 2:
            raise RuntimeError("synthetic replacement setup failure")

    monkeypatch.setattr(Brain3DView, "load_atlas", fail_replacement_once)
    scheduled: list[Callable[[], None]] = []
    monkeypatch.setattr(
        QTimer,
        "singleShot",
        lambda _delay, callback: scheduled.append(callback),
    )
    modal_errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        window,
        "_show_error",
        lambda title, message: modal_errors.append((title, message)),
    )

    window._on_atlas_loaded(make_loaded_payload(atlas_b), window._load_token)
    assert len(scheduled) == 1
    assert window._atlas_recovery is not None

    window._closing = True
    window._invalidate_async_callbacks()
    scheduled[0]()

    assert window._atlas_recovery is None
    assert window._atlas_recovery_load_token is None
    assert repository.open_calls == 0
    assert modal_errors == []


def test_cancelled_recovery_stops_once_in_explicit_unavailable_state(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, atlas_a, atlas_b, _repository, *_rest = active_atlas_replacement_fixture(
        qtbot,
        tmp_path,
        monkeypatch,
        fail_recovery=False,
    )
    slow_repository = SlowRecoveryRepository(atlas_a)
    window._repository_instance = slow_repository
    setup_calls = 0

    def fail_replacement_once(*args: object, **kwargs: object) -> None:
        nonlocal setup_calls
        del args, kwargs
        setup_calls += 1
        if setup_calls == 2:
            raise RuntimeError("synthetic replacement setup failure")

    monkeypatch.setattr(Brain3DView, "load_atlas", fail_replacement_once)
    modal_errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        window,
        "_show_error",
        lambda title, message: modal_errors.append((title, message)),
    )

    window._on_atlas_loaded(make_loaded_payload(atlas_b), window._load_token)
    qtbot.waitUntil(
        lambda: slow_repository.started and window._atlas_recovery_load_token is not None,
        timeout=3000,
    )
    window._cancel_atlas_load()
    qtbot.waitUntil(
        lambda: window._atlas_recovery is None and not window._active_threads,
        timeout=3000,
    )

    assert slow_repository.open_calls == 1
    qtbot.wait(25)
    assert slow_repository.open_calls == 1
    assert window._loaded_atlas is None
    assert window.atlas_status.text().startswith("Atlas unavailable:")
    assert window.rendering_status.text() == "Rendering: previous atlas unavailable"
    assert window.select_atlas_action.isEnabled()
    assert window._atlas_recovery_load_token is None
    assert modal_errors == []


def test_stale_replacement_and_recovery_callbacks_cannot_clear_newer_live_atlas(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, atlas_a, atlas_b, _repository, *_rest = active_atlas_replacement_fixture(
        qtbot,
        tmp_path,
        monkeypatch,
        fail_recovery=False,
    )
    setup_calls = 0

    def fail_replacement_once(*args: object, **kwargs: object) -> None:
        nonlocal setup_calls
        del args, kwargs
        setup_calls += 1
        if setup_calls == 2:
            raise RuntimeError("synthetic replacement setup failure")

    monkeypatch.setattr(Brain3DView, "load_atlas", fail_replacement_once)
    scheduled: list[Callable[[], None]] = []
    monkeypatch.setattr(
        QTimer,
        "singleShot",
        lambda _delay, callback: scheduled.append(callback),
    )
    replacement_token = window._load_token
    window._on_atlas_loaded(make_loaded_payload(atlas_b), replacement_token)
    launched_workers: list[object] = []
    monkeypatch.setattr(
        window,
        "_launch_worker",
        lambda worker, **_kwargs: launched_workers.append(worker),
    )
    scheduled[0]()
    recovery_token = window._atlas_recovery_load_token
    assert recovery_token is not None
    assert len(launched_workers) == 1

    window._invalidate_async_callbacks()
    atlas_c_dir = tmp_path / "atlas-c"
    atlas_c_dir.mkdir()
    atlas_c = FakeLoadedAtlas(atlas_c_dir)
    window._install_loaded_atlas(make_loaded_payload(atlas_c), restoring=False)
    assert window._loaded_atlas is atlas_c

    window._on_atlas_loaded(make_loaded_payload(atlas_a), recovery_token)
    window._on_atlas_load_failed("late recovery failure", recovery_token)
    window._on_atlas_loaded(make_loaded_payload(atlas_b), replacement_token)

    assert window._loaded_atlas is atlas_c
    assert window.project.atlas == atlas_c.metadata
    assert window._atlas_space is not None and window._atlas_space.metadata == atlas_c.metadata
    assert len(window._slice_views) == 6
    assert len(window._brain_views) == 2
    assert window.rendering_status.text() == "Rendering: ready"


def test_stale_atlas_progress_cannot_mutate_current_dialog(
    qtbot: QtBot,
) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    progress = QProgressDialog(window)
    progress.setRange(0, 0)
    window._load_progress = progress
    window._load_token = 7

    window._on_atlas_progress(5, 10, 6)
    assert progress.maximum() == 0

    window._on_atlas_progress(5, 10, 7)
    assert progress.maximum() == 10
    assert progress.value() == 5


def test_current_atlas_stage_updates_progress_text_without_auto_reset(qtbot: QtBot) -> None:
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    progress = QProgressDialog(window)
    progress.setAutoReset(False)
    progress.setRange(0, 10)
    progress.setValue(10)
    window._load_progress = progress
    window._load_token = 7

    window._on_atlas_stage("stale stage", 6)
    assert progress.labelText() != "stale stage"

    window._on_atlas_stage(ATLAS_SURFACE_STAGE_TEXT, 7)
    assert progress.labelText() == ATLAS_SURFACE_STAGE_TEXT
    assert progress.minimum() == 0 and progress.maximum() == 0
    assert not progress.autoReset()
    assert window.rendering_status.text() == "Rendering: preparing exact 3d brain surface…"


def test_gui_cancellation_reaches_busy_worker_without_waiting_for_thread_event_loop(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    atlas = FakeLoadedAtlas(tmp_path)
    window = MainWindow(
        no_download=False,
        suppress_dialogs=True,
        repository=cast(AtlasRepositoryProtocol, SlowCancelableRepository(atlas)),
    )
    qtbot.addWidget(window)
    window.show()

    window._begin_atlas_load("allen_mouse_25um")
    qtbot.waitUntil(lambda: window._load_worker is not None, timeout=1000)
    assert window._load_progress is not None
    assert not window._load_progress.autoClose()
    assert not window._load_progress.autoReset()
    window._cancel_atlas_load()
    qtbot.waitUntil(
        lambda: window.rendering_status.text() == "Rendering: atlas load cancelled",
        timeout=3000,
    )
    qtbot.waitUntil(lambda: not window._active_threads, timeout=3000)
