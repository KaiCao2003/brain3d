"""Direct AP/ML probe geometry resolved from the Allen annotation surface."""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Literal, cast

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.coordinates.anatomical_atlas import (
    brainglobe_physical_to_canonical_anatomical,
    canonical_anatomical_to_brainglobe_physical,
)
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.atlas_reference_models import AtlasBregmaReference
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.probe_models import (
    NormalizedProbePlacement,
    PlacementMethod,
    ProbeModelDefinition,
)
from mouse_brain_planner.domain.probe_plan_models import AtlasSurfaceProbeInput
from mouse_brain_planner.domain.surgery_common import AnimalSurgeryContext
from mouse_brain_planner.surgery.trajectory import (
    attach_surface_entries,
    placement_from_entry_angles_depth,
)

PINPOINT_BREGMA_REFERENCE_ID = "pinpoint-allen-mouse-25um-bregma-2025-11-04"
PINPOINT_BREGMA_SOURCE_COMMIT = "57be3cdc7d6230543ebbd367be1cbcf1a47862a5"
PINPOINT_BREGMA_SOURCE_SHA256 = "23880cef9abacbadd75b2b898a9b43cf1195ca75446f2c34f9ad0c278781f215"
PINPOINT_BREGMA_SOURCE_URL = (
    "https://raw.githubusercontent.com/VirtualBrainLab/Urchin/"
    f"{PINPOINT_BREGMA_SOURCE_COMMIT}/"
    "UnityClient/Packages/vbl.urchin/Scripts/Utils/Utils.cs"
)
SUPPORTED_DIRECT_ATLAS_IDENTITY = ("allen_mouse_25um", "1.2")


class AtlasSurfacePlanningError(ValueError):
    """Raised when direct atlas-surface geometry cannot be resolved exactly."""


def pinpoint_allen_bregma_reference(atlas: AtlasMetadata) -> AtlasBregmaReference:
    """Return Pinpoint's source-pinned Allen CCF bregma convention.

    Pinpoint's coordinate is AP/DV/ML = 5.2/0.332/5.7 mm in the CCF physical
    box.  It is an external planning convention, not a landmark embedded in the
    Allen annotation, which is why the source and limitation travel with every
    direct plan.
    """

    identity = (atlas.atlas_key, atlas.atlas_package_version)
    if identity != SUPPORTED_DIRECT_ATLAS_IDENTITY:
        raise AtlasSurfacePlanningError(
            "direct bregma planning is source-qualified only for "
            "allen_mouse_25um atlas package version 1.2"
        )
    if atlas.resolution_um != (25.0, 25.0, 25.0) or atlas.shape_voxels != (
        528,
        320,
        456,
    ):
        raise AtlasSurfacePlanningError(
            "Allen atlas dimensions do not match the source-qualified 25 µm package"
        )
    reference = AtlasBregmaReference(
        reference_id=PINPOINT_BREGMA_REFERENCE_ID,
        atlas_key=atlas.atlas_key,
        atlas_version=atlas.atlas_package_version,
        ap_um=5200.0,
        dv_um=332.0,
        ml_um=5700.0,
        source_title="Virtual Brain Lab Urchin/Pinpoint Allen CCF bregma defaults",
        source_url=PINPOINT_BREGMA_SOURCE_URL,
        source_revision=f"git commit {PINPOINT_BREGMA_SOURCE_COMMIT}",
        source_sha256=PINPOINT_BREGMA_SOURCE_SHA256,
        retrieved_on=date(2026, 7, 25),
        limitation=(
            "Pinpoint planning convention for Allen CCF coordinates; bregma is not encoded "
            "by the Allen annotation and this population-atlas reference is not an "
            "individual-animal registration."
        ),
    )
    _validate_reference_inside_atlas(reference, atlas)
    return reference


