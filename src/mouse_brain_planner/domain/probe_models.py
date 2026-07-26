"""Source-traceable probe geometry and normalized placement models.

This module intentionally contains no built-in Neuropixels dimensions.  A
manufacturer model can be labelled verified only after the complete geometry
and source artifact pass the validation gate represented below.  Generic and
custom models remain explicitly user-defined/unverified.
"""

from __future__ import annotations

import math
from datetime import date
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mouse_brain_planner.domain.surgery_common import (
    AnimalSurgeryContext,
    FiniteFloat,
    NonNegativeFiniteFloat,
    PositiveFiniteFloat,
    UnitDirectionAPMLDV,
)
from mouse_brain_planner.domain.transform_models import AnatomicalPoint


class ProbeVerificationStatus(StrEnum):
    """Whether a geometry passed the full source/transcription review gate."""

    VERIFIED = "verified"
    SOURCE_TRANSCRIBED_REVIEW_PENDING = "source-transcribed-review-pending"
    USER_DEFINED_UNVERIFIED = "user-defined-unverified"


class ProbeSiteRole(StrEnum):
    """Known role of a recording-site coordinate."""

    RECORDING = "recording"
    REFERENCE = "reference"
    OTHER = "other"


class ProbeTipGeometry(StrEnum):
    """Explicit tip classification without inferred dimensions."""

    CHISEL = "chisel"
    FLAT = "flat"
    TRIANGULAR = "triangular"
    TAPERED = "tapered"
    USER_DEFINED = "user-defined"


class ProbeSourceArtifact(BaseModel):
    """Exact primary artifact used to transcribe factual geometry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=1, max_length=2000)
    document_revision: str = Field(min_length=1, max_length=200)
    retrieved_on: date
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    citation: str = Field(min_length=1, max_length=2000)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        """Require a stable HTTPS source instead of an unlabeled local recollection."""

        if not value.startswith("https://"):
            raise ValueError("probe primary source URL must use https")
        return value


class ProbeModelVerification(BaseModel):
    """Approval evidence controlling whether a model may be called verified."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ProbeVerificationStatus
    primary_sources: tuple[ProbeSourceArtifact, ...] = ()
    complete_geometry_transcribed: bool = False
    independent_transcription_review_completed: bool = False
    transcribed_by: str | None = Field(default=None, min_length=1, max_length=200)
    independently_reviewed_by: str | None = Field(default=None, min_length=1, max_length=200)
    review_notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_verification_gate(self) -> Self:
        """Fail closed when a payload claims verified status without evidence."""

        if self.status is ProbeVerificationStatus.VERIFIED:
            if not self.primary_sources:
                raise ValueError("verified probe model requires at least one primary source")
            if not self.complete_geometry_transcribed:
                raise ValueError("verified probe model requires complete geometry transcription")
            if not self.independent_transcription_review_completed:
                raise ValueError("verified probe model requires independent transcription review")
            if self.transcribed_by is None or self.independently_reviewed_by is None:
                raise ValueError("verified probe model requires named transcriber and reviewer")
            same_reviewer = (
                self.transcribed_by.strip().casefold()
                == self.independently_reviewed_by.strip().casefold()
            )
            if same_reviewer:
                raise ValueError("probe transcriber and independent reviewer must be different")
        elif self.status is ProbeVerificationStatus.SOURCE_TRANSCRIBED_REVIEW_PENDING:
            if not self.primary_sources:
                raise ValueError("source-transcribed probe model requires primary sources")
            if not self.complete_geometry_transcribed:
                raise ValueError(
                    "source-transcribed probe model requires complete geometry transcription"
                )
            if self.transcribed_by is None:
                raise ValueError("source-transcribed probe model requires a named transcriber")
            if self.independent_transcription_review_completed:
                raise ValueError(
                    "review-pending probe model cannot claim completed independent review"
                )
            if self.independently_reviewed_by is not None:
                raise ValueError(
                    "review-pending probe model cannot name an independent reviewer as completed"
                )
        return self


