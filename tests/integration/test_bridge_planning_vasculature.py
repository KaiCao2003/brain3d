from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from mouse_brain_planner.bridge import planning as planning_module
from mouse_brain_planner.bridge.planning import (
    ANIMAL_ONLY_WARNING,
    PlanningBridgeSession,
    register_planning_handlers,
)
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher, BridgeError
from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.persistence.project_io import save_project
from mouse_brain_planner.vasculature.reference_density import (
    BRAINGLOBE_ASR_FRAME_AP_DV_ML,
    STXVN5SV44_V1_SOURCE,
    ReferenceDensityProvenance,
    ReferenceVascularDensity,
    TemplateAlignmentEvidence,
)
from mouse_brain_planner.vasculature.reference_store import CachedReferenceDensity


@dataclass(slots=True)
class _FakeAtlas:
    metadata: AtlasMetadata
    reference: NDArray[np.uint16]
    annotation: NDArray[np.int32]
    brainglobe_atlasapi_version: str = "2.3.1"

    @property
    def regions(self) -> list[RegionRecord]:
        return [
            RegionRecord(
                structure_id=1,
                acronym="TEST",
                name="Test region",
                structure_id_path=(1,),
                rgb=(12, 34, 56),
            )
        ]

    def region_at(self, point: BrainGlobePhysicalPoint) -> RegionRecord | None:
        del point
        return self.regions[0]


def _metadata() -> AtlasMetadata:
    return AtlasMetadata(
        atlas_key="allen_mouse_25um",
        atlas_package_version="1.2",
        species="Mus musculus",
        citation="Allen CCFv3",
        source_url="https://example.invalid/atlas",
        cache_path="/verified/cache",
        metadata_sha256="b" * 64,
        resolution_um=(1.0, 1.0, 1.0),
        shape_voxels=(4, 2, 4),
        symmetric=True,
        midline_ml_um=2.0,
        axes=(
            AtlasAxis(
                array_axis=0,
                anatomical_axis="AP",
                origin_direction="anterior",
                positive_direction="posterior",
                voxel_size_um=1.0,
            ),
            AtlasAxis(
                array_axis=1,
                anatomical_axis="DV",
                origin_direction="superior",
                positive_direction="inferior",
                voxel_size_um=1.0,
            ),
            AtlasAxis(
                array_axis=2,
                anatomical_axis="ML",
                origin_direction="right",
                positive_direction="left",
                voxel_size_um=1.0,
            ),
        ),
    )


def _dispatcher() -> tuple[BridgeDispatcher, PlanningBridgeSession]:
    atlas = _FakeAtlas(
        metadata=_metadata(),
        reference=np.arange(32, dtype=np.uint16).reshape(4, 2, 4),
        annotation=np.ones((4, 2, 4), dtype=np.int32),
    )
    context = BridgeContext(repository_factory=lambda: pytest.fail("repository not expected"))
    context.set_loaded_atlas(atlas)
    dispatcher = BridgeDispatcher(context)
    return dispatcher, register_planning_handlers(dispatcher)


def _register_archived_subject_vascular_handlers_for_test(
    dispatcher: BridgeDispatcher,
    session: PlanningBridgeSession,
) -> None:
    """Bind legacy handlers only inside tests that verify archive compatibility."""

    dispatcher.register("vascular.import", session.vascular_import)
    dispatcher.register("vascular.preview", session.vascular_preview)
    dispatcher.register("vascular.register", session.vascular_register)
    dispatcher.register("vascular.overlay", session.vascular_overlay)


def _register_archived_population_density_handlers_for_test(
    dispatcher: BridgeDispatcher,
    session: PlanningBridgeSession,
) -> None:
    """Bind archived population-density handlers without advertising them."""

    dispatcher.register("vascular.reference.prepare", session.vascular_reference_prepare)
    dispatcher.register("vascular.reference.display", session.vascular_reference_display)
    dispatcher.register("vascular.reference.overlay", session.vascular_reference_overlay)


def _archived_subject_vascular_dispatcher() -> tuple[
    BridgeDispatcher,
    PlanningBridgeSession,
]:
    dispatcher, session = _dispatcher()
    _register_archived_subject_vascular_handlers_for_test(dispatcher, session)
    return dispatcher, session


