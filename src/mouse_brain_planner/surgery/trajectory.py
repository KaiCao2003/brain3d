"""Normalize probe placement inputs and map source-defined recording sites."""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.coordinates.transforms import transform_point, transform_vector
from mouse_brain_planner.domain.probe_models import (
    NormalizedProbePlacement,
    PlacedProbeShank,
    PlacedRecordingSite,
    PlacementMethod,
    ProbeModelDefinition,
    ProbeVerificationStatus,
)
from mouse_brain_planner.domain.stereotaxy_models import (
    BregmaRelativeTargetMM,
    StereotaxicCalibration,
)
from mouse_brain_planner.domain.surgery_common import (
    AnimalSurgeryContext,
    UnitDirectionAPMLDV,
)
from mouse_brain_planner.domain.transform_models import (
    AnatomicalPoint,
    AnatomicalTransform,
    AnatomicalVector,
    TransformMethod,
)
from mouse_brain_planner.surgery.stereotaxy import bregma_relative_target_to_point


class ProbePlacementError(ValueError):
    """Raised when a placement would require guessing geometry or conventions."""


def direction_from_angles(
    *,
    frame_id: str,
    azimuth_deg: float,
    elevation_deg: float,
) -> UnitDirectionAPMLDV:
    """Return the documented inward direction for azimuth/elevation.

    Azimuth rotates about positive DV from positive AP toward positive ML.
    Elevation rotates from the AP/ML plane toward positive DV.  A perfectly
    vertical direction has canonical azimuth zero because azimuth is otherwise
    undefined at the pole.
    """

    if not math.isfinite(azimuth_deg) or azimuth_deg < -180 or azimuth_deg > 180:
        raise ProbePlacementError("azimuth must be finite and within [-180, 180] degrees")
    if not math.isfinite(elevation_deg) or elevation_deg < -90 or elevation_deg > 90:
        raise ProbePlacementError("elevation must be finite and within [-90, 90] degrees")
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    horizontal = math.cos(elevation)
    ap = horizontal * math.cos(azimuth)
    ml = horizontal * math.sin(azimuth)
    dv = math.sin(elevation)
    if abs(horizontal) <= 1e-12:
        ap = 0.0
        ml = 0.0
    return UnitDirectionAPMLDV(frame_id=frame_id, ap=ap, ml=ml, dv=dv)


def angles_from_direction(direction: UnitDirectionAPMLDV) -> tuple[float, float]:
    """Invert :func:`direction_from_angles` using canonical vertical azimuth zero."""

    horizontal = math.hypot(direction.ap, direction.ml)
    elevation = math.degrees(math.atan2(direction.dv, horizontal))
    azimuth = 0.0 if horizontal <= 1e-12 else math.degrees(math.atan2(direction.ml, direction.ap))
    if math.isclose(azimuth, -180.0, rel_tol=0, abs_tol=1e-12):
        azimuth = 180.0
    return azimuth, elevation


def placement_from_entry_target(
    *,
    context: AnimalSurgeryContext,
    model: ProbeModelDefinition,
    name: str,
    entry: AnatomicalPoint,
    target: AnatomicalPoint,
    tip_extension_beyond_target_um: float = 0,
    axial_rotation_deg: float = 0,
    selected_site_ids: Iterable[str] = (),
    custom_geometry_acknowledged: bool = False,
    notes: str = "",
) -> NormalizedProbePlacement:
    """Normalize entry+target, optionally extending the physical tip past target."""

    _same_frame(entry, target)
    extension = _nonnegative_finite(
        tip_extension_beyond_target_um,
        "tip extension beyond target",
    )
    vector = _array(target) - _array(entry)
    target_depth = float(np.linalg.norm(vector))
    if target_depth <= 0:
        raise ProbePlacementError("entry and target must be distinct")
    direction_values = vector / target_depth
    tip = _point(entry.frame_id, _array(target) + direction_values * extension)
    return _placement(
        context=context,
        model=model,
        name=name,
        method=PlacementMethod.ENTRY_TARGET,
        entry=entry,
        target=target,
        tip=tip,
        axial_rotation_deg=axial_rotation_deg,
        selected_site_ids=selected_site_ids,
        custom_geometry_acknowledged=custom_geometry_acknowledged,
        notes=notes,
    )


