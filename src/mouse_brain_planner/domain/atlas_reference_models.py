"""Provenance-bearing stereotaxic references for direct atlas planning.

The Allen CCF volume does not itself encode bregma.  Direct AP/ML planning
therefore has to name the external convention that supplies the reference
coordinate instead of treating an atlas corner or a remembered voxel as
bregma.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mouse_brain_planner.domain.numeric_types import FiniteFloat


class AtlasBregmaReference(BaseModel):
    """One source-pinned bregma coordinate in BrainGlobe physical ASR space."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_id: str = Field(min_length=1, max_length=200)
    atlas_key: str = Field(min_length=1, max_length=200)
    atlas_version: str = Field(min_length=1, max_length=100)
    frame_id: Literal["BRAINGLOBE_PHYSICAL_ASR_UM"] = "BRAINGLOBE_PHYSICAL_ASR_UM"
    component_order: tuple[Literal["AP"], Literal["DV"], Literal["ML"]] = (
        "AP",
        "DV",
        "ML",
    )
    units: Literal["micrometre"] = "micrometre"
    ap_um: FiniteFloat
    dv_um: FiniteFloat
    ml_um: FiniteFloat
    source_title: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=1, max_length=2000)
    source_revision: str = Field(min_length=1, max_length=300)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_on: date
    limitation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        if min(self.ap_um, self.dv_um, self.ml_um) < 0:
            raise ValueError("atlas bregma physical coordinates must be nonnegative")
        if not self.source_url.startswith("https://"):
            raise ValueError("atlas bregma source URL must use HTTPS")
        return self
