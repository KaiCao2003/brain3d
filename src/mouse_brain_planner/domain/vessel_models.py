"""Validated models for subject-specific dorsal vasculature images.

The subject image and its derived registration are intentionally separate from
population reference vascular data.  Pixel coordinates use image columns and
rows; registered coordinates use BrainGlobe ASR physical axes in micrometres.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class SubjectImageFormat(StrEnum):
    """Supported byte-preserved input formats."""

    PNG = "png"
    JPEG = "jpeg"
    TIFF = "tiff"


class DorsalRegistrationMethod(StrEnum):
    """Supported planar landmark transforms."""

    SIMILARITY = "similarity"
    AFFINE = "affine"


class VascularLandmarkKind(StrEnum):
    """Landmark categories exposed by the registration workflow."""

    BREGMA = "bregma"
    LAMBDA = "lambda"
    MIDLINE = "midline"
    VESSEL_BIFURCATION = "vessel-bifurcation"
    CRANIOTOMY = "craniotomy"
    CUSTOM = "custom"


class SubjectVascularImage(BaseModel):
    """Provenance for one unchanged image copied into a project package."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    image_uuid: UUID = Field(default_factory=uuid4)
    original_name: str = Field(min_length=1, max_length=255)
    project_relative_path: str = Field(min_length=1, max_length=500)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(gt=0)
    image_format: SubjectImageFormat
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    frame_count: int = Field(default=1, gt=0)
    pixel_size_x_um: PositiveFiniteFloat | None = None
    pixel_size_y_um: PositiveFiniteFloat | None = None
    imported_at: datetime = Field(default_factory=utc_now)
    coordinate_frame: Literal["IMAGE_PIXEL_COLUMN_ROW"] = "IMAGE_PIXEL_COLUMN_ROW"
    coordinate_note: str = (
        "Pixel origin is the upper-left stored raster sample; column increases right and row "
        "increases down. No physical scale is inferred from DPI metadata."
    )
    subject_specific: Literal[True] = True

    @field_validator("original_name")
    @classmethod
    def validate_original_name(cls, value: str) -> str:
        """Store only a leaf name and reject control characters."""

        if value in {".", ".."} or any(ord(character) < 32 for character in value):
            raise ValueError("original image name must be a safe leaf name")
        if PurePosixPath(value).name != value or "\\" in value:
            raise ValueError("original image name must not contain a path")
        return value

    @field_validator("project_relative_path")
    @classmethod
    def validate_project_relative_path(cls, value: str) -> str:
        """Confine image members to one direct child of ``images/``.

        Keeping the package layout flat lets project I/O open both the
        ``images`` directory and the final file with ``openat`` plus
        ``O_NOFOLLOW``.  That provides a race-resistant confinement boundary
        instead of relying on string normalization alone.
        """

        path = PurePosixPath(value)
        if path.is_absolute() or not path.parts or path.parts[0] != "images":
            raise ValueError("subject image path must be relative to images/")
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("subject image path must not traverse directories")
        if len(path.parts) != 2 or "\\" in path.parts[1]:
            raise ValueError("subject image path must be a direct file in images/")
        if path.as_posix() != value or any(ord(character) < 32 for character in value):
            raise ValueError("subject image path must use canonical printable POSIX spelling")
        return value

    @model_validator(mode="after")
    def validate_pixel_size_pair(self) -> Self:
        """Require both calibrated pixel dimensions or neither."""

        if (self.pixel_size_x_um is None) != (self.pixel_size_y_um is None):
            raise ValueError("pixel size requires both x and y micrometre values")
        return self

    @property
    def calibrated(self) -> bool:
        """Return whether an explicit physical pixel scale was supplied."""

        return self.pixel_size_x_um is not None and self.pixel_size_y_um is not None


