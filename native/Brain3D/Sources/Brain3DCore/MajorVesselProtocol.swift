import CryptoKit
import Foundation
import simd

public enum MajorVesselContract {
    public static let sourceId = "lambada-p60-606-major-vessels-v1"
    public static let sourceDoi = "10.5281/zenodo.18876865"
    public static let sourceRecordURL = "https://zenodo.org/records/18876865"
    public static let sourcePaperDoi = "10.1016/j.cell.2026.03.013"
    public static let specimenId = "P60_606"
    public static let sourceArchiveDigest =
        "sha256:cc6d252ee57154f5bc0f06605a703253470a57c210d76e075831effa2098d66f"
    public static let derivedAssetSHA256 =
        "fb2344e845e604be3424bd63f4222d273eafba34db0df2eaff32f4400fa9afec"
    public static let extractionAlgorithmVersion = "lambada-p60-606-major-runs-v1"
    public static let minimumIncludedDiameterMicrometres = 30.0
    public static let expectedPointCount = 71_313
    public static let expectedRunCount = 11_818
    public static let expectedSegmentCount = 59_495
    public static let maximumPointCount = 500_000
    public static let maximumRunCount = 250_000
    public static let maximumBufferByteCount = 16 * 1024 * 1024
}

public enum MajorVesselContractError: Error, Equatable, LocalizedError, Sendable {
    case invalid(String)

    public var errorDescription: String? {
        switch self {
        case let .invalid(message): message
        }
    }
}

public struct MajorVesselReferenceParameters: Encodable, Equatable, Sendable {
    public let protocolVersion: Int

    public init(protocolVersion: Int = BridgeProtocolVersion.current) {
        self.protocolVersion = protocolVersion
    }
}

