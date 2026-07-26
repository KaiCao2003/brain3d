"""Display-only VesSAP major-vessel bridge with fail-closed safety analysis."""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final, NoReturn
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from pydantic import ValidationError

from mouse_brain_planner.analysis.vessel_clearance import (
    ProbeShankASR,
    RadiusBearingVesselRuns,
    VesselClearanceInputError,
    analyze_probe_vessel_clearance,
)
from mouse_brain_planner.bridge import PROTOCOL_VERSION
from mouse_brain_planner.bridge.server import (
    SUPPORTED_ATLAS_IDENTIFIER,
    SUPPORTED_ATLAS_VERSION,
    BridgeDispatcher,
    BridgeError,
    JsonObject,
    LoadedAtlasProtocol,
    atlas_provenance,
)
from mouse_brain_planner.coordinates.anatomical_atlas import (
    canonical_anatomical_to_brainglobe_physical,
)
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.probe_models import PlacedProbeShank
from mouse_brain_planner.domain.probe_plan_models import (
    PROBE_PLANNING_ALGORITHM_VERSION,
    STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION,
    ProbePlanRecord,
)
from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.domain.vessel_clearance_models import (
    MajorVesselSourceProvenance,
    PhysicalASRPoint,
    ProbeVesselAnalysis,
    ProbeVesselConflict,
    VesselRiskProfile,
)
from mouse_brain_planner.domain.vessel_plan_models import (
    ProbeVesselAnalysisBundle,
    build_probe_vessel_analysis_bundle,
)
from mouse_brain_planner.surgery.trajectory import placed_shank_centerlines
from mouse_brain_planner.vasculature.vessap_major_vessels import (
    ATLAS_SHAPE_ASR,
    ATLAS_VOXEL_SIZE_UM,
    EXTRACTION_ALGORITHM_VERSION,
    MINIMUM_DIAMETER_UM,
    REGISTRATION_TRANSFORM_ID,
    SOURCE_BUNDLE_SHA256,
    SOURCE_ID,
    SOURCE_LICENSE,
    SOURCE_PAPER_DOI,
    SOURCE_RECORD_URL,
    SOURCE_VERSION,
    VesSAPMajorVesselError,
    VesSAPMajorVesselGraph,
    default_asset_is_available,
    load_vessap_major_vessels,
)

MAXIMUM_RETURNED_CONFLICTS: Final = 250
MAXIMUM_PROFILE_DISTANCE_UM: Final = 10_000.0
REFERENCE_PROFILE_ID: Final = "vessap-bl6j-no1-major-30um-v1"
REFERENCE_POLICY: Final = (
    "Display the configured external diameter >= 30 micrometre VesSAP reference only. "
    "Clearance classification is unavailable without published subject-registration "
    "and tissue-distortion uncertainty bounds."
)

ProjectGetter = Callable[[], PlannerProject]
RevisionGetter = Callable[[], int]
ProjectReplacer = Callable[[PlannerProject], int]
GraphLoader = Callable[[], VesSAPMajorVesselGraph]