class DorsalVascularLandmark(BaseModel):
    """One image-to-atlas planar landmark correspondence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    landmark_uuid: UUID = Field(default_factory=uuid4)
    label: str = Field(min_length=1, max_length=200)
    kind: VascularLandmarkKind
    image_column_px: FiniteFloat
    image_row_px: FiniteFloat
    atlas_ap_um: FiniteFloat
    atlas_ml_um: FiniteFloat
    enabled: bool = True


class LandmarkResidual(BaseModel):
    """Residual for one enabled landmark in destination micrometres."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    landmark_uuid: UUID
    ap_error_um: FiniteFloat
    ml_error_um: FiniteFloat
    radial_error_um: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class DorsalVascularRegistration(BaseModel):
    """Versioned planar mapping from image pixels to exact atlas ASR AP/ML."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    registration_uuid: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, gt=0)
    image_uuid: UUID
    atlas_key: str = Field(min_length=1)
    atlas_version: str = Field(min_length=1)
    method: DorsalRegistrationMethod
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
    ]
    landmarks: tuple[DorsalVascularLandmark, ...]
    residuals: tuple[LandmarkResidual, ...]
    rms_residual_um: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    max_residual_um: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    determinant: FiniteFloat
    redundant_control_points: bool
    laterality_confirmed_by_user: bool = False
    laterality_warning: Literal[
        "Image laterality is unverified until the user confirms left/right orientation"
    ] = "Image laterality is unverified until the user confirms left/right orientation"
    created_at: datetime = Field(default_factory=utc_now)
    destination_frame: Literal["BRAINGLOBE_DORSAL_PLANE_AP_ML_UM"] = (
        "BRAINGLOBE_DORSAL_PLANE_AP_ML_UM"
    )
    coordinate_note: str = (
        "Maps [image column px, image row px, 1] to [atlas AP µm, atlas ML µm, 1]. "
        "BrainGlobe ASR AP increases posterior and ML increases left."
    )
    subject_specific: Literal[True] = True

    @property
    def permits_final_export(self) -> bool:
        """Return whether the explicit laterality gate has been satisfied.

        Residual acceptability remains protocol-specific and must be reviewed
        separately; this property deliberately makes no accuracy claim.
        """

        return self.laterality_confirmed_by_user

    @model_validator(mode="after")
    def validate_registration_contract(self) -> Self:
        """Reject malformed homogeneous transforms and inconsistent residuals."""

        matrix = self.matrix_row_major
        tolerance = 1e-9
        if any(
            abs(actual - expected) > tolerance
            for actual, expected in zip(matrix[6:], (0, 0, 1), strict=True)
        ):
            raise ValueError("registration matrix must end with homogeneous row [0, 0, 1]")
        enabled_ids = {landmark.landmark_uuid for landmark in self.landmarks if landmark.enabled}
        residual_ids = {residual.landmark_uuid for residual in self.residuals}
        if enabled_ids != residual_ids:
            raise ValueError("registration residuals must cover every enabled landmark exactly")
        if len(residual_ids) != len(self.residuals):
            raise ValueError("registration residuals contain duplicate landmark IDs")
        if not math.isclose(
            self.max_residual_um,
            max((item.radial_error_um for item in self.residuals), default=0.0),
            rel_tol=1e-10,
            abs_tol=1e-8,
        ):
            raise ValueError("maximum residual does not match landmark residuals")
        return self


class SubjectVascularOverlayState(BaseModel):
    """Project-local display state for a registered subject image."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    image_uuid: UUID
    registration_uuid: UUID | None = None
    visible: bool = False
    opacity: Annotated[float, Field(default=0.65, ge=0, le=1, allow_inf_nan=False)]
    dorsal_plane_dv_um: FiniteFloat | None = None
    segmentation_visible: bool = False
    segmentation_unverified: Literal[True] = True
    display_label: Literal["Subject-specific surface image — registration must be verified"] = (
        "Subject-specific surface image — registration must be verified"
    )


