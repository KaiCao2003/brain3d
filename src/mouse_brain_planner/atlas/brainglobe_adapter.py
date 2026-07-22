"""Stable application boundary for :mod:`brainglobe_atlasapi` 2.3.1.

BrainGlobe objects remain private to this module.  The rest of the application
receives validated domain records, NumPy volume views, or an explicitly
requested mesh.  Importing BrainGlobe is delayed until application-owned paths
have been configured because version 2.3.1 reads its config location at import
time.
"""

from __future__ import annotations

import configparser
import hashlib
import json
import math
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from http.client import HTTPException
from importlib import reload
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from numbers import Integral, Real
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Protocol, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
import tifffile
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
_CATALOG_TOTAL_TIMEOUT_SECONDS = 15.0
_CATALOG_SOCKET_TIMEOUT_SECONDS = 2.0
_CATALOG_MAX_BYTES = 1024 * 1024
_CATALOG_READ_CHUNK_BYTES = 16 * 1024
_OFFICIAL_CATALOG_URL = "https://gin.g-node.org/brainglobe/atlases/raw/master/last_versions.conf"
_SUPPORTED_ATLAS_RESOLUTION_UM = {
    "allen_mouse_25um": (25.0, 25.0, 25.0),
}
_SUPPORTED_ATLAS_SHAPE_VOXELS = {
    "allen_mouse_25um": (528, 320, 456),
}
_SUPPORTED_ATLAS_PACKAGE_VERSIONS = {
    "allen_mouse_25um": frozenset({"1.2"}),
}
SUPPORTED_ATLAS_KEYS = frozenset(_SUPPORTED_ATLAS_RESOLUTION_UM)

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
    left_hemisphere_value: int
    right_hemisphere_value: int

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
    # Production uses the cancellable stdlib transport below. This hook exists
    # only for deterministic injected test runtimes.
    catalog_loader: Callable[[], Mapping[str, object]] | None
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
        catalog_loader=None,
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

        The official BrainGlobe catalog endpoint is read through this adapter's
        bounded transport. Local detection is deliberately based on
        :class:`AppPaths`, rather than on BrainGlobe's process-global default
        cache. ``local_only`` never calls network-aware catalog code.
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
            if name not in SUPPORTED_ATLAS_KEYS:
                continue
            self._validate_atlas_name(name)
            latest_version = str(raw_version).strip()
            if not latest_version:
                raise BrainGlobeContractError(
                    f"BrainGlobe catalog returned an empty version for {name!r}"
                )
            self._validate_package_version(latest_version)
            if latest_version not in _SUPPORTED_ATLAS_PACKAGE_VERSIONS[name]:
                continue
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
        """Load the official catalog without leaving uncancellable work behind."""

        injected_loader = self._runtime.catalog_loader
        if injected_loader is not None:
            # Private dependency-injection seam for deterministic unit fakes.
            # Production runtimes always use the bounded transport below.
            self._raise_if_catalog_cancelled(cancel)
            result = injected_loader()
            self._raise_if_catalog_cancelled(cancel)
            return result
        return self._load_official_catalog(cancel=cancel)

    def _load_official_catalog(
        self,
        *,
        cancel: CancellationCheck | None,
    ) -> Mapping[str, object]:
        """Fetch, validate, and atomically cache BrainGlobe's official catalog."""

        try:
            payload = self._fetch_official_catalog(cancel=cancel)
            available = self._parse_catalog(payload, source=_OFFICIAL_CATALOG_URL)
        except AtlasDownloadCancelledError:
            raise
        except AtlasAdapterError as fetch_error:
            self._raise_if_catalog_cancelled(cancel)
            try:
                cached = self._read_cached_catalog()
            except FileNotFoundError:
                raise FileNotFoundError(
                    "the official BrainGlobe catalog is unavailable and no cached "
                    "last_versions.conf exists"
                ) from fetch_error
            self._raise_if_catalog_cancelled(cancel)
            return cached

        self._raise_if_catalog_cancelled(cancel)
        try:
            self._write_catalog_cache_atomically(payload)
        except OSError:
            # A valid live response remains usable when a read-only filesystem
            # prevents refreshing the optional fallback cache.
            pass
        self._raise_if_catalog_cancelled(cancel)
        return available

    def _fetch_official_catalog(
        self,
        *,
        cancel: CancellationCheck | None,
    ) -> bytes:
        """Read a size-limited response with socket and wall-clock bounds."""

        deadline = time.monotonic() + _CATALOG_TOTAL_TIMEOUT_SECONDS
        self._raise_if_catalog_cancelled(cancel)
        request = Request(
            _OFFICIAL_CATALOG_URL,
            headers={"Accept": "text/plain", "User-Agent": "mouse-brain-planner/1"},
            method="GET",
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AtlasAdapterError("BrainGlobe atlas catalog deadline expired before connection")
        socket_timeout = min(_CATALOG_SOCKET_TIMEOUT_SECONDS, remaining)

        try:
            with urlopen(request, timeout=socket_timeout) as response:
                status = getattr(response, "status", 200)
                if not isinstance(status, int) or status < 200 or status >= 300:
                    raise AtlasAdapterError(
                        f"BrainGlobe atlas catalog returned HTTP status {status!r}"
                    )
                chunks: list[bytes] = []
                total = 0
                while True:
                    self._raise_if_catalog_cancelled(cancel)
                    if time.monotonic() >= deadline:
                        raise AtlasAdapterError(
                            "BrainGlobe atlas catalog exceeded the "
                            f"{_CATALOG_TOTAL_TIMEOUT_SECONDS:g}-second deadline"
                        )
                    read_size = min(
                        _CATALOG_READ_CHUNK_BYTES,
                        _CATALOG_MAX_BYTES - total + 1,
                    )
                    chunk = response.read(read_size)
                    self._raise_if_catalog_cancelled(cancel)
                    if not isinstance(chunk, bytes):
                        raise BrainGlobeContractError(
                            "BrainGlobe atlas catalog response was not bytes"
                        )
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _CATALOG_MAX_BYTES:
                        raise BrainGlobeContractError(
                            f"BrainGlobe atlas catalog exceeded the {_CATALOG_MAX_BYTES}-byte limit"
                        )
                    chunks.append(chunk)
        except AtlasAdapterError:
            raise
        except (HTTPException, URLError, TimeoutError, OSError) as error:
            raise AtlasAdapterError(
                "could not fetch the official BrainGlobe atlas catalog"
            ) from error

        if time.monotonic() >= deadline:
            raise AtlasAdapterError(
                "BrainGlobe atlas catalog exceeded the "
                f"{_CATALOG_TOTAL_TIMEOUT_SECONDS:g}-second deadline"
            )
        return b"".join(chunks)

    def _read_cached_catalog(self) -> Mapping[str, object]:
        cache_path = self.paths.atlas_cache / "last_versions.conf"
        if cache_path.is_symlink() or not cache_path.is_file():
            raise FileNotFoundError(cache_path)
        with cache_path.open("rb") as stream:
            payload = stream.read(_CATALOG_MAX_BYTES + 1)
        if len(payload) > _CATALOG_MAX_BYTES:
            raise BrainGlobeContractError(
                f"cached BrainGlobe atlas catalog exceeds {_CATALOG_MAX_BYTES} bytes"
            )
        return self._parse_catalog(payload, source=str(cache_path))

    def _write_catalog_cache_atomically(self, payload: bytes) -> None:
        cache_path = self.paths.atlas_cache / "last_versions.conf"
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=cache_path.parent,
                prefix=".last_versions-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(cache_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _parse_catalog(payload: bytes, *, source: str) -> Mapping[str, object]:
        try:
            text = payload.decode("utf-8")
            parsed = configparser.ConfigParser(interpolation=None, strict=True)
            parsed.read_string(text, source=source)
        except (UnicodeDecodeError, configparser.Error) as error:
            raise BrainGlobeContractError(
                f"BrainGlobe atlas catalog is not valid UTF-8 INI data: {source}"
            ) from error
        if not parsed.has_section("atlases"):
            raise BrainGlobeContractError(
                f"BrainGlobe atlas catalog has no [atlases] section: {source}"
            )
        available = dict(parsed.items("atlases"))
        if not available:
            raise BrainGlobeContractError(f"BrainGlobe atlas catalog is empty: {source}")
        return available

    @staticmethod
    def _raise_if_catalog_cancelled(cancel: CancellationCheck | None) -> None:
        if cancel is not None and cancel():
            raise AtlasDownloadCancelledError("atlas catalog request cancelled")

    def is_cached(self, atlas_name: str, package_version: str | None = None) -> bool:
        """Return whether the application cache contains the requested package.

        This check is local-only and supports catalog display and diagnostics.
        The authoritative download policy is enforced atomically by
        :meth:`open`.
        """

        self._validate_supported_atlas(atlas_name)
        versions = self._local_versions().get(atlas_name, [])
        if package_version is None:
            return bool(versions)
        self._validate_supported_package_version(atlas_name, package_version)
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

        self._validate_supported_atlas(atlas_name)
        if package_version is not None:
            self._validate_supported_package_version(atlas_name, package_version)
        if cancel is not None and cancel():
            raise AtlasDownloadCancelledError(f"atlas acquisition cancelled: {atlas_name}")

        cached_root = self._cached_root(
            atlas_name,
            package_version=package_version,
            required=not allow_download,
        )
        if cached_root is not None:
            # The low-level Atlas reader performs no catalog lookup, download,
            # repair, or cache deletion.  This is the only safe implementation
            # of a repository-level no-download guarantee.
            upstream_atlas = self._runtime.cached_atlas_factory(cached_root)
        else:
            if package_version is None:
                package_version = self._remote_package_version(
                    atlas_name,
                    cancel=cancel,
                )
            upstream_atlas = self._acquire_exact_package(
                atlas_name,
                package_version=package_version,
                progress=progress,
                cancel=cancel,
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

    def _remote_package_version(
        self,
        atlas_name: str,
        *,
        cancel: CancellationCheck | None,
    ) -> str:
        records = self.list_atlases(cancel=cancel)
        for record in records:
            if record.name == atlas_name:
                return record.latest_version
        raise AtlasAdapterError(
            f"supported atlas {atlas_name!r} is absent from the BrainGlobe catalog"
        )

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
            if not self._is_valid_package(
                staged_root,
                atlas_name=atlas_name,
                package_version=package_version,
            ):
                raise BrainGlobeContractError(
                    f"BrainGlobe staged an invalid atlas package: {staged_root}"
                )
            if cancel is not None and cancel():
                raise AtlasDownloadCancelledError(f"atlas acquisition cancelled: {atlas_name}")

            target = self.paths.atlas_cache / f"{atlas_name}_v{package_version}"
            self._promote_validated_package(
                staged_root,
                target=target,
                atlas_name=atlas_name,
                package_version=package_version,
            )

        return self._runtime.cached_atlas_factory(target.resolve())

    def _promote_validated_package(
        self,
        staged_root: Path,
        *,
        target: Path,
        atlas_name: str,
        package_version: str,
    ) -> None:
        """Promote staging while preserving invalid targets in quarantine."""

        for _attempt in range(3):
            if os.path.lexists(target):
                if self._is_valid_package(
                    target,
                    atlas_name=atlas_name,
                    package_version=package_version,
                ):
                    return
                self._quarantine_invalid_target(target)
            try:
                staged_root.rename(target)
            except OSError:
                if os.path.lexists(target):
                    continue
                raise
            if not self._is_valid_package(
                target,
                atlas_name=atlas_name,
                package_version=package_version,
            ):
                quarantined = self._quarantine_invalid_target(target)
                raise BrainGlobeContractError(
                    "promoted atlas package failed validation and was quarantined at "
                    f"{quarantined.resolve()}"
                )
            return
        raise BrainGlobeContractError(
            f"could not promote atlas package after concurrent cache changes: {target}"
        )

    def _quarantine_invalid_target(self, target: Path) -> Path:
        quarantine = self.paths.atlas_cache / "quarantine"
        if os.path.lexists(quarantine):
            if quarantine.is_symlink() or not quarantine.is_dir():
                raise BrainGlobeContractError(
                    f"atlas quarantine path is not an app-owned directory: {quarantine}"
                )
        else:
            quarantine.mkdir()
        quarantine_resolved = quarantine.resolve()
        try:
            quarantine_resolved.relative_to(self.paths.atlas_cache.resolve())
        except ValueError as error:
            raise BrainGlobeContractError(
                f"atlas quarantine escapes the application cache: {quarantine_resolved}"
            ) from error

        base_name = f"{target.name}.invalid-{time.time_ns()}"
        destination = quarantine / base_name
        suffix = 0
        while os.path.lexists(destination):
            suffix += 1
            destination = quarantine / f"{base_name}-{suffix}"
        target.rename(destination)
        return destination

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
            match = _LOCAL_ATLAS_PATTERN.fullmatch(candidate.name)
            if match is None:
                continue
            name = match.group("name")
            if name not in SUPPORTED_ATLAS_KEYS:
                continue
            version = match.group("version")
            if self._is_valid_package(
                candidate,
                atlas_name=name,
                package_version=version,
            ):
                versions.setdefault(name, []).append(version)
        return versions

    @classmethod
    def _is_valid_package(
        cls,
        candidate: Path,
        *,
        atlas_name: str,
        package_version: str,
    ) -> bool:
        """Validate package identity and cheap JSON/TIFF structure without array loads."""

        try:
            cls._validate_package(
                candidate,
                atlas_name=atlas_name,
                package_version=package_version,
            )
        except (AtlasAdapterError, OSError, TypeError, ValueError, tifffile.TiffFileError):
            return False
        return True

    @classmethod
    def _validate_package(
        cls,
        candidate: Path,
        *,
        atlas_name: str,
        package_version: str,
    ) -> None:
        cls._validate_supported_atlas(atlas_name)
        cls._validate_supported_package_version(atlas_name, package_version)
        if not candidate.is_dir() or candidate.is_symlink():
            raise BrainGlobeContractError(f"atlas package is not a regular directory: {candidate}")
        if candidate.name != f"{atlas_name}_v{package_version}":
            raise BrainGlobeContractError(
                f"atlas package directory has the wrong identity: {candidate.name!r}"
            )
        for filename in _REQUIRED_PACKAGE_FILES:
            path = candidate / filename
            if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
                raise BrainGlobeContractError(
                    f"atlas package file is missing, empty, or non-regular: {path}"
                )

        metadata = cls._read_json_mapping(candidate / "metadata.json", description="metadata")
        if _required_text(metadata, "version") != package_version:
            raise BrainGlobeContractError("atlas metadata version disagrees with its directory")
        if _required_text(metadata, "name") != "allen_mouse":
            raise BrainGlobeContractError("supported atlas metadata name must be 'allen_mouse'")
        if _required_text(metadata, "species").casefold() != "mus musculus":
            raise BrainGlobeContractError("supported atlas species must be Mus musculus")
        if _required_text(metadata, "orientation").lower() != "asr":
            raise BrainGlobeContractError("supported atlas orientation must be ASR")
        shape = _shape_triplet(metadata.get("shape"), field="metadata.shape")
        if shape != _SUPPORTED_ATLAS_SHAPE_VOXELS[atlas_name]:
            raise BrainGlobeContractError(
                f"atlas shape {shape} disagrees with reviewed key {atlas_name!r}"
            )
        resolution = _resolution_triplet(
            metadata.get("resolution"),
            field="metadata.resolution",
        )
        if resolution != _SUPPORTED_ATLAS_RESOLUTION_UM[atlas_name]:
            raise BrainGlobeContractError(
                f"atlas resolution {resolution} disagrees with reviewed key {atlas_name!r}"
            )
        _citation_text(metadata.get("citation"))
        _first_required_text(metadata, "atlas_link", "source_url")
        if metadata.get("symmetric") is not True:
            raise BrainGlobeContractError("supported Allen mouse atlas must be symmetric")

        reference_shape, reference_dtype = cls._tiff_header(candidate / "reference.tiff")
        annotation_shape, annotation_dtype = cls._tiff_header(candidate / "annotation.tiff")
        if reference_shape != shape or annotation_shape != shape:
            raise BrainGlobeContractError(
                "atlas TIFF shapes disagree with metadata: "
                f"metadata={shape}, reference={reference_shape}, annotation={annotation_shape}"
            )
        if reference_dtype != np.dtype(np.uint16):
            raise BrainGlobeContractError("reviewed Allen reference TIFF must be uint16")
        if annotation_dtype != np.dtype(np.uint32):
            raise BrainGlobeContractError("reviewed Allen annotation TIFF must be uint32")

        raw_structures = cls._read_json(candidate / "structures.json", description="structures")
        if not isinstance(raw_structures, list) or not all(
            isinstance(structure, Mapping) for structure in raw_structures
        ):
            raise BrainGlobeContractError("atlas structures must be a list of mappings")
        structures = cast(Sequence[Mapping[str, object]], raw_structures)
        regions = _normalize_regions(structures)
        region_ids = {region.structure_id for region in regions}
        if len(region_ids) != len(regions) or len({region.acronym for region in regions}) != len(
            regions
        ):
            raise BrainGlobeContractError("atlas structures contain duplicate IDs or acronyms")
        if any(
            ancestor not in region_ids
            for region in regions
            for ancestor in region.structure_id_path
        ):
            raise BrainGlobeContractError("atlas hierarchy references an unknown structure ID")

    @staticmethod
    def _read_json(path: Path, *, description: str) -> object:
        try:
            with path.open(encoding="utf-8") as stream:
                return json.load(stream)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise BrainGlobeContractError(
                f"atlas {description} JSON is not parseable: {path}"
            ) from error

    @classmethod
    def _read_json_mapping(cls, path: Path, *, description: str) -> Mapping[str, object]:
        value = cls._read_json(path, description=description)
        if not isinstance(value, Mapping):
            raise BrainGlobeContractError(f"atlas {description} must be a JSON object")
        return cast(Mapping[str, object], value)

    @staticmethod
    def _tiff_header(path: Path) -> tuple[tuple[int, ...], np.dtype[np.generic]]:
        with tifffile.TiffFile(path) as tiff:
            if len(tiff.series) != 1:
                raise BrainGlobeContractError(f"atlas TIFF must have one image series: {path}")
            series = tiff.series[0]
            return tuple(int(value) for value in series.shape), np.dtype(series.dtype)

    @staticmethod
    def _validate_atlas_name(atlas_name: str) -> None:
        if not _ATLAS_NAME_PATTERN.fullmatch(atlas_name):
            raise ValueError(
                "atlas name must start with an ASCII letter or digit and contain only "
                "letters, digits, underscores, periods, or hyphens"
            )

    @classmethod
    def _validate_supported_atlas(cls, atlas_name: str) -> None:
        cls._validate_atlas_name(atlas_name)
        if atlas_name not in SUPPORTED_ATLAS_KEYS:
            supported = ", ".join(sorted(SUPPORTED_ATLAS_KEYS))
            raise BrainGlobeContractError(
                f"atlas {atlas_name!r} has not been reviewed; supported atlases: {supported}"
            )

    @classmethod
    def _validate_supported_package_version(
        cls,
        atlas_name: str,
        package_version: str,
    ) -> None:
        cls._validate_package_version(package_version)
        if package_version not in _SUPPORTED_ATLAS_PACKAGE_VERSIONS[atlas_name]:
            reviewed = ", ".join(sorted(_SUPPORTED_ATLAS_PACKAGE_VERSIONS[atlas_name]))
            raise BrainGlobeContractError(
                f"atlas {atlas_name!r} package v{package_version} has not been reviewed; "
                f"reviewed versions: {reviewed}"
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
        _validate_hemisphere_constants(atlas)
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
    if atlas_key not in SUPPORTED_ATLAS_KEYS:
        raise BrainGlobeContractError(f"atlas {atlas_key!r} has not been reviewed")
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
    if shape != _SUPPORTED_ATLAS_SHAPE_VOXELS[atlas_key]:
        raise BrainGlobeContractError(
            f"BrainGlobe shape {shape} disagrees with reviewed key {atlas_key!r}"
        )

    resolution = _resolution_triplet(atlas.resolution, field="resolution")
    metadata_resolution = _resolution_triplet(raw.get("resolution"), field="metadata.resolution")
    if resolution != metadata_resolution:
        raise BrainGlobeContractError(
            "BrainGlobe resolution property "
            f"{resolution} disagrees with metadata {metadata_resolution}"
        )
    if resolution != _SUPPORTED_ATLAS_RESOLUTION_UM[atlas_key]:
        raise BrainGlobeContractError(
            f"BrainGlobe resolution {resolution} disagrees with reviewed key {atlas_key!r}"
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
    if not symmetric:
        raise BrainGlobeContractError(
            "stable adapter requires a reviewed symmetric Allen mouse atlas"
        )
    midline_ml_um = float(shape[2] * resolution[2]) / 2.0

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
        midline_ml_um=midline_ml_um,
        axes=axes,
    )


def _validate_hemisphere_constants(atlas: _AtlasLike) -> None:
    """Assert the pinned scalar hemisphere labels without opening the label volume."""

    observed = (atlas.left_hemisphere_value, atlas.right_hemisphere_value)
    if any(isinstance(value, bool) or not isinstance(value, Integral) for value in observed):
        raise BrainGlobeContractError(
            "BrainGlobe hemisphere labels must be integral scalar values; "
            f"got left={observed[0]!r}, right={observed[1]!r}"
        )
    normalized = (int(observed[0]), int(observed[1]))
    if normalized != (1, 2):
        raise BrainGlobeContractError(
            "unsupported BrainGlobe hemisphere labels; expected left=1 and right=2, "
            f"got left={normalized[0]} and right={normalized[1]}"
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
