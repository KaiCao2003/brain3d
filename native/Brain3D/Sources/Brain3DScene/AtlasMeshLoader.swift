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
    private struct CacheKey: Hashable {
        let canonicalPath: String
        let atlasRootCanonicalPath: String
        let pathUnderAtlasRoot: String
        let sha256: String
        let byteSize: Int

        init(_ descriptor: AtlasMeshDescriptor) {
            canonicalPath = descriptor.canonicalPath
            atlasRootCanonicalPath = descriptor.atlasRootCanonicalPath
            pathUnderAtlasRoot = descriptor.pathUnderAtlasRoot
            sha256 = descriptor.sha256
            byteSize = descriptor.byteSize
        }
    }

    private struct CacheEntry {
        let mesh: LoadedAtlasMesh
        let sourceByteSize: Int
    }

    // Model I/O can expand OBJ data substantially in memory. Bound both the
    // retained source footprint and entry count; a mesh above the source-byte
    // budget is still returned to the caller but is not retained for browsing.
    private static let defaultMaximumCachedMeshCount = 8
    private static let defaultMaximumCachedSourceBytes = 64 * 1024 * 1024

    private let queue = DispatchQueue(
        label: "org.openai.brain3d.atlas-mesh-loader",
        qos: .userInitiated
    )
    private let maximumCachedMeshCount: Int
    private let maximumCachedSourceBytes: Int
    private var cache: [CacheKey: CacheEntry] = [:]
    private var leastToMostRecentlyUsed: [CacheKey] = []
    private var cachedSourceBytes = 0

    public convenience init() {
        self.init(
            maximumCachedMeshCount: Self.defaultMaximumCachedMeshCount,
            maximumCachedSourceBytes: Self.defaultMaximumCachedSourceBytes
        )
    }

    init(
        maximumCachedMeshCount: Int,
        maximumCachedSourceBytes: Int
    ) {
        precondition(maximumCachedMeshCount >= 0)
        precondition(maximumCachedSourceBytes >= 0)
        self.maximumCachedMeshCount = maximumCachedMeshCount
        self.maximumCachedSourceBytes = maximumCachedSourceBytes
    }

    func load(_ descriptor: AtlasMeshDescriptor) async throws -> LoadedAtlasMesh {
        try await withCheckedThrowingContinuation { continuation in
            queue.async { [self] in
                do {
                    let key = CacheKey(descriptor)
                    if let cached = cache[key] {
                        markMostRecentlyUsed(key)
                        continuation.resume(returning: cached.mesh)
                        return
                    }
                    let loaded = try loadSynchronously(descriptor)
                    insertIntoCache(
                        loaded,
                        key: key,
                        sourceByteSize: descriptor.byteSize
                    )
                    continuation.resume(returning: loaded)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func insertIntoCache(
        _ mesh: LoadedAtlasMesh,
        key: CacheKey,
        sourceByteSize: Int
    ) {
        guard maximumCachedMeshCount > 0,
              sourceByteSize <= maximumCachedSourceBytes
        else { return }

        while cache.count >= maximumCachedMeshCount
            || cachedSourceBytes + sourceByteSize
                > maximumCachedSourceBytes
        {
            guard let leastRecentlyUsed = leastToMostRecentlyUsed.first,
                  let removed = cache.removeValue(forKey: leastRecentlyUsed)
            else {
                cache.removeAll(keepingCapacity: true)
                leastToMostRecentlyUsed.removeAll(keepingCapacity: true)
                cachedSourceBytes = 0
                break
            }
            leastToMostRecentlyUsed.removeFirst()
            cachedSourceBytes -= removed.sourceByteSize
        }

        cache[key] = CacheEntry(
            mesh: mesh,
            sourceByteSize: sourceByteSize
        )
        leastToMostRecentlyUsed.append(key)
        cachedSourceBytes += sourceByteSize
    }

    private func markMostRecentlyUsed(_ key: CacheKey) {
        guard let index = leastToMostRecentlyUsed.firstIndex(of: key) else {
            assertionFailure("Atlas mesh cache recency metadata is inconsistent.")
            return
        }
        leastToMostRecentlyUsed.remove(at: index)
        leastToMostRecentlyUsed.append(key)
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
        let actual = LowercaseHex.encode(SHA256.hash(data: data))
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