public struct MajorVesselSourceProvenance: Decodable, Equatable, Sendable {
    public let sourceId: String
    public let sourceKind: String
    public let datasetTitle: String
    public let authors: [String]
    public let specimenId: String
    public let sourceDoi: String
    public let sourceRecordUrl: String
    public let sourcePaperDoi: String
    public let sourceVersion: String
    public let sourceLicense: String
    public let sourceArchiveDigest: String
    public let derivedAssetSha256: String
    public let extractionAlgorithmVersion: String
    public let atlasIdentifier: String
    public let atlasVersion: String
    public let coordinateFrameId: String
    public let minimumIncludedDiameterMicrometres: Double
    public let physicalUnitsDeclared: Bool
    public let atlasScaleApplied: Bool
    public let geometrySourceAudited: Bool
    public let subjectSpecific: Bool
    public let pialVesselsExcluded: Bool
    public let choroidalVesselsExcluded: Bool
    public let arteryVeinClassificationAvailable: Bool
    public let registrationTransformId: String?
    public let registrationUncertaintyBoundMicrometres: Double?
    public let tissueDistortionUncertaintyBoundMicrometres: Double?
    public let uncertaintyBoundsReviewed: Bool

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case sourceId
        case sourceKind
        case datasetTitle
        case authors
        case specimenId
        case sourceDoi
        case sourceRecordUrl
        case sourcePaperDoi
        case sourceVersion
        case sourceLicense
        case sourceArchiveDigest
        case derivedAssetSha256
        case extractionAlgorithmVersion
        case atlasIdentifier
        case atlasVersion
        case coordinateFrameId
        case minimumIncludedDiameterMicrometres
        case physicalUnitsDeclared
        case atlasScaleApplied
        case geometrySourceAudited
        case subjectSpecific
        case pialVesselsExcluded
        case choroidalVesselsExcluded
        case arteryVeinClassificationAvailable
        case registrationTransformId
        case registrationUncertaintyBoundMicrometres
        case tissueDistortionUncertaintyBoundMicrometres
        case uncertaintyBoundsReviewed
    }

    public init(from decoder: any Decoder) throws {
        try requireMajorVesselExactKeys(decoder, CodingKeys.self, label: "major-vessel provenance")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sourceId = try container.decode(String.self, forKey: .sourceId)
        sourceKind = try container.decode(String.self, forKey: .sourceKind)
        datasetTitle = try container.decode(String.self, forKey: .datasetTitle)
        authors = try container.decode([String].self, forKey: .authors)
        specimenId = try container.decode(String.self, forKey: .specimenId)
        sourceDoi = try container.decode(String.self, forKey: .sourceDoi)
        sourceRecordUrl = try container.decode(String.self, forKey: .sourceRecordUrl)
        sourcePaperDoi = try container.decode(String.self, forKey: .sourcePaperDoi)
        sourceVersion = try container.decode(String.self, forKey: .sourceVersion)
        sourceLicense = try container.decode(String.self, forKey: .sourceLicense)
        sourceArchiveDigest = try container.decode(String.self, forKey: .sourceArchiveDigest)
        derivedAssetSha256 = try container.decode(String.self, forKey: .derivedAssetSha256)
        extractionAlgorithmVersion = try container.decode(
            String.self,
            forKey: .extractionAlgorithmVersion
        )
        atlasIdentifier = try container.decode(String.self, forKey: .atlasIdentifier)
        atlasVersion = try container.decode(String.self, forKey: .atlasVersion)
        coordinateFrameId = try container.decode(String.self, forKey: .coordinateFrameId)
        minimumIncludedDiameterMicrometres = try container.decode(
            Double.self,
            forKey: .minimumIncludedDiameterMicrometres
        )
        physicalUnitsDeclared = try container.decode(Bool.self, forKey: .physicalUnitsDeclared)
        atlasScaleApplied = try container.decode(Bool.self, forKey: .atlasScaleApplied)
        geometrySourceAudited = try container.decode(Bool.self, forKey: .geometrySourceAudited)
        subjectSpecific = try container.decode(Bool.self, forKey: .subjectSpecific)
        pialVesselsExcluded = try container.decode(Bool.self, forKey: .pialVesselsExcluded)
        choroidalVesselsExcluded = try container.decode(
            Bool.self,
            forKey: .choroidalVesselsExcluded
        )
        arteryVeinClassificationAvailable = try container.decode(
            Bool.self,
            forKey: .arteryVeinClassificationAvailable
        )
        registrationTransformId = try container.decodeIfPresent(
            String.self,
            forKey: .registrationTransformId
        )
        registrationUncertaintyBoundMicrometres = try container.decodeIfPresent(
            Double.self,
            forKey: .registrationUncertaintyBoundMicrometres
        )
        tissueDistortionUncertaintyBoundMicrometres = try container.decodeIfPresent(
            Double.self,
            forKey: .tissueDistortionUncertaintyBoundMicrometres
        )
        uncertaintyBoundsReviewed = try container.decode(
            Bool.self,
            forKey: .uncertaintyBoundsReviewed
        )
        try validate()
    }

    private func validate() throws {
        guard sourceId == MajorVesselContract.sourceId,
              sourceKind == "reference-individual-vessel-graph",
              sourceDoi == MajorVesselContract.sourceDoi,
              sourceRecordUrl == MajorVesselContract.sourceRecordURL,
              sourcePaperDoi == MajorVesselContract.sourcePaperDoi,
              specimenId == MajorVesselContract.specimenId,
              sourceArchiveDigest == MajorVesselContract.sourceArchiveDigest,
              derivedAssetSha256 == MajorVesselContract.derivedAssetSHA256,
              extractionAlgorithmVersion == MajorVesselContract.extractionAlgorithmVersion,
              atlasIdentifier == SafetyPolicy.supportedAtlasIdentifier,
              atlasVersion == SafetyPolicy.supportedAtlasVersion,
              coordinateFrameId == AtlasPhysicalCoordinateFrame.expectedFrameId,
              minimumIncludedDiameterMicrometres
                == MajorVesselContract.minimumIncludedDiameterMicrometres,
              physicalUnitsDeclared,
              atlasScaleApplied,
              geometrySourceAudited,
              !subjectSpecific,
              pialVesselsExcluded,
              choroidalVesselsExcluded,
              !arteryVeinClassificationAvailable,
              registrationTransformId == nil,
              registrationUncertaintyBoundMicrometres == nil,
              tissueDistortionUncertaintyBoundMicrometres == nil,
              !uncertaintyBoundsReviewed,
              sourceLicense == "CC BY 4.0",
              !datasetTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !sourceVersion.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !authors.isEmpty,
              authors.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty })
        else {
            throw MajorVesselContractError.invalid(
                "Major-vessel source provenance does not match the pinned reference."
            )
        }
    }
}