def resolve_atlas_surface_input(
    *,
    annotation: NDArray[np.integer[Any]],
    atlas: AtlasMetadata,
    insertion_ap_mm: float,
    insertion_ml_mm: float,
    surface_depth_mm: float,
    sagittal_angle_deg: float,
    probe_layout_rotation_deg: int,
    annotation_sha256: str,
    annotation_source: str,
    bregma_reference: AtlasBregmaReference | None = None,
) -> AtlasSurfaceProbeInput:
    """Resolve the superior boundary of the first annotated AP/ML-column voxel."""

    reference = bregma_reference or pinpoint_allen_bregma_reference(atlas)
    _validate_reference_matches_atlas(reference, atlas)
    volume = _validated_annotation(annotation, atlas)
    if (
        not isinstance(annotation_sha256, str)
        or len(annotation_sha256) != 64
        or any(character not in "0123456789abcdef" for character in annotation_sha256)
    ):
        raise AtlasSurfacePlanningError(
            "annotation SHA-256 must contain 64 lowercase hexadecimal characters"
        )
    normalized_annotation_source = annotation_source.strip()
    if not normalized_annotation_source:
        raise AtlasSurfacePlanningError("annotation source must be recorded")
    if isinstance(probe_layout_rotation_deg, bool) or probe_layout_rotation_deg not in {
        0,
        90,
    }:
        raise AtlasSurfacePlanningError("probe layout rotation must be exactly 0 or 90 degrees")
    layout_rotation = cast(Literal[0, 90], probe_layout_rotation_deg)

    ap_um = reference.ap_um - _finite(insertion_ap_mm, "insertion AP") * 1000.0
    # The operator-facing stereotaxic convention is ML- toward the animal's
    # left hemisphere and ML+ toward its right hemisphere. BrainGlobe ASR
    # physical ML increases from right to left, so the signed operator value
    # must be subtracted from the pinned bregma ML coordinate.
    ml_um = reference.ml_um - _finite(insertion_ml_mm, "insertion ML") * 1000.0
    ap_index = _physical_axis_index(
        ap_um,
        resolution_um=atlas.resolution_um[0],
        size=atlas.shape_voxels[0],
        label="AP",
    )
    ml_index = _physical_axis_index(
        ml_um,
        resolution_um=atlas.resolution_um[2],
        size=atlas.shape_voxels[2],
        label="ML",
    )
    annotated_dv = np.flatnonzero(volume[ap_index, :, ml_index] != 0)
    if annotated_dv.size == 0:
        raise AtlasSurfacePlanningError(
            "the requested AP/ML column contains no annotated brain surface"
        )
    surface_dv_index = int(annotated_dv[0])
    surface_entry = BrainGlobePhysicalPoint(
        atlas_key=atlas.atlas_key,
        atlas_version=atlas.atlas_package_version,
        ap_um=ap_um,
        dv_um=surface_dv_index * atlas.resolution_um[1],
        ml_um=ml_um,
    )
    BrainGlobeAtlasSpace(atlas).physical_to_index(surface_entry)
    try:
        return AtlasSurfaceProbeInput(
            bregma_reference=reference,
            insertion_ap_mm=insertion_ap_mm,
            insertion_ml_mm=insertion_ml_mm,
            surface_depth_mm=surface_depth_mm,
            sagittal_angle_deg=sagittal_angle_deg,
            probe_layout_rotation_deg=layout_rotation,
            surface_entry_physical=surface_entry,
            surface_dv_index=surface_dv_index,
            surface_dv_resolution_um=atlas.resolution_um[1],
            annotation_source=normalized_annotation_source,
            annotation_sha256=annotation_sha256,
        )
    except ValueError as error:
        raise AtlasSurfacePlanningError(str(error)) from error


def placement_from_atlas_surface_input(
    *,
    input_data: AtlasSurfaceProbeInput,
    atlas: AtlasMetadata,
    context: AnimalSurgeryContext,
    model: ProbeModelDefinition,
    name: str,
    custom_geometry_acknowledged: bool = False,
) -> NormalizedProbePlacement:
    """Build the exact entry-to-tip path and shank-plane orientation."""

    _validate_reference_matches_atlas(input_data.bregma_reference, atlas)
    entry_physical = input_data.surface_entry_physical
    BrainGlobeAtlasSpace(atlas).physical_to_index(entry_physical)
    entry = brainglobe_physical_to_canonical_anatomical(entry_physical, atlas)
    azimuth_deg, elevation_deg = _legacy_angles_for_sagittal_tilt(input_data.sagittal_angle_deg)
    # Catalog shank-0 is the operator-facing "shank 1" and AP/ML anchors that
    # shank's surface crossing.  At 0 degrees the remaining NP2013 shanks must
    # extend posterior from it, leaving shank 1 most anterior; at 90 degrees
    # clockwise (viewed dorsally) they extend animal-right, leaving shank 1
    # animal-left-most.  The helper's unrotated spacing axis is canonical +ML,
    # so those two exposed layouts map to internal -90 and 0 respectively.
    internal_axial_rotation_deg = -90.0 + input_data.probe_layout_rotation_deg
    placement = placement_from_entry_angles_depth(
        context=context,
        model=model,
        name=name,
        entry=entry,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
        insertion_depth_um=input_data.surface_depth_mm * 1000.0,
        axial_rotation_deg=internal_axial_rotation_deg,
        custom_geometry_acknowledged=custom_geometry_acknowledged,
    )
    placement = attach_surface_entries(
        placement.model_copy(update={"method": PlacementMethod.ATLAS_SURFACE_AP_ML}),
        skull_entry=None,
        brain_entry=entry,
    )
    # Reject trajectories whose requested path ends outside the exact atlas
    # extent.  Annotation ID zero at the endpoint is not rejected because
    # ventricles and other unlabeled spaces can occur along a valid insertion.
    canonical_anatomical_to_brainglobe_physical(placement.tip, atlas)
    return placement