def _reference_metadata() -> AtlasMetadata:
    voxel_size = 25.0
    return AtlasMetadata(
        atlas_key="allen_mouse_25um",
        atlas_package_version="1.2",
        species="Mus musculus",
        citation="Allen CCFv3",
        source_url="https://example.invalid/atlas",
        cache_path="/verified/reference-cache",
        metadata_sha256="c" * 64,
        resolution_um=(voxel_size, voxel_size, voxel_size),
        shape_voxels=(4, 2, 4),
        symmetric=True,
        midline_ml_um=50.0,
        axes=tuple(
            AtlasAxis(
                array_axis=index,  # type: ignore[arg-type]
                anatomical_axis=anatomical,  # type: ignore[arg-type]
                origin_direction=origin,  # type: ignore[arg-type]
                positive_direction=positive,  # type: ignore[arg-type]
                voxel_size_um=voxel_size,
            )
            for index, anatomical, origin, positive in (
                (0, "AP", "anterior", "posterior"),
                (1, "DV", "superior", "inferior"),
                (2, "ML", "right", "left"),
            )
        ),  # type: ignore[arg-type]
    )


def _cached_reference_density(metadata: AtlasMetadata) -> CachedReferenceDensity:
    values = np.asarray([[[0.0, 1.0]], [[2.0, 2.5]]], dtype=np.float32)
    values.setflags(write=False)
    alignment = TemplateAlignmentEvidence(
        correlation=0.997,
        minimum_correlation=0.99,
        source_shape_mldvpa=STXVN5SV44_V1_SOURCE.source_shape_mldvpa,
        target_shape_asr=metadata.shape_voxels,
        source_voxel_size_um=STXVN5SV44_V1_SOURCE.source_voxel_size_um,
        target_voxel_size_um=25.0,
    )
    provenance = ReferenceDensityProvenance(
        source=STXVN5SV44_V1_SOURCE,
        output_frame=BRAINGLOBE_ASR_FRAME_AP_DV_ML,
        output_shape_asr=(2, 1, 2),
        output_voxel_size_um=50.0,
        output_extent_um_asr=(100.0, 50.0, 100.0),
        template_alignment=alignment,
    )
    return CachedReferenceDensity(
        density=ReferenceVascularDensity(values_asr=values, provenance=provenance),
        prepared_density_sha256="d" * 64,
        atlas_metadata_sha256=metadata.metadata_sha256,
        atlas_reference_sha256="e" * 64,
        archive_sha256_verified=True,
        reused_prepared_cache=False,
    )


@dataclass(slots=True)
class _FakeReferenceDensityStore:
    cached: CachedReferenceDensity
    archive_path: Path | None = None
    download_if_missing: bool | None = None

    def prepare(
        self,
        *,
        atlas: AtlasMetadata,
        atlas_reference_asr: NDArray[np.generic],
        archive_path: Path | None,
        download_if_missing: bool,
    ) -> CachedReferenceDensity:
        assert atlas.metadata_sha256 == self.cached.atlas_metadata_sha256
        assert atlas_reference_asr.shape == atlas.shape_voxels
        self.archive_path = archive_path
        self.download_if_missing = download_if_missing
        return self.cached

    def load_cached(
        self,
        *,
        atlas: AtlasMetadata,
        atlas_reference_asr: NDArray[np.generic],
    ) -> CachedReferenceDensity | None:
        assert atlas_reference_asr.shape == atlas.shape_voxels
        return self.cached


def _reference_dispatcher() -> tuple[
    BridgeDispatcher,
    PlanningBridgeSession,
    _FakeReferenceDensityStore,
]:
    metadata = _reference_metadata()
    atlas = _FakeAtlas(
        metadata=metadata,
        reference=np.arange(32, dtype=np.uint16).reshape(metadata.shape_voxels),
        annotation=np.ones(metadata.shape_voxels, dtype=np.int32),
    )
    context = BridgeContext(repository_factory=lambda: pytest.fail("repository not expected"))
    context.set_loaded_atlas(atlas)
    dispatcher = BridgeDispatcher(context)
    store = _FakeReferenceDensityStore(_cached_reference_density(metadata))
    session = register_planning_handlers(dispatcher, reference_density_store=store)
    _register_archived_population_density_handlers_for_test(dispatcher, session)
    return dispatcher, session, store


def _call(dispatcher: BridgeDispatcher, rpc_method: str, **params: object) -> dict[str, object]:
    return dispatcher.dispatch(rpc_method, {"protocolVersion": 1, **params})


def _write_subject_png(path: Path) -> NDArray[np.uint8]:
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    for row in range(4):
        for column in range(4):
            pixels[row, column] = (row * 40, column * 50, 10, 255)
    Image.fromarray(pixels, mode="RGBA").save(path)
    return pixels


def _landmarks() -> list[dict[str, object]]:
    return [
        {
            "label": "anterior-right",
            "kind": "bregma",
            "imageColumnPixels": 0.0,
            "imageRowPixels": 0.0,
            "atlasApMicrometres": 0.5,
            "atlasMlMicrometres": 3.5,
            "enabled": True,
        },
        {
            "label": "anterior-left",
            "kind": "vessel-bifurcation",
            "imageColumnPixels": 3.0,
            "imageRowPixels": 0.0,
            "atlasApMicrometres": 0.5,
            "atlasMlMicrometres": 0.5,
            "enabled": True,
        },
        {
            "label": "posterior-right",
            "kind": "lambda",
            "imageColumnPixels": 0.0,
            "imageRowPixels": 3.0,
            "atlasApMicrometres": 3.5,
            "atlasMlMicrometres": 3.5,
            "enabled": True,
        },
    ]


