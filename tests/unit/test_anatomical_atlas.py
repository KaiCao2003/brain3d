"""Golden tests for the centralized atlas order/sign conversion."""

from __future__ import annotations

import pytest
from tests.fixtures import make_allen_metadata_test_double

from mouse_brain_planner.coordinates.anatomical_atlas import (
    AnatomicalAtlasConversionError,
    brainglobe_physical_to_canonical_anatomical,
    canonical_anatomical_to_brainglobe_physical,
    canonical_atlas_frame,
)
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint


def test_brainglobe_ap_dv_ml_to_canonical_ap_ml_dv_sign_round_trip() -> None:
    atlas = make_allen_metadata_test_double(25)
    physical = BrainGlobePhysicalPoint(
        atlas_key=atlas.atlas_key,
        atlas_version=atlas.atlas_package_version,
        ap_um=1000,
        dv_um=2000,
        ml_um=3000,
    )

    canonical = brainglobe_physical_to_canonical_anatomical(physical, atlas)

    assert canonical.component_order == ("AP", "ML", "DV")
    assert canonical.as_ap_ml_dv() == (-1000, -3000, -2000)
    assert canonical_atlas_frame(atlas).ap_positive_direction.startswith("anterior")
    assert canonical_atlas_frame(atlas).ml_positive_direction.startswith("right")
    assert canonical_atlas_frame(atlas).dv_positive_direction.startswith("dorsal/up")
    assert canonical_anatomical_to_brainglobe_physical(canonical, atlas) == physical


def test_canonical_to_brainglobe_rejects_wrong_frame() -> None:
    atlas = make_allen_metadata_test_double(25)
    physical = BrainGlobePhysicalPoint(
        atlas_key=atlas.atlas_key,
        atlas_version=atlas.atlas_package_version,
        ap_um=1000,
        dv_um=2000,
        ml_um=3000,
    )
    canonical = brainglobe_physical_to_canonical_anatomical(physical, atlas)

    with pytest.raises(AnatomicalAtlasConversionError, match="does not match"):
        canonical_anatomical_to_brainglobe_physical(
            canonical.model_copy(update={"frame_id": "wrong"}),
            atlas,
        )
