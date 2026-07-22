"""Strict bridge operations for persisted, unprojected implant targets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from mouse_brain_planner.bridge.implant_targets import (
    BREGMA_TARGET_FRAME_ID,
    IMPLANT_PROJECTION_STATUS,
    add_implant_target,
    implant_add,
    implant_list,
    implant_remove,
    register_implant_target_handlers,
)
from mouse_brain_planner.bridge.server import BridgeDispatcher, BridgeError
from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.project_models import (
    MAX_UNPROJECTED_BREGMA_TARGETS,
    PlannerProject,
)
from mouse_brain_planner.persistence.project_io import load_project, save_project


def _add_params(project: PlannerProject, **updates: object) -> dict[str, object]:
    params: dict[str, object] = {
        "protocolVersion": 1,
        "projectId": str(project.project_uuid),
        "expectedProjectRevision": project.project_revision,
        "label": "left visual implant",
        "apMillimetres": -1.25,
        "mlMillimetres": -0.7,
        "dvMillimetres": -2.4,
        "notes": "Animal protocol target; not calibrated.",
    }
    params.update(updates)
    return params


def _target(*, target_id: UUID | None = None, label: str = "site") -> UnprojectedBregmaTarget:
    return UnprojectedBregmaTarget(
        target_uuid=target_id or uuid4(),
        label=label,
        ap_mm=-1.25,
        ml_mm=-0.7,
        dv_mm=-2.4,
        created_at=datetime(2026, 7, 21, 12, 30, tzinfo=UTC),
    )


def _assert_locked_contract(result: dict[str, object]) -> None:
    assert result["projected"] is False
    assert result["usableForNavigation"] is False
    assert result["projectionStatus"] == IMPLANT_PROJECTION_STATUS
    frame = result["coordinateFrame"]
    assert isinstance(frame, dict)
    assert frame == {
        "frameId": BREGMA_TARGET_FRAME_ID,
        "origin": "bregma",
        "componentOrder": ["AP", "ML", "DV"],
        "units": "millimetre",
        "signConvention": {
            "apPositive": "anterior",
            "apNegative": "posterior/back",
            "mlPositive": "right",
            "mlNegative": "left",
            "dvPositive": "dorsal/up",
            "dvNegative": "deep/ventral",
        },
    }


def test_list_empty_project_repeats_frame_signs_units_and_lock() -> None:
    result = implant_list(PlannerProject(), {"protocolVersion": 1})

    assert result["status"] == "listed"
    assert result["targetCount"] == 0
    assert result["targets"] == []
    _assert_locked_contract(result)


def test_add_returns_replacement_with_event_and_exact_unprojected_payload() -> None:
    original_time = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
    original = PlannerProject(modified_at=original_time)

    mutation = implant_add(original, _add_params(original, label="  left visual implant  "))

    assert original.unprojected_bregma_targets == []
    assert original.event_log == []
    assert original.modified_at == original_time
    assert mutation.project is not original
    assert mutation.project.modified_at > original_time
    assert len(mutation.project.unprojected_bregma_targets) == 1
    event = mutation.project.event_log[-1]
    assert event.action == "implant-target-added"
    assert "projected=false" in (event.details or "")

    result = mutation.result
    assert result["status"] == "added"
    assert result["projectId"] == str(original.project_uuid)
    assert result["projectRevision"] == original.project_revision + 1
    assert result["targetCount"] == 1
    _assert_locked_contract(result)
    target = result["target"]
    assert isinstance(target, dict)
    assert target["label"] == "left visual implant"
    assert target["apMillimetres"] == -1.25
    assert target["mlMillimetres"] == -0.7
    assert target["dvMillimetres"] == -2.4
    assert target["frameId"] == BREGMA_TARGET_FRAME_ID
    assert target["origin"] == "bregma"
    assert target["componentOrder"] == ["AP", "ML", "DV"]
    assert target["units"] == "millimetre"
    assert target["apNegativeDirection"] == "posterior/back"
    assert target["mlNegativeDirection"] == "left"
    assert target["dvNegativeDirection"] == "deep/ventral"
    assert target["projected"] is False
    assert target["usableForNavigation"] is False
    assert target["projectionStatus"] == IMPLANT_PROJECTION_STATUS

    listed = implant_list(mutation.project, {"protocolVersion": 1})
    assert listed["targets"] == [target]


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"apMillimetres": True}, "apMillimetres"),
        ({"mlMillimetres": float("nan")}, "mlMillimetres"),
        ({"dvMillimetres": float("inf")}, "dvMillimetres"),
        ({"label": "   "}, "label"),
        ({"notes": None}, "notes"),
    ],
)
def test_add_rejects_boolean_nonfinite_and_invalid_text_without_mutation(
    patch: dict[str, object],
    field: str,
) -> None:
    project = PlannerProject()

    with pytest.raises(BridgeError) as captured:
        implant_add(project, _add_params(project, **patch))

    assert captured.value.code == "INVALID_PARAMS"
    assert captured.value.details["field"] == field
    assert project.unprojected_bregma_targets == []
    assert project.event_log == []


def test_all_operations_reject_unknown_or_missing_fields_and_boolean_protocol() -> None:
    project = PlannerProject()
    cases = [
        lambda: implant_list(project, {"protocolVersion": 1, "unexpected": True}),
        lambda: implant_add(
            project,
            {**_add_params(project), "targetId": str(uuid4())},
        ),
        lambda: implant_add(
            project,
            {key: value for key, value in _add_params(project).items() if key != "label"},
        ),
        lambda: implant_remove(
            project,
            {
                "protocolVersion": 1,
                "projectId": str(project.project_uuid),
                "expectedProjectRevision": project.project_revision,
                "targetId": str(uuid4()),
                "label": "not allowed",
            },
        ),
    ]
    for operation in cases:
        with pytest.raises(BridgeError) as captured:
            operation()
        assert captured.value.code == "INVALID_PARAMS"

    with pytest.raises(BridgeError) as captured:
        implant_list(project, {"protocolVersion": True})
    assert captured.value.code == "PROTOCOL_VERSION_MISMATCH"


def test_remove_returns_replacement_and_not_found_fails_without_mutation() -> None:
    target = _target()
    original = PlannerProject(unprojected_bregma_targets=[target])
    original_modified = original.modified_at

    mutation = implant_remove(
        original,
        {
            "protocolVersion": 1,
            "projectId": str(original.project_uuid),
            "expectedProjectRevision": original.project_revision,
            "targetId": str(target.target_uuid),
        },
    )

    assert original.unprojected_bregma_targets == [target]
    assert original.modified_at == original_modified
    assert mutation.project.unprojected_bregma_targets == []
    assert mutation.project.event_log[-1].action == "implant-target-removed"
    assert mutation.result["status"] == "removed"
    assert mutation.result["projectId"] == str(original.project_uuid)
    assert mutation.result["projectRevision"] == original.project_revision + 1
    assert mutation.result["targetCount"] == 0
    assert mutation.result["target"]["targetId"] == str(target.target_uuid)  # type: ignore[index]
    _assert_locked_contract(mutation.result)

    with pytest.raises(BridgeError) as captured:
        implant_remove(
            original,
            {
                "protocolVersion": 1,
                "projectId": str(original.project_uuid),
                "expectedProjectRevision": original.project_revision,
                "targetId": str(uuid4()),
            },
        )
    assert captured.value.code == "IMPLANT_TARGET_NOT_FOUND"
    assert original.event_log == []


@pytest.mark.parametrize("target_id", [True, 12, "not-a-uuid"])
def test_remove_requires_uuid_string(target_id: object) -> None:
    project = PlannerProject()
    with pytest.raises(BridgeError) as captured:
        implant_remove(
            project,
            {
                "protocolVersion": 1,
                "projectId": str(project.project_uuid),
                "expectedProjectRevision": project.project_revision,
                "targetId": target_id,
            },
        )
    assert captured.value.code == "INVALID_PARAMS"


def test_project_transform_rejects_duplicate_before_publishing_replacement() -> None:
    target = _target()
    project = PlannerProject(unprojected_bregma_targets=[target])

    with pytest.raises(BridgeError) as captured:
        add_implant_target(project, target)

    assert captured.value.code == "IMPLANT_TARGET_DUPLICATE"
    assert project.unprojected_bregma_targets == [target]
    assert project.event_log == []


def test_project_transform_revalidates_forged_fail_closed_model_copy() -> None:
    forged = _target().model_copy(update={"projected": True, "usable_for_navigation": True})
    project = PlannerProject()

    with pytest.raises(BridgeError) as captured:
        add_implant_target(project, forged)

    assert captured.value.code == "IMPLANT_TARGET_INVALID"
    assert project.unprojected_bregma_targets == []
    assert project.event_log == []


def test_project_transform_reports_capacity_without_changing_full_project() -> None:
    targets = [_target(label=f"site {index}") for index in range(MAX_UNPROJECTED_BREGMA_TARGETS)]
    project = PlannerProject(unprojected_bregma_targets=targets)

    with pytest.raises(BridgeError) as captured:
        add_implant_target(project, _target(label="one too many"))

    assert captured.value.code == "IMPLANT_TARGET_CAPACITY_REACHED"
    assert len(project.unprojected_bregma_targets) == MAX_UNPROJECTED_BREGMA_TARGETS
    assert project.event_log == []


def test_added_target_persists_as_exact_list_truth(tmp_path: Path) -> None:
    project = PlannerProject()
    mutation = implant_add(project, _add_params(project))
    saved = save_project(mutation.project, tmp_path / "implant-target")
    loaded = load_project(saved, recover_backup=False)

    persisted = implant_list(loaded, {"protocolVersion": 1})
    in_memory = implant_list(mutation.project, {"protocolVersion": 1})
    assert persisted == in_memory
    target = persisted["targets"][0]  # type: ignore[index]
    assert target["projected"] is False
    assert target["usableForNavigation"] is False
    assert target["projectionStatus"] == IMPLANT_PROJECTION_STATUS


@dataclass(slots=True)
class _ProjectState:
    project: PlannerProject = field(default_factory=PlannerProject)
    replacements: int = 0

    def get(self) -> PlannerProject:
        return self.project

    @property
    def revision(self) -> int:
        return self.project.project_revision

    def replace(self, project: PlannerProject) -> int:
        next_revision = self.revision + 1
        self.project = project.model_copy(update={"project_revision": next_revision})
        self.replacements += 1
        return next_revision


def test_registration_helper_uses_owner_callbacks_only_after_success() -> None:
    state = _ProjectState()
    dispatcher = BridgeDispatcher()
    extension = register_implant_target_handlers(
        dispatcher,
        get_project=state.get,
        get_revision=lambda: state.revision,
        replace_project=state.replace,
    )

    added = dispatcher.dispatch("implant.add", _add_params(state.project))
    assert added["projectRevision"] == 1
    target_id = added["target"]["targetId"]  # type: ignore[index]
    listed = dispatcher.dispatch("implant.list", {"protocolVersion": 1})
    assert extension.get_project() is state.project
    assert listed["targetCount"] == 1
    assert state.replacements == 1

    with pytest.raises(BridgeError):
        dispatcher.dispatch(
            "implant.add",
            {**_add_params(state.project), "unknown": 1},
        )
    assert state.replacements == 1

    dispatcher.dispatch(
        "implant.remove",
        {
            "protocolVersion": 1,
            "projectId": str(state.project.project_uuid),
            "expectedProjectRevision": state.revision,
            "targetId": target_id,
        },
    )
    assert state.project.unprojected_bregma_targets == []
    assert state.replacements == 2

    hello = dispatcher.dispatch(
        "hello",
        {"protocolVersion": 1, "client": "implant-target-test"},
    )
    assert hello["capabilities"]["unprojectedBregmaImplantTargets"] is True  # type: ignore[index]


def test_mutations_reject_wrong_project_and_stale_or_replayed_revision_before_publish() -> None:
    state = _ProjectState()
    dispatcher = BridgeDispatcher()
    register_implant_target_handlers(
        dispatcher,
        get_project=state.get,
        get_revision=lambda: state.revision,
        replace_project=state.replace,
    )
    initial = _add_params(state.project)

    with pytest.raises(BridgeError) as wrong_project:
        dispatcher.dispatch(
            "implant.add",
            {**initial, "projectId": str(uuid4())},
        )
    assert wrong_project.value.code == "PROJECT_ID_MISMATCH"
    assert state.replacements == 0

    added = dispatcher.dispatch("implant.add", initial)
    assert added["projectRevision"] == 1
    assert state.replacements == 1

    with pytest.raises(BridgeError) as replayed:
        dispatcher.dispatch("implant.add", initial)
    assert replayed.value.code == "PROJECT_REVISION_CONFLICT"
    assert replayed.value.details == {
        "expectedProjectRevision": 0,
        "actualProjectRevision": 1,
    }
    assert state.replacements == 1
    assert len(state.project.unprojected_bregma_targets) == 1

    target = added["target"]
    assert isinstance(target, dict)
    with pytest.raises(BridgeError) as stale_remove:
        dispatcher.dispatch(
            "implant.remove",
            {
                "protocolVersion": 1,
                "projectId": str(state.project.project_uuid),
                "expectedProjectRevision": 0,
                "targetId": target["targetId"],
            },
        )
    assert stale_remove.value.code == "PROJECT_REVISION_CONFLICT"
    assert state.replacements == 1


def test_registration_rejects_replacer_that_does_not_publish_exactly_one_revision() -> None:
    state = _ProjectState()
    calls = 0

    def nonpublishing_replacer(project: PlannerProject) -> int:
        nonlocal calls
        del project
        calls += 1
        return state.revision + 1

    dispatcher = BridgeDispatcher()
    register_implant_target_handlers(
        dispatcher,
        get_project=state.get,
        get_revision=lambda: state.revision,
        replace_project=nonpublishing_replacer,
    )

    with pytest.raises(RuntimeError, match="increment revision exactly once"):
        dispatcher.dispatch("implant.add", _add_params(state.project))
    assert calls == 1
    assert state.revision == 0
    assert state.project.unprojected_bregma_targets == []
