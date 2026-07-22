@testable import Brain3DScene
@preconcurrency import SceneKit
import Testing

@Suite("3D mouse-atlas camera behavior")
struct AnimalSceneControllerTests {
    @Test("Reduce Motion disables camera inertia")
    @MainActor
    func reducedMotion() {
        let view = AtlasInteractiveSCNView(frame: .zero)
        let controller = AnimalSceneController(view: view)

        controller.setReduceMotion(true)
        #expect(!controller.cameraInertiaEnabled)

        controller.setReduceMotion(false)
        #expect(controller.cameraInertiaEnabled)
    }
}
