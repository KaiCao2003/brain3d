from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from numpy.typing import NDArray
from tests.fixtures.atlas_factory import make_allen_metadata_test_double

from mouse_brain_planner.bridge.major_vessels import (
    MajorVesselReferenceBridge,
    register_major_vessel_handlers,
)
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher, BridgeError
from mouse_brain_planner.domain.atlas_models import AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.vasculature.vessap_major_vessels import (
    ASSET_SHA256,
    EXTRACTION_ALGORITHM_VERSION,
    MANDATORY_LIMITATIONS,
    REGISTRATION_TRANSFORM_ID,
    SOURCE_BUNDLE_SHA256,
    SOURCE_PAPER_DOI,
    VesSAPMajorVesselError,
    VesSAPMajorVesselGraph,
    VesSAPMajorVesselProvenance,
)


@dataclass(slots=True)
class _FakeAtlas:
    metadata: AtlasMetadata
    brainglobe_atlasapi_version: str = "2.3.1"

    @property
    def reference(self) -> NDArray[np.uint16]:
        return np.zeros((1, 1, 1), dtype=np.uint16)

    @property
    def annotation(self) -> NDArray[np.int32]:
        return np.zeros((1, 1, 1), dtype=np.int32)

    @property
    def regions(self) -> list[RegionRecord]:
        return []

    def region_at(self, point: BrainGlobePhysicalPoint) -> RegionRecord | None:
        del point
        return None

    def root_mesh_file(self) -> Path:
        return Path("/__test_only__/root.obj")

    def mesh_file_for_region(self, region: RegionRecord | int | str) -> Path:
        del region
        return Path("/__test_only__/region.obj")


def _exact_atlas() -> _FakeAtlas:
    return _FakeAtlas(make_allen_metadata_test_double(25))


def _tiny_graph() -> VesSAPMajorVesselGraph:
    # Run zero crosses the test probe at [AP,DV,ML] = [4.5,2.0,5701.0].
    # Run one is distant and proves offsets prevent an artificial connection.
    points = np.array(
        [
            [4.5, 2.0, 5696.5],
            [4.5, 2.0, 5705.5],
            [1_000.0, 1_000.0, 1_000.0],
            [1_100.0, 1_000.0, 1_000.0],
        ],
        dtype=np.float32,
    )
    radii = np.array([15.0, 15.0, 20.0, 20.0], dtype=np.float32)
    offsets = np.array([0, 2, 4], dtype=np.int64)
    source_edges = np.array([7, 9], dtype=np.int32)
    for array in (points, radii, offsets, source_edges):
        array.setflags(write=False)
    provenance = VesSAPMajorVesselProvenance(
        dataset_title="Machine learning analysis of whole mouse brain vasculature",
        authors=("Mihail I. Todorov", "Johannes C. Paetzold", "Ali Ertürk"),
        specimen_id="BL6J-no1",
        record_doi=SOURCE_PAPER_DOI,
        record_url="https://www.discotechnologies.org/VesSAP/",
        license="CC BY-NC 4.0",
        license_url="https://creativecommons.org/licenses/by-nc/4.0/",
        source_sha256="c" * 64,
        asset_sha256=ASSET_SHA256,
        extraction_algorithm_version=EXTRACTION_ALGORITHM_VERSION,
        registration_transform_id=REGISTRATION_TRANSFORM_ID,
        minimum_radius_um=15.0,
        limitations=MANDATORY_LIMITATIONS,
    )
    return VesSAPMajorVesselGraph(
        points_asr_um=points,
        radii_um=radii,
        run_offsets=offsets,
        source_edge_indices=source_edges,
        provenance=provenance,
    )


def _dispatcher_with_atlas(atlas: _FakeAtlas | None = None) -> BridgeDispatcher:
    context = BridgeContext(repository_factory=lambda: pytest.fail("repository not expected"))
    context.loaded_atlas = atlas
    return BridgeDispatcher(context)


def _call(dispatcher: BridgeDispatcher, method: str, **params: object) -> dict[str, object]:
    return dispatcher.dispatch(method, {"protocolVersion": 1, **params})


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _unexpected_project_replace(project: PlannerProject) -> int:
    del project
    pytest.fail("project mutation not expected")