@dataclass(slots=True)
class MajorVesselReferenceBridge:
    """Serve audited reference geometry but never classify surgical clearance."""

    dispatcher: BridgeDispatcher
    get_project: ProjectGetter
    get_revision: RevisionGetter
    replace_project: ProjectReplacer
    graph_loader: GraphLoader = load_vessap_major_vessels
    _graph_cache: VesSAPMajorVesselGraph | None = field(default=None, init=False, repr=False)
    _analysis_cache: RadiusBearingVesselRuns | None = field(default=None, init=False, repr=False)

    def register(self, *, advertise_capability: bool = True) -> None:
        if advertise_capability:
            self.dispatcher.declare_capability("auditedReferenceMajorVessels")
        self.dispatcher.register("vessel.major.reference.get", self.reference_get)
        self.dispatcher.register("vessel.major.reference.geometry", self.reference_geometry)
        self.dispatcher.register("vessel.major.reference.analyze", self.reference_analyze)

    def reference_get(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(params, required={"protocolVersion"})
        _require_protocol(params)
        atlas = self._require_loaded_atlas()
        graph = self._graph()
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "ready",
            "displayLabel": "Reference major vessels",
            "sourceKind": "reference-individual-vessel-graph",
            "subjectSpecific": False,
            "minimumDiameterMicrometres": MINIMUM_DIAMETER_UM,
            "pointCount": int(graph.points_asr_um.shape[0]),
            "runCount": graph.run_count,
            "segmentCount": int(graph.points_asr_um.shape[0] - graph.run_count),
            "pathLengthMicrometres": _path_length(graph),
            "coordinateFrame": {
                "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
                "unit": "micrometres",
                "axisOrder": ["AP", "DV", "ML"],
                "voxelAnchor": "physical_um = continuous_voxel * 25; no half-voxel shift",
            },
            "provenance": _provenance_payload(_source_provenance(graph)),
            "limitations": list(graph.provenance.limitations),
            "atlas": atlas_provenance(atlas),
        }

    def reference_geometry(self, params: Mapping[str, object]) -> JsonObject:
        """Return exact, digest-bound display geometry for the reviewed atlas."""
        _validate_params(params, required={"protocolVersion"})
        _require_protocol(params)
        atlas = self._require_loaded_atlas()
        graph = self._graph()
        points = np.ascontiguousarray(graph.points_asr_um, dtype="<f4")
        radii = np.ascontiguousarray(graph.radii_um, dtype="<f4")
        offsets = np.ascontiguousarray(graph.run_offsets, dtype="<i8")
        source_edges = np.ascontiguousarray(graph.source_edge_indices, dtype="<i4")
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "ready",
            "encoding": "contiguous-little-endian-v1",
            "pointCount": int(points.shape[0]),
            "runCount": graph.run_count,
            "segmentCount": int(points.shape[0] - graph.run_count),
            "pointsASRMicrometres": _buffer_payload(points, shape=list(points.shape)),
            "radiiMicrometres": _buffer_payload(radii, shape=list(radii.shape)),
            "runOffsets": _buffer_payload(offsets, shape=list(offsets.shape)),
            "sourceEdgeIndices": _buffer_payload(
                source_edges,
                shape=list(source_edges.shape),
            ),
            "provenance": _provenance_payload(_source_provenance(graph)),
            "limitations": list(graph.provenance.limitations),
            "atlas": atlas_provenance(atlas),
        }

    def reference_analyze(self, params: Mapping[str, object]) -> JsonObject:
        self._reject_clearance_analysis()
        _validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "planId",
                "expectedPlanInputSha256",
                "requiredMarginMicrometres",
                "registrationUncertaintyMicrometres",
                "riskProfileConfirmed",
                "referenceCoverageAcknowledged",
            },
            optional={"maximumConflicts"},
        )
        _require_protocol(params)
        project = self.get_project()
        _require_project_id(params["projectId"], project)
        actual_revision = self.get_revision()
        expected_revision = _integer(params["expectedProjectRevision"], "expectedProjectRevision")
        if expected_revision != actual_revision:
            raise BridgeError(
                "PROJECT_REVISION_CONFLICT",
                "The vessel analysis request uses a stale project revision.",
                details={
                    "expectedProjectRevision": expected_revision,
                    "actualProjectRevision": actual_revision,
                },
            )
        atlas = self._require_loaded_atlas()
        if project.atlas is None or project.atlas.metadata_sha256 != atlas.metadata.metadata_sha256:
            raise BridgeError(
                "ATLAS_IDENTITY_MISMATCH",
                "The project and loaded atlas provenance do not match.",
            )
        plan = _find_plan(project, params["planId"])
        if plan.planning_algorithm_version not in {
            STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION,
            PROBE_PLANNING_ALGORITHM_VERSION,
        }:
            raise BridgeError(
                "PROBE_PLAN_RECOMPUTE_REQUIRED",
                "This legacy probe plan must be updated through its subject calibration "
                "before vessel analysis.",
                details={
                    "planId": str(plan.plan_uuid),
                    "planningAlgorithmVersion": plan.planning_algorithm_version,
                    "requiredPlanningAlgorithmVersion": PROBE_PLANNING_ALGORITHM_VERSION,
                },
            )
        expected_plan_hash = _sha256(params["expectedPlanInputSha256"], "expectedPlanInputSha256")
        if expected_plan_hash != plan.input_sha256:
            raise BridgeError(
                "ANALYSIS_STALE",
                "The vessel analysis request uses an older probe-plan input.",
                details={"actualPlanInputSha256": plan.input_sha256},
            )
        try:
            project.validate_probe_plan_projection_semantics(plan)
        except ValueError as error:
            raise BridgeError(
                "PROBE_PLAN_PROJECTION_INVALID",
                "The probe plan geometry cannot be reproduced from its preserved inputs.",
                details={"reason": str(error), "exceptionType": type(error).__name__},
            ) from error
        required_margin = _distance(
            params["requiredMarginMicrometres"],
            "requiredMarginMicrometres",
        )
        uncertainty = _distance(
            params["registrationUncertaintyMicrometres"],
            "registrationUncertaintyMicrometres",
        )
        profile_confirmed = _boolean(params["riskProfileConfirmed"], "riskProfileConfirmed")
        coverage_acknowledged = _boolean(
            params["referenceCoverageAcknowledged"],
            "referenceCoverageAcknowledged",
        )
        maximum_conflicts = _integer(
            params.get("maximumConflicts", MAXIMUM_RETURNED_CONFLICTS),
            "maximumConflicts",
        )
        if maximum_conflicts <= 0 or maximum_conflicts > MAXIMUM_RETURNED_CONFLICTS:
            raise BridgeError(
                "INVALID_PARAMS",
                f"maximumConflicts must be in [1, {MAXIMUM_RETURNED_CONFLICTS}].",
                details={"field": "maximumConflicts"},
            )

        graph = self._graph()
        profile = VesselRiskProfile(
            profile_id=REFERENCE_PROFILE_ID,
            minimum_vessel_diameter_um=MINIMUM_DIAMETER_UM,
            required_margin_um=required_margin,
            registration_uncertainty_um=uncertainty,
            source_or_lab_policy=REFERENCE_POLICY,
            confirmed_by_user=profile_confirmed,
            reference_only_coverage_acknowledged=coverage_acknowledged,
        )
        shanks = tuple(
            _physical_shank(shank, project.atlas)
            for shank in placed_shank_centerlines(plan.probe_model, plan.placement)
        )
        try:
            result = analyze_probe_vessel_clearance(
                shanks=shanks,
                vessels=self._analysis_geometry(graph),
                risk_profile=profile,
                provenance=_source_provenance(graph),
                maximum_conflicts=maximum_conflicts,
            )
        except (ValidationError, VesselClearanceInputError) as error:
            raise BridgeError(
                "VESSEL_ANALYSIS_INVALID",
                "The reference-vessel analysis inputs could not be evaluated.",
                details={"exceptionType": type(error).__name__},
            ) from error
        limitations = tuple(graph.provenance.limitations)
        try:
            bundle = build_probe_vessel_analysis_bundle(
                plan_uuid=plan.plan_uuid,
                plan_version=plan.plan_version,
                plan_input_sha256=plan.input_sha256,
                maximum_conflicts=maximum_conflicts,
                analysis=result,
                limitations=limitations,
            )
        except ValidationError as error:
            raise BridgeError(
                "VESSEL_ANALYSIS_INVALID",
                "The reference-vessel analysis result could not be persisted.",
                details={"exceptionType": type(error).__name__},
            ) from error

        current_revision = self.get_revision()
        current_project = self.get_project()
        current_plan = next(
            (item for item in current_project.probe_plans if item.plan_uuid == plan.plan_uuid),
            None,
        )
        if (
            current_revision != expected_revision
            or current_project.project_uuid != project.project_uuid
            or current_plan is None
            or current_plan.plan_version != plan.plan_version
            or current_plan.input_sha256 != plan.input_sha256
        ):
            raise BridgeError(
                "ANALYSIS_STALE",
                "Probe inputs changed before the vessel analysis could be stored.",
                details={"analysisStored": False},
            )
        payload = current_project.model_dump(mode="python")
        payload["probe_vessel_analyses"] = [
            item
            for item in current_project.probe_vessel_analyses
            if item.plan_uuid != plan.plan_uuid
        ] + [bundle]
        try:
            updated = PlannerProject.model_validate(payload)
        except ValidationError as error:
            raise BridgeError(
                "VESSEL_ANALYSIS_INVALID",
                "The plan-linked vessel analysis failed project validation.",
                details={"exceptionType": type(error).__name__},
            ) from error
        updated.touch(
            "probe-major-vessel-analysis-run",
            json.dumps(
                {
                    "analysisSha256": bundle.analysis_sha256,
                    "planId": str(plan.plan_uuid),
                    "planInputSha256": plan.input_sha256,
                    "riskProfile": {
                        "confirmedByUser": profile.confirmed_by_user,
                        "minimumVesselDiameterMicrometres": (profile.minimum_vessel_diameter_um),
                        "profileId": profile.profile_id,
                        "referenceOnlyCoverageAcknowledged": (
                            profile.reference_only_coverage_acknowledged
                        ),
                        "registrationUncertaintyMicrometres": (profile.registration_uncertainty_um),
                        "requiredMarginMicrometres": profile.required_margin_um,
                        "sourceOrLabPolicy": profile.source_or_lab_policy,
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        stored_revision = self.replace_project(updated)
        if stored_revision != expected_revision + 1:
            raise RuntimeError("vessel project replacer did not increment revision exactly once")
        return major_vessel_analysis_result_payload(
            bundle,
            project_uuid=updated.project_uuid,
            project_revision=stored_revision,
        )

    def _reject_clearance_analysis(self) -> NoReturn:
        raise BridgeError(
            "VESSEL_ANALYSIS_UNAVAILABLE",
            (
                "The VesSAP population reference is display-only. Clearance analysis is "
                "unavailable because no subject-registration or tissue-distortion error "
                "bounds are published."
            ),
            details={"displayOnly": True, "subjectSpecific": False},
        )

    def _require_loaded_atlas(self) -> LoadedAtlasProtocol:
        atlas = self.dispatcher.context.loaded_atlas
        if atlas is None:
            raise BridgeError("ATLAS_NOT_OPEN", "Open the reviewed 25 micrometre atlas first.")
        metadata = atlas.metadata
        if (
            metadata.atlas_key != SUPPORTED_ATLAS_IDENTIFIER
            or metadata.atlas_package_version != SUPPORTED_ATLAS_VERSION
            or metadata.shape_voxels != ATLAS_SHAPE_ASR
            or metadata.resolution_um != (ATLAS_VOXEL_SIZE_UM,) * 3
        ):
            raise BridgeError(
                "ATLAS_IDENTITY_MISMATCH",
                "The major-vessel reference accepts only allen_mouse_25um v1.2.",
            )
        return atlas

    def _graph(self) -> VesSAPMajorVesselGraph:
        if self._graph_cache is None:
            try:
                self._graph_cache = self.graph_loader()
            except (VesSAPMajorVesselError, OSError, ValueError) as error:
                raise BridgeError(
                    "VESSEL_GEOMETRY_UNAVAILABLE",
                    "The bundled major-vessel reference failed its integrity checks.",
                    details={"exceptionType": type(error).__name__},
                ) from error
        return self._graph_cache

    def _analysis_geometry(
        self,
        graph: VesSAPMajorVesselGraph,
    ) -> RadiusBearingVesselRuns:
        if self._analysis_cache is None:
            self._analysis_cache = RadiusBearingVesselRuns(
                points_asr_um=np.asarray(graph.points_asr_um, dtype=np.float64),
                radii_um=np.asarray(graph.radii_um, dtype=np.float64),
                run_offsets=graph.run_offsets,
                source_edge_indices=np.asarray(graph.source_edge_indices, dtype=np.int64),
            )
        return self._analysis_cache


def register_major_vessel_handlers(
    dispatcher: BridgeDispatcher,
    *,
    get_project: ProjectGetter,
    get_revision: RevisionGetter,
    replace_project: ProjectReplacer,
    graph_loader: GraphLoader = load_vessap_major_vessels,
) -> MajorVesselReferenceBridge:
    extension = MajorVesselReferenceBridge(
        dispatcher=dispatcher,
        get_project=get_project,
        get_revision=get_revision,
        replace_project=replace_project,
        graph_loader=graph_loader,
    )
    extension.register(
        advertise_capability=(
            graph_loader is not load_vessap_major_vessels or default_asset_is_available()
        )
    )
    return extension


def _physical_shank(shank: PlacedProbeShank, atlas: AtlasMetadata) -> ProbeShankASR:
    entry = canonical_anatomical_to_brainglobe_physical(shank.entry, atlas, require_inside=False)
    tip = canonical_anatomical_to_brainglobe_physical(shank.tip, atlas, require_inside=False)
    return ProbeShankASR(
        shank_id=shank.shank_id,
        entry_asr_um=np.asarray(entry.as_tuple(), dtype=np.float64),
        tip_asr_um=np.asarray(tip.as_tuple(), dtype=np.float64),
        envelope_radius_um=shank.conservative_envelope_radius_um,
    )


def _source_provenance(graph: VesSAPMajorVesselGraph) -> MajorVesselSourceProvenance:
    value = graph.provenance
    return MajorVesselSourceProvenance(
        source_id=SOURCE_ID,
        source_doi=SOURCE_PAPER_DOI,
        source_record_url=SOURCE_RECORD_URL,
        source_paper_doi=SOURCE_PAPER_DOI,
        source_version=SOURCE_VERSION,
        source_license=SOURCE_LICENSE,
        dataset_title=value.dataset_title,
        authors=value.authors,
        specimen_id=value.specimen_id,
        source_archive_digest=f"sha256:{SOURCE_BUNDLE_SHA256}",
        derived_asset_sha256=value.asset_sha256,
        extraction_algorithm_version=EXTRACTION_ALGORITHM_VERSION,
        minimum_included_diameter_um=MINIMUM_DIAMETER_UM,
        pial_vessels_excluded=False,
        choroidal_vessels_excluded=False,
        registration_transform_id=REGISTRATION_TRANSFORM_ID,
    )


def _analysis_payload(result: ProbeVesselAnalysis) -> JsonObject:
    return {
        "algorithmVersion": result.algorithm_version,
        "inputSha256": result.input_sha256,
        "resultStatus": result.result_status.value,
        "statement": result.statement,
        "nearestCenterlineDistanceMicrometres": result.nearest_centerline_distance_um,
        "minimumGeometricClearanceMicrometres": result.minimum_geometric_clearance_um,
        "minimumAdjustedClearanceMicrometres": (result.minimum_uncertainty_adjusted_clearance_um),
        "candidateSegmentCount": result.candidate_segment_count,
        "measuredSegmentCount": result.measured_segment_count,
        "conflicts": [_conflict_payload(item) for item in result.conflicts],
        "conflictsTruncated": result.conflicts_truncated,
        "riskProfile": {
            "profileId": result.risk_profile.profile_id,
            "minimumVesselDiameterMicrometres": (result.risk_profile.minimum_vessel_diameter_um),
            "requiredMarginMicrometres": result.risk_profile.required_margin_um,
            "registrationUncertaintyMicrometres": (result.risk_profile.registration_uncertainty_um),
            "sourceOrLabPolicy": result.risk_profile.source_or_lab_policy,
            "confirmedByUser": result.risk_profile.confirmed_by_user,
            "referenceOnlyCoverageAcknowledged": (
                result.risk_profile.reference_only_coverage_acknowledged
            ),
        },
        "provenance": _provenance_payload(result.provenance),
        "warnings": list(result.warnings),
        "usableForNavigation": False,
    }


def major_vessel_analysis_result_payload(
    bundle: ProbeVesselAnalysisBundle,
    *,
    project_uuid: UUID,
    project_revision: int,
) -> JsonObject:
    """Return the stable native result shape for live and reopened analyses."""

    return {
        "protocolVersion": PROTOCOL_VERSION,
        "projectId": str(project_uuid),
        "projectRevision": project_revision,
        "planId": str(bundle.plan_uuid),
        "planVersion": bundle.plan_version,
        "planInputSha256": bundle.plan_input_sha256,
        "analysis": _analysis_payload(bundle.analysis),
        "limitations": list(bundle.limitations),
    }


def _conflict_payload(conflict: ProbeVesselConflict) -> JsonObject:
    return {
        "conflictId": conflict.conflict_id,
        "shankId": conflict.shank_id,
        "vesselSourceEdgeIndex": conflict.vessel_source_edge_index,
        "vesselRunIndex": conflict.vessel_run_index,
        "vesselSegmentIndexInRun": conflict.vessel_segment_index_in_run,
        "classification": conflict.classification.value,
        "vesselDiameterMicrometres": conflict.vessel_diameter_um,
        "probeEnvelopeRadiusMicrometres": conflict.probe_envelope_radius_um,
        "centerlineDistanceMicrometres": conflict.centerline_distance_um,
        "geometricSurfaceClearanceMicrometres": conflict.geometric_surface_clearance_um,
        "requiredMarginMicrometres": conflict.required_margin_um,
        "registrationUncertaintyMicrometres": conflict.registration_uncertainty_um,
        "adjustedClearanceMicrometres": conflict.uncertainty_adjusted_clearance_um,
        "probePoint": _point_payload(conflict.probe_point),
        "vesselPoint": _point_payload(conflict.vessel_point),
        "insertionDepthMicrometres": conflict.insertion_depth_um,
        "sourceKind": conflict.source_kind,
        "subjectSpecific": False,
        "warnings": list(conflict.warnings),
    }


def _point_payload(point: PhysicalASRPoint) -> JsonObject:
    return {
        "frameId": point.frame_id,
        "apMicrometres": point.ap_um,
        "dvMicrometres": point.dv_um,
        "mlMicrometres": point.ml_um,
    }


def _provenance_payload(value: MajorVesselSourceProvenance) -> JsonObject:
    return {
        "sourceId": value.source_id,
        "sourceKind": value.source_kind,
        "datasetTitle": value.dataset_title,
        "authors": list(value.authors),
        "specimenId": value.specimen_id,
        "sourceDoi": value.source_doi,
        "sourceRecordUrl": value.source_record_url,
        "sourcePaperDoi": value.source_paper_doi,
        "sourceVersion": value.source_version,
        "sourceLicense": value.source_license,
        "sourceArchiveDigest": value.source_archive_digest,
        "derivedAssetSha256": value.derived_asset_sha256,
        "extractionAlgorithmVersion": value.extraction_algorithm_version,
        "atlasIdentifier": value.atlas_key,
        "atlasVersion": value.atlas_version,
        "coordinateFrameId": value.coordinate_frame_id,
        "minimumIncludedDiameterMicrometres": value.minimum_included_diameter_um,
        "physicalUnitsDeclared": value.physical_units_declared,
        "atlasScaleApplied": value.atlas_scale_applied,
        "geometrySourceAudited": value.geometry_source_audited,
        "subjectSpecific": value.subject_specific,
        "pialVesselsExcluded": value.pial_vessels_excluded,
        "choroidalVesselsExcluded": value.choroidal_vessels_excluded,
        "arteryVeinClassificationAvailable": value.artery_vein_classification_available,
        "registrationTransformId": value.registration_transform_id,
        "registrationUncertaintyBoundMicrometres": (value.registration_uncertainty_bound_um),
        "tissueDistortionUncertaintyBoundMicrometres": (
            value.tissue_distortion_uncertainty_bound_um
        ),
        "uncertaintyBoundsReviewed": value.uncertainty_bounds_reviewed,
    }


def _buffer_payload(array: NDArray[np.generic], *, shape: list[int]) -> JsonObject:
    payload = array.tobytes(order="C")
    scalar_type = {
        np.dtype("<f4"): "float32",
        np.dtype("<i8"): "int64",
        np.dtype("<i4"): "int32",
    }.get(array.dtype)
    if scalar_type is None:
        raise TypeError(f"unsupported vessel buffer dtype {array.dtype}")
    return {
        "scalarType": scalar_type,
        "byteOrder": "littleEndian",
        "shape": shape,
        "byteLength": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "dataBase64": base64.b64encode(payload).decode("ascii"),
    }


def _path_length(graph: VesSAPMajorVesselGraph) -> float:
    total = 0.0
    for run_index in range(graph.run_count):
        points = np.asarray(graph.run_points_asr_um(run_index), dtype=np.float64)
        total += float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
    return total


def _find_plan(project: PlannerProject, value: object) -> ProbePlanRecord:
    plan_uuid = _uuid(value, "planId")
    plan = next((item for item in project.probe_plans if item.plan_uuid == plan_uuid), None)
    if plan is None:
        raise BridgeError(
            "PROBE_PLAN_NOT_FOUND",
            "The requested probe plan is not present in the current project.",
        )
    return plan


def _validate_params(
    params: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    actual = set(params)
    missing = required - actual
    unexpected = actual - allowed
    if missing or unexpected:
        raise BridgeError(
            "INVALID_PARAMS",
            "The method parameters do not match the protocol-v1 schema.",
            details={"missing": sorted(missing), "unexpected": sorted(unexpected)},
        )


def _require_protocol(params: Mapping[str, object]) -> None:
    value = params["protocolVersion"]
    if isinstance(value, bool) or not isinstance(value, int) or value != PROTOCOL_VERSION:
        raise BridgeError(
            "PROTOCOL_VERSION_MISMATCH",
            f"protocolVersion must equal {PROTOCOL_VERSION}.",
        )


def _require_project_id(value: object, project: PlannerProject) -> None:
    if _uuid(value, "projectId") != project.project_uuid:
        raise BridgeError("PROJECT_ID_MISMATCH", "The requested project is not active.")


def _uuid(value: object, field_name: str) -> UUID:
    if not isinstance(value, str):
        raise BridgeError("INVALID_PARAMS", f"{field_name} must be a canonical UUID string.")
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be a canonical UUID string.",
        ) from error
    if str(parsed) != value:
        raise BridgeError("INVALID_PARAMS", f"{field_name} must use canonical lowercase form.")
    return parsed


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BridgeError("INVALID_PARAMS", f"{field_name} must be a nonnegative integer.")
    return value


def _distance(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeError("INVALID_PARAMS", f"{field_name} must be numeric.")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= MAXIMUM_PROFILE_DISTANCE_UM:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be finite and in [0, {MAXIMUM_PROFILE_DISTANCE_UM:g}].",
        )
    return number


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise BridgeError("INVALID_PARAMS", f"{field_name} must be a boolean.")
    return value


def _sha256(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BridgeError("INVALID_PARAMS", f"{field_name} must be a lowercase SHA-256.")
    return value
