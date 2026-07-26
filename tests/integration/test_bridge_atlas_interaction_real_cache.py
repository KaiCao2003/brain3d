"""Optional smoke coverage against the exact reviewed local atlas package."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from mouse_brain_planner.atlas.brainglobe_adapter import BrainGlobeAtlasRepository
from mouse_brain_planner.bridge.atlas_interaction import (
    register_atlas_interaction_handlers,
)
from mouse_brain_planner.bridge.planning import register_planning_handlers
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher, BridgeError


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
    loaded_atlas = dispatcher.context.loaded_atlas
    assert loaded_atlas is not None
    visp_ids = [
        region.structure_id for region in loaded_atlas.regions if 385 in region.structure_id_path
    ]
    selected_voxel: tuple[int, int, int] | None = None
    for ap_index in range(loaded_atlas.annotation.shape[0]):
        hits = np.argwhere(np.isin(loaded_atlas.annotation[ap_index], visp_ids))
        if hits.size:
            dv_index, ml_index = (int(value) for value in hits[0])
            selected_voxel = (ap_index, dv_index, ml_index)
            break
    assert selected_voxel is not None
    ap_index, dv_index, ml_index = selected_voxel
    visp_overlays = {
        "dorsal": dispatcher.dispatch(
            "atlas.region.overlay",
            {
                "protocolVersion": 1,
                "structureId": 385,
                "orientation": "dorsal",
            },
        ),
        "coronal": dispatcher.dispatch(
            "atlas.region.overlay",
            {
                "protocolVersion": 1,
                "structureId": 385,
                "orientation": "coronal",
                "index": ap_index,
            },
        ),
        "sagittal": dispatcher.dispatch(
            "atlas.region.overlay",
            {
                "protocolVersion": 1,
                "structureId": 385,
                "orientation": "sagittal",
                "index": ml_index,
            },
        ),
        "horizontal": dispatcher.dispatch(
            "atlas.region.overlay",
            {
                "protocolVersion": 1,
                "structureId": 385,
                "orientation": "horizontal",
                "index": dv_index,
            },
        ),
    }

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
    for orientation, overlay in visp_overlays.items():
        assert overlay["orientation"] == orientation
        overlay_region = overlay["region"]
        assert isinstance(overlay_region, dict)
        assert overlay_region["structureId"] == 385
        visible_pixel_count = overlay["visiblePixelCount"]
        assert isinstance(visible_pixel_count, int)
        assert visible_pixel_count > 0
        assert overlay["mimeType"] == "image/png"
        assert overlay["colorModel"] == "RGBA"
        included_structure_ids = overlay["includedStructureIds"]
        assert isinstance(included_structure_ids, list)
        assert len(included_structure_ids) > 1


@pytest.mark.integration
def test_real_cached_rspd4_is_truthfully_ontology_only() -> None:
    repository = BrainGlobeAtlasRepository()
    if not repository.is_cached("allen_mouse_25um", "1.2"):
        pytest.skip("reviewed allen_mouse_25um v1.2 package is not cached")
    dispatcher = BridgeDispatcher(BridgeContext(repository_factory=lambda: repository))
    register_atlas_interaction_handlers(dispatcher)
    register_planning_handlers(dispatcher)
    dispatcher.dispatch(
        "atlas.open",
        {
            "protocolVersion": 1,
            "identifier": "allen_mouse_25um",
            "version": "1.2",
            "allowDownload": False,
        },
    )

    search = dispatcher.dispatch(
        "atlas.search",
        {"protocolVersion": 1, "query": "RSPd4", "limit": 5},
    )
    region = search["results"][0]["region"]  # type: ignore[index]
    assert region["structureId"] == 545  # type: ignore[index]

    with pytest.raises(BridgeError) as captured:
        dispatcher.dispatch(
            "atlas.mesh",
            {"protocolVersion": 1, "target": "region", "structureId": 545},
        )
    assert captured.value.code == "ATLAS_REGION_HAS_NO_ANNOTATED_VOXELS"
    assert captured.value.details["annotationVoxelCount"] == 0
    assert captured.value.details["includedStructureIds"] == [545]

    for orientation, index in (
        ("dorsal", None),
        ("coronal", 208),
        ("sagittal", 228),
        ("horizontal", 20),
    ):
        params: dict[str, object] = {
            "protocolVersion": 1,
            "structureId": 545,
            "orientation": orientation,
        }
        if index is not None:
            params["index"] = index
        overlay = dispatcher.dispatch("atlas.region.overlay", params)
        assert overlay["region"]["structureId"] == 545  # type: ignore[index]
        assert overlay["includedStructureIds"] == [545]
        assert overlay["visiblePixelCount"] == 0