@dataclass(slots=True)
class _ProjectState:
    project: PlannerProject
    revision: int

    def replace(self, project: PlannerProject) -> int:
        assert project.project_revision == self.revision
        self.revision += 1
        self.project = project.model_copy(update={"project_revision": self.revision})
        return self.revision


def _decode_buffer(
    value: object,
    *,
    dtype: np.dtype[np.generic],
    scalar_type: str,
    shape: tuple[int, ...],
) -> NDArray[np.generic]:
    payload = _mapping(value)
    assert payload["scalarType"] == scalar_type
    assert payload["byteOrder"] == "littleEndian"
    assert payload["shape"] == list(shape)
    encoded = payload["dataBase64"]
    assert isinstance(encoded, str)
    raw = base64.b64decode(encoded, validate=True)
    assert payload["byteLength"] == len(raw)
    assert payload["sha256"] == hashlib.sha256(raw).hexdigest()
    return np.frombuffer(raw, dtype=dtype).reshape(shape)


def _allow_synthetic_analysis(_bridge: MajorVesselReferenceBridge) -> None:
    """Test-only bypass for the archived analysis implementation."""


@pytest.fixture
def qualified_test_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        MajorVesselReferenceBridge,
        "_reject_clearance_analysis",
        _allow_synthetic_analysis,
    )


def test_registration_declares_display_capability_without_loading_geometry() -> None:
    dispatcher = _dispatcher_with_atlas(_exact_atlas())
    load_count = 0

    def loader() -> VesSAPMajorVesselGraph:
        nonlocal load_count
        load_count += 1
        return _tiny_graph()

    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: pytest.fail("project not expected"),
        get_revision=lambda: 0,
        replace_project=_unexpected_project_replace,
        graph_loader=loader,
    )

    hello = _call(dispatcher, "hello", client="major-vessel-contract-test")
    capabilities = _mapping(hello["capabilities"])
    assert capabilities["auditedReferenceMajorVessels"] is True
    assert "radiusAwareReferenceVesselAnalysis" not in capabilities
    assert load_count == 0


def test_planning_session_omits_external_vessel_capability_when_data_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tests.integration.test_bridge_probe_planning import _probe_dispatcher

    monkeypatch.setenv("MOUSE_BRAIN_PLANNER_DATA_DIR", str(tmp_path))
    dispatcher, _session = _probe_dispatcher()
    hello = _call(dispatcher, "hello", client="planning-registration-test")
    capabilities = _mapping(hello["capabilities"])
    assert "auditedReferenceMajorVessels" not in capabilities
    assert "radiusAwareReferenceVesselAnalysis" not in capabilities


def test_clearance_analysis_rejects_before_loading_or_mutating() -> None:
    dispatcher = _dispatcher_with_atlas()
    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: pytest.fail("project must not be read"),
        get_revision=lambda: pytest.fail("revision must not be read"),
        replace_project=lambda _project: pytest.fail("project must not be replaced"),
        graph_loader=lambda: pytest.fail("graph must not be loaded"),
    )

    with pytest.raises(BridgeError) as rejected:
        _call(dispatcher, "vessel.major.reference.analyze")

    assert rejected.value.code == "VESSEL_ANALYSIS_UNAVAILABLE"
    assert "display-only" in rejected.value.message
    assert rejected.value.details == {
        "displayOnly": True,
        "subjectSpecific": False,
    }


