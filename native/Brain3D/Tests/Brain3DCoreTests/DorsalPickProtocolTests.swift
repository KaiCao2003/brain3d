import Brain3DCore
import Foundation
import Testing

@Suite("Strict dorsal atlas picking protocol")
struct DorsalPickProtocolTests {
    @Test("Request contains only protocol version and intrinsic AP/ML pixel coordinates")
    func requestShape() throws {
        let data = try JSONEncoder().encode(try DorsalPickParameters(column: 200, row: 100))
        let object = try #require(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        #expect(Set(object.keys) == ["protocolVersion", "column", "row"])
        #expect(object["protocolVersion"] as? Int == 1)
        #expect(object["column"] as? Int == 200)
        #expect(object["row"] as? Int == 100)
        #expect(throws: Error.self) {
            try DorsalPickParameters(column: -1, row: 0)
        }
    }

    @Test("Hit identifies the dorsal-most annotated voxel in the clicked atlas column")
    func hitDecoding() throws {
        let result = try decode(payload(hit: true))

        #expect(result.status == .hit)
        #expect(result.column == 200)
        #expect(result.row == 100)
        #expect(result.containingVoxelIndex?.ap == 100)
        #expect(result.containingVoxelIndex?.dv == 7)
        #expect(result.containingVoxelIndex?.ml == 200)
        #expect(result.annotationStructureId == 385)
        #expect(result.region?.acronym == "VISp")
        #expect(result.hemisphere == .right)
    }

    @Test("Unannotated columns carry no fabricated anatomical metadata")
    func noHitDecoding() throws {
        let result = try decode(payload(hit: false))

        #expect(result.status == .noAnnotatedVoxel)
        #expect(result.atlasPoint == nil)
        #expect(result.containingVoxelIndex == nil)
        #expect(result.annotationStructureId == nil)
        #expect(result.region == nil)
        #expect(result.hemisphere == nil)
    }

    @Test("Unexpected fields and inconsistent voxel or status metadata fail closed")
    func invalidPayloads() throws {
        var extra = payload(hit: true)
        extra["surfaceGuess"] = true
        #expect(throws: Error.self) { try decode(extra) }

        var wrongColumn = payload(hit: true)
        var voxel = try #require(wrongColumn["containingVoxelIndex"] as? [String: Any])
        voxel["ml"] = 201
        wrongColumn["containingVoxelIndex"] = voxel
        #expect(throws: Error.self) { try decode(wrongColumn) }

        var wrongPoint = payload(hit: true)
        var point = try #require(wrongPoint["atlasPoint"] as? [String: Any])
        point["dvMicrometres"] = 200.0
        wrongPoint["atlasPoint"] = point
        #expect(throws: Error.self) { try decode(wrongPoint) }

        var fabricatedNoHit = payload(hit: true)
        fabricatedNoHit["status"] = "noAnnotatedVoxel"
        #expect(throws: Error.self) { try decode(fabricatedNoHit) }
    }

    private func decode(_ object: [String: Any]) throws -> DorsalPickResult {
        try JSONDecoder().decode(
            DorsalPickResult.self,
            from: JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        )
    }

    private func payload(hit: Bool) -> [String: Any] {
        [
            "protocolVersion": 1,
            "status": hit ? "hit" : "noAnnotatedVoxel",
            "column": 200,
            "row": 100,
            "atlasPoint": hit ? point(ap: 2_512.5, dv: 187.5, ml: 5_012.5) : NSNull(),
            "containingVoxelIndex": hit ? [
                "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
                "ap": 100,
                "dv": 7,
                "ml": 200,
            ] : NSNull(),
            "annotationStructureId": hit ? 385 : NSNull(),
            "region": hit ? region() : NSNull(),
            "hemisphere": hit ? "right" : NSNull(),
            "atlas": atlas(),
        ]
    }

    private func point(ap: Double, dv: Double, ml: Double) -> [String: Any] {
        [
            "frameId": AtlasPhysicalCoordinateFrame.expectedFrameId,
            "apMicrometres": ap,
            "dvMicrometres": dv,
            "mlMicrometres": ml,
        ]
    }

    private func region() -> [String: Any] {
        [
            "structureId": 385,
            "acronym": "VISp",
            "name": "Primary visual area",
            "parentStructureId": 315,
            "structureIdPath": [997, 8, 567, 688, 695, 315, 385],
            "rgb": [8, 133, 140],
        ]
    }

    private func atlas() -> [String: Any] {
        [
            "identifier": "allen_mouse_25um",
            "version": "1.2",
            "metadataSha256": String(repeating: "a", count: 64),
            "resolutionMicrometres": [25.0, 25.0, 25.0],
            "shapeVoxels": [528, 320, 456],
            "orientation": "asr",
            "frameworkName": "brainglobe-atlasapi",
            "sourceAnnotation": "annotation.tiff",
            "citation": "Allen Mouse Brain Common Coordinate Framework",
            "brainGlobeAtlasApiVersion": "2.3.0",
        ]
    }
}
