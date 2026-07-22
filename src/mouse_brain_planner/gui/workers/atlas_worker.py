"""Cancellable atlas catalog and loading workers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Protocol, cast

from PySide6.QtCore import QObject, Signal, Slot

from mouse_brain_planner.atlas.brainglobe_adapter import (
    AtlasCatalogRecord,
    AtlasDownloadCancelledError,
    LoadedAtlas,
)
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.coordinate_models import (
    BrainGlobePhysicalPoint,
    BrainGlobeVoxelIndex,
)
from mouse_brain_planner.rendering.sagittal_cache import SagittalVolumeCache
from mouse_brain_planner.rendering.scene_controller import (
    PreparedWorldMesh,
    prepare_world_mesh,
)


class AtlasRepositoryProtocol(Protocol):
    """Repository operations used by workers."""

    def list_atlases(
        self,
        *,
        local_only: bool = False,
        cancel: Callable[[], bool] | None = None,
    ) -> list[AtlasCatalogRecord]: ...

    def is_cached(self, atlas_name: str, package_version: str | None = None) -> bool: ...

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> LoadedAtlas: ...


AtlasRepositorySource = AtlasRepositoryProtocol | Callable[[], AtlasRepositoryProtocol]
ATLAS_SURFACE_STAGE_TEXT = "Preparing exact 3D brain surface…"


def _resolve_repository(
    source: AtlasRepositorySource,
    *,
    required_method: str,
) -> AtlasRepositoryProtocol:
    """Resolve a repository factory only after the worker thread has started."""

    if not isinstance(source, type) and hasattr(source, required_method):
        return cast(AtlasRepositoryProtocol, source)
    if not callable(source):
        raise TypeError(f"repository does not provide {required_method}()")
    repository = source()
    if not hasattr(repository, required_method):
        raise TypeError(f"repository factory result does not provide {required_method}()")
    return repository


@dataclass(frozen=True, slots=True)
class LoadedAtlasPayload:
    """Atlas data prepared off the GUI thread without full-volume copies."""

    atlas: LoadedAtlas
    root_mesh: PreparedWorldMesh
    sagittal_cache: SagittalVolumeCache | None = None


@dataclass(frozen=True, slots=True)
class RegionMeshPayload:
    """One lazily prepared atlas-region mesh in renderer world coordinates."""

    structure_id: int
    mesh: PreparedWorldMesh


def center_voxel_anchor(space: BrainGlobeAtlasSpace) -> BrainGlobePhysicalPoint:
    """Return the exact center of the atlas' discrete center voxel."""

    metadata = space.metadata
    return space.index_to_center(
        BrainGlobeVoxelIndex(
            atlas_key=metadata.atlas_key,
            atlas_version=metadata.atlas_package_version,
            ap=metadata.shape_voxels[0] // 2,
            dv=metadata.shape_voxels[1] // 2,
            ml=metadata.shape_voxels[2] // 2,
        )
    )


class AtlasCatalogWorker(QObject):
    """Fetch the BrainGlobe catalog without blocking the Qt event loop."""

    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        repository: AtlasRepositorySource,
        *,
        local_only: bool = False,
    ) -> None:
        super().__init__()
        self.repository_source = repository
        self.local_only = local_only
        self._cancel_requested = Event()

    def request_cancel(self) -> None:
        """Request cancellation and suppress any later result signals."""

        self._cancel_requested.set()

    @Slot()
    def run(self) -> None:
        """Fetch catalog records and report a user-readable error."""

        try:
            if self._cancel_requested.is_set():
                raise AtlasDownloadCancelledError("atlas catalog request cancelled")
            repository = _resolve_repository(
                self.repository_source,
                required_method="list_atlases",
            )
            if self._cancel_requested.is_set():
                raise AtlasDownloadCancelledError("atlas catalog request cancelled")
            records = repository.list_atlases(
                local_only=self.local_only,
                cancel=self._cancel_requested.is_set,
            )
        except AtlasDownloadCancelledError:
            pass
        except Exception as error:  # Qt boundary converts failures into a signal.
            if not self._cancel_requested.is_set():
                self.failed.emit(f"{type(error).__name__}: {error}")
        else:
            if not self._cancel_requested.is_set():
                self.succeeded.emit(records)
        finally:
            self.finished.emit()


