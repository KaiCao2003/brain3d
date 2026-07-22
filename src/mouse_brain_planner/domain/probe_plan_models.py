"""Persisted, provenance-complete probe plans and region-analysis bundles."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Final, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.probe_models import (
    NormalizedProbePlacement,
    ProbeModelDefinition,
)
from mouse_brain_planner.domain.region_models import ProbeRegionAnalysis

PROBE_PLANNING_ALGORITHM_VERSION: Final[
    Literal["calibrated-target-angle-depth-v1"]
] = "calibrated-target-angle-depth-v1"
REGION_ANALYSIS_BUNDLE_VERSION: Final[
    Literal["probe-region-analysis-bundle-v1"]
] = "probe-region-analysis-bundle-v1"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProbePlanRecord(BaseModel):
    """One editable plan version tied to exact calibration and atlas inputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    plan_uuid: UUID = Field(default_factory=uuid4)
    plan_version: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    source_target: UnprojectedBregmaTarget
    probe_model: ProbeModelDefinition
    placement: NormalizedProbePlacement
    calibration_uuid: UUID
    calibration_version: int = Field(gt=0)
    calibration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    atlas_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_algorithm_version: Literal["calibrated-target-angle-depth-v1"] = (
        PROBE_PLANNING_ALGORITHM_VERSION
    )
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
        if self.placement.context.subject_id is None:
            raise ValueError("probe plan requires an explicit animal subject ID")
        if self.source_target.projected:
            raise ValueError("probe plan source must preserve the original unprojected target")
        expected = probe_plan_input_digest(
            plan_uuid=self.plan_uuid,
            plan_version=self.plan_version,
            name=self.name,
            source_target=self.source_target,
            probe_model=self.probe_model,
            placement=self.placement,
            calibration_uuid=self.calibration_uuid,
            calibration_version=self.calibration_version,
            calibration_sha256=self.calibration_sha256,
            atlas_metadata_sha256=self.atlas_metadata_sha256,
            projection_sha256=self.projection_sha256,
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
    source_target: UnprojectedBregmaTarget,
    probe_model: ProbeModelDefinition,
    placement: NormalizedProbePlacement,
    calibration_uuid: UUID,
    calibration_version: int,
    calibration_sha256: str,
    atlas_metadata_sha256: str,
    projection_sha256: str,
) -> str:
    """Hash every input that can change displayed or analyzed geometry."""

    return _canonical_sha256(
        {
            "planUuid": str(plan_uuid),
            "planVersion": plan_version,
            "name": name,
            "sourceTarget": source_target.model_dump(mode="json"),
            "probeModel": probe_model.model_dump(mode="json"),
            "placement": placement.model_dump(mode="json"),
            "calibrationUuid": str(calibration_uuid),
            "calibrationVersion": calibration_version,
            "calibrationSha256": calibration_sha256,
            "atlasMetadataSha256": atlas_metadata_sha256,
            "projectionSha256": projection_sha256,
            "planningAlgorithmVersion": PROBE_PLANNING_ALGORITHM_VERSION,
        }
    )


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
