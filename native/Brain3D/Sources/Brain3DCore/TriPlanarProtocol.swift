import Foundation

public enum ViewerContractError: Error, Equatable, LocalizedError, Sendable {
    case invalid(String)

    public var errorDescription: String? {
        switch self {
        case let .invalid(message):
            message
        }
    }
}

public enum ViewerBridgeMethod: String, Codable, CaseIterable, Sendable {
    case stateGet = "viewer.state.get"
    case sliceSet = "viewer.slice.set"
    case sliceRender = "viewer.slice.render"
    case regionPick = "viewer.region.pick"
}

public enum AtlasAnatomicalAxis: String, Codable, CaseIterable, Sendable {
    case ap = "AP"
    case dv = "DV"
    case ml = "ML"
}

public enum AtlasSliceOrientation: String, Codable, CaseIterable, Sendable {
    case coronal
    case sagittal
    case horizontal

    public var fixedAxis: AtlasAnatomicalAxis {
        switch self {
        case .coronal: .ap
        case .sagittal: .ml
        case .horizontal: .dv
        }
    }

    public var rowAxis: AtlasAnatomicalAxis {
        switch self {
        case .coronal, .sagittal: .dv
        case .horizontal: .ap
        }
    }

    public var columnAxis: AtlasAnatomicalAxis {
        switch self {
        case .coronal, .horizontal: .ml
        case .sagittal: .ap
        }
    }
}

public enum AtlasHemisphere: String, Codable, CaseIterable, Sendable {
    case right
    case midline
    case left
}

public enum AtlasOriginDirection: String, Codable, CaseIterable, Sendable {
    case anterior
    case superior
    case right
}

public enum AtlasPositiveDirection: String, Codable, CaseIterable, Sendable {
    case posterior
    case inferior
    case left
}

public struct AtlasASRResolution: Codable, Equatable, Sendable {
    public let apMicrometres: Double
    public let dvMicrometres: Double
    public let mlMicrometres: Double

    public init(
        apMicrometres: Double,
        dvMicrometres: Double,
        mlMicrometres: Double
    ) throws {
        let values = [apMicrometres, dvMicrometres, mlMicrometres]
        guard values.allSatisfy({ $0.isFinite && $0 > 0 }) else {
            throw ViewerContractError.invalid(
                "Atlas ASR resolution must contain three positive finite values."
            )
        }
        self.apMicrometres = apMicrometres
        self.dvMicrometres = dvMicrometres
        self.mlMicrometres = mlMicrometres
    }

    public init(from decoder: any Decoder) throws {
        var container = try decoder.unkeyedContainer()
        let ap = try container.decode(Double.self)
        let dv = try container.decode(Double.self)
        let ml = try container.decode(Double.self)
        guard container.isAtEnd else {
            throw ViewerContractError.invalid(
                "Atlas resolution must use exact [AP,DV,ML] order."
            )
        }
        try self.init(apMicrometres: ap, dvMicrometres: dv, mlMicrometres: ml)
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.unkeyedContainer()
        try container.encode(apMicrometres)
        try container.encode(dvMicrometres)
        try container.encode(mlMicrometres)
    }

    public subscript(axis: AtlasAnatomicalAxis) -> Double {
        switch axis {
        case .ap: apMicrometres
        case .dv: dvMicrometres
        case .ml: mlMicrometres
        }
    }
}

public struct AtlasASRShape: Codable, Equatable, Sendable {
    public let apVoxels: Int
    public let dvVoxels: Int
    public let mlVoxels: Int

    public init(apVoxels: Int, dvVoxels: Int, mlVoxels: Int) throws {
        let values = [apVoxels, dvVoxels, mlVoxels]
        guard values.allSatisfy({ $0 > 0 }) else {
            throw ViewerContractError.invalid(
                "Atlas ASR shape must contain three positive voxel counts."
            )
        }
        self.apVoxels = apVoxels
        self.dvVoxels = dvVoxels
        self.mlVoxels = mlVoxels
    }

    public init(from decoder: any Decoder) throws {
        var container = try decoder.unkeyedContainer()
        let ap = try container.decode(Int.self)
        let dv = try container.decode(Int.self)
        let ml = try container.decode(Int.self)
        guard container.isAtEnd else {
            throw ViewerContractError.invalid(
                "Atlas shape must use exact [AP,DV,ML] order."
            )
        }
        try self.init(apVoxels: ap, dvVoxels: dv, mlVoxels: ml)
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.unkeyedContainer()
        try container.encode(apVoxels)
        try container.encode(dvVoxels)
        try container.encode(mlVoxels)
    }

