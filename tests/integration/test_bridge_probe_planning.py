"""Supported bridge path from calibrated AP/ML/DV target through region export."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from tests.integration.test_bridge_calibration import (
    _call,
    _create,
    _create_params,
    _FakeAtlas,
    _metadata,
    _set_active,
)

from mouse_brain_planner.bridge.planning import (
    PlanningBridgeSession,
    register_planning_handlers,
)
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher, BridgeError
from mouse_brain_planner.probes.catalog import (
    GENERIC_TEST_MODEL_ID,
    GENERIC_TEST_MODEL_VERSION,
    NEUROPIXELS_1_0_MANUFACTURER_SPEC_SHA256,
    NEUROPIXELS_1_0_MODEL_ID,
    NEUROPIXELS_1_0_MODEL_VERSION,
)


def _probe_dispatcher() -> tuple[BridgeDispatcher, PlanningBridgeSession]:
    metadata = _metadata().model_copy(update={"source_annotation": "synthetic-labels-v1"})
    annotation = np.ones(metadata.shape_voxels, dtype=np.int32)
    annotation[:, 4:, :] = 0
    atlas = _FakeAtlas(
        metadata=metadata,
        reference=np.arange(512, dtype=np.uint16).reshape(metadata.shape_voxels),
        annotation=annotation,
    )
    context = BridgeContext(repository_factory=lambda: pytest.fail("repository not expected"))
    context.set_loaded_atlas(atlas)
    dispatcher = BridgeDispatcher(context)
    session = register_planning_handlers(dispatcher)
    _call(
        dispatcher,
        "project.new",
        animalResearchOnlyAcknowledged=True,
        title="Probe test",
        subjectId="mouse-A",
    )
    return dispatcher, session


def _calibrated_target(
    dispatcher: BridgeDispatcher,
    session: PlanningBridgeSession,
) -> str:
    created = _create(dispatcher, session)
    calibration = created["calibration"]
    assert isinstance(calibration, dict)
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)
    _set_active(dispatcher, session, calibration_id)
    added = _call(
        dispatcher,
        "implant.add",
        label="deep target",
        apMillimetres=-0.001,
        mlMillimetres=-0.001,
        dvMillimetres=-0.001,
    )
    target = added["target"]
    assert isinstance(target, dict)
    target_id = target["targetId"]
    assert isinstance(target_id, str)
    return target_id


def _create_plan(
    dispatcher: BridgeDispatcher,
    session: PlanningBridgeSession,
    target_id: str,
) -> dict[str, object]:
    assert session.project is not None
    return _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target_id,
        modelId=GENERIC_TEST_MODEL_ID,
        modelVersion=GENERIC_TEST_MODEL_VERSION,
        name="Vertical generic test",
        azimuthDegrees=0,
        elevationDegrees=-90,
        insertionDepthMicrometres=4,
        axialRotationDegrees=0,
        customGeometryAcknowledged=True,
    )


def test_probe_plan_region_analysis_export_update_and_persistence(tmp_path: Path) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)

    catalog = _call(dispatcher, "probe.catalog.list")
    assert catalog["modelCount"] == 2
    catalog_models = catalog["models"]
    assert isinstance(catalog_models, list)
    assert catalog_models[0]["modelId"] == NEUROPIXELS_1_0_MODEL_ID
    assert catalog_models[0]["verificationStatus"] == "source-transcribed-review-pending"
    assert "review pending" in catalog_models[0]["warning"]

    neuropixels = _call(
        dispatcher,
        "probe.catalog.get",
        modelId=NEUROPIXELS_1_0_MODEL_ID,
        modelVersion=NEUROPIXELS_1_0_MODEL_VERSION,
    )["model"]
    assert isinstance(neuropixels, dict)
    assert neuropixels["siteCount"] == 960
    assert neuropixels["completeGeometryTranscribed"] is True
    assert neuropixels["independentTranscriptionReviewCompleted"] is False
    assert neuropixels["independentlyReviewedBy"] is None
    sources = neuropixels["primarySources"]
    assert isinstance(sources, list)
    assert len(sources) == 4
    assert sources[0]["sha256"] == NEUROPIXELS_1_0_MANUFACTURER_SPEC_SHA256
    shanks = neuropixels["shanks"]
    assert isinstance(shanks, list)
    assert shanks[0]["tipGeometry"] == "chisel"
    assert shanks[0]["tipLengthMicrometres"] == 175
    assert len(shanks[0]["sites"]) == 960

    model = _call(
        dispatcher,
        "probe.catalog.get",
        modelId=GENERIC_TEST_MODEL_ID,
        modelVersion=GENERIC_TEST_MODEL_VERSION,
    )["model"]
    assert isinstance(model, dict)
    assert model["verificationStatus"] == "user-defined-unverified"
    assert model["verifiedDeviceLabelPermitted"] is False

    created = _create_plan(dispatcher, session, target_id)
    plan = created["plan"]
    assert isinstance(plan, dict)
    plan_id = plan["planId"]
    plan_sha = plan["inputSha256"]
    assert isinstance(plan_id, str)
    assert isinstance(plan_sha, str)
    assert plan["usableForNavigation"] is False
    placement = plan["placement"]
    assert isinstance(placement, dict)
    assert placement["method"] == "stereotaxic-target-plus-manipulator-angles"
    manipulator = plan["manipulatorInput"]
    assert isinstance(manipulator, dict)
    assert manipulator["azimuthDegrees"] == 0
    assert manipulator["elevationDegrees"] == -90
    assert manipulator["insertionDepthMicrometres"] == 4
    provenance = plan["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["planningAlgorithmVersion"] == "calibrated-stereotaxic-probe-transform-v2"
    atlas_frame = placement["atlasFrame"]
    assert isinstance(atlas_frame, dict)
    target = atlas_frame["target"]
    entry = atlas_frame["entry"]
    assert isinstance(target, dict)
    assert isinstance(entry, dict)
    assert target["apMicrometres"] == pytest.approx(4.5)
    assert target["mlMicrometres"] == pytest.approx(4.5)
    assert target["dvMicrometres"] == pytest.approx(4.5)
    assert entry["dvMicrometres"] == pytest.approx(0.5)
    assert len(plan["recordingSites"]) == 16  # type: ignore[arg-type]

    assert session.project is not None
    analyzed = _call(
        dispatcher,
        "probe.region.analyze",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan_id,
        expectedPlanInputSha256=plan_sha,
    )
    analysis = analyzed["regionAnalysis"]
    assert isinstance(analysis, dict)
    assert analysis["planInputSha256"] == plan_sha
    shanks = analysis["shanks"]
    assert isinstance(shanks, list)
    assert len(shanks) == 1
    shank = shanks[0]
    assert isinstance(shank, dict)
    segments = shank["segments"]
    assert isinstance(segments, list)
    assert [segment["structureId"] for segment in segments] == [1, 0]  # type: ignore[index]
    assert sum(segment["lengthMicrometres"] for segment in segments) == pytest.approx(4)  # type: ignore[index,operator]
    assignments = shank["recordingSiteAssignments"]
    assert isinstance(assignments, list)
    assert len(assignments) == 16

    revision_before_export = session.project_revision
    assert session.project is not None
    csv_export = _call(
        dispatcher,
        "probe.region.export",
        projectId=str(session.project.project_uuid),
        planId=plan_id,
        expectedPlanInputSha256=plan_sha,
        format="csv",
    )
    assert csv_export["projectMutated"] is False
    assert "region_segment" in str(csv_export["content"])
    assert "recording_site" in str(csv_export["content"])
    assert session.project_revision == revision_before_export

    destination = tmp_path / "probe.mouseplan"
    _call(dispatcher, "project.save", path=str(destination))
    reopened_dispatcher, reopened_session = _probe_dispatcher()
    _call(reopened_dispatcher, "project.open", path=str(destination))
    assert reopened_session.project is not None
    assert len(reopened_session.project.probe_plans) == 1
    assert len(reopened_session.project.probe_region_analyses) == 1
    reopened = _call(
        reopened_dispatcher,
        "probe.plan.get",
        projectId=str(reopened_session.project.project_uuid),
        planId=plan_id,
    )
    assert reopened["regionAnalysis"] is not None

    updated = _call(
        reopened_dispatcher,
        "probe.plan.update",
        projectId=str(reopened_session.project.project_uuid),
        expectedProjectRevision=reopened_session.project_revision,
        planId=plan_id,
        expectedPlanInputSha256=plan_sha,
        targetId=target_id,
        modelId=GENERIC_TEST_MODEL_ID,
        modelVersion=GENERIC_TEST_MODEL_VERSION,
        name="Adjusted vertical generic test",
        azimuthDegrees=0,
        elevationDegrees=-90,
        insertionDepthMicrometres=3,
        axialRotationDegrees=15,
        customGeometryAcknowledged=True,
    )
    updated_plan = updated["plan"]
    assert isinstance(updated_plan, dict)
    assert updated_plan["planVersion"] == 2
    assert updated_plan["inputSha256"] != plan_sha
    assert updated["priorAnalysisCleared"] is True
    assert reopened_session.project is not None
    assert reopened_session.project.probe_region_analyses == []


def test_rotated_calibration_transforms_manipulator_direction_into_atlas_frame() -> None:
    dispatcher, session = _probe_dispatcher()
    params = _create_params(session)
    atlas_landmarks = params["atlasLandmarks"]
    assert isinstance(atlas_landmarks, dict)
    # Proper +30 degree rotation about stereotaxic +DV, expressed through
    # BrainGlobe physical ASR landmark coordinates.
    atlas_landmarks["lambdaPoint"] = {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "atlasIdentifier": "allen_mouse_25um",
        "atlasVersion": "1.2",
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": 5.232050807568877,
        "dvMicrometres": 3.5,
        "mlMicrometres": 4.5,
    }
    atlas_landmarks["leftSkull"] = {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "atlasIdentifier": "allen_mouse_25um",
        "atlasVersion": "1.2",
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": 2.5,
        "dvMicrometres": 3.5,
        "mlMicrometres": 5.232050807568877,
    }
    atlas_landmarks["rightSkull"] = {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "atlasIdentifier": "allen_mouse_25um",
        "atlasVersion": "1.2",
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": 4.5,
        "dvMicrometres": 3.5,
        "mlMicrometres": 1.7679491924311228,
    }
    created_calibration = _call(dispatcher, "calibration.create", **params)
    calibration = created_calibration["calibration"]
    assert isinstance(calibration, dict)
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)
    _set_active(dispatcher, session, calibration_id)
    added = _call(
        dispatcher,
        "implant.add",
        label="rotated target",
        apMillimetres=0,
        mlMillimetres=0,
        dvMillimetres=-0.001,
    )
    target = added["target"]
    assert isinstance(target, dict)
    assert session.project is not None
    response = _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target["targetId"],
        modelId=GENERIC_TEST_MODEL_ID,
        modelVersion=GENERIC_TEST_MODEL_VERSION,
        name="rotated probe",
        azimuthDegrees=0,
        elevationDegrees=0,
        insertionDepthMicrometres=1,
        axialRotationDegrees=30,
        customGeometryAcknowledged=True,
    )
    plan = response["plan"]
    assert isinstance(plan, dict)
    manipulator = plan["manipulatorInput"]
    placement = plan["placement"]
    assert isinstance(manipulator, dict)
    assert isinstance(placement, dict)
    assert manipulator["azimuthDegrees"] == 0
    assert manipulator["elevationDegrees"] == 0
    assert placement["method"] == "stereotaxic-target-plus-manipulator-angles"
    assert placement["azimuthDegrees"] == pytest.approx(30)
    assert placement["elevationDegrees"] == pytest.approx(0)
    canonical = placement["canonicalFrame"]
    assert isinstance(canonical, dict)
    entry = canonical["entry"]
    tip = canonical["tip"]
    assert isinstance(entry, dict)
    assert isinstance(tip, dict)
    assert float(tip["apMicrometres"]) - float(entry["apMicrometres"]) == pytest.approx(
        0.8660254037844386
    )
    assert float(tip["mlMicrometres"]) - float(entry["mlMicrometres"]) == pytest.approx(0.5)
    assert float(tip["dvMicrometres"]) - float(entry["dvMicrometres"]) == pytest.approx(0)


def test_region_analysis_rehashes_exact_annotation_content_after_mutation() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    created = _create_plan(dispatcher, session, target_id)
    plan = created["plan"]
    assert isinstance(plan, dict)
    assert session.project is not None

    first = _call(
        dispatcher,
        "probe.region.analyze",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan["planId"],
        expectedPlanInputSha256=plan["inputSha256"],
    )
    first_bundle = first["regionAnalysis"]
    assert isinstance(first_bundle, dict)
    first_shanks = first_bundle["shanks"]
    assert isinstance(first_shanks, list)
    first_provenance = first_shanks[0]["provenance"]
    assert isinstance(first_provenance, dict)

    atlas = dispatcher.context.loaded_atlas
    assert isinstance(atlas, _FakeAtlas)
    atlas.annotation[:] = 0
    second = _call(
        dispatcher,
        "probe.region.analyze",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan["planId"],
        expectedPlanInputSha256=plan["inputSha256"],
    )
    second_bundle = second["regionAnalysis"]
    assert isinstance(second_bundle, dict)
    second_shanks = second_bundle["shanks"]
    assert isinstance(second_shanks, list)
    second_provenance = second_shanks[0]["provenance"]
    assert isinstance(second_provenance, dict)
    assert second_provenance["annotationSha256"] != first_provenance["annotationSha256"]
    assert second_provenance["inputDigest"] != first_provenance["inputDigest"]


def test_probe_planning_fails_closed_without_acknowledgment_and_on_stale_hash() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    assert session.project is not None
    params = {
        "projectId": str(session.project.project_uuid),
        "expectedProjectRevision": session.project_revision,
        "targetId": target_id,
        "modelId": NEUROPIXELS_1_0_MODEL_ID,
        "modelVersion": NEUROPIXELS_1_0_MODEL_VERSION,
        "name": "Unacknowledged",
        "azimuthDegrees": 0,
        "elevationDegrees": -90,
        "insertionDepthMicrometres": 4,
        "axialRotationDegrees": 0,
        "customGeometryAcknowledged": False,
    }
    with pytest.raises(BridgeError) as unacknowledged:
        _call(dispatcher, "probe.plan.create", **params)
    assert unacknowledged.value.code == "PLACEMENT_INVALID"
    assert session.project_revision == 4

    created = _create_plan(dispatcher, session, target_id)
    plan = created["plan"]
    assert isinstance(plan, dict)
    with pytest.raises(BridgeError) as stale:
        _call(
            dispatcher,
            "probe.region.analyze",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=session.project_revision,
            planId=plan["planId"],
            expectedPlanInputSha256="0" * 64,
        )
    assert stale.value.code == "ANALYSIS_STALE"
    assert session.project_revision == 5
