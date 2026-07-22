"""Strict probe-catalog, placement, and exact region-analysis bridge methods."""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import numpy as np
from pydantic import ValidationError

from mouse_brain_planner.analysis.probe_region_service import (
    ProbeRegionServiceError,
    analyze_probe_plan_regions,
    annotation_array_sha256,
)
from mouse_brain_planner.analysis.region_traversal import RegionTraversalInputError
from mouse_brain_planner.bridge import PROTOCOL_VERSION
from mouse_brain_planner.bridge.protocol_validation import (
    boolean_value,
    finite_number,
    integer_value,
    require_protocol,
    sha256_value,
    text_value,
    uuid_value,
    validate_params,
)
from mouse_brain_planner.bridge.server import (
    BridgeDispatcher,
    BridgeError,
    JsonObject,
    LoadedAtlasProtocol,
)
from mouse_brain_planner.coordinates.anatomical_atlas import (
    AnatomicalAtlasConversionError,
    canonical_anatomical_to_brainglobe_physical,
)
from mouse_brain_planner.coordinates.atlas_space import (
    AtlasIdentityError,
    BrainGlobeAtlasSpace,
    CoordinateBoundsError,
    CoordinateFrameError,
)
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.probe_models import (
    PlacedProbeShank,
    PlacedRecordingSite,
    ProbeModelDefinition,
    ProbeVerificationStatus,
)
from mouse_brain_planner.domain.probe_plan_models import (
    ProbePlanRecord,
    ProbeRegionAnalysisBundle,
)
from mouse_brain_planner.domain.project_models import MAX_PROBE_PLANS, PlannerProject
from mouse_brain_planner.domain.region_models import AtlasPhysicalPointAPMLDV
from mouse_brain_planner.domain.stereotaxy_models import AtlasRegisteredCalibration
from mouse_brain_planner.domain.transform_models import AnatomicalPoint
from mouse_brain_planner.probes.catalog import (
    PROBE_CATALOG_VERSION,
    get_probe_model,
    list_probe_models,
)
from mouse_brain_planner.surgery.probe_planning import (
    ProbePlanningError,
    build_calibrated_probe_plan,
)
from mouse_brain_planner.surgery.trajectory import (
    ProbePlacementError,
    placed_recording_sites,
    placed_shank_centerlines,
)

MAX_EXPORT_CHARACTERS: Final = 4 * 1024 * 1024

ProjectGetter = Callable[[], PlannerProject]
RevisionGetter = Callable[[], int]
ProjectReplacer = Callable[[PlannerProject], int]
AtlasGetter = Callable[[], LoadedAtlasProtocol]


