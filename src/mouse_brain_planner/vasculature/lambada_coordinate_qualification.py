"""Fail-closed coordinate qualification for the pinned LAMBADA P60_606 graph.

This module does not make the reference graph subject-specific or suitable for
surgical navigation.  It answers a narrower, reproducible question: whether
the exact pinned graph contains enough internal annotation and hemisphere
evidence to support the currently proposed ClearMap-to-BrainGlobe axis signs.

The acceptance criteria are constants, not command-line knobs.  A report is an
attestation only when every check passes; otherwise its status is ``rejected``.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import pickle
import struct
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Final, Literal, cast

import numpy as np
import tifffile
from numpy.typing import NDArray

from mouse_brain_planner.vasculature.lambada_major_vessels import (
    ANNOTATIONS_RAW_OFFSET,
    ASSET_SHA256,
    ATLAS_SHAPE_ASR,
    ATLAS_SHAPE_CLEARMAP,
    ATLAS_VOXEL_SIZE_UM,
    COORDINATES_ATLAS_RAW_OFFSET,
    EDGE_GEOMETRY_INDICES_PAYLOAD_OFFSET,
    EDGE_RADII_ATLAS_RAW_OFFSET,
    EXPECTED_CANDIDATE_EDGE_COUNT,
    EXPECTED_QUALIFYING_IN_BOUNDS_POINT_COUNT,
    EXPECTED_RUN_COUNT,
    EXPECTED_RUN_POINT_COUNT,
    EXPECTED_SEGMENT_COUNT,
    EXPECTED_SOURCE_EDGES_WITH_RUNS,
    MINIMUM_RADIUS_ATLAS_VOXEL,
    RADII_ATLAS_RAW_OFFSET,
    SOURCE_EDGE_COUNT,
    SOURCE_FILENAME,
    SOURCE_GEOMETRY_POINT_COUNT,
    SOURCE_SHA256,
    SOURCE_SIZE_BYTES,
    SOURCE_VERTEX_COUNT,
    load_lambada_major_vessels,
)

QUALIFICATION_SCHEMA_VERSION: Final = 1
QUALIFICATION_ALGORITHM_VERSION: Final = "lambada-p60-606-coordinate-signs-v1"
GT_FORMAT_DOCUMENTATION_URL: Final = (
    "https://graph-tool.skewed.de/static/docs/stable/gt_format.html"
)
CLEARMAP_REPOSITORY_URL: Final = "https://github.com/ClearAnatomics/ClearMap"
CLEARMAP_EVIDENCE_COMMIT: Final = "71444a5c7456901f15e8d0ceb06fab72b74161df"
CLEARMAP_ANNOTATION_SOURCE_URL: Final = (
    "https://github.com/ClearAnatomics/ClearMap/blob/"
    f"{CLEARMAP_EVIDENCE_COMMIT}/ClearMap/processors/tube_map.py#L660-L682"
)
CLEARMAP_HEMISPHERE_SEMANTICS_URL: Final = (
    "https://github.com/ClearAnatomics/ClearMap/blob/"
    f"{CLEARMAP_EVIDENCE_COMMIT}/ClearMap/Analysis/Statistics/"
    "data_frame_operations.py#L53-L59"
)
CLEARMAP_GRAPH_STORAGE_URL: Final = (
    "https://github.com/ClearAnatomics/ClearMap/blob/"
    f"{CLEARMAP_EVIDENCE_COMMIT}/ClearMap/Analysis/Graphs/GraphGt.py#L869-L910"
)
ZENODO_DATASET_RECORD_URL: Final = "https://zenodo.org/records/18876865"

ALLEN_ATLAS_DIRECTORY_NAME: Final = "allen_mouse_25um_v1.2"
ALLEN_ANNOTATION_FILENAME: Final = "annotation.tiff"
ALLEN_STRUCTURES_FILENAME: Final = "structures.json"
ALLEN_METADATA_FILENAME: Final = "metadata.json"
ALLEN_ANNOTATION_SIZE_BYTES: Final = 308_270_826
ALLEN_STRUCTURES_SIZE_BYTES: Final = 138_106
ALLEN_METADATA_SIZE_BYTES: Final = 423
ALLEN_ANNOTATION_SHA256: Final = "52775c6086ae6aa7d9df2ad2c9e5ab9ce36effa09f5355c7c45efeada6647e06"
ALLEN_STRUCTURES_SHA256: Final = "7157e6130b354f6bebc21aa79f882274cbbe253ac916d97123805af3b4ff8abd"
ALLEN_METADATA_SHA256: Final = "119132150055826484fa75a4dc17c476d02251c0db8b4d0b7b28f6b8c4b8ae60"

HEMISPHERE_PROPERTY_NAME: Final = "edge_geometry_hemisphere"
MISSING_HEMISPHERE_REASON_CODE: Final = "SOURCE_HEMISPHERE_PROPERTY_MISSING"
HEMISPHERE_COVERAGE_REASON_CODE: Final = "SOURCE_SPECIMEN_COVERAGE_IS_HEMISPHERE"
CLEARMAP_LEFT_HEMISPHERE_VALUE: Final = 0
CLEARMAP_RIGHT_HEMISPHERE_VALUE: Final = 255
ML_MIDLINE_VOXEL: Final = ATLAS_SHAPE_ASR[2] // 2

# Predeclared, non-configurable acceptance criteria.  Fractions keep both the
# comparisons and the canonical JSON independent of binary floating point.
MIN_ANNOTATION_EVALUABLE_POINTS: Final = 50_000
MIN_ANNOTATION_EVALUABLE_FRACTION: Final = Fraction(7, 10)
MIN_ANNOTATION_ANCESTOR_AGREEMENT: Final = Fraction(4, 5)
MIN_EXPECTED_GLOBAL_LEAD: Final = Fraction(1, 100)
MIN_AP_DV_WINNER_MARGIN: Final = Fraction(1, 5)
MIN_HEMISPHERE_DISCRIMINATING_FRACTION: Final = Fraction(19, 20)
MIN_HEMISPHERE_AGREEMENT: Final = Fraction(99, 100)
MIN_HEMISPHERE_WINNER_MARGIN: Final = Fraction(49, 50)
MAX_HEMISPHERE_PICKLE_BYTES: Final = 1_000_000_000

_GT_MAGIC: Final = b"\xe2\x9b\xbe gt"
_GT_VERSION: Final = 1
_GT_PROPERTY_KINDS: Final = {0: "graph", 1: "vertex", 2: "edge"}
_GT_FIXED_VALUE_SIZES: Final = {0: 1, 1: 2, 2: 4, 3: 8, 4: 8, 5: 16}
_GT_VECTOR_VALUE_SIZES: Final = {7: 1, 8: 2, 9: 4, 10: 8, 11: 8, 12: 16}


class LambadaCoordinateQualificationError(ValueError):
    """Raised when qualification input violates a pinned trust boundary."""


@dataclass(frozen=True, slots=True)
class GTPropertyRecord:
    """One graph-tool property record located without decoding its value."""

    kind: Literal["graph", "vertex", "edge"]
    name: str
    type_index: int
    item_count: int
    record_offset: int
    values_offset: int
    values_end_offset: int
    object_payload_offset: int | None = None
    object_payload_size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class GTFileInventory:
    """Validated graph-tool header, topology counts, and property inventory."""

    byte_order: Literal["little", "big"]
    directed: bool
    vertex_count: int
    edge_count: int
    properties: tuple[GTPropertyRecord, ...]


@dataclass(frozen=True, slots=True)
class RetainedSourceSelection:
    """Exact retained derivative plus its original graph-geometry indices."""

    points_clearmap_voxel_f64: NDArray[np.float64]
    source_geometry_indices_i64: NDArray[np.int64]
    radii_um_f32: NDArray[np.float32]
    source_annotation_ids_i32: NDArray[np.int32]
    run_offsets_i64: NDArray[np.int64]
    source_edge_indices_i32: NDArray[np.int32]
    qualifying_in_bounds_points: int
    source_edges_with_runs: int


@dataclass(frozen=True, slots=True)
class AtlasEvidence:
    """Pinned atlas arrays and hierarchy used by the orientation scorer."""

    annotation: NDArray[np.uint32]
    structure_paths: Mapping[int, frozenset[int]]
    identity_report: Mapping[str, object]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_exact(stream: io.BufferedReader, size: int, *, field: str) -> bytes:
    if size < 0:
        raise LambadaCoordinateQualificationError(f"negative byte count for {field}")
    value = stream.read(size)
    if len(value) != size:
        raise LambadaCoordinateQualificationError(f"truncated graph-tool {field}")
    return value


def _unpack_unsigned(raw: bytes, *, byte_order: str) -> int:
    prefix = "<" if byte_order == "little" else ">"
    format_code = {1: "B", 2: "H", 4: "I", 8: "Q"}.get(len(raw))
    if format_code is None:
        raise AssertionError("unsupported integer width")
    return int(struct.unpack(f"{prefix}{format_code}", raw)[0])


def _read_u64(stream: io.BufferedReader, *, byte_order: str, field: str) -> int:
    return _unpack_unsigned(_read_exact(stream, 8, field=field), byte_order=byte_order)


def _seek_forward_checked(
    stream: io.BufferedReader,
    byte_count: int,
    *,
    file_size: int,
    field: str,
) -> None:
    if byte_count < 0 or byte_count > file_size - stream.tell():
        raise LambadaCoordinateQualificationError(f"graph-tool {field} exceeds the file")
    stream.seek(byte_count, os.SEEK_CUR)


def _read_gt_string(
    stream: io.BufferedReader,
    *,
    byte_order: str,
    file_size: int,
    field: str,
    maximum_size: int = 1024 * 1024,
) -> str:
    size = _read_u64(stream, byte_order=byte_order, field=f"{field} length")
    if size > maximum_size:
        raise LambadaCoordinateQualificationError(f"graph-tool {field} is unreasonably large")
    raw = _read_exact(stream, size, field=field)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise LambadaCoordinateQualificationError(
            f"graph-tool {field} is not valid UTF-8"
        ) from error


def _skip_length_prefixed_items(
    stream: io.BufferedReader,
    *,
    count: int,
    element_size: int,
    byte_order: str,
    file_size: int,
    field: str,
) -> tuple[int | None, int | None]:
    first_payload_offset: int | None = None
    first_payload_size: int | None = None
    for item_index in range(count):
        length = _read_u64(
            stream,
            byte_order=byte_order,
            field=f"{field}[{item_index}] length",
        )
        if length > file_size // max(element_size, 1):
            raise LambadaCoordinateQualificationError(
                f"graph-tool {field}[{item_index}] length overflows"
            )
        payload_size = length * element_size
        if item_index == 0:
            first_payload_offset = stream.tell()
            first_payload_size = payload_size
        _seek_forward_checked(
            stream,
            payload_size,
            file_size=file_size,
            field=f"{field}[{item_index}] payload",
        )
    return first_payload_offset, first_payload_size


def scan_gt_file(path: str | Path) -> GTFileInventory:
    """Scan graph-tool metadata using its documented binary encoding.

    No pickle is executed here.  Variable-size property payloads are bounded
    and skipped by their on-disk lengths.
    """

    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise LambadaCoordinateQualificationError(
            "graph-tool input must be a regular non-symlink file"
        )
    file_size = source.stat().st_size
    with source.open("rb") as stream:
        if _read_exact(stream, 6, field="magic") != _GT_MAGIC:
            raise LambadaCoordinateQualificationError("graph-tool magic does not match")
        version = _read_exact(stream, 1, field="version")[0]
        if version != _GT_VERSION:
            raise LambadaCoordinateQualificationError(
                f"unsupported graph-tool version {version}; expected {_GT_VERSION}"
            )
        endian_flag = _read_exact(stream, 1, field="endianness")[0]
        if endian_flag not in (0, 1):
            raise LambadaCoordinateQualificationError("invalid graph-tool endianness flag")
        byte_order: Literal["little", "big"] = "little" if endian_flag == 0 else "big"
        _read_gt_string(
            stream,
            byte_order=byte_order,
            file_size=file_size,
            field="comment",
            maximum_size=16 * 1024 * 1024,
        )
        directed_flag = _read_exact(stream, 1, field="directed flag")[0]
        if directed_flag not in (0, 1):
            raise LambadaCoordinateQualificationError("invalid graph-tool directed flag")
        vertex_count = _read_u64(stream, byte_order=byte_order, field="vertex count")
        if vertex_count == 0 or vertex_count > (1 << 40):
            raise LambadaCoordinateQualificationError("graph-tool vertex count is implausible")
        if vertex_count <= 1 << 8:
            vertex_index_size = 1
        elif vertex_count <= 1 << 16:
            vertex_index_size = 2
        elif vertex_count <= 1 << 32:
            vertex_index_size = 4
        else:
            vertex_index_size = 8
        edge_count = 0
        for vertex_index in range(vertex_count):
            degree = _read_u64(
                stream,
                byte_order=byte_order,
                field=f"degree[{vertex_index}]",
            )
            if degree > file_size // vertex_index_size:
                raise LambadaCoordinateQualificationError(
                    f"graph-tool degree[{vertex_index}] overflows"
                )
            edge_count += degree
            if edge_count > (1 << 48):
                raise LambadaCoordinateQualificationError("graph-tool edge count is implausible")
            _seek_forward_checked(
                stream,
                degree * vertex_index_size,
                file_size=file_size,
                field=f"neighbors[{vertex_index}]",
            )
        property_count = _read_u64(stream, byte_order=byte_order, field="property count")
        if property_count > 100_000:
            raise LambadaCoordinateQualificationError("graph-tool property count is implausible")
        records: list[GTPropertyRecord] = []
        names: set[tuple[str, str]] = set()
        for property_index in range(property_count):
            record_offset = stream.tell()
            kind_index = _read_exact(stream, 1, field=f"property[{property_index}] kind")[0]
            try:
                kind = _GT_PROPERTY_KINDS[kind_index]
            except KeyError as error:
                raise LambadaCoordinateQualificationError(
                    f"property[{property_index}] has an unknown kind"
                ) from error
            name = _read_gt_string(
                stream,
                byte_order=byte_order,
                file_size=file_size,
                field=f"property[{property_index}] name",
            )
            if not name:
                raise LambadaCoordinateQualificationError(
                    f"property[{property_index}] has an empty name"
                )
            key = (kind, name)
            if key in names:
                raise LambadaCoordinateQualificationError(
                    f"duplicate graph-tool property {kind}:{name}"
                )
            names.add(key)
            type_index = _read_exact(stream, 1, field=f"property[{property_index}] type")[0]
            item_count = {"graph": 1, "vertex": vertex_count, "edge": edge_count}[kind]
            values_offset = stream.tell()
            object_offset: int | None = None
            object_size: int | None = None
            if type_index in _GT_FIXED_VALUE_SIZES:
                _seek_forward_checked(
                    stream,
                    item_count * _GT_FIXED_VALUE_SIZES[type_index],
                    file_size=file_size,
                    field=f"property[{property_index}] values",
                )
            elif type_index in (6, 14):
                object_offset, object_size = _skip_length_prefixed_items(
                    stream,
                    count=item_count,
                    element_size=1,
                    byte_order=byte_order,
                    file_size=file_size,
                    field=f"property[{property_index}] values",
                )
                if type_index != 14 or kind != "graph":
                    object_offset = None
                    object_size = None
            elif type_index in _GT_VECTOR_VALUE_SIZES:
                _skip_length_prefixed_items(
                    stream,
                    count=item_count,
                    element_size=_GT_VECTOR_VALUE_SIZES[type_index],
                    byte_order=byte_order,
                    file_size=file_size,
                    field=f"property[{property_index}] vectors",
                )
            elif type_index == 13:
                for item_index in range(item_count):
                    vector_length = _read_u64(
                        stream,
                        byte_order=byte_order,
                        field=f"property[{property_index}] vector[{item_index}] length",
                    )
                    if vector_length > file_size // 8:
                        raise LambadaCoordinateQualificationError(
                            "graph-tool vector<string> length is implausible"
                        )
                    _skip_length_prefixed_items(
                        stream,
                        count=vector_length,
                        element_size=1,
                        byte_order=byte_order,
                        file_size=file_size,
                        field=f"property[{property_index}] vector[{item_index}] strings",
                    )
            else:
                raise LambadaCoordinateQualificationError(
                    f"property[{property_index}] has unsupported value type {type_index}"
                )
            records.append(
                GTPropertyRecord(
                    kind=cast(Literal["graph", "vertex", "edge"], kind),
                    name=name,
                    type_index=type_index,
                    item_count=item_count,
                    record_offset=record_offset,
                    values_offset=values_offset,
                    values_end_offset=stream.tell(),
                    object_payload_offset=object_offset,
                    object_payload_size_bytes=object_size,
                )
            )
        if stream.tell() != file_size:
            raise LambadaCoordinateQualificationError(
                "graph-tool property inventory does not consume the exact file"
            )
    return GTFileInventory(
        byte_order=byte_order,
        directed=bool(directed_flag),
        vertex_count=vertex_count,
        edge_count=edge_count,
        properties=tuple(records),
    )


class _RestrictedNumpyUnpickler(pickle.Unpickler):
    """Unpickler that permits only the globals required by a NumPy ndarray."""

    _ALLOWED_GLOBALS: Final = {
        ("numpy", "dtype"),
        ("numpy", "ndarray"),
        ("numpy.core.multiarray", "_reconstruct"),
        ("numpy._core.multiarray", "_reconstruct"),
    }

    def find_class(self, module: str, name: str) -> object:
        if (module, name) not in self._ALLOWED_GLOBALS:
            raise LambadaCoordinateQualificationError(
                f"pickle global {module}.{name} is not permitted"
            )
        return super().find_class(module, name)

    def persistent_load(self, pid: object) -> object:
        del pid
        raise LambadaCoordinateQualificationError("pickle persistent IDs are not permitted")


def load_graph_numpy_property(
    path: str | Path,
    record: GTPropertyRecord,
    *,
    expected_shape: tuple[int, ...],
) -> NDArray[np.generic]:
    """Decode one bounded graph-level NumPy pickle with an allowlisted loader."""

    if record.kind != "graph" or record.type_index != 14:
        raise LambadaCoordinateQualificationError(
            "requested property is not a graph-level python::object"
        )
    offset = record.object_payload_offset
    size = record.object_payload_size_bytes
    if offset is None or size is None:
        raise LambadaCoordinateQualificationError("graph object payload location is missing")
    if size <= 0 or size > MAX_HEMISPHERE_PICKLE_BYTES:
        raise LambadaCoordinateQualificationError(
            "graph object pickle is empty or exceeds the qualification memory bound"
        )
    source = Path(path)
    with source.open("rb") as stream:
        stream.seek(offset)
        payload = stream.read(size)
    if len(payload) != size:
        raise LambadaCoordinateQualificationError("graph object pickle is truncated")
    payload_stream = io.BytesIO(payload)
    try:
        value = _RestrictedNumpyUnpickler(payload_stream).load()
    except LambadaCoordinateQualificationError:
        raise
    except (EOFError, pickle.UnpicklingError, ValueError, TypeError) as error:
        raise LambadaCoordinateQualificationError(
            "graph object is not an accepted NumPy pickle"
        ) from error
    if payload_stream.read(1):
        raise LambadaCoordinateQualificationError("graph object pickle has trailing bytes")
    if not isinstance(value, np.ndarray):
        raise LambadaCoordinateQualificationError("graph object pickle is not a NumPy ndarray")
    array = np.asarray(value)
    if array.shape != expected_shape:
        raise LambadaCoordinateQualificationError(
            f"graph object shape {array.shape} does not match {expected_shape}"
        )
    if array.dtype.kind not in "iu" or array.dtype.itemsize not in (1, 2, 4, 8):
        raise LambadaCoordinateQualificationError(
            "graph hemisphere ndarray must use a fixed-width integer dtype"
        )
    if not array.flags.c_contiguous:
        raise LambadaCoordinateQualificationError("graph hemisphere ndarray must be C-contiguous")
    array.setflags(write=False)
    return array


def verify_pinned_graph_identity(path: str | Path) -> Mapping[str, object]:
    """Require the exact reviewed extracted graph before reading fixed offsets."""

    source = Path(path)
    if source.name != SOURCE_FILENAME:
        raise LambadaCoordinateQualificationError(
            f"source graph filename must be {SOURCE_FILENAME}"
        )
    if source.is_symlink() or not source.is_file():
        raise LambadaCoordinateQualificationError("source graph must be a regular non-symlink file")
    size = source.stat().st_size
    if size != SOURCE_SIZE_BYTES:
        raise LambadaCoordinateQualificationError(
            "source graph byte count does not match the pinned file"
        )
    digest = _hash_file(source)
    if digest != SOURCE_SHA256:
        raise LambadaCoordinateQualificationError(
            "source graph SHA-256 does not match the pinned file"
        )
    return {"filename": SOURCE_FILENAME, "sha256": digest, "sizeBytes": size}


def _verify_regular_file(
    path: Path,
    *,
    size_bytes: int,
    sha256: str,
) -> Mapping[str, object]:
    if path.is_symlink() or not path.is_file():
        raise LambadaCoordinateQualificationError(
            f"atlas input {path.name} must be a regular non-symlink file"
        )
    if path.stat().st_size != size_bytes:
        raise LambadaCoordinateQualificationError(
            f"atlas input {path.name} byte count does not match the pinned package"
        )
    digest = _hash_file(path)
    if digest != sha256:
        raise LambadaCoordinateQualificationError(
            f"atlas input {path.name} SHA-256 does not match the pinned package"
        )
    return {"filename": path.name, "sha256": digest, "sizeBytes": size_bytes}


def load_pinned_atlas_evidence(atlas_directory: str | Path) -> AtlasEvidence:
    """Open the exact BrainGlobe Allen 25 um v1.2 annotation and hierarchy."""

    directory = Path(atlas_directory)
    if directory.name != ALLEN_ATLAS_DIRECTORY_NAME or not directory.is_dir():
        raise LambadaCoordinateQualificationError(
            f"atlas directory must be {ALLEN_ATLAS_DIRECTORY_NAME}"
        )
    annotation_path = directory / ALLEN_ANNOTATION_FILENAME
    structures_path = directory / ALLEN_STRUCTURES_FILENAME
    metadata_path = directory / ALLEN_METADATA_FILENAME
    annotation_identity = _verify_regular_file(
        annotation_path,
        size_bytes=ALLEN_ANNOTATION_SIZE_BYTES,
        sha256=ALLEN_ANNOTATION_SHA256,
    )
    structures_identity = _verify_regular_file(
        structures_path,
        size_bytes=ALLEN_STRUCTURES_SIZE_BYTES,
        sha256=ALLEN_STRUCTURES_SHA256,
    )
    metadata_identity = _verify_regular_file(
        metadata_path,
        size_bytes=ALLEN_METADATA_SIZE_BYTES,
        sha256=ALLEN_METADATA_SHA256,
    )
    try:
        metadata_value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LambadaCoordinateQualificationError("atlas metadata is not valid JSON") from error
    if not isinstance(metadata_value, dict):
        raise LambadaCoordinateQualificationError("atlas metadata must be a JSON object")
    expected_metadata = {
        "name": "allen_mouse",
        "version": "1.2",
        "resolution": [25.0, 25.0, 25.0],
        "orientation": "asr",
        "shape": list(ATLAS_SHAPE_ASR),
        "symmetric": True,
    }
    for key, expected in expected_metadata.items():
        if metadata_value.get(key) != expected:
            raise LambadaCoordinateQualificationError(
                f"atlas metadata field {key!r} does not match {expected!r}"
            )
    try:
        raw_structures = json.loads(structures_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LambadaCoordinateQualificationError("atlas structures are not valid JSON") from error
    if not isinstance(raw_structures, list) or not raw_structures:
        raise LambadaCoordinateQualificationError("atlas structures must be a non-empty array")
    paths: dict[int, frozenset[int]] = {}
    for index, raw_structure in enumerate(raw_structures):
        if not isinstance(raw_structure, dict):
            raise LambadaCoordinateQualificationError(f"atlas structure[{index}] must be an object")
        structure_id = raw_structure.get("id")
        raw_path = raw_structure.get("structure_id_path")
        if (
            isinstance(structure_id, bool)
            or not isinstance(structure_id, int)
            or structure_id <= 0
            or not isinstance(raw_path, list)
            or not raw_path
            or any(isinstance(item, bool) or not isinstance(item, int) for item in raw_path)
            or raw_path[-1] != structure_id
        ):
            raise LambadaCoordinateQualificationError(
                f"atlas structure[{index}] has an invalid hierarchy path"
            )
        if structure_id in paths:
            raise LambadaCoordinateQualificationError(
                f"atlas contains duplicate structure ID {structure_id}"
            )
        paths[structure_id] = frozenset(raw_path)
    try:
        annotation_value = tifffile.memmap(annotation_path, mode="r")
    except (OSError, ValueError) as error:
        raise LambadaCoordinateQualificationError(
            "atlas annotation TIFF must be directly memory-mappable"
        ) from error
    annotation = np.asarray(annotation_value)
    if annotation.shape != ATLAS_SHAPE_ASR or annotation.dtype != np.dtype(np.uint32):
        raise LambadaCoordinateQualificationError(
            "atlas annotation shape or dtype does not match Allen 25 um v1.2"
        )
    annotation.setflags(write=False)
    return AtlasEvidence(
        annotation=cast(NDArray[np.uint32], annotation),
        structure_paths=paths,
        identity_report={
            "atlasKey": "allen_mouse_25um",
            "atlasPackageVersion": "1.2",
            "orientation": "asr",
            "resolutionUm": [25, 25, 25],
            "shapeVoxels": list(ATLAS_SHAPE_ASR),
            "annotation": annotation_identity,
            "structures": structures_identity,
            "metadata": metadata_identity,
        },
    )


def _true_blocks(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    padded = np.empty(mask.size + 2, dtype=np.bool_)
    padded[0] = False
    padded[-1] = False
    padded[1:-1] = mask
    transitions = np.diff(padded.astype(np.int8, copy=False))
    starts = np.flatnonzero(transitions == 1)
    ends = np.flatnonzero(transitions == -1)
    return [(int(start), int(end)) for start, end in zip(starts, ends, strict=True)]


def rerun_retained_major_vessel_selection(source_path: str | Path) -> RetainedSourceSelection:
    """Repeat the exact v1 pointwise selection and match the bundled bytes."""

    path = Path(source_path)
    coordinates = np.memmap(
        path,
        mode="r",
        dtype="<f8",
        offset=COORDINATES_ATLAS_RAW_OFFSET,
        shape=(SOURCE_GEOMETRY_POINT_COUNT, 3),
    )
    radii = np.memmap(
        path,
        mode="r",
        dtype="<f8",
        offset=RADII_ATLAS_RAW_OFFSET,
        shape=(SOURCE_GEOMETRY_POINT_COUNT,),
    )
    annotations = np.memmap(
        path,
        mode="r",
        dtype="<i8",
        offset=ANNOTATIONS_RAW_OFFSET,
        shape=(SOURCE_GEOMETRY_POINT_COUNT,),
    )
    index_dtype = np.dtype([("length", "<u8"), ("values", "<i8", (2,))])
    index_records = np.memmap(
        path,
        mode="r",
        dtype=index_dtype,
        offset=EDGE_GEOMETRY_INDICES_PAYLOAD_OFFSET,
        shape=(SOURCE_EDGE_COUNT,),
    )
    if not bool(np.all(index_records["length"] == 2)):
        raise LambadaCoordinateQualificationError(
            "source edge_geometry_indices vector widths changed"
        )
    edge_indices = index_records["values"]
    if (
        int(edge_indices[0, 0]) != 0
        or int(edge_indices[-1, 1]) != SOURCE_GEOMETRY_POINT_COUNT
        or not bool(np.all(edge_indices[:, 1] > edge_indices[:, 0]))
        or not bool(np.all(edge_indices[1:, 0] == edge_indices[:-1, 1]))
    ):
        raise LambadaCoordinateQualificationError("source edge geometry ranges are not contiguous")
    edge_radii = np.memmap(
        path,
        mode="r",
        dtype="<f8",
        offset=EDGE_RADII_ATLAS_RAW_OFFSET,
        shape=(SOURCE_EDGE_COUNT,),
    )
    candidate_edges = np.flatnonzero(edge_radii >= MINIMUM_RADIUS_ATLAS_VOXEL)
    if candidate_edges.size != EXPECTED_CANDIDATE_EDGE_COUNT:
        raise LambadaCoordinateQualificationError("source candidate edge count changed")

    point_chunks: list[NDArray[np.float64]] = []
    source_index_chunks: list[NDArray[np.int64]] = []
    radius_chunks: list[NDArray[np.float32]] = []
    annotation_chunks: list[NDArray[np.int32]] = []
    source_edges: list[int] = []
    run_offsets = [0]
    qualifying_in_bounds_points = 0
    edges_with_runs: set[int] = set()
    shape = np.asarray(ATLAS_SHAPE_CLEARMAP, dtype=np.float64)
    for edge_value in candidate_edges:
        edge_index = int(edge_value)
        edge_start = int(edge_indices[edge_index, 0])
        edge_end = int(edge_indices[edge_index, 1])
        edge_coordinates = np.asarray(coordinates[edge_start:edge_end])
        edge_radius_values = np.asarray(radii[edge_start:edge_end])
        qualifying = np.all(np.isfinite(edge_coordinates), axis=1)
        qualifying &= np.isfinite(edge_radius_values)
        qualifying &= np.all(edge_coordinates >= 0.0, axis=1)
        qualifying &= np.all(edge_coordinates < shape, axis=1)
        qualifying &= edge_radius_values >= MINIMUM_RADIUS_ATLAS_VOXEL
        qualifying_in_bounds_points += int(np.count_nonzero(qualifying))
        for block_start, block_end in _true_blocks(qualifying):
            if block_end - block_start < 2:
                continue
            source_start = edge_start + block_start
            source_end = edge_start + block_end
            source_slice = slice(source_start, source_end)
            point_chunks.append(
                np.ascontiguousarray(np.asarray(coordinates[source_slice], dtype=np.float64))
            )
            source_index_chunks.append(np.arange(source_start, source_end, dtype=np.int64))
            radius_chunks.append(
                np.ascontiguousarray(
                    (
                        np.asarray(radii[source_slice], dtype=np.float64) * ATLAS_VOXEL_SIZE_UM
                    ).astype(np.float32)
                )
            )
            source_annotations = np.asarray(annotations[source_slice])
            if source_annotations.size and (
                int(np.min(source_annotations)) < np.iinfo(np.int32).min
                or int(np.max(source_annotations)) > np.iinfo(np.int32).max
            ):
                raise LambadaCoordinateQualificationError("source annotation ID does not fit int32")
            annotation_chunks.append(
                np.ascontiguousarray(source_annotations.astype(np.int32, copy=False))
            )
            source_edges.append(edge_index)
            edges_with_runs.add(edge_index)
            run_offsets.append(run_offsets[-1] + block_end - block_start)
    selection = RetainedSourceSelection(
        points_clearmap_voxel_f64=np.ascontiguousarray(np.concatenate(point_chunks)),
        source_geometry_indices_i64=np.ascontiguousarray(np.concatenate(source_index_chunks)),
        radii_um_f32=np.ascontiguousarray(np.concatenate(radius_chunks)),
        source_annotation_ids_i32=np.ascontiguousarray(np.concatenate(annotation_chunks)),
        run_offsets_i64=np.asarray(run_offsets, dtype=np.int64),
        source_edge_indices_i32=np.asarray(source_edges, dtype=np.int32),
        qualifying_in_bounds_points=qualifying_in_bounds_points,
        source_edges_with_runs=len(edges_with_runs),
    )
    expected_counts = (
        EXPECTED_QUALIFYING_IN_BOUNDS_POINT_COUNT,
        EXPECTED_RUN_POINT_COUNT,
        EXPECTED_SEGMENT_COUNT,
        EXPECTED_RUN_COUNT,
        EXPECTED_SOURCE_EDGES_WITH_RUNS,
    )
    observed_counts = (
        selection.qualifying_in_bounds_points,
        int(selection.points_clearmap_voxel_f64.shape[0]),
        int(selection.points_clearmap_voxel_f64.shape[0] - len(source_edges)),
        len(source_edges),
        selection.source_edges_with_runs,
    )
    if observed_counts != expected_counts:
        raise LambadaCoordinateQualificationError(
            f"retained selection counts changed: {observed_counts}"
        )

    bundled_graph = load_lambada_major_vessels()
    expected_points_asr_um = np.ascontiguousarray(
        selection.points_clearmap_voxel_f64[:, (1, 0, 2)].astype(np.float32)
        * np.float32(ATLAS_VOXEL_SIZE_UM)
    )
    exact_matches = (
        np.array_equal(expected_points_asr_um, bundled_graph.points_asr_um)
        and np.array_equal(selection.radii_um_f32, bundled_graph.radii_um)
        and np.array_equal(
            selection.source_annotation_ids_i32,
            bundled_graph.source_annotation_ids,
        )
        and np.array_equal(selection.run_offsets_i64, bundled_graph.run_offsets)
        and np.array_equal(
            selection.source_edge_indices_i32,
            bundled_graph.source_edge_indices,
        )
    )
    if not exact_matches:
        raise LambadaCoordinateQualificationError(
            "rerun selection does not exactly match the integrity-checked bundled asset"
        )
    return selection


def _rate_report(numerator: int, denominator: int) -> Mapping[str, object]:
    decimal = "0.000000000" if denominator == 0 else f"{numerator / denominator:.9f}"
    return {
        "numerator": numerator,
        "denominator": denominator,
        "decimal": decimal,
    }


def _score_fraction(score: Mapping[str, object]) -> Fraction:
    raw = cast(Mapping[str, object], score["ancestorAgreement"])
    numerator = cast(int, raw["numerator"])
    denominator = cast(int, raw["denominator"])
    return Fraction(numerator, denominator) if denominator else Fraction(0, 1)


def score_annotation_orientations(
    points_clearmap_voxel: NDArray[np.generic],
    source_annotation_ids: NDArray[np.generic],
    atlas_annotation_asr: NDArray[np.generic],
    structure_paths: Mapping[int, frozenset[int]],
) -> list[Mapping[str, object]]:
    """Score all eight sign combinations using source-ancestor agreement."""

    points = np.asarray(points_clearmap_voxel, dtype=np.float64)
    source_ids = np.asarray(source_annotation_ids, dtype=np.int64)
    atlas = np.asarray(atlas_annotation_asr)
    if points.ndim != 2 or points.shape[1:] != (3,) or source_ids.shape != points.shape[:1]:
        raise LambadaCoordinateQualificationError("orientation score inputs have invalid shapes")
    if atlas.shape != ATLAS_SHAPE_ASR or atlas.dtype.kind not in "iu":
        raise LambadaCoordinateQualificationError("orientation atlas has invalid shape or dtype")
    known_ids = frozenset(structure_paths)
    source_known = np.fromiter(
        (int(value) in known_ids for value in source_ids),
        dtype=np.bool_,
        count=source_ids.size,
    )
    base_asr = points[:, (1, 0, 2)]
    shape = np.asarray(ATLAS_SHAPE_ASR, dtype=np.float64)
    scores: list[Mapping[str, object]] = []
    for flip_ap in (False, True):
        for flip_dv in (False, True):
            for flip_ml in (False, True):
                flips = (flip_ap, flip_dv, flip_ml)
                transformed = base_asr.copy()
                for axis, flip in enumerate(flips):
                    if flip:
                        transformed[:, axis] = shape[axis] - 1.0 - transformed[:, axis]
                indices = transformed.astype(np.int64)
                if bool(np.any(indices < 0)) or bool(
                    np.any(indices >= np.asarray(ATLAS_SHAPE_ASR, dtype=np.int64))
                ):
                    raise LambadaCoordinateQualificationError(
                        "retained point left atlas bounds during sign scoring"
                    )
                sampled_ids = np.asarray(
                    atlas[indices[:, 0], indices[:, 1], indices[:, 2]],
                    dtype=np.int64,
                )
                sampled_known = np.fromiter(
                    (int(value) in known_ids for value in sampled_ids),
                    dtype=np.bool_,
                    count=sampled_ids.size,
                )
                evaluable = source_known & sampled_known
                evaluable_indices = np.flatnonzero(evaluable)
                compatible_count = sum(
                    int(source_ids[index]) in structure_paths[int(sampled_ids[index])]
                    for index in evaluable_indices
                )
                evaluable_count = int(evaluable_indices.size)
                exact_count = int(np.count_nonzero(source_ids[evaluable] == sampled_ids[evaluable]))
                label = "_".join(
                    (
                        f"AP_{'FLIP' if flip_ap else 'KEEP'}",
                        f"DV_{'FLIP' if flip_dv else 'KEEP'}",
                        f"ML_{'FLIP' if flip_ml else 'KEEP'}",
                    )
                )
                scores.append(
                    {
                        "label": label,
                        "flipAP": flip_ap,
                        "flipDV": flip_dv,
                        "flipML": flip_ml,
                        "selectedPointCount": int(points.shape[0]),
                        "evaluablePointCount": evaluable_count,
                        "evaluableFraction": _rate_report(evaluable_count, int(points.shape[0])),
                        "ancestorAgreement": _rate_report(
                            compatible_count,
                            evaluable_count,
                        ),
                        "exactLeafAgreement": _rate_report(exact_count, evaluable_count),
                    }
                )
    return scores


def score_hemisphere_laterality(
    points_clearmap_voxel: NDArray[np.generic],
    source_hemisphere_labels: NDArray[np.generic],
) -> Mapping[str, object]:
    """Test whether ClearMap axis 2 already follows right-origin ASR ML."""

    points = np.asarray(points_clearmap_voxel, dtype=np.float64)
    labels = np.asarray(source_hemisphere_labels)
    if points.ndim != 2 or points.shape[1:] != (3,) or labels.shape != points.shape[:1]:
        raise LambadaCoordinateQualificationError("hemisphere score inputs have invalid shapes")
    if labels.dtype.kind not in "iu":
        raise LambadaCoordinateQualificationError("source hemisphere labels must be integral")
    labels_i64 = np.asarray(labels, dtype=np.int64)
    allowed = np.isin(
        labels_i64,
        [CLEARMAP_LEFT_HEMISPHERE_VALUE, CLEARMAP_RIGHT_HEMISPHERE_VALUE],
    )
    if not bool(np.all(allowed)):
        invalid = np.unique(labels_i64[~allowed])
        raise LambadaCoordinateQualificationError(
            f"source hemisphere labels contain unsupported values {invalid[:10].tolist()}"
        )
    ml_coordinates = points[:, 2]
    ml_indices = ml_coordinates.astype(np.int64)
    if bool(np.any(ml_indices < 0)) or bool(np.any(ml_indices >= ATLAS_SHAPE_ASR[2])):
        raise LambadaCoordinateQualificationError("source ML point is outside atlas bounds")
    expected_keep = np.where(
        ml_indices < ML_MIDLINE_VOXEL,
        CLEARMAP_RIGHT_HEMISPHERE_VALUE,
        CLEARMAP_LEFT_HEMISPHERE_VALUE,
    )
    flipped_ml_indices = (ATLAS_SHAPE_ASR[2] - 1.0 - ml_coordinates).astype(np.int64)
    expected_flip = np.where(
        flipped_ml_indices < ML_MIDLINE_VOXEL,
        CLEARMAP_RIGHT_HEMISPHERE_VALUE,
        CLEARMAP_LEFT_HEMISPHERE_VALUE,
    )
    discriminating = expected_keep != expected_flip
    discriminating_count = int(np.count_nonzero(discriminating))
    if discriminating_count == 0:
        raise LambadaCoordinateQualificationError(
            "retained hemisphere evidence has no points that distinguish ML signs"
        )
    keep_count = int(np.count_nonzero(labels_i64[discriminating] == expected_keep[discriminating]))
    flip_count = int(np.count_nonzero(labels_i64[discriminating] == expected_flip[discriminating]))
    return {
        "sourceLabelSemantics": {
            "0": "LH",
            "255": "RH",
            "evidence": (
                "ClearMap Analysis/Statistics/data_frame_operations.py maps 0 to LH and 255 to RH"
            ),
            "sourceUrl": CLEARMAP_HEMISPHERE_SEMANTICS_URL,
        },
        "brainGlobeMLSemantics": "ASR ML origin is right and increasing indices move left",
        "midlineIndex": ML_MIDLINE_VOXEL,
        "selectedPointCount": int(points.shape[0]),
        "discriminatingPointCount": discriminating_count,
        "discriminatingPointFraction": _rate_report(discriminating_count, int(points.shape[0])),
        "nonDiscriminatingMidlinePointCount": int(points.shape[0]) - discriminating_count,
        "keepAxis2Agreement": _rate_report(keep_count, discriminating_count),
        "flipAxis2Agreement": _rate_report(flip_count, discriminating_count),
    }


def _criteria_report() -> Mapping[str, object]:
    return {
        "minimumAnnotationEvaluablePoints": MIN_ANNOTATION_EVALUABLE_POINTS,
        "minimumAnnotationEvaluableFraction": str(MIN_ANNOTATION_EVALUABLE_FRACTION),
        "minimumAnnotationAncestorAgreement": str(MIN_ANNOTATION_ANCESTOR_AGREEMENT),
        "minimumExpectedGlobalLead": str(MIN_EXPECTED_GLOBAL_LEAD),
        "minimumAPDVWinnerMargin": str(MIN_AP_DV_WINNER_MARGIN),
        "minimumHemisphereDiscriminatingFraction": str(MIN_HEMISPHERE_DISCRIMINATING_FRACTION),
        "minimumHemisphereAgreement": str(MIN_HEMISPHERE_AGREEMENT),
        "minimumHemisphereWinnerMargin": str(MIN_HEMISPHERE_WINNER_MARGIN),
        "requiredSourceHemisphereProperty": {
            "kind": "graph",
            "name": HEMISPHERE_PROPERTY_NAME,
            "typeIndex": 14,
            "cardinality": 1,
        },
        "requireWholeBrainCoverageOrExplicitQualifiedMirroring": True,
        "expectedOrientation": "AP_KEEP_DV_KEEP_ML_KEEP",
        "criteriaAreRuntimeConfigurable": False,
    }


def _evaluate_annotation_checks(
    orientation_scores: Sequence[Mapping[str, object]],
) -> tuple[list[Mapping[str, object]], Mapping[str, object]]:
    expected = next(
        score for score in orientation_scores if score["label"] == "AP_KEEP_DV_KEEP_ML_KEEP"
    )
    ordered = sorted(
        orientation_scores,
        key=lambda score: (_score_fraction(score), str(score["label"])),
        reverse=True,
    )
    global_winner = ordered[0]
    global_runner_up = ordered[1]
    expected_fraction = _score_fraction(expected)
    runner_fraction = _score_fraction(global_runner_up)
    expected_evaluable = int(cast(int, expected["evaluablePointCount"]))
    selected_count = int(cast(int, expected["selectedPointCount"]))

    ap_dv_best: dict[tuple[bool, bool], Mapping[str, object]] = {}
    for score in orientation_scores:
        key = (bool(score["flipAP"]), bool(score["flipDV"]))
        previous = ap_dv_best.get(key)
        if previous is None or _score_fraction(score) > _score_fraction(previous):
            ap_dv_best[key] = score
    expected_ap_dv = ap_dv_best[(False, False)]
    ap_dv_runner = max(
        (score for key, score in ap_dv_best.items() if key != (False, False)),
        key=_score_fraction,
    )
    ap_dv_margin = _score_fraction(expected_ap_dv) - _score_fraction(ap_dv_runner)

    check_values = [
        (
            "annotation-evaluable-point-count",
            expected_evaluable >= MIN_ANNOTATION_EVALUABLE_POINTS,
            str(expected_evaluable),
            f">={MIN_ANNOTATION_EVALUABLE_POINTS}",
        ),
        (
            "annotation-evaluable-fraction",
            Fraction(expected_evaluable, selected_count) >= MIN_ANNOTATION_EVALUABLE_FRACTION,
            str(Fraction(expected_evaluable, selected_count)),
            f">={MIN_ANNOTATION_EVALUABLE_FRACTION}",
        ),
        (
            "annotation-ancestor-agreement",
            expected_fraction >= MIN_ANNOTATION_ANCESTOR_AGREEMENT,
            str(expected_fraction),
            f">={MIN_ANNOTATION_ANCESTOR_AGREEMENT}",
        ),
        (
            "expected-orientation-is-global-winner",
            global_winner["label"] == expected["label"],
            str(global_winner["label"]),
            str(expected["label"]),
        ),
        (
            "expected-orientation-global-lead",
            expected_fraction - runner_fraction >= MIN_EXPECTED_GLOBAL_LEAD,
            str(expected_fraction - runner_fraction),
            f">={MIN_EXPECTED_GLOBAL_LEAD}",
        ),
        (
            "ap-dv-sign-margin",
            ap_dv_margin >= MIN_AP_DV_WINNER_MARGIN,
            str(ap_dv_margin),
            f">={MIN_AP_DV_WINNER_MARGIN}",
        ),
    ]
    checks: list[Mapping[str, object]] = [
        {"id": identifier, "passed": passed, "observed": observed, "required": required}
        for identifier, passed, observed, required in check_values
    ]
    summary: Mapping[str, object] = {
        "globalWinner": global_winner["label"],
        "globalRunnerUp": global_runner_up["label"],
        "expectedGlobalLead": str(expected_fraction - runner_fraction),
        "bestAPDVAlternative": ap_dv_runner["label"],
        "apDvWinnerMargin": str(ap_dv_margin),
    }
    return checks, summary


def _evaluate_hemisphere_checks(
    hemisphere_score: Mapping[str, object],
) -> tuple[list[Mapping[str, object]], Mapping[str, object]]:
    keep_raw = cast(Mapping[str, object], hemisphere_score["keepAxis2Agreement"])
    flip_raw = cast(Mapping[str, object], hemisphere_score["flipAxis2Agreement"])
    keep_fraction = Fraction(
        cast(int, keep_raw["numerator"]),
        cast(int, keep_raw["denominator"]),
    )
    flip_fraction = Fraction(
        cast(int, flip_raw["numerator"]),
        cast(int, flip_raw["denominator"]),
    )
    selected_count = cast(int, hemisphere_score["selectedPointCount"])
    discriminating_count = cast(int, hemisphere_score["discriminatingPointCount"])
    check_values = [
        (
            "source-hemisphere-property-present",
            True,
            f"1 graph:{HEMISPHERE_PROPERTY_NAME} typeIndex=14",
            f"1 graph:{HEMISPHERE_PROPERTY_NAME} typeIndex=14",
        ),
        (
            "ml-hemisphere-discriminating-fraction",
            Fraction(discriminating_count, selected_count)
            >= MIN_HEMISPHERE_DISCRIMINATING_FRACTION,
            str(Fraction(discriminating_count, selected_count)),
            f">={MIN_HEMISPHERE_DISCRIMINATING_FRACTION}",
        ),
        (
            "ml-hemisphere-agreement",
            keep_fraction >= MIN_HEMISPHERE_AGREEMENT,
            str(keep_fraction),
            f">={MIN_HEMISPHERE_AGREEMENT}",
        ),
        (
            "ml-hemisphere-winner-margin",
            keep_fraction - flip_fraction >= MIN_HEMISPHERE_WINNER_MARGIN,
            str(keep_fraction - flip_fraction),
            f">={MIN_HEMISPHERE_WINNER_MARGIN}",
        ),
    ]
    checks: list[Mapping[str, object]] = [
        {"id": identifier, "passed": passed, "observed": observed, "required": required}
        for identifier, passed, observed, required in check_values
    ]
    return checks, {"hemisphereWinnerMargin": str(keep_fraction - flip_fraction)}


def _evaluate_checks(
    orientation_scores: Sequence[Mapping[str, object]],
    hemisphere_score: Mapping[str, object],
) -> tuple[list[Mapping[str, object]], Mapping[str, object]]:
    annotation_checks, annotation_summary = _evaluate_annotation_checks(orientation_scores)
    hemisphere_checks, hemisphere_summary = _evaluate_hemisphere_checks(hemisphere_score)
    return annotation_checks + hemisphere_checks, {
        **annotation_summary,
        **hemisphere_summary,
    }


def _property_record_report(record: GTPropertyRecord) -> Mapping[str, object]:
    return {
        "kind": record.kind,
        "name": record.name,
        "typeIndex": record.type_index,
        "itemCount": record.item_count,
        "recordOffset": record.record_offset,
        "valuesOffset": record.values_offset,
        "valuesEndOffset": record.values_end_offset,
        "objectPayloadOffset": record.object_payload_offset,
        "objectPayloadSizeBytes": record.object_payload_size_bytes,
    }


def _graph_tool_report(
    inventory: GTFileInventory,
    *,
    hemisphere_property: Mapping[str, object] | None,
) -> Mapping[str, object]:
    return {
        "formatDocumentation": GT_FORMAT_DOCUMENTATION_URL,
        "byteOrder": inventory.byte_order,
        "directed": inventory.directed,
        "vertexCount": inventory.vertex_count,
        "edgeCount": inventory.edge_count,
        "propertyCount": len(inventory.properties),
        "propertyInventory": [_property_record_report(record) for record in inventory.properties],
        "hemisphereProperty": hemisphere_property,
    }


def _retained_selection_report(selection: RetainedSourceSelection) -> Mapping[str, object]:
    return {
        "assetSha256": ASSET_SHA256,
        "exactBundledAssetMatch": True,
        "candidateEdges": EXPECTED_CANDIDATE_EDGE_COUNT,
        "qualifyingInBoundsPoints": selection.qualifying_in_bounds_points,
        "outputPoints": int(selection.points_clearmap_voxel_f64.shape[0]),
        "outputSegments": int(
            selection.points_clearmap_voxel_f64.shape[0]
            - selection.source_edge_indices_i32.shape[0]
        ),
        "outputRuns": int(selection.source_edge_indices_i32.shape[0]),
        "sourceEdgesWithRuns": selection.source_edges_with_runs,
    }


def assess_pinned_source_coverage(
    source_path: str | Path,
    inventory: GTFileInventory,
    selection: RetainedSourceSelection,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Measure atlas-space coverage without treating numerical sides as laterality labels."""

    matches = [
        record
        for record in inventory.properties
        if record.kind == "vertex" and record.name == "coordinates_atlas"
    ]
    if len(matches) != 1 or matches[0].type_index != 11:
        raise LambadaCoordinateQualificationError(
            "pinned graph must contain one vector<double> vertex coordinates_atlas property"
        )
    record = matches[0]
    record_dtype = np.dtype([("length", "<u8"), ("values", "<f8", (3,))])
    expected_bytes = record.item_count * record_dtype.itemsize
    if record.values_end_offset - record.values_offset != expected_bytes:
        raise LambadaCoordinateQualificationError(
            "vertex coordinates_atlas byte span does not match vector<double>[3] records"
        )
    records = np.memmap(
        Path(source_path),
        mode="r",
        dtype=record_dtype,
        offset=record.values_offset,
        shape=(record.item_count,),
    )
    if not bool(np.all(records["length"] == 3)):
        raise LambadaCoordinateQualificationError(
            "vertex coordinates_atlas contains a non-three-dimensional vector"
        )
    coordinates = records["values"]
    if not bool(np.all(np.isfinite(coordinates))):
        raise LambadaCoordinateQualificationError(
            "vertex coordinates_atlas contains a non-finite value"
        )
    minimum = np.min(coordinates, axis=0)
    maximum = np.max(coordinates, axis=0)
    ml_values = coordinates[:, 2]
    low_side_count = int(np.count_nonzero(ml_values < ML_MIDLINE_VOXEL))
    high_side_count = int(ml_values.size - low_side_count)
    retained_ml = selection.points_clearmap_voxel_f64[:, 2]
    retained_low_count = int(np.count_nonzero(retained_ml < ML_MIDLINE_VOXEL))
    retained_high_count = int(retained_ml.size - retained_low_count)
    graph_level_names = [
        property_record.name
        for property_record in inventory.properties
        if property_record.kind == "graph"
    ]
    report: Mapping[str, object] = {
        "status": "unqualified-for-whole-brain-use",
        "reasonCode": HEMISPHERE_COVERAGE_REASON_CODE,
        "primarySource": {
            "url": ZENODO_DATASET_RECORD_URL,
            "finding": (
                "The official dataset description identifies the specimens as mouse brain "
                "hemispheres, not whole-brain vascular graphs."
            ),
        },
        "atlasMidlineIndex": ML_MIDLINE_VOXEL,
        "vertexCoordinatesAtlas": {
            "pointCount": int(coordinates.shape[0]),
            "minimumByClearMapAxis": [f"{float(value):.9f}" for value in minimum],
            "maximumByClearMapAxis": [f"{float(value):.9f}" for value in maximum],
            "axis2BelowMidlineCount": low_side_count,
            "axis2AtOrAboveMidlineCount": high_side_count,
        },
        "retainedMajorVesselCoordinatesAtlas": {
            "pointCount": int(retained_ml.size),
            "axis2Minimum": f"{float(np.min(retained_ml)):.9f}",
            "axis2Maximum": f"{float(np.max(retained_ml)):.9f}",
            "axis2BelowMidlineCount": retained_low_count,
            "axis2AtOrAboveMidlineCount": retained_high_count,
        },
        "graphMetadataAssessment": {
            "graphLevelPropertyNames": graph_level_names,
            "propertiesBindingBiologicalLaterality": [],
            "propertiesBindingExactWorkflowCommit": [],
            "propertiesContainingSourceOrientationOrAlignmentTransform": [],
            "conclusion": (
                "The graph stores raw, atlas, and MRI coordinates plus a raw image shape, "
                "but no source-orientation label, alignment transform, resampling metadata, "
                "workflow commit, or specimen configuration that binds ML sign."
            ),
        },
        "numericalBothSidesDoNotProveWholeBrain": True,
        "bilateralMirroringQualified": False,
        "bilateralMirroringReason": (
            "Neither the exact graph metadata nor the dataset record defines a reviewed "
            "mirror operation that reconstructs a whole-brain major-vessel reference."
        ),
    }
    check: Mapping[str, object] = {
        "id": "source-coverage-whole-brain",
        "passed": False,
        "observed": "official source declares brain-hemisphere specimens",
        "required": "whole-brain source or explicitly reviewed bilateral reconstruction",
    }
    return report, check


