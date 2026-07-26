import AppKit
import Brain3DCore
@preconcurrency import SceneKit

@MainActor
enum MajorVesselNodeFactory {
    static func makeNode(
        mesh: MajorVesselTubeMeshData,
        transform: AtlasSceneTransform
    ) -> SCNNode {
        let vertexSource = SCNGeometrySource(
            data: mesh.vertexData,
            semantic: .vertex,
            vectorCount: mesh.vertexCount,
            usesFloatComponents: true,
            componentsPerVector: 3,
            bytesPerComponent: MemoryLayout<Float>.size,
            dataOffset: 0,
            dataStride: MemoryLayout<Float>.size * 3
        )
        let normalSource = SCNGeometrySource(
            data: mesh.normalData,
            semantic: .normal,
            vectorCount: mesh.vertexCount,
            usesFloatComponents: true,
            componentsPerVector: 3,
            bytesPerComponent: MemoryLayout<Float>.size,
            dataOffset: 0,
            dataStride: MemoryLayout<Float>.size * 3
        )
        let element = SCNGeometryElement(
            data: mesh.indexData,
            primitiveType: .triangles,
            primitiveCount: mesh.triangleCount,
            bytesPerIndex: MemoryLayout<UInt32>.size
        )
        let geometry = SCNGeometry(sources: [vertexSource, normalSource], elements: [element])
        geometry.name = "radius-bearing-reference-major-vessels"
        geometry.materials = [material()]
        let node = SCNNode(geometry: geometry)
        node.name = "reference-major-vessel-tubes"
        node.categoryBitMask = SceneCategory.majorVessel.rawValue
        node.simdTransform = transform.sourceToSceneMatrix
        // Reference vessels are a planning overlay inside a closed atlas shell.
        // Draw them after anatomical context but before the selected probe and
        // conflict glyphs. Their coordinates and radii remain calibrated; only
        // shell occlusion is intentionally removed.
        node.renderingOrder = 10
        node.opacity = 1
        node.castsShadow = false
        return node
    }

    private static func material() -> SCNMaterial {
        let material = SCNMaterial()
        material.name = "reference-major-vessel-material"
        material.diffuse.contents = NSColor(
            calibratedRed: 1,
            green: 0.12,
            blue: 0.07,
            alpha: 1
        )
        material.emission.contents = NSColor(
            calibratedRed: 0.32,
            green: 0.015,
            blue: 0.008,
            alpha: 1
        )
        material.lightingModel = .constant
        material.transparency = 1
        material.blendMode = .replace
        material.isDoubleSided = true
        // SceneKit's offscreen Metal renderer can depth-fill imported OBJ
        // transparency even when the shell material itself does not request
        // depth writes. An x-ray overlay is therefore required for the same
        // trustworthy interior graph to remain visible in live and PDF views.
        material.readsFromDepthBuffer = false
        material.writesToDepthBuffer = false
        return material
    }
}
