"""Protocol-v1 contracts for the native-shell stdio bridge."""

from __future__ import annotations

import base64
import json
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from typing import Any, NoReturn

import numpy as np
from PIL import Image
from tests.fixtures.atlas_factory import make_allen_metadata_test_double

from mouse_brain_planner.bridge.server import (
    MAX_REQUEST_BYTES,
    BridgeContext,
    BridgeDispatcher,
    BridgeServer,
    encode_rgb_png,
)
from mouse_brain_planner.domain.atlas_models import AtlasMetadata


@dataclass(slots=True)
class _FakeLoadedAtlas:
    metadata: AtlasMetadata = field(default_factory=lambda: make_allen_metadata_test_double(25))
    brainglobe_atlasapi_version: str = "2.3.1"
    _reference: np.ndarray[tuple[int, int, int], np.dtype[np.uint16]] = field(
        init=False, repr=False
    )
    _annotation: np.ndarray[tuple[int, int, int], np.dtype[np.uint32]] = field(
        init=False, repr=False
    )

    def __post_init__(self) -> None:
        shape = self.metadata.shape_voxels
        reference_row = np.arange(shape[2], dtype=np.uint16)[None, None, :]
        annotation_row = np.zeros((1, 1, shape[2]), dtype=np.uint32)
        self._reference = np.broadcast_to(reference_row, shape)
        self._annotation = np.broadcast_to(annotation_row, shape)

    @property
    def reference(self) -> np.ndarray[tuple[int, int, int], np.dtype[np.uint16]]:
        return self._reference

    @property
    def annotation(self) -> np.ndarray[tuple[int, int, int], np.dtype[np.uint32]]:
        return self._annotation


@dataclass(slots=True)
class _FakeRepository:
    loaded: _FakeLoadedAtlas = field(default_factory=_FakeLoadedAtlas)
    cached: bool = True
    open_calls: list[tuple[str, str | None, bool]] = field(default_factory=list)

    def is_cached(self, atlas_name: str, package_version: str | None = None) -> bool:
        assert atlas_name == "allen_mouse_25um"
        assert package_version == "1.2"
        return self.cached

    def open(
        self,
        atlas_name: str,
        *,
        package_version: str | None = None,
        allow_download: bool = True,
        progress: object = None,
        cancel: object = None,
    ) -> _FakeLoadedAtlas:
        del progress, cancel
        self.open_calls.append((atlas_name, package_version, allow_download))
        if not self.cached and not allow_download:
            raise FileNotFoundError("test-only cache miss")
        return self.loaded


def _request(request_id: str | int, method: str, params: dict[str, object]) -> bytes:
    return (json.dumps({"id": request_id, "method": method, "params": params}) + "\n").encode()


def _run(
    payload: bytes,
    *,
    repository: _FakeRepository | None = None,
    configure: Callable[[BridgeDispatcher], None] | None = None,
) -> tuple[list[dict[str, Any]], str, _FakeRepository]:
    selected_repository = repository or _FakeRepository()
    context = BridgeContext(repository_factory=lambda: selected_repository)
    dispatcher = BridgeDispatcher(context)
    if configure is not None:
        configure(dispatcher)
    diagnostics = StringIO()
    output = BytesIO()
    exit_code = BridgeServer(dispatcher, diagnostics).run_stream(BytesIO(payload), output)
    assert exit_code == 0
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    return responses, diagnostics.getvalue(), selected_repository


def test_hello_state_and_clean_shutdown_have_one_response_per_request() -> None:
    payload = b"".join(
        (
            _request(
                "hello-1",
                "hello",
                {"protocolVersion": 1, "client": "Brain3DSwiftUI"},
            ),
            _request("state-1", "state.get", {"protocolVersion": 1}),
            _request("shutdown-1", "shutdown", {"protocolVersion": 1}),
            _request("ignored", "state.get", {"protocolVersion": 1}),
        )
    )

    responses, diagnostics, _ = _run(payload)

    assert [response["id"] for response in responses] == ["hello-1", "state-1", "shutdown-1"]
    hello = responses[0]["result"]
    assert hello["protocolVersion"] == 1
    assert hello["service"] == "mouse-brain-planner"
    assert hello["capabilities"] == {
        "animalOnly": True,
        "atlas25Micrometre": True,
        "atlasDownload": True,
        "atlasSlicePng": True,
        "projectPersistence": True,
        "subjectVascularImport": True,
        "subjectVascularOverlay": True,
        "subjectVascularRegistration": True,
    }
    state = responses[1]["result"]
    assert state["atlas"] == {
        "identifier": "allen_mouse_25um",
        "loaded": False,
        "status": "notLoaded",
        "version": "1.2",
    }
    assert state["subjectVessels"]["registered"] is False
    assert state["populationDensity"]["visible"] is False
    assert responses[2]["result"]["status"] == "shuttingDown"
    assert diagnostics == ""


