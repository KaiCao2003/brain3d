import Foundation

public enum BridgeProtocolVersion {
    public static let current = 1
}

public enum JSONValue: Codable, Equatable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unsupported JSON value"
            )
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case let .string(value):
            try container.encode(value)
        case let .number(value):
            try container.encode(value)
        case let .bool(value):
            try container.encode(value)
        case let .object(value):
            try container.encode(value)
        case let .array(value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

public struct BridgeRequest<Parameters: Encodable & Sendable>: Encodable, Sendable {
    public let id: String
    public let method: String
    public let params: Parameters

    public init(id: String, method: String, params: Parameters) {
        self.id = id
        self.method = method
        self.params = params
    }
}

public struct BridgeRemoteError: Codable, Error, Equatable, Sendable {
    public let code: String
    public let message: String
    public let details: JSONValue?

    public init(code: String, message: String, details: JSONValue? = nil) {
        self.code = code
        self.message = message
        self.details = details
    }
}

public struct BridgeResponse<Result: Decodable & Sendable>: Decodable, Sendable {
    public let id: String
    public let result: Result?
    public let error: BridgeRemoteError?
}

public struct HelloParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let client: String

    public init(
        protocolVersion: Int = BridgeProtocolVersion.current,
        client: String = "Brain3DSwiftUI"
    ) {
        self.protocolVersion = protocolVersion
        self.client = client
    }
}

public struct StateParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int

    public init(protocolVersion: Int = BridgeProtocolVersion.current) {
        self.protocolVersion = protocolVersion
    }
}

public struct BridgeCapabilities: Codable, Equatable, Sendable {
    public let atlas25Micrometre: Bool
    public let atlasDownload: Bool
    public let atlasSlicePng: Bool
    public let animalOnly: Bool
    public let projectPersistence: Bool
    public let subjectVascularImport: Bool
    public let subjectVascularOverlay: Bool
    public let subjectVascularRegistration: Bool
    public let subjectAtlasCalibration: Bool?
    public let calibratedTargetProjection: Bool?
    public let probeCatalog: Bool?
    public let calibratedProbePlanning: Bool?
    public let exactProbeRegionTraversal: Bool?
    public let atlasMeshDescriptor: Bool?
    public let atlasAnnotationRayPick: Bool?
    public let atlasDorsalRegionPick: Bool?
    public let auditedReferenceMajorVessels: Bool?
    public let radiusAwareReferenceVesselAnalysis: Bool?

    public init(
        atlas25Micrometre: Bool,
        atlasDownload: Bool,
        atlasSlicePng: Bool,
        animalOnly: Bool,
        projectPersistence: Bool = false,
        subjectVascularImport: Bool = false,
        subjectVascularOverlay: Bool = false,
        subjectVascularRegistration: Bool = false,
        subjectAtlasCalibration: Bool? = nil,
        calibratedTargetProjection: Bool? = nil,
        probeCatalog: Bool? = nil,
        calibratedProbePlanning: Bool? = nil,
        exactProbeRegionTraversal: Bool? = nil,
        atlasMeshDescriptor: Bool? = nil,
        atlasAnnotationRayPick: Bool? = nil,
        atlasDorsalRegionPick: Bool? = nil,
        auditedReferenceMajorVessels: Bool? = nil,
        radiusAwareReferenceVesselAnalysis: Bool? = nil
    ) {
        self.atlas25Micrometre = atlas25Micrometre
        self.atlasDownload = atlasDownload
        self.atlasSlicePng = atlasSlicePng
        self.animalOnly = animalOnly
        self.projectPersistence = projectPersistence
        self.subjectVascularImport = subjectVascularImport
        self.subjectVascularOverlay = subjectVascularOverlay
        self.subjectVascularRegistration = subjectVascularRegistration
        self.subjectAtlasCalibration = subjectAtlasCalibration
        self.calibratedTargetProjection = calibratedTargetProjection
        self.probeCatalog = probeCatalog
        self.calibratedProbePlanning = calibratedProbePlanning
        self.exactProbeRegionTraversal = exactProbeRegionTraversal
        self.atlasMeshDescriptor = atlasMeshDescriptor
        self.atlasAnnotationRayPick = atlasAnnotationRayPick
        self.atlasDorsalRegionPick = atlasDorsalRegionPick
        self.auditedReferenceMajorVessels = auditedReferenceMajorVessels
        self.radiusAwareReferenceVesselAnalysis = radiusAwareReferenceVesselAnalysis
    }
}