@dataclass(slots=True)
class ProbePlanningBridge:
    """Revision-safe adapter over persisted probe and traversal services."""

    dispatcher: BridgeDispatcher
    get_project: ProjectGetter
    get_revision: RevisionGetter
    replace_project: ProjectReplacer
    get_atlas: AtlasGetter
    _annotation_cache_key: tuple[str, tuple[int, ...], str] | None = None
    _annotation_sha256: str | None = None

    def register(self) -> None:
        self.dispatcher.register("probe.catalog.list", self.catalog_list)
        self.dispatcher.register("probe.catalog.get", self.catalog_get)
        self.dispatcher.register("probe.plan.list", self.plan_list)
        self.dispatcher.register("probe.plan.get", self.plan_get)
        self.dispatcher.register("probe.plan.create", self.plan_create)
        self.dispatcher.register("probe.plan.update", self.plan_update)
        self.dispatcher.register("probe.plan.remove", self.plan_remove)
        self.dispatcher.register("probe.region.get", self.region_get)
        self.dispatcher.register("probe.region.analyze", self.region_analyze)
        self.dispatcher.register("probe.region.export", self.region_export)
        self.dispatcher.declare_capability("probeCatalog")
        self.dispatcher.declare_capability("calibratedProbePlanning")
        self.dispatcher.declare_capability("exactProbeRegionTraversal")

    def catalog_list(self, params: Mapping[str, object]) -> JsonObject:
        validate_params(params, required={"protocolVersion"})
        require_protocol(params)
        models = list_probe_models()
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "listed",
            "catalogVersion": PROBE_CATALOG_VERSION,
            "modelCount": len(models),
            "models": [_model_payload(model, detail=False) for model in models],
        }

    def catalog_get(self, params: Mapping[str, object]) -> JsonObject:
        validate_params(
            params,
            required={"protocolVersion", "modelId", "modelVersion"},
        )
        require_protocol(params)
        model = _catalog_model(params)
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "found",
            "catalogVersion": PROBE_CATALOG_VERSION,
            "model": _model_payload(model, detail=True),
        }

    def plan_list(self, params: Mapping[str, object]) -> JsonObject:
        validate_params(params, required={"protocolVersion", "projectId"})
        require_protocol(params)
        project = self._validated_project(params["projectId"])
        analyses = {item.plan_uuid: item for item in project.probe_region_analyses}
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "listed",
            "projectId": str(project.project_uuid),
            "projectRevision": self.get_revision(),
            "planCount": len(project.probe_plans),
            "plans": [
                _plan_summary(plan, analyses.get(plan.plan_uuid)) for plan in project.probe_plans
            ],
        }

    def plan_get(self, params: Mapping[str, object]) -> JsonObject:
        validate_params(
            params,
            required={"protocolVersion", "projectId", "planId"},
        )
        require_protocol(params)
        project = self._validated_project(params["projectId"])
        plan = _find_plan(project, params["planId"])
        analysis = _find_analysis(project, plan.plan_uuid, required=False)
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "found",
            "projectId": str(project.project_uuid),
            "projectRevision": self.get_revision(),
            "plan": _plan_detail(plan, project.atlas),
            "regionAnalysis": (None if analysis is None else _region_bundle_payload(analysis)),
        }

    def plan_create(self, params: Mapping[str, object]) -> JsonObject:
        required = _PLAN_INPUT_FIELDS | {
            "protocolVersion",
            "projectId",
            "expectedProjectRevision",
        }
        validate_params(params, required=required)
        require_protocol(params)
        project = self._validated_mutation_project(params)
        if len(project.probe_plans) >= MAX_PROBE_PLANS:
            raise BridgeError(
                "PROBE_PLAN_CAPACITY_REACHED",
                "The project has reached its bounded probe-plan capacity.",
                details={"maximum": MAX_PROBE_PLANS},
            )
        plan = self._build_plan(project, params, plan_uuid=None, plan_version=1)
        updated = _project_update(project, probe_plans=[*project.probe_plans, plan])
        updated.touch(
            "probe-plan-created",
            f"plan={plan.plan_uuid}; version=1; inputSha256={plan.input_sha256}",
        )
        return self._publish(
            updated,
            status="created",
            extra={"plan": _plan_detail(plan, updated.atlas)},
        )

    def plan_update(self, params: Mapping[str, object]) -> JsonObject:
        required = _PLAN_INPUT_FIELDS | {
            "protocolVersion",
            "projectId",
            "expectedProjectRevision",
            "planId",
            "expectedPlanInputSha256",
        }
        validate_params(params, required=required)
        require_protocol(params)
        project = self._validated_mutation_project(params)
        existing = _find_plan(project, params["planId"])
        _require_plan_hash(existing, params["expectedPlanInputSha256"])
        plan = self._build_plan(
            project,
            params,
            plan_uuid=existing.plan_uuid,
            plan_version=existing.plan_version + 1,
            created_at=existing.created_at,
        )
        updated = _project_update(
            project,
            probe_plans=[
                plan if item.plan_uuid == existing.plan_uuid else item
                for item in project.probe_plans
            ],
            probe_region_analyses=[
                item
                for item in project.probe_region_analyses
                if item.plan_uuid != existing.plan_uuid
            ],
        )
        updated.touch(
            "probe-plan-updated",
            f"plan={plan.plan_uuid}; version={plan.plan_version}; "
            f"inputSha256={plan.input_sha256}; priorAnalysisCleared=true",
        )
        return self._publish(
            updated,
            status="updated",
            extra={"plan": _plan_detail(plan, updated.atlas), "priorAnalysisCleared": True},
        )

    def plan_remove(self, params: Mapping[str, object]) -> JsonObject:
        validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "planId",
                "expectedPlanInputSha256",
            },
        )
        require_protocol(params)
        project = self._validated_mutation_project(params)
        plan = _find_plan(project, params["planId"])
        _require_plan_hash(plan, params["expectedPlanInputSha256"])
        analysis_removed = any(
            item.plan_uuid == plan.plan_uuid for item in project.probe_region_analyses
        )
        updated = _project_update(
            project,
            probe_plans=[item for item in project.probe_plans if item.plan_uuid != plan.plan_uuid],
            probe_region_analyses=[
                item for item in project.probe_region_analyses if item.plan_uuid != plan.plan_uuid
            ],
        )
        updated.touch(
            "probe-plan-removed",
            f"plan={plan.plan_uuid}; regionAnalysisRemoved={str(analysis_removed).lower()}",
        )
        return self._publish(
            updated,
            status="removed",
            extra={
                "planId": str(plan.plan_uuid),
                "regionAnalysisRemoved": analysis_removed,
            },
        )

    def region_get(self, params: Mapping[str, object]) -> JsonObject:
        validate_params(
            params,
            required={"protocolVersion", "projectId", "planId"},
        )
        require_protocol(params)
        project = self._validated_project(params["projectId"])
        plan = _find_plan(project, params["planId"])
        analysis = _find_analysis(project, plan.plan_uuid, required=True)
        assert analysis is not None
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "found",
            "projectId": str(project.project_uuid),
            "projectRevision": self.get_revision(),
            "regionAnalysis": _region_bundle_payload(analysis),
        }

    def region_analyze(self, params: Mapping[str, object]) -> JsonObject:
        validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "planId",
                "expectedPlanInputSha256",
            },
        )
        require_protocol(params)
        project = self._validated_mutation_project(params)
        plan = _find_plan(project, params["planId"])
        _require_plan_hash(plan, params["expectedPlanInputSha256"])
        atlas = self.get_atlas()
        if project.atlas is None or project.atlas.metadata_sha256 != atlas.metadata.metadata_sha256:
            raise BridgeError(
                "ATLAS_IDENTITY_MISMATCH",
                "The loaded atlas does not match the probe plan's project atlas.",
            )
        annotation_version = atlas.metadata.source_annotation
        if annotation_version is None or not annotation_version.strip():
            raise BridgeError(
                "ATLAS_ANNOTATION_PROVENANCE_MISSING",
                "The loaded atlas does not declare an annotation source version.",
            )
        try:
            annotation = np.asarray(atlas.annotation)
            annotation_sha256 = self._annotation_digest(annotation, atlas.metadata)
            analysis = analyze_probe_plan_regions(
                plan=plan,
                annotation=annotation,
                metadata=atlas.metadata,
                annotation_sha256=annotation_sha256,
                annotation_version=annotation_version,
                regions={region.structure_id: region for region in atlas.regions},
            )
        except (
            AnatomicalAtlasConversionError,
            ProbePlacementError,
            ProbeRegionServiceError,
            RegionTraversalInputError,
            TypeError,
            ValidationError,
            ValueError,
        ) as error:
            raise BridgeError(
                "REGION_ANALYSIS_REJECTED",
                "The exact probe-region analysis could not be completed from verified inputs.",
                details={"reason": str(error), "exceptionType": type(error).__name__},
            ) from error
        current_revision = self.get_revision()
        current_project = self.get_project()
        current_plan = next(
            (item for item in current_project.probe_plans if item.plan_uuid == plan.plan_uuid),
            None,
        )
        if (
            current_revision
            != integer_value(params["expectedProjectRevision"], "expectedProjectRevision")
            or current_plan is None
            or current_plan.input_sha256 != plan.input_sha256
        ):
            raise BridgeError(
                "ANALYSIS_STALE",
                "Probe inputs changed before the region analysis could be stored.",
                details={"analysisStored": False},
            )
        updated = _project_update(
            current_project,
            probe_region_analyses=[
                item
                for item in current_project.probe_region_analyses
                if item.plan_uuid != plan.plan_uuid
            ]
            + [analysis],
        )
        updated.touch(
            "probe-region-analysis-run",
            f"plan={plan.plan_uuid}; planInputSha256={plan.input_sha256}; "
            f"analysisSha256={analysis.analysis_sha256}",
        )
        return self._publish(
            updated,
            status="analyzed",
            extra={"regionAnalysis": _region_bundle_payload(analysis)},
        )

    def region_export(self, params: Mapping[str, object]) -> JsonObject:
        validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "planId",
                "expectedPlanInputSha256",
                "format",
            },
        )
        require_protocol(params)
        project = self._validated_project(params["projectId"])
        plan = _find_plan(project, params["planId"])
        _require_plan_hash(plan, params["expectedPlanInputSha256"])
        analysis = _find_analysis(project, plan.plan_uuid, required=True)
        assert analysis is not None
        export_format = text_value(params["format"], "format", maximum=10).lower()
        if export_format == "csv":
            content = _region_csv(plan, analysis)
            mime_type = "text/csv"
            file_extension = "csv"
        elif export_format == "json":
            content = analysis.model_dump_json(indent=2)
            mime_type = "application/json"
            file_extension = "json"
        else:
            raise BridgeError(
                "INVALID_PARAMS",
                "format must be exactly csv or json.",
            )
        if len(content) > MAX_EXPORT_CHARACTERS:
            raise BridgeError(
                "EXPORT_TOO_LARGE",
                "The in-memory region export exceeds the bridge response limit.",
            )
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "exportedReadOnly",
            "projectId": str(project.project_uuid),
            "projectRevision": self.get_revision(),
            "planId": str(plan.plan_uuid),
            "planInputSha256": plan.input_sha256,
            "analysisSha256": analysis.analysis_sha256,
            "format": export_format,
            "mimeType": mime_type,
            "suggestedFileName": f"probe-regions-{plan.plan_uuid}.{file_extension}",
            "content": content,
            "contentSha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "projectMutated": False,
        }

    def _validated_project(self, raw_project_id: object) -> PlannerProject:
        project = self.get_project()
        project_id = uuid_value(raw_project_id, "projectId")
        if project_id != project.project_uuid:
            raise BridgeError(
                "PROJECT_ID_MISMATCH",
                "The probe request does not belong to the current project.",
            )
        return project

    def _validated_mutation_project(self, params: Mapping[str, object]) -> PlannerProject:
        project = self._validated_project(params["projectId"])
        expected = integer_value(params["expectedProjectRevision"], "expectedProjectRevision")
        actual = self.get_revision()
        if expected != actual:
            raise BridgeError(
                "PROJECT_REVISION_CONFLICT",
                "The probe mutation was based on a stale project revision.",
                details={"expectedProjectRevision": expected, "actualProjectRevision": actual},
            )
        return project

    def _build_plan(
        self,
        project: PlannerProject,
        params: Mapping[str, object],
        *,
        plan_uuid: UUID | None,
        plan_version: int,
        created_at: Any | None = None,
    ) -> ProbePlanRecord:
        if project.atlas is None:
            raise BridgeError("ATLAS_NOT_OPEN", "A project atlas is required for probe planning.")
        if project.active_calibration_uuid is None:
            raise BridgeError(
                "CALIBRATION_REQUIRED",
                "Activate a non-failed subject calibration before creating a probe plan.",
            )
        calibration = _find_calibration(project, project.active_calibration_uuid)
        if not calibration.permits_planning:
            raise BridgeError(
                "CALIBRATION_FAILED_QC",
                "The active calibration failed QC and cannot create a probe plan.",
            )
        target_id = uuid_value(params["targetId"], "targetId")
        target = next(
            (item for item in project.unprojected_bregma_targets if item.target_uuid == target_id),
            None,
        )
        if target is None:
            raise BridgeError(
                "IMPLANT_TARGET_NOT_FOUND",
                "The requested bregma target is not in the current project.",
            )
        model = _catalog_model(params)
        try:
            plan, _ = build_calibrated_probe_plan(
                target=target,
                calibration=calibration,
                atlas=project.atlas,
                model=model,
                name=text_value(params["name"], "name", maximum=200),
                azimuth_deg=finite_number(
                    params["azimuthDegrees"],
                    "azimuthDegrees",
                    minimum=-180,
                    maximum=180,
                ),
                elevation_deg=finite_number(
                    params["elevationDegrees"],
                    "elevationDegrees",
                    minimum=-90,
                    maximum=90,
                ),
                insertion_depth_um=finite_number(
                    params["insertionDepthMicrometres"],
                    "insertionDepthMicrometres",
                    minimum=0,
                    minimum_inclusive=False,
                ),
                axial_rotation_deg=finite_number(
                    params["axialRotationDegrees"],
                    "axialRotationDegrees",
                    minimum=-180,
                    maximum=180,
                ),
                custom_geometry_acknowledged=boolean_value(
                    params["customGeometryAcknowledged"],
                    "customGeometryAcknowledged",
                ),
                plan_uuid=plan_uuid,
                plan_version=plan_version,
                created_at=created_at,
            )
        except (
            AnatomicalAtlasConversionError,
            AtlasIdentityError,
            CoordinateBoundsError,
            CoordinateFrameError,
            ProbePlacementError,
            ProbePlanningError,
            ValidationError,
            ValueError,
        ) as error:
            raise BridgeError(
                "PLACEMENT_INVALID",
                "The calibrated probe placement was rejected.",
                details={"reason": str(error), "exceptionType": type(error).__name__},
            ) from error
        return plan

    def _annotation_digest(
        self,
        annotation: np.ndarray[Any, Any],
        metadata: AtlasMetadata,
    ) -> str:
        key = (metadata.metadata_sha256, tuple(annotation.shape), annotation.dtype.str)
        if key != self._annotation_cache_key or self._annotation_sha256 is None:
            self._annotation_sha256 = annotation_array_sha256(annotation)
            self._annotation_cache_key = key
        return self._annotation_sha256

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
            raise RuntimeError("probe project replacer did not increment revision exactly once")
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": status,
            "projectId": str(project.project_uuid),
            "projectRevision": actual_revision,
            **extra,
        }


