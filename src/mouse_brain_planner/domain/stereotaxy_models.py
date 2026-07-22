"""Validated bregma/lambda skull-calibration models."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mouse_brain_planner.domain.surgery_common import (
    AnimalSurgeryContext,
    FiniteFloat,
    NonNegativeFiniteFloat,
    PositiveFiniteFloat,
)
from mouse_brain_planner.domain.transform_models import (
    AnatomicalFrameDefinition,
    AnatomicalPoint,
    AnatomicalTransform,
)


class DorsoventralReference(StrEnum):
    """Explicit zero-reference choices for user-facing DV values."""

    BREGMA = "bregma"
    SKULL_SURFACE_AT_INSERTION = "skull-surface-at-insertion"
    BRAIN_SURFACE_AT_INSERTION = "brain-surface-at-insertion"
    ATLAS_DORSAL_BOUNDARY = "atlas-dorsal-boundary"
    USER_DEFINED_REFERENCE_PLANE = "user-defined-reference-plane"


class CalibrationQuality(StrEnum):
    """Result of user-configured numerical calibration checks."""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class SkullLandmarkSet(BaseModel):
    """Four measured landmarks sufficient to define a full rigid skull frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bregma: AnatomicalPoint
    lambda_point: AnatomicalPoint
    left_skull: AnatomicalPoint
    right_skull: AnatomicalPoint
    reported_bregma_lambda_distance_um: PositiveFiniteFloat
    laterality_confirmed_from_the_animal: Literal[True]

    @model_validator(mode="after")
    def validate_landmark_frames_and_identity(self) -> Self:
        """Require one frame and four distinct locations."""

        points = (self.bregma, self.lambda_point, self.left_skull, self.right_skull)
        frame_ids = {point.frame_id for point in points}
        if len(frame_ids) != 1:
            raise ValueError("all skull landmarks must use the same explicit source frame")
        coordinates = {point.as_ap_ml_dv() for point in points}
        if len(coordinates) != len(points):
            raise ValueError("bregma, lambda, left-skull, and right-skull points must be distinct")
        return self


class CalibrationQualityLimits(BaseModel):
    """User/lab-selected QC limits; no surgical threshold is silently invented."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum_axis_baseline_um: PositiveFiniteFloat
    distance_warning_um: PositiveFiniteFloat
    distance_failure_um: PositiveFiniteFloat
    lateral_ap_warning_um: PositiveFiniteFloat
    lateral_ap_failure_um: PositiveFiniteFloat
    transform_rms_warning_um: PositiveFiniteFloat
    transform_rms_failure_um: PositiveFiniteFloat

    @model_validator(mode="after")
    def validate_warning_failure_order(self) -> Self:
        """A warning threshold must be strictly below its failure threshold."""

        pairs = (
            ("distance", self.distance_warning_um, self.distance_failure_um),
            ("lateral AP", self.lateral_ap_warning_um, self.lateral_ap_failure_um),
            (
                "transform RMS",
                self.transform_rms_warning_um,
                self.transform_rms_failure_um,
            ),
        )
        for label, warning, failure in pairs:
            if warning >= failure:
                raise ValueError(f"{label} warning limit must be below failure limit")
        return self


class SkullLevelingAngles(BaseModel):
    """Euler angles of the source-to-stereotaxic rigid rotation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pitch_deg: FiniteFloat = Field(ge=-90, le=90)
    roll_deg: FiniteFloat = Field(ge=-180, le=180)
    yaw_deg: FiniteFloat = Field(ge=-180, le=180)
    convention: Literal[
        "R_DV(yaw) @ R_ML(pitch) @ R_AP(roll); source AP/ML/DV to leveled AP/ML/DV"
    ] = "R_DV(yaw) @ R_ML(pitch) @ R_AP(roll); source AP/ML/DV to leveled AP/ML/DV"