public struct HelloResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let service: String
    public let applicationVersion: String
    public let capabilities: BridgeCapabilities

    public init(
        protocolVersion: Int,
        service: String,
        applicationVersion: String,
        capabilities: BridgeCapabilities
    ) {
        self.protocolVersion = protocolVersion
        self.service = service
        self.applicationVersion = applicationVersion
        self.capabilities = capabilities
    }
}

public struct AtlasBridgeState: Codable, Equatable, Sendable {
    public let identifier: String
    public let version: String
    public let loaded: Bool
    public let status: String

    public init(identifier: String, version: String, loaded: Bool, status: String) {
        self.identifier = identifier
        self.version = version
        self.loaded = loaded
        self.status = status
    }

    public var isSupportedAndLoaded: Bool {
        loaded
            && identifier == SafetyPolicy.supportedAtlasIdentifier
            && version == SafetyPolicy.supportedAtlasVersion
    }
}

public struct SubjectVesselsBridgeState: Codable, Equatable, Sendable {
    public let imported: Bool
    public let registered: Bool
    public let images: [SubjectVesselImageBridgeState]

    public init(
        imported: Bool,
        registered: Bool,
        images: [SubjectVesselImageBridgeState] = []
    ) {
        self.imported = imported
        self.registered = registered
        self.images = images
    }

    public var primaryImage: SubjectVesselImageBridgeState? { images.last }
}

public struct SubjectVesselImageBridgeState: Codable, Equatable, Sendable {
    public let imageId: String
    public let sourceName: String
    public let sourceSha256: String
    public let byteSize: Int
    public let widthPixels: Int
    public let heightPixels: Int
    public let registered: Bool
    public let residualMicrometres: Double?
    public let maximumResidualMicrometres: Double?
    public let lateralityConfirmed: Bool
    public let visible: Bool

    public init(
        imageId: String,
        sourceName: String,
        sourceSha256: String,
        byteSize: Int,
        widthPixels: Int,
        heightPixels: Int,
        registered: Bool,
        residualMicrometres: Double?,
        maximumResidualMicrometres: Double? = nil,
        lateralityConfirmed: Bool,
        visible: Bool = false
    ) {
        self.imageId = imageId
        self.sourceName = sourceName
        self.sourceSha256 = sourceSha256
        self.byteSize = byteSize
        self.widthPixels = widthPixels
        self.heightPixels = heightPixels
        self.registered = registered
        self.residualMicrometres = residualMicrometres
        self.maximumResidualMicrometres = maximumResidualMicrometres
        self.lateralityConfirmed = lateralityConfirmed
        self.visible = visible
    }
}

public struct PopulationDensityBridgeState: Codable, Equatable, Sendable {
    public let available: Bool
    public let visible: Bool
    public let opacity: Double
    public let status: String

    public init(available: Bool, visible: Bool, opacity: Double, status: String) {
        self.available = available
        self.visible = visible
        self.opacity = opacity
        self.status = status
    }
}

public struct PlannerBridgeState: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let animalOnly: Bool?
    public let warning: String?
    public let atlas: AtlasBridgeState
    public let project: ProjectBridgeState?
    public let subjectVessels: SubjectVesselsBridgeState
    public let populationDensity: PopulationDensityBridgeState

    public init(
        protocolVersion: Int,
        animalOnly: Bool? = nil,
        warning: String? = nil,
        atlas: AtlasBridgeState,
        project: ProjectBridgeState? = nil,
        subjectVessels: SubjectVesselsBridgeState,
        populationDensity: PopulationDensityBridgeState
    ) {
        self.protocolVersion = protocolVersion
        self.animalOnly = animalOnly
        self.warning = warning
        self.atlas = atlas
        self.project = project
        self.subjectVessels = subjectVessels
        self.populationDensity = populationDensity
    }
}