    public subscript(axis: AtlasAnatomicalAxis) -> Int {
        switch axis {
        case .ap: apVoxels
        case .dv: dvVoxels
        case .ml: mlVoxels
        }
    }
}

public struct ViewerAtlasIdentity: Decodable, Equatable, Sendable {
    public let identifier: String
    public let version: String
    public let metadataSha256: String
    public let resolutionMicrometres: AtlasASRResolution
    public let shapeVoxels: AtlasASRShape
    public let orientation: String
    public let frameworkName: String
    public let sourceAnnotation: String?
    public let citation: String
    public let brainGlobeAtlasApiVersion: String

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case identifier
        case version
        case metadataSha256
        case resolutionMicrometres
        case shapeVoxels
        case orientation
        case frameworkName
        case sourceAnnotation
        case citation
        case brainGlobeAtlasApiVersion
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "viewer atlas identity")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        identifier = try container.decode(String.self, forKey: .identifier)
        version = try container.decode(String.self, forKey: .version)
        metadataSha256 = try container.decode(String.self, forKey: .metadataSha256)
        resolutionMicrometres = try container.decode(
            AtlasASRResolution.self,
            forKey: .resolutionMicrometres
        )
        shapeVoxels = try container.decode(AtlasASRShape.self, forKey: .shapeVoxels)
        orientation = try container.decode(String.self, forKey: .orientation)
        frameworkName = try container.decode(String.self, forKey: .frameworkName)
        sourceAnnotation = try container.decodeIfPresent(String.self, forKey: .sourceAnnotation)
        citation = try container.decode(String.self, forKey: .citation)
        brainGlobeAtlasApiVersion = try container.decode(
            String.self,
            forKey: .brainGlobeAtlasApiVersion
        )
        try validate()
    }

    private func validate() throws {
        guard identifier == SafetyPolicy.supportedAtlasIdentifier,
              version == SafetyPolicy.supportedAtlasVersion
        else {
            throw ViewerContractError.invalid(
                "Viewer state must use the exact supported atlas identity."
            )
        }
        guard metadataSha256.utf8.count == 64,
              metadataSha256.utf8.allSatisfy({
                  ($0 >= 48 && $0 <= 57) || ($0 >= 97 && $0 <= 102)
              })
        else {
            throw ViewerContractError.invalid(
                "Atlas metadataSha256 must be 64 lowercase hexadecimal characters."
            )
        }
        guard orientation == "asr" else {
            throw ViewerContractError.invalid(
                "Atlas orientation must be the reviewed BrainGlobe ASR orientation."
            )
        }
        guard !frameworkName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !citation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !brainGlobeAtlasApiVersion.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw ViewerContractError.invalid(
                "Atlas provenance text fields must be nonempty."
            )
        }
        if let sourceAnnotation,
           sourceAnnotation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        {
            throw ViewerContractError.invalid(
                "sourceAnnotation must be nonempty when supplied."
            )
        }
    }
}

public struct AtlasAxisDescriptor: Decodable, Equatable, Sendable {
    public let arrayAxis: Int
    public let anatomicalAxis: AtlasAnatomicalAxis
    public let originDirection: AtlasOriginDirection
    public let positiveDirection: AtlasPositiveDirection
    public let voxelSizeMicrometres: Double

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case arrayAxis
        case anatomicalAxis
        case originDirection
        case positiveDirection
        case voxelSizeMicrometres
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "atlas axis descriptor")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        arrayAxis = try container.decode(Int.self, forKey: .arrayAxis)
        anatomicalAxis = try container.decode(AtlasAnatomicalAxis.self, forKey: .anatomicalAxis)
        originDirection = try container.decode(AtlasOriginDirection.self, forKey: .originDirection)
        positiveDirection = try container.decode(
            AtlasPositiveDirection.self,
            forKey: .positiveDirection
        )
        voxelSizeMicrometres = try container.decode(Double.self, forKey: .voxelSizeMicrometres)
        guard (0 ... 2).contains(arrayAxis),
              voxelSizeMicrometres.isFinite,
              voxelSizeMicrometres > 0
        else {
            throw ViewerContractError.invalid(
                "Atlas axis index and voxel size must be valid."
            )
        }
    }
}

