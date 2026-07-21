"""Phase 1 atlas-selection, worker, and linked-view integration tests."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import pyvista as pv
from pytestqt.qtbot import QtBot

import mouse_brain_planner.gui.main_window as main_window_module
from mouse_brain_planner.atlas.brainglobe_adapter import (
    AtlasCatalogRecord,
    AtlasDownloadCancelledError,
    LoadedAtlas,
)
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.project_models import PlannerProject, RegionDisplayState
from mouse_brain_planner.gui.dialogs.atlas_selection import (
    ALLEN_RAW_VOLUME_BYTES,
    AtlasSelectionDialog,
    format_bytes,
)
from mouse_brain_planner.gui.main_window import MainWindow
from mouse_brain_planner.gui.viewers.brain_3d_view import Brain3DView
from mouse_brain_planner.gui.workers.atlas_worker import (
    AtlasCatalogWorker,
    AtlasLoadWorker,
    AtlasRepositoryProtocol,
    LoadedAtlasPayload,
    RegionMeshPayload,
    RegionMeshWorker,
)

pytestmark = pytest.mark.gui


def make_small_asr_metadata(cache_path: Path) -> AtlasMetadata:
    """Return explicit small metadata for orchestration tests only."""

    resolution = (100.0, 200.0, 300.0)
    return AtlasMetadata(
        atlas_key="allen_mouse_25um",
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

    def __init__(self, tmp_path: Path) -> None:
        self.metadata = make_small_asr_metadata(tmp_path)
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
        return [AtlasCatalogRecord("allen_mouse_25um", "1.2", True)]

    def is_cached(self, atlas_name: str, package_version: str | None = None) -> bool:
        return atlas_name == "allen_mouse_25um" and package_version in {None, "1.2"}

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> LoadedAtlas:
        assert atlas_name == "allen_mouse_25um"
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
        assert atlas_name == "allen_mouse_25um"
        self.last_package_version = package_version
        self.last_allow_download = allow_download
        for completed in range(1, 501):
            if cancel is not None and cancel():
                raise AtlasDownloadCancelledError("cancelled test atlas")
            if progress is not None:
                progress(completed, 500)
            time.sleep(0.001)
        return cast(LoadedAtlas, self.atlas)


def test_atlas_dialog_disables_remote_entries_in_no_download_mode(qtbot: QtBot) -> None:
    records = [
        AtlasCatalogRecord("allen_mouse_10um", "1.2", False),
        AtlasCatalogRecord("allen_mouse_25um", "1.2", True),
    ]
    dialog = AtlasSelectionDialog(records, no_download=True)
    qtbot.addWidget(dialog)

    assert dialog.atlas_tree.topLevelItem(0).isDisabled()  # type: ignore[union-attr]
    assert dialog.selected_record == records[1]
    assert format_bytes(ALLEN_RAW_VOLUME_BYTES["allen_mouse_10um"]) in (
        dialog.memory_warning.text()
    )


def test_catalog_selection_preserves_exact_advertised_package_version(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = AtlasCatalogRecord("allen_mouse_25um", "1.2", True)

    class AcceptedAtlasDialog:
        DialogCode = AtlasSelectionDialog.DialogCode

        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            self.selected_record = record

        def exec(self) -> AtlasSelectionDialog.DialogCode:
            return self.DialogCode.Accepted

    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    begin_calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(main_window_module, "AtlasSelectionDialog", AcceptedAtlasDialog)
    monkeypatch.setattr(
        window,
        "_begin_atlas_load",
        lambda name, **kwargs: begin_calls.append((name, kwargs.get("package_version"))),
    )

    window._show_atlas_selection([record])

    assert begin_calls == [("allen_mouse_25um", "1.2")]


def test_workers_return_validated_mesh_payloads(qtbot: QtBot, tmp_path: Path) -> None:
    atlas = FakeLoadedAtlas(tmp_path)
    repository = FakeRepository(atlas)
    catalog_worker = AtlasCatalogWorker(repository)
    load_worker = AtlasLoadWorker(repository, "allen_mouse_25um")
    region_worker = RegionMeshWorker(cast(LoadedAtlas, atlas), 2)

    with qtbot.waitSignal(catalog_worker.succeeded, timeout=1000) as catalog_signal:
        catalog_worker.run()
    with qtbot.waitSignal(load_worker.succeeded, timeout=1000) as load_signal:
        load_worker.run()
    with qtbot.waitSignal(region_worker.succeeded, timeout=1000) as region_signal:
        region_worker.run()

    assert catalog_signal.args == [repository.list_atlases()]
    loaded_payload = load_signal.args[0]
    assert isinstance(loaded_payload, LoadedAtlasPayload)
    assert loaded_payload.root_mesh.n_points > 0
    region_payload = region_signal.args[0]
    assert isinstance(region_payload, RegionMeshPayload)
    assert region_payload.structure_id == 2
    assert region_payload.mesh.n_cells > 0


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
    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    atlas = FakeLoadedAtlas(tmp_path)
    window = MainWindow(
        no_download=True,
        suppress_dialogs=True,
        repository=FakeRepository(atlas),
    )
    qtbot.addWidget(window)
    payload = LoadedAtlasPayload(
        atlas=cast(LoadedAtlas, atlas),
        root_mesh=pv.Sphere(theta_resolution=8, phi_resolution=8),
    )

    window._install_loaded_atlas(payload, restoring=False)
    window.show()

    assert len(window._slice_views) == 6
    assert all(view.cursor_voxel == (2, 2, 3) for view in window._slice_views)
    window._slice_views[0].slice_slider.setValue(1)
    assert all(view.cursor_voxel == (1, 2, 3) for view in window._slice_views)
    assert "A→P 150.0" in window.atlas_coordinate_status.text()
    assert window.project.selected_region_id == 2
    assert window._region_items[2].text(0) == "CA1"

    window.region_search.setText("field ca1")
    assert not window._region_items[2].isHidden()
    assert not window._region_items[1].isHidden()
    for query, structure_id in (("ADN", 3), ("RSC", 4), ("MEC", 5)):
        window.region_search.setText(query)
        assert not window._region_items[structure_id].isHidden()

    saved_cursor = window.project.linked_cursor
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
    assert window.project.selected_region_id == saved_selection == 3
    assert window.region_tree.currentItem() is window._region_items[3]
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
    payload = LoadedAtlasPayload(
        atlas=cast(LoadedAtlas, atlas),
        root_mesh=pv.Sphere(theta_resolution=8, phi_resolution=8),
    )

    window._install_loaded_atlas(payload, restoring=False)
    window._set_region_display(3, visible=True, custom_rgb=(1, 2, 3))
    window._install_loaded_atlas(payload, restoring=False)

    assert window.project.region_display == []
    assert window._region_items[3].checkState(0) == window._region_items[2].checkState(0)
    assert window._region_items[3].checkState(0).value == 0


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
    payload = LoadedAtlasPayload(
        atlas=cast(LoadedAtlas, atlas),
        root_mesh=pv.Sphere(theta_resolution=8, phi_resolution=8),
    )

    window._on_atlas_loaded(payload, window._load_token)

    assert window._loaded_atlas is None
    assert errors and errors[0][0] == "Atlas setup failed"
    assert "structure IDs" in errors[0][1]
    assert "888, 999" in errors[0][1]
    assert "Verify the atlas package/version" in errors[0][1]


def test_background_selection_clears_tree_and_records_project_change(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Brain3DView, "load_atlas", lambda *args, **kwargs: None)
    atlas = FakeLoadedAtlas(tmp_path)
    window = MainWindow(no_download=True, suppress_dialogs=True)
    qtbot.addWidget(window)
    window._install_loaded_atlas(
        LoadedAtlasPayload(
            atlas=cast(LoadedAtlas, atlas),
            root_mesh=pv.Sphere(theta_resolution=8, phi_resolution=8),
        ),
        restoring=False,
    )
    window._set_dirty(False)

    window._select_region(None)

    assert window.project.selected_region_id is None
    assert window.region_tree.currentItem() is None
    assert window.region_tree.selectedItems() == []
    assert window._dirty
    assert window.project.event_log[-1].action == "region-selected"


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
            LoadedAtlasPayload(
                atlas=cast(LoadedAtlas, atlas),
                root_mesh=pv.Sphere(theta_resolution=8, phi_resolution=8),
            ),
            restoring=False,
        )

    assert len(loaded_views) == 2
    assert loaded_views[1] in disposed_views
    assert window._loaded_atlas is None
    assert window._four_panel_brain is None
    assert window.project.atlas is None


def test_stale_atlas_progress_cannot_mutate_current_dialog(
    qtbot: QtBot,
) -> None:
    from PySide6.QtWidgets import QProgressDialog

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
    window._cancel_atlas_load()
    qtbot.waitUntil(
        lambda: window.rendering_status.text() == "Rendering: atlas load cancelled",
        timeout=3000,
    )
    qtbot.waitUntil(lambda: not window._active_threads, timeout=3000)
