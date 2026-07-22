"""Qualification tests for radius-aware major-vessel clearance."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.optimize import minimize_scalar

from mouse_brain_planner.analysis.vessel_clearance import (
    NO_CONFLICT_STATEMENT,
    ProbeShankASR,
    RadiusBearingVesselRuns,
    VesselClearanceInputError,
    analyze_probe_vessel_clearance,
)
from mouse_brain_planner.domain.vessel_clearance_models import (
    MajorVesselSourceProvenance,
    ProbeVesselResultStatus,
    VesselConflictClassification,
    VesselRiskProfile,
)
from mouse_brain_planner.surgery.measurements import finite_segment_closest_points


def _source() -> MajorVesselSourceProvenance:
    return MajorVesselSourceProvenance(
        source_id="synthetic-test-source",
        source_doi="10.0000/test",
        source_record_url="https://example.test/reference",
        source_paper_doi="10.0000/test-paper",
        source_version="test-v1",
        source_license="CC BY 4.0",
        dataset_title="Synthetic vessel fixture",
        authors=("Test Author",),
        specimen_id="synthetic-1",
        source_archive_digest="md5:00000000000000000000000000000000",
        derived_asset_sha256="0" * 64,
        extraction_algorithm_version="test-extractor-v1",
        minimum_included_diameter_um=30,
    )


def _profile(
    *,
    margin: float = 10,
    uncertainty: float = 10,
    confirmed: bool = True,
) -> VesselRiskProfile:
    return VesselRiskProfile(
        profile_id="mouse-major-vessel-test-v1",
        minimum_vessel_diameter_um=30,
        required_margin_um=margin,
        registration_uncertainty_um=uncertainty,
        source_or_lab_policy="Synthetic qualification fixture only.",
        confirmed_by_user=confirmed,
        reference_only_coverage_acknowledged=confirmed,
    )


def _horizontal_vessel(*, distance: float, repeats: int = 1) -> RadiusBearingVesselRuns:
    points: list[tuple[float, float, float]] = []
    offsets = [0]
    for _repeat in range(repeats):
        points.extend(((-10, 0, distance), (10, 0, distance)))
        offsets.append(len(points))
    return RadiusBearingVesselRuns(
        points_asr_um=np.asarray(points, dtype=np.float64),
        radii_um=np.full(len(points), 15.0, dtype=np.float64),
        run_offsets=np.asarray(offsets, dtype=np.int64),
        source_edge_indices=np.arange(repeats, dtype=np.int64),
    )


def _probe(*, shank_id: str = "shank-1", ml: float = 0) -> ProbeShankASR:
    return ProbeShankASR(
        shank_id=shank_id,
        entry_asr_um=np.asarray((0, 0, ml), dtype=np.float64),
        tip_asr_um=np.asarray((0, 100, ml), dtype=np.float64),
        envelope_radius_um=5,
    )


@pytest.mark.parametrize(
    ("distance", "expected_status", "expected_classification"),
    [
        (10, ProbeVesselResultStatus.INTERSECTION, VesselConflictClassification.INTERSECTION),
        (
            25,
            ProbeVesselResultStatus.MARGIN_VIOLATION,
            VesselConflictClassification.MARGIN_VIOLATION,
        ),
        (
            35,
            ProbeVesselResultStatus.UNCERTAINTY_VIOLATION,
            VesselConflictClassification.UNCERTAINTY_VIOLATION,
        ),
    ],
)
def test_classifies_physical_margin_and_uncertainty_boundaries(
    distance: float,
    expected_status: ProbeVesselResultStatus,
    expected_classification: VesselConflictClassification,
) -> None:
    result = analyze_probe_vessel_clearance(
        shanks=(_probe(),),
        vessels=_horizontal_vessel(distance=distance),
        risk_profile=_profile(),
        provenance=_source(),
    )

    assert result.result_status is expected_status
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.classification is expected_classification
    assert conflict.centerline_distance_um == pytest.approx(distance)
    assert conflict.vessel_diameter_um == pytest.approx(30)
    assert conflict.probe_envelope_radius_um == pytest.approx(5)
    assert conflict.geometric_surface_clearance_um == pytest.approx(distance - 20)
    assert conflict.uncertainty_adjusted_clearance_um == pytest.approx(distance - 40)
    assert conflict.insertion_depth_um == pytest.approx(0)


def test_no_conflict_uses_only_the_reviewed_bounded_statement() -> None:
    result = analyze_probe_vessel_clearance(
        shanks=(_probe(),),
        vessels=_horizontal_vessel(distance=50),
        risk_profile=_profile(),
        provenance=_source(),
    )

    assert result.result_status is ProbeVesselResultStatus.NO_CONFLICT_DETECTED
    assert result.statement == NO_CONFLICT_STATEMENT
    assert result.conflicts == ()
    assert result.minimum_uncertainty_adjusted_clearance_um == pytest.approx(10)
    assert "safe" not in result.statement.casefold()


def test_unconfirmed_reference_profile_returns_measurements_without_classification() -> None:
    result = analyze_probe_vessel_clearance(
        shanks=(_probe(),),
        vessels=_horizontal_vessel(distance=10),
        risk_profile=_profile(confirmed=False),
        provenance=_source(),
    )

    assert result.result_status is ProbeVesselResultStatus.INSUFFICIENT_GEOMETRY
    assert result.conflicts == ()
    assert result.minimum_geometric_clearance_um == pytest.approx(-10)
    assert "explicitly confirmed" in result.statement


def test_multi_shank_result_identifies_only_the_conflicting_shank() -> None:
    result = analyze_probe_vessel_clearance(
        shanks=(
            _probe(shank_id="near", ml=0),
            _probe(shank_id="far", ml=1_000),
        ),
        vessels=_horizontal_vessel(distance=10),
        risk_profile=_profile(),
        provenance=_source(),
    )

    assert result.result_status is ProbeVesselResultStatus.INTERSECTION
    assert {conflict.shank_id for conflict in result.conflicts} == {"near"}
    assert result.measured_segment_count == 2


def test_conflict_limit_is_deterministic_and_disclosed() -> None:
    result = analyze_probe_vessel_clearance(
        shanks=(_probe(),),
        vessels=_horizontal_vessel(distance=10, repeats=4),
        risk_profile=_profile(),
        provenance=_source(),
        maximum_conflicts=2,
    )

    assert result.conflicts_truncated
    assert len(result.conflicts) == 2
    assert [item.vessel_source_edge_index for item in result.conflicts] == [0, 1]


def test_vectorized_global_nearest_matches_shared_scalar_kernel() -> None:
    rng = np.random.default_rng(149)
    points = rng.normal(size=(30, 3)) * 100
    # One continuous run yields 29 nonzero segments with overwhelming probability.
    vessels = RadiusBearingVesselRuns(
        points_asr_um=points,
        radii_um=np.full(points.shape[0], 15.0),
        run_offsets=np.asarray((0, points.shape[0]), dtype=np.int64),
        source_edge_indices=np.asarray((17,), dtype=np.int64),
    )
    shank = ProbeShankASR(
        shank_id="random",
        entry_asr_um=np.asarray((-50, 25, 10), dtype=np.float64),
        tip_asr_um=np.asarray((90, -20, 70), dtype=np.float64),
        envelope_radius_um=5,
    )

    scalar_distances = [
        finite_segment_closest_points(
            shank.entry_asr_um,
            shank.tip_asr_um,
            points[index],
            points[index + 1],
        )[0]
        for index in range(points.shape[0] - 1)
    ]
    result = analyze_probe_vessel_clearance(
        shanks=(shank,),
        vessels=vessels,
        risk_profile=_profile(margin=0, uncertainty=0),
        provenance=_source(),
    )

    assert result.nearest_centerline_distance_um == pytest.approx(min(scalar_distances), abs=1e-10)
    assert result.minimum_geometric_clearance_um == pytest.approx(
        min(scalar_distances) - 20,
        abs=1e-10,
    )


def test_tapered_radius_minimization_catches_large_radius_endpoint() -> None:
    vessels = RadiusBearingVesselRuns(
        points_asr_um=np.asarray(((30, 0, 0), (40, 0, 0)), dtype=np.float64),
        radii_um=np.asarray((15, 40), dtype=np.float64),
        run_offsets=np.asarray((0, 2), dtype=np.int64),
        source_edge_indices=np.asarray((23,), dtype=np.int64),
    )
    probe = ProbeShankASR(
        shank_id="taper-regression",
        entry_asr_um=np.asarray((0, 0, 0), dtype=np.float64),
        tip_asr_um=np.asarray((0, 10, 0), dtype=np.float64),
        envelope_radius_um=5,
    )

    result = analyze_probe_vessel_clearance(
        shanks=(probe,),
        vessels=vessels,
        risk_profile=_profile(margin=0, uncertainty=0),
        provenance=_source(),
    )

    assert result.algorithm_version == "major-vessel-aabb-tapered-surface-v2"
    assert result.result_status is ProbeVesselResultStatus.INTERSECTION
    assert result.nearest_centerline_distance_um == pytest.approx(30)
    assert result.minimum_geometric_clearance_um == pytest.approx(-5)
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.vessel_source_edge_index == 23
    assert conflict.centerline_distance_um == pytest.approx(40)
    assert conflict.vessel_diameter_um == pytest.approx(80)
    assert conflict.geometric_surface_clearance_um == pytest.approx(-5)
    assert conflict.vessel_point.ap_um == pytest.approx(40)


def test_vectorized_tapered_minimum_matches_independent_scalar_oracle() -> None:
    rng = np.random.default_rng(20260722)
    probe = ProbeShankASR(
        shank_id="random-taper",
        entry_asr_um=np.asarray((-25, 10, 5), dtype=np.float64),
        tip_asr_um=np.asarray((75, 120, -40), dtype=np.float64),
        envelope_radius_um=7,
    )
    probe_direction = probe.tip_asr_um - probe.entry_asr_um
    probe_squared_length = float(np.dot(probe_direction, probe_direction))

    for edge_index in range(24):
        start = rng.normal(size=3) * 100
        end = start + rng.normal(size=3) * 80
        if np.linalg.norm(end - start) < 1e-6:
            end[0] += 1.0
        start_radius, end_radius = rng.uniform(15, 50, size=2)
        vessels = RadiusBearingVesselRuns(
            points_asr_um=np.asarray((start, end), dtype=np.float64),
            radii_um=np.asarray((start_radius, end_radius), dtype=np.float64),
            run_offsets=np.asarray((0, 2), dtype=np.int64),
            source_edge_indices=np.asarray((edge_index,), dtype=np.int64),
        )

        def scalar_objective(
            fraction: float,
            *,
            segment_start: np.ndarray = start,
            segment_end: np.ndarray = end,
            radius_start: float = start_radius,
            radius_end: float = end_radius,
        ) -> float:
            vessel_point = segment_start + fraction * (segment_end - segment_start)
            probe_fraction = float(
                np.clip(
                    np.dot(vessel_point - probe.entry_asr_um, probe_direction)
                    / probe_squared_length,
                    0.0,
                    1.0,
                )
            )
            probe_point = probe.entry_asr_um + probe_fraction * probe_direction
            radius = radius_start + fraction * (radius_end - radius_start)
            return float(np.linalg.norm(probe_point - vessel_point) - radius - 7.0)

        oracle = minimize_scalar(
            scalar_objective,
            bounds=(0.0, 1.0),
            method="bounded",
            options={"xatol": 1e-12, "maxiter": 500},
        )
        expected = min(
            scalar_objective(0.0),
            scalar_objective(float(oracle.x)),
            scalar_objective(1.0),
        )
        result = analyze_probe_vessel_clearance(
            shanks=(probe,),
            vessels=vessels,
            risk_profile=_profile(margin=0, uncertainty=0),
            provenance=_source(),
        )

        assert result.minimum_geometric_clearance_um == pytest.approx(expected, abs=1e-8)


def test_input_hash_is_stable_and_changes_with_margin() -> None:
    common = {
        "shanks": (_probe(),),
        "vessels": _horizontal_vessel(distance=50),
        "provenance": _source(),
    }
    first = analyze_probe_vessel_clearance(risk_profile=_profile(margin=10), **common)
    repeated = analyze_probe_vessel_clearance(risk_profile=_profile(margin=10), **common)
    changed = analyze_probe_vessel_clearance(risk_profile=_profile(margin=11), **common)

    assert first.input_sha256 == repeated.input_sha256
    assert first.input_sha256 != changed.input_sha256


def test_rejects_profile_threshold_that_does_not_match_asset() -> None:
    profile = _profile().model_copy(update={"minimum_vessel_diameter_um": 80})
    with pytest.raises(VesselClearanceInputError, match="pointwise threshold"):
        analyze_probe_vessel_clearance(
            shanks=(_probe(),),
            vessels=_horizontal_vessel(distance=50),
            risk_profile=profile,
            provenance=_source(),
        )


def test_rejects_malformed_or_zero_length_geometry() -> None:
    with pytest.raises(VesselClearanceInputError, match="N >= 2"):
        RadiusBearingVesselRuns(
            points_asr_um=np.zeros((1, 3)),
            radii_um=np.ones(1) * 15,
            run_offsets=np.asarray((0, 1), dtype=np.int64),
            source_edge_indices=np.asarray((0,), dtype=np.int64),
        )

    zero_length = RadiusBearingVesselRuns(
        points_asr_um=np.asarray(((1, 2, 3), (1, 2, 3)), dtype=np.float64),
        radii_um=np.asarray((15, 15), dtype=np.float64),
        run_offsets=np.asarray((0, 2), dtype=np.int64),
        source_edge_indices=np.asarray((0,), dtype=np.int64),
    )
    with pytest.raises(VesselClearanceInputError, match="zero-length"):
        analyze_probe_vessel_clearance(
            shanks=(_probe(),),
            vessels=zero_length,
            risk_profile=_profile(),
            provenance=_source(),
        )


def test_probe_requires_finite_distinct_points_and_positive_radius() -> None:
    with pytest.raises(VesselClearanceInputError, match="distinct"):
        ProbeShankASR(
            shank_id="same",
            entry_asr_um=np.zeros(3),
            tip_asr_um=np.zeros(3),
            envelope_radius_um=5,
        )
    with pytest.raises(VesselClearanceInputError, match="positive"):
        ProbeShankASR(
            shank_id="radius",
            entry_asr_um=np.zeros(3),
            tip_asr_um=np.ones(3),
            envelope_radius_um=math.nan,
        )
