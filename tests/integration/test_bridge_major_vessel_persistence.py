"""Major-vessel analysis persistence across a real project save/open boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit.test_bridge_major_vessels import (
    _analysis_params,
    _dispatcher_with_atlas,
    _FakeAtlas,
    _mapping,
    _project_with_probe_plan,
    _ProjectState,
    _tiny_graph,
)

from mouse_brain_planner.bridge.major_vessels import register_major_vessel_handlers
from mouse_brain_planner.bridge.planning import PlanningBridgeSession, register_planning_handlers
from mouse_brain_planner.bridge.server import BridgeDispatcher, BridgeError


def _call(dispatcher: BridgeDispatcher, method: str, **params: object) -> dict[str, object]:
    return dispatcher.dispatch(method, {"protocolVersion": 1, **params})


def _open_saved(
    path: Path,
    atlas: _FakeAtlas,
) -> tuple[BridgeDispatcher, PlanningBridgeSession]:
    dispatcher = _dispatcher_with_atlas(atlas)
    session = register_planning_handlers(dispatcher)
    _call(dispatcher, "project.open", path=str(path))
    return dispatcher, session


def test_analysis_save_open_round_trip_and_plan_mutations_invalidate(tmp_path: Path) -> None:
    project, initial_revision = _project_with_probe_plan()
    assert project.atlas is not None
    exact_atlas = _FakeAtlas(project.atlas)
    state = _ProjectState(project=project, revision=initial_revision)
    analysis_dispatcher = _dispatcher_with_atlas(exact_atlas)
    register_major_vessel_handlers(
        analysis_dispatcher,
        get_project=lambda: state.project,
        get_revision=lambda: state.revision,
        replace_project=state.replace,
        graph_loader=_tiny_graph,
    )

    live = _call(
        analysis_dispatcher,
        "vessel.major.reference.analyze",
        **_analysis_params(
            state.project,
            state.revision,
            profile_confirmed=True,
            coverage_acknowledged=True,
        ),
    )
    assert len(state.project.probe_vessel_analyses) == 1
    persisted_before_save = state.project.probe_vessel_analyses[0].model_dump(mode="json")
    bundle = state.project.probe_vessel_analyses[0]
    assert bundle.analysis.risk_profile.required_margin_um == 10
    assert bundle.analysis.risk_profile.registration_uncertainty_um == 20
    assert bundle.analysis.risk_profile.confirmed_by_user is True
    assert bundle.analysis.risk_profile.reference_only_coverage_acknowledged is True
    assert bundle.analysis.provenance.registration_transform_id is None
    assert bundle.analysis.provenance.registration_uncertainty_bound_um is None
    assert bundle.analysis.provenance.tissue_distortion_uncertainty_bound_um is None
    assert bundle.analysis.provenance.uncertainty_bounds_reviewed is False
    assert len(bundle.analysis_sha256) == 64
    assert len(bundle.analysis.input_sha256) == 64
    assert bundle.analysis.provenance.source_archive_digest.startswith("sha256:")
    assert len(bundle.analysis.provenance.derived_asset_sha256) == 64

    save_dispatcher = _dispatcher_with_atlas(exact_atlas)
    save_session = register_planning_handlers(save_dispatcher)
    save_session.project = state.project
    save_session.project_revision = state.revision
    save_session.saved_revision = None
    destination = tmp_path / "vessel-round-trip.mouseplan"
    _call(save_dispatcher, "project.save", path=str(destination))
    saved_revision = state.revision + 1
    assert save_session.project_revision == saved_revision
    assert save_session.project is not None
    assert save_session.project.project_revision == saved_revision

    reopened_dispatcher, reopened_session = _open_saved(destination, exact_atlas)
    assert reopened_session.project is not None
    assert reopened_session.project_revision == saved_revision
    assert reopened_session.project.project_revision == saved_revision
    assert (
        reopened_session.project.probe_vessel_analyses[0].model_dump(mode="json")
        == persisted_before_save
    )
    plan = reopened_session.project.probe_plans[0]
    reopened_plan = _call(
        reopened_dispatcher,
        "probe.plan.get",
        projectId=str(reopened_session.project.project_uuid),
        planId=str(plan.plan_uuid),
    )
    restored = reopened_plan["majorVesselAnalysis"]
    assert isinstance(restored, dict)
    expected_restored = dict(live)
    expected_restored["projectRevision"] = saved_revision
    assert restored == expected_restored

    stale_params = _analysis_params(
        reopened_session.project,
        saved_revision - 1,
        profile_confirmed=True,
        coverage_acknowledged=True,
    )
    with pytest.raises(BridgeError) as stale:
        _call(
            reopened_dispatcher,
            "vessel.major.reference.analyze",
            **stale_params,
        )
    assert stale.value.code == "PROJECT_REVISION_CONFLICT"
    assert reopened_session.project.probe_vessel_analyses[0].analysis_sha256 == (
        bundle.analysis_sha256
    )

    manipulator = plan.manipulator_input
    assert manipulator is not None
    updated = _call(
        reopened_dispatcher,
        "probe.plan.update",
        projectId=str(reopened_session.project.project_uuid),
        expectedProjectRevision=reopened_session.project_revision,
        planId=str(plan.plan_uuid),
        expectedPlanInputSha256=plan.input_sha256,
        targetId=str(plan.source_target.target_uuid),
        modelId=plan.probe_model.model_id,
        modelVersion=plan.probe_model.model_version,
        name=f"{plan.name} updated",
        azimuthDegrees=manipulator.azimuth_deg,
        elevationDegrees=manipulator.elevation_deg,
        insertionDepthMicrometres=manipulator.insertion_depth_um,
        axialRotationDegrees=manipulator.axial_rotation_deg,
        customGeometryAcknowledged=plan.placement.custom_geometry_acknowledged,
    )
    assert updated["projectRevision"] == saved_revision + 1
    assert reopened_session.project.probe_vessel_analyses == []
    updated_plan = _mapping(updated["plan"])
    after_update = _call(
        reopened_dispatcher,
        "probe.plan.get",
        projectId=str(reopened_session.project.project_uuid),
        planId=updated_plan["planId"],
    )
    assert after_update["majorVesselAnalysis"] is None

    remove_dispatcher, remove_session = _open_saved(destination, exact_atlas)
    assert remove_session.project is not None
    remove_plan = remove_session.project.probe_plans[0]
    removed = _call(
        remove_dispatcher,
        "probe.plan.remove",
        projectId=str(remove_session.project.project_uuid),
        expectedProjectRevision=remove_session.project_revision,
        planId=str(remove_plan.plan_uuid),
        expectedPlanInputSha256=remove_plan.input_sha256,
    )
    assert removed["projectRevision"] == saved_revision + 1
    assert remove_session.project.probe_plans == []
    assert remove_session.project.probe_vessel_analyses == []