public struct AtlasCoordinateBounds: Decodable, Equatable, Sendable {
    public let minimumInclusiveMicrometres: [Double]
    public let maximumExclusiveMicrometres: [Double]

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case minimumInclusiveMicrometres
        case maximumExclusiveMicrometres
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "atlas coordinate bounds")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        minimumInclusiveMicrometres = try container.decode(
            [Double].self,
            forKey: .minimumInclusiveMicrometres
        )
        maximumExclusiveMicrometres = try container.decode(
            [Double].self,
            forKey: .maximumExclusiveMicrometres
        )
        guard minimumInclusiveMicrometres.count == 3,
              maximumExclusiveMicrometres.count == 3,
              minimumInclusiveMicrometres.allSatisfy({ $0.isFinite }),
              maximumExclusiveMicrometres.allSatisfy({ $0.isFinite })
        else {
            throw ViewerContractError.invalid(
                "Atlas coordinate bounds must contain finite [AP,DV,ML] triples."
            )
        }
    }
}

public struct AtlasPhysicalCoordinateFrame: Decodable, Equatable, Sendable {
    public static let expectedFrameId = "BRAINGLOBE_PHYSICAL_ASR_UM"

    public let frameId: String
    public let unit: String
    public let coordinateKind: String
    public let axisOrder: [AtlasAnatomicalAxis]
    public let origin: [AtlasOriginDirection]
    public let positiveDirections: [AtlasPositiveDirection]
    public let axes: [AtlasAxisDescriptor]
    public let bregmaRelative: Bool
    public let stereotaxicCalibrationApplied: Bool
    public let voxelAnchorOffsetApplied: Bool
    public let bounds: AtlasCoordinateBounds

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case frameId
        case unit
        case coordinateKind
        case axisOrder
        case origin
        case positiveDirections
        case axes
        case bregmaRelative
        case stereotaxicCalibrationApplied
        case voxelAnchorOffsetApplied
        case bounds
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "atlas physical coordinate frame")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        frameId = try container.decode(String.self, forKey: .frameId)
        unit = try container.decode(String.self, forKey: .unit)
        coordinateKind = try container.decode(String.self, forKey: .coordinateKind)
        axisOrder = try container.decode([AtlasAnatomicalAxis].self, forKey: .axisOrder)
        origin = try container.decode([AtlasOriginDirection].self, forKey: .origin)
        positiveDirections = try container.decode(
            [AtlasPositiveDirection].self,
            forKey: .positiveDirections
        )
        axes = try container.decode([AtlasAxisDescriptor].self, forKey: .axes)
        bregmaRelative = try container.decode(Bool.self, forKey: .bregmaRelative)
        stereotaxicCalibrationApplied = try container.decode(
            Bool.self,
            forKey: .stereotaxicCalibrationApplied
        )
        voxelAnchorOffsetApplied = try container.decode(
            Bool.self,
            forKey: .voxelAnchorOffsetApplied
        )
        bounds = try container.decode(AtlasCoordinateBounds.self, forKey: .bounds)
        try validateSemantics()
    }

    private func validateSemantics() throws {
        let expectedAxes: [AtlasAnatomicalAxis] = [.ap, .dv, .ml]
        let expectedOrigins: [AtlasOriginDirection] = [.anterior, .superior, .right]
        let expectedPositive: [AtlasPositiveDirection] = [.posterior, .inferior, .left]
        guard frameId == Self.expectedFrameId,
              unit == "micrometres",
              coordinateKind == "continuousPhysical",
              axisOrder == expectedAxes,
              origin == expectedOrigins,
              positiveDirections == expectedPositive,
              !bregmaRelative,
              !stereotaxicCalibrationApplied,
              !voxelAnchorOffsetApplied,
              axes.count == 3
        else {
            throw ViewerContractError.invalid(
                "Coordinate frame must be explicit BrainGlobe [AP,DV,ML] physical ASR."
            )
        }
        for (index, descriptor) in axes.enumerated() {
            guard descriptor.arrayAxis == index,
                  descriptor.anatomicalAxis == expectedAxes[index],
                  descriptor.originDirection == expectedOrigins[index],
                  descriptor.positiveDirection == expectedPositive[index]
            else {
                throw ViewerContractError.invalid(
                    "Coordinate-frame axis descriptors do not match BrainGlobe ASR."
                )
            }
        }
    }
}