def placement_from_entry_angles_depth(
    *,
    context: AnimalSurgeryContext,
    model: ProbeModelDefinition,
    name: str,
    entry: AnatomicalPoint,
    azimuth_deg: float,
    elevation_deg: float,
    insertion_depth_um: float,
    target_depth_um: float | None = None,
    axial_rotation_deg: float = 0,
    selected_site_ids: Iterable[str] = (),
    custom_geometry_acknowledged: bool = False,
    notes: str = "",
) -> NormalizedProbePlacement:
    """Normalize entry, angles, depth, and an optional target depth."""

    depth = _positive_finite(insertion_depth_um, "insertion depth")
    target_depth = (
        depth
        if target_depth_um is None
        else _nonnegative_finite(
            target_depth_um,
            "target depth",
        )
    )
    if target_depth > depth:
        raise ProbePlacementError(
            f"target depth {target_depth:g} exceeds insertion depth {depth:g} micrometres"
        )
    direction = direction_from_angles(
        frame_id=entry.frame_id,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
    )
    values = np.asarray(direction.as_ap_ml_dv(), dtype=np.float64)
    tip = _point(entry.frame_id, _array(entry) + values * depth)
    target = _point(entry.frame_id, _array(entry) + values * target_depth)
    return _placement(
        context=context,
        model=model,
        name=name,
        method=PlacementMethod.ENTRY_ANGLES_DEPTH,
        entry=entry,
        target=target,
        tip=tip,
        axial_rotation_deg=axial_rotation_deg,
        selected_site_ids=selected_site_ids,
        custom_geometry_acknowledged=custom_geometry_acknowledged,
        notes=notes,
    )


def placement_from_target_angles_depth(
    *,
    context: AnimalSurgeryContext,
    model: ProbeModelDefinition,
    name: str,
    target: AnatomicalPoint,
    azimuth_deg: float,
    elevation_deg: float,
    insertion_depth_um: float,
    axial_rotation_deg: float = 0,
    selected_site_ids: Iterable[str] = (),
    custom_geometry_acknowledged: bool = False,
    notes: str = "",
) -> NormalizedProbePlacement:
    """Normalize target+angles+depth, explicitly treating target as physical tip."""

    depth = _positive_finite(insertion_depth_um, "insertion depth")
    direction = direction_from_angles(
        frame_id=target.frame_id,
        azimuth_deg=azimuth_deg,
        elevation_deg=elevation_deg,
    )
    values = np.asarray(direction.as_ap_ml_dv(), dtype=np.float64)
    entry = _point(target.frame_id, _array(target) - values * depth)
    return _placement(
        context=context,
        model=model,
        name=name,
        method=PlacementMethod.TARGET_ANGLES_DEPTH,
        entry=entry,
        target=target,
        tip=target,
        axial_rotation_deg=axial_rotation_deg,
        selected_site_ids=selected_site_ids,
        custom_geometry_acknowledged=custom_geometry_acknowledged,
        notes=notes,
    )


def placement_from_stereotaxic_target(
    *,
    calibration: StereotaxicCalibration,
    model: ProbeModelDefinition,
    name: str,
    target: AnatomicalPoint,
    manipulator_azimuth_deg: float,
    manipulator_elevation_deg: float,
    insertion_depth_um: float,
    axial_rotation_deg: float = 0,
    selected_site_ids: Iterable[str] = (),
    custom_geometry_acknowledged: bool = False,
    notes: str = "",
) -> NormalizedProbePlacement:
    """Normalize bregma-relative target and declared manipulator angles.

    The manipulator angles use the same explicit convention as every normalized
    trajectory.  A failed calibration is rejected rather than converted with a
    warning that downstream code might ignore.
    """

    if not calibration.permits_planning:
        raise ProbePlacementError("failed stereotaxic calibration cannot create a placement")
    if target.frame_id != calibration.stereotaxic_frame.frame_id:
        raise ProbePlacementError("target frame does not match stereotaxic calibration frame")
    placement = placement_from_target_angles_depth(
        context=calibration.context,
        model=model,
        name=name,
        target=target,
        azimuth_deg=manipulator_azimuth_deg,
        elevation_deg=manipulator_elevation_deg,
        insertion_depth_um=insertion_depth_um,
        axial_rotation_deg=axial_rotation_deg,
        selected_site_ids=selected_site_ids,
        custom_geometry_acknowledged=custom_geometry_acknowledged,
        notes=notes,
    )
    return placement.model_copy(update={"method": PlacementMethod.STEREOTAXIC_TARGET_MANIPULATOR})


