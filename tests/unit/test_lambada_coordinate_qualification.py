from __future__ import annotations

import hashlib
import json
import pickle
import struct
from pathlib import Path

import numpy as np
import pytest

import mouse_brain_planner.vasculature.lambada_coordinate_qualification as qualification
from mouse_brain_planner.vasculature.lambada_coordinate_qualification import (
    ATLAS_SHAPE_ASR,
    LambadaCoordinateQualificationError,
    RetainedSourceSelection,
    assess_pinned_source_coverage,
    canonical_report_bytes,
    load_graph_numpy_property,
    scan_gt_file,
    score_annotation_orientations,
    score_hemisphere_laterality,
    write_canonical_report,
)


def _u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def _gt_string(value: str) -> bytes:
    payload = value.encode("utf-8")
    return _u64(len(payload)) + payload


def _write_small_gt(path: Path, *, object_payload: bytes, trailing: bytes = b"") -> None:
    payload = bytearray(b"\xe2\x9b\xbe gt\x01\x00")
    payload.extend(_gt_string("qualification fixture"))
    payload.extend(b"\x00")  # undirected
    payload.extend(_u64(3))
    payload.extend(_u64(1) + b"\x01")
    payload.extend(_u64(1) + b"\x02")
    payload.extend(_u64(0))
    payload.extend(_u64(3))

    payload.extend(b"\x00")
    payload.extend(_gt_string("edge_geometry_hemisphere"))
    payload.extend(b"\x0e")
    payload.extend(_u64(len(object_payload)))
    payload.extend(object_payload)

    payload.extend(b"\x01")
    payload.extend(_gt_string("vertex_id"))
    payload.extend(b"\x02")
    payload.extend(struct.pack("<iii", 10, 11, 12))

    payload.extend(b"\x02")
    payload.extend(_gt_string("edge_geometry_indices"))
    payload.extend(b"\x0a")
    payload.extend(_u64(2) + struct.pack("<qq", 0, 2))
    payload.extend(_u64(2) + struct.pack("<qq", 2, 3))
    payload.extend(trailing)
    path.write_bytes(payload)


def _write_coverage_gt(path: Path) -> None:
    payload = bytearray(b"\xe2\x9b\xbe gt\x01\x00")
    payload.extend(_gt_string("coverage fixture"))
    payload.extend(b"\x00")
    payload.extend(_u64(3))
    payload.extend(_u64(1) + b"\x01")
    payload.extend(_u64(1) + b"\x02")
    payload.extend(_u64(0))
    payload.extend(_u64(1))
    payload.extend(b"\x01")
    payload.extend(_gt_string("coordinates_atlas"))
    payload.extend(b"\x0b")
    for coordinates in ((1.0, 2.0, 100.0), (3.0, 4.0, 227.0), (5.0, 6.0, 240.0)):
        payload.extend(_u64(3))
        payload.extend(struct.pack("<ddd", *coordinates))
    path.write_bytes(payload)


def test_scans_documented_gt_inventory_and_decodes_restricted_numpy_property(
    tmp_path: Path,
) -> None:
    hemisphere = np.array([255, 0, 255], dtype=np.int64)
    source = tmp_path / "fixture.gt"
    _write_small_gt(source, object_payload=pickle.dumps(hemisphere, protocol=4))

    inventory = scan_gt_file(source)

    assert inventory.byte_order == "little"
    assert not inventory.directed
    assert inventory.vertex_count == 3
    assert inventory.edge_count == 2
    assert [(record.kind, record.name, record.type_index) for record in inventory.properties] == [
        ("graph", "edge_geometry_hemisphere", 14),
        ("vertex", "vertex_id", 2),
        ("edge", "edge_geometry_indices", 10),
    ]
    record = inventory.properties[0]
    assert record.object_payload_size_bytes == len(pickle.dumps(hemisphere, protocol=4))
    decoded = load_graph_numpy_property(source, record, expected_shape=(3,))
    np.testing.assert_array_equal(decoded, hemisphere)
    assert not decoded.flags.writeable


def test_restricted_numpy_property_rejects_non_numpy_pickle_global(tmp_path: Path) -> None:
    source = tmp_path / "fixture.gt"
    _write_small_gt(source, object_payload=pickle.dumps(eval, protocol=4))
    record = scan_gt_file(source).properties[0]

    with pytest.raises(LambadaCoordinateQualificationError, match="not permitted"):
        load_graph_numpy_property(source, record, expected_shape=(3,))


def test_gt_scanner_rejects_unaccounted_trailing_bytes(tmp_path: Path) -> None:
    source = tmp_path / "fixture.gt"
    _write_small_gt(
        source,
        object_payload=pickle.dumps(np.array([0, 255, 0]), protocol=4),
        trailing=b"unexpected",
    )

    with pytest.raises(LambadaCoordinateQualificationError, match="exact file"):
        scan_gt_file(source)


