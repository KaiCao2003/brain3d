"""Shared, serializable primitives for animal-only surgery planning.

All anatomical values use named AP/ML/DV components.  Public models never
accept an undocumented three-element coordinate array.  The safety context is
deliberately narrow: this package models research planning for mice and cannot
be re-labelled as a human or clinical navigation context through serialized
input.
"""

from __future__ import annotations

import math
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mouse_brain_planner.domain.numeric_types import (
    FiniteFloat,
    NonNegativeFiniteFloat,
    PositiveFiniteFloat,
)

__all__ = [
    "ANIMAL_RESEARCH_WARNING",
    "AnimalSurgeryContext",
    "FinalPlanConfirmation",
    "FiniteFloat",
    "NonNegativeFiniteFloat",
    "PositiveFiniteFloat",
    "UnitDirectionAPMLDV",
]


class AnimalSurgeryContext(BaseModel):
    """Immutable scope guard for every surgery-domain object.

    Literal fields make a saved payload fail validation if it is changed to a
    human, clinical, or certified-navigation use case.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    context_uuid: UUID = Field(default_factory=uuid4)
    species: Literal["Mus musculus"] = "Mus musculus"
    use_case: Literal["animal-research-surgery-planning"] = "animal-research-surgery-planning"
    research_use_only: Literal[True] = True
    certified_navigation_device: Literal[False] = False
    independent_coordinate_verification_required: Literal[True] = True
    subject_id: str | None = Field(default=None, min_length=1, max_length=200)


class FinalPlanConfirmation(BaseModel):
    """Explicit user confirmation required at the later export boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    context_uuid: UUID
    independently_verified_against_animal_and_rig: Literal[True]
    understands_population_atlas_limitation: Literal[True]
    understands_not_certified_navigation: Literal[True]
    confirmed_by: str = Field(min_length=1, max_length=200)
    confirmation_note: str = Field(min_length=1, max_length=2000)


class UnitDirectionAPMLDV(BaseModel):
    """Dimensionless unit direction in a named AP/ML/DV frame."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame_id: str = Field(min_length=1, max_length=200)
    ap: FiniteFloat
    ml: FiniteFloat
    dv: FiniteFloat
    component_order: tuple[Literal["AP"], Literal["ML"], Literal["DV"]] = (
        "AP",
        "ML",
        "DV",
    )
    units: Literal["dimensionless"] = "dimensionless"

    @model_validator(mode="after")
    def validate_unit_length(self) -> Self:
        """Reject zero or non-normalized directions instead of guessing intent."""

        magnitude = math.sqrt(self.ap * self.ap + self.ml * self.ml + self.dv * self.dv)
        if not math.isclose(magnitude, 1.0, rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"direction magnitude must equal 1; got {magnitude:.12g}")
        return self

    def as_ap_ml_dv(self) -> tuple[float, float, float]:
        """Return values in the documented anatomical component order."""

        return (self.ap, self.ml, self.dv)


ANIMAL_RESEARCH_WARNING = (
    "Animal research planning only; population-atlas coordinates and all calculated geometry "
    "must be independently verified against the individual mouse and stereotaxic apparatus."
)