class ProbeLocalPoint(BaseModel):
    """Point in the documented probe-local frame, in micrometres.

    ``axial_from_tip_um`` is zero at the tip and increases toward the base.
    Lateral and normal offsets complete a right-handed local frame.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    axial_from_tip_um: NonNegativeFiniteFloat
    lateral_um: FiniteFloat = 0
    normal_um: FiniteFloat = 0
    units: Literal["micrometre"] = "micrometre"


class RecordingSiteDefinition(BaseModel):
    """One source-defined recording/reference site in probe-local coordinates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    site_id: str = Field(min_length=1, max_length=200)
    local: ProbeLocalPoint
    role: ProbeSiteRole = ProbeSiteRole.RECORDING
    bank: str | None = Field(default=None, min_length=1, max_length=200)


class ProbeShankDefinition(BaseModel):
    """One implantable planar shank and its complete local site table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shank_id: str = Field(min_length=1, max_length=200)
    length_um: PositiveFiniteFloat
    width_um: PositiveFiniteFloat
    thickness_um: PositiveFiniteFloat
    tip_geometry: ProbeTipGeometry
    tip_length_um: NonNegativeFiniteFloat
    center_lateral_um: FiniteFloat = 0
    center_normal_um: FiniteFloat = 0
    tip_geometry_notes: str = Field(min_length=1, max_length=1000)
    sites: tuple[RecordingSiteDefinition, ...] = ()

    @model_validator(mode="after")
    def validate_shank_geometry_and_sites(self) -> Self:
        """Keep all sites within the declared implantable shank envelope."""

        if self.tip_length_um >= self.length_um:
            raise ValueError("probe tip length must be shorter than shank length")
        site_ids = [site.site_id for site in self.sites]
        if len(site_ids) != len(set(site_ids)):
            raise ValueError(f"shank {self.shank_id!r} contains duplicate site IDs")
        half_width = self.width_um / 2.0
        half_thickness = self.thickness_um / 2.0
        for site in self.sites:
            if site.local.axial_from_tip_um > self.length_um:
                raise ValueError(
                    f"site {site.site_id!r} lies beyond declared shank length "
                    f"({site.local.axial_from_tip_um:g} > {self.length_um:g} micrometres)"
                )
            if abs(site.local.lateral_um) > half_width:
                raise ValueError(f"site {site.site_id!r} lies outside declared shank width")
            if abs(site.local.normal_um) > half_thickness:
                raise ValueError(f"site {site.site_id!r} lies outside declared shank thickness")
        return self


class ProbeModelDefinition(BaseModel):
    """Versioned, unit-explicit probe geometry with verification provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str = Field(min_length=1, max_length=200)
    model_version: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=300)
    manufacturer: str | None = Field(default=None, min_length=1, max_length=200)
    product_code: str | None = Field(default=None, min_length=1, max_length=200)
    hardware_revision: str | None = Field(default=None, min_length=1, max_length=200)
    verification: ProbeModelVerification
    declared_shank_count: int = Field(gt=0)
    expected_site_count: int | None = Field(default=None, ge=0)
    shanks: tuple[ProbeShankDefinition, ...] = Field(min_length=1)
    coordinate_origin: Literal["primary-shank-tip"] = "primary-shank-tip"
    local_axis_definition: Literal[
        "axial-from-tip-toward-base, lateral-right, normal-by-right-hand-rule"
    ] = "axial-from-tip-toward-base, lateral-right, normal-by-right-hand-rule"
    insertion_axis_definition: Literal["entry-toward-tip"] = "entry-toward-tip"
    units: Literal["micrometre"] = "micrometre"
    geometry_notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_model_geometry_and_identity(self) -> Self:
        """Validate counts, unique IDs, source identity, and verified completeness."""

        if len(self.shanks) != self.declared_shank_count:
            raise ValueError(
                f"declared shank count {self.declared_shank_count} does not match "
                f"{len(self.shanks)} shank definitions"
            )
        shank_ids = [shank.shank_id for shank in self.shanks]
        if len(shank_ids) != len(set(shank_ids)):
            raise ValueError("probe model contains duplicate shank IDs")
        all_site_ids = [site.site_id for shank in self.shanks for site in shank.sites]
        if len(all_site_ids) != len(set(all_site_ids)):
            raise ValueError("site IDs must be unique across the entire probe model")
        if self.expected_site_count is not None and self.expected_site_count != len(all_site_ids):
            raise ValueError(
                f"expected site count {self.expected_site_count} does not match "
                f"{len(all_site_ids)} encoded sites"
            )
        if self.verification.status is ProbeVerificationStatus.VERIFIED:
            if self.expected_site_count is None:
                raise ValueError("verified probe model requires an expected site count")
            missing = tuple(
                name
                for name, value in (
                    ("manufacturer", self.manufacturer),
                    ("product code", self.product_code),
                    ("hardware revision", self.hardware_revision),
                )
                if value is None
            )
            if missing:
                raise ValueError("verified probe model is missing exact " + ", ".join(missing))
        return self

    @property
    def permits_verified_device_label(self) -> bool:
        """Return whether UI/export may call this exact model verified."""

        return self.verification.status is ProbeVerificationStatus.VERIFIED


