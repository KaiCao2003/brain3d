"""Pure mesh-transform tests for the 3D renderer boundary."""

from __future__ import annotations

import numpy as np
import pytest
import pyvista as pv
from tests.fixtures import make_allen_metadata_test_double

from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.rendering.scene_controller import (
    SceneController,
    prepare_world_mesh,
)


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
        self.render_count = 0
        self.mesh_args: list[tuple[object, ...]] = []
        self.mesh_kwargs: list[dict[str, object]] = []
        self.axes_kwargs: list[dict[str, object]] = []
        self.removed_actors: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.reset_calls: list[dict[str, object]] = []
        self.picking_callback: object | None = None
        self.picking_kwargs: dict[str, object] = {}

    def add_mesh(self, *args: object, **kwargs: object) -> FakeActor:
        self.actor_count += 1
        self.mesh_args.append(args)
        self.mesh_kwargs.append(kwargs)
        return FakeActor(f"actor:{self.actor_count}")

    def add_axes(self, *args: object, **kwargs: object) -> object:
        self.axes_kwargs.append(kwargs)
        return object()

    def set_background(self, *args: object, **kwargs: object) -> object:
        return object()

    def render(self) -> None:
        self.render_count += 1

    def remove_actor(self, *args: object, **kwargs: object) -> object:
        self.removed_actors.append((args, kwargs))
        return object()

    def enable_point_picking(self, *args: object, **kwargs: object) -> object:
        self.picking_callback = kwargs["callback"]
        self.picking_kwargs = kwargs
        return object()

    def reset_camera(self, *args: object, **kwargs: object) -> object:
        del args
        self.reset_calls.append(kwargs)
        return object()

    def clear(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_prepare_world_mesh_applies_reflection_and_repairs_faces() -> None:
    metadata = make_allen_metadata_test_double(25)
    space = BrainGlobeAtlasSpace(metadata)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=20.0,
        dv_um=10.0,
        ml_um=30.0,
    )
    triangle = pv.PolyData(
        np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]]),
        np.array([3, 0, 1, 2]),
    )
    transform = space.world_transform_matrix(anchor)
    cancellation_checks: list[bool] = []

    prepared = prepare_world_mesh(
        triangle,
        space,
        anchor,
        check_cancelled=lambda: cancellation_checks.append(True),
    )

    assert np.linalg.det(transform[:3, :3]) == -1.0
    np.testing.assert_allclose(
        prepared.mesh.points,
        np.array([[30.0, 20.0, 10.0], [30.0, 10.0, 10.0], [30.0, 20.0, 0.0]]),
    )
    assert prepared.mesh.n_cells == 1
    assert "Normals" in prepared.mesh.point_data
    assert prepared.atlas_metadata == metadata
    assert prepared.renderer_anchor == anchor
    assert prepared.frame_id == "SURGERY_WORLD_RAS_UM"
    assert len(cancellation_checks) == 6


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
    controller.load_root_mesh(prepare_world_mesh(pv.Sphere(radius=100.0), space, anchor))
    received: list[BrainGlobePhysicalPoint] = []
    received_regions: list[tuple[int, BrainGlobePhysicalPoint]] = []
    controller.set_region(
        2,
        prepare_world_mesh(pv.Sphere(radius=50.0), space, anchor),
        rgb=(10, 20, 30),
        opacity=0.5,
        visible=True,
    )

    controller.enable_physical_picking(
        received.append,
        region_callback=lambda structure_id, point: received_regions.append((structure_id, point)),
    )

    assert plotter.picking_kwargs["use_picker"] is True
    assert callable(plotter.picking_callback)
    callback = plotter.picking_callback
    root_actor = FakeActor("actor:1")
    callback((0.0, 0.0, 0.0), FakePicker(root_actor))
    assert len(received) == 1
    assert received[0].as_tuple() == anchor.as_tuple()

    callback((0.0, 0.0, 0.0), FakePicker(FakeActor("actor:2")))
    assert received_regions == [(2, anchor)]
    assert len(received) == 1

    callback((0.0, 0.0, 0.0), FakePicker(FakeActor("unregistered")))
    callback((1e9, 1e9, 1e9), FakePicker(root_actor))
    callback((0.0, 0.0, 0.0), FakePicker(None))
    assert len(received) == 1


def test_scene_mutations_batch_each_user_update_into_one_render() -> None:
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
    source = prepare_world_mesh(pv.Sphere(radius=100.0), space, anchor)

    controller.load_root_mesh(source)
    assert plotter.render_count == 1
    assert plotter.mesh_kwargs[-1]["render"] is False
    assert plotter.axes_kwargs == [
        {
            "xlabel": "ML Right (+) / Left (-)",
            "ylabel": "AP Anterior (+) / Posterior (-)",
            "zlabel": "DV Superior/Dorsal (+) / Inferior/Ventral (-)",
        }
    ]

    controller.set_crosshair(anchor)
    assert plotter.render_count == 2
    assert all(kwargs["render"] is False for kwargs in plotter.mesh_kwargs[-3:])

    controller.set_region(2, source, rgb=(10, 20, 30), opacity=0.5, visible=True)
    assert plotter.render_count == 3
    assert plotter.mesh_kwargs[-1]["render"] is False

    controller.set_camera("dorsal")
    assert plotter.render_count == 4
    controller.reset_camera()
    assert plotter.render_count == 5


