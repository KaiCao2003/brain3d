"""Project serialization, atomic save, and recovery tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from tests.fixtures.atlas_factory import make_allen_metadata_test_double

from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.persistence.project_io import (
    CHECKSUMS_FILENAME,
    PROJECT_FILENAME,
    ProjectIntegrityError,
    load_project,
    normalize_project_path,
    save_project,
    validate_project,
)


def test_project_round_trip_has_no_numeric_or_identity_drift(tmp_path: Path) -> None:
    project = PlannerProject(title="Round trip", subject_id="mouse-001")
    project.touch("created-for-test", "reproducible event")

    saved = save_project(project, tmp_path / "round-trip")
    loaded = load_project(saved)

    assert saved.name == "round-trip.mouseplan"
    assert loaded.model_dump(mode="json") == project.model_dump(mode="json")
    assert (saved / CHECKSUMS_FILENAME).is_file()


def test_second_save_keeps_recoverable_previous_package(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Version one"), tmp_path / "plan.mouseplan")
    replacement = PlannerProject(title="Version two")
    save_project(replacement, path)
    backup = path.with_name(path.name + ".bak")

    assert backup.is_dir()
    assert load_project(path).title == "Version two"
    assert load_project(backup, recover_backup=False).title == "Version one"


def test_corrupt_current_project_recovers_verified_backup(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Known good"), tmp_path / "recover.mouseplan")
    save_project(PlannerProject(title="Current"), path)
    (path / PROJECT_FILENAME).write_text("{}\n", encoding="utf-8")

    recovered = load_project(path)

    assert recovered.title == "Known good"


def test_checksum_tamper_fails_closed_without_backup(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Tamper test"), tmp_path / "tamper.mouseplan")
    payload = json.loads((path / PROJECT_FILENAME).read_text(encoding="utf-8"))
    payload["title"] = "silently modified"
    (path / PROJECT_FILENAME).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectIntegrityError, match="checksum mismatch"):
        load_project(path, recover_backup=False)
    assert validate_project(path)


def test_normalize_project_path_only_appends_required_suffix(tmp_path: Path) -> None:
    assert normalize_project_path(tmp_path / "named").name == "named.mouseplan"
    assert normalize_project_path(tmp_path / "named.mouseplan").name == "named.mouseplan"
    assert normalize_project_path(tmp_path / "named.mouseplan.bak").name == "named.mouseplan.bak"


def test_project_rejects_mixed_or_out_of_bounds_atlas_cursor() -> None:
    metadata = make_allen_metadata_test_double(25)
    valid = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=12.5,
        dv_um=12.5,
        ml_um=12.5,
    )
    project = PlannerProject(atlas=metadata, linked_cursor=valid)

    with pytest.raises(ValidationError, match="does not match project atlas"):
        project.linked_cursor = valid.model_copy(update={"atlas_version": "wrong"})
    project = PlannerProject(atlas=metadata, linked_cursor=valid)
    with pytest.raises(ValidationError, match=r"outside atlas bounds \[0, 13200"):
        project.linked_cursor = valid.model_copy(update={"ap_um": 13_200.0})
    with pytest.raises(ValidationError, match="requires atlas metadata"):
        PlannerProject(linked_cursor=valid)
