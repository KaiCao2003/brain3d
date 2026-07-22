"""BrainGlobe ASR coordinate conversion and bounds enforcement."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import (
    BrainGlobePhysicalPoint,
    BrainGlobeVoxelIndex,
    BrainGlobeVoxelPoint,
    Hemisphere,
    SurgeryWorldPoint,
    VoxelAnchor,
)


class CoordinateBoundsError(ValueError):
    """Raised when a point lies outside the declared atlas extent."""


class AtlasIdentityError(ValueError):
    """Raised when a point belongs to a different atlas package."""


class CoordinateFrameError(ValueError):
    """Raised when a typed point declares the wrong coordinate frame."""


class BrainGlobeAtlasSpace:
    """Conversion service for one exact BrainGlobe atlas package.

    BrainGlobe stable atlas packages use ASR array coordinates in
    ``[AP, DV, ML]`` order. This service validates half-open bounds before a
    coordinate reaches NumPy or BrainGlobe, preventing negative-index wrap.
    """

    def __init__(self, metadata: AtlasMetadata) -> None:
        self.metadata = metadata

    def voxel_to_physical(self, point: BrainGlobeVoxelPoint) -> BrainGlobePhysicalPoint:
        """Convert a continuous voxel coordinate to micrometres."""

        self._check_voxel(point)
        values = point.as_tuple()
        self._validate_half_open(values, self.metadata.shape_voxels, "voxel")
        physical = tuple(
            value * resolution
            for value, resolution in zip(values, self.metadata.resolution_um, strict=True)
        )
        return BrainGlobePhysicalPoint(
            atlas_key=point.atlas_key,
            atlas_version=point.atlas_version,
            ap_um=physical[0],
            dv_um=physical[1],
            ml_um=physical[2],
        )

    def index_to_center(self, index: BrainGlobeVoxelIndex) -> BrainGlobePhysicalPoint:
        """Return the physical center of a discrete annotation voxel."""

        self._check_index(index)
        values = index.as_tuple()
        self._validate_index(values)
        center = tuple(
            (value + 0.5) * resolution
            for value, resolution in zip(values, self.metadata.resolution_um, strict=True)
        )
        return BrainGlobePhysicalPoint(
            atlas_key=index.atlas_key,
            atlas_version=index.atlas_version,
            ap_um=center[0],
            dv_um=center[1],
            ml_um=center[2],
        )

    def physical_to_voxel(self, point: BrainGlobePhysicalPoint) -> BrainGlobeVoxelPoint:
        """Convert physical micrometres to a continuous voxel coordinate."""

        self._check_physical(point)
        voxel = tuple(
            value / resolution
            for value, resolution in zip(point.as_tuple(), self.metadata.resolution_um, strict=True)
        )
        return BrainGlobeVoxelPoint(
            atlas_key=point.atlas_key,
            atlas_version=point.atlas_version,
            ap=voxel[0],
            dv=voxel[1],
            ml=voxel[2],
            anchor=VoxelAnchor.CONTINUOUS_INDEX,
        )

    def physical_to_index(self, point: BrainGlobePhysicalPoint) -> BrainGlobeVoxelIndex:
        """Map physical coordinates to the containing annotation voxel."""

        voxel = self.physical_to_voxel(point)
        voxel_values = voxel.as_tuple()
        indices = (
            math.floor(voxel_values[0]),
            math.floor(voxel_values[1]),
            math.floor(voxel_values[2]),
        )
        self._validate_index(indices)
        return BrainGlobeVoxelIndex(
            atlas_key=point.atlas_key,
            atlas_version=point.atlas_version,
            ap=indices[0],
            dv=indices[1],
            ml=indices[2],
        )

    def physical_to_world(
        self,
        point: BrainGlobePhysicalPoint,
        anchor: BrainGlobePhysicalPoint,
    ) -> SurgeryWorldPoint:
        """Map ASR physical coordinates into the right-handed render frame."""

        self._check_physical(point)
        self._check_physical(anchor)
        return SurgeryWorldPoint(
            atlas_key=point.atlas_key,
            atlas_version=point.atlas_version,
            ml_right_um=anchor.ml_um - point.ml_um,
            ap_anterior_um=anchor.ap_um - point.ap_um,
            dv_dorsal_um=anchor.dv_um - point.dv_um,
        )

    def world_to_physical(
        self,
        point: SurgeryWorldPoint,
        anchor: BrainGlobePhysicalPoint,
    ) -> BrainGlobePhysicalPoint:
        """Invert the right-handed render-frame mapping."""

        self._check_world(point)
        self._check_physical(anchor)
        result = BrainGlobePhysicalPoint(
            atlas_key=point.atlas_key,
            atlas_version=point.atlas_version,
            ap_um=anchor.ap_um - point.ap_anterior_um,
            dv_um=anchor.dv_um - point.dv_dorsal_um,
            ml_um=anchor.ml_um - point.ml_right_um,
        )
        self._check_physical(result)
        return result

    def world_transform_matrix(self, anchor: BrainGlobePhysicalPoint) -> NDArray[np.float64]:
        """Return the ASR-physical to render-world homogeneous matrix."""

        self._check_physical(anchor)
        return np.array(
            [
                [0.0, 0.0, -1.0, anchor.ml_um],
                [-1.0, 0.0, 0.0, anchor.ap_um],
                [0.0, -1.0, 0.0, anchor.dv_um],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

    def hemisphere(
        self,
        point: BrainGlobePhysicalPoint,
        *,
        midline_tolerance_um: float = 1e-9,
    ) -> Hemisphere:
        """Classify a physical point relative to the atlas midline."""

        self._check_physical(point)
        if midline_tolerance_um < 0 or not math.isfinite(midline_tolerance_um):
            raise ValueError("midline tolerance must be finite and non-negative")
        midline = self.metadata.midline_ml_um
        delta = point.ml_um - midline
        if abs(delta) <= midline_tolerance_um:
            return Hemisphere.MIDLINE
        return Hemisphere.RIGHT if delta < 0 else Hemisphere.LEFT

    def _check_physical(self, point: BrainGlobePhysicalPoint) -> None:
        self._check_frame(
            point.frame_id,
            "BRAINGLOBE_PHYSICAL_ASR_UM",
            "physical point",
        )
        self._check_identity(point.atlas_key, point.atlas_version)
        self._validate_half_open(point.as_tuple(), self.metadata.extent_um, "micrometre")

    def _check_voxel(self, point: BrainGlobeVoxelPoint) -> None:
        self._check_frame(point.frame_id, "BRAINGLOBE_VOXEL_ASR", "voxel point")
        if point.anchor != VoxelAnchor.CONTINUOUS_INDEX:
            raise CoordinateFrameError(
                f"voxel point anchor must be continuous-index; got {point.anchor!r}"
            )
        self._check_identity(point.atlas_key, point.atlas_version)

    def _check_index(self, index: BrainGlobeVoxelIndex) -> None:
        self._check_frame(index.frame_id, "BRAINGLOBE_VOXEL_INDEX_ASR", "voxel index")
        self._check_identity(index.atlas_key, index.atlas_version)

    def _check_world(self, point: SurgeryWorldPoint) -> None:
        self._check_frame(point.frame_id, "SURGERY_WORLD_RAS_UM", "world point")
        self._check_identity(point.atlas_key, point.atlas_version)

    @staticmethod
    def _check_frame(actual: object, expected: str, point_kind: str) -> None:
        if actual != expected:
            raise CoordinateFrameError(f"{point_kind} frame {actual!r} does not match {expected!r}")

    def _check_identity(self, atlas_key: str, atlas_version: str) -> None:
        expected = (self.metadata.atlas_key, self.metadata.atlas_package_version)
        actual = (atlas_key, atlas_version)
        if actual != expected:
            raise AtlasIdentityError(f"point atlas identity {actual} does not match {expected}")

    def _validate_index(self, values: tuple[int, int, int]) -> None:
        for axis, (value, size) in enumerate(zip(values, self.metadata.shape_voxels, strict=True)):
            if value < 0 or value >= size:
                raise CoordinateBoundsError(f"axis {axis} index {value} is outside [0, {size})")

    @staticmethod
    def _validate_half_open(
        values: tuple[float, float, float],
        upper_bounds: tuple[int, int, int] | tuple[float, float, float],
        unit_label: str,
    ) -> None:
        for axis, (value, upper) in enumerate(zip(values, upper_bounds, strict=True)):
            if not math.isfinite(value):
                raise CoordinateBoundsError(
                    f"axis {axis} {unit_label} value {value!r} is not finite"
                )
            if value < 0 or value >= upper:
                raise CoordinateBoundsError(
                    f"axis {axis} {unit_label} value {value:g} is outside [0, {upper})"
                )
