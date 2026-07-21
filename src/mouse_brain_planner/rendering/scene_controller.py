"""PyVista/VTK scene ownership for atlas geometry."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

import numpy as np
import pyvista as pv
from numpy.typing import NDArray

from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.coordinate_models import (
    BrainGlobePhysicalPoint,
    SurgeryWorldPoint,
)

MeshSource = str | Path | pv.DataSet


class PlotterProtocol(Protocol):
    """Small typed surface used from PyVista's dynamically wrapped plotter."""

    camera_position: object

    def add_mesh(self, *args: object, **kwargs: object) -> object: ...

    def add_axes(self, *args: object, **kwargs: object) -> object: ...

    def set_background(self, *args: object, **kwargs: object) -> object: ...

    def render(self) -> None: ...

    def remove_actor(self, *args: object, **kwargs: object) -> object: ...

    def enable_point_picking(self, *args: object, **kwargs: object) -> object: ...

    def reset_camera(self, *args: object, **kwargs: object) -> object: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...


class PickerProtocol(Protocol):
    """VTK picker surface needed to identify the actor behind a point."""

    def GetActor(self) -> object | None: ...  # noqa: N802 - VTK API


def _vtk_object_identity(value: object) -> str:
    """Return a stable key for Python wrappers around one VTK object."""

    memory_address = getattr(value, "memory_address", None)
    if isinstance(memory_address, str):
        return memory_address
    address_method = getattr(value, "GetAddressAsString", None)
    if callable(address_method):
        address = address_method("")
        if isinstance(address, str):
            return address
    return f"python:{id(value)}"


def prepare_world_mesh(
    source: MeshSource,
    transform: NDArray[np.float64],
) -> pv.PolyData:
    """Load/copy a mesh, transform ASR µm to world µm, and repair winding."""

    dataset = pv.read(str(source)) if isinstance(source, (str, Path)) else source.copy(deep=True)
    surface = dataset if isinstance(dataset, pv.PolyData) else dataset.extract_surface()
    transformed = surface.transform(transform, inplace=False)
    if np.linalg.det(transform[:3, :3]) < 0:
        transformed = transformed.flip_faces(inplace=False)
    return cast(
        pv.PolyData,
        transformed.compute_normals(
            cell_normals=True,
            point_normals=True,
            consistent_normals=True,
            inplace=False,
        ),
    )


