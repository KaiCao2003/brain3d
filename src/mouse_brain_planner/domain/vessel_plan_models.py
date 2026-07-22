"""Plan-linked persisted major-vessel analysis bundles."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Final, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mouse_brain_planner.domain.vessel_clearance_models import ProbeVesselAnalysis

VESSEL_ANALYSIS_BUNDLE_VERSION: Final[Literal["probe-major-vessel-analysis-bundle-v1"]] = (
    "probe-major-vessel-analysis-bundle-v1"
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProbeVesselAnalysisBundle(BaseModel):
    """One immutable result tied to one exact probe-plan input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    analysis_uuid: UUID = Field(default_factory=uuid4)
    plan_uuid: UUID
    plan_version: int = Field(gt=0)
    plan_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    algorithm_version: Literal["probe-major-vessel-analysis-bundle-v1"] = (
        VESSEL_ANALYSIS_BUNDLE_VERSION
    )
    maximum_conflicts: int = Field(gt=0, le=250)
    analysis: ProbeVesselAnalysis
    limitations: tuple[str, ...] = Field(min_length=1, max_length=64)
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    computed_at: datetime = Field(default_factory=_utc_now)
    usable_for_navigation: Literal[False] = False

    @field_validator("computed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("vessel-analysis timestamp must include a timezone")
        return value.astimezone(UTC)

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 2_000 for item in value):
            raise ValueError("vessel-analysis limitations must be bounded non-empty text")
        return value

    @model_validator(mode="after")
    def validate_bundle_digest(self) -> Self:
        if len(self.analysis.conflicts) > self.maximum_conflicts:
            raise ValueError(
                "vessel-analysis conflicts exceed the persisted maximum-conflicts request"
            )
        expected = probe_vessel_bundle_digest(
            plan_uuid=self.plan_uuid,
            plan_version=self.plan_version,
            plan_input_sha256=self.plan_input_sha256,
            maximum_conflicts=self.maximum_conflicts,
            analysis=self.analysis,
            limitations=self.limitations,
        )
        if self.analysis_sha256 != expected:
            raise ValueError("vessel-analysis SHA-256 does not match its persisted result")
        return self


def build_probe_vessel_analysis_bundle(
    *,
    plan_uuid: UUID,
    plan_version: int,
    plan_input_sha256: str,
    maximum_conflicts: int,
    analysis: ProbeVesselAnalysis,
    limitations: tuple[str, ...],
) -> ProbeVesselAnalysisBundle:
    """Build a validated persisted result without duplicating digest logic."""

    digest = probe_vessel_bundle_digest(
        plan_uuid=plan_uuid,
        plan_version=plan_version,
        plan_input_sha256=plan_input_sha256,
        maximum_conflicts=maximum_conflicts,
        analysis=analysis,
        limitations=limitations,
    )
    return ProbeVesselAnalysisBundle(
        plan_uuid=plan_uuid,
        plan_version=plan_version,
        plan_input_sha256=plan_input_sha256,
        maximum_conflicts=maximum_conflicts,
        analysis=analysis,
        limitations=limitations,
        analysis_sha256=digest,
    )


def probe_vessel_bundle_digest(
    *,
    plan_uuid: UUID,
    plan_version: int,
    plan_input_sha256: str,
    maximum_conflicts: int,
    analysis: ProbeVesselAnalysis,
    limitations: tuple[str, ...],
) -> str:
    """Hash the exact plan link, computation controls, result, and disclosure."""

    payload = {
        "planUuid": str(plan_uuid),
        "planVersion": plan_version,
        "planInputSha256": plan_input_sha256,
        "algorithmVersion": VESSEL_ANALYSIS_BUNDLE_VERSION,
        "maximumConflicts": maximum_conflicts,
        "analysis": analysis.model_dump(mode="json"),
        "limitations": list(limitations),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