def _new_project(dispatcher: BridgeDispatcher) -> None:
    result = _call(
        dispatcher,
        "project.new",
        animalResearchOnlyAcknowledged=True,
        title="Mouse A dorsal plan",
        subjectId="animal-A",
    )
    assert result["status"] == "created"
    assert result["animalOnly"] is True
    assert result["warning"] == ANIMAL_ONLY_WARNING


def _save_project(
    dispatcher: BridgeDispatcher,
    session: PlanningBridgeSession,
    *,
    path: Path | None = None,
) -> dict[str, object]:
    assert session.project is not None
    params: dict[str, object] = {
        "projectId": str(session.project.project_uuid),
        "expectedProjectRevision": session.project_revision,
    }
    if path is not None:
        params["path"] = str(path)
    return _call(dispatcher, "project.save", **params)


def test_primary_bridge_does_not_expose_archived_vascular_methods_or_capabilities() -> None:
    dispatcher, _ = _dispatcher()

    hello = _call(dispatcher, "hello", client="archive-boundary-test")
    capabilities = hello["capabilities"]
    assert isinstance(capabilities, dict)
    assert {
        "subjectVascularImport",
        "subjectVascularOverlay",
        "subjectVascularRegistration",
        "populationReferenceDensityPrepare",
        "populationReferenceDensityDisplayMutation",
        "populationReferenceDensityOverlay",
    }.isdisjoint(capabilities)

    archived_methods = (
        "vascular.import",
        "vascular.preview",
        "vascular.register",
        "vascular.overlay",
        "vascular.reference.prepare",
        "vascular.reference.display",
        "vascular.reference.overlay",
    )
    for method in archived_methods:
        with pytest.raises(BridgeError) as caught:
            _call(dispatcher, method)
        assert caught.value.code == "METHOD_NOT_FOUND"
        assert caught.value.details == {"method": method}


def test_archived_subject_vessel_journey_saves_reopens_and_preserves_registration(
    tmp_path: Path,
) -> None:
    dispatcher, session = _archived_subject_vascular_dispatcher()
    _new_project(dispatcher)
    source = tmp_path / "animal-dorsal.png"
    source_pixels = _write_subject_png(source)

    imported = _call(dispatcher, "vascular.import", path=str(source))
    image = imported["image"]
    assert isinstance(image, dict)
    image_id = image["imageId"]
    assert isinstance(image_id, str)
    assert image["sourceName"] == source.name
    assert image["subjectSpecific"] is True

    preview = _call(dispatcher, "vascular.preview", imageId=image_id)
    with Image.open(io.BytesIO(base64.b64decode(str(preview["pngBase64"])))) as decoded:
        assert decoded.size == (4, 4)
    assert preview["originalWidthPixels"] == 4
    assert preview["previewToOriginalScaleX"] == 1.0

    registered = _call(
        dispatcher,
        "vascular.register",
        imageId=image_id,
        method="similarity",
        landmarks=_landmarks(),
        lateralityConfirmed=True,
        opacity=0.5,
    )
    assert registered["status"] == "registered"
    assert registered["lateralityConfirmed"] is True
    assert registered["rmsResidualMicrometres"] == pytest.approx(0.0, abs=1e-12)
    matrix_before = registered["matrixRowMajor"]

    overlay = _call(dispatcher, "vascular.overlay", imageId=image_id, opacity=0.5)
    assert overlay["subjectSpecific"] is True
    assert overlay["rowAxis"] == "AP"
    assert overlay["columnAxis"] == "ML"
    with Image.open(io.BytesIO(base64.b64decode(str(overlay["pngBase64"])))) as decoded:
        rendered = np.asarray(decoded.convert("RGBA"), dtype=np.uint8)
    expected = source_pixels[:, ::-1].copy()
    expected[..., 3] = 128
    np.testing.assert_array_equal(rendered, expected)

    destination = tmp_path / "animal-a.mouseplan"
    saved = _save_project(dispatcher, session, path=destination)
    assert saved["status"] == "saved"
    assert destination.is_dir()
    assert (destination / "images").is_dir()

    reopened_dispatcher, reopened_session = _archived_subject_vascular_dispatcher()
    opened = _call(reopened_dispatcher, "project.open", path=str(destination))
    assert opened["status"] == "opened"
    assert opened["subjectVascularImageCount"] == 1
    state = _call(reopened_dispatcher, "state.get")
    subject_vessels = state["subjectVessels"]
    assert isinstance(subject_vessels, dict)
    assert subject_vessels["imported"] is True
    assert subject_vessels["registered"] is True
    vessel_images = subject_vessels["images"]
    assert isinstance(vessel_images, list)
    assert vessel_images[0]["lateralityConfirmed"] is True
    registration_after = reopened_session.project
    assert registration_after is not None
    assert (
        list(registration_after.dorsal_vascular_registrations[0].matrix_row_major) == matrix_before
    )
    reopened_overlay = _call(
        reopened_dispatcher,
        "vascular.overlay",
        imageId=image_id,
        opacity=0.5,
    )
    assert reopened_overlay["pngBase64"] == overlay["pngBase64"]
    assert session.project is not None