def test_reference_metadata_and_geometry_buffers_are_exact_and_hashed(
    qualified_test_reference: None,
) -> None:
    dispatcher = _dispatcher_with_atlas(_exact_atlas())
    graph = _tiny_graph()
    load_count = 0

    def loader() -> VesSAPMajorVesselGraph:
        nonlocal load_count
        load_count += 1
        return graph

    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: pytest.fail("project not expected"),
        get_revision=lambda: 0,
        replace_project=_unexpected_project_replace,
        graph_loader=loader,
    )

    metadata = _call(dispatcher, "vessel.major.reference.get")
    assert metadata["status"] == "ready"
    assert metadata["sourceKind"] == "reference-individual-vessel-graph"
    assert metadata["subjectSpecific"] is False
    assert metadata["minimumDiameterMicrometres"] == 30.0
    assert metadata["pointCount"] == 4
    assert metadata["runCount"] == 2
    assert metadata["segmentCount"] == 2
    assert metadata["pathLengthMicrometres"] == pytest.approx(109.0)
    assert metadata["limitations"] == list(MANDATORY_LIMITATIONS)
    frame = _mapping(metadata["coordinateFrame"])
    assert frame == {
        "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
        "unit": "micrometres",
        "axisOrder": ["AP", "DV", "ML"],
        "voxelAnchor": "physical_um = continuous_voxel * 25; no half-voxel shift",
    }
    provenance = _mapping(metadata["provenance"])
    assert provenance["sourceDoi"] == SOURCE_PAPER_DOI
    assert provenance["sourceArchiveDigest"] == f"sha256:{SOURCE_BUNDLE_SHA256}"
    assert provenance["derivedAssetSha256"] == ASSET_SHA256
    assert provenance["minimumIncludedDiameterMicrometres"] == 30.0
    assert provenance["physicalUnitsDeclared"] is True
    assert provenance["atlasScaleApplied"] is True
    assert provenance["geometrySourceAudited"] is True
    assert provenance["subjectSpecific"] is False
    assert provenance["pialVesselsExcluded"] is False
    assert provenance["choroidalVesselsExcluded"] is False
    assert provenance["arteryVeinClassificationAvailable"] is False
    assert provenance["registrationTransformId"] == REGISTRATION_TRANSFORM_ID
    assert provenance["registrationUncertaintyBoundMicrometres"] is None
    assert provenance["tissueDistortionUncertaintyBoundMicrometres"] is None
    assert provenance["uncertaintyBoundsReviewed"] is False
    atlas = _mapping(metadata["atlas"])
    assert atlas["identifier"] == "allen_mouse_25um"
    assert atlas["version"] == "1.2"
    assert atlas["resolutionMicrometres"] == [25.0, 25.0, 25.0]
    assert atlas["shapeVoxels"] == [528, 320, 456]

    geometry = _call(dispatcher, "vessel.major.reference.geometry")
    assert geometry["encoding"] == "contiguous-little-endian-v1"
    assert geometry["pointCount"] == 4
    assert geometry["runCount"] == 2
    assert geometry["segmentCount"] == 2
    np.testing.assert_array_equal(
        _decode_buffer(
            geometry["pointsASRMicrometres"],
            dtype=np.dtype("<f4"),
            scalar_type="float32",
            shape=(4, 3),
        ),
        graph.points_asr_um,
    )
    np.testing.assert_array_equal(
        _decode_buffer(
            geometry["radiiMicrometres"],
            dtype=np.dtype("<f4"),
            scalar_type="float32",
            shape=(4,),
        ),
        graph.radii_um,
    )
    np.testing.assert_array_equal(
        _decode_buffer(
            geometry["runOffsets"],
            dtype=np.dtype("<i8"),
            scalar_type="int64",
            shape=(3,),
        ),
        graph.run_offsets,
    )
    np.testing.assert_array_equal(
        _decode_buffer(
            geometry["sourceEdgeIndices"],
            dtype=np.dtype("<i4"),
            scalar_type="int32",
            shape=(2,),
        ),
        graph.source_edge_indices,
    )
    assert geometry["provenance"] == provenance
    assert geometry["limitations"] == list(MANDATORY_LIMITATIONS)
    assert load_count == 1


def test_integrity_failure_is_lazy_and_redacted_at_the_bridge_boundary(
    qualified_test_reference: None,
) -> None:
    dispatcher = _dispatcher_with_atlas(_exact_atlas())
    load_count = 0

    def failing_loader() -> VesSAPMajorVesselGraph:
        nonlocal load_count
        load_count += 1
        raise VesSAPMajorVesselError("test-only internal asset detail")

    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: pytest.fail("project not expected"),
        get_revision=lambda: 0,
        replace_project=_unexpected_project_replace,
        graph_loader=failing_loader,
    )
    _call(dispatcher, "hello", client="lazy-integrity-test")
    assert load_count == 0

    with pytest.raises(BridgeError) as failure:
        _call(dispatcher, "vessel.major.reference.get")
    assert failure.value.code == "VESSEL_GEOMETRY_UNAVAILABLE"
    assert failure.value.details == {"exceptionType": "VesSAPMajorVesselError"}
    assert "internal asset detail" not in failure.value.message
    assert load_count == 1