_PLAN_INPUT_FIELDS: Final[set[str]] = {
    "targetId",
    "modelId",
    "modelVersion",
    "name",
    "azimuthDegrees",
    "elevationDegrees",
    "insertionDepthMicrometres",
    "axialRotationDegrees",
    "customGeometryAcknowledged",
}


def register_probe_planning_handlers(
    dispatcher: BridgeDispatcher,
    *,
    get_project: ProjectGetter,
    get_revision: RevisionGetter,
    replace_project: ProjectReplacer,
    get_atlas: AtlasGetter,
) -> ProbePlanningBridge:
    extension = ProbePlanningBridge(
        dispatcher=dispatcher,
        get_project=get_project,
        get_revision=get_revision,
        replace_project=replace_project,
        get_atlas=get_atlas,
    )
    extension.register()
    return extension


def _catalog_model(params: Mapping[str, object]) -> ProbeModelDefinition:
    model_id = text_value(params["modelId"], "modelId", maximum=200)
    model_version = text_value(params["modelVersion"], "modelVersion", maximum=100)
    try:
        return get_probe_model(model_id, model_version)
    except KeyError as error:
        raise BridgeError(
            "PROBE_MODEL_NOT_FOUND",
            "The exact probe model identity is not in the reviewed catalog.",
            details={"modelId": model_id, "modelVersion": model_version},
        ) from error


