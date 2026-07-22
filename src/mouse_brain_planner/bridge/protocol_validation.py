"""Shared strict scalar and parameter validation for bridge extensions."""

from __future__ import annotations

import math
from collections.abc import Mapping
from uuid import UUID

from mouse_brain_planner.bridge import PROTOCOL_VERSION
from mouse_brain_planner.bridge.server import BridgeError


def validate_params(
    params: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    actual = set(params)
    missing = sorted(required - actual)
    unexpected = sorted(actual - allowed)
    if missing or unexpected:
        raise BridgeError(
            "INVALID_PARAMS",
            "Request parameters do not match the strict method contract.",
            details={"missing": missing, "unexpected": unexpected},
        )


def require_protocol(params: Mapping[str, object]) -> None:
    value = params.get("protocolVersion")
    if isinstance(value, bool) or not isinstance(value, int) or value != PROTOCOL_VERSION:
        raise BridgeError(
            "PROTOCOL_VERSION_MISMATCH",
            f"protocolVersion must equal {PROTOCOL_VERSION}.",
            details={"received": value},
        )


def uuid_value(value: object, field: str) -> UUID:
    if not isinstance(value, str):
        raise BridgeError("INVALID_PARAMS", f"{field} must be a UUID string.")
    try:
        return UUID(value)
    except ValueError as error:
        raise BridgeError("INVALID_PARAMS", f"{field} must be a UUID string.") from error


def text_value(value: object, field: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str):
        raise BridgeError("INVALID_PARAMS", f"{field} must be text.")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must contain 1 to {maximum} non-whitespace characters.",
        )
    return normalized


def integer_value(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be an integer at least {minimum}.",
        )
    return value


def finite_number(
    value: object,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_inclusive: bool = True,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeError("INVALID_PARAMS", f"{field} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise BridgeError("INVALID_PARAMS", f"{field} must be a finite number.")
    below = minimum is not None and (number < minimum if minimum_inclusive else number <= minimum)
    above = maximum is not None and number > maximum
    if below or above:
        bounds = {
            "minimum": minimum,
            "minimumInclusive": minimum_inclusive,
            "maximum": maximum,
        }
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} is outside the permitted range.",
            details={"field": field, "value": number, **bounds},
        )
    return number


def boolean_value(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise BridgeError("INVALID_PARAMS", f"{field} must be a boolean.")
    return value


def sha256_value(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be 64 lowercase hexadecimal characters.",
        )
    return value
