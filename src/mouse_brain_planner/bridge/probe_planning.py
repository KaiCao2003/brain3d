"""Strict probe-catalog, placement, and exact region-analysis bridge methods."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
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
    ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION,
    PROBE_PLANNING_ALGORITHM_VERSION,
    STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION,
    ProbePlacementMode,
    ProbePlanRecord,
    ProbeRegionAnalysisBundle,
)
from mouse_brain_planner.domain.project_models import MAX_PROBE_PLANS, PlannerProject
from mouse_brain_planner.domain.region_models import AtlasPhysicalPointAPMLDV
from mouse_brain_planner.domain.stereotaxy_models import (
    AtlasRegisteredCalibration,
    atlas_registered_calibration_sha256,
)
from mouse_brain_planner.domain.transform_models import AnatomicalPoint
from mouse_brain_planner.probes.catalog import (
    PROBE_CATALOG_VERSION,
    get_supported_probe_model,
    list_probe_models,
)
from mouse_brain_planner.surgery.probe_planning import (
    ProbePlanningError,
    build_atlas_surface_probe_plan,
    build_calibrated_probe_plan,
    validate_atlas_surface_probe_plan_semantics,
)
from mouse_brain_planner.surgery.trajectory import (
    ProbePlacementError,
    placed_recording_sites,
    placed_shank_centerlines,
    placement_cross_section_axes,
)

MAX_EXPORT_CHARACTERS: Final = 4 * 1024 * 1024
REGION_EXPORT_SCHEMA_VERSION: Final = 2
MAX_SUBJECT_FILENAME_COMPONENT_CHARACTERS: Final = 64

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
        self.dispatcher.register("probe.region.export.confirm", self.region_export_confirm)
        self.dispatcher.declare_capability("probeCatalog")
        self.dispatcher.declare_capability("calibratedProbePlanning")
        self.dispatcher.declare_capability("atlasSurfaceProbePlanning")
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
        project_revision = self.get_revision()
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "found",
            "projectId": str(project.project_uuid),
            "projectRevision": project_revision,
            "plan": _plan_detail(plan, project.atlas),
            "regionAnalysis": (None if analysis is None else _region_bundle_payload(analysis)),
            # Legacy bundles stay in the project for byte-preserving audit/history,
            # but the current source failed coordinate qualification. Never revive
            # a stale result through the product protocol while geometry is gated.
            "majorVesselAnalysis": None,
        }

    def plan_create(self, params: Mapping[str, object]) -> JsonObject:
        _validate_plan_mutation_params(params, updating=False)
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
        _validate_plan_mutation_params(params, updating=True)
        require_protocol(params)
        project = self._validated_mutation_project(params)
        existing = _find_plan(project, params["planId"])
        _require_plan_hash(existing, params["expectedPlanInputSha256"])
        region_analysis_cleared = any(
            item.plan_uuid == existing.plan_uuid for item in project.probe_region_analyses
        )
        vessel_analysis_cleared = any(
            item.plan_uuid == existing.plan_uuid for item in project.probe_vessel_analyses
        )
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
            probe_vessel_analyses=[
                item
                for item in project.probe_vessel_analyses
                if item.plan_uuid != existing.plan_uuid
            ],
        )
        updated.touch(
            "probe-plan-updated",
            f"plan={plan.plan_uuid}; version={plan.plan_version}; "
            f"inputSha256={plan.input_sha256}; "
            f"regionAnalysisCleared={str(region_analysis_cleared).lower()}; "
            f"majorVesselAnalysisCleared={str(vessel_analysis_cleared).lower()}",
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
        vessel_analysis_removed = any(
            item.plan_uuid == plan.plan_uuid for item in project.probe_vessel_analyses
        )
        updated = _project_update(
            project,
            probe_plans=[item for item in project.probe_plans if item.plan_uuid != plan.plan_uuid],
            probe_region_analyses=[
                item for item in project.probe_region_analyses if item.plan_uuid != plan.plan_uuid
            ],
            probe_vessel_analyses=[
                item for item in project.probe_vessel_analyses if item.plan_uuid != plan.plan_uuid
            ],
        )
        updated.touch(
            "probe-plan-removed",
            f"plan={plan.plan_uuid}; regionAnalysisRemoved={str(analysis_removed).lower()}; "
            f"majorVesselAnalysisRemoved={str(vessel_analysis_removed).lower()}",
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
        _require_current_probe_geometry(plan)
        _require_plan_projection_semantics(project, plan)
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
            if plan.planning_algorithm_version == ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION:
                validate_atlas_surface_probe_plan_semantics(
                    plan=plan,
                    atlas=atlas.metadata,
                    annotation=annotation,
                    annotation_sha256=annotation_sha256,
                )
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
                "expectedProjectRevision",
                "planId",
                "expectedPlanInputSha256",
                "format",
            },
        )
        require_protocol(params)
        project = self._validated_mutation_project(params)
        plan = _find_plan(project, params["planId"])
        _require_plan_hash(plan, params["expectedPlanInputSha256"])
        analysis = _find_analysis(project, plan.plan_uuid, required=True)
        assert analysis is not None
        export_format, content, mime_type, file_extension = _region_export_content(
            project,
            plan,
            analysis,
            params["format"],
        )
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "generated",
            "projectId": str(project.project_uuid),
            "projectRevision": self.get_revision(),
            "planId": str(plan.plan_uuid),
            "planInputSha256": plan.input_sha256,
            "analysisSha256": analysis.analysis_sha256,
            "format": export_format,
            "mimeType": mime_type,
            "suggestedFileName": _region_export_filename(
                project,
                plan,
                file_extension=file_extension,
            ),
            "content": content,
            "contentSha256": content_sha256,
            "projectMutated": False,
        }

    def region_export_confirm(self, params: Mapping[str, object]) -> JsonObject:
        """Record a completed client-side atomic write, never an attempted export."""

        validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "planId",
                "expectedPlanInputSha256",
                "analysisSha256",
                "format",
                "contentSha256",
            },
        )
        require_protocol(params)
        project = self._validated_mutation_project(params)
        plan = _find_plan(project, params["planId"])
        _require_plan_hash(plan, params["expectedPlanInputSha256"])
        analysis = _find_analysis(project, plan.plan_uuid, required=True)
        assert analysis is not None
        expected_analysis_sha256 = sha256_value(params["analysisSha256"], "analysisSha256")
        if expected_analysis_sha256 != analysis.analysis_sha256:
            raise BridgeError(
                "ANALYSIS_STALE",
                "The saved export refers to an older probe-region analysis.",
                details={"actualAnalysisSha256": analysis.analysis_sha256},
            )
        export_format, content, _mime_type, _file_extension = _region_export_content(
            project,
            plan,
            analysis,
            params["format"],
        )
        actual_content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        expected_content_sha256 = sha256_value(params["contentSha256"], "contentSha256")
        if expected_content_sha256 != actual_content_sha256:
            raise BridgeError(
                "EXPORT_CONTENT_MISMATCH",
                "The saved export digest does not match the current exact analysis export.",
                details={"actualContentSha256": actual_content_sha256},
            )
        updated = project.model_copy(deep=True)
        updated.touch(
            "probe-region-analysis-exported",
            json.dumps(
                {
                    "analysisSha256": analysis.analysis_sha256,
                    "contentSha256": actual_content_sha256,
                    "format": export_format,
                    "planId": str(plan.plan_uuid),
                    "planInputSha256": plan.input_sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        return self._publish(
            updated,
            status="exported",
            extra={
                "planId": str(plan.plan_uuid),
                "planInputSha256": plan.input_sha256,
                "analysisSha256": analysis.analysis_sha256,
                "format": export_format,
                "contentSha256": actual_content_sha256,
                "projectMutated": True,
            },
        )

    def _validated_project(self, raw_project_id: object) -> PlannerProject:
        project = self.get_project()
        project_id = uuid_value(raw_project_id, "projectId")
        if project_id != project.project_uuid:
            raise BridgeError(
                "PROJECT_ID_MISMATCH",
                "The probe request does not belong to the current project.",
            )
        self._validate_loaded_surface_geometry(project)
        return project

    def _validate_loaded_surface_geometry(self, project: PlannerProject) -> None:
        surface_plans = tuple(
            plan
            for plan in project.probe_plans
            if (plan.planning_algorithm_version == ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION)
        )
        if not surface_plans:
            return
        loaded_atlas = self.get_atlas()
        if (
            project.atlas is None
            or loaded_atlas.metadata.metadata_sha256 != project.atlas.metadata_sha256
        ):
            raise BridgeError(
                "ATLAS_IDENTITY_MISMATCH",
                "The loaded annotation does not match the project atlas-surface plan.",
            )
        annotation = np.asarray(loaded_atlas.annotation)
        try:
            for plan in surface_plans:
                input_data = plan.surface_relative_input
                if input_data is None:  # guarded by the record model
                    raise ProbePlanningError(
                        "atlas-surface plan is missing preserved direct inputs"
                    )
                validate_atlas_surface_probe_plan_semantics(
                    plan=plan,
                    atlas=loaded_atlas.metadata,
                    annotation=annotation,
                    # Re-resolving the AP/ML column catches forged surface DV
                    # without hashing the full immutable volume on every list/get.
                    annotation_sha256=input_data.annotation_sha256,
                )
        except (ProbePlacementError, ProbePlanningError, ValidationError, ValueError) as error:
            raise BridgeError(
                "PROBE_PLAN_SURFACE_INVALID",
                "The persisted probe surface cannot be reproduced from the loaded annotation.",
                details={"reason": str(error), "exceptionType": type(error).__name__},
            ) from error

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
        model = _catalog_model(params)
        placement_mode = _placement_mode(params)
        if placement_mode is ProbePlacementMode.ATLAS_SURFACE_AP_ML:
            loaded_atlas = self.get_atlas()
            if loaded_atlas.metadata.metadata_sha256 != project.atlas.metadata_sha256:
                raise BridgeError(
                    "ATLAS_IDENTITY_MISMATCH",
                    "The loaded annotation does not match the project atlas.",
                )
            annotation_source = loaded_atlas.metadata.source_annotation
            if annotation_source is None or not annotation_source.strip():
                raise BridgeError(
                    "ATLAS_ANNOTATION_PROVENANCE_MISSING",
                    "Direct surface planning requires a source-versioned annotation.",
                )
            annotation = np.asarray(loaded_atlas.annotation)
            annotation_sha256 = self._annotation_digest(annotation, loaded_atlas.metadata)
            existing_context = None
            if plan_uuid is not None:
                existing = next(
                    (item for item in project.probe_plans if item.plan_uuid == plan_uuid),
                    None,
                )
                if (
                    existing is not None
                    and existing.planning_algorithm_version
                    == ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION
                ):
                    existing_context = existing.placement.context
            raw_name = params.get("name")
            name = None if raw_name is None else text_value(raw_name, "name", maximum=200)
            layout_rotation = finite_number(
                params["probeLayoutRotationDegrees"],
                "probeLayoutRotationDegrees",
                minimum=0,
                maximum=90,
            )
            if layout_rotation not in {0.0, 90.0}:
                raise BridgeError(
                    "INVALID_PARAMS",
                    "probeLayoutRotationDegrees must be exactly 0 or 90.",
                )
            try:
                plan, _ = build_atlas_surface_probe_plan(
                    annotation=annotation,
                    annotation_sha256=annotation_sha256,
                    annotation_source=annotation_source,
                    atlas=project.atlas,
                    model=model,
                    insertion_ap_mm=finite_number(
                        params["insertionAPMillimetres"],
                        "insertionAPMillimetres",
                    ),
                    insertion_ml_mm=finite_number(
                        params["insertionMLMillimetres"],
                        "insertionMLMillimetres",
                    ),
                    surface_depth_mm=finite_number(
                        params["surfaceDepthMillimetres"],
                        "surfaceDepthMillimetres",
                        minimum=0,
                        minimum_inclusive=False,
                    ),
                    sagittal_angle_deg=_strict_sagittal_angle(params["sagittalAngleDegrees"]),
                    probe_layout_rotation_deg=int(layout_rotation),
                    subject_id=project.subject_id,
                    name=name,
                    context=existing_context,
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
                    "The atlas-surface probe placement was rejected.",
                    details={"reason": str(error), "exceptionType": type(error).__name__},
                ) from error
            return plan
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
        try:
            plan, _ = build_calibrated_probe_plan(
                target=target,
                calibration=calibration,
                atlas=project.atlas,
                model=model,
                name=text_value(params["name"], "name", maximum=200),
                azimuth_deg=_optional_finite_number(
                    params,
                    "azimuthDegrees",
                    "azimuthDegrees",
                    minimum=-180,
                    maximum=180,
                ),
                elevation_deg=_optional_finite_number(
                    params,
                    "elevationDegrees",
                    "elevationDegrees",
                    minimum=-90,
                    maximum=90,
                ),
                insertion_depth_um=_optional_finite_number(
                    params,
                    "insertionDepthMicrometres",
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
                placement_mode=placement_mode,
                entry_ap_mm=_optional_finite_number(
                    params,
                    "entryAPMillimetres",
                    "entryAPMillimetres",
                ),
                entry_ml_mm=_optional_finite_number(
                    params,
                    "entryMLMillimetres",
                    "entryMLMillimetres",
                ),
                entry_dv_mm=_optional_finite_number(
                    params,
                    "entryDVMillimetres",
                    "entryDVMillimetres",
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
        del metadata
        # Content provenance must describe the exact array analyzed. Shape,
        # dtype, and atlas metadata cannot detect replacement or in-place
        # mutation, so a cached digest would let changed labels inherit an old
        # scientific hash. Correctness takes priority over avoiding this
        # bounded sequential read.
        return annotation_array_sha256(annotation)

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


_PLAN_LEGACY_COMMON_INPUT_FIELDS: Final[set[str]] = {
    "targetId",
    "modelId",
    "modelVersion",
    "name",
    "axialRotationDegrees",
    "customGeometryAcknowledged",
}

_PLAN_LEGACY_MODE_INPUT_FIELDS: Final[set[str]] = {
    "placementMode",
    "entryAPMillimetres",
    "entryMLMillimetres",
    "entryDVMillimetres",
    "azimuthDegrees",
    "elevationDegrees",
    "insertionDepthMicrometres",
}

_PLAN_SURFACE_INPUT_FIELDS: Final[set[str]] = {
    "placementMode",
    "modelId",
    "modelVersion",
    "insertionAPMillimetres",
    "insertionMLMillimetres",
    "surfaceDepthMillimetres",
    "sagittalAngleDegrees",
    "probeLayoutRotationDegrees",
}


def _validate_plan_mutation_params(
    params: Mapping[str, object],
    *,
    updating: bool,
) -> None:
    """Apply one strict field shape for v4 and preserve the legacy shape."""

    mutation_envelope = {
        "protocolVersion",
        "projectId",
        "expectedProjectRevision",
    }
    if updating:
        mutation_envelope |= {"planId", "expectedPlanInputSha256"}
    raw_mode = params.get("placementMode")
    if raw_mode == ProbePlacementMode.ATLAS_SURFACE_AP_ML.value:
        validate_params(
            params,
            required=mutation_envelope | _PLAN_SURFACE_INPUT_FIELDS,
            optional={"name"},
        )
        return
    validate_params(
        params,
        required=mutation_envelope | _PLAN_LEGACY_COMMON_INPUT_FIELDS,
        optional=_PLAN_LEGACY_MODE_INPUT_FIELDS,
    )


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


def _placement_mode(params: Mapping[str, object]) -> ProbePlacementMode:
    raw = params.get(
        "placementMode",
        ProbePlacementMode.STEREOTAXIC_TARGET_MANIPULATOR.value,
    )
    value = text_value(raw, "placementMode", maximum=50)
    try:
        return ProbePlacementMode(value)
    except ValueError as error:
        raise BridgeError(
            "INVALID_PARAMS",
            "placementMode must be one of the explicit supported modes.",
            details={
                "received": value,
                "supported": [mode.value for mode in ProbePlacementMode],
            },
        ) from error


def _optional_finite_number(
    params: Mapping[str, object],
    key: str,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_inclusive: bool = True,
) -> float | None:
    if key not in params:
        return None
    return finite_number(
        params[key],
        field,
        minimum=minimum,
        maximum=maximum,
        minimum_inclusive=minimum_inclusive,
    )


def _strict_sagittal_angle(value: object) -> float:
    angle = finite_number(
        value,
        "sagittalAngleDegrees",
        minimum=-90,
        maximum=90,
    )
    if not -90 < angle < 90:
        raise BridgeError(
            "INVALID_PARAMS",
            "sagittalAngleDegrees must be strictly between -90 and 90.",
        )
    return angle


def _catalog_model(params: Mapping[str, object]) -> ProbeModelDefinition:
    model_id = text_value(params["modelId"], "modelId", maximum=200)
    model_version = text_value(params["modelVersion"], "modelVersion", maximum=100)
    try:
        return get_supported_probe_model(model_id, model_version)
    except KeyError as error:
        raise BridgeError(
            "PROBE_MODEL_NOT_FOUND",
            "The exact probe model identity is not in the supported production catalog.",
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


def _require_current_probe_geometry(plan: ProbePlanRecord) -> None:
    if plan.planning_algorithm_version not in {
        STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION,
        PROBE_PLANNING_ALGORITHM_VERSION,
        ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION,
    }:
        raise BridgeError(
            "PROBE_PLAN_RECOMPUTE_REQUIRED",
            "This legacy probe plan must be updated through its subject calibration "
            "before analysis.",
            details={
                "planId": str(plan.plan_uuid),
                "planningAlgorithmVersion": plan.planning_algorithm_version,
                "requiredPlanningAlgorithmVersion": PROBE_PLANNING_ALGORITHM_VERSION,
            },
        )


def _require_plan_projection_semantics(
    project: PlannerProject,
    plan: ProbePlanRecord,
) -> None:
    try:
        project.validate_probe_plan_projection_semantics(plan)
    except ValueError as error:
        raise BridgeError(
            "PROBE_PLAN_PROJECTION_INVALID",
            "The probe plan target cannot be reproduced from its project target and calibration.",
            details={"reason": str(error), "exceptionType": type(error).__name__},
        ) from error


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
            "pending; verify the source-traced geometry before animal use"
        )
    return "Generic software-test geometry — not a verified Neuropixels device profile"


def _plan_summary(
    plan: ProbePlanRecord,
    analysis: ProbeRegionAnalysisBundle | None,
) -> JsonObject:
    source_target = plan.source_target
    return {
        "planId": str(plan.plan_uuid),
        "planVersion": plan.plan_version,
        "name": plan.name,
        "targetId": None if source_target is None else str(source_target.target_uuid),
        "targetLabel": None if source_target is None else source_target.label,
        "modelId": plan.probe_model.model_id,
        "modelVersion": plan.probe_model.model_version,
        "modelDisplayName": plan.probe_model.display_name,
        "verificationStatus": plan.probe_model.verification.status.value,
        "placementMode": (
            ProbePlacementMode.ATLAS_SURFACE_AP_ML.value
            if plan.surface_relative_input is not None
            else (
                plan.placement_input.mode.value
                if plan.placement_input is not None
                else (
                    ProbePlacementMode.STEREOTAXIC_TARGET_MANIPULATOR.value
                    if (
                        plan.planning_algorithm_version
                        == STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION
                    )
                    else ProbePlacementMode.TARGET_ANGLES_DEPTH.value
                )
            )
        ),
        "inputSha256": plan.input_sha256,
        "calibrationId": (None if plan.calibration_uuid is None else str(plan.calibration_uuid)),
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
    lateral_direction, normal_direction = placement_cross_section_axes(plan.placement)
    direction_frame_id = plan.placement.entry.frame_id
    return {
        **_plan_summary(plan, None),
        "sourceTarget": (
            None
            if plan.source_target is None
            else {
                "frameId": plan.source_target.frame_id,
                "origin": plan.source_target.origin,
                "componentOrder": list(plan.source_target.component_order),
                "units": plan.source_target.units,
                "apMillimetres": plan.source_target.ap_mm,
                "mlMillimetres": plan.source_target.ml_mm,
                "dvMillimetres": plan.source_target.dv_mm,
            }
        ),
        "manipulatorInput": (
            None
            if plan.manipulator_input is None
            else {
                "frameId": plan.manipulator_input.frame_id,
                "azimuthDegrees": plan.manipulator_input.azimuth_deg,
                "elevationDegrees": plan.manipulator_input.elevation_deg,
                "insertionDepthMicrometres": plan.manipulator_input.insertion_depth_um,
                "axialRotationDegrees": plan.manipulator_input.axial_rotation_deg,
                "angleConvention": plan.manipulator_input.angle_convention,
            }
        ),
        "placementInput": _placement_input_payload(plan),
        "surfaceRelativeInput": _surface_relative_input_payload(plan),
        "placement": {
            "placementId": str(plan.placement.placement_uuid),
            "method": plan.placement.method.value,
            "azimuthDegrees": plan.placement.azimuth_deg,
            "elevationDegrees": plan.placement.elevation_deg,
            "insertionDepthMicrometres": plan.placement.insertion_depth_um,
            "axialRotationDegrees": plan.placement.axial_rotation_deg,
            "angleConvention": plan.placement.angle_convention,
            "inwardDirection": _direction_payload(
                direction_frame_id,
                plan.placement.inward_direction.as_ap_ml_dv(),
            ),
            "localLateralDirection": _direction_payload(
                direction_frame_id,
                (
                    float(lateral_direction[0]),
                    float(lateral_direction[1]),
                    float(lateral_direction[2]),
                ),
            ),
            "localNormalDirection": _direction_payload(
                direction_frame_id,
                (
                    float(normal_direction[0]),
                    float(normal_direction[1]),
                    float(normal_direction[2]),
                ),
            ),
            "modelToPlacementUniformScale": (plan.placement.model_to_placement_uniform_scale),
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
            "calibrationId": (
                None if plan.calibration_uuid is None else str(plan.calibration_uuid)
            ),
            "calibrationVersion": plan.calibration_version,
            "calibrationSha256": plan.calibration_sha256,
            "atlasMetadataSha256": plan.atlas_metadata_sha256,
            "projectionSha256": plan.projection_sha256,
            "planningAlgorithmVersion": plan.planning_algorithm_version,
            "planInputSha256": plan.input_sha256,
            "catalogVersion": PROBE_CATALOG_VERSION,
        },
        "warning": (
            "Animal research planning only — probe geometry and atlas placement must be "
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


def _direction_payload(
    frame_id: str,
    components: tuple[float, float, float],
) -> JsonObject:
    """Serialize an AP/ML/DV unit vector without leaving frame or unit implicit."""

    ap, ml, dv = components
    return {
        "frameId": frame_id,
        "componentOrder": ["AP", "ML", "DV"],
        "units": "dimensionless",
        "ap": ap,
        "ml": ml,
        "dv": dv,
    }


def _placement_input_payload(plan: ProbePlanRecord) -> JsonObject | None:
    placement_input = plan.placement_input
    if placement_input is None:
        return None
    entry = placement_input.entry
    return {
        "mode": placement_input.mode.value,
        "entry": (
            None
            if entry is None
            else {
                "frameId": entry.frame_id,
                "origin": entry.origin,
                "componentOrder": list(entry.component_order),
                "units": entry.units,
                "apPositiveDirection": entry.ap_positive_direction,
                "apNegativeDirection": entry.ap_negative_direction,
                "mlPositiveDirection": entry.ml_positive_direction,
                "mlNegativeDirection": entry.ml_negative_direction,
                "dvPositiveDirection": entry.dv_positive_direction,
                "dvNegativeDirection": entry.dv_negative_direction,
                "apMillimetres": entry.ap_mm,
                "mlMillimetres": entry.ml_mm,
                "dvMillimetres": entry.dv_mm,
            }
        ),
        "angleFrameId": placement_input.angle_frame_id,
        "azimuthDegrees": placement_input.azimuth_deg,
        "elevationDegrees": placement_input.elevation_deg,
        "insertionDepthMicrometres": placement_input.insertion_depth_um,
        "axialRotationDegrees": placement_input.axial_rotation_deg,
        "angleConvention": placement_input.angle_convention,
    }


def _surface_relative_input_payload(plan: ProbePlanRecord) -> JsonObject | None:
    input_data = plan.surface_relative_input
    if input_data is None:
        return None
    reference = input_data.bregma_reference
    surface = input_data.surface_entry_physical
    return {
        "mode": input_data.mode,
        "bregmaReference": {
            "referenceId": reference.reference_id,
            "atlasIdentifier": reference.atlas_key,
            "atlasVersion": reference.atlas_version,
            "frameId": reference.frame_id,
            "componentOrder": list(reference.component_order),
            "units": reference.units,
            "apMicrometres": reference.ap_um,
            "dvMicrometres": reference.dv_um,
            "mlMicrometres": reference.ml_um,
            "sourceTitle": reference.source_title,
            "sourceUrl": reference.source_url,
            "sourceRevision": reference.source_revision,
            "sourceSha256": reference.source_sha256,
            "retrievedOn": reference.retrieved_on.isoformat(),
            "limitation": reference.limitation,
        },
        "insertionAPMillimetres": input_data.insertion_ap_mm,
        "insertionMLMillimetres": input_data.insertion_ml_mm,
        "surfaceDepthMillimetres": input_data.surface_depth_mm,
        "sagittalAngleDegrees": input_data.sagittal_angle_deg,
        "probeLayoutRotationDegrees": input_data.probe_layout_rotation_deg,
        "surfaceEntry": {
            "atlasIdentifier": surface.atlas_key,
            "atlasVersion": surface.atlas_version,
            "frameId": surface.frame_id,
            "componentOrder": ["AP", "DV", "ML"],
            "units": "micrometre",
            "apMicrometres": surface.ap_um,
            "dvMicrometres": surface.dv_um,
            "mlMicrometres": surface.ml_um,
        },
        "surfaceDVIndex": input_data.surface_dv_index,
        "surfaceDVResolutionMicrometres": input_data.surface_dv_resolution_um,
        "annotationSource": input_data.annotation_source,
        "annotationSha256": input_data.annotation_sha256,
        "surfaceDefinitionVersion": input_data.surface_definition_version,
        "apSignConvention": input_data.ap_sign_convention,
        "mlSignConvention": input_data.ml_sign_convention,
        "depthConvention": input_data.depth_convention,
        "angleConvention": input_data.angle_convention,
        "layoutConvention": input_data.layout_convention,
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
        # ``entry`` is retained as the implanted-path start for protocol
        # compatibility.  The explicit role and proximal endpoint prevent 2-D
        # and 3-D consumers from treating insertion depth as physical length.
        "entry": _physical_payload(shank.entry, atlas),
        "surfaceEntry": _physical_payload(shank.entry, atlas),
        "tip": _physical_payload(shank.tip, atlas),
        "proximalEnd": _physical_payload(shank.proximal_end, atlas),
        "totalLengthMicrometres": shank.length_um,
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


def _region_export_filename(
    project: PlannerProject,
    plan: ProbePlanRecord,
    *,
    file_extension: str,
) -> str:
    """Return a bounded filename with a filesystem-safe animal identifier."""

    subject_component = _safe_subject_filename_component(
        project.subject_id,
        fallback_seed=str(project.project_uuid),
    )
    return f"probe-regions-{subject_component}-{plan.plan_uuid}.{file_extension}"


def _safe_subject_filename_component(subject_id: str | None, *, fallback_seed: str) -> str:
    """Preserve safe ASCII IDs and digest-bind any lossy filename normalization."""

    raw = "" if subject_id is None else subject_id.strip()
    digest_seed = raw or fallback_seed
    digest = hashlib.sha256(digest_seed.encode("utf-8")).hexdigest()[:12]
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", raw)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-_")
    if not normalized:
        return f"subject-{digest}"
    if normalized == raw and len(normalized) <= MAX_SUBJECT_FILENAME_COMPONENT_CHARACTERS:
        return normalized
    prefix = normalized[: MAX_SUBJECT_FILENAME_COMPONENT_CHARACTERS - len(digest) - 1]
    prefix = prefix.rstrip("-_")
    if not prefix:
        return f"subject-{digest}"
    return f"{prefix}-{digest}"


def _region_csv(
    project: PlannerProject,
    calibration: AtlasRegisteredCalibration | None,
    plan: ProbePlanRecord,
    bundle: ProbeRegionAnalysisBundle,
) -> str:
    if project.atlas is None:
        raise BridgeError("ATLAS_NOT_OPEN", "Probe-region export requires project atlas metadata.")
    if calibration is None:
        surface_input = plan.surface_relative_input
        if surface_input is None:
            raise BridgeError(
                "CALIBRATION_REQUIRED",
                "Legacy probe-region export requires its exact calibration.",
            )
        transform_matrix = json.dumps(
            [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            separators=(",", ":"),
            allow_nan=False,
        )
        calibration_columns: list[object] = [
            "",
            "",
            "",
            f"atlas-surface:{surface_input.bregma_reference.reference_id}",
            1,
            "direct-atlas-reference",
            "BRAINGLOBE_PHYSICAL_ASR_UM",
            plan.placement.entry.frame_id,
            transform_matrix,
            "",
            "",
        ]
    else:
        transform = calibration.atlas_transform
        transform_matrix = json.dumps(
            list(transform.matrix_row_major),
            separators=(",", ":"),
            allow_nan=False,
        )
        calibration_columns = [
            str(calibration.calibration_uuid),
            calibration.calibration_version,
            plan.calibration_sha256 or "",
            str(transform.transform_uuid),
            transform.version,
            transform.method.value,
            transform.source_frame.frame_id,
            transform.destination_frame.frame_id,
            transform_matrix,
            transform.rms_residual_um,
            transform.max_residual_um,
        ]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "record_type",
            "export_schema_version",
            "project_id",
            "project_title",
            "subject_id",
            "plan_id",
            "plan_version",
            "plan_input_sha256",
            "analysis_sha256",
            "atlas_identifier",
            "atlas_version",
            "atlas_metadata_sha256",
            "coordinate_convention",
            "calibration_id",
            "calibration_version",
            "calibration_sha256",
            "transform_id",
            "transform_version",
            "transform_method",
            "transform_source_frame_id",
            "transform_destination_frame_id",
            "transform_matrix_row_major_ap_ml_dv",
            "transform_rms_residual_um",
            "transform_max_residual_um",
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
        REGION_EXPORT_SCHEMA_VERSION,
        str(project.project_uuid),
        project.title,
        project.subject_id or "",
        str(plan.plan_uuid),
        plan.plan_version,
        plan.input_sha256,
        bundle.analysis_sha256,
        project.atlas.atlas_key,
        project.atlas.atlas_package_version,
        project.atlas.metadata_sha256,
        project.coordinate_convention,
        *calibration_columns,
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


def _region_export_content(
    project: PlannerProject,
    plan: ProbePlanRecord,
    analysis: ProbeRegionAnalysisBundle,
    raw_format: object,
) -> tuple[str, str, str, str]:
    """Build the exact bounded export bytes used by generation and confirmation."""

    if project.atlas is None:
        raise BridgeError("ATLAS_NOT_OPEN", "Probe-region export requires project atlas metadata.")
    calibration: AtlasRegisteredCalibration | None
    if plan.planning_algorithm_version == ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION:
        calibration = None
    else:
        if plan.calibration_uuid is None:
            raise BridgeError(
                "CALIBRATION_REQUIRED",
                "Legacy probe-region export requires its exact calibration.",
            )
        calibration = _find_calibration(project, plan.calibration_uuid)
        actual_calibration_sha256 = atlas_registered_calibration_sha256(calibration)
        if plan.calibration_sha256 != actual_calibration_sha256:
            raise BridgeError(
                "CALIBRATION_DIGEST_MISMATCH",
                "The probe plan no longer matches its exact animal calibration snapshot.",
                details={
                    "actualCalibrationSha256": actual_calibration_sha256,
                    "planCalibrationSha256": plan.calibration_sha256,
                },
            )
        if not calibration.permits_final_export:
            raise BridgeError(
                "CALIBRATION_FINAL_EXPORT_BLOCKED",
                "The exact animal calibration referenced by this probe plan does not permit "
                "final export.",
                details={
                    "calibrationId": str(calibration.calibration_uuid),
                    "calibrationSha256": actual_calibration_sha256,
                    "quality": calibration.effective_quality.value,
                    "transformMethod": calibration.atlas_transform.method.value,
                    "affineDistortionAcknowledged": (
                        calibration.atlas_transform.affine_distortion_acknowledged
                    ),
                    "permitsFinalExport": False,
                },
            )
    _require_plan_projection_semantics(project, plan)
    export_format = text_value(raw_format, "format", maximum=10).lower()
    if export_format == "csv":
        content = _region_csv(project, calibration, plan, analysis)
        mime_type = "text/csv"
        file_extension = "csv"
    elif export_format == "json":
        calibration_payload: JsonObject | None
        if calibration is None:
            calibration_payload = None
        else:
            transform = calibration.atlas_transform
            calibration_payload = {
                "calibrationId": str(calibration.calibration_uuid),
                "calibrationSha256": plan.calibration_sha256,
                "calibrationVersion": calibration.calibration_version,
                "profileId": calibration.profile_id,
                "transform": {
                    "destinationFrame": transform.destination_frame.model_dump(mode="json"),
                    "matrixRowMajorAPMLDV": list(transform.matrix_row_major),
                    "maximumResidualMicrometres": transform.max_residual_um,
                    "method": transform.method.value,
                    "rmsResidualMicrometres": transform.rms_residual_um,
                    "sourceFrame": transform.source_frame.model_dump(mode="json"),
                    "transformId": str(transform.transform_uuid),
                    "transformVersion": transform.version,
                },
            }
        content = json.dumps(
            {
                "analysis": analysis.model_dump(mode="json"),
                "atlas": {
                    "identifier": project.atlas.atlas_key,
                    "metadataSha256": project.atlas.metadata_sha256,
                    "version": project.atlas.atlas_package_version,
                },
                "calibration": calibration_payload,
                "atlasSurfaceReference": (
                    None
                    if plan.surface_relative_input is None
                    else plan.surface_relative_input.model_dump(mode="json")
                ),
                "coordinateConvention": project.coordinate_convention,
                "exportKind": "probe-region-analysis",
                "exportSchemaVersion": REGION_EXPORT_SCHEMA_VERSION,
                "project": {
                    "projectId": str(project.project_uuid),
                    "subjectId": project.subject_id,
                    "title": project.title,
                },
                "probePlan": {
                    "planId": str(plan.plan_uuid),
                    "planInputSha256": plan.input_sha256,
                    "planVersion": plan.plan_version,
                    "sourceTarget": (
                        None
                        if plan.source_target is None
                        else plan.source_target.model_dump(mode="json")
                    ),
                },
            },
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
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
    return export_format, content, mime_type, file_extension
