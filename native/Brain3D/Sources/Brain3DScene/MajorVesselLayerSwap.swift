@preconcurrency import SceneKit

/// Owns the SceneKit layer identity used by asynchronous vessel-mesh refreshes.
///
/// A same-source display-filter update retains the last complete node while its
/// replacement is built. A source/atlas change still clears immediately so
/// geometry is never shown against provenance it does not belong to.
@MainActor
final class MajorVesselLayerSwap {
    let layer = SCNNode()

    private(set) var digest: String?
    private(set) var sourceIdentity: String?

    var hasVisibleNode: Bool {
        !layer.childNodes.isEmpty
    }

    func isCurrent(_ candidateDigest: String) -> Bool {
        digest == candidateDigest && hasVisibleNode
    }

    func clear() {
        layer.childNodes.forEach { $0.removeFromParentNode() }
        digest = nil
        sourceIdentity = nil
    }

    func prepare(for candidateSourceIdentity: String) {
        guard sourceIdentity != candidateSourceIdentity else { return }
        clear()
    }

    func commit(
        node: SCNNode?,
        digest candidateDigest: String,
        sourceIdentity candidateSourceIdentity: String
    ) {
        let previousNodes = layer.childNodes
        if let node {
            // Add first, then detach the old nodes within the same main-actor
            // turn. Observers never encounter an empty same-source layer.
            layer.addChildNode(node)
        }
        previousNodes.forEach { $0.removeFromParentNode() }
        digest = candidateDigest
        sourceIdentity = candidateSourceIdentity
    }
}
