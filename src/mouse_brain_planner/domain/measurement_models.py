"""Serializable measurement results and vessel-geometry provenance guards."""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mouse_brain_planner.domain.surgery_common import (
    AnimalSurgeryContext,
    NonNegativeFiniteFloat,
)
from mouse_brain_planner.domain.transform_models import AnatomicalPoint


class LinearMeasurementKind(StrEnum):
    """Geometric meaning of a linear result."""

    POINT_TO_POINT = "point-to-point"
    POINT_TO_INFINITE_LINE = "point-to-infinite-line"
    POINT_TO_SEGMENT = "point-to-segment"
    PATH_LENGTH = "path-length"
    PROBE_CENTERLINE_TO_CENTERLINE = "probe-centerline-to-centerline"


class VesselGeometrySourceKind(StrEnum):
    """Sources that may or may not contain distance-capable vessel geometry."""

    SUBJECT_REGISTERED_3D_SEGMENTATION = "subject-registered-3d-segmentation"
    REFERENCE_INDIVIDUAL_VESSEL_GRAPH = "reference-individual-vessel-graph"
    SUBJECT_SURFACE_IMAGE_2D = "subject-surface-image-2d"
    POPULATION_REFERENCE_DENSITY = "population-reference-density"


class VesselDataRepresentation(StrEnum):
    """Scientific representation, kept separate from display styling."""

    POLYLINE_3D = "polyline-3d"
    SURFACE_IMAGE_2D = "surface-image-2d"
    SCALAR_DENSITY_VOLUME = "scalar-density-volume"