@pytest.mark.parametrize(
    "metadata_update",
    [
        {"atlas_key": "allen_mouse_10um"},
        {"atlas_package_version": "1.1"},
        {"shape_voxels": (527, 320, 456)},
        {"resolution_um": (20.0, 25.0, 25.0)},
    ],
)
def test_reference_rejects_every_nonexact_atlas_contract(
    metadata_update: dict[str, object],
    qualified_test_reference: None,
) -> None:
    metadata = make_allen_metadata_test_double(25).model_copy(update=metadata_update)
    dispatcher = _dispatcher_with_atlas(_FakeAtlas(metadata))
    load_count = 0

    def loader() -> VesSAPMajorVesselGraph:
        nonlocal load_count
        load_count += 1
        return _tiny_graph()

    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: pytest.fail("project not expected"),
        get_revision=lambda: 0,
        replace_project=_unexpected_project_replace,
        graph_loader=loader,
    )

    with pytest.raises(BridgeError) as rejected:
        _call(dispatcher, "vessel.major.reference.get")
    assert rejected.value.code == "ATLAS_IDENTITY_MISMATCH"
    assert load_count == 0


def _project_with_probe_plan() -> tuple[PlannerProject, int]:
    from tests.integration.test_bridge_calibration import (
        _atlas_point,
        _create_params,
        _set_active,
        _source_point,
    )

    from mouse_brain_planner.bridge.planning import register_planning_handlers
    from mouse_brain_planner.probes.catalog import (
        NEUROPIXELS_2_0_MODEL_VERSION,
        NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
    )

    dispatcher = _dispatcher_with_atlas(_exact_atlas())
    session = register_planning_handlers(dispatcher)
    _call(
        dispatcher,
        "project.new",
        animalResearchOnlyAcknowledged=True,
        title="Major-vessel probe test",
        subjectId="mouse-A",
    )
    calibration_params = _create_params(session)
    skull_landmarks = _mapping(calibration_params["skullLandmarks"])
    skull_landmarks["leftSkull"] = _source_point(0, -25, 0)
    skull_landmarks["rightSkull"] = _source_point(0, 25, 0)
    atlas_landmarks = _mapping(calibration_params["atlasLandmarks"])
    atlas_landmarks.update(
        bregma=_atlas_point(3.5, 3.5, 5700),
        lambdaPoint=_atlas_point(5.5, 3.5, 5700),
        leftSkull=_atlas_point(3.5, 3.5, 5725),
        rightSkull=_atlas_point(3.5, 3.5, 5675),
    )
    created_calibration = _call(
        dispatcher,
        "calibration.create",
        **calibration_params,
    )
    calibration = _mapping(created_calibration["calibration"])
    calibration_id = calibration["calibrationId"]
    assert isinstance(calibration_id, str)
    _set_active(dispatcher, session, calibration_id)
    assert session.project is not None
    added_target = _call(
        dispatcher,
        "implant.add",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        label="major-vessel test target",
        apMillimetres=-0.001,
        mlMillimetres=-0.001,
        dvMillimetres=-0.001,
    )
    target = _mapping(added_target["target"])
    target_id = target["targetId"]
    assert isinstance(target_id, str)
    _call(
        dispatcher,
        "probe.plan.create",
        projectId=str(session.project.project_uuid),
        expectedProjectRevision=session.project_revision,
        targetId=target_id,
        modelId=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        modelVersion=NEUROPIXELS_2_0_MODEL_VERSION,
        name="Vertical NP2 single-shank major-vessel test",
        azimuthDegrees=0,
        elevationDegrees=-90,
        insertionDepthMicrometres=4,
        axialRotationDegrees=0,
        customGeometryAcknowledged=True,
    )
    assert session.project is not None
    return session.project, session.project_revision


