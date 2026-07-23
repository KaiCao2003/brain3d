"""Project-schema migration entry point."""

from __future__ import annotations

import copy
import math
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.project_models import MAX_UNPROJECTED_BREGMA_TARGETS
from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION


class UnsupportedProjectSchemaError(ValueError):
    """Raised when a project cannot be migrated safely."""


def migrate_project_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Migrate a project payload to the current schema.

    Schema 1 omitted the explicit atlas midline and renderer anchor. Schema 2
    records both. Schema 3 adds bounded vascular state and unprojected
    coordinate-entry targets. Schema 4 adds versioned subject calibrations and
    an explicit active-calibration UUID. Schema 5 adds persisted probe plans
    and exact region-analysis bundles. Schema 6 persists the monotonic project
    revision and plan-linked major-vessel analysis bundles. Schema 7 makes
    every probe plan's immutable source-target snapshot a required project
    target. Legacy schema-5/6 projects could delete that target while retaining
    the plan, so migration restores an unambiguous missing snapshot instead of
    weakening the current referential-integrity invariant. Earlier projects
    otherwise default new state to empty without altering legacy AP/ML/DV
    coordinates.
    """

    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise UnsupportedProjectSchemaError(
            f"project schema {version!r} cannot be migrated to {PROJECT_SCHEMA_VERSION}"
        )
    if version == PROJECT_SCHEMA_VERSION:
        missing = {"project_revision", "probe_vessel_analyses"} - set(payload)
        if missing:
            raise UnsupportedProjectSchemaError(
                f"schema {PROJECT_SCHEMA_VERSION} project is missing required persisted state: "
                + ", ".join(sorted(missing))
            )
        return payload
    if version == 1:
        return _migrate_v6_to_v7(
            _migrate_v5_to_v6(
                _migrate_v4_to_v5(_migrate_v3_to_v4(_migrate_v2_to_v3(_migrate_v1_to_v2(payload))))
            )
        )
    if version == 2:
        return _migrate_v6_to_v7(
            _migrate_v5_to_v6(_migrate_v4_to_v5(_migrate_v3_to_v4(_migrate_v2_to_v3(payload))))
        )
    if version == 3:
        return _migrate_v6_to_v7(_migrate_v5_to_v6(_migrate_v4_to_v5(_migrate_v3_to_v4(payload))))
    if version == 4:
        return _migrate_v6_to_v7(_migrate_v5_to_v6(_migrate_v4_to_v5(payload)))
    if version == 5:
        return _migrate_v6_to_v7(_migrate_v5_to_v6(payload))
    if version == 6:
        return _migrate_v6_to_v7(payload)
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


_SCHEMA_4_ADDED_DEFAULTS: dict[str, object] = {
    "calibrations": [],
    "active_calibration_uuid": None,
}


def _migrate_v3_to_v4(payload: dict[str, Any]) -> dict[str, Any]:
    """Add empty calibration state without modifying schema-3 target inputs."""

    migrated = copy.deepcopy(payload)
    for field, default in _SCHEMA_4_ADDED_DEFAULTS.items():
        if field in migrated and migrated[field] != default:
            raise UnsupportedProjectSchemaError(
                f"schema 3 {field} must be the schema 4 migration default {default!r}"
            )
        migrated[field] = copy.deepcopy(default)
    migrated["schema_version"] = 4
    return migrated


_SCHEMA_5_ADDED_DEFAULTS: dict[str, object] = {
    "probe_plans": [],
    "probe_region_analyses": [],
}


def _migrate_v4_to_v5(payload: dict[str, Any]) -> dict[str, Any]:
    """Add empty probe state without inventing a placement or analysis."""

    migrated = copy.deepcopy(payload)
    for field, default in _SCHEMA_5_ADDED_DEFAULTS.items():
        if field in migrated and migrated[field] != default:
            raise UnsupportedProjectSchemaError(
                f"schema 4 {field} must be the schema 5 migration default {default!r}"
            )
        migrated[field] = copy.deepcopy(default)
    migrated["schema_version"] = 5
    return migrated


_SCHEMA_6_ADDED_DEFAULTS: dict[str, object] = {
    "project_revision": 0,
    "probe_vessel_analyses": [],
}


def _migrate_v5_to_v6(payload: dict[str, Any]) -> dict[str, Any]:
    """Add only revision zero and empty vessel analyses to legacy projects."""

    migrated = copy.deepcopy(payload)
    for field, default in _SCHEMA_6_ADDED_DEFAULTS.items():
        if field in migrated and migrated[field] != default:
            raise UnsupportedProjectSchemaError(
                f"schema 5 {field} must be the schema 6 migration default {default!r}"
            )
        migrated[field] = copy.deepcopy(default)
    migrated["schema_version"] = 6
    return migrated


def _migrate_v6_to_v7(payload: dict[str, Any]) -> dict[str, Any]:
    """Restore unambiguous plan source targets deleted under schema 6.

    Schema 6 required target UUID uniqueness but did not require a plan's
    immutable ``source_target`` snapshot to remain in the project target list.
    Preserve the existing target order, then append each missing source target
    in first-plan-reference order. Identical references are coalesced. Any
    duplicate project UUID or differing snapshots for one UUID are ambiguous
    and therefore rejected rather than guessed.
    """

    migrated = copy.deepcopy(payload)
    raw_targets = migrated.get("unprojected_bregma_targets")
    if not isinstance(raw_targets, list):
        raise UnsupportedProjectSchemaError("schema 6 unprojected_bregma_targets must be an array")
    raw_plans = migrated.get("probe_plans")
    if not isinstance(raw_plans, list):
        raise UnsupportedProjectSchemaError("schema 6 probe_plans must be an array")

    targets_by_id: dict[UUID, UnprojectedBregmaTarget] = {}
    for index, raw_target in enumerate(raw_targets):
        target = _schema_six_target(raw_target, field=f"unprojected_bregma_targets[{index}]")
        if target.target_uuid in targets_by_id:
            raise UnsupportedProjectSchemaError(
                "schema 6 unprojected_bregma_targets contains duplicate target UUID "
                f"{target.target_uuid}"
            )
        targets_by_id[target.target_uuid] = target

    referenced_by_id: dict[UUID, UnprojectedBregmaTarget] = {}
    missing_targets: list[dict[str, Any]] = []
    for index, raw_plan in enumerate(raw_plans):
        if not isinstance(raw_plan, dict):
            raise UnsupportedProjectSchemaError(f"schema 6 probe_plans[{index}] must be an object")
        source = _schema_six_target(
            raw_plan.get("source_target"),
            field=f"probe_plans[{index}].source_target",
        )
        previous_source = referenced_by_id.get(source.target_uuid)
        if previous_source is not None and previous_source != source:
            raise UnsupportedProjectSchemaError(
                "schema 6 probe plans contain conflicting source-target snapshots for UUID "
                f"{source.target_uuid}"
            )
        referenced_by_id[source.target_uuid] = source

        current = targets_by_id.get(source.target_uuid)
        if current is not None:
            if current != source:
                raise UnsupportedProjectSchemaError(
                    "schema 6 project target conflicts with a probe-plan source snapshot for UUID "
                    f"{source.target_uuid}"
                )
            continue
        if previous_source is None:
            restored = source.model_dump(mode="json")
            missing_targets.append(restored)
            targets_by_id[source.target_uuid] = source

    if len(raw_targets) + len(missing_targets) > MAX_UNPROJECTED_BREGMA_TARGETS:
        raise UnsupportedProjectSchemaError(
            "schema 6 source-target restoration would exceed the schema 7 target limit "
            f"of {MAX_UNPROJECTED_BREGMA_TARGETS}"
        )
    migrated["unprojected_bregma_targets"] = [*raw_targets, *missing_targets]
    migrated["schema_version"] = 7
    return migrated


def _schema_six_target(raw_target: object, *, field: str) -> UnprojectedBregmaTarget:
    """Validate one legacy target snapshot without accepting partial identity."""

    try:
        return UnprojectedBregmaTarget.model_validate(raw_target)
    except ValidationError as error:
        raise UnsupportedProjectSchemaError(
            f"schema 6 {field} is not a valid source-target snapshot"
        ) from error


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