def test_project_creation_requires_animal_only_acknowledgement() -> None:
    dispatcher, _ = _dispatcher()

    with pytest.raises(BridgeError) as caught:
        _call(
            dispatcher,
            "project.new",
            animalResearchOnlyAcknowledged=False,
        )

    assert caught.value.code == "ANIMAL_ONLY_ACKNOWLEDGEMENT_REQUIRED"


def test_project_creation_requires_animal_subject_id() -> None:
    dispatcher, _ = _dispatcher()

    with pytest.raises(BridgeError) as caught:
        _call(
            dispatcher,
            "project.new",
            animalResearchOnlyAcknowledged=True,
        )

    assert caught.value.code == "ANIMAL_SUBJECT_ID_REQUIRED"


@pytest.mark.parametrize("subject_id", [None, "   "])
def test_project_open_rejects_subjectless_legacy_package(
    tmp_path: Path,
    subject_id: str | None,
) -> None:
    metadata = _metadata()
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=1.5,
        dv_um=0.5,
        ml_um=1.5,
    )
    path = save_project(
        PlannerProject(
            title="Legacy subjectless project",
            subject_id=subject_id,
            atlas=metadata,
            renderer_anchor=anchor,
            scientific_disclaimer_acknowledged=True,
        ),
        tmp_path / "subjectless.mouseplan",
    )
    dispatcher, session = _dispatcher()

    with pytest.raises(BridgeError) as caught:
        _call(dispatcher, "project.open", path=str(path))

    assert caught.value.code == "ANIMAL_SUBJECT_ID_REQUIRED"
    assert "explicit subject ID" in caught.value.message
    assert caught.value.details == {
        "projectOpened": False,
        "suggestedAction": "Create a new animal plan with an explicit subject ID.",
    }
    assert session.project is None
    assert session.project_revision == 0


def test_backend_project_revision_is_authoritative_for_unsaved_changes(
    tmp_path: Path,
) -> None:
    dispatcher, session = _dispatcher()
    _new_project(dispatcher)

    created_state = _call(dispatcher, "state.get")
    created_project = created_state["project"]
    assert isinstance(created_project, dict)
    assert created_project["revision"] == 1
    assert created_project["isDirty"] is True
    events = created_project["eventLog"]
    assert isinstance(events, list)
    assert len(events) == 1
    assert events[0]["action"] == "project-created"
    assert events[0]["details"] == ANIMAL_ONLY_WARNING
    assert created_project["rendererAnchor"] == {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "apMicrometres": 2.5,
        "dvMicrometres": 1.5,
        "mlMicrometres": 2.5,
    }

    destination = tmp_path / "revision.mouseplan"
    _save_project(dispatcher, session, path=destination)
    saved_state = _call(dispatcher, "state.get")
    saved_project = saved_state["project"]
    assert isinstance(saved_project, dict)
    assert saved_project["revision"] == 2
    assert saved_project["isDirty"] is False

    _call(
        dispatcher,
        "viewer.slice.set",
        projectId=saved_project["projectId"],
        expectedProjectRevision=2,
        orientation="coronal",
        index=1,
    )
    imported_state = _call(dispatcher, "state.get")
    imported_project = imported_state["project"]
    assert isinstance(imported_project, dict)
    assert imported_project["revision"] == 3
    assert imported_project["isDirty"] is True

    _save_project(dispatcher, session)
    resaved_state = _call(dispatcher, "state.get")
    resaved_project = resaved_state["project"]
    assert isinstance(resaved_project, dict)
    assert resaved_project["revision"] == 4
    assert resaved_project["isDirty"] is False

    reopened_dispatcher, _ = _dispatcher()
    _call(reopened_dispatcher, "project.open", path=str(destination))
    reopened_state = _call(reopened_dispatcher, "state.get")
    reopened_project = reopened_state["project"]
    assert isinstance(reopened_project, dict)
    assert reopened_project["revision"] == 4
    assert reopened_project["isDirty"] is False
    with pytest.raises(BridgeError) as stale:
        _call(
            reopened_dispatcher,
            "viewer.slice.set",
            projectId=reopened_project["projectId"],
            expectedProjectRevision=0,
            orientation="coronal",
            index=0,
        )
    assert stale.value.code == "PROJECT_REVISION_CONFLICT"


