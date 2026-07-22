"""Explicit models for finite probe-to-atlas region traversal.

The atlas-native point below deliberately uses domain component order
``AP, ML, DV`` while retaining BrainGlobe ASR's origin and directions.  This
keeps anatomical component order out of NumPy indexing code without pretending
that the atlas extent corner is bregma or a subject coordinate frame.
"""

from __future__ import annotations

import math
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mouse_brain_planner.domain.coordinate_models import BrainGlobeVoxelIndex

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class TraversalLocation(StrEnum):
    """Semantic meaning of an annotation lookup result."""

    STRUCTURE = "structure"
    OUTSIDE_BRAIN = "outside-brain"
    OUTSIDE_ATLAS = "outside-atlas"


class TraversalHemisphere(StrEnum):
    """Hemisphere occupied by a positive-length region run."""

    LEFT = "left"
    RIGHT = "right"
    MIDLINE = "midline"
    UNKNOWN = "unknown"


class _DepthInterval(Protocol):
    entry_depth_um: float
    exit_depth_um: float
    length_um: float


class AtlasPhysicalPointAPMLDV(BaseModel):
    """Atlas-native physical point in canonical ``AP, ML, DV`` component order.

    Coordinates are micrometres from the BrainGlobe ASR volume's
    anterior/superior/right *voxel-corner* origin.  Positive AP is posterior,
    positive ML is left, and positive DV is inferior.  ``coordinate_transform_id``
    identifies the calibration/transform that produced the atlas-native point;
    the literal ``atlas-native-identity`` is appropriate only for points authored
    directly in this declared atlas frame (for example, synthetic tests).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    atlas_key: str = Field(min_length=1, max_length=200)
    atlas_version: str = Field(min_length=1, max_length=200)
    coordinate_transform_id: str = Field(min_length=1, max_length=300)
    ap_um: FiniteFloat
    ml_um: FiniteFloat
    dv_um: FiniteFloat
    frame_id: Literal["BRAINGLOBE_PHYSICAL_ASR_AP_ML_DV_UM"] = "BRAINGLOBE_PHYSICAL_ASR_AP_ML_DV_UM"
    component_order: tuple[Literal["AP"], Literal["ML"], Literal["DV"]] = (
        "AP",
        "ML",
        "DV",
    )
    units: Literal["micrometre"] = "micrometre"
    origin: Literal["atlas-anterior-superior-right-voxel-corner"] = (
        "atlas-anterior-superior-right-voxel-corner"
    )
    ap_positive_direction: Literal["posterior"] = "posterior"
    ml_positive_direction: Literal["left"] = "left"
    dv_positive_direction: Literal["inferior"] = "inferior"
    voxel_anchor: Literal["continuous-voxel-corner"] = "continuous-voxel-corner"

    @field_validator("ap_um", "ml_um", "dv_um", mode="before")
    @classmethod
    def reject_boolean_coordinate(cls, value: object) -> object:
        """Reject Python booleans before Pydantic can coerce them to 0/1."""

        if isinstance(value, bool):
            raise ValueError("atlas physical coordinate components cannot be boolean")
        return value

    def as_ap_ml_dv(self) -> tuple[float, float, float]:
        """Return the explicitly documented domain component order."""

        return (self.ap_um, self.ml_um, self.dv_um)


class CalibratedProbeShankSegment(BaseModel):
    """One finite shank centerline already transformed into the atlas frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    placement_uuid: UUID
    probe_model_id: str = Field(min_length=1, max_length=200)
    probe_model_version: str = Field(min_length=1, max_length=100)
    shank_id: str = Field(min_length=1, max_length=200)
    entry: AtlasPhysicalPointAPMLDV
    tip: AtlasPhysicalPointAPMLDV

    @model_validator(mode="after")
    def validate_one_coordinate_space_and_nonzero_length(self) -> Self:
        """Reject mixed atlas/transform identities and zero-length segments."""

        entry_space = (
            self.entry.atlas_key,
            self.entry.atlas_version,
            self.entry.frame_id,
            self.entry.coordinate_transform_id,
        )
        tip_space = (
            self.tip.atlas_key,
            self.tip.atlas_version,
            self.tip.frame_id,
            self.tip.coordinate_transform_id,
        )
        if entry_space != tip_space:
            raise ValueError("probe entry and tip must use one atlas and coordinate transform")
        if self.entry.as_ap_ml_dv() == self.tip.as_ap_ml_dv():
            raise ValueError("probe entry and tip must be distinct")
        return self