class PlacementMethod(StrEnum):
    """Input method normalized into one trajectory representation."""

    ENTRY_TARGET = "entry-plus-target"
    ENTRY_ANGLES_DEPTH = "entry-plus-angles-depth"
    TARGET_ANGLES_DEPTH = "target-plus-angles-depth"
    STEREOTAXIC_TARGET_MANIPULATOR = "stereotaxic-target-plus-manipulator-angles"
    ATLAS_SURFACE_AP_ML = "atlas-surface-ap-ml-plus-depth-angle-layout"


class NormalizedProbePlacement(BaseModel):
    """One normalized AP/ML/DV probe trajectory and surface intersections."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    placement_uuid: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    context: AnimalSurgeryContext
    probe_model_id: str = Field(min_length=1, max_length=200)
    probe_model_version: str = Field(min_length=1, max_length=100)
    method: PlacementMethod
    entry: AnatomicalPoint
    target: AnatomicalPoint
    tip: AnatomicalPoint
    skull_entry: AnatomicalPoint | None = None
    brain_entry: AnatomicalPoint | None = None
    inward_direction: UnitDirectionAPMLDV
    local_lateral_direction: UnitDirectionAPMLDV | None = None
    local_normal_direction: UnitDirectionAPMLDV | None = None
    model_to_placement_uniform_scale: PositiveFiniteFloat = 1.0
    insertion_depth_um: PositiveFiniteFloat
    azimuth_deg: FiniteFloat = Field(ge=-180, le=180)
    elevation_deg: FiniteFloat = Field(ge=-90, le=90)
    angle_convention: Literal[
        "azimuth about +DV from +AP toward +ML; elevation from AP-ML plane toward +DV"
    ] = "azimuth about +DV from +AP toward +ML; elevation from AP-ML plane toward +DV"
    axial_rotation_deg: FiniteFloat = Field(default=0, ge=-180, le=180)
    selected_site_ids: tuple[str, ...] = ()
    custom_geometry_acknowledged: bool = False
    visible: bool = True
    display_opacity: FiniteFloat = Field(default=1, ge=0, le=1)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_normalized_geometry(self) -> Self:
        """Reject frame mismatches and serialized direction/depth/angle drift."""

        points = tuple(
            point
            for point in (
                self.entry,
                self.target,
                self.tip,
                self.skull_entry,
                self.brain_entry,
            )
            if point is not None
        )
        if any(point.frame_id != self.entry.frame_id for point in points):
            raise ValueError("all placement coordinates must use one explicit frame")
        if self.inward_direction.frame_id != self.entry.frame_id:
            raise ValueError("placement direction frame does not match placement points")
        if (self.local_lateral_direction is None) != (self.local_normal_direction is None):
            raise ValueError(
                "placement local lateral and normal directions must be stored together"
            )
        if self.local_lateral_direction is not None and self.local_normal_direction is not None:
            local_directions = (
                self.local_lateral_direction,
                self.local_normal_direction,
            )
            if any(direction.frame_id != self.entry.frame_id for direction in local_directions):
                raise ValueError("placement local directions must use the placement frame")
            inward_vector = self.inward_direction.as_ap_ml_dv()
            lateral_vector = self.local_lateral_direction.as_ap_ml_dv()
            normal_vector = self.local_normal_direction.as_ap_ml_dv()
            dot_products = (
                sum(a * b for a, b in zip(inward_vector, lateral_vector, strict=True)),
                sum(a * b for a, b in zip(inward_vector, normal_vector, strict=True)),
                sum(a * b for a, b in zip(lateral_vector, normal_vector, strict=True)),
            )
            if any(not math.isclose(value, 0.0, rel_tol=0, abs_tol=1e-9) for value in dot_products):
                raise ValueError("placement local directions must form an orthonormal basis")
            # The probe convention defines normal = (-inward) x lateral.
            expected_normal = (
                -inward_vector[1] * lateral_vector[2] + inward_vector[2] * lateral_vector[1],
                -inward_vector[2] * lateral_vector[0] + inward_vector[0] * lateral_vector[2],
                -inward_vector[0] * lateral_vector[1] + inward_vector[1] * lateral_vector[0],
            )
            if any(
                not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-9)
                for actual, expected in zip(normal_vector, expected_normal, strict=True)
            ):
                raise ValueError("placement local basis does not follow the probe right-hand rule")
        if len(self.selected_site_ids) != len(set(self.selected_site_ids)):
            raise ValueError("selected recording-site IDs must be unique")

        entry = self.entry.as_ap_ml_dv()
        tip = self.tip.as_ap_ml_dv()
        vector = (
            tip[0] - entry[0],
            tip[1] - entry[1],
            tip[2] - entry[2],
        )
        depth = math.sqrt(sum(component * component for component in vector))
        tolerance = max(1e-6, self.insertion_depth_um * 1e-10)
        if not math.isclose(depth, self.insertion_depth_um, rel_tol=0, abs_tol=tolerance):
            raise ValueError(
                f"insertion depth {self.insertion_depth_um:g} does not match entry-tip "
                f"distance {depth:g} micrometres"
            )
        expected_direction = (
            vector[0] / depth,
            vector[1] / depth,
            vector[2] / depth,
        )
        actual_direction = self.inward_direction.as_ap_ml_dv()
        if any(
            not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-9)
            for actual, expected in zip(actual_direction, expected_direction, strict=True)
        ):
            raise ValueError("stored inward direction does not match entry-to-tip geometry")
        expected_azimuth, expected_elevation = _angles_from_direction(expected_direction)
        if not math.isclose(self.azimuth_deg, expected_azimuth, rel_tol=0, abs_tol=1e-8):
            raise ValueError("stored azimuth does not match normalized trajectory direction")
        if not math.isclose(self.elevation_deg, expected_elevation, rel_tol=0, abs_tol=1e-8):
            raise ValueError("stored elevation does not match normalized trajectory direction")

        target_distance = _signed_line_distance(self.entry, self.target, actual_direction)
        target_off_axis = _point_line_distance(self.entry, self.target, actual_direction)
        if target_off_axis > tolerance:
            raise ValueError(
                f"target is {target_off_axis:g} micrometres off the normalized trajectory"
            )
        if target_distance < -tolerance or target_distance > self.insertion_depth_um + tolerance:
            raise ValueError("target must lie between the normalized entry and tip")

        skull_distance = _optional_surface_distance(
            label="skull entry",
            origin=self.entry,
            point=self.skull_entry,
            direction=actual_direction,
            tolerance=tolerance,
        )
        brain_distance = _optional_surface_distance(
            label="brain entry",
            origin=self.entry,
            point=self.brain_entry,
            direction=actual_direction,
            tolerance=tolerance,
        )
        if skull_distance is not None and brain_distance is not None:
            if skull_distance > brain_distance + tolerance:
                raise ValueError("skull entry must occur before or at brain entry along insertion")
        for label, distance in (("skull entry", skull_distance), ("brain entry", brain_distance)):
            if distance is not None and distance > self.insertion_depth_um + tolerance:
                raise ValueError(f"{label} cannot occur beyond the probe tip")
        return self


class PlacedRecordingSite(BaseModel):
    """One local site mapped into the placement's anatomical frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    placement_uuid: UUID
    probe_model_id: str
    probe_model_version: str
    shank_id: str
    site_id: str
    role: ProbeSiteRole
    bank: str | None = None
    point: AnatomicalPoint


