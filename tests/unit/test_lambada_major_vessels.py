from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from mouse_brain_planner.vasculature.lambada_major_vessels import (
    ASSET_FILENAME,
    EXPECTED_RUN_COUNT,
    EXPECTED_RUN_POINT_COUNT,
    MANDATORY_LIMITATIONS,
    MANIFEST_FILENAME,
    MINIMUM_RADIUS_UM,
    LambadaMajorVesselError,
    bundled_asset_paths,
    extract_major_vessel_runs,
    load_lambada_major_vessels,
    write_deterministic_npz,
)


def _small_source_arrays() -> tuple[
    np.ndarray[tuple[int, int], np.dtype[np.float64]],
    np.ndarray[tuple[int], np.dtype[np.float64]],
    np.ndarray[tuple[int], np.dtype[np.int64]],
    np.ndarray[tuple[int, int], np.dtype[np.int64]],
]:
    coordinates = np.array(
        [
            [10.0, 20.0, 30.0],
            [11.0, 21.0, 31.0],
            [12.0, 22.0, 32.0],
            [13.0, 23.0, 33.0],
            [14.0, 528.0, 34.0],
            [15.0, 25.0, 35.0],
            [16.0, 26.0, 36.0],
            [17.0, 27.0, 37.0],
            [np.nan, 28.0, 38.0],
            [19.0, 29.0, 39.0],
            [20.0, 30.0, 40.0],
            [21.0, 31.0, 41.0],
        ],
        dtype=np.float64,
    )
    radii_atlas_voxel = np.array(
        [0.6, 0.7, 0.59, 0.8, 0.9, 0.9, 1.0, 0.7, 0.9, 0.6, 0.7, 0.8],
        dtype=np.float64,
    )
    annotations = np.arange(100, 112, dtype=np.int64)
    edge_indices = np.array([[0, 8], [8, 12]], dtype=np.int64)
    return coordinates, radii_atlas_voxel, annotations, edge_indices


def test_extracts_maximal_pointwise_runs_without_clipping_or_half_voxel_shift() -> None:
    coordinates, radii, annotations, edge_indices = _small_source_arrays()

    data = extract_major_vessel_runs(coordinates, radii, annotations, edge_indices)

    selected = np.array([0, 1, 5, 6, 7, 9, 10, 11])
    expected_points = coordinates[selected][:, [1, 0, 2]].astype(np.float32)
    np.testing.assert_array_equal(data.points_asr_voxel_f32, expected_points)
    np.testing.assert_array_equal(
        data.radii_um_f32,
        (radii[selected] * 25.0).astype(np.float32),
    )
    np.testing.assert_array_equal(
        data.source_annotation_ids_i32,
        annotations[selected].astype(np.int32),
    )
    np.testing.assert_array_equal(data.run_offsets_i64, [0, 2, 5, 8])
    np.testing.assert_array_equal(data.source_edge_indices_i32, [0, 0, 1])


def test_pointwise_run_extractor_rejects_fractional_edge_ranges() -> None:
    coordinates, radii, annotations, _ = _small_source_arrays()

    with pytest.raises(LambadaMajorVesselError, match="must contain integers"):
        extract_major_vessel_runs(
            coordinates,
            radii,
            annotations,
            np.array([[0.0, 2.0]], dtype=np.float64),
        )


def test_deterministic_npz_writer_reproduces_identical_bytes(tmp_path: Path) -> None:
    coordinates, radii, annotations, edge_indices = _small_source_arrays()
    data = extract_major_vessel_runs(coordinates, radii, annotations, edge_indices)
    first = tmp_path / "first.npz"
    second = tmp_path / "second.npz"

    first_identity = write_deterministic_npz(first, data)
    second_identity = write_deterministic_npz(second, data)

    assert first_identity == second_identity
    assert first.read_bytes() == second.read_bytes()


def test_bundled_asset_loads_as_immutable_physical_asr_geometry() -> None:
    graph = load_lambada_major_vessels()

    assert graph.points_asr_um.shape == (EXPECTED_RUN_POINT_COUNT, 3)
    assert graph.radii_um.shape == (EXPECTED_RUN_POINT_COUNT,)
    assert graph.run_count == EXPECTED_RUN_COUNT
    assert graph.run_offsets.shape == (EXPECTED_RUN_COUNT + 1,)
    assert graph.points_asr_um.dtype == np.dtype("<f4")
    assert not graph.points_asr_um.flags.writeable
    assert not graph.radii_um.flags.writeable
    assert not graph.source_annotation_ids.flags.writeable
    assert not graph.run_offsets.flags.writeable
    assert not graph.source_edge_indices.flags.writeable
    assert bool(np.all(graph.points_asr_um >= 0.0))
    assert bool(np.all(graph.points_asr_um < np.array([13_200.0, 8_000.0, 11_400.0])))
    assert float(np.min(graph.radii_um)) >= MINIMUM_RADIUS_UM
    assert graph.provenance.limitations == MANDATORY_LIMITATIONS
    assert not graph.run_points_asr_um(0).flags.writeable
    with pytest.raises(TypeError, match="integer"):
        graph.run_points_asr_um(True)
    with pytest.raises(IndexError, match="outside"):
        graph.run_points_asr_um(graph.run_count)


def test_loader_rejects_asset_bytes_that_do_not_match_manifest(tmp_path: Path) -> None:
    bundled_asset, bundled_manifest = bundled_asset_paths()
    copied_asset = tmp_path / ASSET_FILENAME
    copied_manifest = tmp_path / MANIFEST_FILENAME
    shutil.copyfile(bundled_asset, copied_asset)
    shutil.copyfile(bundled_manifest, copied_manifest)
    payload = bytearray(copied_asset.read_bytes())
    payload[len(payload) // 2] ^= 0x01
    copied_asset.write_bytes(payload)

    with pytest.raises(LambadaMajorVesselError, match="SHA-256"):
        load_lambada_major_vessels(copied_asset, copied_manifest)


def test_loader_rejects_removed_mandatory_limitation(tmp_path: Path) -> None:
    bundled_asset, bundled_manifest = bundled_asset_paths()
    copied_asset = tmp_path / ASSET_FILENAME
    copied_manifest = tmp_path / MANIFEST_FILENAME
    shutil.copyfile(bundled_asset, copied_asset)
    manifest = json.loads(bundled_manifest.read_text(encoding="utf-8"))
    manifest["limitations"] = manifest["limitations"][:-1]
    copied_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(LambadaMajorVesselError, match="limitations"):
        load_lambada_major_vessels(copied_asset, copied_manifest)


def test_loader_rejects_rehashed_replacement_asset(tmp_path: Path) -> None:
    bundled_asset, bundled_manifest = bundled_asset_paths()
    copied_asset = tmp_path / ASSET_FILENAME
    copied_manifest = tmp_path / MANIFEST_FILENAME
    shutil.copyfile(bundled_asset, copied_asset)
    payload = bytearray(copied_asset.read_bytes())
    payload[len(payload) // 2] ^= 0x01
    copied_asset.write_bytes(payload)
    manifest = json.loads(bundled_manifest.read_text(encoding="utf-8"))
    manifest["asset"]["sha256"] = hashlib.sha256(payload).hexdigest()
    copied_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(LambadaMajorVesselError, match="reviewed build"):
        load_lambada_major_vessels(copied_asset, copied_manifest)
