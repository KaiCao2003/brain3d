from __future__ import annotations

import base64
import struct
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from numpy.typing import NDArray

from mouse_brain_planner.bridge import viewer_state as viewer_state_module
from mouse_brain_planner.bridge.atlas_interaction import _source_coordinate_frame
from mouse_brain_planner.bridge.planning import register_planning_handlers
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher, BridgeError
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint


@dataclass(slots=True)
class _ViewerAtlas:
    metadata: AtlasMetadata
    reference: NDArray[np.uint16]
    annotation: NDArray[np.int32]
    brainglobe_atlasapi_version: str = "2.3.1"

    @property
    def regions(self) -> list[RegionRecord]:
        return [
            RegionRecord(
                structure_id=1,
                acronym="RIGHT",
                name="Right test region",
                structure_id_path=(1,),
                rgb=(20, 40, 60),
            ),
            RegionRecord(
                structure_id=2,
                acronym="LEFT",
                name="Left test region",
                structure_id_path=(2,),
                rgb=(80, 100, 120),
            ),
        ]

    def region_at(self, point: BrainGlobePhysicalPoint) -> RegionRecord | None:
        index = BrainGlobeAtlasSpace(self.metadata).physical_to_index(point)
        structure_id = int(self.annotation[index.ap, index.dv, index.ml])
        return next(
            (region for region in self.regions if region.structure_id == structure_id), None
        )


