"""PyVista/VTK scene ownership for atlas geometry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol, cast

import numpy as np
import pyvista as pv

from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import (
    BrainGlobePhysicalPoint,
    SurgeryWorldPoint,
)

MeshSource = str | Path | pv.DataSet
CancellationCheck = Callable[[], None]


@dataclass(frozen=True, slots=True)
class PreparedWorldMesh:
    """Immutable handoff for geometry already mapped into renderer world space.

    The VTK dataset itself is treated as read-only after construction.  Atlas
    metadata and the exact physical anchor travel with it so a GUI scene cannot
    silently render geometry prepared for another atlas package or origin.
    """

    frame_id: ClassVar[Literal["SURGERY_WORLD_RAS_UM"]] = "SURGERY_WORLD_RAS_UM"

    mesh: pv.PolyData
    atlas_metadata: AtlasMetadata
    renderer_anchor: BrainGlobePhysicalPoint

    def __post_init__(self) -> None:
        if not isinstance(self.mesh, pv.PolyData):
            raise TypeError("prepared world mesh must contain PyVista PolyData")
        # This validates the anchor frame, atlas key/version, finite values, and
        # half-open atlas bounds even if a caller bypassed normal worker setup.
        BrainGlobeAtlasSpace(self.atlas_metadata).world_transform_matrix(self.renderer_anchor)

    def validate_for(
        self,
        space: BrainGlobeAtlasSpace,
        anchor: BrainGlobePhysicalPoint,
    ) -> pv.PolyData:
        """Fail closed unless this prepared geometry matches the target scene."""

        expected_metadata = space.metadata.model_dump(exclude={"cache_path"})
        actual_metadata = self.atlas_metadata.model_dump(exclude={"cache_path"})
        if actual_metadata != expected_metadata:
            raise ValueError(
                "prepared mesh atlas identity does not match the target scene: "
                f"prepared {self.atlas_metadata.atlas_key} "
                f"v{self.atlas_metadata.atlas_package_version}, target "
                f"{space.metadata.atlas_key} v{space.metadata.atlas_package_version}"
            )
        # Validate both points against the target space before comparing their
        # exact persisted values.  An anchor difference changes every vertex.
        space.world_transform_matrix(anchor)
        space.world_transform_matrix(self.renderer_anchor)
        if self.renderer_anchor != anchor:
            raise ValueError(
                "prepared mesh renderer anchor does not match the target scene: "
                f"prepared {self.renderer_anchor.as_tuple()}, target {anchor.as_tuple()}"
            )
        return self.mesh


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
    space: BrainGlobeAtlasSpace,
    anchor: BrainGlobePhysicalPoint,
    *,
    check_cancelled: CancellationCheck | None = None,
) -> PreparedWorldMesh:
    """Prepare ASR geometry completely before it reaches the GUI thread."""

    def cancellation_point() -> None:
        if check_cancelled is not None:
            check_cancelled()

    # Each potentially expensive stage is bracketed so project replacement or
    # application shutdown suppresses delivery at the earliest safe boundary.
    cancellation_point()
    dataset = pv.read(str(source)) if isinstance(source, (str, Path)) else source.copy(deep=True)
    cancellation_point()
    surface = dataset if isinstance(dataset, pv.PolyData) else dataset.extract_surface()
    cancellation_point()
    transform = space.world_transform_matrix(anchor)
    transformed = surface.transform(transform, inplace=False)
    cancellation_point()
    if np.linalg.det(transform[:3, :3]) < 0:
        transformed = transformed.flip_faces(inplace=False)
    cancellation_point()
    world_mesh = cast(
        pv.PolyData,
        transformed.compute_normals(
            cell_normals=True,
            point_normals=True,
            consistent_normals=True,
            inplace=False,
        ),
    )
    cancellation_point()
    return PreparedWorldMesh(
        mesh=world_mesh,
        atlas_metadata=space.metadata,
        renderer_anchor=anchor,
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
        # Constructor validation makes a malformed or cross-atlas scene fail
        # before any native VTK actor is allocated.
        self.space.world_transform_matrix(self.anchor)
        self._region_sources: dict[int, PreparedWorldMesh] = {}
        self._region_world_meshes: dict[int, pv.PolyData] = {}
        self._root_actor_key: str | None = None
        self._region_actor_keys: dict[int, str] = {}
        self._actor_region_ids: dict[str, int] = {}
        self._pickable_actor_keys: set[str] = set()
        self._disposed = False

    def load_root_mesh(self, source: PreparedWorldMesh) -> None:
        """Create the atlas-root actor from worker-prepared world geometry."""

        mesh = source.validate_for(self.space, self.anchor)
        actor = self.plotter.add_mesh(
            mesh,
            name="atlas-root",
            color=(0.82, 0.86, 0.90),
            opacity=0.18,
            smooth_shading=True,
            pickable=True,
            reset_camera=True,
            render=False,
        )
        self._root_actor_key = _vtk_object_identity(actor)
        self._pickable_actor_keys.add(self._root_actor_key)
        self.plotter.add_axes(
            xlabel="ML Right (+) / Left (-)",
            ylabel="AP Anterior (+) / Posterior (-)",
            zlabel="DV Superior/Dorsal (+) / Inferior/Ventral (-)",
        )
        self.plotter.set_background((0.055, 0.065, 0.085))
        self.plotter.render()

    def set_region(
        self,
        structure_id: int,
        source: PreparedWorldMesh,
        *,
        rgb: tuple[int, int, int],
        opacity: float,
        visible: bool,
    ) -> None:
        """Add, update, or hide one lazily requested region mesh."""

        name = f"region-{structure_id}"
        # Validate before touching actor or cache state.  A late payload from a
        # replaced atlas therefore cannot partially mutate the current scene.
        mesh = source.validate_for(self.space, self.anchor)
        previous_actor_key = self._region_actor_keys.pop(structure_id, None)
        if previous_actor_key is not None:
            self._pickable_actor_keys.discard(previous_actor_key)
            self._actor_region_ids.pop(previous_actor_key, None)
        if not visible:
            self._region_sources.pop(structure_id, None)
            self._region_world_meshes.pop(structure_id, None)
            self.plotter.remove_actor(name, reset_camera=False, render=False)
            self.plotter.render()
            return
        self._region_sources[structure_id] = source
        self._region_world_meshes[structure_id] = mesh
        color = tuple(component / 255.0 for component in rgb)
        actor = self.plotter.add_mesh(
            mesh,
            name=name,
            color=color,
            opacity=opacity,
            smooth_shading=True,
            pickable=True,
            reset_camera=False,
            render=False,
        )
        actor_key = _vtk_object_identity(actor)
        self._region_actor_keys[structure_id] = actor_key
        self._actor_region_ids[actor_key] = structure_id
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
                render=False,
            )
        self.plotter.render()

    def enable_physical_picking(
        self,
        callback: Callable[[BrainGlobePhysicalPoint], None],
        *,
        region_callback: Callable[[int, BrainGlobePhysicalPoint], None] | None = None,
    ) -> None:
        """Map renderer picks back to physical space and preserve actor identity."""

        def picked(
            world_values: tuple[float, float, float],
            picker: PickerProtocol,
        ) -> None:
            actor = picker.GetActor()
            if actor is None:
                return
            actor_key = _vtk_object_identity(actor)
            if actor_key not in self._pickable_actor_keys:
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
            region_id = self._actor_region_ids.get(actor_key)
            if region_id is not None and region_callback is not None:
                region_callback(region_id, physical)
            else:
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
        self.plotter.reset_camera(render=False)
        self.plotter.render()

    def reset_camera(self) -> None:
        """Reset the active camera around visible actors."""

        self.plotter.reset_camera(render=False)
        self.plotter.render()

    def center_region(self, structure_id: int) -> bool:
        """Frame one currently visible region and report whether it was available."""

        mesh = self._region_world_meshes.get(structure_id)
        if mesh is None or structure_id not in self._region_actor_keys:
            return False
        self.plotter.reset_camera(bounds=mesh.bounds, render=False)
        self.plotter.render()
        return True

    def dispose(self) -> None:
        """Release renderer-owned VTK resources exactly once."""

        if self._disposed:
            return
        self._disposed = True
        self._region_sources.clear()
        self._region_world_meshes.clear()
        self._region_actor_keys.clear()
        self._actor_region_ids.clear()
        self._pickable_actor_keys.clear()
        self._root_actor_key = None
        self.plotter.clear()
        self.plotter.close()