def test_bad_lines_are_isolated_and_strict_json_is_enforced() -> None:
    payload = b"".join(
        (
            b"not-json\n",
            b'{"id":"dup","id":"again","method":"state.get","params":{}}\n',
            b'{"id":"nan","method":"state.get","params":{"protocolVersion":NaN}}\n',
            b"[]\n",
            _request("extra", "state.get", {"protocolVersion": 1})[:-2] + b',"unexpected":true}\n',
            _request("valid", "state.get", {"protocolVersion": 1}),
        )
    )

    responses, diagnostics, _ = _run(payload)

    assert len(responses) == 6
    assert [response["error"]["code"] for response in responses[:3]] == [
        "PARSE_ERROR",
        "PARSE_ERROR",
        "PARSE_ERROR",
    ]
    assert responses[3]["error"]["code"] == "INVALID_REQUEST"
    assert responses[4]["error"]["code"] in {"PARSE_ERROR", "INVALID_REQUEST"}
    assert responses[5]["id"] == "valid"
    assert "result" in responses[5]
    assert diagnostics.count("bridge request rejected:") == 5


def test_wrong_protocol_and_unknown_method_echo_valid_request_ids() -> None:
    payload = _request("version", "state.get", {"protocolVersion": 2}) + _request(
        17, "future.method", {"protocolVersion": 1}
    )

    responses, _, _ = _run(payload)

    assert responses[0]["id"] == "version"
    assert responses[0]["error"]["code"] == "PROTOCOL_VERSION_MISMATCH"
    assert responses[1]["id"] == 17
    assert responses[1]["error"] == {
        "code": "METHOD_NOT_FOUND",
        "details": {"method": "future.method"},
        "message": "The requested bridge method is not available.",
    }


def test_atlas_list_is_local_only_and_exposes_only_reviewed_package() -> None:
    repository = _FakeRepository(cached=False)

    responses, diagnostics, _ = _run(
        _request("list", "atlas.list", {"protocolVersion": 1}),
        repository=repository,
    )

    assert diagnostics == ""
    assert responses[0]["result"]["atlases"] == [
        {
            "cached": False,
            "downloadSupported": True,
            "identifier": "allen_mouse_25um",
            "resolutionMicrometres": [25.0, 25.0, 25.0],
            "status": "notCached",
            "version": "1.2",
        }
    ]
    assert repository.open_calls == []


def test_atlas_open_rejects_traversal_alias_and_unreviewed_resolution() -> None:
    requests = (
        _request(
            "traversal",
            "atlas.open",
            {
                "protocolVersion": 1,
                "identifier": "../allen_mouse_25um",
                "version": "1.2",
            },
        )
        + _request(
            "10um",
            "atlas.open",
            {
                "protocolVersion": 1,
                "identifier": "allen_mouse_10um",
                "version": "1.2",
            },
        )
        + _request(
            "version-traversal",
            "atlas.open",
            {
                "protocolVersion": 1,
                "identifier": "allen_mouse_25um",
                "version": "1.2/../../etc",
            },
        )
    )

    responses, _, repository = _run(requests)

    assert [response["error"]["code"] for response in responses] == [
        "UNSUPPORTED_ATLAS",
        "UNSUPPORTED_ATLAS",
        "UNSUPPORTED_ATLAS",
    ]
    assert repository.open_calls == []


def test_atlas_open_is_offline_by_default_and_download_requires_explicit_true() -> None:
    repository = _FakeRepository(cached=False)
    params = {
        "protocolVersion": 1,
        "identifier": "allen_mouse_25um",
        "version": "1.2",
    }
    payload = _request("offline", "atlas.open", params) + _request(
        "download",
        "atlas.open",
        {**params, "allowDownload": True},
    )

    responses, _, _ = _run(payload, repository=repository)

    assert responses[0]["error"]["code"] == "ATLAS_NOT_CACHED"
    assert responses[1]["result"]["status"] == "loaded"
    assert repository.open_calls == [
        ("allen_mouse_25um", "1.2", False),
        ("allen_mouse_25um", "1.2", True),
    ]


