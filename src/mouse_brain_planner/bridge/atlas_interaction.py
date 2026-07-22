"""Read-only atlas region, point, and mesh methods for the native shell.

The extension deliberately exposes atlas-native BrainGlobe ASR coordinates.
It never treats those coordinates as bregma-relative stereotaxic values and it
never serializes mesh contents through the newline-delimited JSON transport.
"""

from __future__ import annotations

import hashlib
import math
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from mouse_brain_planner.analysis.region_traversal import (
    ANNOTATION_RAY_PICK_ALGORITHM_VERSION,
    RegionTraversalInputError,
    first_annotated_voxel_on_segment,
)
from mouse_brain_planner.atlas.brainglobe_adapter import AtlasAdapterError
from mouse_brain_planner.bridge import PROTOCOL_VERSION
from mouse_brain_planner.bridge.server import (
    SUPPORTED_ATLAS_IDENTIFIER,
    SUPPORTED_ATLAS_VERSION,
    BridgeDispatcher,
    BridgeError,
    JsonObject,
    LoadedAtlasProtocol,
    atlas_provenance,
)
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint

MAX_REGION_PAGE_SIZE: Final = 500
DEFAULT_REGION_PAGE_SIZE: Final = 200
MAX_SEARCH_RESULTS: Final = 100
DEFAULT_SEARCH_RESULTS: Final = 25
MAX_SEARCH_QUERY_CHARACTERS: Final = 128
HASH_CHUNK_BYTES: Final = 1024 * 1024
ATLAS_PHYSICAL_FRAME_ID: Final = "BRAINGLOBE_PHYSICAL_ASR_UM"


