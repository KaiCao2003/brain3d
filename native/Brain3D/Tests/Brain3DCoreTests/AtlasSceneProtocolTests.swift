import Brain3DCore
import Foundation
import Testing

@Suite("Strict 3D atlas bridge protocol")
struct AtlasSceneProtocolTests {
    @Test("Mesh and ray requests use only the reviewed protocol fields")
    func requestShapes() throws {
        let meshData = try JSONEncoder().encode(try AtlasMeshParameters())
        let mesh = try #require(JSONSerialization.jsonObject(with: meshData) as? [String: Any])
        #expect(Set(mesh.keys) == Set(["protocolVersion", "target"]))
        #expect(mesh["target"] as? String == "root")

        let start = try AtlasRayPoint(
            apMicrometres: -10,
            dvMicrometres: 20,
            mlMicrometres: 30
        )
        let end = try AtlasRayPoint(
            apMicrometres: 100,
            dvMicrometres: 20,
            mlMicrometres: 30
        )
        let rayData = try JSONEncoder().encode(
            try AtlasRayPickParameters(start: start, end: end)
        )
        let ray = try #require(JSONSerialization.jsonObject(with: rayData) as? [String: Any])
        #expect(Set(ray.keys) == Set([
            "protocolVersion", "frameId",
            "startApMicrometres", "startDvMicrometres", "startMlMicrometres",
            "endApMicrometres", "endDvMicrometres", "endMlMicrometres",
        ]))
        #expect(ray["frameId"] as? String == AtlasSceneContract.physicalFrameId)
    }

    @Test("Verified root mesh descriptor and provenance decode together")
    func meshDecoding() throws {
        let result = try decode(AtlasMeshResult.self, object: meshPayload())

        #expect(result.target == .root)
        #expect(result.region == nil)
        #expect(result.mesh.pathUnderAtlasRoot == "meshes/997.obj")
        #expect(result.mesh.byteSize == 4_728_758)
        #expect(result.atlas.shapeVoxels.apVoxels == 528)
    }

    @Test("Mesh payload fails closed on path escape, extra fields, or target mismatch")
    func invalidMeshPayloads() throws {
        var escaped = meshPayload()
        var escapedDescriptor = try #require(escaped["mesh"] as? [String: Any])
        escapedDescriptor["pathUnderAtlasRoot"] = "../outside.obj"
        escaped["mesh"] = escapedDescriptor
        #expect(throws: Error.self) {
            try decode(AtlasMeshResult.self, object: escaped)
        }

        var extra = meshPayload()
        extra["contents"] = "not-allowed"
        #expect(throws: Error.self) {
            try decode(AtlasMeshResult.self, object: extra)
        }

        var mismatched = meshPayload()
        mismatched["target"] = "region"
        #expect(throws: Error.self) {
            try decode(AtlasMeshResult.self, object: mismatched)
        }
    }

    @Test("Ray hit locks algorithm, annotation, region, and physical frame")
    func rayHitDecoding() throws {
        let result = try decode(AtlasRayPickResult.self, object: rayPayload(hit: true))
        let hit = try #require(result.hit)

        #expect(result.status == .hit)
        #expect(result.algorithmVersion == AtlasSceneContract.rayPickAlgorithmVersion)
        #expect(hit.annotationStructureId == hit.region.structureId)
        #expect(hit.region.acronym == "VISp")
        #expect(hit.hemisphere == .right)
        #expect(hit.containingVoxelIndex.ap == 1)
    }

    @Test("No-hit and hit status cannot contradict the optional payload")
    func rayStatusConsistency() throws {
        let noHit = try decode(AtlasRayPickResult.self, object: rayPayload(hit: false))
        #expect(noHit.status == .noAnnotatedVoxel)
        #expect(noHit.hit == nil)

        var inconsistent = rayPayload(hit: false)
        inconsistent["status"] = "hit"
        #expect(throws: Error.self) {
            try decode(AtlasRayPickResult.self, object: inconsistent)
        }
    }

    @Test("Project state carries the persisted renderer anchor")
    func projectRendererAnchor() throws {
        let project: [String: Any] = [
            "projectId": "project-1",
            "title": "Animal plan",
            "subjectId": NSNull(),
            "path": NSNull(),
            "requiresSaveAs": true,
            "recoveredFromBackup": false,
            "schemaVersion": 4,
            "revision": 2,
            "isDirty": true,
            "animalResearchOnlyAcknowledged": true,
            "calibrationCount": 1,
            "activeCalibrationId": NSNull(),
            "probePlanCount": 0,
            "probeRegionAnalysisCount": 0,
            "rendererAnchor": point(ap: 6_612.5, dv: 4_012.5, ml: 5_712.5),
        ]
        let result = try decode(ProjectBridgeState.self, object: project)

        #expect(result.rendererAnchor?.apMicrometres == 6_612.5)
        #expect(result.rendererAnchor?.dvMicrometres == 4_012.5)
        #expect(result.rendererAnchor?.mlMicrometres == 5_712.5)
    }

    private func decode<T: Decodable>(_ type: T.Type, object: Any) throws -> T {
        try JSONDecoder().decode(
            type,
            from: JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        )
    }

    private func meshPayload() -> [String: Any] {
        [
            "protocolVersion": 1,
            "target": "root",
            "region": NSNull(),
            "mesh": [
                "canonicalPath": "/tmp/allen-atlas/meshes/997.obj",
                "atlasRootCanonicalPath": "/tmp/allen-atlas",
                "pathUnderAtlasRoot": "meshes/997.obj",
                "sha256": String(repeating: "b", count: 64),
                "byteSize": 4_728_758,
                "fileExtension": ".obj",
                "contentsIncluded": false,
            ],
            "sourceCoordinateFrame": coordinateFrame(),
            "atlas": atlas(),
        ]
    }

    private func rayPayload(hit: Bool) -> [String: Any] {
        [
            "protocolVersion": 1,
            "status": hit ? "hit" : "noAnnotatedVoxel",
            "algorithmVersion": AtlasSceneContract.rayPickAlgorithmVersion,
            "hit": hit ? [
                "entryPoint": point(ap: 25, dv: 50, ml: 75),
                "voxelCenter": point(ap: 37.5, dv: 62.5, ml: 87.5),
                "containingVoxelIndex": [
                    "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
                    "ap": 1,
                    "dv": 2,
                    "ml": 3,
                ],
                "annotationStructureId": 385,
                "region": region(),
                "hemisphere": "right",
                "distanceFromRayStartMicrometres": 100.0,
                "distanceInsideVoxelMicrometres": 25.0,
            ] : NSNull(),
            "coordinateFrame": coordinateFrame(),
            "atlas": atlas(),
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

    private func coordinateFrame() -> [String: Any] {
        [
            "frameId": AtlasSceneContract.physicalFrameId,
            "unit": "micrometres",
            "coordinateKind": "continuousPhysical",
            "axisOrder": ["AP", "DV", "ML"],
            "origin": ["anterior", "superior", "right"],
            "positiveDirections": ["posterior", "inferior", "left"],
            "axes": [
                axis(0, "AP", "anterior", "posterior"),
                axis(1, "DV", "superior", "inferior"),
                axis(2, "ML", "right", "left"),
            ],
            "bregmaRelative": false,
            "stereotaxicCalibrationApplied": false,
            "voxelAnchorOffsetApplied": false,
            "bounds": [
                "minimumInclusiveMicrometres": [0.0, 0.0, 0.0],
                "maximumExclusiveMicrometres": [13_200.0, 8_000.0, 11_400.0],
            ],
        ]
    }

    private func axis(
        _ index: Int,
        _ anatomical: String,
        _ origin: String,
        _ positive: String
    ) -> [String: Any] {
        [
            "arrayAxis": index,
            "anatomicalAxis": anatomical,
            "originDirection": origin,
            "positiveDirection": positive,
            "voxelSizeMicrometres": 25.0,
        ]
    }

    private func point(ap: Double, dv: Double, ml: Double) -> [String: Any] {
        [
            "frameId": AtlasSceneContract.physicalFrameId,
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
}
