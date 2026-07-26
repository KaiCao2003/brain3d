"""Multi-shank adapter from persisted probe plans to exact atlas DDA."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.analysis.atlas_axis_order import (
    brain_globe_physical_ap_dv_ml_to_domain_ap_ml_dv,
)
from mouse_brain_planner.analysis.region_traversal import analyze_probe_regions
from mouse_brain_planner.coordinates.anatomical_atlas import (
    canonical_anatomical_to_brainglobe_physical,
)
from mouse_brain_planner.domain.atlas_models import AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.probe_models import PlacedProbeShank, PlacedRecordingSite
from mouse_brain_planner.domain.probe_plan_models import (
    ProbePlanRecord,
    ProbeRegionAnalysisBundle,
    probe_region_bundle_digest,
)
from mouse_brain_planner.domain.region_models import (
    AtlasPhysicalPointAPMLDV,
    AtlasRecordingSitePoint,
    CalibratedProbeShankSegment,
)
from mouse_brain_planner.domain.transform_models import AnatomicalPoint
from mouse_brain_planner.probes.catalog import (
    ProbeModelCatalogSnapshotError,
    validate_probe_model_catalog_snapshot,
)
from mouse_brain_planner.surgery.trajectory import (
    placed_recording_sites,
    placed_shank_centerlines,
)


class ProbeRegionServiceError(ValueError):
    """Raised when a persisted plan cannot be analyzed without guessing."""


def analyze_probe_plan_regions(
    *,
    plan: ProbePlanRecord,
    annotation: NDArray[np.integer[Any]],
    metadata: AtlasMetadata,
    annotation_sha256: str,
    annotation_version: str,
    regions: Mapping[int, RegionRecord],
) -> ProbeRegionAnalysisBundle:
    """Analyze every placed shank and recording site in stable model order."""

    if plan.atlas_metadata_sha256 != metadata.metadata_sha256:
        raise ProbeRegionServiceError("probe plan atlas digest does not match loaded atlas")
    try:
        validate_probe_model_catalog_snapshot(plan.probe_model)
    except ProbeModelCatalogSnapshotError as error:
        raise ProbeRegionServiceError(
            "probe model snapshot is not exact source-pinned catalog geometry"
        ) from error
    if plan.surface_relative_input is not None:
        transform_id = (
            "atlas-surface:"
            f"{plan.surface_relative_input.bregma_reference.reference_id}:"
            f"{plan.surface_relative_input.annotation_sha256}:"
            f"{plan.projection_sha256}"
        )
    else:
        transform_id = (
            f"calibration:{plan.calibration_uuid}:"
            f"v{plan.calibration_version}:{plan.calibration_sha256}"
        )
    shanks = placed_shank_centerlines(plan.probe_model, plan.placement)
    sites = placed_recording_sites(plan.probe_model, plan.placement)
    sites_by_shank: dict[str, list[AtlasRecordingSitePoint]] = {
        shank.shank_id: [] for shank in shanks
    }
    for site in sites:
        try:
            sites_by_shank[site.shank_id].append(
                _atlas_site(site, metadata=metadata, transform_id=transform_id)
            )
        except KeyError as error:
            raise ProbeRegionServiceError(
                f"recording site references unknown placed shank {site.shank_id!r}"
            ) from error
    analyses = tuple(
        analyze_probe_regions(
            annotation=annotation,
            metadata=metadata,
            annotation_sha256=annotation_sha256,
            annotation_version=annotation_version,
            segment=_atlas_shank(shank, metadata=metadata, transform_id=transform_id),
            regions=regions,
            recording_sites=tuple(sites_by_shank[shank.shank_id]),
        )
        for shank in shanks
    )
    digest = probe_region_bundle_digest(
        plan_uuid=plan.plan_uuid,
        plan_version=plan.plan_version,
        plan_input_sha256=plan.input_sha256,
        shank_analyses=analyses,
    )
    return ProbeRegionAnalysisBundle(
        plan_uuid=plan.plan_uuid,
        plan_version=plan.plan_version,
        plan_input_sha256=plan.input_sha256,
        shank_analyses=analyses,
        analysis_sha256=digest,
    )


def annotation_array_sha256(annotation: NDArray[np.generic]) -> str:
    """Hash array bytes without copying a contiguous production atlas volume."""

    if not isinstance(annotation, np.ndarray) or annotation.ndim != 3:
        raise ProbeRegionServiceError("annotation digest requires one 3-D NumPy array")
    digest = hashlib.sha256()
    if annotation.flags.c_contiguous:
        digest.update(memoryview(annotation).cast("B"))
    else:
        for slab in annotation:
            digest.update(memoryview(np.ascontiguousarray(slab)).cast("B"))
    return digest.hexdigest()


def _atlas_shank(
    shank: PlacedProbeShank,
    *,
    metadata: AtlasMetadata,
    transform_id: str,
) -> CalibratedProbeShankSegment:
    return CalibratedProbeShankSegment(
        placement_uuid=shank.placement_uuid,
        probe_model_id=shank.probe_model_id,
        probe_model_version=shank.probe_model_version,
        shank_id=shank.shank_id,
        entry=_atlas_point(
            shank.entry,
            metadata=metadata,
            transform_id=transform_id,
        ),
        tip=_atlas_point(
            shank.tip,
            metadata=metadata,
            transform_id=transform_id,
        ),
    )


def _atlas_site(
    site: PlacedRecordingSite,
    *,
    metadata: AtlasMetadata,
    transform_id: str,
) -> AtlasRecordingSitePoint:
    return AtlasRecordingSitePoint(
        placement_uuid=site.placement_uuid,
        probe_model_id=site.probe_model_id,
        probe_model_version=site.probe_model_version,
        shank_id=site.shank_id,
        site_id=site.site_id,
        point=_atlas_point(site.point, metadata=metadata, transform_id=transform_id),
    )


def _atlas_point(
    point: AnatomicalPoint,
    *,
    metadata: AtlasMetadata,
    transform_id: str,
) -> AtlasPhysicalPointAPMLDV:
    if not isinstance(point, AnatomicalPoint):
        raise TypeError("probe geometry point must be an AnatomicalPoint")
    physical = canonical_anatomical_to_brainglobe_physical(
        point,
        metadata,
        require_inside=False,
    )
    return brain_globe_physical_ap_dv_ml_to_domain_ap_ml_dv(
        ap_um=physical.ap_um,
        dv_um=physical.dv_um,
        ml_um=physical.ml_um,
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        coordinate_transform_id=transform_id,
    )
