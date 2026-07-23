"""Radius-aware major-vessel analysis models with fail-closed language.

These models represent measurements against one explicit 3-D reference graph.
They never promote a reference specimen to subject-specific anatomy and never
use the word ``safe`` as a result classification.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class VesselConflictClassification(StrEnum):
    """Ordered physical/margin/uncertainty result for one closest approach."""

    INTERSECTION = "intersection"
    MARGIN_VIOLATION = "marginViolation"
    UNCERTAINTY_VIOLATION = "uncertaintyViolation"


class ProbeVesselResultStatus(StrEnum):
    """Overall classification without clinical or navigation claims."""

    INTERSECTION = "intersection"
    MARGIN_VIOLATION = "marginViolation"
    UNCERTAINTY_VIOLATION = "uncertaintyViolation"
    NO_CONFLICT_DETECTED = "noConflictDetected"
    INSUFFICIENT_GEOMETRY = "insufficientGeometry"


class VesselRiskProfile(BaseModel):
    """Explicit project/lab thresholds required before classification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(min_length=1, max_length=200)
    minimum_vessel_diameter_um: PositiveFiniteFloat
    required_margin_um: NonNegativeFiniteFloat
    registration_uncertainty_um: NonNegativeFiniteFloat
    source_or_lab_policy: str = Field(min_length=1, max_length=2_000)
    confirmed_by_user: bool
    reference_only_coverage_acknowledged: bool


class MajorVesselSourceProvenance(BaseModel):
    """Immutable provenance needed to interpret a derived reference graph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1, max_length=300)
    source_kind: Literal["reference-individual-vessel-graph"] = "reference-individual-vessel-graph"
    source_doi: str = Field(min_length=1, max_length=300)
    source_record_url: str = Field(min_length=1, max_length=2_000)
    source_paper_doi: str = Field(min_length=1, max_length=300)
    source_version: str = Field(min_length=1, max_length=200)
    source_license: str = Field(min_length=1, max_length=300)
    dataset_title: str = Field(min_length=1, max_length=500)
    # Schema 6 originally bounded the containing project member, not author count/text.
    authors: tuple[str, ...] = Field(min_length=1)
    specimen_id: str = Field(min_length=1, max_length=200)
    source_archive_digest: str = Field(min_length=1, max_length=300)
    derived_asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_algorithm_version: str = Field(min_length=1, max_length=300)
    atlas_key: Literal["allen_mouse_25um"] = "allen_mouse_25um"
    atlas_version: Literal["1.2"] = "1.2"
    coordinate_frame_id: Literal["BRAINGLOBE_PHYSICAL_ASR_UM"] = "BRAINGLOBE_PHYSICAL_ASR_UM"
    minimum_included_diameter_um: PositiveFiniteFloat
    physical_units_declared: Literal[True] = True
    atlas_scale_applied: Literal[True] = True
    geometry_source_audited: Literal[True] = True
    subject_specific: Literal[False] = False
    pial_vessels_excluded: bool = True
    choroidal_vessels_excluded: bool = True
    artery_vein_classification_available: Literal[False] = False
    registration_transform_id: str | None = Field(default=None, min_length=1, max_length=300)
    registration_uncertainty_bound_um: NonNegativeFiniteFloat | None = None
    tissue_distortion_uncertainty_bound_um: NonNegativeFiniteFloat | None = None
    uncertainty_bounds_reviewed: bool = False

    @model_validator(mode="after")
    def validate_uncertainty_evidence(self) -> Self:
        """Require a complete reviewed evidence package before absence classification.

        A graph can still provide useful positive conflict measurements when these
        fields are unavailable.  Missing evidence must, however, remain explicit
        so an acknowledgment or a user-entered zero cannot silently manufacture a
        bounded registration/tissue-distortion claim.
        """

        bounds = (
            self.registration_uncertainty_bound_um,
            self.tissue_distortion_uncertainty_bound_um,
        )
        if self.uncertainty_bounds_reviewed and (
            self.registration_transform_id is None or any(value is None for value in bounds)
        ):
            raise ValueError(
                "reviewed vessel uncertainty requires a transform ID and both uncertainty bounds"
            )
        return self

    @property
    def minimum_spatial_uncertainty_bound_um(self) -> float | None:
        """Return the conservative combined source bound, or ``None`` if unqualified."""

        if (
            not self.uncertainty_bounds_reviewed
            or self.registration_transform_id is None
            or self.registration_uncertainty_bound_um is None
            or self.tissue_distortion_uncertainty_bound_um is None
        ):
            return None
        return self.registration_uncertainty_bound_um + self.tissue_distortion_uncertainty_bound_um


class PhysicalASRPoint(BaseModel):
    """One continuous physical point in BrainGlobe ASR axis order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame_id: Literal["BRAINGLOBE_PHYSICAL_ASR_UM"] = "BRAINGLOBE_PHYSICAL_ASR_UM"
    ap_um: FiniteFloat
    dv_um: FiniteFloat
    ml_um: FiniteFloat


