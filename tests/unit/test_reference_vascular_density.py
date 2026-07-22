from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from mouse_brain_planner.vasculature import (
    BRAINGLOBE_ASR_FRAME_AP_DV_ML,
    SOURCE_FRAME_ML_DV_AP,
    STXVN5SV44_V1_ARCHIVE_SHA256,
    STXVN5SV44_V1_DENSITY_HEADER,
    STXVN5SV44_V1_SOURCE,
    STXVN5SV44_V1_TEMPLATE_HEADER,
    NiftiHeaderEvidence,
    ReferenceDensitySourceProvenance,
    ReferenceDensityValidationError,
    prepare_reference_vascular_density,
    reorder_mldvpa_to_brainglobe_asr,
    resample_asr_center_aligned,
    symmetrize_asr_ml,
    validate_source_nifti_header,
    validate_template_alignment,
)


def _synthetic_source(
    shape: tuple[int, int, int] = (4, 4, 4),
    *,
    source_voxel_size_um: float = 20.0,
) -> ReferenceDensitySourceProvenance:
    header_shape = (*shape, 1)
    return ReferenceDensitySourceProvenance(
        dataset_title="Synthetic test double for stxvn5sv44 v1",
        contributor="tests",
        version=1,
        doi="test:stxvn5sv44-v1-contract",
        landing_page_url="https://example.invalid/test-only",
        license_name="TEST ONLY",
        license_url="https://example.invalid/test-only-license",
        attribution="Synthetic test data; not animal data.",
        archive_filename="synthetic.7z",
        archive_size_bytes=1,
        archive_sha256="0" * 64,
        density_member_path="synthetic-density.nii",
        template_member_path="synthetic-template.nii",
        source_shape_mldvpa=shape,
        source_voxel_size_um=source_voxel_size_um,
        source_axis_order=SOURCE_FRAME_ML_DV_AP,
        density_value_units="m/mm^3",
        rolling_window_um=100.0,
        population_subject_count=1,
        density_header=NiftiHeaderEvidence(
            shape=header_shape,
            spatial_zooms=(1.0, 1.0, 1.0),
            space_unit="unknown",
            qform_code=0,
            sform_code=0,
            dtype_name="float32",
        ),
        template_header=NiftiHeaderEvidence(
            shape=header_shape,
            spatial_zooms=(source_voxel_size_um,) * 3,
            space_unit="micron",
            qform_code=0,
            sform_code=0,
            dtype_name="int16",
        ),
    )


def _coordinate_ramp(shape: tuple[int, int, int]) -> np.ndarray:
    ml, dv, ap = np.indices(shape, dtype=np.float32)
    return ml * np.float32(100.0) + dv * np.float32(10.0) + ap


def test_reviewed_source_provenance_is_immutable_and_does_not_overclaim() -> None:
    source = STXVN5SV44_V1_SOURCE

    assert source.doi == "10.17632/stxvn5sv44.1"
    assert source.version == 1
    assert source.license_name == "CC BY 4.0"
    assert source.archive_size_bytes == 311_493_514
    assert source.archive_sha256 == STXVN5SV44_V1_ARCHIVE_SHA256
    assert source.source_shape_mldvpa == (570, 400, 660)
    assert source.source_voxel_size_um == 20.0
    assert source.source_axis_order == SOURCE_FRAME_ML_DV_AP
    assert source.extent_um_asr == (13_200.0, 8_000.0, 11_400.0)
    assert source.density_value_units == "m/mm^3"
    assert source.rolling_window_um == 100.0
    assert not source.ml_polarity_resolved
    assert not source.subject_specific
    assert not source.contains_individual_vessel_paths
    assert not source.supports_vessel_clearance
    assert STXVN5SV44_V1_DENSITY_HEADER.spatial_zooms == (1.0, 1.0, 1.0)
    assert STXVN5SV44_V1_DENSITY_HEADER.space_unit == "unknown"
    assert STXVN5SV44_V1_TEMPLATE_HEADER.spatial_zooms == (20.0, 20.0, 20.0)
    assert STXVN5SV44_V1_DENSITY_HEADER.qform_code == 0
    assert STXVN5SV44_V1_DENSITY_HEADER.sform_code == 0

    with pytest.raises(FrozenInstanceError):
        source.version = 2  # type: ignore[misc]


