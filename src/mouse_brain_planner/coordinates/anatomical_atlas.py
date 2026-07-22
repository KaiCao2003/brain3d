"""Explicit conversion between canonical anatomical and BrainGlobe atlas coordinates.

The planning domain uses named ``AP, ML, DV`` components with positive
anterior, right, and dorsal directions. BrainGlobe physical ASR coordinates
are stored as ``AP, DV, ML`` distances from the anterior/superior/right origin
and therefore increase posterior, inferior, and left. This module is the one
place where that order and sign boundary is crossed.
"""

from __future__ import annotations

from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.transform_models import (
    AnatomicalFrameDefinition,
    AnatomicalPoint,
    CoordinateSystemKind,
)


class AnatomicalAtlasConversionError(ValueError):
    """Raised when an anatomical point is not in the exact canonical atlas frame."""


def canonical_atlas_frame(metadata: AtlasMetadata) -> AnatomicalFrameDefinition:
    """Return the exact anterior/right/dorsal-positive frame for an atlas package."""

    return AnatomicalFrameDefinition(
        frame_id=(
            f"ATLAS_CANONICAL_AP_ML_DV_UM:{metadata.atlas_key}:{metadata.atlas_package_version}"
        ),
        kind=CoordinateSystemKind.ATLAS,
        origin_description=(
            "BrainGlobe ASR physical origin; canonical AP/ML/DV components are "
            "sign-negated from posterior/inferior/left-increasing physical distances"
        ),
        ap_positive_direction="anterior (opposite BrainGlobe physical AP increase)",
        ml_positive_direction="right (opposite BrainGlobe physical ML increase)",
        dv_positive_direction="dorsal/up (opposite BrainGlobe physical DV increase)",
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
    )


def brainglobe_physical_to_canonical_anatomical(
    point: BrainGlobePhysicalPoint,
    metadata: AtlasMetadata,
) -> AnatomicalPoint:
    """Convert bounded BrainGlobe ``[AP,DV,ML]`` physical data to ``AP,ML,DV``."""

    BrainGlobeAtlasSpace(metadata).physical_to_voxel(point)
    return AnatomicalPoint(
        frame_id=canonical_atlas_frame(metadata).frame_id,
        ap_um=-point.ap_um,
        ml_um=-point.ml_um,
        dv_um=-point.dv_um,
    )


def canonical_anatomical_to_brainglobe_physical(
    point: AnatomicalPoint,
    metadata: AtlasMetadata,
    *,
    require_inside: bool = True,
) -> BrainGlobePhysicalPoint:
    """Convert canonical ``AP,ML,DV`` data to BrainGlobe physical ASR data.

    Calibrated targets use the default bounded mode.  A finite probe segment
    may begin above/outside the atlas and is clipped later by the exact DDA;
    that caller must explicitly pass ``require_inside=False``.
    """

    expected_frame = canonical_atlas_frame(metadata).frame_id
    if point.frame_id != expected_frame:
        raise AnatomicalAtlasConversionError(
            f"anatomical atlas point frame {point.frame_id!r} does not match {expected_frame!r}"
        )
    physical = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=-point.ap_um,
        dv_um=-point.dv_um,
        ml_um=-point.ml_um,
    )
    if require_inside:
        BrainGlobeAtlasSpace(metadata).physical_to_voxel(physical)
    return physical
