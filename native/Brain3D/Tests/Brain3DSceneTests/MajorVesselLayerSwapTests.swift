@preconcurrency import SceneKit
import Testing

@testable import Brain3DScene

@Suite("Atomic major-vessel layer refresh")
@MainActor
struct MajorVesselLayerSwapTests {
    @Test("Same-source preparation keeps the valid layer until replacement")
    func retainsLayerWhileReplacementIsPending() {
        let swap = MajorVesselLayerSwap()
        let original = SCNNode()
        original.name = "original-vessels"
        swap.commit(
            node: original,
            digest: "verified-source:30",
            sourceIdentity: "verified-source"
        )

        swap.prepare(for: "verified-source")

        #expect(swap.layer.childNodes.count == 1)
        #expect(swap.layer.childNodes.first === original)
        #expect(original.parent === swap.layer)

        let replacement = SCNNode()
        replacement.name = "filtered-vessels"
        swap.commit(
            node: replacement,
            digest: "verified-source:80",
            sourceIdentity: "verified-source"
        )

        #expect(swap.layer.childNodes.count == 1)
        #expect(swap.layer.childNodes.first === replacement)
        #expect(replacement.parent === swap.layer)
        #expect(original.parent == nil)
        #expect(swap.isCurrent("verified-source:80"))
    }

    @Test("A different provenance is cleared before preparation")
    func clearsMismatchedSource() {
        let swap = MajorVesselLayerSwap()
        let original = SCNNode()
        swap.commit(
            node: original,
            digest: "source-a:30",
            sourceIdentity: "source-a"
        )

        swap.prepare(for: "source-b")

        #expect(swap.layer.childNodes.isEmpty)
        #expect(original.parent == nil)
        #expect(swap.digest == nil)
        #expect(swap.sourceIdentity == nil)
    }
}
