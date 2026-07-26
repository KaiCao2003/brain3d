"""Deterministic project-schema migration tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from tests.fixtures import make_allen_metadata_test_double

from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.project_models import (
    MAX_UNPROJECTED_BREGMA_TARGETS,
    PlannerProject,
)
from mouse_brain_planner.persistence.migrations import (
    UnsupportedProjectSchemaError,
    migrate_project_payload,
)
from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION


def _legacy_v1_payload() -> dict[str, object]:
    metadata = make_allen_metadata_test_double(25).model_dump(mode="json")
    metadata.pop("midline_ml_um")
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 1
    payload["atlas"] = metadata
    payload.pop("renderer_anchor")
    return payload


def _target_payload(
    *,
    target_uuid: object | None = None,
    label: str = "legacy plan target",
) -> dict[str, object]:
    updates = {} if target_uuid is None else {"target_uuid": target_uuid}
    return (
        UnprojectedBregmaTarget(
            label=label,
            ap_mm=-1.25,
            ml_mm=-0.8,
            dv_mm=-3.5,
            notes="restore this exact immutable snapshot",
        )
        .model_copy(update=updates)
        .model_dump(mode="json")
    )


def _schema_six_payload(
    *,
    targets: list[object] | None = None,
    source_targets: list[object] | None = None,
) -> dict[str, object]:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 6
    payload["unprojected_bregma_targets"] = [] if targets is None else targets
    payload["probe_plans"] = [
        {"source_target": source_target}
        for source_target in ([] if source_targets is None else source_targets)
    ]
    return payload


def test_schema_one_migrates_explicit_midline_and_previous_renderer_anchor() -> None:
    payload = _legacy_v1_payload()

    migrated = migrate_project_payload(payload)
    project = PlannerProject.model_validate(migrated)

    assert payload["schema_version"] == 1
    assert "renderer_anchor" not in payload
    assert migrated["schema_version"] == PROJECT_SCHEMA_VERSION
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
    assert project.probe_plans == []
    assert project.probe_region_analyses == []
    assert project.probe_vessel_analyses == []
    assert project.project_revision == 0


def test_schema_one_without_atlas_migrates_to_explicit_null_anchor() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 1
    payload.pop("renderer_anchor")

    migrated = migrate_project_payload(payload)

    assert migrated["schema_version"] == PROJECT_SCHEMA_VERSION
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
    assert migrated["schema_version"] == PROJECT_SCHEMA_VERSION
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

    assert migrated["schema_version"] == PROJECT_SCHEMA_VERSION
    assert migrated["calibrations"] == []
    assert migrated["active_calibration_uuid"] is None
    assert migrated["unprojected_bregma_targets"] == original_targets


def test_schema_three_rejects_unversioned_calibration_state() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 3
    payload["calibrations"] = [{"untrusted": True}]

    with pytest.raises(UnsupportedProjectSchemaError, match="schema 4 migration default"):
        migrate_project_payload(payload)


def test_schema_four_adds_only_empty_probe_state() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 4
    payload.pop("probe_plans")
    payload.pop("probe_region_analyses")
    original_calibrations = payload["calibrations"]
    original_targets = payload["unprojected_bregma_targets"]

    migrated = migrate_project_payload(payload)

    assert migrated["schema_version"] == PROJECT_SCHEMA_VERSION
    assert migrated["probe_plans"] == []
    assert migrated["probe_region_analyses"] == []
    assert migrated["calibrations"] == original_calibrations
    assert migrated["unprojected_bregma_targets"] == original_targets


def test_schema_five_adds_only_zero_revision_and_empty_vessel_analyses() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 5
    payload.pop("project_revision")
    payload.pop("probe_vessel_analyses")
    original_probe_plans = payload["probe_plans"]

    migrated = migrate_project_payload(payload)

    assert migrated["schema_version"] == PROJECT_SCHEMA_VERSION
    assert migrated["project_revision"] == 0
    assert migrated["probe_vessel_analyses"] == []
    assert migrated["probe_plans"] == original_probe_plans


@pytest.mark.parametrize(
    ("field", "value"),
    [("project_revision", 7), ("probe_vessel_analyses", [{"untrusted": True}])],
)
def test_schema_five_rejects_unversioned_revision_or_vessel_state(
    field: str,
    value: object,
) -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 5
    payload[field] = value

    with pytest.raises(UnsupportedProjectSchemaError, match="schema 6 migration default"):
        migrate_project_payload(payload)


@pytest.mark.parametrize("schema_version", [7, 8, PROJECT_SCHEMA_VERSION])
@pytest.mark.parametrize("missing", ["project_revision", "probe_vessel_analyses"])
def test_schema_seven_and_current_reject_missing_persisted_concurrency_or_analysis_state(
    schema_version: int,
    missing: str,
) -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = schema_version
    payload.pop(missing)

    with pytest.raises(
        UnsupportedProjectSchemaError,
        match=rf"schema {schema_version} project is missing required persisted state",
    ):
        migrate_project_payload(payload)


def test_schema_seven_only_versions_semantic_contract_without_rewriting_payload() -> None:
    payload = PlannerProject(title="Coherent schema seven").model_dump(mode="json")
    payload["schema_version"] = 7
    original_event_log = payload["event_log"]

    migrated = migrate_project_payload(payload)

    assert payload["schema_version"] == 7
    assert migrated == {**payload, "schema_version": PROJECT_SCHEMA_VERSION}
    assert migrated is not payload
    assert migrated["event_log"] is not original_event_log
    assert PlannerProject.model_validate(migrated).title == "Coherent schema seven"


def test_schema_six_restores_each_missing_source_target_once_without_mutating_input() -> None:
    retained = _target_payload(label="retained target")
    first_missing = _target_payload(label="first referenced missing target")
    second_missing = _target_payload(label="second referenced missing target")
    payload = _schema_six_payload(
        targets=[retained],
        source_targets=[first_missing, second_missing, first_missing],
    )

    migrated = migrate_project_payload(payload)

    assert payload["schema_version"] == 6
    assert payload["unprojected_bregma_targets"] == [retained]
    assert migrated["schema_version"] == PROJECT_SCHEMA_VERSION
    assert migrated["unprojected_bregma_targets"] == [
        retained,
        first_missing,
        second_missing,
    ]


def test_schema_six_keeps_matching_current_source_target_without_duplication() -> None:
    source = _target_payload()
    payload = _schema_six_payload(targets=[source], source_targets=[source, source])

    migrated = migrate_project_payload(payload)

    assert migrated["unprojected_bregma_targets"] == [source]


def test_schema_six_rejects_duplicate_project_target_uuid_even_when_snapshots_match() -> None:
    target = _target_payload()
    payload = _schema_six_payload(targets=[target, target])

    with pytest.raises(UnsupportedProjectSchemaError, match="duplicate target UUID"):
        migrate_project_payload(payload)


def test_schema_six_rejects_restoration_beyond_current_target_capacity() -> None:
    targets = [
        _target_payload(label=f"existing target {index}")
        for index in range(MAX_UNPROJECTED_BREGMA_TARGETS)
    ]
    payload = _schema_six_payload(
        targets=targets,
        source_targets=[_target_payload(label="missing source target")],
    )

    with pytest.raises(UnsupportedProjectSchemaError, match=r"would exceed.*target limit"):
        migrate_project_payload(payload)


@pytest.mark.parametrize("conflict_location", ["plans", "project"])
def test_schema_six_rejects_conflicting_snapshots_for_one_target_uuid(
    conflict_location: str,
) -> None:
    target_id = uuid4()
    original = _target_payload(target_uuid=target_id)
    conflicting = _target_payload(target_uuid=target_id, label="conflicting coordinates owner")
    if conflict_location == "plans":
        payload = _schema_six_payload(source_targets=[original, conflicting])
        expected = "probe plans contain conflicting source-target snapshots"
    else:
        payload = _schema_six_payload(targets=[conflicting], source_targets=[original])
        expected = "project target conflicts with a probe-plan source snapshot"

    with pytest.raises(UnsupportedProjectSchemaError, match=expected):
        migrate_project_payload(payload)


@pytest.mark.parametrize(
    ("field", "payload"),
    [
        ("unprojected_bregma_targets", None),
        ("probe_plans", None),
        ("probe_plans", ["not-an-object"]),
        ("source_target", [{"source_target": None}]),
    ],
)
def test_schema_six_rejects_malformed_target_recovery_state(
    field: str,
    payload: object,
) -> None:
    legacy = _schema_six_payload()
    if field == "source_target":
        legacy["probe_plans"] = payload
        expected = "source-target snapshot"
    else:
        legacy[field] = payload
        expected = "must be an array" if payload is None else "must be an object"

    with pytest.raises(UnsupportedProjectSchemaError, match=expected):
        migrate_project_payload(legacy)


def test_schema_four_rejects_unversioned_probe_state() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 4
    payload["probe_plans"] = [{"untrusted": True}]

    with pytest.raises(UnsupportedProjectSchemaError, match="schema 5 migration default"):
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
