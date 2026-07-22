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

import mouse_brain_planner.bridge.major_vessels as major_vessels_module
from mouse_brain_planner.bridge.major_vessels import (
    COORDINATE_QUALIFICATION_BLOCKING_REASONS,
    COORDINATE_QUALIFICATION_REPORT_FILENAME,
    COORDINATE_QUALIFICATION_REPORT_SHA256,
    MajorVesselReferenceBridge,
    _qualification_report_is_verified_rejection,
    register_major_vessel_handlers,
)
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher, BridgeError
from mouse_brain_planner.domain.atlas_models import AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.vasculature.lambada_major_vessels import (
    ASSET_SHA256,
    EXPECTED_RUN_COUNT,
    EXPECTED_RUN_POINT_COUNT,
    EXTRACTION_ALGORITHM_VERSION,
    MANDATORY_LIMITATIONS,
    SOURCE_ARCHIVE_SHA256,
    SOURCE_RECORD_DOI,
    LambadaMajorVesselError,
    LambadaMajorVesselGraph,
    LambadaMajorVesselProvenance,
    load_lambada_major_vessels,
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


def _tiny_graph() -> LambadaMajorVesselGraph:
    # Run zero crosses the test probe at [AP,DV,ML] = [4.5,2.0,4.5].
    # Run one is distant and proves offsets prevent an artificial connection.
    points = np.array(
        [
            [4.5, 2.0, 0.0],
            [4.5, 2.0, 9.0],
            [1_000.0, 1_000.0, 1_000.0],
            [1_100.0, 1_000.0, 1_000.0],
        ],
        dtype=np.float32,
    )
    radii = np.array([15.0, 15.0, 20.0, 20.0], dtype=np.float32)
    annotations = np.array([1, 1, 2, 2], dtype=np.int32)
    offsets = np.array([0, 2, 4], dtype=np.int64)
    source_edges = np.array([7, 9], dtype=np.int32)
    for array in (points, radii, annotations, offsets, source_edges):
        array.setflags(write=False)
    provenance = LambadaMajorVesselProvenance(
        dataset_title="Vascular graphs of the developing post-natal mouse brain",
        authors=("Nicolas Renier", "Elisa de Launoit", "Sophie Skriabine"),
        specimen_id="P60_606",
        record_doi=SOURCE_RECORD_DOI,
        record_url="https://zenodo.org/records/18876865",
        license="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        source_sha256="c" * 64,
        asset_sha256=ASSET_SHA256,
        extraction_algorithm_version=EXTRACTION_ALGORITHM_VERSION,
        minimum_radius_um=15.0,
        limitations=MANDATORY_LIMITATIONS,
    )
    return LambadaMajorVesselGraph(
        points_asr_um=points,
        radii_um=radii,
        source_annotation_ids=annotations,
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


def _allow_synthetic_reference(_bridge: MajorVesselReferenceBridge) -> None:
    """Test-only bypass for legacy synthetic geometry and analysis contracts."""


@pytest.fixture
def qualified_test_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        MajorVesselReferenceBridge,
        "_reject_unqualified_reference",
        _allow_synthetic_reference,
    )


def test_registration_omits_unqualified_capabilities_without_loading_geometry() -> None:
    dispatcher = _dispatcher_with_atlas(_exact_atlas())
    load_count = 0

    def loader() -> LambadaMajorVesselGraph:
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
    assert "auditedReferenceMajorVessels" not in capabilities
    assert "radiusAwareReferenceVesselAnalysis" not in capabilities
    assert load_count == 0


def test_planning_session_registers_fail_closed_major_vessel_methods() -> None:
    from tests.integration.test_bridge_probe_planning import _probe_dispatcher

    dispatcher, _session = _probe_dispatcher()
    hello = _call(dispatcher, "hello", client="planning-registration-test")
    capabilities = _mapping(hello["capabilities"])
    assert "auditedReferenceMajorVessels" not in capabilities
    assert "radiusAwareReferenceVesselAnalysis" not in capabilities
    with pytest.raises(BridgeError) as qualification_gate:
        _call(dispatcher, "vessel.major.reference.get")
    assert qualification_gate.value.code == "VESSEL_GEOMETRY_UNAVAILABLE"
    assert qualification_gate.value.details == {
        "qualificationReportSha256": COORDINATE_QUALIFICATION_REPORT_SHA256,
        "qualificationReportVerified": True,
        "reasonCodes": list(COORDINATE_QUALIFICATION_BLOCKING_REASONS),
    }


@pytest.mark.parametrize(
    "method",
    [
        "vessel.major.reference.get",
        "vessel.major.reference.geometry",
        "vessel.major.reference.analyze",
    ],
)
def test_unqualified_reference_endpoints_reject_before_loading_or_mutating(method: str) -> None:
    dispatcher = _dispatcher_with_atlas()
    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: pytest.fail("project must not be read"),
        get_revision=lambda: pytest.fail("revision must not be read"),
        replace_project=lambda _project: pytest.fail("project must not be replaced"),
        graph_loader=lambda: pytest.fail("graph must not be loaded"),
    )

    with pytest.raises(BridgeError) as rejected:
        _call(dispatcher, method)

    assert rejected.value.code == "VESSEL_GEOMETRY_UNAVAILABLE"
    assert "laterality and whole-brain coverage" in rejected.value.message
    assert rejected.value.details == {
        "qualificationReportSha256": COORDINATE_QUALIFICATION_REPORT_SHA256,
        "qualificationReportVerified": True,
        "reasonCodes": list(COORDINATE_QUALIFICATION_BLOCKING_REASONS),
    }