def _analysis_params(
    project: PlannerProject,
    revision: int,
    *,
    profile_confirmed: bool,
    coverage_acknowledged: bool,
) -> dict[str, object]:
    plan = project.probe_plans[0]
    return {
        "projectId": str(project.project_uuid),
        "expectedProjectRevision": revision,
        "planId": str(plan.plan_uuid),
        "expectedPlanInputSha256": plan.input_sha256,
        "requiredMarginMicrometres": 10.0,
        "registrationUncertaintyMicrometres": 20.0,
        "riskProfileConfirmed": profile_confirmed,
        "referenceCoverageAcknowledged": coverage_acknowledged,
        "maximumConflicts": 10,
    }


def test_analysis_requires_both_acknowledgements_before_classifying_conflicts(
    qualified_test_reference: None,
) -> None:
    project, revision = _project_with_probe_plan()
    assert project.atlas is not None
    state = _ProjectState(project=project, revision=revision)
    dispatcher = _dispatcher_with_atlas(_FakeAtlas(project.atlas))
    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: state.project,
        get_revision=lambda: state.revision,
        replace_project=state.replace,
        graph_loader=_tiny_graph,
    )

    for profile_confirmed, coverage_acknowledged in (
        (False, False),
        (True, False),
        (False, True),
    ):
        prior_revision = state.revision
        response = _call(
            dispatcher,
            "vessel.major.reference.analyze",
            **_analysis_params(
                state.project,
                state.revision,
                profile_confirmed=profile_confirmed,
                coverage_acknowledged=coverage_acknowledged,
            ),
        )
        assert response["projectRevision"] == prior_revision + 1 == state.revision
        assert len(state.project.probe_vessel_analyses) == 1
        analysis = _mapping(response["analysis"])
        assert response["limitations"] == list(MANDATORY_LIMITATIONS)
        assert analysis["resultStatus"] == "insufficientGeometry"
        assert analysis["conflicts"] == []
        assert analysis["conflictsTruncated"] is False
        assert analysis["usableForNavigation"] is False
        profile = _mapping(analysis["riskProfile"])
        assert profile["confirmedByUser"] is profile_confirmed
        assert profile["referenceOnlyCoverageAcknowledged"] is coverage_acknowledged
        assert "explicitly confirmed" in str(analysis["statement"])

    confirmed = _call(
        dispatcher,
        "vessel.major.reference.analyze",
        **_analysis_params(
            state.project,
            state.revision,
            profile_confirmed=True,
            coverage_acknowledged=True,
        ),
    )
    assert confirmed["projectId"] == str(project.project_uuid)
    assert confirmed["projectRevision"] == state.revision
    assert confirmed["planId"] == str(project.probe_plans[0].plan_uuid)
    assert confirmed["planInputSha256"] == project.probe_plans[0].input_sha256
    assert confirmed["limitations"] == list(MANDATORY_LIMITATIONS)
    analysis = _mapping(confirmed["analysis"])
    assert analysis["algorithmVersion"] == "major-vessel-aabb-tapered-surface-v3"
    assert analysis["resultStatus"] == "intersection"
    assert analysis["candidateSegmentCount"] == 1
    assert analysis["measuredSegmentCount"] == 1
    assert analysis["conflictsTruncated"] is False
    assert analysis["usableForNavigation"] is False
    warnings = analysis["warnings"]
    assert isinstance(warnings, list)
    assert any("without vascular-type classification" in str(item) for item in warnings)
    conflicts = analysis["conflicts"]
    assert isinstance(conflicts, list)
    assert len(conflicts) == 1
    conflict = _mapping(conflicts[0])
    assert conflict["classification"] == "intersection"
    assert conflict["vesselSourceEdgeIndex"] == 7
    assert conflict["vesselRunIndex"] == 0
    assert conflict["vesselSegmentIndexInRun"] == 0
    assert conflict["vesselDiameterMicrometres"] == 30.0
    assert conflict["subjectSpecific"] is False
    assert _mapping(conflict["probePoint"])["frameId"] == "BRAINGLOBE_PHYSICAL_ASR_UM"
    assert _mapping(conflict["vesselPoint"])["frameId"] == "BRAINGLOBE_PHYSICAL_ASR_UM"
    provenance = _mapping(analysis["provenance"])
    assert provenance["physicalUnitsDeclared"] is True
    assert provenance["atlasScaleApplied"] is True
    assert provenance["registrationTransformId"] == REGISTRATION_TRANSFORM_ID
    assert provenance["registrationUncertaintyBoundMicrometres"] is None
    assert provenance["tissueDistortionUncertaintyBoundMicrometres"] is None
    assert provenance["uncertaintyBoundsReviewed"] is False


