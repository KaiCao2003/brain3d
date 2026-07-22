import Brain3DCore
@testable import Brain3DScene
@preconcurrency import SceneKit
import simd
import Testing

@Suite("Selected probe conservative envelope")
struct ProbeEnvelopeNodeFactoryTests {
    @Test("Cylinder preserves physical midpoint, length, direction, and radius")
    @MainActor
    func cylinderGeometry() throws {
        let entry = ProbePhysicalPoint(
            apMicrometres: 0,
            dvMicrometres: 0,
            mlMicrometres: 0
        )
        let tip = ProbePhysicalPoint(
            apMicrometres: 1_000,
            dvMicrometres: 0,
            mlMicrometres: 0
        )
        let shank = ProbePlacedShank(
            shankId: "shank-1",
            entry: entry,
            tip: tip,
            widthMicrometres: 80,
            thicknessMicrometres: 40,
            conservativeEnvelopeRadiusMicrometres: 50,
            envelopeDefinition: "circumscribed conservative test envelope"
        )
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 0,
            anchorDvMicrometres: 0,
            anchorMlMicrometres: 0
        )

        let root = try ProbeEnvelopeNodeFactory.makeNode(
            for: [shank],
            usableForNavigation: false,
            transform: transform
        )
        let node = try #require(root.childNodes.first)
        let cylinder = try #require(node.geometry as? SCNCylinder)

        #expect(abs(cylinder.height - 1) < 0.000_001)
        #expect(abs(cylinder.radius - 0.05) < 0.000_001)
        #expect(simd_distance(node.simdPosition, SIMD3<Float>(0, 0, 0.5)) < 0.000_001)
        let renderedAxis = node.simdOrientation.act(SIMD3<Float>(0, 1, 0))
        #expect(simd_distance(renderedAxis, SIMD3<Float>(0, 0, 1)) < 0.000_001)
        #expect(node.categoryBitMask == SceneCategory.probe.rawValue)
    }

    @Test("Zero-length physical geometry fails closed")
    @MainActor
    func zeroLengthRejected() throws {
        let point = ProbePhysicalPoint(
            apMicrometres: 100,
            dvMicrometres: 200,
            mlMicrometres: 300
        )
        let shank = ProbePlacedShank(
            shankId: "shank-1",
            entry: point,
            tip: point,
            widthMicrometres: 80,
            thicknessMicrometres: 40,
            conservativeEnvelopeRadiusMicrometres: 50,
            envelopeDefinition: "invalid zero-length test envelope"
        )
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 0,
            anchorDvMicrometres: 0,
            anchorMlMicrometres: 0
        )

        #expect(throws: AtlasSceneContractError.self) {
            try ProbeEnvelopeNodeFactory.makeNode(
                for: [shank],
                usableForNavigation: false,
                transform: transform
            )
        }
    }
}
