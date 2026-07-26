"""Bridge coverage for direct Pinpoint-style AP/ML surface probe planning."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from tests.fixtures.atlas_factory import make_allen_metadata_test_double
from tests.integration.test_bridge_calibration import _call, _FakeAtlas

from mouse_brain_planner.analysis.probe_region_service import annotation_array_sha256
from mouse_brain_planner.bridge.planning import PlanningBridgeSession, register_planning_handlers
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher, BridgeError
from mouse_brain_planner.persistence.project_io import save_project
from mouse_brain_planner.probes.catalog import (
    NEUROPIXELS_2_0_MODEL_VERSION,
    NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
    NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
)


def _surface_dispatcher(
    annotation: np.ndarray,
    *,
    create_project: bool,
) -> tuple[BridgeDispatcher, PlanningBridgeSession]:
    metadata = make_allen_metadata_test_double(25)
    reference = np.broadcast_to(
        np.zeros((1, 1, 1), dtype=np.uint16),
        metadata.shape_voxels,
    )
    atlas = _FakeAtlas(
        metadata=metadata,
        reference=reference,
        annotation=annotation,
    )
    context = BridgeContext(repository_factory=lambda: pytest.fail("repository not expected"))
    context.set_loaded_atlas(atlas)
    dispatcher = BridgeDispatcher(context)
    session = register_planning_handlers(dispatcher)
    if create_project:
        _call(
            dispatcher,
            "project.new",
            animalResearchOnlyAcknowledged=True,
            title="Direct atlas-surface test",
        )
    return dispatcher, session


def _annotation(*, surface_dv_index: int = 20) -> np.ndarray:
    annotation = np.zeros((528, 320, 456), dtype=np.uint8)
    for ap_index, ml_index in (
        (208, 228),
        (248, 268),
        (168, 188),
    ):
        annotation[ap_index, surface_dv_index:, ml_index] = 1
    return annotation


def _surface_create_params(session: PlanningBridgeSession) -> dict[str, object]:
    assert session.project is not None
    return {
        "projectId": str(session.project.project_uuid),
        "expectedProjectRevision": session.project_revision,
        "placementMode": "ATLAS_SURFACE_AP_ML",
        "modelId": NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        "modelVersion": NEUROPIXELS_2_0_MODEL_VERSION,
        "insertionAPMillimetres": 0.0,
        "insertionMLMillimetres": 0.0,
        "surfaceDepthMillimetres": 2.3,
        "sagittalAngleDegrees": 12.0,
        "probeLayoutRotationDegrees": 90,
    }


def test_direct_surface_create_and_update_need_no_target_calibration_or_checkbox() -> None:
    annotation = _annotation()
    dispatcher, session = _surface_dispatcher(annotation, create_project=True)
    assert session.project is not None
    assert session.project.subject_id is None
    assert session.project.calibrations == []
    assert session.project.unprojected_bregma_targets == []

    created = _call(
        dispatcher,
        "probe.plan.create",
        **_surface_create_params(session),
    )
    plan = created["plan"]
    assert isinstance(plan, dict)
    assert plan["name"] == "NP2003 · AP 0 · ML 0"
    assert plan["placementMode"] == "ATLAS_SURFACE_AP_ML"
    assert plan["targetId"] is None
    assert plan["targetLabel"] is None
    assert plan["calibrationId"] is None
    assert plan["calibrationVersion"] is None
    assert plan["sourceTarget"] is None
    assert plan["manipulatorInput"] is None
    assert plan["placementInput"] is None
    surface = plan["surfaceRelativeInput"]
    assert isinstance(surface, dict)
    assert surface["surfaceDepthMillimetres"] == 2.3
    assert surface["surfaceDVIndex"] == 20
    assert surface["annotationSha256"] == annotation_array_sha256(annotation)
    assert surface["surfaceEntry"] == {
        "atlasIdentifier": "allen_mouse_25um",
        "atlasVersion": "1.2",
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "componentOrder": ["AP", "DV", "ML"],
        "units": "micrometre",
        "apMicrometres": 5200.0,
        "dvMicrometres": 500.0,
        "mlMicrometres": 5700.0,
    }
    placement = plan["placement"]
    assert isinstance(placement, dict)
    inward = placement["inwardDirection"]
    lateral = placement["localLateralDirection"]
    assert isinstance(inward, dict)
    assert isinstance(lateral, dict)
    assert inward["ap"] < 0
    assert inward["ml"] == pytest.approx(0, abs=1e-12)
    assert inward["dv"] < 0
    assert lateral["ap"] == pytest.approx(0, abs=1e-12)
    assert lateral["ml"] == pytest.approx(1, abs=1e-12)
    assert lateral["dv"] == pytest.approx(0, abs=1e-12)
    provenance = plan["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["calibrationId"] is None
    assert provenance["calibrationSha256"] is None
    assert provenance["planningAlgorithmVersion"] == ("pinpoint-atlas-surface-ap-ml-depth-v4")

    updated = _call(
        dispatcher,
        "probe.plan.update",
        **{
            **_surface_create_params(session),
            "planId": plan["planId"],
            "expectedPlanInputSha256": plan["inputSha256"],
            "sagittalAngleDegrees": -12.0,
            "probeLayoutRotationDegrees": 0,
        },
    )
    updated_plan = updated["plan"]
    assert isinstance(updated_plan, dict)
    assert updated_plan["planVersion"] == 2
    updated_placement = updated_plan["placement"]
    assert isinstance(updated_placement, dict)
    updated_inward = updated_placement["inwardDirection"]
    updated_lateral = updated_placement["localLateralDirection"]
    assert isinstance(updated_inward, dict)
    assert isinstance(updated_lateral, dict)
    assert updated_inward["ap"] > 0
    assert updated_lateral["ap"] < 0
    assert updated_lateral["ml"] == pytest.approx(0, abs=1e-12)
    assert updated_lateral["dv"] < 0

    with pytest.raises(BridgeError) as extra_legacy_field:
        _call(
            dispatcher,
            "probe.plan.create",
            **{
                **_surface_create_params(session),
                "customGeometryAcknowledged": True,
            },
        )
    assert extra_legacy_field.value.code == "INVALID_PARAMS"


@pytest.mark.parametrize(
    ("ap_mm", "ml_mm", "expected_ap_um", "expected_ml_um", "hemisphere"),
    (
        (-1.0, -1.0, 6200.0, 6700.0, "left"),
        (1.0, 1.0, 4200.0, 4700.0, "right"),
    ),
)
def test_direct_surface_coordinates_preserve_final_operator_signs(
    ap_mm: float,
    ml_mm: float,
    expected_ap_um: float,
    expected_ml_um: float,
    hemisphere: str,
) -> None:
    dispatcher, session = _surface_dispatcher(_annotation(), create_project=True)

    created = _call(
        dispatcher,
        "probe.plan.create",
        **{
            **_surface_create_params(session),
            "insertionAPMillimetres": ap_mm,
            "insertionMLMillimetres": ml_mm,
        },
    )
    plan = created["plan"]
    assert isinstance(plan, dict)
    surface = plan["surfaceRelativeInput"]
    assert isinstance(surface, dict)
    entry = surface["surfaceEntry"]
    assert isinstance(entry, dict)
    assert entry["apMicrometres"] == expected_ap_um
    assert entry["mlMicrometres"] == expected_ml_um
    assert surface["mlSignConvention"] == ("ML positive animal right; ML negative animal left")
    assert ("left" if ml_mm < 0 else "right") == hemisphere


@pytest.mark.parametrize(
    ("model_id", "layout", "expected_count", "spacing_axis", "spacing_sign"),
    (
        (NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID, 0, 1, "apMicrometres", 1),
        (NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID, 0, 4, "apMicrometres", 1),
        (NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID, 90, 4, "mlMicrometres", -1),
    ),
)
def test_direct_products_publish_exact_distinct_shanks_for_each_layout(
    model_id: str,
    layout: int,
    expected_count: int,
    spacing_axis: str,
    spacing_sign: int,
) -> None:
    dispatcher, session = _surface_dispatcher(_annotation(), create_project=True)
    created = _call(
        dispatcher,
        "probe.plan.create",
        **{
            **_surface_create_params(session),
            "modelId": model_id,
            "sagittalAngleDegrees": 0.0,
            "probeLayoutRotationDegrees": layout,
        },
    )
    plan = created["plan"]
    assert isinstance(plan, dict)
    shanks = plan["shanks"]
    assert isinstance(shanks, list)
    assert [shank["shankId"] for shank in shanks] == [
        f"shank-{index}" for index in range(expected_count)
    ]
    assert len(shanks) == expected_count
    surface = plan["surfaceRelativeInput"]
    assert isinstance(surface, dict)
    surface_entry = surface["surfaceEntry"]
    assert isinstance(surface_entry, dict)
    shank_zero_entry = shanks[0]["entry"]
    assert isinstance(shank_zero_entry, dict)
    for axis in ("apMicrometres", "dvMicrometres", "mlMicrometres"):
        assert shank_zero_entry[axis] == surface_entry[axis]

    for shank in shanks:
        assert shank["surfaceEntry"] == shank["entry"]
        assert shank["totalLengthMicrometres"] == 10_000.0
        surface_vector = np.asarray(
            [shank["entry"][axis] for axis in ("apMicrometres", "dvMicrometres", "mlMicrometres")]
        )
        distal_vector = np.asarray(
            [shank["tip"][axis] for axis in ("apMicrometres", "dvMicrometres", "mlMicrometres")]
        )
        proximal_vector = np.asarray(
            [
                shank["proximalEnd"][axis]
                for axis in ("apMicrometres", "dvMicrometres", "mlMicrometres")
            ]
        )
        assert np.linalg.norm(distal_vector - surface_vector) == pytest.approx(2_300)
        assert np.linalg.norm(distal_vector - proximal_vector) == pytest.approx(10_000)
        assert np.linalg.norm(surface_vector - proximal_vector) == pytest.approx(7_700)
        assert shank["proximalEnd"]["dvMicrometres"] == pytest.approx(-7_200)
        assert shank["proximalEnd"]["insideAtlas"] is False

    centerlines = {
        (
            *(
                shank["entry"][axis]
                for axis in (
                    "apMicrometres",
                    "dvMicrometres",
                    "mlMicrometres",
                )
            ),
            *(
                shank["tip"][axis]
                for axis in (
                    "apMicrometres",
                    "dvMicrometres",
                    "mlMicrometres",
                )
            ),
            *(
                shank["proximalEnd"][axis]
                for axis in (
                    "apMicrometres",
                    "dvMicrometres",
                    "mlMicrometres",
                )
            ),
        )
        for shank in shanks
    }
    assert len(centerlines) == expected_count
    if expected_count == 4:
        entry_values = [shank["entry"][spacing_axis] for shank in shanks]
        tip_values = [shank["tip"][spacing_axis] for shank in shanks]
        expected_steps = [spacing_sign * 250.0] * 3
        assert np.diff(entry_values).tolist() == expected_steps
        assert np.diff(tip_values).tolist() == expected_steps

        fixed_axis = "mlMicrometres" if spacing_axis == "apMicrometres" else "apMicrometres"
        assert len({shank["entry"][fixed_axis] for shank in shanks}) == 1
        assert len({shank["tip"][fixed_axis] for shank in shanks}) == 1


def test_project_open_rejects_surface_plan_if_loaded_annotation_bytes_change(
    tmp_path: Path,
) -> None:
    annotation = _annotation()
    dispatcher, session = _surface_dispatcher(annotation, create_project=True)
    _call(
        dispatcher,
        "probe.plan.create",
        **_surface_create_params(session),
    )
    assert session.project is not None
    package = save_project(session.project, tmp_path / "surface-plan")

    annotation[0, 0, 0] = 1
    reopened_dispatcher, reopened_session = _surface_dispatcher(
        annotation,
        create_project=False,
    )
    with pytest.raises(BridgeError) as rejected:
        _call(reopened_dispatcher, "project.open", path=str(package))

    assert rejected.value.code == "PROJECT_OPEN_FAILED"
    assert rejected.value.details["projectOpened"] is False
    assert reopened_session.project is None
