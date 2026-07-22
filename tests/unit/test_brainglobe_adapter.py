"""Contract tests for the only BrainGlobe boundary in the application."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable, Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import tifffile

import mouse_brain_planner.atlas.brainglobe_adapter as adapter
from mouse_brain_planner.atlas.brainglobe_adapter import (
    AtlasCatalogRecord,
    AtlasDownloadCancelledError,
    BrainGlobeAtlasRepository,
    BrainGlobeContractError,
)
from mouse_brain_planner.coordinates.atlas_space import (
    AtlasIdentityError,
    CoordinateBoundsError,
)
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.paths import AppPaths

_CORE_PACKAGE_FILES = (
    "metadata.json",
    "reference.tiff",
    "annotation.tiff",
    "structures.json",
)


def _write_valid_cache_package(path: Path) -> None:
    """Create a structurally valid tiny atlas package for cache discovery."""

    atlas_name, package_version = path.name.rsplit("_v", 1)
    resolution = 10 if atlas_name.endswith("_10um") else 25
    shape = (2, 3, 4)
    path.mkdir()
    metadata = {
        "name": "allen_mouse",
        "citation": "Test-only atlas package",
        "atlas_link": "https://example.test/allen",
        "species": "Mus musculus",
        "symmetric": True,
        "resolution": [resolution] * 3,
        "orientation": "asr",
        "shape": list(shape),
        "version": package_version,
    }
    structures = [
        {
            "id": 1,
            "acronym": "root",
            "name": "Root structure",
            "structure_id_path": [1],
            "rgb_triplet": [255, 255, 255],
        },
        {
            "id": 2,
            "acronym": "CA1",
            "name": "Field CA1",
            "structure_id_path": [1, 2],
            "rgb_triplet": [10, 20, 30],
        },
    ]
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (path / "structures.json").write_text(json.dumps(structures), encoding="utf-8")
    tifffile.imwrite(
        path / "reference.tiff",
        np.arange(24, dtype=np.uint16).reshape(shape),
        photometric="minisblack",
        metadata=None,
    )
    tifffile.imwrite(
        path / "annotation.tiff",
        np.full(shape, 2, dtype=np.uint32),
        photometric="minisblack",
        metadata=None,
    )


class FakeBrainGlobeAtlas:
    """Small in-memory stand-in for the stable upstream object."""

    def __init__(
        self,
        atlas_name: str,
        *,
        brainglobe_dir: Path,
        interm_download_dir: Path,
        check_latest: bool,
        config_dir: Path,
        fn_update: Callable[[int, int], None] | None,
        calls: list[dict[str, object]],
        metadata_bytes: bytes,
    ) -> None:
        calls.append(
            {
                "atlas_name": atlas_name,
                "brainglobe_dir": brainglobe_dir,
                "interm_download_dir": interm_download_dir,
                "temporary_exists": interm_download_dir.is_dir(),
                "check_latest": check_latest,
                "config_dir": config_dir,
                "fn_update": fn_update,
            }
        )
        if fn_update is not None:
            fn_update(4, 10)
            fn_update(10, 10)

        metadata_payload = json.loads(metadata_bytes)
        package_version = str(metadata_payload["version"])
        self.atlas_name = atlas_name
        self.left_hemisphere_value = 1
        self.right_hemisphere_value = 2
        self.root_dir = brainglobe_dir / f"{atlas_name}_v{package_version}"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        resolution = 10 if atlas_name.endswith("_10um") else 25
        self._resolution = (resolution, resolution, resolution)
        metadata_payload["resolution"] = [resolution] * 3
        effective_metadata_bytes = json.dumps(metadata_payload, separators=(",", ":")).encode()
        (self.root_dir / "metadata.json").write_bytes(effective_metadata_bytes)
        meshes_dir = self.root_dir / "meshes"
        meshes_dir.mkdir(exist_ok=True)
        (meshes_dir / "1.obj").write_text("root mesh", encoding="utf-8")
        (meshes_dir / "2.obj").write_text("CA1 mesh", encoding="utf-8")
        self.metadata: Mapping[str, object] = metadata_payload
        self.structures_list: list[Mapping[str, object]] = [
            {
                "id": 1,
                "acronym": "root",
                "name": "Root structure",
                "structure_id_path": [1],
                "rgb_triplet": [255, 255, 255],
                "mesh_filename": self.root_dir / "meshes" / "1.obj",
            },
            {
                "id": 2,
                "acronym": "CA1",
                "name": "Field CA1",
                "structure_id_path": [1, 2],
                "rgb_triplet": [10, 20, 30],
                "mesh_filename": self.root_dir / "meshes" / "2.obj",
            },
        ]
        self._reference = np.arange(24, dtype=np.uint16).reshape((2, 3, 4))
        self._annotation = np.full((2, 3, 4), 2, dtype=np.uint32)
        serializable_structures = [
            {key: value for key, value in structure.items() if key != "mesh_filename"}
            for structure in self.structures_list
        ]
        (self.root_dir / "structures.json").write_text(
            json.dumps(serializable_structures),
            encoding="utf-8",
        )
        tifffile.imwrite(
            self.root_dir / "reference.tiff",
            self._reference,
            photometric="minisblack",
            metadata=None,
        )
        tifffile.imwrite(
            self.root_dir / "annotation.tiff",
            self._annotation,
            photometric="minisblack",
            metadata=None,
        )
        self.lookup_calls: list[tuple[tuple[float, float, float], bool]] = []
        self.lookup_result = 2
        self.root_mesh_value = object()
        self.region_mesh_values = {1: object(), 2: object(), "root": object(), "CA1": object()}
        self.region_mesh_files: dict[int | str, Path] = {
            1: meshes_dir / "1.obj",
            2: meshes_dir / "2.obj",
            "root": meshes_dir / "1.obj",
            "CA1": meshes_dir / "2.obj",
        }

    @property
    def resolution(self) -> tuple[int, int, int]:
        return self._resolution

    @property
    def orientation(self) -> str:
        return "asr"

    @property
    def shape(self) -> tuple[int, int, int]:
        return (2, 3, 4)

    @property
    def reference(self) -> np.ndarray[Any, Any]:
        return self._reference

    @property
    def annotation(self) -> np.ndarray[Any, Any]:
        return self._annotation

    def structure_from_coords(
        self,
        coords: tuple[float, float, float],
        microns: bool = False,
    ) -> int:
        self.lookup_calls.append((coords, microns))
        return self.lookup_result

    def mesh_from_structure(self, structure: int | str) -> object:
        return self.region_mesh_values[structure]

    def root_mesh(self) -> object:
        return self.root_mesh_value

    def meshfile_from_structure(self, structure: int | str) -> Path:
        return self.region_mesh_files[structure]

    def root_meshfile(self) -> Path:
        return self.region_mesh_files["root"]


class FakeBrainGlobeConfig:
    """Fake of AtlasAPI's official read/write configuration functions."""

    def __init__(self) -> None:
        self.values: dict[str, dict[str, str]] = {
            "default_dirs": {
                "brainglobe_dir": "/legacy/atlases",
                "interm_download_dir": "/legacy/downloads",
            },
            "unrelated": {"preserve_me": "unchanged"},
        }
        self.calls: list[tuple[object, ...]] = []

    def read_config(self, path: Path) -> Mapping[str, Mapping[str, str]]:
        self.calls.append(("read_config", path))
        return self.values

    def write_config_value(self, key: str, value: object, path: Path) -> None:
        self.calls.append(("write_config_value", key, value, path))
        for section in self.values.values():
            if key in section:
                section[key] = str(value)


