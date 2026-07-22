"""Versioned, human-readable project models."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.vessel_models import (
    DorsalVascularRegistration,
    ReferenceVascularDensityProjectState,
    SubjectVascularImage,
    SubjectVascularOverlayState,
)
from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION, __version__

MAX_PROJECT_EVENTS = 1_000
MAX_SUBJECT_VASCULAR_IMAGES = 128
MAX_DORSAL_VASCULAR_REGISTRATIONS = 1_024
MAX_UNPROJECTED_BREGMA_TARGETS = 256


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


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class RegionDisplayState(BaseModel):
    """Project-local display settings that never mutate atlas metadata."""

    model_config = ConfigDict(frozen=True)

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

    model_config = ConfigDict(frozen=True)

    timestamp: datetime = Field(default_factory=utc_now)
    action: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=1000)


class PlannerProject(BaseModel):
    """Versioned animal surgery-planning project state."""

    model_config = ConfigDict(validate_assignment=True)

    schema_version: int = PROJECT_SCHEMA_VERSION
    application_version: str = __version__
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
    coordinate_convention: str = "BrainGlobe ASR: [AP,DV,ML], origin A/S/R, increasing P/I/L, µm"
    scientific_disclaimer_acknowledged: bool = False
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

    @model_validator(mode="after")
    def validate_atlas_bound_state(self) -> Self:
        """Reject mixed atlas identities and out-of-bounds persisted cursors."""

        target_ids = [target.target_uuid for target in self.unprojected_bregma_targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("unprojected bregma targets contain duplicate UUIDs")

        if self.atlas is None:
            if self.linked_cursor is not None:
                raise ValueError("a linked atlas cursor requires atlas metadata")
            if self.renderer_anchor is not None:
                raise ValueError("a renderer anchor requires atlas metadata")
            if self.viewer_slice_depths is not None or self.viewer_region_selection is not None:
                raise ValueError("viewer slice state requires atlas metadata")
            if self.selected_region_id is not None or self.region_display:
                raise ValueError("atlas region state requires atlas metadata")
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

        if self.viewer_slice_depths is not None:
            depth_limits = {
                "coronal": self.atlas.shape_voxels[0],
                "sagittal": self.atlas.shape_voxels[2],
                "horizontal": self.atlas.shape_voxels[1],
            }
            for orientation, limit in depth_limits.items():
                depth = getattr(self.viewer_slice_depths, orientation)
                if depth < 0 or depth >= limit:
                    raise ValueError(
                        f"{orientation} viewer slice {depth} is outside [0, {limit})"
                    )

        if self.viewer_region_selection is not None:
            if self.viewer_slice_depths is None:
                raise ValueError("a viewer region selection requires persisted slice depths")
            selection = self.viewer_region_selection
            if selection.atlas_point.atlas_key != self.atlas.atlas_key or (
                selection.atlas_point.atlas_version != self.atlas.atlas_package_version
            ):
                raise ValueError("viewer region selection atlas identity does not match project")
            orientation_axes = {
                "coronal": (0, 1, 2),
                "sagittal": (2, 1, 0),
                "horizontal": (1, 0, 2),
            }
            if selection.orientation not in orientation_axes:
                raise ValueError("viewer region selection orientation is unsupported")
            fixed_axis, row_axis, column_axis = orientation_axes[selection.orientation]
            expected_depth = getattr(self.viewer_slice_depths, selection.orientation)
            if selection.index < 0 or selection.row < 0 or selection.column < 0:
                raise ValueError("viewer region selection indices must be nonnegative")
            if selection.index != expected_depth:
                raise ValueError("viewer region selection does not belong to the persisted slice")
            if selection.row >= self.atlas.shape_voxels[row_axis] or (
                selection.column >= self.atlas.shape_voxels[column_axis]
            ):
                raise ValueError("viewer region selection pixel is outside the slice image")
            point_voxel = tuple(
                math.floor(value / resolution)
                for value, resolution in zip(
                    selection.atlas_point.as_tuple(),
                    self.atlas.resolution_um,
                    strict=True,
                )
            )
            expected_voxel = [0, 0, 0]
            expected_voxel[fixed_axis] = selection.index
            expected_voxel[row_axis] = selection.row
            expected_voxel[column_axis] = selection.column
            if point_voxel != tuple(expected_voxel):
                raise ValueError("viewer region selection point does not match its intrinsic pixel")

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
        expected_atlas_identity = (
            self.atlas.atlas_key,
            self.atlas.atlas_package_version,
        )
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
