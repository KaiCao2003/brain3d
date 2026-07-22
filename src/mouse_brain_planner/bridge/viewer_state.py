"""Authoritative independent slice depths and region picks for the native viewer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError

from mouse_brain_planner.atlas.brainglobe_adapter import AtlasAdapterError
from mouse_brain_planner.bridge import PROTOCOL_VERSION
from mouse_brain_planner.bridge.atlas_interaction import (
    ATLAS_PHYSICAL_FRAME_ID,
    _region_payload,
    _source_coordinate_frame,
)
from mouse_brain_planner.bridge.server import (
    BridgeDispatcher,
    BridgeError,
    JsonObject,
    LoadedAtlasProtocol,
    atlas_provenance,
    render_atlas_slice_payload,
)
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import RegionRecord
from mouse_brain_planner.domain.coordinate_models import (
    BrainGlobePhysicalPoint,
    BrainGlobeVoxelIndex,
)
from mouse_brain_planner.domain.project_models import (
    PlannerProject,
    ViewerRegionSelection,
    ViewerSliceDepths,
    utc_now,
)
from mouse_brain_planner.rendering.slice_renderer import SliceOrientation, SliceRenderer

ProjectGetter = Callable[[], PlannerProject]
RevisionGetter = Callable[[], int]
ProjectReplacer = Callable[[PlannerProject], int]


@dataclass(slots=True)
class ViewerStateBridge:
    """Register strict viewer mutations against one planning session."""

    dispatcher: BridgeDispatcher
    get_project: ProjectGetter
    get_revision: RevisionGetter
    replace_project: ProjectReplacer

    def register(self) -> None:
        self.dispatcher.register("viewer.state.get", self.state_get)
        self.dispatcher.register("viewer.region.pick", self.region_pick)
        self.dispatcher.register("viewer.slice.set", self.slice_set)
        self.dispatcher.register("viewer.slice.render", self.slice_render)
        self.dispatcher.declare_capability("independentSliceViewer")
        self.dispatcher.declare_capability("independentSliceRender")

    def state_get(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(params, required={"protocolVersion"})
        _require_protocol(params)
        project = self.get_project()
        atlas = self._require_loaded_atlas()
        renderer = self._require_renderer()
        _validate_project_atlas(project, atlas)
        _require_slice_depths(project)
        return self.snapshot(project, self.get_revision(), atlas=atlas, renderer=renderer)

    def region_pick(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "orientation",
                "index",
                "column",
                "row",
            },
        )
        _require_protocol(params)
        project, atlas, renderer = self._validated_mutation_context(params)
        orientation = _orientation(params["orientation"])
        slice_index = _integer(params["index"], "index")
        depths = _require_slice_depths(project)
        persisted_index = _depth_for(depths, orientation)
        if slice_index != persisted_index:
            raise BridgeError(
                "VIEWER_SLICE_STALE",
                "The selected pixel does not belong to the persisted slice depth.",
                details={
                    "orientation": orientation.value,
                    "requestedIndex": slice_index,
                    "persistedIndex": persisted_index,
                },
            )
        column = _integer(params["column"], "column")
        row = _integer(params["row"], "row")
        try:
            voxel = renderer.pixel_to_voxel(orientation, slice_index, column, row)
        except IndexError as error:
            rows, columns = renderer.image_shape(orientation)
            raise BridgeError(
                "VIEWER_PICK_OUT_OF_RANGE",
                "The selected intrinsic PNG pixel is outside the persisted slice.",
                details={
                    "orientation": orientation.value,
                    "index": slice_index,
                    "sliceCount": renderer.slice_count(orientation),
                    "column": column,
                    "row": row,
                    "width": columns,
                    "height": rows,
                },
            ) from error
        point = BrainGlobeAtlasSpace(atlas.metadata).index_to_center(
            BrainGlobeVoxelIndex(
                atlas_key=atlas.metadata.atlas_key,
                atlas_version=atlas.metadata.atlas_package_version,
                ap=voxel[0],
                dv=voxel[1],
                ml=voxel[2],
            )
        )
        region = _region_at(atlas, point)
        updated = _validated_project_update(
            project,
            viewer_region_selection=ViewerRegionSelection(
                orientation=orientation.value,
                index=slice_index,
                column=column,
                row=row,
                atlas_point=point,
            ),
            selected_region_id=None if region is None else region.structure_id,
        )
        return self._publish(updated, atlas, renderer, status="regionSelected")

    def slice_set(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "orientation",
                "index",
            },
        )
        _require_protocol(params)
        project, atlas, renderer = self._validated_mutation_context(params)
        orientation = _orientation(params["orientation"])
        slice_index = _validated_slice_index(
            renderer, orientation, _integer(params["index"], "index")
        )
        updated = _project_with_slice(project, orientation, slice_index)
        return self._publish(updated, atlas, renderer, status="sliceUpdated")

    def slice_render(self, params: Mapping[str, object]) -> JsonObject:
        """Atomically store one depth and return its full-resolution lossless PNG."""

        _validate_params(
            params,
            required={
                "protocolVersion",
                "projectId",
                "expectedProjectRevision",
                "orientation",
                "index",
            },
        )
        _require_protocol(params)
        project, atlas, renderer = self._validated_mutation_context(params)
        orientation = _orientation(params["orientation"])
        slice_index = _validated_slice_index(
            renderer, orientation, _integer(params["index"], "index")
        )
        updated = _project_with_slice(project, orientation, slice_index)
        rendered_slice = render_atlas_slice_payload(
            atlas,
            renderer,
            orientation,
            slice_index,
            compression_level=1,
        )
        result = self._publish(updated, atlas, renderer, status="sliceUpdated")
        result["renderedSlice"] = rendered_slice
        return result

    def snapshot(
        self,
        project: PlannerProject | None = None,
        revision: int | None = None,
        *,
        atlas: LoadedAtlasProtocol | None = None,
        renderer: SliceRenderer | None = None,
    ) -> JsonObject:
        """Return the canonical metadata-only independent-view snapshot."""

        resolved_project = self.get_project() if project is None else project
        resolved_revision = self.get_revision() if revision is None else revision
        resolved_atlas = self._require_loaded_atlas() if atlas is None else atlas
        resolved_renderer = self._require_renderer() if renderer is None else renderer
        _validate_project_atlas(resolved_project, resolved_atlas)
        depths = _require_slice_depths(resolved_project)
        slices: JsonObject = {}
        for orientation in SliceOrientation:
            slice_index = _depth_for(depths, orientation)
            slices[orientation.value] = {
                "orientation": orientation.value,
                "index": slice_index,
                "sliceCount": resolved_renderer.slice_count(orientation),
                "fixedAxis": orientation.fixed_axis_name,
                "rowAxis": orientation.row_axis_name,
                "columnAxis": orientation.column_axis_name,
                "sliceCenterMicrometres": (
                    resolved_renderer.slice_center_mm(orientation, slice_index) * 1000.0
                ),
            }
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "projectId": str(resolved_project.project_uuid),
            "projectRevision": resolved_revision,
            "atlas": atlas_provenance(resolved_atlas),
            "coordinateFrame": _source_coordinate_frame(resolved_atlas.metadata),
            "slices": slices,
            "selection": _selection_payload(resolved_project, resolved_atlas),
        }

    def _validated_context(
        self, raw_project_id: object
    ) -> tuple[PlannerProject, LoadedAtlasProtocol, SliceRenderer]:
        project = self.get_project()
        _require_matching_project_id(raw_project_id, project)
        atlas = self._require_loaded_atlas()
        renderer = self._require_renderer()
        _validate_project_atlas(project, atlas)
        _require_slice_depths(project)
        return project, atlas, renderer

    def _validated_mutation_context(
        self, params: Mapping[str, object]
    ) -> tuple[PlannerProject, LoadedAtlasProtocol, SliceRenderer]:
        project, atlas, renderer = self._validated_context(params["projectId"])
        expected = _integer(params["expectedProjectRevision"], "expectedProjectRevision")
        actual = self.get_revision()
        if expected != actual:
            raise BridgeError(
                "PROJECT_REVISION_CONFLICT",
                "The viewer mutation was based on a stale project revision.",
                details={
                    "expectedProjectRevision": expected,
                    "actualProjectRevision": actual,
                },
            )
        return project, atlas, renderer

    def _publish(
        self,
        updated: PlannerProject,
        atlas: LoadedAtlasProtocol,
        renderer: SliceRenderer,
        *,
        status: str,
    ) -> JsonObject:
        next_revision = self.get_revision() + 1
        snapshot = self.snapshot(updated, next_revision, atlas=atlas, renderer=renderer)
        revision = self.replace_project(updated)
        if revision != next_revision:
            raise RuntimeError("viewer project replacer did not increment revision exactly once")
        return {**snapshot, "status": status}

    def _require_loaded_atlas(self) -> LoadedAtlasProtocol:
        atlas = self.dispatcher.context.loaded_atlas
        if atlas is None:
            raise BridgeError("ATLAS_NOT_OPEN", "Open the reviewed atlas first.")
        return atlas

    def _require_renderer(self) -> SliceRenderer:
        renderer = self.dispatcher.context.renderer
        if renderer is None:
            raise BridgeError("ATLAS_NOT_OPEN", "Open the reviewed atlas first.")
        return renderer


def register_viewer_state_handlers(
    dispatcher: BridgeDispatcher,
    *,
    get_project: ProjectGetter,
    get_revision: RevisionGetter,
    replace_project: ProjectReplacer,
) -> ViewerStateBridge:
    extension = ViewerStateBridge(dispatcher, get_project, get_revision, replace_project)
    extension.register()
    return extension


def _project_with_slice(
    project: PlannerProject,
    orientation: SliceOrientation,
    slice_index: int,
) -> PlannerProject:
    depths = _require_slice_depths(project)
    updated_depths = depths.model_copy(update={orientation.value: slice_index})
    return _validated_project_update(
        project,
        viewer_slice_depths=updated_depths,
        viewer_region_selection=None,
        selected_region_id=None,
    )


def _validated_project_update(project: PlannerProject, **updates: object) -> PlannerProject:
    payload = project.model_dump(mode="python")
    payload.update(updates)
    payload["modified_at"] = utc_now()
    try:
        return PlannerProject.model_validate(payload)
    except ValidationError as error:
        raise BridgeError(
            "PROJECT_STATE_INVALID",
            "The viewer mutation would create an invalid project state.",
            details={"validationErrors": error.error_count()},
        ) from error


def _selection_payload(project: PlannerProject, atlas: LoadedAtlasProtocol) -> JsonObject | None:
    selection = project.viewer_region_selection
    if selection is None:
        return None
    index = BrainGlobeAtlasSpace(atlas.metadata).physical_to_index(selection.atlas_point)
    region = _region_at(atlas, selection.atlas_point)
    return {
        "orientation": selection.orientation,
        "index": selection.index,
        "column": selection.column,
        "row": selection.row,
        "atlasPoint": _point_payload(selection.atlas_point),
        "containingVoxelIndex": {
            "frameId": index.frame_id,
            "ap": index.ap,
            "dv": index.dv,
            "ml": index.ml,
        },
        "region": None if region is None else _region_payload(region),
        "hemisphere": BrainGlobeAtlasSpace(atlas.metadata).hemisphere(selection.atlas_point).value,
    }


def _validate_params(params: Mapping[str, object], *, required: set[str]) -> None:
    actual = set(params)
    if actual != required:
        raise BridgeError(
            "INVALID_PARAMS",
            "The method parameters do not match the protocol-v1 schema.",
            details={
                "missing": sorted(required - actual),
                "unexpected": sorted(actual - required),
            },
        )


def _require_protocol(params: Mapping[str, object]) -> None:
    value = params["protocolVersion"]
    if isinstance(value, bool) or not isinstance(value, int) or value != PROTOCOL_VERSION:
        raise BridgeError(
            "PROTOCOL_VERSION_MISMATCH",
            f"protocolVersion must equal {PROTOCOL_VERSION}.",
            details={"supported": PROTOCOL_VERSION},
        )


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a nonnegative integer.",
            details={"field": field},
        )
    return value


def _orientation(value: object) -> SliceOrientation:
    if not isinstance(value, str):
        raise BridgeError(
            "INVALID_PARAMS",
            "orientation must be coronal, sagittal, or horizontal.",
            details={"field": "orientation"},
        )
    try:
        return SliceOrientation(value)
    except ValueError as error:
        raise BridgeError(
            "INVALID_PARAMS",
            "orientation must be coronal, sagittal, or horizontal.",
            details={"field": "orientation", "allowed": [item.value for item in SliceOrientation]},
        ) from error


def _validated_slice_index(
    renderer: SliceRenderer,
    orientation: SliceOrientation,
    slice_index: int,
) -> int:
    slice_count = renderer.slice_count(orientation)
    if slice_index >= slice_count:
        raise BridgeError(
            "SLICE_OUT_OF_RANGE",
            "The requested slice index is outside the atlas volume.",
            details={
                "orientation": orientation.value,
                "index": slice_index,
                "sliceCount": slice_count,
            },
        )
    return slice_index


def _require_matching_project_id(value: object, project: PlannerProject) -> None:
    if not isinstance(value, str):
        raise BridgeError(
            "INVALID_PARAMS",
            "projectId must be a canonical UUID string.",
            details={"field": "projectId"},
        )
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as error:
        raise BridgeError(
            "INVALID_PARAMS",
            "projectId must be a canonical UUID string.",
            details={"field": "projectId"},
        ) from error
    if str(parsed) != value:
        raise BridgeError(
            "INVALID_PARAMS",
            "projectId must be a canonical UUID string.",
            details={"field": "projectId"},
        )
    if parsed != project.project_uuid:
        raise BridgeError(
            "PROJECT_ID_MISMATCH",
            "The viewer request does not target the open project.",
            details={"requestedProjectId": value, "openProjectId": str(project.project_uuid)},
        )


def _validate_project_atlas(project: PlannerProject, atlas: LoadedAtlasProtocol) -> None:
    if project.atlas is None:
        raise BridgeError("PROJECT_ATLAS_REQUIRED", "The viewer requires an atlas-bound project.")
    if project.atlas.model_dump(exclude={"cache_path"}) != atlas.metadata.model_dump(
        exclude={"cache_path"}
    ):
        raise BridgeError(
            "PROJECT_ATLAS_MISMATCH",
            "The project atlas does not exactly match the loaded atlas.",
        )


def _require_slice_depths(project: PlannerProject) -> ViewerSliceDepths:
    if project.viewer_slice_depths is None:
        raise BridgeError(
            "VIEWER_STATE_UNAVAILABLE",
            "The atlas-bound project does not contain independent slice depths.",
        )
    return project.viewer_slice_depths


def _depth_for(depths: ViewerSliceDepths, orientation: SliceOrientation) -> int:
    if orientation is SliceOrientation.CORONAL:
        return depths.coronal
    if orientation is SliceOrientation.SAGITTAL:
        return depths.sagittal
    return depths.horizontal


def _region_at(atlas: LoadedAtlasProtocol, point: BrainGlobePhysicalPoint) -> RegionRecord | None:
    try:
        region = atlas.region_at(point)
    except (AtlasAdapterError, KeyError, OSError, TypeError, ValueError) as error:
        raise BridgeError(
            "ATLAS_POINT_LOOKUP_FAILED",
            "The reviewed atlas could not resolve the containing annotation region.",
            details={"exceptionType": type(error).__name__},
        ) from error
    if region is not None and not isinstance(region, RegionRecord):
        raise BridgeError(
            "ATLAS_CONTRACT_VIOLATION",
            "The atlas returned a non-normalized region record.",
            details={"returnedType": type(region).__name__},
        )
    return region


def _point_payload(point: BrainGlobePhysicalPoint) -> JsonObject:
    return {
        "frameId": ATLAS_PHYSICAL_FRAME_ID,
        "apMicrometres": point.ap_um,
        "dvMicrometres": point.dv_um,
        "mlMicrometres": point.ml_um,
    }