class FakeCatalogResponse:
    """Context-managed byte response for catalog transport tests."""

    status = 200

    def __init__(self, payload: bytes, *, on_read: Callable[[], None] | None = None) -> None:
        self._stream = BytesIO(payload)
        self._on_read = on_read

    def __enter__(self) -> FakeCatalogResponse:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        chunk = self._stream.read(size)
        if self._on_read is not None:
            self._on_read()
        return chunk


@pytest.fixture
def app_paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths(
        config=tmp_path / "config",
        data=tmp_path / "data",
        cache=tmp_path / "cache",
        atlas_cache=tmp_path / "data" / "atlases",
        download_cache=tmp_path / "cache" / "atlas-downloads",
    )
    paths.ensure()
    return paths


@pytest.fixture
def metadata_bytes() -> bytes:
    return json.dumps(
        {
            "name": "allen_mouse",
            "citation": "Wang et al. 2020",
            "atlas_link": "https://example.test/allen",
            "species": "Mus musculus",
            "symmetric": True,
            "resolution": [25, 25, 25],
            "orientation": "asr",
            "shape": [2, 3, 4],
            "version": "1.2",
        },
        separators=(",", ":"),
    ).encode()


@pytest.fixture(autouse=True)
def tiny_reviewed_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep adapter unit packages tiny while production retains published shapes."""

    monkeypatch.setitem(adapter._SUPPORTED_ATLAS_SHAPE_VOXELS, "allen_mouse_25um", (2, 3, 4))


@pytest.fixture
def fake_runtime(
    metadata_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[adapter._BrainGlobeRuntime, list[dict[str, object]], list[FakeBrainGlobeAtlas]]:
    calls: list[dict[str, object]] = []
    atlases: list[FakeBrainGlobeAtlas] = []

    def factory(atlas_name: str, **kwargs: object) -> FakeBrainGlobeAtlas:
        atlas = FakeBrainGlobeAtlas(
            atlas_name,
            brainglobe_dir=kwargs["brainglobe_dir"],  # type: ignore[arg-type]
            interm_download_dir=kwargs["interm_download_dir"],  # type: ignore[arg-type]
            check_latest=kwargs["check_latest"],  # type: ignore[arg-type]
            config_dir=kwargs["config_dir"],  # type: ignore[arg-type]
            fn_update=kwargs["fn_update"],  # type: ignore[arg-type]
            calls=calls,
            metadata_bytes=metadata_bytes,
        )
        atlases.append(atlas)
        return atlas

    def cached_factory(root_dir: Path) -> FakeBrainGlobeAtlas:
        for atlas in reversed(atlases):
            if atlas.root_dir.resolve() == root_dir.resolve():
                return atlas
        if atlases:
            atlas = atlases[-1]
            old_root = atlas.root_dir.resolve()
            atlas.root_dir = root_dir
            atlas.region_mesh_files = {
                key: root_dir / path.resolve().relative_to(old_root)
                for key, path in atlas.region_mesh_files.items()
            }
            for structure in atlas.structures_list:
                mesh_filename = Path(structure["mesh_filename"])
                structure["mesh_filename"] = root_dir / mesh_filename.resolve().relative_to(
                    old_root
                )
            return atlas
        raise FileNotFoundError(root_dir)

    runtime = adapter._BrainGlobeRuntime(
        atlas_factory=factory,  # type: ignore[arg-type]
        cached_atlas_factory=cached_factory,
        catalog_loader=lambda: {
            "allen_mouse_10um": "1.2",
            "allen_mouse_25um": "1.2",
            "allen_human_500um": "1.0",
            "private_mouse_50um": "0.4",
        },
        config_api=FakeBrainGlobeConfig(),
        library_version="2.3.1",
    )
    monkeypatch.setattr(adapter, "_load_runtime", lambda: runtime)
    return runtime, calls, atlases


def _with_production_catalog(runtime: adapter._BrainGlobeRuntime) -> adapter._BrainGlobeRuntime:
    return adapter._BrainGlobeRuntime(
        atlas_factory=runtime.atlas_factory,
        cached_atlas_factory=runtime.cached_atlas_factory,
        catalog_loader=None,
        config_api=runtime.config_api,
        library_version=runtime.library_version,
    )


def _assert_no_catalog_request_thread() -> None:
    assert all(thread.name != "brainglobe-catalog-request" for thread in threading.enumerate())


def test_list_atlases_merges_remote_catalog_with_explicit_local_cache(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, _ = fake_runtime
    _write_valid_cache_package(app_paths.atlas_cache / "allen_mouse_25um_v1.1")
    _write_valid_cache_package(app_paths.atlas_cache / "private_mouse_50um_v0.4")
    (app_paths.atlas_cache / "not-an-atlas").mkdir()

    repository = BrainGlobeAtlasRepository(app_paths)
    records = repository.list_atlases()

    assert records == [
        AtlasCatalogRecord("allen_mouse_25um", "1.2", False),
    ]
    assert not repository.is_cached("allen_mouse_25um")
    with pytest.raises(BrainGlobeContractError, match=r"package v1\.1 has not been reviewed"):
        repository.is_cached("allen_mouse_25um", "1.1")
    assert not repository.is_cached("allen_mouse_25um", "1.2")
    with pytest.raises(BrainGlobeContractError, match="has not been reviewed"):
        repository.is_cached("allen_mouse_10um")
    with pytest.raises(BrainGlobeContractError, match="has not been reviewed"):
        repository.is_cached("private_mouse_50um", "0.4")


def test_catalog_downloaded_means_exact_latest_package_is_cached(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, _ = fake_runtime
    _write_valid_cache_package(app_paths.atlas_cache / "allen_mouse_25um_v1.1")
    repository = BrainGlobeAtlasRepository(app_paths)

    assert (
        next(
            record for record in repository.list_atlases() if record.name == "allen_mouse_25um"
        ).downloaded
        is False
    )

    _write_valid_cache_package(app_paths.atlas_cache / "allen_mouse_25um_v1.2")
    assert (
        next(
            record for record in repository.list_atlases() if record.name == "allen_mouse_25um"
        ).downloaded
        is True
    )


def test_empty_or_partial_package_is_not_reported_as_cached(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, _ = fake_runtime
    package = app_paths.atlas_cache / "allen_mouse_25um_v1.2"
    package.mkdir()
    repository = BrainGlobeAtlasRepository(app_paths)

    assert not repository.is_cached("allen_mouse_25um", "1.2")
    (package / "metadata.json").write_bytes(b"{}")
    assert not repository.is_cached("allen_mouse_25um", "1.2")
    assert all(not record.downloaded for record in repository.list_atlases())


def test_cache_shape_must_match_the_published_reviewed_key(
    app_paths: AppPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = app_paths.atlas_cache / "allen_mouse_25um_v1.2"
    _write_valid_cache_package(package)
    monkeypatch.setitem(
        adapter._SUPPORTED_ATLAS_SHAPE_VOXELS,
        "allen_mouse_25um",
        (528, 320, 456),
    )

    with pytest.raises(BrainGlobeContractError, match="disagrees with reviewed key"):
        BrainGlobeAtlasRepository._validate_package(
            package,
            atlas_name="allen_mouse_25um",
            package_version="1.2",
        )


def test_nonempty_garbage_and_mismatched_tiff_fail_package_validation(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, _ = fake_runtime
    garbage = app_paths.cache / "garbage" / "allen_mouse_25um_v1.2"
    garbage.mkdir(parents=True)
    for filename in _CORE_PACKAGE_FILES:
        (garbage / filename).write_bytes(b"nonempty garbage")
    mismatched = app_paths.cache / "mismatched" / "allen_mouse_25um_v1.2"
    mismatched.parent.mkdir()
    _write_valid_cache_package(mismatched)
    tifffile.imwrite(
        mismatched / "reference.tiff",
        np.zeros((1, 2, 3), dtype=np.uint16),
        photometric="minisblack",
        metadata=None,
    )
    assert not BrainGlobeAtlasRepository._is_valid_package(
        garbage,
        atlas_name="allen_mouse_25um",
        package_version="1.2",
    )
    assert not BrainGlobeAtlasRepository._is_valid_package(
        mismatched,
        atlas_name="allen_mouse_25um",
        package_version="1.2",
    )


def test_malformed_structures_json_is_not_reported_as_cached(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, _ = fake_runtime
    package = app_paths.atlas_cache / "allen_mouse_25um_v1.2"
    _write_valid_cache_package(package)
    (package / "structures.json").write_text(
        json.dumps([{"id": "not-an-integer"}]),
        encoding="utf-8",
    )
    repository = BrainGlobeAtlasRepository(app_paths)

    assert not repository.is_cached("allen_mouse_25um", "1.2")
    assert (
        next(
            record for record in repository.list_atlases() if record.name == "allen_mouse_25um"
        ).downloaded
        is False
    )


def test_unreviewed_tiff_dtype_is_not_reported_as_cached(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, _ = fake_runtime
    package = app_paths.atlas_cache / "allen_mouse_25um_v1.2"
    _write_valid_cache_package(package)
    tifffile.imwrite(
        package / "annotation.tiff",
        np.full((2, 3, 4), 2, dtype=np.uint16),
        photometric="minisblack",
        metadata=None,
    )

    assert not BrainGlobeAtlasRepository(app_paths).is_cached(
        "allen_mouse_25um",
        "1.2",
    )


def test_catalog_and_local_only_mode_expose_only_reviewed_allen_mouse_atlases(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    runtime, calls, _ = fake_runtime
    _write_valid_cache_package(app_paths.atlas_cache / "allen_mouse_25um_v1.2")
    unsupported_cache = app_paths.atlas_cache / "allen_mouse_10um_v1.2"
    _write_valid_cache_package(unsupported_cache)
    unsupported_metadata = (unsupported_cache / "metadata.json").read_bytes()
    _write_valid_cache_package(app_paths.atlas_cache / "private_mouse_50um_v0.4")
    repository = BrainGlobeAtlasRepository(app_paths)

    assert [record.name for record in repository.list_atlases()] == [
        "allen_mouse_25um",
    ]
    assert repository.list_atlases(local_only=True) == [
        AtlasCatalogRecord("allen_mouse_25um", "1.2", True)
    ]
    with pytest.raises(BrainGlobeContractError, match="has not been reviewed"):
        repository.open("allen_human_500um")
    with pytest.raises(BrainGlobeContractError, match="has not been reviewed"):
        repository.open("private_mouse_50um")
    with pytest.raises(BrainGlobeContractError, match="has not been reviewed"):
        repository.open("allen_mouse_10um", package_version="1.2")
    with pytest.raises(BrainGlobeContractError, match="has not been reviewed"):
        repository.is_cached("allen_mouse_10um", "1.2")
    assert unsupported_cache.is_dir()
    assert (unsupported_cache / "metadata.json").read_bytes() == unsupported_metadata
    assert calls == []

    future_runtime = adapter._BrainGlobeRuntime(
        atlas_factory=runtime.atlas_factory,
        cached_atlas_factory=runtime.cached_atlas_factory,
        catalog_loader=lambda: {
            "allen_mouse_10um": "1.3",
            "allen_mouse_25um": "1.3",
        },
        config_api=runtime.config_api,
        library_version=runtime.library_version,
    )
    assert BrainGlobeAtlasRepository(app_paths, _runtime=future_runtime).list_atlases() == [
        AtlasCatalogRecord("allen_mouse_25um", "1.2", True)
    ]


def test_production_catalog_fetch_is_size_bounded_and_atomically_cached_without_thread(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _, _ = fake_runtime
    payload = (
        b"[atlases]\nallen_mouse_10um = 1.2\nallen_mouse_25um = 1.2\nallen_human_500um = 1.0\n"
    )
    observed_timeouts: list[float] = []

    def fake_urlopen(_request: object, *, timeout: float) -> FakeCatalogResponse:
        observed_timeouts.append(timeout)
        return FakeCatalogResponse(payload)

    monkeypatch.setattr(adapter, "urlopen", fake_urlopen)
    cache_path = app_paths.atlas_cache / "last_versions.conf"
    cache_path.write_text("[atlases]\nallen_mouse_10um = 0.0\n", encoding="utf-8")

    records = BrainGlobeAtlasRepository(
        app_paths,
        _runtime=_with_production_catalog(runtime),
    ).list_atlases()

    assert records == [
        AtlasCatalogRecord("allen_mouse_25um", "1.2", False),
    ]
    assert observed_timeouts == [adapter._CATALOG_SOCKET_TIMEOUT_SECONDS]
    assert cache_path.read_bytes() == payload
    assert list(app_paths.atlas_cache.glob(".last_versions-*.tmp")) == []
    _assert_no_catalog_request_thread()


def test_production_catalog_timeout_uses_valid_cache_without_thread(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _, _ = fake_runtime
    cache_path = app_paths.atlas_cache / "last_versions.conf"
    cache_path.write_text(
        "[atlases]\nallen_mouse_10um = 1.2\nallen_mouse_25um = 1.2\n",
        encoding="utf-8",
    )

    def timed_out_urlopen(_request: object, *, timeout: float) -> FakeCatalogResponse:
        assert 0 < timeout <= adapter._CATALOG_SOCKET_TIMEOUT_SECONDS
        raise TimeoutError("deterministic socket timeout")

    monkeypatch.setattr(adapter, "urlopen", timed_out_urlopen)

    records = BrainGlobeAtlasRepository(
        app_paths,
        _runtime=_with_production_catalog(runtime),
    ).list_atlases()

    assert records == [
        AtlasCatalogRecord("allen_mouse_25um", "1.2", False),
    ]
    _assert_no_catalog_request_thread()


def test_production_catalog_cancellation_stops_during_read_without_thread(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _, _ = fake_runtime
    cancelled = False

    def mark_cancelled() -> None:
        nonlocal cancelled
        cancelled = True

    def fake_urlopen(_request: object, *, timeout: float) -> FakeCatalogResponse:
        assert 0 < timeout <= adapter._CATALOG_SOCKET_TIMEOUT_SECONDS
        return FakeCatalogResponse(
            b"[atlases]\nallen_mouse_10um = 1.2\n",
            on_read=mark_cancelled,
        )

    monkeypatch.setattr(adapter, "urlopen", fake_urlopen)
    repository = BrainGlobeAtlasRepository(
        app_paths,
        _runtime=_with_production_catalog(runtime),
    )

    with pytest.raises(AtlasDownloadCancelledError, match="catalog request cancelled"):
        repository.list_atlases(cancel=lambda: cancelled)

    assert not (app_paths.atlas_cache / "last_versions.conf").exists()
    _assert_no_catalog_request_thread()


def test_repository_overrides_inherited_brainglobe_config_directory(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _ = fake_runtime
    monkeypatch.setenv("BRAINGLOBE_CONFIG_DIR", str(app_paths.cache / "external-config"))

    BrainGlobeAtlasRepository(app_paths)

    expected = (app_paths.config / "brainglobe").resolve()
    assert os.environ["BRAINGLOBE_CONFIG_DIR"] == str(expected)
    assert expected.is_dir()


def test_repository_configures_catalog_cache_with_official_api_and_preserves_other_fields(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    runtime, _, _ = fake_runtime
    config_api = runtime.config_api
    assert isinstance(config_api, FakeBrainGlobeConfig)

    BrainGlobeAtlasRepository(app_paths)

    config_file = app_paths.config / "brainglobe" / "bg_config.conf"
    assert config_api.values["default_dirs"] == {
        "brainglobe_dir": str(app_paths.atlas_cache.resolve()),
        "interm_download_dir": str(app_paths.download_cache.resolve()),
    }
    assert config_api.values["unrelated"] == {"preserve_me": "unchanged"}
    assert config_api.calls == [
        ("read_config", config_file),
        (
            "write_config_value",
            "brainglobe_dir",
            str(app_paths.atlas_cache.resolve()),
            config_file,
        ),
        (
            "write_config_value",
            "interm_download_dir",
            str(app_paths.download_cache.resolve()),
            config_file,
        ),
        ("read_config", config_file),
    ]


def test_open_uses_unique_application_paths_and_stable_constructor_contract(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    runtime, calls, _ = fake_runtime
    progress: list[tuple[int, int]] = []
    repository = BrainGlobeAtlasRepository(app_paths)
    second_root = app_paths.cache.parent / "second-installation"
    second_paths = AppPaths(
        config=second_root / "config",
        data=second_root / "data",
        cache=second_root / "cache",
        atlas_cache=second_root / "data" / "atlases",
        download_cache=second_root / "cache" / "atlas-downloads",
    )
    second_paths.ensure()

    repository.open("allen_mouse_25um", progress=lambda done, total: progress.append((done, total)))
    BrainGlobeAtlasRepository(second_paths, _runtime=runtime).open("allen_mouse_25um")

    first_temporary = calls[0]["interm_download_dir"]
    second_temporary = calls[1]["interm_download_dir"]
    assert isinstance(first_temporary, Path)
    assert isinstance(second_temporary, Path)
    assert calls[0]["brainglobe_dir"] != app_paths.atlas_cache
    assert calls[0]["check_latest"] is False
    assert calls[0]["config_dir"] == app_paths.config / "brainglobe" / "bg_config.conf"
    assert calls[0]["temporary_exists"] is True
    assert first_temporary.parent == app_paths.download_cache
    assert second_temporary.parent == second_paths.download_cache
    assert first_temporary != second_temporary
    assert not first_temporary.exists()
    assert not second_temporary.exists()
    assert progress == [(4, 10), (10, 10)]


def test_cached_only_open_is_enforced_inside_repository_without_upstream_factory(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, calls, _ = fake_runtime
    repository = BrainGlobeAtlasRepository(app_paths)

    with pytest.raises(adapter.AtlasAdapterError, match="downloads are disabled"):
        repository.open(
            "allen_mouse_25um",
            package_version="1.2",
            allow_download=False,
        )
    assert calls == []

    downloaded = repository.open("allen_mouse_25um")
    cached = repository.open(
        "allen_mouse_25um",
        package_version="1.2",
        allow_download=False,
    )

    assert len(calls) == 1
    assert cached.metadata == downloaded.metadata


def test_open_rejects_package_version_different_from_loaded_metadata(
    app_paths: AppPaths,
    metadata_bytes: bytes,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    runtime, calls, atlases = fake_runtime
    stale_metadata = json.loads(metadata_bytes)
    stale_metadata["version"] = "1.1"

    def stale_factory(atlas_name: str, **kwargs: object) -> FakeBrainGlobeAtlas:
        atlas = FakeBrainGlobeAtlas(
            atlas_name,
            brainglobe_dir=kwargs["brainglobe_dir"],  # type: ignore[arg-type]
            interm_download_dir=kwargs["interm_download_dir"],  # type: ignore[arg-type]
            check_latest=kwargs["check_latest"],  # type: ignore[arg-type]
            config_dir=kwargs["config_dir"],  # type: ignore[arg-type]
            fn_update=kwargs["fn_update"],  # type: ignore[arg-type]
            calls=calls,
            metadata_bytes=json.dumps(stale_metadata, separators=(",", ":")).encode(),
        )
        atlases.append(atlas)
        return atlas

    stale_runtime = adapter._BrainGlobeRuntime(
        atlas_factory=stale_factory,  # type: ignore[arg-type]
        cached_atlas_factory=runtime.cached_atlas_factory,
        catalog_loader=runtime.catalog_loader,
        config_api=runtime.config_api,
        library_version=runtime.library_version,
    )
    repository = BrainGlobeAtlasRepository(app_paths, _runtime=stale_runtime)

    with pytest.raises(BrainGlobeContractError, match=r"requested .* v1\.2.*acquired v1\.1"):
        repository.open("allen_mouse_25um", package_version="1.2")
    assert len(calls) == 1
    assert not (app_paths.atlas_cache / "allen_mouse_25um_v1.2").exists()


def test_open_rejects_unreviewed_package_version_before_factory(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, calls, _ = fake_runtime

    with pytest.raises(BrainGlobeContractError, match=r"package v9\.9 has not been reviewed"):
        BrainGlobeAtlasRepository(app_paths).open(
            "allen_mouse_25um",
            package_version="9.9",
        )
    assert calls == []


def test_open_rejects_changed_upstream_hemisphere_constants_without_promotion(
    app_paths: AppPaths,
    metadata_bytes: bytes,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    runtime, calls, atlases = fake_runtime

    def changed_contract_factory(atlas_name: str, **kwargs: object) -> FakeBrainGlobeAtlas:
        atlas = FakeBrainGlobeAtlas(
            atlas_name,
            brainglobe_dir=kwargs["brainglobe_dir"],  # type: ignore[arg-type]
            interm_download_dir=kwargs["interm_download_dir"],  # type: ignore[arg-type]
            check_latest=kwargs["check_latest"],  # type: ignore[arg-type]
            config_dir=kwargs["config_dir"],  # type: ignore[arg-type]
            fn_update=kwargs["fn_update"],  # type: ignore[arg-type]
            calls=calls,
            metadata_bytes=metadata_bytes,
        )
        atlas.left_hemisphere_value = 2
        atlas.right_hemisphere_value = 1
        atlases.append(atlas)
        return atlas

    changed_runtime = adapter._BrainGlobeRuntime(
        atlas_factory=changed_contract_factory,  # type: ignore[arg-type]
        cached_atlas_factory=runtime.cached_atlas_factory,
        catalog_loader=runtime.catalog_loader,
        config_api=runtime.config_api,
        library_version=runtime.library_version,
    )

    with pytest.raises(
        BrainGlobeContractError,
        match="expected left=1 and right=2",
    ):
        BrainGlobeAtlasRepository(app_paths, _runtime=changed_runtime).open(
            "allen_mouse_25um",
            package_version="1.2",
        )
    assert len(calls) == 1
    assert not (app_paths.atlas_cache / "allen_mouse_25um_v1.2").exists()


def test_explicit_version_acquisition_ignores_older_cached_package(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, calls, _ = fake_runtime
    _write_valid_cache_package(app_paths.atlas_cache / "allen_mouse_25um_v1.1")
    repository = BrainGlobeAtlasRepository(app_paths)

    loaded = repository.open("allen_mouse_25um", package_version="1.2")

    assert loaded.metadata.atlas_package_version == "1.2"
    assert loaded.metadata.cache_path == str(
        (app_paths.atlas_cache / "allen_mouse_25um_v1.2").resolve()
    )
    assert calls[0]["brainglobe_dir"] != app_paths.atlas_cache
    assert (app_paths.atlas_cache / "allen_mouse_25um_v1.1").is_dir()
    assert repository.is_cached("allen_mouse_25um", "1.2")


def test_corrupt_target_is_quarantined_then_replaced_without_redownload_loop(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, calls, _ = fake_runtime
    target = app_paths.atlas_cache / "allen_mouse_25um_v1.2"
    target.mkdir()
    for filename in _CORE_PACKAGE_FILES:
        (target / filename).write_bytes(b"recoverable corrupt content")
    repository = BrainGlobeAtlasRepository(app_paths)

    assert not repository.is_cached("allen_mouse_25um", "1.2")
    first = repository.open("allen_mouse_25um", package_version="1.2")
    second = repository.open("allen_mouse_25um", package_version="1.2")

    assert first.metadata == second.metadata
    assert repository.is_cached("allen_mouse_25um", "1.2")
    assert len(calls) == 1
    quarantined = list((app_paths.atlas_cache / "quarantine").iterdir())
    assert len(quarantined) == 1
    assert quarantined[0].name.startswith("allen_mouse_25um_v1.2.invalid-")
    assert (quarantined[0] / "metadata.json").read_bytes() == b"recoverable corrupt content"


def test_loaded_atlas_normalizes_provenance_without_copying_volumes(
    app_paths: AppPaths,
    metadata_bytes: bytes,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, upstream_atlases = fake_runtime
    loaded = BrainGlobeAtlasRepository(app_paths).open("allen_mouse_25um")
    upstream = upstream_atlases[0]

    assert loaded.reference is upstream.reference
    assert loaded.annotation is upstream.annotation
    assert loaded.brainglobe_atlasapi_version == "2.3.1"
    assert loaded.metadata.atlas_key == "allen_mouse_25um"
    assert loaded.metadata.atlas_package_version == "1.2"
    assert loaded.metadata.source_annotation == "annotation/ccf_2017"
    assert loaded.metadata.framework_name == "Allen CCFv3"
    assert loaded.metadata.resolution_um == (25.0, 25.0, 25.0)
    assert loaded.metadata.shape_voxels == (2, 3, 4)
    assert loaded.metadata.midline_ml_um == 50.0
    assert loaded.metadata.metadata_sha256 == hashlib.sha256(metadata_bytes).hexdigest()
    assert [region.acronym for region in loaded.regions] == ["root", "CA1"]
    assert loaded.regions[1].parent_id == 1

    renderer_anchor = BrainGlobePhysicalPoint(
        atlas_key=loaded.metadata.atlas_key,
        atlas_version=loaded.metadata.atlas_package_version,
        ap_um=15.0,
        dv_um=15.0,
        ml_um=25.0,
    )
    project_payload = json.loads(
        PlannerProject(
            atlas=loaded.metadata,
            renderer_anchor=renderer_anchor,
        ).model_dump_json()
    )
    assert project_payload["atlas"]["atlas_package_version"] == "1.2"
    assert "structures_list" not in project_payload["atlas"]
    assert "mesh_filename" not in project_payload["atlas"]


def test_loaded_atlas_exposes_root_and_validated_region_meshes(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, upstream_atlases = fake_runtime
    loaded = BrainGlobeAtlasRepository(app_paths).open("allen_mouse_25um")
    upstream = upstream_atlases[0]

    assert loaded.root_mesh() is upstream.root_mesh_value
    assert loaded.region_mesh(2) is upstream.region_mesh_values[2]
    assert loaded.region_mesh("CA1") is upstream.region_mesh_values["CA1"]
    assert loaded.mesh_for_region(loaded.regions[1]) is upstream.region_mesh_values[2]
    assert loaded.root_mesh_file() == upstream.region_mesh_files["root"].resolve()
    assert loaded.region_mesh_file(2) == upstream.region_mesh_files[2].resolve()
    assert loaded.mesh_file_for_region("CA1") == upstream.region_mesh_files["CA1"].resolve()
    with pytest.raises(KeyError, match="unknown atlas structure ID"):
        loaded.region_mesh(999)

    escaped_mesh = app_paths.cache / "outside-atlas.obj"
    escaped_mesh.write_text("not atlas-owned", encoding="utf-8")
    upstream.region_mesh_files[2] = escaped_mesh
    with pytest.raises(BrainGlobeContractError, match="escapes atlas root"):
        loaded.region_mesh_file(2)


def test_structure_lookup_validates_identity_and_half_open_bounds_first(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, upstream_atlases = fake_runtime
    loaded = BrainGlobeAtlasRepository(app_paths).open("allen_mouse_25um")
    upstream = upstream_atlases[0]
    valid = BrainGlobePhysicalPoint(
        atlas_key="allen_mouse_25um",
        atlas_version="1.2",
        ap_um=49.999,
        dv_um=74.999,
        ml_um=99.999,
    )

    assert loaded.structure_at(valid) == loaded.regions[1]
    assert upstream.lookup_calls == [((49.999, 74.999, 99.999), True)]

    invalid_points = [
        BrainGlobePhysicalPoint(
            atlas_key="allen_mouse_25um",
            atlas_version="1.2",
            ap_um=-0.1,
            dv_um=0,
            ml_um=0,
        ),
        BrainGlobePhysicalPoint(
            atlas_key="allen_mouse_25um",
            atlas_version="1.2",
            ap_um=50,
            dv_um=0,
            ml_um=0,
        ),
        BrainGlobePhysicalPoint.model_construct(
            atlas_key="allen_mouse_25um",
            atlas_version="1.2",
            ap_um=float("nan"),
            dv_um=0.0,
            ml_um=0.0,
            frame_id="BRAINGLOBE_PHYSICAL_ASR_UM",
        ),
    ]
    for point in invalid_points:
        with pytest.raises(CoordinateBoundsError):
            loaded.region_at(point)
    with pytest.raises(AtlasIdentityError):
        loaded.region_at(
            BrainGlobePhysicalPoint(
                atlas_key="different_atlas",
                atlas_version="1.2",
                ap_um=0,
                dv_um=0,
                ml_um=0,
            )
        )
    assert len(upstream.lookup_calls) == 1


def test_cancellation_interrupts_upstream_callback_and_cleans_staging_directory(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, calls, _ = fake_runtime
    cancellation_checks = 0

    def cancel() -> bool:
        nonlocal cancellation_checks
        cancellation_checks += 1
        return cancellation_checks >= 2

    repository = BrainGlobeAtlasRepository(app_paths)
    with pytest.raises(AtlasDownloadCancelledError, match="allen_mouse_25um"):
        repository.open("allen_mouse_25um", package_version="1.2", cancel=cancel)

    temporary = calls[0]["interm_download_dir"]
    assert isinstance(temporary, Path)
    assert not temporary.exists()


def test_wrong_library_version_fails_before_any_upstream_operation(
    app_paths: AppPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory_called = False

    def factory(atlas_name: str, **kwargs: object) -> FakeBrainGlobeAtlas:
        del atlas_name, kwargs
        nonlocal factory_called
        factory_called = True
        raise AssertionError("factory must not be called")

    runtime = adapter._BrainGlobeRuntime(
        atlas_factory=factory,  # type: ignore[arg-type]
        cached_atlas_factory=lambda path: (_ for _ in ()).throw(FileNotFoundError(path)),
        catalog_loader=lambda: {},
        config_api=FakeBrainGlobeConfig(),
        library_version="3.0.0",
    )
    monkeypatch.setattr(adapter, "_load_runtime", lambda: runtime)

    with pytest.raises(BrainGlobeContractError, match=r"expected '2\.3\.1'"):
        BrainGlobeAtlasRepository(app_paths)
    assert factory_called is False