class VesselGeometryProvenance(BaseModel):
    """Provenance used to gate any vessel-distance calculation."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1, max_length=500)
    source_kind: VesselGeometrySourceKind
    representation: VesselDataRepresentation
    source_label: str = Field(min_length=1, max_length=1000)
    coordinate_frame_id: str = Field(min_length=1, max_length=200)
    subject_id: str | None = Field(default=None, min_length=1, max_length=200)
    registration_id: str | None = Field(default=None, min_length=1, max_length=500)
    registration_residual_um: NonNegativeFiniteFloat | None = None
    physical_scale_calibrated: bool
    geometry_reviewed_by_user: bool
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_source_representation(self) -> Self:
        """Keep source claims, dimensionality, and registration evidence aligned."""

        if self.source_kind is VesselGeometrySourceKind.SUBJECT_REGISTERED_3D_SEGMENTATION:
            if self.representation is not VesselDataRepresentation.POLYLINE_3D:
                raise ValueError("subject 3-D vessel segmentation requires 3-D polyline geometry")
            if self.subject_id is None or self.registration_id is None:
                raise ValueError(
                    "subject 3-D vessel geometry requires subject and registration IDs"
                )
            if self.registration_residual_um is None:
                raise ValueError("subject 3-D vessel geometry requires registration residual")
        elif self.source_kind is VesselGeometrySourceKind.REFERENCE_INDIVIDUAL_VESSEL_GRAPH:
            if self.representation is not VesselDataRepresentation.POLYLINE_3D:
                raise ValueError("reference individual-vessel graph requires 3-D polyline geometry")
            if self.subject_id is not None:
                raise ValueError(
                    "reference vessel graph must not claim the planned animal subject ID"
                )
            if self.registration_id is None or self.registration_residual_um is None:
                raise ValueError(
                    "reference vessel graph requires explicit registration ID and residual"
                )
        elif self.source_kind is VesselGeometrySourceKind.SUBJECT_SURFACE_IMAGE_2D:
            if self.representation is not VesselDataRepresentation.SURFACE_IMAGE_2D:
                raise ValueError("subject surface image must remain explicitly 2-D")
        elif self.representation is not VesselDataRepresentation.SCALAR_DENSITY_VOLUME:
            raise ValueError("population vascular density must remain a scalar density volume")
        elif self.subject_id is not None:
            raise ValueError("population vascular density must not claim a subject animal ID")
        return self


class VesselPolyline(BaseModel):
    """One explicitly registered 3-D vessel centerline polyline."""

    model_config = ConfigDict(frozen=True)

    vessel_id: str = Field(min_length=1, max_length=500)
    points: tuple[AnatomicalPoint, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_polyline(self) -> Self:
        """Require one frame and non-degenerate consecutive segments."""

        frame_id = self.points[0].frame_id
        if any(point.frame_id != frame_id for point in self.points):
            raise ValueError("all vessel polyline points must use one explicit frame")
        for first, second in pairwise(self.points):
            if first.as_ap_ml_dv() == second.as_ap_ml_dv():
                raise ValueError("vessel polyline cannot contain a zero-length segment")
        return self


class LinearMeasurement(BaseModel):
    """One unit-explicit linear geometric result."""

    model_config = ConfigDict(frozen=True)

    measurement_uuid: UUID = Field(default_factory=uuid4)
    context: AnimalSurgeryContext
    kind: LinearMeasurementKind
    value_um: NonNegativeFiniteFloat
    frame_id: str = Field(min_length=1, max_length=200)
    calculation_method: str = Field(min_length=1, max_length=1000)
    model_based_estimate: bool = False
    safety_determination: Literal[False] = False
    units: Literal["micrometre"] = "micrometre"


class AngularMeasurement(BaseModel):
    """Unsigned angle between two normalized trajectories."""

    model_config = ConfigDict(frozen=True)

    measurement_uuid: UUID = Field(default_factory=uuid4)
    context: AnimalSurgeryContext
    value_deg: NonNegativeFiniteFloat = Field(le=180)
    frame_id: str = Field(min_length=1, max_length=200)
    calculation_method: Literal["acos of clamped AP/ML/DV unit-vector dot product"] = (
        "acos of clamped AP/ML/DV unit-vector dot product"
    )
    model_based_estimate: Literal[True] = True
    safety_determination: Literal[False] = False
    units: Literal["degree"] = "degree"


class VesselDistanceMeasurement(BaseModel):
    """Nearest centerline distance with an unavoidable non-safety label."""

    model_config = ConfigDict(frozen=True)

    measurement_uuid: UUID = Field(default_factory=uuid4)
    context: AnimalSurgeryContext
    vessel_id: str = Field(min_length=1, max_length=500)
    distance_um: NonNegativeFiniteFloat
    trajectory_point: AnatomicalPoint
    vessel_point: AnatomicalPoint
    provenance: VesselGeometryProvenance
    subject_specific: bool
    interpretation: Literal[
        "subject-specific geometry distance; not a safety determination",
        "reference-only geometry distance; not subject-specific and not a safety determination",
    ]
    calculation_method: Literal[
        "exact minimum Euclidean distance between finite 3-D centerline segments"
    ] = "exact minimum Euclidean distance between finite 3-D centerline segments"
    model_based_estimate: Literal[True] = True
    safety_determination: Literal[False] = False
    units: Literal["micrometre"] = "micrometre"

    @model_validator(mode="after")
    def validate_interpretation(self) -> Self:
        """Prevent a reference graph from being serialized as subject-specific."""

        expected_subject_specific = (
            self.provenance.source_kind
            is VesselGeometrySourceKind.SUBJECT_REGISTERED_3D_SEGMENTATION
        )
        if self.subject_specific != expected_subject_specific:
            raise ValueError("vessel distance subject-specific flag contradicts provenance")
        expected_interpretation = (
            "subject-specific geometry distance; not a safety determination"
            if expected_subject_specific
            else (
                "reference-only geometry distance; not subject-specific and not a safety "
                "determination"
            )
        )
        if self.interpretation != expected_interpretation:
            raise ValueError("vessel distance interpretation contradicts provenance")
        if expected_subject_specific:
            if self.context.subject_id is None:
                raise ValueError(
                    "subject-specific vessel distance requires a subject ID in animal context"
                )
            if self.provenance.subject_id != self.context.subject_id:
                raise ValueError(
                    "subject-specific vessel geometry subject ID does not match animal context"
                )
        if self.trajectory_point.frame_id != self.provenance.coordinate_frame_id:
            raise ValueError("trajectory nearest point frame does not match vessel provenance")
        if self.vessel_point.frame_id != self.provenance.coordinate_frame_id:
            raise ValueError("vessel nearest point frame does not match vessel provenance")
        return self