def test_project_save_rejects_wrong_stale_and_out_of_order_requests_without_overwrite(
    tmp_path: Path,
) -> None:
    dispatcher, session = _dispatcher()
    _new_project(dispatcher)
    assert session.project is not None
    project_id = str(session.project.project_uuid)
    destination = tmp_path / "revision-guard.mouseplan"

    with pytest.raises(BridgeError) as wrong_project:
        _call(
            dispatcher,
            "project.save",
            projectId="00000000-0000-0000-0000-000000000001",
            expectedProjectRevision=session.project_revision,
            path=str(destination),
        )
    assert wrong_project.value.code == "PROJECT_ID_MISMATCH"
    assert not destination.exists()
    assert session.project_revision == 1

    with pytest.raises(BridgeError) as stale_initial:
        _call(
            dispatcher,
            "project.save",
            projectId=project_id,
            expectedProjectRevision=0,
            path=str(destination),
        )
    assert stale_initial.value.code == "PROJECT_REVISION_CONFLICT"
    assert not destination.exists()
    assert session.project_revision == 1

    saved = _call(
        dispatcher,
        "project.save",
        projectId=project_id,
        expectedProjectRevision=1,
        path=str(destination),
    )
    assert saved["projectId"] == project_id
    assert saved["projectRevision"] == 2
    assert session.project_revision == 2
    assert session.project.project_revision == 2

    # A request prepared at revision 2 becomes stale after another mutation.
    _call(
        dispatcher,
        "viewer.slice.set",
        projectId=project_id,
        expectedProjectRevision=2,
        orientation="coronal",
        index=0,
    )
    assert session.project_revision == 3
    with pytest.raises(BridgeError) as out_of_order:
        _call(
            dispatcher,
            "project.save",
            projectId=project_id,
            expectedProjectRevision=2,
            path=str(destination),
        )
    assert out_of_order.value.code == "PROJECT_REVISION_CONFLICT"
    assert session.project_revision == 3

    reopened_dispatcher, reopened_session = _dispatcher()
    _call(reopened_dispatcher, "project.open", path=str(destination))
    assert reopened_session.project is not None
    assert reopened_session.project_revision == 2
    assert reopened_session.project.project_revision == 2


def test_project_save_failure_rolls_back_revision_event_and_session_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher, session = _dispatcher()
    _new_project(dispatcher)
    assert session.project is not None
    before = session.project.model_dump(mode="json")
    before_revision = session.project_revision

    def fail_save(*args: object, **kwargs: object) -> Path:
        del args, kwargs
        raise OSError("test-only save failure")

    monkeypatch.setattr(planning_module, "save_project", fail_save)
    destination = tmp_path / "must-not-exist.mouseplan"
    with pytest.raises(BridgeError) as failure:
        _save_project(dispatcher, session, path=destination)

    assert failure.value.code == "PROJECT_SAVE_FAILED"
    assert session.project is not None
    assert session.project.model_dump(mode="json") == before
    assert session.project_revision == before_revision == 1
    assert session.project.project_revision == before_revision
    assert session.project_path is None
    assert session.saved_revision is None
    assert not destination.exists()


def test_archived_unconfirmed_laterality_never_produces_subject_overlay(
    tmp_path: Path,
) -> None:
    dispatcher, _ = _archived_subject_vascular_dispatcher()
    _new_project(dispatcher)
    source = tmp_path / "animal-dorsal.png"
    _write_subject_png(source)
    imported = _call(dispatcher, "vascular.import", path=str(source))
    image = imported["image"]
    assert isinstance(image, dict)
    image_id = image["imageId"]
    _call(
        dispatcher,
        "vascular.register",
        imageId=image_id,
        method="similarity",
        landmarks=_landmarks(),
        lateralityConfirmed=False,
    )

    with pytest.raises(BridgeError) as caught:
        _call(dispatcher, "vascular.overlay", imageId=image_id)

    assert caught.value.code == "VASCULAR_LATERALITY_CONFIRMATION_REQUIRED"


def test_state_never_describes_population_density_as_subject_vessel_paths() -> None:
    dispatcher, _ = _dispatcher()
    _new_project(dispatcher)

    state = _call(dispatcher, "state.get")
    density = state["populationDensity"]
    assert isinstance(density, dict)
    assert density["available"] is False
    assert density["visible"] is False
    assert density["opacity"] == 0.65
    assert "not subject-specific vessel paths" in str(density["disclaimer"])


