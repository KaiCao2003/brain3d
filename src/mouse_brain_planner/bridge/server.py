"""Newline-delimited JSON bridge for a native SwiftUI shell.

Each input line is one protocol-v1 request::

    {"id":"request-id","method":"hello","params":{"protocolVersion":1,"client":"..."}}

Exactly one JSON line is written for every consumed request.  Standard output
is reserved for those responses; operational diagnostics are written only to
standard error.
"""

from __future__ import annotations

import base64
import json
import struct
import sys
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from io import BufferedReader, BufferedWriter
from pathlib import Path
from typing import BinaryIO, Final, Protocol, TextIO, cast

import numpy as np
from numpy.typing import NDArray

from mouse_brain_planner.atlas.brainglobe_adapter import (
    AtlasAdapterError,
    BrainGlobeAtlasRepository,
)
from mouse_brain_planner.bridge import PROTOCOL_VERSION
from mouse_brain_planner.domain.atlas_models import AtlasMetadata, RegionRecord
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.rendering.slice_renderer import SliceOrientation, SliceRenderer
from mouse_brain_planner.version import __version__

SUPPORTED_ATLAS_IDENTIFIER: Final = "allen_mouse_25um"
SUPPORTED_ATLAS_VERSION: Final = "1.2"
MAX_REQUEST_BYTES: Final = 1024 * 1024
MAX_REQUEST_ID_LENGTH: Final = 128
MAX_CLIENT_NAME_LENGTH: Final = 128

JsonObject = dict[str, object]
RequestId = str | int
BridgeHandler = Callable[[Mapping[str, object]], JsonObject]


class LoadedAtlasProtocol(Protocol):
    """The stable loaded-atlas surface consumed by the bridge."""

    metadata: AtlasMetadata
    brainglobe_atlasapi_version: str

    @property
    def reference(self) -> NDArray[np.generic]: ...

    @property
    def annotation(self) -> NDArray[np.generic]: ...

    @property
    def regions(self) -> list[RegionRecord]: ...

    def region_at(self, point: BrainGlobePhysicalPoint) -> RegionRecord | None: ...

    def root_mesh_file(self) -> Path: ...

    def mesh_file_for_region(self, region: RegionRecord | int | str) -> Path: ...


class AtlasRepositoryProtocol(Protocol):
    """Repository operations used by protocol-v1 atlas methods."""

    def is_cached(self, atlas_name: str, package_version: str | None = None) -> bool: ...

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> LoadedAtlasProtocol: ...


