"""Validated atlas and region metadata contracts."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AtlasAxis(BaseModel):
    """Meaning of one BrainGlobe array axis."""

    model_config = ConfigDict(frozen=True)

    array_axis: Literal[0, 1, 2]
    anatomical_axis: Literal["AP", "DV", "ML"]
    origin_direction: Literal["anterior", "superior", "right"]
    positive_direction: Literal["posterior", "inferior", "left"]
    voxel_size_um: float = Field(gt=0, allow_inf_nan=False)


class AtlasMetadata(BaseModel):
    """Normalized metadata for one exact atlas package."""

    model_config = ConfigDict(frozen=True)

    atlas_key: str = Field(min_length=1)
    atlas_package_version: str = Field(min_length=1)
    species: str = Field(min_length=1)
    citation: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    cache_path: str = Field(min_length=1)
    metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolution_um: tuple[float, float, float]
    shape_voxels: tuple[int, int, int]
    standardized_orientation: Literal["asr"] = "asr"
    source_annotation: str | None = None
    framework_name: str = "Allen CCFv3"
    symmetric: bool
    axes: tuple[AtlasAxis, AtlasAxis, AtlasAxis]

    @field_validator("resolution_um")
    @classmethod
    def validate_resolution(cls, value: tuple[float, float, float]) -> tuple[float, float, float]:
        """Require exactly three positive finite voxel sizes."""

        if any(not 0 < component < float("inf") for component in value):
            raise ValueError("atlas resolution must contain three positive finite values")
        return value

    @field_validator("shape_voxels")
    @classmethod
    def validate_shape(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        """Require exactly three positive volume dimensions."""

        if any(component <= 0 for component in value):
            raise ValueError("atlas shape must contain three positive dimensions")
        return value

    @field_validator("axes")
    @classmethod
    def validate_axes(
        cls, value: tuple[AtlasAxis, AtlasAxis, AtlasAxis]
    ) -> tuple[AtlasAxis, AtlasAxis, AtlasAxis]:
        """Enforce the stable BrainGlobe ASR array contract."""

        expected = (
            (0, "AP", "anterior", "posterior"),
            (1, "DV", "superior", "inferior"),
            (2, "ML", "right", "left"),
        )
        actual = tuple(
            (
                axis.array_axis,
                axis.anatomical_axis,
                axis.origin_direction,
                axis.positive_direction,
            )
            for axis in value
        )
        if actual != expected:
            raise ValueError(f"expected BrainGlobe ASR axes {expected}, got {actual}")
        return value

    @model_validator(mode="after")
    def validate_axis_voxel_sizes(self) -> Self:
        """Require axis descriptors to repeat the canonical resolution exactly."""

        axis_sizes = tuple(axis.voxel_size_um for axis in self.axes)
        if axis_sizes != self.resolution_um:
            raise ValueError(
                "atlas axis voxel sizes must equal resolution_um; "
                f"got axes={axis_sizes}, resolution={self.resolution_um}"
            )
        return self

    @property
    def extent_um(self) -> tuple[float, float, float]:
        """Half-open physical extent ``shape * resolution`` in ASR order."""

        return tuple(
            float(size * resolution)
            for size, resolution in zip(self.shape_voxels, self.resolution_um, strict=True)
        )  # type: ignore[return-value]


class RegionRecord(BaseModel):
    """One atlas structure with hierarchy and source display color."""

    model_config = ConfigDict(frozen=True)

    structure_id: int = Field(gt=0)
    acronym: str = Field(min_length=1)
    name: str = Field(min_length=1)
    structure_id_path: tuple[int, ...] = Field(min_length=1)
    rgb: tuple[int, int, int]

    @field_validator("rgb")
    @classmethod
    def validate_rgb(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        """Require 8-bit RGB components."""

        if any(component < 0 or component > 255 for component in value):
            raise ValueError("region RGB components must be in [0, 255]")
        return value

    @property
    def parent_id(self) -> int | None:
        """Return the immediate parent structure identifier, if any."""

        return self.structure_id_path[-2] if len(self.structure_id_path) > 1 else None
