import AppKit
import Brain3DCore
import CryptoKit
import Foundation
import simd
@testable import Brain3DScene
import Testing

@Suite("Offscreen 3D mouse-atlas rendering")
struct SceneKitRenderSmokeTests {
    @Test("Verified OBJ and radius-bearing vessel graph render together")
    @MainActor
    func rendersPixels() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let meshResult = try decodeMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: [
                "frameId": AtlasSceneContract.physicalFrameId,
                "apMicrometres": 6_600.0,
                "dvMicrometres": 4_000.0,
                "mlMicrometres": 5_700.0,
            ]
        )
        let snapshot = try AnimalSceneSnapshot(
            projectId: "render-smoke-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil
        )
        let view = AtlasInteractiveSCNView(frame: CGRect(x: 0, y: 0, width: 320, height: 240))
        let controller = AnimalSceneController(view: view)
        var phase = AnimalScenePhase.idle

        await controller.apply(snapshot: snapshot) { phase = $0 }
        let brainOnlyBitmap = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        )
        let vesselGraph = try makeMajorVesselGraph(atlas: meshResult.atlas)
        let vesselMesh = try MajorVesselTubeMeshBuilder.build(
            pointsASRMicrometres: vesselGraph.pointsASRMicrometres,
            radiiMicrometres: vesselGraph.radiiMicrometres,
            runOffsets: vesselGraph.runOffsets
        )
        let vesselNode = MajorVesselNodeFactory.makeNode(
            mesh: vesselMesh,
            transform: snapshot.transform
        )
        let vesselLayer = try #require(
            view.scene?.rootNode.childNode(
                withName: "reviewed-major-vessel-layer",
                recursively: false
            )
        )
        vesselLayer.addChildNode(vesselNode)

        let image = controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        let bitmap = try bitmap(from: image)
        let data = try #require(bitmap.bitmapData)
        let bytes = UnsafeBufferPointer(
            start: data,
            count: bitmap.bytesPerRow * bitmap.pixelsHigh
        )

        #expect(phase == .ready)
        #expect(vesselGraph.pointCount == 3)
        #expect(vesselGraph.runCount == 1)
        #expect(vesselGraph.segmentCount == 2)
        #expect(vesselNode.parent === vesselLayer)
        #expect(vesselNode.geometry?.name == "radius-bearing-reference-major-vessels")
        #expect(vesselNode.geometry?.elements.first?.primitiveType == .triangles)
        #expect(vesselNode.geometry?.elements.first?.primitiveCount == 24)
        #expect(vesselNode.renderingOrder == 20)
        #expect(vesselNode.opacity == 1)
        let vesselMaterial = try #require(vesselNode.geometry?.firstMaterial)
        #expect(vesselMaterial.lightingModel == .constant)
        #expect(vesselMaterial.readsFromDepthBuffer)
        #expect(vesselMaterial.writesToDepthBuffer)
        let importedBrainRoot = try #require(
            view.scene?.rootNode.childNode(withName: "verified-atlas-obj", recursively: true)
        )
        let brainNode = try #require(
            importedBrainRoot.childNodes(passingTest: { node, _ in
                node.geometry != nil
            }).first
        )
        let brainMaterial = try #require(brainNode.geometry?.firstMaterial)
        #expect(brainNode.renderingOrder == -10_000)
        #expect(abs(brainNode.opacity - 0.28) < 0.0001)
        #expect(brainMaterial.lightingModel == .constant)
        #expect(abs(brainMaterial.transparency - 0.65) < 0.0001)
        #expect(brainMaterial.transparencyMode == .singleLayer)
        #expect(!brainMaterial.readsFromDepthBuffer)
        #expect(!brainMaterial.writesToDepthBuffer)
        #expect(bytes.min() != bytes.max())
        #expect(visibleVesselPixelCount(brainOnlyBitmap) == 0)
        #expect(visibleVesselPixelCount(bitmap) >= 20)
    }

    @Test("Snapshot requires current vessel geometry before accepting a selected conflict")
    func selectedConflictSnapshotContract() throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let meshResult = try decodeMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let conflict = try decodeConflict()
        let withoutConflict = try AnimalSceneSnapshot(
            projectId: "render-smoke-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil
        )
        #expect(throws: AtlasSceneContractError.self) {
            _ = try AnimalSceneSnapshot(
                projectId: "render-smoke-project",
                projectRevision: 1,
                rendererAnchor: anchor,
                meshResult: meshResult,
                selectedProbePlan: nil,
                selectedVesselConflict: conflict
            )
        }
        #expect(withoutConflict.selectedVesselConflict == nil)
        try AnimalSceneSnapshot.validateSelectedVesselConflict(
            conflict,
            bounds: meshResult.sourceCoordinateFrame.bounds,
            selectedProbeShankIds: ["shank-1"]
        )
        #expect(throws: AtlasSceneContractError.self) {
            try AnimalSceneSnapshot.validateSelectedVesselConflict(
                conflict,
                bounds: meshResult.sourceCoordinateFrame.bounds,
                selectedProbeShankIds: ["another-shank"]
            )
        }

        let outOfBounds = try decodeConflict(overrides: [
            "vesselPoint": physicalPoint(ap: 13_200, dv: 4_000, ml: 5_700),
        ])
        #expect(throws: AtlasSceneContractError.self) {
            try AnimalSceneSnapshot.validateSelectedVesselConflict(
                outOfBounds,
                bounds: meshResult.sourceCoordinateFrame.bounds,
                selectedProbeShankIds: ["shank-1"]
            )
        }
    }

    private func bitmap(from image: NSImage) throws -> NSBitmapImageRep {
        let tiff = try #require(image.tiffRepresentation)
        return try #require(NSBitmapImageRep(data: tiff))
    }

    private func makeMajorVesselGraph(atlas: ViewerAtlasIdentity) throws -> MajorVesselGraph {
        try MajorVesselGraph(
            pointsASRMicrometres: [
                SIMD3(6_100, 4_000, 5_700),
                SIMD3(6_600, 4_000, 5_700),
                SIMD3(7_100, 4_000, 5_700),
            ],
            radiiMicrometres: [220, 260, 220],
            runOffsets: [0, 3],
            sourceEdgeIndices: [0],
            atlas: atlas,
            minimumIncludedDiameterMicrometres:
                MajorVesselContract.minimumIncludedDiameterMicrometres
        )
    }

    private func visibleVesselPixelCount(_ bitmap: NSBitmapImageRep) -> Int {
        var count = 0
        for y in 0 ..< bitmap.pixelsHigh {
            for x in 0 ..< bitmap.pixelsWide {
                guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB)
                else { continue }
                if color.redComponent > 0.45,
                   color.redComponent > color.greenComponent * 1.5,
                   color.redComponent > color.blueComponent * 1.3
                {
                    count += 1
                }
            }
        }
        return count
    }

    private func decodeConflict(
        overrides: [String: Any] = [:]
    ) throws -> MajorVesselConflict {
        var object: [String: Any] = [
            "conflictId": "shank-1:edge-7:run-0:segment-0",
            "shankId": "shank-1",
            "vesselSourceEdgeIndex": 7,
            "vesselRunIndex": 0,
            "vesselSegmentIndexInRun": 0,
            "classification": "intersection",
            "vesselDiameterMicrometres": 30.0,
            "probeEnvelopeRadiusMicrometres": 35.0,
            "centerlineDistanceMicrometres": 200.0,
            "geometricSurfaceClearanceMicrometres": 150.0,
            "requiredMarginMicrometres": 100.0,
            "registrationUncertaintyMicrometres": 75.0,
            "adjustedClearanceMicrometres": -25.0,
            "probePoint": physicalPoint(ap: 6_600, dv: 3_900, ml: 5_700),
            "vesselPoint": physicalPoint(ap: 6_600, dv: 4_100, ml: 5_700),
            "insertionDepthMicrometres": 100.0,
            "sourceKind": "reference-individual-vessel-graph",
            "subjectSpecific": false,
            "warnings": ["Single-specimen reference only."],
        ]
        overrides.forEach { object[$0.key] = $0.value }
        return try decode(MajorVesselConflict.self, object: object)
    }

    private func physicalPoint(ap: Double, dv: Double, ml: Double) -> [String: Any] {
        [
            "frameId": AtlasPhysicalCoordinateFrame.expectedFrameId,
            "apMicrometres": ap,
            "dvMicrometres": dv,
            "mlMicrometres": ml,
        ]
    }

    private func makeFixture() throws -> (
        root: URL,
        obj: URL,
        sha256: String,
        byteSize: Int
    ) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("brain3d-render-\(UUID().uuidString)", isDirectory: true)
        let meshes = root.appendingPathComponent("meshes", isDirectory: true)
        try FileManager.default.createDirectory(at: meshes, withIntermediateDirectories: true)
        let obj = meshes.appendingPathComponent("997.obj")
        let data = Data(
            """
            o brain
            v 1800 1600 1600
            v 11400 1600 1600
            v 11400 6400 1600
            v 1800 6400 1600
            v 1800 1600 9800
            v 11400 1600 9800
            v 11400 6400 9800
            v 1800 6400 9800
            f 1 2 3
            f 1 3 4
            f 5 8 7
            f 5 7 6
            f 1 5 6
            f 1 6 2
            f 2 6 7
            f 2 7 3
            f 3 7 8
            f 3 8 4
            f 5 1 4
            f 5 4 8
            """.utf8
        )
        try data.write(to: obj, options: .atomic)
        let sha = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return (root.standardizedFileURL, obj.standardizedFileURL, sha, data.count)
    }

    private func decodeMeshResult(
        fixture: (root: URL, obj: URL, sha256: String, byteSize: Int)
    ) throws -> AtlasMeshResult {
        try decode(
            AtlasMeshResult.self,
            object: [
                "protocolVersion": 1,
                "target": "root",
                "region": NSNull(),
                "mesh": [
                    "canonicalPath": fixture.obj.path,
                    "atlasRootCanonicalPath": fixture.root.path,
                    "pathUnderAtlasRoot": "meshes/997.obj",
                    "sha256": fixture.sha256,
                    "byteSize": fixture.byteSize,
                    "fileExtension": ".obj",
                    "contentsIncluded": false,
                ],
                "sourceCoordinateFrame": coordinateFrame(),
                "atlas": atlas(),
            ]
        )
    }

    private func decode<T: Decodable>(_ type: T.Type, object: Any) throws -> T {
        try JSONDecoder().decode(
            type,
            from: JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        )
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
}