def test_packaged_rejection_report_is_exactly_digest_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = (
        Path(major_vessels_module.__file__).parent.parent
        / "assets"
        / "vasculature"
        / COORDINATE_QUALIFICATION_REPORT_FILENAME
    )

    assert hashlib.sha256(report_path.read_bytes()).hexdigest() == (
        COORDINATE_QUALIFICATION_REPORT_SHA256
    )
    assert _qualification_report_is_verified_rejection() is True

    monkeypatch.setattr(
        major_vessels_module,
        "COORDINATE_QUALIFICATION_REPORT_SHA256",
        "0" * 64,
    )
    assert _qualification_report_is_verified_rejection() is False

    dispatcher = _dispatcher_with_atlas()
    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: pytest.fail("project must not be read"),
        get_revision=lambda: pytest.fail("revision must not be read"),
        replace_project=lambda _project: pytest.fail("project must not be replaced"),
        graph_loader=lambda: pytest.fail("graph must not be loaded"),
    )
    with pytest.raises(BridgeError) as rejected:
        _call(dispatcher, "vessel.major.reference.geometry")
    assert rejected.value.code == "VESSEL_GEOMETRY_UNAVAILABLE"
    assert rejected.value.details["qualificationReportVerified"] is False


def test_reference_metadata_and_geometry_buffers_are_exact_and_hashed(
    qualified_test_reference: None,
) -> None:
    dispatcher = _dispatcher_with_atlas(_exact_atlas())
    graph = _tiny_graph()
    load_count = 0

    def loader() -> LambadaMajorVesselGraph:
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
    assert provenance["sourceDoi"] == SOURCE_RECORD_DOI
    assert provenance["sourceArchiveDigest"] == f"sha256:{SOURCE_ARCHIVE_SHA256}"
    assert provenance["derivedAssetSha256"] == ASSET_SHA256
    assert provenance["minimumIncludedDiameterMicrometres"] == 30.0
    assert provenance["physicalUnitsDeclared"] is True
    assert provenance["atlasScaleApplied"] is True
    assert provenance["geometrySourceAudited"] is True
    assert provenance["subjectSpecific"] is False
    assert provenance["pialVesselsExcluded"] is True
    assert provenance["choroidalVesselsExcluded"] is True
    assert provenance["arteryVeinClassificationAvailable"] is False
    assert provenance["registrationTransformId"] is None
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