def test_atlas_dorsal_returns_real_ap_ml_surface_projection() -> None:
    dispatcher, _ = _dispatcher()

    dorsal = _call(dispatcher, "atlas.dorsal")

    assert dorsal["width"] == 4
    assert dorsal["height"] == 4
    assert dorsal["rowAxis"] == "AP"
    assert dorsal["columnAxis"] == "ML"
    assert dorsal["surfaceDvMinimumMicrometres"] == 0.5
    assert dorsal["surfaceDvMaximumMicrometres"] == 0.5
    assert "not a subject skull surface" in str(dorsal["displayLabel"])
    with Image.open(io.BytesIO(base64.b64decode(str(dorsal["pngBase64"])))) as decoded:
        assert decoded.size == (4, 4)


def test_atlas_dorsal_pick_capability_is_discoverable() -> None:
    dispatcher, _ = _dispatcher()

    hello = _call(dispatcher, "hello", client="dorsal-pick-test")

    capabilities = hello["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["atlasDorsalRegionPick"] is True


def test_atlas_dorsal_pick_returns_first_annotated_dv_voxel() -> None:
    dispatcher, _ = _dispatcher()
    atlas = dispatcher.context.loaded_atlas
    assert isinstance(atlas, _FakeAtlas)
    atlas.annotation.fill(0)
    atlas.annotation[2, 1, 3] = 1

    picked = _call(dispatcher, "atlas.dorsal.pick", column=3, row=2)

    assert set(picked) == {
        "protocolVersion",
        "status",
        "column",
        "row",
        "atlasPoint",
        "containingVoxelIndex",
        "annotationStructureId",
        "region",
        "hemisphere",
        "atlas",
    }
    assert picked["status"] == "hit"
    assert picked["column"] == 3
    assert picked["row"] == 2
    assert picked["atlasPoint"] == {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "apMicrometres": 2.5,
        "dvMicrometres": 1.5,
        "mlMicrometres": 3.5,
    }
    assert picked["containingVoxelIndex"] == {
        "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
        "ap": 2,
        "dv": 1,
        "ml": 3,
    }
    assert picked["annotationStructureId"] == 1
    assert picked["region"] == {
        "structureId": 1,
        "acronym": "TEST",
        "name": "Test region",
        "parentStructureId": None,
        "structureIdPath": [1],
        "rgb": [12, 34, 56],
    }
    assert picked["hemisphere"] == "left"
    identity = picked["atlas"]
    assert isinstance(identity, dict)
    assert set(identity) == {
        "identifier",
        "version",
        "metadataSha256",
        "resolutionMicrometres",
        "shapeVoxels",
        "orientation",
        "frameworkName",
        "sourceAnnotation",
        "citation",
        "brainGlobeAtlasApiVersion",
    }
    assert identity["identifier"] == "allen_mouse_25um"
    assert identity["version"] == "1.2"
    assert identity["metadataSha256"] == "b" * 64
    assert identity["resolutionMicrometres"] == [1.0, 1.0, 1.0]
    assert identity["shapeVoxels"] == [4, 2, 4]


def test_atlas_dorsal_pick_returns_explicit_no_annotation_payload() -> None:
    dispatcher, _ = _dispatcher()
    atlas = dispatcher.context.loaded_atlas
    assert isinstance(atlas, _FakeAtlas)
    atlas.annotation.fill(0)

    picked = _call(dispatcher, "atlas.dorsal.pick", column=1, row=3)

    assert picked["status"] == "noAnnotatedVoxel"
    assert picked["column"] == 1
    assert picked["row"] == 3
    for field in (
        "atlasPoint",
        "containingVoxelIndex",
        "annotationStructureId",
        "region",
        "hemisphere",
    ):
        assert picked[field] is None
    assert isinstance(picked["atlas"], dict)


@pytest.mark.parametrize(
    ("params", "error_code"),
    (
        ({"protocolVersion": 1, "column": 0}, "INVALID_PARAMS"),
        (
            {"protocolVersion": 1, "column": 0, "row": 0, "unexpected": 1},
            "INVALID_PARAMS",
        ),
        ({"protocolVersion": 1, "column": True, "row": 0}, "INVALID_PARAMS"),
        ({"protocolVersion": 1, "column": 0, "row": 0.0}, "INVALID_PARAMS"),
        ({"protocolVersion": 1, "column": -1, "row": 0}, "INVALID_PARAMS"),
        ({"protocolVersion": 1, "column": 4, "row": 0}, "DORSAL_PICK_OUT_OF_RANGE"),
        ({"protocolVersion": 1, "column": 0, "row": 4}, "DORSAL_PICK_OUT_OF_RANGE"),
        ({"protocolVersion": 2, "column": 0, "row": 0}, "PROTOCOL_VERSION_MISMATCH"),
    ),
)
def test_atlas_dorsal_pick_rejects_invalid_schema_types_and_bounds(
    params: dict[str, object],
    error_code: str,
) -> None:
    dispatcher, _ = _dispatcher()

    with pytest.raises(BridgeError) as caught:
        dispatcher.dispatch("atlas.dorsal.pick", params)

    assert caught.value.code == error_code


def test_atlas_dorsal_pick_rejects_annotation_region_identity_mismatch() -> None:
    dispatcher, _ = _dispatcher()
    atlas = dispatcher.context.loaded_atlas
    assert isinstance(atlas, _FakeAtlas)
    atlas.annotation.fill(0)
    atlas.annotation[0, 0, 0] = 999

    with pytest.raises(BridgeError) as caught:
        _call(dispatcher, "atlas.dorsal.pick", column=0, row=0)

    assert caught.value.code == "ATLAS_CONTRACT_VIOLATION"


def test_atlas_dorsal_pick_requires_open_atlas() -> None:
    dispatcher = BridgeDispatcher()
    register_planning_handlers(dispatcher)

    with pytest.raises(BridgeError) as caught:
        _call(dispatcher, "atlas.dorsal.pick", column=0, row=0)

    assert caught.value.code == "ATLAS_NOT_OPEN"


def test_population_reference_prepare_updates_runtime_project_and_exact_contract(
    tmp_path: Path,
) -> None:
    dispatcher, _, store = _reference_dispatcher()
    _new_project(dispatcher)
    selected_archive = tmp_path / "selected.7z"

    result = _call(
        dispatcher,
        "vascular.reference.prepare",
        archivePath=str(selected_archive),
        downloadIfMissing=False,
    )

    assert set(result) == {
        "protocolVersion",
        "status",
        "source",
        "atlas",
        "density",
        "cache",
        "disclosure",
    }
    assert result["status"] == "preparedReferenceDensity"
    source = result["source"]
    assert isinstance(source, dict)
    assert source["doi"] == "10.17632/stxvn5sv44.1"
    assert source["archiveSizeBytes"] == 311_493_514
    assert source["archiveSha256"] == (
        "c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe"
    )
    density = result["density"]
    assert isinstance(density, dict)
    assert density["outputShapeASR"] == [2, 1, 2]
    assert density["outputResolutionMicrometres"] == 50.0
    assert density["templateCorrelation"] == 0.997
    assert density["subjectSpecific"] is False
    assert density["containsIndividualVesselPaths"] is False
    assert density["supportsVesselClearance"] is False
    cache = result["cache"]
    assert isinstance(cache, dict)
    assert cache == {
        "archiveSha256Verified": True,
        "preparedDensitySha256": "d" * 64,
        "reusedPreparedCache": False,
    }
    assert store.archive_path == selected_archive
    assert store.download_if_missing is False

    state = _call(dispatcher, "state.get")
    population = state["populationDensity"]
    project = state["project"]
    assert isinstance(population, dict)
    assert isinstance(project, dict)
    assert population["available"] is True
    assert population["visible"] is False
    assert population["opacity"] == 0.65
    assert population["status"] == "preparedReferenceDensity"
    assert project["revision"] == 2
    assert project["isDirty"] is True


def test_population_reference_overlay_is_transparent_ap_ml_dv_maximum_png() -> None:
    dispatcher, _, _ = _reference_dispatcher()
    _new_project(dispatcher)
    _call(dispatcher, "vascular.reference.prepare", downloadIfMissing=False)
    display = _call(
        dispatcher,
        "vascular.reference.display",
        visible=True,
        opacity=0.42,
    )

    overlay = _call(dispatcher, "vascular.reference.overlay")

    assert display == {
        "protocolVersion": 1,
        "status": "updatedReferenceDensityDisplay",
        "display": {"visible": True, "opacity": 0.42},
    }

    assert set(overlay) == {
        "protocolVersion",
        "status",
        "mimeType",
        "pngBase64",
        "width",
        "height",
        "rowAxis",
        "columnAxis",
        "projectionAxis",
        "projectionMethod",
        "atlasResolutionMicrometres",
        "densityResolutionMicrometres",
        "window",
        "display",
        "source",
        "atlas",
        "subjectSpecific",
        "containsIndividualVesselPaths",
        "supportsVesselClearance",
        "displayLabel",
        "disclosure",
    }
    assert overlay["status"] == "renderedReferenceDensity"
    assert overlay["width"] == 4
    assert overlay["height"] == 4
    assert overlay["rowAxis"] == "AP"
    assert overlay["columnAxis"] == "ML"
    assert overlay["projectionAxis"] == "DV"
    assert overlay["projectionMethod"] == "maximum"
    assert overlay["atlasResolutionMicrometres"] == [25.0, 25.0]
    assert overlay["densityResolutionMicrometres"] == 50.0
    assert overlay["window"] == {
        "low": 0.0,
        "high": 2.5,
        "units": "m/mm^3",
        "opacity": 0.42,
        "colorMap": "red-to-magenta",
    }
    assert overlay["display"] == {"visible": True, "opacity": 0.42}
    assert overlay["subjectSpecific"] is False
    assert overlay["containsIndividualVesselPaths"] is False
    assert overlay["supportsVesselClearance"] is False
    assert "not individual vessel paths" in str(overlay["disclosure"])
    with Image.open(io.BytesIO(base64.b64decode(str(overlay["pngBase64"])))) as decoded:
        assert decoded.mode == "RGBA"
        assert decoded.size == (4, 4)
        alpha = np.asarray(decoded)[..., 3]
        assert int(alpha.max()) == round(0.42 * 255)


def test_population_state_never_claims_available_from_metadata_without_runtime() -> None:
    dispatcher, session, _ = _reference_dispatcher()
    _new_project(dispatcher)
    _call(dispatcher, "vascular.reference.prepare", downloadIfMissing=False)
    _call(dispatcher, "vascular.reference.display", visible=True, opacity=0.37)
    session._reference_density_cache = None

    state = _call(dispatcher, "state.get")
    density = state["populationDensity"]
    assert isinstance(density, dict)
    assert density["available"] is False
    assert density["visible"] is False
    assert density["opacity"] == 0.37
    assert density["status"] == "preparedCacheUnavailable"
    with pytest.raises(BridgeError) as caught:
        _call(dispatcher, "vascular.reference.overlay")
    assert caught.value.code == "REFERENCE_DENSITY_NOT_PREPARED"


def test_population_reference_compact_metadata_rebinds_only_to_verified_cache(
    tmp_path: Path,
) -> None:
    dispatcher, session, _ = _reference_dispatcher()
    _new_project(dispatcher)
    _call(dispatcher, "vascular.reference.prepare", downloadIfMissing=False)
    _call(dispatcher, "vascular.reference.display", visible=True, opacity=0.37)
    destination = tmp_path / "population-reference.mouseplan"
    _save_project(dispatcher, session, path=destination)

    reopened_dispatcher, _, _ = _reference_dispatcher()
    _call(reopened_dispatcher, "project.open", path=str(destination))

    state = _call(reopened_dispatcher, "state.get")
    density = state["populationDensity"]
    project = state["project"]
    assert isinstance(density, dict)
    assert isinstance(project, dict)
    assert density["available"] is True
    assert density["visible"] is True
    assert density["opacity"] == 0.37
    assert density["status"] == "preparedReferenceDensity"
    assert project["isDirty"] is False
    overlay = _call(reopened_dispatcher, "vascular.reference.overlay")
    assert overlay["window"]["opacity"] == 0.37  # type: ignore[index]
    assert overlay["display"] == {"visible": True, "opacity": 0.37}


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"visible": 1, "opacity": 0.65}, "visible"),
        ({"visible": True, "opacity": True}, "opacity"),
        ({"visible": True, "opacity": float("nan")}, "opacity"),
        ({"visible": True, "opacity": 0.0}, "opacity"),
        ({"visible": True, "opacity": -0.01}, "opacity"),
        ({"visible": True, "opacity": 1.01}, "opacity"),
    ],
)
def test_population_reference_display_rejects_ambiguous_or_invalid_values(
    params: dict[str, object],
    field: str,
) -> None:
    dispatcher, _, _ = _reference_dispatcher()
    _new_project(dispatcher)
    _call(dispatcher, "vascular.reference.prepare", downloadIfMissing=False)

    with pytest.raises(BridgeError) as caught:
        _call(dispatcher, "vascular.reference.display", **params)

    assert caught.value.code == "INVALID_PARAMS"
    assert caught.value.details == {"field": field}


def test_population_reference_display_schema_and_hidden_overlay_fail_closed() -> None:
    dispatcher, _, _ = _reference_dispatcher()
    _new_project(dispatcher)
    _call(dispatcher, "vascular.reference.prepare", downloadIfMissing=False)

    with pytest.raises(BridgeError) as missing:
        dispatcher.dispatch(
            "vascular.reference.display",
            {"protocolVersion": 1, "visible": True},
        )
    assert missing.value.code == "INVALID_PARAMS"
    assert missing.value.details == {"missing": ["opacity"], "unexpected": []}

    with pytest.raises(BridgeError) as unexpected:
        _call(
            dispatcher,
            "vascular.reference.display",
            visible=True,
            opacity=0.65,
            unexpected=True,
        )
    assert unexpected.value.code == "INVALID_PARAMS"

    with pytest.raises(BridgeError) as hidden:
        _call(dispatcher, "vascular.reference.overlay")
    assert hidden.value.code == "REFERENCE_DENSITY_NOT_VISIBLE"