def _find_calibration(
    project: PlannerProject,
    calibration_uuid: UUID,
) -> AtlasRegisteredCalibration:
    calibration = next(
        (item for item in project.calibrations if item.calibration_uuid == calibration_uuid),
        None,
    )
    if calibration is None:
        raise BridgeError(
            "CALIBRATION_REQUIRED",
            "The active calibration is not available in the current project.",
        )
    return calibration


def _find_plan(project: PlannerProject, raw_plan_id: object) -> ProbePlanRecord:
    plan_id = uuid_value(raw_plan_id, "planId")
    plan = next((item for item in project.probe_plans if item.plan_uuid == plan_id), None)
    if plan is None:
        raise BridgeError(
            "PROBE_PLAN_NOT_FOUND",
            "The requested probe plan is not in the current project.",
            details={"planId": str(plan_id)},
        )
    return plan


def _find_analysis(
    project: PlannerProject,
    plan_uuid: UUID,
    *,
    required: bool,
) -> ProbeRegionAnalysisBundle | None:
    analysis = next(
        (item for item in project.probe_region_analyses if item.plan_uuid == plan_uuid),
        None,
    )
    if required and analysis is None:
        raise BridgeError(
            "REGION_ANALYSIS_NOT_FOUND",
            "Run exact region analysis for this probe plan first.",
            details={"planId": str(plan_uuid)},
        )
    return analysis


