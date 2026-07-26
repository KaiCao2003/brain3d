"""Real-cache planning QA from Allen 25 um slices through persisted NP2 analysis.

The atlas arrays, labels, rendering, and region traversal in this module are
real cached ``allen_mouse_25um`` v1.2 data.  The calibration measurements are
deterministic software-QA inputs, not measurements from an operated animal and
not evidence of surgical validation.
"""

from __future__ import annotations

import base64
import struct
from pathlib import Path

import pytest

from mouse_brain_planner.atlas.brainglobe_adapter import BrainGlobeAtlasRepository
from mouse_brain_planner.bridge.atlas_interaction import register_atlas_interaction_handlers
from mouse_brain_planner.bridge.planning import (
    PlanningBridgeSession,
    register_planning_handlers,
)
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher
from mouse_brain_planner.probes.catalog import (
    NEUROPIXELS_2_0_MODEL_VERSION,
    NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
)

ATLAS_IDENTIFIER = "allen_mouse_25um"
ATLAS_VERSION = "1.2"
ATLAS_METADATA_SHA256 = "119132150055826484fa75a4dc17c476d02251c0db8b4d0b7b28f6b8c4b8ae60"
SUBJECT_ID = "software-qa-animal-25um-001"


def _call(dispatcher: BridgeDispatcher, method: str, **params: object) -> dict[str, object]:
    return dispatcher.dispatch(method, {"protocolVersion": 1, **params})


@pytest.fixture(scope="module")
def cached_repository() -> BrainGlobeAtlasRepository:
    repository = BrainGlobeAtlasRepository()
    if not repository.is_cached(ATLAS_IDENTIFIER, ATLAS_VERSION):
        pytest.skip("allen_mouse_25um v1.2 is not cached; real-data workflow was not substituted")
    return repository


def _open_real_atlas(
    repository: BrainGlobeAtlasRepository,
) -> tuple[BridgeDispatcher, PlanningBridgeSession, dict[str, object]]:
    dispatcher = BridgeDispatcher(BridgeContext(repository_factory=lambda: repository))
    register_atlas_interaction_handlers(dispatcher)
    session = register_planning_handlers(dispatcher)
    opened = _call(
        dispatcher,
        "atlas.open",
        identifier=ATLAS_IDENTIFIER,
        version=ATLAS_VERSION,
        allowDownload=False,
    )
    return dispatcher, session, opened


def _source_point(ap_um: float, ml_um: float, dv_um: float) -> dict[str, object]:
    return {
        "frameId": "SOFTWARE_QA_RIG_AP_ML_DV_UM",
        "componentOrder": ["AP", "ML", "DV"],
        "units": "micrometre",
        "apMicrometres": ap_um,
        "mlMicrometres": ml_um,
        "dvMicrometres": dv_um,
    }


def _atlas_point(ap_um: float, dv_um: float, ml_um: float) -> dict[str, object]:
    return {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "atlasIdentifier": ATLAS_IDENTIFIER,
        "atlasVersion": ATLAS_VERSION,
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": ap_um,
        "dvMicrometres": dv_um,
        "mlMicrometres": ml_um,
    }