def test_reorder_transposes_mldvpa_to_asr_and_reverses_only_ap() -> None:
    source = _coordinate_ramp((2, 3, 4))

    actual = reorder_mldvpa_to_brainglobe_asr(source)

    expected = np.transpose(source, (2, 1, 0))[::-1, :, :]
    np.testing.assert_array_equal(actual, expected)
    assert actual.shape == (4, 3, 2)
    assert actual[0, 0, 0] == source[0, 0, 3]
    assert actual[-1, -1, -1] == source[-1, -1, 0]


def test_ml_symmetrization_removes_undocumented_laterality() -> None:
    source = np.arange(2 * 3 * 4, dtype=np.float32).reshape((2, 3, 4))

    actual = symmetrize_asr_ml(source)

    expected = source * np.float32(0.5) + source[:, :, ::-1] * np.float32(0.5)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(actual, actual[:, :, ::-1])
    assert actual.dtype == np.dtype(np.float32)


def test_center_aligned_resampling_preserves_extent_and_linear_values() -> None:
    ap, dv, ml = np.indices((4, 4, 4), dtype=np.float32)
    source = ap + dv * np.float32(10.0) + ml * np.float32(100.0)

    actual = resample_asr_center_aligned(
        source,
        source_voxel_size_um=20.0,
        target_voxel_size_um=40.0,
    )

    target_centres_in_source_indices = np.array([0.5, 2.5], dtype=np.float32)
    expected = (
        target_centres_in_source_indices[:, None, None]
        + target_centres_in_source_indices[None, :, None] * np.float32(10.0)
        + target_centres_in_source_indices[None, None, :] * np.float32(100.0)
    )
    assert actual.shape == (2, 2, 2)
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-5)
    assert tuple(size * 40.0 for size in actual.shape) == (80.0, 80.0, 80.0)


def test_template_alignment_accepts_the_declared_orientation_only() -> None:
    ml, dv, ap = np.indices((4, 4, 4), dtype=np.float32)
    source_template = ap * np.float32(100.0) + dv * np.float32(10.0) + ml
    target_reference = resample_asr_center_aligned(
        reorder_mldvpa_to_brainglobe_asr(source_template),
        source_voxel_size_um=20.0,
        target_voxel_size_um=40.0,
    )

    evidence = validate_template_alignment(
        source_template,
        target_reference,
        source_voxel_size_um=20.0,
        target_voxel_size_um=40.0,
    )

    assert evidence.correlation == pytest.approx(1.0, abs=1e-12)
    assert evidence.minimum_correlation == 0.99
    assert evidence.source_shape_mldvpa == (4, 4, 4)
    assert evidence.target_shape_asr == (2, 2, 2)

    with pytest.raises(ReferenceDensityValidationError, match="below the required minimum"):
        validate_template_alignment(
            source_template,
            target_reference[::-1, :, :],
            source_voxel_size_um=20.0,
            target_voxel_size_um=40.0,
        )


def test_preparation_returns_read_only_typed_population_density() -> None:
    source = _synthetic_source()
    density = (_coordinate_ramp(source.source_shape_mldvpa) + np.float32(1.0))[..., None]
    template = _coordinate_ramp(source.source_shape_mldvpa).astype(np.int16)[..., None]
    target_reference = resample_asr_center_aligned(
        reorder_mldvpa_to_brainglobe_asr(template[..., 0]),
        source_voxel_size_um=20.0,
        target_voxel_size_um=40.0,
    )

    result = prepare_reference_vascular_density(
        density,
        density_header=source.density_header,
        source_template_mldvpa=template,
        template_header=source.template_header,
        target_atlas_reference_asr=target_reference,
        target_atlas_voxel_size_um=40.0,
        output_voxel_size_um=40.0,
        source=source,
    )

    assert result.values_asr.shape == (2, 2, 2)
    assert result.values_asr.dtype == np.dtype(np.float32)
    assert not result.values_asr.flags.writeable
    np.testing.assert_array_equal(result.values_asr, result.values_asr[:, :, ::-1])
    assert result.provenance.source is source
    assert result.provenance.output_frame == BRAINGLOBE_ASR_FRAME_AP_DV_ML
    assert result.provenance.output_voxel_size_um == 40.0
    assert result.provenance.output_extent_um_asr == (80.0, 80.0, 80.0)
    assert result.provenance.ap_axis_reversed
    assert result.provenance.ml_symmetrized
    assert result.provenance.template_alignment.correlation == pytest.approx(1.0)
    assert not result.provenance.subject_specific
    assert not result.provenance.contains_individual_vessel_paths
    assert not result.provenance.supports_vessel_clearance
    with pytest.raises(ValueError, match="read-only"):
        result.values_asr[0, 0, 0] = np.float32(0.0)


