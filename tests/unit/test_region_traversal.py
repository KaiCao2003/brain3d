"""Synthetic proofs for exact finite 3-D annotation traversal."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from uuid import UUID

import numpy as np
import pytest
from pydantic import ValidationError

from mouse_brain_planner.analysis.atlas_axis_order import (
    brain_globe_physical_ap_dv_ml_to_domain_ap_ml_dv,
    domain_ap_ml_dv_to_brain_globe_physical_ap_dv_ml,
)
from mouse_brain_planner.analysis.region_traversal import (
    REGION_TRAVERSAL_ALGORITHM_VERSION,
    RegionTraversalInputError,
    analyze_probe_regions,
)
from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.region_models import (
    AtlasPhysicalPointAPMLDV,
    AtlasRecordingSitePoint,
    CalibratedProbeShankSegment,
    ProbeRegionAnalysis,
    TraversalHemisphere,
    TraversalLocation,
)

PLACEMENT_UUID = UUID("12345678-1234-4123-8123-123456789abc")
TRANSFORM_ID = "synthetic-reviewed-atlas-transform-v1"
ANNOTATION_SHA256 = "a" * 64
ANNOTATION_VERSION = "synthetic-hand-authored-v1"


def _metadata(
    *,
    shape: tuple[int, int, int],
    spacing: tuple[float, float, float] = (10.0, 20.0, 30.0),
) -> AtlasMetadata:
    identity = f"synthetic:{shape}:{spacing}".encode()
    return AtlasMetadata(
        atlas_key="synthetic_mouse_atlas",
        atlas_package_version="1",
        species="Mus musculus",
        citation="Hand-authored synthetic traversal fixture",
        source_url="https://example.invalid/synthetic-atlas",
        cache_path="/__synthetic_region_traversal_fixture__",
        metadata_sha256=hashlib.sha256(identity).hexdigest(),
        resolution_um=spacing,
        shape_voxels=shape,
        standardized_orientation="asr",
        source_annotation="synthetic labels",
        framework_name="Synthetic test atlas",
        symmetric=True,
        midline_ml_um=shape[2] * spacing[2] / 2.0,
        axes=(
            AtlasAxis(
                array_axis=0,
                anatomical_axis="AP",
                origin_direction="anterior",
                positive_direction="posterior",
                voxel_size_um=spacing[0],
            ),
            AtlasAxis(
                array_axis=1,
                anatomical_axis="DV",
                origin_direction="superior",
                positive_direction="inferior",
                voxel_size_um=spacing[1],
            ),
            AtlasAxis(
                array_axis=2,
                anatomical_axis="ML",
                origin_direction="right",
                positive_direction="left",
                voxel_size_um=spacing[2],
            ),
        ),
    )


def _point(
    metadata: AtlasMetadata,
    *,
    ap_um: float,
    ml_um: float,
    dv_um: float,
    transform_id: str = TRANSFORM_ID,
) -> AtlasPhysicalPointAPMLDV:
    return AtlasPhysicalPointAPMLDV(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        coordinate_transform_id=transform_id,
        ap_um=ap_um,
        ml_um=ml_um,
        dv_um=dv_um,
    )


def _segment(
    metadata: AtlasMetadata,
    *,
    entry: tuple[float, float, float],
    tip: tuple[float, float, float],
) -> CalibratedProbeShankSegment:
    """Build from domain-ordered ``(AP, ML, DV)`` fixture coordinates."""

    return CalibratedProbeShankSegment(
        placement_uuid=PLACEMENT_UUID,
        probe_model_id="synthetic-probe",
        probe_model_version="1",
        shank_id="shank-0",
        entry=_point(metadata, ap_um=entry[0], ml_um=entry[1], dv_um=entry[2]),
        tip=_point(metadata, ap_um=tip[0], ml_um=tip[1], dv_um=tip[2]),
    )


def _site(
    metadata: AtlasMetadata,
    site_id: str,
    *,
    ap_um: float,
    ml_um: float,
    dv_um: float,
) -> AtlasRecordingSitePoint:
    return AtlasRecordingSitePoint(
        placement_uuid=PLACEMENT_UUID,
        probe_model_id="synthetic-probe",
        probe_model_version="1",
        shank_id="shank-0",
        site_id=site_id,
        point=_point(metadata, ap_um=ap_um, ml_um=ml_um, dv_um=dv_um),
    )


def _regions(*structure_ids: int) -> dict[int, RegionRecord]:
    return {
        structure_id: RegionRecord(
            structure_id=structure_id,
            acronym=f"R{structure_id}",
            name=f"Synthetic region {structure_id}",
            structure_id_path=(997, structure_id),
            rgb=(structure_id % 256, (structure_id * 2) % 256, (structure_id * 3) % 256),
        )
        for structure_id in structure_ids
    }


def _analyze(
    annotation: np.ndarray,
    metadata: AtlasMetadata,
    segment: CalibratedProbeShankSegment,
    *,
    regions: Mapping[int, RegionRecord] | None = None,
    sites: Sequence[AtlasRecordingSitePoint] = (),
) -> ProbeRegionAnalysis:
    return analyze_probe_regions(
        annotation=annotation,
        metadata=metadata,
        annotation_sha256=ANNOTATION_SHA256,
        annotation_version=ANNOTATION_VERSION,
        segment=segment,
        regions={} if regions is None else regions,
        recording_sites=sites,
    )


def _voxel_indices(result: ProbeRegionAnalysis) -> list[tuple[int, int, int]]:
    return [interval.voxel.as_tuple() for interval in result.voxel_intervals]


def test_axis_conversion_is_centralized_and_round_trips_without_sign_guessing() -> None:
    metadata = _metadata(shape=(2, 2, 2))
    point = _point(metadata, ap_um=11.0, ml_um=33.0, dv_um=22.0)

    brain_globe_order = domain_ap_ml_dv_to_brain_globe_physical_ap_dv_ml(point)
    round_trip = brain_globe_physical_ap_dv_ml_to_domain_ap_ml_dv(
        ap_um=brain_globe_order[0],
        dv_um=brain_globe_order[1],
        ml_um=brain_globe_order[2],
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        coordinate_transform_id=TRANSFORM_ID,
    )

    assert point.as_ap_ml_dv() == (11.0, 33.0, 22.0)
    assert brain_globe_order == (11.0, 22.0, 33.0)
    assert round_trip == point
    assert point.ap_positive_direction == "posterior"
    assert point.ml_positive_direction == "left"
    assert point.dv_positive_direction == "inferior"
    assert point.voxel_anchor == "continuous-voxel-corner"


@pytest.mark.parametrize("invalid", (True, float("nan"), float("inf"), float("-inf")))
def test_atlas_points_reject_bool_nan_and_infinity(invalid: object) -> None:
    metadata = _metadata(shape=(1, 1, 1))

    with pytest.raises(ValidationError):
        AtlasPhysicalPointAPMLDV(
            atlas_key=metadata.atlas_key,
            atlas_version=metadata.atlas_package_version,
            coordinate_transform_id=TRANSFORM_ID,
            ap_um=invalid,
            ml_um=0.0,
            dv_um=0.0,
        )


def test_axis_aligned_clip_preserves_one_voxel_slab_and_repeated_region_runs() -> None:
    metadata = _metadata(shape=(5, 1, 1))
    annotation = np.array([1, 1, 2, 1, 1], dtype=np.uint32).reshape(5, 1, 1)
    segment = _segment(metadata, entry=(-5.0, 15.0, 10.0), tip=(55.0, 15.0, 10.0))

    result = _analyze(annotation, metadata, segment, regions=_regions(1, 2))

    assert result.intersects_atlas
    assert result.starts_outside_atlas
    assert result.ends_outside_atlas
    assert result.clipped_entry_depth_um == pytest.approx(5.0)
    assert result.clipped_exit_depth_um == pytest.approx(55.0)
    assert result.clipped_path_length_um == pytest.approx(50.0)
    assert result.outside_atlas_path_length_um == pytest.approx(10.0)
    assert _voxel_indices(result) == [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0)]
    assert [interval.length_um for interval in result.voxel_intervals] == pytest.approx(
        [10.0] * 5
    )
    assert [run.structure_id for run in result.segments] == [1, 2, 1]
    assert [run.length_um for run in result.segments] == pytest.approx([20.0, 10.0, 20.0])
    assert [run.voxel_count for run in result.segments] == [2, 1, 2]
    assert all(run.hemisphere is TraversalHemisphere.MIDLINE for run in result.segments)
    assert math.fsum(run.length_um for run in result.segments) == pytest.approx(
        result.clipped_path_length_um
    )


def test_non_corner_diagonal_visits_every_positive_length_voxel_in_order() -> None:
    metadata = _metadata(shape=(3, 2, 1), spacing=(10.0, 10.0, 10.0))
    annotation = np.ones(metadata.shape_voxels, dtype=np.uint32)
    # BrainGlobe voxel coordinates: (0.2, 0.2, 0.5) -> (2.8, 1.8, 0.5).
    segment = _segment(metadata, entry=(2.0, 5.0, 2.0), tip=(28.0, 5.0, 18.0))

    result = _analyze(annotation, metadata, segment, regions=_regions(1))

    assert _voxel_indices(result) == [(0, 0, 0), (1, 0, 0), (1, 1, 0), (2, 1, 0)]
    assert len(result.segments) == 1
    assert result.segments[0].voxel_count == 4
    assert math.fsum(item.length_um for item in result.voxel_intervals) == pytest.approx(
        result.total_path_length_um
    )


def test_exact_corner_crossing_advances_all_tied_axes_without_edge_voxels() -> None:
    metadata = _metadata(shape=(2, 2, 2), spacing=(10.0, 20.0, 30.0))
    annotation = np.ones(metadata.shape_voxels, dtype=np.uint16)
    segment = _segment(metadata, entry=(0.0, 0.0, 0.0), tip=(20.0, 60.0, 40.0))

    result = _analyze(annotation, metadata, segment, regions=_regions(1))

    assert _voxel_indices(result) == [(0, 0, 0), (1, 1, 1)]
    expected_length = math.sqrt(20.0**2 + 60.0**2 + 40.0**2)
    assert result.total_path_length_um == pytest.approx(expected_length)
    assert [item.length_um for item in result.voxel_intervals] == pytest.approx(
        [expected_length / 2.0, expected_length / 2.0]
    )


def test_boundary_tangent_with_only_point_contact_has_no_voxel_interval() -> None:
    metadata = _metadata(shape=(1, 1, 1))
    annotation = np.ones(metadata.shape_voxels, dtype=np.uint8)
    segment = _segment(metadata, entry=(-10.0, 15.0, 10.0), tip=(0.0, 15.0, 10.0))

    result = _analyze(annotation, metadata, segment, regions=_regions(1))

    assert not result.intersects_atlas
    assert result.voxel_intervals == ()
    assert result.segments == ()
    assert result.outside_atlas_path_length_um == pytest.approx(10.0)


def test_line_on_internal_boundary_uses_half_open_positive_side() -> None:
    metadata = _metadata(shape=(1, 1, 2))
    annotation = np.array([[[1, 2]]], dtype=np.uint32)
    # ML=30 um is the exact boundary between ML voxels 0 and 1.
    segment = _segment(metadata, entry=(0.0, 30.0, 10.0), tip=(10.0, 30.0, 10.0))

    result = _analyze(annotation, metadata, segment, regions=_regions(1, 2))

    assert _voxel_indices(result) == [(0, 0, 1)]
    assert [run.structure_id for run in result.segments] == [2]


def test_line_on_excluded_upper_face_has_no_in_volume_length() -> None:
    metadata = _metadata(shape=(1, 1, 2))
    annotation = np.ones(metadata.shape_voxels, dtype=np.uint32)
    # ML=60 um is the half-open atlas upper face.
    segment = _segment(metadata, entry=(0.0, 60.0, 10.0), tip=(10.0, 60.0, 10.0))

    result = _analyze(annotation, metadata, segment, regions=_regions(1))

    assert not result.intersects_atlas
    assert result.starts_outside_atlas and result.ends_outside_atlas


def test_negative_direction_from_exact_boundary_owns_following_negative_side_interval() -> None:
    metadata = _metadata(shape=(3, 1, 1))
    annotation = np.array([1, 2, 3], dtype=np.uint32).reshape(3, 1, 1)
    segment = _segment(metadata, entry=(20.0, 15.0, 10.0), tip=(0.0, 15.0, 10.0))
    boundary_site = _site(metadata, "boundary", ap_um=20.0, ml_um=15.0, dv_um=10.0)

    result = _analyze(
        annotation,
        metadata,
        segment,
        regions=_regions(1, 2, 3),
        sites=(boundary_site,),
    )

    # Positive-length traversal immediately after t=0 is in AP voxel 1.
    assert _voxel_indices(result) == [(1, 0, 0), (0, 0, 0)]
    # A point lookup at the same exact boundary follows [lower, upper): voxel 2.
    assert result.site_assignments[0].voxel is not None
    assert result.site_assignments[0].voxel.as_tuple() == (2, 0, 0)
    assert result.site_assignments[0].structure_id == 3


def test_annotation_zero_is_preserved_as_outside_brain_not_dropped() -> None:
    metadata = _metadata(shape=(2, 1, 1))
    annotation = np.array([0, 1], dtype=np.uint32).reshape(2, 1, 1)
    segment = _segment(metadata, entry=(0.0, 15.0, 10.0), tip=(20.0, 15.0, 10.0))

    result = _analyze(annotation, metadata, segment, regions=_regions(1))

    assert [run.structure_id for run in result.segments] == [0, 1]
    outside_brain = result.segments[0]
    assert outside_brain.location is TraversalLocation.OUTSIDE_BRAIN
    assert outside_brain.acronym == "outside-brain"
    assert outside_brain.name == "Outside annotated brain"
    assert outside_brain.length_um == pytest.approx(10.0)


def test_non_isotropic_site_assignments_use_half_open_boundaries_and_distinct_states() -> None:
    metadata = _metadata(shape=(1, 1, 3), spacing=(10.0, 20.0, 30.0))
    annotation = np.array([[[0, 1, 2]]], dtype=np.uint32)
    segment = _segment(metadata, entry=(5.0, 0.0, 10.0), tip=(5.0, 90.0, 10.0))
    sites = (
        _site(metadata, "inside-zero", ap_um=5.0, ml_um=15.0, dv_um=10.0),
        _site(metadata, "exact-boundary", ap_um=5.0, ml_um=30.0, dv_um=10.0),
        _site(metadata, "upper-face", ap_um=5.0, ml_um=90.0, dv_um=10.0),
    )

    result = _analyze(
        annotation,
        metadata,
        segment,
        regions=_regions(1, 2),
        sites=sites,
    )

    inside_zero, exact_boundary, upper_face = result.site_assignments
    assert inside_zero.location is TraversalLocation.OUTSIDE_BRAIN
    assert inside_zero.inside_atlas and not inside_zero.inside_brain
    assert inside_zero.structure_id == 0
    assert exact_boundary.voxel is not None
    assert exact_boundary.voxel.as_tuple() == (0, 0, 1)
    assert exact_boundary.structure_id == 1
    assert exact_boundary.inside_atlas and exact_boundary.inside_brain
    assert upper_face.location is TraversalLocation.OUTSIDE_ATLAS
    assert upper_face.voxel is None
    assert not upper_face.inside_atlas and not upper_face.inside_brain
    assert [item.length_um for item in result.voxel_intervals] == pytest.approx(
        [30.0, 30.0, 30.0]
    )


def test_completely_outside_segment_still_assigns_sites_and_reports_full_outside_length() -> None:
    metadata = _metadata(shape=(1, 1, 1))
    annotation = np.zeros(metadata.shape_voxels, dtype=np.uint32)
    segment = _segment(metadata, entry=(-30.0, 15.0, 10.0), tip=(-10.0, 15.0, 10.0))
    outside_site = _site(metadata, "outside", ap_um=-20.0, ml_um=15.0, dv_um=10.0)

    result = _analyze(annotation, metadata, segment, sites=(outside_site,))

    assert not result.intersects_atlas
    assert result.clipped_path_length_um == 0
    assert result.outside_atlas_path_length_um == pytest.approx(20.0)
    assert result.site_assignments[0].location is TraversalLocation.OUTSIDE_ATLAS


@pytest.mark.parametrize(
    ("annotation", "error_type", "message"),
    (
        (np.zeros((1, 1), dtype=np.uint32), RegionTraversalInputError, "three-dimensional"),
        (np.zeros((2, 1, 1), dtype=np.uint32), RegionTraversalInputError, "shape must equal"),
        (np.zeros((1, 1, 1), dtype=np.float64), TypeError, "non-boolean integer"),
        (np.zeros((1, 1, 1), dtype=np.bool_), TypeError, "non-boolean integer"),
    ),
)
def test_annotation_rejects_invalid_shape_and_dtype(
    annotation: np.ndarray,
    error_type: type[Exception],
    message: str,
) -> None:
    metadata = _metadata(shape=(1, 1, 1))
    segment = _segment(metadata, entry=(0.0, 0.0, 0.0), tip=(10.0, 30.0, 20.0))

    with pytest.raises(error_type, match=message):
        _analyze(annotation, metadata, segment)


def test_annotation_rejects_non_array_and_negative_or_unknown_visited_ids() -> None:
    metadata = _metadata(shape=(1, 1, 1))
    segment = _segment(metadata, entry=(0.0, 0.0, 0.0), tip=(10.0, 30.0, 20.0))

    with pytest.raises(TypeError, match="NumPy array"):
        analyze_probe_regions(
            annotation=[[[1]]],  # type: ignore[arg-type]
            metadata=metadata,
            annotation_sha256=ANNOTATION_SHA256,
            annotation_version=ANNOTATION_VERSION,
            segment=segment,
            regions=_regions(1),
        )
    with pytest.raises(RegionTraversalInputError, match="non-negative"):
        _analyze(np.array([[[-1]]], dtype=np.int16), metadata, segment)
    with pytest.raises(RegionTraversalInputError, match="absent from region metadata"):
        _analyze(np.array([[[7]]], dtype=np.uint16), metadata, segment)


def test_segment_and_site_identity_validation_fail_closed() -> None:
    metadata = _metadata(shape=(1, 1, 1))
    point = _point(metadata, ap_um=1.0, ml_um=1.0, dv_um=1.0)
    with pytest.raises(ValidationError, match="must be distinct"):
        CalibratedProbeShankSegment(
            placement_uuid=PLACEMENT_UUID,
            probe_model_id="synthetic-probe",
            probe_model_version="1",
            shank_id="shank-0",
            entry=point,
            tip=point,
        )

    segment = _segment(metadata, entry=(0.0, 0.0, 0.0), tip=(10.0, 30.0, 20.0))
    duplicate = _site(metadata, "duplicate", ap_um=1.0, ml_um=1.0, dv_um=1.0)
    with pytest.raises(RegionTraversalInputError, match="duplicate recording site"):
        _analyze(
            np.ones((1, 1, 1), dtype=np.uint8),
            metadata,
            segment,
            regions=_regions(1),
            sites=(duplicate, duplicate),
        )


def test_input_digest_is_deterministic_and_changes_with_site_input() -> None:
    metadata = _metadata(shape=(1, 1, 1))
    annotation = np.ones(metadata.shape_voxels, dtype=np.uint8)
    segment = _segment(metadata, entry=(0.0, 0.0, 0.0), tip=(10.0, 30.0, 20.0))
    first = _analyze(annotation, metadata, segment, regions=_regions(1))
    second = _analyze(annotation, metadata, segment, regions=_regions(1))
    with_site = _analyze(
        annotation,
        metadata,
        segment,
        regions=_regions(1),
        sites=(_site(metadata, "s0", ap_um=1.0, ml_um=1.0, dv_um=1.0),),
    )

    assert first.algorithm_version == REGION_TRAVERSAL_ALGORITHM_VERSION
    assert first.input_digest == second.input_digest
    assert first.analysis_uuid != second.analysis_uuid
    assert with_site.input_digest != first.input_digest
    assert first.annotation_sha256 == ANNOTATION_SHA256
    assert first.annotation_version == ANNOTATION_VERSION