class AtlasRecordingSitePoint(BaseModel):
    """One placed recording site already transformed into the atlas frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    placement_uuid: UUID
    probe_model_id: str = Field(min_length=1, max_length=200)
    probe_model_version: str = Field(min_length=1, max_length=100)
    shank_id: str = Field(min_length=1, max_length=200)
    site_id: str = Field(min_length=1, max_length=200)
    point: AtlasPhysicalPointAPMLDV


class RegionTraversalVoxelInterval(BaseModel):
    """Positive-length parametric interval owned by one annotation voxel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    voxel: BrainGlobeVoxelIndex
    structure_id: int = Field(ge=0)
    location: TraversalLocation
    entry_t: FiniteFloat = Field(ge=0, le=1)
    exit_t: FiniteFloat = Field(ge=0, le=1)
    entry_depth_um: NonNegativeFiniteFloat
    exit_depth_um: NonNegativeFiniteFloat
    length_um: NonNegativeFiniteFloat

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        """Keep interval parameter and physical-depth representations coherent."""

        if self.exit_t <= self.entry_t:
            raise ValueError("voxel traversal intervals must have positive parametric length")
        if self.exit_depth_um <= self.entry_depth_um:
            raise ValueError("voxel traversal intervals must have positive physical length")
        expected = self.exit_depth_um - self.entry_depth_um
        if not math.isclose(self.length_um, expected, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError("voxel interval length must equal exit depth minus entry depth")
        if self.structure_id == 0 and self.location is not TraversalLocation.OUTSIDE_BRAIN:
            raise ValueError("annotation ID 0 must remain explicitly outside-brain")
        if self.structure_id > 0 and self.location is not TraversalLocation.STRUCTURE:
            raise ValueError("positive annotation IDs must be structure intervals")
        return self


class RegionTraversalSegment(BaseModel):
    """Run-length encoded adjacent annotation voxels with one structure ID."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shank_id: str = Field(min_length=1, max_length=200)
    structure_id: int = Field(ge=0)
    acronym: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=1000)
    structure_id_path: tuple[int, ...] = ()
    rgb: tuple[int, int, int]
    location: TraversalLocation
    hemisphere: TraversalHemisphere
    entry_depth_um: NonNegativeFiniteFloat
    exit_depth_um: NonNegativeFiniteFloat
    length_um: NonNegativeFiniteFloat
    entry_point: AtlasPhysicalPointAPMLDV
    exit_point: AtlasPhysicalPointAPMLDV
    voxel_count: int = Field(gt=0)

    @field_validator("rgb")
    @classmethod
    def validate_rgb(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        """Require source-compatible 8-bit color components."""

        if any(component < 0 or component > 255 for component in value):
            raise ValueError("region RGB components must be in [0, 255]")
        return value

    @model_validator(mode="after")
    def validate_depth_interval(self) -> Self:
        """Keep physical segment length coherent with depth endpoints."""

        if self.exit_depth_um <= self.entry_depth_um:
            raise ValueError("region traversal segments must have positive length")
        expected = self.exit_depth_um - self.entry_depth_um
        if not math.isclose(self.length_um, expected, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError("region segment length must equal exit depth minus entry depth")
        if self.structure_id == 0 and self.location is not TraversalLocation.OUTSIDE_BRAIN:
            raise ValueError("annotation ID 0 must remain explicitly outside-brain")
        if self.structure_id > 0 and self.location is not TraversalLocation.STRUCTURE:
            raise ValueError("positive annotation IDs must be structure segments")
        return self


class RecordingSiteRegionAssignment(BaseModel):
    """Half-open annotation lookup for one placed recording site."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shank_id: str = Field(min_length=1, max_length=200)
    site_id: str = Field(min_length=1, max_length=200)
    point: AtlasPhysicalPointAPMLDV
    voxel: BrainGlobeVoxelIndex | None
    structure_id: int = Field(ge=0)
    acronym: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=1000)
    structure_id_path: tuple[int, ...] = ()
    rgb: tuple[int, int, int]
    location: TraversalLocation
    inside_atlas: bool
    inside_brain: bool

    @model_validator(mode="after")
    def validate_location_flags(self) -> Self:
        """Prevent outside-atlas and outside-brain states from being conflated."""

        if self.location is TraversalLocation.OUTSIDE_ATLAS:
            if self.inside_atlas or self.inside_brain or self.voxel is not None:
                raise ValueError("outside-atlas sites cannot have an atlas voxel or inside flags")
        elif not self.inside_atlas or self.voxel is None:
            raise ValueError("in-atlas site assignments require an annotation voxel")
        if self.location is TraversalLocation.OUTSIDE_BRAIN:
            if self.structure_id != 0 or self.inside_brain:
                raise ValueError("outside-brain assignments must preserve annotation ID 0")
        if self.location is TraversalLocation.STRUCTURE:
            if self.structure_id <= 0 or not self.inside_brain:
                raise ValueError("structure assignments require a positive annotation ID")
        return self


