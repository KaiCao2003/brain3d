"""Annotation-authoritative overlays for one selected Allen ontology region."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.rendering.slice_renderer import RGBColor

REGION_OVERLAY_ALGORITHM_VERSION: Final = "annotation-descendants-filled-outline-v1"
REGION_OVERLAY_FILL_ALPHA: Final = 104
REGION_OVERLAY_OUTLINE_ALPHA: Final = 255
_DORSAL_AP_CHUNK_SIZE: Final = 16


@dataclass(frozen=True, slots=True)
class RegionOverlayFrame:
    """A straight-alpha RGBA overlay and its exact annotation masks."""

    selected: NDArray[np.bool_]
    outline: NDArray[np.bool_]
    rgba: NDArray[np.uint8]


def render_region_overlay(
    annotation_2d: NDArray[Any],
    *,
    included_structure_ids: Collection[int],
    color: RGBColor,
) -> RegionOverlayFrame:
    """Render a filled and two-sided outline from exact annotation IDs.

    ``included_structure_ids`` is supplied by the ontology-aware bridge and
    normally contains the selected structure plus every descendant. This
    matters because Allen annotation voxels often store leaf IDs rather than a
    selected parent ID.
    """

    annotation = np.asarray(annotation_2d)
    if annotation.ndim != 2:
        raise ValueError("region overlay annotation must be two-dimensional")
    if not np.issubdtype(annotation.dtype, np.integer):
        raise TypeError("region overlay annotation must use an integer dtype")
    ids = _validated_structure_ids(included_structure_ids)
    selected_color = _validated_color(color)

    if len(ids) == 1:
        selected = annotation == ids[0]
    else:
        selected = np.isin(annotation, ids)
    selected = np.asarray(selected, dtype=np.bool_)
    outline = _two_sided_mask_outline(selected)

    rgba = np.zeros((*annotation.shape, 4), dtype=np.uint8)
    if np.any(selected):
        rgba[selected, :3] = selected_color
        rgba[selected, 3] = REGION_OVERLAY_FILL_ALPHA
    if np.any(outline):
        # A lightened version of the Allen structure color remains legible on
        # both bright reference tissue and the black exterior.
        outline_color = tuple(
            min(255, round(component * 0.65 + 255 * 0.35)) for component in selected_color
        )
        rgba[outline, :3] = outline_color
        rgba[outline, 3] = REGION_OVERLAY_OUTLINE_ALPHA

    selected.setflags(write=False)
    outline.setflags(write=False)
    rgba.setflags(write=False)
    return RegionOverlayFrame(
        selected=selected,
        outline=outline,
        rgba=np.ascontiguousarray(rgba),
    )


def dorsal_surface_annotation(
    annotation_asr: NDArray[Any],
    *,
    ap_chunk_size: int = _DORSAL_AP_CHUNK_SIZE,
) -> NDArray[Any]:
    """Return the first nonzero DV label on every AP/ML column.

    The result matches :func:`render_dorsal_surface`, but this implementation
    works in bounded AP chunks so selecting a region does not allocate an
    atlas-sized temporary boolean volume.
    """

    annotation = np.asarray(annotation_asr)
    if annotation.ndim != 3 or any(size <= 0 for size in annotation.shape):
        raise ValueError("dorsal annotation projection requires a non-empty [AP,DV,ML] volume")
    if not np.issubdtype(annotation.dtype, np.integer):
        raise TypeError("dorsal annotation projection requires an integer volume")
    if isinstance(ap_chunk_size, bool) or not isinstance(ap_chunk_size, int):
        raise TypeError("ap_chunk_size must be an integer")
    if ap_chunk_size <= 0:
        raise ValueError("ap_chunk_size must be positive")

    ap_count, _, ml_count = annotation.shape
    surface = np.zeros((ap_count, ml_count), dtype=annotation.dtype)
    for start in range(0, ap_count, ap_chunk_size):
        stop = min(ap_count, start + ap_chunk_size)
        chunk = annotation[start:stop]
        annotated = chunk != 0
        brain_mask = np.any(annotated, axis=1)
        first_dv = np.argmax(annotated, axis=1)
        labels = np.take_along_axis(
            chunk,
            first_dv[:, np.newaxis, :],
            axis=1,
        )[:, 0, :]
        labels = np.asarray(labels).copy()
        labels[~brain_mask] = 0
        surface[start:stop] = labels
    surface.setflags(write=False)
    return surface


def _two_sided_mask_outline(mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
    outline = np.zeros(mask.shape, dtype=np.bool_)
    vertical_changes = mask[1:, :] != mask[:-1, :]
    outline[1:, :] |= vertical_changes
    outline[:-1, :] |= vertical_changes
    horizontal_changes = mask[:, 1:] != mask[:, :-1]
    outline[:, 1:] |= horizontal_changes
    outline[:, :-1] |= horizontal_changes
    # Treat the image exterior as unselected so a selected structure clipped by
    # a slice edge still has a closed visible boundary.
    outline[0, :] |= mask[0, :]
    outline[-1, :] |= mask[-1, :]
    outline[:, 0] |= mask[:, 0]
    outline[:, -1] |= mask[:, -1]
    return outline


def _validated_structure_ids(values: Collection[int]) -> tuple[int, ...]:
    normalized: set[int] = set()
    for value in values:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise TypeError("included structure IDs must be integers")
        structure_id = int(value)
        if structure_id <= 0:
            raise ValueError("included structure IDs must be positive")
        normalized.add(structure_id)
    if not normalized:
        raise ValueError("included structure IDs must not be empty")
    return tuple(sorted(normalized))


def _validated_color(value: RGBColor) -> RGBColor:
    if len(value) != 3 or any(
        isinstance(component, (bool, np.bool_))
        or not isinstance(component, (int, np.integer))
        or int(component) < 0
        or int(component) > 255
        for component in value
    ):
        raise ValueError("region overlay color must contain three bytes")
    return (int(value[0]), int(value[1]), int(value[2]))
