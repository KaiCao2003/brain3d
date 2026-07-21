"""Stable application boundary for :mod:`brainglobe_atlasapi` 2.3.1.

BrainGlobe objects remain private to this module.  The rest of the application
receives validated domain records, NumPy volume views, or an explicitly
requested mesh.  Importing BrainGlobe is delayed until application-owned paths
have been configured because version 2.3.1 reads its config location at import
time.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import reload
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from numbers import Integral, Real
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.paths import AppPaths, app_paths, configure_brainglobe_environment

BRAINGLOBE_ATLASAPI_VERSION = "2.3.1"
_ATLAS_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_PACKAGE_VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
_LOCAL_ATLAS_PATTERN = re.compile(
    rf"^(?P<name>.+)_v(?P<version>{_PACKAGE_VERSION_PATTERN.pattern[1:-1]})$"
)
_REQUIRED_PACKAGE_FILES = (
    "metadata.json",
    "reference.tiff",
    "annotation.tiff",
    "structures.json",
)
_CATALOG_TIMEOUT_SECONDS = 15.0

ProgressCallback = Callable[[int, int], None]
CancellationCheck = Callable[[], bool]


class AtlasAdapterError(RuntimeError):
    """Base error raised by the application-owned atlas boundary."""


class BrainGlobeContractError(AtlasAdapterError):
    """Raised when the installed library or atlas violates the pinned contract."""


class AtlasDownloadCancelledError(AtlasAdapterError):
    """Raised when cancellation is requested during atlas acquisition."""


@dataclass(frozen=True, slots=True)
class AtlasCatalogRecord:
    """One available BrainGlobe atlas and its local-cache state."""

    name: str
    latest_version: str
    downloaded: bool


class _AtlasLike(Protocol):
    """The small stable 2.3.1 surface consumed by this adapter."""

    atlas_name: str
    root_dir: Path
    metadata: Mapping[str, object]
    structures_list: Sequence[Mapping[str, object]]

    @property
    def resolution(self) -> tuple[object, object, object]: ...

    @property
    def orientation(self) -> str: ...

    @property
    def shape(self) -> tuple[object, object, object]: ...

    @property
    def reference(self) -> NDArray[np.generic]: ...

    @property
    def annotation(self) -> NDArray[np.generic]: ...

    def structure_from_coords(
        self,
        coords: tuple[float, float, float],
        microns: bool = False,
    ) -> object: ...

    def mesh_from_structure(self, structure: int | str) -> object: ...

    def root_mesh(self) -> object: ...

    def meshfile_from_structure(self, structure: int | str) -> Path: ...

    def root_meshfile(self) -> Path: ...


class _AtlasFactory(Protocol):
    def __call__(
        self,
        atlas_name: str,
        *,
        brainglobe_dir: Path,
        interm_download_dir: Path,
        check_latest: bool,
        config_dir: Path,
        fn_update: ProgressCallback | None,
    ) -> _AtlasLike: ...


class _ConfigApi(Protocol):
    """Official BrainGlobe configuration functions used by this boundary."""

    def read_config(self, path: Path) -> Mapping[str, Mapping[str, str]]: ...

    def write_config_value(self, key: str, value: object, path: Path) -> None: ...


@dataclass(frozen=True, slots=True)
class _BrainGlobeRuntime:
    atlas_factory: _AtlasFactory
    cached_atlas_factory: Callable[[Path], _AtlasLike]
    catalog_loader: Callable[[], Mapping[str, object]]
    config_api: _ConfigApi
    library_version: str


def _load_runtime() -> _BrainGlobeRuntime:
    """Import the pinned upstream API after its config path is established."""

    try:
        installed_version = distribution_version("brainglobe-atlasapi")
    except PackageNotFoundError as error:
        raise BrainGlobeContractError(
            "brainglobe-atlasapi is not installed; expected exactly version 2.3.1"
        ) from error

    from brainglobe_atlasapi import BrainGlobeAtlas, config
    from brainglobe_atlasapi.core import Atlas
    from brainglobe_atlasapi.list_atlases import get_all_atlases_lastversions

    expected_config_dir = Path(os.environ["BRAINGLOBE_CONFIG_DIR"]).resolve()
    if Path(config.CONFIG_DIR).resolve() != expected_config_dir:
        # BrainGlobe stores its config location at module import time.  Reload
        # the module if another library imported it before this application
        # established its app-owned environment.
        config = reload(config)
    if Path(config.CONFIG_DIR).resolve() != expected_config_dir:
        raise BrainGlobeContractError(
            "BrainGlobe retained an external config directory; expected "
            f"{expected_config_dir}, got {Path(config.CONFIG_DIR).resolve()}"
        )

    return _BrainGlobeRuntime(
        atlas_factory=cast(_AtlasFactory, BrainGlobeAtlas),
        cached_atlas_factory=cast(Callable[[Path], _AtlasLike], Atlas),
        catalog_loader=cast(
            Callable[[], Mapping[str, object]],
            get_all_atlases_lastversions,
        ),
        config_api=cast(_ConfigApi, config),
        library_version=installed_version,
    )


def _configure_upstream_paths(
    config_api: _ConfigApi,
    *,
    config_file: Path,
    atlas_cache: Path,
    download_cache: Path,
) -> None:
    """Persist and verify app-owned paths using AtlasAPI's config API.

    ``read_config`` creates BrainGlobe's supported default file when needed.
    ``write_config_value`` updates only the two known keys, preserving all
    unrelated sections and values in an existing user configuration.
    """

    config_api.read_config(config_file)
    expected_paths = {
        "brainglobe_dir": atlas_cache.resolve(),
        "interm_download_dir": download_cache.resolve(),
    }
    for key, expected in expected_paths.items():
        config_api.write_config_value(key, str(expected), config_file)

    configured = config_api.read_config(config_file)
    try:
        default_dirs = configured["default_dirs"]
    except KeyError as error:
        raise BrainGlobeContractError(
            f"BrainGlobe config {config_file} has no 'default_dirs' section"
        ) from error
    for key, expected in expected_paths.items():
        raw_value = default_dirs.get(key)
        if raw_value is None or Path(raw_value).expanduser().resolve() != expected:
            raise BrainGlobeContractError(
                f"BrainGlobe config {config_file} did not retain {key}={expected}"
            )


class BrainGlobeAtlasRepository:
    """Discover and open atlases exclusively through stable AtlasAPI 2.3.1."""

    def __init__(
        self,
        paths: AppPaths | None = None,
        *,
        _runtime: _BrainGlobeRuntime | None = None,
    ) -> None:
        self.paths = configure_brainglobe_environment(paths or app_paths())
        self._runtime = _runtime or _load_runtime()
        if self._runtime.library_version != BRAINGLOBE_ATLASAPI_VERSION:
            raise BrainGlobeContractError(
                "unsupported brainglobe-atlasapi version "
                f"{self._runtime.library_version!r}; expected "
                f"{BRAINGLOBE_ATLASAPI_VERSION!r}"
            )
        _configure_upstream_paths(
            self._runtime.config_api,
            config_file=self.paths.config / "brainglobe" / "bg_config.conf",
            atlas_cache=self.paths.atlas_cache,
            download_cache=self.paths.download_cache,
        )

    def list_atlases(
        self,
        *,
        local_only: bool = False,
        cancel: CancellationCheck | None = None,
    ) -> list[AtlasCatalogRecord]:
        """Return available atlases merged with the application-owned cache.

        AtlasAPI owns retrieval and parsing of the remote catalog.  Local
        detection is deliberately based on :class:`AppPaths`, rather than on
        BrainGlobe's process-global default cache.  ``local_only`` never calls
        upstream network-aware catalog code.
        """

        if cancel is not None and cancel():
            raise AtlasDownloadCancelledError("atlas catalog request cancelled")
        available: Mapping[str, object]
        if local_only:
            available = {}
        else:
            try:
                available = self._load_catalog_bounded(cancel=cancel)
            except FileNotFoundError:
                # First-run offline operation can still enumerate already
                # cached atlas packages when no remote catalog cache exists.
                available = {}

        remote_versions: dict[str, str] = {}
        for raw_name, raw_version in available.items():
            name = str(raw_name)
            self._validate_atlas_name(name)
            latest_version = str(raw_version).strip()
            if not latest_version:
                raise BrainGlobeContractError(
                    f"BrainGlobe catalog returned an empty version for {name!r}"
                )
            self._validate_package_version(latest_version)
            remote_versions[name] = latest_version

        local_versions = self._local_versions()
        records: list[AtlasCatalogRecord] = []
        for name in sorted(remote_versions.keys() | local_versions.keys()):
            if name in remote_versions:
                latest_version = remote_versions[name]
            else:
                latest_version = max(local_versions[name], key=_version_sort_key)
            records.append(
                AtlasCatalogRecord(
                    name=name,
                    latest_version=latest_version,
                    downloaded=latest_version in local_versions.get(name, []),
                )
            )
        return records

    def _load_catalog_bounded(
        self,
        *,
        cancel: CancellationCheck | None,
    ) -> Mapping[str, object]:
        """Bound an upstream catalog call whose pinned HTTP request lacks a timeout."""

        finished = Event()
        outcome: list[Mapping[str, object] | Exception] = []

        def load() -> None:
            try:
                outcome.append(self._runtime.catalog_loader())
            except Exception as error:
                outcome.append(error)
            finally:
                finished.set()

        Thread(
            target=load,
            name="brainglobe-catalog-request",
            daemon=True,
        ).start()
        deadline = time.monotonic() + _CATALOG_TIMEOUT_SECONDS
        while True:
            if cancel is not None and cancel():
                raise AtlasDownloadCancelledError("atlas catalog request cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AtlasAdapterError(
                    "BrainGlobe atlas catalog did not respond within "
                    f"{_CATALOG_TIMEOUT_SECONDS:g} seconds"
                )
            if finished.wait(min(0.1, remaining)):
                break

        if not outcome:
            raise BrainGlobeContractError("BrainGlobe catalog loader returned no outcome")
        result = outcome[0]
        if isinstance(result, Exception):
            raise result
        return result

    def is_cached(self, atlas_name: str, package_version: str | None = None) -> bool:
        """Return whether the application cache contains the requested package.

        This check is local-only and supports catalog display and diagnostics.
        The authoritative download policy is enforced atomically by
        :meth:`open`.
        """

        self._validate_atlas_name(atlas_name)
        versions = self._local_versions().get(atlas_name, [])
        if package_version is None:
            return bool(versions)
        self._validate_package_version(package_version)
        return package_version in versions

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: ProgressCallback | None = None,
        cancel: CancellationCheck | None = None,
    ) -> LoadedAtlas:
        """Open one exact cached package or acquire an atlas when permitted.

        Cached-only calls use BrainGlobe's low-level package reader, which
        cannot consult the network, delete a corrupt cache, or invoke the
        downloader.  Acquisition calls receive a unique intermediate
        directory. Raising :class:`AtlasDownloadCancelledError` from the
        upstream progress callback aborts the transfer, and
        ``TemporaryDirectory`` removes its partial archive without implementing
        a second downloader.
        """

        self._validate_atlas_name(atlas_name)
        if package_version is not None:
            self._validate_package_version(package_version)
        if cancel is not None and cancel():
            raise AtlasDownloadCancelledError(f"atlas acquisition cancelled: {atlas_name}")

        cached_root = self._cached_root(
            atlas_name,
            package_version=package_version,
            required=not allow_download,
        )
        if cached_root is not None and (not allow_download or package_version is not None):
            # The low-level Atlas reader performs no catalog lookup, download,
            # repair, or cache deletion.  This is the only safe implementation
            # of a repository-level no-download guarantee.
            upstream_atlas = self._runtime.cached_atlas_factory(cached_root)
        elif package_version is not None:
            upstream_atlas = self._acquire_exact_package(
                atlas_name,
                package_version=package_version,
                progress=progress,
                cancel=cancel,
            )
        else:
            update_callback = self._progress_callback(
                atlas_name=atlas_name,
                progress=progress,
                cancel=cancel,
            )
            prefix = f"{atlas_name}-"
            config_file = self.paths.config / "brainglobe" / "bg_config.conf"
            with TemporaryDirectory(prefix=prefix, dir=self.paths.download_cache) as temporary:
                upstream_atlas = self._runtime.atlas_factory(
                    atlas_name,
                    brainglobe_dir=self.paths.atlas_cache,
                    interm_download_dir=Path(temporary),
                    check_latest=False,
                    config_dir=config_file,
                    fn_update=update_callback,
                )

            actual_name = str(upstream_atlas.atlas_name)
            if actual_name != atlas_name:
                raise BrainGlobeContractError(
                    f"requested atlas {atlas_name!r}, but BrainGlobe opened {actual_name!r}"
                )
        if cancel is not None and cancel():
            raise AtlasDownloadCancelledError(f"atlas acquisition cancelled: {atlas_name}")
        atlas_root = Path(upstream_atlas.root_dir).resolve()
        try:
            atlas_root.relative_to(self.paths.atlas_cache.resolve())
        except ValueError as error:
            raise BrainGlobeContractError(
                f"BrainGlobe opened atlas outside the application cache: {atlas_root}"
            ) from error
        loaded = LoadedAtlas(
            upstream_atlas,
            atlas_key=atlas_name,
            brainglobe_atlasapi_version=self._runtime.library_version,
        )
        if package_version is not None and loaded.metadata.atlas_package_version != package_version:
            raise BrainGlobeContractError(
                f"requested atlas {atlas_name!r} package v{package_version}, but "
                f"BrainGlobe opened v{loaded.metadata.atlas_package_version}"
            )
        return loaded

    def _acquire_exact_package(
        self,
        atlas_name: str,
        *,
        package_version: str,
        progress: ProgressCallback | None,
        cancel: CancellationCheck | None,
    ) -> _AtlasLike:
        """Acquire and verify a requested latest package without touching older caches."""

        update_callback = self._progress_callback(
            atlas_name=atlas_name,
            progress=progress,
            cancel=cancel,
        )
        config_file = self.paths.config / "brainglobe" / "bg_config.conf"
        with (
            TemporaryDirectory(prefix=f".{atlas_name}-", dir=self.paths.atlas_cache) as staging,
            TemporaryDirectory(prefix=f"{atlas_name}-", dir=self.paths.download_cache) as download,
        ):
            staging_cache = Path(staging) / "packages"
            staging_cache.mkdir()
            staged_atlas = self._runtime.atlas_factory(
                atlas_name,
                brainglobe_dir=staging_cache,
                interm_download_dir=Path(download),
                check_latest=False,
                config_dir=config_file,
                fn_update=update_callback,
            )
            actual_name = str(staged_atlas.atlas_name)
            if actual_name != atlas_name:
                raise BrainGlobeContractError(
                    f"requested atlas {atlas_name!r}, but BrainGlobe acquired {actual_name!r}"
                )
            staged_root = Path(staged_atlas.root_dir).resolve()
            try:
                staged_root.relative_to(staging_cache.resolve())
            except ValueError as error:
                raise BrainGlobeContractError(
                    f"BrainGlobe staged atlas outside the isolated cache: {staged_root}"
                ) from error
            if not self._is_complete_package(staged_root):
                raise BrainGlobeContractError(
                    f"BrainGlobe staged an incomplete atlas package: {staged_root}"
                )
            staged_loaded = LoadedAtlas(
                staged_atlas,
                atlas_key=atlas_name,
                brainglobe_atlasapi_version=self._runtime.library_version,
            )
            actual_version = staged_loaded.metadata.atlas_package_version
            if actual_version != package_version:
                raise BrainGlobeContractError(
                    f"requested atlas {atlas_name!r} package v{package_version}, but "
                    f"BrainGlobe acquired v{actual_version}"
                )
            if cancel is not None and cancel():
                raise AtlasDownloadCancelledError(f"atlas acquisition cancelled: {atlas_name}")

            target = self.paths.atlas_cache / f"{atlas_name}_v{package_version}"
            if target.exists():
                # Another process won the race.  Never overwrite it; the
                # ordinary read-only validation below decides whether it is
                # usable as the exact requested package.
                if not self._is_complete_package(target):
                    raise BrainGlobeContractError(
                        f"concurrent atlas package is incomplete: {target.resolve()}"
                    )
            else:
                staged_root.replace(target)

        return self._runtime.cached_atlas_factory(target.resolve())

    def _cached_root(
        self,
        atlas_name: str,
        *,
        package_version: str | None,
        required: bool,
    ) -> Path | None:
        versions = self._local_versions().get(atlas_name, [])
        selected_version = package_version
        if selected_version is None and versions:
            selected_version = max(versions, key=_version_sort_key)
        if selected_version is None or selected_version not in versions:
            if required:
                version = "" if package_version is None else f" v{package_version}"
                raise AtlasAdapterError(
                    f"atlas {atlas_name}{version} is not in the application cache; "
                    "downloads are disabled"
                )
            return None
        return (self.paths.atlas_cache / f"{atlas_name}_v{selected_version}").resolve()

    def _local_versions(self) -> dict[str, list[str]]:
        versions: dict[str, list[str]] = {}
        for candidate in self.paths.atlas_cache.iterdir():
            if (
                not candidate.is_dir()
                or candidate.is_symlink()
                or not self._is_complete_package(candidate)
            ):
                continue
            match = _LOCAL_ATLAS_PATTERN.fullmatch(candidate.name)
            if match is None:
                continue
            name = match.group("name")
            self._validate_atlas_name(name)
            versions.setdefault(name, []).append(match.group("version"))
        return versions

    @staticmethod
    def _is_complete_package(candidate: Path) -> bool:
        """Return whether stable core atlas files are regular and nonempty."""

        for filename in _REQUIRED_PACKAGE_FILES:
            path = candidate / filename
            if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
                return False
        return True

    @staticmethod
    def _validate_atlas_name(atlas_name: str) -> None:
        if not _ATLAS_NAME_PATTERN.fullmatch(atlas_name):
            raise ValueError(
                "atlas name must start with an ASCII letter or digit and contain only "
                "letters, digits, underscores, periods, or hyphens"
            )

    @staticmethod
    def _validate_package_version(package_version: str) -> None:
        if not _PACKAGE_VERSION_PATTERN.fullmatch(package_version):
            raise ValueError("atlas package version must contain dot-separated integers")

    @staticmethod
    def _progress_callback(
        *,
        atlas_name: str,
        progress: ProgressCallback | None,
        cancel: CancellationCheck | None,
    ) -> ProgressCallback | None:
        if progress is None and cancel is None:
            return None

        def update(completed: int, total: int) -> None:
            if cancel is not None and cancel():
                raise AtlasDownloadCancelledError(f"atlas acquisition cancelled: {atlas_name}")
            if progress is not None:
                progress(completed, total)

        return update


class LoadedAtlas:
    """A loaded atlas with only application-owned records exposed publicly."""

    __slots__ = (
        "__atlas",
        "_regions",
        "_regions_by_acronym",
        "_regions_by_id",
        "_space",
        "brainglobe_atlasapi_version",
        "metadata",
    )

    def __init__(
        self,
        atlas: _AtlasLike,
        *,
        atlas_key: str,
        brainglobe_atlasapi_version: str,
    ) -> None:
        if brainglobe_atlasapi_version != BRAINGLOBE_ATLASAPI_VERSION:
            raise BrainGlobeContractError(
                "LoadedAtlas requires brainglobe-atlasapi "
                f"{BRAINGLOBE_ATLASAPI_VERSION}, got {brainglobe_atlasapi_version}"
            )
        self.__atlas = atlas
        self.brainglobe_atlasapi_version = brainglobe_atlasapi_version
        self.metadata = _normalize_metadata(atlas, atlas_key=atlas_key)
        self._space = BrainGlobeAtlasSpace(self.metadata)
        self._regions = tuple(_normalize_regions(atlas.structures_list))
        self._regions_by_id = {region.structure_id: region for region in self._regions}
        self._regions_by_acronym = {region.acronym: region for region in self._regions}
        if len(self._regions_by_id) != len(self._regions):
            raise BrainGlobeContractError("atlas contains duplicate structure IDs")
        if len(self._regions_by_acronym) != len(self._regions):
            raise BrainGlobeContractError("atlas contains duplicate structure acronyms")

    @property
    def reference(self) -> NDArray[np.generic]:
        """Return BrainGlobe's lazily loaded reference array without copying."""

        return self.__atlas.reference

    @property
    def annotation(self) -> NDArray[np.generic]:
        """Return BrainGlobe's lazily loaded annotation array without copying."""

        return self.__atlas.annotation

    @property
    def regions(self) -> list[RegionRecord]:
        """Return normalized, JSON-safe region records in atlas order."""

        return list(self._regions)

    def structure_at(self, point: BrainGlobePhysicalPoint) -> RegionRecord | None:
        """Resolve a physical point after identity and half-open bounds checks."""

        # BrainGlobe 2.3.1 truncates coordinates and permits NumPy negative
        # indexing.  This conversion is intentionally performed before the
        # upstream call even though only its validation side effect is needed.
        self._space.physical_to_index(point)
        raw_structure_id = self.__atlas.structure_from_coords(point.as_tuple(), microns=True)
        if isinstance(raw_structure_id, bool) or not isinstance(raw_structure_id, Integral):
            raise BrainGlobeContractError(
                "BrainGlobe structure lookup returned a non-integral identifier: "
                f"{raw_structure_id!r}"
            )
        structure_id = int(raw_structure_id)
        if structure_id == 0:
            return None
        try:
            return self._regions_by_id[structure_id]
        except KeyError as error:
            raise BrainGlobeContractError(
                f"annotation references unknown structure ID {structure_id}"
            ) from error

    def region_at(self, point: BrainGlobePhysicalPoint) -> RegionRecord | None:
        """Alias for :meth:`structure_at` using application terminology."""

        return self.structure_at(point)

    def root_mesh(self) -> object:
        """Load and return the root mesh through BrainGlobe's lazy mesh API."""

        return self.__atlas.root_mesh()

    def region_mesh(self, region: RegionRecord | int | str) -> object:
        """Load one validated region mesh without exposing a structure object."""

        return self.__atlas.mesh_from_structure(self._region_identifier(region))

    def mesh_for_region(self, region: RegionRecord | int | str) -> object:
        """Readable alias for :meth:`region_mesh`."""

        return self.region_mesh(region)

    def root_mesh_file(self) -> Path:
        """Return the verified root mesh path inside this exact atlas package."""

        return self._validated_mesh_file(self.__atlas.root_meshfile(), description="root mesh")

    def region_mesh_file(self, region: RegionRecord | int | str) -> Path:
        """Return one verified region mesh path inside this atlas package."""

        identifier = self._region_identifier(region)
        return self._validated_mesh_file(
            self.__atlas.meshfile_from_structure(identifier),
            description=f"mesh for structure {identifier!r}",
        )

    def mesh_file_for_region(self, region: RegionRecord | int | str) -> Path:
        """Readable alias for :meth:`region_mesh_file`."""

        return self.region_mesh_file(region)

    def _region_identifier(self, region: RegionRecord | int | str) -> int | str:
        identifier: int | str
        if isinstance(region, RegionRecord):
            identifier = region.structure_id
        elif isinstance(region, bool):
            raise KeyError("boolean values are not valid atlas structure identifiers")
        else:
            identifier = region

        if isinstance(identifier, int):
            if identifier not in self._regions_by_id:
                raise KeyError(f"unknown atlas structure ID {identifier}")
        elif isinstance(identifier, str):
            if identifier not in self._regions_by_acronym:
                raise KeyError(f"unknown atlas structure acronym {identifier!r}")
        else:
            raise TypeError("region must be a RegionRecord, structure ID, or acronym")
        return identifier

    def _validated_mesh_file(self, value: Path, *, description: str) -> Path:
        atlas_root = Path(self.metadata.cache_path).resolve()
        path = Path(value).resolve()
        try:
            path.relative_to(atlas_root)
        except ValueError as error:
            raise BrainGlobeContractError(
                f"BrainGlobe {description} escapes atlas root {atlas_root}: {path}"
            ) from error
        if not path.is_file():
            raise BrainGlobeContractError(f"BrainGlobe {description} file is missing: {path}")
        return path