def placement_from_bregma_relative_mm(
    *,
    calibration: StereotaxicCalibration,
    model: ProbeModelDefinition,
    name: str,
    target: BregmaRelativeTargetMM,
    manipulator_azimuth_deg: float,
    manipulator_elevation_deg: float,
    insertion_depth_um: float,
    axial_rotation_deg: float = 0,
    selected_site_ids: Iterable[str] = (),
    custom_geometry_acknowledged: bool = False,
    notes: str = "",
) -> NormalizedProbePlacement:
    """Canonical direct implant entry from calibrated bregma-relative millimetres."""

    target_point = bregma_relative_target_to_point(
        target=target,
        calibration=calibration,
    )
    return placement_from_stereotaxic_target(
        calibration=calibration,
        model=model,
        name=name,
        target=target_point,
        manipulator_azimuth_deg=manipulator_azimuth_deg,
        manipulator_elevation_deg=manipulator_elevation_deg,
        insertion_depth_um=insertion_depth_um,
        axial_rotation_deg=axial_rotation_deg,
        selected_site_ids=selected_site_ids,
        custom_geometry_acknowledged=custom_geometry_acknowledged,
        notes=notes,
    )


def transform_probe_placement_uniform(
    placement: NormalizedProbePlacement,
    transform: AnatomicalTransform,
) -> NormalizedProbePlacement:
    """Map a complete probe pose through a proper rigid/similarity transform.

    A probe pose is more than its target point: its insertion direction, local
    lateral/normal basis, recording-site offsets, shank offsets, and envelope
    dimensions must cross the same calibration boundary.  Full affine maps are
    deliberately rejected because they shear a physical probe cross-section;
    that requires an explicit non-rigid envelope model rather than an
    orthonormal-placement approximation.
    """

    if transform.method not in {TransformMethod.RIGID, TransformMethod.SIMILARITY}:
        raise ProbePlacementError(
            "probe geometry projection requires a rigid or similarity atlas transform; "
            "an affine transform would shear the physical probe envelope"
        )
    if placement.entry.frame_id != transform.source_frame.frame_id:
        raise ProbePlacementError("probe placement frame does not match calibration transform")

    source_lateral, source_normal = _placement_cross_section_axes(placement)
    source_basis = (
        np.asarray(placement.inward_direction.as_ap_ml_dv(), dtype=np.float64),
        source_lateral,
        source_normal,
    )
    transformed_basis: list[NDArray[np.float64]] = []
    scales: list[float] = []
    for values in source_basis:
        mapped = transform_vector(
            transform,
            AnatomicalVector(
                frame_id=placement.entry.frame_id,
                ap_um=float(values[0]),
                ml_um=float(values[1]),
                dv_um=float(values[2]),
            ),
        )
        mapped_values = np.asarray(mapped.as_ap_ml_dv(), dtype=np.float64)
        scale = float(np.linalg.norm(mapped_values))
        if not math.isfinite(scale) or scale <= 0:
            raise ProbePlacementError("calibration transform produced an invalid probe basis")
        transformed_basis.append(mapped_values / scale)
        scales.append(scale)
    uniform_scale = scales[0]
    if any(
        not math.isclose(value, uniform_scale, rel_tol=1e-9, abs_tol=1e-12) for value in scales[1:]
    ):
        raise ProbePlacementError("calibration transform does not preserve a uniform probe scale")

    inward, lateral, normal = transformed_basis
    if not np.allclose(np.cross(-inward, lateral), normal, rtol=0, atol=1e-9):
        raise ProbePlacementError("calibration transform changed the probe basis handedness")

    entry = transform_point(transform, placement.entry)
    target = transform_point(transform, placement.target)
    tip = transform_point(transform, placement.tip)
    transformed_vector = _array(tip) - _array(entry)
    transformed_depth = float(np.linalg.norm(transformed_vector))
    if transformed_depth <= 0 or not math.isclose(
        transformed_depth,
        placement.insertion_depth_um * uniform_scale,
        rel_tol=1e-9,
        abs_tol=1e-6,
    ):
        raise ProbePlacementError("calibration transform produced inconsistent probe depth")
    transformed_direction = transformed_vector / transformed_depth
    if not np.allclose(transformed_direction, inward, rtol=0, atol=1e-9):
        raise ProbePlacementError("calibration transform produced inconsistent probe direction")
    azimuth, elevation = angles_from_direction(
        UnitDirectionAPMLDV(
            frame_id=entry.frame_id,
            ap=float(inward[0]),
            ml=float(inward[1]),
            dv=float(inward[2]),
        )
    )

    def optional_point(point: AnatomicalPoint | None) -> AnatomicalPoint | None:
        return None if point is None else transform_point(transform, point)

    return NormalizedProbePlacement.model_validate(
        {
            **placement.model_dump(mode="python"),
            "entry": entry,
            "target": target,
            "tip": tip,
            "skull_entry": optional_point(placement.skull_entry),
            "brain_entry": optional_point(placement.brain_entry),
            "inward_direction": UnitDirectionAPMLDV(
                frame_id=entry.frame_id,
                ap=float(inward[0]),
                ml=float(inward[1]),
                dv=float(inward[2]),
            ),
            "local_lateral_direction": UnitDirectionAPMLDV(
                frame_id=entry.frame_id,
                ap=float(lateral[0]),
                ml=float(lateral[1]),
                dv=float(lateral[2]),
            ),
            "local_normal_direction": UnitDirectionAPMLDV(
                frame_id=entry.frame_id,
                ap=float(normal[0]),
                ml=float(normal[1]),
                dv=float(normal[2]),
            ),
            "model_to_placement_uniform_scale": (
                placement.model_to_placement_uniform_scale * uniform_scale
            ),
            "insertion_depth_um": transformed_depth,
            "azimuth_deg": azimuth,
            "elevation_deg": elevation,
        }
    )


