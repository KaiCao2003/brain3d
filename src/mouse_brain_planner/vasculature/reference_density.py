"""Fail-closed conversion of the reviewed Allen-registered vascular density.

The Wu/Kim companion deposit provides a population vascular *length-density*
field, not vessel paths.  Its density NIfTI header does not carry trustworthy
spatial metadata: the reviewed file reports unit voxel spacing, unknown units,
and no qform or sform even though the deposit README declares a 20 micrometre
``[ML, DV, AP]`` grid.  This module therefore validates that exact caveat and
uses only the pinned source contract below for spatial conversion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage  # type: ignore[import-untyped]

SOURCE_FRAME_ML_DV_AP = ("ML", "DV", "AP")
BRAINGLOBE_ASR_FRAME_AP_DV_ML = ("AP", "DV", "ML")
DEFAULT_REFERENCE_DENSITY_RESOLUTION_UM = 50.0
DEFAULT_MINIMUM_TEMPLATE_CORRELATION = 0.99

STXVN5SV44_V1_DOI = "10.17632/stxvn5sv44.1"
STXVN5SV44_V1_LICENSE = "CC BY 4.0"
STXVN5SV44_V1_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
STXVN5SV44_V1_ARCHIVE_SHA256 = "c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe"
STXVN5SV44_V1_ATTRIBUTION = (
    "Kim, Yongsoo (2022), 'Cerebrovascular, pericyte, and neuronal cell type "
    "mapping data 2022', Mendeley Data, V1, doi:10.17632/stxvn5sv44.1, "
    "licensed CC BY 4.0."
)

HeaderKind = Literal["density", "template"]


class ReferenceDensityValidationError(ValueError):
    """Raised when source data cannot be converted without guessing."""


@dataclass(frozen=True, slots=True)
class NiftiHeaderEvidence:
    """Normalized NIfTI fields needed to recognize one reviewed file."""

    shape: tuple[int, ...]
    spatial_zooms: tuple[float, float, float]
    space_unit: str
    qform_code: int
    sform_code: int
    dtype_name: str

    def __post_init__(self) -> None:
        if len(self.shape) not in (3, 4) or any(size <= 0 for size in self.shape):
            raise ValueError("NIfTI evidence shape must contain three or four positive dimensions")
        if len(self.shape) == 4 and self.shape[3] != 1:
            raise ValueError("a four-dimensional density NIfTI must have one trailing volume")
        if any(not math.isfinite(value) or value <= 0 for value in self.spatial_zooms):
            raise ValueError("NIfTI spatial zooms must be positive and finite")
        if not self.space_unit:
            raise ValueError("NIfTI space unit must be explicit, including 'unknown'")
        if self.qform_code < 0 or self.sform_code < 0:
            raise ValueError("NIfTI transform codes cannot be negative")
        if not self.dtype_name:
            raise ValueError("NIfTI dtype name must be explicit")


@dataclass(frozen=True, slots=True)
class ReferenceDensitySourceProvenance:
    """Immutable identity and reviewed spatial contract for one source."""

    dataset_title: str
    contributor: str
    version: int
    doi: str
    landing_page_url: str
    license_name: str
    license_url: str
    attribution: str
    archive_filename: str
    archive_size_bytes: int
    archive_sha256: str
    density_member_path: str
    template_member_path: str
    source_shape_mldvpa: tuple[int, int, int]
    source_voxel_size_um: float
    source_axis_order: tuple[str, str, str]
    density_value_units: str
    rolling_window_um: float
    population_subject_count: int
    density_header: NiftiHeaderEvidence
    template_header: NiftiHeaderEvidence
    ml_polarity_resolved: bool = False
    subject_specific: bool = False
    contains_individual_vessel_paths: bool = False
    supports_vessel_clearance: bool = False

    def __post_init__(self) -> None:
        if self.version <= 0:
            raise ValueError("dataset version must be positive")
        if self.archive_size_bytes <= 0:
            raise ValueError("archive size must be positive")
        if len(self.archive_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.archive_sha256
        ):
            raise ValueError("archive SHA-256 must contain 64 lowercase hexadecimal characters")
        if any(size <= 0 for size in self.source_shape_mldvpa):
            raise ValueError("source density shape must be positive")
        if not math.isfinite(self.source_voxel_size_um) or self.source_voxel_size_um <= 0:
            raise ValueError("source voxel size must be positive and finite")
        if self.source_axis_order != SOURCE_FRAME_ML_DV_AP:
            raise ValueError(
                f"source axis order must be {SOURCE_FRAME_ML_DV_AP}, got {self.source_axis_order}"
            )
        if not math.isfinite(self.rolling_window_um) or self.rolling_window_um <= 0:
            raise ValueError("rolling window must be positive and finite")
        if self.population_subject_count <= 0:
            raise ValueError("population subject count must be positive")
        expected_header_shape = (*self.source_shape_mldvpa, 1)
        if self.density_header.shape != expected_header_shape:
            raise ValueError(
                "density header shape must equal source shape plus one trailing volume"
            )
        if self.template_header.shape != expected_header_shape:
            raise ValueError(
                "template header shape must equal source shape plus one trailing volume"
            )
        if self.ml_polarity_resolved:
            raise ValueError("this conversion contract requires unresolved ML polarity")
        if self.subject_specific or self.contains_individual_vessel_paths:
            raise ValueError(
                "reference density cannot claim subject-specific anatomy or vessel paths"
            )
        if self.supports_vessel_clearance:
            raise ValueError("a scalar reference density cannot support vessel-clearance claims")

    @property
    def extent_um_mldvpa(self) -> tuple[float, float, float]:
        """Return the half-open source extent in ``[ML,DV,AP]`` order."""

        return tuple(float(size * self.source_voxel_size_um) for size in self.source_shape_mldvpa)  # type: ignore[return-value]

    @property
    def extent_um_asr(self) -> tuple[float, float, float]:
        """Return the same physical extent in BrainGlobe ``[AP,DV,ML]`` order."""

        ml, dv, ap = self.extent_um_mldvpa
        return (ap, dv, ml)


@dataclass(frozen=True, slots=True)
class TemplateAlignmentEvidence:
    """Evidence that the reviewed source grid matches one target atlas grid."""

    correlation: float
    minimum_correlation: float
    source_shape_mldvpa: tuple[int, int, int]
    target_shape_asr: tuple[int, int, int]
    source_voxel_size_um: float
    target_voxel_size_um: float
    comparison_mask: str = "union of non-zero template voxels"


@dataclass(frozen=True, slots=True)
class ReferenceDensityProvenance:
    """Source identity plus every spatial modification applied to the output."""

    source: ReferenceDensitySourceProvenance
    output_frame: tuple[str, str, str]
    output_shape_asr: tuple[int, int, int]
    output_voxel_size_um: float
    output_extent_um_asr: tuple[float, float, float]
    template_alignment: TemplateAlignmentEvidence
    ap_axis_reversed: bool = True
    ml_symmetrized: bool = True
    ml_symmetrization_reason: str = "source ML polarity is not documented"
    resampling_method: str = "linear interpolation at voxel centres with exact extents"
    subject_specific: bool = False
    contains_individual_vessel_paths: bool = False
    supports_vessel_clearance: bool = False


@dataclass(frozen=True, slots=True, eq=False)
class ReferenceVascularDensity:
    """Read-only population reference density in BrainGlobe ASR order."""

    values_asr: NDArray[np.float32]
    provenance: ReferenceDensityProvenance

    def __post_init__(self) -> None:
        if self.values_asr.dtype != np.dtype(np.float32):
            raise ValueError("prepared reference density must use float32")
        if self.values_asr.shape != self.provenance.output_shape_asr:
            raise ValueError("prepared density shape does not match its provenance")
        if self.values_asr.flags.writeable:
            raise ValueError("prepared reference density must be read-only")


STXVN5SV44_V1_DENSITY_HEADER = NiftiHeaderEvidence(
    shape=(570, 400, 660, 1),
    spatial_zooms=(1.0, 1.0, 1.0),
    space_unit="unknown",
    qform_code=0,
    sform_code=0,
    dtype_name="float32",
)

STXVN5SV44_V1_TEMPLATE_HEADER = NiftiHeaderEvidence(
    shape=(570, 400, 660, 1),
    spatial_zooms=(20.0, 20.0, 20.0),
    space_unit="micron",
    qform_code=0,
    sform_code=0,
    dtype_name="int16",
)

STXVN5SV44_V1_SOURCE = ReferenceDensitySourceProvenance(
    dataset_title="Cerebrovascular, pericyte, and neuronal cell type mapping data 2022",
    contributor="Yongsoo Kim",
    version=1,
    doi=STXVN5SV44_V1_DOI,
    landing_page_url="https://data.mendeley.com/datasets/stxvn5sv44/1",
    license_name=STXVN5SV44_V1_LICENSE,
    license_url=STXVN5SV44_V1_LICENSE_URL,
    attribution=STXVN5SV44_V1_ATTRIBUTION,
    archive_filename="NVU_mapping_Adult_mouse_brain (1).7z",
    archive_size_bytes=311_493_514,
    archive_sha256=STXVN5SV44_V1_ARCHIVE_SHA256,
    density_member_path="Vascular_length_Brain-wide/Vessel_LengthDensity_P56.nii",
    template_member_path="Vascular_length_Brain-wide/AllenCCF_template_20um-isotropic.nii",
    source_shape_mldvpa=(570, 400, 660),
    source_voxel_size_um=20.0,
    source_axis_order=SOURCE_FRAME_ML_DV_AP,
    density_value_units="m/mm^3",
    rolling_window_um=100.0,
    population_subject_count=4,
    density_header=STXVN5SV44_V1_DENSITY_HEADER,
    template_header=STXVN5SV44_V1_TEMPLATE_HEADER,
)


def validate_source_nifti_header(
    evidence: NiftiHeaderEvidence,
    *,
    source: ReferenceDensitySourceProvenance = STXVN5SV44_V1_SOURCE,
    kind: HeaderKind,
) -> None:
    """Require the exact reviewed header, including its known missing transform.

    The density header's unit spacing is not accepted as physical evidence.  It
    is accepted only because the pinned README and included template establish
    the source grid independently.  Any changed or corrected-looking header is
    an unreviewed input and fails closed.
    """

    expected = source.density_header if kind == "density" else source.template_header
    if evidence != expected:
        raise ReferenceDensityValidationError(
            f"{kind} NIfTI header does not match the pinned {source.doi} contract: "
            f"expected {expected!r}, got {evidence!r}"
        )


def reorder_mldvpa_to_brainglobe_asr(values_mldvpa: NDArray[Any]) -> NDArray[Any]:
    """Map source ``[ML,DV,AP]`` to ``[AP,DV,ML]`` and reverse AP.

    ML is not flipped here because its polarity is unresolved.  Call
    :func:`symmetrize_asr_ml` before treating the result as a usable reference.
    """

    values = _validated_numeric_volume(values_mldvpa, "source [ML,DV,AP] volume")
    return np.transpose(values, (2, 1, 0))[::-1, :, :]


def symmetrize_asr_ml(values_asr: NDArray[Any]) -> NDArray[np.float32]:
    """Average both ML polarities so an undocumented laterality is never guessed."""

    values = _validated_numeric_volume(values_asr, "BrainGlobe ASR volume")
    native = np.asarray(values, dtype=np.float32)
    result = np.empty(native.shape, dtype=np.float32)
    for ap_index in range(native.shape[0]):
        plane = native[ap_index]
        result[ap_index] = plane * np.float32(0.5) + plane[:, ::-1] * np.float32(0.5)
    _validate_nonnegative_finite(result, "ML-symmetrized volume")
    return result


def resample_asr_center_aligned(
    values_asr: NDArray[Any],
    *,
    source_voxel_size_um: float,
    target_voxel_size_um: float = DEFAULT_REFERENCE_DENSITY_RESOLUTION_UM,
) -> NDArray[np.float32]:
    """Linearly resample voxel centres while preserving exact half-open extents."""

    values = _validated_numeric_volume(values_asr, "ASR volume to resample")
    source_resolution = _positive_finite(source_voxel_size_um, "source voxel size")
    target_resolution = _positive_finite(target_voxel_size_um, "target voxel size")
    if target_resolution < source_resolution and not math.isclose(
        target_resolution,
        source_resolution,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ReferenceDensityValidationError(
            "reference-density resampling may only preserve or lower spatial resolution"
        )

    output_shape = _exact_output_shape(values.shape, source_resolution, target_resolution)
    zoom = tuple(
        output_size / input_size
        for output_size, input_size in zip(output_shape, values.shape, strict=True)
    )
    resampled = cast(
        NDArray[np.float32],
        ndimage.zoom(
            values,
            zoom=zoom,
            output=np.float32,
            order=1,
            mode="nearest",
            prefilter=False,
            grid_mode=True,
        ),
    )
    if resampled.shape != output_shape:
        raise ReferenceDensityValidationError(
            f"resampler returned shape {resampled.shape}, expected exact shape {output_shape}"
        )
    _validate_nonnegative_finite(resampled, "resampled ASR volume")
    return resampled


def validate_template_alignment(
    source_template_mldvpa: NDArray[Any],
    target_atlas_reference_asr: NDArray[Any],
    *,
    source_voxel_size_um: float,
    target_voxel_size_um: float,
    minimum_correlation: float = DEFAULT_MINIMUM_TEMPLATE_CORRELATION,
) -> TemplateAlignmentEvidence:
    """Validate source-template alignment against a target atlas reference."""

    threshold = _validated_correlation_threshold(minimum_correlation)
    source_template = _validated_numeric_volume(
        source_template_mldvpa,
        "source template [ML,DV,AP]",
    )
    target_reference = _validated_numeric_volume(
        target_atlas_reference_asr,
        "target atlas reference [AP,DV,ML]",
    )
    source_resolution = _positive_finite(source_voxel_size_um, "source voxel size")
    target_resolution = _positive_finite(target_voxel_size_um, "target voxel size")

    expected_target_shape = _exact_output_shape(
        (source_template.shape[2], source_template.shape[1], source_template.shape[0]),
        source_resolution,
        target_resolution,
    )
    if target_reference.shape != expected_target_shape:
        raise ReferenceDensityValidationError(
            "target atlas reference does not have the same exact physical extent: "
            f"expected ASR shape {expected_target_shape} at {target_resolution:g} µm, "
            f"got {target_reference.shape}"
        )

    source_asr = reorder_mldvpa_to_brainglobe_asr(source_template)
    source_on_target = resample_asr_center_aligned(
        source_asr,
        source_voxel_size_um=source_resolution,
        target_voxel_size_um=target_resolution,
    )
    correlation = _nonzero_union_pearson(source_on_target, target_reference)
    if correlation < threshold:
        raise ReferenceDensityValidationError(
            f"source template correlation {correlation:.6f} is below the required "
            f"minimum {threshold:.6f}"
        )
    return TemplateAlignmentEvidence(
        correlation=correlation,
        minimum_correlation=threshold,
        source_shape_mldvpa=source_template.shape,
        target_shape_asr=target_reference.shape,
        source_voxel_size_um=source_resolution,
        target_voxel_size_um=target_resolution,
    )


def prepare_reference_vascular_density(
    source_density_mldvpa: NDArray[Any],
    *,
    density_header: NiftiHeaderEvidence,
    source_template_mldvpa: NDArray[Any],
    template_header: NiftiHeaderEvidence,
    target_atlas_reference_asr: NDArray[Any],
    target_atlas_voxel_size_um: float,
    output_voxel_size_um: float = DEFAULT_REFERENCE_DENSITY_RESOLUTION_UM,
    minimum_template_correlation: float = DEFAULT_MINIMUM_TEMPLATE_CORRELATION,
    source: ReferenceDensitySourceProvenance = STXVN5SV44_V1_SOURCE,
) -> ReferenceVascularDensity:
    """Prepare a read-only, provenance-bound population reference density."""

    validate_source_nifti_header(density_header, source=source, kind="density")
    validate_source_nifti_header(template_header, source=source, kind="template")
    density = _spatial_source_volume(
        source_density_mldvpa,
        expected_shape=source.source_shape_mldvpa,
        name="source vascular density",
        require_floating=True,
    )
    template = _spatial_source_volume(
        source_template_mldvpa,
        expected_shape=source.source_shape_mldvpa,
        name="source CCF template",
        require_floating=False,
    )

    alignment = validate_template_alignment(
        template,
        target_atlas_reference_asr,
        source_voxel_size_um=source.source_voxel_size_um,
        target_voxel_size_um=target_atlas_voxel_size_um,
        minimum_correlation=minimum_template_correlation,
    )

    density_asr = reorder_mldvpa_to_brainglobe_asr(density)
    resampled = resample_asr_center_aligned(
        density_asr,
        source_voxel_size_um=source.source_voxel_size_um,
        target_voxel_size_um=output_voxel_size_um,
    )
    prepared = symmetrize_asr_ml(resampled)
    prepared.setflags(write=False)
    output_resolution = _positive_finite(output_voxel_size_um, "output voxel size")
    output_shape = cast(tuple[int, int, int], prepared.shape)
    output_extent = tuple(float(size * output_resolution) for size in output_shape)
    expected_extent = source.extent_um_asr
    if output_extent != expected_extent:
        raise ReferenceDensityValidationError(
            f"prepared density extent {output_extent} does not equal source extent "
            f"{expected_extent}"
        )

    provenance = ReferenceDensityProvenance(
        source=source,
        output_frame=BRAINGLOBE_ASR_FRAME_AP_DV_ML,
        output_shape_asr=output_shape,
        output_voxel_size_um=output_resolution,
        output_extent_um_asr=output_extent,
        template_alignment=alignment,
    )
    return ReferenceVascularDensity(values_asr=prepared, provenance=provenance)


def _spatial_source_volume(
    values: NDArray[Any],
    *,
    expected_shape: tuple[int, int, int],
    name: str,
    require_floating: bool,
) -> NDArray[Any]:
    array = np.asanyarray(values)
    if array.ndim == 4 and array.shape[-1] == 1:
        array = array[..., 0]
    if array.ndim != 3 or array.shape != expected_shape:
        raise ReferenceDensityValidationError(
            f"{name} must have reviewed [ML,DV,AP] shape {expected_shape} "
            f"(optionally with one trailing volume), got {values.shape}"
        )
    if require_floating and not np.issubdtype(array.dtype, np.floating):
        raise ReferenceDensityValidationError(f"{name} must contain floating-point density values")
    return _validated_numeric_volume(array, name)


def _validated_numeric_volume(values: NDArray[Any], name: str) -> NDArray[Any]:
    array = np.asanyarray(values)
    if array.ndim != 3 or any(size <= 0 for size in array.shape):
        raise ReferenceDensityValidationError(f"{name} must be a non-empty three-dimensional array")
    if not np.issubdtype(array.dtype, np.number) or np.issubdtype(
        array.dtype,
        np.complexfloating,
    ):
        raise ReferenceDensityValidationError(f"{name} must have a real numeric dtype")
    _validate_nonnegative_finite(array, name)
    return array


def _validate_nonnegative_finite(values: NDArray[Any], name: str) -> None:
    for axis_zero in range(values.shape[0]):
        chunk = np.asanyarray(values[axis_zero])
        if not bool(np.all(np.isfinite(chunk))):
            raise ReferenceDensityValidationError(f"{name} contains non-finite values")
        if bool(np.any(chunk < 0)):
            raise ReferenceDensityValidationError(f"{name} contains negative values")


def _positive_finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ReferenceDensityValidationError(f"{name} must be positive and finite")
    return result


def _exact_output_shape(
    input_shape: tuple[int, ...],
    source_voxel_size_um: float,
    target_voxel_size_um: float,
) -> tuple[int, int, int]:
    if len(input_shape) != 3:
        raise ReferenceDensityValidationError("resampling requires a three-dimensional shape")
    output: list[int] = []
    for axis, size in enumerate(input_shape):
        extent = float(size * source_voxel_size_um)
        exact_count = extent / target_voxel_size_um
        rounded_count = round(exact_count)
        if rounded_count <= 0 or not math.isclose(
            exact_count,
            rounded_count,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ReferenceDensityValidationError(
                f"axis {axis} extent {extent:g} µm is not exactly divisible by "
                f"target voxel size {target_voxel_size_um:g} µm"
            )
        output.append(rounded_count)
    return (output[0], output[1], output[2])


def _validated_correlation_threshold(value: float) -> float:
    threshold = float(value)
    if not math.isfinite(threshold) or threshold <= 0 or threshold > 1:
        raise ReferenceDensityValidationError(
            "minimum template correlation must be finite and inside (0, 1]"
        )
    return threshold


def _nonzero_union_pearson(
    source: NDArray[Any],
    target: NDArray[Any],
) -> float:
    if source.shape != target.shape:
        raise ReferenceDensityValidationError("template correlation requires equal shapes")
    count = 0
    sum_source = 0.0
    sum_target = 0.0
    square_source = 0.0
    square_target = 0.0
    cross = 0.0
    for axis_zero in range(source.shape[0]):
        source_plane = np.asarray(source[axis_zero], dtype=np.float64)
        target_plane = np.asarray(target[axis_zero], dtype=np.float64)
        mask = (source_plane != 0) | (target_plane != 0)
        if not bool(np.any(mask)):
            continue
        source_values = source_plane[mask]
        target_values = target_plane[mask]
        count += int(source_values.size)
        sum_source += float(np.sum(source_values, dtype=np.float64))
        sum_target += float(np.sum(target_values, dtype=np.float64))
        square_source += float(np.dot(source_values, source_values))
        square_target += float(np.dot(target_values, target_values))
        cross += float(np.dot(source_values, target_values))
    if count < 2:
        raise ReferenceDensityValidationError(
            "template comparison has fewer than two non-zero-union voxels"
        )
    covariance = cross - (sum_source * sum_target / count)
    variance_source = square_source - (sum_source * sum_source / count)
    variance_target = square_target - (sum_target * sum_target / count)
    if variance_source <= 0 or variance_target <= 0:
        raise ReferenceDensityValidationError("template comparison has zero intensity variance")
    correlation = covariance / math.sqrt(variance_source * variance_target)
    if not math.isfinite(correlation):
        raise ReferenceDensityValidationError("template correlation is not finite")
    return min(1.0, max(-1.0, correlation))