public struct AtlasPhysicalPoint: Codable, Equatable, Sendable {
    public let frameId: String
    public let apMicrometres: Double
    public let dvMicrometres: Double
    public let mlMicrometres: Double

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case frameId
        case apMicrometres
        case dvMicrometres
        case mlMicrometres
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "atlas physical point")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        frameId = try container.decode(String.self, forKey: .frameId)
        apMicrometres = try container.decode(Double.self, forKey: .apMicrometres)
        dvMicrometres = try container.decode(Double.self, forKey: .dvMicrometres)
        mlMicrometres = try container.decode(Double.self, forKey: .mlMicrometres)
        guard frameId == AtlasPhysicalCoordinateFrame.expectedFrameId else {
            throw ViewerContractError.invalid(
                "Atlas point frameId must be BRAINGLOBE_PHYSICAL_ASR_UM."
            )
        }
        guard [apMicrometres, dvMicrometres, mlMicrometres]
            .allSatisfy({ $0.isFinite && $0 >= 0 })
        else {
            throw ViewerContractError.invalid(
                "Atlas point coordinates must be finite nonnegative micrometre values."
            )
        }
    }

    public subscript(axis: AtlasAnatomicalAxis) -> Double {
        switch axis {
        case .ap: apMicrometres
        case .dv: dvMicrometres
        case .ml: mlMicrometres
        }
    }
}

public struct AtlasVoxelIndex: Decodable, Equatable, Sendable {
    public static let expectedFrameId = "BRAINGLOBE_VOXEL_INDEX_ASR"

    public let frameId: String
    public let ap: Int
    public let dv: Int
    public let ml: Int

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case frameId
        case ap
        case dv
        case ml
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "atlas voxel index")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        frameId = try container.decode(String.self, forKey: .frameId)
        ap = try container.decode(Int.self, forKey: .ap)
        dv = try container.decode(Int.self, forKey: .dv)
        ml = try container.decode(Int.self, forKey: .ml)
        guard frameId == Self.expectedFrameId, ap >= 0, dv >= 0, ml >= 0 else {
            throw ViewerContractError.invalid(
                "Voxel indices must be nonnegative BrainGlobe [AP,DV,ML] indices."
            )
        }
    }

    public subscript(axis: AtlasAnatomicalAxis) -> Int {
        switch axis {
        case .ap: ap
        case .dv: dv
        case .ml: ml
        }
    }
}

public struct AtlasRegionSummary: Decodable, Equatable, Sendable {
    public let structureId: Int
    public let acronym: String
    public let name: String
    public let parentStructureId: Int?
    public let structureIdPath: [Int]
    public let rgb: [Int]

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case structureId
        case acronym
        case name
        case parentStructureId
        case structureIdPath
        case rgb
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "atlas region summary")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        structureId = try container.decode(Int.self, forKey: .structureId)
        acronym = try container.decode(String.self, forKey: .acronym)
        name = try container.decode(String.self, forKey: .name)
        parentStructureId = try container.decodeIfPresent(Int.self, forKey: .parentStructureId)
        structureIdPath = try container.decode([Int].self, forKey: .structureIdPath)
        rgb = try container.decode([Int].self, forKey: .rgb)

        guard structureId > 0,
              !acronym.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !structureIdPath.isEmpty,
              structureIdPath.allSatisfy({ $0 > 0 }),
              structureIdPath.last == structureId,
              rgb.count == 3,
              rgb.allSatisfy({ (0 ... 255).contains($0) })
        else {
            throw ViewerContractError.invalid("Atlas region metadata is malformed.")
        }
        let expectedParent = structureIdPath.count > 1
            ? structureIdPath[structureIdPath.count - 2]
            : nil
        guard parentStructureId == expectedParent else {
            throw ViewerContractError.invalid(
                "Atlas region parent must agree with structureIdPath."
            )
        }
    }
}