class BridgeError(Exception):
    """A deterministic, client-safe protocol failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


class _DuplicateKeyError(ValueError):
    pass


@dataclass(slots=True)
class BridgeContext:
    """Mutable backend state shared by registered bridge handlers.

    Additional project or vasculature handlers can be registered against the
    same context without changing NDJSON framing or the server loop.
    """

    repository_factory: Callable[[], AtlasRepositoryProtocol] = BrainGlobeAtlasRepository
    loaded_atlas: LoadedAtlasProtocol | None = None
    renderer: SliceRenderer | None = None
    shutdown_requested: bool = False
    _repository: AtlasRepositoryProtocol | None = field(default=None, init=False, repr=False)

    def repository(self) -> AtlasRepositoryProtocol:
        """Create the application-owned repository lazily and at most once."""

        if self._repository is None:
            try:
                self._repository = self.repository_factory()
            except Exception as error:
                raise BridgeError(
                    "ATLAS_REPOSITORY_UNAVAILABLE",
                    "The atlas repository could not be initialized.",
                    details={"exceptionType": type(error).__name__},
                ) from error
        return self._repository

    def set_loaded_atlas(self, atlas: LoadedAtlasProtocol) -> None:
        """Validate and publish one atlas and its reusable slice renderer."""

        metadata = atlas.metadata
        if (
            metadata.atlas_key != SUPPORTED_ATLAS_IDENTIFIER
            or metadata.atlas_package_version != SUPPORTED_ATLAS_VERSION
        ):
            raise BridgeError(
                "ATLAS_CONTRACT_VIOLATION",
                "The repository returned an unsupported atlas identity.",
                details={
                    "identifier": metadata.atlas_key,
                    "version": metadata.atlas_package_version,
                },
            )
        reference = np.asarray(atlas.reference)
        annotation = np.asarray(atlas.annotation)
        expected_shape = metadata.shape_voxels
        if reference.shape != expected_shape or annotation.shape != expected_shape:
            raise BridgeError(
                "ATLAS_CONTRACT_VIOLATION",
                "Atlas arrays do not match the reviewed metadata shape.",
                details={
                    "expectedShape": list(expected_shape),
                    "referenceShape": list(reference.shape),
                    "annotationShape": list(annotation.shape),
                },
            )
        try:
            renderer = SliceRenderer(
                reference,
                annotation,
                resolution_um=metadata.resolution_um,
            )
        except (TypeError, ValueError) as error:
            raise BridgeError(
                "ATLAS_CONTRACT_VIOLATION",
                "Atlas arrays cannot be rendered safely.",
                details={"exceptionType": type(error).__name__},
            ) from error
        self.loaded_atlas = atlas
        self.renderer = renderer


class BridgeDispatcher:
    """Extensible method registry with protocol-v1 built-ins."""

    def __init__(self, context: BridgeContext | None = None) -> None:
        self.context = context or BridgeContext()
        self._handlers: dict[str, BridgeHandler] = {}
        self._capabilities: dict[str, bool] = {
            "animalOnly": True,
            "atlas25Micrometre": True,
            "atlasDownload": True,
            "atlasSlicePng": True,
            "projectPersistence": True,
            "subjectVascularImport": True,
            "subjectVascularOverlay": True,
            "subjectVascularRegistration": True,
        }
        self._register_builtins()

    def register(self, method: str, handler: BridgeHandler, *, replace: bool = False) -> None:
        """Register an extension method without changing transport code."""

        if not isinstance(method, str) or not method or len(method) > 64:
            raise ValueError("bridge method name must contain 1 to 64 characters")
        if method in self._handlers and not replace:
            raise ValueError(f"bridge method {method!r} is already registered")
        self._handlers[method] = handler

    def dispatch(self, method: str, params: Mapping[str, object]) -> JsonObject:
        """Invoke one registered handler or return a deterministic method error."""

        handler = self._handlers.get(method)
        if handler is None:
            raise BridgeError(
                "METHOD_NOT_FOUND",
                "The requested bridge method is not available.",
                details={"method": method},
            )
        return handler(params)

    def declare_capability(self, name: str) -> None:
        """Publish one extension capability through the versioned hello result."""

        if not isinstance(name, str) or not name or len(name) > 64:
            raise ValueError("bridge capability name must contain 1 to 64 characters")
        self._capabilities[name] = True

    def _register_builtins(self) -> None:
        self.register("hello", self._hello)
        self.register("state.get", self._state_get)
        self.register("atlas.list", self._atlas_list)
        self.register("atlas.open", self._atlas_open)
        self.register("atlas.slice", self._atlas_slice)
        self.register("shutdown", self._shutdown)

    def _hello(self, params: Mapping[str, object]) -> JsonObject:
        _validate_param_keys(params, required={"protocolVersion", "client"})
        _require_protocol_version(params)
        client = params["client"]
        if not isinstance(client, str) or not client or len(client) > MAX_CLIENT_NAME_LENGTH:
            raise BridgeError(
                "INVALID_PARAMS",
                f"client must contain 1 to {MAX_CLIENT_NAME_LENGTH} characters.",
                details={"field": "client"},
            )
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "service": "mouse-brain-planner",
            "applicationVersion": __version__,
            "capabilities": dict(self._capabilities),
        }

    def _state_get(self, params: Mapping[str, object]) -> JsonObject:
        _validate_param_keys(params, required={"protocolVersion"})
        _require_protocol_version(params)
        atlas = self.context.loaded_atlas
        if atlas is None:
            atlas_state: JsonObject = {
                "identifier": SUPPORTED_ATLAS_IDENTIFIER,
                "version": SUPPORTED_ATLAS_VERSION,
                "loaded": False,
                "status": "notLoaded",
            }
        else:
            atlas_state = {
                "identifier": atlas.metadata.atlas_key,
                "version": atlas.metadata.atlas_package_version,
                "loaded": True,
                "status": "loaded",
            }
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "atlas": atlas_state,
            "subjectVessels": {
                "imported": False,
                "registered": False,
                "sourceName": None,
                "residualMicrometres": None,
                "lateralityConfirmed": False,
            },
            "populationDensity": {
                "available": False,
                "visible": False,
                "opacity": 0.65,
                "status": "notLoaded",
            },
        }

    def _atlas_list(self, params: Mapping[str, object]) -> JsonObject:
        _validate_param_keys(params, required={"protocolVersion"})
        _require_protocol_version(params)
        try:
            cached = self.context.repository().is_cached(
                SUPPORTED_ATLAS_IDENTIFIER,
                SUPPORTED_ATLAS_VERSION,
            )
        except BridgeError:
            raise
        except (AtlasAdapterError, OSError, ValueError) as error:
            raise BridgeError(
                "ATLAS_REPOSITORY_UNAVAILABLE",
                "The local atlas cache could not be inspected.",
                details={"exceptionType": type(error).__name__},
            ) from error
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "atlases": [
                {
                    "identifier": SUPPORTED_ATLAS_IDENTIFIER,
                    "version": SUPPORTED_ATLAS_VERSION,
                    "resolutionMicrometres": [25.0, 25.0, 25.0],
                    "cached": cached,
                    "status": "cached" if cached else "notCached",
                    "downloadSupported": True,
                }
            ],
        }

    def _atlas_open(self, params: Mapping[str, object]) -> JsonObject:
        _validate_param_keys(
            params,
            required={"protocolVersion", "identifier", "version"},
            optional={"allowDownload"},
        )
        _require_protocol_version(params)
        identifier = params["identifier"]
        version = params["version"]
        if identifier != SUPPORTED_ATLAS_IDENTIFIER or version != SUPPORTED_ATLAS_VERSION:
            raise BridgeError(
                "UNSUPPORTED_ATLAS",
                "Only the reviewed 25 micrometre Allen mouse atlas is supported.",
                details={
                    "requestedIdentifier": _safe_scalar(identifier),
                    "requestedVersion": _safe_scalar(version),
                    "supportedIdentifier": SUPPORTED_ATLAS_IDENTIFIER,
                    "supportedVersion": SUPPORTED_ATLAS_VERSION,
                },
            )
        allow_download = params.get("allowDownload", False)
        if not isinstance(allow_download, bool):
            raise BridgeError(
                "INVALID_PARAMS",
                "allowDownload must be a boolean.",
                details={"field": "allowDownload"},
            )

        existing = self.context.loaded_atlas
        if existing is not None:
            return _atlas_open_result(existing)

        try:
            loaded = self.context.repository().open(
                SUPPORTED_ATLAS_IDENTIFIER,
                package_version=SUPPORTED_ATLAS_VERSION,
                allow_download=allow_download,
            )
        except FileNotFoundError as error:
            raise BridgeError(
                "ATLAS_NOT_CACHED",
                "The reviewed atlas is not cached; retry with allowDownload true.",
                details={
                    "identifier": SUPPORTED_ATLAS_IDENTIFIER,
                    "version": SUPPORTED_ATLAS_VERSION,
                },
            ) from error
        except BridgeError:
            raise
        except (AtlasAdapterError, OSError, ValueError) as error:
            raise BridgeError(
                "ATLAS_OPEN_FAILED",
                "The reviewed atlas could not be opened and validated.",
                details={"exceptionType": type(error).__name__},
            ) from error
        self.context.set_loaded_atlas(loaded)
        return _atlas_open_result(loaded)

    def _atlas_slice(self, params: Mapping[str, object]) -> JsonObject:
        _validate_param_keys(
            params,
            required={"protocolVersion", "orientation", "index"},
        )
        _require_protocol_version(params)
        atlas = self.context.loaded_atlas
        renderer = self.context.renderer
        if atlas is None or renderer is None:
            raise BridgeError(
                "ATLAS_NOT_OPEN",
                "Open the reviewed atlas before requesting slices.",
            )
        raw_orientation = params["orientation"]
        allowed_orientations = tuple(item.value for item in SliceOrientation)
        if not isinstance(raw_orientation, str) or raw_orientation not in allowed_orientations:
            raise BridgeError(
                "INVALID_PARAMS",
                "orientation must be coronal, sagittal, or horizontal.",
                details={"field": "orientation", "allowed": list(allowed_orientations)},
            )
        raw_index = params["index"]
        if isinstance(raw_index, bool) or not isinstance(raw_index, int) or raw_index < 0:
            raise BridgeError(
                "INVALID_PARAMS",
                "index must be a nonnegative integer.",
                details={"field": "index"},
            )
        orientation = SliceOrientation(raw_orientation)
        try:
            frame = renderer.render_slice(orientation, raw_index)
            png = encode_rgb_png(frame.rgb)
            height, width = frame.rgb.shape[:2]
            center_um = renderer.slice_center_mm(orientation, raw_index) * 1000.0
        except IndexError as error:
            raise BridgeError(
                "SLICE_OUT_OF_RANGE",
                "The requested slice index is outside the atlas volume.",
                details={
                    "orientation": orientation.value,
                    "index": raw_index,
                    "sliceCount": renderer.slice_count(orientation),
                },
            ) from error
        except (TypeError, ValueError, zlib.error) as error:
            raise BridgeError(
                "SLICE_RENDER_FAILED",
                "The requested atlas slice could not be rendered safely.",
                details={"exceptionType": type(error).__name__},
            ) from error
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "mimeType": "image/png",
            "pngBase64": base64.b64encode(png).decode("ascii"),
            "width": int(width),
            "height": int(height),
            "orientation": orientation.value,
            "index": raw_index,
            "fixedAxis": orientation.fixed_axis_name,
            "sliceCenterMicrometres": center_um,
            "atlas": atlas_provenance(atlas),
        }

    def _shutdown(self, params: Mapping[str, object]) -> JsonObject:
        _validate_param_keys(params, required={"protocolVersion"})
        _require_protocol_version(params)
        self.context.shutdown_requested = True
        return {"protocolVersion": PROTOCOL_VERSION, "status": "shuttingDown"}


@dataclass(slots=True)
class BridgeServer:
    """Fail-closed NDJSON framing around an extensible dispatcher."""

    dispatcher: BridgeDispatcher = field(default_factory=BridgeDispatcher)
    diagnostics: TextIO = sys.stderr

    def run_stream(self, input_stream: BinaryIO, output_stream: BinaryIO) -> int:
        """Process requests until EOF or a successful ``shutdown`` request."""

        while not self.dispatcher.context.shutdown_requested:
            raw_line = input_stream.readline(MAX_REQUEST_BYTES + 1)
            if not raw_line:
                break
            if len(raw_line) > MAX_REQUEST_BYTES:
                if not raw_line.endswith(b"\n"):
                    self._drain_oversized_line(input_stream)
                self._write_error(
                    output_stream,
                    None,
                    BridgeError(
                        "REQUEST_TOO_LARGE",
                        f"A request line may contain at most {MAX_REQUEST_BYTES} bytes.",
                        details={"maxBytes": MAX_REQUEST_BYTES},
                    ),
                )
                continue
            request_id: RequestId | None = None
            try:
                request = _decode_request(raw_line)
                request_id = request.request_id
                result = self.dispatcher.dispatch(request.method, request.params)
                response: JsonObject = {"id": request_id, "result": result}
            except BridgeError as error:
                self._diagnose(error)
                self._write_error(output_stream, request_id, error)
                continue
            except Exception as error:  # final containment boundary for extension handlers
                self._diagnose_unexpected(error)
                self._write_error(
                    output_stream,
                    request_id,
                    BridgeError(
                        "INTERNAL_ERROR",
                        "The bridge rejected the request because of an internal error.",
                        details={"exceptionType": type(error).__name__},
                    ),
                )
                continue
            self._write_response(output_stream, response)
        return 0

    @staticmethod
    def _drain_oversized_line(input_stream: BinaryIO) -> None:
        while True:
            remainder = input_stream.readline(MAX_REQUEST_BYTES + 1)
            if not remainder or remainder.endswith(b"\n"):
                return

    def _write_error(
        self,
        output_stream: BinaryIO,
        request_id: RequestId | None,
        error: BridgeError,
    ) -> None:
        self._write_response(
            output_stream,
            {
                "id": request_id,
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                },
            },
        )

    @staticmethod
    def _write_response(output_stream: BinaryIO, response: Mapping[str, object]) -> None:
        try:
            payload = json.dumps(
                response,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            payload = json.dumps(
                {
                    "id": response.get("id"),
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "The bridge produced a non-JSON response.",
                        "details": {"exceptionType": type(error).__name__},
                    },
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        output_stream.write(payload + b"\n")
        output_stream.flush()

    def _diagnose(self, error: BridgeError) -> None:
        print(f"bridge request rejected: {error.code}: {error.message}", file=self.diagnostics)
        self.diagnostics.flush()

    def _diagnose_unexpected(self, error: Exception) -> None:
        print(
            f"bridge handler failed: {type(error).__name__}: {error}",
            file=self.diagnostics,
        )
        self.diagnostics.flush()


@dataclass(frozen=True, slots=True)
class _Request:
    request_id: RequestId
    method: str
    params: Mapping[str, object]


def _decode_request(raw_line: bytes) -> _Request:
    try:
        text = raw_line.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BridgeError("PARSE_ERROR", "The request line must be valid UTF-8 JSON.") from error
    if not text.strip():
        raise BridgeError("PARSE_ERROR", "The request line must not be blank.")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite_constant,
        )
    except (_DuplicateKeyError, json.JSONDecodeError, ValueError) as error:
        raise BridgeError(
            "PARSE_ERROR",
            "The request line must contain one strict JSON object.",
            details={"exceptionType": type(error).__name__},
        ) from error
    if not isinstance(value, dict):
        raise BridgeError("INVALID_REQUEST", "The request must be a JSON object.")
    request = cast(dict[object, object], value)
    keys = set(request)
    required = {"id", "method", "params"}
    if keys != required:
        raise BridgeError(
            "INVALID_REQUEST",
            "The request must contain exactly id, method, and params.",
            details={
                "missing": sorted(required - keys),
                "unexpected": sorted(str(key) for key in keys - required),
            },
        )
    request_id = request["id"]
    if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
        raise BridgeError(
            "INVALID_REQUEST",
            "id must be a nonempty string or a nonnegative integer.",
            details={"field": "id"},
        )
    if isinstance(request_id, str):
        if not request_id or len(request_id) > MAX_REQUEST_ID_LENGTH:
            raise BridgeError(
                "INVALID_REQUEST",
                f"string id must contain 1 to {MAX_REQUEST_ID_LENGTH} characters.",
                details={"field": "id"},
            )
    elif request_id < 0 or request_id > (1 << 53) - 1:
        raise BridgeError(
            "INVALID_REQUEST",
            "integer id must be in the JSON-safe range [0, 2^53 - 1].",
            details={"field": "id"},
        )
    method = request["method"]
    if not isinstance(method, str) or not method or len(method) > 64:
        raise BridgeError(
            "INVALID_REQUEST",
            "method must contain 1 to 64 characters.",
            details={"field": "method"},
        )
    params = request["params"]
    if not isinstance(params, dict):
        raise BridgeError(
            "INVALID_REQUEST",
            "params must be a JSON object.",
            details={"field": "params"},
        )
    return _Request(request_id=request_id, method=method, params=cast(JsonObject, params))


def _unique_object(pairs: list[tuple[str, object]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON number is not permitted: {value}")


def _validate_param_keys(
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


def _require_protocol_version(params: Mapping[str, object]) -> None:
    value = params["protocolVersion"]
    if isinstance(value, bool) or not isinstance(value, int) or value != PROTOCOL_VERSION:
        raise BridgeError(
            "PROTOCOL_VERSION_MISMATCH",
            f"protocolVersion must equal {PROTOCOL_VERSION}.",
            details={"supported": PROTOCOL_VERSION, "received": _safe_scalar(value)},
        )


def _safe_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return type(value).__name__


def _atlas_open_result(atlas: LoadedAtlasProtocol) -> JsonObject:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "status": "loaded",
        "atlas": atlas_provenance(atlas),
    }


def atlas_provenance(atlas: LoadedAtlasProtocol) -> JsonObject:
    """Return the canonical protocol-v1 identity for one reviewed atlas."""

    metadata = atlas.metadata
    return {
        "identifier": metadata.atlas_key,
        "version": metadata.atlas_package_version,
        "metadataSha256": metadata.metadata_sha256,
        "resolutionMicrometres": list(metadata.resolution_um),
        "shapeVoxels": list(metadata.shape_voxels),
        "orientation": metadata.standardized_orientation,
        "frameworkName": metadata.framework_name,
        "sourceAnnotation": metadata.source_annotation,
        "citation": metadata.citation,
        "brainGlobeAtlasApiVersion": atlas.brainglobe_atlasapi_version,
    }


def encode_rgb_png(rgb: NDArray[np.uint8]) -> bytes:
    """Encode a contiguous 8-bit RGB image as a deterministic PNG."""

    values = np.asarray(rgb)
    if values.dtype != np.dtype(np.uint8) or values.ndim != 3 or values.shape[2] != 3:
        raise TypeError("PNG input must be an 8-bit RGB array")
    height, width, _ = values.shape
    if height <= 0 or width <= 0 or height > 100_000 or width > 100_000:
        raise ValueError("PNG dimensions must be in [1, 100000]")
    contiguous = np.ascontiguousarray(values)
    scanlines = b"".join(b"\x00" + contiguous[row].tobytes() for row in range(height))
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        signature
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, level=6))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def main() -> int:
    """Run the protocol-v1 server on standard streams."""

    # Imported here to keep the framing module acyclic: planning handlers use
    # the public dispatcher and error contracts defined above.
    from mouse_brain_planner.bridge.atlas_interaction import (
        register_atlas_interaction_handlers,
    )
    from mouse_brain_planner.bridge.planning import register_planning_handlers

    input_stream = cast(BufferedReader, sys.stdin.buffer)
    output_stream = cast(BufferedWriter, sys.stdout.buffer)
    dispatcher = BridgeDispatcher()
    register_atlas_interaction_handlers(dispatcher)
    register_planning_handlers(dispatcher)
    return BridgeServer(dispatcher=dispatcher, diagnostics=sys.stderr).run_stream(
        input_stream,
        output_stream,
    )


if __name__ == "__main__":
    raise SystemExit(main())
