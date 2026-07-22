"""Protocol-v1 operations for unprojected bregma-relative implant targets.

The bridge deliberately stores only the signed AP/ML/DV values entered by the
user.  These operations do not infer an atlas point and keep every response
locked until a separate, explicit bregma/skull calibration is available.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from pydantic import ValidationError

from mouse_brain_planner.bridge import PROTOCOL_VERSION
from mouse_brain_planner.bridge.server import BridgeDispatcher, BridgeError, JsonObject
from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.project_models import (
    MAX_UNPROJECTED_BREGMA_TARGETS,
    PlannerProject,
)

BREGMA_TARGET_FRAME_ID: Final = "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"
IMPLANT_PROJECTION_STATUS: Final = "lockedUntilExplicitBregmaSkullCalibration"


@dataclass(frozen=True, slots=True)
class ImplantAddParameters:
    """Normalized protocol inputs for one target addition."""

    label: str
    ap_mm: float
    ml_mm: float
    dv_mm: float
    notes: str


@dataclass(frozen=True, slots=True)
class ImplantTargetMutation:
    """An immutable project replacement and its protocol result."""

    project: PlannerProject
    result: JsonObject


ProjectReader = Callable[[], PlannerProject]
ProjectReplacer = Callable[[PlannerProject], None]


@dataclass(slots=True)
class ImplantTargetBridge:
    """Small callback adapter that leaves project ownership with the caller."""

    dispatcher: BridgeDispatcher
    get_project: ProjectReader
    replace_project: ProjectReplacer

    def register(self) -> None:
        """Register the three handlers without depending on the planning session."""

        self.dispatcher.register("implant.list", self.list_targets)
        self.dispatcher.register("implant.add", self.add_target)
        self.dispatcher.register("implant.remove", self.remove_target)
        self.dispatcher.declare_capability("unprojectedBregmaImplantTargets")

    def list_targets(self, params: Mapping[str, object]) -> JsonObject:
        return implant_list(self.get_project(), params)

    def add_target(self, params: Mapping[str, object]) -> JsonObject:
        mutation = implant_add(self.get_project(), params)
        self.replace_project(mutation.project)
        return mutation.result

    def remove_target(self, params: Mapping[str, object]) -> JsonObject:
        mutation = implant_remove(self.get_project(), params)
        self.replace_project(mutation.project)
        return mutation.result


def register_implant_target_handlers(
    dispatcher: BridgeDispatcher,
    *,
    get_project: ProjectReader,
    replace_project: ProjectReplacer,
) -> ImplantTargetBridge:
    """Register implant handlers against caller-owned project state.

    ``replace_project`` is called exactly once after a successful add or
    remove.  The eventual planning-session integration can therefore publish
    the returned replacement and increment its own revision atomically.
    """

    extension = ImplantTargetBridge(dispatcher, get_project, replace_project)
    extension.register()
    return extension


def parse_implant_list_params(params: Mapping[str, object]) -> None:
    """Validate the exact protocol-v1 ``implant.list`` parameter schema."""

    _validate_params(params, required={"protocolVersion"})
    _require_protocol(params)


def parse_implant_add_params(params: Mapping[str, object]) -> ImplantAddParameters:
    """Validate and normalize the exact ``implant.add`` parameter schema."""

    _validate_params(
        params,
        required={
            "protocolVersion",
            "label",
            "apMillimetres",
            "mlMillimetres",
            "dvMillimetres",
        },
        optional={"notes"},
    )
    _require_protocol(params)
    return ImplantAddParameters(
        label=_text(params["label"], field="label", maximum=200, require_visible=True),
        ap_mm=_finite_number(params["apMillimetres"], field="apMillimetres"),
        ml_mm=_finite_number(params["mlMillimetres"], field="mlMillimetres"),
        dv_mm=_finite_number(params["dvMillimetres"], field="dvMillimetres"),
        notes=_text(params.get("notes", ""), field="notes", maximum=4000),
    )


def parse_implant_remove_params(params: Mapping[str, object]) -> UUID:
    """Validate ``implant.remove`` parameters and return the requested UUID."""

    _validate_params(params, required={"protocolVersion", "targetId"})
    _require_protocol(params)
    return _uuid(params["targetId"], field="targetId")


def implant_list(project: PlannerProject, params: Mapping[str, object]) -> JsonObject:
    """Return all persisted targets without projecting or mutating the project."""

    parse_implant_list_params(params)
    snapshot = _validated_project_snapshot(project)
    return _operation_result(
        status="listed",
        target_count=len(snapshot.unprojected_bregma_targets),
        targets=[implant_target_payload(target) for target in snapshot.unprojected_bregma_targets],
    )


def implant_add(
    project: PlannerProject,
    params: Mapping[str, object],
) -> ImplantTargetMutation:
    """Parse one add request and return a validated replacement project."""

    parsed = parse_implant_add_params(params)
    try:
        target = UnprojectedBregmaTarget(
            label=parsed.label,
            ap_mm=parsed.ap_mm,
            ml_mm=parsed.ml_mm,
            dv_mm=parsed.dv_mm,
            notes=parsed.notes,
        )
    except ValidationError as error:  # Defensive protocol/domain boundary.
        raise BridgeError(
            "INVALID_PARAMS",
            "The implant target did not satisfy the persisted coordinate schema.",
            details={"validationErrors": error.error_count()},
        ) from error
    replacement = add_implant_target(project, target)
    stored = replacement.unprojected_bregma_targets[-1]
    return ImplantTargetMutation(
        project=replacement,
        result=_operation_result(
            status="added",
            target_count=len(replacement.unprojected_bregma_targets),
            target=implant_target_payload(stored),
        ),
    )


def implant_remove(
    project: PlannerProject,
    params: Mapping[str, object],
) -> ImplantTargetMutation:
    """Parse one remove request and return a validated replacement project."""

    target_id = parse_implant_remove_params(params)
    replacement, removed = remove_implant_target(project, target_id)
    return ImplantTargetMutation(
        project=replacement,
        result=_operation_result(
            status="removed",
            target_count=len(replacement.unprojected_bregma_targets),
            target=implant_target_payload(removed),
        ),
    )


def add_implant_target(
    project: PlannerProject,
    target: UnprojectedBregmaTarget,
) -> PlannerProject:
    """Return a project copy containing ``target`` and an audit event."""

    snapshot = _validated_project_snapshot(project)
    candidate = _validated_target_snapshot(target)
    if any(
        existing.target_uuid == candidate.target_uuid
        for existing in snapshot.unprojected_bregma_targets
    ):
        raise BridgeError(
            "IMPLANT_TARGET_DUPLICATE",
            "The implant target UUID is already present in the current project.",
            details={"targetId": str(candidate.target_uuid)},
        )
    if len(snapshot.unprojected_bregma_targets) >= MAX_UNPROJECTED_BREGMA_TARGETS:
        raise BridgeError(
            "IMPLANT_TARGET_CAPACITY_REACHED",
            "The project has reached the maximum number of implant targets.",
            details={"maximum": MAX_UNPROJECTED_BREGMA_TARGETS},
        )
    replacement = _replace_targets(
        snapshot,
        [*snapshot.unprojected_bregma_targets, candidate],
    )
    replacement.touch(
        "implant-target-added",
        f"target={candidate.target_uuid}; frame={BREGMA_TARGET_FRAME_ID}; projected=false",
    )
    return replacement


def remove_implant_target(
    project: PlannerProject,
    target_id: UUID,
) -> tuple[PlannerProject, UnprojectedBregmaTarget]:
    """Return a project copy without ``target_id`` plus the removed target."""

    snapshot = _validated_project_snapshot(project)
    removed = next(
        (
            target
            for target in snapshot.unprojected_bregma_targets
            if target.target_uuid == target_id
        ),
        None,
    )
    if removed is None:
        raise BridgeError(
            "IMPLANT_TARGET_NOT_FOUND",
            "The requested implant target is not in the current project.",
            details={"targetId": str(target_id)},
        )
    replacement = _replace_targets(
        snapshot,
        [
            target
            for target in snapshot.unprojected_bregma_targets
            if target.target_uuid != target_id
        ],
    )
    replacement.touch(
        "implant-target-removed",
        f"target={target_id}; frame={BREGMA_TARGET_FRAME_ID}; projected=false",
    )
    return replacement, removed


def implant_target_payload(target: UnprojectedBregmaTarget) -> JsonObject:
    """Serialize one target while repeating the complete fail-closed contract."""

    target = _validated_target_snapshot(target)
    return {
        "targetId": str(target.target_uuid),
        "schemaVersion": target.schema_version,
        "label": target.label,
        "apMillimetres": target.ap_mm,
        "mlMillimetres": target.ml_mm,
        "dvMillimetres": target.dv_mm,
        "frameId": target.frame_id,
        "origin": target.origin,
        "componentOrder": list(target.component_order),
        "units": target.units,
        "apPositiveDirection": target.ap_positive_direction,
        "apNegativeDirection": target.ap_negative_direction,
        "mlPositiveDirection": target.ml_positive_direction,
        "mlNegativeDirection": target.ml_negative_direction,
        "dvPositiveDirection": target.dv_positive_direction,
        "dvNegativeDirection": target.dv_negative_direction,
        "createdAt": target.created_at.isoformat().replace("+00:00", "Z"),
        "notes": target.notes,
        "projected": False,
        "usableForNavigation": False,
        "projectionStatus": IMPLANT_PROJECTION_STATUS,
    }


def _operation_result(
    *,
    status: str,
    target_count: int,
    target: JsonObject | None = None,
    targets: list[JsonObject] | None = None,
) -> JsonObject:
    result: JsonObject = {
        "protocolVersion": PROTOCOL_VERSION,
        "status": status,
        "targetCount": target_count,
        "coordinateFrame": _coordinate_frame_payload(),
        "projected": False,
        "usableForNavigation": False,
        "projectionStatus": IMPLANT_PROJECTION_STATUS,
    }
    if target is not None:
        result["target"] = target
    if targets is not None:
        result["targets"] = targets
    return result


def _coordinate_frame_payload() -> JsonObject:
    return {
        "frameId": BREGMA_TARGET_FRAME_ID,
        "origin": "bregma",
        "componentOrder": ["AP", "ML", "DV"],
        "units": "millimetre",
        "signConvention": {
            "apPositive": "anterior",
            "apNegative": "posterior/back",
            "mlPositive": "right",
            "mlNegative": "left",
            "dvPositive": "dorsal/up",
            "dvNegative": "deep/ventral",
        },
    }


def _replace_targets(
    project: PlannerProject,
    targets: list[UnprojectedBregmaTarget],
) -> PlannerProject:
    payload = project.model_dump(mode="python")
    payload["unprojected_bregma_targets"] = targets
    try:
        return PlannerProject.model_validate(payload)
    except ValidationError as error:
        raise BridgeError(
            "PROJECT_STATE_INVALID",
            "The implant target change did not produce a valid project.",
            details={"validationErrors": error.error_count()},
        ) from error


def _validated_project_snapshot(project: PlannerProject) -> PlannerProject:
    try:
        return PlannerProject.model_validate(project.model_dump(mode="python"))
    except ValidationError as error:
        raise BridgeError(
            "PROJECT_STATE_INVALID",
            "The current project failed validation before the implant operation.",
            details={"validationErrors": error.error_count()},
        ) from error


def _validated_target_snapshot(target: UnprojectedBregmaTarget) -> UnprojectedBregmaTarget:
    try:
        return UnprojectedBregmaTarget.model_validate(target.model_dump(mode="python"))
    except ValidationError as error:
        raise BridgeError(
            "IMPLANT_TARGET_INVALID",
            "The implant target failed its persisted fail-closed schema.",
            details={"validationErrors": error.error_count()},
        ) from error


def _validate_params(
    params: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    actual = set(params)
    missing = required - actual
    unexpected = actual - allowed
    if missing or unexpected:
        raise BridgeError(
            "INVALID_PARAMS",
            "The method parameters do not match the protocol-v1 schema.",
            details={"missing": sorted(missing), "unexpected": sorted(unexpected)},
        )


def _require_protocol(params: Mapping[str, object]) -> None:
    value = params["protocolVersion"]
    if isinstance(value, bool) or not isinstance(value, int) or value != PROTOCOL_VERSION:
        raise BridgeError(
            "PROTOCOL_VERSION_MISMATCH",
            f"protocolVersion must equal {PROTOCOL_VERSION}.",
            details={"supported": PROTOCOL_VERSION},
        )


def _finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a finite number in millimetres.",
            details={"field": field},
        )
    try:
        normalized = float(value)
    except (OverflowError, ValueError) as error:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a finite number in millimetres.",
            details={"field": field},
        ) from error
    if not math.isfinite(normalized):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a finite number in millimetres.",
            details={"field": field},
        )
    return 0.0 if normalized == 0 else normalized


def _text(
    value: object,
    *,
    field: str,
    maximum: int,
    require_visible: bool = False,
) -> str:
    if not isinstance(value, str):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a string no longer than {maximum} characters.",
            details={"field": field},
        )
    normalized = value.strip() if require_visible else value
    if len(normalized) > maximum or (require_visible and not normalized):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a string no longer than {maximum} characters.",
            details={"field": field},
        )
    return normalized


def _uuid(value: object, *, field: str) -> UUID:
    if not isinstance(value, str):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a UUID string.",
            details={"field": field},
        )
    try:
        return UUID(value)
    except ValueError as error:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a UUID string.",
            details={"field": field},
        ) from error
