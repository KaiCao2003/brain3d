"""Versioned, human-readable project models."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mouse_brain_planner.coordinates.anatomical_atlas import (
    canonical_anatomical_to_brainglobe_physical,
)
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.probe_plan_models import (
    ProbePlacementMode,
    ProbePlanRecord,
    ProbeRegionAnalysisBundle,
)
from mouse_brain_planner.domain.stereotaxy_models import (
    AtlasRegisteredCalibration,
    atlas_registered_calibration_sha256,
)
from mouse_brain_planner.domain.vessel_models import (
    DorsalVascularRegistration,
    ReferenceVascularDensityProjectState,
    SubjectVascularImage,
    SubjectVascularOverlayState,
)
from mouse_brain_planner.domain.vessel_plan_models import ProbeVesselAnalysisBundle
from mouse_brain_planner.surgery.calibration_validation import (
    validate_atlas_registered_calibration_reproducibility,
)
from mouse_brain_planner.surgery.probe_planning import (
    validate_probe_plan_projection_semantics as validate_plan_projection_semantics,
)
from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION, __version__

MAX_PROJECT_EVENTS = 1_000
MAX_SUBJECT_VASCULAR_IMAGES = 128
MAX_DORSAL_VASCULAR_REGISTRATIONS = 1_024
MAX_UNPROJECTED_BREGMA_TARGETS = 256
MAX_CALIBRATIONS = 32
MAX_PROBE_PLANS = 32
MAX_PROBE_REGION_ANALYSES = 32
MAX_PROBE_VESSEL_ANALYSES = 32


class ViewerSliceDepths(BaseModel):
    """Independent zero-based slice indices for the three orthogonal views."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    coronal: int = Field(ge=0)
    sagittal: int = Field(ge=0)
    horizontal: int = Field(ge=0)


