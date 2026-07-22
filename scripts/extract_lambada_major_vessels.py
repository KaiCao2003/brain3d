#!/usr/bin/env python3
"""Build the pinned compact LAMBADA P60_606 major-vessel asset."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from mouse_brain_planner.vasculature.lambada_major_vessels import (
    ASSET_FILENAME,
    MANIFEST_FILENAME,
    build_asset_manifest,
    bundled_asset_paths,
    extract_pinned_lambada_major_vessels,
    write_asset_manifest,
    write_deterministic_npz,
)


def _arguments() -> argparse.Namespace:
    bundled_asset, bundled_manifest = bundled_asset_paths()
    parser = argparse.ArgumentParser(
        description=(
            "Verify the exact 12 GB P60_606 graph and derive the reviewed >=15 um radius "
            "in-bounds polyline runs."
        )
    )
    parser.add_argument("source_graph", type=Path, help="extracted 606_graph_2024-12-03.gt")
    parser.add_argument(
        "--output",
        type=Path,
        default=bundled_asset,
        help=f"asset destination (default: {bundled_asset})",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=bundled_manifest,
        help=f"manifest destination (default: {bundled_manifest})",
    )
    return parser.parse_args()


def main() -> int:
    """Run the fail-closed extraction and byte-reproducibility check."""

    arguments = _arguments()
    source = arguments.source_graph.expanduser()
    output = arguments.output.expanduser()
    manifest_path = arguments.manifest.expanduser()
    if output.name != ASSET_FILENAME:
        raise SystemExit(f"--output filename must be {ASSET_FILENAME}")
    if manifest_path.name != MANIFEST_FILENAME:
        raise SystemExit(f"--manifest filename must be {MANIFEST_FILENAME}")
    if output.parent != manifest_path.parent:
        raise SystemExit("the asset and manifest must be adjacent")

    data, report = extract_pinned_lambada_major_vessels(source)
    asset_sha256, asset_size_bytes = write_deterministic_npz(output, data)
    with tempfile.TemporaryDirectory(prefix="lambada-major-vessels-") as temporary_directory:
        reproducibility_path = Path(temporary_directory) / ASSET_FILENAME
        repeated_sha256, repeated_size = write_deterministic_npz(reproducibility_path, data)
    if (repeated_sha256, repeated_size) != (asset_sha256, asset_size_bytes):
        raise SystemExit("deterministic asset reproduction failed")

    manifest = build_asset_manifest(
        asset_sha256=asset_sha256,
        asset_size_bytes=asset_size_bytes,
        data=data,
        report=report,
    )
    write_asset_manifest(manifest_path, manifest)
    print(
        json.dumps(
            {
                "asset": str(output.resolve()),
                "asset_sha256": asset_sha256,
                "asset_size_bytes": asset_size_bytes,
                "manifest": str(manifest_path.resolve()),
                "report": asdict(report),
                "reproducible": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
