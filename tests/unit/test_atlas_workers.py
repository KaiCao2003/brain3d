"""Unit tests for worker cancellation at non-Qt integration boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pyvista as pv
from tests.fixtures import make_allen_metadata_test_double

import mouse_brain_planner.gui.workers.atlas_worker as atlas_worker_module
from mouse_brain_planner.atlas.brainglobe_adapter import LoadedAtlas
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.gui.workers.atlas_worker import (
    ATLAS_SURFACE_STAGE_TEXT,
    AtlasLoadWorker,
    LoadedAtlasPayload,
    RegionMeshPayload,
    RegionMeshWorker,
    center_voxel_anchor,
)


class _TrackingAtlas:
    def __init__(self) -> None:
        self.mesh_requests = 0

    def mesh_file_for_region(self, structure_id: int) -> Path:
        del structure_id
        self.mesh_requests += 1
        raise AssertionError("a pre-cancelled worker must not touch atlas storage")


def test_region_mesh_worker_pre_cancel_suppresses_io_and_results() -> None:
    atlas = _TrackingAtlas()
    worker = RegionMeshWorker(
        cast(LoadedAtlas, atlas),
        7,
        renderer_anchor=BrainGlobePhysicalPoint(
            atlas_key="unused-test-atlas",
            atlas_version="unused-test-version",
            ap_um=0.0,
            dv_um=0.0,
            ml_um=0.0,
        ),
    )
    succeeded: list[object] = []
    failed: list[tuple[int, str]] = []
    finished: list[bool] = []
    worker.succeeded.connect(succeeded.append)
    worker.failed.connect(lambda structure_id, message: failed.append((structure_id, message)))
    worker.finished.connect(lambda: finished.append(True))

    worker.request_cancel()
    worker.run()

    assert atlas.mesh_requests == 0
    assert succeeded == []
    assert failed == []
    assert finished == [True]


class _MeshAtlas:
    def __init__(self, mesh_path: Path) -> None:
        self.metadata = make_allen_metadata_test_double(25)
        self.mesh_path = mesh_path

    def root_mesh_file(self) -> Path:
        return self.mesh_path

    def mesh_file_for_region(self, structure_id: int) -> Path:
        assert structure_id == 7
        return self.mesh_path


class _SmallVolumeMeshAtlas(_MeshAtlas):
    def __init__(self, mesh_path: Path) -> None:
        super().__init__(mesh_path)
        shape = (4, 5, 6)
        self.metadata = self.metadata.model_copy(
            update={
                "shape_voxels": shape,
                "midline_ml_um": shape[2] * self.metadata.resolution_um[2] / 2.0,
            }
        )
        self.reference = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)
        self.annotation = np.zeros(shape, dtype=np.uint32)


class _MeshRepository:
    def __init__(self, atlas: _MeshAtlas) -> None:
        self.atlas = atlas

    def open(self, *args: object, **kwargs: object) -> LoadedAtlas:
        del args, kwargs
        return cast(LoadedAtlas, self.atlas)


def test_atlas_and_region_workers_deliver_world_mesh_with_exact_anchor(tmp_path: Path) -> None:
    mesh_path = tmp_path / "mesh.vtp"
    pv.Sphere(radius=25.0, theta_resolution=8, phi_resolution=8).save(mesh_path)
    atlas = _MeshAtlas(mesh_path)
    space = BrainGlobeAtlasSpace(atlas.metadata)
    persisted_anchor = center_voxel_anchor(space).model_copy(update={"ap_um": 5000.0})
    load_worker = AtlasLoadWorker(
        cast(object, _MeshRepository(atlas)),  # protocol is exercised structurally
        atlas.metadata.atlas_key,
        preload_volumes=False,
        renderer_anchor=persisted_anchor,
    )
    load_results: list[object] = []
    load_worker.succeeded.connect(load_results.append)

    load_worker.run()

    assert len(load_results) == 1
    loaded = load_results[0]
    assert isinstance(loaded, LoadedAtlasPayload)
    assert loaded.root_mesh.renderer_anchor == persisted_anchor
    assert loaded.root_mesh.atlas_metadata == atlas.metadata
    loaded.root_mesh.validate_for(space, persisted_anchor)
    assert "Normals" in loaded.root_mesh.mesh.point_data

    region_worker = RegionMeshWorker(
        cast(LoadedAtlas, atlas),
        7,
        renderer_anchor=persisted_anchor,
    )
    region_results: list[object] = []
    region_worker.succeeded.connect(region_results.append)

    region_worker.run()

    assert len(region_results) == 1
    region = region_results[0]
    assert isinstance(region, RegionMeshPayload)
    assert region.structure_id == 7
    assert region.mesh.renderer_anchor == persisted_anchor
    region.mesh.validate_for(space, persisted_anchor)


def test_atlas_worker_fresh_load_uses_exact_center_voxel_anchor(tmp_path: Path) -> None:
    mesh_path = tmp_path / "mesh.vtp"
    pv.Sphere(radius=25.0, theta_resolution=8, phi_resolution=8).save(mesh_path)
    atlas = _MeshAtlas(mesh_path)
    worker = AtlasLoadWorker(
        cast(object, _MeshRepository(atlas)),
        atlas.metadata.atlas_key,
        preload_volumes=False,
    )
    results: list[object] = []
    worker.succeeded.connect(results.append)

    worker.run()

    assert len(results) == 1
    payload = results[0]
    assert isinstance(payload, LoadedAtlasPayload)
    assert payload.root_mesh.renderer_anchor == center_voxel_anchor(
        BrainGlobeAtlasSpace(atlas.metadata)
    )


def test_worker_preloads_25um_without_sagittal_cache_preparation(tmp_path: Path) -> None:
    mesh_path = tmp_path / "mesh.vtp"
    pv.Sphere(radius=25.0, theta_resolution=8, phi_resolution=8).save(mesh_path)
    atlas = _SmallVolumeMeshAtlas(mesh_path)
    assert "prepare_sagittal_cache" not in vars(atlas_worker_module)
    assert "reviewed_10um_requires_sagittal_cache" not in vars(atlas_worker_module)
    worker = AtlasLoadWorker(
        cast(object, _MeshRepository(atlas)),
        atlas.metadata.atlas_key,
    )
    stages: list[str] = []
    results: list[object] = []
    worker.stage_changed.connect(stages.append)
    worker.succeeded.connect(results.append)

    worker.run()

    assert stages == [ATLAS_SURFACE_STAGE_TEXT]
    assert len(results) == 1
    payload = results[0]
    assert isinstance(payload, LoadedAtlasPayload)
    assert payload.sagittal_cache is None
