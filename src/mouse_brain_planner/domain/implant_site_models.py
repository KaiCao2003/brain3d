"""Safe, unprojected bregma-relative implant-site inputs.

These models deliberately stop before atlas or skull-calibration projection.
They preserve exactly what a user entered relative to bregma while making the
non-navigation status impossible to change through a valid serialized model.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mouse_brain_planner.domain.surgery_common import FiniteFloat

BregmaAxis = Literal["AP", "ML", "DV"]

_DECIMAL_INPUT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class UnprojectedBregmaTarget(BaseModel):
    """One animal implant site entered in millimetres relative to bregma.

    No atlas identity, skull calibration, or transform is accepted here.  A
    later, explicit calibration boundary may create a different projected
    object; this stored input always remains unprojected and non-navigational.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    target_uuid: UUID = Field(default_factory=uuid4)
    schema_version: Literal[1] = 1
    label: str = Field(min_length=1, max_length=200)
    ap_mm: FiniteFloat
    ml_mm: FiniteFloat
    dv_mm: FiniteFloat
    frame_id: Literal["BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"] = (
        "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"
    )
    origin: Literal["bregma"] = "bregma"
    component_order: tuple[Literal["AP"], Literal["ML"], Literal["DV"]] = (
        "AP",
        "ML",
        "DV",
    )
    units: Literal["millimetre"] = "millimetre"
    ap_positive_direction: Literal["anterior"] = "anterior"
    ap_negative_direction: Literal["posterior/back"] = "posterior/back"
    ml_positive_direction: Literal["right"] = "right"
    ml_negative_direction: Literal["left"] = "left"
    dv_positive_direction: Literal["dorsal/up"] = "dorsal/up"
    dv_negative_direction: Literal["deep/ventral"] = "deep/ventral"
    created_at: datetime = Field(default_factory=_utc_now)
    notes: str = Field(default="", max_length=4000)
    projected: Literal[False] = False
    usable_for_navigation: Literal[False] = Field(default=False, alias="usableForNavigation")

    @field_validator("label")
    @classmethod
    def normalize_nonempty_label(cls, value: str) -> str:
        """Store a visible label rather than whitespace-only UI input."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("implant-site label must contain non-whitespace text")
        return normalized

    @field_validator("ap_mm", "ml_mm", "dv_mm", mode="before")
    @classmethod
    def reject_boolean_coordinates(cls, value: object) -> object:
        """Do not let JSON booleans silently become 1 mm or 0 mm."""

        if isinstance(value, bool):
            raise ValueError("implant-site coordinates must be finite numbers, not booleans")
        return value

    @field_validator("created_at")
    @classmethod
    def normalize_created_at_to_utc(cls, value: datetime) -> datetime:
        """Require an unambiguous timestamp and normalize it to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("implant-site created_at must include a timezone")
        return value.astimezone(UTC)

    def as_ap_ml_dv_mm(self) -> tuple[float, float, float]:
        """Return the named components in the model's documented order."""

        return (self.ap_mm, self.ml_mm, self.dv_mm)


@dataclass(frozen=True, slots=True)
class ParsedBregmaCoordinatesMM:
    """Validated decimal UI values in named AP/ML/DV order."""

    ap_mm: float
    ml_mm: float
    dv_mm: float

    def as_ap_ml_dv(self) -> tuple[float, float, float]:
        return (self.ap_mm, self.ml_mm, self.dv_mm)


def parse_decimal_mm(text: str, *, axis: BregmaAxis) -> float:
    """Parse one finite, base-10 UI coordinate without inventing a range.

    Leading and trailing whitespace are harmless. Exponents, grouping
    separators, locale commas, NaN, and infinities are rejected so the text box
    has one predictable interpretation.
    """

    if not isinstance(text, str):
        raise ValueError(f"{axis} must be entered as decimal text in millimetres")
    normalized = text.strip()
    if not normalized or _DECIMAL_INPUT.fullmatch(normalized) is None:
        raise ValueError(f"{axis} must be a finite decimal number in millimetres")
    try:
        decimal_value = Decimal(normalized)
    except InvalidOperation as error:  # Defensive; the grammar is intentionally narrower.
        raise ValueError(f"{axis} must be a finite decimal number in millimetres") from error
    if not decimal_value.is_finite():
        raise ValueError(f"{axis} must be a finite decimal number in millimetres")
    value = float(decimal_value)
    if not math.isfinite(value):
        raise ValueError(f"{axis} is outside the finite numeric range")
    return 0.0 if value == 0 else value


def validate_bregma_decimal_inputs(
    *,
    ap_text: str,
    ml_text: str,
    dv_text: str,
) -> ParsedBregmaCoordinatesMM:
    """Validate three UI fields and return named millimetre values."""

    return ParsedBregmaCoordinatesMM(
        ap_mm=parse_decimal_mm(ap_text, axis="AP"),
        ml_mm=parse_decimal_mm(ml_text, axis="ML"),
        dv_mm=parse_decimal_mm(dv_text, axis="DV"),
    )


def unprojected_bregma_target_summary(target: UnprojectedBregmaTarget) -> str:
    """Return a compact display string with signs and safety status visible."""

    ap_direction = _direction(target.ap_mm, "anterior", "posterior/back")
    ml_direction = _direction(target.ml_mm, "right", "left")
    dv_direction = _direction(target.dv_mm, "dorsal/up", "deep/ventral")
    return (
        f"{target.label} — "
        f"AP {_signed_value(target.ap_mm)} mm ({ap_direction}), "
        f"ML {_signed_value(target.ml_mm)} mm ({ml_direction}), "
        f"DV {_signed_value(target.dv_mm)} mm ({dv_direction}), "
        "from bregma; unprojected; not usable for navigation"
    )


def _signed_value(value: float) -> str:
    if value == 0:
        return "0"
    rendered = str(value)
    return rendered if value < 0 else f"+{rendered}"


def _direction(value: float, positive: str, negative: str) -> str:
    if value > 0:
        return positive
    if value < 0:
        return negative
    return "zero"