def attach_surface_entries(
    placement: NormalizedProbePlacement,
    *,
    skull_entry: AnatomicalPoint | None,
    brain_entry: AnatomicalPoint | None,
) -> NormalizedProbePlacement:
    """Attach and validate ordered collinear skull/brain surface intersections."""

    return NormalizedProbePlacement.model_validate(
        {
            **placement.model_dump(mode="python"),
            "skull_entry": skull_entry,
            "brain_entry": brain_entry,
        }
    )


def placed_recording_sites(
    model: ProbeModelDefinition,
    placement: NormalizedProbePlacement,
    *,
    selected_only: bool = False,
) -> tuple[PlacedRecordingSite, ...]:
    """Map source-defined local recording sites into anatomical AP/ML/DV space."""

    _validate_model_placement_pair(model, placement)
    available = {site.site_id for shank in model.shanks for site in shank.sites}
    unknown = tuple(site_id for site_id in placement.selected_site_ids if site_id not in available)
    if unknown:
        raise ProbePlacementError(
            "placement selects unknown recording sites: " + ", ".join(unknown)
        )

    inward = np.asarray(placement.inward_direction.as_ap_ml_dv(), dtype=np.float64)
    axial_toward_base = -inward
    lateral, normal = _placement_cross_section_axes(placement)
    geometry_scale = placement.model_to_placement_uniform_scale
    tip = _array(placement.tip)
    selected = set(placement.selected_site_ids)
    placed: list[PlacedRecordingSite] = []
    for shank in model.shanks:
        for site in shank.sites:
            if selected_only and site.site_id not in selected:
                continue
            local = site.local
            point = (
                tip
                + axial_toward_base * (local.axial_from_tip_um * geometry_scale)
                + lateral * ((shank.center_lateral_um + local.lateral_um) * geometry_scale)
                + normal * ((shank.center_normal_um + local.normal_um) * geometry_scale)
            )
            placed.append(
                PlacedRecordingSite(
                    placement_uuid=placement.placement_uuid,
                    probe_model_id=model.model_id,
                    probe_model_version=model.model_version,
                    shank_id=shank.shank_id,
                    site_id=site.site_id,
                    role=site.role,
                    bank=site.bank,
                    point=_point(placement.entry.frame_id, point),
                )
            )
    return tuple(placed)


