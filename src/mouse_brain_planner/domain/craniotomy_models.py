"""Validated planar skull/surface and craniotomy geometry models."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mouse_brain_planner.domain.surgery_common import (
    AnimalSurgeryContext,
    FiniteFloat,
    NonNegativeFiniteFloat,
    PositiveFiniteFloat,
    UnitDirectionAPMLDV,
)
from mouse_brain_planner.domain.transform_models import AnatomicalPoint


class SurfaceSource(StrEnum):
    """Provenance of the plane used to place a craniotomy."""

    SUBJECT_SKULL_MESH = "subject-skull-mesh"
    SUBJECT_MRI_SURFACE = "subject-mri-surface"
    USER_DEFINED_PLANAR_SKULL_APPROXIMATION = "user-defined-planar-skull-approximation"
    ATLAS_BRAIN_SURFACE = "atlas-brain-surface"
    DORSAL_CORTICAL_SURFACE = "dorsal-cortical-surface"


class SkullIntersectionQuality(StrEnum):
    """Whether skull geometry is subject-specific or explicitly approximate."""

    SUBJECT_SPECIFIC_SURFACE = "subject-specific-surface"
    APPROXIMATION = "approximation-no-subject-skull-model"


class PlannedOpeningKind(StrEnum):
    """Purpose of one planar opening/exclusion footprint."""

    BURR_HOLE = "burr-hole"
    CRANIOTOMY = "craniotomy"
    DUROTOMY = "durotomy"
    HEADPOST_EXCLUSION = "headpost-exclusion"
    IMPLANT_BASE = "implant-base"
    CEMENT_FOOTPRINT = "cement-footprint"


class PlanarPoint(BaseModel):
    """AP/ML offsets in one named surface plane, in micrometres."""

    model_config = ConfigDict(frozen=True)

    ap_um: FiniteFloat
    ml_um: FiniteFloat
    component_order: tuple[Literal["AP"], Literal["ML"]] = ("AP", "ML")
    units: Literal["micrometre"] = "micrometre"

    def as_ap_ml(self) -> tuple[float, float]:
        """Return the documented plane component order."""

        return (self.ap_um, self.ml_um)


class SurfacePlane(BaseModel):
    """One orthonormal AP/ML plane embedded in an anatomical frame."""

    model_config = ConfigDict(frozen=True)

    plane_id: str = Field(min_length=1, max_length=200)
    source: SurfaceSource
    source_asset_id: str | None = Field(default=None, min_length=1, max_length=500)
    origin: AnatomicalPoint
    ap_axis: UnitDirectionAPMLDV
    ml_axis: UnitDirectionAPMLDV
    registration_residual_um: NonNegativeFiniteFloat | None = None
    provenance: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_plane_frame_and_axes(self) -> Self:
        """Require matching frames and an orthonormal in-plane basis."""

        if (
            self.ap_axis.frame_id != self.origin.frame_id
            or self.ml_axis.frame_id != self.origin.frame_id
        ):
            raise ValueError("surface origin and AP/ML axes must use one explicit frame")
        dot = sum(
            ap * ml
            for ap, ml in zip(
                self.ap_axis.as_ap_ml_dv(),
                self.ml_axis.as_ap_ml_dv(),
                strict=True,
            )
        )
        if not math.isclose(dot, 0.0, rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"surface AP and ML axes must be orthogonal; dot product is {dot:g}")
        subject_specific = self.source in {
            SurfaceSource.SUBJECT_SKULL_MESH,
            SurfaceSource.SUBJECT_MRI_SURFACE,
        }
        if subject_specific and self.source_asset_id is None:
            raise ValueError("subject-specific surface plane requires a source asset ID")
        if subject_specific and self.registration_residual_um is None:
            raise ValueError("subject-specific surface plane requires registration residual")
        return self


class CircularOpening(BaseModel):
    """Circular opening/footprint in a surface plane."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["circle"] = "circle"
    center: PlanarPoint
    diameter_um: PositiveFiniteFloat


class EllipticalOpening(BaseModel):
    """Rotated ellipse with full AP and ML diameters."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["ellipse"] = "ellipse"
    center: PlanarPoint
    ap_diameter_um: PositiveFiniteFloat
    ml_diameter_um: PositiveFiniteFloat
    rotation_deg: FiniteFloat = Field(default=0, ge=-180, le=180)


class RectangularOpening(BaseModel):
    """Rotated rectangle with AP length and ML width."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["rectangle"] = "rectangle"
    center: PlanarPoint
    ap_length_um: PositiveFiniteFloat
    ml_width_um: PositiveFiniteFloat
    rotation_deg: FiniteFloat = Field(default=0, ge=-180, le=180)


