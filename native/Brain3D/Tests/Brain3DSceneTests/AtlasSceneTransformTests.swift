import Brain3DCore
@testable import Brain3DScene
import simd
import Testing

@Suite("Allen atlas SceneKit coordinate transform")
struct AtlasSceneTransformTests {
    @Test("Anchor maps to origin and ASR directions map to renderer axes")
    func axisDirections() throws {
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 6_600,
            anchorDvMicrometres: 4_000,
            anchorMlMicrometres: 5_700
        )

        #expect(try transform.scenePoint(
            apMicrometres: 6_600,
            dvMicrometres: 4_000,
            mlMicrometres: 5_700
        ) == .zero)
        #expect(try transform.scenePoint(
            apMicrometres: 7_600,
            dvMicrometres: 4_000,
            mlMicrometres: 5_700
        ) == SIMD3<Float>(0, 0, 1))
        #expect(try transform.scenePoint(
            apMicrometres: 6_600,
            dvMicrometres: 5_000,
            mlMicrometres: 5_700
        ) == SIMD3<Float>(0, -1, 0))
        #expect(try transform.scenePoint(
            apMicrometres: 6_600,
            dvMicrometres: 4_000,
            mlMicrometres: 6_700
        ) == SIMD3<Float>(-1, 0, 0))
    }

    @Test("Asymmetric physical points round-trip without a voxel-center offset")
    func roundTrip() throws {
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 6_612.5,
            anchorDvMicrometres: 4_012.5,
            anchorMlMicrometres: 5_712.5
        )
        let scene = try transform.scenePoint(
            apMicrometres: 1_237.25,
            dvMicrometres: 6_543.5,
            mlMicrometres: 9_876.75
        )
        let physical = try transform.atlasPoint(from: scene)

        #expect(abs(physical.apMicrometres - 1_237.25) < 0.001)
        #expect(abs(physical.dvMicrometres - 6_543.5) < 0.001)
        #expect(abs(physical.mlMicrometres - 9_876.75) < 0.001)
    }

    @Test("Column-major matrix agrees with direct conversion and reflects winding")
    func matrixAgreement() throws {
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 6_600,
            anchorDvMicrometres: 4_000,
            anchorMlMicrometres: 5_700
        )
        let physical = SIMD4<Float>(1_250, 3_375, 8_625, 1)
        let matrixPoint = transform.sourceToSceneMatrix * physical
        let direct = try transform.scenePoint(
            apMicrometres: Double(physical.x),
            dvMicrometres: Double(physical.y),
            mlMicrometres: Double(physical.z)
        )

        #expect(
            simd_distance(SIMD3(matrixPoint.x, matrixPoint.y, matrixPoint.z), direct)
                < 0.000_001
        )
        #expect(simd_determinant(transform.sourceToSceneMatrix) < 0)
    }
}
