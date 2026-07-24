import AppKit
@preconcurrency import SceneKit

public enum AnimalSceneSnapshotRenderError: Error, LocalizedError {
    case failed(String)
    case didNotFinish

    public var errorDescription: String? {
        switch self {
        case let .failed(message):
            "The 3D planning view could not be rendered: \(message)"
        case .didNotFinish:
            "The 3D planning view did not finish rendering."
        }
    }
}

/// Produces the same light-background SceneKit view used by the interactive
/// workspace, including the current probe and reviewed major-vessel layers.
///
/// Export uses a separate offscreen controller so it never changes the
/// operator's current camera or selection.
@MainActor
public enum AnimalSceneSnapshotRenderer {
    public static func render(
        snapshot: AnimalSceneSnapshot,
        size: CGSize
    ) async throws -> NSImage {
        guard size.width > 0, size.height > 0 else {
            throw AnimalSceneSnapshotRenderError.didNotFinish
        }
        let view = AtlasInteractiveSCNView(
            frame: NSRect(origin: .zero, size: size),
            options: [
                SCNView.Option.preferredRenderingAPI.rawValue:
                    SCNRenderingAPI.metal.rawValue,
            ]
        )
        let controller = AnimalSceneController(view: view)
        var finalPhase: AnimalScenePhase = .idle
        await controller.apply(snapshot: snapshot) { phase in
            finalPhase = phase
        }
        switch finalPhase {
        case .ready:
            return controller.offscreenSnapshot(size: size)
        case let .failed(message):
            throw AnimalSceneSnapshotRenderError.failed(message)
        case .idle, .loading:
            throw AnimalSceneSnapshotRenderError.didNotFinish
        }
    }
}