class PolygonalOpening(BaseModel):
    """Simple custom polygon in a surface plane."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["polygon"] = "polygon"
    vertices: tuple[PlanarPoint, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_simple_polygon(self) -> Self:
        """Reject duplicate, zero-area, and self-intersecting polygons."""

        values = tuple(vertex.as_ap_ml() for vertex in self.vertices)
        if len(set(values)) != len(values):
            raise ValueError("polygon vertices must be unique")
        count = len(values)
        for first_index in range(count):
            first_start = values[first_index]
            first_end = values[(first_index + 1) % count]
            for second_index in range(first_index + 1, count):
                if second_index in {
                    first_index,
                    (first_index + 1) % count,
                    (first_index - 1) % count,
                }:
                    continue
                second_start = values[second_index]
                second_end = values[(second_index + 1) % count]
                if _segments_intersect(first_start, first_end, second_start, second_end):
                    raise ValueError("polygon boundary must not self-intersect")
        twice_area = sum(
            first[0] * second[1] - second[0] * first[1]
            for first, second in zip(values, values[1:] + values[:1], strict=True)
        )
        if abs(twice_area) <= 1e-9:
            raise ValueError("polygon must have non-zero area")
        return self


type OpeningGeometry = Annotated[
    CircularOpening | EllipticalOpening | RectangularOpening | PolygonalOpening,
    Field(discriminator="kind"),
]


class CraniotomyPlan(BaseModel):
    """One animal-only planar opening/exclusion plan with provenance."""

    model_config = ConfigDict(frozen=True)

    plan_uuid: UUID = Field(default_factory=uuid4)
    schema_version: Literal[1] = 1
    context: AnimalSurgeryContext
    name: str = Field(min_length=1, max_length=200)
    opening_kind: PlannedOpeningKind
    surface: SurfacePlane
    skull_intersection_quality: SkullIntersectionQuality
    geometry: OpeningGeometry
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_skull_quality_label(self) -> Self:
        """Prevent atlas/user-plane geometry from being labelled subject-specific."""

        subject_specific = self.surface.source in {
            SurfaceSource.SUBJECT_SKULL_MESH,
            SurfaceSource.SUBJECT_MRI_SURFACE,
        }
        expected = (
            SkullIntersectionQuality.SUBJECT_SPECIFIC_SURFACE
            if subject_specific
            else SkullIntersectionQuality.APPROXIMATION
        )
        if self.skull_intersection_quality is not expected:
            raise ValueError(
                f"surface source {self.surface.source.value!r} requires skull quality "
                f"{expected.value!r}"
            )
        return self

    @property
    def is_skull_approximation(self) -> bool:
        """Return the exact warning state required by reports and UI."""

        return self.skull_intersection_quality is SkullIntersectionQuality.APPROXIMATION


class CraniotomyMetrics(BaseModel):
    """Calculated dimensions for one opening/footprint."""

    model_config = ConfigDict(frozen=True)

    plan_uuid: UUID
    area_um2: PositiveFiniteFloat
    perimeter_um: PositiveFiniteFloat
    maximum_ap_span_um: PositiveFiniteFloat
    maximum_ml_span_um: PositiveFiniteFloat
    perimeter_method: str = Field(min_length=1, max_length=500)
    skull_intersection_quality: SkullIntersectionQuality
    units_length: Literal["micrometre"] = "micrometre"
    units_area: Literal["square-micrometre"] = "square-micrometre"


def _segments_intersect(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> bool:
    def orientation(
        first: tuple[float, float],
        second: tuple[float, float],
        third: tuple[float, float],
    ) -> float:
        return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (
            third[0] - first[0]
        )

    def on_segment(
        first: tuple[float, float],
        point: tuple[float, float],
        second: tuple[float, float],
    ) -> bool:
        return (
            min(first[0], second[0]) - 1e-12 <= point[0] <= max(first[0], second[0]) + 1e-12
            and min(first[1], second[1]) - 1e-12 <= point[1] <= max(first[1], second[1]) + 1e-12
        )

    orientations = (
        orientation(first_start, first_end, second_start),
        orientation(first_start, first_end, second_end),
        orientation(second_start, second_end, first_start),
        orientation(second_start, second_end, first_end),
    )
    if orientations[0] * orientations[1] < 0 and orientations[2] * orientations[3] < 0:
        return True
    return (
        (abs(orientations[0]) <= 1e-12 and on_segment(first_start, second_start, first_end))
        or (abs(orientations[1]) <= 1e-12 and on_segment(first_start, second_end, first_end))
        or (abs(orientations[2]) <= 1e-12 and on_segment(second_start, first_start, second_end))
        or (abs(orientations[3]) <= 1e-12 and on_segment(second_start, first_end, second_end))
    )
