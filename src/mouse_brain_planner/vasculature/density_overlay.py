"""Pure, fail-closed slice rendering for population vascular density."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage  # type: ignore[import-untyped]

from mouse_brain_planner.rendering.slice_renderer import SliceOrientation
from mouse_brain_planner.vasculature.reference_density import (
    BRAINGLOBE_ASR_FRAME_AP_DV_ML,
    ReferenceDensityValidationError,
    ReferenceVascularDensity,
)

REFERENCE_DENSITY_DISCLOSURE_LABEL = (
    "Symmetrized population reference vascular length density — four adult mice — "
    "100 µm local window — not subject-specific and not vessel paths"
)
REFERENCE_DENSITY_DV_MAXIMUM_LABEL = (
    "Symmetrized population reference vascular length density — DV maximum projection"
)
REFERENCE_DENSITY_PROJECTION_DISCLOSURE = (
    "Population reference from four fixed adult mice with a 100 µm local window; "
    "not subject-specific, not individual vessel paths, and not usable for vessel clearance"
)
REFERENCE_DENSITY_PROJECTION_WINDOW_LOW = 0.0
REFERENCE_DENSITY_PROJECTION_WINDOW_HIGH = 2.5
REFERENCE_DENSITY_PROJECTION_OPACITY = 0.65


class ReferenceDensityOverlayError(ReferenceDensityValidationError):
    """Raised when a density cannot be rendered without guessing."""


@dataclass(frozen=True, slots=True, eq=False)
class ReferenceDensityAtlasBinding:
    """One density validated against the exact loaded atlas grid."""

    density: ReferenceVascularDensity
    atlas_shape_asr: tuple[int, int, int]
    atlas_resolution_um: tuple[float, float, float]

    def __post_init__(self) -> None:
        shape = _validated_shape(self.atlas_shape_asr)
        resolution = _validated_resolution(self.atlas_resolution_um)
        _validate_density_against_atlas(self.density, shape, resolution)
        object.__setattr__(self, "atlas_shape_asr", shape)
        object.__setattr__(self, "atlas_resolution_um", resolution)


@dataclass(frozen=True, slots=True)
class ReferenceDensityHeatmapStyle:
    """Explicit reproducible scalar window and maximum overlay opacity."""

    opacity: float
    window_low: float
    window_high: float

    def __post_init__(self) -> None:
        opacity = float(self.opacity)
        low = float(self.window_low)
        high = float(self.window_high)
        if not math.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ReferenceDensityOverlayError("density heatmap opacity must be within [0, 1]")
        if not math.isfinite(low) or not math.isfinite(high):
            raise ReferenceDensityOverlayError("density heatmap window limits must be finite")
        if low < 0.0:
            raise ReferenceDensityOverlayError("density heatmap window low must be non-negative")
        if high <= low:
            raise ReferenceDensityOverlayError(
                "density heatmap window high must be greater than its low limit"
            )
        object.__setattr__(self, "opacity", opacity)
        object.__setattr__(self, "window_low", low)
        object.__setattr__(self, "window_high", high)


@dataclass(frozen=True, slots=True)
class ReferenceDensityDorsalProjection:
    """Transparent atlas-grid RGBA for a declared DV maximum projection."""

    rgba: NDArray[np.uint8]
    atlas_resolution_ap_um: float
    atlas_resolution_ml_um: float
    density_resolution_um: float
    row_axis: str = "AP"
    column_axis: str = "ML"
    projection_axis: str = "DV"
    projection_method: str = "maximum"
    display_label: str = REFERENCE_DENSITY_DV_MAXIMUM_LABEL
    disclosure: str = REFERENCE_DENSITY_PROJECTION_DISCLOSURE

    def __post_init__(self) -> None:
        if self.rgba.ndim != 3 or self.rgba.shape[2] != 4:
            raise ReferenceDensityOverlayError(
                "reference-density projection must have shape [AP,ML,4]"
            )
        if self.rgba.dtype != np.dtype(np.uint8):
            raise ReferenceDensityOverlayError("reference-density projection must use uint8 RGBA")
        if self.rgba.flags.writeable:
            raise ReferenceDensityOverlayError("reference-density projection must be immutable")


def sample_reference_density_plane(
    binding: ReferenceDensityAtlasBinding,
    orientation: SliceOrientation | str,
    slice_index: int,
) -> NDArray[np.float32]:
    """Sample an atlas-centred orthogonal plane from the coarser ASR field.

    Atlas and density coordinates share the half-open ASR physical extent.
    Every atlas voxel centre is mapped to a continuous density-centre index via
    ``physical_um / density_resolution_um - 0.5``.  Coordinates are explicitly
    clipped to the density grid before one bounded, vectorized linear sample.
    """

    normalized = SliceOrientation.coerce(orientation)
    if isinstance(slice_index, (bool, np.bool_)) or not isinstance(slice_index, (int, np.integer)):
        raise ReferenceDensityOverlayError("slice index must be an integer")
    index = int(slice_index)
    fixed_size = binding.atlas_shape_asr[normalized.fixed_axis]
    if index < 0 or index >= fixed_size:
        raise ReferenceDensityOverlayError(
            f"{normalized.fixed_axis_name} density slice {index} is outside [0, {fixed_size})"
        )

    density_values = binding.density.values_asr
    density_resolution = binding.density.provenance.output_voxel_size_um
    rows = binding.atlas_shape_asr[normalized.row_axis]
    columns = binding.atlas_shape_asr[normalized.column_axis]
    coordinates = np.empty((3, rows, columns), dtype=np.float64)
    fixed_coordinate = _atlas_centres_as_density_indices(
        np.asarray([index], dtype=np.float64),
        atlas_resolution_um=binding.atlas_resolution_um[normalized.fixed_axis],
        density_resolution_um=density_resolution,
        density_axis_size=density_values.shape[normalized.fixed_axis],
    )[0]
    row_coordinates = _atlas_centres_as_density_indices(
        np.arange(rows, dtype=np.float64),
        atlas_resolution_um=binding.atlas_resolution_um[normalized.row_axis],
        density_resolution_um=density_resolution,
        density_axis_size=density_values.shape[normalized.row_axis],
    )
    column_coordinates = _atlas_centres_as_density_indices(
        np.arange(columns, dtype=np.float64),
        atlas_resolution_um=binding.atlas_resolution_um[normalized.column_axis],
        density_resolution_um=density_resolution,
        density_axis_size=density_values.shape[normalized.column_axis],
    )
    coordinates[normalized.fixed_axis].fill(fixed_coordinate)
    coordinates[normalized.row_axis] = row_coordinates[:, np.newaxis]
    coordinates[normalized.column_axis] = column_coordinates[np.newaxis, :]

    sampled = cast(
        NDArray[np.float32],
        ndimage.map_coordinates(
            density_values,
            coordinates,
            output=np.float32,
            order=1,
            mode="nearest",
            prefilter=False,
        ),
    )
    expected_shape = (rows, columns)
    if sampled.shape != expected_shape:
        raise ReferenceDensityOverlayError(
            f"density sampler returned shape {sampled.shape}, expected {expected_shape}"
        )
    if not bool(np.all(np.isfinite(sampled))) or bool(np.any(sampled < 0.0)):
        raise ReferenceDensityOverlayError("sampled density contains invalid values")
    sampled.setflags(write=False)
    return sampled


def composite_reference_density_heatmap(
    base_rgb: NDArray[np.uint8],
    density_plane: NDArray[np.float32],
    style: ReferenceDensityHeatmapStyle,
) -> NDArray[np.uint8]:
    """Composite a deterministic red-to-magenta scalar heatmap over RGB.

    Positive values use the explicit fixed opacity.  The scalar window maps its
    low end to red and high end to magenta.  Exact zero is always transparent,
    and non-finite or negative input fails before any color is produced.
    """

    base = np.asarray(base_rgb)
    density = np.asarray(density_plane)
    if base.dtype != np.dtype(np.uint8) or base.ndim != 3 or base.shape[2] != 3:
        raise ReferenceDensityOverlayError("base image must be uint8 RGB with shape (H, W, 3)")
    if density.ndim != 2 or density.shape != base.shape[:2]:
        raise ReferenceDensityOverlayError(
            f"density plane shape {density.shape} must equal base image shape {base.shape[:2]}"
        )
    if not np.issubdtype(density.dtype, np.floating):
        raise ReferenceDensityOverlayError("density plane must use a floating-point dtype")
    if not bool(np.all(np.isfinite(density))):
        raise ReferenceDensityOverlayError("density plane contains non-finite values")
    if bool(np.any(density < 0.0)):
        raise ReferenceDensityOverlayError("density plane contains negative values")

    normalized = np.asarray(density, dtype=np.float64)
    normalized = (normalized - style.window_low) / (style.window_high - style.window_low)
    np.clip(normalized, 0.0, 1.0, out=normalized)
    heatmap = np.empty(base.shape, dtype=np.float64)
    heatmap[..., 0] = 255.0
    heatmap[..., 1] = 0.0
    heatmap[..., 2] = np.rint(normalized * 255.0)
    alpha = np.where(density > 0.0, style.opacity, 0.0)[..., np.newaxis]
    result = np.rint(base.astype(np.float64) * (1.0 - alpha) + heatmap * alpha)
    return np.ascontiguousarray(result, dtype=np.uint8)


def render_reference_density_dv_maximum_projection(
    binding: ReferenceDensityAtlasBinding,
    *,
    style: ReferenceDensityHeatmapStyle | None = None,
    brain_mask_ap_ml: NDArray[np.bool_] | None = None,
) -> ReferenceDensityDorsalProjection:
    """Render a transparent AP-by-ML PNG source using a declared DV maximum.

    The scalar maximum is computed on the prepared density grid and sampled at
    the loaded atlas AP/ML voxel centres. Alpha scales from zero to the declared
    maximum opacity, and an optional exact atlas annotation footprint clips the
    overlay to brain pixels. This is a display projection only: it deliberately
    preserves no DV location and therefore cannot represent vessel paths or
    support clearance calculations.
    """

    selected_style = style or ReferenceDensityHeatmapStyle(
        opacity=REFERENCE_DENSITY_PROJECTION_OPACITY,
        window_low=REFERENCE_DENSITY_PROJECTION_WINDOW_LOW,
        window_high=REFERENCE_DENSITY_PROJECTION_WINDOW_HIGH,
    )
    values = binding.density.values_asr
    maximum_ap_ml = np.max(values, axis=1)
    density_resolution = binding.density.provenance.output_voxel_size_um
    ap_size, _, ml_size = binding.atlas_shape_asr
    ap_coordinates = _atlas_centres_as_density_indices(
        np.arange(ap_size, dtype=np.float64),
        atlas_resolution_um=binding.atlas_resolution_um[0],
        density_resolution_um=density_resolution,
        density_axis_size=maximum_ap_ml.shape[0],
    )
    ml_coordinates = _atlas_centres_as_density_indices(
        np.arange(ml_size, dtype=np.float64),
        atlas_resolution_um=binding.atlas_resolution_um[2],
        density_resolution_um=density_resolution,
        density_axis_size=maximum_ap_ml.shape[1],
    )
    coordinates = np.empty((2, ap_size, ml_size), dtype=np.float64)
    coordinates[0] = ap_coordinates[:, np.newaxis]
    coordinates[1] = ml_coordinates[np.newaxis, :]
    sampled = cast(
        NDArray[np.float32],
        ndimage.map_coordinates(
            maximum_ap_ml,
            coordinates,
            output=np.float32,
            order=1,
            mode="nearest",
            prefilter=False,
        ),
    )
    if not bool(np.all(np.isfinite(sampled))) or bool(np.any(sampled < 0.0)):
        raise ReferenceDensityOverlayError(
            "reference-density DV maximum projection contains invalid values"
        )

    normalized = np.asarray(sampled, dtype=np.float64)
    normalized = (normalized - selected_style.window_low) / (
        selected_style.window_high - selected_style.window_low
    )
    np.clip(normalized, 0.0, 1.0, out=normalized)
    if brain_mask_ap_ml is None:
        brain_mask = np.ones((ap_size, ml_size), dtype=np.bool_)
    else:
        brain_mask = np.asarray(brain_mask_ap_ml)
        if brain_mask.dtype != np.dtype(np.bool_) or brain_mask.shape != (ap_size, ml_size):
            raise ReferenceDensityOverlayError(
                "dorsal brain mask must be boolean with the exact atlas AP/ML shape"
            )
    rgba = np.empty((ap_size, ml_size, 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 1] = 0
    rgba[..., 2] = np.rint(normalized * 255.0).astype(np.uint8)
    alpha = np.rint(normalized * selected_style.opacity * 255.0).astype(np.uint8)
    alpha[(sampled <= selected_style.window_low) | ~brain_mask] = 0
    rgba[..., 3] = alpha
    rgba.setflags(write=False)
    return ReferenceDensityDorsalProjection(
        rgba=rgba,
        atlas_resolution_ap_um=binding.atlas_resolution_um[0],
        atlas_resolution_ml_um=binding.atlas_resolution_um[2],
        density_resolution_um=density_resolution,
    )


def _validated_shape(shape: tuple[int, int, int]) -> tuple[int, int, int]:
    if len(shape) != 3:
        raise ReferenceDensityOverlayError("loaded atlas shape must contain AP, DV, and ML")
    normalized: list[int] = []
    for size in shape:
        if isinstance(size, bool):
            raise ReferenceDensityOverlayError("loaded atlas shape must contain integer sizes")
        try:
            integer = int(size)
        except (TypeError, ValueError, OverflowError) as error:
            raise ReferenceDensityOverlayError(
                "loaded atlas shape must contain integer sizes"
            ) from error
        if integer != size or integer <= 0:
            raise ReferenceDensityOverlayError(
                "loaded atlas shape must contain positive integer sizes"
            )
        normalized.append(integer)
    return cast(tuple[int, int, int], tuple(normalized))


def _validated_resolution(
    resolution: tuple[float, float, float],
) -> tuple[float, float, float]:
    if len(resolution) != 3:
        raise ReferenceDensityOverlayError(
            "loaded atlas resolution must contain AP, DV, and ML values"
        )
    normalized = tuple(float(value) for value in resolution)
    if any(not math.isfinite(value) or value <= 0.0 for value in normalized):
        raise ReferenceDensityOverlayError(
            "loaded atlas resolution must contain positive finite values"
        )
    return cast(tuple[float, float, float], normalized)


def _validate_density_against_atlas(
    density: ReferenceVascularDensity,
    atlas_shape: tuple[int, int, int],
    atlas_resolution: tuple[float, float, float],
) -> None:
    provenance = density.provenance
    alignment = provenance.template_alignment
    values = density.values_asr
    if provenance.output_frame != BRAINGLOBE_ASR_FRAME_AP_DV_ML:
        raise ReferenceDensityOverlayError("reference density must use BrainGlobe ASR order")
    if alignment.target_shape_asr != atlas_shape:
        raise ReferenceDensityOverlayError(
            "reference-density template-alignment target shape does not match loaded atlas: "
            f"{alignment.target_shape_asr} != {atlas_shape}"
        )
    if any(
        not _exact_physical_match(alignment.target_voxel_size_um, resolution)
        for resolution in atlas_resolution
    ):
        raise ReferenceDensityOverlayError(
            "reference-density template-alignment target resolution does not match loaded atlas"
        )
    if values.shape != provenance.output_shape_asr or values.dtype != np.dtype(np.float32):
        raise ReferenceDensityOverlayError(
            "reference-density array shape or dtype does not match prepared provenance"
        )
    if values.flags.writeable:
        raise ReferenceDensityOverlayError("reference-density array must remain read-only")
    if not bool(np.all(np.isfinite(values))):
        raise ReferenceDensityOverlayError("reference-density volume contains non-finite values")
    if bool(np.any(values < 0.0)):
        raise ReferenceDensityOverlayError("reference-density volume contains negative values")

    output_resolution = float(provenance.output_voxel_size_um)
    if not math.isfinite(output_resolution) or output_resolution <= 0.0:
        raise ReferenceDensityOverlayError(
            "reference-density output resolution must be positive and finite"
        )
    if any(output_resolution < resolution for resolution in atlas_resolution):
        raise ReferenceDensityOverlayError(
            "reference-density grid cannot have finer resolution than the loaded atlas"
        )
    output_extent = tuple(float(size * output_resolution) for size in provenance.output_shape_asr)
    atlas_extent = tuple(
        float(size * resolution)
        for size, resolution in zip(atlas_shape, atlas_resolution, strict=True)
    )
    if any(
        not _exact_physical_match(actual, recorded)
        for actual, recorded in zip(output_extent, provenance.output_extent_um_asr, strict=True)
    ):
        raise ReferenceDensityOverlayError(
            "reference-density output extent does not match its recorded provenance"
        )
    if any(
        not _exact_physical_match(density_extent, loaded_extent)
        for density_extent, loaded_extent in zip(output_extent, atlas_extent, strict=True)
    ):
        raise ReferenceDensityOverlayError(
            "reference-density physical extent does not match the loaded atlas"
        )

    correlation = float(alignment.correlation)
    minimum = float(alignment.minimum_correlation)
    if (
        not math.isfinite(correlation)
        or not math.isfinite(minimum)
        or not 0.0 < minimum <= 1.0
        or correlation < minimum
        or correlation > 1.0
    ):
        raise ReferenceDensityOverlayError(
            "reference-density template-alignment correlation is not valid"
        )
    source = provenance.source
    if (
        not provenance.ml_symmetrized
        or provenance.subject_specific
        or provenance.contains_individual_vessel_paths
        or provenance.supports_vessel_clearance
        or source.population_subject_count != 4
        or not _exact_physical_match(source.rolling_window_um, 100.0)
        or source.subject_specific
        or source.contains_individual_vessel_paths
        or source.supports_vessel_clearance
    ):
        raise ReferenceDensityOverlayError(
            "reference-density safety provenance does not support the required disclosure"
        )


def _atlas_centres_as_density_indices(
    atlas_indices: NDArray[np.float64],
    *,
    atlas_resolution_um: float,
    density_resolution_um: float,
    density_axis_size: int,
) -> NDArray[np.float64]:
    coordinates = (atlas_indices + np.float64(0.5)) * np.float64(atlas_resolution_um) / np.float64(
        density_resolution_um
    ) - np.float64(0.5)
    return np.clip(coordinates, 0.0, float(density_axis_size - 1))


def _exact_physical_match(first: float, second: float) -> bool:
    return math.isclose(float(first), float(second), rel_tol=0.0, abs_tol=1e-9)
