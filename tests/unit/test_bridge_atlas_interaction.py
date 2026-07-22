"""Strict protocol tests for read-only atlas interaction bridge methods."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from tests.fixtures.atlas_factory import make_allen_metadata_test_double

from mouse_brain_planner.bridge.atlas_interaction import (
    register_atlas_interaction_handlers,
)
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher, BridgeServer
from mouse_brain_planner.domain.atlas_models import AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint


@dataclass(slots=True)
class _FakeLoadedAtlas:
    metadata: AtlasMetadata
    root_path: Path
    region_paths: dict[int, Path]
    brainglobe_atlasapi_version: str = "2.3.1"
    lookup_calls: list[BrainGlobePhysicalPoint] = field(default_factory=list)
    _reference: np.ndarray[tuple[int, int, int], np.dtype[np.uint16]] = field(
        init=False, repr=False
    )
    _annotation: np.ndarray[tuple[int, int, int], np.dtype[np.uint32]] = field(
        init=False, repr=False
    )
    _regions: list[RegionRecord] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._regions = [
            RegionRecord(
                structure_id=997,
                acronym="root",
                name="root",
                structure_id_path=(997,),
                rgb=(255, 255, 255),
            ),
            RegionRecord(
                structure_id=315,
                acronym="Isocortex",
                name="Isocortex",
                structure_id_path=(997, 315),
                rgb=(112, 255, 112),
            ),
            RegionRecord(
                structure_id=385,
                acronym="VISp",
                name="Primary visual area",
                structure_id_path=(997, 315, 385),
                rgb=(8, 133, 140),
            ),
            RegionRecord(
                structure_id=394,
                acronym="VISam",
                name="Anteromedial visual area",
                structure_id_path=(997, 315, 394),
                rgb=(13, 159, 145),
            ),
        ]
        shape = self.metadata.shape_voxels
        self._reference = np.broadcast_to(
            np.zeros((1, 1, 1), dtype=np.uint16),
            shape,
        )
        self._annotation = np.broadcast_to(
            np.full((1, 1, 1), 385, dtype=np.uint32),
            shape,
        )

    @property
    def reference(self) -> np.ndarray[tuple[int, int, int], np.dtype[np.uint16]]:
        return self._reference

    @property
    def annotation(self) -> np.ndarray[tuple[int, int, int], np.dtype[np.uint32]]:
        return self._annotation

    @property
    def regions(self) -> list[RegionRecord]:
        return list(self._regions)

    def region_at(self, point: BrainGlobePhysicalPoint) -> RegionRecord | None:
        self.lookup_calls.append(point)
        return None if point.ml_um == 0.0 else self._regions[2]

    def root_mesh_file(self) -> Path:
        return self.root_path

    def mesh_file_for_region(self, region: RegionRecord | int | str) -> Path:
        if not isinstance(region, RegionRecord):
            raise AssertionError("handler must pass one normalized region record")
        return self.region_paths[region.structure_id]


@pytest.fixture
def fake_atlas(tmp_path: Path) -> _FakeLoadedAtlas:
    atlas_root = tmp_path / "allen_mouse_25um_v1.2"
    meshes = atlas_root / "meshes"
    meshes.mkdir(parents=True)
    root_path = meshes / "997.obj"
    region_path = meshes / "385.obj"
    root_path.write_bytes(b"# root\nv 0 0 0\n")
    region_path.write_bytes(b"# VISp\nv 25 50 75\n")
    metadata = make_allen_metadata_test_double(25).model_copy(
        update={"cache_path": str(atlas_root)}
    )
    return _FakeLoadedAtlas(
        metadata=metadata,
        root_path=root_path,
        region_paths={385: region_path},
    )


def _request(request_id: str, method: str, params: dict[str, object]) -> bytes:
    return (json.dumps({"id": request_id, "method": method, "params": params}) + "\n").encode()


def _run(
    payload: bytes,
    *,
    atlas: _FakeLoadedAtlas | None,
) -> tuple[list[dict[str, Any]], str]:
    context = BridgeContext()
    if atlas is not None:
        context.set_loaded_atlas(atlas)
    dispatcher = BridgeDispatcher(context)
    register_atlas_interaction_handlers(dispatcher)
    output = BytesIO()
    diagnostics = StringIO()
    assert BridgeServer(dispatcher, diagnostics).run_stream(BytesIO(payload), output) == 0
    return [json.loads(line) for line in output.getvalue().splitlines()], diagnostics.getvalue()


def test_extension_capabilities_are_discoverable_without_loading_atlas() -> None:
    responses, diagnostics = _run(
        _request(
            "hello",
            "hello",
            {"protocolVersion": 1, "client": "Brain3DSwiftUI"},
        ),
        atlas=None,
    )

    capabilities = responses[0]["result"]["capabilities"]
    assert capabilities["atlasRegionRecords"] is True
    assert capabilities["atlasRegionSearch"] is True
    assert capabilities["atlasPhysicalPointLookup"] is True
    assert capabilities["atlasAnnotationRayPick"] is True
    assert capabilities["atlasMeshDescriptor"] is True
    assert diagnostics == ""


def test_regions_are_normalized_paginated_records_with_exact_provenance(
    fake_atlas: _FakeLoadedAtlas,
) -> None:
    responses, diagnostics = _run(
        _request(
            "regions",
            "atlas.regions",
            {"protocolVersion": 1, "offset": 1, "limit": 2},
        ),
        atlas=fake_atlas,
    )

    result = responses[0]["result"]
    assert result["totalCount"] == 4
    assert result["returnedCount"] == 2
    assert result["hasMore"] is True
    assert result["regions"] == [
        {
            "acronym": "Isocortex",
            "name": "Isocortex",
            "parentStructureId": 997,
            "rgb": [112, 255, 112],
            "structureId": 315,
            "structureIdPath": [997, 315],
        },
        {
            "acronym": "VISp",
            "name": "Primary visual area",
            "parentStructureId": 315,
            "rgb": [8, 133, 140],
            "structureId": 385,
            "structureIdPath": [997, 315, 385],
        },
    ]
    assert result["atlas"]["identifier"] == "allen_mouse_25um"
    assert result["atlas"]["version"] == "1.2"
    assert diagnostics == ""


def test_region_search_is_deterministic_and_does_not_fuzzy_guess(
    fake_atlas: _FakeLoadedAtlas,
) -> None:
    payload = b"".join(
        (
            _request(
                "prefix",
                "atlas.search",
                {"protocolVersion": 1, "query": "vis", "limit": 10},
            ),
            _request(
                "id",
                "atlas.search",
                {"protocolVersion": 1, "query": "385"},
            ),
            _request(
                "typo",
                "atlas.search",
                {"protocolVersion": 1, "query": "VSP"},
            ),
        )
    )

    responses, _ = _run(payload, atlas=fake_atlas)

    prefix = responses[0]["result"]
    assert [item["region"]["acronym"] for item in prefix["results"]] == ["VISam", "VISp"]
    assert [item["matchKind"] for item in prefix["results"]] == [
        "acronymPrefix",
        "acronymPrefix",
    ]
    assert responses[1]["result"]["results"] == [
        {
            "matchKind": "structureIdExact",
            "region": {
                "acronym": "VISp",
                "name": "Primary visual area",
                "parentStructureId": 315,
                "rgb": [8, 133, 140],
                "structureId": 385,
                "structureIdPath": [997, 315, 385],
            },
        }
    ]
    assert responses[2]["result"]["returnedCount"] == 0


def test_point_lookup_returns_named_asr_values_voxel_region_and_provenance(
    fake_atlas: _FakeLoadedAtlas,
) -> None:
    responses, diagnostics = _run(
        _request(
            "point",
            "atlas.point",
            {
                "protocolVersion": 1,
                "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
                "apMicrometres": 62.5,
                "dvMicrometres": 37.5,
                "mlMicrometres": 112.5,
            },
        ),
        atlas=fake_atlas,
    )

    result = responses[0]["result"]
    assert result["point"] == {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "apMicrometres": 62.5,
        "dvMicrometres": 37.5,
        "mlMicrometres": 112.5,
    }
    assert result["containingVoxelIndex"] == {
        "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
        "ap": 2,
        "dv": 1,
        "ml": 4,
    }
    assert result["containingVoxelCenter"] == {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "apMicrometres": 62.5,
        "dvMicrometres": 37.5,
        "mlMicrometres": 112.5,
    }
    assert result["region"]["structureId"] == 385
    assert result["annotationStructureId"] == 385
    assert result["coordinateFrame"]["axisOrder"] == ["AP", "DV", "ML"]
    assert result["coordinateFrame"]["origin"] == ["anterior", "superior", "right"]
    assert result["coordinateFrame"]["positiveDirections"] == [
        "posterior",
        "inferior",
        "left",
    ]
    assert result["coordinateFrame"]["bregmaRelative"] is False
    assert result["coordinateFrame"]["stereotaxicCalibrationApplied"] is False
    assert result["atlas"]["metadataSha256"] == fake_atlas.metadata.metadata_sha256
    assert len(fake_atlas.lookup_calls) == 1
    assert diagnostics == ""


def test_point_lookup_background_is_explicit_null(fake_atlas: _FakeLoadedAtlas) -> None:
    responses, _ = _run(
        _request(
            "background",
            "atlas.point",
            {
                "protocolVersion": 1,
                "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
                "apMicrometres": 0,
                "dvMicrometres": 0,
                "mlMicrometres": 0,
            },
        ),
        atlas=fake_atlas,
    )

    assert responses[0]["result"]["region"] is None
    assert responses[0]["result"]["annotationStructureId"] == 0


def _ray_params(**patch: object) -> dict[str, object]:
    params: dict[str, object] = {
        "protocolVersion": 1,
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "startApMicrometres": -100.0,
        "startDvMicrometres": 12.5,
        "startMlMicrometres": 12.5,
        "endApMicrometres": 200.0,
        "endDvMicrometres": 12.5,
        "endMlMicrometres": 12.5,
    }
    params.update(patch)
    return params


def test_annotation_ray_pick_returns_first_exact_voxel_and_region(
    fake_atlas: _FakeLoadedAtlas,
) -> None:
    responses, diagnostics = _run(
        _request("ray", "atlas.ray.pick", _ray_params()),
        atlas=fake_atlas,
    )

    result = responses[0]["result"]
    assert result["status"] == "hit"
    assert result["algorithmVersion"] == "amanatides-woo-clipped-half-open-first-nonzero-v1"
    assert result["coordinateFrame"]["axisOrder"] == ["AP", "DV", "ML"]
    hit = result["hit"]
    assert hit["containingVoxelIndex"] == {
        "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
        "ap": 0,
        "dv": 0,
        "ml": 0,
    }
    assert hit["voxelCenter"] == {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "apMicrometres": 12.5,
        "dvMicrometres": 12.5,
        "mlMicrometres": 12.5,
    }
    assert hit["entryPoint"]["apMicrometres"] == pytest.approx(0.0)
    assert hit["distanceFromRayStartMicrometres"] == pytest.approx(100.0)
    assert hit["distanceInsideVoxelMicrometres"] == pytest.approx(25.0)
    assert hit["annotationStructureId"] == 385
    assert hit["region"]["name"] == "Primary visual area"
    assert diagnostics == ""


@pytest.mark.parametrize(
    ("patch", "error_code"),
    (
        ({"frameId": "STEREOTAXIC_USER_BREGMA"}, "INVALID_PARAMS"),
        ({"startApMicrometres": True}, "INVALID_PARAMS"),
        ({"endApMicrometres": float("nan")}, "PARSE_ERROR"),
        (
            {
                "endApMicrometres": -100.0,
                "endDvMicrometres": 12.5,
                "endMlMicrometres": 12.5,
            },
            "ATLAS_RAY_INVALID",
        ),
    ),
)
def test_annotation_ray_pick_rejects_implicit_frames_and_invalid_segments(
    fake_atlas: _FakeLoadedAtlas,
    patch: dict[str, object],
    error_code: str,
) -> None:
    responses, _ = _run(
        _request("invalid-ray", "atlas.ray.pick", _ray_params(**patch)),
        atlas=fake_atlas,
    )

    assert responses[0]["error"]["code"] == error_code


@pytest.mark.parametrize(
    ("patch", "error_code"),
    [
        ({"apMicrometres": -0.1}, "ATLAS_POINT_OUT_OF_RANGE"),
        ({"apMicrometres": 13_200.0}, "ATLAS_POINT_OUT_OF_RANGE"),
        ({"mlMicrometres": 11_400.0}, "ATLAS_POINT_OUT_OF_RANGE"),
        ({"dvMicrometres": True}, "INVALID_PARAMS"),
        ({"frameId": "STEREOTAXIC_USER_BREGMA"}, "INVALID_PARAMS"),
    ],
)
def test_point_rejects_bounds_types_and_any_implicit_bregma_frame_before_lookup(
    fake_atlas: _FakeLoadedAtlas,
    patch: dict[str, object],
    error_code: str,
) -> None:
    params: dict[str, object] = {
        "protocolVersion": 1,
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "apMicrometres": 0.0,
        "dvMicrometres": 0.0,
        "mlMicrometres": 0.0,
    }
    params.update(patch)

    responses, _ = _run(_request("invalid", "atlas.point", params), atlas=fake_atlas)

    assert responses[0]["error"]["code"] == error_code
    assert fake_atlas.lookup_calls == []


def test_mesh_descriptor_hashes_verified_atlas_file_without_inlining_contents(
    fake_atlas: _FakeLoadedAtlas,
) -> None:
    responses, diagnostics = _run(
        _request(
            "mesh",
            "atlas.mesh",
            {"protocolVersion": 1, "target": "region", "structureId": 385},
        ),
        atlas=fake_atlas,
    )

    result = responses[0]["result"]
    mesh = result["mesh"]
    expected_path = fake_atlas.region_paths[385].resolve()
    expected_bytes = expected_path.read_bytes()
    assert result["target"] == "region"
    assert result["region"]["acronym"] == "VISp"
    assert mesh["canonicalPath"] == str(expected_path)
    assert mesh["atlasRootCanonicalPath"] == fake_atlas.metadata.cache_path
    assert mesh["pathUnderAtlasRoot"] == "meshes/385.obj"
    assert mesh["sha256"] == hashlib.sha256(expected_bytes).hexdigest()
    assert mesh["byteSize"] == len(expected_bytes)
    assert mesh["fileExtension"] == ".obj"
    assert mesh["contentsIncluded"] is False
    assert "contents" not in mesh
    assert "base64" not in json.dumps(result).casefold()
    assert result["sourceCoordinateFrame"]["frameId"] == "BRAINGLOBE_PHYSICAL_ASR_UM"
    assert result["sourceCoordinateFrame"]["voxelAnchorOffsetApplied"] is False
    assert diagnostics == ""


def test_root_mesh_descriptor_requires_root_schema(fake_atlas: _FakeLoadedAtlas) -> None:
    payload = b"".join(
        (
            _request(
                "root",
                "atlas.mesh",
                {"protocolVersion": 1, "target": "root"},
            ),
            _request(
                "root-extra",
                "atlas.mesh",
                {"protocolVersion": 1, "target": "root", "structureId": 997},
            ),
            _request(
                "region-missing",
                "atlas.mesh",
                {"protocolVersion": 1, "target": "region"},
            ),
            _request(
                "unknown-region",
                "atlas.mesh",
                {"protocolVersion": 1, "target": "region", "structureId": 999999},
            ),
        )
    )

    responses, _ = _run(payload, atlas=fake_atlas)

    assert responses[0]["result"]["mesh"]["pathUnderAtlasRoot"] == "meshes/997.obj"
    assert responses[0]["result"]["region"] is None
    assert responses[1]["error"]["code"] == "INVALID_PARAMS"
    assert responses[2]["error"]["code"] == "INVALID_PARAMS"
    assert responses[3]["error"]["code"] == "ATLAS_REGION_NOT_FOUND"


def test_mesh_path_escape_is_rejected_even_if_adapter_double_returns_it(
    fake_atlas: _FakeLoadedAtlas,
    tmp_path: Path,
) -> None:
    escaped = tmp_path / "outside.obj"
    escaped.write_bytes(b"outside")
    fake_atlas.region_paths[385] = escaped

    responses, _ = _run(
        _request(
            "escaped",
            "atlas.mesh",
            {"protocolVersion": 1, "target": "region", "structureId": 385},
        ),
        atlas=fake_atlas,
    )

    assert responses[0]["error"]["code"] == "ATLAS_MESH_PATH_INVALID"


@pytest.mark.parametrize(
    "method",
    ["atlas.regions", "atlas.search", "atlas.point", "atlas.ray.pick", "atlas.mesh"],
)
def test_all_interaction_methods_require_an_open_atlas(method: str) -> None:
    params_by_method: dict[str, dict[str, object]] = {
        "atlas.regions": {"protocolVersion": 1},
        "atlas.search": {"protocolVersion": 1, "query": "VISp"},
        "atlas.point": {
            "protocolVersion": 1,
            "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
            "apMicrometres": 0,
            "dvMicrometres": 0,
            "mlMicrometres": 0,
        },
        "atlas.ray.pick": _ray_params(),
        "atlas.mesh": {"protocolVersion": 1, "target": "root"},
    }

    responses, _ = _run(
        _request("not-open", method, params_by_method[method]),
        atlas=None,
    )

    assert responses[0]["error"]["code"] == "ATLAS_NOT_OPEN"
