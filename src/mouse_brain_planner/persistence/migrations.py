"""Project-schema migration entry point."""

from __future__ import annotations

import copy
import math
from typing import Any

from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION


class UnsupportedProjectSchemaError(ValueError):
    """Raised when a project cannot be migrated safely."""


def migrate_project_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Migrate a project payload to the current schema.

    Schema 1 omitted the explicit atlas midline and renderer anchor. Schema 2
    records both. Schema 3 adds bounded vascular project state; the current
    schema-3 model also adds bounded unprojected coordinate-entry targets.
    Earlier projects default all of that state to empty.
    """

    version = payload.get("schema_version")
    if version == PROJECT_SCHEMA_VERSION:
        return payload
    if version == 1:
        return _migrate_v2_to_v3(_migrate_v1_to_v2(payload))
    if version == 2:
        return _migrate_v2_to_v3(payload)
    raise UnsupportedProjectSchemaError(
        f"project schema {version!r} cannot be migrated to {PROJECT_SCHEMA_VERSION}"
    )


def _migrate_v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(payload)
    atlas = migrated.get("atlas")
    if atlas is None:
        migrated["renderer_anchor"] = None
    elif isinstance(atlas, dict):
        shape = _positive_integer_triplet(atlas.get("shape_voxels"), "atlas.shape_voxels")
        resolution = _positive_float_triplet(atlas.get("resolution_um"), "atlas.resolution_um")
        if atlas.get("standardized_orientation", "asr") != "asr":
            raise UnsupportedProjectSchemaError(
                "schema 1 atlas migration requires BrainGlobe ASR orientation"
            )
        if atlas.get("symmetric") is not True:
            raise UnsupportedProjectSchemaError(
                "schema 1 atlas migration cannot infer a midline for a non-symmetric atlas"
            )
        atlas.setdefault("midline_ml_um", shape[2] * resolution[2] / 2.0)
        migrated.setdefault(
            "renderer_anchor",
            {
                "atlas_key": _required_text(atlas.get("atlas_key"), "atlas.atlas_key"),
                "atlas_version": _required_text(
                    atlas.get("atlas_package_version"),
                    "atlas.atlas_package_version",
                ),
                "ap_um": (shape[0] // 2 + 0.5) * resolution[0],
                "dv_um": (shape[1] // 2 + 0.5) * resolution[1],
                "ml_um": (shape[2] // 2 + 0.5) * resolution[2],
                "frame_id": "BRAINGLOBE_PHYSICAL_ASR_UM",
            },
        )
    else:
        raise UnsupportedProjectSchemaError("schema 1 atlas field must be an object or null")

    event_log = migrated.get("event_log")
    if isinstance(event_log, list) and len(event_log) > 1_000:
        migrated["event_log"] = event_log[-1_000:]
    migrated["schema_version"] = 2
    return migrated


_SCHEMA_3_ADDED_DEFAULTS: dict[str, object] = {
    "subject_vascular_images": [],
    "dorsal_vascular_registrations": [],
    "subject_vascular_overlays": [],
    "reference_vascular_density": None,
    "unprojected_bregma_targets": [],
}


def _migrate_v2_to_v3(payload: dict[str, Any]) -> dict[str, Any]:
    """Add only exact empty post-schema-2 defaults to a schema-2 project.

    Schema 2 had no defined vascular or unprojected-target fields. Non-empty
    values under those names therefore have no trustworthy package-asset,
    coordinate-frame, or atlas-reference contract and must not be promoted.
    """

    migrated = copy.deepcopy(payload)
    for field, default in _SCHEMA_3_ADDED_DEFAULTS.items():
        if field in migrated and migrated[field] != default:
            raise UnsupportedProjectSchemaError(
                f"schema 2 {field} must be the schema 3 migration default {default!r}"
            )
        migrated[field] = copy.deepcopy(default)
    migrated["schema_version"] = 3
    return migrated


def _positive_integer_triplet(value: object, field: str) -> tuple[int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise UnsupportedProjectSchemaError(f"schema 1 {field} must contain three integers")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise UnsupportedProjectSchemaError(f"schema 1 {field} must contain positive integers")
    return (value[0], value[1], value[2])


def _positive_float_triplet(value: object, field: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise UnsupportedProjectSchemaError(f"schema 1 {field} must contain three numbers")
    converted: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise UnsupportedProjectSchemaError(
                f"schema 1 {field} must contain positive finite numbers"
            )
        number = float(item)
        if number <= 0 or not math.isfinite(number):
            raise UnsupportedProjectSchemaError(
                f"schema 1 {field} must contain positive finite numbers"
            )
        converted.append(number)
    return (converted[0], converted[1], converted[2])


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UnsupportedProjectSchemaError(f"schema 1 {field} must be non-empty text")
    return value
