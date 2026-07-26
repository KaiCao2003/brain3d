"""Calibrated target-to-probe planning service shared by bridge and tests."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.coordinates.anatomical_atlas import (
    canonical_anatomical_to_brainglobe_physical,
)
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.coordinates.transforms import transform_point
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.probe_models import NormalizedProbePlacement, ProbeModelDefinition
from mouse_brain_planner.domain.probe_plan_models import (
    ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION,
    LEGACY_PROBE_PLANNING_ALGORITHM_VERSION,
    PROBE_PLANNING_ALGORITHM_VERSION,
    STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION,
    AtlasSurfaceProbeInput,
    BregmaRelativeEntryInput,
    ProbeManipulatorInput,
    ProbePlacementInput,
    ProbePlacementMode,
    ProbePlanRecord,
    probe_plan_input_digest,
)
from mouse_brain_planner.domain.stereotaxy_models import (
    AtlasRegisteredCalibration,
    BregmaRelativeTargetMM,
    atlas_registered_calibration_sha256,
)
from mouse_brain_planner.domain.surgery_common import AnimalSurgeryContext, UnitDirectionAPMLDV
from mouse_brain_planner.domain.transform_models import AnatomicalPoint
from mouse_brain_planner.probes.catalog import validate_probe_model_catalog_snapshot
from mouse_brain_planner.surgery.atlas_surface_planning import (
    placement_from_atlas_surface_input,
    resolve_atlas_surface_input,
    validate_resolved_surface_against_annotation,
)
from mouse_brain_planner.surgery.stereotaxy import bregma_relative_target_to_point
from mouse_brain_planner.surgery.trajectory import (
    direction_from_angles,
    placement_from_entry_angles_depth,
    placement_from_entry_target,
    placement_from_stereotaxic_target,
    placement_from_target_angles_depth,
    transform_probe_placement_uniform,
)

TARGET_PROJECTION_ALGORITHM_VERSION = "bregma-target-through-subject-atlas-calibration-v1"
PROBE_TARGET_MATCH_ABSOLUTE_TOLERANCE_UM = 1e-6
PROBE_DIRECTION_MATCH_ABSOLUTE_TOLERANCE = 1e-9
PROBE_ANGLE_MATCH_ABSOLUTE_TOLERANCE_DEG = 1e-8
PROBE_SCALE_MATCH_ABSOLUTE_TOLERANCE = 1e-12


class ProbePlanningError(ValueError):
    """Raised when a plan would require an invalid or implicit assumption."""


def build_atlas_surface_probe_plan(
    *,
    annotation: NDArray[np.integer[Any]],
    annotation_sha256: str,
    annotation_source: str,
    atlas: AtlasMetadata,
    model: ProbeModelDefinition,
    insertion_ap_mm: float,
    insertion_ml_mm: float,
    surface_depth_mm: float,
    sagittal_angle_deg: float,
    probe_layout_rotation_deg: int,
    subject_id: str | None,
    name: str | None = None,
    context: AnimalSurgeryContext | None = None,
    plan_uuid: UUID | None = None,
    plan_version: int = 1,
    created_at: datetime | None = None,
) -> tuple[ProbePlanRecord, BrainGlobePhysicalPoint]:
    """Create the calibration-free Pinpoint-style atlas-surface plan."""

    validate_probe_model_catalog_snapshot(model)
    if context is not None and context.subject_id != subject_id:
        raise ProbePlanningError("preserved plan context does not match project subject")
    actual_context = context or AnimalSurgeryContext(subject_id=subject_id)
    input_data = resolve_atlas_surface_input(
        annotation=annotation,
        atlas=atlas,
        insertion_ap_mm=insertion_ap_mm,
        insertion_ml_mm=insertion_ml_mm,
        surface_depth_mm=surface_depth_mm,
        sagittal_angle_deg=sagittal_angle_deg,
        probe_layout_rotation_deg=probe_layout_rotation_deg,
        annotation_sha256=annotation_sha256,
        annotation_source=annotation_source,
    )
    normalized_name = (
        name.strip()
        if name is not None and name.strip()
        else _default_surface_plan_name(model, input_data)
    )
    placement = placement_from_atlas_surface_input(
        input_data=input_data,
        atlas=atlas,
        context=actual_context,
        model=model,
        name=normalized_name,
        custom_geometry_acknowledged=False,
    )
    actual_plan_uuid = plan_uuid or uuid4()
    projection_sha256 = atlas_surface_projection_digest(input_data)
    input_sha256 = probe_plan_input_digest(
        plan_uuid=actual_plan_uuid,
        plan_version=plan_version,
        name=normalized_name,
        source_target=None,
        probe_model=model,
        placement=placement,
        calibration_uuid=None,
        calibration_version=None,
        calibration_sha256=None,
        atlas_metadata_sha256=atlas.metadata_sha256,
        projection_sha256=projection_sha256,
        surface_relative_input=input_data,
        planning_algorithm_version=ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION,
    )
    values: dict[str, object] = {
        "plan_uuid": actual_plan_uuid,
        "plan_version": plan_version,
        "name": normalized_name,
        "source_target": None,
        "probe_model": model,
        "manipulator_input": None,
        "placement_input": None,
        "surface_relative_input": input_data,
        "placement": placement,
        "calibration_uuid": None,
        "calibration_version": None,
        "calibration_sha256": None,
        "atlas_metadata_sha256": atlas.metadata_sha256,
        "projection_sha256": projection_sha256,
        "planning_algorithm_version": ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION,
        "input_sha256": input_sha256,
    }
    if created_at is not None:
        values["created_at"] = created_at
    return ProbePlanRecord.model_validate(values), input_data.surface_entry_physical


def validate_atlas_surface_probe_plan_semantics(
    *,
    plan: ProbePlanRecord,
    atlas: AtlasMetadata,
    annotation: NDArray[np.integer[Any]] | None = None,
    annotation_sha256: str | None = None,
) -> None:
    """Reproduce v4 geometry, optionally checking the loaded annotation bytes."""

    if plan.planning_algorithm_version != ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION:
        raise ProbePlanningError("plan is not an atlas-surface v4 plan")
    input_data = plan.surface_relative_input
    if input_data is None:
        raise ProbePlanningError("atlas-surface plan is missing preserved inputs")
    validate_probe_model_catalog_snapshot(plan.probe_model)
    if plan.atlas_metadata_sha256 != atlas.metadata_sha256:
        raise ProbePlanningError("probe plan atlas digest does not match the project atlas")
    expected_projection_sha256 = atlas_surface_projection_digest(input_data)
    if plan.projection_sha256 != expected_projection_sha256:
        raise ProbePlanningError("atlas-surface projection digest does not match its inputs")
    expected = placement_from_atlas_surface_input(
        input_data=input_data,
        atlas=atlas,
        context=plan.placement.context,
        model=plan.probe_model,
        name=plan.name,
        custom_geometry_acknowledged=plan.placement.custom_geometry_acknowledged,
    )
    validate_rederived_probe_placement_geometry(actual=plan.placement, expected=expected)
    if annotation is not None:
        if annotation_sha256 is None:
            raise ProbePlanningError("annotation SHA-256 is required when revalidating the surface")
        validate_resolved_surface_against_annotation(
            input_data=input_data,
            annotation=annotation,
            atlas=atlas,
            annotation_sha256=annotation_sha256,
        )


def atlas_surface_projection_digest(input_data: AtlasSurfaceProbeInput) -> str:
    """Hash the resolved surface boundary and all external reference provenance."""

    encoded = json.dumps(
        {
            "algorithm": ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION,
            "surfaceRelativeInput": input_data.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _default_surface_plan_name(
    model: ProbeModelDefinition,
    input_data: AtlasSurfaceProbeInput,
) -> str:
    product = model.product_code or model.display_name
    return f"{product} · AP {input_data.insertion_ap_mm:g} · ML {input_data.insertion_ml_mm:g}"


def project_bregma_target_through_calibration(
    *,
    target: UnprojectedBregmaTarget,
    calibration: AtlasRegisteredCalibration,
    atlas: AtlasMetadata,
) -> tuple[AnatomicalPoint, AnatomicalPoint, BrainGlobePhysicalPoint]:
    """Reproduce the exact source-target projection stored by a probe plan."""

    if not calibration.permits_planning:
        raise ProbePlanningError("failed calibration cannot create or validate a probe plan")
    if calibration.atlas_metadata_sha256 != atlas.metadata_sha256:
        raise ProbePlanningError("calibration atlas digest does not match the project atlas")
    destination = calibration.atlas_transform.destination_frame
    if (destination.atlas_key, destination.atlas_version) != (
        atlas.atlas_key,
        atlas.atlas_package_version,
    ):
        raise ProbePlanningError("calibration atlas identity does not match the project atlas")
    context = calibration.skull_calibration.context
    if context.subject_id is None:
        raise ProbePlanningError("calibrated probe planning requires an animal subject ID")
    skull = calibration.skull_calibration
    calibrated_target = BregmaRelativeTargetMM(
        context_uuid=context.context_uuid,
        calibration_uuid=calibration.calibration_uuid,
        profile_id=calibration.profile_id,
        stereotaxic_frame_id=skull.stereotaxic_frame.frame_id,
        ap_mm=target.ap_mm,
        ml_mm=target.ml_mm,
        dv_mm=target.dv_mm,
    )
    stereotaxic_point = bregma_relative_target_to_point(
        target=calibrated_target,
        calibration=skull,
    )
    atlas_anatomical_point = transform_point(
        calibration.atlas_transform,
        stereotaxic_point,
    )
    atlas_physical_point = canonical_anatomical_to_brainglobe_physical(
        atlas_anatomical_point,
        atlas,
    )
    BrainGlobeAtlasSpace(atlas).physical_to_index(atlas_physical_point)
    return stereotaxic_point, atlas_anatomical_point, atlas_physical_point


def validate_probe_plan_projection_semantics(
    *,
    plan: ProbePlanRecord,
    target: UnprojectedBregmaTarget,
    calibration: AtlasRegisteredCalibration,
    atlas: AtlasMetadata,
) -> None:
    """Reject a self-rehashed plan that cannot be reproduced from its source inputs."""

    validate_probe_model_catalog_snapshot(
        plan.probe_model,
        allow_unknown_identity=(
            plan.planning_algorithm_version == LEGACY_PROBE_PLANNING_ALGORITHM_VERSION
        ),
    )
    if plan.source_target != target:
        raise ProbePlanningError(
            "probe plan source target snapshot does not match the referenced project target"
        )
    if plan.calibration_uuid != calibration.calibration_uuid:
        raise ProbePlanningError("probe plan calibration UUID does not match its reference")
    if plan.calibration_version != calibration.calibration_version:
        raise ProbePlanningError("probe plan calibration version does not match its reference")
    calibration_sha256 = atlas_registered_calibration_sha256(calibration)
    if plan.calibration_sha256 != calibration_sha256:
        raise ProbePlanningError("probe plan calibration digest does not match its reference")
    if plan.atlas_metadata_sha256 != atlas.metadata_sha256:
        raise ProbePlanningError("probe plan atlas digest does not match the project atlas")
    if plan.placement.context != calibration.skull_calibration.context:
        raise ProbePlanningError(
            "probe plan animal context does not match the referenced calibration"
        )
    _, expected_atlas_target, expected_physical_target = project_bregma_target_through_calibration(
        target=target,
        calibration=calibration,
        atlas=atlas,
    )
    actual_target = plan.placement.target
    if actual_target.frame_id != expected_atlas_target.frame_id or any(
        not math.isclose(
            actual,
            expected,
            rel_tol=0,
            abs_tol=PROBE_TARGET_MATCH_ABSOLUTE_TOLERANCE_UM,
        )
        for actual, expected in zip(
            actual_target.as_ap_ml_dv(),
            expected_atlas_target.as_ap_ml_dv(),
            strict=True,
        )
    ):
        raise ProbePlanningError(
            "probe plan placement target does not match the calibrated source target"
        )
    expected_projection_sha256 = target_projection_digest(
        target=target,
        calibration_sha256=calibration_sha256,
        atlas_point=expected_physical_target,
    )
    if plan.projection_sha256 != expected_projection_sha256:
        raise ProbePlanningError(
            "probe plan projection digest does not match the calibrated source target"
        )
    expected_placement = rederive_probe_plan_placement(
        plan=plan,
        target=target,
        calibration=calibration,
        atlas=atlas,
    )
    if expected_placement is not None:
        validate_rederived_probe_placement_geometry(
            actual=plan.placement,
            expected=expected_placement,
        )


def rederive_probe_plan_placement(
    *,
    plan: ProbePlanRecord,
    target: UnprojectedBregmaTarget,
    calibration: AtlasRegisteredCalibration,
    atlas: AtlasMetadata,
) -> NormalizedProbePlacement | None:
    """Rebuild current placement geometry from inputs independent of serialized geometry.

    Version-one records predate preserved manipulator/placement inputs. They
    remain loadable for audit, while analysis continues to require v2 or v3.
    """

    if plan.planning_algorithm_version == LEGACY_PROBE_PLANNING_ALGORITHM_VERSION:
        return None
    if plan.planning_algorithm_version == STEREOTAXIC_PROBE_PLANNING_ALGORITHM_VERSION:
        manipulator = plan.manipulator_input
        if manipulator is None:
            raise ProbePlanningError("v2 probe plan is missing preserved manipulator inputs")
        stereotaxic_target, _, _ = project_bregma_target_through_calibration(
            target=target,
            calibration=calibration,
            atlas=atlas,
        )
        source_placement = placement_from_stereotaxic_target(
            calibration=calibration.skull_calibration,
            model=plan.probe_model,
            name=plan.name,
            target=stereotaxic_target,
            manipulator_azimuth_deg=manipulator.azimuth_deg,
            manipulator_elevation_deg=manipulator.elevation_deg,
            insertion_depth_um=manipulator.insertion_depth_um,
            axial_rotation_deg=manipulator.axial_rotation_deg,
            custom_geometry_acknowledged=plan.placement.custom_geometry_acknowledged,
        )
        return transform_probe_placement_uniform(
            source_placement,
            calibration.atlas_transform,
        )
    if plan.planning_algorithm_version != PROBE_PLANNING_ALGORITHM_VERSION:
        raise ProbePlanningError(
            f"unsupported probe planning algorithm {plan.planning_algorithm_version!r}"
        )
    placement_input = plan.placement_input
    if placement_input is None:
        raise ProbePlanningError("v3 probe plan is missing preserved placement-mode inputs")
    entry = placement_input.entry
    expected_plan, _ = build_calibrated_probe_plan(
        target=target,
        calibration=calibration,
        atlas=atlas,
        model=plan.probe_model,
        name=plan.name,
        azimuth_deg=placement_input.azimuth_deg,
        elevation_deg=placement_input.elevation_deg,
        insertion_depth_um=placement_input.insertion_depth_um,
        axial_rotation_deg=placement_input.axial_rotation_deg,
        custom_geometry_acknowledged=plan.placement.custom_geometry_acknowledged,
        placement_mode=placement_input.mode,
        entry_ap_mm=None if entry is None else entry.ap_mm,
        entry_ml_mm=None if entry is None else entry.ml_mm,
        entry_dv_mm=None if entry is None else entry.dv_mm,
        plan_uuid=plan.plan_uuid,
        plan_version=plan.plan_version,
        created_at=plan.created_at,
    )
    return expected_plan.placement


def validate_rederived_probe_placement_geometry(
    *,
    actual: NormalizedProbePlacement,
    expected: NormalizedProbePlacement,
) -> None:
    """Compare every placement field that changes physical probe geometry."""

    mismatches: list[str] = []
    exact_fields = (
        ("name", actual.name, expected.name),
        ("context", actual.context, expected.context),
        ("probe model ID", actual.probe_model_id, expected.probe_model_id),
        ("probe model version", actual.probe_model_version, expected.probe_model_version),
        ("placement method", actual.method, expected.method),
        ("angle convention", actual.angle_convention, expected.angle_convention),
    )
    mismatches.extend(
        label for label, value, expected_value in exact_fields if value != expected_value
    )

    mismatches.extend(
        label
        for label in ("entry", "target", "tip", "skull_entry", "brain_entry")
        if not _optional_anatomical_points_match(
            getattr(actual, label),
            getattr(expected, label),
        )
    )
    mismatches.extend(
        label
        for label in (
            "inward_direction",
            "local_lateral_direction",
            "local_normal_direction",
        )
        if not _optional_directions_match(
            getattr(actual, label),
            getattr(expected, label),
        )
    )

    scalar_fields = (
        (
            "insertion depth",
            actual.insertion_depth_um,
            expected.insertion_depth_um,
            PROBE_TARGET_MATCH_ABSOLUTE_TOLERANCE_UM,
            1e-10,
        ),
        (
            "azimuth",
            actual.azimuth_deg,
            expected.azimuth_deg,
            PROBE_ANGLE_MATCH_ABSOLUTE_TOLERANCE_DEG,
            0.0,
        ),
        (
            "elevation",
            actual.elevation_deg,
            expected.elevation_deg,
            PROBE_ANGLE_MATCH_ABSOLUTE_TOLERANCE_DEG,
            0.0,
        ),
        (
            "axial rotation",
            actual.axial_rotation_deg,
            expected.axial_rotation_deg,
            PROBE_ANGLE_MATCH_ABSOLUTE_TOLERANCE_DEG,
            0.0,
        ),
        (
            "model-to-placement scale",
            actual.model_to_placement_uniform_scale,
            expected.model_to_placement_uniform_scale,
            PROBE_SCALE_MATCH_ABSOLUTE_TOLERANCE,
            1e-9,
        ),
    )
    mismatches.extend(
        label
        for label, value, expected_value, absolute_tolerance, relative_tolerance in scalar_fields
        if not math.isclose(
            value,
            expected_value,
            rel_tol=relative_tolerance,
            abs_tol=absolute_tolerance,
        )
    )
    if mismatches:
        raise ProbePlanningError(
            "probe plan placement geometry does not match preserved planning inputs: "
            + ", ".join(mismatches)
        )


def _optional_anatomical_points_match(
    actual: AnatomicalPoint | None,
    expected: AnatomicalPoint | None,
) -> bool:
    if actual is None or expected is None:
        return actual is expected
    return actual.frame_id == expected.frame_id and all(
        math.isclose(
            value,
            expected_value,
            rel_tol=0,
            abs_tol=PROBE_TARGET_MATCH_ABSOLUTE_TOLERANCE_UM,
        )
        for value, expected_value in zip(
            actual.as_ap_ml_dv(),
            expected.as_ap_ml_dv(),
            strict=True,
        )
    )


def _optional_directions_match(
    actual: UnitDirectionAPMLDV | None,
    expected: UnitDirectionAPMLDV | None,
) -> bool:
    if actual is None or expected is None:
        return actual is expected
    return actual.frame_id == expected.frame_id and all(
        math.isclose(
            value,
            expected_value,
            rel_tol=0,
            abs_tol=PROBE_DIRECTION_MATCH_ABSOLUTE_TOLERANCE,
        )
        for value, expected_value in zip(
            actual.as_ap_ml_dv(),
            expected.as_ap_ml_dv(),
            strict=True,
        )
    )


def build_calibrated_probe_plan(
    *,
    target: UnprojectedBregmaTarget,
    calibration: AtlasRegisteredCalibration,
    atlas: AtlasMetadata,
    model: ProbeModelDefinition,
    name: str,
    azimuth_deg: float | None,
    elevation_deg: float | None,
    insertion_depth_um: float | None,
    axial_rotation_deg: float,
    custom_geometry_acknowledged: bool,
    placement_mode: ProbePlacementMode = ProbePlacementMode.STEREOTAXIC_TARGET_MANIPULATOR,
    entry_ap_mm: float | None = None,
    entry_ml_mm: float | None = None,
    entry_dv_mm: float | None = None,
    plan_uuid: UUID | None = None,
    plan_version: int = 1,
    created_at: datetime | None = None,
) -> tuple[ProbePlanRecord, BrainGlobePhysicalPoint]:
    """Project one preserved target and normalize an editable probe placement.

    The calibrated target is treated as the physical probe tip.  Entry is
    derived from the user-supplied angle convention and insertion depth; it may
    lie outside the atlas and is clipped only during region/vessel analysis.
    """

    destination = calibration.atlas_transform.destination_frame
    context = calibration.skull_calibration.context
    if not model.permits_verified_device_label and not custom_geometry_acknowledged:
        raise ProbePlanningError(
            "probe geometry without completed independent review requires explicit user "
            "acknowledgment"
        )
    skull = calibration.skull_calibration
    stereotaxic_point, atlas_anatomical_point, atlas_physical_point = (
        project_bregma_target_through_calibration(
            target=target,
            calibration=calibration,
            atlas=atlas,
        )
    )
    entry_values = (entry_ap_mm, entry_ml_mm, entry_dv_mm)
    has_complete_entry = all(value is not None for value in entry_values)
    if any(value is not None for value in entry_values) and not has_complete_entry:
        raise ProbePlanningError("entry AP, ML, and DV must be supplied together")
    if has_complete_entry:
        assert entry_ap_mm is not None
        assert entry_ml_mm is not None
        assert entry_dv_mm is not None
        entry_input: BregmaRelativeEntryInput | None = BregmaRelativeEntryInput(
            ap_mm=entry_ap_mm,
            ml_mm=entry_ml_mm,
            dv_mm=entry_dv_mm,
        )
    else:
        entry_input = None
    needs_angles = placement_mode is not ProbePlacementMode.ENTRY_AND_TARGET
    if needs_angles and (
        azimuth_deg is None or elevation_deg is None or insertion_depth_um is None
    ):
        raise ProbePlanningError(f"{placement_mode.value} requires angles and insertion depth")
    if not needs_angles and any(
        value is not None for value in (azimuth_deg, elevation_deg, insertion_depth_um)
    ):
        raise ProbePlanningError("ENTRY_AND_TARGET derives angles and depth from its two points")
    angle_frame_id = (
        None
        if not needs_angles
        else (
            destination.frame_id
            if placement_mode is ProbePlacementMode.TARGET_ANGLES_DEPTH
            else skull.stereotaxic_frame.frame_id
        )
    )
    placement_input = ProbePlacementInput(
        mode=placement_mode,
        entry=entry_input,
        angle_frame_id=angle_frame_id,
        azimuth_deg=azimuth_deg if needs_angles else None,
        elevation_deg=elevation_deg if needs_angles else None,
        insertion_depth_um=insertion_depth_um if needs_angles else None,
        axial_rotation_deg=axial_rotation_deg,
        angle_convention=(
            ProbeManipulatorInput.model_fields["angle_convention"].default if needs_angles else None
        ),
    )
    manipulator_input: ProbeManipulatorInput | None = None
    if placement_mode is ProbePlacementMode.STEREOTAXIC_TARGET_MANIPULATOR:
        assert azimuth_deg is not None
        assert elevation_deg is not None
        assert insertion_depth_um is not None
        manipulator_input = ProbeManipulatorInput(
            frame_id=skull.stereotaxic_frame.frame_id,
            azimuth_deg=azimuth_deg,
            elevation_deg=elevation_deg,
            insertion_depth_um=insertion_depth_um,
            axial_rotation_deg=axial_rotation_deg,
        )
        source_placement = placement_from_stereotaxic_target(
            calibration=skull,
            model=model,
            name=name,
            target=stereotaxic_point,
            manipulator_azimuth_deg=azimuth_deg,
            manipulator_elevation_deg=elevation_deg,
            insertion_depth_um=insertion_depth_um,
            axial_rotation_deg=axial_rotation_deg,
            custom_geometry_acknowledged=custom_geometry_acknowledged,
        )
        placement = transform_probe_placement_uniform(
            source_placement,
            calibration.atlas_transform,
        )
    elif placement_mode is ProbePlacementMode.TARGET_ANGLES_DEPTH:
        assert azimuth_deg is not None
        assert elevation_deg is not None
        assert insertion_depth_um is not None
        placement = placement_from_target_angles_depth(
            context=context,
            model=model,
            name=name,
            target=atlas_anatomical_point,
            azimuth_deg=azimuth_deg,
            elevation_deg=elevation_deg,
            insertion_depth_um=insertion_depth_um,
            axial_rotation_deg=axial_rotation_deg,
            custom_geometry_acknowledged=custom_geometry_acknowledged,
        )
    else:
        if entry_input is None:
            raise ProbePlanningError(f"{placement_mode.value} requires an entry coordinate")
        calibrated_entry = BregmaRelativeTargetMM(
            context_uuid=context.context_uuid,
            calibration_uuid=calibration.calibration_uuid,
            profile_id=calibration.profile_id,
            stereotaxic_frame_id=skull.stereotaxic_frame.frame_id,
            ap_mm=entry_input.ap_mm,
            ml_mm=entry_input.ml_mm,
            dv_mm=entry_input.dv_mm,
        )
        entry_stereotaxic = bregma_relative_target_to_point(
            target=calibrated_entry,
            calibration=skull,
        )
        if placement_mode is ProbePlacementMode.ENTRY_AND_TARGET:
            source_placement = placement_from_entry_target(
                context=context,
                model=model,
                name=name,
                entry=entry_stereotaxic,
                target=stereotaxic_point,
                axial_rotation_deg=axial_rotation_deg,
                custom_geometry_acknowledged=custom_geometry_acknowledged,
            )
            placement = transform_probe_placement_uniform(
                source_placement,
                calibration.atlas_transform,
            )
        else:
            assert placement_mode is ProbePlacementMode.ENTRY_ANGLES_DEPTH
            assert azimuth_deg is not None
            assert elevation_deg is not None
            assert insertion_depth_um is not None
            direction = direction_from_angles(
                frame_id=entry_stereotaxic.frame_id,
                azimuth_deg=azimuth_deg,
                elevation_deg=elevation_deg,
            )
            delta = tuple(
                target_value - entry_value
                for target_value, entry_value in zip(
                    stereotaxic_point.as_ap_ml_dv(),
                    entry_stereotaxic.as_ap_ml_dv(),
                    strict=True,
                )
            )
            direction_values = direction.as_ap_ml_dv()
            target_depth = sum(
                component * direction_component
                for component, direction_component in zip(
                    delta,
                    direction_values,
                    strict=True,
                )
            )
            off_axis = math.sqrt(
                sum(
                    (component - target_depth * direction_component) ** 2
                    for component, direction_component in zip(
                        delta,
                        direction_values,
                        strict=True,
                    )
                )
            )
            tolerance = max(1e-6, insertion_depth_um * 1e-10)
            if off_axis > tolerance:
                raise ProbePlanningError(
                    "the selected target is not on the entry/angle trajectory "
                    f"({off_axis:g} micrometres off axis); use ENTRY_AND_TARGET to derive angles"
                )
            if target_depth < -tolerance or target_depth > insertion_depth_um + tolerance:
                raise ProbePlanningError(
                    "the selected target must lie between entry and tip for ENTRY_ANGLES_DEPTH"
                )
            source_placement = placement_from_entry_angles_depth(
                context=context,
                model=model,
                name=name,
                entry=entry_stereotaxic,
                azimuth_deg=azimuth_deg,
                elevation_deg=elevation_deg,
                insertion_depth_um=insertion_depth_um,
                target_depth_um=max(0.0, min(insertion_depth_um, target_depth)),
                axial_rotation_deg=axial_rotation_deg,
                custom_geometry_acknowledged=custom_geometry_acknowledged,
            )
            placement_payload = source_placement.model_dump(mode="python")
            placement_payload["target"] = stereotaxic_point
            source_placement = NormalizedProbePlacement.model_validate(placement_payload)
            placement = transform_probe_placement_uniform(
                source_placement,
                calibration.atlas_transform,
            )
    if placement.target != atlas_anatomical_point:
        raise ProbePlanningError(
            "target projection and transformed probe placement produced different atlas points"
        )
    actual_plan_uuid = plan_uuid or uuid4()
    calibration_sha256 = atlas_registered_calibration_sha256(calibration)
    projection_sha256 = target_projection_digest(
        target=target,
        calibration_sha256=calibration_sha256,
        atlas_point=atlas_physical_point,
    )
    normalized_name = name.strip()
    input_sha256 = probe_plan_input_digest(
        plan_uuid=actual_plan_uuid,
        plan_version=plan_version,
        name=normalized_name,
        source_target=target,
        probe_model=model,
        manipulator_input=manipulator_input,
        placement_input=placement_input,
        placement=placement,
        calibration_uuid=calibration.calibration_uuid,
        calibration_version=calibration.calibration_version,
        calibration_sha256=calibration_sha256,
        atlas_metadata_sha256=atlas.metadata_sha256,
        projection_sha256=projection_sha256,
        planning_algorithm_version=PROBE_PLANNING_ALGORITHM_VERSION,
    )
    values: dict[str, object] = {
        "plan_uuid": actual_plan_uuid,
        "plan_version": plan_version,
        "name": normalized_name,
        "source_target": target,
        "probe_model": model,
        "manipulator_input": manipulator_input,
        "placement_input": placement_input,
        "placement": placement,
        "calibration_uuid": calibration.calibration_uuid,
        "calibration_version": calibration.calibration_version,
        "calibration_sha256": calibration_sha256,
        "atlas_metadata_sha256": atlas.metadata_sha256,
        "projection_sha256": projection_sha256,
        "planning_algorithm_version": PROBE_PLANNING_ALGORITHM_VERSION,
        "input_sha256": input_sha256,
    }
    if created_at is not None:
        values["created_at"] = created_at
    return ProbePlanRecord.model_validate(values), atlas_physical_point


def target_projection_digest(
    *,
    target: UnprojectedBregmaTarget,
    calibration_sha256: str,
    atlas_point: BrainGlobePhysicalPoint,
) -> str:
    """Hash the same preserved target/calibration/atlas projection boundary."""

    encoded = json.dumps(
        {
            "target": target.model_dump(mode="json"),
            "calibrationSha256": calibration_sha256,
            "atlasPoint": atlas_point.model_dump(mode="json"),
            "algorithm": TARGET_PROJECTION_ALGORITHM_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
