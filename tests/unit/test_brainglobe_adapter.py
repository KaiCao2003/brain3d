"""Contract tests for the only BrainGlobe boundary in the application."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest

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


def _write_cache_package_stub(path: Path) -> None:
    """Create the minimum nonempty package files used by cache discovery."""

    path.mkdir()
    for filename in _CORE_PACKAGE_FILES:
        (path / filename).write_bytes(b"test-package-file")


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

        self.atlas_name = atlas_name
        self.root_dir = brainglobe_dir / f"{atlas_name}_v1.2"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        (self.root_dir / "metadata.json").write_bytes(metadata_bytes)
        (self.root_dir / "reference.tiff").write_bytes(b"fake-reference")
        (self.root_dir / "annotation.tiff").write_bytes(b"fake-annotation")
        (self.root_dir / "structures.json").write_bytes(b"[]")
        meshes_dir = self.root_dir / "meshes"
        meshes_dir.mkdir(exist_ok=True)
        (meshes_dir / "1.obj").write_text("root mesh", encoding="utf-8")
        (meshes_dir / "2.obj").write_text("CA1 mesh", encoding="utf-8")
        self.metadata: Mapping[str, object] = json.loads(metadata_bytes)
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
        return (10, 10, 10)

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
            "resolution": [10, 10, 10],
            "orientation": "asr",
            "shape": [2, 3, 4],
            "version": "1.2",
        },
        separators=(",", ":"),
    ).encode()


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
        },
        config_api=FakeBrainGlobeConfig(),
        library_version="2.3.1",
    )
    monkeypatch.setattr(adapter, "_load_runtime", lambda: runtime)
    return runtime, calls, atlases


def test_list_atlases_merges_remote_catalog_with_explicit_local_cache(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, _ = fake_runtime
    _write_cache_package_stub(app_paths.atlas_cache / "allen_mouse_25um_v1.1")
    _write_cache_package_stub(app_paths.atlas_cache / "private_mouse_50um_v0.4")
    (app_paths.atlas_cache / "not-an-atlas").mkdir()

    repository = BrainGlobeAtlasRepository(app_paths)
    records = repository.list_atlases()

    assert records == [
        AtlasCatalogRecord("allen_mouse_10um", "1.2", False),
        AtlasCatalogRecord("allen_mouse_25um", "1.2", False),
        AtlasCatalogRecord("private_mouse_50um", "0.4", True),
    ]
    assert repository.is_cached("allen_mouse_25um")
    assert repository.is_cached("allen_mouse_25um", "1.1")
    assert not repository.is_cached("allen_mouse_25um", "1.2")
    assert not repository.is_cached("allen_mouse_10um")


def test_catalog_downloaded_means_exact_latest_package_is_cached(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, _, _ = fake_runtime
    _write_cache_package_stub(app_paths.atlas_cache / "allen_mouse_25um_v1.1")
    repository = BrainGlobeAtlasRepository(app_paths)

    assert (
        next(
            record for record in repository.list_atlases() if record.name == "allen_mouse_25um"
        ).downloaded
        is False
    )

    _write_cache_package_stub(app_paths.atlas_cache / "allen_mouse_25um_v1.2")
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
    empty = app_paths.atlas_cache / "allen_mouse_10um_v1.2"
    empty.mkdir()
    partial = app_paths.atlas_cache / "allen_mouse_25um_v1.2"
    partial.mkdir()
    (partial / "metadata.json").write_bytes(b"{}")
    repository = BrainGlobeAtlasRepository(app_paths)

    assert not repository.is_cached("allen_mouse_10um", "1.2")
    assert not repository.is_cached("allen_mouse_25um", "1.2")
    assert all(not record.downloaded for record in repository.list_atlases())


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
    _, calls, _ = fake_runtime
    progress: list[tuple[int, int]] = []
    repository = BrainGlobeAtlasRepository(app_paths)

    repository.open("allen_mouse_25um", progress=lambda done, total: progress.append((done, total)))
    repository.open("allen_mouse_25um")

    first_temporary = calls[0]["interm_download_dir"]
    second_temporary = calls[1]["interm_download_dir"]
    assert isinstance(first_temporary, Path)
    assert isinstance(second_temporary, Path)
    assert calls[0]["brainglobe_dir"] == app_paths.atlas_cache
    assert calls[0]["check_latest"] is False
    assert calls[0]["config_dir"] == app_paths.config / "brainglobe" / "bg_config.conf"
    assert calls[0]["temporary_exists"] is True
    assert first_temporary.parent == app_paths.download_cache
    assert second_temporary.parent == app_paths.download_cache
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
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, calls, _ = fake_runtime
    repository = BrainGlobeAtlasRepository(app_paths)

    with pytest.raises(BrainGlobeContractError, match=r"requested .* v9\.9.*acquired v1\.2"):
        repository.open("allen_mouse_25um", package_version="9.9")
    assert len(calls) == 1
    assert not (app_paths.atlas_cache / "allen_mouse_25um_v9.9").exists()


def test_explicit_version_acquisition_ignores_older_cached_package(
    app_paths: AppPaths,
    fake_runtime: tuple[
        adapter._BrainGlobeRuntime,
        list[dict[str, object]],
        list[FakeBrainGlobeAtlas],
    ],
) -> None:
    _, calls, _ = fake_runtime
    _write_cache_package_stub(app_paths.atlas_cache / "allen_mouse_25um_v1.1")
    repository = BrainGlobeAtlasRepository(app_paths)

    loaded = repository.open("allen_mouse_25um", package_version="1.2")

    assert loaded.metadata.atlas_package_version == "1.2"
    assert loaded.metadata.cache_path == str(
        (app_paths.atlas_cache / "allen_mouse_25um_v1.2").resolve()
    )
    assert calls[0]["brainglobe_dir"] != app_paths.atlas_cache
    assert (app_paths.atlas_cache / "allen_mouse_25um_v1.1").is_dir()
    assert repository.is_cached("allen_mouse_25um", "1.2")


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
    loaded = BrainGlobeAtlasRepository(app_paths).open("allen_mouse_10um")
    upstream = upstream_atlases[0]

    assert loaded.reference is upstream.reference
    assert loaded.annotation is upstream.annotation
    assert loaded.brainglobe_atlasapi_version == "2.3.1"
    assert loaded.metadata.atlas_key == "allen_mouse_10um"
    assert loaded.metadata.atlas_package_version == "1.2"
    assert loaded.metadata.source_annotation == "annotation/ccf_2017"
    assert loaded.metadata.framework_name == "Allen CCFv3"
    assert loaded.metadata.resolution_um == (10.0, 10.0, 10.0)
    assert loaded.metadata.shape_voxels == (2, 3, 4)
    assert loaded.metadata.metadata_sha256 == hashlib.sha256(metadata_bytes).hexdigest()
    assert [region.acronym for region in loaded.regions] == ["root", "CA1"]
    assert loaded.regions[1].parent_id == 1

    project_payload = json.loads(PlannerProject(atlas=loaded.metadata).model_dump_json())
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
    loaded = BrainGlobeAtlasRepository(app_paths).open("allen_mouse_10um")
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
    loaded = BrainGlobeAtlasRepository(app_paths).open("allen_mouse_10um")
    upstream = upstream_atlases[0]
    valid = BrainGlobePhysicalPoint(
        atlas_key="allen_mouse_10um",
        atlas_version="1.2",
        ap_um=19.999,
        dv_um=29.999,
        ml_um=39.999,
    )

    assert loaded.structure_at(valid) == loaded.regions[1]
    assert upstream.lookup_calls == [((19.999, 29.999, 39.999), True)]

    invalid_points = [
        BrainGlobePhysicalPoint(
            atlas_key="allen_mouse_10um",
            atlas_version="1.2",
            ap_um=-0.1,
            dv_um=0,
            ml_um=0,
        ),
        BrainGlobePhysicalPoint(
            atlas_key="allen_mouse_10um",
            atlas_version="1.2",
            ap_um=20,
            dv_um=0,
            ml_um=0,
        ),
        BrainGlobePhysicalPoint.model_construct(
            atlas_key="allen_mouse_10um",
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
    with pytest.raises(AtlasDownloadCancelledError, match="allen_mouse_10um"):
        repository.open("allen_mouse_10um", cancel=cancel)

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
