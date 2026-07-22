"""Vectorized orthogonal slicing for BrainGlobe ASR volumes.

BrainGlobe arrays are kept in their authoritative ``[AP, DV, ML]`` order. A
view changes only which axis is fixed and which two axes become image rows and
columns; it never performs an implicit anatomical flip.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

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

    @property
    def row_axis_name(self) -> str:
        """Anatomical name of the image-row axis."""

        return ("AP", "DV", "ML")[self.row_axis]

    @property
    def column_axis_name(self) -> str:
        """Anatomical name of the image-column axis."""

        return ("AP", "DV", "ML")[self.column_axis]


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


@dataclass(frozen=True, slots=True)
class _SliceCacheKey:
    """Canonical inputs that can change a composed slice frame."""

    orientation: SliceOrientation
    slice_index: int
    contrast_low: float | None
    contrast_high: float | None
    selected_region_ids: tuple[int, ...]
    selected_color: RGBColor
    selected_alpha: float
    outline_color: RGBColor
    outline_alpha: float


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

    source = np.asarray(image)
    if source.ndim != 2:
        raise ValueError(f"grayscale input must be two-dimensional, got shape {source.shape}")

    # Reviewed Allen references are uint16.  Mapping them through a 65,536-entry
    # lookup table produces the same float64 subtract/scale/clip/rint result as
    # a slice-sized float64 working copy while bounding temporary memory and GUI
    # latency for large atlas views.
    if source.dtype == np.dtype(np.uint16):
        resolved_low = float(source.min()) if low is None else float(low)
        resolved_high = float(source.max()) if high is None else float(high)
        if not math.isfinite(resolved_low) or not math.isfinite(resolved_high):
            raise ValueError("contrast limits must be finite")
        if resolved_high < resolved_low:
            raise ValueError("contrast high limit must be greater than or equal to the low limit")
        if resolved_high == resolved_low:
            return np.zeros(source.shape, dtype=np.uint8)

        lookup = np.arange(1 << 16, dtype=np.float64)
        lookup -= resolved_low
        lookup /= resolved_high - resolved_low
        np.clip(lookup, 0.0, 1.0, out=lookup)
        lookup *= 255.0
        np.rint(lookup, out=lookup)
        return np.asarray(lookup.astype(np.uint8)[source], dtype=np.uint8)

    values = np.asarray(source, dtype=np.float64)
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

    _CACHE_FRAMES_PER_ORIENTATION = 2
    _CACHE_MAX_BYTES = 64 * 1024 * 1024

    def __init__(
        self,
        reference: NDArray[Any],
        annotation: NDArray[Any],
        *,
        resolution_um: tuple[float, float, float],
        sagittal_reference: NDArray[Any] | None = None,
        sagittal_annotation: NDArray[Any] | None = None,
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

        if (sagittal_reference is None) != (sagittal_annotation is None):
            raise ValueError("sagittal reference and annotation arrays must be provided together")
        optimized_reference = None if sagittal_reference is None else np.asarray(sagittal_reference)
        optimized_annotation = (
            None if sagittal_annotation is None else np.asarray(sagittal_annotation)
        )
        if optimized_reference is not None and optimized_annotation is not None:
            sagittal_shape = (
                reference_values.shape[2],
                reference_values.shape[1],
                reference_values.shape[0],
            )
            if (
                optimized_reference.shape != sagittal_shape
                or optimized_annotation.shape != sagittal_shape
            ):
                raise ValueError(
                    f"optimized sagittal arrays must use exact [ML,DV,AP] shape {sagittal_shape}"
                )
            if optimized_reference.dtype != reference_values.dtype:
                raise TypeError("optimized sagittal reference dtype must match the ASR reference")
            if optimized_annotation.dtype != annotation_values.dtype:
                raise TypeError("optimized sagittal annotation dtype must match the ASR annotation")

        self.reference = reference_values
        self.annotation = annotation_values
        self._sagittal_reference = optimized_reference
        self._sagittal_annotation = optimized_annotation
        self.resolution_um = tuple(float(value) for value in resolution_um)
        self.shape: tuple[int, int, int] = tuple(int(size) for size in reference_values.shape)  # type: ignore[assignment]
        # A renderer belongs to exactly one atlas instance, so cached frames can
        # never be reused across atlas volumes. Two entries per orientation
        # cover the paired slice views while bounding retained working arrays.
        self._frame_cache: OrderedDict[_SliceCacheKey, tuple[SliceFrame, int]] = OrderedDict()
        self._frame_cache_bytes = 0

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

        normalized = SliceOrientation.coerce(orientation)
        if normalized is SliceOrientation.SAGITTAL and self._sagittal_reference is not None:
            index = self._validate_slice_index(normalized, slice_index)
            return cast(NDArray[Any], self._sagittal_reference[index])
        return extract_asr_slice(self.reference, normalized, slice_index)

    def annotation_slice(
        self, orientation: SliceOrientation | str, slice_index: int
    ) -> NDArray[Any]:
        """Extract an annotation image with the documented displayed axes."""

        normalized = SliceOrientation.coerce(orientation)
        if normalized is SliceOrientation.SAGITTAL and self._sagittal_annotation is not None:
            index = self._validate_slice_index(normalized, slice_index)
            return cast(NDArray[Any], self._sagittal_annotation[index])
        return extract_asr_slice(self.annotation, normalized, slice_index)

    def render_slice(
        self,
        orientation: SliceOrientation | str,
        slice_index: int,
        *,
        contrast_low: float | None = None,
        contrast_high: float | None = None,
        selected_region_id: int | None = None,
        selected_region_ids: Collection[int] | None = None,
        selected_color: RGBColor = (0, 174, 239),
        selected_alpha: float = 0.35,
        outline_color: RGBColor = (255, 170, 0),
        outline_alpha: float = 1.0,
    ) -> SliceFrame:
        """Compose grayscale, annotation outlines, and a selected-region overlay."""

        normalized = SliceOrientation.coerce(orientation)
        index = self._validate_slice_index(normalized, slice_index)
        resolved_low = None if contrast_low is None else float(contrast_low)
        resolved_high = None if contrast_high is None else float(contrast_high)
        region_ids: set[int] = set()
        if selected_region_id is not None:
            region_ids.add(_integer_value(selected_region_id, "selected region ID"))
        if selected_region_ids is not None:
            region_ids.update(
                _integer_value(region_id, "selected region ID") for region_id in selected_region_ids
            )
        selected_alpha_value = _alpha_value(selected_alpha, "selected alpha")
        outline_alpha_value = _alpha_value(outline_alpha, "outline alpha")
        selected_color_value = _color_components(selected_color, "selected color")
        outline_color_value = _color_components(outline_color, "outline color")
        cache_key = _SliceCacheKey(
            orientation=normalized,
            slice_index=index,
            contrast_low=resolved_low,
            contrast_high=resolved_high,
            selected_region_ids=tuple(sorted(region_ids)),
            selected_color=selected_color_value,
            selected_alpha=selected_alpha_value,
            outline_color=outline_color_value,
            outline_alpha=outline_alpha_value,
        )
        cached = self._frame_cache.get(cache_key)
        if cached is not None:
            self._frame_cache.move_to_end(cache_key)
            return cached[0]

        reference = self.reference_slice(normalized, index)
        annotation = self.annotation_slice(normalized, index)
        grayscale = normalize_grayscale(
            reference,
            low=resolved_low,
            high=resolved_high,
        )
        outline = annotation_outline(annotation)
        selected = np.zeros(annotation.shape, dtype=np.bool_)
        if len(region_ids) == 1:
            selected = annotation == next(iter(region_ids))
        elif region_ids:
            selected = np.isin(annotation, tuple(region_ids))

        composed = _compose_rgb(
            grayscale,
            selected,
            selected_color_value,
            selected_alpha_value,
            outline,
            outline_color_value,
            outline_alpha_value,
        )

        frame = SliceFrame(
            orientation=normalized,
            slice_index=index,
            reference=reference,
            annotation=annotation,
            grayscale=grayscale,
            annotation_outline=outline,
            selected_region=selected,
            rgb=composed,
        )
        self._freeze_frame(frame)
        self._cache_frame(cache_key, frame)
        return frame

    def _cache_frame(self, cache_key: _SliceCacheKey, frame: SliceFrame) -> None:
        """Retain one immutable frame without exceeding either cache bound."""

        cache_bytes = sum(
            array.nbytes
            for array in (
                frame.grayscale,
                frame.annotation_outline,
                frame.selected_region,
                frame.rgb,
            )
        )
        if cache_bytes > self._CACHE_MAX_BYTES:
            return

        self._frame_cache[cache_key] = (frame, cache_bytes)
        self._frame_cache_bytes += cache_bytes
        orientation_keys = [
            key for key in self._frame_cache if key.orientation is cache_key.orientation
        ]
        while len(orientation_keys) > self._CACHE_FRAMES_PER_ORIENTATION:
            self._evict_frame(orientation_keys.pop(0))
        while self._frame_cache_bytes > self._CACHE_MAX_BYTES:
            oldest_key = next(iter(self._frame_cache))
            self._evict_frame(oldest_key)

    def _evict_frame(self, cache_key: _SliceCacheKey) -> None:
        _, cache_bytes = self._frame_cache.pop(cache_key)
        self._frame_cache_bytes -= cache_bytes

    @staticmethod
    def _freeze_frame(frame: SliceFrame) -> None:
        """Make every array exposed by a shared frame reject writes."""

        for array in (
            frame.reference,
            frame.annotation,
            frame.grayscale,
            frame.annotation_outline,
            frame.selected_region,
            frame.rgb,
        ):
            array.setflags(write=False)

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


def _color_components(value: RGBColor, label: str) -> RGBColor:
    if len(value) != 3 or any(
        isinstance(component, bool)
        or not isinstance(component, (int, np.integer))
        or component < 0
        or component > 255
        for component in value
    ):
        raise ValueError(f"{label} must contain three integer values in [0, 255]")
    return (int(value[0]), int(value[1]), int(value[2]))


def _compose_rgb(
    grayscale: NDArray[np.uint8],
    selected: NDArray[np.bool_],
    selected_color: RGBColor,
    selected_alpha: float,
    outline: NDArray[np.bool_],
    outline_color: RGBColor,
    outline_alpha: float,
) -> NDArray[np.uint8]:
    """Blend overlays exactly while allocating float pixels only where needed."""

    rgb = np.repeat(grayscale[:, :, np.newaxis], 3, axis=2)
    active = np.zeros(grayscale.shape, dtype=np.bool_)
    if selected_alpha != 0.0:
        active |= selected
    if outline_alpha != 0.0:
        active |= outline
    if not np.any(active):
        return np.ascontiguousarray(rgb)

    # Preserve the former float32 operation order (selection, then outline,
    # then one final rounding) for pixel-exact output at arbitrary alphas.
    pixels = np.repeat(grayscale[active, np.newaxis], 3, axis=1).astype(np.float32)
    if selected_alpha != 0.0:
        selected_pixels = selected[active]
        if np.any(selected_pixels):
            selected_rgb = np.asarray(selected_color, dtype=np.float32)
            pixels[selected_pixels] = (
                pixels[selected_pixels] * (1.0 - selected_alpha) + selected_rgb * selected_alpha
            )
    if outline_alpha != 0.0:
        outline_pixels = outline[active]
        if np.any(outline_pixels):
            outline_rgb = np.asarray(outline_color, dtype=np.float32)
            pixels[outline_pixels] = (
                pixels[outline_pixels] * (1.0 - outline_alpha) + outline_rgb * outline_alpha
            )
    rgb[active] = np.rint(np.clip(pixels, 0.0, 255.0)).astype(np.uint8)
    return np.ascontiguousarray(rgb)