class CalibrationQCResult(BaseModel):
    """Exact residual metrics and messages for a fitted calibration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quality: CalibrationQuality
    geometric_bregma_lambda_distance_um: PositiveFiniteFloat
    reported_bregma_lambda_distance_um: PositiveFiniteFloat
    bregma_lambda_distance_error_um: NonNegativeFiniteFloat
    lateral_landmark_ap_mismatch_um: NonNegativeFiniteFloat
    lateral_landmark_dv_mismatch_um: NonNegativeFiniteFloat
    transform_rms_residual_um: NonNegativeFiniteFloat
    transform_max_residual_um: NonNegativeFiniteFloat
    messages: tuple[str, ...]
    limits_source: str = Field(min_length=1, max_length=1000)


class StereotaxicCalibration(BaseModel):
    """Versioned animal skull calibration with an explicit rigid transform."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    calibration_uuid: UUID = Field(default_factory=uuid4)
    schema_version: Literal[1] = 1
    profile_id: str = Field(min_length=1, max_length=200)
    context: AnimalSurgeryContext
    source_frame: AnatomicalFrameDefinition
    stereotaxic_frame: AnatomicalFrameDefinition
    landmarks: SkullLandmarkSet
    dv_reference: DorsoventralReference
    dv_reference_description: str = Field(min_length=1, max_length=1000)
    transform: AnatomicalTransform
    leveling_angles: SkullLevelingAngles
    quality_limits: CalibrationQualityLimits
    qc: CalibrationQCResult
    method: Literal["rigid-bregma-lambda-left-right-skull-landmark-leveling-v1"] = (
        "rigid-bregma-lambda-left-right-skull-landmark-leveling-v1"
    )
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_calibration_contract(self) -> Self:
        """Keep duplicated frame and residual metadata internally consistent."""

        if self.transform.source_frame != self.source_frame:
            raise ValueError("calibration transform source frame does not match calibration")
        if self.transform.destination_frame != self.stereotaxic_frame:
            raise ValueError("calibration transform destination frame does not match calibration")
        if self.landmarks.bregma.frame_id != self.source_frame.frame_id:
            raise ValueError("skull landmark frame does not match calibration source frame")
        if self.qc.transform_rms_residual_um != self.transform.rms_residual_um:
            raise ValueError("calibration QC RMS does not match transform residual")
        if self.qc.transform_max_residual_um != self.transform.max_residual_um:
            raise ValueError("calibration QC maximum does not match transform residual")
        return self

    @property
    def permits_planning(self) -> bool:
        """Fail closed when configured calibration checks failed."""

        return self.qc.quality is not CalibrationQuality.FAIL

    @property
    def permits_final_export(self) -> bool:
        """A failed calibration cannot be used at a final export boundary."""

        return self.permits_planning and self.transform.permits_final_export