def _require_plan_hash(plan: ProbePlanRecord, raw_hash: object) -> None:
    expected = sha256_value(raw_hash, "expectedPlanInputSha256")
    if expected != plan.input_sha256:
        raise BridgeError(
            "ANALYSIS_STALE",
            "The request refers to an older probe-plan input.",
            details={"expectedPlanInputSha256": expected, "actual": plan.input_sha256},
        )


def _project_update(project: PlannerProject, **changes: object) -> PlannerProject:
    payload = project.model_dump(mode="python")
    payload.update(changes)
    return PlannerProject.model_validate(payload)


def _model_payload(model: ProbeModelDefinition, *, detail: bool) -> JsonObject:
    base: JsonObject = {
        "modelId": model.model_id,
        "modelVersion": model.model_version,
        "displayName": model.display_name,
        "manufacturer": model.manufacturer,
        "productCode": model.product_code,
        "hardwareRevision": model.hardware_revision,
        "verificationStatus": model.verification.status.value,
        "verifiedDeviceLabelPermitted": model.permits_verified_device_label,
        "shankCount": model.declared_shank_count,
        "siteCount": sum(len(shank.sites) for shank in model.shanks),
        "units": model.units,
        "warning": _model_warning(model),
    }
    if detail:
        base["geometryNotes"] = model.geometry_notes
        base["reviewNotes"] = model.verification.review_notes
        base["completeGeometryTranscribed"] = model.verification.complete_geometry_transcribed
        base["independentTranscriptionReviewCompleted"] = (
            model.verification.independent_transcription_review_completed
        )
        base["transcribedBy"] = model.verification.transcribed_by
        base["independentlyReviewedBy"] = model.verification.independently_reviewed_by
        base["coordinateOrigin"] = model.coordinate_origin
        base["localAxisDefinition"] = model.local_axis_definition
        base["insertionAxisDefinition"] = model.insertion_axis_definition
        base["primarySources"] = [
            {
                "title": source.title,
                "sourceUrl": source.source_url,
                "documentRevision": source.document_revision,
                "retrievedOn": source.retrieved_on.isoformat(),
                "sha256": source.sha256,
                "citation": source.citation,
            }
            for source in model.verification.primary_sources
        ]
        base["shanks"] = [
            {
                "shankId": shank.shank_id,
                "lengthMicrometres": shank.length_um,
                "widthMicrometres": shank.width_um,
                "thicknessMicrometres": shank.thickness_um,
                "tipGeometry": shank.tip_geometry.value,
                "tipLengthMicrometres": shank.tip_length_um,
                "tipGeometryNotes": shank.tip_geometry_notes,
                "centerLateralMicrometres": shank.center_lateral_um,
                "centerNormalMicrometres": shank.center_normal_um,
                "siteCount": len(shank.sites),
                "sites": [
                    {
                        "siteId": site.site_id,
                        "role": site.role.value,
                        "bank": site.bank,
                        "axialFromTipMicrometres": site.local.axial_from_tip_um,
                        "lateralMicrometres": site.local.lateral_um,
                        "normalMicrometres": site.local.normal_um,
                    }
                    for site in shank.sites
                ],
            }
            for shank in model.shanks
        ]
    return base