def placed_shank_centerlines(
    model: ProbeModelDefinition,
    placement: NormalizedProbePlacement,
) -> tuple[PlacedProbeShank, ...]:
    """Map every source-defined shank offset into the anatomical frame."""

    _validate_model_placement_pair(model, placement)
    lateral, normal = _placement_cross_section_axes(placement)
    geometry_scale = placement.model_to_placement_uniform_scale
    entry = _array(placement.entry)
    tip = _array(placement.tip)
    return tuple(
        PlacedProbeShank(
            placement_uuid=placement.placement_uuid,
            probe_model_id=model.model_id,
            probe_model_version=model.model_version,
            shank_id=shank.shank_id,
            entry=_point(
                placement.entry.frame_id,
                entry
                + lateral * (shank.center_lateral_um * geometry_scale)
                + normal * (shank.center_normal_um * geometry_scale),
            ),
            tip=_point(
                placement.entry.frame_id,
                tip
                + lateral * (shank.center_lateral_um * geometry_scale)
                + normal * (shank.center_normal_um * geometry_scale),
            ),
            width_um=shank.width_um * geometry_scale,
            thickness_um=shank.thickness_um * geometry_scale,
        )
        for shank in model.shanks
    )


def placement_permits_final_export(
    model: ProbeModelDefinition,
    placement: NormalizedProbePlacement,
) -> bool:
    """Apply the verified/custom geometry gate without implying surgical safety."""

    _validate_model_placement_pair(model, placement)
    if model.verification.status is ProbeVerificationStatus.VERIFIED:
        return True
    return placement.custom_geometry_acknowledged


def _placement(
    *,
    context: AnimalSurgeryContext,
    model: ProbeModelDefinition,
    name: str,
    method: PlacementMethod,
    entry: AnatomicalPoint,
    target: AnatomicalPoint,
    tip: AnatomicalPoint,
    axial_rotation_deg: float,
    selected_site_ids: Iterable[str],
    custom_geometry_acknowledged: bool,
    notes: str,
) -> NormalizedProbePlacement:
    vector = _array(tip) - _array(entry)
    depth = float(np.linalg.norm(vector))
    if depth <= 0:
        raise ProbePlacementError("normalized entry and tip must be distinct")
    too_short = tuple(
        shank.shank_id
        for shank in model.shanks
        if depth > shank.length_um + max(1e-6, shank.length_um * 1e-10)
    )
    if too_short:
        raise ProbePlacementError(
            "insertion depth exceeds declared shank length for: " + ", ".join(too_short)
        )
    direction_values = vector / depth
    direction = UnitDirectionAPMLDV(
        frame_id=entry.frame_id,
        ap=float(direction_values[0]),
        ml=float(direction_values[1]),
        dv=float(direction_values[2]),
    )
    azimuth, elevation = angles_from_direction(direction)
    lateral, normal = _local_cross_section_axes(
        direction_values,
        axial_rotation_deg=axial_rotation_deg,
    )
    return NormalizedProbePlacement(
        name=name,
        context=context,
        probe_model_id=model.model_id,
        probe_model_version=model.model_version,
        method=method,
        entry=entry,
        target=target,
        tip=tip,
        inward_direction=direction,
        local_lateral_direction=UnitDirectionAPMLDV(
            frame_id=entry.frame_id,
            ap=float(lateral[0]),
            ml=float(lateral[1]),
            dv=float(lateral[2]),
        ),
        local_normal_direction=UnitDirectionAPMLDV(
            frame_id=entry.frame_id,
            ap=float(normal[0]),
            ml=float(normal[1]),
            dv=float(normal[2]),
        ),
        model_to_placement_uniform_scale=1.0,
        insertion_depth_um=depth,
        azimuth_deg=azimuth,
        elevation_deg=elevation,
        axial_rotation_deg=axial_rotation_deg,
        selected_site_ids=tuple(selected_site_ids),
        custom_geometry_acknowledged=custom_geometry_acknowledged,
        notes=notes,
    )