public struct MajorVesselGraph: Equatable, Sendable {
    public let pointsASRMicrometres: [SIMD3<Float>]
    public let radiiMicrometres: [Float]
    public let runOffsets: [Int]
    public let sourceEdgeIndices: [Int32]

    public init(
        pointsASRMicrometres: [SIMD3<Float>],
        radiiMicrometres: [Float],
        runOffsets: [Int],
        sourceEdgeIndices: [Int32],
        atlas: ViewerAtlasIdentity,
        minimumIncludedDiameterMicrometres: Double
    ) throws {
        guard !pointsASRMicrometres.isEmpty,
              pointsASRMicrometres.count <= MajorVesselContract.maximumPointCount,
              radiiMicrometres.count == pointsASRMicrometres.count,
              runOffsets.count >= 2,
              runOffsets.count - 1 <= MajorVesselContract.maximumRunCount,
              sourceEdgeIndices.count == runOffsets.count - 1,
              runOffsets.first == 0,
              runOffsets.last == pointsASRMicrometres.count,
              zip(runOffsets, runOffsets.dropFirst()).allSatisfy({ $1 - $0 >= 2 }),
              sourceEdgeIndices.allSatisfy({ $0 >= 0 })
        else {
            throw MajorVesselContractError.invalid(
                "Major-vessel point, radius, and run counts are inconsistent."
            )
        }
        let minimumRadius = Float(minimumIncludedDiameterMicrometres / 2)
        guard minimumRadius.isFinite,
              minimumRadius > 0,
              radiiMicrometres.allSatisfy({ $0.isFinite && $0 >= minimumRadius })
        else {
            throw MajorVesselContractError.invalid(
                "Major-vessel radii violate the declared diameter threshold."
            )
        }
        let maxima = SIMD3<Float>(
            Float(atlas.resolutionMicrometres.apMicrometres * Double(atlas.shapeVoxels.apVoxels)),
            Float(atlas.resolutionMicrometres.dvMicrometres * Double(atlas.shapeVoxels.dvVoxels)),
            Float(atlas.resolutionMicrometres.mlMicrometres * Double(atlas.shapeVoxels.mlVoxels))
        )
        guard pointsASRMicrometres.allSatisfy({ point in
            point.x.isFinite && point.y.isFinite && point.z.isFinite
                && point.x >= 0 && point.x < maxima.x
                && point.y >= 0 && point.y < maxima.y
                && point.z >= 0 && point.z < maxima.z
        }) else {
            throw MajorVesselContractError.invalid(
                "Major-vessel coordinates lie outside the matched atlas bounds."
            )
        }
        for runIndex in 0 ..< sourceEdgeIndices.count {
            let start = runOffsets[runIndex]
            let end = runOffsets[runIndex + 1]
            guard (start ..< end - 1).allSatisfy({ index in
                pointsASRMicrometres[index] != pointsASRMicrometres[index + 1]
            }) else {
                throw MajorVesselContractError.invalid(
                    "Major-vessel runs contain a zero-length segment."
                )
            }
        }
        self.pointsASRMicrometres = pointsASRMicrometres
        self.radiiMicrometres = radiiMicrometres
        self.runOffsets = runOffsets
        self.sourceEdgeIndices = sourceEdgeIndices
    }

    public var pointCount: Int { pointsASRMicrometres.count }
    public var runCount: Int { runOffsets.count - 1 }
    public var segmentCount: Int { pointCount - runCount }
}

