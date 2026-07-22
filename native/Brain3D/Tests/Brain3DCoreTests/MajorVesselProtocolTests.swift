import Brain3DCore
import CryptoKit
import Foundation
import Testing

@Suite("Pinned major-vessel protocol")
struct MajorVesselProtocolTests {
    @Test("Exact binary geometry decodes with pinned provenance")
    func validGeometry() throws {
        let payload = try geometryPayload()
        let result = try JSONDecoder().decode(MajorVesselGeometryResult.self, from: payload)

        #expect(result.pointCount == MajorVesselContract.expectedPointCount)
        #expect(result.runCount == MajorVesselContract.expectedRunCount)
        #expect(result.segmentCount == MajorVesselContract.expectedSegmentCount)
        #expect(result.graph.pointsASRMicrometres[0] == SIMD3<Float>(0.5, 0.5, 0.5))
        #expect(result.graph.radiiMicrometres[0] == 15.25)
        #expect(result.graph.runOffsets.first == 0)
        #expect(result.graph.runOffsets.last == MajorVesselContract.expectedPointCount)
        #expect(result.provenance.derivedAssetSha256 == MajorVesselContract.derivedAssetSHA256)
        #expect(result.limitations.contains(where: {
            $0.localizedCaseInsensitiveContains("pial")
        }))
    }

    @Test("Every buffer SHA-256 is enforced before publication")
    func corruptBufferDigest() throws {
        var object = try #require(
            JSONSerialization.jsonObject(with: geometryPayload()) as? [String: Any]
        )
        var points = try #require(object["pointsASRMicrometres"] as? [String: Any])
        points["sha256"] = String(repeating: "0", count: 64)
        object["pointsASRMicrometres"] = points
        let corrupted = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])

        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(MajorVesselGeometryResult.self, from: corrupted)
        }
    }

    @Test("A legacy calibration claim is rejected rather than ignored")
    func rejectsLegacyScaleClaim() throws {
        var object = try #require(
            JSONSerialization.jsonObject(with: geometryPayload()) as? [String: Any]
        )
        var provenance = try #require(object["provenance"] as? [String: Any])
        provenance.removeValue(forKey: "physicalUnitsDeclared")
        provenance["physicalScaleCalibrated"] = true
        object["provenance"] = provenance
        let legacy = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])

        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(MajorVesselGeometryResult.self, from: legacy)
        }
    }

    @Test("Slice overlay includes only radius-bearing geometry touching the slab")
    func radiusBearingSlab() throws {
        let atlas = try atlasIdentity()
        let graph = try MajorVesselGraph(
            pointsASRMicrometres: [
                SIMD3(60, 25, 25), SIMD3(60, 75, 25),
                SIMD3(70, 25, 50), SIMD3(70, 75, 50),
            ],
            radiiMicrometres: [15, 15, 15, 15],
            runOffsets: [0, 2, 4],
            sourceEdgeIndices: [11, 12],
            atlas: atlas,
            minimumIncludedDiameterMicrometres: 30
        )

        let overlay = MajorVesselSliceOverlayGeometry.make(
            graph: graph,
            atlas: atlas,
            assetSHA256: MajorVesselContract.derivedAssetSHA256,
            orientation: .coronal,
            sliceIndex: 1
        )

        #expect(overlay.segments.count == 1)
        #expect(overlay.segments[0].sourceEdgeIndex == 11)
        #expect(overlay.segments[0].start == ProbeSliceImagePoint(column: 1, row: 1))
        #expect(overlay.segments[0].end == ProbeSliceImagePoint(column: 1, row: 3))
    }

    @Test("Dorsal projection preserves every path and physical radius")
    func dorsalProjection() throws {
        let atlas = try atlasIdentity()
        let graph = try MajorVesselGraph(
            pointsASRMicrometres: [SIMD3(25, 100, 50), SIMD3(75, 200, 100)],
            radiiMicrometres: [15, 21],
            runOffsets: [0, 2],
            sourceEdgeIndices: [9],
            atlas: atlas,
            minimumIncludedDiameterMicrometres: 30
        )

        let overlay = MajorVesselSliceOverlayGeometry.makeDorsalProjection(
            graph: graph,
            atlas: atlas,
            assetSHA256: MajorVesselContract.derivedAssetSHA256
        )

        #expect(overlay.segments.count == 1)
        #expect(overlay.segments[0].start == ProbeSliceImagePoint(column: 2, row: 1))
        #expect(overlay.segments[0].end == ProbeSliceImagePoint(column: 4, row: 3))
        #expect(overlay.segments[0].startRadiusMicrometres == 15)
        #expect(overlay.segments[0].endRadiusMicrometres == 21)
    }

    private func geometryPayload() throws -> Data {
        let pointCount = MajorVesselContract.expectedPointCount
        let runCount = MajorVesselContract.expectedRunCount
        var pointScalars: [Float] = []
        pointScalars.reserveCapacity(pointCount * 3)
        for index in 0 ..< pointCount {
            pointScalars.append(Float(index % 528) * 25 + 0.5)
            pointScalars.append(Float((index / 528) % 320) * 25 + 0.5)
            pointScalars.append(Float((index / (528 * 320)) % 456) * 25 + 0.5)
        }
        let radii = [Float](repeating: 15.25, count: pointCount)
        var offsets = [Int64](repeating: 0, count: runCount + 1)
        let longerRunCount = pointCount - runCount * 6
        var cursor = 0
        for run in 0 ..< runCount {
            cursor += run < longerRunCount ? 7 : 6
            offsets[run + 1] = Int64(cursor)
        }
        let edges = (0 ..< runCount).map(Int32.init)
        let object: [String: Any] = [
            "protocolVersion": 1,
            "status": "ready",
            "encoding": "contiguous-little-endian-v1",
            "pointCount": pointCount,
            "runCount": runCount,
            "segmentCount": MajorVesselContract.expectedSegmentCount,
            "pointsASRMicrometres": buffer(float32: pointScalars, shape: [pointCount, 3]),
            "radiiMicrometres": buffer(float32: radii, shape: [pointCount]),
            "runOffsets": buffer(int64: offsets, shape: [runCount + 1]),
            "sourceEdgeIndices": buffer(int32: edges, shape: [runCount]),
            "provenance": provenanceObject,
            "limitations": [
                "Single cleared reference; not subject-specific anatomy.",
                "Pial and choroidal vessels are excluded.",
            ],
            "atlas": atlasObject,
        ]
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    private func atlasIdentity() throws -> ViewerAtlasIdentity {
        let data = try JSONSerialization.data(withJSONObject: atlasObject, options: [.sortedKeys])
        return try JSONDecoder().decode(ViewerAtlasIdentity.self, from: data)
    }

    private var atlasObject: [String: Any] {
        [
            "identifier": "allen_mouse_25um",
            "version": "1.2",
            "metadataSha256": String(repeating: "a", count: 64),
            "resolutionMicrometres": [25, 25, 25],
            "shapeVoxels": [528, 320, 456],
            "orientation": "asr",
            "frameworkName": "Allen CCFv3",
            "sourceAnnotation": "annotation/ccf_2017",
            "citation": "Allen mouse atlas",
            "brainGlobeAtlasApiVersion": "2.3.1",
        ]
    }

    private var provenanceObject: [String: Any] {
        [
            "sourceId": MajorVesselContract.sourceId,
            "sourceKind": "reference-individual-vessel-graph",
            "datasetTitle": "Vascular graphs of the developing post-natal mouse brain",
            "authors": ["Nicolas Renier", "Elisa de Launoit", "Sophie Skriabine"],
            "specimenId": MajorVesselContract.specimenId,
            "sourceDoi": MajorVesselContract.sourceDoi,
            "sourceRecordUrl": MajorVesselContract.sourceRecordURL,
            "sourcePaperDoi": MajorVesselContract.sourcePaperDoi,
            "sourceVersion": "P60_606 / 606_graph_2024-12-03.gt",
            "sourceLicense": "CC BY 4.0",
            "sourceArchiveDigest": MajorVesselContract.sourceArchiveDigest,
            "derivedAssetSha256": MajorVesselContract.derivedAssetSHA256,
            "extractionAlgorithmVersion": MajorVesselContract.extractionAlgorithmVersion,
            "atlasIdentifier": "allen_mouse_25um",
            "atlasVersion": "1.2",
            "coordinateFrameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
            "minimumIncludedDiameterMicrometres": 30,
            "physicalUnitsDeclared": true,
            "atlasScaleApplied": true,
            "geometrySourceAudited": true,
            "subjectSpecific": false,
            "pialVesselsExcluded": true,
            "choroidalVesselsExcluded": true,
            "arteryVeinClassificationAvailable": false,
        ]
    }

    private func buffer(float32 values: [Float], shape: [Int]) -> [String: Any] {
        var data = Data(capacity: values.count * 4)
        for value in values {
            var bits = value.bitPattern.littleEndian
            withUnsafeBytes(of: &bits) { data.append(contentsOf: $0) }
        }
        return bufferObject(data: data, scalarType: "float32", shape: shape)
    }

    private func buffer(int64 values: [Int64], shape: [Int]) -> [String: Any] {
        var data = Data(capacity: values.count * 8)
        for value in values {
            var encoded = value.littleEndian
            withUnsafeBytes(of: &encoded) { data.append(contentsOf: $0) }
        }
        return bufferObject(data: data, scalarType: "int64", shape: shape)
    }

    private func buffer(int32 values: [Int32], shape: [Int]) -> [String: Any] {
        var data = Data(capacity: values.count * 4)
        for value in values {
            var encoded = value.littleEndian
            withUnsafeBytes(of: &encoded) { data.append(contentsOf: $0) }
        }
        return bufferObject(data: data, scalarType: "int32", shape: shape)
    }

    private func bufferObject(
        data: Data,
        scalarType: String,
        shape: [Int]
    ) -> [String: Any] {
        [
            "scalarType": scalarType,
            "byteOrder": "littleEndian",
            "shape": shape,
            "byteLength": data.count,
            "sha256": SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(),
            "dataBase64": data.base64EncodedString(),
        ]
    }
}