def _metadata() -> AtlasMetadata:
    resolution = (10.0, 20.0, 30.0)
    return AtlasMetadata(
        atlas_key="allen_mouse_25um",
        atlas_package_version="1.2",
        species="Mus musculus",
        citation="Viewer contract test atlas",
        source_url="https://example.invalid/viewer-atlas",
        cache_path="/verified/viewer-atlas",
        metadata_sha256="a" * 64,
        resolution_um=resolution,
        shape_voxels=(4, 3, 6),
        source_annotation="annotation/ccf_2017",
        symmetric=True,
        midline_ml_um=90.0,
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


def _dispatcher() -> BridgeDispatcher:
    metadata = _metadata()
    annotation = np.ones(metadata.shape_voxels, dtype=np.int32)
    annotation[:, :, 3:] = 2
    atlas = _ViewerAtlas(
        metadata=metadata,
        reference=np.arange(np.prod(metadata.shape_voxels), dtype=np.uint16).reshape(
            metadata.shape_voxels
        ),
        annotation=annotation,
    )
    context = BridgeContext(repository_factory=lambda: pytest.fail("repository not expected"))
    context.set_loaded_atlas(atlas)
    dispatcher = BridgeDispatcher(context)
    register_planning_handlers(dispatcher)
    return dispatcher


def _call(dispatcher: BridgeDispatcher, method: str, **params: object) -> dict[str, object]:
    return dispatcher.dispatch(method, {"protocolVersion": 1, **params})


def _new_project(dispatcher: BridgeDispatcher) -> tuple[str, int]:
    created = _call(
        dispatcher,
        "project.new",
        animalResearchOnlyAcknowledged=True,
        title="Independent viewer contract",
    )
    project_id = created["projectId"]
    assert isinstance(project_id, str)
    state = _call(dispatcher, "viewer.state.get")
    revision = state["projectRevision"]
    assert isinstance(revision, int)
    return project_id, revision


def _assert_error(code: str, operation: object) -> None:
    assert callable(operation)
    with pytest.raises(BridgeError) as captured:
        operation()
    assert captured.value.code == code


def _snapshot_keys() -> set[str]:
    return {
        "protocolVersion",
        "projectId",
        "projectRevision",
        "atlas",
        "coordinateFrame",
        "slices",
        "selection",
    }


def test_initial_snapshot_has_three_independent_depths_and_no_selection() -> None:
    dispatcher = _dispatcher()
    assert _call(dispatcher, "state.get")["viewer"] is None
    _assert_error("PROJECT_NOT_OPEN", lambda: _call(dispatcher, "viewer.state.get"))

    project_id, revision = _new_project(dispatcher)
    snapshot = _call(dispatcher, "viewer.state.get")
    _assert_error(
        "INVALID_PARAMS",
        lambda: _call(dispatcher, "viewer.state.get", projectId=project_id),
    )

    assert set(snapshot) == _snapshot_keys()
    assert snapshot["projectId"] == project_id
    assert snapshot["projectRevision"] == revision == 1
    assert snapshot["selection"] is None
    assert snapshot["coordinateFrame"] == _source_coordinate_frame(_metadata())
    assert snapshot["slices"] == {
        "coronal": {
            "orientation": "coronal",
            "index": 2,
            "sliceCount": 4,
            "fixedAxis": "AP",
            "rowAxis": "DV",
            "columnAxis": "ML",
            "sliceCenterMicrometres": 25.0,
        },
        "sagittal": {
            "orientation": "sagittal",
            "index": 3,
            "sliceCount": 6,
            "fixedAxis": "ML",
            "rowAxis": "DV",
            "columnAxis": "AP",
            "sliceCenterMicrometres": 105.0,
        },
        "horizontal": {
            "orientation": "horizontal",
            "index": 1,
            "sliceCount": 3,
            "fixedAxis": "DV",
            "rowAxis": "AP",
            "columnAxis": "ML",
            "sliceCenterMicrometres": 30.0,
        },
    }
    assert _call(dispatcher, "state.get")["viewer"] == snapshot


def test_slice_mutations_change_only_one_depth_and_clear_selection() -> None:
    dispatcher = _dispatcher()
    project_id, revision = _new_project(dispatcher)

    coronal = _call(
        dispatcher,
        "viewer.slice.set",
        projectId=project_id,
        expectedProjectRevision=revision,
        orientation="coronal",
        index=1,
    )
    assert coronal["status"] == "sliceUpdated"
    assert set(coronal) == _snapshot_keys() | {"status"}
    assert {name: item["index"] for name, item in coronal["slices"].items()} == {
        "coronal": 1,
        "sagittal": 3,
        "horizontal": 1,
    }

    sagittal = _call(
        dispatcher,
        "viewer.slice.set",
        projectId=project_id,
        expectedProjectRevision=coronal["projectRevision"],
        orientation="sagittal",
        index=5,
    )
    horizontal = _call(
        dispatcher,
        "viewer.slice.set",
        projectId=project_id,
        expectedProjectRevision=sagittal["projectRevision"],
        orientation="horizontal",
        index=2,
    )
    assert {name: item["index"] for name, item in horizontal["slices"].items()} == {
        "coronal": 1,
        "sagittal": 5,
        "horizontal": 2,
    }
    assert horizontal["selection"] is None

    selected = _call(
        dispatcher,
        "viewer.region.pick",
        projectId=project_id,
        expectedProjectRevision=horizontal["projectRevision"],
        orientation="coronal",
        index=1,
        column=4,
        row=2,
    )
    assert selected["selection"] is not None
    cleared = _call(
        dispatcher,
        "viewer.slice.set",
        projectId=project_id,
        expectedProjectRevision=selected["projectRevision"],
        orientation="horizontal",
        index=1,
    )
    assert cleared["selection"] is None
    assert {name: item["index"] for name, item in cleared["slices"].items()} == {
        "coronal": 1,
        "sagittal": 5,
        "horizontal": 1,
    }


def test_region_pick_replaces_selection_without_changing_any_depth() -> None:
    dispatcher = _dispatcher()
    project_id, revision = _new_project(dispatcher)
    before = _call(dispatcher, "viewer.state.get")
    before_depths = {
        name: item["index"] for name, item in before["slices"].items()
    }

    first = _call(
        dispatcher,
        "viewer.region.pick",
        projectId=project_id,
        expectedProjectRevision=revision,
        orientation="coronal",
        index=2,
        column=4,
        row=2,
    )
    assert first["status"] == "regionSelected"
    assert set(first) == _snapshot_keys() | {"status"}
    assert {name: item["index"] for name, item in first["slices"].items()} == before_depths
    assert first["selection"] == {
        "orientation": "coronal",
        "index": 2,
        "column": 4,
        "row": 2,
        "atlasPoint": {
            "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
            "apMicrometres": 25.0,
            "dvMicrometres": 50.0,
            "mlMicrometres": 135.0,
        },
        "containingVoxelIndex": {
            "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
            "ap": 2,
            "dv": 2,
            "ml": 4,
        },
        "region": {
            "structureId": 2,
            "acronym": "LEFT",
            "name": "Left test region",
            "parentStructureId": None,
            "structureIdPath": [2],
            "rgb": [80, 100, 120],
        },
        "hemisphere": "left",
    }

    second = _call(
        dispatcher,
        "viewer.region.pick",
        projectId=project_id,
        expectedProjectRevision=first["projectRevision"],
        orientation="horizontal",
        index=1,
        column=1,
        row=0,
    )
    assert {name: item["index"] for name, item in second["slices"].items()} == before_depths
    selection = second["selection"]
    assert isinstance(selection, dict)
    selected_pixel = (
        selection["orientation"],
        selection["index"],
        selection["column"],
        selection["row"],
    )
    assert selected_pixel == (
        "horizontal",
        1,
        1,
        0,
    )
    assert selection["region"]["acronym"] == "RIGHT"


def test_slice_render_returns_matching_snapshot_and_png() -> None:
    dispatcher = _dispatcher()
    project_id, revision = _new_project(dispatcher)
    result = _call(
        dispatcher,
        "viewer.slice.render",
        projectId=project_id,
        expectedProjectRevision=revision,
        orientation="horizontal",
        index=2,
    )

    assert set(result) == _snapshot_keys() | {"status", "renderedSlice"}
    assert result["status"] == "sliceUpdated"
    assert result["projectRevision"] == revision + 1
    assert result["selection"] is None
    rendered = result["renderedSlice"]
    assert rendered["orientation"] == "horizontal"
    assert rendered["index"] == result["slices"]["horizontal"]["index"] == 2
    assert rendered["sliceCenterMicrometres"] == 50.0
    assert rendered["atlas"] == result["atlas"]
    png = base64.b64decode(str(rendered["pngBase64"]), validate=True)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", png[16:24]) == (6, 4)


def test_slice_render_rejects_stale_work_before_render_and_is_atomic_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = _dispatcher()
    project_id, revision = _new_project(dispatcher)
    initial = _call(dispatcher, "viewer.state.get")
    render_calls = 0

    def fail_render(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal render_calls
        render_calls += 1
        raise BridgeError("SLICE_RENDER_FAILED", "test encoder failure")

    monkeypatch.setattr(viewer_state_module, "render_atlas_slice_payload", fail_render)
    _assert_error(
        "PROJECT_REVISION_CONFLICT",
        lambda: _call(
            dispatcher,
            "viewer.slice.render",
            projectId=project_id,
            expectedProjectRevision=revision + 1,
            orientation="coronal",
            index=1,
        ),
    )
    assert render_calls == 0
    _assert_error(
        "SLICE_RENDER_FAILED",
        lambda: _call(
            dispatcher,
            "viewer.slice.render",
            projectId=project_id,
            expectedProjectRevision=revision,
            orientation="coronal",
            index=1,
        ),
    )
    assert render_calls == 1
    assert _call(dispatcher, "viewer.state.get") == initial


def test_stale_revision_stale_slice_and_bad_pixels_do_not_mutate_state() -> None:
    dispatcher = _dispatcher()
    project_id, revision = _new_project(dispatcher)
    initial = _call(dispatcher, "viewer.state.get")

    _assert_error(
        "PROJECT_ID_MISMATCH",
        lambda: _call(
            dispatcher,
            "viewer.slice.set",
            projectId=str(uuid4()),
            expectedProjectRevision=revision,
            orientation="coronal",
            index=1,
        ),
    )
    _assert_error(
        "PROJECT_REVISION_CONFLICT",
        lambda: _call(
            dispatcher,
            "viewer.slice.set",
            projectId=project_id,
            expectedProjectRevision=revision + 1,
            orientation="coronal",
            index=1,
        ),
    )
    _assert_error(
        "VIEWER_SLICE_STALE",
        lambda: _call(
            dispatcher,
            "viewer.region.pick",
            projectId=project_id,
            expectedProjectRevision=revision,
            orientation="coronal",
            index=1,
            column=0,
            row=0,
        ),
    )
    _assert_error(
        "VIEWER_PICK_OUT_OF_RANGE",
        lambda: _call(
            dispatcher,
            "viewer.region.pick",
            projectId=project_id,
            expectedProjectRevision=revision,
            orientation="coronal",
            index=2,
            column=6,
            row=0,
        ),
    )
    _assert_error(
        "SLICE_OUT_OF_RANGE",
        lambda: _call(
            dispatcher,
            "viewer.slice.set",
            projectId=project_id,
            expectedProjectRevision=revision,
            orientation="horizontal",
            index=3,
        ),
    )
    _assert_error(
        "INVALID_PARAMS",
        lambda: _call(
            dispatcher,
            "viewer.region.pick",
            projectId=project_id,
            expectedProjectRevision=revision,
            orientation="Coronal",
            index=2,
            column=0,
            row=0,
        ),
    )
    _assert_error(
        "METHOD_NOT_FOUND",
        lambda: _call(
            dispatcher,
            "viewer.cursor.pick",
            projectId=project_id,
            expectedProjectRevision=revision,
            orientation="coronal",
            index=2,
            column=0,
            row=0,
        ),
    )
    _assert_error(
        "METHOD_NOT_FOUND",
        lambda: _call(
            dispatcher,
            "viewer.cursor.set",
            projectId=project_id,
            expectedProjectRevision=revision,
        ),
    )
    assert _call(dispatcher, "viewer.state.get") == initial


def test_exact_parameter_keys_are_enforced() -> None:
    dispatcher = _dispatcher()
    project_id, revision = _new_project(dispatcher)
    _assert_error(
        "INVALID_PARAMS",
        lambda: _call(
            dispatcher,
            "viewer.slice.set",
            projectId=project_id,
            expectedProjectRevision=revision,
            orientation="coronal",
            index=2,
            cursor={"x": 1},
        ),
    )
    _assert_error(
        "INVALID_PARAMS",
        lambda: _call(
            dispatcher,
            "viewer.region.pick",
            projectId=project_id,
            expectedProjectRevision=revision,
            orientation="coronal",
            index=2,
            column=0,
        ),
    )


def test_independent_depths_and_selection_survive_save_and_reopen(tmp_path: Path) -> None:
    dispatcher = _dispatcher()
    project_id, revision = _new_project(dispatcher)
    coronal = _call(
        dispatcher,
        "viewer.slice.set",
        projectId=project_id,
        expectedProjectRevision=revision,
        orientation="coronal",
        index=1,
    )
    sagittal = _call(
        dispatcher,
        "viewer.slice.set",
        projectId=project_id,
        expectedProjectRevision=coronal["projectRevision"],
        orientation="sagittal",
        index=5,
    )
    selected = _call(
        dispatcher,
        "viewer.region.pick",
        projectId=project_id,
        expectedProjectRevision=sagittal["projectRevision"],
        orientation="sagittal",
        index=5,
        column=1,
        row=2,
    )
    destination = tmp_path / "independent-viewer.mouseplan"
    _call(dispatcher, "project.save", path=str(destination))

    reopened = _dispatcher()
    opened = _call(reopened, "project.open", path=str(destination))
    assert opened["projectId"] == project_id
    snapshot = _call(reopened, "viewer.state.get")
    assert snapshot["projectRevision"] == 0
    assert snapshot["slices"] == selected["slices"]
    assert snapshot["selection"] == selected["selection"]
    assert _call(reopened, "state.get")["viewer"] == snapshot


def test_opening_current_schema_project_without_viewer_fields_initializes_depths(
    tmp_path: Path,
) -> None:
    dispatcher = _dispatcher()
    project_id, _ = _new_project(dispatcher)
    destination = tmp_path / "legacy-v3-viewer.mouseplan"
    _call(dispatcher, "project.save", path=str(destination))

    # Simulate a schema-3 package created before independent viewer fields existed.
    project_file = destination / "project.json"
    checksums_file = destination / "checksums.json"
    import hashlib
    import json

    project_payload = json.loads(project_file.read_text())
    project_payload.pop("viewer_slice_depths")
    project_payload.pop("viewer_region_selection")
    project_file.write_text(json.dumps(project_payload, sort_keys=True, separators=(",", ":")))
    checksums = json.loads(checksums_file.read_text())
    checksums["project.json"] = hashlib.sha256(project_file.read_bytes()).hexdigest()
    checksums_file.write_text(json.dumps(checksums, sort_keys=True, separators=(",", ":")))

    reopened = _dispatcher()
    opened = _call(reopened, "project.open", path=str(destination))
    assert opened["projectId"] == project_id
    snapshot = _call(reopened, "viewer.state.get")
    assert snapshot["selection"] is None
    assert {name: item["index"] for name, item in snapshot["slices"].items()} == {
        "coronal": 2,
        "sagittal": 3,
        "horizontal": 1,
    }
