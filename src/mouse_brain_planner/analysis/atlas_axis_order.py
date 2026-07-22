"""Single conversion boundary between domain AP/ML/DV and BrainGlobe AP/DV/ML.

These helpers perform an axis permutation only.  They never infer bregma,
change the declared BrainGlobe ASR origin, or silently flip signs.
"""

from __future__ import annotations

from mouse_brain_planner.domain.region_models import AtlasPhysicalPointAPMLDV


def domain_ap_ml_dv_to_brain_globe_physical_ap_dv_ml(
    point: AtlasPhysicalPointAPMLDV,
) -> tuple[float, float, float]:
    """Return one atlas-native point in BrainGlobe array-axis order."""

    if not isinstance(point, AtlasPhysicalPointAPMLDV):
        raise TypeError("point must be an AtlasPhysicalPointAPMLDV")
    return (point.ap_um, point.dv_um, point.ml_um)


def brain_globe_physical_ap_dv_ml_to_domain_ap_ml_dv(
    *,
    ap_um: float,
    dv_um: float,
    ml_um: float,
    atlas_key: str,
    atlas_version: str,
    coordinate_transform_id: str,
) -> AtlasPhysicalPointAPMLDV:
    """Build a domain-ordered point from explicitly named BrainGlobe values."""

    return AtlasPhysicalPointAPMLDV(
        atlas_key=atlas_key,
        atlas_version=atlas_version,
        coordinate_transform_id=coordinate_transform_id,
        ap_um=ap_um,
        ml_um=ml_um,
        dv_um=dv_um,
    )
