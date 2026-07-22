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
        // The contextual brain shell deliberately does not write depth. The
        // vessel and probe overlays share this depth-tested pass so their
        // front/back relationship follows calibrated geometry, not draw order.
        node.renderingOrder = 20
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
        material.readsFromDepthBuffer = true
        material.writesToDepthBuffer = true
        return material
    }
}