class AtlasRegisteredCalibration(BaseModel):
    """Versioned subject calibration with an explicit stereotaxic-to-atlas fit.

    ``skull_calibration`` levels user-measured skull coordinates into the
    bregma-relative stereotaxic frame. ``atlas_transform`` is a separate,
    landmark-fitted boundary into the exact anterior/right/dorsal-positive
    canonical frame for one atlas package. Neither boundary contains a built-in
    bregma voxel or reference-animal constant.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    calibration_version: int = Field(gt=0)
    skull_calibration: StereotaxicCalibration
    atlas_transform: AnatomicalTransform
    atlas_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["subject-calibrated"] = "subject-calibrated"
    algorithm_version: Literal["subject-skull-and-atlas-landmark-fit-v1"] = (
        "subject-skull-and-atlas-landmark-fit-v1"
    )

    @field_validator("calibration_version", mode="before")
    @classmethod
    def reject_boolean_version(cls, value: object) -> object:
        """Do not let a JSON boolean silently become calibration version one."""

        if isinstance(value, bool):
            raise ValueError("calibration version must be an integer, not a boolean")
        return value

    @model_validator(mode="after")
    def validate_registered_boundary(self) -> Self:
        """Keep both fitted transforms and their versions/frames coherent."""

        calibration = self.skull_calibration
        if calibration.transform.version != self.calibration_version:
            raise ValueError("skull calibration transform version does not match calibration")
        if self.atlas_transform.version != self.calibration_version:
            raise ValueError("atlas transform version does not match calibration")
        if self.atlas_transform.source_frame != calibration.stereotaxic_frame:
            raise ValueError("atlas transform source is not the calibrated stereotaxic frame")
        destination = self.atlas_transform.destination_frame
        if destination.kind.value != "atlas":
            raise ValueError("calibration atlas transform destination must be an atlas frame")
        if destination.atlas_key is None or destination.atlas_version is None:
            raise ValueError("calibration atlas transform requires exact atlas identity")
        expected_frame_id = (
            f"ATLAS_CANONICAL_AP_ML_DV_UM:{destination.atlas_key}:{destination.atlas_version}"
        )
        if destination.frame_id != expected_frame_id:
            raise ValueError("calibration atlas transform is not in the canonical atlas frame")
        if not destination.ap_positive_direction.startswith("anterior") or not (
            destination.ml_positive_direction.startswith("right")
            and destination.dv_positive_direction.startswith("dorsal/up")
        ):
            raise ValueError("calibration atlas frame must be anterior/right/dorsal-positive")
        return self

    @property
    def calibration_uuid(self) -> UUID:
        """Return the stable UUID owned by the underlying subject calibration."""

        return self.skull_calibration.calibration_uuid

    @property
    def profile_id(self) -> str:
        """Return the user-visible version family identifier."""

        return self.skull_calibration.profile_id

    @property
    def effective_quality(self) -> CalibrationQuality:
        """Combine skull QC and atlas-fit RMS using the recorded lab limits."""

        calibration = self.skull_calibration
        if calibration.qc.quality is CalibrationQuality.FAIL:
            return CalibrationQuality.FAIL
        rms = self.atlas_transform.rms_residual_um
        limits = calibration.quality_limits
        if rms >= limits.transform_rms_failure_um:
            return CalibrationQuality.FAIL
        if (
            calibration.qc.quality is CalibrationQuality.WARNING
            or rms >= limits.transform_rms_warning_um
        ):
            return CalibrationQuality.WARNING
        return CalibrationQuality.PASS

    @property
    def permits_planning(self) -> bool:
        """Fail closed if either the skull or atlas-registration QC failed."""

        return self.effective_quality is not CalibrationQuality.FAIL

    @property
    def permits_final_export(self) -> bool:
        """Also require any affine distortion acknowledgment at export."""

        return self.permits_planning and self.atlas_transform.permits_final_export


def atlas_registered_calibration_sha256(calibration: AtlasRegisteredCalibration) -> str:
    """Hash the complete canonical calibration snapshot used by every consumer."""

    encoded = json.dumps(
        calibration.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class BregmaRelativeTargetMM(BaseModel):
    """Canonical direct implant target in calibrated bregma-relative millimetres.

    This type cannot be projected into atlas space on its own.  It carries the
    exact calibration/profile identity required by the conversion boundary, so
    an atlas anchor or a remembered bregma constant cannot be substituted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    context_uuid: UUID
    calibration_uuid: UUID
    profile_id: str = Field(min_length=1, max_length=200)
    stereotaxic_frame_id: str = Field(min_length=1, max_length=200)
    ap_mm: FiniteFloat
    ml_mm: FiniteFloat
    dv_mm: FiniteFloat
    ap_positive_direction: Literal["anterior"] = "anterior"
    ap_negative_direction: Literal["posterior/back"] = "posterior/back"
    ml_positive_direction: Literal["right"] = "right"
    ml_negative_direction: Literal["left"] = "left"
    dv_positive_direction: Literal["dorsal/up"] = "dorsal/up"
    dv_negative_direction: Literal["deep/ventral"] = "deep/ventral"
    dv_reference: Literal["bregma"] = "bregma"
    component_order: tuple[Literal["AP"], Literal["ML"], Literal["DV"]] = (
        "AP",
        "ML",
        "DV",
    )
    units: Literal["millimetre"] = "millimetre"
