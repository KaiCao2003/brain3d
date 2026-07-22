"""Explicit coordinate point types.

The application does not pass undocumented three-element arrays between
subsystems.  Each type encodes axis order, frame, atlas identity, and units.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class Hemisphere(StrEnum):
    """Anatomical hemisphere classification."""

    LEFT = "left"
    RIGHT = "right"
    MIDLINE = "midline"


class VoxelAnchor(StrEnum):
    """Meaning of a voxel coordinate."""

    CONTINUOUS_INDEX = "continuous-index"
    VOXEL_CENTER = "voxel-center"


class _AtlasPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    atlas_key: str = Field(min_length=1)
    atlas_version: str = Field(min_length=1)


class BrainGlobeVoxelPoint(_AtlasPoint):
    """Continuous BrainGlobe ASR voxel coordinate in ``[AP, DV, ML]`` order."""

    ap: FiniteFloat
    dv: FiniteFloat
    ml: FiniteFloat
    frame_id: Literal["BRAINGLOBE_VOXEL_ASR"] = "BRAINGLOBE_VOXEL_ASR"
    anchor: Literal[VoxelAnchor.CONTINUOUS_INDEX] = VoxelAnchor.CONTINUOUS_INDEX

    def as_tuple(self) -> tuple[float, float, float]:
        """Return the documented ``[AP, DV, ML]`` value tuple."""

        return (self.ap, self.dv, self.ml)


class BrainGlobeVoxelIndex(_AtlasPoint):
    """Discrete BrainGlobe annotation index in ``[AP, DV, ML]`` order."""

    ap: int = Field(ge=0)
    dv: int = Field(ge=0)
    ml: int = Field(ge=0)
    frame_id: Literal["BRAINGLOBE_VOXEL_INDEX_ASR"] = "BRAINGLOBE_VOXEL_INDEX_ASR"

    def as_tuple(self) -> tuple[int, int, int]:
        """Return the documented integer index tuple."""

        return (self.ap, self.dv, self.ml)


class BrainGlobePhysicalPoint(_AtlasPoint):
    """BrainGlobe ASR physical coordinate in micrometres.

    Axes are ``[AP, DV, ML]`` with the origin at anterior/superior/right and
    positive directions toward posterior/inferior/left.
    """

    ap_um: FiniteFloat
    dv_um: FiniteFloat
    ml_um: FiniteFloat
    frame_id: Literal["BRAINGLOBE_PHYSICAL_ASR_UM"] = "BRAINGLOBE_PHYSICAL_ASR_UM"

    def as_tuple(self) -> tuple[float, float, float]:
        """Return the documented ``[AP, DV, ML]`` micrometre tuple."""

        return (self.ap_um, self.dv_um, self.ml_um)


class SurgeryWorldPoint(_AtlasPoint):
    """Right-handed renderer coordinate in micrometres.

    ``x=ML right+``, ``y=AP anterior+``, and ``z=DV dorsal+``.
    """

    ml_right_um: FiniteFloat
    ap_anterior_um: FiniteFloat
    dv_dorsal_um: FiniteFloat
    frame_id: Literal["SURGERY_WORLD_RAS_UM"] = "SURGERY_WORLD_RAS_UM"

    def as_tuple(self) -> tuple[float, float, float]:
        """Return the documented ``[ML, AP, DV]`` world tuple."""

        return (self.ml_right_um, self.ap_anterior_um, self.dv_dorsal_um)


class DisplayCoordinate(BaseModel):
    """User-facing named AP/ML/DV values with an explicit convention."""

    model_config = ConfigDict(frozen=True)

    ap_mm: FiniteFloat
    ml_mm: FiniteFloat
    dv_mm: FiniteFloat
    frame_id: str = Field(min_length=1)
    convention_label: str = Field(min_length=1)

    @field_validator("ap_mm", "ml_mm", "dv_mm")
    @classmethod
    def reject_non_finite(cls, value: float) -> float:
        """Defensively reject non-finite values before scientific use."""

        if not math.isfinite(value):
            raise ValueError("coordinate values must be finite")
        return value