class ReferenceVascularDensityProjectState(BaseModel):
    """Persisted provenance and display state for the reviewed density field.

    The in-memory density object contains a NumPy array and dataclass graph, so
    it is deliberately not serialized through Pydantic.  This compact model
    pins the source and the safety-relevant conversion evidence without ever
    representing the scalar field as subject-specific vessel paths.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_atlas_key: str = Field(min_length=1)
    target_atlas_version: str = Field(min_length=1)
    target_atlas_metadata_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    source_doi: Literal["10.17632/stxvn5sv44.1"] = "10.17632/stxvn5sv44.1"
    source_version: Literal[1] = 1
    source_download_url: Literal[
        "https://data.mendeley.com/public-files/datasets/stxvn5sv44/files/"
        "10accc6f-e41f-4c0f-b6d5-9ca2af9db74a/file_downloaded"
    ] = (
        "https://data.mendeley.com/public-files/datasets/stxvn5sv44/files/"
        "10accc6f-e41f-4c0f-b6d5-9ca2af9db74a/file_downloaded"
    )
    source_archive_sha256: Literal[
        "c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe"
    ] = "c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe"
    density_member_sha256: Literal[
        "0a0cbdf62068783259a7f11f1e6f2992c57ff1678d0481c2ea36d64899ed4484"
    ] = "0a0cbdf62068783259a7f11f1e6f2992c57ff1678d0481c2ea36d64899ed4484"
    template_member_sha256: Literal[
        "3d3004f0de9410f6cadfd93ac08d78aaf4a2c504fd2c07275bd5064b6b0a7e0a"
    ] = "3d3004f0de9410f6cadfd93ac08d78aaf4a2c504fd2c07275bd5064b6b0a7e0a"
    density_value_units: Literal["m/mm^3"] = "m/mm^3"
    rolling_window_um: PositiveFiniteFloat = 100.0
    population_subject_count: Literal[4] = 4
    output_shape_asr: tuple[int, int, int]
    output_voxel_size_um: PositiveFiniteFloat = 50.0
    template_correlation: Annotated[float, Field(ge=0.99, le=1, allow_inf_nan=False)]
    minimum_template_correlation: Annotated[
        float,
        Field(gt=0, le=1, allow_inf_nan=False),
    ] = 0.99
    ap_axis_reversed: Literal[True] = True
    ml_symmetrized: Literal[True] = True
    ml_symmetrization_reason: Literal["source ML polarity is not documented"] = (
        "source ML polarity is not documented"
    )
    preparation_algorithm: Literal["stxvn5sv44-v1-asr-50um-linear-ml-sym-v1"] = (
        "stxvn5sv44-v1-asr-50um-linear-ml-sym-v1"
    )
    prepared_density_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    subject_specific: Literal[False] = False
    contains_individual_vessel_paths: Literal[False] = False
    supports_vessel_clearance: Literal[False] = False
    visible: bool = False
    opacity: Annotated[float, Field(default=0.65, ge=0, le=1, allow_inf_nan=False)]
    display_label: Literal[
        "Population reference vascular length density — not subject-specific vessel paths"
    ] = "Population reference vascular length density — not subject-specific vessel paths"

    @field_validator("output_shape_asr")
    @classmethod
    def validate_output_shape(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        """Reject empty or malformed prepared grids."""

        if any(size <= 0 for size in value):
            raise ValueError("reference density output shape must be positive")
        return value

    @field_validator("rolling_window_um")
    @classmethod
    def validate_pinned_rolling_window(cls, value: float) -> float:
        """Keep the persisted source contract pinned to the reviewed deposit."""

        if value != 100.0:
            raise ValueError("reference density rolling window must be exactly 100 µm")
        return value

    @field_validator("minimum_template_correlation")
    @classmethod
    def validate_pinned_minimum_correlation(cls, value: float) -> float:
        """Keep the persisted alignment acceptance gate pinned at 0.99."""

        if value != 0.99:
            raise ValueError("reference density minimum template correlation must equal 0.99")
        return value

    @model_validator(mode="after")
    def validate_visible_opacity(self) -> Self:
        """Reject a display marked visible while its maximum alpha is zero."""

        if self.visible and self.opacity <= 0:
            raise ValueError("visible reference density requires positive opacity")
        return self
