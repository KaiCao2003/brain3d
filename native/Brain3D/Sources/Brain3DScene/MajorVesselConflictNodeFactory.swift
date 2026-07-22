import AppKit
import Brain3DCore
@preconcurrency import SceneKit
import simd

struct SelectedMajorVesselSegment: Equatable, Sendable {
    let startASRMicrometres: SIMD3<Float>
    let endASRMicrometres: SIMD3<Float>
    let startRadiusMicrometres: Float
    let endRadiusMicrometres: Float
}

@MainActor
enum MajorVesselConflictNodeFactory {
    private static let glyphRadius = Float(
        55 * AtlasSceneTransform.sceneUnitsPerMicrometre
    )
    private static let connectorRadius = Float(
        10 * AtlasSceneTransform.sceneUnitsPerMicrometre
    )

    static func makeNode(
        for conflict: MajorVesselConflict,
        graph: MajorVesselGraph,
        transform: AtlasSceneTransform
    ) throws -> SCNNode {
        guard let segment = selectedSegment(for: conflict, in: graph) else {
            throw AtlasSceneContractError.invalid(
                "The selected vessel conflict does not resolve to its reviewed source segment."
            )
        }
        let container = SCNNode()
        container.name = "selected-major-vessel-conflict"
        container.categoryBitMask = SceneCategory.selectedVesselConflict.rawValue

        let probePoint = try scenePoint(conflict.probePoint, transform: transform)
        let vesselPoint = try scenePoint(conflict.vesselPoint, transform: transform)
        container.addChildNode(makeGlyph(
            name: "selected-conflict-probe-point",
            position: probePoint,
            color: .systemOrange
        ))
        container.addChildNode(makeGlyph(
            name: "selected-conflict-vessel-point",
            position: vesselPoint,
            color: .systemCyan
        ))
        container.addChildNode(makeConnector(from: probePoint, to: vesselPoint))

        let mesh = try MajorVesselTubeMeshBuilder.build(
            pointsASRMicrometres: [
                segment.startASRMicrometres,
                segment.endASRMicrometres,
            ],
            radiiMicrometres: [
                segment.startRadiusMicrometres,
                segment.endRadiusMicrometres,
            ],
            runOffsets: [0, 2]
        )
        let segmentNode = MajorVesselNodeFactory.makeNode(
            mesh: mesh,
            transform: transform
        )
        segmentNode.name = "selected-conflict-vessel-segment"
        segmentNode.geometry?.name = "selected-conflict-exact-vessel-segment"
        segmentNode.geometry?.materials = [material(
            name: "selected-conflict-vessel-segment-material",
            color: .systemYellow
        )]
        segmentNode.categoryBitMask = SceneCategory.selectedVesselConflict.rawValue
        segmentNode.renderingOrder = 30
        container.addChildNode(segmentNode)
        return container
    }

    nonisolated static func selectedSegment(
        for conflict: MajorVesselConflict,
        in graph: MajorVesselGraph
    ) -> SelectedMajorVesselSegment? {
        let runIndex = conflict.vesselRunIndex
        let segmentIndex = conflict.vesselSegmentIndexInRun
        guard graph.runOffsets.indices.dropLast().contains(runIndex),
              graph.sourceEdgeIndices.indices.contains(runIndex),
              let expectedEdge = Int32(exactly: conflict.vesselSourceEdgeIndex),
              graph.sourceEdgeIndices[runIndex] == expectedEdge
        else { return nil }

        let runStart = graph.runOffsets[runIndex]
        let runEnd = graph.runOffsets[runIndex + 1]
        guard segmentIndex >= 0,
              segmentIndex < runEnd - runStart - 1
        else { return nil }
        let pointIndex = runStart + segmentIndex
        guard graph.pointsASRMicrometres.indices.contains(pointIndex),
              graph.pointsASRMicrometres.indices.contains(pointIndex + 1),
              graph.radiiMicrometres.indices.contains(pointIndex),
              graph.radiiMicrometres.indices.contains(pointIndex + 1)
        else { return nil }

        let start = graph.pointsASRMicrometres[pointIndex]
        let end = graph.pointsASRMicrometres[pointIndex + 1]
        let vesselPoint = SIMD3<Float>(
            Float(conflict.vesselPoint.apMicrometres),
            Float(conflict.vesselPoint.dvMicrometres),
            Float(conflict.vesselPoint.mlMicrometres)
        )
        guard pointToSegmentDistance(vesselPoint, start: start, end: end) <= 1
        else { return nil }

        return SelectedMajorVesselSegment(
            startASRMicrometres: start,
            endASRMicrometres: end,
            startRadiusMicrometres: graph.radiiMicrometres[pointIndex],
            endRadiusMicrometres: graph.radiiMicrometres[pointIndex + 1]
        )
    }