public struct MajorVesselGeometryResult: Decodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let encoding: String
    public let pointCount: Int
    public let runCount: Int
    public let segmentCount: Int
    public let graph: MajorVesselGraph
    public let provenance: MajorVesselSourceProvenance
    public let limitations: [String]
    public let atlas: ViewerAtlasIdentity

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case protocolVersion
        case status
        case encoding
        case pointCount
        case runCount
        case segmentCount
        case pointsASRMicrometres
        case radiiMicrometres
        case runOffsets
        case sourceEdgeIndices
        case provenance
        case limitations
        case atlas
    }

    public init(from decoder: any Decoder) throws {
        try requireMajorVesselExactKeys(decoder, CodingKeys.self, label: "major-vessel geometry")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        protocolVersion = try container.decode(Int.self, forKey: .protocolVersion)
        status = try container.decode(String.self, forKey: .status)
        encoding = try container.decode(String.self, forKey: .encoding)
        pointCount = try container.decode(Int.self, forKey: .pointCount)
        runCount = try container.decode(Int.self, forKey: .runCount)
        segmentCount = try container.decode(Int.self, forKey: .segmentCount)
        let pointsBuffer = try container.decode(
            MajorVesselBuffer.self,
            forKey: .pointsASRMicrometres
        )
        let radiiBuffer = try container.decode(
            MajorVesselBuffer.self,
            forKey: .radiiMicrometres
        )
        let offsetsBuffer = try container.decode(MajorVesselBuffer.self, forKey: .runOffsets)
        let edgesBuffer = try container.decode(MajorVesselBuffer.self, forKey: .sourceEdgeIndices)
        provenance = try container.decode(MajorVesselSourceProvenance.self, forKey: .provenance)
        limitations = try container.decode([String].self, forKey: .limitations)
        atlas = try container.decode(ViewerAtlasIdentity.self, forKey: .atlas)
        guard protocolVersion == BridgeProtocolVersion.current,
              status == "ready",
              encoding == "contiguous-little-endian-v1",
              pointCount == MajorVesselContract.expectedPointCount,
              pointCount <= MajorVesselContract.maximumPointCount,
              runCount == MajorVesselContract.expectedRunCount,
              runCount <= MajorVesselContract.maximumRunCount,
              segmentCount == MajorVesselContract.expectedSegmentCount,
              segmentCount == pointCount - runCount,
              provenance.atlasIdentifier == atlas.identifier,
              provenance.atlasVersion == atlas.version,
              !limitations.isEmpty,
              limitations.allSatisfy({
                  !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
              }),
              limitations.contains(where: { $0.localizedCaseInsensitiveContains("pial") }),
              limitations.contains(where: { $0.localizedCaseInsensitiveContains("subject-specific") })
        else {
            throw MajorVesselContractError.invalid(
                "Major-vessel geometry metadata is inconsistent."
            )
        }
        try pointsBuffer.require(scalarType: "float32", shape: [pointCount, 3])
        try radiiBuffer.require(scalarType: "float32", shape: [pointCount])
        try offsetsBuffer.require(scalarType: "int64", shape: [runCount + 1])
        try edgesBuffer.require(scalarType: "int32", shape: [runCount])
        let pointScalars = try pointsBuffer.float32Values()
        var points: [SIMD3<Float>] = []
        points.reserveCapacity(pointCount)
        for index in 0 ..< pointCount {
            points.append(
                SIMD3(
                    pointScalars[index * 3],
                    pointScalars[index * 3 + 1],
                    pointScalars[index * 3 + 2]
                )
            )
        }
        graph = try MajorVesselGraph(
            pointsASRMicrometres: points,
            radiiMicrometres: try radiiBuffer.float32Values(),
            runOffsets: try offsetsBuffer.intValues(),
            sourceEdgeIndices: try edgesBuffer.int32Values(),
            atlas: atlas,
            minimumIncludedDiameterMicrometres: provenance.minimumIncludedDiameterMicrometres
        )
        guard graph.pointCount == pointCount,
              graph.runCount == runCount,
              graph.segmentCount == segmentCount
        else {
            throw MajorVesselContractError.invalid(
                "Decoded major-vessel geometry does not match its declared counts."
            )
        }
    }
}