class ProbeRegionAnalysis(BaseModel):
    """Complete deterministic geometry result for one finite probe shank."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_uuid: UUID = Field(default_factory=uuid4)
    placement_uuid: UUID
    probe_model_id: str = Field(min_length=1, max_length=200)
    probe_model_version: str = Field(min_length=1, max_length=100)
    shank_id: str = Field(min_length=1, max_length=200)
    atlas_key: str = Field(min_length=1, max_length=200)
    atlas_version: str = Field(min_length=1, max_length=200)
    atlas_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_version: str = Field(min_length=1, max_length=300)
    algorithm_version: str = Field(min_length=1, max_length=100)
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    tie_break_rule: Literal[
        "half-open-lower-inclusive; negative crossings own following negative-side interval; "
        "simultaneous boundary crossings advance every tied axis"
    ]
    total_path_length_um: NonNegativeFiniteFloat
    intersects_atlas: bool
    starts_outside_atlas: bool
    ends_outside_atlas: bool
    clipped_entry_depth_um: NonNegativeFiniteFloat | None
    clipped_exit_depth_um: NonNegativeFiniteFloat | None
    clipped_path_length_um: NonNegativeFiniteFloat
    outside_atlas_path_length_um: NonNegativeFiniteFloat
    voxel_intervals: tuple[RegionTraversalVoxelInterval, ...]
    segments: tuple[RegionTraversalSegment, ...]
    site_assignments: tuple[RecordingSiteRegionAssignment, ...]

    @model_validator(mode="after")
    def validate_analysis_partition(self) -> Self:
        """Prove that voxel and region intervals partition the clipped segment."""

        expected_outside = self.total_path_length_um - self.clipped_path_length_um
        if not math.isclose(
            self.outside_atlas_path_length_um,
            expected_outside,
            rel_tol=1e-12,
            abs_tol=1e-8,
        ):
            raise ValueError("outside-atlas length must equal total minus clipped length")
        if self.intersects_atlas:
            if self.clipped_entry_depth_um is None or self.clipped_exit_depth_um is None:
                raise ValueError("intersecting analyses require both clipped depth endpoints")
            if not self.voxel_intervals or not self.segments:
                raise ValueError("an atlas intersection must contain voxel and region intervals")
        else:
            if self.clipped_entry_depth_um is not None or self.clipped_exit_depth_um is not None:
                raise ValueError("non-intersecting analyses cannot have clipped depth endpoints")
            if self.voxel_intervals or self.segments or self.clipped_path_length_um != 0:
                raise ValueError("non-intersecting analyses cannot contain traversal intervals")

        _validate_depth_partition(
            self.voxel_intervals,
            label="voxel",
            clipped_entry_depth_um=self.clipped_entry_depth_um,
            clipped_exit_depth_um=self.clipped_exit_depth_um,
            clipped_path_length_um=self.clipped_path_length_um,
        )
        _validate_depth_partition(
            self.segments,
            label="region",
            clipped_entry_depth_um=self.clipped_entry_depth_um,
            clipped_exit_depth_um=self.clipped_exit_depth_um,
            clipped_path_length_um=self.clipped_path_length_um,
        )

        site_keys = [(site.shank_id, site.site_id) for site in self.site_assignments]
        if len(site_keys) != len(set(site_keys)):
            raise ValueError("recording-site assignments must be unique per shank and site")
        return self


def _validate_depth_partition(
    intervals: tuple[_DepthInterval, ...],
    *,
    label: str,
    clipped_entry_depth_um: float | None,
    clipped_exit_depth_um: float | None,
    clipped_path_length_um: float,
) -> None:
    if not intervals:
        return
    if not math.isclose(
        intervals[0].entry_depth_um,
        clipped_entry_depth_um or 0,
        rel_tol=1e-12,
        abs_tol=1e-8,
    ):
        raise ValueError(f"{label} intervals must begin at the clipped entry")
    if not math.isclose(
        intervals[-1].exit_depth_um,
        clipped_exit_depth_um or 0,
        rel_tol=1e-12,
        abs_tol=1e-8,
    ):
        raise ValueError(f"{label} intervals must end at the clipped exit")
    for previous, current in pairwise(intervals):
        if not math.isclose(
            previous.exit_depth_um,
            current.entry_depth_um,
            rel_tol=1e-12,
            abs_tol=1e-8,
        ):
            raise ValueError(f"{label} intervals must be contiguous")
    summed = math.fsum(interval.length_um for interval in intervals)
    if not math.isclose(
        summed,
        clipped_path_length_um,
        rel_tol=1e-12,
        abs_tol=1e-8,
    ):
        raise ValueError(f"{label} interval lengths must sum to clipped path length")
