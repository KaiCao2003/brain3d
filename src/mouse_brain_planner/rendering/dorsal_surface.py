"""Vectorized dorsal atlas-surface projection in BrainGlobe ASR coordinates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.rendering.slice_renderer import annotation_outline, normalize_grayscale


@dataclass(frozen=True, slots=True)
class DorsalSurfaceFrame:
    """Population-atlas dorsal surface sampled along each AP/ML column."""

    reference: NDArray[Any]
    annotation: NDArray[Any]
    surface_dv_index: NDArray[np.int32]
    brain_mask: NDArray[np.bool_]
    grayscale: NDArray[np.uint8]
    rgb: NDArray[np.uint8]
    dv_resolution_um: float
    row_axis: str = "AP"
    column_axis: str = "ML"
    display_label: str = "Allen atlas dorsal surface projection — not a subject skull surface"


def render_dorsal_surface(
    reference_asr: NDArray[Any],
    annotation_asr: NDArray[Any],
    *,
    resolution_um: tuple[float, float, float],
) -> DorsalSurfaceFrame:
    """Sample the first annotated DV voxel for every atlas AP/ML column.

    BrainGlobe ASR DV increases inferiorly, so the smallest annotated DV index
    is the atlas dorsal boundary for that AP/ML column.  This is a population
    atlas projection; it does not model an individual animal's skull or brain
    deformation.
    """

    reference = np.asarray(reference_asr)
    annotation = np.asarray(annotation_asr)
    if reference.ndim != 3 or annotation.ndim != 3:
        raise ValueError("dorsal projection requires three-dimensional [AP,DV,ML] volumes")
    if reference.shape != annotation.shape or any(size <= 0 for size in reference.shape):
        raise ValueError("dorsal reference and annotation must have the same non-empty ASR shape")
    if not np.issubdtype(reference.dtype, np.number):
        raise TypeError("dorsal reference must use a numeric dtype")
    if not np.issubdtype(annotation.dtype, np.integer):
        raise TypeError("dorsal annotation must use an integer dtype")
    if len(resolution_um) != 3 or any(
        not math.isfinite(float(value)) or float(value) <= 0 for value in resolution_um
    ):
        raise ValueError("resolution_um must contain three positive finite ASR values")

    annotated = annotation != 0
    brain_mask = np.any(annotated, axis=1)
    surface_dv_index = np.argmax(annotated, axis=1).astype(np.int32)
    gather = surface_dv_index[:, np.newaxis, :]
    surface_reference = np.take_along_axis(reference, gather, axis=1)[:, 0, :].copy()
    surface_annotation = np.take_along_axis(annotation, gather, axis=1)[:, 0, :].copy()
    surface_reference[~brain_mask] = 0
    surface_annotation[~brain_mask] = 0

    grayscale = normalize_grayscale(surface_reference)
    grayscale[~brain_mask] = 0
    rgb = np.repeat(grayscale[..., np.newaxis], 3, axis=2)
    outline = annotation_outline(surface_annotation)
    outline &= brain_mask
    if np.any(outline):
        base = rgb[outline].astype(np.float32)
        orange = np.asarray((255.0, 170.0, 0.0), dtype=np.float32)
        rgb[outline] = np.rint(base * 0.25 + orange * 0.75).astype(np.uint8)

    for array in (
        surface_reference,
        surface_annotation,
        surface_dv_index,
        brain_mask,
        grayscale,
        rgb,
    ):
        array.setflags(write=False)
    return DorsalSurfaceFrame(
        reference=surface_reference,
        annotation=surface_annotation,
        surface_dv_index=surface_dv_index,
        brain_mask=brain_mask,
        grayscale=grayscale,
        rgb=rgb,
        dv_resolution_um=float(resolution_um[1]),
    )
