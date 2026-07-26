"""Persisted, provenance-complete probe plans and region-analysis bundles."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mouse_brain_planner.domain.atlas_reference_models import AtlasBregmaReference
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.probe_models import (
    NormalizedProbePlacement,
    PlacementMethod,
    ProbeModelDefinition,
)
from mouse_brain_planner.domain.region_models import ProbeRegionAnalysis
from mouse_brain_planner.domain.surgery_common import FiniteFloat, PositiveFiniteFloat

LEGACY_PROBE_PLANNING_ALGORITHM_VERSION: Final[Literal["calibrated-target-angle-depth-v1"]] = (
    "calibrated-target-angle-depth-v1"
)
STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION: Final[
    Literal["calibrated-stereotaxic-probe-transform-v2"]
] = "calibrated-stereotaxic-probe-transform-v2"
PROBE_PLANNING_ALGORITHM_VERSION: Final[Literal["calibrated-explicit-placement-mode-v3"]] = (
    "calibrated-explicit-placement-mode-v3"
)
ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION: Final[
    Literal["pinpoint-atlas-surface-ap-ml-depth-v4"]
] = "pinpoint-atlas-surface-ap-ml-depth-v4"
ATLAS_SURFACE_DEFINITION_VERSION: Final[Literal["first-annotated-voxel-superior-boundary-v1"]] = (
    "first-annotated-voxel-superior-boundary-v1"
)
REGION_ANALYSIS_BUNDLE_VERSION: Final[Literal["probe-region-analysis-bundle-v1"]] = (
    "probe-region-analysis-bundle-v1"
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProbeManipulatorInput(BaseModel):
    """Exact subject-stereotaxic controls entered by the operator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame_id: str = Field(min_length=1, max_length=200)
    azimuth_deg: FiniteFloat = Field(ge=-180, le=180)
    elevation_deg: FiniteFloat = Field(ge=-90, le=90)
    insertion_depth_um: PositiveFiniteFloat
    axial_rotation_deg: FiniteFloat = Field(ge=-180, le=180)
    angle_convention: Literal[
        "azimuth about +DV from +AP toward +ML; elevation from AP-ML plane toward +DV"
    ] = "azimuth about +DV from +AP toward +ML; elevation from AP-ML plane toward +DV"


class ProbePlacementMode(StrEnum):
    """Operator-visible input modes normalized into one calibrated trajectory."""

    ENTRY_AND_TARGET = "ENTRY_AND_TARGET"
    ENTRY_ANGLES_DEPTH = "ENTRY_ANGLES_DEPTH"
    TARGET_ANGLES_DEPTH = "TARGET_ANGLES_DEPTH"
    STEREOTAXIC_TARGET_MANIPULATOR = "STEREOTAXIC_TARGET_MANIPULATOR"
    ATLAS_SURFACE_AP_ML = "ATLAS_SURFACE_AP_ML"

    @property
    def placement_method(self) -> PlacementMethod:
        return {
            ProbePlacementMode.ENTRY_AND_TARGET: PlacementMethod.ENTRY_TARGET,
            ProbePlacementMode.ENTRY_ANGLES_DEPTH: PlacementMethod.ENTRY_ANGLES_DEPTH,
            ProbePlacementMode.TARGET_ANGLES_DEPTH: PlacementMethod.TARGET_ANGLES_DEPTH,
            ProbePlacementMode.STEREOTAXIC_TARGET_MANIPULATOR: (
                PlacementMethod.STEREOTAXIC_TARGET_MANIPULATOR
            ),
            ProbePlacementMode.ATLAS_SURFACE_AP_ML: PlacementMethod.ATLAS_SURFACE_AP_ML,
        }[self]


