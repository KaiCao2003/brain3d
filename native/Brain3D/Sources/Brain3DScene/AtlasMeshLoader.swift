import Brain3DCore
import CryptoKit
import Foundation
@preconcurrency import ModelIO
@preconcurrency import SceneKit
import SceneKit.ModelIO

public enum AtlasMeshLoadError: Error, Equatable, LocalizedError, Sendable {
    case invalid(String)
    case unavailable(String)

    public var errorDescription: String? {
        switch self {
        case let .invalid(message), let .unavailable(message): message
        }
    }
}

final class LoadedAtlasMesh: @unchecked Sendable {
    private let scene: SCNScene

    init(scene: SCNScene) {
        self.scene = scene
    }

    @MainActor
    func makeRootNode() -> SCNNode {
        scene.rootNode.clone()
    }
}

public final class AtlasMeshLoader: @unchecked Sendable {
    private let queue = DispatchQueue(
        label: "org.openai.brain3d.atlas-mesh-loader",
        qos: .userInitiated
    )
    private var cache: [String: LoadedAtlasMesh] = [:]

    public init() {}

    func load(_ descriptor: AtlasMeshDescriptor) async throws -> LoadedAtlasMesh {
        try await withCheckedThrowingContinuation { continuation in
            queue.async { [self] in
                do {
                    if let cached = cache[descriptor.sha256] {
                        continuation.resume(returning: cached)
                        return
                    }
                    let loaded = try loadSynchronously(descriptor)
                    cache[descriptor.sha256] = loaded
                    continuation.resume(returning: loaded)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func loadSynchronously(_ descriptor: AtlasMeshDescriptor) throws -> LoadedAtlasMesh {
        let fileManager = FileManager.default
        let describedURL = URL(fileURLWithPath: descriptor.canonicalPath).standardizedFileURL
        let describedRoot = URL(
            fileURLWithPath: descriptor.atlasRootCanonicalPath,
            isDirectory: true
        ).standardizedFileURL
        let resolvedURL = describedURL.resolvingSymlinksInPath().standardizedFileURL
        let resolvedRoot = describedRoot.resolvingSymlinksInPath().standardizedFileURL
        guard resolvedURL.path == describedURL.path,
              resolvedRoot.path == describedRoot.path,
              isDescendant(resolvedURL, of: resolvedRoot)
        else {
            throw AtlasMeshLoadError.invalid(
                "Atlas mesh path is not a canonical descendant of its reviewed atlas root."
            )
        }
        guard fileManager.fileExists(atPath: resolvedURL.path) else {
            throw AtlasMeshLoadError.unavailable("The verified atlas mesh file is missing.")
        }
        let values = try resolvedURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
        guard values.isRegularFile == true,
              let fileSize = values.fileSize,
              fileSize == descriptor.byteSize,
              fileSize > 0,
              fileSize <= AtlasSceneContract.maximumMeshByteSize
        else {
            throw AtlasMeshLoadError.invalid(
                "Atlas mesh file type or byte size no longer matches its descriptor."
            )
        }
        try verifyDigest(of: resolvedURL, expected: descriptor.sha256)

        let asset = MDLAsset(url: resolvedURL)
        guard asset.count > 0 else {
            throw AtlasMeshLoadError.invalid("The reviewed atlas OBJ contains no objects.")
        }
        let scene = SCNScene(mdlAsset: asset)
        guard containsGeometry(scene.rootNode) else {
            throw AtlasMeshLoadError.invalid("The reviewed atlas OBJ contains no mesh geometry.")
        }

        let pathAfterLoad = resolvedURL.resolvingSymlinksInPath().standardizedFileURL
        guard pathAfterLoad.path == descriptor.canonicalPath else {
            throw AtlasMeshLoadError.invalid("Atlas mesh path changed while it was loading.")
        }
        try verifyDigest(of: pathAfterLoad, expected: descriptor.sha256)
        return LoadedAtlasMesh(scene: scene)
    }

    private func verifyDigest(of url: URL, expected: String) throws {
        let data: Data
        do {
            data = try Data(contentsOf: url, options: [.mappedIfSafe])
        } catch {
            throw AtlasMeshLoadError.unavailable(
                "The verified atlas mesh could not be read: \(error.localizedDescription)"
            )
        }
        let actual = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard actual == expected else {
            throw AtlasMeshLoadError.invalid(
                "Atlas mesh SHA-256 no longer matches its verified descriptor."
            )
        }
    }

    private func isDescendant(_ file: URL, of directory: URL) -> Bool {
        let directoryComponents = directory.pathComponents
        let fileComponents = file.pathComponents
        guard fileComponents.count > directoryComponents.count else { return false }
        return fileComponents.prefix(directoryComponents.count)
            .elementsEqual(directoryComponents)
    }

    private func containsGeometry(_ node: SCNNode) -> Bool {
        if node.geometry != nil { return true }
        return node.childNodes.contains(where: containsGeometry)
    }
}
