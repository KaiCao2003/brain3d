"""Unprojected bregma target validation and persistence tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mouse_brain_planner.domain.implant_site_models import (
    UnprojectedBregmaTarget,
    parse_decimal_mm,
    unprojected_bregma_target_summary,
    validate_bregma_decimal_inputs,
)
from mouse_brain_planner.domain.project_models import (
    MAX_UNPROJECTED_BREGMA_TARGETS,
    PlannerProject,
)
from mouse_brain_planner.persistence.migrations import (
    UnsupportedProjectSchemaError,
    migrate_project_payload,
)
from mouse_brain_planner.persistence.project_io import (
    CHECKSUMS_FILENAME,
    PROJECT_FILENAME,
    load_project,
    save_project,
)


def _target(**updates: object) -> UnprojectedBregmaTarget:
    values: dict[str, object] = {
        "target_uuid": uuid4(),
        "label": "left visual implant",
        "ap_mm": -1.25,
        "ml_mm": -0.7,
        "dv_mm": -2.4,
        "created_at": datetime(2026, 7, 21, 12, 30, tzinfo=UTC),
        "notes": "Entered from the animal protocol; not projected.",
    }
    values.update(updates)
    return UnprojectedBregmaTarget.model_validate(values)


def test_target_preserves_fixed_bregma_frame_signs_and_fail_closed_flags() -> None:
    target = _target(label="  left visual implant  ")

    assert target.label == "left visual implant"
    assert target.as_ap_ml_dv_mm() == (-1.25, -0.7, -2.4)
    assert target.frame_id == "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"
    assert target.origin == "bregma"
    assert target.units == "millimetre"
    assert target.component_order == ("AP", "ML", "DV")
    assert target.ap_negative_direction == "posterior/back"
    assert target.ml_negative_direction == "left"
    assert target.dv_negative_direction == "deep/ventral"
    assert target.projected is False
    assert target.usable_for_navigation is False
    assert target.model_dump(mode="json", by_alias=True)["usableForNavigation"] is False

    for field in ("projected", "usable_for_navigation"):
        payload = target.model_dump(mode="json")
        payload[field] = True
        with pytest.raises(ValidationError, match=field):
            UnprojectedBregmaTarget.model_validate(payload)


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), float("-inf")])
def test_target_rejects_nonfinite_coordinates(coordinate: float) -> None:
    with pytest.raises(ValidationError, match="finite number"):
        _target(ap_mm=coordinate)


def test_target_rejects_blank_label_and_ambiguous_timestamp() -> None:
    with pytest.raises(ValidationError, match="non-whitespace"):
        _target(label=" \t ")
    with pytest.raises(ValidationError, match="timezone"):
        _target(created_at=datetime(2026, 7, 21, 12, 30))
    with pytest.raises(ValidationError, match="not booleans"):
        _target(ml_mm=True)


@pytest.mark.parametrize(
    "text",
    ["", " ", "nan", "inf", "1e3", "1,25", "1 000", "+.", "--1", "\uff11\uff12.\uff13"],
)
def test_decimal_ui_parser_rejects_ambiguous_or_nondecimal_text(text: str) -> None:
    with pytest.raises(ValueError, match="AP must"):
        parse_decimal_mm(text, axis="AP")


def test_decimal_ui_helpers_return_named_finite_values_without_negative_zero() -> None:
    parsed = validate_bregma_decimal_inputs(
        ap_text=" -1.250 ",
        ml_text="+.70",
        dv_text="-0",
    )

    assert parsed.as_ap_ml_dv() == (-1.25, 0.7, 0.0)
    assert str(parsed.dv_mm) == "0.0"
    with pytest.raises(ValueError, match="outside the finite numeric range"):
        parse_decimal_mm("9" * 400, axis="DV")


def test_display_summary_makes_directions_and_non_navigation_status_visible() -> None:
    summary = unprojected_bregma_target_summary(_target(ml_mm=0.7))

    assert summary == (
        "left visual implant — AP -1.25 mm (posterior/back), "
        "ML +0.7 mm (right), DV -2.4 mm (deep/ventral), from bregma; "
        "unprojected; not usable for navigation"
    )


def test_project_bounds_targets_and_rejects_duplicate_uuids_without_an_atlas() -> None:
    target = _target()
    with pytest.raises(ValidationError, match="duplicate UUIDs"):
        PlannerProject(unprojected_bregma_targets=[target, target])

    maximum = [
        target.model_copy(update={"target_uuid": uuid4(), "label": f"site {index}"})
        for index in range(MAX_UNPROJECTED_BREGMA_TARGETS)
    ]
    assert len(PlannerProject(unprojected_bregma_targets=maximum).unprojected_bregma_targets) == (
        MAX_UNPROJECTED_BREGMA_TARGETS
    )
    with pytest.raises(ValidationError, match=f"at most {MAX_UNPROJECTED_BREGMA_TARGETS}"):
        PlannerProject(
            unprojected_bregma_targets=[
                *maximum,
                target.model_copy(update={"target_uuid": uuid4()}),
            ]
        )


def test_target_round_trip_is_covered_by_project_json_checksum(tmp_path) -> None:
    project = PlannerProject(
        title="Coordinate-entry plan",
        unprojected_bregma_targets=[_target()],
    )

    saved = save_project(project, tmp_path / "coordinate-entry")
    project_bytes = (saved / PROJECT_FILENAME).read_bytes()
    payload = json.loads(project_bytes)
    checksums = json.loads((saved / CHECKSUMS_FILENAME).read_text(encoding="utf-8"))
    loaded = load_project(saved, recover_backup=False)

    assert (
        payload["unprojected_bregma_targets"]
        == project.model_dump(mode="json")["unprojected_bregma_targets"]
    )
    assert checksums[PROJECT_FILENAME] == hashlib.sha256(project_bytes).hexdigest()
    assert loaded.model_dump(mode="json") == project.model_dump(mode="json")


def test_existing_schema_three_package_without_target_field_loads_empty(tmp_path) -> None:
    saved = save_project(PlannerProject(), tmp_path / "pre-target-schema-three")
    project_path = saved / PROJECT_FILENAME
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    payload.pop("unprojected_bregma_targets")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    project_path.write_bytes(encoded)
    checksums_path = saved / CHECKSUMS_FILENAME
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[PROJECT_FILENAME] = hashlib.sha256(encoded).hexdigest()
    checksums_path.write_text(
        json.dumps(checksums, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    assert load_project(saved, recover_backup=False).unprojected_bregma_targets == []


def test_schema_two_cannot_smuggle_unversioned_coordinate_targets() -> None:
    payload = PlannerProject().model_dump(mode="json")
    payload["schema_version"] = 2
    payload.pop("unprojected_bregma_targets")
    assert migrate_project_payload(payload)["unprojected_bregma_targets"] == []

    payload["unprojected_bregma_targets"] = [_target().model_dump(mode="json")]
    with pytest.raises(UnsupportedProjectSchemaError, match="schema 3 migration default"):
        migrate_project_payload(payload)
