"""Versioned, unit-explicit models for anatomical coordinate transforms.

Transform matrices in this module always multiply column vectors ordered
``[AP, ML, DV, 1]`` in micrometres.  A frame definition supplies the origin
and positive anatomical directions; a bare matrix or bare three-vector is not
a valid public value.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
type AnatomicalComponentOrder = tuple[Literal["AP"], Literal["ML"], Literal["DV"]]


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class CoordinateSystemKind(StrEnum):
    """Scientific coordinate-system categories kept distinct in exports."""

    ATLAS = "atlas"
    STEREOTAXIC = "stereotaxic"
    SKULL = "skull"
    SUBJECT = "subject"
    SURGERY_WORLD = "surgery-world"


class TransformMethod(StrEnum):
    """Supported or derived homogeneous-transform methods."""

    RIGID = "rigid"
    SIMILARITY = "similarity"
    AFFINE = "affine"
    COMPOSED = "composed"
    INVERSE = "inverse"


class AnatomicalFrameDefinition(BaseModel):
    """Definition of one named AP/ML/DV frame in micrometres."""

    model_config = ConfigDict(frozen=True)

    frame_id: str = Field(min_length=1, max_length=200)
    kind: CoordinateSystemKind
    origin_description: str = Field(min_length=1, max_length=1000)
    ap_positive_direction: str = Field(min_length=1, max_length=100)
    ml_positive_direction: str = Field(min_length=1, max_length=100)
    dv_positive_direction: str = Field(min_length=1, max_length=100)
    component_order: AnatomicalComponentOrder = ("AP", "ML", "DV")
    units: Literal["micrometre"] = "micrometre"
    atlas_key: str | None = None
    atlas_version: str | None = None

    @model_validator(mode="after")
    def validate_atlas_identity_pair(self) -> Self:
        """Require complete atlas identity for atlas frames and nowhere implicitly."""

        has_key = self.atlas_key is not None
        has_version = self.atlas_version is not None
        if has_key != has_version:
            raise ValueError("atlas frame identity requires both atlas key and version")
        if self.kind is CoordinateSystemKind.ATLAS and not has_key:
            raise ValueError("atlas coordinate frames require exact atlas identity")
        return self


class AnatomicalPoint(BaseModel):
    """One named-frame point with explicit anatomical components."""

    model_config = ConfigDict(frozen=True)

    frame_id: str = Field(min_length=1, max_length=200)
    ap_um: FiniteFloat
    ml_um: FiniteFloat
    dv_um: FiniteFloat
    component_order: AnatomicalComponentOrder = ("AP", "ML", "DV")
    units: Literal["micrometre"] = "micrometre"

    def as_ap_ml_dv(self) -> tuple[float, float, float]:
        """Return the documented component order for numerical operations."""

        return (self.ap_um, self.ml_um, self.dv_um)


class AnatomicalVector(BaseModel):
    """One named-frame direction or displacement; translation never applies."""

    model_config = ConfigDict(frozen=True)

    frame_id: str = Field(min_length=1, max_length=200)
    ap_um: FiniteFloat
    ml_um: FiniteFloat
    dv_um: FiniteFloat
    component_order: AnatomicalComponentOrder = ("AP", "ML", "DV")
    units: Literal["micrometre"] = "micrometre"

    def as_ap_ml_dv(self) -> tuple[float, float, float]:
        """Return the documented component order for numerical operations."""

        return (self.ap_um, self.ml_um, self.dv_um)


class LandmarkCorrespondence3D(BaseModel):
    """One explicitly paired source and destination landmark."""

    model_config = ConfigDict(frozen=True)

    landmark_uuid: UUID = Field(default_factory=uuid4)
    label: str = Field(min_length=1, max_length=200)
    source: AnatomicalPoint
    destination: AnatomicalPoint
    enabled: bool = True


class TransformLandmarkResidual(BaseModel):
    """Destination-frame residual for one enabled 3D landmark."""

    model_config = ConfigDict(frozen=True)

    landmark_uuid: UUID
    ap_error_um: FiniteFloat
    ml_error_um: FiniteFloat
    dv_error_um: FiniteFloat
    radial_error_um: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class AnatomicalTransform(BaseModel):
    """One validated versioned homogeneous transform in AP/ML/DV order."""

    model_config = ConfigDict(frozen=True)

    transform_uuid: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, gt=0)
    source_frame: AnatomicalFrameDefinition
    destination_frame: AnatomicalFrameDefinition
    method: TransformMethod
    matrix_row_major: tuple[
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
        FiniteFloat,
    ]
    landmarks: tuple[LandmarkCorrespondence3D, ...] = ()
    residuals: tuple[TransformLandmarkResidual, ...] = ()
    rms_residual_um: Annotated[float, Field(default=0, ge=0, allow_inf_nan=False)]
    max_residual_um: Annotated[float, Field(default=0, ge=0, allow_inf_nan=False)]
    affine_distortion_acknowledged: bool = False
    derived_from_transform_uuids: tuple[UUID, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)
    notes: str = Field(default="", max_length=4000)
    component_order: AnatomicalComponentOrder = ("AP", "ML", "DV")
    units: Literal["micrometre"] = "micrometre"

    @field_validator("matrix_row_major")
    @classmethod
    def validate_matrix(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        """Reject non-homogeneous, singular, or method-independent invalid matrices."""

        matrix = np.asarray(value, dtype=np.float64).reshape(4, 4)
        if not np.all(np.isfinite(matrix)):
            raise ValueError("transform matrix must be finite")
        if not np.allclose(matrix[3], (0, 0, 0, 1), rtol=0, atol=1e-10):
            raise ValueError("transform matrix must end with homogeneous row [0, 0, 0, 1]")
        determinant = float(np.linalg.det(matrix[:3, :3]))
        if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
            raise ValueError("transform linear component must be invertible")
        return value

    @model_validator(mode="after")
    def validate_transform_contract(self) -> Self:
        """Validate frame, method, residual, and distortion invariants."""

        if self.source_frame.frame_id == self.destination_frame.frame_id:
            raise ValueError("transform source and destination frames must differ")
        matrix = np.asarray(self.matrix_row_major, dtype=np.float64).reshape(4, 4)
        linear = matrix[:3, :3]
        gram = linear.T @ linear
        determinant = float(np.linalg.det(linear))
        if self.method is TransformMethod.RIGID:
            if not np.allclose(gram, np.eye(3), rtol=0, atol=1e-8) or not math.isclose(
                determinant,
                1.0,
                rel_tol=0,
                abs_tol=1e-8,
            ):
                raise ValueError("rigid transform must contain a proper unit rotation")
        elif self.method is TransformMethod.SIMILARITY:
            scale_squared = float(np.trace(gram) / 3.0)
            if (
                scale_squared <= 0
                or determinant <= 0
                or not np.allclose(
                    gram,
                    np.eye(3) * scale_squared,
                    rtol=1e-8,
                    atol=1e-8,
                )
            ):
                raise ValueError(
                    "similarity transform must contain a proper rotation and uniform scale"
                )

        enabled_ids = {item.landmark_uuid for item in self.landmarks if item.enabled}
        residual_ids = {item.landmark_uuid for item in self.residuals}
        if enabled_ids != residual_ids:
            raise ValueError("transform residuals must cover every enabled landmark exactly")
        if len(residual_ids) != len(self.residuals):
            raise ValueError("transform residuals contain duplicate landmark UUIDs")
        for landmark in self.landmarks:
            if landmark.source.frame_id != self.source_frame.frame_id:
                raise ValueError("landmark source frame does not match transform source")
            if landmark.destination.frame_id != self.destination_frame.frame_id:
                raise ValueError("landmark destination frame does not match transform destination")
        expected_maximum = max((item.radial_error_um for item in self.residuals), default=0.0)
        if not math.isclose(
            self.max_residual_um,
            expected_maximum,
            rel_tol=1e-10,
            abs_tol=1e-8,
        ):
            raise ValueError("maximum transform residual does not match landmark residuals")
        if self.method is not TransformMethod.AFFINE and self.affine_distortion_acknowledged:
            raise ValueError("affine distortion acknowledgment applies only to affine transforms")
        if self.method in {TransformMethod.COMPOSED, TransformMethod.INVERSE}:
            if not self.derived_from_transform_uuids:
                raise ValueError("derived transforms must identify their source transforms")
        elif self.derived_from_transform_uuids:
            raise ValueError("fitted transforms cannot claim derived transform UUIDs")
        return self

    @property
    def permits_final_export(self) -> bool:
        """Return whether the affine distortion warning has been acknowledged."""

        return self.method is not TransformMethod.AFFINE or self.affine_distortion_acknowledged

    @property
    def determinant(self) -> float:
        """Return the signed determinant of the linear component."""

        matrix = np.asarray(self.matrix_row_major, dtype=np.float64).reshape(4, 4)
        return float(np.linalg.det(matrix[:3, :3]))