public struct ProjectBridgeState: Codable, Equatable, Sendable {
    public let projectId: String
    public let title: String
    public let subjectId: String?
    public let path: String?
    public let requiresSaveAs: Bool
    public let recoveredFromBackup: Bool
    public let schemaVersion: Int
    public let revision: Int
    public let isDirty: Bool
    public let animalResearchOnlyAcknowledged: Bool
    public let calibrationCount: Int?
    public let activeCalibrationId: String?
    public let probePlanCount: Int?
    public let probeRegionAnalysisCount: Int?
    public let rendererAnchor: AtlasPhysicalPoint?
}

public struct AtlasOpenParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let identifier: String
    public let version: String
    public let allowDownload: Bool

    public init(allowDownload: Bool) {
        protocolVersion = BridgeProtocolVersion.current
        identifier = SafetyPolicy.supportedAtlasIdentifier
        version = SafetyPolicy.supportedAtlasVersion
        self.allowDownload = allowDownload
    }
}

public struct AtlasProvenance: Codable, Equatable, Sendable {
    public let identifier: String
    public let version: String
    public let metadataSha256: String
    public let resolutionMicrometres: [Double]
    public let shapeVoxels: [Int]
    public let orientation: String
    public let frameworkName: String
    public let sourceAnnotation: String
    public let citation: String
    public let brainGlobeAtlasApiVersion: String
}

public struct AtlasOpenResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let atlas: AtlasProvenance
}

public struct AtlasSliceParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let orientation: String
    public let index: Int

    public init(orientation: String, index: Int) {
        protocolVersion = BridgeProtocolVersion.current
        self.orientation = orientation
        self.index = index
    }
}

public struct AtlasSliceResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let mimeType: String
    public let pngBase64: String
    public let width: Int
    public let height: Int
    public let orientation: String
    public let index: Int
    public let sliceCount: Int
    public let fixedAxis: String
    public let rowAxis: String
    public let columnAxis: String
    public let sliceCenterMicrometres: Double
    public let atlas: AtlasProvenance
}

public struct AtlasDorsalParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int

    public init() {
        protocolVersion = BridgeProtocolVersion.current
    }
}

public struct AtlasDorsalIdentity: Codable, Equatable, Sendable {
    public let identifier: String
    public let version: String
    public let resolutionMicrometres: [Double]
    public let orientation: String
}

public struct AtlasDorsalResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let mimeType: String
    public let pngBase64: String
    public let width: Int
    public let height: Int
    public let rowAxis: String
    public let columnAxis: String
    public let surfaceDvMinimumMicrometres: Double?
    public let surfaceDvMaximumMicrometres: Double?
    public let displayLabel: String
    public let surfaceDefinition: String
    public let atlas: AtlasDorsalIdentity
}

public struct ProjectNewParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let animalResearchOnlyAcknowledged: Bool
    public let title: String?
    public let subjectId: String?

    public init?(
        acknowledgement: AnimalOnlyAcknowledgementState,
        title: String? = nil,
        subjectId: String? = nil
    ) {
        guard acknowledgement.isExplicitlyAcknowledged else { return nil }
        protocolVersion = BridgeProtocolVersion.current
        animalResearchOnlyAcknowledged = acknowledgement.isExplicitlyAcknowledged
        self.title = title
        self.subjectId = subjectId
    }
}

public struct ProjectNewResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let title: String
    public let subjectId: String?
    public let animalOnly: Bool
    public let warning: String
}

public struct ProjectSaveParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let path: String?

    public init(path: String? = nil) {
        protocolVersion = BridgeProtocolVersion.current
        self.path = path
    }
}

public struct ProjectSaveResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let path: String
    public let projectId: String
}

public struct ProjectOpenParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let path: String

    public init(path: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.path = path
    }
}

public struct ProjectOpenResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let title: String
    public let sourcePath: String
    public let requiresSaveAs: Bool
    public let recoveredFromBackup: Bool
    public let subjectVascularImageCount: Int
}