def test_real_bundled_graph_round_trips_through_bridge_buffers(
    qualified_test_reference: None,
) -> None:
    dispatcher = _dispatcher_with_atlas(_exact_atlas())
    graph = load_lambada_major_vessels()
    register_major_vessel_handlers(
        dispatcher,
        get_project=lambda: pytest.fail("project not expected"),
        get_revision=lambda: 0,
        replace_project=_unexpected_project_replace,
        graph_loader=lambda: graph,
    )

    geometry = _call(dispatcher, "vessel.major.reference.geometry")
    assert geometry["pointCount"] == EXPECTED_RUN_POINT_COUNT
    assert geometry["runCount"] == EXPECTED_RUN_COUNT
    assert geometry["segmentCount"] == EXPECTED_RUN_POINT_COUNT - EXPECTED_RUN_COUNT
    np.testing.assert_array_equal(
        _decode_buffer(
            geometry["pointsASRMicrometres"],
            dtype=np.dtype("<f4"),
            scalar_type="float32",
            shape=(EXPECTED_RUN_POINT_COUNT, 3),
        ),
        graph.points_asr_um,
    )
    np.testing.assert_array_equal(
        _decode_buffer(
            geometry["radiiMicrometres"],
            dtype=np.dtype("<f4"),
            scalar_type="float32",
            shape=(EXPECTED_RUN_POINT_COUNT,),
        ),
        graph.radii_um,
    )
    np.testing.assert_array_equal(
        _decode_buffer(
            geometry["runOffsets"],
            dtype=np.dtype("<i8"),
            scalar_type="int64",
            shape=(EXPECTED_RUN_COUNT + 1,),
        ),
        graph.run_offsets,
    )
    np.testing.assert_array_equal(
        _decode_buffer(
            geometry["sourceEdgeIndices"],
            dtype=np.dtype("<i4"),
            scalar_type="int32",
            shape=(EXPECTED_RUN_COUNT,),
        ),
        graph.source_edge_indices,
    )
    assert _mapping(geometry["provenance"])["derivedAssetSha256"] == ASSET_SHA256
    assert geometry["limitations"] == list(MANDATORY_LIMITATIONS)


def test_integrity_failure_is_lazy_and_redacted_at_the_bridge_boundary(
    qualified_test_reference: None,
) -> None:
    dispatcher = _dispatcher_with_atlas(_exact_atlas())
    load_count = 0

    def failing_loader() -> LambadaMajorVesselGraph:
        nonlocal load_count
        load_count += 1
        raise LambadaMajorVesselError("test-only internal asset detail")

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
    assert failure.value.details == {"exceptionType": "LambadaMajorVesselError"}
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

    def loader() -> LambadaMajorVesselGraph:
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
    from tests.integration.test_bridge_probe_planning import (
        _calibrated_target,
        _create_plan,
        _probe_dispatcher,
    )

    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    assert session.project.atlas is not None
    exact_metadata = make_allen_metadata_test_double(25).model_copy(
        update={"metadata_sha256": session.project.atlas.metadata_sha256}
    )
    payload = session.project.model_dump(mode="python")
    payload["atlas"] = exact_metadata.model_dump(mode="python")
    return PlannerProject.model_validate(payload), session.project_revision


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
    assert provenance["registrationTransformId"] is None
    assert provenance["registrationUncertaintyBoundMicrometres"] is None
    assert provenance["tissueDistortionUncertaintyBoundMicrometres"] is None
    assert provenance["uncertaintyBoundsReviewed"] is False


def test_analysis_does_not_overwrite_project_when_revision_changes_during_compute(
    qualified_test_reference: None,
) -> None:
    project, revision = _project_with_probe_plan()
    assert project.atlas is not None
    state = _ProjectState(project=project, revision=revision)
    dispatcher = _dispatcher_with_atlas(_FakeAtlas(project.atlas))

    def concurrently_mutating_loader() -> LambadaMajorVesselGraph:
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

    def loader() -> LambadaMajorVesselGraph:
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