def test_analysis_rejects_same_target_rehashed_alternate_probe_before_loading_graph(
    qualified_test_reference: None,
) -> None:
    from tests.integration.test_bridge_probe_planning import (
        _same_target_alternate_trajectory_rehashed_plan,
    )

    project, revision = _project_with_probe_plan()
    assert project.atlas is not None
    forged = _same_target_alternate_trajectory_rehashed_plan(
        project,
        project.probe_plans[0],
    )
    project.probe_plans[0] = forged
    state = _ProjectState(project=project, revision=revision)
    dispatcher = _dispatcher_with_atlas(_FakeAtlas(project.atlas))
    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: state.project,
        get_revision=lambda: state.revision,
        replace_project=state.replace,
        graph_loader=lambda: pytest.fail("forged geometry must be rejected before graph loading"),
    )

    with pytest.raises(BridgeError) as rejection:
        _call(
            dispatcher,
            "vessel.major.reference.analyze",
            **_analysis_params(
                state.project,
                state.revision,
                profile_confirmed=True,
                coverage_acknowledged=True,
            ),
        )

    assert rejection.value.code == "PROBE_PLAN_PROJECTION_INVALID"
    assert "placement geometry does not match" in rejection.value.details["reason"]
    assert state.revision == revision
    assert state.project.probe_vessel_analyses == []


def test_analysis_does_not_overwrite_project_when_revision_changes_during_compute(
    qualified_test_reference: None,
) -> None:
    project, revision = _project_with_probe_plan()
    assert project.atlas is not None
    state = _ProjectState(project=project, revision=revision)
    dispatcher = _dispatcher_with_atlas(_FakeAtlas(project.atlas))

    def concurrently_mutating_loader() -> VesSAPMajorVesselGraph:
        state.revision += 1
        state.project = state.project.model_copy(update={"project_revision": state.revision})
        return _tiny_graph()

    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: state.project,
        get_revision=lambda: state.revision,
        replace_project=state.replace,
        graph_loader=concurrently_mutating_loader,
    )
    with pytest.raises(BridgeError) as stale:
        _call(
            dispatcher,
            "vessel.major.reference.analyze",
            **_analysis_params(
                project,
                revision,
                profile_confirmed=True,
                coverage_acknowledged=True,
            ),
        )

    assert stale.value.code == "ANALYSIS_STALE"
    assert stale.value.details == {"analysisStored": False}
    assert state.revision == revision + 1
    assert state.project.probe_vessel_analyses == []


def test_analysis_rejects_stale_hash_and_nonboolean_acknowledgement_before_loading_graph(
    qualified_test_reference: None,
) -> None:
    project, revision = _project_with_probe_plan()
    assert project.atlas is not None
    state = _ProjectState(project=project, revision=revision)
    dispatcher = _dispatcher_with_atlas(_FakeAtlas(project.atlas))
    load_count = 0

    def loader() -> VesSAPMajorVesselGraph:
        nonlocal load_count
        load_count += 1
        return _tiny_graph()

    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: state.project,
        get_revision=lambda: state.revision,
        replace_project=state.replace,
        graph_loader=loader,
    )
    stale_params = _analysis_params(
        project,
        revision,
        profile_confirmed=True,
        coverage_acknowledged=True,
    )
    stale_params["expectedPlanInputSha256"] = "0" * 64
    with pytest.raises(BridgeError) as stale:
        _call(dispatcher, "vessel.major.reference.analyze", **stale_params)
    assert stale.value.code == "ANALYSIS_STALE"
    assert load_count == 0

    invalid_params = _analysis_params(
        project,
        revision,
        profile_confirmed=True,
        coverage_acknowledged=True,
    )
    invalid_params["riskProfileConfirmed"] = 1
    with pytest.raises(BridgeError) as invalid:
        _call(dispatcher, "vessel.major.reference.analyze", **invalid_params)
    assert invalid.value.code == "INVALID_PARAMS"
    assert load_count == 0
