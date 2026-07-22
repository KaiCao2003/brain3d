import Foundation

public enum AtlasSceneContract {
    public static let physicalFrameId = AtlasPhysicalCoordinateFrame.expectedFrameId
    public static let rayPickAlgorithmVersion =
        "amanatides-woo-clipped-half-open-first-nonzero-v1"
    public static let maximumMeshByteSize = 128 * 1024 * 1024
    public static let maximumRayLengthMicrometres = 250_000.0
}

public enum AtlasSceneContractError: Error, Equatable, LocalizedError, Sendable {
    case invalid(String)

    public var errorDescription: String? {
        switch self {
        case let .invalid(message): message
        }
    }
}

public enum AtlasMeshTarget: String, Codable, CaseIterable, Equatable, Sendable {
    case root
    case region
}

public struct AtlasMeshParameters: Encodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let target: AtlasMeshTarget
    public let structureId: Int?

    public init(target: AtlasMeshTarget = .root, structureId: Int? = nil) throws {
        guard (target == .root && structureId == nil)
                || (target == .region && structureId.map({ $0 > 0 }) == true)
        else {
            throw AtlasSceneContractError.invalid(
                "Root mesh requests omit structureId; region requests require a positive ID."
            )
        }
        protocolVersion = BridgeProtocolVersion.current
        self.target = target
        self.structureId = structureId
    }
}

public struct AtlasMeshDescriptor: Decodable, Equatable, Sendable {
    public let canonicalPath: String
    public let atlasRootCanonicalPath: String
    public let pathUnderAtlasRoot: String
    public let sha256: String
    public let byteSize: Int
    public let fileExtension: String
    public let contentsIncluded: Bool

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case canonicalPath
        case atlasRootCanonicalPath
        case pathUnderAtlasRoot
        case sha256
        case byteSize
        case fileExtension
        case contentsIncluded
    }

    public init(from decoder: any Decoder) throws {
        try requireAtlasSceneExactKeys(decoder, CodingKeys.self, label: "atlas mesh descriptor")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        canonicalPath = try container.decode(String.self, forKey: .canonicalPath)
        atlasRootCanonicalPath = try container.decode(
            String.self,
            forKey: .atlasRootCanonicalPath
        )
        pathUnderAtlasRoot = try container.decode(String.self, forKey: .pathUnderAtlasRoot)
        sha256 = try container.decode(String.self, forKey: .sha256)
        byteSize = try container.decode(Int.self, forKey: .byteSize)
        fileExtension = try container.decode(String.self, forKey: .fileExtension)
        contentsIncluded = try container.decode(Bool.self, forKey: .contentsIncluded)
        try validate()
    }

    private func validate() throws {
        let meshURL = URL(fileURLWithPath: canonicalPath).standardizedFileURL
        let atlasRootURL = URL(fileURLWithPath: atlasRootCanonicalPath).standardizedFileURL
        let relativeComponents = pathUnderAtlasRoot.split(separator: "/", omittingEmptySubsequences: false)
        guard canonicalPath.hasPrefix("/"), atlasRootCanonicalPath.hasPrefix("/") else {
            throw AtlasSceneContractError.invalid("Atlas mesh paths must be absolute.")
        }
        guard !pathUnderAtlasRoot.isEmpty,
              !pathUnderAtlasRoot.hasPrefix("/"),
              !relativeComponents.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." })
        else {
            throw AtlasSceneContractError.invalid(
                "Atlas mesh relative path must remain beneath the atlas root."
            )
        }
        let expectedURL = atlasRootURL.appendingPathComponent(pathUnderAtlasRoot).standardizedFileURL
        guard meshURL.path == expectedURL.path else {
            throw AtlasSceneContractError.invalid(
                "Atlas mesh canonical and root-relative paths must identify the same file."
            )
        }
        guard fileExtension == ".obj",
              meshURL.pathExtension.lowercased() == "obj",
              pathUnderAtlasRoot.lowercased().hasSuffix(".obj")
        else {
            throw AtlasSceneContractError.invalid("Only reviewed OBJ atlas meshes are accepted.")
        }
        guard byteSize > 0, byteSize <= AtlasSceneContract.maximumMeshByteSize else {
            throw AtlasSceneContractError.invalid(
                "Atlas mesh byte size exceeds the supported limit."
            )
        }
        guard isLowercaseSHA256(sha256) else {
            throw AtlasSceneContractError.invalid(
                "Atlas mesh sha256 must be 64 lowercase hexadecimal characters."
            )
        }
        guard !contentsIncluded else {
            throw AtlasSceneContractError.invalid(
                "Atlas mesh contents must not be embedded in the bridge payload."
            )
        }
    }
}

