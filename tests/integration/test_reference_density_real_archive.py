"""Opt-in real-source qualification against a caller-selected pinned archive."""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path

import pytest
from PIL import Image

from mouse_brain_planner.atlas.brainglobe_adapter import BrainGlobeAtlasRepository
from mouse_brain_planner.bridge.planning import register_planning_handlers
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher
from mouse_brain_planner.vasculature.density_overlay import (
    ReferenceDensityAtlasBinding,
    render_reference_density_dv_maximum_projection,
)
from mouse_brain_planner.vasculature.reference_store import ReferenceDensityStore


@pytest.mark.integration
def test_real_pinned_archive_prepares_and_reopens_on_cached_25um_atlas(
    tmp_path: Path,
) -> None:
    archive_value = os.environ.get("MOUSE_BRAIN_PLANNER_VASCULAR_ARCHIVE")
    if archive_value is None:
        pytest.skip("set MOUSE_BRAIN_PLANNER_VASCULAR_ARCHIVE for real-source qualification")
    archive = Path(archive_value).expanduser()
    if not archive.is_file():
        pytest.fail("MOUSE_BRAIN_PLANNER_VASCULAR_ARCHIVE does not name a regular file")
    repository = BrainGlobeAtlasRepository()
    if not repository.is_cached("allen_mouse_25um", "1.2"):
        pytest.skip("reviewed allen_mouse_25um v1.2 package is not cached")
    atlas = repository.open(
        "allen_mouse_25um",
        package_version="1.2",
        allow_download=False,
    )
    cache_value = os.environ.get("MOUSE_BRAIN_PLANNER_VASCULAR_TEST_CACHE")
    cache_root = Path(cache_value).expanduser() if cache_value is not None else tmp_path / "cache"
    store = ReferenceDensityStore(cache_root)

    prepared = store.prepare(
        atlas=atlas.metadata,
        atlas_reference_asr=atlas.reference,
        archive_path=archive,
        download_if_missing=False,
    )

    assert prepared.density.values_asr.shape == (264, 160, 228)
    assert prepared.density.provenance.output_voxel_size_um == 50.0
    assert prepared.density.provenance.template_alignment.correlation >= 0.99
    assert not prepared.density.values_asr.flags.writeable
    binding = ReferenceDensityAtlasBinding(
        prepared.density,
        atlas_shape_asr=atlas.metadata.shape_voxels,
        atlas_resolution_um=atlas.metadata.resolution_um,
    )
    projection = render_reference_density_dv_maximum_projection(binding)
    assert projection.rgba.shape == (528, 456, 4)
    assert not projection.rgba.flags.writeable

    reopened = ReferenceDensityStore(cache_root).load_cached(
        atlas=atlas.metadata,
        atlas_reference_asr=atlas.reference,
    )
    assert reopened is not None
    assert reopened.reused_prepared_cache
    assert reopened.prepared_density_sha256 == prepared.prepared_density_sha256

    context = BridgeContext(repository_factory=lambda: repository)
    context.set_loaded_atlas(atlas)
    dispatcher = BridgeDispatcher(context)
    session = register_planning_handlers(dispatcher, reference_density_store=store)
    # Population density is archived from the production bridge. This real-data
    # test binds the preserved implementation explicitly to verify it remains
    # readable without re-advertising the feature to the application.
    dispatcher.register("vascular.reference.prepare", session.vascular_reference_prepare)
    dispatcher.register("vascular.reference.display", session.vascular_reference_display)
    dispatcher.register("vascular.reference.overlay", session.vascular_reference_overlay)
    dispatcher.dispatch(
        "project.new",
        {
            "protocolVersion": 1,
            "animalResearchOnlyAcknowledged": True,
            "subjectId": "reference-density-mouse-A",
        },
    )
    bridge_prepared = dispatcher.dispatch(
        "vascular.reference.prepare",
        {
            "protocolVersion": 1,
            "archivePath": str(archive),
            "downloadIfMissing": False,
        },
    )
    dispatcher.dispatch(
        "vascular.reference.display",
        {"protocolVersion": 1, "visible": True, "opacity": 0.65},
    )
    overlay = dispatcher.dispatch(
        "vascular.reference.overlay",
        {"protocolVersion": 1},
    )
    assert bridge_prepared["density"]["templateCorrelation"] >= 0.99  # type: ignore[index]
    assert overlay["width"] == 456
    assert overlay["height"] == 528
    with Image.open(io.BytesIO(base64.b64decode(str(overlay["pngBase64"])))) as image:
        assert image.mode == "RGBA"
        assert image.size == (456, 528)
