"""Pure mesh-transform tests for the 3D renderer boundary."""

from __future__ import annotations

import numpy as np
import pyvista as pv
from tests.fixtures import make_allen_metadata_test_double

from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.rendering.scene_controller import SceneController, prepare_world_mesh


class FakeActor:
    """Stable actor identity for picker filtering tests."""

    def __init__(self, memory_address: str) -> None:
        self.memory_address = memory_address


class FakePicker:
    def __init__(self, actor: object | None) -> None:
        self.actor = actor

    def GetActor(self) -> object | None:  # noqa: N802 - VTK API
        return self.actor


class FakePlotter:
    """Minimal plotter that captures the point-picking callback."""

    def __init__(self) -> None:
        self.camera_position: object = None
        self.actor_count = 0
        self.picking_callback: object | None = None
        self.picking_kwargs: dict[str, object] = {}

    def add_mesh(self, *args: object, **kwargs: object) -> FakeActor:
        self.actor_count += 1
        return FakeActor(f"actor:{self.actor_count}")

    def add_axes(self, *args: object, **kwargs: object) -> object:
        return object()

    def set_background(self, *args: object, **kwargs: object) -> object:
        return object()

    def render(self) -> None:
        return None

    def remove_actor(self, *args: object, **kwargs: object) -> object:
        return object()

    def enable_point_picking(self, *args: object, **kwargs: object) -> object:
        self.picking_callback = kwargs["callback"]
        self.picking_kwargs = kwargs
        return object()

    def reset_camera(self, *args: object, **kwargs: object) -> object:
        return object()

    def clear(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_prepare_world_mesh_applies_reflection_and_repairs_faces() -> None:
    triangle = pv.PolyData(
        np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]]),
        np.array([3, 0, 1, 2]),
    )
    transform = np.array(
        [
            [0.0, 0.0, -1.0, 30.0],
            [-1.0, 0.0, 0.0, 20.0],
            [0.0, -1.0, 0.0, 10.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    transformed = prepare_world_mesh(triangle, transform)

    assert np.linalg.det(transform[:3, :3]) == -1.0
    np.testing.assert_allclose(
        transformed.points,
        np.array([[30.0, 20.0, 10.0], [30.0, 10.0, 10.0], [30.0, 20.0, 0.0]]),
    )
    assert transformed.n_cells == 1
    assert "Normals" in transformed.point_data


def test_physical_picking_is_actor_filtered_and_bounds_safe() -> None:
    metadata = make_allen_metadata_test_double(25)
    space = BrainGlobeAtlasSpace(metadata)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=metadata.extent_um[0] / 2,
        dv_um=metadata.extent_um[1] / 2,
        ml_um=metadata.extent_um[2] / 2,
    )
    plotter = FakePlotter()
    controller = SceneController(plotter, space, anchor)
    controller.load_root_mesh(pv.Sphere(radius=100.0))
    received: list[BrainGlobePhysicalPoint] = []

    controller.enable_physical_picking(received.append)

    assert plotter.picking_kwargs["use_picker"] is True
    assert callable(plotter.picking_callback)
    callback = plotter.picking_callback
    root_actor = FakeActor("actor:1")
    callback((0.0, 0.0, 0.0), FakePicker(root_actor))
    assert len(received) == 1
    assert received[0].as_tuple() == anchor.as_tuple()

    callback((0.0, 0.0, 0.0), FakePicker(FakeActor("unregistered")))
    callback((1e9, 1e9, 1e9), FakePicker(root_actor))
    callback((0.0, 0.0, 0.0), FakePicker(None))
    assert len(received) == 1
