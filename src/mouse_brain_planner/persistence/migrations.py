"""Project-schema migration entry point."""

from __future__ import annotations

from typing import Any

from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION


class UnsupportedProjectSchemaError(ValueError):
    """Raised when a project cannot be migrated safely."""


def migrate_project_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Migrate a project payload to the current schema.

    Schema 1 is the first released format. Future migrations must be explicit,
    deterministic, and covered by fixture tests.
    """

    version = payload.get("schema_version")
    if version == PROJECT_SCHEMA_VERSION:
        return payload
    raise UnsupportedProjectSchemaError(
        f"project schema {version!r} cannot be migrated to {PROJECT_SCHEMA_VERSION}"
    )
