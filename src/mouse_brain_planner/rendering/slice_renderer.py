"""Vectorized orthogonal slicing for BrainGlobe ASR volumes.

BrainGlobe arrays are kept in their authoritative ``[AP, DV, ML]`` order. A
view changes only which axis is fixed and which two axes become image rows and
columns; it never performs an implicit anatomical flip.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
from numpy.typing import NDArray

type VoxelIndex = tuple[int, int, int]
type RGBColor = tuple[int, int, int]


class SliceOrientation(StrEnum):
    """Orthogonal view names and their fixed BrainGlobe ASR axes."""

    CORONAL = "coronal"
    SAGITTAL = "sagittal"
    HORIZONTAL = "horizontal"

    @classmethod
    def coerce(cls, value: SliceOrientation | str) -> SliceOrientation:
        """Return a normalized orientation with an actionable error."""

        if isinstance(value, cls):
            return value
        try:
            return cls(value.lower())
        except (AttributeError, ValueError) as error:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"orientation must be one of: {choices}") from error

    @property
    def fixed_axis(self) -> int:
        """Array axis held constant by this view."""

        if self is SliceOrientation.CORONAL:
            return 0  # AP
        if self is SliceOrientation.SAGITTAL:
            return 2  # ML
        return 1  # DV

    @property
    def row_axis(self) -> int:
        """BrainGlobe array axis displayed as image rows."""

        if self in (SliceOrientation.CORONAL, SliceOrientation.SAGITTAL):
            return 1  # DV
        return 0  # AP

    @property
    def column_axis(self) -> int:
        """BrainGlobe array axis displayed as image columns."""

        if self is SliceOrientation.SAGITTAL:
            return 0  # AP
        return 2  # ML

    @property
    def fixed_axis_name(self) -> str:
        """Anatomical name of the fixed axis."""

        return ("AP", "DV", "ML")[self.fixed_axis]


@dataclass(frozen=True, slots=True)
class SliceFrame:
    """One rendered slice and the masks used to compose it."""

    orientation: SliceOrientation
    slice_index: int
    reference: NDArray[Any]
    annotation: NDArray[Any]
    grayscale: NDArray[np.uint8]
    annotation_outline: NDArray[np.bool_]
    selected_region: NDArray[np.bool_]
    rgb: NDArray[np.uint8]


def extract_asr_slice(
    volume: NDArray[Any],
    orientation: SliceOrientation | str,
    slice_index: int,
) -> NDArray[Any]:
    """Extract a 2D view from a ``[AP, DV, ML]`` volume.

    Returned image axes are:

    - coronal: rows DV, columns ML, fixed AP;
    - sagittal: rows DV, columns AP, fixed ML;
    - horizontal: rows AP, columns ML, fixed DV.

    The result is normally a NumPy view. No per-pixel Python work is performed.
    """

    values = np.asarray(volume)
    if values.ndim != 3:
        raise ValueError(f"ASR volume must be three-dimensional, got shape {values.shape}")
    normalized = SliceOrientation.coerce(orientation)
    index = _integer_value(slice_index, "slice index")
    size = int(values.shape[normalized.fixed_axis])
    if index < 0 or index >= size:
        raise IndexError(f"{normalized.fixed_axis_name} slice {index} is outside [0, {size})")

    if normalized is SliceOrientation.CORONAL:
        return values[index, :, :]
    if normalized is SliceOrientation.SAGITTAL:
        return values[:, :, index].T
    return values[:, index, :]


def normalize_grayscale(
    image: NDArray[Any],
    *,
    low: float | None = None,
    high: float | None = None,
) -> NDArray[np.uint8]:
    """Apply a contrast window and return an 8-bit grayscale image.

    Missing limits are derived from finite values in this slice. Non-finite
    pixels render black. A constant auto-window also renders black instead of
    dividing by zero.
    """

    values = np.asarray(image, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError(f"grayscale input must be two-dimensional, got shape {values.shape}")
    finite = np.isfinite(values)
    finite_values = values[finite]
    if finite_values.size == 0:
        return np.zeros(values.shape, dtype=np.uint8)

    resolved_low = float(finite_values.min()) if low is None else float(low)
    resolved_high = float(finite_values.max()) if high is None else float(high)
    if not math.isfinite(resolved_low) or not math.isfinite(resolved_high):
        raise ValueError("contrast limits must be finite")
    if resolved_high < resolved_low:
        raise ValueError("contrast high limit must be greater than or equal to the low limit")
    if resolved_high == resolved_low:
        return np.zeros(values.shape, dtype=np.uint8)

    scaled = np.zeros(values.shape, dtype=np.float64)
    np.subtract(values, resolved_low, out=scaled, where=finite)
    scaled /= resolved_high - resolved_low
    np.clip(scaled, 0.0, 1.0, out=scaled)
    scaled[~finite] = 0.0
    return np.rint(scaled * 255.0).astype(np.uint8)


def annotation_outline(annotation: NDArray[Any]) -> NDArray[np.bool_]:
    """Return a two-sided, one-pixel outline at annotation label transitions."""

    labels = np.asarray(annotation)
    if labels.ndim != 2:
        raise ValueError(f"annotation input must be two-dimensional, got shape {labels.shape}")

    outline = np.zeros(labels.shape, dtype=np.bool_)
    vertical_changes = labels[1:, :] != labels[:-1, :]
    outline[1:, :] |= vertical_changes
    outline[:-1, :] |= vertical_changes
    horizontal_changes = labels[:, 1:] != labels[:, :-1]
    outline[:, 1:] |= horizontal_changes
    outline[:, :-1] |= horizontal_changes
    return outline


class SliceRenderer:
    """Render and map orthogonal slices from one explicit ASR test or atlas volume."""

    def __init__(
        self,
        reference: NDArray[Any],
        annotation: NDArray[Any],
        *,
        resolution_um: tuple[float, float, float],
    ) -> None:
        reference_values = np.asarray(reference)
        annotation_values = np.asarray(annotation)
        if reference_values.ndim != 3:
            raise ValueError("reference volume must be three-dimensional [AP, DV, ML]")
        if annotation_values.ndim != 3:
            raise ValueError("annotation volume must be three-dimensional [AP, DV, ML]")
        if reference_values.shape != annotation_values.shape:
            raise ValueError(
                "reference and annotation volumes must have the same [AP, DV, ML] shape"
            )
        if any(size <= 0 for size in reference_values.shape):
            raise ValueError("volume axes must all contain at least one voxel")
        if not np.issubdtype(annotation_values.dtype, np.integer):
            raise TypeError("annotation labels must use an integer NumPy dtype")
        if len(resolution_um) != 3 or any(
            not math.isfinite(float(value)) or float(value) <= 0 for value in resolution_um
        ):
            raise ValueError("resolution_um must contain three positive finite ASR values")

        self.reference = reference_values
        self.annotation = annotation_values
        self.resolution_um = tuple(float(value) for value in resolution_um)
        self.shape: tuple[int, int, int] = tuple(int(size) for size in reference_values.shape)  # type: ignore[assignment]

    def image_shape(self, orientation: SliceOrientation | str) -> tuple[int, int]:
        """Return displayed ``(rows, columns)`` for an orientation."""

        normalized = SliceOrientation.coerce(orientation)
        return (self.shape[normalized.row_axis], self.shape[normalized.column_axis])

    def slice_count(self, orientation: SliceOrientation | str) -> int:
        """Return the number of available positions on the fixed axis."""

        normalized = SliceOrientation.coerce(orientation)
        return self.shape[normalized.fixed_axis]

    def reference_slice(
        self, orientation: SliceOrientation | str, slice_index: int
    ) -> NDArray[Any]:
        """Extract a reference image with the documented displayed axes."""

        return extract_asr_slice(self.reference, orientation, slice_index)

    def annotation_slice(
        self, orientation: SliceOrientation | str, slice_index: int
    ) -> NDArray[Any]:
        """Extract an annotation image with the documented displayed axes."""

        return extract_asr_slice(self.annotation, orientation, slice_index)

    def render_slice(
        self,
        orientation: SliceOrientation | str,
        slice_index: int,
        *,
        contrast_low: float | None = None,
        contrast_high: float | None = None,
        selected_region_id: int | None = None,
        selected_color: RGBColor = (0, 174, 239),
        selected_alpha: float = 0.35,
        outline_color: RGBColor = (255, 170, 0),
        outline_alpha: float = 1.0,
    ) -> SliceFrame:
        """Compose grayscale, annotation outlines, and a selected-region overlay."""

        normalized = SliceOrientation.coerce(orientation)
        reference = self.reference_slice(normalized, slice_index)
        annotation = self.annotation_slice(normalized, slice_index)
        grayscale = normalize_grayscale(
            reference,
            low=contrast_low,
            high=contrast_high,
        )
        outline = annotation_outline(annotation)
        selected = np.zeros(annotation.shape, dtype=np.bool_)
        if selected_region_id is not None:
            region_id = _integer_value(selected_region_id, "selected region ID")
            selected = annotation == region_id

        selected_alpha_value = _alpha_value(selected_alpha, "selected alpha")
        outline_alpha_value = _alpha_value(outline_alpha, "outline alpha")
        selected_rgb = _color_value(selected_color, "selected color")
        outline_rgb = _color_value(outline_color, "outline color")

        rgb = np.repeat(grayscale[:, :, np.newaxis], 3, axis=2).astype(np.float32)
        _blend(rgb, selected, selected_rgb, selected_alpha_value)
        _blend(rgb, outline, outline_rgb, outline_alpha_value)
        composed = np.rint(np.clip(rgb, 0.0, 255.0)).astype(np.uint8)

        return SliceFrame(
            orientation=normalized,
            slice_index=_integer_value(slice_index, "slice index"),
            reference=reference,
            annotation=annotation,
            grayscale=grayscale,
            annotation_outline=outline,
            selected_region=selected,
            rgb=np.ascontiguousarray(composed),
        )

    def pixel_to_voxel(
        self,
        orientation: SliceOrientation | str,
        slice_index: int,
        column: int,
        row: int,
    ) -> VoxelIndex:
        """Map an image pixel ``(column, row)`` to ``(AP, DV, ML)``."""

        normalized = SliceOrientation.coerce(orientation)
        fixed = self._validate_slice_index(normalized, slice_index)
        column_value = _integer_value(column, "pixel column")
        row_value = _integer_value(row, "pixel row")
        rows, columns = self.image_shape(normalized)
        if column_value < 0 or column_value >= columns:
            raise IndexError(f"pixel column {column_value} is outside [0, {columns})")
        if row_value < 0 or row_value >= rows:
            raise IndexError(f"pixel row {row_value} is outside [0, {rows})")

        voxel = [0, 0, 0]
        voxel[normalized.fixed_axis] = fixed
        voxel[normalized.row_axis] = row_value
        voxel[normalized.column_axis] = column_value
        return (voxel[0], voxel[1], voxel[2])

    def voxel_to_pixel(
        self,
        orientation: SliceOrientation | str,
        voxel: VoxelIndex,
    ) -> tuple[int, int]:
        """Map an ``(AP, DV, ML)`` index to image ``(column, row)``."""

        normalized = SliceOrientation.coerce(orientation)
        values = self.validate_voxel(voxel)
        return (values[normalized.column_axis], values[normalized.row_axis])

    def slice_index_for_voxel(
        self,
        orientation: SliceOrientation | str,
        voxel: VoxelIndex,
    ) -> int:
        """Return the fixed-axis slice containing an ASR voxel."""

        normalized = SliceOrientation.coerce(orientation)
        values = self.validate_voxel(voxel)
        return values[normalized.fixed_axis]

    def validate_voxel(self, voxel: VoxelIndex) -> VoxelIndex:
        """Validate and normalize one discrete ``(AP, DV, ML)`` index."""

        if len(voxel) != 3:
            raise ValueError("voxel index must contain AP, DV, and ML")
        values = tuple(_integer_value(value, "voxel component") for value in voxel)
        for axis, (value, size) in enumerate(zip(values, self.shape, strict=True)):
            if value < 0 or value >= size:
                raise IndexError(f"ASR axis {axis} index {value} is outside [0, {size})")
        return values  # type: ignore[return-value]

    def slice_center_mm(
        self,
        orientation: SliceOrientation | str,
        slice_index: int,
    ) -> float:
        """Return the selected voxel-center coordinate from the ASR origin in mm."""

        normalized = SliceOrientation.coerce(orientation)
        index = self._validate_slice_index(normalized, slice_index)
        resolution = self.resolution_um[normalized.fixed_axis]
        return (index + 0.5) * resolution / 1000.0

    def slice_index_from_mm(
        self,
        orientation: SliceOrientation | str,
        position_mm: float,
    ) -> int:
        """Map an ASR physical coordinate in mm to its containing slice."""

        normalized = SliceOrientation.coerce(orientation)
        position = float(position_mm)
        if not math.isfinite(position):
            raise ValueError("slice position must be finite")
        extent_mm = (
            self.shape[normalized.fixed_axis] * self.resolution_um[normalized.fixed_axis] / 1000.0
        )
        if position < 0 or position >= extent_mm:
            raise IndexError(
                f"{normalized.fixed_axis_name} position {position:g} mm is outside "
                f"[0, {extent_mm:g})"
            )
        scaled = position * 1000.0 / self.resolution_um[normalized.fixed_axis]
        # Preserve half-open voxel semantics at a decimal value intended to be
        # an exact boundary despite normal binary floating-point representation.
        return min(math.floor(scaled + 1e-12), self.slice_count(normalized) - 1)

    def _validate_slice_index(
        self,
        orientation: SliceOrientation,
        slice_index: int,
    ) -> int:
        index = _integer_value(slice_index, "slice index")
        size = self.slice_count(orientation)
        if index < 0 or index >= size:
            raise IndexError(f"{orientation.fixed_axis_name} slice {index} is outside [0, {size})")
        return index


def _integer_value(value: int, label: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{label} must be an integer")
    return int(value)


def _alpha_value(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise ValueError(f"{label} must be finite and in [0, 1]")
    return result


def _color_value(value: RGBColor, label: str) -> NDArray[np.float32]:
    if len(value) != 3 or any(
        isinstance(component, bool)
        or not isinstance(component, (int, np.integer))
        or component < 0
        or component > 255
        for component in value
    ):
        raise ValueError(f"{label} must contain three integer values in [0, 255]")
    return np.asarray(value, dtype=np.float32)


def _blend(
    rgb: NDArray[np.float32],
    mask: NDArray[np.bool_],
    color: NDArray[np.float32],
    alpha: float,
) -> None:
    """Blend one solid color through a boolean mask using NumPy indexing."""

    if alpha == 0.0 or not np.any(mask):
        return
    rgb[mask] = rgb[mask] * (1.0 - alpha) + color * alpha