public struct VascularImportParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let path: String
    public let pixelSizeXMicrometres: Double?
    public let pixelSizeYMicrometres: Double?

    public init(
        path: String,
        pixelSizeXMicrometres: Double? = nil,
        pixelSizeYMicrometres: Double? = nil
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.path = path
        self.pixelSizeXMicrometres = pixelSizeXMicrometres
        self.pixelSizeYMicrometres = pixelSizeYMicrometres
    }
}

public struct ImportedVascularImage: Codable, Equatable, Sendable {
    public let imageId: String
    public let sourceName: String
    public let sourceSha256: String
    public let byteSize: Int
    public let format: String
    public let widthPixels: Int
    public let heightPixels: Int
    public let frameCount: Int
    public let calibrated: Bool
    public let pixelSizeXMicrometres: Double?
    public let pixelSizeYMicrometres: Double?
    public let coordinateFrame: String
    public let subjectSpecific: Bool
}

public struct VascularImportResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let image: ImportedVascularImage
    public let warning: String
}

public struct VascularPreviewParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let imageId: String

    public init(imageId: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.imageId = imageId
    }
}

public struct VascularPreviewResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let imageId: String
    public let mimeType: String
    public let pngBase64: String
    public let originalWidthPixels: Int
    public let originalHeightPixels: Int
    public let previewWidthPixels: Int
    public let previewHeightPixels: Int
    public let previewToOriginalScaleX: Double
    public let previewToOriginalScaleY: Double
    public let coordinateFrame: String
}

public struct VascularOverlayParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let imageId: String
    public let opacity: Double?

    public init(imageId: String, opacity: Double? = nil) {
        protocolVersion = BridgeProtocolVersion.current
        self.imageId = imageId
        self.opacity = opacity
    }
}

public struct VascularOverlayResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let imageId: String
    public let registrationId: String
    public let mimeType: String
    public let pngBase64: String
    public let width: Int
    public let height: Int
    public let rowAxis: String
    public let columnAxis: String
    public let resolutionMicrometres: [Double]
    public let subjectSpecific: Bool
    public let displayLabel: String
    public let rmsResidualMicrometres: Double
    public let maximumResidualMicrometres: Double
    public let lateralityConfirmed: Bool
}

public struct VascularLandmarkParameters: Codable, Equatable, Sendable {
    public let label: String
    public let kind: String
    public let imageColumnPixels: Double
    public let imageRowPixels: Double
    public let atlasApMicrometres: Double
    public let atlasMlMicrometres: Double
    public let enabled: Bool

    public init(
        label: String,
        kind: String,
        imageColumnPixels: Double,
        imageRowPixels: Double,
        atlasApMicrometres: Double,
        atlasMlMicrometres: Double,
        enabled: Bool
    ) {
        self.label = label
        self.kind = kind
        self.imageColumnPixels = imageColumnPixels
        self.imageRowPixels = imageRowPixels
        self.atlasApMicrometres = atlasApMicrometres
        self.atlasMlMicrometres = atlasMlMicrometres
        self.enabled = enabled
    }
}

public struct VascularRegisterParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let imageId: String
    public let method: String
    public let landmarks: [VascularLandmarkParameters]
    public let lateralityConfirmed: Bool
    public let opacity: Double

    public init(
        imageId: String,
        method: String,
        landmarks: [VascularLandmarkParameters],
        lateralityConfirmed: Bool,
        opacity: Double = 0.65
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.imageId = imageId
        self.method = method
        self.landmarks = landmarks
        self.lateralityConfirmed = lateralityConfirmed
        self.opacity = opacity
    }
}

public struct VascularLandmarkResidual: Codable, Equatable, Sendable {
    public let landmarkId: String
    public let apErrorMicrometres: Double
    public let mlErrorMicrometres: Double
    public let radialErrorMicrometres: Double
}

public struct VascularRegisterResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let registrationId: String
    public let version: Int
    public let method: String
    public let matrixRowMajor: [Double]
    public let rmsResidualMicrometres: Double
    public let maximumResidualMicrometres: Double
    public let redundantControlPoints: Bool
    public let lateralityConfirmed: Bool
    public let visible: Bool
    public let warning: String
    public let residuals: [VascularLandmarkResidual]
}
