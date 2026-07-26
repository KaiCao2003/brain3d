import Brain3DCore
@preconcurrency import SceneKit
import SwiftUI

@MainActor
public struct AnimalAtlasSceneView: NSViewRepresentable {
    public typealias NSViewType = SCNView

    public let snapshot: AnimalSceneSnapshot
    public let reduceMotion: Bool
    public let resetGeneration: Int
    private let phaseChanged: (String, AnimalScenePhase) -> Void
    private let rayPicked: (AtlasRayPoint, AtlasRayPoint) -> Void
    private let blankSelected: () -> Void

    public init(
        snapshot: AnimalSceneSnapshot,
        reduceMotion: Bool,
        resetGeneration: Int,
        phaseChanged: @escaping (String, AnimalScenePhase) -> Void,
        rayPicked: @escaping (AtlasRayPoint, AtlasRayPoint) -> Void,
        blankSelected: @escaping () -> Void
    ) {
        self.snapshot = snapshot
        self.reduceMotion = reduceMotion
        self.resetGeneration = resetGeneration
        self.phaseChanged = phaseChanged
        self.rayPicked = rayPicked
        self.blankSelected = blankSelected
    }

    public func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    public func makeNSView(context: Context) -> SCNView {
        let view = AtlasInteractiveSCNView(frame: .zero, options: [
            SCNView.Option.preferredRenderingAPI.rawValue: SCNRenderingAPI.metal.rawValue,
        ])
        view.setAccessibilityLabel("Interactive 3D mouse atlas")
        view.setAccessibilityHelp(
            "Drag to orbit, use two-finger drag to pan, pinch or scroll to zoom, and click the brain to inspect a region."
        )
        context.coordinator.attach(view)
        return view
    }

    public func updateNSView(_ nsView: SCNView, context: Context) {
        guard let interactiveView = nsView as? AtlasInteractiveSCNView else { return }
        context.coordinator.parent = self
        context.coordinator.update(view: interactiveView)
    }

    public static func dismantleNSView(_ nsView: SCNView, coordinator: Coordinator) {
        coordinator.stop()
        (nsView as? AtlasInteractiveSCNView)?.onSceneClick = nil
    }

    @MainActor
    public final class Coordinator {
        var parent: AnimalAtlasSceneView
        private var controller: AnimalSceneController?
        private var applyTask: Task<Void, Never>?
        private var lastSnapshotIdentity: String?
        private var lastResetGeneration: Int

        init(parent: AnimalAtlasSceneView) {
            self.parent = parent
            lastResetGeneration = parent.resetGeneration
        }

        func attach(_ view: AtlasInteractiveSCNView) {
            let controller = AnimalSceneController(view: view)
            controller.onRayPick = { [weak self] start, end in
                self?.parent.rayPicked(start, end)
            }
            controller.onBlankSelection = { [weak self] in
                self?.parent.blankSelected()
            }
            self.controller = controller
            update(view: view)
        }

        func update(view: AtlasInteractiveSCNView) {
            guard let controller else { return }
            controller.setReduceMotion(parent.reduceMotion)
            if lastSnapshotIdentity != parent.snapshot.identity {
                lastSnapshotIdentity = parent.snapshot.identity
                applyTask?.cancel()
                let snapshot = parent.snapshot
                let snapshotIdentity = snapshot.identity
                applyTask = Task { @MainActor [weak self, weak controller] in
                    guard let self, let controller else { return }
                    // `updateNSView` runs inside SwiftUI's render transaction.
                    // Defer renderer phase callbacks until that transaction has
                    // ended so `.loading`/`.ready` never publish model changes
                    // from within the representable update itself.
                    await Task.yield()
                    guard !Task.isCancelled else { return }
                    await controller.apply(snapshot: snapshot) { [weak self] phase in
                        self?.parent.phaseChanged(snapshotIdentity, phase)
                    }
                }
            }
            if lastResetGeneration != parent.resetGeneration {
                lastResetGeneration = parent.resetGeneration
                controller.resetCamera()
            }
        }

        func stop() {
            applyTask?.cancel()
            applyTask = nil
            controller?.onRayPick = nil
            controller?.onBlankSelection = nil
            controller = nil
        }
    }
}
