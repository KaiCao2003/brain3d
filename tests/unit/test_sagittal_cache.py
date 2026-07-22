"""Tests for the exact disk-backed sagittal display layout."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile
from numpy.testing import assert_array_equal
from tests.fixtures import make_allen_metadata_test_double

import mouse_brain_planner.rendering.sagittal_cache as cache_module
from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata
from mouse_brain_planner.rendering.sagittal_cache import (
    SagittalCacheCancelledError,
    SagittalCacheError,
    prepare_sagittal_cache,
    reviewed_10um_requires_sagittal_cache,
)


def make_source_atlas(
    tmp_path: Path,
    *,
    shape: tuple[int, int, int] = (5, 4, 3),
) -> tuple[AtlasMetadata, np.memmap, np.memmap, Path]:
    atlas_root = tmp_path / "atlas"
    atlas_root.mkdir()
    reference = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)
    annotation = (reference % 7).astype(np.uint32)
    tifffile.imwrite(atlas_root / "reference.tiff", reference, photometric="minisblack")
    tifffile.imwrite(atlas_root / "annotation.tiff", annotation, photometric="minisblack")
    resolution = (10.0, 10.0, 10.0)
    metadata = AtlasMetadata(
        atlas_key="small-sagittal-cache-test-double",
        atlas_package_version="1.2",
        species="Mus musculus",
        citation="Synthetic cache test double; not anatomical evidence",
        source_url="https://example.invalid/sagittal-cache-test",
        cache_path=str(atlas_root),
        metadata_sha256="a" * 64,
        resolution_um=resolution,
        shape_voxels=shape,
        source_annotation="synthetic-test-double",
        symmetric=True,
        midline_ml_um=shape[2] * resolution[2] / 2.0,
        axes=(
            AtlasAxis(
                array_axis=0,
                anatomical_axis="AP",
                origin_direction="anterior",
                positive_direction="posterior",
                voxel_size_um=resolution[0],
            ),
            AtlasAxis(
                array_axis=1,
                anatomical_axis="DV",
                origin_direction="superior",
                positive_direction="inferior",
                voxel_size_um=resolution[1],
            ),
            AtlasAxis(
                array_axis=2,
                anatomical_axis="ML",
                origin_direction="right",
                positive_direction="left",
                voxel_size_um=resolution[2],
            ),
        ),
    )
    return (
        metadata,
        tifffile.memmap(atlas_root / "reference.tiff"),
        tifffile.memmap(atlas_root / "annotation.tiff"),
        atlas_root,
    )


def test_only_exact_reviewed_10um_contract_requires_cache() -> None:
    reviewed_10um = make_allen_metadata_test_double(10)

    assert reviewed_10um_requires_sagittal_cache(reviewed_10um)
    assert not reviewed_10um_requires_sagittal_cache(make_allen_metadata_test_double(25))
    assert not reviewed_10um_requires_sagittal_cache(
        reviewed_10um.model_copy(update={"atlas_package_version": "1.3"})
    )


def test_cache_is_read_only_exact_for_every_ml_plane_and_reused(tmp_path: Path) -> None:
    metadata, reference, annotation, _ = make_source_atlas(tmp_path)
    cache_root = tmp_path / "derived"
    progress: list[tuple[int, int]] = []

    cache = prepare_sagittal_cache(
        metadata,
        reference,
        annotation,
        cache_root=cache_root,
        progress=lambda completed, total: progress.append((completed, total)),
    )

    assert isinstance(cache.reference, np.memmap)
    assert isinstance(cache.annotation, np.memmap)
    assert cache.reference.mode == cache.annotation.mode == "r"
    assert not cache.reference.flags.writeable
    assert not cache.annotation.flags.writeable
    assert cache.reference.shape == (3, 4, 5)
    for ml_index in range(metadata.shape_voxels[2]):
        assert_array_equal(cache.reference[ml_index], reference[:, :, ml_index].T)
        assert_array_equal(cache.annotation[ml_index], annotation[:, :, ml_index].T)
    assert progress[0][0] == 0
    assert progress[-1][0] == progress[-1][1]

    reuse_progress: list[tuple[int, int]] = []
    reused = prepare_sagittal_cache(
        metadata,
        reference,
        annotation,
        cache_root=cache_root,
        progress=lambda completed, total: reuse_progress.append((completed, total)),
    )
    assert reused.path == cache.path
    assert reused.cache_key == cache.cache_key
    assert reuse_progress == []


def test_manifest_binds_source_stats_and_exact_output_bytes(tmp_path: Path) -> None:
    metadata, reference, annotation, atlas_root = make_source_atlas(tmp_path)
    cache = prepare_sagittal_cache(
        metadata,
        reference,
        annotation,
        cache_root=tmp_path / "derived",
    )

    manifest = json.loads((cache.path / "manifest.json").read_text(encoding="utf-8"))

    sources = {value["name"]: value for value in manifest["source"]}
    for filename in ("reference.tiff", "annotation.tiff"):
        source_stat = (atlas_root / filename).stat()
        assert sources[filename]["size"] == source_stat.st_size
        assert sources[filename]["mtime_ns"] == source_stat.st_mtime_ns
    assert manifest["reference_output_bytes"] == reference.nbytes
    assert manifest["annotation_output_bytes"] == annotation.nbytes
    assert manifest["total_output_bytes"] == reference.nbytes + annotation.nbytes


def test_source_mtime_fingerprint_change_atomically_rebuilds_same_slot(tmp_path: Path) -> None:
    metadata, reference, annotation, atlas_root = make_source_atlas(tmp_path)
    cache_root = tmp_path / "derived"
    first = prepare_sagittal_cache(
        metadata,
        reference,
        annotation,
        cache_root=cache_root,
    )
    source = atlas_root / "reference.tiff"
    before = source.stat()
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
    progress: list[tuple[int, int]] = []

    rebuilt = prepare_sagittal_cache(
        metadata,
        reference,
        annotation,
        cache_root=cache_root,
        progress=lambda completed, total: progress.append((completed, total)),
    )

    assert rebuilt.path == first.path
    assert rebuilt.cache_key != first.cache_key
    assert progress[-1][0] == progress[-1][1]
    assert len([path for path in cache_root.iterdir() if path.name.startswith("atlas-")]) == 1
    assert not any(".stage." in path.name or ".old." in path.name for path in cache_root.iterdir())


def test_progress_is_throttled_but_cancellation_checks_every_tile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata, reference, annotation, _ = make_source_atlas(tmp_path)
    monkeypatch.setattr(cache_module, "_TILE_EDGE", 1)
    progress: list[tuple[int, int]] = []
    cache = prepare_sagittal_cache(
        metadata,
        reference,
        annotation,
        cache_root=tmp_path / "complete",
        progress=lambda completed, total: progress.append((completed, total)),
    )
    del cache

    total_tiles = 2 * np.prod(metadata.shape_voxels)
    assert progress[-1] == (total_tiles, total_tiles)
    assert len(progress) <= total_tiles // 32 + 2

    cancel_progress: list[tuple[int, int]] = []

    def record_progress(completed: int, total: int) -> None:
        cancel_progress.append((completed, total))

    with pytest.raises(SagittalCacheCancelledError, match="cancelled"):
        prepare_sagittal_cache(
            metadata,
            reference,
            annotation,
            cache_root=tmp_path / "cancelled",
            progress=record_progress,
            cancel=lambda: bool(cancel_progress),
        )

    cancelled_root = tmp_path / "cancelled"
    assert not any(path.name.startswith("atlas-") for path in cancelled_root.iterdir())
    assert not any(".stage." in path.name for path in cancelled_root.iterdir())


def test_source_symlink_and_insufficient_disk_fail_without_partial_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata, reference, annotation, atlas_root = make_source_atlas(tmp_path)
    reference_path = atlas_root / "reference.tiff"
    real_reference = atlas_root / "reference-real.tiff"
    reference_path.replace(real_reference)
    reference_path.symlink_to(real_reference.name)

    with pytest.raises(SagittalCacheError, match="non-symlink"):
        prepare_sagittal_cache(
            metadata,
            reference,
            annotation,
            cache_root=tmp_path / "symlink-cache",
        )

    reference_path.unlink()
    real_reference.replace(reference_path)
    monkeypatch.setattr(
        cache_module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=0),
    )
    disk_root = tmp_path / "disk-cache"
    with pytest.raises(SagittalCacheError, match="insufficient free disk"):
        prepare_sagittal_cache(
            metadata,
            reference,
            annotation,
            cache_root=disk_root,
        )
    assert not any(path.name.startswith("atlas-") for path in disk_root.iterdir())


@pytest.mark.parametrize("corruption", ["array", "manifest"])
def test_corrupt_final_artifact_is_atomically_rebuilt(
    tmp_path: Path,
    corruption: str,
) -> None:
    metadata, reference, annotation, _ = make_source_atlas(tmp_path)
    cache_root = tmp_path / "derived"
    first = prepare_sagittal_cache(
        metadata,
        reference,
        annotation,
        cache_root=cache_root,
    )
    if corruption == "array":
        array_path = first.path / "reference-ml-dv-ap.npy"
        with array_path.open("r+b") as stream:
            stream.truncate(array_path.stat().st_size - 1)
    else:
        (first.path / "manifest.json").write_text("{}\n", encoding="utf-8")
    progress: list[tuple[int, int]] = []

    rebuilt = prepare_sagittal_cache(
        metadata,
        reference,
        annotation,
        cache_root=cache_root,
        progress=lambda completed, total: progress.append((completed, total)),
    )

    assert progress[-1][0] == progress[-1][1]
    assert rebuilt.reference.mode == "r"
    for ml_index in range(metadata.shape_voxels[2]):
        assert_array_equal(rebuilt.reference[ml_index], reference[:, :, ml_index].T)
    assert not any(".stage." in path.name or ".old." in path.name for path in cache_root.iterdir())


def test_failed_install_restores_displaced_prior_cache_without_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata, reference, annotation, atlas_root = make_source_atlas(tmp_path)
    cache_root = tmp_path / "derived"
    first = prepare_sagittal_cache(
        metadata,
        reference,
        annotation,
        cache_root=cache_root,
    )
    prior_manifest = (first.path / "manifest.json").read_bytes()
    source = atlas_root / "annotation.tiff"
    before = source.stat()
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
    original_replace = Path.replace

    def fail_stage_install(path: Path, target: Path) -> Path:
        if ".stage." in path.name and target == first.path:
            raise OSError("synthetic staged install failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_stage_install)

    with pytest.raises(OSError, match="synthetic staged install failure"):
        prepare_sagittal_cache(
            metadata,
            reference,
            annotation,
            cache_root=cache_root,
        )

    assert first.path.is_dir()
    assert (first.path / "manifest.json").read_bytes() == prior_manifest
    assert not any(".stage." in path.name or ".old." in path.name for path in cache_root.iterdir())
