"""Supported bridge path from calibrated AP/ML/DV target through region export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4

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
from mouse_brain_planner.coordinates.transforms import (
    fit_anatomical_transform,
    transform_point,
)
from mouse_brain_planner.domain.probe_models import NormalizedProbePlacement
from mouse_brain_planner.domain.probe_plan_models import (
    LEGACY_PROBE_PLANNING_ALGORITHM_VERSION,
    STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION,
    ProbePlacementMode,
    ProbePlanRecord,
    probe_plan_input_digest,
)
from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.domain.stereotaxy_models import AtlasRegisteredCalibration
from mouse_brain_planner.domain.transform_models import (
    AnatomicalPoint,
    AnatomicalTransform,
    LandmarkCorrespondence3D,
    TransformMethod,
)
from mouse_brain_planner.persistence.project_io import (
    CHECKSUMS_FILENAME,
    PROJECT_FILENAME,
    load_project,
    save_project,
)
from mouse_brain_planner.probes.catalog import (
    GENERIC_TEST_MODEL_ID,
    GENERIC_TEST_MODEL_VERSION,
    NEUROPIXELS_1_0_MODEL_ID,
    NEUROPIXELS_1_0_MODEL_VERSION,
    NEUROPIXELS_2_0_MODEL_VERSION,
    NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID,
    NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
    NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
)
from mouse_brain_planner.surgery.probe_planning import build_calibrated_probe_plan
from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION


@pytest.mark.parametrize(
    ("model_id", "model_version"),
    (
        (
            NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID,
            NEUROPIXELS_2_0_MODEL_VERSION,
        ),
        (NEUROPIXELS_1_0_MODEL_ID, NEUROPIXELS_1_0_MODEL_VERSION),
        (GENERIC_TEST_MODEL_ID, GENERIC_TEST_MODEL_VERSION),
    ),
)
def test_product_probe_endpoints_reject_archived_models(
    model_id: str,
    model_version: str,
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    assert session.project is not None

    with pytest.raises(BridgeError) as catalog_rejection:
        _call(
            dispatcher,
            "probe.catalog.get",
            modelId=model_id,
            modelVersion=model_version,
        )
    assert catalog_rejection.value.code == "PROBE_MODEL_NOT_FOUND"

    revision_before_create = session.project_revision
    with pytest.raises(BridgeError) as create_rejection:
        _call(
            dispatcher,
            "probe.plan.create",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before_create,
            targetId=target_id,
            modelId=model_id,
            modelVersion=model_version,
            name="Archived model must not be product-creatable",
            azimuthDegrees=0,
            elevationDegrees=-90,
            insertionDepthMicrometres=4,
            axialRotationDegrees=0,
            customGeometryAcknowledged=True,
        )
    assert create_rejection.value.code == "PROBE_MODEL_NOT_FOUND"
    assert session.project_revision == revision_before_create
    assert session.project.probe_plans == []

    created = _create_plan(dispatcher, session, target_id)
    plan = created["plan"]
    assert isinstance(plan, dict)
    revision_before_update = session.project_revision
    with pytest.raises(BridgeError) as update_rejection:
        _call(
            dispatcher,
            "probe.plan.update",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before_update,
            planId=plan["planId"],
            expectedPlanInputSha256=plan["inputSha256"],
            targetId=target_id,
            modelId=model_id,
            modelVersion=model_version,
            name="Archived model must not be product-updatable",
            azimuthDegrees=0,
            elevationDegrees=-90,
            insertionDepthMicrometres=4,
            axialRotationDegrees=0,
            customGeometryAcknowledged=True,
        )
    assert update_rejection.value.code == "PROBE_MODEL_NOT_FOUND"
    assert session.project_revision == revision_before_update
    assert session.project.probe_plans[0].input_sha256 == plan["inputSha256"]


def _probe_dispatcher(
    *,
    subject_id: str = "mouse-A",
    title: str = "Probe test",
) -> tuple[BridgeDispatcher, PlanningBridgeSession]:
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
        title=title,
        subjectId=subject_id,
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
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
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
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name="Vertical NP2 single-shank test",
        azimuthDegrees=0,
        elevationDegrees=-90,
        insertionDepthMicrometres=4,
        axialRotationDegrees=0,
        customGeometryAcknowledged=True,
    )


def _translated_rehashed_plan(
    plan: ProbePlanRecord,
    *,
    ap_delta_um: float = 0.25,
) -> ProbePlanRecord:
    placement_payload = plan.placement.model_dump(mode="python")
    for field in ("entry", "target", "tip", "skull_entry", "brain_entry"):
        raw_point = placement_payload[field]
        if raw_point is None:
            continue
        point = dict(raw_point)
        point["ap_um"] = float(point["ap_um"]) + ap_delta_um
        placement_payload[field] = point
    translated_placement = NormalizedProbePlacement.model_validate(placement_payload)
    return _plan_with_rehashed_placement(plan, translated_placement)


def _plan_with_rehashed_placement(
    plan: ProbePlanRecord,
    placement: NormalizedProbePlacement,
) -> ProbePlanRecord:
    input_sha256 = probe_plan_input_digest(
        plan_uuid=plan.plan_uuid,
        plan_version=plan.plan_version,
        name=plan.name,
        source_target=plan.source_target,
        probe_model=plan.probe_model,
        manipulator_input=plan.manipulator_input,
        placement_input=plan.placement_input,
        placement=placement,
        calibration_uuid=plan.calibration_uuid,
        calibration_version=plan.calibration_version,
        calibration_sha256=plan.calibration_sha256,
        atlas_metadata_sha256=plan.atlas_metadata_sha256,
        projection_sha256=plan.projection_sha256,
        planning_algorithm_version=plan.planning_algorithm_version,
    )
    payload = plan.model_dump(mode="python")
    payload.update(placement=placement, input_sha256=input_sha256)
    return ProbePlanRecord.model_validate(payload)


def _wider_model_rehashed_plan(plan: ProbePlanRecord) -> ProbePlanRecord:
    shanks = list(plan.probe_model.shanks)
    shanks[0] = shanks[0].model_copy(update={"width_um": 700})
    forged_model = plan.probe_model.model_copy(update={"shanks": tuple(shanks)})
    input_sha256 = probe_plan_input_digest(
        plan_uuid=plan.plan_uuid,
        plan_version=plan.plan_version,
        name=plan.name,
        source_target=plan.source_target,
        probe_model=forged_model,
        manipulator_input=plan.manipulator_input,
        placement_input=plan.placement_input,
        placement=plan.placement,
        calibration_uuid=plan.calibration_uuid,
        calibration_version=plan.calibration_version,
        calibration_sha256=plan.calibration_sha256,
        atlas_metadata_sha256=plan.atlas_metadata_sha256,
        projection_sha256=plan.projection_sha256,
        planning_algorithm_version=plan.planning_algorithm_version,
    )
    payload = plan.model_dump(mode="python")
    payload.update(probe_model=forged_model, input_sha256=input_sha256)
    return ProbePlanRecord.model_validate(payload)


def _as_v2_plan(plan: ProbePlanRecord) -> ProbePlanRecord:
    assert plan.manipulator_input is not None
    input_sha256 = probe_plan_input_digest(
        plan_uuid=plan.plan_uuid,
        plan_version=plan.plan_version,
        name=plan.name,
        source_target=plan.source_target,
        probe_model=plan.probe_model,
        manipulator_input=plan.manipulator_input,
        placement=plan.placement,
        calibration_uuid=plan.calibration_uuid,
        calibration_version=plan.calibration_version,
        calibration_sha256=plan.calibration_sha256,
        atlas_metadata_sha256=plan.atlas_metadata_sha256,
        projection_sha256=plan.projection_sha256,
        planning_algorithm_version=STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION,
    )
    payload = plan.model_dump(mode="python")
    payload.update(
        placement_input=None,
        planning_algorithm_version=STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION,
        input_sha256=input_sha256,
    )
    return ProbePlanRecord.model_validate(payload)


def _as_v1_plan(plan: ProbePlanRecord) -> ProbePlanRecord:
    assert plan.placement.method.value == "target-plus-angles-depth"
    placement_payload = plan.placement.model_dump(mode="python")
    placement_payload.pop("local_lateral_direction")
    placement_payload.pop("local_normal_direction")
    placement_payload.pop("model_to_placement_uniform_scale")
    legacy_placement = NormalizedProbePlacement.model_validate(placement_payload)
    input_sha256 = probe_plan_input_digest(
        plan_uuid=plan.plan_uuid,
        plan_version=plan.plan_version,
        name=plan.name,
        source_target=plan.source_target,
        probe_model=plan.probe_model,
        placement=legacy_placement,
        calibration_uuid=plan.calibration_uuid,
        calibration_version=plan.calibration_version,
        calibration_sha256=plan.calibration_sha256,
        atlas_metadata_sha256=plan.atlas_metadata_sha256,
        projection_sha256=plan.projection_sha256,
        planning_algorithm_version=LEGACY_PROBE_PLANNING_ALGORITHM_VERSION,
    )
    payload = plan.model_dump(mode="python")
    payload.update(
        placement=legacy_placement,
        placement_input=None,
        manipulator_input=None,
        planning_algorithm_version=LEGACY_PROBE_PLANNING_ALGORITHM_VERSION,
        input_sha256=input_sha256,
    )
    return ProbePlanRecord.model_validate(payload)


def _same_target_alternate_trajectory_rehashed_plan(
    project: PlannerProject,
    plan: ProbePlanRecord,
) -> ProbePlanRecord:
    assert project.atlas is not None
    target = next(
        item
        for item in project.unprojected_bregma_targets
        if item.target_uuid == plan.source_target.target_uuid
    )
    calibration = next(
        item for item in project.calibrations if item.calibration_uuid == plan.calibration_uuid
    )
    alternate, _ = build_calibrated_probe_plan(
        target=target,
        calibration=calibration,
        atlas=project.atlas,
        model=plan.probe_model,
        name=plan.name,
        azimuth_deg=45,
        elevation_deg=-70,
        insertion_depth_um=4,
        axial_rotation_deg=plan.placement.axial_rotation_deg,
        custom_geometry_acknowledged=plan.placement.custom_geometry_acknowledged,
        placement_mode=ProbePlacementMode.STEREOTAXIC_TARGET_MANIPULATOR,
    )
    placement_payload = alternate.placement.model_dump(mode="python")
    placement_payload.update(
        placement_uuid=plan.placement.placement_uuid,
        selected_site_ids=plan.placement.selected_site_ids,
        visible=plan.placement.visible,
        display_opacity=plan.placement.display_opacity,
        notes=plan.placement.notes,
    )
    alternate_placement = NormalizedProbePlacement.model_validate(placement_payload)
    assert alternate_placement.target == plan.placement.target
    assert alternate_placement.entry != plan.placement.entry
    return _plan_with_rehashed_placement(plan, alternate_placement)


def _rewrite_project_json(package: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    (package / PROJECT_FILENAME).write_bytes(encoded)
    checksums_path = package / CHECKSUMS_FILENAME
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[PROJECT_FILENAME] = hashlib.sha256(encoded).hexdigest()
    checksums_path.write_text(
        json.dumps(checksums, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _direction_array(raw: object, *, expected_frame_id: str) -> np.ndarray:
    assert isinstance(raw, dict)
    assert set(raw) == {"frameId", "componentOrder", "units", "ap", "ml", "dv"}
    assert raw["frameId"] == expected_frame_id
    assert raw["componentOrder"] == ["AP", "ML", "DV"]
    assert raw["units"] == "dimensionless"
    return np.asarray(
        (float(raw["ap"]), float(raw["ml"]), float(raw["dv"])),
        dtype=np.float64,
    )


def _canonical_point_array(raw: object) -> np.ndarray:
    assert isinstance(raw, dict)
    return np.asarray(
        (
            float(raw["apMicrometres"]),
            float(raw["mlMicrometres"]),
            float(raw["dvMicrometres"]),
        ),
        dtype=np.float64,
    )


def _physical_point_as_canonical_array(raw: object) -> np.ndarray:
    assert isinstance(raw, dict)
    return np.asarray(
        (
            -float(raw["apMicrometres"]),
            -float(raw["mlMicrometres"]),
            -float(raw["dvMicrometres"]),
        ),
        dtype=np.float64,
    )


def _assert_bridge_geometry_reconstructs_from_placement_basis(
    plan: dict[str, object],
    catalog_model: dict[str, object],
    *,
    expected_scale: float,
) -> None:
    placement = plan["placement"]
    assert isinstance(placement, dict)
    assert set(placement) == {
        "placementId",
        "method",
        "azimuthDegrees",
        "elevationDegrees",
        "insertionDepthMicrometres",
        "axialRotationDegrees",
        "angleConvention",
        "inwardDirection",
        "localLateralDirection",
        "localNormalDirection",
        "modelToPlacementUniformScale",
        "canonicalFrame",
        "atlasFrame",
    }
    canonical = placement["canonicalFrame"]
    assert isinstance(canonical, dict)
    frame_id = canonical["frameId"]
    assert isinstance(frame_id, str)
    inward = _direction_array(placement["inwardDirection"], expected_frame_id=frame_id)
    lateral = _direction_array(
        placement["localLateralDirection"],
        expected_frame_id=frame_id,
    )
    normal = _direction_array(
        placement["localNormalDirection"],
        expected_frame_id=frame_id,
    )
    scale = float(placement["modelToPlacementUniformScale"])
    assert scale == pytest.approx(expected_scale)
    assert np.linalg.norm(inward) == pytest.approx(1)
    assert np.linalg.norm(lateral) == pytest.approx(1)
    assert np.linalg.norm(normal) == pytest.approx(1)
    assert np.dot(inward, lateral) == pytest.approx(0, abs=1e-9)
    assert np.dot(inward, normal) == pytest.approx(0, abs=1e-9)
    assert np.dot(lateral, normal) == pytest.approx(0, abs=1e-9)
    assert np.cross(-inward, lateral) == pytest.approx(normal, abs=1e-9)

    entry = _canonical_point_array(canonical["entry"])
    tip = _canonical_point_array(canonical["tip"])
    depth = float(placement["insertionDepthMicrometres"])
    assert tip == pytest.approx(entry + inward * depth, abs=1e-7)

    model_shanks = catalog_model["shanks"]
    placed_shanks = plan["shanks"]
    placed_sites = plan["recordingSites"]
    assert isinstance(model_shanks, list)
    assert isinstance(placed_shanks, list)
    assert isinstance(placed_sites, list)
    placed_shanks_by_id = {
        shank["shankId"]: shank for shank in placed_shanks if isinstance(shank, dict)
    }
    placed_sites_by_id = {site["siteId"]: site for site in placed_sites if isinstance(site, dict)}
    assert len(placed_shanks_by_id) == len(model_shanks)
    assert len(placed_sites_by_id) == int(catalog_model["siteCount"])

    checked_site_ids: set[str] = set()
    for model_shank in model_shanks:
        assert isinstance(model_shank, dict)
        shank_id = model_shank["shankId"]
        assert isinstance(shank_id, str)
        placed_shank = placed_shanks_by_id[shank_id]
        center_lateral = float(model_shank["centerLateralMicrometres"])
        center_normal = float(model_shank["centerNormalMicrometres"])
        center_offset = lateral * center_lateral * scale + normal * center_normal * scale
        assert _physical_point_as_canonical_array(placed_shank["entry"]) == pytest.approx(
            entry + center_offset,
            abs=1e-7,
        )
        assert _physical_point_as_canonical_array(placed_shank["tip"]) == pytest.approx(
            tip + center_offset,
            abs=1e-7,
        )
        expected_width = float(model_shank["widthMicrometres"]) * scale
        expected_thickness = float(model_shank["thicknessMicrometres"]) * scale
        assert placed_shank["widthMicrometres"] == pytest.approx(expected_width)
        assert placed_shank["thicknessMicrometres"] == pytest.approx(expected_thickness)
        assert placed_shank["conservativeEnvelopeRadiusMicrometres"] == pytest.approx(
            np.hypot(expected_width / 2, expected_thickness / 2)
        )
        assert (
            placed_shank["envelopeDefinition"]
            == "circumscribed-radius-of-rectangular-cross-section"
        )

        model_sites = model_shank["sites"]
        assert isinstance(model_sites, list)
        for model_site in model_sites:
            assert isinstance(model_site, dict)
            site_id = model_site["siteId"]
            assert isinstance(site_id, str)
            placed_site = placed_sites_by_id[site_id]
            assert placed_site["shankId"] == shank_id
            expected_site = (
                tip
                - inward * float(model_site["axialFromTipMicrometres"]) * scale
                + lateral * (center_lateral + float(model_site["lateralMicrometres"])) * scale
                + normal * (center_normal + float(model_site["normalMicrometres"])) * scale
            )
            assert _physical_point_as_canonical_array(placed_site["point"]) == pytest.approx(
                expected_site, abs=1e-7
            )
            checked_site_ids.add(site_id)
    assert checked_site_ids == set(placed_sites_by_id)


def _calibration_with_changed_snapshot(
    calibration: AtlasRegisteredCalibration,
) -> AtlasRegisteredCalibration:
    changed_transform = calibration.atlas_transform.model_copy(
        update={"notes": "same identity, deliberately changed calibration snapshot"}
    )
    return calibration.model_copy(update={"atlas_transform": changed_transform})


def _unacknowledged_affine_calibration(
    calibration: AtlasRegisteredCalibration,
) -> AtlasRegisteredCalibration:
    original = calibration.atlas_transform
    volume_source = AnatomicalPoint(
        frame_id=original.source_frame.frame_id,
        ap_um=0,
        ml_um=0,
        dv_um=1,
    )
    volume_landmark = LandmarkCorrespondence3D(
        label="affine-volume-control",
        source=volume_source,
        destination=transform_point(original, volume_source),
    )
    affine = fit_anatomical_transform(
        source_frame=original.source_frame,
        destination_frame=original.destination_frame,
        landmarks=(*original.landmarks, volume_landmark),
        method=TransformMethod.AFFINE,
        version=original.version,
        affine_distortion_acknowledged=False,
        notes=original.notes,
    )
    return AtlasRegisteredCalibration.model_validate(
        {
            **calibration.model_dump(mode="python"),
            "atlas_transform": affine,
        }
    )


def test_project_rejects_probe_plan_bound_to_different_calibration_snapshot() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None

    changed = _calibration_with_changed_snapshot(session.project.calibrations[0])
    payload = session.project.model_dump(mode="python")
    payload["calibrations"] = [changed.model_dump(mode="python")]

    with pytest.raises(ValueError, match="probe plan calibration digest"):
        PlannerProject.model_validate(payload)


@pytest.mark.parametrize("tamper", ["missing", "changed"])
def test_project_rejects_probe_plan_with_missing_or_changed_source_target(
    tamper: str,
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    payload = session.project.model_dump(mode="python")
    if tamper == "missing":
        payload["unprojected_bregma_targets"] = []
        expected = "probe plan source target is not present"
    else:
        targets = payload["unprojected_bregma_targets"]
        assert isinstance(targets, list)
        changed = dict(targets[0])
        changed["label"] = "different current target snapshot"
        payload["unprojected_bregma_targets"] = [changed]
        expected = "probe plan source target snapshot does not match"

    with pytest.raises(ValueError, match=expected):
        PlannerProject.model_validate(payload)


def test_schema_seven_project_load_rejects_translated_probe_geometry_with_recomputed_self_hash(
    tmp_path: Path,
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    stored = session.project.probe_plans[0]
    forged = _translated_rehashed_plan(stored)
    assert forged.input_sha256 != stored.input_sha256
    assert forged.placement.target != stored.placement.target

    package = save_project(session.project, tmp_path / "translated-rehashed-plan")
    payload = json.loads((package / PROJECT_FILENAME).read_text(encoding="utf-8"))
    payload["schema_version"] = 7
    payload["probe_plans"] = [forged.model_dump(mode="json")]
    _rewrite_project_json(package, payload)

    with pytest.raises(
        ValueError,
        match="placement target does not match the calibrated source target",
    ):
        load_project(package, recover_backup=False)


def test_schema_seven_project_load_accepts_exact_canonical_probe_model_snapshot(
    tmp_path: Path,
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    canonical_model = session.project.probe_plans[0].probe_model

    package = save_project(session.project, tmp_path / "canonical-schema-seven-plan")
    payload = json.loads((package / PROJECT_FILENAME).read_text(encoding="utf-8"))
    payload["schema_version"] = 7
    _rewrite_project_json(package, payload)

    restored = load_project(package, recover_backup=False)

    assert restored.schema_version == PROJECT_SCHEMA_VERSION
    assert restored.probe_plans[0].probe_model == canonical_model


def test_schema_seven_project_load_rejects_wider_probe_model_with_recomputed_self_hash(
    tmp_path: Path,
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    original = session.project.probe_plans[0]
    forged = _wider_model_rehashed_plan(original)
    assert forged.probe_model.shanks[0].width_um == 700
    assert forged.input_sha256 != original.input_sha256

    package = save_project(session.project, tmp_path / "wider-rehashed-schema-seven-plan")
    payload = json.loads((package / PROJECT_FILENAME).read_text(encoding="utf-8"))
    payload["schema_version"] = 7
    payload["probe_plans"] = [forged.model_dump(mode="json")]
    _rewrite_project_json(package, payload)

    with pytest.raises(ValueError, match="does not exactly match the source-pinned catalog"):
        load_project(package, recover_backup=False)


def test_region_analysis_rejects_translated_rehashed_geometry_without_mutation() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    forged = _translated_rehashed_plan(session.project.probe_plans[0])
    session.project.probe_plans[0] = forged
    revision_before = session.project_revision
    events_before = tuple(session.project.event_log)

    with pytest.raises(BridgeError) as rejection:
        _call(
            dispatcher,
            "probe.region.analyze",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before,
            planId=str(forged.plan_uuid),
            expectedPlanInputSha256=forged.input_sha256,
        )

    assert rejection.value.code == "PROBE_PLAN_PROJECTION_INVALID"
    assert "placement target does not match" in rejection.value.details["reason"]
    assert session.project_revision == revision_before
    assert tuple(session.project.event_log) == events_before
    assert session.project.probe_region_analyses == []


def test_region_analysis_rejects_rehashed_probe_model_geometry_without_mutation() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    forged = _wider_model_rehashed_plan(session.project.probe_plans[0])
    session.project.probe_plans[0] = forged
    revision_before = session.project_revision
    events_before = tuple(session.project.event_log)

    with pytest.raises(BridgeError) as rejection:
        _call(
            dispatcher,
            "probe.region.analyze",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before,
            planId=str(forged.plan_uuid),
            expectedPlanInputSha256=forged.input_sha256,
        )

    assert rejection.value.code == "PROBE_PLAN_PROJECTION_INVALID"
    assert "does not exactly match the source-pinned catalog" in rejection.value.details["reason"]
    assert session.project_revision == revision_before
    assert tuple(session.project.event_log) == events_before
    assert session.project.probe_region_analyses == []


@pytest.mark.parametrize("algorithm", ("v2", "v3"))
def test_schema_seven_project_load_rejects_same_target_alternate_trajectory_with_original_inputs(
    tmp_path: Path,
    algorithm: str,
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    original = session.project.probe_plans[0]
    if algorithm == "v2":
        original = _as_v2_plan(original)
        valid_payload = session.project.model_dump(mode="python")
        valid_payload["probe_plans"] = [original.model_dump(mode="python")]
        valid_project = PlannerProject.model_validate(valid_payload)
    else:
        valid_project = session.project
    forged = _same_target_alternate_trajectory_rehashed_plan(valid_project, original)

    # The old target-only boundary and the record's internal hash both pass:
    # source target, projected target, projection digest, and raw inputs are unchanged.
    assert forged.source_target == original.source_target
    assert forged.placement.target == original.placement.target
    assert forged.projection_sha256 == original.projection_sha256
    assert forged.placement_input == original.placement_input
    assert forged.manipulator_input == original.manipulator_input
    assert forged.input_sha256 != original.input_sha256

    package = save_project(valid_project, tmp_path / f"alternate-trajectory-{algorithm}")
    payload = json.loads((package / PROJECT_FILENAME).read_text(encoding="utf-8"))
    payload["schema_version"] = 7
    payload["probe_plans"] = [forged.model_dump(mode="json")]
    _rewrite_project_json(package, payload)

    with pytest.raises(
        ValueError,
        match="placement geometry does not match preserved planning inputs",
    ):
        load_project(package, recover_backup=False)


def test_region_analysis_rejects_same_target_alternate_trajectory_without_mutation() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    original = session.project.probe_plans[0]
    forged = _same_target_alternate_trajectory_rehashed_plan(session.project, original)
    session.project.probe_plans[0] = forged
    revision_before = session.project_revision
    events_before = tuple(session.project.event_log)

    with pytest.raises(BridgeError) as rejection:
        _call(
            dispatcher,
            "probe.region.analyze",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before,
            planId=str(forged.plan_uuid),
            expectedPlanInputSha256=forged.input_sha256,
        )

    assert rejection.value.code == "PROBE_PLAN_PROJECTION_INVALID"
    assert "placement geometry does not match" in rejection.value.details["reason"]
    assert session.project_revision == revision_before
    assert tuple(session.project.event_log) == events_before
    assert session.project.probe_region_analyses == []


def test_region_export_rejects_same_target_alternate_trajectory_without_mutation() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    created = _create_plan(dispatcher, session, target_id)
    plan_payload = created["plan"]
    assert isinstance(plan_payload, dict)
    assert session.project is not None
    _call(
        dispatcher,
        "probe.region.analyze",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan_payload["planId"],
        expectedPlanInputSha256=plan_payload["inputSha256"],
    )
    original = session.project.probe_plans[0]
    forged = _same_target_alternate_trajectory_rehashed_plan(session.project, original)
    session.project.probe_plans[0] = forged
    revision_before = session.project_revision
    events_before = tuple(session.project.event_log)

    with pytest.raises(BridgeError) as rejection:
        _call(
            dispatcher,
            "probe.region.export",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before,
            planId=str(forged.plan_uuid),
            expectedPlanInputSha256=forged.input_sha256,
            format="json",
        )

    assert rejection.value.code == "PROBE_PLAN_PROJECTION_INVALID"
    assert "placement geometry does not match" in rejection.value.details["reason"]
    assert session.project_revision == revision_before
    assert tuple(session.project.event_log) == events_before


def test_region_export_rejects_rehashed_probe_model_geometry_without_mutation() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    created = _create_plan(dispatcher, session, target_id)
    plan_payload = created["plan"]
    assert isinstance(plan_payload, dict)
    assert session.project is not None
    _call(
        dispatcher,
        "probe.region.analyze",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan_payload["planId"],
        expectedPlanInputSha256=plan_payload["inputSha256"],
    )
    forged = _wider_model_rehashed_plan(session.project.probe_plans[0])
    session.project.probe_plans[0] = forged
    revision_before = session.project_revision
    events_before = tuple(session.project.event_log)

    with pytest.raises(BridgeError) as rejection:
        _call(
            dispatcher,
            "probe.region.export",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before,
            planId=str(forged.plan_uuid),
            expectedPlanInputSha256=forged.input_sha256,
            format="json",
        )

    assert rejection.value.code == "PROBE_PLAN_PROJECTION_INVALID"
    assert "does not exactly match the source-pinned catalog" in rejection.value.details["reason"]
    assert session.project_revision == revision_before
    assert tuple(session.project.event_log) == events_before


def test_project_rejects_rehashed_forged_target_projection_digest() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    stored = session.project.probe_plans[0]
    forged_projection_sha256 = "f" * 64
    assert forged_projection_sha256 != stored.projection_sha256
    forged_input_sha256 = probe_plan_input_digest(
        plan_uuid=stored.plan_uuid,
        plan_version=stored.plan_version,
        name=stored.name,
        source_target=stored.source_target,
        probe_model=stored.probe_model,
        manipulator_input=stored.manipulator_input,
        placement_input=stored.placement_input,
        placement=stored.placement,
        calibration_uuid=stored.calibration_uuid,
        calibration_version=stored.calibration_version,
        calibration_sha256=stored.calibration_sha256,
        atlas_metadata_sha256=stored.atlas_metadata_sha256,
        projection_sha256=forged_projection_sha256,
        planning_algorithm_version=stored.planning_algorithm_version,
    )
    plan_payload = stored.model_dump(mode="python")
    plan_payload.update(
        projection_sha256=forged_projection_sha256,
        input_sha256=forged_input_sha256,
    )
    forged = ProbePlanRecord.model_validate(plan_payload)
    project_payload = session.project.model_dump(mode="python")
    project_payload["probe_plans"] = [forged.model_dump(mode="python")]

    with pytest.raises(
        ValueError,
        match="projection digest does not match the calibrated source target",
    ):
        PlannerProject.model_validate(project_payload)


@pytest.mark.parametrize(
    ("landmark_label", "canonical_ml_um", "expected"),
    (
        (
            "bregma",
            -2.0,
            "bregma and lambda must lie within half one ML voxel",
        ),
        (
            "right-skull",
            -3.75,
            "right-skull and left-skull landmarks must lie at least half one ML voxel",
        ),
    ),
)
def test_schema_seven_project_load_rejects_forged_calibration_atlas_midline_semantics(
    tmp_path: Path,
    landmark_label: str,
    canonical_ml_um: float,
    expected: str,
) -> None:
    dispatcher, session = _probe_dispatcher()
    _calibrated_target(dispatcher, session)
    assert session.project is not None
    package = save_project(session.project, tmp_path / f"legacy-{landmark_label}")
    payload = json.loads((package / PROJECT_FILENAME).read_text(encoding="utf-8"))
    payload["schema_version"] = 7
    calibration = payload["calibrations"][0]
    landmarks = calibration["atlas_transform"]["landmarks"]
    landmark = next(item for item in landmarks if item["label"] == landmark_label)
    landmark["destination"]["ml_um"] = canonical_ml_um
    _rewrite_project_json(package, payload)

    with pytest.raises(ValueError, match=expected):
        load_project(package, recover_backup=False)


def test_schema_six_package_with_deleted_plan_target_reopens_by_restoring_snapshot(
    tmp_path: Path,
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    source_target = session.project.probe_plans[0].source_target
    package = save_project(session.project, tmp_path / "schema-six-deleted-target")
    project_path = package / PROJECT_FILENAME
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 6
    payload["unprojected_bregma_targets"] = []
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    project_path.write_bytes(encoded)
    checksums_path = package / CHECKSUMS_FILENAME
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[PROJECT_FILENAME] = hashlib.sha256(encoded).hexdigest()
    checksums_path.write_text(
        json.dumps(checksums, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    reopened = load_project(package, recover_backup=False)

    assert reopened.schema_version == PROJECT_SCHEMA_VERSION
    assert reopened.unprojected_bregma_targets == [source_target]
    assert reopened.probe_plans[0].source_target == source_target


def test_implant_removal_rejects_target_referenced_by_probe_plan_without_mutation() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    created = _create_plan(dispatcher, session, target_id)
    plan = created["plan"]
    assert isinstance(plan, dict)
    assert session.project is not None
    _call(
        dispatcher,
        "probe.region.analyze",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan["planId"],
        expectedPlanInputSha256=plan["inputSha256"],
    )
    revision_before_remove = session.project_revision
    project_before_remove = session.project.model_dump(mode="json")

    with pytest.raises(BridgeError) as in_use:
        _call(
            dispatcher,
            "implant.remove",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before_remove,
            targetId=target_id,
        )

    assert in_use.value.code == "IMPLANT_TARGET_IN_USE"
    assert in_use.value.details == {
        "targetId": target_id,
        "probePlanCount": 1,
        "probePlanIds": [plan["planId"]],
        "cascadeDeletePerformed": False,
    }
    assert session.project_revision == revision_before_remove
    assert session.project.model_dump(mode="json") == project_before_remove


def test_region_export_rejects_changed_calibration_snapshot_without_audit_mutation() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    created = _create_plan(dispatcher, session, target_id)
    plan = created["plan"]
    assert isinstance(plan, dict)
    assert session.project is not None
    _call(
        dispatcher,
        "probe.region.analyze",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan["planId"],
        expectedPlanInputSha256=plan["inputSha256"],
    )
    assert session.project is not None
    changed = _calibration_with_changed_snapshot(session.project.calibrations[0])
    session.project = session.project.model_copy(update={"calibrations": [changed]})
    revision_before_export = session.project_revision
    event_count_before_export = len(session.project.event_log)

    with pytest.raises(BridgeError) as mismatch:
        _call(
            dispatcher,
            "probe.region.export",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=session.project_revision,
            planId=plan["planId"],
            expectedPlanInputSha256=plan["inputSha256"],
            format="json",
        )

    assert mismatch.value.code == "CALIBRATION_DIGEST_MISMATCH"
    assert session.project_revision == revision_before_export
    assert len(session.project.event_log) == event_count_before_export


def test_region_export_blocks_unacknowledged_affine_without_mutation() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    assert session.project is not None
    blocked_calibration = _unacknowledged_affine_calibration(session.project.calibrations[0])
    payload = session.project.model_dump(mode="python")
    payload["calibrations"] = [blocked_calibration.model_dump(mode="python")]
    session.project = PlannerProject.model_validate(payload)
    assert blocked_calibration.permits_planning
    assert not blocked_calibration.permits_final_export

    created = _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target_id,
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name="Direct-atlas affine plan",
        placementMode="TARGET_ANGLES_DEPTH",
        azimuthDegrees=0,
        elevationDegrees=-90,
        insertionDepthMicrometres=4,
        axialRotationDegrees=0,
        customGeometryAcknowledged=True,
    )
    plan = created["plan"]
    assert isinstance(plan, dict)
    analyzed = _call(
        dispatcher,
        "probe.region.analyze",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan["planId"],
        expectedPlanInputSha256=plan["inputSha256"],
    )
    analysis = analyzed["regionAnalysis"]
    assert isinstance(analysis, dict)
    revision_before_export = session.project_revision
    project_before_export = session.project.model_dump(mode="json")

    with pytest.raises(BridgeError) as generation:
        _call(
            dispatcher,
            "probe.region.export",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before_export,
            planId=plan["planId"],
            expectedPlanInputSha256=plan["inputSha256"],
            format="json",
        )
    assert generation.value.code == "CALIBRATION_FINAL_EXPORT_BLOCKED"
    assert generation.value.details == {
        "calibrationId": str(blocked_calibration.calibration_uuid),
        "calibrationSha256": plan["provenance"]["calibrationSha256"],  # type: ignore[index]
        "quality": "pass",
        "transformMethod": "affine",
        "affineDistortionAcknowledged": False,
        "permitsFinalExport": False,
    }
    assert session.project_revision == revision_before_export
    assert session.project.model_dump(mode="json") == project_before_export

    with pytest.raises(BridgeError) as confirmation:
        _call(
            dispatcher,
            "probe.region.export.confirm",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before_export,
            planId=plan["planId"],
            expectedPlanInputSha256=plan["inputSha256"],
            analysisSha256=analysis["analysisSha256"],
            format="json",
            contentSha256="0" * 64,
        )
    assert confirmation.value.code == "CALIBRATION_FINAL_EXPORT_BLOCKED"
    assert session.project_revision == revision_before_export
    assert session.project.model_dump(mode="json") == project_before_export


def test_probe_plan_region_analysis_export_update_and_persistence(tmp_path: Path) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)

    catalog = _call(dispatcher, "probe.catalog.list")
    assert catalog["catalogVersion"] == "brain3d-probe-catalog-v6"
    assert catalog["modelCount"] == 2
    catalog_models = catalog["models"]
    assert isinstance(catalog_models, list)
    assert catalog_models[0]["modelId"] == NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID
    assert catalog_models[0]["verificationStatus"] == "source-transcribed-review-pending"
    assert "review pending" in catalog_models[0]["warning"]
    assert catalog_models[1]["modelId"] == NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID
    assert catalog_models[1]["productCode"] == "NP2013"
    assert {
        NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID,
        NEUROPIXELS_1_0_MODEL_ID,
        GENERIC_TEST_MODEL_ID,
    }.isdisjoint(model["modelId"] for model in catalog_models)

    neuropixels = _call(
        dispatcher,
        "probe.catalog.get",
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
    )["model"]
    assert isinstance(neuropixels, dict)
    assert neuropixels["siteCount"] == 1280
    assert neuropixels["completeGeometryTranscribed"] is True
    assert neuropixels["independentTranscriptionReviewCompleted"] is False
    assert neuropixels["independentlyReviewedBy"] is None
    sources = neuropixels["primarySources"]
    assert isinstance(sources, list)
    assert len(sources) == 5
    shanks = neuropixels["shanks"]
    assert isinstance(shanks, list)
    assert shanks[0]["tipGeometry"] == "chisel"
    assert shanks[0]["tipLengthMicrometres"] == 175
    assert len(shanks[0]["sites"]) == 1280

    created = _create_plan(dispatcher, session, target_id)
    plan = created["plan"]
    assert isinstance(plan, dict)
    plan_id = plan["planId"]
    plan_sha = plan["inputSha256"]
    assert isinstance(plan_id, str)
    assert isinstance(plan_sha, str)
    assert plan["usableForNavigation"] is False
    assert "probe geometry and atlas placement" in plan["warning"]
    assert "generic geometry" not in plan["warning"]
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
    assert provenance["planningAlgorithmVersion"] == "calibrated-explicit-placement-mode-v3"
    placement_input = plan["placementInput"]
    assert isinstance(placement_input, dict)
    assert placement_input["mode"] == "STEREOTAXIC_TARGET_MANIPULATOR"
    assert placement_input["entry"] is None
    assert placement_input["angleFrameId"].startswith("STEREOTAXIC:")
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
    assert len(plan["recordingSites"]) == 1280  # type: ignore[arg-type]

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
    assert len(assignments) == 1280

    revision_before_export = session.project_revision
    assert session.project is not None
    event_count_before_export = len(session.project.event_log)
    csv_export = _call(
        dispatcher,
        "probe.region.export",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=revision_before_export,
        planId=plan_id,
        expectedPlanInputSha256=plan_sha,
        format="csv",
    )
    assert csv_export["status"] == "generated"
    assert csv_export["projectMutated"] is False
    assert "region_segment" in str(csv_export["content"])
    assert "recording_site" in str(csv_export["content"])
    csv_rows = list(csv.DictReader(io.StringIO(str(csv_export["content"]))))
    assert csv_rows
    csv_provenance = csv_rows[0]
    assert csv_provenance["export_schema_version"] == "2"
    assert csv_provenance["project_id"] == str(session.project.project_uuid)
    assert csv_provenance["project_title"] == "Probe test"
    assert csv_provenance["subject_id"] == "mouse-A"
    assert csv_provenance["atlas_identifier"] == "allen_mouse_25um"
    assert csv_provenance["atlas_version"] == "1.2"
    assert csv_provenance["atlas_metadata_sha256"] == "a" * 64
    assert csv_provenance["coordinate_convention"] == session.project.coordinate_convention
    assert csv_provenance["calibration_id"] == plan["calibrationId"]
    assert csv_provenance["calibration_sha256"] == plan["provenance"]["calibrationSha256"]  # type: ignore[index]
    assert csv_provenance["transform_source_frame_id"].startswith("STEREOTAXIC:")
    assert csv_provenance["transform_destination_frame_id"].startswith(
        "ATLAS_CANONICAL_AP_ML_DV_UM:"
    )
    assert len(json.loads(csv_provenance["transform_matrix_row_major_ap_ml_dv"])) == 16
    assert session.project_revision == revision_before_export
    assert csv_export["projectRevision"] == revision_before_export
    assert csv_export["suggestedFileName"] == f"probe-regions-mouse-A-{plan_id}.csv"
    assert len(session.project.event_log) == event_count_before_export

    json_export = _call(
        dispatcher,
        "probe.region.export",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=revision_before_export,
        planId=plan_id,
        expectedPlanInputSha256=plan_sha,
        format="json",
    )
    json_payload = json.loads(str(json_export["content"]))
    assert json_payload["exportKind"] == "probe-region-analysis"
    assert json_payload["exportSchemaVersion"] == 2
    assert json_payload["project"] == {
        "projectId": str(session.project.project_uuid),
        "subjectId": "mouse-A",
        "title": "Probe test",
    }
    assert json_payload["coordinateConvention"] == session.project.coordinate_convention
    assert json_payload["atlas"] == {
        "identifier": "allen_mouse_25um",
        "metadataSha256": "a" * 64,
        "version": "1.2",
    }
    assert json_payload["calibration"]["calibrationId"] == plan["calibrationId"]
    assert (
        json_payload["calibration"]["calibrationSha256"] == plan["provenance"]["calibrationSha256"]
    )
    assert len(json_payload["calibration"]["transform"]["matrixRowMajorAPMLDV"]) == 16
    assert json_payload["analysis"]["analysis_sha256"] == analysis["analysisSha256"]
    assert session.project_revision == revision_before_export
    assert len(session.project.event_log) == event_count_before_export

    # Generation precedes the native save panel. A cancel or failed write must
    # leave no durable claim that an export occurred.
    _call(dispatcher, "state.get")
    assert session.project_revision == revision_before_export
    assert len(session.project.event_log) == event_count_before_export

    with pytest.raises(BridgeError) as mismatched_confirmation:
        _call(
            dispatcher,
            "probe.region.export.confirm",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before_export,
            planId=plan_id,
            expectedPlanInputSha256=plan_sha,
            analysisSha256=csv_export["analysisSha256"],
            format="csv",
            contentSha256="f" * 64,
        )
    assert mismatched_confirmation.value.code == "EXPORT_CONTENT_MISMATCH"
    assert session.project_revision == revision_before_export
    assert len(session.project.event_log) == event_count_before_export

    confirmed = _call(
        dispatcher,
        "probe.region.export.confirm",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=revision_before_export,
        planId=plan_id,
        expectedPlanInputSha256=plan_sha,
        analysisSha256=csv_export["analysisSha256"],
        format="csv",
        contentSha256=csv_export["contentSha256"],
    )
    assert confirmed["status"] == "exported"
    assert confirmed["projectMutated"] is True
    assert session.project_revision == revision_before_export + 1
    assert confirmed["projectRevision"] == session.project_revision
    assert session.project is not None
    export_event = session.project.event_log[-1]
    assert export_event.action == "probe-region-analysis-exported"
    export_details = json.loads(export_event.details or "")
    assert export_details == {
        "analysisSha256": analysis["analysisSha256"],
        "contentSha256": csv_export["contentSha256"],
        "format": "csv",
        "planId": plan_id,
        "planInputSha256": plan_sha,
    }
    state = _call(dispatcher, "state.get")
    state_project = state["project"]
    assert isinstance(state_project, dict)
    state_events = state_project["eventLog"]
    assert isinstance(state_events, list)
    assert state_events[-1]["action"] == "probe-region-analysis-exported"
    event_count = len(session.project.event_log)
    with pytest.raises(BridgeError) as stale_export:
        _call(
            dispatcher,
            "probe.region.export",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision_before_export,
            planId=plan_id,
            expectedPlanInputSha256=plan_sha,
            format="json",
        )
    assert stale_export.value.code == "PROJECT_REVISION_CONFLICT"
    assert len(session.project.event_log) == event_count

    destination = tmp_path / "probe.mouseplan"
    _call(
        dispatcher,
        "project.save",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        path=str(destination),
    )
    reopened_dispatcher, reopened_session = _probe_dispatcher()
    _call(reopened_dispatcher, "project.open", path=str(destination))
    assert reopened_session.project is not None
    assert len(reopened_session.project.probe_plans) == 1
    assert len(reopened_session.project.probe_region_analyses) == 1
    assert any(
        event.action == "probe-region-analysis-exported"
        for event in reopened_session.project.event_log
    )
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
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name="Adjusted vertical NP2 test",
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
    updated_placement = updated_plan["placement"]
    assert isinstance(updated_placement, dict)
    updated_canonical = updated_placement["canonicalFrame"]
    assert isinstance(updated_canonical, dict)
    updated_frame_id = updated_canonical["frameId"]
    assert isinstance(updated_frame_id, str)
    _direction_array(
        updated_placement["inwardDirection"],
        expected_frame_id=updated_frame_id,
    )
    _direction_array(
        updated_placement["localLateralDirection"],
        expected_frame_id=updated_frame_id,
    )
    _direction_array(
        updated_placement["localNormalDirection"],
        expected_frame_id=updated_frame_id,
    )
    assert updated_placement["modelToPlacementUniformScale"] == pytest.approx(1)
    assert reopened_session.project is not None
    assert reopened_session.project.probe_region_analyses == []


@pytest.mark.parametrize(
    ("model_id", "expected_shanks", "expected_sites"),
    (
        (NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID, 1, 1280),
        (NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID, 4, 5120),
    ),
)
def test_np2_models_create_complete_source_traced_plans(
    model_id: str,
    expected_shanks: int,
    expected_sites: int,
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    assert session.project is not None

    created = _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target_id,
        modelId=model_id,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name="Neuropixels 2.0 trajectory",
        azimuthDegrees=0,
        elevationDegrees=-90,
        insertionDepthMicrometres=4,
        axialRotationDegrees=0,
        customGeometryAcknowledged=True,
    )
    plan = created["plan"]
    assert isinstance(plan, dict)
    assert plan["modelId"] == model_id
    assert plan["modelVersion"] == NEUROPIXELS_2_0_MODEL_VERSION
    assert plan["verificationStatus"] == "source-transcribed-review-pending"
    assert plan["usableForNavigation"] is False
    assert "probe geometry and atlas placement" in plan["warning"]
    assert "generic geometry" not in plan["warning"]
    shanks = plan["shanks"]
    recording_sites = plan["recordingSites"]
    assert isinstance(shanks, list)
    assert isinstance(recording_sites, list)
    assert len(shanks) == expected_shanks
    assert len(recording_sites) == expected_sites
    assert [shank["shankId"] for shank in shanks] == [
        f"shank-{index}" for index in range(expected_shanks)
    ]


@pytest.mark.parametrize(
    "model_id",
    (
        NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
    ),
)
def test_np2_bridge_basis_reconstructs_every_scaled_shank_and_site(
    model_id: str,
) -> None:
    dispatcher, session = _probe_dispatcher()
    params = _create_params(session)
    params["atlasTransformMethod"] = "similarity"
    atlas_landmarks = params["atlasLandmarks"]
    assert isinstance(atlas_landmarks, dict)
    scale = 1.5
    angle = np.deg2rad(30)
    rotation = np.asarray(
        (
            (1, 0, 0),
            (0, np.cos(angle), -np.sin(angle)),
            (0, np.sin(angle), np.cos(angle)),
        ),
        dtype=np.float64,
    )
    canonical_bregma = np.asarray((-3.5, -3.5, -3.5), dtype=np.float64)
    source_landmarks = {
        "bregma": np.asarray((0, 0, 0), dtype=np.float64),
        "lambdaPoint": np.asarray((-2, 0, 0), dtype=np.float64),
        "leftSkull": np.asarray((0, -2, 0), dtype=np.float64),
        "rightSkull": np.asarray((0, 2, 0), dtype=np.float64),
    }
    for landmark_name, source_point in source_landmarks.items():
        canonical_point = canonical_bregma + scale * (rotation @ source_point)
        atlas_landmarks[landmark_name] = {
            "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
            "atlasIdentifier": "allen_mouse_25um",
            "atlasVersion": "1.2",
            "componentOrder": ["AP", "DV", "ML"],
            "units": "micrometre",
            "apMicrometres": -float(canonical_point[0]),
            "dvMicrometres": -float(canonical_point[2]),
            "mlMicrometres": -float(canonical_point[1]),
        }
    calibration_response = _call(dispatcher, "calibration.create", **params)
    calibration = calibration_response["calibration"]
    assert isinstance(calibration, dict)
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)
    _set_active(dispatcher, session, calibration_id)
    assert session.project is not None
    target_response = _call(
        dispatcher,
        "implant.add",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        label="rotated similarity target",
        apMillimetres=0,
        mlMillimetres=0,
        dvMillimetres=-0.001,
    )
    target = target_response["target"]
    assert isinstance(target, dict)
    created = _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target["targetId"],
        modelId=model_id,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name="NP2 strict geometry contract",
        placementMode="STEREOTAXIC_TARGET_MANIPULATOR",
        azimuthDegrees=23,
        elevationDegrees=-65,
        insertionDepthMicrometres=3000,
        axialRotationDegrees=37,
        customGeometryAcknowledged=True,
    )
    plan = created["plan"]
    assert isinstance(plan, dict)
    catalog_response = _call(
        dispatcher,
        "probe.catalog.get",
        modelId=model_id,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
    )
    catalog_model = catalog_response["model"]
    assert isinstance(catalog_model, dict)

    _assert_bridge_geometry_reconstructs_from_placement_basis(
        plan,
        catalog_model,
        expected_scale=scale,
    )
    assert session.project is not None
    v2_plan = _as_v2_plan(session.project.probe_plans[0])
    v2_payload = session.project.model_dump(mode="python")
    v2_payload["probe_plans"] = [v2_plan.model_dump(mode="python")]
    restored_v2 = PlannerProject.model_validate(v2_payload)
    assert restored_v2.probe_plans == [v2_plan]


def test_legacy_null_stored_axes_are_resolved_by_the_plan_detail_contract() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    assert session.project is not None
    created = _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target_id,
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name="Legacy direct-atlas target-angle test",
        placementMode="TARGET_ANGLES_DEPTH",
        azimuthDegrees=0,
        elevationDegrees=-90,
        insertionDepthMicrometres=4,
        axialRotationDegrees=0,
        customGeometryAcknowledged=True,
    )
    current_plan = created["plan"]
    assert isinstance(current_plan, dict)
    stored = session.project.probe_plans[0]
    legacy = _as_v1_plan(stored)
    assert legacy.placement.local_lateral_direction is None
    assert legacy.placement.local_normal_direction is None
    project_payload = session.project.model_dump(mode="python")
    project_payload["probe_plans"] = [legacy.model_dump(mode="python")]
    session.project = PlannerProject.model_validate(project_payload)

    reopened = _call(
        dispatcher,
        "probe.plan.get",
        projectId=str(session.project.project_uuid),
        planId=str(legacy.plan_uuid),
    )
    legacy_plan = reopened["plan"]
    assert isinstance(legacy_plan, dict)
    current_placement = current_plan["placement"]
    legacy_bridge_placement = legacy_plan["placement"]
    assert isinstance(current_placement, dict)
    assert isinstance(legacy_bridge_placement, dict)
    assert (
        legacy_bridge_placement["localLateralDirection"]
        == current_placement["localLateralDirection"]
    )
    assert (
        legacy_bridge_placement["localNormalDirection"] == current_placement["localNormalDirection"]
    )
    assert legacy_bridge_placement["modelToPlacementUniformScale"] == pytest.approx(1)
    assert legacy_plan["shanks"] == current_plan["shanks"]
    assert legacy_plan["recordingSites"] == current_plan["recordingSites"]

    with pytest.raises(BridgeError) as analysis_rejection:
        _call(
            dispatcher,
            "probe.region.analyze",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=session.project_revision,
            planId=str(legacy.plan_uuid),
            expectedPlanInputSha256=legacy.input_sha256,
        )
    assert analysis_rejection.value.code == "PROBE_PLAN_RECOMPUTE_REQUIRED"


def test_legacy_v1_project_rejects_rehashed_foreign_calibration_context() -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    assert session.project is not None
    _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target_id,
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name="Legacy context binding test",
        placementMode="TARGET_ANGLES_DEPTH",
        azimuthDegrees=0,
        elevationDegrees=-90,
        insertionDepthMicrometres=4,
        axialRotationDegrees=0,
        customGeometryAcknowledged=True,
    )
    legacy = _as_v1_plan(session.project.probe_plans[0])
    valid_payload = session.project.model_dump(mode="python")
    valid_payload["probe_plans"] = [legacy.model_dump(mode="python")]
    valid_project = PlannerProject.model_validate(valid_payload)

    foreign_context = legacy.placement.context.model_copy(update={"context_uuid": uuid4()})
    placement_payload = legacy.placement.model_dump(mode="python")
    placement_payload["context"] = foreign_context
    foreign_placement = NormalizedProbePlacement.model_validate(placement_payload)
    forged = _plan_with_rehashed_placement(legacy, foreign_placement)
    assert forged.placement.context.subject_id == legacy.placement.context.subject_id
    assert forged.placement.context.context_uuid != legacy.placement.context.context_uuid
    forged_payload = valid_project.model_dump(mode="python")
    forged_payload["probe_plans"] = [forged.model_dump(mode="python")]

    with pytest.raises(
        ValueError,
        match="animal context does not match the referenced calibration",
    ):
        PlannerProject.model_validate(forged_payload)


def test_region_export_filename_safely_identifies_non_filename_subject() -> None:
    subject_id = "../../mouse A🐁"
    dispatcher, session = _probe_dispatcher(subject_id=subject_id)
    target_id = _calibrated_target(dispatcher, session)
    created = _create_plan(dispatcher, session, target_id)
    plan = created["plan"]
    assert isinstance(plan, dict)
    assert session.project is not None
    _call(
        dispatcher,
        "probe.region.analyze",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan["planId"],
        expectedPlanInputSha256=plan["inputSha256"],
    )
    exported = _call(
        dispatcher,
        "probe.region.export",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        planId=plan["planId"],
        expectedPlanInputSha256=plan["inputSha256"],
        format="json",
    )

    suggested = exported["suggestedFileName"]
    assert isinstance(suggested, str)
    assert Path(suggested).name == suggested
    assert "/" not in suggested
    assert ".." not in suggested
    assert "🐁" not in suggested
    assert suggested.startswith("probe-regions-mouse-A-")
    assert suggested.endswith(f"-{plan['planId']}.json")
    payload = json.loads(str(exported["content"]))
    assert payload["project"]["subjectId"] == subject_id


@pytest.mark.parametrize(
    ("mode", "specific", "expected_method", "expects_manipulator"),
    (
        (
            "ENTRY_AND_TARGET",
            {
                "entryAPMillimetres": -0.001,
                "entryMLMillimetres": -0.001,
                "entryDVMillimetres": 0.003,
            },
            "entry-plus-target",
            False,
        ),
        (
            "ENTRY_ANGLES_DEPTH",
            {
                "entryAPMillimetres": -0.001,
                "entryMLMillimetres": -0.001,
                "entryDVMillimetres": 0.003,
                "azimuthDegrees": 0,
                "elevationDegrees": -90,
                "insertionDepthMicrometres": 4,
            },
            "entry-plus-angles-depth",
            False,
        ),
        (
            "TARGET_ANGLES_DEPTH",
            {
                "azimuthDegrees": 0,
                "elevationDegrees": -90,
                "insertionDepthMicrometres": 4,
            },
            "target-plus-angles-depth",
            False,
        ),
        (
            "STEREOTAXIC_TARGET_MANIPULATOR",
            {
                "azimuthDegrees": 0,
                "elevationDegrees": -90,
                "insertionDepthMicrometres": 4,
            },
            "stereotaxic-target-plus-manipulator-angles",
            True,
        ),
    ),
)
def test_all_explicit_placement_modes_are_product_reachable_and_persist_exact_inputs(
    mode: str,
    specific: dict[str, object],
    expected_method: str,
    expects_manipulator: bool,
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    assert session.project is not None
    created = _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target_id,
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name=f"{mode} test",
        placementMode=mode,
        axialRotationDegrees=12,
        customGeometryAcknowledged=True,
        **specific,
    )
    plan = created["plan"]
    assert isinstance(plan, dict)
    assert plan["placementMode"] == mode
    assert plan["placement"]["method"] == expected_method  # type: ignore[index]
    assert (plan["manipulatorInput"] is not None) is expects_manipulator
    placement_input = plan["placementInput"]
    assert isinstance(placement_input, dict)
    assert placement_input["mode"] == mode
    assert placement_input["axialRotationDegrees"] == 12
    if mode.startswith("ENTRY_"):
        entry = placement_input["entry"]
        assert isinstance(entry, dict)
        assert entry["frameId"] == "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"
        assert entry["origin"] == "bregma"
        assert entry["componentOrder"] == ["AP", "ML", "DV"]
        assert entry["apNegativeDirection"] == "posterior/back"
        assert entry["mlNegativeDirection"] == "left"
        assert entry["dvNegativeDirection"] == "deep/ventral"
    else:
        assert placement_input["entry"] is None
    assert session.project.probe_plans[0].placement_input is not None
    restored = PlannerProject.model_validate(session.project.model_dump(mode="python"))
    assert restored.probe_plans == session.project.probe_plans


@pytest.mark.parametrize(
    ("mode", "specific"),
    (
        (
            "ENTRY_AND_TARGET",
            {
                "entryAPMillimetres": -0.001,
                "entryMLMillimetres": -0.001,
                "entryDVMillimetres": 0.003,
            },
        ),
        (
            "ENTRY_ANGLES_DEPTH",
            {
                "entryAPMillimetres": -0.001,
                "entryMLMillimetres": -0.001,
                "entryDVMillimetres": 0.003,
                "azimuthDegrees": 0,
                "elevationDegrees": -90,
                "insertionDepthMicrometres": 4,
            },
        ),
    ),
)
def test_entry_modes_transform_the_complete_pose_through_similarity_calibration(
    mode: str,
    specific: dict[str, object],
) -> None:
    dispatcher, session = _probe_dispatcher()
    params = _create_params(session)
    params["atlasTransformMethod"] = "similarity"
    atlas_landmarks = params["atlasLandmarks"]
    assert isinstance(atlas_landmarks, dict)
    # The stereotaxic baselines are 2 µm. These 3 µm atlas baselines therefore
    # produce a proper 1.5x similarity fit without changing handedness.
    atlas_landmarks["lambdaPoint"] = {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "atlasIdentifier": "allen_mouse_25um",
        "atlasVersion": "1.2",
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": 6.5,
        "dvMicrometres": 3.5,
        "mlMicrometres": 3.5,
    }
    atlas_landmarks["leftSkull"] = {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "atlasIdentifier": "allen_mouse_25um",
        "atlasVersion": "1.2",
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": 3.5,
        "dvMicrometres": 3.5,
        "mlMicrometres": 6.5,
    }
    atlas_landmarks["rightSkull"] = {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "atlasIdentifier": "allen_mouse_25um",
        "atlasVersion": "1.2",
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": 3.5,
        "dvMicrometres": 3.5,
        "mlMicrometres": 0.5,
    }
    created_calibration = _call(dispatcher, "calibration.create", **params)
    calibration = created_calibration["calibration"]
    assert isinstance(calibration, dict)
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)
    _set_active(dispatcher, session, calibration_id)
    assert session.project is not None
    added = _call(
        dispatcher,
        "implant.add",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        label="similarity target",
        apMillimetres=-0.001,
        mlMillimetres=-0.001,
        dvMillimetres=-0.001,
    )
    target = added["target"]
    assert isinstance(target, dict)
    response = _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target["targetId"],
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name=f"{mode} similarity",
        placementMode=mode,
        axialRotationDegrees=0,
        customGeometryAcknowledged=True,
        **specific,
    )
    assert response["status"] == "created"
    stored = session.project.probe_plans[-1]
    assert stored.placement.model_to_placement_uniform_scale == pytest.approx(1.5)
    assert stored.placement.insertion_depth_um == pytest.approx(6.0)
    if mode == "ENTRY_ANGLES_DEPTH":
        assert stored.placement_input is not None
        assert stored.placement_input.angle_frame_id is not None
        assert stored.placement_input.angle_frame_id.startswith("STEREOTAXIC:")


@pytest.mark.parametrize(
    ("mode", "specific"),
    (
        (
            "ENTRY_AND_TARGET",
            {
                "entryAPMillimetres": -0.001,
                "entryMLMillimetres": -0.001,
                "entryDVMillimetres": 0.003,
            },
        ),
        (
            "ENTRY_ANGLES_DEPTH",
            {
                "entryAPMillimetres": -0.001,
                "entryMLMillimetres": -0.001,
                "entryDVMillimetres": 0.003,
                "azimuthDegrees": 0,
                "elevationDegrees": -90,
                "insertionDepthMicrometres": 4,
            },
        ),
    ),
)
def test_entry_modes_reject_affine_calibration_before_projecting_probe_geometry(
    mode: str,
    specific: dict[str, object],
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    assert session.project is not None
    original = session.project.calibrations[0]
    matrix = list(original.atlas_transform.matrix_row_major)
    matrix[1] += 0.2
    affine = AnatomicalTransform.model_validate(
        {
            **original.atlas_transform.model_dump(mode="python"),
            "method": TransformMethod.AFFINE,
            "matrix_row_major": tuple(matrix),
        }
    )
    modified = AtlasRegisteredCalibration.model_validate(
        {
            **original.model_dump(mode="python"),
            "atlas_transform": affine,
        }
    )
    session.project.calibrations[0] = modified
    revision = session.project_revision
    with pytest.raises(BridgeError) as rejected:
        _call(
            dispatcher,
            "probe.plan.create",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=revision,
            targetId=target_id,
            modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
            modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
            name=f"{mode} affine rejection",
            placementMode=mode,
            axialRotationDegrees=0,
            customGeometryAcknowledged=True,
            **specific,
        )
    assert rejected.value.code == "PLACEMENT_INVALID"
    assert "affine transform would shear" in rejected.value.details["reason"]
    assert session.project_revision == revision
    assert session.project.probe_plans == []


@pytest.mark.parametrize(
    "overrides",
    (
        {"placementMode": "UNKNOWN"},
        {"placementMode": "ENTRY_AND_TARGET"},
        {
            "placementMode": "ENTRY_AND_TARGET",
            "entryAPMillimetres": 0,
            "entryMLMillimetres": 0,
            "entryDVMillimetres": 0,
            "azimuthDegrees": 0,
        },
        {
            "placementMode": "TARGET_ANGLES_DEPTH",
            "entryAPMillimetres": 0,
            "entryMLMillimetres": 0,
            "entryDVMillimetres": 0,
        },
    ),
)
def test_explicit_placement_modes_reject_unknown_incomplete_or_irrelevant_inputs(
    overrides: dict[str, object],
) -> None:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    assert session.project is not None
    params: dict[str, object] = {
        "projectId": str(session.project.project_uuid),
        "expectedProjectRevision": session.project_revision,
        "targetId": target_id,
        "modelId": NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        "modelVersion": NEUROPIXELS_2_0_MODEL_VERSION,
        "name": "invalid placement",
        "axialRotationDegrees": 0,
        "customGeometryAcknowledged": True,
        **overrides,
    }
    if overrides.get("placementMode") == "TARGET_ANGLES_DEPTH":
        params.update(
            azimuthDegrees=0,
            elevationDegrees=-90,
            insertionDepthMicrometres=4,
        )
    with pytest.raises(BridgeError) as rejected:
        _call(dispatcher, "probe.plan.create", **params)
    assert rejected.value.code in {"INVALID_PARAMS", "PLACEMENT_INVALID"}


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
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
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
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
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
        "modelId": NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        "modelVersion": NEUROPIXELS_2_0_MODEL_VERSION,
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
