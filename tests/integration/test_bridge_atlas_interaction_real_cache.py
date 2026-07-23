"""Optional smoke coverage against the exact reviewed local atlas package."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mouse_brain_planner.atlas.brainglobe_adapter import BrainGlobeAtlasRepository
from mouse_brain_planner.bridge.atlas_interaction import (
    register_atlas_interaction_handlers,
)
from mouse_brain_planner.bridge.planning import register_planning_handlers
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher


@pytest.mark.integration
def test_real_cached_25um_full_ontology_point_and_mesh_descriptors() -> None:
    repository = BrainGlobeAtlasRepository()
    if not repository.is_cached("allen_mouse_25um", "1.2"):
        pytest.skip("reviewed allen_mouse_25um v1.2 package is not cached")
    dispatcher = BridgeDispatcher(BridgeContext(repository_factory=lambda: repository))
    register_atlas_interaction_handlers(dispatcher)
    register_planning_handlers(dispatcher)

    opened = dispatcher.dispatch(
        "atlas.open",
        {
            "protocolVersion": 1,
            "identifier": "allen_mouse_25um",
            "version": "1.2",
            "allowDownload": False,
        },
    )
    searched = dispatcher.dispatch(
        "atlas.search",
        {"protocolVersion": 1, "query": "VISp", "limit": 5},
    )
    regions = dispatcher.dispatch(
        "atlas.regions",
        {"protocolVersion": 1, "offset": 0, "limit": 1},
    )
    thalamus_search = dispatcher.dispatch(
        "atlas.search",
        {"protocolVersion": 1, "query": "Thalamus", "limit": 5},
    )
    point = dispatcher.dispatch(
        "atlas.point",
        {
            "protocolVersion": 1,
            "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
            "apMicrometres": 3000.0,
            "dvMicrometres": 2000.0,
            "mlMicrometres": 4500.0,
        },
    )
    ray = dispatcher.dispatch(
        "atlas.ray.pick",
        {
            "protocolVersion": 1,
            "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
            "startApMicrometres": 3000.0,
            "startDvMicrometres": -1000.0,
            "startMlMicrometres": 4500.0,
            "endApMicrometres": 3000.0,
            "endDvMicrometres": 9000.0,
            "endMlMicrometres": 4500.0,
        },
    )
    dorsal_pick = dispatcher.dispatch(
        "atlas.dorsal.pick",
        {"protocolVersion": 1, "column": 180, "row": 120},
    )
    mesh = dispatcher.dispatch(
        "atlas.mesh",
        {"protocolVersion": 1, "target": "root"},
    )
    thalamus_id = thalamus_search["results"][0]["region"]["structureId"]  # type: ignore[index]
    thalamus_mesh = dispatcher.dispatch(
        "atlas.mesh",
        {"protocolVersion": 1, "target": "region", "structureId": thalamus_id},
    )

    assert opened["atlas"]["shapeVoxels"] == [528, 320, 456]
    assert regions["totalCount"] == 840
    assert searched["results"][0]["matchKind"] == "acronymExact"  # type: ignore[index]
    assert searched["results"][0]["region"]["structureId"] == 385  # type: ignore[index]
    assert thalamus_search["results"][0]["region"]["acronym"] == "TH"  # type: ignore[index]
    assert point["containingVoxelIndex"] == {
        "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
        "ap": 120,
        "dv": 80,
        "ml": 180,
    }
    assert point["region"]["structureId"] == 767  # type: ignore[index]
    assert point["region"]["acronym"] == "MOs5"  # type: ignore[index]
    assert ray["status"] == "hit"
    assert ray["hit"]["annotationStructureId"] > 0  # type: ignore[index,operator]
    assert ray["hit"]["region"]["name"]  # type: ignore[index]
    assert dorsal_pick["status"] == "hit"
    assert dorsal_pick["containingVoxelIndex"]["ap"] == 120  # type: ignore[index]
    assert dorsal_pick["containingVoxelIndex"]["ml"] == 180  # type: ignore[index]
    assert dorsal_pick["annotationStructureId"] == dorsal_pick["region"]["structureId"]  # type: ignore[index]
    assert dorsal_pick["atlas"]["metadataSha256"] == opened["atlas"]["metadataSha256"]  # type: ignore[index]
    descriptor = mesh["mesh"]
    canonical_path = Path(descriptor["canonicalPath"])  # type: ignore[arg-type,index]
    assert canonical_path.is_file()
    assert descriptor["pathUnderAtlasRoot"] == "meshes/997.obj"  # type: ignore[index]
    assert descriptor["byteSize"] == canonical_path.stat().st_size  # type: ignore[index]
    assert descriptor["sha256"] == hashlib.sha256(canonical_path.read_bytes()).hexdigest()  # type: ignore[index]
    assert descriptor["contentsIncluded"] is False  # type: ignore[index]
    thalamus_descriptor = thalamus_mesh["mesh"]
    thalamus_path = Path(thalamus_descriptor["canonicalPath"])  # type: ignore[arg-type,index]
    assert thalamus_mesh["region"]["acronym"] == "TH"  # type: ignore[index]
    assert thalamus_descriptor["pathUnderAtlasRoot"] == f"meshes/{thalamus_id}.obj"  # type: ignore[index]
    assert thalamus_path.is_file()
    assert thalamus_descriptor["sha256"] == hashlib.sha256(thalamus_path.read_bytes()).hexdigest()