class AtlasLoadWorker(QObject):
    """Acquire and preload one atlas outside the GUI thread."""

    progress = Signal(int, int)
    stage_changed = Signal(str)
    succeeded = Signal(object)
    cancelled = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        repository: AtlasRepositorySource,
        atlas_name: str,
        *,
        preload_volumes: bool = True,
        allow_download: bool = True,
        package_version: str | None = None,
        renderer_anchor: BrainGlobePhysicalPoint | None = None,
    ) -> None:
        super().__init__()
        self.repository_source = repository
        self.atlas_name = atlas_name
        self.preload_volumes = preload_volumes
        self.allow_download = allow_download
        self.package_version = package_version
        self.renderer_anchor = renderer_anchor
        self._cancel_requested = Event()

    def request_cancel(self) -> None:
        """Request cancellation from any thread using a thread-safe event."""

        self._cancel_requested.set()

    @Slot()
    def run(self) -> None:
        """Open, validate, and preload atlas data without copying arrays."""

        try:
            self._raise_if_cancelled()
            repository = _resolve_repository(
                self.repository_source,
                required_method="open",
            )
            self._raise_if_cancelled()
            loaded = repository.open(
                self.atlas_name,
                package_version=self.package_version,
                allow_download=self.allow_download,
                progress=self._report_progress,
                cancel=self._cancel_requested.is_set,
            )
            self._raise_if_cancelled()
            if self.preload_volumes:
                reference = loaded.reference
                self._raise_if_cancelled()
                annotation = loaded.annotation
                expected_shape = loaded.metadata.shape_voxels
                if reference.shape != expected_shape:
                    raise ValueError(
                        f"reference shape {reference.shape} does not match "
                        f"metadata {expected_shape}"
                    )
                if annotation.shape != expected_shape:
                    raise ValueError(
                        f"annotation shape {annotation.shape} does not match "
                        f"metadata {expected_shape}"
                    )
            self.stage_changed.emit(ATLAS_SURFACE_STAGE_TEXT)
            space = BrainGlobeAtlasSpace(loaded.metadata)
            renderer_anchor = self.renderer_anchor or center_voxel_anchor(space)
            # Parsing, ASR-to-world transformation, reflected-face repair, and
            # normals all belong in this worker. The GUI only creates actors.
            root_mesh = prepare_world_mesh(
                loaded.root_mesh_file(),
                space,
                renderer_anchor,
                check_cancelled=self._raise_if_cancelled,
            )
        except AtlasDownloadCancelledError as error:
            self.cancelled.emit(str(error))
        except Exception as error:  # Qt boundary converts failures into a signal.
            self.failed.emit(f"{type(error).__name__}: {error}")
        else:
            self.succeeded.emit(
                LoadedAtlasPayload(
                    atlas=loaded,
                    root_mesh=root_mesh,
                )
            )
        finally:
            self.finished.emit()

    def _report_progress(self, completed: int, total: int) -> None:
        self._raise_if_cancelled()
        self.progress.emit(completed, total)

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested.is_set():
            raise AtlasDownloadCancelledError(f"atlas acquisition cancelled: {self.atlas_name}")


class RegionMeshWorker(QObject):
    """Prepare one validated region mesh away from the GUI thread."""

    succeeded = Signal(object)
    failed = Signal(int, str)
    finished = Signal()

    def __init__(
        self,
        atlas: LoadedAtlas,
        structure_id: int,
        *,
        renderer_anchor: BrainGlobePhysicalPoint,
    ) -> None:
        super().__init__()
        self.atlas = atlas
        self.structure_id = structure_id
        self.renderer_anchor = renderer_anchor
        self._cancel_requested = Event()

    def request_cancel(self) -> None:
        """Suppress mesh delivery after the owning project or atlas changes."""

        self._cancel_requested.set()

    @Slot()
    def run(self) -> None:
        """Read one atlas-owned mesh and report it with its structure ID."""

        try:
            self._raise_if_cancelled()
            mesh_path = self.atlas.mesh_file_for_region(self.structure_id)
            self._raise_if_cancelled()
            mesh = prepare_world_mesh(
                mesh_path,
                BrainGlobeAtlasSpace(self.atlas.metadata),
                self.renderer_anchor,
                check_cancelled=self._raise_if_cancelled,
            )
        except AtlasDownloadCancelledError:
            pass
        except Exception as error:  # Qt boundary converts failures into a signal.
            if not self._cancel_requested.is_set():
                self.failed.emit(self.structure_id, f"{type(error).__name__}: {error}")
        else:
            if not self._cancel_requested.is_set():
                self.succeeded.emit(RegionMeshPayload(structure_id=self.structure_id, mesh=mesh))
        finally:
            self.finished.emit()

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested.is_set():
            raise AtlasDownloadCancelledError(
                f"region mesh preparation cancelled: {self.structure_id}"
            )
