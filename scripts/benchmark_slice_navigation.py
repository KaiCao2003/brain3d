#!/usr/bin/env python3
"""Benchmark real cached-atlas slice navigation before and after the fused RPC.

The benchmark never downloads data. It measures backend dispatch, independent
slice-state publication, full-resolution rendering, PNG encoding, and base64
construction. NDJSON pipe scheduling and Swift decoding are intentionally not
included, so the reported improvement is a conservative backend-only result.
"""

from __future__ import annotations

import argparse
import json
from statistics import median
from time import perf_counter

from mouse_brain_planner.atlas.brainglobe_adapter import BrainGlobeAtlasRepository
from mouse_brain_planner.bridge.planning import register_planning_handlers
from mouse_brain_planner.bridge.server import BridgeContext, BridgeDispatcher


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def _summary(milliseconds: list[float]) -> dict[str, float]:
    return {
        "medianMilliseconds": round(median(milliseconds), 3),
        "p95Milliseconds": round(_percentile(milliseconds, 0.95), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=12)
    args = parser.parse_args()
    if args.iterations < 4 or args.iterations > 1_000:
        parser.error("--iterations must be in [4, 1000]")

    opened_at = perf_counter()
    repository = BrainGlobeAtlasRepository()
    atlas = repository.open(
        "allen_mouse_25um",
        package_version="1.2",
        allow_download=False,
    )
    atlas_open_seconds = perf_counter() - opened_at
    context = BridgeContext(repository_factory=lambda: repository)
    context.set_loaded_atlas(atlas)
    dispatcher = BridgeDispatcher(context)
    register_planning_handlers(dispatcher)
    created = dispatcher.dispatch(
        "project.new",
        {"protocolVersion": 1, "animalResearchOnlyAcknowledged": True},
    )
    project_id = created["projectId"]
    if not isinstance(project_id, str):
        raise RuntimeError("project.new returned a non-string projectId")
    revision = 1
    orientation_centres = {
        "coronal": atlas.metadata.shape_voxels[0] // 2,
        "sagittal": atlas.metadata.shape_voxels[2] // 2,
        "horizontal": atlas.metadata.shape_voxels[1] // 2,
    }
    results: dict[str, object] = {}
    for orientation, centre in orientation_centres.items():
        indices = [centre + ((step * 5) % 11) - 5 for step in range(args.iterations)]

        # Warm volume pages and both encoder paths without retaining the same
        # two slice-cache entries used by the measured sequence.
        warmed = dispatcher.dispatch(
            "viewer.slice.render",
            {
                "protocolVersion": 1,
                "projectId": project_id,
                "expectedProjectRevision": revision,
                "orientation": orientation,
                "index": centre,
            },
        )
        revision = int(warmed["projectRevision"])
        dispatcher.dispatch(
            "atlas.slice",
            {"protocolVersion": 1, "orientation": orientation, "index": centre},
        )

        separated_ms: list[float] = []
        for index in indices:
            started = perf_counter()
            mutation = dispatcher.dispatch(
                "viewer.slice.set",
                {
                    "protocolVersion": 1,
                    "projectId": project_id,
                    "expectedProjectRevision": revision,
                    "orientation": orientation,
                    "index": index,
                },
            )
            revision = int(mutation["projectRevision"])
            dispatcher.dispatch(
                "atlas.slice",
                {"protocolVersion": 1, "orientation": orientation, "index": index},
            )
            separated_ms.append((perf_counter() - started) * 1_000.0)

        fused_ms: list[float] = []
        for index in reversed(indices):
            started = perf_counter()
            mutation = dispatcher.dispatch(
                "viewer.slice.render",
                {
                    "protocolVersion": 1,
                    "projectId": project_id,
                    "expectedProjectRevision": revision,
                    "orientation": orientation,
                    "index": index,
                },
            )
            revision = int(mutation["projectRevision"])
            fused_ms.append((perf_counter() - started) * 1_000.0)

        old_median = median(separated_ms)
        fused_median = median(fused_ms)
        results[orientation] = {
            "separateViewerSetPlusAtlasSlice": _summary(separated_ms),
            "fusedViewerSliceRender": _summary(fused_ms),
            "medianSpeedup": round(old_median / fused_median, 2),
            "fullResolution": True,
            "losslessPng": True,
        }

    print(
        json.dumps(
            {
                "atlas": {
                    "identifier": atlas.metadata.atlas_key,
                    "version": atlas.metadata.atlas_package_version,
                    "shapeVoxels": list(atlas.metadata.shape_voxels),
                    "atlasOpenSeconds": round(atlas_open_seconds, 3),
                },
                "iterationsPerPath": args.iterations,
                "results": results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
