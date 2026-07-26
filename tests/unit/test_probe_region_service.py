"""End-to-end synthetic proofs for persisted multi-shank region analysis."""

from __future__ import annotations

import hashlib
from uuid import uuid4

import numpy as np
import pytest

from mouse_brain_planner.analysis.probe_region_service import (
    ProbeRegionServiceError,
    analyze_probe_plan_regions,
    annotation_array_sha256,
)
from mouse_brain_planner.coordinates.anatomical_atlas import canonical_atlas_frame
from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.probe_models import NormalizedProbePlacement
from mouse_brain_planner.domain.probe_plan_models import (
    ProbePlanRecord,
    probe_plan_input_digest,
)
from mouse_brain_planner.domain.surgery_common import AnimalSurgeryContext
from mouse_brain_planner.domain.transform_models import AnatomicalPoint
from mouse_brain_planner.probes.catalog import (
    GENERIC_TEST_MODEL_ID,
    GENERIC_TEST_MODEL_VERSION,
    get_probe_model,
)
from mouse_brain_planner.surgery.trajectory import placement_from_target_angles_depth


def _metadata() -> AtlasMetadata:
    shape = (6, 6, 6)
    spacing = (1.0, 1.0, 1.0)
    return AtlasMetadata(
        atlas_key="synthetic_mouse_atlas",
        atlas_package_version="1",
        species="Mus musculus",
        citation="Hand-authored synthetic probe service fixture",
        source_url="https://example.invalid/synthetic-atlas",
        cache_path="/__synthetic_probe_service_fixture__",
        metadata_sha256=hashlib.sha256(b"probe-service-atlas").hexdigest(),
        resolution_um=spacing,
        shape_voxels=shape,
        source_annotation="synthetic-labels-v1",
        framework_name="Synthetic test atlas",
        symmetric=True,
        midline_ml_um=3,
        axes=(
            AtlasAxis(
                array_axis=0,
                anatomical_axis="AP",
                origin_direction="anterior",
                positive_direction="posterior",
                voxel_size_um=1,
            ),
            AtlasAxis(
                array_axis=1,
                anatomical_axis="DV",
                origin_direction="superior",
                positive_direction="inferior",
                voxel_size_um=1,
            ),
            AtlasAxis(
                array_axis=2,
                anatomical_axis="ML",
                origin_direction="right",
                positive_direction="left",
                voxel_size_um=1,
            ),
        ),
    )


def _plan(metadata: AtlasMetadata) -> ProbePlanRecord:
    model = get_probe_model(GENERIC_TEST_MODEL_ID, GENERIC_TEST_MODEL_VERSION)
    name = "Synthetic vertical plan"
    placement = placement_from_target_angles_depth(
        context=AnimalSurgeryContext(subject_id="mouse-test"),
        model=model,
        name=name,
        target=AnatomicalPoint(
            frame_id=canonical_atlas_frame(metadata).frame_id,
            ap_um=-2.5,
            ml_um=-2.5,
            dv_um=-4.5,
        ),
        azimuth_deg=0,
        elevation_deg=-90,
        insertion_depth_um=4,
        custom_geometry_acknowledged=True,
    )
    legacy_placement_payload = placement.model_dump(mode="python")
    legacy_placement_payload.pop("local_lateral_direction")
    legacy_placement_payload.pop("local_normal_direction")
    legacy_placement_payload.pop("model_to_placement_uniform_scale")
    placement = NormalizedProbePlacement.model_validate(legacy_placement_payload)
    target = UnprojectedBregmaTarget(label="target", ap_mm=0, ml_mm=0, dv_mm=-0.004)
    plan_uuid = uuid4()
    calibration_uuid = uuid4()
    digest = probe_plan_input_digest(
        plan_uuid=plan_uuid,
        plan_version=1,
        name=name,
        source_target=target,
        probe_model=model,
        placement=placement,
        calibration_uuid=calibration_uuid,
        calibration_version=1,
        calibration_sha256="a" * 64,
        atlas_metadata_sha256=metadata.metadata_sha256,
        projection_sha256="b" * 64,
    )
    return ProbePlanRecord(
        plan_uuid=plan_uuid,
        plan_version=1,
        name=name,
        source_target=target,
        probe_model=model,
        placement=placement,
        calibration_uuid=calibration_uuid,
        calibration_version=1,
        calibration_sha256="a" * 64,
        atlas_metadata_sha256=metadata.metadata_sha256,
        projection_sha256="b" * 64,
        input_sha256=digest,
    )