def test_scores_all_flips_with_source_annotation_as_ancestor(tmp_path: Path) -> None:
    annotation_path = tmp_path / "annotation.raw"
    annotation = np.memmap(
        annotation_path,
        mode="w+",
        dtype=np.uint32,
        shape=ATLAS_SHAPE_ASR,
    )
    points = np.array(
        [
            [20.25, 40.5, 60.75],
            [21.25, 41.5, 61.75],
            [22.25, 42.5, 62.75],
            [23.25, 43.5, 63.75],
        ],
        dtype=np.float64,
    )
    source_ids = np.array([10, 10, 10, 10], dtype=np.int32)
    expected_asr = points[:, (1, 0, 2)].astype(np.int64)
    annotation[expected_asr[:, 0], expected_asr[:, 1], expected_asr[:, 2]] = 20
    annotation.flush()

    scores = score_annotation_orientations(
        points,
        source_ids,
        annotation,
        {10: frozenset({10}), 20: frozenset({10, 20})},
    )

    assert len(scores) == 8
    expected = next(score for score in scores if score["label"] == "AP_KEEP_DV_KEEP_ML_KEEP")
    assert expected["evaluablePointCount"] == 4
    assert expected["ancestorAgreement"] == {
        "numerator": 4,
        "denominator": 4,
        "decimal": "1.000000000",
    }
    alternatives = [score for score in scores if score is not expected]
    assert all(score["evaluablePointCount"] == 0 for score in alternatives)


def test_hemisphere_score_uses_right_origin_left_increasing_ml() -> None:
    points = np.array(
        [
            [10.0, 20.0, 0.0],
            [10.0, 20.0, 227.0],
            [10.0, 20.0, 228.0],
            [10.0, 20.0, 455.0],
        ]
    )
    source_labels = np.array([255, 255, 0, 0], dtype=np.int64)

    score = score_hemisphere_laterality(points, source_labels)

    assert score["keepAxis2Agreement"] == {
        "numerator": 4,
        "denominator": 4,
        "decimal": "1.000000000",
    }
    assert score["flipAxis2Agreement"] == {
        "numerator": 0,
        "denominator": 4,
        "decimal": "0.000000000",
    }


def test_canonical_report_writer_is_stable_and_atomic(tmp_path: Path) -> None:
    report = {"status": "rejected", "schemaVersion": 1, "nested": {"z": 2, "a": 1}}
    expected = b'{"nested":{"a":1,"z":2},"schemaVersion":1,"status":"rejected"}\n'
    output = tmp_path / "report.json"

    assert canonical_report_bytes(report) == expected
    digest = write_canonical_report(output, report)

    assert output.read_bytes() == expected
    assert digest == hashlib.sha256(expected).hexdigest()
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "rejected"


def test_source_coverage_does_not_promote_numerical_both_sides_to_whole_brain(
    tmp_path: Path,
) -> None:
    source = tmp_path / "coverage.gt"
    _write_coverage_gt(source)
    selection = RetainedSourceSelection(
        points_clearmap_voxel_f64=np.array(
            [[1.0, 2.0, 120.0], [3.0, 4.0, 235.0]], dtype=np.float64
        ),
        source_geometry_indices_i64=np.array([0, 1], dtype=np.int64),
        radii_um_f32=np.array([15.0, 15.0], dtype=np.float32),
        source_annotation_ids_i32=np.array([1, 1], dtype=np.int32),
        run_offsets_i64=np.array([0, 2], dtype=np.int64),
        source_edge_indices_i32=np.array([1], dtype=np.int32),
        qualifying_in_bounds_points=2,
        source_edges_with_runs=1,
    )

    report, check = assess_pinned_source_coverage(source, scan_gt_file(source), selection)

    assert report["status"] == "unqualified-for-whole-brain-use"
    assert report["numericalBothSidesDoNotProveWholeBrain"] is True
    assert report["bilateralMirroringQualified"] is False
    vertex_report = report["vertexCoordinatesAtlas"]
    assert isinstance(vertex_report, dict)
    assert vertex_report["axis2BelowMidlineCount"] == 2
    assert vertex_report["axis2AtOrAboveMidlineCount"] == 1
    assert check["passed"] is False


def test_committed_rejection_report_preserves_inventory_scores_and_blockers() -> None:
    report_path = (
        Path(qualification.__file__).parent.parent
        / "assets"
        / "vasculature"
        / "lambada_p60_606_coordinate_qualification_rejected_v1.json"
    )
    documentation_report_path = (
        Path(qualification.__file__).parents[3]
        / "docs"
        / "evidence"
        / "lambada_p60_606_coordinate_qualification_rejected_v1.json"
    )
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)

    assert hashlib.sha256(report_bytes).hexdigest() == (
        "0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a"
    )
    assert documentation_report_path.read_bytes() == report_bytes
    assert report["status"] == "rejected"
    assert report["source"] == {
        "filename": "606_graph_2024-12-03.gt",
        "sha256": "c2568cfbecd3f3eb720519be9d042f0cb41606741b8dd2f018bad1c54d36ef85",
        "sizeBytes": 12_282_574_483,
    }
    assert report["graphTool"]["propertyCount"] == 31
    assert len(report["graphTool"]["propertyInventory"]) == 31
    assert report["graphTool"]["hemisphereProperty"] is None
    assert len(report["annotationOrientation"]["scores"]) == 8
    assert report["retainedSelection"]["exactBundledAssetMatch"] is True
    assert report["retainedSelection"]["outputPoints"] == 71_313
    assert report["retainedSelection"]["outputRuns"] == 11_818
    assert report["sourceCoverage"]["bilateralMirroringQualified"] is False
    assert report["sourceCoverage"]["status"] == "unqualified-for-whole-brain-use"
    checks = {check["id"]: check["passed"] for check in report["checks"]}
    assert checks["ap-dv-sign-margin"] is True
    assert checks["source-hemisphere-property-present"] is False
    assert checks["source-coverage-whole-brain"] is False
    assert report["decision"]["qualifiedMapping"] is None
    assert report["decision"]["blockingReasons"] == [
        "SOURCE_HEMISPHERE_PROPERTY_MISSING",
        "SOURCE_SPECIMEN_COVERAGE_IS_HEMISPHERE",
    ]
