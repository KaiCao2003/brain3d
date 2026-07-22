#!/usr/bin/env python3
"""Generate a fail-closed coordinate attestation for LAMBADA P60_606."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from mouse_brain_planner.vasculature.lambada_coordinate_qualification import (
    QUALIFICATION_ALGORITHM_VERSION,
    QUALIFICATION_SCHEMA_VERSION,
    LambadaCoordinateQualificationError,
    canonical_report_bytes,
    qualify_pinned_lambada_coordinates,
    write_canonical_report,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Qualify AP/DV signs and ML laterality for the exact pinned LAMBADA "
            "P60_606 graph against the exact Allen 25 um v1.2 atlas."
        )
    )
    parser.add_argument("source_graph", type=Path, help="extracted 606_graph_2024-12-03.gt")
    parser.add_argument(
        "atlas_directory",
        type=Path,
        help="exact BrainGlobe allen_mouse_25um_v1.2 package directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="canonical JSON report destination",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        report = qualify_pinned_lambada_coordinates(
            arguments.source_graph.expanduser(),
            arguments.atlas_directory.expanduser(),
        )
    except LambadaCoordinateQualificationError as error:
        report = {
            "schemaVersion": QUALIFICATION_SCHEMA_VERSION,
            "algorithmVersion": QUALIFICATION_ALGORITHM_VERSION,
            "status": "rejected",
            "qualificationError": str(error),
        }
    report_sha256 = write_canonical_report(arguments.output.expanduser(), report)
    payload = canonical_report_bytes(report)
    if hashlib.sha256(payload).hexdigest() != report_sha256:
        raise AssertionError("canonical report digest changed after writing")
    print(
        json.dumps(
            {
                "output": str(arguments.output.expanduser().resolve()),
                "reportSha256": report_sha256,
                "status": report["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "qualified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
