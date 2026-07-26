import AppKit
import Brain3DCore
@testable import Brain3DScene
@preconcurrency import SceneKit
import simd
import Testing

@Suite("Displayed 3D implant site")
struct ImplantSiteNodeFactoryTests {
    @Test("Pink location glyph preserves its exact physical ASR point")
    @MainActor
    func locationGlyph() throws {
        let marker = ImplantSiteSceneMarker(
            targetId: "target-direction-test",
            label: "AP- posterior / ML- animal-left",
            point: ProbePhysicalPoint(
                apMicrometres: 6_400,
                dvMicrometres: 1_832,
                mlMicrometres: 6_200,
                voxelIndex: ProbeVoxelIndex(ap: 256, dv: 73, ml: 248)
            )
        )
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 5_400,
            anchorDvMicrometres: 332,
            anchorMlMicrometres: 5_700
        )

        let node = try ImplantSiteNodeFactory.makeNode(
            for: marker,
            transform: transform
        )
        let sphere = try #require(node.geometry as? SCNSphere)
        let material = try #require(sphere.firstMaterial)
        let color = try #require(
            material.diffuse.contents as? NSColor
        ).usingColorSpace(.deviceRGB)

        #expect(simd_distance(node.simdPosition, SIMD3<Float>(-0.5, -1.5, 1)) < 0.000_001)
        #expect(abs(sphere.radius - 0.15) < 0.000_001)
        #expect(node.categoryBitMask == SceneCategory.implantSite.rawValue)
        #expect(node.renderingOrder == 25)
        #expect(!node.castsShadow)
        #expect(material.lightingModel == .constant)
        #expect(!material.readsFromDepthBuffer)
        #expect(!material.writesToDepthBuffer)
        #expect(try #require(color).redComponent > 0.95)
        #expect(try #require(color).greenComponent < 0.25)
        #expect(try #require(color).blueComponent > 0.25)
    }
}
