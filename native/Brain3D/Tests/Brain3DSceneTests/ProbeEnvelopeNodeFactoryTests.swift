import Brain3DCore
@testable import Brain3DScene
@preconcurrency import SceneKit
import simd
import Testing

@Suite("Selected probe conservative envelope")
struct ProbeEnvelopeNodeFactoryTests {
    @Test("NP2003 and NP2013 enforce their exact 3D shank cardinality")
    @MainActor
    func directProductShankCardinality() throws {
        let single = placedShanks(layoutRotationDegrees: 0, count: 1)
        let four = placedShanks(layoutRotationDegrees: 0, count: 4)

        #expect(ProbeEnvelopeNodeFactory.expectedShankCount(
            forDirectModelId: ProbePlanningContract.neuropixels2SingleShankModelId
        ) == 1)
        #expect(ProbeEnvelopeNodeFactory.expectedShankCount(
            forDirectModelId:
                ProbePlanningContract.neuropixels2StandardFourShankModelId
        ) == 4)
        try ProbeEnvelopeNodeFactory.validateDirectProductShanks(
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId,
            shanks: single
        )
        try ProbeEnvelopeNodeFactory.validateDirectProductShanks(
            modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId,
            shanks: four
        )

        #expect(throws: AtlasSceneContractError.self) {
            try ProbeEnvelopeNodeFactory.validateDirectProductShanks(
                modelId:
                    ProbePlanningContract.neuropixels2StandardFourShankModelId,
                shanks: single
            )
        }
        #expect(throws: AtlasSceneContractError.self) {
            try ProbeEnvelopeNodeFactory.validateDirectProductShanks(
                modelId: ProbePlanningContract.neuropixels2SingleShankModelId,
                shanks: four
            )
        }

        let coincident = four.enumerated().map { index, shank in
            ProbePlacedShank(
                shankId: "coincident-\(index)",
                entry: four[0].entry,
                tip: four[0].tip,
                widthMicrometres: shank.widthMicrometres,
                thicknessMicrometres: shank.thicknessMicrometres,
                conservativeEnvelopeRadiusMicrometres:
                    shank.conservativeEnvelopeRadiusMicrometres,
                envelopeDefinition: shank.envelopeDefinition
            )
        }
        #expect(throws: AtlasSceneContractError.self) {
            try ProbeEnvelopeNodeFactory.validateDirectProductShanks(
                modelId:
                    ProbePlanningContract.neuropixels2StandardFourShankModelId,
                shanks: coincident
            )
        }
    }

    @Test("NP2013 creates four distinct scene nodes in both surgical layouts")
    @MainActor
    func fourShankSceneLayouts() throws {
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 5_200,
            anchorDvMicrometres: 500,
            anchorMlMicrometres: 5_700
        )

        let sagittal = try ProbeEnvelopeNodeFactory.makeNode(
            for: placedShanks(layoutRotationDegrees: 0, count: 4),
            usableForNavigation: false,
            transform: transform
        )
        let clockwise = try ProbeEnvelopeNodeFactory.makeNode(
            for: placedShanks(layoutRotationDegrees: 90, count: 4),
            usableForNavigation: false,
            transform: transform
        )

        #expect(sagittal.childNodes.count == 4)
        #expect(clockwise.childNodes.count == 4)
        #expect(Set(sagittal.childNodes.compactMap(\.name)).count == 4)
        #expect(Set(clockwise.childNodes.compactMap(\.name)).count == 4)

        let sagittalPositions = sagittal.childNodes.map(\.simdPosition)
        #expect(sagittalPositions.allSatisfy {
            abs($0.x - sagittalPositions[0].x) < 0.000_001
        })
        #expect(Set(sagittalPositions.map {
            Int(($0.z * 1_000).rounded())
        }).count == 4)

        let clockwisePositions = clockwise.childNodes.map(\.simdPosition)
        #expect(clockwisePositions.allSatisfy {
            abs($0.z - clockwisePositions[0].z) < 0.000_001
        })
        #expect(Set(clockwisePositions.map {
            Int(($0.x * 1_000).rounded())
        }).count == 4)

        let sagittalSource = placedShanks(layoutRotationDegrees: 0, count: 4)
        #expect(sagittalSource.map(\.entry.apMicrometres) == [
            5_200, 5_450, 5_700, 5_950,
        ])
        #expect(sagittalSource.map(\.entry.mlMicrometres).allSatisfy { $0 == 5_700 })
        let clockwiseSource = placedShanks(layoutRotationDegrees: 90, count: 4)
        #expect(clockwiseSource.map(\.entry.mlMicrometres) == [
            5_700, 5_450, 5_200, 4_950,
        ])
        #expect(clockwiseSource.map(\.entry.apMicrometres).allSatisfy { $0 == 5_200 })
    }

    @Test("Current geometry renders the complete 10 mm shaft across the surface")
    @MainActor
    func completePhysicalShankGeometry() throws {
        let surface = ProbePhysicalPoint(
            apMicrometres: 5_200,
            dvMicrometres: 500,
            mlMicrometres: 5_700
        )
        let shank = ProbePlacedShank(
            shankId: "shank-0",
            entry: surface,
            tip: ProbePhysicalPoint(
                apMicrometres: 5_200,
                dvMicrometres: 2_800,
                mlMicrometres: 5_700
            ),
            widthMicrometres: 70,
            thicknessMicrometres: 24,
            conservativeEnvelopeRadiusMicrometres: hypot(35, 12),
            envelopeDefinition: "circumscribed-radius-of-rectangular-cross-section",
            surfaceEntry: surface,
            proximalEnd: ProbePhysicalPoint(
                apMicrometres: 5_200,
                dvMicrometres: -7_200,
                mlMicrometres: 5_700,
                insideAtlas: false
            ),
            totalLengthMicrometres: 10_000
        )
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 5_200,
            anchorDvMicrometres: 500,
            anchorMlMicrometres: 5_700
        )

        let root = try ProbeEnvelopeNodeFactory.makeNode(
            for: [shank],
            usableForNavigation: false,
            transform: transform
        )
        let node = try #require(root.childNodes.first)
        let cylinder = try #require(node.geometry as? SCNCylinder)

        #expect(abs(cylinder.height - 10) < 0.000_001)
        #expect(abs(node.simdPosition.y - 2.7) < 0.000_001)
        let renderedAxis = node.simdOrientation.act(SIMD3<Float>(0, 1, 0))
        #expect(simd_distance(renderedAxis, SIMD3<Float>(0, -1, 0)) < 0.000_001)
        #expect(shank.surfaceAnchor == surface)
        #expect(shank.renderedProximalEnd.dvMicrometres == -7_200)
    }

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

    private func placedShanks(
        layoutRotationDegrees: Int,
        count: Int
    ) -> [ProbePlacedShank] {
        (0 ..< count).map { index in
            let offset = Double(index) * 250
            let ap = 5_200 + (layoutRotationDegrees == 0 ? offset : 0)
            let ml = 5_700 - (layoutRotationDegrees == 90 ? offset : 0)
            let surface = ProbePhysicalPoint(
                apMicrometres: ap,
                dvMicrometres: 500,
                mlMicrometres: ml
            )
            return ProbePlacedShank(
                shankId: "shank-\(index)",
                entry: surface,
                tip: ProbePhysicalPoint(
                    apMicrometres: ap,
                    dvMicrometres: 2_800,
                    mlMicrometres: ml
                ),
                widthMicrometres: 70,
                thicknessMicrometres: 24,
                conservativeEnvelopeRadiusMicrometres: 37,
                envelopeDefinition:
                    "circumscribed-radius-of-rectangular-cross-section",
                surfaceEntry: surface,
                proximalEnd: ProbePhysicalPoint(
                    apMicrometres: ap,
                    dvMicrometres: -7_200,
                    mlMicrometres: ml,
                    insideAtlas: false
                ),
                totalLengthMicrometres: 10_000
            )
        }
    }
}
