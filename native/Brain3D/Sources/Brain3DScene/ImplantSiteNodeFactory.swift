import AppKit
import Brain3DCore
@preconcurrency import SceneKit

@MainActor
enum ImplantSiteNodeFactory {
    private static let glyphRadiusMicrometres = 150.0

    static func makeNode(
        for marker: ImplantSiteSceneMarker,
        transform: AtlasSceneTransform
    ) throws -> SCNNode {
        let radius = CGFloat(
            glyphRadiusMicrometres * AtlasSceneTransform.sceneUnitsPerMicrometre
        )
        let geometry = SCNSphere(radius: radius)
        geometry.segmentCount = 24
        geometry.materials = [material()]

        let node = SCNNode(geometry: geometry)
        node.name = "implant-site-\(marker.targetId)"
        node.simdPosition = try transform.scenePoint(marker.point)
        node.categoryBitMask = SceneCategory.implantSite.rawValue
        // This is a location glyph, not a claim about the implant's physical size.
        node.renderingOrder = 25
        node.castsShadow = false
        return node
    }

    private static func material() -> SCNMaterial {
        let material = SCNMaterial()
        material.name = "displayed-implant-site"
        let color = NSColor(
            srgbRed: 1,
            green: 0.176,
            blue: 0.333,
            alpha: 1
        )
        material.diffuse.contents = color
        material.emission.contents = color
        material.lightingModel = .constant
        material.isDoubleSided = true
        // The point must remain legible inside the translucent atlas shell.
        material.readsFromDepthBuffer = false
        material.writesToDepthBuffer = false
        return material
    }
}
