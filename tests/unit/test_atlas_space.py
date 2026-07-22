"""Unit tests for the explicit BrainGlobe ASR coordinate contract."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import BaseModel
from tests.fixtures import AllenResolution, make_allen_metadata_test_double

from mouse_brain_planner.coordinates.atlas_space import (
    AtlasIdentityError,
    BrainGlobeAtlasSpace,
    CoordinateBoundsError,
    CoordinateFrameError,
)
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import (
    BrainGlobePhysicalPoint,
    BrainGlobeVoxelIndex,
    BrainGlobeVoxelPoint,
    Hemisphere,
    SurgeryWorldPoint,
    VoxelAnchor,
)

ATLAS_CASES = (
    pytest.param(
        10,
        "allen_mouse_10um",
        (1320, 800, 1140),
        (1319, 799, 1139),
        (13190.0, 7990.0, 11390.0),
        (13195.0, 7995.0, 11395.0),
        id="10um",
    ),
    pytest.param(
        25,
        "allen_mouse_25um",
        (528, 320, 456),
        (527, 319, 455),
        (13175.0, 7975.0, 11375.0),
        (13187.5, 7987.5, 11387.5),
        id="25um",
    ),
)


def _physical(
    metadata: AtlasMetadata,
    values: tuple[float, float, float],
    *,
    atlas_key: str | None = None,
    atlas_version: str | None = None,
) -> BrainGlobePhysicalPoint:
    return BrainGlobePhysicalPoint(
        atlas_key=atlas_key or metadata.atlas_key,
        atlas_version=atlas_version or metadata.atlas_package_version,
        ap_um=values[0],
        dv_um=values[1],
        ml_um=values[2],
    )


def _voxel(
    metadata: AtlasMetadata,
    values: tuple[float, float, float],
    *,
    atlas_key: str | None = None,
    atlas_version: str | None = None,
) -> BrainGlobeVoxelPoint:
    return BrainGlobeVoxelPoint(
        atlas_key=atlas_key or metadata.atlas_key,
        atlas_version=atlas_version or metadata.atlas_package_version,
        ap=values[0],
        dv=values[1],
        ml=values[2],
    )


def _index(
    metadata: AtlasMetadata,
    values: tuple[int, int, int],
) -> BrainGlobeVoxelIndex:
    return BrainGlobeVoxelIndex(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap=values[0],
        dv=values[1],
        ml=values[2],
    )


@pytest.mark.parametrize(
    (
        "resolution_um",
        "atlas_key",
        "shape",
        "last_index",
        "last_anchor",
        "last_center",
    ),
    ATLAS_CASES,
)
def test_metadata_test_double_matches_published_contract(
    resolution_um: AllenResolution,
    atlas_key: str,
    shape: tuple[int, int, int],
    last_index: tuple[int, int, int],
    last_anchor: tuple[float, float, float],
    last_center: tuple[float, float, float],
) -> None:
    metadata = make_allen_metadata_test_double(resolution_um)

    assert metadata.atlas_key == atlas_key
    assert metadata.atlas_package_version == "1.2"
    assert metadata.standardized_orientation == "asr"
    assert metadata.source_annotation == "annotation/ccf_2017"
    assert metadata.shape_voxels == shape
    assert metadata.resolution_um == (float(resolution_um),) * 3
    assert metadata.extent_um == (13200.0, 8000.0, 11400.0)
    assert metadata.midline_ml_um == 5700.0
    assert tuple(axis.voxel_size_um for axis in metadata.axes) == metadata.resolution_um
    assert tuple(
        (
            axis.array_axis,
            axis.anatomical_axis,
            axis.origin_direction,
            axis.positive_direction,
        )
        for axis in metadata.axes
    ) == (
        (0, "AP", "anterior", "posterior"),
        (1, "DV", "superior", "inferior"),
        (2, "ML", "right", "left"),
    )
    assert "__atlas_test_double__" in metadata.cache_path
    assert metadata.source_url.endswith(f"{atlas_key}_v1.2.tar.gz")
    assert len(metadata.metadata_sha256) == 64

    space = BrainGlobeAtlasSpace(metadata)
    center = space.index_to_center(_index(metadata, last_index))
    np.testing.assert_allclose(center.as_tuple(), last_center, rtol=0.0, atol=0.0)
    expected_anchor = tuple(
        value * resolution
        for value, resolution in zip(last_index, metadata.resolution_um, strict=True)
    )
    assert expected_anchor == last_anchor


def test_metadata_rejects_axis_voxel_size_different_from_resolution() -> None:
    metadata = make_allen_metadata_test_double(25)
    payload = metadata.model_dump()
    payload["axes"][1]["voxel_size_um"] = 10.0

    with pytest.raises(ValueError, match="axis voxel sizes must equal resolution_um"):
        AtlasMetadata.model_validate(payload)


@pytest.mark.parametrize("resolution_um", (10, 25), ids=("10um", "25um"))
def test_continuous_voxel_physical_round_trip(resolution_um: AllenResolution) -> None:
    metadata = make_allen_metadata_test_double(resolution_um)
    space = BrainGlobeAtlasSpace(metadata)
    samples = (
        (0.0, 0.0, 0.0),
        (0.125, 1.5, 2.75),
        tuple(float(size) - 1e-6 for size in metadata.shape_voxels),
    )

    for values in samples:
        physical = space.voxel_to_physical(_voxel(metadata, values))
        round_trip = space.physical_to_voxel(physical)

        assert physical.frame_id == "BRAINGLOBE_PHYSICAL_ASR_UM"
        assert round_trip.frame_id == "BRAINGLOBE_VOXEL_ASR"
        assert round_trip.anchor is VoxelAnchor.CONTINUOUS_INDEX
        np.testing.assert_allclose(round_trip.as_tuple(), values, rtol=0.0, atol=1e-9)


@pytest.mark.parametrize("resolution_um", (10, 25), ids=("10um", "25um"))
def test_discrete_index_center_round_trip(resolution_um: AllenResolution) -> None:
    metadata = make_allen_metadata_test_double(resolution_um)
    space = BrainGlobeAtlasSpace(metadata)
    indices = (
        (0, 0, 0),
        tuple(size // 2 for size in metadata.shape_voxels),
        tuple(size - 1 for size in metadata.shape_voxels),
    )

    for values in indices:
        index = _index(metadata, values)
        center = space.index_to_center(index)
        continuous = space.physical_to_voxel(center)
        round_trip = space.physical_to_index(center)
        expected_center = tuple(
            (value + 0.5) * resolution
            for value, resolution in zip(values, metadata.resolution_um, strict=True)
        )

        np.testing.assert_allclose(center.as_tuple(), expected_center, rtol=0.0, atol=0.0)
        np.testing.assert_allclose(
            continuous.as_tuple(),
            tuple(value + 0.5 for value in values),
            rtol=0.0,
            atol=0.0,
        )
        assert round_trip.as_tuple() == values


@pytest.mark.parametrize("resolution_um", (10, 25), ids=("10um", "25um"))
@pytest.mark.parametrize("axis", (0, 1, 2))
def test_physical_coordinates_enforce_half_open_bounds(
    resolution_um: AllenResolution,
    axis: int,
) -> None:
    metadata = make_allen_metadata_test_double(resolution_um)
    space = BrainGlobeAtlasSpace(metadata)
    just_inside = tuple(np.nextafter(upper, 0.0) for upper in metadata.extent_um)
    expected_last = tuple(size - 1 for size in metadata.shape_voxels)

    assert space.physical_to_index(_physical(metadata, just_inside)).as_tuple() == expected_last

    at_upper = [0.0, 0.0, 0.0]
    at_upper[axis] = metadata.extent_um[axis]
    with pytest.raises(CoordinateBoundsError, match=rf"axis {axis} .* outside"):
        space.physical_to_index(_physical(metadata, tuple(at_upper)))

    negative = [0.0, 0.0, 0.0]
    negative[axis] = -0.1
    with pytest.raises(CoordinateBoundsError, match=rf"axis {axis} .* outside"):
        space.physical_to_index(_physical(metadata, tuple(negative)))


@pytest.mark.parametrize("resolution_um", (10, 25), ids=("10um", "25um"))
@pytest.mark.parametrize("axis", (0, 1, 2))
def test_voxel_coordinates_and_indices_enforce_half_open_bounds(
    resolution_um: AllenResolution,
    axis: int,
) -> None:
    metadata = make_allen_metadata_test_double(resolution_um)
    space = BrainGlobeAtlasSpace(metadata)

    just_inside = tuple(np.nextafter(float(size), 0.0) for size in metadata.shape_voxels)
    space.voxel_to_physical(_voxel(metadata, just_inside))

    at_upper = [0.0, 0.0, 0.0]
    at_upper[axis] = float(metadata.shape_voxels[axis])
    with pytest.raises(CoordinateBoundsError, match=rf"axis {axis} .* outside"):
        space.voxel_to_physical(_voxel(metadata, tuple(at_upper)))

    negative = [0.0, 0.0, 0.0]
    negative[axis] = -0.1
    with pytest.raises(CoordinateBoundsError, match=rf"axis {axis} .* outside"):
        space.voxel_to_physical(_voxel(metadata, tuple(negative)))

    invalid_index_values = [0, 0, 0]
    invalid_index_values[axis] = metadata.shape_voxels[axis]
    with pytest.raises(CoordinateBoundsError, match=rf"axis {axis} index .* outside"):
        space.index_to_center(_index(metadata, tuple(invalid_index_values)))

    malformed_negative_index = [0, 0, 0]
    malformed_negative_index[axis] = -1
    index = BrainGlobeVoxelIndex.model_construct(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap=malformed_negative_index[0],
        dv=malformed_negative_index[1],
        ml=malformed_negative_index[2],
    )
    with pytest.raises(CoordinateBoundsError, match=rf"axis {axis} index -1 is outside"):
        space.index_to_center(index)


@pytest.mark.parametrize("resolution_um", (10, 25), ids=("10um", "25um"))
@pytest.mark.parametrize("axis", (0, 1, 2))
@pytest.mark.parametrize("invalid", (math.nan, math.inf, -math.inf), ids=("nan", "inf", "-inf"))
def test_space_defensively_rejects_non_finite_physical_points(
    resolution_um: AllenResolution,
    axis: int,
    invalid: float,
) -> None:
    metadata = make_allen_metadata_test_double(resolution_um)
    values = [0.0, 0.0, 0.0]
    values[axis] = invalid
    malformed = BrainGlobePhysicalPoint.model_construct(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=values[0],
        dv_um=values[1],
        ml_um=values[2],
    )

    with pytest.raises(CoordinateBoundsError, match=rf"axis {axis} .* not finite"):
        BrainGlobeAtlasSpace(metadata).physical_to_index(malformed)


@pytest.mark.parametrize("resolution_um", (10, 25), ids=("10um", "25um"))
@pytest.mark.parametrize("axis", (0, 1, 2))
@pytest.mark.parametrize("invalid", (math.nan, math.inf, -math.inf), ids=("nan", "inf", "-inf"))
def test_space_defensively_rejects_non_finite_voxel_points(
    resolution_um: AllenResolution,
    axis: int,
    invalid: float,
) -> None:
    metadata = make_allen_metadata_test_double(resolution_um)
    values = [0.0, 0.0, 0.0]
    values[axis] = invalid
    malformed = BrainGlobeVoxelPoint.model_construct(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap=values[0],
        dv=values[1],
        ml=values[2],
    )

    with pytest.raises(CoordinateBoundsError, match=rf"axis {axis} .* not finite"):
        BrainGlobeAtlasSpace(metadata).voxel_to_physical(malformed)


@pytest.mark.parametrize(
    ("atlas_key", "atlas_version"),
    (("other_atlas", "1.2"), ("allen_mouse_25um", "9.9")),
    ids=("wrong-key", "wrong-version"),
)
def test_point_identity_mismatch_is_rejected(atlas_key: str, atlas_version: str) -> None:
    metadata = make_allen_metadata_test_double(25)
    space = BrainGlobeAtlasSpace(metadata)
    physical = _physical(
        metadata,
        (100.0, 100.0, 100.0),
        atlas_key=atlas_key,
        atlas_version=atlas_version,
    )
    voxel = _voxel(
        metadata,
        (1.0, 1.0, 1.0),
        atlas_key=atlas_key,
        atlas_version=atlas_version,
    )

    with pytest.raises(AtlasIdentityError, match="does not match"):
        space.physical_to_index(physical)
    with pytest.raises(AtlasIdentityError, match="does not match"):
        space.voxel_to_physical(voxel)


def test_anchor_identity_mismatch_is_rejected() -> None:
    metadata = make_allen_metadata_test_double(25)
    space = BrainGlobeAtlasSpace(metadata)
    point = _physical(metadata, (100.0, 100.0, 100.0))
    wrong_anchor = _physical(
        metadata,
        (6600.0, 4000.0, 5700.0),
        atlas_version="9.9",
    )

    with pytest.raises(AtlasIdentityError, match="does not match"):
        space.physical_to_world(point, wrong_anchor)
    with pytest.raises(AtlasIdentityError, match="does not match"):
        space.world_transform_matrix(wrong_anchor)


@pytest.mark.parametrize(
    ("point_type", "payload", "wrong_frame"),
    (
        (
            BrainGlobeVoxelPoint,
            {"ap": 1.0, "dv": 1.0, "ml": 1.0},
            "BRAINGLOBE_PHYSICAL_ASR_UM",
        ),
        (
            BrainGlobeVoxelIndex,
            {"ap": 1, "dv": 1, "ml": 1},
            "BRAINGLOBE_VOXEL_ASR",
        ),
        (
            BrainGlobePhysicalPoint,
            {"ap_um": 1.0, "dv_um": 1.0, "ml_um": 1.0},
            "SURGERY_WORLD_RAS_UM",
        ),
        (
            SurgeryWorldPoint,
            {"ml_right_um": 1.0, "ap_anterior_um": 1.0, "dv_dorsal_um": 1.0},
            "BRAINGLOBE_PHYSICAL_ASR_UM",
        ),
    ),
    ids=("voxel", "index", "physical", "world"),
)
def test_point_models_reject_caller_overridden_frames(
    point_type: type[BaseModel],
    payload: dict[str, float | int],
    wrong_frame: str,
) -> None:
    metadata = make_allen_metadata_test_double(25)

    with pytest.raises(ValueError, match="Input should be"):
        point_type.model_validate(
            {
                "atlas_key": metadata.atlas_key,
                "atlas_version": metadata.atlas_package_version,
                "frame_id": wrong_frame,
                **payload,
            }
        )


def test_voxel_point_model_rejects_voxel_center_anchor() -> None:
    metadata = make_allen_metadata_test_double(25)

    with pytest.raises(ValueError, match="continuous-index"):
        BrainGlobeVoxelPoint.model_validate(
            {
                "atlas_key": metadata.atlas_key,
                "atlas_version": metadata.atlas_package_version,
                "ap": 1.0,
                "dv": 1.0,
                "ml": 1.0,
                "anchor": VoxelAnchor.VOXEL_CENTER,
            }
        )


def test_space_defensively_rejects_constructed_wrong_frames_and_anchor() -> None:
    metadata = make_allen_metadata_test_double(25)
    space = BrainGlobeAtlasSpace(metadata)
    malformed_voxel = BrainGlobeVoxelPoint.model_construct(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap=1.0,
        dv=1.0,
        ml=1.0,
        frame_id="WRONG",
    )
    malformed_anchor = BrainGlobeVoxelPoint.model_construct(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap=1.0,
        dv=1.0,
        ml=1.0,
        anchor=VoxelAnchor.VOXEL_CENTER,
    )
    malformed_index = BrainGlobeVoxelIndex.model_construct(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap=1,
        dv=1,
        ml=1,
        frame_id="WRONG",
    )
    malformed_physical = BrainGlobePhysicalPoint.model_construct(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=100.0,
        dv_um=100.0,
        ml_um=100.0,
        frame_id="WRONG",
    )
    malformed_world = SurgeryWorldPoint.model_construct(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ml_right_um=0.0,
        ap_anterior_um=0.0,
        dv_dorsal_um=0.0,
        frame_id="WRONG",
    )
    valid_anchor = _physical(metadata, (100.0, 100.0, 100.0))

    with pytest.raises(CoordinateFrameError, match="voxel point frame"):
        space.voxel_to_physical(malformed_voxel)
    with pytest.raises(CoordinateFrameError, match="anchor must be continuous-index"):
        space.voxel_to_physical(malformed_anchor)
    with pytest.raises(CoordinateFrameError, match="voxel index frame"):
        space.index_to_center(malformed_index)
    with pytest.raises(CoordinateFrameError, match="physical point frame"):
        space.physical_to_index(malformed_physical)
    with pytest.raises(CoordinateFrameError, match="world point frame"):
        space.world_to_physical(malformed_world, valid_anchor)


@pytest.mark.parametrize("resolution_um", (10, 25), ids=("10um", "25um"))
def test_world_matrix_has_negative_determinant_and_inverts(
    resolution_um: AllenResolution,
) -> None:
    metadata = make_allen_metadata_test_double(resolution_um)
    space = BrainGlobeAtlasSpace(metadata)
    anchor = _physical(metadata, (6600.0, 4000.0, 5700.0))
    point = _physical(metadata, (123.25, 456.5, 789.75))
    matrix = space.world_transform_matrix(anchor)
    expected = np.array(
        [
            [0.0, 0.0, -1.0, 5700.0],
            [-1.0, 0.0, 0.0, 6600.0],
            [0.0, -1.0, 0.0, 4000.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    np.testing.assert_array_equal(matrix, expected)
    assert np.linalg.det(matrix[:3, :3]) == pytest.approx(-1.0, abs=0.0)

    world = space.physical_to_world(point, anchor)
    homogeneous = np.array([*point.as_tuple(), 1.0])
    mapped = matrix @ homogeneous
    np.testing.assert_allclose(mapped[:3], world.as_tuple(), rtol=0.0, atol=1e-12)
    assert mapped[3] == 1.0

    round_trip = space.world_to_physical(world, anchor)
    np.testing.assert_allclose(round_trip.as_tuple(), point.as_tuple(), rtol=0.0, atol=1e-12)
    inverse_mapped = np.linalg.inv(matrix) @ mapped
    np.testing.assert_allclose(inverse_mapped, homogeneous, rtol=0.0, atol=1e-12)

    world_origin = space.physical_to_world(anchor, anchor)
    assert world_origin.as_tuple() == (0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    ("resolution_um", "last_right_index", "first_left_index"),
    (
        pytest.param(10, 569, 570, id="10um"),
        pytest.param(25, 227, 228, id="25um"),
    ),
)
def test_hemisphere_and_midline_contract(
    resolution_um: AllenResolution,
    last_right_index: int,
    first_left_index: int,
) -> None:
    metadata = make_allen_metadata_test_double(resolution_um)
    space = BrainGlobeAtlasSpace(metadata)
    midline_um = metadata.extent_um[2] / 2.0
    right_center_um = (last_right_index + 0.5) * resolution_um
    left_center_um = (first_left_index + 0.5) * resolution_um

    assert midline_um == 5700.0
    assert space.hemisphere(_physical(metadata, (0.0, 0.0, midline_um))) is Hemisphere.MIDLINE
    assert space.hemisphere(_physical(metadata, (0.0, 0.0, right_center_um))) is Hemisphere.RIGHT
    assert space.hemisphere(_physical(metadata, (0.0, 0.0, left_center_um))) is Hemisphere.LEFT


@pytest.mark.parametrize("invalid", (-1.0, math.nan, math.inf), ids=("negative", "nan", "inf"))
def test_hemisphere_rejects_invalid_tolerance(invalid: float) -> None:
    metadata = make_allen_metadata_test_double(25)
    point = _physical(metadata, (0.0, 0.0, 5700.0))

    with pytest.raises(ValueError, match="tolerance must be finite and non-negative"):
        BrainGlobeAtlasSpace(metadata).hemisphere(point, midline_tolerance_um=invalid)


def test_hemisphere_uses_explicit_metadata_midline_not_extent_midpoint() -> None:
    payload = make_allen_metadata_test_double(25).model_dump()
    payload["symmetric"] = False
    payload["midline_ml_um"] = 5600.0
    metadata = AtlasMetadata.model_validate(payload)
    space = BrainGlobeAtlasSpace(metadata)

    assert space.hemisphere(_physical(metadata, (0.0, 0.0, 5600.0))) is Hemisphere.MIDLINE
    assert space.hemisphere(_physical(metadata, (0.0, 0.0, 5650.0))) is Hemisphere.LEFT


def test_symmetric_metadata_rejects_noncentral_midline() -> None:
    payload = make_allen_metadata_test_double(25).model_dump()
    payload["midline_ml_um"] = 5600.0

    with pytest.raises(ValueError, match="must equal half the ML extent"):
        AtlasMetadata.model_validate(payload)