def test_header_validation_requires_the_reviewed_defective_header() -> None:
    validate_source_nifti_header(STXVN5SV44_V1_DENSITY_HEADER, kind="density")
    validate_source_nifti_header(STXVN5SV44_V1_TEMPLATE_HEADER, kind="template")

    corrected_spacing = replace(
        STXVN5SV44_V1_DENSITY_HEADER,
        spatial_zooms=(20.0, 20.0, 20.0),
    )
    corrected_transform = replace(STXVN5SV44_V1_DENSITY_HEADER, sform_code=1)
    with pytest.raises(ReferenceDensityValidationError, match="does not match the pinned"):
        validate_source_nifti_header(corrected_spacing, kind="density")
    with pytest.raises(ReferenceDensityValidationError, match="does not match the pinned"):
        validate_source_nifti_header(corrected_transform, kind="density")


@pytest.mark.parametrize("invalid_value", [np.nan, np.inf, -1.0])
def test_preparation_rejects_invalid_density_values(invalid_value: float) -> None:
    source = _synthetic_source()
    density = np.ones(source.source_shape_mldvpa, dtype=np.float32)
    density[0, 0, 0] = invalid_value
    template = _coordinate_ramp(source.source_shape_mldvpa).astype(np.int16)
    target_reference = reorder_mldvpa_to_brainglobe_asr(template)

    with pytest.raises(ReferenceDensityValidationError, match=r"non-finite|negative"):
        prepare_reference_vascular_density(
            density,
            density_header=source.density_header,
            source_template_mldvpa=template,
            template_header=source.template_header,
            target_atlas_reference_asr=target_reference,
            target_atlas_voxel_size_um=20.0,
            output_voxel_size_um=20.0,
            source=source,
        )


def test_preparation_rejects_shape_dtype_and_atlas_extent_mismatches() -> None:
    source = _synthetic_source()
    template = _coordinate_ramp(source.source_shape_mldvpa).astype(np.int16)
    target_reference = reorder_mldvpa_to_brainglobe_asr(template)

    with pytest.raises(ReferenceDensityValidationError, match=r"reviewed.*shape"):
        prepare_reference_vascular_density(
            np.ones((3, 4, 4), dtype=np.float32),
            density_header=source.density_header,
            source_template_mldvpa=template,
            template_header=source.template_header,
            target_atlas_reference_asr=target_reference,
            target_atlas_voxel_size_um=20.0,
            source=source,
        )
    with pytest.raises(ReferenceDensityValidationError, match="floating-point density"):
        prepare_reference_vascular_density(
            np.ones(source.source_shape_mldvpa, dtype=np.int16),
            density_header=source.density_header,
            source_template_mldvpa=template,
            template_header=source.template_header,
            target_atlas_reference_asr=target_reference,
            target_atlas_voxel_size_um=20.0,
            source=source,
        )
    with pytest.raises(ReferenceDensityValidationError, match="same exact physical extent"):
        prepare_reference_vascular_density(
            np.ones(source.source_shape_mldvpa, dtype=np.float32),
            density_header=source.density_header,
            source_template_mldvpa=template,
            template_header=source.template_header,
            target_atlas_reference_asr=np.ones((3, 4, 4), dtype=np.float32),
            target_atlas_voxel_size_um=20.0,
            source=source,
        )


def test_resampling_rejects_upsampling_and_inexact_extents() -> None:
    volume = np.ones((3, 3, 3), dtype=np.float32)

    with pytest.raises(ReferenceDensityValidationError, match="preserve or lower"):
        resample_asr_center_aligned(
            volume,
            source_voxel_size_um=20.0,
            target_voxel_size_um=10.0,
        )
    with pytest.raises(ReferenceDensityValidationError, match="not exactly divisible"):
        resample_asr_center_aligned(
            volume,
            source_voxel_size_um=20.0,
            target_voxel_size_um=50.0,
        )


def test_template_alignment_rejects_zero_variance_and_bad_thresholds() -> None:
    template = np.ones((4, 4, 4), dtype=np.float32)
    target = reorder_mldvpa_to_brainglobe_asr(template)

    with pytest.raises(ReferenceDensityValidationError, match="zero intensity variance"):
        validate_template_alignment(
            template,
            target,
            source_voxel_size_um=20.0,
            target_voxel_size_um=20.0,
        )
    with pytest.raises(ReferenceDensityValidationError, match=r"inside \(0, 1\]"):
        validate_template_alignment(
            _coordinate_ramp((4, 4, 4)),
            target,
            source_voxel_size_um=20.0,
            target_voxel_size_um=20.0,
            minimum_correlation=0.0,
        )