@dataclass(slots=True)
class AtlasInteractionBridge:
    """Register planning-safe, read-only operations for one loaded atlas."""

    dispatcher: BridgeDispatcher

    def register(self) -> None:
        """Publish the handlers and their independently discoverable capabilities."""

        self.dispatcher.register("atlas.regions", self.regions)
        self.dispatcher.register("atlas.search", self.search)
        self.dispatcher.register("atlas.point", self.point)
        self.dispatcher.register("atlas.ray.pick", self.ray_pick)
        self.dispatcher.register("atlas.mesh", self.mesh)
        self.dispatcher.declare_capability("atlasRegionRecords")
        self.dispatcher.declare_capability("atlasRegionSearch")
        self.dispatcher.declare_capability("atlasPhysicalPointLookup")
        self.dispatcher.declare_capability("atlasAnnotationRayPick")
        self.dispatcher.declare_capability("atlasMeshDescriptor")

    def regions(self, params: Mapping[str, object]) -> JsonObject:
        """Return one deterministic page of normalized atlas region records."""

        _validate_params(
            params,
            required={"protocolVersion"},
            optional={"offset", "limit"},
        )
        _require_protocol(params)
        offset = _bounded_integer(
            params.get("offset", 0),
            field="offset",
            minimum=0,
            maximum=(1 << 31) - 1,
        )
        limit = _bounded_integer(
            params.get("limit", DEFAULT_REGION_PAGE_SIZE),
            field="limit",
            minimum=1,
            maximum=MAX_REGION_PAGE_SIZE,
        )
        atlas = self._require_loaded_atlas()
        records = _validated_regions(atlas)
        page = records[offset : offset + limit]
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "offset": offset,
            "limit": limit,
            "returnedCount": len(page),
            "totalCount": len(records),
            "hasMore": offset + len(page) < len(records),
            "regions": [_region_payload(region) for region in page],
            "atlas": atlas_provenance(atlas),
        }

    def search(self, params: Mapping[str, object]) -> JsonObject:
        """Search exact normalized IDs, acronyms, and names without fuzzy guessing."""

        _validate_params(
            params,
            required={"protocolVersion", "query"},
            optional={"limit"},
        )
        _require_protocol(params)
        raw_query = params["query"]
        if (
            not isinstance(raw_query, str)
            or not raw_query.strip()
            or len(raw_query) > MAX_SEARCH_QUERY_CHARACTERS
        ):
            raise BridgeError(
                "INVALID_PARAMS",
                (
                    "query must contain 1 to "
                    f"{MAX_SEARCH_QUERY_CHARACTERS} non-whitespace characters."
                ),
                details={"field": "query"},
            )
        query = raw_query.strip()
        normalized_query = query.casefold()
        limit = _bounded_integer(
            params.get("limit", DEFAULT_SEARCH_RESULTS),
            field="limit",
            minimum=1,
            maximum=MAX_SEARCH_RESULTS,
        )
        atlas = self._require_loaded_atlas()
        ranked: list[tuple[int, str, int, RegionRecord, str]] = []
        for region in _validated_regions(atlas):
            match = _region_match(region, normalized_query, query)
            if match is None:
                continue
            rank, kind = match
            ranked.append((rank, region.acronym.casefold(), region.structure_id, region, kind))
        ranked.sort(key=lambda item: item[:3])
        selected = ranked[:limit]
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "query": query,
            "matchingRule": (
                "case-insensitive exact, prefix, then substring matching over normalized "
                "acronym/name; decimal structure ID is exact only"
            ),
            "returnedCount": len(selected),
            "totalMatchCount": len(ranked),
            "results": [
                {"matchKind": match_kind, "region": _region_payload(region)}
                for _, _, _, region, match_kind in selected
            ],
            "atlas": atlas_provenance(atlas),
        }

    def point(self, params: Mapping[str, object]) -> JsonObject:
        """Resolve a bounded atlas-native physical point to its containing region."""

        _validate_params(
            params,
            required={
                "protocolVersion",
                "frameId",
                "apMicrometres",
                "dvMicrometres",
                "mlMicrometres",
            },
        )
        _require_protocol(params)
        if params["frameId"] != ATLAS_PHYSICAL_FRAME_ID:
            raise BridgeError(
                "INVALID_PARAMS",
                (
                    "frameId must be BRAINGLOBE_PHYSICAL_ASR_UM; bregma-relative "
                    "coordinates require an explicit stereotaxic calibration."
                ),
                details={"field": "frameId", "expected": ATLAS_PHYSICAL_FRAME_ID},
            )
        ap_um = _finite_number(params["apMicrometres"], field="apMicrometres")
        dv_um = _finite_number(params["dvMicrometres"], field="dvMicrometres")
        ml_um = _finite_number(params["mlMicrometres"], field="mlMicrometres")
        atlas = self._require_loaded_atlas()
        point = BrainGlobePhysicalPoint(
            atlas_key=atlas.metadata.atlas_key,
            atlas_version=atlas.metadata.atlas_package_version,
            ap_um=ap_um,
            dv_um=dv_um,
            ml_um=ml_um,
        )
        space = BrainGlobeAtlasSpace(atlas.metadata)
        try:
            index = space.physical_to_index(point)
            center = space.index_to_center(index)
        except ValueError as error:
            raise BridgeError(
                "ATLAS_POINT_OUT_OF_RANGE",
                "The atlas-native point must lie inside the half-open 25 micrometre volume.",
                details={
                    "frameId": ATLAS_PHYSICAL_FRAME_ID,
                    "minimumInclusiveMicrometres": [0.0, 0.0, 0.0],
                    "maximumExclusiveMicrometres": list(atlas.metadata.extent_um),
                },
            ) from error
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
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "point": {
                "frameId": ATLAS_PHYSICAL_FRAME_ID,
                "apMicrometres": point.ap_um,
                "dvMicrometres": point.dv_um,
                "mlMicrometres": point.ml_um,
            },
            "containingVoxelIndex": {
                "frameId": index.frame_id,
                "ap": index.ap,
                "dv": index.dv,
                "ml": index.ml,
            },
            "containingVoxelCenter": {
                "frameId": center.frame_id,
                "apMicrometres": center.ap_um,
                "dvMicrometres": center.dv_um,
                "mlMicrometres": center.ml_um,
            },
            "region": None if region is None else _region_payload(region),
            "annotationStructureId": 0 if region is None else region.structure_id,
            "coordinateFrame": _source_coordinate_frame(atlas.metadata),
            "atlas": atlas_provenance(atlas),
        }

    def mesh(self, params: Mapping[str, object]) -> JsonObject:
        """Describe, but never inline, one verified atlas-owned mesh file."""

        _validate_params(
            params,
            required={"protocolVersion", "target"},
            optional={"structureId"},
        )
        _require_protocol(params)
        target = params["target"]
        if not isinstance(target, str) or target not in {"root", "region"}:
            raise BridgeError(
                "INVALID_PARAMS",
                "target must be root or region.",
                details={"field": "target", "allowed": ["root", "region"]},
            )
        atlas = self._require_loaded_atlas()
        region: RegionRecord | None = None
        try:
            if target == "root":
                if "structureId" in params:
                    raise BridgeError(
                        "INVALID_PARAMS",
                        "structureId must be omitted when target is root.",
                        details={"field": "structureId"},
                    )
                mesh_path = atlas.root_mesh_file()
            else:
                if "structureId" not in params:
                    raise BridgeError(
                        "INVALID_PARAMS",
                        "structureId is required when target is region.",
                        details={"field": "structureId"},
                    )
                structure_id = _bounded_integer(
                    params["structureId"],
                    field="structureId",
                    minimum=1,
                    maximum=(1 << 63) - 1,
                )
                by_id = {item.structure_id: item for item in _validated_regions(atlas)}
                region = by_id.get(structure_id)
                if region is None:
                    raise BridgeError(
                        "ATLAS_REGION_NOT_FOUND",
                        "The requested structure ID is not present in the loaded atlas.",
                        details={"structureId": structure_id},
                    )
                mesh_path = atlas.mesh_file_for_region(region)
        except BridgeError:
            raise
        except (AtlasAdapterError, KeyError, OSError, TypeError, ValueError) as error:
            raise BridgeError(
                "ATLAS_MESH_UNAVAILABLE",
                "The reviewed atlas could not provide the requested mesh file.",
                details={"target": target, "exceptionType": type(error).__name__},
            ) from error
        descriptor = _mesh_descriptor(mesh_path, atlas.metadata)
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "target": target,
            "region": None if region is None else _region_payload(region),
            "mesh": descriptor,
            "sourceCoordinateFrame": _source_coordinate_frame(atlas.metadata),
            "atlas": atlas_provenance(atlas),
        }

    def ray_pick(self, params: Mapping[str, object]) -> JsonObject:
        """Resolve the first annotated voxel crossed by a finite camera ray."""

        coordinate_fields = (
            "startApMicrometres",
            "startDvMicrometres",
            "startMlMicrometres",
            "endApMicrometres",
            "endDvMicrometres",
            "endMlMicrometres",
        )
        _validate_params(
            params,
            required={"protocolVersion", "frameId", *coordinate_fields},
        )
        _require_protocol(params)
        if params["frameId"] != ATLAS_PHYSICAL_FRAME_ID:
            raise BridgeError(
                "INVALID_PARAMS",
                "frameId must be BRAINGLOBE_PHYSICAL_ASR_UM.",
                details={"field": "frameId", "expected": ATLAS_PHYSICAL_FRAME_ID},
            )
        values = {field: _finite_number(params[field], field=field) for field in coordinate_fields}
        start = (
            values["startApMicrometres"],
            values["startDvMicrometres"],
            values["startMlMicrometres"],
        )
        end = (
            values["endApMicrometres"],
            values["endDvMicrometres"],
            values["endMlMicrometres"],
        )
        atlas = self._require_loaded_atlas()
        try:
            hit = first_annotated_voxel_on_segment(
                annotation=atlas.annotation,
                metadata=atlas.metadata,
                start_ap_dv_ml_um=start,
                end_ap_dv_ml_um=end,
            )
        except (RegionTraversalInputError, TypeError, ValueError) as error:
            raise BridgeError(
                "ATLAS_RAY_INVALID",
                "The finite atlas camera ray is invalid.",
                details={"exceptionType": type(error).__name__},
            ) from error
        result: JsonObject = {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "noAnnotatedVoxel" if hit is None else "hit",
            "algorithmVersion": ANNOTATION_RAY_PICK_ALGORITHM_VERSION,
            "hit": None,
            "coordinateFrame": _source_coordinate_frame(atlas.metadata),
            "atlas": atlas_provenance(atlas),
        }
        if hit is None:
            return result

        regions_by_id = {region.structure_id: region for region in _validated_regions(atlas)}
        region = regions_by_id.get(hit.annotation_id)
        if region is None:
            raise BridgeError(
                "ATLAS_CONTRACT_VIOLATION",
                "The annotation ray crossed an ID missing from the atlas region records.",
                details={"annotationStructureId": hit.annotation_id},
            )
        entry_ap, entry_dv, entry_ml = hit.entry_point_ap_dv_ml_um
        center_ap, center_dv, center_ml = hit.voxel_center_ap_dv_ml_um
        center_point = BrainGlobePhysicalPoint(
            atlas_key=atlas.metadata.atlas_key,
            atlas_version=atlas.metadata.atlas_package_version,
            ap_um=center_ap,
            dv_um=center_dv,
            ml_um=center_ml,
        )
        result["hit"] = {
            "entryPoint": {
                "frameId": ATLAS_PHYSICAL_FRAME_ID,
                "apMicrometres": entry_ap,
                "dvMicrometres": entry_dv,
                "mlMicrometres": entry_ml,
            },
            "voxelCenter": {
                "frameId": ATLAS_PHYSICAL_FRAME_ID,
                "apMicrometres": center_ap,
                "dvMicrometres": center_dv,
                "mlMicrometres": center_ml,
            },
            "containingVoxelIndex": {
                "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
                "ap": hit.index_ap_dv_ml[0],
                "dv": hit.index_ap_dv_ml[1],
                "ml": hit.index_ap_dv_ml[2],
            },
            "annotationStructureId": hit.annotation_id,
            "region": _region_payload(region),
            "hemisphere": BrainGlobeAtlasSpace(atlas.metadata).hemisphere(center_point).value,
            "distanceFromRayStartMicrometres": hit.distance_from_start_um,
            "distanceInsideVoxelMicrometres": hit.distance_inside_voxel_um,
        }
        return result

    def _require_loaded_atlas(self) -> LoadedAtlasProtocol:
        atlas = self.dispatcher.context.loaded_atlas
        if atlas is None:
            raise BridgeError(
                "ATLAS_NOT_OPEN",
                "Open the reviewed 25 micrometre atlas before requesting atlas data.",
            )
        if (
            atlas.metadata.atlas_key != SUPPORTED_ATLAS_IDENTIFIER
            or atlas.metadata.atlas_package_version != SUPPORTED_ATLAS_VERSION
            or atlas.metadata.resolution_um != (25.0, 25.0, 25.0)
        ):
            raise BridgeError(
                "ATLAS_CONTRACT_VIOLATION",
                "Atlas interaction methods accept only allen_mouse_25um v1.2 at 25 micrometres.",
                details={
                    "identifier": atlas.metadata.atlas_key,
                    "version": atlas.metadata.atlas_package_version,
                    "resolutionMicrometres": list(atlas.metadata.resolution_um),
                },
            )
        return atlas


