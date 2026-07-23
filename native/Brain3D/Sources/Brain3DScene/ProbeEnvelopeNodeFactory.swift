import AppKit
import Brain3DCore
@preconcurrency import SceneKit
import simd

@MainActor
enum ProbeEnvelopeNodeFactory {
    static func makeNode(
        for plan: ProbePlanDetail?,
        transform: AtlasSceneTransform
    ) throws -> SCNNode {
        let container = SCNNode()
        container.name = "selected-probe-envelope"
        container.categoryBitMask = SceneCategory.probe.rawValue
        guard let plan else { return container }
        guard plan.hasCurrentPlanningGeometry else { return container }

        return try makeNode(
            for: plan.shanks,
            usableForNavigation: plan.usableForNavigation,
            transform: transform,
            container: container
        )
    }

    static func makeNode(
        for shanks: [ProbePlacedShank],
        usableForNavigation: Bool,
        transform: AtlasSceneTransform,
        container: SCNNode = SCNNode()
    ) throws -> SCNNode {
        container.name = "selected-probe-envelope"
        container.categoryBitMask = SceneCategory.probe.rawValue
        for shank in shanks {
            let entry = try transform.scenePoint(shank.entry)
            let tip = try transform.scenePoint(shank.tip)
            let delta = tip - entry
            let length = simd_length(delta)
            let radius = Float(
                shank.conservativeEnvelopeRadiusMicrometres
                    * AtlasSceneTransform.sceneUnitsPerMicrometre
            )
            guard length.isFinite,
                  length > 0,
                  radius.isFinite,
                  radius > 0
            else {
                throw AtlasSceneContractError.invalid(
                    "Selected probe shank has invalid 3D envelope geometry."
                )
            }

            let geometry = SCNCylinder(radius: CGFloat(radius), height: CGFloat(length))
            geometry.radialSegmentCount = 18
            geometry.heightSegmentCount = 1
            geometry.materials = [material(usableForNavigation: usableForNavigation)]
            let node = SCNNode(geometry: geometry)
            node.name = "probe-shank-\(shank.shankId)"
            node.simdPosition = (entry + tip) * 0.5
            node.simdOrientation = orientation(fromYAxisTo: delta / length)
            node.categoryBitMask = SceneCategory.probe.rawValue
            node.renderingOrder = 20
            node.castsShadow = false
            container.addChildNode(node)
        }
        return container
    }

    private static func orientation(fromYAxisTo direction: SIMD3<Float>) -> simd_quatf {
        let yAxis = SIMD3<Float>(0, 1, 0)
        if simd_dot(yAxis, direction) < -0.9999 {
            return simd_quatf(angle: .pi, axis: SIMD3<Float>(1, 0, 0))
        }
        return simd_quatf(from: yAxis, to: direction)
    }

    private static func material(usableForNavigation: Bool) -> SCNMaterial {
        let material = SCNMaterial()
        material.name = "probe-conservative-envelope"
        let color = usableForNavigation ? NSColor.systemYellow : NSColor.systemOrange
        material.diffuse.contents = color
        material.emission.contents = color
        material.lightingModel = .constant
        material.isDoubleSided = true
        // The probe is planning geometry, not an anatomical surface. Render it
        // as an x-ray overlay so an atlas shell cannot hide an intracranial
        // trajectory on SceneKit/Metal implementations that flatten imported
        // OBJ transparency.
        material.readsFromDepthBuffer = false
        material.writesToDepthBuffer = false
        return material
    }
}

enum SceneCategory: Int {
    case brain = 1
    case probe = 2
    case majorVessel = 4
    case selectedVesselConflict = 8
    case highlightedRegion = 16
}