def _model_warning(model: ProbeModelDefinition) -> str | None:
    """Return a status-specific warning without overstating source review."""

    if model.permits_verified_device_label:
        return None
    if model.verification.status is ProbeVerificationStatus.SOURCE_TRANSCRIBED_REVIEW_PENDING:
        return (
            "Source-transcribed manufacturer geometry — independent transcription review "
            "pending; explicit acknowledgement required"
        )
    return "Generic software-test geometry — not a verified Neuropixels device profile"


def _plan_summary(
    plan: ProbePlanRecord,
    analysis: ProbeRegionAnalysisBundle | None,
) -> JsonObject:
    return {
        "planId": str(plan.plan_uuid),
        "planVersion": plan.plan_version,
        "name": plan.name,
        "targetId": str(plan.source_target.target_uuid),
        "targetLabel": plan.source_target.label,
        "modelId": plan.probe_model.model_id,
        "modelVersion": plan.probe_model.model_version,
        "modelDisplayName": plan.probe_model.display_name,
        "verificationStatus": plan.probe_model.verification.status.value,
        "inputSha256": plan.input_sha256,
        "calibrationId": str(plan.calibration_uuid),
        "calibrationVersion": plan.calibration_version,
        "regionAnalysisAvailable": analysis is not None,
        "regionAnalysisSha256": None if analysis is None else analysis.analysis_sha256,
        "usableForNavigation": False,
    }


