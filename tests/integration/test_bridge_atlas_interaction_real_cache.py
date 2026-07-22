"""Optional smoke coverage against the exact reviewed local atlas package."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mouse_brain_planner.atlas.brainglobe_adapter import BrainGlobeAtlasRepository
from mouse_brain_planner.bridge.atlas_interaction import (
    register_atlas_interaction_handlers,
)
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher


@pytest.mark.integration
def test_real_cached_25um_regions_point_and_root_mesh_descriptor() -> None:
    repository = BrainGlobeAtlasRepository()
    if not repository.is_cached("allen_mouse_25um", "1.2"):
        pytest.skip("reviewed allen_mouse_25um v1.2 package is not cached")
    dispatcher = BridgeDispatcher(BridgeContext(repository_factory=lambda: repository))
    register_atlas_interaction_handlers(dispatcher)

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
    mesh = dispatcher.dispatch(
        "atlas.mesh",
        {"protocolVersion": 1, "target": "root"},
    )

    assert opened["atlas"]["shapeVoxels"] == [528, 320, 456]
    assert searched["results"][0]["matchKind"] == "acronymExact"  # type: ignore[index]
    assert searched["results"][0]["region"]["structureId"] == 385  # type: ignore[index]
    assert point["containingVoxelIndex"] == {
        "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
        "ap": 120,
        "dv": 80,
        "ml": 180,
    }
    assert point["region"]["structureId"] == 767  # type: ignore[index]
    assert point["region"]["acronym"] == "MOs5"  # type: ignore[index]
    descriptor = mesh["mesh"]
    canonical_path = Path(descriptor["canonicalPath"])  # type: ignore[arg-type,index]
    assert canonical_path.is_file()
    assert descriptor["pathUnderAtlasRoot"] == "meshes/997.obj"  # type: ignore[index]
    assert descriptor["byteSize"] == canonical_path.stat().st_size  # type: ignore[index]
    assert descriptor["sha256"] == hashlib.sha256(canonical_path.read_bytes()).hexdigest()  # type: ignore[index]
    assert descriptor["contentsIncluded"] is False  # type: ignore[index]
