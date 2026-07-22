"""Calibrated target-to-probe planning service shared by bridge and tests."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from uuid import UUID, uuid4

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
    PROBE_PLANNING_ALGORITHM_VERSION,
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


class ProbePlanningError(ValueError):
    """Raised when a plan would require an invalid or implicit assumption."""


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

    if not calibration.permits_planning:
        raise ProbePlanningError("failed calibration cannot create a probe plan")
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
    if not model.permits_verified_device_label and not custom_geometry_acknowledged:
        raise ProbePlanningError(
            "probe geometry without completed independent review requires explicit user "
            "acknowledgment"
        )
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