def _plan_detail(plan: ProbePlanRecord, atlas: AtlasMetadata | None) -> JsonObject:
    if atlas is None:
        raise ValueError("probe plan detail requires project atlas metadata")
    shanks = placed_shank_centerlines(plan.probe_model, plan.placement)
    sites = placed_recording_sites(plan.probe_model, plan.placement)
    return {
        **_plan_summary(plan, None),
        "sourceTarget": {
            "frameId": plan.source_target.frame_id,
            "origin": plan.source_target.origin,
            "componentOrder": list(plan.source_target.component_order),
            "units": plan.source_target.units,
            "apMillimetres": plan.source_target.ap_mm,
            "mlMillimetres": plan.source_target.ml_mm,
            "dvMillimetres": plan.source_target.dv_mm,
        },
        "placement": {
            "placementId": str(plan.placement.placement_uuid),
            "method": plan.placement.method.value,
            "azimuthDegrees": plan.placement.azimuth_deg,
            "elevationDegrees": plan.placement.elevation_deg,
            "insertionDepthMicrometres": plan.placement.insertion_depth_um,
            "axialRotationDegrees": plan.placement.axial_rotation_deg,
            "angleConvention": plan.placement.angle_convention,
            "canonicalFrame": {
                "frameId": plan.placement.entry.frame_id,
                "componentOrder": ["AP", "ML", "DV"],
                "units": "micrometre",
                "apPositiveDirection": "anterior",
                "mlPositiveDirection": "right",
                "dvPositiveDirection": "dorsal/up",
                "entry": _anatomical_point_payload(plan.placement.entry),
                "target": _anatomical_point_payload(plan.placement.target),
                "tip": _anatomical_point_payload(plan.placement.tip),
            },
            "atlasFrame": {
                "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
                "componentOrder": ["AP", "DV", "ML"],
                "units": "micrometre",
                "origin": "anterior/superior/right atlas corner",
                "entry": _physical_payload(plan.placement.entry, atlas),
                "target": _physical_payload(plan.placement.target, atlas),
                "tip": _physical_payload(plan.placement.tip, atlas),
            },
        },
        "shanks": [_shank_payload(shank, atlas) for shank in shanks],
        "recordingSites": [_site_payload(site, atlas) for site in sites],
        "provenance": {
            "calibrationId": str(plan.calibration_uuid),
            "calibrationVersion": plan.calibration_version,
            "calibrationSha256": plan.calibration_sha256,
            "atlasMetadataSha256": plan.atlas_metadata_sha256,
            "projectionSha256": plan.projection_sha256,
            "planningAlgorithmVersion": plan.planning_algorithm_version,
            "planInputSha256": plan.input_sha256,
            "catalogVersion": PROBE_CATALOG_VERSION,
        },
        "warning": (
            "Animal research planning only — generic geometry and atlas placement must be "
            "independently verified against the animal, probe, and rig"
        ),
        "usableForNavigation": False,
    }


def _anatomical_point_payload(point: AnatomicalPoint) -> JsonObject:
    return {
        "apMicrometres": point.ap_um,
        "mlMicrometres": point.ml_um,
        "dvMicrometres": point.dv_um,
    }


def _physical_payload(point: AnatomicalPoint, atlas: AtlasMetadata) -> JsonObject:
    physical = canonical_anatomical_to_brainglobe_physical(
        point,
        atlas,
        require_inside=False,
    )
    inside = True
    voxel: JsonObject | None
    try:
        index = BrainGlobeAtlasSpace(atlas).physical_to_index(physical)
        voxel = {"ap": index.ap, "dv": index.dv, "ml": index.ml}
    except CoordinateBoundsError:
        inside = False
        voxel = None
    return {
        "apMicrometres": physical.ap_um,
        "dvMicrometres": physical.dv_um,
        "mlMicrometres": physical.ml_um,
        "insideAtlas": inside,
        "voxelIndex": voxel,
    }


def _shank_payload(shank: PlacedProbeShank, atlas: AtlasMetadata) -> JsonObject:
    return {
        "shankId": shank.shank_id,
        "entry": _physical_payload(shank.entry, atlas),
        "tip": _physical_payload(shank.tip, atlas),
        "widthMicrometres": shank.width_um,
        "thicknessMicrometres": shank.thickness_um,
        "conservativeEnvelopeRadiusMicrometres": shank.conservative_envelope_radius_um,
        "envelopeDefinition": shank.envelope_definition,
    }


def _site_payload(site: PlacedRecordingSite, atlas: AtlasMetadata) -> JsonObject:
    return {
        "shankId": site.shank_id,
        "siteId": site.site_id,
        "role": site.role.value,
        "bank": site.bank,
        "point": _physical_payload(site.point, atlas),
    }


