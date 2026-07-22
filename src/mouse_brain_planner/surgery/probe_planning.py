"""Calibrated target-to-probe planning service shared by bridge and tests."""

from __future__ import annotations

import hashlib
import json
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
from mouse_brain_planner.domain.probe_models import ProbeModelDefinition
from mouse_brain_planner.domain.probe_plan_models import (
    ProbePlanRecord,
    probe_plan_input_digest,
)
from mouse_brain_planner.domain.stereotaxy_models import (
    AtlasRegisteredCalibration,
    BregmaRelativeTargetMM,
)
from mouse_brain_planner.surgery.stereotaxy import bregma_relative_target_to_point
from mouse_brain_planner.surgery.trajectory import placement_from_target_angles_depth

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
    azimuth_deg: float,
    elevation_deg: float,
    insertion_depth_um: float,
    axial_rotation_deg: float,
    custom_geometry_acknowledged: bool,
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
            "unverified generic/custom geometry requires explicit user acknowledgment"
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
    actual_plan_uuid = plan_uuid or uuid4()
    calibration_sha256 = calibration_digest(calibration)
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
        placement=placement,
        calibration_uuid=calibration.calibration_uuid,
        calibration_version=calibration.calibration_version,
        calibration_sha256=calibration_sha256,
        atlas_metadata_sha256=atlas.metadata_sha256,
        projection_sha256=projection_sha256,
    )
    values: dict[str, object] = {
        "plan_uuid": actual_plan_uuid,
        "plan_version": plan_version,
        "name": normalized_name,
        "source_target": target,
        "probe_model": model,
        "placement": placement,
        "calibration_uuid": calibration.calibration_uuid,
        "calibration_version": calibration.calibration_version,
        "calibration_sha256": calibration_sha256,
        "atlas_metadata_sha256": atlas.metadata_sha256,
        "projection_sha256": projection_sha256,
        "input_sha256": input_sha256,
    }
    if created_at is not None:
        values["created_at"] = created_at
    return ProbePlanRecord.model_validate(values), atlas_physical_point


def calibration_digest(calibration: AtlasRegisteredCalibration) -> str:
    """Return the canonical digest used at every calibration consumer."""

    encoded = json.dumps(
        calibration.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