public struct TriPlanarSliceMetadata: Decodable, Equatable, Sendable {
    public let orientation: AtlasSliceOrientation
    public let index: Int
    public let sliceCount: Int
    public let fixedAxis: AtlasAnatomicalAxis
    public let rowAxis: AtlasAnatomicalAxis
    public let columnAxis: AtlasAnatomicalAxis
    public let sliceCenterMicrometres: Double

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case orientation
        case index
        case sliceCount
        case fixedAxis
        case rowAxis
        case columnAxis
        case sliceCenterMicrometres
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "tri-planar slice metadata")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        orientation = try container.decode(AtlasSliceOrientation.self, forKey: .orientation)
        index = try container.decode(Int.self, forKey: .index)
        sliceCount = try container.decode(Int.self, forKey: .sliceCount)
        fixedAxis = try container.decode(AtlasAnatomicalAxis.self, forKey: .fixedAxis)
        rowAxis = try container.decode(AtlasAnatomicalAxis.self, forKey: .rowAxis)
        columnAxis = try container.decode(AtlasAnatomicalAxis.self, forKey: .columnAxis)
        sliceCenterMicrometres = try container.decode(
            Double.self,
            forKey: .sliceCenterMicrometres
        )
        guard index >= 0,
              sliceCount > 0,
              index < sliceCount,
              sliceCenterMicrometres.isFinite,
              sliceCenterMicrometres >= 0,
              fixedAxis == orientation.fixedAxis,
              rowAxis == orientation.rowAxis,
              columnAxis == orientation.columnAxis
        else {
            throw ViewerContractError.invalid(
                "Slice metadata does not match the canonical orientation-axis table."
            )
        }
    }
}

public struct TriPlanarSlices: Decodable, Equatable, Sendable {
    public let coronal: TriPlanarSliceMetadata
    public let sagittal: TriPlanarSliceMetadata
    public let horizontal: TriPlanarSliceMetadata

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case coronal
        case sagittal
        case horizontal
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "tri-planar slice set")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        coronal = try container.decode(TriPlanarSliceMetadata.self, forKey: .coronal)
        sagittal = try container.decode(TriPlanarSliceMetadata.self, forKey: .sagittal)
        horizontal = try container.decode(TriPlanarSliceMetadata.self, forKey: .horizontal)
        guard coronal.orientation == .coronal,
              sagittal.orientation == .sagittal,
              horizontal.orientation == .horizontal
        else {
            throw ViewerContractError.invalid(
                "Named tri-planar slices must contain their matching orientations."
            )
        }
    }

    public subscript(orientation: AtlasSliceOrientation) -> TriPlanarSliceMetadata {
        switch orientation {
        case .coronal: coronal
        case .sagittal: sagittal
        case .horizontal: horizontal
        }
    }
}

public struct ViewerCanonicalSnapshot: Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: UUID
    public let projectRevision: Int
    public let atlas: ViewerAtlasIdentity
    public let coordinateFrame: AtlasPhysicalCoordinateFrame
    public let slices: TriPlanarSlices
    public let selection: ViewerRegionSelection?

    fileprivate init(
        protocolVersion: Int,
        projectId: UUID,
        projectRevision: Int,
        atlas: ViewerAtlasIdentity,
        coordinateFrame: AtlasPhysicalCoordinateFrame,
        slices: TriPlanarSlices,
        selection: ViewerRegionSelection?
    ) throws {
        self.protocolVersion = protocolVersion
        self.projectId = projectId
        self.projectRevision = projectRevision
        self.atlas = atlas
        self.coordinateFrame = coordinateFrame
        self.slices = slices
        self.selection = selection
        try validate()
    }

    private func validate() throws {
        guard protocolVersion == BridgeProtocolVersion.current else {
            throw ViewerContractError.invalid(
                "Viewer snapshot protocolVersion does not match the Swift bridge."
            )
        }
        guard projectRevision >= 0 else {
            throw ViewerContractError.invalid("Project revision must be nonnegative.")
        }

        let expectedAxes: [AtlasAnatomicalAxis] = [.ap, .dv, .ml]
        let minimum = coordinateFrame.bounds.minimumInclusiveMicrometres
        let maximum = coordinateFrame.bounds.maximumExclusiveMicrometres
        for (arrayIndex, axis) in expectedAxes.enumerated() {
            let resolution = atlas.resolutionMicrometres[axis]
            let count = atlas.shapeVoxels[axis]
            let expectedExtent = Double(count) * resolution
            guard expectedExtent.isFinite,
                  approximatelyEqual(minimum[arrayIndex], 0),
                  approximatelyEqual(maximum[arrayIndex], expectedExtent),
                  approximatelyEqual(
                      coordinateFrame.axes[arrayIndex].voxelSizeMicrometres,
                      resolution
                  )
            else {
                throw ViewerContractError.invalid(
                    "Coordinate frame bounds or voxel sizes do not match the atlas."
                )
            }

        }

        for orientation in AtlasSliceOrientation.allCases {
            let slice = slices[orientation]
            let expectedCount = atlas.shapeVoxels[orientation.fixedAxis]
            let expectedCenter =
                (Double(slice.index) + 0.5)
                * atlas.resolutionMicrometres[orientation.fixedAxis]
            guard slice.sliceCount == expectedCount,
                  slice.index < expectedCount,
                  approximatelyEqual(slice.sliceCenterMicrometres, expectedCenter)
            else {
                throw ViewerContractError.invalid(
                    "Independent slice index, center, or count disagrees with the atlas."
                )
            }
        }
        try selection?.validate(against: self)
    }
}

