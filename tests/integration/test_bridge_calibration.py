"""End-to-end bridge coverage for subject calibration and target projection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest
from numpy.typing import NDArray

from mouse_brain_planner.bridge.planning import PlanningBridgeSession, register_planning_handlers
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher, BridgeError
from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.probe_plan_models import ProbePlanRecord


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
        citation="Allen CCFv3 test double",
        source_url="https://example.invalid/atlas",
        cache_path="/__test_only__/atlas",
        metadata_sha256="a" * 64,
        resolution_um=(1.0, 1.0, 1.0),
        shape_voxels=(8, 8, 8),
        symmetric=True,
        midline_ml_um=4.0,
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
    metadata = _metadata()
    atlas = _FakeAtlas(
        metadata=metadata,
        reference=np.arange(512, dtype=np.uint16).reshape(metadata.shape_voxels),
        annotation=np.ones(metadata.shape_voxels, dtype=np.int32),
    )
    context = BridgeContext(repository_factory=lambda: pytest.fail("repository not expected"))
    context.set_loaded_atlas(atlas)
    dispatcher = BridgeDispatcher(context)
    session = register_planning_handlers(dispatcher)
    _call(
        dispatcher,
        "project.new",
        animalResearchOnlyAcknowledged=True,
        title="Calibration test",
        subjectId="mouse-A",
    )
    return dispatcher, session


def _call(dispatcher: BridgeDispatcher, method: str, **params: object) -> dict[str, object]:
    return dispatcher.dispatch(method, {"protocolVersion": 1, **params})


def _source_point(ap: float, ml: float, dv: float) -> dict[str, object]:
    return {
        "frameId": "MOUSE_A_RIG_AP_ML_DV_UM",
        "componentOrder": ["AP", "ML", "DV"],
        "units": "micrometre",
        "apMicrometres": ap,
        "mlMicrometres": ml,
        "dvMicrometres": dv,
    }


def _atlas_point(ap: float, dv: float, ml: float) -> dict[str, object]:
    return {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "atlasIdentifier": "allen_mouse_25um",
        "atlasVersion": "1.2",
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": ap,
        "dvMicrometres": dv,
        "mlMicrometres": ml,
    }


def _create_params(
    session: PlanningBridgeSession,
    *,
    expected_revision: int | None = None,
) -> dict[str, object]:
    assert session.project is not None
    return {
        "projectId": str(session.project.project_uuid),
        "expectedProjectRevision": (
            session.project_revision if expected_revision is None else expected_revision
        ),
        "profileId": "mouse-A-session-1",
        "sourceFrame": {
            "frameId": "MOUSE_A_RIG_AP_ML_DV_UM",
            "kind": "skull",
            "originDescription": "Recorded micromanipulator origin for mouse A",
            "apPositiveDirection": "apparatus AP positive",
            "mlPositiveDirection": "apparatus ML positive",
            "dvPositiveDirection": "apparatus DV positive",
            "componentOrder": ["AP", "ML", "DV"],
            "units": "micrometre",
        },
        "skullLandmarks": {
            "bregma": _source_point(0, 0, 0),
            "lambdaPoint": _source_point(-2, 0, 0),
            "leftSkull": _source_point(0, -2, 0),
            "rightSkull": _source_point(0, 2, 0),
            "reportedBregmaLambdaDistanceMicrometres": 2.0,
            "lateralityConfirmedFromAnimal": True,
        },
        "atlasLandmarks": {
            "bregma": _atlas_point(3.5, 3.5, 3.5),
            "lambdaPoint": _atlas_point(5.5, 3.5, 3.5),
            "leftSkull": _atlas_point(3.5, 3.5, 5.5),
            "rightSkull": _atlas_point(3.5, 3.5, 1.5),
        },
        "qualityLimits": {
            "minimumAxisBaselineMicrometres": 0.1,
            "distanceWarningMicrometres": 0.1,
            "distanceFailureMicrometres": 0.3,
            "lateralApWarningMicrometres": 0.1,
            "lateralApFailureMicrometres": 0.3,
            "transformRmsWarningMicrometres": 0.1,
            "transformRmsFailureMicrometres": 0.3,
        },
        "dvReference": "bregma",
        "dvReferenceDescription": "DV zero is the user-measured bregma point",
        "limitsSource": "Test lab SOP revision 1",
        "atlasTransformMethod": "rigid",
        "affineDistortionAcknowledged": False,
        "notes": "Test-only subject calibration",
    }


def _create(
    dispatcher: BridgeDispatcher,
    session: PlanningBridgeSession,
) -> dict[str, object]:
    return _call(dispatcher, "calibration.create", **_create_params(session))


def _set_active(
    dispatcher: BridgeDispatcher,
    session: PlanningBridgeSession,
    calibration_id: str,
) -> dict[str, object]:
    assert session.project is not None
    return _call(
        dispatcher,
        "calibration.setActive",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        calibrationId=calibration_id,
    )


def test_calibration_crud_projection_and_persistence_round_trip(tmp_path: Path) -> None:
    dispatcher, session = _dispatcher()
    hello = _call(dispatcher, "hello", client="calibration-test")
    capabilities = hello["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["subjectAtlasCalibration"] is True
    assert capabilities["calibratedTargetProjection"] is True
    created = _create(dispatcher, session)
    calibration = created["calibration"]
    assert isinstance(calibration, dict)
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)
    assert created["projectRevision"] == 2
    assert calibration["quality"] == "pass"
    assert calibration["permitsPlanning"] is True
    assert calibration["atlasMetadataSha256"] == "a" * 64
    assert len(str(calibration["calibrationSha256"])) == 64

    assert session.project is not None
    listed = _call(
        dispatcher,
        "calibration.list",
        projectId=str(session.project.project_uuid),
    )
    assert listed["calibrationCount"] == 1
    assert listed["activeCalibrationId"] is None
    fetched = _call(
        dispatcher,
        "calibration.get",
        projectId=str(session.project.project_uuid),
        calibrationId=calibration_id,
    )
    fetched_calibration = fetched["calibration"]
    assert isinstance(fetched_calibration, dict)
    assert fetched_calibration["calibrationSha256"] == calibration["calibrationSha256"]
    validated = _call(
        dispatcher,
        "calibration.validate",
        projectId=str(session.project.project_uuid),
        calibrationId=calibration_id,
    )
    assert validated["storedLandmarksReproduced"] is True
    assert session.project_revision == 2

    activated = _set_active(dispatcher, session, calibration_id)
    assert activated["projectRevision"] == 3
    assert activated["activeCalibrationId"] == calibration_id

    target_added = _call(
        dispatcher,
        "implant.add",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        label="negative signs",
        apMillimetres=-0.001,
        mlMillimetres=-0.001,
        dvMillimetres=-0.001,
    )
    target = target_added["target"]
    assert isinstance(target, dict)
    target_id = target["targetId"]
    assert isinstance(target_id, str)
    assert session.project_revision == 4

    projected = _call(
        dispatcher,
        "calibration.projectTarget",
        projectId=str(session.project.project_uuid),
        targetId=target_id,
    )
    atlas_point = projected["atlasPoint"]
    assert isinstance(atlas_point, dict)
    assert atlas_point["apMicrometres"] == pytest.approx(4.5)
    assert atlas_point["mlMicrometres"] == pytest.approx(4.5)
    assert atlas_point["dvMicrometres"] == pytest.approx(4.5)
    assert projected["status"] == "projectedReadOnly"
    assert projected["sourceTargetPreserved"] is True
    assert projected["projectionPersisted"] is False
    assert projected["usableForPlanning"] is True
    assert projected["usableForNavigation"] is False
    assert session.project_revision == 4
    provenance = projected["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["calibrationId"] == calibration_id
    assert provenance["atlasMetadataSha256"] == "a" * 64

    repeated = _call(
        dispatcher,
        "calibration.projectTarget",
        projectId=str(session.project.project_uuid),
        targetId=target_id,
    )
    repeated_provenance = repeated["provenance"]
    assert isinstance(repeated_provenance, dict)
    assert repeated_provenance["projectionSha256"] == provenance["projectionSha256"]
    assert session.project is not None
    assert session.project.unprojected_bregma_targets[0].projected is False

    destination = tmp_path / "calibrated.mouseplan"
    _call(
        dispatcher,
        "project.save",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        path=str(destination),
    )
    reopened_dispatcher, reopened_session = _dispatcher()
    _call(reopened_dispatcher, "project.open", path=str(destination))
    assert reopened_session.project is not None
    assert reopened_session.project.active_calibration_uuid is not None
    assert len(reopened_session.project.calibrations) == 1
    reopened_validation = _call(
        reopened_dispatcher,
        "calibration.validate",
        projectId=str(reopened_session.project.project_uuid),
        calibrationId=calibration_id,
    )
    assert reopened_validation["storedLandmarksReproduced"] is True
    reopened_get = _call(
        reopened_dispatcher,
        "calibration.get",
        projectId=str(reopened_session.project.project_uuid),
        calibrationId=calibration_id,
    )
    reopened_calibration = reopened_get["calibration"]
    assert isinstance(reopened_calibration, dict)
    assert reopened_calibration["calibrationSha256"] == calibration["calibrationSha256"]

    removed = _call(
        reopened_dispatcher,
        "calibration.remove",
        projectId=str(reopened_session.project.project_uuid),
        expectedProjectRevision=reopened_session.project_revision,
        calibrationId=calibration_id,
    )
    assert removed["activeCalibrationCleared"] is True
    assert removed["legacyTargetsPreserved"] is True
    assert reopened_session.project is not None
    assert reopened_session.project.active_calibration_uuid is None
    assert len(reopened_session.project.unprojected_bregma_targets) == 1


def test_calibration_mutation_rejects_stale_revision_without_state_change() -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session, expected_revision=0)

    with pytest.raises(BridgeError) as caught:
        _call(dispatcher, "calibration.create", **params)

    assert caught.value.code == "PROJECT_REVISION_CONFLICT"
    assert session.project_revision == 1
    assert session.project is not None
    assert session.project.calibrations == []


def test_calibration_remove_rejects_persisted_probe_plan_reference() -> None:
    dispatcher, session = _dispatcher()
    created = _create(dispatcher, session)
    calibration = created["calibration"]
    assert isinstance(calibration, dict)
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)
    assert session.project is not None
    plan_id = uuid4()
    session.project.probe_plans.append(
        ProbePlanRecord.model_construct(
            plan_uuid=plan_id,
            calibration_uuid=UUID(calibration_id),
        )
    )

    with pytest.raises(BridgeError) as caught:
        _call(
            dispatcher,
            "calibration.remove",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=session.project_revision,
            calibrationId=calibration_id,
        )

    assert caught.value.code == "CALIBRATION_IN_USE"
    assert caught.value.details == {
        "calibrationId": calibration_id,
        "probePlanCount": 1,
        "probePlanIds": [str(plan_id)],
        "cascadeDeletePerformed": False,
    }
    assert session.project_revision == 2
    assert len(session.project.calibrations) == 1
    assert len(session.project.probe_plans) == 1


@pytest.mark.parametrize("invalid", [True, float("nan"), float("inf"), float("-inf")])
def test_calibration_rejects_boolean_or_nonfinite_landmarks(invalid: object) -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    skull = params["skullLandmarks"]
    assert isinstance(skull, dict)
    bregma = skull["bregma"]
    assert isinstance(bregma, dict)
    bregma["apMicrometres"] = invalid

    with pytest.raises(BridgeError) as caught:
        _call(dispatcher, "calibration.create", **params)

    assert caught.value.code == "INVALID_PARAMS"
    assert session.project_revision == 1


def test_calibration_rejects_integer_too_large_for_a_finite_float() -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    skull = params["skullLandmarks"]
    assert isinstance(skull, dict)
    bregma = skull["bregma"]
    assert isinstance(bregma, dict)
    bregma["apMicrometres"] = 10**10_000

    with pytest.raises(BridgeError) as caught:
        _call(dispatcher, "calibration.create", **params)

    assert caught.value.code == "INVALID_PARAMS"
    assert session.project_revision == 1


def test_calibration_rejects_degenerate_skull_and_unconfirmed_laterality() -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    skull = params["skullLandmarks"]
    assert isinstance(skull, dict)
    skull["leftSkull"] = _source_point(-1, 0, 0)
    skull["rightSkull"] = _source_point(1, 0, 0)

    with pytest.raises(BridgeError) as degenerate:
        _call(dispatcher, "calibration.create", **params)
    assert degenerate.value.code == "CALIBRATION_FIT_REJECTED"

    params = _create_params(session)
    skull = params["skullLandmarks"]
    assert isinstance(skull, dict)
    skull["lateralityConfirmedFromAnimal"] = False
    with pytest.raises(BridgeError) as unconfirmed:
        _call(dispatcher, "calibration.create", **params)
    assert unconfirmed.value.code == "INVALID_PARAMS"
    assert session.project_revision == 1


def test_calibration_rejects_invalid_qc_order_and_outside_atlas_landmark() -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    limits = params["qualityLimits"]
    assert isinstance(limits, dict)
    limits["distanceWarningMicrometres"] = 0.3
    limits["distanceFailureMicrometres"] = 0.3
    with pytest.raises(BridgeError) as limits_error:
        _call(dispatcher, "calibration.create", **params)
    assert limits_error.value.code == "CALIBRATION_INPUT_REJECTED"

    params = _create_params(session)
    landmarks = params["atlasLandmarks"]
    assert isinstance(landmarks, dict)
    landmarks["bregma"] = _atlas_point(8.0, 3.5, 3.5)
    with pytest.raises(BridgeError) as bounds_error:
        _call(dispatcher, "calibration.create", **params)
    assert bounds_error.value.code == "CALIBRATION_INPUT_REJECTED"
    assert session.project_revision == 1


def test_calibration_rejects_swapped_atlas_laterality_and_bregma_lambda() -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    landmarks = params["atlasLandmarks"]
    assert isinstance(landmarks, dict)
    landmarks["leftSkull"], landmarks["rightSkull"] = (
        landmarks["rightSkull"],
        landmarks["leftSkull"],
    )
    with pytest.raises(BridgeError) as laterality:
        _call(dispatcher, "calibration.create", **params)
    assert laterality.value.code == "CALIBRATION_LATERALITY_MISMATCH"

    params = _create_params(session)
    landmarks = params["atlasLandmarks"]
    assert isinstance(landmarks, dict)
    landmarks["bregma"], landmarks["lambdaPoint"] = (
        landmarks["lambdaPoint"],
        landmarks["bregma"],
    )
    with pytest.raises(BridgeError) as order:
        _call(dispatcher, "calibration.create", **params)
    assert order.value.code == "CALIBRATION_LANDMARK_ORDER_INVALID"
    assert session.project_revision == 1


@pytest.mark.parametrize(
    "invalid_landmarks",
    (
        "shifted-midsagittal-axis",
        "lateral-landmarks-on-one-side",
        "lateral-landmarks-too-close-to-midline",
    ),
)
def test_calibration_rejects_atlas_midline_mismatch_without_mutation(
    invalid_landmarks: str,
) -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    landmarks = params["atlasLandmarks"]
    assert isinstance(landmarks, dict)

    if invalid_landmarks == "shifted-midsagittal-axis":
        for label in ("bregma", "lambdaPoint", "leftSkull", "rightSkull"):
            point = landmarks[label]
            assert isinstance(point, dict)
            point["mlMicrometres"] = float(point["mlMicrometres"]) - 1.0
    elif invalid_landmarks == "lateral-landmarks-on-one-side":
        landmarks["leftSkull"] = _atlas_point(3.5, 3.5, 3.0)
    else:
        landmarks["rightSkull"] = _atlas_point(3.5, 3.5, 3.75)
        landmarks["leftSkull"] = _atlas_point(3.5, 3.5, 4.25)

    with pytest.raises(BridgeError) as mismatch:
        _call(dispatcher, "calibration.create", **params)

    assert mismatch.value.code == "CALIBRATION_ATLAS_MIDLINE_MISMATCH"
    assert mismatch.value.details["atlasMidlineMlMicrometres"] == 4.0
    assert session.project_revision == 1
    assert session.project is not None
    assert session.project.calibrations == []
    assert session.project.active_calibration_uuid is None


def test_half_voxel_midline_calibration_maps_signed_ml_to_correct_hemispheres() -> None:
    dispatcher, session = _dispatcher()
    created = _create(dispatcher, session)
    calibration = created["calibration"]
    assert isinstance(calibration, dict)
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)
    _set_active(dispatcher, session, calibration_id)
    assert session.project is not None

    target_ids: dict[str, str] = {}
    for label, ml_mm in (("left target", -0.001), ("right target", 0.001)):
        added = _call(
            dispatcher,
            "implant.add",
            projectId=str(session.project.project_uuid),
            expectedProjectRevision=session.project_revision,
            label=label,
            apMillimetres=0.0,
            mlMillimetres=ml_mm,
            dvMillimetres=0.0,
        )
        target = added["target"]
        assert isinstance(target, dict)
        target_id = target["targetId"]
        assert isinstance(target_id, str)
        target_ids[label] = target_id

    revision_after_targets = session.project_revision
    projected_left = _call(
        dispatcher,
        "calibration.projectTarget",
        projectId=str(session.project.project_uuid),
        targetId=target_ids["left target"],
    )
    projected_right = _call(
        dispatcher,
        "calibration.projectTarget",
        projectId=str(session.project.project_uuid),
        targetId=target_ids["right target"],
    )

    left_point = projected_left["atlasPoint"]
    right_point = projected_right["atlasPoint"]
    assert isinstance(left_point, dict)
    assert isinstance(right_point, dict)
    midline_ml_um = session.project.atlas.midline_ml_um
    assert left_point["mlMicrometres"] > midline_ml_um
    assert right_point["mlMicrometres"] < midline_ml_um
    midline_voxel = session.project.atlas.shape_voxels[2] // 2
    assert projected_left["containingVoxelIndex"]["ml"] >= midline_voxel
    assert projected_right["containingVoxelIndex"]["ml"] < midline_voxel
    assert projected_left["coordinateSemantics"]["mlNegativeDirection"] == "left"
    assert projected_right["coordinateSemantics"]["mlPositiveDirection"] == "right"
    assert session.project_revision == revision_after_targets


def test_failed_calibration_is_persisted_for_review_but_cannot_be_active() -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    skull = params["skullLandmarks"]
    assert isinstance(skull, dict)
    skull["reportedBregmaLambdaDistanceMicrometres"] = 3.0

    created = _call(dispatcher, "calibration.create", **params)
    calibration = created["calibration"]
    assert isinstance(calibration, dict)
    assert calibration["quality"] == "fail"
    assert calibration["permitsPlanning"] is False
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)

    with pytest.raises(BridgeError) as caught:
        _set_active(dispatcher, session, calibration_id)

    assert caught.value.code == "CALIBRATION_QC_FAILED"
    assert session.project_revision == 2
    assert session.project is not None
    assert session.project.active_calibration_uuid is None


def test_failed_atlas_registration_qc_cannot_be_active() -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    landmarks = params["atlasLandmarks"]
    assert isinstance(landmarks, dict)
    landmarks["lambdaPoint"] = _atlas_point(7.0, 3.5, 3.5)

    created = _call(dispatcher, "calibration.create", **params)
    calibration = created["calibration"]
    assert isinstance(calibration, dict)
    assert calibration["skullQuality"] == "pass"
    assert calibration["quality"] == "fail"
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)

    with pytest.raises(BridgeError) as caught:
        _set_active(dispatcher, session, calibration_id)
    assert caught.value.code == "CALIBRATION_QC_FAILED"


def test_warning_calibration_can_be_active_but_reports_warning() -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    skull = params["skullLandmarks"]
    assert isinstance(skull, dict)
    skull["reportedBregmaLambdaDistanceMicrometres"] = 2.15

    created = _call(dispatcher, "calibration.create", **params)
    calibration = created["calibration"]
    assert isinstance(calibration, dict)
    assert calibration["quality"] == "warning"
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)

    active = _set_active(dispatcher, session, calibration_id)

    assert active["activeCalibrationId"] == calibration_id


def test_projection_requires_active_calibration_and_rejects_outside_atlas() -> None:
    dispatcher, session = _dispatcher()
    assert session.project is not None
    target_added = _call(
        dispatcher,
        "implant.add",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        label="outside",
        apMillimetres=-1.0,
        mlMillimetres=0.0,
        dvMillimetres=0.0,
    )
    target = target_added["target"]
    assert isinstance(target, dict)
    target_id = target["targetId"]

    with pytest.raises(BridgeError) as missing:
        _call(
            dispatcher,
            "calibration.projectTarget",
            projectId=str(session.project.project_uuid),
            targetId=target_id,
        )
    assert missing.value.code == "CALIBRATION_REQUIRED"

    created = _create(dispatcher, session)
    calibration = created["calibration"]
    assert isinstance(calibration, dict)
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)
    _set_active(dispatcher, session, calibration_id)

    with pytest.raises(BridgeError) as outside:
        _call(
            dispatcher,
            "calibration.projectTarget",
            projectId=str(session.project.project_uuid),
            targetId=target_id,
        )
    assert outside.value.code == "TARGET_PROJECTION_REJECTED"
    assert session.project.unprojected_bregma_targets[0].projected is False