def _normalize_metadata(atlas: _AtlasLike, *, atlas_key: str) -> AtlasMetadata:
    raw = atlas.metadata
    orientation = str(atlas.orientation).lower()
    metadata_orientation = _required_text(raw, "orientation").lower()
    if orientation != "asr" or metadata_orientation != "asr":
        raise BrainGlobeContractError(
            "stable adapter requires BrainGlobe ASR orientation; got "
            f"property={orientation!r}, metadata={metadata_orientation!r}"
        )

    shape = _shape_triplet(atlas.shape, field="shape")
    metadata_shape = _shape_triplet(raw.get("shape"), field="metadata.shape")
    if shape != metadata_shape:
        raise BrainGlobeContractError(
            f"BrainGlobe shape property {shape} disagrees with metadata {metadata_shape}"
        )

    resolution = _resolution_triplet(atlas.resolution, field="resolution")
    metadata_resolution = _resolution_triplet(raw.get("resolution"), field="metadata.resolution")
    if resolution != metadata_resolution:
        raise BrainGlobeContractError(
            "BrainGlobe resolution property "
            f"{resolution} disagrees with metadata {metadata_resolution}"
        )

    root_dir = Path(atlas.root_dir).resolve()
    package_version = _required_text(raw, "version")
    expected_root_name = f"{atlas_key}_v{package_version}"
    if root_dir.name != expected_root_name:
        raise BrainGlobeContractError(
            f"atlas package directory {root_dir.name!r} does not match metadata identity "
            f"{expected_root_name!r}"
        )
    metadata_path = root_dir / "metadata.json"
    if not metadata_path.is_file():
        raise BrainGlobeContractError(f"atlas metadata file is missing: {metadata_path}")
    with metadata_path.open("rb") as metadata_file:
        metadata_sha256 = hashlib.file_digest(metadata_file, "sha256").hexdigest()

    source_annotation = _optional_text(raw, "source_annotation")
    if source_annotation is None and atlas_key.startswith("allen_mouse_"):
        # Stable 2.3.1 Allen packagers explicitly request this annotation,
        # although the generated metadata schema has no dedicated field.
        source_annotation = "annotation/ccf_2017"

    framework_name = _optional_text(raw, "framework_name")
    if framework_name is None:
        framework_name = (
            "Allen CCFv3" if atlas_key.startswith("allen_mouse_") else _required_text(raw, "name")
        )

    axes = (
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
    )
    symmetric = raw.get("symmetric")
    if not isinstance(symmetric, bool):
        raise BrainGlobeContractError("atlas metadata 'symmetric' must be a boolean")

    return AtlasMetadata(
        atlas_key=atlas_key,
        atlas_package_version=package_version,
        species=_required_text(raw, "species"),
        citation=_citation_text(raw.get("citation")),
        source_url=_first_required_text(raw, "atlas_link", "source_url"),
        cache_path=str(root_dir),
        metadata_sha256=metadata_sha256,
        resolution_um=resolution,
        shape_voxels=shape,
        standardized_orientation="asr",
        source_annotation=source_annotation,
        framework_name=framework_name,
        symmetric=symmetric,
        axes=axes,
    )