public struct ViewerRegionSelection: Decodable, Equatable, Sendable {
    public let orientation: AtlasSliceOrientation
    public let index: Int
    public let column: Int
    public let row: Int
    public let atlasPoint: AtlasPhysicalPoint
    public let containingVoxelIndex: AtlasVoxelIndex
    public let region: AtlasRegionSummary?
    public let hemisphere: AtlasHemisphere

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case orientation
        case index
        case column
        case row
        case atlasPoint
        case containingVoxelIndex
        case region
        case hemisphere
    }

    public init(from decoder: any Decoder) throws {
        try requireExactKeys(decoder, CodingKeys.self, label: "viewer region selection")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        orientation = try container.decode(AtlasSliceOrientation.self, forKey: .orientation)
        index = try container.decode(Int.self, forKey: .index)
        column = try container.decode(Int.self, forKey: .column)
        row = try container.decode(Int.self, forKey: .row)
        atlasPoint = try container.decode(AtlasPhysicalPoint.self, forKey: .atlasPoint)
        containingVoxelIndex = try container.decode(
            AtlasVoxelIndex.self,
            forKey: .containingVoxelIndex
        )
        region = try container.decodeIfPresent(AtlasRegionSummary.self, forKey: .region)
        hemisphere = try container.decode(AtlasHemisphere.self, forKey: .hemisphere)
        guard index >= 0, column >= 0, row >= 0 else {
            throw ViewerContractError.invalid(
                "Region-selection slice and pixel values must be nonnegative integers."
            )
        }
    }

    fileprivate func validate(against snapshot: ViewerCanonicalSnapshot) throws {
        let slice = snapshot.slices[orientation]
        let expectedVoxelByAxis: [AtlasAnatomicalAxis: Int] = [
            orientation.fixedAxis: index,
            orientation.columnAxis: column,
            orientation.rowAxis: row,
        ]
        guard index == slice.index,
              column < snapshot.atlas.shapeVoxels[orientation.columnAxis],
              row < snapshot.atlas.shapeVoxels[orientation.rowAxis]
        else {
            throw ViewerContractError.invalid(
                "Region selection must belong to the persisted slice and intrinsic PNG bounds."
            )
        }
        for axis in AtlasAnatomicalAxis.allCases {
            guard let expectedIndex = expectedVoxelByAxis[axis],
                  containingVoxelIndex[axis] == expectedIndex
            else {
                throw ViewerContractError.invalid(
                    "Region selection voxel index does not match its slice pixel."
                )
            }
            let expectedCenter =
                (Double(expectedIndex) + 0.5) * snapshot.atlas.resolutionMicrometres[axis]
            guard approximatelyEqual(atlasPoint[axis], expectedCenter) else {
                throw ViewerContractError.invalid(
                    "Region selection atlas point is not the selected voxel center."
                )
            }
        }

        let midline =
            Double(snapshot.atlas.shapeVoxels.mlVoxels)
            * snapshot.atlas.resolutionMicrometres.mlMicrometres / 2.0
        let delta = atlasPoint.mlMicrometres - midline
        let expectedHemisphere: AtlasHemisphere = if abs(delta) <= 1e-9 {
            .midline
        } else if delta < 0 {
            .right
        } else {
            .left
        }
        guard hemisphere == expectedHemisphere else {
            throw ViewerContractError.invalid(
                "Region-selection hemisphere does not match its atlas ML coordinate."
            )
        }
    }
}