    private static func scenePoint(
        _ point: MajorVesselPhysicalPoint,
        transform: AtlasSceneTransform
    ) throws -> SIMD3<Float> {
        try transform.scenePoint(
            apMicrometres: point.apMicrometres,
            dvMicrometres: point.dvMicrometres,
            mlMicrometres: point.mlMicrometres
        )
    }

    private static func makeGlyph(
        name: String,
        position: SIMD3<Float>,
        color: NSColor
    ) -> SCNNode {
        let geometry = SCNSphere(radius: CGFloat(glyphRadius))
        geometry.segmentCount = 20
        geometry.name = name
        geometry.materials = [material(name: "\(name)-material", color: color)]
        let node = SCNNode(geometry: geometry)
        node.name = name
        node.simdPosition = position
        node.categoryBitMask = SceneCategory.selectedVesselConflict.rawValue
        node.renderingOrder = 30
        node.castsShadow = false
        return node
    }

    private static func makeConnector(
        from start: SIMD3<Float>,
        to end: SIMD3<Float>
    ) -> SCNNode {
        let delta = end - start
        let length = simd_length(delta)
        let geometry: SCNGeometry
        let node = SCNNode()
        if length.isFinite, length > 1e-7 {
            let cylinder = SCNCylinder(
                radius: CGFloat(connectorRadius),
                height: CGFloat(length)
            )
            cylinder.radialSegmentCount = 10
            cylinder.heightSegmentCount = 1
            geometry = cylinder
            node.simdPosition = (start + end) * 0.5
            node.simdOrientation = orientation(fromYAxisTo: delta / length)
        } else {
            geometry = SCNSphere(radius: CGFloat(connectorRadius))
            node.simdPosition = start
        }
        geometry.name = "selected-conflict-closest-point-connector"
        geometry.materials = [material(
            name: "selected-conflict-connector-material",
            color: .white
        )]
        node.geometry = geometry
        node.name = "selected-conflict-closest-point-connector"
        node.categoryBitMask = SceneCategory.selectedVesselConflict.rawValue
        node.renderingOrder = 30
        node.castsShadow = false
        return node
    }

    private static func orientation(fromYAxisTo direction: SIMD3<Float>) -> simd_quatf {
        let yAxis = SIMD3<Float>(0, 1, 0)
        if simd_dot(yAxis, direction) < -0.9999 {
            return simd_quatf(angle: .pi, axis: SIMD3<Float>(1, 0, 0))
        }
        return simd_quatf(from: yAxis, to: direction)
    }

    nonisolated private static func pointToSegmentDistance(
        _ point: SIMD3<Float>,
        start: SIMD3<Float>,
        end: SIMD3<Float>
    ) -> Float {
        let delta = end - start
        let squaredLength = simd_length_squared(delta)
        guard squaredLength.isFinite, squaredLength > 0 else { return .infinity }
        let fraction = max(0, min(1, simd_dot(point - start, delta) / squaredLength))
        return simd_distance(point, start + fraction * delta)
    }

    private static func material(name: String, color: NSColor) -> SCNMaterial {
        let material = SCNMaterial()
        material.name = name
        material.diffuse.contents = color
        material.emission.contents = color.withAlphaComponent(0.38)
        material.lightingModel = .constant
        material.transparency = 1
        material.blendMode = .replace
        material.isDoubleSided = true
        material.readsFromDepthBuffer = true
        material.writesToDepthBuffer = true
        return material
    }
}
