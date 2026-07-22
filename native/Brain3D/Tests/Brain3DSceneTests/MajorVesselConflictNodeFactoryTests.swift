import Brain3DCore
import Foundation
import simd
@testable import Brain3DScene
import Testing

@Suite("Selected 3D vessel-conflict geometry")
struct MajorVesselConflictNodeFactoryTests {
    @Test("Closest points, connector, and exact identified segment share depth testing")
    @MainActor
    func exactConflictGeometry() throws {
        let atlas = try atlasIdentity()
        let graph = try MajorVesselGraph(
            pointsASRMicrometres: [
                SIMD3(100, 200, 300),
                SIMD3(200, 200, 300),
                SIMD3(300, 200, 300),
            ],
            radiiMicrometres: [15, 20, 25],
            runOffsets: [0, 3],
            sourceEdgeIndices: [7],
            atlas: atlas,
            minimumIncludedDiameterMicrometres: 30
        )
        let conflict = try decodeConflict()
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 150,
            anchorDvMicrometres: 225,
            anchorMlMicrometres: 300
        )

        let selected = try #require(
            MajorVesselConflictNodeFactory.selectedSegment(for: conflict, in: graph)
        )
        #expect(selected.startASRMicrometres == SIMD3(100, 200, 300))
        #expect(selected.endASRMicrometres == SIMD3(200, 200, 300))
        #expect(selected.startRadiusMicrometres == 15)
        #expect(selected.endRadiusMicrometres == 20)

        let node = try MajorVesselConflictNodeFactory.makeNode(
            for: conflict,
            graph: graph,
            transform: transform
        )
        #expect(node.name == "selected-major-vessel-conflict")
        #expect(node.childNodes.count == 4)

        let probeGlyph = try #require(node.childNode(
            withName: "selected-conflict-probe-point",
            recursively: false
        ))
        let vesselGlyph = try #require(node.childNode(
            withName: "selected-conflict-vessel-point",
            recursively: false
        ))
        let connector = try #require(node.childNode(
            withName: "selected-conflict-closest-point-connector",
            recursively: false
        ))
        let segment = try #require(node.childNode(
            withName: "selected-conflict-vessel-segment",
            recursively: false
        ))
        let expectedProbePoint = try transform.scenePoint(
            apMicrometres: 150,
            dvMicrometres: 250,
            mlMicrometres: 300
        )
        let expectedVesselPoint = try transform.scenePoint(
            apMicrometres: 150,
            dvMicrometres: 200,
            mlMicrometres: 300
        )
        #expect(probeGlyph.simdPosition == expectedProbePoint)
        #expect(vesselGlyph.simdPosition == expectedVesselPoint)
        #expect(connector.geometry?.name == "selected-conflict-closest-point-connector")
        #expect(segment.geometry?.name == "selected-conflict-exact-vessel-segment")
        #expect(segment.geometry?.elements.first?.primitiveType == .triangles)
        #expect(segment.geometry?.elements.first?.primitiveCount == 12)
        #expect(segment.simdTransform == transform.sourceToSceneMatrix)

        let geometryNodes = node.childNodes(passingTest: { child, _ in
            child.geometry != nil
        })
        #expect(geometryNodes.count == 4)
        for geometryNode in geometryNodes {
            let material = try #require(geometryNode.geometry?.firstMaterial)
            #expect(material.readsFromDepthBuffer)
            #expect(material.writesToDepthBuffer)
            #expect(geometryNode.renderingOrder == 30)
        }
    }

    @Test("Stale graph identifiers or closest point never highlight another segment")
    @MainActor
    func rejectsUnsafeSegmentIdentity() throws {
        let atlas = try atlasIdentity()
        let graph = try MajorVesselGraph(
            pointsASRMicrometres: [SIMD3(100, 200, 300), SIMD3(200, 200, 300)],
            radiiMicrometres: [15, 20],
            runOffsets: [0, 2],
            sourceEdgeIndices: [7],
            atlas: atlas,
            minimumIncludedDiameterMicrometres: 30
        )
        let wrongEdge = try decodeConflict(overrides: ["vesselSourceEdgeIndex": 8])
        let stalePoint = try decodeConflict(overrides: [
            "vesselPoint": physicalPoint(ap: 300, dv: 200, ml: 300),
        ])
        #expect(MajorVesselConflictNodeFactory.selectedSegment(
            for: wrongEdge,
            in: graph
        ) == nil)
        #expect(MajorVesselConflictNodeFactory.selectedSegment(
            for: stalePoint,
            in: graph
        ) == nil)

        #expect(throws: AtlasSceneContractError.self) {
            try MajorVesselConflictNodeFactory.makeNode(
                for: wrongEdge,
                graph: graph,
                transform: try AtlasSceneTransform(
                    anchorApMicrometres: 150,
                    anchorDvMicrometres: 225,
                    anchorMlMicrometres: 300
                )
            )
        }
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
            "centerlineDistanceMicrometres": 50.0,
            "geometricSurfaceClearanceMicrometres": 0.0,
            "requiredMarginMicrometres": 100.0,
            "registrationUncertaintyMicrometres": 75.0,
            "adjustedClearanceMicrometres": -175.0,
            "probePoint": physicalPoint(ap: 150, dv: 250, ml: 300),
            "vesselPoint": physicalPoint(ap: 150, dv: 200, ml: 300),
            "insertionDepthMicrometres": 100.0,
            "sourceKind": "reference-individual-vessel-graph",
            "subjectSpecific": false,
            "warnings": ["Single-specimen reference only."],
        ]
        overrides.forEach { object[$0.key] = $0.value }
        return try JSONDecoder().decode(
            MajorVesselConflict.self,
            from: JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        )
    }

    private func physicalPoint(ap: Double, dv: Double, ml: Double) -> [String: Any] {
        [
            "frameId": AtlasPhysicalCoordinateFrame.expectedFrameId,
            "apMicrometres": ap,
            "dvMicrometres": dv,
            "mlMicrometres": ml,
        ]
    }

    private func atlasIdentity() throws -> ViewerAtlasIdentity {
        let object: [String: Any] = [
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
        return try JSONDecoder().decode(
            ViewerAtlasIdentity.self,
            from: JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        )
    }
}
