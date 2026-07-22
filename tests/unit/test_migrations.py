"""Deterministic project-schema migration tests."""

from __future__ import annotations

import pytest
from tests.fixtures import make_allen_metadata_test_double

from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.persistence.migrations import (
    UnsupportedProjectSchemaError,
    migrate_project_payload,
)


def _legacy_v1_payload() -> dict[str, object]:
    metadata = make_allen_metadata_test_double(25).model_dump(mode="json")
    metadata.pop("midline_ml_um")
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 1
    payload["atlas"] = metadata
    payload.pop("renderer_anchor")
    return payload


def test_schema_one_migrates_explicit_midline_and_previous_renderer_anchor() -> None:
    payload = _legacy_v1_payload()

    migrated = migrate_project_payload(payload)
    project = PlannerProject.model_validate(migrated)

    assert payload["schema_version"] == 1
    assert "renderer_anchor" not in payload
    assert migrated["schema_version"] == 4
    assert project.atlas is not None
    assert project.atlas.midline_ml_um == 5700.0
    assert project.renderer_anchor is not None
    assert project.renderer_anchor.as_tuple() == (6612.5, 4012.5, 5712.5)
    assert project.subject_vascular_images == []
    assert project.dorsal_vascular_registrations == []
    assert project.subject_vascular_overlays == []
    assert project.reference_vascular_density is None
    assert project.calibrations == []
    assert project.active_calibration_uuid is None


def test_schema_one_without_atlas_migrates_to_explicit_null_anchor() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 1
    payload.pop("renderer_anchor")

    migrated = migrate_project_payload(payload)

    assert migrated["schema_version"] == 4
    assert migrated["renderer_anchor"] is None
    assert PlannerProject.model_validate(migrated).renderer_anchor is None


def test_schema_two_migrates_only_exact_empty_vascular_defaults() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 2
    for field in (
        "subject_vascular_images",
        "dorsal_vascular_registrations",
        "subject_vascular_overlays",
        "reference_vascular_density",
    ):
        payload.pop(field)

    migrated = migrate_project_payload(payload)

    assert payload["schema_version"] == 2
    assert migrated["schema_version"] == 4
    assert migrated["subject_vascular_images"] == []
    assert migrated["dorsal_vascular_registrations"] == []
    assert migrated["subject_vascular_overlays"] == []
    assert migrated["reference_vascular_density"] is None
    assert migrated["calibrations"] == []
    assert migrated["active_calibration_uuid"] is None


def test_schema_three_migrates_calibration_defaults_without_changing_targets() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 3
    payload.pop("calibrations")
    payload.pop("active_calibration_uuid")
    original_targets = payload["unprojected_bregma_targets"]

    migrated = migrate_project_payload(payload)

    assert migrated["schema_version"] == 4
    assert migrated["calibrations"] == []
    assert migrated["active_calibration_uuid"] is None
    assert migrated["unprojected_bregma_targets"] == original_targets


def test_schema_three_rejects_unversioned_calibration_state() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 3
    payload["calibrations"] = [{"untrusted": True}]

    with pytest.raises(UnsupportedProjectSchemaError, match="schema 4 migration default"):
        migrate_project_payload(payload)


def test_schema_two_rejects_unversioned_nonempty_vascular_state() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 2
    payload["subject_vascular_images"] = [{"untrusted": True}]

    with pytest.raises(UnsupportedProjectSchemaError, match="schema 3 migration default"):
        migrate_project_payload(payload)


def test_schema_one_asymmetric_atlas_fails_closed() -> None:
    payload = _legacy_v1_payload()
    atlas = payload["atlas"]
    assert isinstance(atlas, dict)
    atlas["symmetric"] = False

    with pytest.raises(UnsupportedProjectSchemaError, match="non-symmetric"):
        migrate_project_payload(payload)


def test_schema_one_migration_bounds_legacy_event_history() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 1
    payload.pop("renderer_anchor")
    payload["event_log"] = [
        {"timestamp": "2026-07-21T00:00:00Z", "action": "legacy", "details": str(index)}
        for index in range(1_025)
    ]

    migrated = migrate_project_payload(payload)

    assert len(migrated["event_log"]) == 1_000
    assert migrated["event_log"][0]["details"] == "25"


def test_unknown_project_schema_is_rejected() -> None:
    with pytest.raises(UnsupportedProjectSchemaError, match="schema 99"):
        migrate_project_payload({"schema_version": 99})


@pytest.mark.parametrize("invalid", [True, False, 3.0, "3", None])
def test_noninteger_or_boolean_project_schema_is_rejected(invalid: object) -> None:
    with pytest.raises(UnsupportedProjectSchemaError, match="cannot be migrated"):
        migrate_project_payload({"schema_version": invalid})