def _calibration_params(project_id: str, revision: int) -> dict[str, object]:
    """Return exact, internally consistent software-QA correspondences.

    These values exercise fitting and persistence against the real atlas. They
    deliberately do not claim to be measured bregma coordinates for an animal.
    """

    return {
        "projectId": project_id,
        "expectedProjectRevision": revision,
        "profileId": "software-qa-calibration-25um-v1",
        "sourceFrame": {
            "frameId": "SOFTWARE_QA_RIG_AP_ML_DV_UM",
            "kind": "skull",
            "originDescription": "Deterministic software-QA origin; not an animal measurement",
            "apPositiveDirection": "fixture AP positive",
            "mlPositiveDirection": "fixture ML positive",
            "dvPositiveDirection": "fixture DV positive",
            "componentOrder": ["AP", "ML", "DV"],
            "units": "micrometre",
        },
        "skullLandmarks": {
            "bregma": _source_point(0.0, 0.0, 0.0),
            "lambdaPoint": _source_point(-2_000.0, 0.0, 0.0),
            "leftSkull": _source_point(0.0, -1_000.0, 0.0),
            "rightSkull": _source_point(0.0, 1_000.0, 0.0),
            "reportedBregmaLambdaDistanceMicrometres": 2_000.0,
            "lateralityConfirmedFromAnimal": True,
        },
        "atlasLandmarks": {
            # This is an engineering fixture, not an official Allen bregma.
            # Keep its bregma/lambda axis on the reviewed 5.7 mm atlas
            # midline so negative ML is visibly animal-left (screen-right) and the
            # fixture cannot conceal a laterality regression.
            "bregma": _atlas_point(3_000.0, 2_000.0, 5_700.0),
            "lambdaPoint": _atlas_point(5_000.0, 2_000.0, 5_700.0),
            "leftSkull": _atlas_point(3_000.0, 2_000.0, 6_700.0),
            "rightSkull": _atlas_point(3_000.0, 2_000.0, 4_700.0),
        },
        "qualityLimits": {
            "minimumAxisBaselineMicrometres": 500.0,
            "distanceWarningMicrometres": 25.0,
            "distanceFailureMicrometres": 100.0,
            "lateralApWarningMicrometres": 25.0,
            "lateralApFailureMicrometres": 100.0,
            "transformRmsWarningMicrometres": 25.0,
            "transformRmsFailureMicrometres": 100.0,
        },
        "dvReference": "bregma",
        "dvReferenceDescription": "Software-QA bregma DV zero; not an animal measurement",
        "limitsSource": "Software integration-test thresholds; not a surgical SOP",
        "atlasTransformMethod": "rigid",
        "affineDistortionAcknowledged": False,
        "notes": "Engineering QA fixture",
    }


def _assert_lossless_real_slice(
    response: dict[str, object],
    *,
    orientation: str,
    index: int,
    dimensions: tuple[int, int],
) -> None:
    rendered = response["renderedSlice"]
    assert isinstance(rendered, dict)
    assert rendered["orientation"] == orientation
    assert rendered["index"] == index
    assert rendered["mimeType"] == "image/png"
    assert (rendered["width"], rendered["height"]) == dimensions
    png = base64.b64decode(str(rendered["pngBase64"]), validate=True)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", png[16:24]) == dimensions