def test_hiding_region_releases_transformed_mesh_cache() -> None:
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
    source = prepare_world_mesh(pv.Sphere(radius=100.0), space, anchor)

    controller.set_region(2, source, rgb=(10, 20, 30), opacity=0.5, visible=True)
    assert 2 in controller._region_world_meshes

    controller.set_region(2, source, rgb=(10, 20, 30), opacity=0.5, visible=False)

    assert 2 not in controller._region_sources
    assert 2 not in controller._region_world_meshes
    assert 2 not in controller._region_actor_keys
    assert plotter.removed_actors[-1][1] == {"reset_camera": False, "render": False}
    assert plotter.render_count == 2


def test_center_region_frames_only_a_visible_region_mesh() -> None:
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
    source = prepare_world_mesh(
        pv.Sphere(radius=100.0, theta_resolution=8, phi_resolution=8),
        space,
        anchor,
    )
    controller.set_region(42, source, rgb=(10, 20, 30), opacity=0.6, visible=True)
    expected_bounds = controller._region_world_meshes[42].bounds
    prior_renders = plotter.render_count

    assert controller.center_region(42)
    assert plotter.reset_calls[-1]["bounds"] == pytest.approx(expected_bounds)
    assert plotter.reset_calls[-1]["render"] is False
    assert plotter.render_count == prior_renders + 1

    controller.set_region(42, source, rgb=(10, 20, 30), opacity=0.6, visible=False)
    assert not controller.center_region(42)
    assert not controller.center_region(999)


def test_two_scenes_share_worker_prepared_mesh_without_duplicate_preparation() -> None:
    metadata = make_allen_metadata_test_double(25)
    space = BrainGlobeAtlasSpace(metadata)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=metadata.extent_um[0] / 2,
        dv_um=metadata.extent_um[1] / 2,
        ml_um=metadata.extent_um[2] / 2,
    )
    prepared = prepare_world_mesh(
        pv.Sphere(radius=100.0, theta_resolution=8, phi_resolution=8),
        space,
        anchor,
    )
    first_plotter = FakePlotter()
    second_plotter = FakePlotter()
    first = SceneController(first_plotter, space, anchor)
    second = SceneController(second_plotter, space, anchor)

    first.load_root_mesh(prepared)
    second.load_root_mesh(prepared)
    first.set_region(2, prepared, rgb=(10, 20, 30), opacity=0.5, visible=True)
    second.set_region(2, prepared, rgb=(10, 20, 30), opacity=0.5, visible=True)

    assert first_plotter.mesh_args[0][0] is prepared.mesh
    assert second_plotter.mesh_args[0][0] is prepared.mesh
    assert first_plotter.mesh_args[1][0] is prepared.mesh
    assert second_plotter.mesh_args[1][0] is prepared.mesh


def test_prepared_mesh_identity_and_anchor_mismatches_fail_before_actor_creation() -> None:
    metadata = make_allen_metadata_test_double(25)
    space = BrainGlobeAtlasSpace(metadata)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=100.0,
        dv_um=100.0,
        ml_um=100.0,
    )
    prepared = prepare_world_mesh(pv.Sphere(radius=25.0), space, anchor)

    shifted_anchor = anchor.model_copy(update={"ap_um": 125.0})
    shifted_plotter = FakePlotter()
    shifted_scene = SceneController(shifted_plotter, space, shifted_anchor)
    with pytest.raises(ValueError, match="renderer anchor"):
        shifted_scene.load_root_mesh(prepared)
    assert shifted_plotter.actor_count == 0

    other_metadata = make_allen_metadata_test_double(10)
    other_space = BrainGlobeAtlasSpace(other_metadata)
    other_anchor = BrainGlobePhysicalPoint(
        atlas_key=other_metadata.atlas_key,
        atlas_version=other_metadata.atlas_package_version,
        ap_um=100.0,
        dv_um=100.0,
        ml_um=100.0,
    )
    other_plotter = FakePlotter()
    other_scene = SceneController(other_plotter, other_space, other_anchor)
    with pytest.raises(ValueError, match="atlas identity"):
        other_scene.set_region(
            2,
            prepared,
            rgb=(10, 20, 30),
            opacity=0.5,
            visible=True,
        )
    assert other_plotter.actor_count == 0


def test_asymmetric_landmarks_and_camera_presets_preserve_anatomical_sides() -> None:
    metadata = make_allen_metadata_test_double(25)
    space = BrainGlobeAtlasSpace(metadata)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=6600.0,
        dv_um=4000.0,
        ml_um=metadata.midline_ml_um,
    )
    right_landmark = anchor.model_copy(update={"ml_um": 1000.0})
    left_landmark = anchor.model_copy(update={"ml_um": 10_400.0})

    assert space.physical_to_world(right_landmark, anchor).ml_right_um > 0
    assert space.physical_to_world(left_landmark, anchor).ml_right_um < 0

    plotter = FakePlotter()
    controller = SceneController(plotter, space, anchor)
    expected_axis_and_sign = {
        "right": (0, 1),
        "left": (0, -1),
        "anterior": (1, 1),
        "posterior": (1, -1),
        "dorsal": (2, 1),
        "ventral": (2, -1),
    }
    for preset, (axis, sign) in expected_axis_and_sign.items():
        controller.set_camera(preset)
        camera = plotter.camera_position
        assert isinstance(camera, list)
        position = camera[0]
        assert isinstance(position, tuple)
        assert np.sign(position[axis]) == sign
        assert tuple(value for index, value in enumerate(position) if index != axis) == (0.0, 0.0)