class ViewerRegionSelection(BaseModel):
    """One explicit region pick on one persisted slice image."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    orientation: Literal["coronal", "sagittal", "horizontal"]
    index: int = Field(ge=0)
    column: int = Field(ge=0)
    row: int = Field(ge=0)
    atlas_point: BrainGlobePhysicalPoint


def validate_viewer_state_semantics(
    *,
    atlas: AtlasMetadata | None,
    slice_depths: ViewerSliceDepths | None,
    region_selection: ViewerRegionSelection | None,
) -> None:
    """Validate the viewer-only subset without rebuilding unrelated surgery plans."""

    if atlas is None:
        if slice_depths is not None or region_selection is not None:
            raise ValueError("viewer slice state requires atlas metadata")
        return

    if slice_depths is not None:
        depth_limits = {
            "coronal": atlas.shape_voxels[0],
            "sagittal": atlas.shape_voxels[2],
            "horizontal": atlas.shape_voxels[1],
        }
        for orientation, limit in depth_limits.items():
            depth = getattr(slice_depths, orientation)
            if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0 or depth >= limit:
                raise ValueError(f"{orientation} viewer slice {depth} is outside [0, {limit})")

    if region_selection is None:
        return
    if slice_depths is None:
        raise ValueError("a viewer region selection requires persisted slice depths")
    if region_selection.atlas_point.atlas_key != atlas.atlas_key or (
        region_selection.atlas_point.atlas_version != atlas.atlas_package_version
    ):
        raise ValueError("viewer region selection atlas identity does not match project")
    orientation_axes = {
        "coronal": (0, 1, 2),
        "sagittal": (2, 1, 0),
        "horizontal": (1, 0, 2),
    }
    if region_selection.orientation not in orientation_axes:
        raise ValueError("viewer region selection orientation is unsupported")
    fixed_axis, row_axis, column_axis = orientation_axes[region_selection.orientation]
    expected_depth = getattr(slice_depths, region_selection.orientation)
    for label, value in (
        ("index", region_selection.index),
        ("row", region_selection.row),
        ("column", region_selection.column),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"viewer region selection {label} must be nonnegative")
    if region_selection.index != expected_depth:
        raise ValueError("viewer region selection does not belong to the persisted slice")
    if region_selection.row >= atlas.shape_voxels[row_axis] or (
        region_selection.column >= atlas.shape_voxels[column_axis]
    ):
        raise ValueError("viewer region selection pixel is outside the slice image")
    point_voxel = tuple(
        math.floor(value / resolution)
        for value, resolution in zip(
            region_selection.atlas_point.as_tuple(),
            atlas.resolution_um,
            strict=True,
        )
    )
    expected_voxel = [0, 0, 0]
    expected_voxel[fixed_axis] = region_selection.index
    expected_voxel[row_axis] = region_selection.row
    expected_voxel[column_axis] = region_selection.column
    if point_voxel != tuple(expected_voxel):
        raise ValueError("viewer region selection point does not match its intrinsic pixel")


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


def validate_calibration_atlas_landmark_semantics(
    calibration: AtlasRegisteredCalibration,
    atlas: AtlasMetadata,
) -> None:
    """Require persisted atlas landmarks to preserve midline and laterality labels."""

    required_labels = ("bregma", "lambda", "left-skull", "right-skull")
    landmark_points = {}
    for label in required_labels:
        matches = tuple(
            landmark.destination
            for landmark in calibration.atlas_transform.landmarks
            if landmark.enabled and landmark.label == label
        )
        if len(matches) != 1:
            raise ValueError(
                f"calibration atlas transform must contain exactly one enabled {label} landmark"
            )
        landmark_points[label] = canonical_anatomical_to_brainglobe_physical(
            matches[0],
            atlas,
        )

    midline_ml_um = atlas.midline_ml_um
    half_ml_voxel_um = atlas.resolution_um[2] / 2.0
    floating_tolerance_um = max(1e-9, math.ulp(midline_ml_um))
    midline_tolerance_um = half_ml_voxel_um + floating_tolerance_um
    if landmark_points["bregma"].ap_um >= landmark_points["lambda"].ap_um:
        raise ValueError(
            "calibration atlas bregma must remain anterior to atlas lambda "
            "in BrainGlobe ASR coordinates"
        )
    if any(
        abs(landmark_points[label].ml_um - midline_ml_um) > midline_tolerance_um
        for label in ("bregma", "lambda")
    ):
        raise ValueError(
            "calibration atlas bregma and lambda must lie within half one ML voxel "
            "of the project atlas midline"
        )

    right_limit_um = midline_ml_um - half_ml_voxel_um
    left_limit_um = midline_ml_um + half_ml_voxel_um
    if (
        landmark_points["right-skull"].ml_um > right_limit_um + floating_tolerance_um
        or landmark_points["left-skull"].ml_um < left_limit_um - floating_tolerance_um
    ):
        raise ValueError(
            "calibration atlas right-skull and left-skull landmarks must lie at least "
            "half one ML voxel into their named hemispheres"
        )


class RegionDisplayState(BaseModel):
    """Project-local display settings that never mutate atlas metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    structure_id: int = Field(gt=0)
    visible: bool = False
    opacity: float = Field(default=0.65, ge=0.0, le=1.0, allow_inf_nan=False)
    custom_rgb: tuple[int, int, int] | None = None

    @field_validator("custom_rgb")
    @classmethod
    def validate_custom_rgb(cls, value: tuple[int, int, int] | None) -> tuple[int, int, int] | None:
        """Validate optional project-local region colors."""

        if value is not None and any(component < 0 or component > 255 for component in value):
            raise ValueError("custom RGB components must be in [0, 255]")
        return value


