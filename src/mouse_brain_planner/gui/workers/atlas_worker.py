"""Cancellable atlas catalog and loading workers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Protocol

import pyvista as pv
from PySide6.QtCore import QObject, Signal, Slot

from mouse_brain_planner.atlas.brainglobe_adapter import (
    AtlasCatalogRecord,
    AtlasDownloadCancelledError,
    LoadedAtlas,
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


@dataclass(frozen=True, slots=True)
class LoadedAtlasPayload:
    """Atlas data prepared off the GUI thread without full-volume copies."""

    atlas: LoadedAtlas
    root_mesh: pv.DataSet


@dataclass(frozen=True, slots=True)
class RegionMeshPayload:
    """One lazily parsed atlas-region mesh."""

    structure_id: int
    mesh: pv.DataSet


class AtlasCatalogWorker(QObject):
    """Fetch the BrainGlobe catalog without blocking the Qt event loop."""

    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        repository: AtlasRepositoryProtocol,
        *,
        local_only: bool = False,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.local_only = local_only
        self._cancel_requested = Event()

    def request_cancel(self) -> None:
        """Request cancellation and suppress any later result signals."""

        self._cancel_requested.set()

    @Slot()
    def run(self) -> None:
        """Fetch catalog records and report a user-readable error."""

        try:
            records = self.repository.list_atlases(
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
    succeeded = Signal(object)
    cancelled = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        repository: AtlasRepositoryProtocol,
        atlas_name: str,
        *,
        preload_volumes: bool = True,
        allow_download: bool = True,
        package_version: str | None = None,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.atlas_name = atlas_name
        self.preload_volumes = preload_volumes
        self.allow_download = allow_download
        self.package_version = package_version
        self._cancel_requested = Event()

    def request_cancel(self) -> None:
        """Request cancellation from any thread using a thread-safe event."""

        self._cancel_requested.set()

    @Slot()
    def run(self) -> None:
        """Open, validate, and preload atlas data without copying arrays."""

        try:
            loaded = self.repository.open(
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
            # File parsing belongs in the worker.  The GUI thread receives a
            # complete, non-rendering VTK dataset and only creates actors.
            root_mesh = pv.read(str(loaded.root_mesh_file()))
            self._raise_if_cancelled()
        except AtlasDownloadCancelledError as error:
            self.cancelled.emit(str(error))
        except Exception as error:  # Qt boundary converts failures into a signal.
            self.failed.emit(f"{type(error).__name__}: {error}")
        else:
            self.succeeded.emit(LoadedAtlasPayload(atlas=loaded, root_mesh=root_mesh))
        finally:
            self.finished.emit()

    def _report_progress(self, completed: int, total: int) -> None:
        self._raise_if_cancelled()
        self.progress.emit(completed, total)

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested.is_set():
            raise AtlasDownloadCancelledError(f"atlas acquisition cancelled: {self.atlas_name}")


class RegionMeshWorker(QObject):
    """Parse one validated region mesh away from the GUI thread."""

    succeeded = Signal(object)
    failed = Signal(int, str)
    finished = Signal()

    def __init__(self, atlas: LoadedAtlas, structure_id: int) -> None:
        super().__init__()
        self.atlas = atlas
        self.structure_id = structure_id

    @Slot()
    def run(self) -> None:
        """Read one atlas-owned mesh and report it with its structure ID."""

        try:
            mesh_path = self.atlas.mesh_file_for_region(self.structure_id)
            mesh = pv.read(str(mesh_path))
        except Exception as error:  # Qt boundary converts failures into a signal.
            self.failed.emit(self.structure_id, f"{type(error).__name__}: {error}")
        else:
            self.succeeded.emit(RegionMeshPayload(structure_id=self.structure_id, mesh=mesh))
        finally:
            self.finished.emit()