public struct AtlasMeshResult: Decodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let target: AtlasMeshTarget
    public let region: AtlasRegionSummary?
    public let mesh: AtlasMeshDescriptor
    public let sourceCoordinateFrame: AtlasPhysicalCoordinateFrame
    public let atlas: ViewerAtlasIdentity

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case protocolVersion
        case target
        case region
        case mesh
        case sourceCoordinateFrame
        case atlas
    }

    public init(from decoder: any Decoder) throws {
        try requireAtlasSceneExactKeys(decoder, CodingKeys.self, label: "atlas mesh result")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        protocolVersion = try container.decode(Int.self, forKey: .protocolVersion)
        target = try container.decode(AtlasMeshTarget.self, forKey: .target)
        region = try container.decodeIfPresent(AtlasRegionSummary.self, forKey: .region)
        mesh = try container.decode(AtlasMeshDescriptor.self, forKey: .mesh)
        sourceCoordinateFrame = try container.decode(
            AtlasPhysicalCoordinateFrame.self,
            forKey: .sourceCoordinateFrame
        )
        atlas = try container.decode(ViewerAtlasIdentity.self, forKey: .atlas)
        guard protocolVersion == BridgeProtocolVersion.current else {
            throw AtlasSceneContractError.invalid("Atlas mesh protocol version is unsupported.")
        }
        guard (target == .root && region == nil) || (target == .region && region != nil) else {
            throw AtlasSceneContractError.invalid(
                "Atlas mesh target and optional region are inconsistent."
            )
        }
        try validateFrameMatchesAtlas(frame: sourceCoordinateFrame, atlas: atlas)
    }
}

public struct AtlasRayPoint: Equatable, Sendable {
    public let apMicrometres: Double
    public let dvMicrometres: Double
    public let mlMicrometres: Double

    public init(
        apMicrometres: Double,
        dvMicrometres: Double,
        mlMicrometres: Double
    ) throws {
        guard [apMicrometres, dvMicrometres, mlMicrometres].allSatisfy(\.isFinite) else {
            throw AtlasSceneContractError.invalid("Atlas ray points must be finite.")
        }
        self.apMicrometres = apMicrometres
        self.dvMicrometres = dvMicrometres
        self.mlMicrometres = mlMicrometres
    }
}

public struct AtlasRayPickParameters: Encodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let frameId: String
    public let startApMicrometres: Double
    public let startDvMicrometres: Double
    public let startMlMicrometres: Double
    public let endApMicrometres: Double
    public let endDvMicrometres: Double
    public let endMlMicrometres: Double

    public init(start: AtlasRayPoint, end: AtlasRayPoint) throws {
        let delta = SIMD3<Double>(
            end.apMicrometres - start.apMicrometres,
            end.dvMicrometres - start.dvMicrometres,
            end.mlMicrometres - start.mlMicrometres
        )
        let length = delta.length
        guard length.isFinite,
              length > 0,
              length <= AtlasSceneContract.maximumRayLengthMicrometres
        else {
            throw AtlasSceneContractError.invalid(
                "Atlas ray length must be positive and within the reviewed scene limit."
            )
        }
        protocolVersion = BridgeProtocolVersion.current
        frameId = AtlasSceneContract.physicalFrameId
        startApMicrometres = start.apMicrometres
        startDvMicrometres = start.dvMicrometres
        startMlMicrometres = start.mlMicrometres
        endApMicrometres = end.apMicrometres
        endDvMicrometres = end.dvMicrometres
        endMlMicrometres = end.mlMicrometres
    }
}

public enum AtlasRayPickStatus: String, Decodable, CaseIterable, Equatable, Sendable {
    case hit
    case noAnnotatedVoxel
}

public struct AtlasRayPickHit: Decodable, Equatable, Sendable {
    public let entryPoint: AtlasPhysicalPoint
    public let voxelCenter: AtlasPhysicalPoint
    public let containingVoxelIndex: AtlasVoxelIndex
    public let annotationStructureId: Int
    public let region: AtlasRegionSummary
    public let hemisphere: AtlasHemisphere
    public let distanceFromRayStartMicrometres: Double
    public let distanceInsideVoxelMicrometres: Double

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case entryPoint
        case voxelCenter
        case containingVoxelIndex
        case annotationStructureId
        case region
        case hemisphere
        case distanceFromRayStartMicrometres
        case distanceInsideVoxelMicrometres
    }

    public init(from decoder: any Decoder) throws {
        try requireAtlasSceneExactKeys(decoder, CodingKeys.self, label: "atlas ray hit")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        entryPoint = try container.decode(AtlasPhysicalPoint.self, forKey: .entryPoint)
        voxelCenter = try container.decode(AtlasPhysicalPoint.self, forKey: .voxelCenter)
        containingVoxelIndex = try container.decode(
            AtlasVoxelIndex.self,
            forKey: .containingVoxelIndex
        )
        annotationStructureId = try container.decode(Int.self, forKey: .annotationStructureId)
        region = try container.decode(AtlasRegionSummary.self, forKey: .region)
        hemisphere = try container.decode(AtlasHemisphere.self, forKey: .hemisphere)
        distanceFromRayStartMicrometres = try container.decode(
            Double.self,
            forKey: .distanceFromRayStartMicrometres
        )
        distanceInsideVoxelMicrometres = try container.decode(
            Double.self,
            forKey: .distanceInsideVoxelMicrometres
        )
        guard annotationStructureId > 0,
              annotationStructureId == region.structureId,
              distanceFromRayStartMicrometres.isFinite,
              distanceFromRayStartMicrometres >= 0,
              distanceInsideVoxelMicrometres.isFinite,
              distanceInsideVoxelMicrometres > 0
        else {
            throw AtlasSceneContractError.invalid("Atlas ray hit metadata is inconsistent.")
        }
    }
}

