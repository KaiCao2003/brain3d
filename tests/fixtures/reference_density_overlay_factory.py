"""Small provenance-complete reference-density test doubles."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.vasculature.reference_density import (
    BRAINGLOBE_ASR_FRAME_AP_DV_ML,
    SOURCE_FRAME_ML_DV_AP,
    NiftiHeaderEvidence,
    ReferenceDensityProvenance,
    ReferenceDensitySourceProvenance,
    ReferenceVascularDensity,
    TemplateAlignmentEvidence,
)


def make_reference_density_overlay_test_double(
    values_asr: NDArray[np.float32] | None = None,
    *,
    density_shape_asr: tuple[int, int, int] = (2, 3, 4),
    density_resolution_um: float = 100.0,
    atlas_resolution_um: float = 50.0,
) -> ReferenceVascularDensity:
    """Return synthetic values with truthful four-subject safety provenance."""

    if values_asr is None:
        values = np.arange(np.prod(density_shape_asr), dtype=np.float32).reshape(density_shape_asr)
    else:
        values = np.asarray(values_asr, dtype=np.float32).copy()
        density_shape_asr = values.shape
    output_extent = tuple(float(size * density_resolution_um) for size in density_shape_asr)
    atlas_shape = tuple(round(extent / atlas_resolution_um) for extent in output_extent)
    source_shape_mldvpa = (
        density_shape_asr[2],
        density_shape_asr[1],
        density_shape_asr[0],
    )
    source_header_shape = (*source_shape_mldvpa, 1)
    source = ReferenceDensitySourceProvenance(
        dataset_title="Synthetic four-mouse vascular density test double",
        contributor="tests",
        version=1,
        doi="test:reference-density-overlay",
        landing_page_url="https://example.invalid/reference-density-overlay",
        license_name="TEST ONLY",
        license_url="https://example.invalid/test-license",
        attribution="Synthetic values; no animal anatomy.",
        archive_filename="synthetic.7z",
        archive_size_bytes=1,
        archive_sha256="0" * 64,
        density_member_path="synthetic-density.nii",
        template_member_path="synthetic-template.nii",
        source_shape_mldvpa=source_shape_mldvpa,
        source_voxel_size_um=density_resolution_um,
        source_axis_order=SOURCE_FRAME_ML_DV_AP,
        density_value_units="m/mm^3",
        rolling_window_um=100.0,
        population_subject_count=4,
        density_header=NiftiHeaderEvidence(
            shape=source_header_shape,
            spatial_zooms=(1.0, 1.0, 1.0),
            space_unit="unknown",
            qform_code=0,
            sform_code=0,
            dtype_name="float32",
        ),
        template_header=NiftiHeaderEvidence(
            shape=source_header_shape,
            spatial_zooms=(density_resolution_um,) * 3,
            space_unit="micron",
            qform_code=0,
            sform_code=0,
            dtype_name="int16",
        ),
    )
    alignment = TemplateAlignmentEvidence(
        correlation=1.0,
        minimum_correlation=0.99,
        source_shape_mldvpa=source_shape_mldvpa,
        target_shape_asr=atlas_shape,  # type: ignore[arg-type]
        source_voxel_size_um=density_resolution_um,
        target_voxel_size_um=atlas_resolution_um,
    )
    provenance = ReferenceDensityProvenance(
        source=source,
        output_frame=BRAINGLOBE_ASR_FRAME_AP_DV_ML,
        output_shape_asr=density_shape_asr,
        output_voxel_size_um=density_resolution_um,
        output_extent_um_asr=output_extent,  # type: ignore[arg-type]
        template_alignment=alignment,
    )
    values.setflags(write=False)
    return ReferenceVascularDensity(values_asr=values, provenance=provenance)