def register_atlas_interaction_handlers(
    dispatcher: BridgeDispatcher,
) -> AtlasInteractionBridge:
    """Register read-only atlas interaction handlers and return their owner."""

    extension = AtlasInteractionBridge(dispatcher)
    extension.register()
    return extension


def _validated_regions(atlas: LoadedAtlasProtocol) -> list[RegionRecord]:
    raw_records = atlas.regions
    if not isinstance(raw_records, list) or any(
        not isinstance(region, RegionRecord) for region in raw_records
    ):
        raise BridgeError(
            "ATLAS_CONTRACT_VIOLATION",
            "The atlas region collection is not a list of normalized RegionRecord values.",
        )
    records = list(raw_records)
    ids = [region.structure_id for region in records]
    acronyms = [region.acronym for region in records]
    if len(set(ids)) != len(ids) or len(set(acronyms)) != len(acronyms):
        raise BridgeError(
            "ATLAS_CONTRACT_VIOLATION",
            "The normalized atlas region collection contains duplicate identities.",
        )
    return records


def _region_payload(region: RegionRecord) -> JsonObject:
    return {
        "structureId": region.structure_id,
        "acronym": region.acronym,
        "name": region.name,
        "parentStructureId": region.parent_id,
        "structureIdPath": list(region.structure_id_path),
        "rgb": list(region.rgb),
    }


