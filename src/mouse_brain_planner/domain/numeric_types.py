"""Strict finite numeric aliases shared by scientific domain models."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field


def reject_boolean_scientific_number(value: object) -> object:
    """Reject JSON booleans before Pydantic can coerce them to zero or one."""

    if isinstance(value, bool):
        raise ValueError("scientific numeric values must not be booleans")
    return value


FiniteFloat = Annotated[
    float,
    BeforeValidator(reject_boolean_scientific_number),
    Field(allow_inf_nan=False),
]
NonNegativeFiniteFloat = Annotated[
    float,
    BeforeValidator(reject_boolean_scientific_number),
    Field(ge=0, allow_inf_nan=False),
]
PositiveFiniteFloat = Annotated[
    float,
    BeforeValidator(reject_boolean_scientific_number),
    Field(gt=0, allow_inf_nan=False),
]