public struct AtlasRayPickResult: Decodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: AtlasRayPickStatus
    public let algorithmVersion: String
    public let hit: AtlasRayPickHit?
    public let coordinateFrame: AtlasPhysicalCoordinateFrame
    public let atlas: ViewerAtlasIdentity

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case protocolVersion
        case status
        case algorithmVersion
        case hit
        case coordinateFrame
        case atlas
    }

    public init(from decoder: any Decoder) throws {
        try requireAtlasSceneExactKeys(decoder, CodingKeys.self, label: "atlas ray-pick result")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        protocolVersion = try container.decode(Int.self, forKey: .protocolVersion)
        status = try container.decode(AtlasRayPickStatus.self, forKey: .status)
        algorithmVersion = try container.decode(String.self, forKey: .algorithmVersion)
        hit = try container.decodeIfPresent(AtlasRayPickHit.self, forKey: .hit)
        coordinateFrame = try container.decode(
            AtlasPhysicalCoordinateFrame.self,
            forKey: .coordinateFrame
        )
        atlas = try container.decode(ViewerAtlasIdentity.self, forKey: .atlas)
        guard protocolVersion == BridgeProtocolVersion.current,
              algorithmVersion == AtlasSceneContract.rayPickAlgorithmVersion
        else {
            throw AtlasSceneContractError.invalid(
                "Atlas ray-pick protocol or algorithm version is unsupported."
            )
        }
        guard (status == .hit && hit != nil)
                || (status == .noAnnotatedVoxel && hit == nil)
        else {
            throw AtlasSceneContractError.invalid(
                "Atlas ray-pick status and optional hit are inconsistent."
            )
        }
        try validateFrameMatchesAtlas(frame: coordinateFrame, atlas: atlas)
    }
}

private func requireAtlasSceneExactKeys<Keys: CodingKey & CaseIterable>(
    _ decoder: any Decoder,
    _ keyType: Keys.Type,
    label: String
) throws {
    let dynamic = try decoder.container(keyedBy: AtlasSceneDynamicCodingKey.self)
    let actual = Set(dynamic.allKeys.map(\.stringValue))
    let expected = Set(Keys.allCases.map(\.stringValue))
    guard actual == expected else {
        throw AtlasSceneContractError.invalid(
            "\(label) keys do not match protocol v1 exactly."
        )
    }
}

private struct AtlasSceneDynamicCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int? = nil

    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}

private func isLowercaseSHA256(_ value: String) -> Bool {
    value.utf8.count == 64 && value.utf8.allSatisfy {
        ($0 >= 48 && $0 <= 57) || ($0 >= 97 && $0 <= 102)
    }
}

private func validateFrameMatchesAtlas(
    frame: AtlasPhysicalCoordinateFrame,
    atlas: ViewerAtlasIdentity
) throws {
    let resolution = [
        atlas.resolutionMicrometres.apMicrometres,
        atlas.resolutionMicrometres.dvMicrometres,
        atlas.resolutionMicrometres.mlMicrometres,
    ]
    let shape = [atlas.shapeVoxels.apVoxels, atlas.shapeVoxels.dvVoxels, atlas.shapeVoxels.mlVoxels]
    let expectedMaximum = zip(resolution, shape).map { pair in
        pair.0 * Double(pair.1)
    }
    guard frame.bounds.minimumInclusiveMicrometres == [0, 0, 0],
          zip(frame.axes, resolution).allSatisfy({ pair in
              abs(pair.0.voxelSizeMicrometres - pair.1) < 1e-9
          }),
          zip(frame.bounds.maximumExclusiveMicrometres, expectedMaximum).allSatisfy({ pair in
              abs(pair.0 - pair.1) < 1e-6
          })
    else {
        throw AtlasSceneContractError.invalid(
            "Atlas coordinate frame bounds and resolution must match atlas provenance."
        )
    }
}

private extension SIMD3 where Scalar == Double {
    var length: Double { (x * x + y * y + z * z).squareRoot() }
}