def _region_match(
    region: RegionRecord,
    normalized_query: str,
    display_query: str,
) -> tuple[int, str] | None:
    acronym = region.acronym.casefold()
    name = region.name.casefold()
    if display_query.isdecimal() and str(region.structure_id) == display_query:
        return (0, "structureIdExact")
    if acronym == normalized_query:
        return (1, "acronymExact")
    if name == normalized_query:
        return (2, "nameExact")
    if acronym.startswith(normalized_query):
        return (3, "acronymPrefix")
    if name.startswith(normalized_query):
        return (4, "namePrefix")
    if normalized_query in acronym:
        return (5, "acronymSubstring")
    if normalized_query in name:
        return (6, "nameSubstring")
    return None


def _source_coordinate_frame(metadata: AtlasMetadata) -> JsonObject:
    return {
        "frameId": ATLAS_PHYSICAL_FRAME_ID,
        "unit": "micrometres",
        "coordinateKind": "continuousPhysical",
        "axisOrder": ["AP", "DV", "ML"],
        "origin": ["anterior", "superior", "right"],
        "positiveDirections": ["posterior", "inferior", "left"],
        "axes": [
            {
                "arrayAxis": axis.array_axis,
                "anatomicalAxis": axis.anatomical_axis,
                "originDirection": axis.origin_direction,
                "positiveDirection": axis.positive_direction,
                "voxelSizeMicrometres": axis.voxel_size_um,
            }
            for axis in metadata.axes
        ],
        "bregmaRelative": False,
        "stereotaxicCalibrationApplied": False,
        "voxelAnchorOffsetApplied": False,
        "bounds": {
            "minimumInclusiveMicrometres": [0.0, 0.0, 0.0],
            "maximumExclusiveMicrometres": list(metadata.extent_um),
        },
    }


