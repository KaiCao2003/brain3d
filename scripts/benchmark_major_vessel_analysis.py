#!/usr/bin/env python3
"""Benchmark V3 analysis against the verified bundled LAMBADA asset.

The script performs no network access.  It reports one asset-load measurement,
one cold analysis, and bounded repeated warm analyses as machine-readable JSON.
Python/module startup time is intentionally outside the reported measurements.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
from statistics import median
from time import perf_counter

import numpy as np

from mouse_brain_planner.analysis.vessel_clearance import (
    ProbeShankASR,
    RadiusBearingVesselRuns,
    analyze_probe_vessel_clearance,
)
from mouse_brain_planner.domain.vessel_clearance_models import (
    MajorVesselSourceProvenance,
    ProbeVesselAnalysis,
    VesselRiskProfile,
)
from mouse_brain_planner.vasculature.lambada_major_vessels import (
    ASSET_SHA256,
    EXPECTED_RUN_COUNT,
    EXPECTED_RUN_POINT_COUNT,
    EXPECTED_SEGMENT_COUNT,
    EXTRACTION_ALGORITHM_VERSION,
    MINIMUM_DIAMETER_UM,
    SOURCE_ARCHIVE_SHA256,
    SOURCE_LICENSE,
    SOURCE_PAPER_DOI,
    SOURCE_RECORD_DOI,
    SOURCE_RECORD_URL,
    LambadaMajorVesselGraph,
    load_lambada_major_vessels,
)

MINIMUM_ITERATIONS = 5
MAXIMUM_ITERATIONS = 100
DEFAULT_ITERATIONS = 20
MAXIMUM_CONFLICTS = 10_000


def _percentile(values: list[float], fraction: float) -> float:
    """Return a linearly interpolated percentile for one nonempty sample."""

    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _darwin_sysctl(name: str) -> str | None:
    if platform.system() != "Darwin":
        return None
    try:
        completed = subprocess.run(
            ["sysctl", "-n", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _machine_payload() -> dict[str, str]:
    os_version = platform.mac_ver()[0] if platform.system() == "Darwin" else platform.release()
    return {
        "system": platform.system(),
        "osVersion": os_version,
        "architecture": platform.machine(),
        "hardwareModel": _darwin_sysctl("hw.model") or "unknown",
        "processor": (
            _darwin_sysctl("machdep.cpu.brand_string") or platform.processor() or "unknown"
        ),
    }


def _analysis_geometry(graph: LambadaMajorVesselGraph) -> RadiusBearingVesselRuns:
    return RadiusBearingVesselRuns(
        points_asr_um=np.asarray(graph.points_asr_um, dtype=np.float64),
        radii_um=np.asarray(graph.radii_um, dtype=np.float64),
        run_offsets=graph.run_offsets,
        source_edge_indices=np.asarray(graph.source_edge_indices, dtype=np.int64),
    )


def _source_provenance(graph: LambadaMajorVesselGraph) -> MajorVesselSourceProvenance:
    value = graph.provenance
    return MajorVesselSourceProvenance(
        source_id="lambada-p60-606-major-vessels-v1",
        source_doi=SOURCE_RECORD_DOI,
        source_record_url=SOURCE_RECORD_URL,
        source_paper_doi=SOURCE_PAPER_DOI,
        source_version="P60_606 / 606_graph_2024-12-03.gt",
        source_license=SOURCE_LICENSE,
        dataset_title=value.dataset_title,
        authors=value.authors,
        specimen_id=value.specimen_id,
        source_archive_digest=f"sha256:{SOURCE_ARCHIVE_SHA256}",
        derived_asset_sha256=value.asset_sha256,
        extraction_algorithm_version=EXTRACTION_ALGORITHM_VERSION,
        minimum_included_diameter_um=MINIMUM_DIAMETER_UM,
    )


def _benchmark_inputs() -> tuple[ProbeShankASR, VesselRiskProfile]:
    shank = ProbeShankASR(
        shank_id="benchmark-shank",
        entry_asr_um=np.asarray((6_600.0, 0.0, 5_700.0), dtype=np.float64),
        tip_asr_um=np.asarray((6_600.0, 6_000.0, 5_700.0), dtype=np.float64),
        envelope_radius_um=35.0,
    )
    profile = VesselRiskProfile(
        profile_id="benchmark-profile-v1",
        minimum_vessel_diameter_um=MINIMUM_DIAMETER_UM,
        required_margin_um=100.0,
        registration_uncertainty_um=100.0,
        source_or_lab_policy="Deterministic offline performance benchmark only.",
        confirmed_by_user=True,
        reference_only_coverage_acknowledged=True,
    )
    return shank, profile


def _run_analysis(
    *,
    shank: ProbeShankASR,
    vessels: RadiusBearingVesselRuns,
    profile: VesselRiskProfile,
    provenance: MajorVesselSourceProvenance,
) -> ProbeVesselAnalysis:
    return analyze_probe_vessel_clearance(
        shanks=(shank,),
        vessels=vessels,
        risk_profile=profile,
        provenance=provenance,
        maximum_conflicts=MAXIMUM_CONFLICTS,
    )


def _result_signature(result: ProbeVesselAnalysis) -> tuple[object, ...]:
    return (
        result.algorithm_version,
        result.input_sha256,
        result.result_status,
        result.candidate_segment_count,
        result.measured_segment_count,
        len(result.conflicts),
        result.conflicts_truncated,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark bundled major-vessel analysis without network access."
    )
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    args = parser.parse_args()
    if not MINIMUM_ITERATIONS <= args.iterations <= MAXIMUM_ITERATIONS:
        parser.error(f"--iterations must be in [{MINIMUM_ITERATIONS}, {MAXIMUM_ITERATIONS}]")

    loaded_at = perf_counter()
    graph = load_lambada_major_vessels()
    vessels = _analysis_geometry(graph)
    load_ms = (perf_counter() - loaded_at) * 1_000.0
    segment_count = int(np.sum(np.diff(graph.run_offsets) - 1))
    if (
        graph.points_asr_um.shape[0] != EXPECTED_RUN_POINT_COUNT
        or graph.run_offsets.size - 1 != EXPECTED_RUN_COUNT
        or segment_count != EXPECTED_SEGMENT_COUNT
        or graph.provenance.asset_sha256 != ASSET_SHA256
    ):
        raise RuntimeError("bundled benchmark geometry does not match its reviewed constants")

    shank, profile = _benchmark_inputs()
    provenance = _source_provenance(graph)
    cold_at = perf_counter()
    cold_result = _run_analysis(
        shank=shank,
        vessels=vessels,
        profile=profile,
        provenance=provenance,
    )
    cold_ms = (perf_counter() - cold_at) * 1_000.0
    expected_signature = _result_signature(cold_result)

    warm_ms: list[float] = []
    for _iteration in range(args.iterations):
        warm_at = perf_counter()
        warm_result = _run_analysis(
            shank=shank,
            vessels=vessels,
            profile=profile,
            provenance=provenance,
        )
        warm_ms.append((perf_counter() - warm_at) * 1_000.0)
        if _result_signature(warm_result) != expected_signature:
            raise RuntimeError("warm benchmark result changed across identical inputs")

    if cold_result.candidate_segment_count != cold_result.measured_segment_count:
        raise RuntimeError("exact measured count differs from the candidate count")
    if cold_result.conflicts_truncated:
        raise RuntimeError("benchmark conflict output was truncated")

    print(
        json.dumps(
            {
                "benchmark": "bundled-lambada-major-vessel-analysis-v1",
                "machine": _machine_payload(),
                "python": {
                    "implementation": platform.python_implementation(),
                    "version": platform.python_version(),
                },
                "asset": {
                    "sha256": graph.provenance.asset_sha256,
                    "points": int(graph.points_asr_um.shape[0]),
                    "runs": int(graph.run_offsets.size - 1),
                    "segments": segment_count,
                },
                "analysisInput": {
                    "entryASRMicrometres": shank.entry_asr_um.tolist(),
                    "tipASRMicrometres": shank.tip_asr_um.tolist(),
                    "probeEnvelopeRadiusMicrometres": shank.envelope_radius_um,
                    "requiredMarginMicrometres": profile.required_margin_um,
                    "registrationUncertaintyMicrometres": (profile.registration_uncertainty_um),
                },
                "analysisResult": {
                    "algorithmVersion": cold_result.algorithm_version,
                    "status": cold_result.result_status.value,
                    "candidateSegments": cold_result.candidate_segment_count,
                    "measuredSegments": cold_result.measured_segment_count,
                    "conflicts": len(cold_result.conflicts),
                },
                "timingMilliseconds": {
                    "load": round(load_ms, 3),
                    "cold": round(cold_ms, 3),
                    "warm": {
                        "iterations": args.iterations,
                        "median": round(median(warm_ms), 3),
                        "p95": round(_percentile(warm_ms, 0.95), 3),
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
