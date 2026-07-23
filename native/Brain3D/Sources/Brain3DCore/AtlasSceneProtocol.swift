import Foundation

public enum AtlasSceneContract {
    public static let physicalFrameId = AtlasPhysicalCoordinateFrame.expectedFrameId
    public static let rayPickAlgorithmVersion =
        "amanatides-woo-clipped-half-open-first-nonzero-v1"
    public static let maximumRegionSearchCharacters = 128
    public static let maximumRegionSearchResults = 100
    public static let regionSearchMatchingRule =
        "case-insensitive exact, prefix, then substring matching over normalized "
            + "acronym/name; decimal structure ID is exact only"
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

public struct AtlasRegionsParameters: Encodable, Equatable, Sendable {
    public static let maximumPageSize = 500

    public let protocolVersion: Int
    public let offset: Int
    public let limit: Int

    public init(offset: Int = 0, limit: Int = maximumPageSize) throws {
        guard offset >= 0, (1 ... Self.maximumPageSize).contains(limit) else {
            throw AtlasSceneContractError.invalid(
                "Atlas region pages require a nonnegative offset and 1–500 records."
            )
        }
        protocolVersion = BridgeProtocolVersion.current
        self.offset = offset
        self.limit = limit
    }
}

public struct AtlasRegionsResult: Decodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let offset: Int
    public let limit: Int
    public let returnedCount: Int
    public let totalCount: Int
    public let hasMore: Bool
    public let regions: [AtlasRegionSummary]
    public let atlas: ViewerAtlasIdentity

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case protocolVersion
        case offset
        case limit
        case returnedCount
        case totalCount
        case hasMore
        case regions
        case atlas
    }

    public init(from decoder: any Decoder) throws {
        try requireAtlasSceneExactKeys(
            decoder,
            CodingKeys.self,
            label: "atlas regions result"
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        protocolVersion = try container.decode(Int.self, forKey: .protocolVersion)
        offset = try container.decode(Int.self, forKey: .offset)
        limit = try container.decode(Int.self, forKey: .limit)
        returnedCount = try container.decode(Int.self, forKey: .returnedCount)
        totalCount = try container.decode(Int.self, forKey: .totalCount)
        hasMore = try container.decode(Bool.self, forKey: .hasMore)
        regions = try container.decode([AtlasRegionSummary].self, forKey: .regions)
        atlas = try container.decode(ViewerAtlasIdentity.self, forKey: .atlas)

        let consumedCount = offset + returnedCount
        guard protocolVersion == BridgeProtocolVersion.current,
              offset >= 0,
              (1 ... AtlasRegionsParameters.maximumPageSize).contains(limit),
              returnedCount == regions.count,
              returnedCount <= limit,
              totalCount > 0,
              consumedCount <= totalCount,
              hasMore == (consumedCount < totalCount),
              !hasMore || returnedCount > 0,
              Set(regions.map(\.structureId)).count == regions.count,
              Set(regions.map(\.acronym)).count == regions.count
        else {
            throw AtlasSceneContractError.invalid(
                "Atlas region page metadata or identities are inconsistent."
            )
        }
    }
}

public struct AtlasRegionTreeNode: Identifiable, Equatable, Sendable {
    public let region: AtlasRegionSummary
    public let children: [AtlasRegionTreeNode]

    public var id: Int { region.structureId }
    public var outlineChildren: [AtlasRegionTreeNode]? {
        children.isEmpty ? nil : children
    }

    fileprivate init(region: AtlasRegionSummary, children: [AtlasRegionTreeNode]) {
        self.region = region
        self.children = children
    }
}

public struct AtlasRegionHierarchy: Equatable, Sendable {
    public let regions: [AtlasRegionSummary]
    public let roots: [AtlasRegionTreeNode]
    public let childrenByParentStructureId: [Int: [AtlasRegionSummary]]

    private let regionsByStructureId: [Int: AtlasRegionSummary]

    public init(regions: [AtlasRegionSummary]) throws {
        guard !regions.isEmpty,
              Set(regions.map(\.structureId)).count == regions.count,
              Set(regions.map(\.acronym)).count == regions.count
        else {
            throw AtlasSceneContractError.invalid(
                "The complete atlas ontology must contain unique region identities."
            )
        }

        let byId = Dictionary(uniqueKeysWithValues: regions.map { ($0.structureId, $0) })
        var childRegions: [Int: [AtlasRegionSummary]] = [:]
        var rootRegions: [AtlasRegionSummary] = []
        for region in regions {
            guard Set(region.structureIdPath).count == region.structureIdPath.count,
                  region.structureIdPath.allSatisfy({ byId[$0] != nil })
            else {
                throw AtlasSceneContractError.invalid(
                    "Every ontology path must be acyclic and resolve within the complete atlas."
                )
            }
            if let parentId = region.parentStructureId {
                guard let parent = byId[parentId],
                      parent.structureIdPath == Array(region.structureIdPath.dropLast())
                else {
                    throw AtlasSceneContractError.invalid(
                        "Every ontology parent must exist and own the child's exact path prefix."
                    )
                }
                childRegions[parentId, default: []].append(region)
            } else {
                guard region.structureIdPath == [region.structureId] else {
                    throw AtlasSceneContractError.invalid(
                        "Atlas ontology roots must contain only their own structure ID."
                    )
                }
                rootRegions.append(region)
            }
        }
        guard !rootRegions.isEmpty else {
            throw AtlasSceneContractError.invalid(
                "The complete atlas ontology must contain at least one root."
            )
        }

        func node(for region: AtlasRegionSummary) -> AtlasRegionTreeNode {
            AtlasRegionTreeNode(
                region: region,
                children: childRegions[region.structureId, default: []].map(node(for:))
            )
        }

        self.regions = regions
        roots = rootRegions.map(node(for:))
        childrenByParentStructureId = childRegions
        regionsByStructureId = byId
    }