class ProjectEvent(BaseModel):
    """A meaningful project action without private OS information."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime = Field(default_factory=utc_now)
    action: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=1000)


class PlannerProject(BaseModel):
    """Versioned animal surgery-planning project state."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    schema_version: int = PROJECT_SCHEMA_VERSION
    application_version: str = __version__
    project_revision: int = Field(default=0, ge=0)
    project_uuid: UUID = Field(default_factory=uuid4)
    title: str = Field(default="Untitled surgery plan", min_length=1, max_length=200)
    subject_id: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)
    modified_at: datetime = Field(default_factory=utc_now)
    atlas: AtlasMetadata | None = None
    linked_cursor: BrainGlobePhysicalPoint | None = None
    renderer_anchor: BrainGlobePhysicalPoint | None = None
    viewer_slice_depths: ViewerSliceDepths | None = None
    viewer_region_selection: ViewerRegionSelection | None = None
    selected_region_id: int | None = Field(default=None, gt=0)
    # Schema 6 originally accepted any collection that fit the bounded regions.json member.
    # Narrowing this field requires a schema migration, not an in-place validation change.
    region_display: list[RegionDisplayState] = Field(default_factory=list)
    subject_vascular_images: list[SubjectVascularImage] = Field(
        default_factory=list,
        max_length=MAX_SUBJECT_VASCULAR_IMAGES,
    )
    dorsal_vascular_registrations: list[DorsalVascularRegistration] = Field(
        default_factory=list,
        max_length=MAX_DORSAL_VASCULAR_REGISTRATIONS,
    )
    subject_vascular_overlays: list[SubjectVascularOverlayState] = Field(
        default_factory=list,
        max_length=MAX_SUBJECT_VASCULAR_IMAGES,
    )
    reference_vascular_density: ReferenceVascularDensityProjectState | None = None
    unprojected_bregma_targets: list[UnprojectedBregmaTarget] = Field(
        default_factory=list,
        max_length=MAX_UNPROJECTED_BREGMA_TARGETS,
    )
    calibrations: list[AtlasRegisteredCalibration] = Field(
        default_factory=list,
        max_length=MAX_CALIBRATIONS,
    )
    active_calibration_uuid: UUID | None = None
    probe_plans: list[ProbePlanRecord] = Field(
        default_factory=list,
        max_length=MAX_PROBE_PLANS,
    )
    probe_region_analyses: list[ProbeRegionAnalysisBundle] = Field(
        default_factory=list,
        max_length=MAX_PROBE_REGION_ANALYSES,
    )
    probe_vessel_analyses: list[ProbeVesselAnalysisBundle] = Field(
        default_factory=list,
        max_length=MAX_PROBE_VESSEL_ANALYSES,
    )
    coordinate_convention: str = "BrainGlobe ASR: [AP,DV,ML], origin A/S/R, increasing P/I/L, µm"
    scientific_disclaimer_acknowledged: bool = False
    # Schema 6 originally accepted any text that fit the bounded project.json member.
    user_notes: str = ""
    event_log: list[ProjectEvent] = Field(default_factory=list, max_length=MAX_PROJECT_EVENTS)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        """Reject future or invalid schemas before migration."""

        if value != PROJECT_SCHEMA_VERSION:
            raise ValueError(
                f"project schema {value} is unsupported; expected {PROJECT_SCHEMA_VERSION}"
            )
        return value

    @field_validator("project_revision", mode="before")
    @classmethod
    def validate_project_revision(cls, value: object) -> int:
        """Reject booleans and coercible text at the persisted concurrency boundary."""

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("project revision must be a nonnegative integer")
        return value

    def validate_probe_plan_projection_semantics(self, plan: ProbePlanRecord) -> None:
        """Reproduce one persisted plan's target and current-version placement geometry."""

        if self.atlas is None:
            raise ValueError("probe plan projection validation requires project atlas metadata")
        target = next(
            (
                item
                for item in self.unprojected_bregma_targets
                if item.target_uuid == plan.source_target.target_uuid
            ),
            None,
        )
        if target is None:
            raise ValueError("probe plan source target is not present in the current project")
        calibration = next(
            (item for item in self.calibrations if item.calibration_uuid == plan.calibration_uuid),
            None,
        )
        if calibration is None:
            raise ValueError("probe plan references an unavailable calibration")
        validate_plan_projection_semantics(
            plan=plan,
            target=target,
            calibration=calibration,
            atlas=self.atlas,
        )

    @model_validator(mode="after")
    def validate_atlas_bound_state(self) -> Self:
        """Reject mixed atlas identities and out-of-bounds persisted cursors."""

        target_ids = [target.target_uuid for target in self.unprojected_bregma_targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("unprojected bregma targets contain duplicate UUIDs")
        targets_by_id = {target.target_uuid: target for target in self.unprojected_bregma_targets}

        calibration_ids = [item.calibration_uuid for item in self.calibrations]
        if len(calibration_ids) != len(set(calibration_ids)):
            raise ValueError("calibrations contain duplicate UUIDs")
        calibration_versions = [
            (item.profile_id, item.calibration_version) for item in self.calibrations
        ]
        if len(calibration_versions) != len(set(calibration_versions)):
            raise ValueError("each calibration profile version must be unique")
        calibrations_by_id = {item.calibration_uuid: item for item in self.calibrations}
        active_calibration = (
            None
            if self.active_calibration_uuid is None
            else calibrations_by_id.get(self.active_calibration_uuid)
        )
        if self.active_calibration_uuid is not None and active_calibration is None:
            raise ValueError("active calibration UUID does not identify a persisted calibration")
        if active_calibration is not None and not active_calibration.permits_planning:
            raise ValueError("a failed calibration cannot be active")

        plan_ids = [item.plan_uuid for item in self.probe_plans]
        if len(plan_ids) != len(set(plan_ids)):
            raise ValueError("probe plans contain duplicate UUIDs")
        analyses_by_plan = [item.plan_uuid for item in self.probe_region_analyses]
        if len(analyses_by_plan) != len(set(analyses_by_plan)):
            raise ValueError("only one current region-analysis bundle is allowed per probe plan")
        vessel_analyses_by_plan = [item.plan_uuid for item in self.probe_vessel_analyses]
        if len(vessel_analyses_by_plan) != len(set(vessel_analyses_by_plan)):
            raise ValueError("only one current vessel-analysis bundle is allowed per probe plan")

        if self.atlas is None:
            if self.linked_cursor is not None:
                raise ValueError("a linked atlas cursor requires atlas metadata")
            if self.renderer_anchor is not None:
                raise ValueError("a renderer anchor requires atlas metadata")
            validate_viewer_state_semantics(
                atlas=self.atlas,
                slice_depths=self.viewer_slice_depths,
                region_selection=self.viewer_region_selection,
            )
            if self.selected_region_id is not None or self.region_display:
                raise ValueError("atlas region state requires atlas metadata")
            if self.calibrations or self.active_calibration_uuid is not None:
                raise ValueError("atlas-registered calibration state requires atlas metadata")
            if self.probe_plans or self.probe_region_analyses or self.probe_vessel_analyses:
                raise ValueError("probe planning state requires atlas metadata")
            if (
                self.subject_vascular_images
                or self.dorsal_vascular_registrations
                or self.subject_vascular_overlays
                or self.reference_vascular_density is not None
            ):
                raise ValueError("vascular state requires atlas metadata")
            return self

        for label, point in (
            ("legacy atlas point", self.linked_cursor),
            ("renderer anchor", self.renderer_anchor),
        ):
            if point is None:
                continue
            expected_identity = (
                self.atlas.atlas_key,
                self.atlas.atlas_package_version,
            )
            point_identity = (
                point.atlas_key,
                point.atlas_version,
            )
            if point_identity != expected_identity:
                raise ValueError(
                    f"{label} atlas identity {point_identity} does not match "
                    f"project atlas {expected_identity}"
                )
            for axis, (value, extent) in enumerate(
                zip(
                    point.as_tuple(),
                    self.atlas.extent_um,
                    strict=True,
                )
            ):
                if value < 0 or value >= extent:
                    raise ValueError(
                        f"{label} axis {axis} value {value:g} is outside "
                        f"atlas bounds [0, {extent}) µm"
                    )

        if self.renderer_anchor is None:
            raise ValueError("an atlas-bound project requires a renderer anchor")

        expected_atlas_identity = (
            self.atlas.atlas_key,
            self.atlas.atlas_package_version,
        )
        for calibration in self.calibrations:
            destination = calibration.atlas_transform.destination_frame
            calibration_identity = (destination.atlas_key, destination.atlas_version)
            if calibration_identity != expected_atlas_identity:
                raise ValueError(
                    "calibration atlas identity "
                    f"{calibration_identity} does not match project atlas "
                    f"{expected_atlas_identity}"
                )
            if calibration.atlas_metadata_sha256 != self.atlas.metadata_sha256:
                raise ValueError("calibration atlas metadata digest does not match project atlas")
            calibration_subject = calibration.skull_calibration.context.subject_id
            if calibration_subject != self.subject_id:
                raise ValueError(
                    "calibration animal subject ID does not match the current project subject"
                )
            validate_calibration_atlas_landmark_semantics(calibration, self.atlas)
            validate_atlas_registered_calibration_reproducibility(calibration)

        plans_by_id = {item.plan_uuid: item for item in self.probe_plans}
        for plan in self.probe_plans:
            referenced_target = targets_by_id.get(plan.source_target.target_uuid)
            if referenced_target is None:
                raise ValueError("probe plan source target is not present in the current project")
            if referenced_target != plan.source_target:
                raise ValueError(
                    "probe plan source target snapshot does not match the current project target"
                )
            if plan.atlas_metadata_sha256 != self.atlas.metadata_sha256:
                raise ValueError("probe plan atlas metadata digest does not match project atlas")
            if plan.placement.context.subject_id != self.subject_id:
                raise ValueError("probe plan animal subject ID does not match the project subject")
            referenced_calibration = calibrations_by_id.get(plan.calibration_uuid)
            if referenced_calibration is None:
                raise ValueError("probe plan references an unavailable calibration")
            if referenced_calibration.calibration_version != plan.calibration_version:
                raise ValueError(
                    "probe plan calibration version does not match project calibration"
                )
            if plan.calibration_sha256 != atlas_registered_calibration_sha256(
                referenced_calibration
            ):
                raise ValueError("probe plan calibration digest does not match project calibration")
            if plan.manipulator_input is not None and (
                plan.manipulator_input.frame_id
                != referenced_calibration.atlas_transform.source_frame.frame_id
            ):
                raise ValueError(
                    "probe plan manipulator input frame does not match its calibration"
                )
            if plan.placement_input is not None and (
                plan.placement_input.mode is not ProbePlacementMode.ENTRY_AND_TARGET
            ):
                expected_angle_frame = (
                    referenced_calibration.atlas_transform.destination_frame.frame_id
                    if plan.placement_input.mode is ProbePlacementMode.TARGET_ANGLES_DEPTH
                    else referenced_calibration.atlas_transform.source_frame.frame_id
                )
                if plan.placement_input.angle_frame_id != expected_angle_frame:
                    raise ValueError(
                        "probe placement angle frame does not match its calibration mode"
                    )
            if not plan.probe_model.permits_verified_device_label and not (
                plan.placement.custom_geometry_acknowledged
            ):
                raise ValueError("unverified probe plan geometry requires explicit acknowledgment")
            self.validate_probe_plan_projection_semantics(plan)
        for bundle in self.probe_region_analyses:
            referenced_plan = plans_by_id.get(bundle.plan_uuid)
            if referenced_plan is None:
                raise ValueError("region analysis references an unavailable probe plan")
            if bundle.plan_version != referenced_plan.plan_version or (
                bundle.plan_input_sha256 != referenced_plan.input_sha256
            ):
                raise ValueError("region analysis is stale for its current probe plan")
            placement_ids = {analysis.placement_uuid for analysis in bundle.shank_analyses}
            if placement_ids != {referenced_plan.placement.placement_uuid}:
                raise ValueError("region analysis placement does not match its probe plan")
            expected_shanks = {shank.shank_id for shank in referenced_plan.probe_model.shanks}
            actual_shanks = {analysis.shank_id for analysis in bundle.shank_analyses}
            if actual_shanks != expected_shanks:
                raise ValueError("region analysis does not cover every probe-model shank")
        for vessel_bundle in self.probe_vessel_analyses:
            referenced_plan = plans_by_id.get(vessel_bundle.plan_uuid)
            if referenced_plan is None:
                raise ValueError("vessel analysis references an unavailable probe plan")
            if vessel_bundle.plan_version != referenced_plan.plan_version or (
                vessel_bundle.plan_input_sha256 != referenced_plan.input_sha256
            ):
                raise ValueError("vessel analysis is stale for its current probe plan")
            provenance = vessel_bundle.analysis.provenance
            if (provenance.atlas_key, provenance.atlas_version) != expected_atlas_identity:
                raise ValueError("vessel analysis atlas identity does not match project atlas")

        validate_viewer_state_semantics(
            atlas=self.atlas,
            slice_depths=self.viewer_slice_depths,
            region_selection=self.viewer_region_selection,
        )

        region_ids = [state.structure_id for state in self.region_display]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("project region display state contains duplicate structure IDs")

        image_ids = [image.image_uuid for image in self.subject_vascular_images]
        if len(image_ids) != len(set(image_ids)):
            raise ValueError("subject vascular images contain duplicate UUIDs")
        image_paths = [
            image.project_relative_path.casefold() for image in self.subject_vascular_images
        ]
        if len(image_paths) != len(set(image_paths)):
            raise ValueError("subject vascular images contain duplicate package paths")
        images_by_id = {image.image_uuid: image for image in self.subject_vascular_images}

        registration_ids = [
            registration.registration_uuid for registration in self.dorsal_vascular_registrations
        ]
        if len(registration_ids) != len(set(registration_ids)):
            raise ValueError("dorsal vascular registrations contain duplicate UUIDs")
        registration_versions = [
            (registration.image_uuid, registration.version)
            for registration in self.dorsal_vascular_registrations
        ]
        if len(registration_versions) != len(set(registration_versions)):
            raise ValueError("each subject image registration version must be unique")
        registrations_by_id = {
            registration.registration_uuid: registration
            for registration in self.dorsal_vascular_registrations
        }
        for registration in self.dorsal_vascular_registrations:
            if registration.image_uuid not in images_by_id:
                raise ValueError("dorsal vascular registration references an unknown image UUID")
            registration_identity = (registration.atlas_key, registration.atlas_version)
            if registration_identity != expected_atlas_identity:
                raise ValueError(
                    "dorsal vascular registration atlas identity "
                    f"{registration_identity} does not match project atlas "
                    f"{expected_atlas_identity}"
                )

        overlay_image_ids = [overlay.image_uuid for overlay in self.subject_vascular_overlays]
        if len(overlay_image_ids) != len(set(overlay_image_ids)):
            raise ValueError("subject vascular overlays contain duplicate image UUIDs")
        for overlay in self.subject_vascular_overlays:
            if overlay.image_uuid not in images_by_id:
                raise ValueError("subject vascular overlay references an unknown image UUID")
            overlay_registration: DorsalVascularRegistration | None = (
                registrations_by_id.get(overlay.registration_uuid)
                if overlay.registration_uuid is not None
                else None
            )
            if overlay.registration_uuid is not None and overlay_registration is None:
                raise ValueError("subject vascular overlay references an unknown registration UUID")
            if (
                overlay_registration is not None
                and overlay_registration.image_uuid != overlay.image_uuid
            ):
                raise ValueError("subject vascular overlay registration belongs to another image")
            if overlay.visible and overlay_registration is None:
                raise ValueError("a visible subject vascular overlay requires a registration")
            if overlay.segmentation_visible and not overlay.visible:
                raise ValueError("subject vascular segmentation requires its overlay to be visible")
            if overlay.dorsal_plane_dv_um is not None and not (
                0 <= overlay.dorsal_plane_dv_um < self.atlas.extent_um[1]
            ):
                raise ValueError("subject vascular overlay DV plane is outside atlas bounds")

        if self.reference_vascular_density is not None:
            reference_identity = (
                self.reference_vascular_density.target_atlas_key,
                self.reference_vascular_density.target_atlas_version,
            )
            if reference_identity != expected_atlas_identity:
                raise ValueError(
                    "reference vascular density atlas identity "
                    f"{reference_identity} does not match project atlas "
                    f"{expected_atlas_identity}"
                )
            reference_extent = tuple(
                size * self.reference_vascular_density.output_voxel_size_um
                for size in self.reference_vascular_density.output_shape_asr
            )
            if any(
                not math.isclose(
                    actual,
                    expected,
                    rel_tol=1e-10,
                    abs_tol=1e-6,
                )
                for actual, expected in zip(
                    reference_extent,
                    self.atlas.extent_um,
                    strict=True,
                )
            ):
                raise ValueError(
                    "reference vascular density output extent "
                    f"{reference_extent} does not match project atlas extent "
                    f"{self.atlas.extent_um}"
                )
        return self

    def touch(self, action: str, details: str | None = None) -> None:
        """Update modification time and append one reproducible event."""

        self.modified_at = utc_now()
        overflow = len(self.event_log) - MAX_PROJECT_EVENTS + 1
        if overflow > 0:
            del self.event_log[:overflow]
        self.event_log.append(ProjectEvent(action=action, details=details))