def _region_bundle_payload(bundle: ProbeRegionAnalysisBundle) -> JsonObject:
    return {
        "analysisId": str(bundle.analysis_uuid),
        "planId": str(bundle.plan_uuid),
        "planVersion": bundle.plan_version,
        "planInputSha256": bundle.plan_input_sha256,
        "algorithmVersion": bundle.algorithm_version,
        "analysisSha256": bundle.analysis_sha256,
        "computedAt": bundle.computed_at.isoformat(),
        "usableForNavigation": False,
        "shanks": [
            {
                "analysisId": str(analysis.analysis_uuid),
                "shankId": analysis.shank_id,
                "totalPathLengthMicrometres": analysis.total_path_length_um,
                "clippedPathLengthMicrometres": analysis.clipped_path_length_um,
                "outsideAtlasPathLengthMicrometres": analysis.outside_atlas_path_length_um,
                "intersectsAtlas": analysis.intersects_atlas,
                "segments": [
                    {
                        "structureId": segment.structure_id,
                        "acronym": segment.acronym,
                        "name": segment.name,
                        "hemisphere": segment.hemisphere.value,
                        "location": segment.location.value,
                        "entryDepthMicrometres": segment.entry_depth_um,
                        "exitDepthMicrometres": segment.exit_depth_um,
                        "lengthMicrometres": segment.length_um,
                        "entryPoint": _atlas_analysis_point_payload(segment.entry_point),
                        "exitPoint": _atlas_analysis_point_payload(segment.exit_point),
                        "voxelCount": segment.voxel_count,
                        "rgb": list(segment.rgb),
                    }
                    for segment in analysis.segments
                ],
                "recordingSiteAssignments": [
                    {
                        "siteId": assignment.site_id,
                        "structureId": assignment.structure_id,
                        "acronym": assignment.acronym,
                        "name": assignment.name,
                        "location": assignment.location.value,
                        "insideAtlas": assignment.inside_atlas,
                        "insideBrain": assignment.inside_brain,
                        "point": _atlas_analysis_point_payload(assignment.point),
                        "voxelIndex": (
                            None
                            if assignment.voxel is None
                            else {
                                "ap": assignment.voxel.ap,
                                "dv": assignment.voxel.dv,
                                "ml": assignment.voxel.ml,
                            }
                        ),
                    }
                    for assignment in analysis.site_assignments
                ],
                "provenance": {
                    "atlasIdentifier": analysis.atlas_key,
                    "atlasVersion": analysis.atlas_version,
                    "atlasMetadataSha256": analysis.atlas_metadata_sha256,
                    "annotationSha256": analysis.annotation_sha256,
                    "annotationVersion": analysis.annotation_version,
                    "algorithmVersion": analysis.algorithm_version,
                    "inputDigest": analysis.input_digest,
                    "tieBreakRule": analysis.tie_break_rule,
                },
            }
            for analysis in bundle.shank_analyses
        ],
    }


def _atlas_analysis_point_payload(point: AtlasPhysicalPointAPMLDV) -> JsonObject:
    return {
        "frameId": point.frame_id,
        "componentOrder": list(point.component_order),
        "units": point.units,
        "apMicrometres": point.ap_um,
        "mlMicrometres": point.ml_um,
        "dvMicrometres": point.dv_um,
    }


def _region_csv(plan: ProbePlanRecord, bundle: ProbeRegionAnalysisBundle) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "record_type",
            "plan_id",
            "plan_version",
            "plan_input_sha256",
            "analysis_sha256",
            "shank_id",
            "site_id",
            "structure_id",
            "acronym",
            "name",
            "entry_depth_um",
            "exit_depth_um",
            "length_um",
            "location",
            "hemisphere",
            "inside_atlas",
            "inside_brain",
        ]
    )
    common = [
        str(plan.plan_uuid),
        plan.plan_version,
        plan.input_sha256,
        bundle.analysis_sha256,
    ]
    for analysis in bundle.shank_analyses:
        for segment in analysis.segments:
            writer.writerow(
                [
                    "region_segment",
                    *common,
                    analysis.shank_id,
                    "",
                    segment.structure_id,
                    segment.acronym,
                    segment.name,
                    segment.entry_depth_um,
                    segment.exit_depth_um,
                    segment.length_um,
                    segment.location.value,
                    segment.hemisphere.value,
                    True,
                    segment.structure_id > 0,
                ]
            )
        for assignment in analysis.site_assignments:
            writer.writerow(
                [
                    "recording_site",
                    *common,
                    analysis.shank_id,
                    assignment.site_id,
                    assignment.structure_id,
                    assignment.acronym,
                    assignment.name,
                    "",
                    "",
                    "",
                    assignment.location.value,
                    "",
                    assignment.inside_atlas,
                    assignment.inside_brain,
                ]
            )
    return stream.getvalue()