@pytest.mark.integration
def test_real_cached_25um_calibrated_neuropixels_workflow_round_trip(
    cached_repository: BrainGlobeAtlasRepository,
    tmp_path: Path,
) -> None:
    dispatcher, session, opened = _open_real_atlas(cached_repository)
    atlas = opened["atlas"]
    assert isinstance(atlas, dict)
    assert atlas["identifier"] == ATLAS_IDENTIFIER
    assert atlas["version"] == ATLAS_VERSION
    assert atlas["metadataSha256"] == ATLAS_METADATA_SHA256
    assert atlas["resolutionMicrometres"] == [25.0, 25.0, 25.0]
    assert atlas["shapeVoxels"] == [528, 320, 456]

    created = _call(
        dispatcher,
        "project.new",
        animalResearchOnlyAcknowledged=True,
        title="Real Allen 25 um software-QA workflow",
        subjectId=SUBJECT_ID,
    )
    project_id = created["projectId"]
    assert isinstance(project_id, str)
    assert created["animalOnly"] is True
    assert created["subjectId"] == SUBJECT_ID

    viewer = _call(dispatcher, "viewer.state.get")
    assert viewer["projectRevision"] == 1
    expected_depths = {"coronal": 120, "sagittal": 180, "horizontal": 80}
    expected_dimensions = {
        "coronal": (456, 320),
        "sagittal": (528, 320),
        "horizontal": (456, 528),
    }
    revision = 1
    configured_orientations: list[str] = []
    for orientation in ("coronal", "sagittal", "horizontal"):
        rendered = _call(
            dispatcher,
            "viewer.slice.render",
            projectId=project_id,
            expectedProjectRevision=revision,
            orientation=orientation,
            index=expected_depths[orientation],
        )
        revision += 1
        assert rendered["projectRevision"] == revision
        _assert_lossless_real_slice(
            rendered,
            orientation=orientation,
            index=expected_depths[orientation],
            dimensions=expected_dimensions[orientation],
        )
        slices = rendered["slices"]
        assert isinstance(slices, dict)
        configured_orientations.append(orientation)
        for configured_orientation in configured_orientations:
            retained_slice = slices[configured_orientation]
            assert isinstance(retained_slice, dict)
            assert retained_slice["index"] == expected_depths[configured_orientation]

    selected = _call(
        dispatcher,
        "viewer.region.pick",
        projectId=project_id,
        expectedProjectRevision=revision,
        orientation="coronal",
        index=120,
        column=180,
        row=80,
    )
    revision += 1
    assert selected["projectRevision"] == revision
    slices = selected["slices"]
    assert isinstance(slices, dict)
    assert {name: item["index"] for name, item in slices.items()} == expected_depths
    selection = selected["selection"]
    assert isinstance(selection, dict)
    assert selection["containingVoxelIndex"] == {
        "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
        "ap": 120,
        "dv": 80,
        "ml": 180,
    }
    region = selection["region"]
    assert isinstance(region, dict)
    assert region["structureId"] == 767
    assert region["acronym"] == "MOs5"
    assert region["name"] == "Secondary motor area, layer 5"

    calibration_created = _call(
        dispatcher,
        "calibration.create",
        **_calibration_params(project_id, revision),
    )
    revision += 1
    assert calibration_created["projectRevision"] == revision
    calibration = calibration_created["calibration"]
    assert isinstance(calibration, dict)
    assert calibration["quality"] == "pass"
    assert calibration["permitsPlanning"] is True
    assert calibration["atlasMetadataSha256"] == ATLAS_METADATA_SHA256
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)

    activated = _call(
        dispatcher,
        "calibration.setActive",
        projectId=project_id,
        expectedProjectRevision=revision,
        calibrationId=calibration_id,
    )
    revision += 1
    assert activated["projectRevision"] == revision

    added = _call(
        dispatcher,
        "implant.add",
        projectId=project_id,
        expectedProjectRevision=revision,
        label="QA target: negative AP / ML / DV",
        apMillimetres=-1.0,
        mlMillimetres=-0.5,
        dvMillimetres=-1.5,
    )
    revision += 1
    assert added["projectRevision"] == revision
    target = added["target"]
    assert isinstance(target, dict)
    assert target["apMillimetres"] == -1.0
    assert target["mlMillimetres"] == -0.5
    assert target["dvMillimetres"] == -1.5
    assert target["apNegativeDirection"] == "posterior/back"
    assert target["mlNegativeDirection"] == "left"
    assert target["dvNegativeDirection"] == "deep/ventral"
    assert target["projected"] is False
    target_id = target["targetId"]
    assert isinstance(target_id, str)

    projected = _call(
        dispatcher,
        "calibration.projectTarget",
        projectId=project_id,
        targetId=target_id,
    )
    projected_point = projected["atlasPoint"]
    assert isinstance(projected_point, dict)
    assert projected_point["apMicrometres"] == pytest.approx(4_000.0)
    assert projected_point["dvMicrometres"] == pytest.approx(3_500.0)
    assert projected_point["mlMicrometres"] == pytest.approx(6_200.0)
    assert projected_point["apMicrometres"] > 3_000.0
    assert projected_point["mlMicrometres"] > 5_700.0
    assert projected["usableForNavigation"] is False
    assert session.project_revision == revision

    catalog = _call(
        dispatcher,
        "probe.catalog.get",
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
    )
    model = catalog["model"]
    assert isinstance(model, dict)
    assert model["siteCount"] == 1280
    assert model["verificationStatus"] == "source-transcribed-review-pending"
    assert model["independentTranscriptionReviewCompleted"] is False

    plan_created = _call(
        dispatcher,
        "probe.plan.create",
        projectId=project_id,
        expectedProjectRevision=revision,
        targetId=target_id,
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name="Real-atlas NP2 software-QA placement",
        placementMode="STEREOTAXIC_TARGET_MANIPULATOR",
        azimuthDegrees=0.0,
        elevationDegrees=-90.0,
        insertionDepthMicrometres=3_000.0,
        axialRotationDegrees=0.0,
        customGeometryAcknowledged=True,
    )
    revision += 1
    assert plan_created["projectRevision"] == revision
    plan = plan_created["plan"]
    assert isinstance(plan, dict)
    assert plan["placementMode"] == "STEREOTAXIC_TARGET_MANIPULATOR"
    assert plan["usableForNavigation"] is False
    assert len(plan["recordingSites"]) == 1280
    plan_id = plan["planId"]
    plan_sha256 = plan["inputSha256"]
    assert isinstance(plan_id, str)
    assert isinstance(plan_sha256, str)

    analyzed = _call(
        dispatcher,
        "probe.region.analyze",
        projectId=project_id,
        expectedProjectRevision=revision,
        planId=plan_id,
        expectedPlanInputSha256=plan_sha256,
    )
    revision += 1
    assert analyzed["projectRevision"] == revision
    analysis = analyzed["regionAnalysis"]
    assert isinstance(analysis, dict)
    assert analysis["planInputSha256"] == plan_sha256
    shanks = analysis["shanks"]
    assert isinstance(shanks, list)
    assert len(shanks) == 1
    shank = shanks[0]
    assert isinstance(shank, dict)
    segments = shank["segments"]
    assignments = shank["recordingSiteAssignments"]
    assert isinstance(segments, list)
    assert isinstance(assignments, list)
    assert segments
    assert len(assignments) == 1280
    assert any(int(segment["structureId"]) > 0 for segment in segments)
    provenance = shank["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["atlasMetadataSha256"] == ATLAS_METADATA_SHA256
    assert provenance["annotationVersion"] == "annotation/ccf_2017"

    destination = tmp_path / "real-25um-neuropixels.mouseplan"
    saved = _call(
        dispatcher,
        "project.save",
        projectId=project_id,
        expectedProjectRevision=revision,
        path=str(destination),
    )
    revision += 1
    assert saved["projectRevision"] == revision
    assert destination.is_dir()
    assert (destination / "project.json").is_file()

    reopened_dispatcher, reopened_session, reopened_atlas = _open_real_atlas(cached_repository)
    assert reopened_atlas["atlas"] == opened["atlas"]
    reopened = _call(reopened_dispatcher, "project.open", path=str(destination))
    assert reopened["projectId"] == project_id
    assert reopened_session.project_revision == revision
    restored_project = reopened_session.project
    assert restored_project is not None
    assert restored_project.subject_id == SUBJECT_ID
    assert restored_project.atlas is not None
    assert restored_project.atlas.metadata_sha256 == ATLAS_METADATA_SHA256
    assert restored_project.viewer_slice_depths is not None
    assert restored_project.viewer_slice_depths.model_dump() == expected_depths
    assert restored_project.viewer_region_selection is not None
    assert restored_project.viewer_region_selection.atlas_point.ap_um == pytest.approx(3_012.5)
    assert restored_project.active_calibration_uuid is not None
    assert len(restored_project.calibrations) == 1
    assert len(restored_project.unprojected_bregma_targets) == 1
    assert len(restored_project.probe_plans) == 1
    assert len(restored_project.probe_region_analyses) == 1
    restored = _call(
        reopened_dispatcher,
        "probe.plan.get",
        projectId=project_id,
        planId=plan_id,
    )
    assert restored["projectRevision"] == revision
    restored_plan = restored["plan"]
    restored_analysis = restored["regionAnalysis"]
    assert isinstance(restored_plan, dict)
    assert isinstance(restored_analysis, dict)
    assert restored_plan["inputSha256"] == plan_sha256
    assert restored_analysis["analysisSha256"] == analysis["analysisSha256"]


@pytest.mark.integration
def test_real_cached_25um_major_vessel_clearance_remains_display_only() -> None:
    pytest.skip(
        "the VesSAP reference overlay has a reviewed atlas transform but no subject-registration "
        "or tissue-distortion error bounds; clearance analysis is intentionally unavailable"
    )