public struct ViewerStateParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int

    public init() {
        protocolVersion = BridgeProtocolVersion.current
    }
}

public struct ViewerSliceSetParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let orientation: AtlasSliceOrientation
    public let index: Int

    public init(
        projectId: UUID,
        expectedProjectRevision: Int,
        orientation: AtlasSliceOrientation,
        index: Int
    ) throws {
        guard expectedProjectRevision >= 0, index >= 0 else {
            throw ViewerContractError.invalid(
                "Expected project revision and slice index must be nonnegative."
            )
        }
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId.uuidString.lowercased()
        self.expectedProjectRevision = expectedProjectRevision
        self.orientation = orientation
        self.index = index
    }
}

/// The fused slice mutation uses the same exact request shape as `viewer.slice.set`.
public typealias ViewerSliceRenderParameters = ViewerSliceSetParameters

public struct ViewerRegionPickParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let orientation: AtlasSliceOrientation
    public let index: Int
    public let column: Int
    public let row: Int

    public init(
        projectId: UUID,
        expectedProjectRevision: Int,
        orientation: AtlasSliceOrientation,
        index: Int,
        column: Int,
        row: Int
    ) throws {
        guard expectedProjectRevision >= 0,
              index >= 0,
              column >= 0,
              row >= 0
        else {
            throw ViewerContractError.invalid(
                "Expected revision, slice index, column, and row must be nonnegative."
            )
        }
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId.uuidString.lowercased()
        self.expectedProjectRevision = expectedProjectRevision
        self.orientation = orientation
        self.index = index
        self.column = column
        self.row = row
    }
}

public struct ViewerStateResult: Decodable, Equatable, Sendable {
    public let snapshot: ViewerCanonicalSnapshot

    public init(from decoder: any Decoder) throws {
        snapshot = try decodeViewerSnapshot(from: decoder)
    }
}

public enum ViewerMutationStatus: String, Decodable, Equatable, Sendable {
    case sliceUpdated
    case regionSelected
}

public struct ViewerSliceUpdateResult: Decodable, Equatable, Sendable {
    public let status: ViewerMutationStatus
    public let snapshot: ViewerCanonicalSnapshot

    public init(from decoder: any Decoder) throws {
        snapshot = try decodeViewerSnapshot(from: decoder, additionalKeys: ["status"])
        let container = try decoder.container(keyedBy: AnyCodingKey.self)
        status = try container.decode(
            ViewerMutationStatus.self,
            forKey: AnyCodingKey("status")
        )
        guard status == .sliceUpdated else {
            throw ViewerContractError.invalid("Slice update returned an invalid status.")
        }
    }
}

public struct ViewerRegionPickResult: Decodable, Equatable, Sendable {
    public let status: ViewerMutationStatus
    public let snapshot: ViewerCanonicalSnapshot

    public init(from decoder: any Decoder) throws {
        snapshot = try decodeViewerSnapshot(
            from: decoder,
            additionalKeys: ["status"]
        )
        let container = try decoder.container(keyedBy: AnyCodingKey.self)
        status = try container.decode(
            ViewerMutationStatus.self,
            forKey: AnyCodingKey("status")
        )
        guard status == .regionSelected, snapshot.selection != nil else {
            throw ViewerContractError.invalid(
                "Region-pick response must contain a selected region pixel."
            )
        }
    }
}

public struct ViewerSliceRenderResult: Decodable, Equatable, Sendable {
    public let status: ViewerMutationStatus
    public let renderedSlice: AtlasSliceResult
    public let snapshot: ViewerCanonicalSnapshot

    public init(from decoder: any Decoder) throws {
        snapshot = try decodeViewerSnapshot(
            from: decoder,
            additionalKeys: ["status", "renderedSlice"]
        )
        let container = try decoder.container(keyedBy: AnyCodingKey.self)
        status = try container.decode(
            ViewerMutationStatus.self,
            forKey: AnyCodingKey("status")
        )
        guard status == .sliceUpdated else {
            throw ViewerContractError.invalid("Slice render returned an invalid status.")
        }
        renderedSlice = try container.decode(
            AtlasSliceResult.self,
            forKey: AnyCodingKey("renderedSlice")
        )
        try validateRenderedSlice()
    }