    public func region(structureId: Int) -> AtlasRegionSummary? {
        regionsByStructureId[structureId]
    }

    public func children(of structureId: Int) -> [AtlasRegionSummary] {
        childrenByParentStructureId[structureId, default: []]
    }
}

public struct AtlasRegionPageAccumulator: Sendable {
    private var atlas: ViewerAtlasIdentity?
    private var totalCount: Int?
    private var regions: [AtlasRegionSummary] = []
    private var structureIds: Set<Int> = []
    private var acronyms: Set<String> = []
    private var complete = false

    public init() {}

    public var nextOffset: Int { regions.count }

    public mutating func append(_ page: AtlasRegionsResult) throws {
        guard !complete, page.offset == nextOffset else {
            throw AtlasSceneContractError.invalid(
                "Atlas region pages must be appended once in contiguous offset order."
            )
        }
        if let atlas {
            guard page.atlas == atlas else {
                throw AtlasSceneContractError.invalid(
                    "Every atlas region page must use one immutable atlas identity."
                )
            }
        } else {
            atlas = page.atlas
        }
        if let totalCount {
            guard page.totalCount == totalCount else {
                throw AtlasSceneContractError.invalid(
                    "Atlas region totalCount changed while paging."
                )
            }
        } else {
            totalCount = page.totalCount
        }
        for region in page.regions {
            guard structureIds.insert(region.structureId).inserted,
                  acronyms.insert(region.acronym).inserted
            else {
                throw AtlasSceneContractError.invalid(
                    "Atlas region identities must remain unique across pages."
                )
            }
            regions.append(region)
        }
        complete = !page.hasMore
    }

    public func finish() throws -> AtlasRegionHierarchy {
        guard complete,
              let totalCount,
              regions.count == totalCount
        else {
            throw AtlasSceneContractError.invalid(
                "Every advertised atlas region page must load before building the hierarchy."
            )
        }
        return try AtlasRegionHierarchy(regions: regions)
    }
}

public struct AtlasRegionSearchParameters: Encodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let query: String
    public let limit: Int

    public init(query: String, limit: Int = 25) throws {
        let normalized = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty,
              normalized.count <= AtlasSceneContract.maximumRegionSearchCharacters,
              (1 ... AtlasSceneContract.maximumRegionSearchResults).contains(limit)
        else {
            throw AtlasSceneContractError.invalid(
                "Atlas search requires 1–128 characters and 1–100 results."
            )
        }
        protocolVersion = BridgeProtocolVersion.current
        self.query = normalized
        self.limit = limit
    }
}

public enum AtlasRegionSearchMatchKind: String, Decodable, CaseIterable, Equatable, Sendable {
    case structureIdExact
    case acronymExact
    case nameExact
    case acronymPrefix
    case namePrefix
    case acronymSubstring
    case nameSubstring
}

public struct AtlasRegionSearchHit: Decodable, Equatable, Identifiable, Sendable {
    public let matchKind: AtlasRegionSearchMatchKind
    public let region: AtlasRegionSummary

    public var id: Int { region.structureId }

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case matchKind
        case region
    }

    public init(from decoder: any Decoder) throws {
        try requireAtlasSceneExactKeys(
            decoder,
            CodingKeys.self,
            label: "atlas region search hit"
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        matchKind = try container.decode(AtlasRegionSearchMatchKind.self, forKey: .matchKind)
        region = try container.decode(AtlasRegionSummary.self, forKey: .region)
    }
}

public struct AtlasRegionSearchResult: Decodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let query: String
    public let matchingRule: String
    public let returnedCount: Int
    public let totalMatchCount: Int
    public let results: [AtlasRegionSearchHit]
    public let atlas: ViewerAtlasIdentity

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case protocolVersion
        case query
        case matchingRule
        case returnedCount
        case totalMatchCount
        case results
        case atlas
    }

    public init(from decoder: any Decoder) throws {
        try requireAtlasSceneExactKeys(
            decoder,
            CodingKeys.self,
            label: "atlas region search result"
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        protocolVersion = try container.decode(Int.self, forKey: .protocolVersion)
        query = try container.decode(String.self, forKey: .query)
        matchingRule = try container.decode(String.self, forKey: .matchingRule)
        returnedCount = try container.decode(Int.self, forKey: .returnedCount)
        totalMatchCount = try container.decode(Int.self, forKey: .totalMatchCount)
        results = try container.decode([AtlasRegionSearchHit].self, forKey: .results)
        atlas = try container.decode(ViewerAtlasIdentity.self, forKey: .atlas)
        guard protocolVersion == BridgeProtocolVersion.current,
              !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              query.count <= AtlasSceneContract.maximumRegionSearchCharacters,
              matchingRule == AtlasSceneContract.regionSearchMatchingRule,
              returnedCount == results.count,
              returnedCount >= 0,
              returnedCount <= AtlasSceneContract.maximumRegionSearchResults,
              totalMatchCount >= returnedCount,
              Set(results.map(\.region.structureId)).count == results.count
        else {
            throw AtlasSceneContractError.invalid(
                "Atlas region search metadata is inconsistent."
            )
        }
    }
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