class SceneController:
    """Own VTK objects for one 3D viewer and release them deterministically."""

    def __init__(
        self,
        plotter: PlotterProtocol,
        space: BrainGlobeAtlasSpace,
        anchor: BrainGlobePhysicalPoint,
    ) -> None:
        self.plotter = plotter
        self.space = space
        self.anchor = anchor
        self._region_sources: dict[int, MeshSource] = {}
        self._region_source_keys: dict[int, str | int] = {}
        self._region_world_meshes: dict[int, pv.PolyData] = {}
        self._root_actor_key: str | None = None
        self._region_actor_keys: dict[int, str] = {}
        self._pickable_actor_keys: set[str] = set()
        self._disposed = False

    def load_root_mesh(self, source: MeshSource) -> None:
        """Show the atlas root as a translucent anatomical shell."""

        mesh = prepare_world_mesh(source, self.space.world_transform_matrix(self.anchor))
        actor = self.plotter.add_mesh(
            mesh,
            name="atlas-root",
            color=(0.82, 0.86, 0.90),
            opacity=0.18,
            smooth_shading=True,
            pickable=True,
            reset_camera=True,
        )
        self._root_actor_key = _vtk_object_identity(actor)
        self._pickable_actor_keys.add(self._root_actor_key)
        self.plotter.add_axes(
            xlabel="ML right (+)",
            ylabel="AP anterior (+)",
            zlabel="DV dorsal (+)",
        )
        self.plotter.set_background((0.055, 0.065, 0.085))
        self.plotter.render()

    def set_region(
        self,
        structure_id: int,
        source: MeshSource,
        *,
        rgb: tuple[int, int, int],
        opacity: float,
        visible: bool,
    ) -> None:
        """Add, update, or hide one lazily requested region mesh."""

        name = f"region-{structure_id}"
        self._region_sources[structure_id] = source
        previous_actor_key = self._region_actor_keys.pop(structure_id, None)
        if previous_actor_key is not None:
            self._pickable_actor_keys.discard(previous_actor_key)
        if not visible:
            self.plotter.remove_actor(name, reset_camera=False, render=True)
            return
        source_key: str | int
        if isinstance(source, (str, Path)):
            source_key = str(Path(source).resolve())
        else:
            source_key = id(source)
        if self._region_source_keys.get(structure_id) != source_key:
            self._region_world_meshes[structure_id] = prepare_world_mesh(
                source,
                self.space.world_transform_matrix(self.anchor),
            )
            self._region_source_keys[structure_id] = source_key
        mesh = self._region_world_meshes[structure_id]
        color = tuple(component / 255.0 for component in rgb)
        actor = self.plotter.add_mesh(
            mesh,
            name=name,
            color=color,
            opacity=opacity,
            smooth_shading=True,
            pickable=True,
            reset_camera=False,
        )
        actor_key = _vtk_object_identity(actor)
        self._region_actor_keys[structure_id] = actor_key
        self._pickable_actor_keys.add(actor_key)
        self.plotter.render()

    def set_crosshair(self, point: BrainGlobePhysicalPoint) -> None:
        """Render a tri-axial physical crosshair at the linked cursor."""

        world = self.space.physical_to_world(point, self.anchor)
        center = np.asarray(world.as_tuple(), dtype=np.float64)
        half_length = max(self.space.metadata.extent_um) * 0.018
        colors = ((0.96, 0.35, 0.38), (0.30, 0.82, 0.55), (0.34, 0.62, 0.98))
        for axis, color in enumerate(colors):
            start = center.copy()
            end = center.copy()
            start[axis] -= half_length
            end[axis] += half_length
            self.plotter.add_mesh(
                pv.Line(start, end),
                name=f"crosshair-{axis}",
                color=color,
                line_width=2.0,
                pickable=False,
                reset_camera=False,
            )
        self.plotter.render()

    def enable_physical_picking(
        self,
        callback: Callable[[BrainGlobePhysicalPoint], None],
    ) -> None:
        """Map renderer picks back into checked BrainGlobe physical space."""

        def picked(
            world_values: tuple[float, float, float],
            picker: PickerProtocol,
        ) -> None:
            actor = picker.GetActor()
            if actor is None or _vtk_object_identity(actor) not in self._pickable_actor_keys:
                return
            try:
                world = SurgeryWorldPoint(
                    atlas_key=self.space.metadata.atlas_key,
                    atlas_version=self.space.metadata.atlas_package_version,
                    ml_right_um=float(world_values[0]),
                    ap_anterior_um=float(world_values[1]),
                    dv_dorsal_um=float(world_values[2]),
                )
                physical = self.space.world_to_physical(world, self.anchor)
            except (IndexError, TypeError, ValueError):
                # Root meshes may extend slightly beyond the half-open annotation
                # volume. An invalid surface pick is ignored at the VTK boundary.
                return
            callback(physical)

        self.plotter.enable_point_picking(
            callback=picked,
            left_clicking=True,
            show_message=False,
            show_point=False,
            use_picker=True,
            pickable_window=False,
        )

    def set_camera(self, preset: str) -> None:
        """Apply an anatomical camera preset in the right-handed world frame."""

        distance = max(self.space.metadata.extent_um) * 1.6
        positions: dict[str, tuple[float, float, float]] = {
            "anterior": (0.0, distance, 0.0),
            "posterior": (0.0, -distance, 0.0),
            "dorsal": (0.0, 0.0, distance),
            "ventral": (0.0, 0.0, -distance),
            "right": (distance, 0.0, 0.0),
            "left": (-distance, 0.0, 0.0),
        }
        if preset not in positions:
            raise ValueError(f"unknown anatomical camera preset: {preset}")
        view_up = (0.0, 0.0, 1.0) if preset not in {"dorsal", "ventral"} else (0.0, 1.0, 0.0)
        self.plotter.camera_position = [positions[preset], (0.0, 0.0, 0.0), view_up]
        self.plotter.reset_camera()
        self.plotter.render()

    def reset_camera(self) -> None:
        """Reset the active camera around visible actors."""

        self.plotter.reset_camera()
        self.plotter.render()

    def dispose(self) -> None:
        """Release renderer-owned VTK resources exactly once."""

        if self._disposed:
            return
        self._disposed = True
        self._region_sources.clear()
        self._region_source_keys.clear()
        self._region_world_meshes.clear()
        self._region_actor_keys.clear()
        self._pickable_actor_keys.clear()
        self._root_actor_key = None
        self.plotter.clear()
        self.plotter.close()
