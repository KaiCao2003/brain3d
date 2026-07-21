"""Versioned, human-readable project models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION, __version__


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
    """Phase 1 project state."""

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
    selected_region_id: int | None = Field(default=None, gt=0)
    region_display: list[RegionDisplayState] = Field(default_factory=list)
    coordinate_convention: str = "BrainGlobe ASR: [AP,DV,ML], origin A/S/R, increasing P/I/L, µm"
    scientific_disclaimer_acknowledged: bool = False
    user_notes: str = ""
    event_log: list[ProjectEvent] = Field(default_factory=list)

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

        if self.atlas is None:
            if self.linked_cursor is not None:
                raise ValueError("a linked atlas cursor requires atlas metadata")
            if self.selected_region_id is not None or self.region_display:
                raise ValueError("atlas region state requires atlas metadata")
            return self

        if self.linked_cursor is not None:
            expected_identity = (
                self.atlas.atlas_key,
                self.atlas.atlas_package_version,
            )
            cursor_identity = (
                self.linked_cursor.atlas_key,
                self.linked_cursor.atlas_version,
            )
            if cursor_identity != expected_identity:
                raise ValueError(
                    f"linked cursor atlas identity {cursor_identity} does not match "
                    f"project atlas {expected_identity}"
                )
            for axis, (value, extent) in enumerate(
                zip(
                    self.linked_cursor.as_tuple(),
                    self.atlas.extent_um,
                    strict=True,
                )
            ):
                if value < 0 or value >= extent:
                    raise ValueError(
                        f"linked cursor axis {axis} value {value:g} is outside "
                        f"atlas bounds [0, {extent}) µm"
                    )

        region_ids = [state.structure_id for state in self.region_display]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("project region display state contains duplicate structure IDs")
        return self

    def touch(self, action: str, details: str | None = None) -> None:
        """Update modification time and append one reproducible event."""

        self.modified_at = utc_now()
        self.event_log.append(ProjectEvent(action=action, details=details))