def _placement_cross_section_axes(
    placement: NormalizedProbePlacement,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    if (
        placement.local_lateral_direction is not None
        and placement.local_normal_direction is not None
    ):
        return (
            np.asarray(placement.local_lateral_direction.as_ap_ml_dv(), dtype=np.float64),
            np.asarray(placement.local_normal_direction.as_ap_ml_dv(), dtype=np.float64),
        )
    inward = np.asarray(placement.inward_direction.as_ap_ml_dv(), dtype=np.float64)
    return _local_cross_section_axes(
        inward,
        axial_rotation_deg=placement.axial_rotation_deg,
    )


def _local_cross_section_axes(
    inward: NDArray[np.float64],
    *,
    axial_rotation_deg: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    reference = np.asarray((0.0, 1.0, 0.0), dtype=np.float64)
    projected = reference - float(np.dot(reference, inward)) * inward
    if float(np.linalg.norm(projected)) <= 1e-10:
        reference = np.asarray((1.0, 0.0, 0.0), dtype=np.float64)
        projected = reference - float(np.dot(reference, inward)) * inward
    lateral = projected / np.linalg.norm(projected)
    axial_toward_base = -inward
    normal = np.cross(axial_toward_base, lateral)
    normal /= np.linalg.norm(normal)
    angle = math.radians(axial_rotation_deg)
    rotated_lateral = _rotate_about_axis(lateral, inward, angle)
    rotated_normal = _rotate_about_axis(normal, inward, angle)
    return rotated_lateral, rotated_normal


def _rotate_about_axis(
    vector: NDArray[np.float64],
    axis: NDArray[np.float64],
    angle: float,
) -> NDArray[np.float64]:
    return (
        vector * math.cos(angle)
        + np.cross(axis, vector) * math.sin(angle)
        + axis * float(np.dot(axis, vector)) * (1.0 - math.cos(angle))
    )


def _validate_model_placement_pair(
    model: ProbeModelDefinition,
    placement: NormalizedProbePlacement,
) -> None:
    if (placement.probe_model_id, placement.probe_model_version) != (
        model.model_id,
        model.model_version,
    ):
        raise ProbePlacementError("placement references a different probe model identity")


def _same_frame(first: AnatomicalPoint, second: AnatomicalPoint) -> None:
    if first.frame_id != second.frame_id:
        raise ProbePlacementError("placement points must use one explicit coordinate frame")


def _positive_finite(value: float, label: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ProbePlacementError(f"{label} must be finite and positive")
    return float(value)


def _nonnegative_finite(value: float, label: str) -> float:
    if not math.isfinite(value) or value < 0:
        raise ProbePlacementError(f"{label} must be finite and non-negative")
    return float(value)


def _array(point: AnatomicalPoint) -> NDArray[np.float64]:
    return np.asarray(point.as_ap_ml_dv(), dtype=np.float64)


def _point(frame_id: str, values: NDArray[np.float64]) -> AnatomicalPoint:
    return AnatomicalPoint(
        frame_id=frame_id,
        ap_um=float(values[0]),
        ml_um=float(values[1]),
        dv_um=float(values[2]),
    )
