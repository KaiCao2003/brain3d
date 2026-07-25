"""Typed, revision-safe subject calibration and target-projection bridge.

No operation in this module invents an atlas bregma coordinate. A calibration
is persisted only after fitting both the measured skull frame and explicit
user-supplied correspondences into the exact project atlas. Legacy AP/ML/DV
targets are immutable inputs; projection returns derived data without replacing
or deleting them.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from pydantic import ValidationError

from mouse_brain_planner.bridge import PROTOCOL_VERSION
from mouse_brain_planner.bridge.server import BridgeDispatcher, BridgeError, JsonObject
from mouse_brain_planner.coordinates.anatomical_atlas import (
    AnatomicalAtlasConversionError,
    brainglobe_physical_to_canonical_anatomical,
    canonical_anatomical_to_brainglobe_physical,
    canonical_atlas_frame,
)
from mouse_brain_planner.coordinates.atlas_space import (
    AtlasIdentityError,
    BrainGlobeAtlasSpace,
    CoordinateBoundsError,
    CoordinateFrameError,
)
from mouse_brain_planner.coordinates.transforms import (
    TransformValidationError,
    fit_anatomical_transform,
    transform_point,
)
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.project_models import (
    MAX_CALIBRATIONS,
    PlannerProject,
    utc_now,
)
from mouse_brain_planner.domain.stereotaxy_models import (
    AtlasRegisteredCalibration,
    BregmaRelativeTargetMM,
    CalibrationQualityLimits,
    DorsoventralReference,
    SkullLandmarkSet,
    atlas_registered_calibration_sha256,
)
from mouse_brain_planner.domain.surgery_common import AnimalSurgeryContext
from mouse_brain_planner.domain.transform_models import (
    AnatomicalFrameDefinition,
    AnatomicalPoint,
    CoordinateSystemKind,
    LandmarkCorrespondence3D,
    TransformMethod,
)
from mouse_brain_planner.surgery.calibration_validation import (
    validate_atlas_registered_calibration_reproducibility,
)
from mouse_brain_planner.surgery.stereotaxy import (
    StereotaxicCalibrationError,
    bregma_relative_target_to_point,
    calibrate_skull_landmarks,
)

MAX_REGISTRATION_LANDMARKS: Final = 128

ProjectGetter = Callable[[], PlannerProject]
RevisionGetter = Callable[[], int]
ProjectReplacer = Callable[[PlannerProject], int]


@dataclass(frozen=True, slots=True)
class _AtlasLandmarkInput:
    label: str
    source_skull_point: AnatomicalPoint
    atlas_physical_point: BrainGlobePhysicalPoint


@dataclass(frozen=True, slots=True)
class _CalibrationCreateInput:
    profile_id: str
    source_frame: AnatomicalFrameDefinition
    skull_landmarks: SkullLandmarkSet
    atlas_landmarks: tuple[_AtlasLandmarkInput, ...]
    quality_limits: CalibrationQualityLimits
    dv_reference: DorsoventralReference
    dv_reference_description: str
    limits_source: str
    atlas_transform_method: TransformMethod
    affine_distortion_acknowledged: bool
    notes: str


@dataclass(slots=True)
class CalibrationBridge:
    """Register calibration operations against one authoritative project session."""

    dispatcher: BridgeDispatcher
    get_project: ProjectGetter
    get_revision: RevisionGetter
    replace_project: ProjectReplacer

    def register(self) -> None:
        self.dispatcher.register("calibration.list", self.list_calibrations)
        self.dispatcher.register("calibration.get", self.get_calibration)
        self.dispatcher.register("calibration.create", self.create_calibration)
        self.dispatcher.register("calibration.setActive", self.set_active)
        self.dispatcher.register("calibration.validate", self.validate_calibration)
        self.dispatcher.register("calibration.remove", self.remove_calibration)
        self.dispatcher.register("calibration.projectTarget", self.project_target)
        self.dispatcher.declare_capability("subjectAtlasCalibration")
        self.dispatcher.declare_capability("calibratedTargetProjection")

    def list_calibrations(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(params, required={"protocolVersion", "projectId"})
        _require_protocol(params)
        project = self._validated_project(params["projectId"])
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "listed",
            "projectId": str(project.project_uuid),
            "projectRevision": self.get_revision(),
            "activeCalibrationId": (
                None
                if project.active_calibration_uuid is None
                else str(project.active_calibration_uuid)
            ),
            "calibrationCount": len(project.calibrations),
            "calibrations": [_calibration_summary(item, project) for item in project.calibrations],
        }

    def get_calibration(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={"protocolVersion", "projectId", "calibrationId"},
        )
        _require_protocol(params)
        project = self._validated_project(params["projectId"])
        calibration = _find_calibration(project, params["calibrationId"])
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "found",
            "projectId": str(project.project_uuid),
            "projectRevision": self.get_revision(),
            "calibration": _calibration_detail(calibration, project),
        }

    def create_calibration(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "profileId",
                "sourceFrame",
                "skullLandmarks",
                "atlasLandmarks",
                "qualityLimits",
                "dvReference",
                "dvReferenceDescription",
                "limitsSource",
                "atlasTransformMethod",
                "affineDistortionAcknowledged",
            },
            optional={"additionalLandmarks", "notes"},
        )
        _require_protocol(params)
        project = self._validated_mutation_project(params)
        if len(project.calibrations) >= MAX_CALIBRATIONS:
            raise BridgeError(
                "CALIBRATION_CAPACITY_REACHED",
                "The project has reached its bounded calibration capacity.",
                details={"maximum": MAX_CALIBRATIONS},
            )
        atlas = _require_project_atlas(project)
        try:
            parsed = _parse_create_input(params, atlas)
        except BridgeError:
            raise
        except (
            AtlasIdentityError,
            CoordinateBoundsError,
            CoordinateFrameError,
            ValidationError,
            ValueError,
        ) as error:
            raise BridgeError(
                "CALIBRATION_INPUT_REJECTED",
                "The calibration input does not satisfy the typed scientific schema.",
                details={"reason": str(error), "exceptionType": type(error).__name__},
            ) from error
        version = 1 + max(
            (
                item.calibration_version
                for item in project.calibrations
                if item.profile_id == parsed.profile_id
            ),
            default=0,
        )
        try:
            skull_calibration = calibrate_skull_landmarks(
                context=AnimalSurgeryContext(subject_id=project.subject_id),
                profile_id=parsed.profile_id,
                source_frame=parsed.source_frame,
                landmarks=parsed.skull_landmarks,
                dv_reference=parsed.dv_reference,
                dv_reference_description=parsed.dv_reference_description,
                quality_limits=parsed.quality_limits,
                limits_source=parsed.limits_source,
                version=version,
                notes=parsed.notes,
            )
            correspondences = tuple(
                LandmarkCorrespondence3D(
                    label=item.label,
                    source=transform_point(
                        skull_calibration.transform,
                        item.source_skull_point,
                    ),
                    destination=brainglobe_physical_to_canonical_anatomical(
                        item.atlas_physical_point,
                        atlas,
                    ),
                )
                for item in parsed.atlas_landmarks
            )
            atlas_transform = fit_anatomical_transform(
                source_frame=skull_calibration.stereotaxic_frame,
                destination_frame=canonical_atlas_frame(atlas),
                landmarks=correspondences,
                method=parsed.atlas_transform_method,
                version=version,
                affine_distortion_acknowledged=parsed.affine_distortion_acknowledged,
                notes=parsed.notes,
            )
            calibration = AtlasRegisteredCalibration(
                calibration_version=version,
                skull_calibration=skull_calibration,
                atlas_transform=atlas_transform,
                atlas_metadata_sha256=atlas.metadata_sha256,
            )
            validate_atlas_registered_calibration_reproducibility(calibration)
            updated = _project_update(
                project,
                calibrations=[*project.calibrations, calibration],
            )
        except (
            AnatomicalAtlasConversionError,
            AtlasIdentityError,
            CoordinateBoundsError,
            CoordinateFrameError,
            StereotaxicCalibrationError,
            TransformValidationError,
            ValidationError,
            ValueError,
        ) as error:
            raise BridgeError(
                "CALIBRATION_FIT_REJECTED",
                "The subject calibration or explicit atlas registration was rejected.",
                details={"reason": str(error), "exceptionType": type(error).__name__},
            ) from error
        updated.touch(
            "calibration-created",
            f"calibration={calibration.calibration_uuid}; profile={calibration.profile_id}; "
            f"version={calibration.calibration_version}; "
            f"quality={calibration.effective_quality.value}",
        )
        return self._publish(
            updated,
            status="created",
            extra={"calibration": _calibration_detail(calibration, updated)},
        )

    def set_active(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "calibrationId",
            },
        )
        _require_protocol(params)
        project = self._validated_mutation_project(params)
        calibration = _find_calibration(project, params["calibrationId"])
        if not calibration.permits_planning:
            raise BridgeError(
                "CALIBRATION_QC_FAILED",
                "A failed calibration cannot be made active or used for planning.",
                details={
                    "calibrationId": str(calibration.calibration_uuid),
                    "quality": calibration.effective_quality.value,
                },
            )
        updated = _project_update(
            project,
            active_calibration_uuid=calibration.calibration_uuid,
        )
        updated.touch(
            "active-calibration-set",
            f"calibration={calibration.calibration_uuid}; "
            f"quality={calibration.effective_quality.value}",
        )
        return self._publish(
            updated,
            status="activeCalibrationSet",
            extra={"calibration": _calibration_summary(calibration, updated)},
        )

    def validate_calibration(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={"protocolVersion", "projectId", "calibrationId"},
        )
        _require_protocol(params)
        project = self._validated_project(params["projectId"])
        calibration = _find_calibration(project, params["calibrationId"])
        try:
            validate_atlas_registered_calibration_reproducibility(calibration)
        except (
            StereotaxicCalibrationError,
            TransformValidationError,
            ValidationError,
            ValueError,
        ) as error:
            raise BridgeError(
                "CALIBRATION_VALIDATION_FAILED",
                "The persisted calibration did not reproduce from its stored landmarks.",
                details={"reason": str(error), "exceptionType": type(error).__name__},
            ) from error
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "validated",
            "projectId": str(project.project_uuid),
            "projectRevision": self.get_revision(),
            "calibration": _calibration_summary(calibration, project),
            "storedLandmarksReproduced": True,
        }

    def remove_calibration(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "calibrationId",
            },
        )
        _require_protocol(params)
        project = self._validated_mutation_project(params)
        calibration = _find_calibration(project, params["calibrationId"])
        referencing_plan_ids = sorted(
            str(plan.plan_uuid)
            for plan in project.probe_plans
            if plan.calibration_uuid == calibration.calibration_uuid
        )
        if referencing_plan_ids:
            raise BridgeError(
                "CALIBRATION_IN_USE",
                "The calibration is referenced by persisted probe plans and cannot be removed.",
                details={
                    "calibrationId": str(calibration.calibration_uuid),
                    "probePlanCount": len(referencing_plan_ids),
                    "probePlanIds": referencing_plan_ids,
                    "cascadeDeletePerformed": False,
                },
            )
        was_active = project.active_calibration_uuid == calibration.calibration_uuid
        updated = _project_update(
            project,
            calibrations=[
                item
                for item in project.calibrations
                if item.calibration_uuid != calibration.calibration_uuid
            ],
            active_calibration_uuid=None if was_active else project.active_calibration_uuid,
        )
        updated.touch(
            "calibration-removed",
            f"calibration={calibration.calibration_uuid}; activeCleared={str(was_active).lower()}; "
            "legacyTargetsPreserved=true",
        )
        return self._publish(
            updated,
            status="removed",
            extra={
                "calibrationId": str(calibration.calibration_uuid),
                "activeCalibrationCleared": was_active,
                "legacyTargetsPreserved": True,
            },
        )

    def project_target(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={"protocolVersion", "projectId", "targetId"},
        )
        _require_protocol(params)
        project = self._validated_project(params["projectId"])
        atlas = _require_project_atlas(project)
        if project.active_calibration_uuid is None:
            raise BridgeError(
                "CALIBRATION_REQUIRED",
                "Select a non-failed subject calibration before projecting a target.",
            )
        calibration = _find_calibration(project, str(project.active_calibration_uuid))
        if not calibration.permits_planning:
            raise BridgeError(
                "CALIBRATION_QC_FAILED",
                "The active calibration failed QC and cannot project a target.",
            )
        target_id = _uuid(params["targetId"], "targetId")
        target = next(
            (item for item in project.unprojected_bregma_targets if item.target_uuid == target_id),
            None,
        )
        if target is None:
            raise BridgeError(
                "IMPLANT_TARGET_NOT_FOUND",
                "The requested unprojected target is not in the current project.",
                details={"targetId": str(target_id)},
            )
        if target.projected:
            raise BridgeError(
                "IMPLANT_TARGET_ALREADY_PROJECTED",
                "Only the original unprojected target can cross this calibration boundary.",
            )
        skull = calibration.skull_calibration
        try:
            calibrated_target = BregmaRelativeTargetMM(
                context_uuid=skull.context.context_uuid,
                calibration_uuid=skull.calibration_uuid,
                profile_id=skull.profile_id,
                stereotaxic_frame_id=skull.stereotaxic_frame.frame_id,
                ap_mm=target.ap_mm,
                ml_mm=target.ml_mm,
                dv_mm=target.dv_mm,
            )
            stereotaxic_point = bregma_relative_target_to_point(
                target=calibrated_target,
                calibration=skull,
            )
            atlas_anatomical = transform_point(
                calibration.atlas_transform,
                stereotaxic_point,
            )
            atlas_point = canonical_anatomical_to_brainglobe_physical(
                atlas_anatomical,
                atlas,
            )
            containing_voxel = BrainGlobeAtlasSpace(atlas).physical_to_index(atlas_point)
        except (
            AnatomicalAtlasConversionError,
            AtlasIdentityError,
            CoordinateBoundsError,
            CoordinateFrameError,
            StereotaxicCalibrationError,
            TransformValidationError,
            ValidationError,
            ValueError,
        ) as error:
            raise BridgeError(
                "TARGET_PROJECTION_REJECTED",
                "The calibrated target does not produce a valid point inside the project atlas.",
                details={"reason": str(error), "exceptionType": type(error).__name__},
            ) from error
        calibration_digest = _calibration_digest(calibration)
        projection_digest = _projection_digest(
            target.model_dump(mode="json"),
            calibration_digest,
            atlas_point.model_dump(mode="json"),
        )
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "projectedReadOnly",
            "projectId": str(project.project_uuid),
            "projectRevision": self.get_revision(),
            "targetId": str(target.target_uuid),
            "sourceTargetPreserved": True,
            "projectionPersisted": False,
            "usableForPlanning": True,
            "usableForNavigation": False,
            "stereotaxicPoint": _anatomical_point_payload(stereotaxic_point),
            "atlasPoint": _atlas_point_payload(atlas_point),
            "containingVoxelIndex": {
                "frameId": containing_voxel.frame_id,
                "componentOrder": ["AP", "DV", "ML"],
                "ap": containing_voxel.ap,
                "dv": containing_voxel.dv,
                "ml": containing_voxel.ml,
            },
            "provenance": {
                "calibrationId": str(calibration.calibration_uuid),
                "calibrationSchemaVersion": calibration.schema_version,
                "calibrationVersion": calibration.calibration_version,
                "calibrationSha256": calibration_digest,
                "atlasTransformId": str(calibration.atlas_transform.transform_uuid),
                "atlasTransformVersion": calibration.atlas_transform.version,
                "atlasTransformMethod": calibration.atlas_transform.method.value,
                "atlasMetadataSha256": calibration.atlas_metadata_sha256,
                "projectionAlgorithm": "bregma-target-through-subject-atlas-calibration-v1",
                "projectionSha256": projection_digest,
            },
            "coordinateSemantics": _target_coordinate_semantics(),
            "warning": (
                "Animal research planning only — derived atlas point is not certified "
                "navigation output and must be independently verified against the animal and rig"
            ),
        }

    def _validated_project(self, raw_project_id: object) -> PlannerProject:
        project = self.get_project()
        project_id = _uuid(raw_project_id, "projectId")
        if project_id != project.project_uuid:
            raise BridgeError(
                "PROJECT_ID_MISMATCH",
                "The calibration request does not belong to the current project.",
                details={
                    "requestedProjectId": str(project_id),
                    "currentProjectId": str(project.project_uuid),
                },
            )
        return project

    def _validated_mutation_project(self, params: Mapping[str, object]) -> PlannerProject:
        project = self._validated_project(params["projectId"])
        expected = _integer(params["expectedProjectRevision"], "expectedProjectRevision")
        actual = self.get_revision()
        if expected != actual:
            raise BridgeError(
                "PROJECT_REVISION_CONFLICT",
                "The calibration mutation was based on a stale project revision.",
                details={
                    "expectedProjectRevision": expected,
                    "actualProjectRevision": actual,
                },
            )
        return project

    def _publish(
        self,
        project: PlannerProject,
        *,
        status: str,
        extra: JsonObject,
    ) -> JsonObject:
        expected_revision = self.get_revision() + 1
        actual_revision = self.replace_project(project)
        if actual_revision != expected_revision:
            raise RuntimeError(
                "calibration project replacer did not increment revision exactly once"
            )
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": status,
            "projectId": str(project.project_uuid),
            "projectRevision": actual_revision,
            "activeCalibrationId": (
                None
                if project.active_calibration_uuid is None
                else str(project.active_calibration_uuid)
            ),
            **extra,
        }


def register_calibration_handlers(
    dispatcher: BridgeDispatcher,
    *,
    get_project: ProjectGetter,
    get_revision: RevisionGetter,
    replace_project: ProjectReplacer,
) -> CalibrationBridge:
    """Register the calibration product boundary and return its adapter."""

    extension = CalibrationBridge(dispatcher, get_project, get_revision, replace_project)
    extension.register()
    return extension


def _parse_create_input(
    params: Mapping[str, object],
    atlas: AtlasMetadata,
) -> _CalibrationCreateInput:
    source_frame_payload = _object(params["sourceFrame"], "sourceFrame")
    _validate_nested_keys(
        source_frame_payload,
        "sourceFrame",
        {
            "frameId",
            "kind",
            "originDescription",
            "apPositiveDirection",
            "mlPositiveDirection",
            "dvPositiveDirection",
            "componentOrder",
            "units",
        },
    )
    _require_exact_value(source_frame_payload["kind"], "skull", "sourceFrame.kind")
    _require_exact_value(
        source_frame_payload["componentOrder"],
        ["AP", "ML", "DV"],
        "sourceFrame.componentOrder",
    )
    _require_exact_value(
        source_frame_payload["units"],
        "micrometre",
        "sourceFrame.units",
    )
    source_frame = AnatomicalFrameDefinition(
        frame_id=_text(source_frame_payload["frameId"], "sourceFrame.frameId", 200),
        kind=CoordinateSystemKind.SKULL,
        origin_description=_text(
            source_frame_payload["originDescription"],
            "sourceFrame.originDescription",
            1000,
        ),
        ap_positive_direction=_text(
            source_frame_payload["apPositiveDirection"],
            "sourceFrame.apPositiveDirection",
            100,
        ),
        ml_positive_direction=_text(
            source_frame_payload["mlPositiveDirection"],
            "sourceFrame.mlPositiveDirection",
            100,
        ),
        dv_positive_direction=_text(
            source_frame_payload["dvPositiveDirection"],
            "sourceFrame.dvPositiveDirection",
            100,
        ),
    )

    skull_payload = _object(params["skullLandmarks"], "skullLandmarks")
    _validate_nested_keys(
        skull_payload,
        "skullLandmarks",
        {
            "bregma",
            "lambdaPoint",
            "leftSkull",
            "rightSkull",
            "reportedBregmaLambdaDistanceMicrometres",
            "lateralityConfirmedFromAnimal",
        },
    )
    if skull_payload["lateralityConfirmedFromAnimal"] is not True:
        raise BridgeError(
            "INVALID_PARAMS",
            "lateralityConfirmedFromAnimal must be the boolean true.",
            details={"field": "skullLandmarks.lateralityConfirmedFromAnimal"},
        )
    source_points = {
        "bregma": _source_point(skull_payload["bregma"], source_frame, "bregma"),
        "lambda": _source_point(skull_payload["lambdaPoint"], source_frame, "lambdaPoint"),
        "left-skull": _source_point(skull_payload["leftSkull"], source_frame, "leftSkull"),
        "right-skull": _source_point(skull_payload["rightSkull"], source_frame, "rightSkull"),
    }
    skull_landmarks = SkullLandmarkSet(
        bregma=source_points["bregma"],
        lambda_point=source_points["lambda"],
        left_skull=source_points["left-skull"],
        right_skull=source_points["right-skull"],
        reported_bregma_lambda_distance_um=_positive_number(
            skull_payload["reportedBregmaLambdaDistanceMicrometres"],
            "skullLandmarks.reportedBregmaLambdaDistanceMicrometres",
        ),
        laterality_confirmed_from_the_animal=True,
    )

    atlas_payload = _object(params["atlasLandmarks"], "atlasLandmarks")
    _validate_nested_keys(
        atlas_payload,
        "atlasLandmarks",
        {"bregma", "lambdaPoint", "leftSkull", "rightSkull"},
    )
    atlas_points = {
        "bregma": _atlas_point(atlas_payload["bregma"], atlas, "bregma"),
        "lambda": _atlas_point(atlas_payload["lambdaPoint"], atlas, "lambdaPoint"),
        "left-skull": _atlas_point(atlas_payload["leftSkull"], atlas, "leftSkull"),
        "right-skull": _atlas_point(atlas_payload["rightSkull"], atlas, "rightSkull"),
    }
    if atlas_points["bregma"].ap_um >= atlas_points["lambda"].ap_um:
        raise BridgeError(
            "CALIBRATION_LANDMARK_ORDER_INVALID",
            "Atlas bregma must be anterior to atlas lambda in BrainGlobe ASR coordinates.",
        )
    if atlas_points["right-skull"].ml_um >= atlas_points["left-skull"].ml_um:
        raise BridgeError(
            "CALIBRATION_LATERALITY_MISMATCH",
            "Atlas right-skull ML must be closer to the right origin than left-skull ML.",
        )
    atlas_midline_ml_um = atlas.midline_ml_um
    half_ml_voxel_um = atlas.resolution_um[2] / 2.0
    floating_tolerance_um = max(1e-9, math.ulp(atlas_midline_ml_um))
    midline_alignment_tolerance_um = half_ml_voxel_um + floating_tolerance_um
    off_midline = {
        label: point.ml_um
        for label, point in (
            ("bregma", atlas_points["bregma"]),
            ("lambdaPoint", atlas_points["lambda"]),
        )
        if abs(point.ml_um - atlas_midline_ml_um) > midline_alignment_tolerance_um
    }
    if off_midline:
        raise BridgeError(
            "CALIBRATION_ATLAS_MIDLINE_MISMATCH",
            "Atlas bregma and lambda must lie on the atlas midsagittal plane "
            "(within half one ML voxel). Re-select both landmarks at the atlas midline.",
            details={
                "atlasMidlineMlMicrometres": atlas_midline_ml_um,
                "halfMlVoxelToleranceMicrometres": half_ml_voxel_um,
                "offMidlineLandmarks": off_midline,
            },
        )
    right_limit_um = atlas_midline_ml_um - half_ml_voxel_um
    left_limit_um = atlas_midline_ml_um + half_ml_voxel_um
    if (
        atlas_points["right-skull"].ml_um > right_limit_um + floating_tolerance_um
        or atlas_points["left-skull"].ml_um < left_limit_um - floating_tolerance_um
    ):
        raise BridgeError(
            "CALIBRATION_ATLAS_MIDLINE_MISMATCH",
            "Atlas right-skull and left-skull landmarks must straddle the atlas midline, "
            "with each landmark at least half one ML voxel from it. "
            "Re-select the landmarks on their named hemispheres.",
            details={
                "atlasMidlineMlMicrometres": atlas_midline_ml_um,
                "minimumLateralSeparationMicrometres": half_ml_voxel_um,
                "rightSkullMlMicrometres": atlas_points["right-skull"].ml_um,
                "leftSkullMlMicrometres": atlas_points["left-skull"].ml_um,
            },
        )
    atlas_landmarks: list[_AtlasLandmarkInput] = [
        _AtlasLandmarkInput(
            label=label,
            source_skull_point=source_points[label],
            atlas_physical_point=atlas_points[label],
        )
        for label in ("bregma", "lambda", "left-skull", "right-skull")
    ]
    additional = params.get("additionalLandmarks", [])
    if not isinstance(additional, list):
        raise BridgeError(
            "INVALID_PARAMS",
            "additionalLandmarks must be an array.",
            details={"field": "additionalLandmarks"},
        )
    if len(additional) > MAX_REGISTRATION_LANDMARKS - len(atlas_landmarks):
        raise BridgeError(
            "INVALID_PARAMS",
            "additionalLandmarks exceeds the bounded calibration landmark capacity.",
            details={"maximum": MAX_REGISTRATION_LANDMARKS - len(atlas_landmarks)},
        )
    for index, raw in enumerate(additional):
        item = _object(raw, f"additionalLandmarks[{index}]")
        _validate_nested_keys(
            item,
            f"additionalLandmarks[{index}]",
            {"label", "sourceSkullPoint", "atlasPoint"},
        )
        atlas_landmarks.append(
            _AtlasLandmarkInput(
                label=_text(item["label"], f"additionalLandmarks[{index}].label", 200),
                source_skull_point=_source_point(
                    item["sourceSkullPoint"],
                    source_frame,
                    f"additionalLandmarks[{index}].sourceSkullPoint",
                ),
                atlas_physical_point=_atlas_point(
                    item["atlasPoint"],
                    atlas,
                    f"additionalLandmarks[{index}].atlasPoint",
                ),
            )
        )

    limits_payload = _object(params["qualityLimits"], "qualityLimits")
    limit_fields = {
        "minimumAxisBaselineMicrometres": "minimum_axis_baseline_um",
        "distanceWarningMicrometres": "distance_warning_um",
        "distanceFailureMicrometres": "distance_failure_um",
        "lateralApWarningMicrometres": "lateral_ap_warning_um",
        "lateralApFailureMicrometres": "lateral_ap_failure_um",
        "transformRmsWarningMicrometres": "transform_rms_warning_um",
        "transformRmsFailureMicrometres": "transform_rms_failure_um",
    }
    _validate_nested_keys(limits_payload, "qualityLimits", set(limit_fields))
    quality_limits = CalibrationQualityLimits(
        **{
            destination: _positive_number(limits_payload[source], f"qualityLimits.{source}")
            for source, destination in limit_fields.items()
        }
    )

    raw_dv_reference = params["dvReference"]
    if not isinstance(raw_dv_reference, str):
        raise BridgeError(
            "INVALID_PARAMS",
            "dvReference must be a supported string enum.",
            details={"field": "dvReference"},
        )
    try:
        dv_reference = DorsoventralReference(raw_dv_reference)
    except ValueError as error:
        raise BridgeError(
            "INVALID_PARAMS",
            "dvReference is not a supported value.",
            details={
                "field": "dvReference",
                "allowed": [item.value for item in DorsoventralReference],
            },
        ) from error

    raw_method = params["atlasTransformMethod"]
    if not isinstance(raw_method, str):
        raise BridgeError(
            "INVALID_PARAMS",
            "atlasTransformMethod must be rigid, similarity, or affine.",
            details={"field": "atlasTransformMethod"},
        )
    try:
        method = TransformMethod(raw_method)
    except ValueError as error:
        raise BridgeError(
            "INVALID_PARAMS",
            "atlasTransformMethod must be rigid, similarity, or affine.",
            details={"field": "atlasTransformMethod"},
        ) from error
    if method not in {TransformMethod.RIGID, TransformMethod.SIMILARITY, TransformMethod.AFFINE}:
        raise BridgeError(
            "INVALID_PARAMS",
            "atlasTransformMethod must be rigid, similarity, or affine.",
            details={"field": "atlasTransformMethod"},
        )
    acknowledgment = params["affineDistortionAcknowledged"]
    if not isinstance(acknowledgment, bool):
        raise BridgeError(
            "INVALID_PARAMS",
            "affineDistortionAcknowledged must be a boolean.",
            details={"field": "affineDistortionAcknowledged"},
        )
    return _CalibrationCreateInput(
        profile_id=_text(params["profileId"], "profileId", 200),
        source_frame=source_frame,
        skull_landmarks=skull_landmarks,
        atlas_landmarks=tuple(atlas_landmarks),
        quality_limits=quality_limits,
        dv_reference=dv_reference,
        dv_reference_description=_text(
            params["dvReferenceDescription"], "dvReferenceDescription", 1000
        ),
        limits_source=_text(params["limitsSource"], "limitsSource", 1000),
        atlas_transform_method=method,
        affine_distortion_acknowledged=acknowledgment,
        notes=_text(params.get("notes", ""), "notes", 4000, allow_empty=True),
    )


def _source_point(
    raw: object,
    frame: AnatomicalFrameDefinition,
    field: str,
) -> AnatomicalPoint:
    payload = _object(raw, field)
    _validate_nested_keys(
        payload,
        field,
        {
            "frameId",
            "componentOrder",
            "units",
            "apMicrometres",
            "mlMicrometres",
            "dvMicrometres",
        },
    )
    _require_exact_value(payload["frameId"], frame.frame_id, f"{field}.frameId")
    _require_exact_value(
        payload["componentOrder"],
        ["AP", "ML", "DV"],
        f"{field}.componentOrder",
    )
    _require_exact_value(payload["units"], "micrometre", f"{field}.units")
    return AnatomicalPoint(
        frame_id=frame.frame_id,
        ap_um=_finite_number(payload["apMicrometres"], f"{field}.apMicrometres"),
        ml_um=_finite_number(payload["mlMicrometres"], f"{field}.mlMicrometres"),
        dv_um=_finite_number(payload["dvMicrometres"], f"{field}.dvMicrometres"),
    )


def _atlas_point(raw: object, atlas: AtlasMetadata, field: str) -> BrainGlobePhysicalPoint:
    payload = _object(raw, field)
    _validate_nested_keys(
        payload,
        field,
        {
            "frameId",
            "atlasIdentifier",
            "atlasVersion",
            "componentOrder",
            "units",
            "apMicrometres",
            "dvMicrometres",
            "mlMicrometres",
        },
    )
    _require_exact_value(
        payload["frameId"],
        "BRAINGLOBE_PHYSICAL_ASR_UM",
        f"{field}.frameId",
    )
    _require_exact_value(
        payload["atlasIdentifier"],
        atlas.atlas_key,
        f"{field}.atlasIdentifier",
    )
    _require_exact_value(
        payload["atlasVersion"],
        atlas.atlas_package_version,
        f"{field}.atlasVersion",
    )
    _require_exact_value(
        payload["componentOrder"],
        ["AP", "DV", "ML"],
        f"{field}.componentOrder",
    )
    _require_exact_value(payload["units"], "micrometre", f"{field}.units")
    point = BrainGlobePhysicalPoint(
        atlas_key=atlas.atlas_key,
        atlas_version=atlas.atlas_package_version,
        ap_um=_finite_number(payload["apMicrometres"], f"{field}.apMicrometres"),
        dv_um=_finite_number(payload["dvMicrometres"], f"{field}.dvMicrometres"),
        ml_um=_finite_number(payload["mlMicrometres"], f"{field}.mlMicrometres"),
    )
    BrainGlobeAtlasSpace(atlas).physical_to_voxel(point)
    return point


def _project_update(project: PlannerProject, **updates: object) -> PlannerProject:
    payload = project.model_dump(mode="python")
    payload.update(updates)
    payload["modified_at"] = utc_now()
    try:
        return PlannerProject.model_validate(payload)
    except ValidationError as error:
        raise BridgeError(
            "PROJECT_STATE_INVALID",
            "The calibration mutation would create invalid project state.",
            details={"validationErrors": error.error_count()},
        ) from error


def _find_calibration(
    project: PlannerProject,
    raw_calibration_id: object,
) -> AtlasRegisteredCalibration:
    calibration_id = _uuid(raw_calibration_id, "calibrationId")
    calibration = next(
        (item for item in project.calibrations if item.calibration_uuid == calibration_id),
        None,
    )
    if calibration is None:
        raise BridgeError(
            "CALIBRATION_NOT_FOUND",
            "The requested calibration is not in the current project.",
            details={"calibrationId": str(calibration_id)},
        )
    return calibration


def _require_project_atlas(project: PlannerProject) -> AtlasMetadata:
    if project.atlas is None:
        raise BridgeError(
            "PROJECT_ATLAS_REQUIRED",
            "An exact project atlas is required for subject calibration.",
        )
    return project.atlas


def _calibration_summary(
    calibration: AtlasRegisteredCalibration,
    project: PlannerProject,
) -> JsonObject:
    return {
        "calibrationId": str(calibration.calibration_uuid),
        "schemaVersion": calibration.schema_version,
        "calibrationVersion": calibration.calibration_version,
        "profileId": calibration.profile_id,
        "mode": calibration.mode,
        "quality": calibration.effective_quality.value,
        "permitsPlanning": calibration.permits_planning,
        "permitsFinalExport": calibration.permits_final_export,
        "active": project.active_calibration_uuid == calibration.calibration_uuid,
        "skullQuality": calibration.skull_calibration.qc.quality.value,
        "skullRmsResidualMicrometres": (calibration.skull_calibration.qc.transform_rms_residual_um),
        "atlasRmsResidualMicrometres": calibration.atlas_transform.rms_residual_um,
        "atlasMaximumResidualMicrometres": calibration.atlas_transform.max_residual_um,
        "atlasTransformMethod": calibration.atlas_transform.method.value,
        "atlasMetadataSha256": calibration.atlas_metadata_sha256,
        "calibrationSha256": _calibration_digest(calibration),
        "qcMessages": list(_effective_qc_messages(calibration)),
    }


def _calibration_detail(
    calibration: AtlasRegisteredCalibration,
    project: PlannerProject,
) -> JsonObject:
    skull = calibration.skull_calibration
    detail = _calibration_summary(calibration, project)
    detail.update(
        {
            "algorithmVersion": calibration.algorithm_version,
            "createdAt": skull.transform.created_at.isoformat().replace("+00:00", "Z"),
            "animalContext": {
                "contextId": str(skull.context.context_uuid),
                "species": skull.context.species,
                "useCase": skull.context.use_case,
                "researchUseOnly": skull.context.research_use_only,
                "certifiedNavigationDevice": skull.context.certified_navigation_device,
                "independentCoordinateVerificationRequired": (
                    skull.context.independent_coordinate_verification_required
                ),
                "subjectId": skull.context.subject_id,
            },
            "sourceFrame": _frame_payload(skull.source_frame),
            "stereotaxicFrame": _frame_payload(skull.stereotaxic_frame),
            "atlasFrame": _frame_payload(calibration.atlas_transform.destination_frame),
            "dvReference": skull.dv_reference.value,
            "dvReferenceDescription": skull.dv_reference_description,
            "skullLandmarks": {
                "bregma": _anatomical_point_payload(skull.landmarks.bregma),
                "lambdaPoint": _anatomical_point_payload(skull.landmarks.lambda_point),
                "leftSkull": _anatomical_point_payload(skull.landmarks.left_skull),
                "rightSkull": _anatomical_point_payload(skull.landmarks.right_skull),
                "reportedBregmaLambdaDistanceMicrometres": (
                    skull.landmarks.reported_bregma_lambda_distance_um
                ),
                "lateralityConfirmedFromAnimal": (
                    skull.landmarks.laterality_confirmed_from_the_animal
                ),
            },
            "qualityLimits": {
                "minimumAxisBaselineMicrometres": (skull.quality_limits.minimum_axis_baseline_um),
                "distanceWarningMicrometres": skull.quality_limits.distance_warning_um,
                "distanceFailureMicrometres": skull.quality_limits.distance_failure_um,
                "lateralApWarningMicrometres": skull.quality_limits.lateral_ap_warning_um,
                "lateralApFailureMicrometres": skull.quality_limits.lateral_ap_failure_um,
                "transformRmsWarningMicrometres": (skull.quality_limits.transform_rms_warning_um),
                "transformRmsFailureMicrometres": (skull.quality_limits.transform_rms_failure_um),
            },
            "limitsSource": skull.qc.limits_source,
            "skullTransform": _transform_payload(skull.transform),
            "atlasTransform": _transform_payload(calibration.atlas_transform),
            "levelingAngles": {
                "pitchDegrees": skull.leveling_angles.pitch_deg,
                "rollDegrees": skull.leveling_angles.roll_deg,
                "yawDegrees": skull.leveling_angles.yaw_deg,
                "convention": skull.leveling_angles.convention,
            },
            "notes": skull.notes,
        }
    )
    return detail


def _frame_payload(frame: AnatomicalFrameDefinition) -> JsonObject:
    return {
        "frameId": frame.frame_id,
        "kind": frame.kind.value,
        "originDescription": frame.origin_description,
        "componentOrder": list(frame.component_order),
        "units": frame.units,
        "apPositiveDirection": frame.ap_positive_direction,
        "mlPositiveDirection": frame.ml_positive_direction,
        "dvPositiveDirection": frame.dv_positive_direction,
        "atlasIdentifier": frame.atlas_key,
        "atlasVersion": frame.atlas_version,
    }


def _transform_payload(transform: object) -> JsonObject:
    from mouse_brain_planner.domain.transform_models import AnatomicalTransform

    if not isinstance(transform, AnatomicalTransform):
        raise TypeError("transform payload requires AnatomicalTransform")
    return {
        "transformId": str(transform.transform_uuid),
        "version": transform.version,
        "method": transform.method.value,
        "matrixRowMajor": list(transform.matrix_row_major),
        "rmsResidualMicrometres": transform.rms_residual_um,
        "maximumResidualMicrometres": transform.max_residual_um,
        "affineDistortionAcknowledged": transform.affine_distortion_acknowledged,
        "createdAt": transform.created_at.isoformat().replace("+00:00", "Z"),
        "notes": transform.notes,
        "landmarks": [
            {
                "landmarkId": str(item.landmark_uuid),
                "label": item.label,
                "source": _anatomical_point_payload(item.source),
                "destination": _anatomical_point_payload(item.destination),
                "enabled": item.enabled,
            }
            for item in transform.landmarks
        ],
        "residuals": [
            {
                "landmarkId": str(item.landmark_uuid),
                "apErrorMicrometres": item.ap_error_um,
                "mlErrorMicrometres": item.ml_error_um,
                "dvErrorMicrometres": item.dv_error_um,
                "radialErrorMicrometres": item.radial_error_um,
            }
            for item in transform.residuals
        ],
    }


def _anatomical_point_payload(point: AnatomicalPoint) -> JsonObject:
    return {
        "frameId": point.frame_id,
        "componentOrder": list(point.component_order),
        "units": point.units,
        "apMicrometres": point.ap_um,
        "mlMicrometres": point.ml_um,
        "dvMicrometres": point.dv_um,
    }


def _atlas_point_payload(point: BrainGlobePhysicalPoint) -> JsonObject:
    return {
        "frameId": point.frame_id,
        "atlasIdentifier": point.atlas_key,
        "atlasVersion": point.atlas_version,
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": point.ap_um,
        "dvMicrometres": point.dv_um,
        "mlMicrometres": point.ml_um,
    }


def _effective_qc_messages(calibration: AtlasRegisteredCalibration) -> tuple[str, ...]:
    messages = list(calibration.skull_calibration.qc.messages)
    rms = calibration.atlas_transform.rms_residual_um
    limits = calibration.skull_calibration.quality_limits
    if rms >= limits.transform_rms_failure_um:
        messages.append(
            "FAIL: atlas landmark RMS residual "
            f"{rms:g} micrometres is at or above configured failure limit "
            f"{limits.transform_rms_failure_um:g}"
        )
    elif rms >= limits.transform_rms_warning_um:
        messages.append(
            "WARNING: atlas landmark RMS residual "
            f"{rms:g} micrometres is at or above configured warning limit "
            f"{limits.transform_rms_warning_um:g}"
        )
    else:
        messages.append("PASS: atlas landmark RMS residual is below the configured warning limit")
    return tuple(messages)


def _calibration_digest(calibration: AtlasRegisteredCalibration) -> str:
    return atlas_registered_calibration_sha256(calibration)


def _projection_digest(
    target: Mapping[str, object],
    calibration_digest: str,
    atlas_point: Mapping[str, object],
) -> str:
    encoded = json.dumps(
        {
            "target": dict(target),
            "calibrationSha256": calibration_digest,
            "atlasPoint": dict(atlas_point),
            "algorithm": "bregma-target-through-subject-atlas-calibration-v1",
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _target_coordinate_semantics() -> JsonObject:
    return {
        "frameId": "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED",
        "origin": "bregma",
        "componentOrder": ["AP", "ML", "DV"],
        "units": "millimetre",
        "apPositiveDirection": "anterior",
        "apNegativeDirection": "posterior/back",
        "mlPositiveDirection": "right",
        "mlNegativeDirection": "left",
        "dvPositiveDirection": "dorsal/up",
        "dvNegativeDirection": "deep/ventral",
    }


def _validate_params(
    params: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    actual = set(params)
    if required - actual or actual - allowed:
        raise BridgeError(
            "INVALID_PARAMS",
            "The method parameters do not match the protocol-v1 calibration schema.",
            details={
                "missing": sorted(required - actual),
                "unexpected": sorted(actual - allowed),
            },
        )


def _validate_nested_keys(
    payload: Mapping[str, object],
    field: str,
    required: set[str],
) -> None:
    actual = set(payload)
    if actual != required:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} does not match its exact object schema.",
            details={
                "field": field,
                "missing": sorted(required - actual),
                "unexpected": sorted(actual - required),
            },
        )


def _require_protocol(params: Mapping[str, object]) -> None:
    value = params["protocolVersion"]
    if isinstance(value, bool) or not isinstance(value, int) or value != PROTOCOL_VERSION:
        raise BridgeError(
            "PROTOCOL_VERSION_MISMATCH",
            f"protocolVersion must equal {PROTOCOL_VERSION}.",
        )


def _require_exact_value(value: object, expected: object, field: str) -> None:
    if value != expected or type(value) is not type(expected):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} does not match the required coordinate contract.",
            details={"field": field, "expected": expected},
        )


def _object(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be an object with string keys.",
            details={"field": field},
        )
    return value


def _text(
    value: object,
    field: str,
    maximum: int,
    *,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be text.",
            details={"field": field},
        )
    normalized = value.strip()
    if (not allow_empty and not normalized) or len(normalized) > maximum:
        qualifier = f"0 to {maximum}" if allow_empty else f"1 to {maximum}"
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must contain {qualifier} visible characters.",
            details={"field": field},
        )
    return normalized


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a finite number and not a boolean.",
            details={"field": field},
        )
    try:
        converted = float(value)
    except (OverflowError, ValueError) as error:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a finite number.",
            details={"field": field},
        ) from error
    if not math.isfinite(converted):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a finite number.",
            details={"field": field},
        )
    return converted


def _positive_number(value: object, field: str) -> float:
    converted = _finite_number(value, field)
    if converted <= 0:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be greater than zero.",
            details={"field": field},
        )
    return converted


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a nonnegative integer.",
            details={"field": field},
        )
    return value


def _uuid(value: object, field: str) -> UUID:
    if not isinstance(value, str):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a UUID string.",
            details={"field": field},
        )
    try:
        return UUID(value)
    except ValueError as error:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a UUID string.",
            details={"field": field},
        ) from error