def _mesh_descriptor(mesh_path: Path, metadata: AtlasMetadata) -> JsonObject:
    try:
        atlas_root = Path(metadata.cache_path).resolve(strict=True)
        canonical = Path(mesh_path).resolve(strict=True)
        relative = canonical.relative_to(atlas_root)
    except (OSError, RuntimeError, ValueError) as error:
        raise BridgeError(
            "ATLAS_MESH_PATH_INVALID",
            "The mesh path is not a canonical file beneath the reviewed atlas root.",
            details={"exceptionType": type(error).__name__},
        ) from error
    if relative == Path():
        raise BridgeError(
            "ATLAS_MESH_PATH_INVALID",
            "The atlas root directory cannot be used as a mesh file.",
        )
    try:
        with canonical.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise BridgeError(
                    "ATLAS_MESH_PATH_INVALID",
                    "The resolved atlas mesh path is not a regular file.",
                )
            digest = hashlib.sha256()
            while chunk := stream.read(HASH_CHUNK_BYTES):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        path_after = canonical.stat()
    except BridgeError:
        raise
    except OSError as error:
        raise BridgeError(
            "ATLAS_MESH_UNAVAILABLE",
            "The verified atlas mesh file could not be read for integrity metadata.",
            details={"exceptionType": type(error).__name__},
        ) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    path_identity = (
        path_after.st_dev,
        path_after.st_ino,
        path_after.st_size,
        path_after.st_mtime_ns,
    )
    if before_identity != after_identity or after_identity != path_identity:
        raise BridgeError(
            "ATLAS_MESH_CHANGED",
            "The atlas mesh changed while its descriptor was being computed.",
        )
    return {
        "canonicalPath": str(canonical),
        "atlasRootCanonicalPath": str(atlas_root),
        "pathUnderAtlasRoot": relative.as_posix(),
        "sha256": digest.hexdigest(),
        "byteSize": before.st_size,
        "fileExtension": canonical.suffix.lower(),
        "contentsIncluded": False,
    }


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


def _bounded_integer(
    value: object,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be an integer in [{minimum}, {maximum}].",
            details={"field": field},
        )
    return value


def _finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a finite number.",
            details={"field": field},
        )
    try:
        normalized = float(value)
    except (OverflowError, ValueError) as error:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a finite number.",
            details={"field": field},
        ) from error
    if not math.isfinite(normalized):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field} must be a finite number.",
            details={"field": field},
        )
    return normalized