class PlacedProbeShank(BaseModel):
    """One placed shank with both the implanted path and full physical extent.

    ``entry`` remains the surface crossing used by region/vessel analysis and
    ``tip`` is the distal target.  ``proximal_end`` is the catalogued base end
    of the complete shank, which can lie outside the atlas.  Keeping those
    points separate prevents a renderer from mistaking insertion depth for the
    physical shank length.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    placement_uuid: UUID
    probe_model_id: str = Field(min_length=1, max_length=200)
    probe_model_version: str = Field(min_length=1, max_length=100)
    shank_id: str = Field(min_length=1, max_length=200)
    entry: AnatomicalPoint
    tip: AnatomicalPoint
    proximal_end: AnatomicalPoint
    length_um: PositiveFiniteFloat
    width_um: PositiveFiniteFloat
    thickness_um: PositiveFiniteFloat
    envelope_definition: Literal["circumscribed-radius-of-rectangular-cross-section"] = (
        "circumscribed-radius-of-rectangular-cross-section"
    )

    @model_validator(mode="after")
    def validate_shank(self) -> Self:
        if not (self.entry.frame_id == self.tip.frame_id == self.proximal_end.frame_id):
            raise ValueError(
                "placed shank surface entry, distal tip, and proximal end "
                "must use one explicit frame"
            )
        if self.entry.as_ap_ml_dv() == self.tip.as_ap_ml_dv():
            raise ValueError("placed shank entry and tip must be distinct")

        proximal = self.proximal_end.as_ap_ml_dv()
        surface = self.entry.as_ap_ml_dv()
        distal = self.tip.as_ap_ml_dv()
        full_axis = tuple(
            distal_value - proximal_value
            for distal_value, proximal_value in zip(distal, proximal, strict=True)
        )
        full_length = math.sqrt(sum(component * component for component in full_axis))
        tolerance = max(1e-6, self.length_um * 1e-10)
        if not math.isclose(full_length, self.length_um, rel_tol=0, abs_tol=tolerance):
            raise ValueError(
                f"placed shank length {self.length_um:g} does not match "
                f"proximal-to-tip distance {full_length:g} micrometres"
            )
        unit_axis = tuple(component / full_length for component in full_axis)
        proximal_to_surface = tuple(
            surface_value - proximal_value
            for surface_value, proximal_value in zip(surface, proximal, strict=True)
        )
        surface_distance = sum(
            component * axis for component, axis in zip(proximal_to_surface, unit_axis, strict=True)
        )
        surface_off_axis = math.sqrt(
            sum(
                (component - surface_distance * axis) ** 2
                for component, axis in zip(proximal_to_surface, unit_axis, strict=True)
            )
        )
        if surface_off_axis > tolerance:
            raise ValueError("placed shank surface entry is off the full physical centerline")
        if surface_distance < -tolerance or surface_distance > full_length + tolerance:
            raise ValueError(
                "placed shank surface entry must lie between proximal end and distal tip"
            )
        return self

    @property
    def conservative_envelope_radius_um(self) -> float:
        """Return the circumscribed radius used by conservative clearance."""

        return math.hypot(self.width_um / 2.0, self.thickness_um / 2.0)


def _angles_from_direction(direction: tuple[float, float, float]) -> tuple[float, float]:
    ap, ml, dv = direction
    horizontal = math.hypot(ap, ml)
    elevation = math.degrees(math.atan2(dv, horizontal))
    azimuth = 0.0 if horizontal <= 1e-12 else math.degrees(math.atan2(ml, ap))
    if math.isclose(azimuth, -180.0, rel_tol=0, abs_tol=1e-12):
        azimuth = 180.0
    return azimuth, elevation


def _signed_line_distance(
    origin: AnatomicalPoint,
    point: AnatomicalPoint,
    direction: tuple[float, float, float],
) -> float:
    delta = tuple(
        point_value - origin_value
        for origin_value, point_value in zip(origin.as_ap_ml_dv(), point.as_ap_ml_dv(), strict=True)
    )
    return sum(value * axis for value, axis in zip(delta, direction, strict=True))


def _point_line_distance(
    origin: AnatomicalPoint,
    point: AnatomicalPoint,
    direction: tuple[float, float, float],
) -> float:
    delta = tuple(
        point_value - origin_value
        for origin_value, point_value in zip(origin.as_ap_ml_dv(), point.as_ap_ml_dv(), strict=True)
    )
    projected = sum(value * axis for value, axis in zip(delta, direction, strict=True))
    residual = tuple(value - projected * axis for value, axis in zip(delta, direction, strict=True))
    return math.sqrt(sum(value * value for value in residual))


def _optional_surface_distance(
    *,
    label: str,
    origin: AnatomicalPoint,
    point: AnatomicalPoint | None,
    direction: tuple[float, float, float],
    tolerance: float,
) -> float | None:
    if point is None:
        return None
    off_axis = _point_line_distance(origin, point, direction)
    if off_axis > tolerance:
        raise ValueError(f"{label} is {off_axis:g} micrometres off the normalized trajectory")
    return _signed_line_distance(origin, point, direction)
