import Foundation

public enum DorsalPickContractError: Error, Equatable, LocalizedError, Sendable {
    case invalid(String)

    public var errorDescription: String? {
        switch self {
        case let .invalid(message): message
        }
    }
}

public struct DorsalPickParameters: Encodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let column: Int
    public let row: Int

    public init(column: Int, row: Int) throws {
        guard column >= 0, row >= 0 else {
            throw DorsalPickContractError.invalid(
                "Dorsal atlas pixel coordinates must be nonnegative."
            )
        }
        protocolVersion = BridgeProtocolVersion.current
        self.column = column
        self.row = row
    }
}

public enum DorsalPickStatus: String, Decodable, CaseIterable, Equatable, Sendable {
    case hit
    case noAnnotatedVoxel
}

public struct DorsalPickResult: Decodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: DorsalPickStatus
    public let column: Int
    public let row: Int
    public let atlasPoint: AtlasPhysicalPoint?
    public let containingVoxelIndex: AtlasVoxelIndex?
    public let annotationStructureId: Int?
    public let region: AtlasRegionSummary?
    public let hemisphere: AtlasHemisphere?
    public let atlas: ViewerAtlasIdentity

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case protocolVersion
        case status
        case column
        case row
        case atlasPoint
        case containingVoxelIndex
        case annotationStructureId
        case region
        case hemisphere
        case atlas
    }

    public init(from decoder: any Decoder) throws {
        try requireDorsalPickExactKeys(decoder, CodingKeys.self, label: "dorsal atlas pick")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        protocolVersion = try container.decode(Int.self, forKey: .protocolVersion)
        status = try container.decode(DorsalPickStatus.self, forKey: .status)
        column = try container.decode(Int.self, forKey: .column)
        row = try container.decode(Int.self, forKey: .row)
        atlasPoint = try container.decodeIfPresent(AtlasPhysicalPoint.self, forKey: .atlasPoint)
        containingVoxelIndex = try container.decodeIfPresent(
            AtlasVoxelIndex.self,
            forKey: .containingVoxelIndex
        )
        annotationStructureId = try container.decodeIfPresent(
            Int.self,
            forKey: .annotationStructureId
        )
        region = try container.decodeIfPresent(AtlasRegionSummary.self, forKey: .region)
        hemisphere = try container.decodeIfPresent(AtlasHemisphere.self, forKey: .hemisphere)
        atlas = try container.decode(ViewerAtlasIdentity.self, forKey: .atlas)
        try validate()
    }

    private func validate() throws {
        guard protocolVersion == BridgeProtocolVersion.current,
              column >= 0,
              column < atlas.shapeVoxels.mlVoxels,
              row >= 0,
              row < atlas.shapeVoxels.apVoxels
        else {
            throw DorsalPickContractError.invalid(
                "Dorsal pick protocol or intrinsic AP/ML pixel coordinates are invalid."
            )
        }

        switch status {
        case .noAnnotatedVoxel:
            guard atlasPoint == nil,
                  containingVoxelIndex == nil,
                  annotationStructureId == nil,
                  region == nil,
                  hemisphere == nil
            else {
                throw DorsalPickContractError.invalid(
                    "An unannotated dorsal column must not include fabricated hit metadata."
                )
            }
        case .hit:
            guard let atlasPoint,
                  let containingVoxelIndex,
                  let annotationStructureId,
                  let region,
                  hemisphere != nil,
                  annotationStructureId > 0,
                  annotationStructureId == region.structureId,
                  containingVoxelIndex.ap == row,
                  containingVoxelIndex.ml == column,
                  containingVoxelIndex.dv < atlas.shapeVoxels.dvVoxels
            else {
                throw DorsalPickContractError.invalid(
                    "Dorsal hit metadata does not identify the clicked AP/ML atlas column."
                )
            }

            let expectedAP = (Double(containingVoxelIndex.ap) + 0.5)
                * atlas.resolutionMicrometres.apMicrometres
            let expectedDV = (Double(containingVoxelIndex.dv) + 0.5)
                * atlas.resolutionMicrometres.dvMicrometres
            let expectedML = (Double(containingVoxelIndex.ml) + 0.5)
                * atlas.resolutionMicrometres.mlMicrometres
            guard dorsalPickApproximatelyEqual(atlasPoint.apMicrometres, expectedAP),
                  dorsalPickApproximatelyEqual(atlasPoint.dvMicrometres, expectedDV),
                  dorsalPickApproximatelyEqual(atlasPoint.mlMicrometres, expectedML)
            else {
                throw DorsalPickContractError.invalid(
                    "Dorsal hit physical coordinates must be the containing voxel centre."
                )
            }
        }
    }
}

private func requireDorsalPickExactKeys<Keys: CodingKey & CaseIterable>(
    _ decoder: any Decoder,
    _ keyType: Keys.Type,
    label: String
) throws {
    let container = try decoder.container(keyedBy: AnyDorsalPickCodingKey.self)
    let expected = Set(keyType.allCases.map(\.stringValue))
    let actual = Set(container.allKeys.map(\.stringValue))
    guard actual == expected else {
        throw DorsalPickContractError.invalid(
            "Unexpected \(label) keys: expected \(expected.sorted()), got \(actual.sorted())."
        )
    }
}

private struct AnyDorsalPickCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int?

    init?(stringValue: String) {
        self.stringValue = stringValue
        intValue = nil
    }

    init?(intValue: Int) {
        stringValue = String(intValue)
        self.intValue = intValue
    }
}

private func dorsalPickApproximatelyEqual(_ lhs: Double, _ rhs: Double) -> Bool {
    abs(lhs - rhs) <= max(1e-9, max(abs(lhs), abs(rhs)) * 1e-12)
}