def validate_resolved_surface_against_annotation(
    *,
    input_data: AtlasSurfaceProbeInput,
    annotation: NDArray[np.integer[Any]],
    atlas: AtlasMetadata,
    annotation_sha256: str,
) -> None:
    """Re-resolve persisted AP/ML controls and reject stale surface evidence."""

    expected = resolve_atlas_surface_input(
        annotation=annotation,
        atlas=atlas,
        insertion_ap_mm=input_data.insertion_ap_mm,
        insertion_ml_mm=input_data.insertion_ml_mm,
        surface_depth_mm=input_data.surface_depth_mm,
        sagittal_angle_deg=input_data.sagittal_angle_deg,
        probe_layout_rotation_deg=input_data.probe_layout_rotation_deg,
        annotation_sha256=annotation_sha256,
        annotation_source=input_data.annotation_source,
        bregma_reference=input_data.bregma_reference,
    )
    if expected != input_data:
        raise AtlasSurfacePlanningError(
            "persisted atlas-surface evidence does not match the loaded annotation"
        )


def expected_sagittal_inward_direction(angle_deg: float) -> tuple[float, float, float]:
    """Return canonical AP/ML/DV direction for the user-visible tilt."""

    angle = _finite(angle_deg, "sagittal angle")
    if not -90 < angle < 90:
        raise AtlasSurfacePlanningError(
            "sagittal angle must be strictly between -90 and 90 degrees"
        )
    radians = math.radians(angle)
    return (-math.sin(radians), 0.0, -math.cos(radians))


def _legacy_angles_for_sagittal_tilt(angle_deg: float) -> tuple[float, float]:
    ap, _ml, dv = expected_sagittal_inward_direction(angle_deg)
    horizontal = abs(ap)
    elevation = math.degrees(math.atan2(dv, horizontal))
    azimuth = 0.0 if horizontal <= 1e-12 or ap > 0 else 180.0
    return azimuth, elevation


def _validated_annotation(
    annotation: NDArray[np.integer[Any]],
    atlas: AtlasMetadata,
) -> NDArray[np.integer[Any]]:
    if not isinstance(annotation, np.ndarray) or annotation.ndim != 3:
        raise AtlasSurfacePlanningError("atlas surface requires one 3-D NumPy annotation")
    if annotation.shape != atlas.shape_voxels:
        raise AtlasSurfacePlanningError(
            f"annotation shape {annotation.shape} does not match atlas {atlas.shape_voxels}"
        )
    if not np.issubdtype(annotation.dtype, np.integer):
        raise AtlasSurfacePlanningError("atlas annotation must use an integer dtype")
    return annotation


def _physical_axis_index(
    value_um: float,
    *,
    resolution_um: float,
    size: int,
    label: str,
) -> int:
    extent = resolution_um * size
    if value_um < 0 or value_um >= extent:
        raise AtlasSurfacePlanningError(
            f"bregma-relative {label} coordinate resolves outside atlas [0, {extent:g}) µm"
        )
    return math.floor(value_um / resolution_um)


def _validate_reference_matches_atlas(
    reference: AtlasBregmaReference,
    atlas: AtlasMetadata,
) -> None:
    if (reference.atlas_key, reference.atlas_version) != (
        atlas.atlas_key,
        atlas.atlas_package_version,
    ):
        raise AtlasSurfacePlanningError("bregma reference atlas identity does not match project")
    _validate_reference_inside_atlas(reference, atlas)


def _validate_reference_inside_atlas(
    reference: AtlasBregmaReference,
    atlas: AtlasMetadata,
) -> None:
    point = BrainGlobePhysicalPoint(
        atlas_key=reference.atlas_key,
        atlas_version=reference.atlas_version,
        ap_um=reference.ap_um,
        dv_um=reference.dv_um,
        ml_um=reference.ml_um,
    )
    BrainGlobeAtlasSpace(atlas).physical_to_index(point)


def _finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AtlasSurfacePlanningError(f"{label} must be a finite number")
    return float(value)