private struct MajorVesselBuffer: Decodable, Equatable, Sendable {
    let scalarType: String
    let byteOrder: String
    let shape: [Int]
    let byteLength: Int
    let sha256: String
    let dataBase64: Data

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case scalarType
        case byteOrder
        case shape
        case byteLength
        case sha256
        case dataBase64
    }

    init(from decoder: any Decoder) throws {
        try requireMajorVesselExactKeys(decoder, CodingKeys.self, label: "major-vessel buffer")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        scalarType = try container.decode(String.self, forKey: .scalarType)
        byteOrder = try container.decode(String.self, forKey: .byteOrder)
        shape = try container.decode([Int].self, forKey: .shape)
        byteLength = try container.decode(Int.self, forKey: .byteLength)
        sha256 = try container.decode(String.self, forKey: .sha256)
        dataBase64 = try container.decode(Data.self, forKey: .dataBase64)
        guard byteOrder == "littleEndian",
              byteLength > 0,
              byteLength <= MajorVesselContract.maximumBufferByteCount,
              byteLength == dataBase64.count,
              isMajorVesselSHA256(sha256),
              SHA256.hash(data: dataBase64).hex == sha256,
              !shape.isEmpty,
              shape.allSatisfy({ $0 > 0 })
        else {
            throw MajorVesselContractError.invalid(
                "Major-vessel binary buffer failed its integrity contract."
            )
        }
    }

    func require(scalarType expectedScalarType: String, shape expectedShape: [Int]) throws {
        let scalarByteCount: Int
        switch expectedScalarType {
        case "float32", "int32": scalarByteCount = 4
        case "int64": scalarByteCount = 8
        default: throw MajorVesselContractError.invalid("Unsupported major-vessel scalar type.")
        }
        var elementCount = 1
        for dimension in expectedShape {
            let multiplication = elementCount.multipliedReportingOverflow(by: dimension)
            guard !multiplication.overflow else {
                throw MajorVesselContractError.invalid("Major-vessel buffer shape overflowed.")
            }
            elementCount = multiplication.partialValue
        }
        let byteMultiplication = elementCount.multipliedReportingOverflow(by: scalarByteCount)
        guard !byteMultiplication.overflow,
              scalarType == expectedScalarType,
              shape == expectedShape,
              byteLength == byteMultiplication.partialValue
        else {
            throw MajorVesselContractError.invalid(
                "Major-vessel buffer scalar type, shape, or byte count is inconsistent."
            )
        }
    }

    func float32Values() throws -> [Float] {
        guard scalarType == "float32", byteLength % 4 == 0 else {
            throw MajorVesselContractError.invalid("Major-vessel float buffer is inconsistent.")
        }
        return dataBase64.withUnsafeBytes { bytes in
            (0 ..< byteLength / 4).map { index in
                let bits = UInt32(littleEndian: bytes.loadUnaligned(
                    fromByteOffset: index * 4,
                    as: UInt32.self
                ))
                return Float(bitPattern: bits)
            }
        }
    }

    func intValues() throws -> [Int] {
        guard scalarType == "int64", byteLength % 8 == 0 else {
            throw MajorVesselContractError.invalid("Major-vessel offset buffer is inconsistent.")
        }
        return try dataBase64.withUnsafeBytes { bytes in
            try (0 ..< byteLength / 8).map { index in
                let value = Int64(littleEndian: bytes.loadUnaligned(
                    fromByteOffset: index * 8,
                    as: Int64.self
                ))
                guard let converted = Int(exactly: value) else {
                    throw MajorVesselContractError.invalid(
                        "Major-vessel run offset exceeds the native integer range."
                    )
                }
                return converted
            }
        }
    }

    func int32Values() throws -> [Int32] {
        guard scalarType == "int32", byteLength % 4 == 0 else {
            throw MajorVesselContractError.invalid("Major-vessel edge buffer is inconsistent.")
        }
        return dataBase64.withUnsafeBytes { bytes in
            (0 ..< byteLength / 4).map { index in
                Int32(littleEndian: bytes.loadUnaligned(
                    fromByteOffset: index * 4,
                    as: Int32.self
                ))
            }
        }
    }
}

private func requireMajorVesselExactKeys<Keys: CodingKey & CaseIterable>(
    _ decoder: any Decoder,
    _ keyType: Keys.Type,
    label: String
) throws {
    let dynamic = try decoder.container(keyedBy: MajorVesselDynamicCodingKey.self)
    let actual = Set(dynamic.allKeys.map(\.stringValue))
    let expected = Set(Keys.allCases.map(\.stringValue))
    guard actual == expected else {
        throw MajorVesselContractError.invalid(
            "\(label) keys do not match protocol v1 exactly."
        )
    }
}

private struct MajorVesselDynamicCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int? = nil

    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}

private func isMajorVesselSHA256(_ value: String) -> Bool {
    value.utf8.count == 64 && value.utf8.allSatisfy {
        ($0 >= 48 && $0 <= 57) || ($0 >= 97 && $0 <= 102)
    }
}

private extension Digest {
    var hex: String { map { String(format: "%02x", $0) }.joined() }
}