def test_repeated_slices_are_valid_deterministic_pngs_with_provenance() -> None:
    open_params = {
        "protocolVersion": 1,
        "identifier": "allen_mouse_25um",
        "version": "1.2",
    }
    slice_params = {"protocolVersion": 1, "orientation": "coronal", "index": 4}
    payload = b"".join(
        (
            _request("open", "atlas.open", open_params),
            _request("slice-1", "atlas.slice", slice_params),
            _request("out-of-range", "atlas.slice", {**slice_params, "index": 528}),
            _request("slice-2", "atlas.slice", slice_params),
        )
    )

    responses, _, repository = _run(payload)

    assert repository.open_calls == [("allen_mouse_25um", "1.2", False)]
    first = responses[1]["result"]
    second = responses[3]["result"]
    assert first["pngBase64"] == second["pngBase64"]
    png = base64.b64decode(first["pngBase64"], validate=True)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (456, 320)
    assert (first["width"], first["height"]) == (456, 320)
    assert first["orientation"] == "coronal"
    assert first["fixedAxis"] == "AP"
    assert first["rowAxis"] == "DV"
    assert first["columnAxis"] == "ML"
    assert first["sliceCount"] == 528
    assert first["sliceCenterMicrometres"] == 112.5
    assert first["atlas"]["identifier"] == "allen_mouse_25um"
    assert first["atlas"]["version"] == "1.2"
    assert first["atlas"]["resolutionMicrometres"] == [25.0, 25.0, 25.0]
    assert responses[2]["error"]["code"] == "SLICE_OUT_OF_RANGE"
    assert responses[2]["error"]["details"]["sliceCount"] == 528


def test_navigation_png_compression_is_full_resolution_and_pixel_lossless() -> None:
    expected = np.arange(7 * 11 * 3, dtype=np.uint8).reshape(7, 11, 3)

    fast = encode_rgb_png(expected, compression_level=1)
    archival = encode_rgb_png(expected, compression_level=6)

    assert fast.startswith(b"\x89PNG\r\n\x1a\n")
    assert archival.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(fast)) as decoded:
        assert decoded.size == (11, 7)
        np.testing.assert_array_equal(np.asarray(decoded.convert("RGB")), expected)
    with Image.open(BytesIO(archival)) as decoded:
        np.testing.assert_array_equal(np.asarray(decoded.convert("RGB")), expected)


def test_slice_requires_an_open_atlas_and_exact_orientation_and_index_types() -> None:
    payload = b"".join(
        (
            _request(
                "not-open",
                "atlas.slice",
                {"protocolVersion": 1, "orientation": "coronal", "index": 0},
            ),
            _request(
                "open",
                "atlas.open",
                {
                    "protocolVersion": 1,
                    "identifier": "allen_mouse_25um",
                    "version": "1.2",
                },
            ),
            _request(
                "case",
                "atlas.slice",
                {"protocolVersion": 1, "orientation": "Coronal", "index": 0},
            ),
            _request(
                "boolean",
                "atlas.slice",
                {"protocolVersion": 1, "orientation": "coronal", "index": True},
            ),
        )
    )

    responses, _, _ = _run(payload)

    assert responses[0]["error"]["code"] == "ATLAS_NOT_OPEN"
    assert responses[2]["error"]["code"] == "INVALID_PARAMS"
    assert responses[3]["error"]["code"] == "INVALID_PARAMS"


def test_extension_handler_failure_is_contained_and_next_request_survives() -> None:
    def configure(dispatcher: BridgeDispatcher) -> None:
        def fail(_params: object) -> NoReturn:
            raise RuntimeError("test-only extension failure")

        dispatcher.register("test.fail", fail)

    payload = _request("failure", "test.fail", {}) + _request(
        "after", "state.get", {"protocolVersion": 1}
    )

    responses, diagnostics, _ = _run(payload, configure=configure)

    assert responses[0]["error"]["code"] == "INTERNAL_ERROR"
    assert responses[0]["error"]["details"] == {"exceptionType": "RuntimeError"}
    assert responses[1]["id"] == "after"
    assert "result" in responses[1]
    assert "test-only extension failure" in diagnostics


def test_oversized_request_is_drained_and_following_request_survives() -> None:
    oversized = b"x" * (MAX_REQUEST_BYTES + 10) + b"\n"
    payload = oversized + _request("after", "state.get", {"protocolVersion": 1})

    responses, _, _ = _run(payload)

    assert responses[0]["id"] is None
    assert responses[0]["error"]["code"] == "REQUEST_TOO_LARGE"
    assert responses[1]["id"] == "after"
    assert "result" in responses[1]
