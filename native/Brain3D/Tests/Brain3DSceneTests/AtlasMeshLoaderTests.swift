import Brain3DCore
@testable import Brain3DScene
import CryptoKit
import Foundation
@preconcurrency import SceneKit
import Testing

@Suite("Verified Allen OBJ loader")
struct AtlasMeshLoaderTests {
    @Test("A descriptor-locked OBJ loads through Model I/O")
    @MainActor
    func validOBJ() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let descriptor = try decodeDescriptor(
            url: fixture.obj,
            root: fixture.root,
            sha256: fixture.sha256,
            byteSize: fixture.byteSize
        )

        let loaded = try await AtlasMeshLoader().load(descriptor)
        let root = loaded.makeRootNode()

        #expect(containsGeometry(root))
    }

    @Test("A changed digest fails before geometry is accepted")
    func wrongDigest() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let descriptor = try decodeDescriptor(
            url: fixture.obj,
            root: fixture.root,
            sha256: String(repeating: "0", count: 64),
            byteSize: fixture.byteSize
        )

        await #expect(throws: AtlasMeshLoadError.self) {
            try await AtlasMeshLoader().load(descriptor)
        }
    }

    private func makeFixture() throws -> (root: URL, obj: URL, sha256: String, byteSize: Int) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("brain3d-scene-\(UUID().uuidString)", isDirectory: true)
        let meshes = root.appendingPathComponent("meshes", isDirectory: true)
        try FileManager.default.createDirectory(at: meshes, withIntermediateDirectories: true)
        let obj = meshes.appendingPathComponent("997.obj")
        let data = Data(
            """
            o brain
            v 0 0 0
            v 1000 0 0
            v 0 1000 0
            vn 0 0 1
            f 1//1 2//1 3//1
            """.utf8
        )
        try data.write(to: obj, options: .atomic)
        let sha = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return (
            root.standardizedFileURL,
            obj.standardizedFileURL,
            sha,
            data.count
        )
    }

    private func decodeDescriptor(
        url: URL,
        root: URL,
        sha256: String,
        byteSize: Int
    ) throws -> AtlasMeshDescriptor {
        let object: [String: Any] = [
            "canonicalPath": url.path,
            "atlasRootCanonicalPath": root.path,
            "pathUnderAtlasRoot": "meshes/997.obj",
            "sha256": sha256,
            "byteSize": byteSize,
            "fileExtension": ".obj",
            "contentsIncluded": false,
        ]
        return try JSONDecoder().decode(
            AtlasMeshDescriptor.self,
            from: JSONSerialization.data(withJSONObject: object)
        )
    }

    private func containsGeometry(_ node: SCNNode) -> Bool {
        node.geometry != nil || node.childNodes.contains(where: containsGeometry)
    }
}