def _scope_limitations() -> list[str]:
    return [
        (
            "This report qualifies only axis permutation, AP/DV signs, and ML laterality "
            "for the exact pinned files when every check passes."
        ),
        (
            "It does not bound atlas-registration error, tissue distortion, biological "
            "variation, or omitted vessels."
        ),
        (
            "It does not make the fixed-tissue reference subject-specific or validate it "
            "for surgical navigation."
        ),
        (
            "It does not establish artery/vein identity or clearance when no "
            "loaded-geometry conflict is found."
        ),
    ]


def qualify_pinned_lambada_coordinates(
    source_graph: str | Path,
    atlas_directory: str | Path,
) -> Mapping[str, object]:
    """Run the full qualification and return a canonicalizable report mapping."""

    source_identity = verify_pinned_graph_identity(source_graph)
    inventory = scan_gt_file(source_graph)
    if (
        inventory.byte_order != "little"
        or inventory.vertex_count != SOURCE_VERTEX_COUNT
        or inventory.edge_count != SOURCE_EDGE_COUNT
    ):
        raise LambadaCoordinateQualificationError(
            "graph-tool topology inventory does not match the pinned source"
        )
    selection = rerun_retained_major_vessel_selection(source_graph)
    atlas = load_pinned_atlas_evidence(atlas_directory)
    orientation_scores = score_annotation_orientations(
        selection.points_clearmap_voxel_f64,
        selection.source_annotation_ids_i32,
        atlas.annotation,
        atlas.structure_paths,
    )
    annotation_checks, annotation_summary = _evaluate_annotation_checks(orientation_scores)
    source_coverage, source_coverage_check = assess_pinned_source_coverage(
        source_graph,
        inventory,
        selection,
    )
    common_report: dict[str, object] = {
        "schemaVersion": QUALIFICATION_SCHEMA_VERSION,
        "algorithmVersion": QUALIFICATION_ALGORITHM_VERSION,
        "source": source_identity,
        "clearMapImplementationEvidence": {
            "repository": CLEARMAP_REPOSITORY_URL,
            "commit": CLEARMAP_EVIDENCE_COMMIT,
            "annotationAndHemispherePropertyCreation": CLEARMAP_ANNOTATION_SOURCE_URL,
            "graphLevelEdgeGeometryStorage": CLEARMAP_GRAPH_STORAGE_URL,
            "hemisphereLabelSemantics": CLEARMAP_HEMISPHERE_SEMANTICS_URL,
            "evidenceScope": (
                "Context only. Generic repository code does not bind a workflow commit, "
                "configuration, or transform to the exact P60_606 artifact."
            ),
            "exactArtifactWorkflowCommit": None,
            "exactArtifactSpecimenConfiguration": None,
        },
        "atlas": atlas.identity_report,
        "retainedSelection": _retained_selection_report(selection),
        "sourceCoverage": source_coverage,
        "predeclaredAcceptanceCriteria": _criteria_report(),
        "annotationOrientation": {
            "method": (
                "For each of all eight AP/DV/ML sign combinations, truncate retained "
                "continuous voxels exactly as ClearMap label_points does, sample the pinned "
                "Allen annotation, and count the source annotation when it is an ancestor "
                "of the sampled Allen structure. AP/DV are judged separately from bilateral "
                "ML symmetry."
            ),
            "scores": orientation_scores,
        },
        "scopeLimitations": _scope_limitations(),
    }
    hemisphere_records = [
        record
        for record in inventory.properties
        if record.kind == "graph" and record.name == HEMISPHERE_PROPERTY_NAME
    ]
    if not hemisphere_records:
        property_check: Mapping[str, object] = {
            "id": "source-hemisphere-property-present",
            "passed": False,
            "observed": "0 matching properties",
            "required": f"1 graph:{HEMISPHERE_PROPERTY_NAME} typeIndex=14",
        }
        return {
            **common_report,
            "status": "rejected",
            "graphTool": _graph_tool_report(inventory, hemisphere_property=None),
            "hemisphereLaterality": {
                "status": "unavailable",
                "reasonCode": MISSING_HEMISPHERE_REASON_CODE,
                "reason": (
                    "The exact pinned graph has no graph-level edge_geometry_hemisphere "
                    "property. Its bilateral annotation cannot distinguish the two ML signs, "
                    "and generic pipeline defaults are not specimen evidence."
                ),
                "observedMatchingPropertyCount": 0,
                "requiredProperty": cast(
                    Mapping[str, object],
                    _criteria_report()["requiredSourceHemisphereProperty"],
                ),
                "genericPipelineEvidenceSubstituted": False,
            },
            "checks": [*annotation_checks, property_check, source_coverage_check],
            "decision": {
                **annotation_summary,
                "hemisphereWinnerMargin": None,
                "blockingReasons": [
                    MISSING_HEMISPHERE_REASON_CODE,
                    HEMISPHERE_COVERAGE_REASON_CODE,
                ],
                "qualifiedMapping": None,
            },
        }
    hemisphere_record = hemisphere_records[0]
    if hemisphere_record.type_index != 14:
        invalid_type_reason = "SOURCE_HEMISPHERE_PROPERTY_INVALID_TYPE"
        property_check = {
            "id": "source-hemisphere-property-present",
            "passed": False,
            "observed": (
                f"1 graph:{HEMISPHERE_PROPERTY_NAME} typeIndex={hemisphere_record.type_index}"
            ),
            "required": f"1 graph:{HEMISPHERE_PROPERTY_NAME} typeIndex=14",
        }
        return {
            **common_report,
            "status": "rejected",
            "graphTool": _graph_tool_report(
                inventory,
                hemisphere_property=_property_record_report(hemisphere_record),
            ),
            "hemisphereLaterality": {
                "status": "unavailable",
                "reasonCode": invalid_type_reason,
                "reason": (
                    "The exact pinned graph's edge_geometry_hemisphere property is not a "
                    "graph-level python::object and cannot be decoded as pinned evidence."
                ),
                "observedMatchingPropertyCount": 1,
                "requiredProperty": cast(
                    Mapping[str, object],
                    _criteria_report()["requiredSourceHemisphereProperty"],
                ),
                "genericPipelineEvidenceSubstituted": False,
            },
            "checks": [*annotation_checks, property_check, source_coverage_check],
            "decision": {
                **annotation_summary,
                "hemisphereWinnerMargin": None,
                "blockingReasons": [
                    invalid_type_reason,
                    HEMISPHERE_COVERAGE_REASON_CODE,
                ],
                "qualifiedMapping": None,
            },
        }
    hemispheres = load_graph_numpy_property(
        source_graph,
        hemisphere_record,
        expected_shape=(SOURCE_GEOMETRY_POINT_COUNT,),
    )
    unique_hemispheres = {int(value) for value in np.unique(hemispheres)}
    if unique_hemispheres != {
        CLEARMAP_LEFT_HEMISPHERE_VALUE,
        CLEARMAP_RIGHT_HEMISPHERE_VALUE,
    }:
        raise LambadaCoordinateQualificationError(
            f"full source hemisphere inventory changed: {sorted(unique_hemispheres)}"
        )
    selected_hemispheres = np.ascontiguousarray(hemispheres[selection.source_geometry_indices_i64])
    del hemispheres
    hemisphere_score = score_hemisphere_laterality(
        selection.points_clearmap_voxel_f64,
        selected_hemispheres,
    )
    checks, decision_summary = _evaluate_checks(orientation_scores, hemisphere_score)
    checks.append(source_coverage_check)
    passed = all(bool(check["passed"]) for check in checks)
    return {
        **common_report,
        "status": "qualified" if passed else "rejected",
        "graphTool": _graph_tool_report(
            inventory,
            hemisphere_property={
                **_property_record_report(hemisphere_record),
                "name": hemisphere_record.name,
                "kind": hemisphere_record.kind,
                "typeIndex": hemisphere_record.type_index,
                "recordOffset": hemisphere_record.record_offset,
                "picklePayloadOffset": hemisphere_record.object_payload_offset,
                "picklePayloadSizeBytes": hemisphere_record.object_payload_size_bytes,
                "decodedShape": [SOURCE_GEOMETRY_POINT_COUNT],
                "decodedLabels": sorted(unique_hemispheres),
                "restrictedUnpickler": True,
            },
        ),
        "hemisphereLaterality": hemisphere_score,
        "checks": checks,
        "decision": {
            **decision_summary,
            "blockingReasons": ([] if passed else [HEMISPHERE_COVERAGE_REASON_CODE]),
            "qualifiedMapping": (
                {
                    "sourceOrder": ["ClearMap axis 0", "ClearMap axis 1", "ClearMap axis 2"],
                    "brainGlobeASROrder": ["AP", "DV", "ML"],
                    "permutation": [1, 0, 2],
                    "axisFlips": [False, False, False],
                    "mlOrigin": "right",
                    "mlIncreasingDirection": "left",
                }
                if passed
                else None
            ),
        },
    }


def canonical_report_bytes(report: Mapping[str, object]) -> bytes:
    """Serialize a report with stable key ordering and no environment paths."""

    return (
        json.dumps(
            report,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def write_canonical_report(path: str | Path, report: Mapping[str, object]) -> str:
    """Atomically write canonical JSON and return its SHA-256 digest."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_report_bytes(report)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()
