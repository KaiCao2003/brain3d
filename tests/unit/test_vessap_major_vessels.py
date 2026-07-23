from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from mouse_brain_planner.vasculature.vessap_major_vessels import (
    ASSET_FILENAME,
    ASSET_SHA256,
    EXPECTED_PATH_LENGTH_UM,
    EXPECTED_POINT_COUNT,
    EXPECTED_RUN_COUNT,
    EXPECTED_SEGMENT_COUNT,
    MANDATORY_LIMITATIONS,
    MANIFEST_FILENAME,
    MINIMUM_RADIUS_UM,
    REGISTRATION_TRANSFORM_ID,
    SOURCE_LICENSE,
    SOURCE_SPECIMEN_ID,
    VesSAPMajorVesselError,
    bundled_asset_paths,
    load_vessap_major_vessels,
)


def test_bundled_vessap_graph_is_exact_immutable_physical_asr_geometry() -> None:
    graph = load_vessap_major_vessels()

    assert graph.points_asr_um.shape == (EXPECTED_POINT_COUNT, 3)
    assert graph.radii_um.shape == (EXPECTED_POINT_COUNT,)
    assert graph.run_count == EXPECTED_RUN_COUNT
    assert graph.run_offsets.shape == (EXPECTED_RUN_COUNT + 1,)
    assert EXPECTED_POINT_COUNT - graph.run_count == EXPECTED_SEGMENT_COUNT
    assert graph.points_asr_um.dtype == np.dtype("<f4")
    assert graph.radii_um.dtype == np.dtype("<f4")
    assert graph.run_offsets.dtype == np.dtype("<i8")
    assert graph.source_edge_indices.dtype == np.dtype("<i4")
    assert not graph.points_asr_um.flags.writeable
    assert not graph.radii_um.flags.writeable
    assert not graph.run_offsets.flags.writeable
    assert not graph.source_edge_indices.flags.writeable
    assert bool(np.all(graph.points_asr_um >= 0.0))
    assert bool(np.all(graph.points_asr_um < np.array([13_200.0, 8_000.0, 11_400.0])))
    assert float(np.min(graph.radii_um)) >= MINIMUM_RADIUS_UM
    assert graph.provenance.specimen_id == SOURCE_SPECIMEN_ID
    assert graph.provenance.license == SOURCE_LICENSE
    assert graph.provenance.asset_sha256 == ASSET_SHA256
    assert graph.provenance.registration_transform_id == REGISTRATION_TRANSFORM_ID
    assert graph.provenance.limitations == MANDATORY_LIMITATIONS
    assert any("display-only" in item for item in graph.provenance.limitations)
    assert any("capillaries" in item for item in graph.provenance.limitations)

    deltas = graph.points_asr_um[1:].astype(np.float64) - graph.points_asr_um[:-1].astype(
        np.float64
    )
    keep = np.ones(deltas.shape[0], dtype=np.bool_)
    keep[graph.run_offsets[1:-1] - 1] = False
    assert float(np.linalg.norm(deltas[keep], axis=1).sum()) == pytest.approx(
        EXPECTED_PATH_LENGTH_UM,
        abs=1e-3,
    )

    assert not graph.run_points_asr_um(0).flags.writeable
    with pytest.raises(TypeError, match="integer"):
        graph.run_points_asr_um(True)
    with pytest.raises(IndexError, match="outside"):
        graph.run_points_asr_um(graph.run_count)


def test_vessap_loader_rejects_asset_byte_tampering(tmp_path: Path) -> None:
    bundled_asset, bundled_manifest = bundled_asset_paths()
    copied_asset = tmp_path / ASSET_FILENAME
    copied_manifest = tmp_path / MANIFEST_FILENAME
    shutil.copyfile(bundled_asset, copied_asset)
    shutil.copyfile(bundled_manifest, copied_manifest)
    payload = bytearray(copied_asset.read_bytes())
    payload[len(payload) // 2] ^= 0x01
    copied_asset.write_bytes(payload)

    with pytest.raises(VesSAPMajorVesselError, match="SHA-256"):
        load_vessap_major_vessels(copied_asset, copied_manifest)


def test_vessap_loader_rejects_relaxed_display_only_limitations(tmp_path: Path) -> None:
    bundled_asset, bundled_manifest = bundled_asset_paths()
    copied_asset = tmp_path / ASSET_FILENAME
    copied_manifest = tmp_path / MANIFEST_FILENAME
    shutil.copyfile(bundled_asset, copied_asset)
    manifest = json.loads(bundled_manifest.read_text(encoding="utf-8"))
    manifest["limitations"] = manifest["limitations"][:-1]
    copied_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(VesSAPMajorVesselError, match="limitations"):
        load_vessap_major_vessels(copied_asset, copied_manifest)


def test_vessap_loader_rejects_transform_identity_changes(tmp_path: Path) -> None:
    bundled_asset, bundled_manifest = bundled_asset_paths()
    copied_asset = tmp_path / ASSET_FILENAME
    copied_manifest = tmp_path / MANIFEST_FILENAME
    shutil.copyfile(bundled_asset, copied_asset)
    manifest = json.loads(bundled_manifest.read_text(encoding="utf-8"))
    manifest["registration"]["mapping"] = "unreviewed replacement"
    copied_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(VesSAPMajorVesselError, match="registration evidence"):
        load_vessap_major_vessels(copied_asset, copied_manifest)
