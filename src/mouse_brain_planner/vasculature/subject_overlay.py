"""Render a registered subject dorsal image on the exact atlas AP/ML grid.

This module performs display resampling only.  It never segments vessels,
computes vessel clearance, or changes the byte-preserved source image.  Output
rows are atlas AP and output columns are atlas ML, both sampled at physical
voxel centres in the BrainGlobe ASR frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from scipy.ndimage import map_coordinates  # type: ignore[import-untyped]

from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.vessel_models import (
    DorsalVascularRegistration,
    SubjectVascularImage,
)
from mouse_brain_planner.vasculature.subject_image import verify_subject_vascular_image


class SubjectOverlayRenderError(ValueError):
    """Raised when a subject image cannot be rendered without guessing."""


@dataclass(frozen=True, slots=True)
class RegisteredDorsalOverlay:
    """One RGBA raster on an explicit BrainGlobe dorsal-plane grid."""

    rgba: NDArray[np.uint8]
    atlas_key: str
    atlas_version: str
    resolution_ap_um: float
    resolution_ml_um: float
    row_axis: str = "AP"
    column_axis: str = "ML"
    subject_specific: bool = True
    display_label: str = "Subject-specific surface image — registration must be verified"

    def __post_init__(self) -> None:
        if self.rgba.ndim != 3 or self.rgba.shape[2] != 4:
            raise SubjectOverlayRenderError("registered dorsal overlay must have shape [AP,ML,4]")
        if self.rgba.dtype != np.dtype(np.uint8):
            raise SubjectOverlayRenderError("registered dorsal overlay must use uint8 RGBA")
        if self.rgba.flags.writeable:
            raise SubjectOverlayRenderError("registered dorsal overlay must be immutable")


def render_registered_dorsal_overlay(
    *,
    image: SubjectVascularImage,
    registration: DorsalVascularRegistration,
    package_root: str | Path,
    atlas: AtlasMetadata,
    opacity: float = 0.65,
) -> RegisteredDorsalOverlay:
    """Resample a verified source image onto the loaded atlas dorsal grid.

    The stored registration maps ``[image column px, image row px, 1]`` to
    ``[atlas AP um, atlas ML um, 1]``.  This function evaluates its inverse at
    every atlas AP/ML voxel centre and uses bounded bilinear interpolation.
    Pixels outside the registered source image are transparent.
    """

    _validate_contract(image=image, registration=registration, atlas=atlas, opacity=opacity)
    source_path = verify_subject_vascular_image(image, package_root=package_root)
    source = _decode_rgba(
        source_path,
        expected_width=image.width_px,
        expected_height=image.height_px,
    )

    matrix = np.asarray(registration.matrix_row_major, dtype=np.float64).reshape(3, 3)
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as error:
        raise SubjectOverlayRenderError("subject dorsal registration is noninvertible") from error
    if not np.all(np.isfinite(inverse)):
        raise SubjectOverlayRenderError("subject dorsal registration inverse is not finite")

    ap_size, _, ml_size = atlas.shape_voxels
    ap_resolution, _, ml_resolution = atlas.resolution_um
    ap_centres = (np.arange(ap_size, dtype=np.float64) + 0.5) * ap_resolution
    ml_centres = (np.arange(ml_size, dtype=np.float64) + 0.5) * ml_resolution
    ap_grid, ml_grid = np.meshgrid(ap_centres, ml_centres, indexing="ij")
    destination = np.stack(
        (ap_grid.reshape(-1), ml_grid.reshape(-1), np.ones(ap_grid.size, dtype=np.float64))
    )
    mapped = inverse @ destination
    denominator = mapped[2]
    if np.any(np.abs(denominator) <= 1e-12):
        raise SubjectOverlayRenderError(
            "registration inverse produced an invalid homogeneous scale"
        )
    source_columns = mapped[0] / denominator
    source_rows = mapped[1] / denominator
    if not np.all(np.isfinite(source_columns)) or not np.all(np.isfinite(source_rows)):
        raise SubjectOverlayRenderError(
            "registration inverse produced non-finite image coordinates"
        )
    source_columns = _clamp_boundary_roundoff(source_columns, image.width_px)
    source_rows = _clamp_boundary_roundoff(source_rows, image.height_px)

    coordinates = np.vstack((source_rows, source_columns))
    sampled = np.empty((ap_size, ml_size, 4), dtype=np.float64)
    source_float = np.asarray(source, dtype=np.float64)
    for channel in range(4):
        sampled[..., channel] = map_coordinates(
            source_float[..., channel],
            coordinates,
            order=1,
            mode="constant",
            cval=0.0,
            prefilter=False,
        ).reshape(ap_size, ml_size)

    sampled[..., 3] *= float(opacity)
    rgba = np.rint(np.clip(sampled, 0.0, 255.0)).astype(np.uint8)
    rgba.setflags(write=False)
    return RegisteredDorsalOverlay(
        rgba=rgba,
        atlas_key=atlas.atlas_key,
        atlas_version=atlas.atlas_package_version,
        resolution_ap_um=float(ap_resolution),
        resolution_ml_um=float(ml_resolution),
    )


def _validate_contract(
    *,
    image: SubjectVascularImage,
    registration: DorsalVascularRegistration,
    atlas: AtlasMetadata,
    opacity: float,
) -> None:
    if registration.image_uuid != image.image_uuid:
        raise SubjectOverlayRenderError("registration belongs to a different subject image")
    expected_identity = (atlas.atlas_key, atlas.atlas_package_version)
    actual_identity = (registration.atlas_key, registration.atlas_version)
    if actual_identity != expected_identity:
        raise SubjectOverlayRenderError(
            f"registration atlas {actual_identity} does not match loaded atlas {expected_identity}"
        )
    if not registration.laterality_confirmed_by_user:
        raise SubjectOverlayRenderError(
            "subject image laterality must be confirmed before displaying the registered overlay"
        )
    if not math.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
        raise SubjectOverlayRenderError("subject overlay opacity must be finite and within [0, 1]")


def _decode_rgba(path: Path, *, expected_width: int, expected_height: int) -> NDArray[np.uint8]:
    try:
        with Image.open(path) as opened:
            opened.seek(0)
            decoded = np.asarray(opened.convert("RGBA"), dtype=np.uint8)
    except OSError as error:
        raise SubjectOverlayRenderError("verified subject image could not be decoded") from error
    if decoded.shape != (expected_height, expected_width, 4):
        raise SubjectOverlayRenderError(
            "decoded subject image dimensions differ from its verified import metadata"
        )
    return decoded


def _clamp_boundary_roundoff(values: NDArray[np.float64], size: int) -> NDArray[np.float64]:
    """Clamp only sub-nanopixel inverse-transform error at valid edge samples."""

    result = values.copy()
    tolerance_px = 1e-9
    lower = (result < 0.0) & (result >= -tolerance_px)
    upper_bound = float(size - 1)
    upper = (result > upper_bound) & (result <= upper_bound + tolerance_px)
    result[lower] = 0.0
    result[upper] = upper_bound
    return result