def _normalize_regions(
    structures: Sequence[Mapping[str, object]],
) -> list[RegionRecord]:
    regions: list[RegionRecord] = []
    for index, structure in enumerate(structures):
        structure_id = _positive_integer(structure.get("id"), f"structures[{index}].id")
        structure_path = _integer_tuple(
            structure.get("structure_id_path"),
            field=f"structures[{index}].structure_id_path",
        )
        if not structure_path or structure_path[-1] != structure_id:
            raise BrainGlobeContractError(
                f"structure {structure_id} has an invalid hierarchy path {structure_path}"
            )
        rgb = _rgb_triplet(
            structure.get("rgb_triplet"),
            field=f"structures[{index}].rgb_triplet",
        )
        regions.append(
            RegionRecord(
                structure_id=structure_id,
                acronym=_required_text(structure, "acronym"),
                name=_required_text(structure, "name"),
                structure_id_path=structure_path,
                rgb=rgb,
            )
        )
    if not regions:
        raise BrainGlobeContractError("atlas contains no structure records")
    return regions


def _required_text(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BrainGlobeContractError(f"atlas metadata field {key!r} must be non-empty text")
    return value.strip()


def _optional_text(mapping: Mapping[str, object], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise BrainGlobeContractError(f"atlas metadata field {key!r} must be non-empty text")
    return value.strip()


def _first_required_text(mapping: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise BrainGlobeContractError(
        f"atlas metadata must contain one non-empty text field from {keys}"
    )


def _citation_text(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        citations = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if len(citations) == len(value) and citations:
            return "; ".join(citations)
    raise BrainGlobeContractError("atlas metadata field 'citation' must contain citation text")


def _triplet(value: object, *, field: str) -> tuple[object, object, object]:
    if isinstance(value, (str, bytes)):
        raise BrainGlobeContractError(f"{field} must be a three-element sequence")
    try:
        items = tuple(cast(Iterable[object], value))
    except TypeError as error:
        raise BrainGlobeContractError(f"{field} must be a three-element sequence") from error
    if len(items) != 3:
        raise BrainGlobeContractError(f"{field} must contain exactly three elements")
    return (items[0], items[1], items[2])


def _shape_triplet(value: object, *, field: str) -> tuple[int, int, int]:
    items = _triplet(value, field=field)
    result: list[int] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, Integral) or int(item) <= 0:
            raise BrainGlobeContractError(f"{field} must contain positive integers")
        result.append(int(item))
    return (result[0], result[1], result[2])


def _resolution_triplet(value: object, *, field: str) -> tuple[float, float, float]:
    items = _triplet(value, field=field)
    result: list[float] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, Real):
            raise BrainGlobeContractError(f"{field} must contain positive finite numbers")
        component = float(item)
        if not math.isfinite(component) or component <= 0:
            raise BrainGlobeContractError(f"{field} must contain positive finite numbers")
        result.append(component)
    return (result[0], result[1], result[2])


def _integer_tuple(value: object, *, field: str) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)):
        raise BrainGlobeContractError(f"{field} must be an integer sequence")
    try:
        items = tuple(cast(Iterable[object], value))
    except TypeError as error:
        raise BrainGlobeContractError(f"{field} must be an integer sequence") from error
    return tuple(_positive_integer(item, field) for item in items)


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) <= 0:
        raise BrainGlobeContractError(f"{field} must be a positive integer")
    return int(value)


def _rgb_triplet(value: object, *, field: str) -> tuple[int, int, int]:
    items = _triplet(value, field=field)
    result: list[int] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, Integral):
            raise BrainGlobeContractError(f"{field} must contain integer RGB components")
        component = int(item)
        if component < 0 or component > 255:
            raise BrainGlobeContractError(f"{field} components must be in [0, 255]")
        result.append(component)
    return (result[0], result[1], result[2])


def _version_sort_key(value: str) -> tuple[int, ...]:
    return tuple(int(component) for component in value.split("."))