class ProbeVesselConflict(BaseModel):
    """One uncertainty-adjusted conflict against a finite vessel segment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    conflict_id: str = Field(min_length=1, max_length=300)
    shank_id: str = Field(min_length=1, max_length=200)
    vessel_source_edge_index: int = Field(ge=0)
    vessel_run_index: int = Field(ge=0)
    vessel_segment_index_in_run: int = Field(ge=0)
    classification: VesselConflictClassification
    vessel_diameter_um: PositiveFiniteFloat
    probe_envelope_radius_um: PositiveFiniteFloat
    centerline_distance_um: NonNegativeFiniteFloat
    geometric_surface_clearance_um: FiniteFloat
    required_margin_um: NonNegativeFiniteFloat
    registration_uncertainty_um: NonNegativeFiniteFloat
    uncertainty_adjusted_clearance_um: FiniteFloat
    probe_point: PhysicalASRPoint
    vessel_point: PhysicalASRPoint
    insertion_depth_um: NonNegativeFiniteFloat
    source_kind: Literal["reference-individual-vessel-graph"] = "reference-individual-vessel-graph"
    subject_specific: Literal[False] = False
    # Preserve the original schema-6 record contract; project I/O supplies the byte cap.
    warnings: tuple[str, ...]


class ProbeVesselAnalysis(BaseModel):
    """Explainable result for every shank against one immutable graph/profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    algorithm_version: Literal["major-vessel-aabb-tapered-surface-v3"] = (
        "major-vessel-aabb-tapered-surface-v3"
    )
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_status: ProbeVesselResultStatus
    nearest_centerline_distance_um: NonNegativeFiniteFloat | None
    minimum_geometric_clearance_um: FiniteFloat | None
    minimum_uncertainty_adjusted_clearance_um: FiniteFloat | None
    candidate_segment_count: int = Field(ge=0)
    measured_segment_count: int = Field(ge=0)
    conflicts: tuple[ProbeVesselConflict, ...]
    conflicts_truncated: bool
    risk_profile: VesselRiskProfile
    provenance: MajorVesselSourceProvenance
    statement: str = Field(min_length=1, max_length=2_000)
    # Preserve the original schema-6 record contract; project I/O supplies the byte cap.
    warnings: tuple[str, ...]
    usable_for_navigation: Literal[False] = False

    @model_validator(mode="after")
    def validate_status_and_statement(self) -> Self:
        """Keep result status, conflicts, and required wording mutually consistent."""

        if "safe" in self.statement.casefold():
            raise ValueError("vessel-analysis statement must not use safety language")
        if self.measured_segment_count != self.candidate_segment_count:
            raise ValueError("measured segment count must equal the exact narrow-phase candidates")
        if self.result_status is ProbeVesselResultStatus.INSUFFICIENT_GEOMETRY:
            if self.conflicts:
                raise ValueError("an insufficient-geometry result cannot publish conflicts")
        elif not (
            self.risk_profile.confirmed_by_user
            and self.risk_profile.reference_only_coverage_acknowledged
        ):
            raise ValueError("classified vessel result requires both explicit acknowledgements")
        if self.result_status is ProbeVesselResultStatus.NO_CONFLICT_DETECTED:
            required = (
                "No conflict detected within the loaded geometry and stated uncertainty "
                "assumptions."
            )
            if self.statement != required:
                raise ValueError("no-conflict result must use the reviewed bounded statement")
            if self.conflicts:
                raise ValueError("no-conflict result cannot contain conflicts")
            minimum_source_bound = self.provenance.minimum_spatial_uncertainty_bound_um
            if minimum_source_bound is None:
                raise ValueError(
                    "no-conflict result requires reviewed registration and tissue "
                    "uncertainty bounds"
                )
            if self.risk_profile.registration_uncertainty_um + 1e-6 < minimum_source_bound:
                raise ValueError(
                    "no-conflict result uncertainty is below the reviewed source bound"
                )
        if (
            self.result_status
            in {
                ProbeVesselResultStatus.INTERSECTION,
                ProbeVesselResultStatus.MARGIN_VIOLATION,
                ProbeVesselResultStatus.UNCERTAINTY_VIOLATION,
            }
            and not self.conflicts
        ):
            raise ValueError("a conflict result must contain at least one classified conflict")
        return self