    private func validateRenderedSlice() throws {
        guard let orientation = AtlasSliceOrientation(rawValue: renderedSlice.orientation) else {
            throw ViewerContractError.invalid("Rendered slice orientation is unsupported.")
        }
        let expected = snapshot.slices[orientation]
        let expectedWidth = snapshot.atlas.shapeVoxels[orientation.columnAxis]
        let expectedHeight = snapshot.atlas.shapeVoxels[orientation.rowAxis]
        guard renderedSlice.protocolVersion == BridgeProtocolVersion.current,
              renderedSlice.mimeType == "image/png",
              !renderedSlice.pngBase64.isEmpty,
              renderedSlice.width == expectedWidth,
              renderedSlice.height == expectedHeight,
              renderedSlice.index == expected.index,
              renderedSlice.sliceCount == expected.sliceCount,
              renderedSlice.fixedAxis == expected.fixedAxis.rawValue,
              renderedSlice.rowAxis == expected.rowAxis.rawValue,
              renderedSlice.columnAxis == expected.columnAxis.rawValue,
              approximatelyEqual(
                  renderedSlice.sliceCenterMicrometres,
                  expected.sliceCenterMicrometres
              ),
              renderedSlice.atlas.identifier == snapshot.atlas.identifier,
              renderedSlice.atlas.version == snapshot.atlas.version,
              renderedSlice.atlas.metadataSha256 == snapshot.atlas.metadataSha256
        else {
            throw ViewerContractError.invalid(
                "Rendered slice does not match the canonical viewer snapshot."
            )
        }
    }
}

private let viewerSnapshotKeys: Set<String> = [
    "protocolVersion",
    "projectId",
    "projectRevision",
    "atlas",
    "coordinateFrame",
    "slices",
    "selection",
]

private func decodeViewerSnapshot(
    from decoder: any Decoder,
    additionalKeys: Set<String> = []
) throws -> ViewerCanonicalSnapshot {
    try requireExactKeys(
        decoder,
        allowed: viewerSnapshotKeys.union(additionalKeys),
        label: "viewer snapshot"
    )
    let container = try decoder.container(keyedBy: AnyCodingKey.self)
    return try ViewerCanonicalSnapshot(
        protocolVersion: container.decode(Int.self, forKey: AnyCodingKey("protocolVersion")),
        projectId: container.decode(UUID.self, forKey: AnyCodingKey("projectId")),
        projectRevision: container.decode(Int.self, forKey: AnyCodingKey("projectRevision")),
        atlas: container.decode(ViewerAtlasIdentity.self, forKey: AnyCodingKey("atlas")),
        coordinateFrame: container.decode(
            AtlasPhysicalCoordinateFrame.self,
            forKey: AnyCodingKey("coordinateFrame")
        ),
        slices: container.decode(TriPlanarSlices.self, forKey: AnyCodingKey("slices")),
        selection: container.decodeIfPresent(
            ViewerRegionSelection.self,
            forKey: AnyCodingKey("selection")
        )
    )
}

private struct AnyCodingKey: CodingKey, Hashable {
    let stringValue: String
    let intValue: Int?

    init(_ stringValue: String) {
        self.stringValue = stringValue
        intValue = nil
    }

    init?(stringValue: String) {
        self.init(stringValue)
    }

    init?(intValue: Int) {
        stringValue = String(intValue)
        self.intValue = intValue
    }
}

private func requireExactKeys<Keys: CodingKey & CaseIterable>(
    _ decoder: any Decoder,
    _: Keys.Type,
    label: String
) throws where Keys.AllCases: Sequence {
    let allowed = Set(Keys.allCases.map(\.stringValue))
    try requireExactKeys(decoder, allowed: allowed, label: label)
}

private func requireExactKeys(
    _ decoder: any Decoder,
    allowed: Set<String>,
    label: String
) throws {
    let container = try decoder.container(keyedBy: AnyCodingKey.self)
    let actual = Set(container.allKeys.map(\.stringValue))
    guard actual == allowed else {
        let missing = allowed.subtracting(actual).sorted()
        let unexpected = actual.subtracting(allowed).sorted()
        throw ViewerContractError.invalid(
            "\(label) keys do not match the contract; missing=\(missing), unexpected=\(unexpected)."
        )
    }
}

private func approximatelyEqual(_ lhs: Double, _ rhs: Double) -> Bool {
    abs(lhs - rhs) <= 1e-9
}