def test_plan_service_traverses_exact_regions_and_assigns_every_site() -> None:
    metadata = _metadata()
    annotation = np.ones(metadata.shape_voxels, dtype=np.uint16)
    annotation[:, 3:, :] = 2
    plan = _plan(metadata)
    regions = {
        1: RegionRecord(
            structure_id=1,
            acronym="UP",
            name="Upper synthetic layer",
            structure_id_path=(997, 1),
            rgb=(1, 2, 3),
        ),
        2: RegionRecord(
            structure_id=2,
            acronym="DOWN",
            name="Lower synthetic layer",
            structure_id_path=(997, 2),
            rgb=(4, 5, 6),
        ),
    }

    result = analyze_probe_plan_regions(
        plan=plan,
        annotation=annotation,
        metadata=metadata,
        annotation_sha256=annotation_array_sha256(annotation),
        annotation_version="synthetic-labels-v1",
        regions=regions,
    )

    assert len(result.shank_analyses) == 1
    analysis = result.shank_analyses[0]
    assert [segment.structure_id for segment in analysis.segments] == [1, 2]
    assert [segment.length_um for segment in analysis.segments] == pytest.approx([2.5, 1.5])
    assert len(analysis.site_assignments) == 16
    assert all(not assignment.inside_atlas for assignment in analysis.site_assignments)
    assert result.plan_input_sha256 == plan.input_sha256


def test_plan_service_rejects_self_rehashed_noncanonical_model_geometry() -> None:
    metadata = _metadata()
    plan = _plan(metadata)
    wider_shank = plan.probe_model.shanks[0].model_copy(update={"width_um": 700})
    forged_model = plan.probe_model.model_copy(update={"shanks": (wider_shank,)})
    input_sha256 = probe_plan_input_digest(
        plan_uuid=plan.plan_uuid,
        plan_version=plan.plan_version,
        name=plan.name,
        source_target=plan.source_target,
        probe_model=forged_model,
        placement=plan.placement,
        calibration_uuid=plan.calibration_uuid,
        calibration_version=plan.calibration_version,
        calibration_sha256=plan.calibration_sha256,
        atlas_metadata_sha256=plan.atlas_metadata_sha256,
        projection_sha256=plan.projection_sha256,
    )
    forged = ProbePlanRecord.model_validate(
        plan.model_copy(
            update={
                "probe_model": forged_model,
                "input_sha256": input_sha256,
            }
        ).model_dump(mode="python")
    )
    annotation = np.ones(metadata.shape_voxels, dtype=np.uint16)

    with pytest.raises(ProbeRegionServiceError, match="not exact source-pinned catalog"):
        analyze_probe_plan_regions(
            plan=forged,
            annotation=annotation,
            metadata=metadata,
            annotation_sha256=annotation_array_sha256(annotation),
            annotation_version="synthetic-labels-v1",
            regions={},
        )


def test_annotation_digest_is_layout_independent_and_content_sensitive() -> None:
    annotation = np.arange(64, dtype=np.uint16).reshape(4, 4, 4)

    expected = annotation_array_sha256(annotation)

    assert annotation_array_sha256(np.asfortranarray(annotation)) == expected
    changed = annotation.copy()
    changed[1, 2, 3] += 1
    assert annotation_array_sha256(changed) != expected