class BregmaRelativeEntryInput(BaseModel):
    """Exact editable entry coordinate entered relative to the animal's bregma."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame_id: Literal["BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"] = (
        "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"
    )
    origin: Literal["bregma"] = "bregma"
    component_order: tuple[Literal["AP"], Literal["ML"], Literal["DV"]] = (
        "AP",
        "ML",
        "DV",
    )
    units: Literal["millimetre"] = "millimetre"
    ap_positive_direction: Literal["anterior"] = "anterior"
    ap_negative_direction: Literal["posterior/back"] = "posterior/back"
    ml_positive_direction: Literal["right"] = "right"
    ml_negative_direction: Literal["left"] = "left"
    dv_positive_direction: Literal["dorsal/up"] = "dorsal/up"
    dv_negative_direction: Literal["deep/ventral"] = "deep/ventral"
    ap_mm: FiniteFloat
    ml_mm: FiniteFloat
    dv_mm: FiniteFloat


class ProbePlacementInput(BaseModel):
    """Exact mode-specific controls retained independently from normalized geometry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ProbePlacementMode
    entry: BregmaRelativeEntryInput | None = None
    angle_frame_id: str | None = Field(default=None, min_length=1, max_length=200)
    azimuth_deg: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    elevation_deg: FiniteFloat | None = Field(default=None, ge=-90, le=90)
    insertion_depth_um: PositiveFiniteFloat | None = None
    axial_rotation_deg: FiniteFloat = Field(ge=-180, le=180)
    angle_convention: (
        Literal["azimuth about +DV from +AP toward +ML; elevation from AP-ML plane toward +DV"]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_mode_fields(self) -> Self:
        needs_entry = self.mode in {
            ProbePlacementMode.ENTRY_AND_TARGET,
            ProbePlacementMode.ENTRY_ANGLES_DEPTH,
        }
        if (self.entry is not None) != needs_entry:
            raise ValueError(f"{self.mode.value} has an invalid entry-coordinate shape")
        needs_angles = self.mode is not ProbePlacementMode.ENTRY_AND_TARGET
        angle_fields = (
            self.angle_frame_id,
            self.azimuth_deg,
            self.elevation_deg,
            self.insertion_depth_um,
            self.angle_convention,
        )
        if needs_angles and any(value is None for value in angle_fields):
            raise ValueError(f"{self.mode.value} requires angles, depth, and angle frame")
        if not needs_angles and any(value is not None for value in angle_fields):
            raise ValueError(f"{self.mode.value} cannot contain angle or depth inputs")
        return self


class AtlasSurfaceProbeInput(BaseModel):
    """Exact direct-planning controls plus the resolved atlas-surface evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["ATLAS_SURFACE_AP_ML"] = "ATLAS_SURFACE_AP_ML"
    bregma_reference: AtlasBregmaReference
    insertion_ap_mm: FiniteFloat
    insertion_ml_mm: FiniteFloat
    surface_depth_mm: PositiveFiniteFloat
    sagittal_angle_deg: FiniteFloat = Field(gt=-90, lt=90)
    probe_layout_rotation_deg: Literal[0, 90]
    surface_entry_physical: BrainGlobePhysicalPoint
    surface_dv_index: int = Field(ge=0)
    surface_dv_resolution_um: PositiveFiniteFloat
    annotation_source: str = Field(min_length=1, max_length=500)
    annotation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    surface_definition_version: Literal["first-annotated-voxel-superior-boundary-v1"] = (
        ATLAS_SURFACE_DEFINITION_VERSION
    )
    ap_sign_convention: Literal["AP positive anterior; AP negative posterior/back"] = (
        "AP positive anterior; AP negative posterior/back"
    )
    ml_sign_convention: Literal["ML positive animal right; ML negative animal left"] = (
        "ML positive animal right; ML negative animal left"
    )
    depth_convention: Literal[
        "positive path length from the resolved atlas brain-surface entry"
    ] = "positive path length from the resolved atlas brain-surface entry"
    angle_convention: Literal[
        "zero is deep/ventral; positive advances anterior-to-posterior; "
        "negative advances posterior-to-anterior"
    ] = (
        "zero is deep/ventral; positive advances anterior-to-posterior; "
        "negative advances posterior-to-anterior"
    )
    layout_convention: Literal[
        "0 degrees places the shank array in the sagittal plane; "
        "90 degrees rotates it clockwise when viewed dorsally"
    ] = (
        "0 degrees places the shank array in the sagittal plane; "
        "90 degrees rotates it clockwise when viewed dorsally"
    )

    @field_validator("probe_layout_rotation_deg", mode="before")
    @classmethod
    def reject_boolean_layout_rotation(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("probe layout rotation must be 0 or 90 degrees")
        return value

    @model_validator(mode="after")
    def validate_reference_identity(self) -> Self:
        reference_identity = (
            self.bregma_reference.atlas_key,
            self.bregma_reference.atlas_version,
        )
        entry_identity = (
            self.surface_entry_physical.atlas_key,
            self.surface_entry_physical.atlas_version,
        )
        if entry_identity != reference_identity:
            raise ValueError("surface entry atlas identity does not match bregma reference")
        expected_ap_um = self.bregma_reference.ap_um - self.insertion_ap_mm * 1000.0
        expected_ml_um = self.bregma_reference.ml_um - self.insertion_ml_mm * 1000.0
        if not (
            abs(self.surface_entry_physical.ap_um - expected_ap_um) <= 1e-6
            and abs(self.surface_entry_physical.ml_um - expected_ml_um) <= 1e-6
        ):
            raise ValueError("surface entry AP/ML does not match bregma-relative input")
        expected_dv_um = self.surface_dv_index * self.surface_dv_resolution_um
        if abs(self.surface_entry_physical.dv_um - expected_dv_um) > 1e-6:
            raise ValueError("surface entry is not the recorded superior voxel boundary")
        return self


class ProbePlanRecord(BaseModel):
    """One editable plan version tied to exact calibration and atlas inputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    plan_uuid: UUID = Field(default_factory=uuid4)
    plan_version: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    source_target: UnprojectedBregmaTarget | None
    probe_model: ProbeModelDefinition
    manipulator_input: ProbeManipulatorInput | None = None
    placement_input: ProbePlacementInput | None = None
    surface_relative_input: AtlasSurfaceProbeInput | None = None
    placement: NormalizedProbePlacement
    calibration_uuid: UUID | None = None
    calibration_version: int | None = Field(default=None, gt=0)
    calibration_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    atlas_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_algorithm_version: Literal[
        "calibrated-target-angle-depth-v1",
        "calibrated-stereotaxic-probe-transform-v2",
        "calibrated-explicit-placement-mode-v3",
        "pinpoint-atlas-surface-ap-ml-depth-v4",
    ] = LEGACY_PROBE_PLANNING_ALGORITHM_VERSION
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=_utc_now)
    modified_at: datetime = Field(default_factory=_utc_now)
    usable_for_navigation: Literal[False] = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("probe plan name must contain non-whitespace text")
        return normalized

    @field_validator("created_at", "modified_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("probe plan timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_identity_and_digest(self) -> Self:
        """Reject mixed model identities, subjects, or a stale serialized hash."""

        model_identity = (self.probe_model.model_id, self.probe_model.model_version)
        placement_identity = (
            self.placement.probe_model_id,
            self.placement.probe_model_version,
        )
        if model_identity != placement_identity:
            raise ValueError("probe plan model snapshot does not match placement identity")
        if self.placement.name != self.name:
            raise ValueError("probe plan name does not match normalized placement name")
        is_surface_plan = (
            self.planning_algorithm_version == ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION
        )
        if self.placement.context.subject_id is None and not is_surface_plan:
            raise ValueError("probe plan requires an explicit animal subject ID")
        if self.source_target is not None and self.source_target.projected:
            raise ValueError("probe plan source must preserve the original unprojected target")
        if not is_surface_plan:
            if self.source_target is None:
                raise ValueError("v1-v3 probe plans require an unprojected source target")
            if (
                self.calibration_uuid is None
                or self.calibration_version is None
                or self.calibration_sha256 is None
            ):
                raise ValueError("v1-v3 probe plans require exact calibration provenance")
            if self.surface_relative_input is not None:
                raise ValueError("v1-v3 probe plans cannot contain atlas-surface inputs")
        if self.planning_algorithm_version == LEGACY_PROBE_PLANNING_ALGORITHM_VERSION:
            if self.manipulator_input is not None or self.placement_input is not None:
                raise ValueError("v1 probe plans cannot contain later-version planning inputs")
            if self.placement.method is not PlacementMethod.TARGET_ANGLES_DEPTH:
                raise ValueError("v1 probe plans require direct atlas target-angle placement")
            if (
                self.placement.local_lateral_direction is not None
                or self.placement.local_normal_direction is not None
                or self.placement.model_to_placement_uniform_scale != 1
            ):
                raise ValueError("v1 probe plans require unresolved legacy cross-section geometry")
        elif self.planning_algorithm_version == STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION:
            if self.manipulator_input is None:
                raise ValueError("v2 probe plans require preserved manipulator inputs")
            if self.placement.method.value != "stereotaxic-target-plus-manipulator-angles":
                raise ValueError("v2 probe plans require stereotaxic manipulator placement")
            if self.placement_input is not None:
                raise ValueError("v2 probe plans cannot contain v3 placement inputs")
        elif self.planning_algorithm_version == PROBE_PLANNING_ALGORITHM_VERSION:
            if self.placement_input is None:
                raise ValueError("v3 probe plans require preserved placement-mode inputs")
            if self.placement.method is not self.placement_input.mode.placement_method:
                raise ValueError("placement mode does not match normalized placement method")
            if self.placement_input.mode is ProbePlacementMode.STEREOTAXIC_TARGET_MANIPULATOR:
                if self.manipulator_input is None:
                    raise ValueError("stereotaxic mode requires preserved manipulator inputs")
                comparable = (
                    self.placement_input.angle_frame_id,
                    self.placement_input.azimuth_deg,
                    self.placement_input.elevation_deg,
                    self.placement_input.insertion_depth_um,
                    self.placement_input.axial_rotation_deg,
                )
                manipulator = (
                    self.manipulator_input.frame_id,
                    self.manipulator_input.azimuth_deg,
                    self.manipulator_input.elevation_deg,
                    self.manipulator_input.insertion_depth_um,
                    self.manipulator_input.axial_rotation_deg,
                )
                if comparable != manipulator:
                    raise ValueError("placement input does not match preserved manipulator input")
            elif self.manipulator_input is not None:
                raise ValueError("non-manipulator placement modes cannot contain manipulator input")
        elif is_surface_plan:
            if (
                self.source_target is not None
                or self.manipulator_input is not None
                or self.placement_input is not None
            ):
                raise ValueError("v4 atlas-surface plans cannot contain legacy target inputs")
            if any(
                value is not None
                for value in (
                    self.calibration_uuid,
                    self.calibration_version,
                    self.calibration_sha256,
                )
            ):
                raise ValueError("v4 atlas-surface plans cannot claim a subject calibration")
            if self.surface_relative_input is None:
                raise ValueError("v4 atlas-surface plans require preserved direct inputs")
            if self.placement.method is not PlacementMethod.ATLAS_SURFACE_AP_ML:
                raise ValueError("v4 atlas-surface plan has the wrong placement method")
        expected = probe_plan_input_digest(
            plan_uuid=self.plan_uuid,
            plan_version=self.plan_version,
            name=self.name,
            source_target=self.source_target,
            probe_model=self.probe_model,
            manipulator_input=self.manipulator_input,
            placement_input=self.placement_input,
            surface_relative_input=self.surface_relative_input,
            placement=self.placement,
            calibration_uuid=self.calibration_uuid,
            calibration_version=self.calibration_version,
            calibration_sha256=self.calibration_sha256,
            atlas_metadata_sha256=self.atlas_metadata_sha256,
            projection_sha256=self.projection_sha256,
            planning_algorithm_version=self.planning_algorithm_version,
        )
        if self.input_sha256 != expected:
            raise ValueError("probe plan input SHA-256 does not match its scientific inputs")
        return self


class ProbeRegionAnalysisBundle(BaseModel):
    """All shank traversals for one exact immutable probe-plan input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    analysis_uuid: UUID = Field(default_factory=uuid4)
    plan_uuid: UUID
    plan_version: int = Field(gt=0)
    plan_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    algorithm_version: Literal["probe-region-analysis-bundle-v1"] = REGION_ANALYSIS_BUNDLE_VERSION
    shank_analyses: tuple[ProbeRegionAnalysis, ...] = Field(min_length=1)
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    computed_at: datetime = Field(default_factory=_utc_now)
    usable_for_navigation: Literal[False] = False

    @field_validator("computed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("region-analysis timestamp must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        """Require one placement/model and exactly one result per shank ID."""

        placement_ids = {analysis.placement_uuid for analysis in self.shank_analyses}
        model_ids = {
            (analysis.probe_model_id, analysis.probe_model_version)
            for analysis in self.shank_analyses
        }
        shank_ids = [analysis.shank_id for analysis in self.shank_analyses]
        if len(placement_ids) != 1 or len(model_ids) != 1:
            raise ValueError("region bundle analyses must share placement and model identity")
        if len(shank_ids) != len(set(shank_ids)):
            raise ValueError("region bundle cannot contain duplicate shank analyses")
        expected = probe_region_bundle_digest(
            plan_uuid=self.plan_uuid,
            plan_version=self.plan_version,
            plan_input_sha256=self.plan_input_sha256,
            shank_analyses=self.shank_analyses,
        )
        if self.analysis_sha256 != expected:
            raise ValueError("region-analysis SHA-256 does not match its persisted results")
        return self


def probe_plan_input_digest(
    *,
    plan_uuid: UUID,
    plan_version: int,
    name: str,
    source_target: UnprojectedBregmaTarget | None,
    probe_model: ProbeModelDefinition,
    placement: NormalizedProbePlacement,
    calibration_uuid: UUID | None,
    calibration_version: int | None,
    calibration_sha256: str | None,
    atlas_metadata_sha256: str,
    projection_sha256: str,
    manipulator_input: ProbeManipulatorInput | None = None,
    placement_input: ProbePlacementInput | None = None,
    surface_relative_input: AtlasSurfaceProbeInput | None = None,
    planning_algorithm_version: Literal[
        "calibrated-target-angle-depth-v1",
        "calibrated-stereotaxic-probe-transform-v2",
        "calibrated-explicit-placement-mode-v3",
        "pinpoint-atlas-surface-ap-ml-depth-v4",
    ] = LEGACY_PROBE_PLANNING_ALGORITHM_VERSION,
) -> str:
    """Hash every input that can change displayed or analyzed geometry."""

    placement_payload = placement.model_dump(mode="json")
    if planning_algorithm_version == LEGACY_PROBE_PLANNING_ALGORITHM_VERSION:
        placement_payload.pop("local_lateral_direction", None)
        placement_payload.pop("local_normal_direction", None)
        placement_payload.pop("model_to_placement_uniform_scale", None)
    payload: dict[str, object] = {
        "planUuid": str(plan_uuid),
        "planVersion": plan_version,
        "name": name,
        "sourceTarget": (None if source_target is None else source_target.model_dump(mode="json")),
        "probeModel": probe_model.model_dump(mode="json"),
        "placement": placement_payload,
        "calibrationUuid": None if calibration_uuid is None else str(calibration_uuid),
        "calibrationVersion": calibration_version,
        "calibrationSha256": calibration_sha256,
        "atlasMetadataSha256": atlas_metadata_sha256,
        "projectionSha256": projection_sha256,
        "planningAlgorithmVersion": planning_algorithm_version,
    }
    if planning_algorithm_version in {
        STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION,
        PROBE_PLANNING_ALGORITHM_VERSION,
    }:
        payload["manipulatorInput"] = (
            None if manipulator_input is None else manipulator_input.model_dump(mode="json")
        )
    if planning_algorithm_version == PROBE_PLANNING_ALGORITHM_VERSION:
        payload["placementInput"] = (
            None if placement_input is None else placement_input.model_dump(mode="json")
        )
    if planning_algorithm_version == ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION:
        payload["surfaceRelativeInput"] = (
            None
            if surface_relative_input is None
            else surface_relative_input.model_dump(mode="json")
        )
    return _canonical_sha256(payload)


def probe_region_bundle_digest(
    *,
    plan_uuid: UUID,
    plan_version: int,
    plan_input_sha256: str,
    shank_analyses: tuple[ProbeRegionAnalysis, ...],
) -> str:
    """Hash an ordered multi-shank result and its plan-staleness key."""

    return _canonical_sha256(
        {
            "planUuid": str(plan_uuid),
            "planVersion": plan_version,
            "planInputSha256": plan_input_sha256,
            "algorithmVersion": REGION_ANALYSIS_BUNDLE_VERSION,
            "shankAnalyses": [analysis.model_dump(mode="json") for analysis in shank_analyses],
        }
    )


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
