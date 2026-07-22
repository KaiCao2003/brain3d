import Foundation

public struct ReferenceDensityPrepareParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let archivePath: String?
    public let downloadIfMissing: Bool

    public init(archivePath: String? = nil, downloadIfMissing: Bool) {
        protocolVersion = BridgeProtocolVersion.current
        self.archivePath = archivePath
        self.downloadIfMissing = downloadIfMissing
    }
}

/// Pinned source identity shared by preparation and render responses.
///
/// Preparation responses include the optional download/member fields; render
/// responses intentionally repeat only the immutable DOI, version, and archive
/// digest. Unknown future fields are ignored by synthesized `Codable` decoding.
public struct ReferenceDensitySourceIdentity: Codable, Equatable, Sendable {
    public let doi: String
    public let version: Int
    public let archiveSha256: String
    public let landingPageUrl: String?
    public let downloadUrl: String?
    public let archiveFilename: String?
    public let archiveSizeBytes: Int?
    public let densityMemberPath: String?
    public let templateMemberPath: String?

    public init(
        doi: String,
        version: Int,
        archiveSha256: String,
        landingPageUrl: String? = nil,
        downloadUrl: String? = nil,
        archiveFilename: String? = nil,
        archiveSizeBytes: Int? = nil,
        densityMemberPath: String? = nil,
        templateMemberPath: String? = nil
    ) {
        self.doi = doi
        self.version = version
        self.archiveSha256 = archiveSha256
        self.landingPageUrl = landingPageUrl
        self.downloadUrl = downloadUrl
        self.archiveFilename = archiveFilename
        self.archiveSizeBytes = archiveSizeBytes
        self.densityMemberPath = densityMemberPath
        self.templateMemberPath = templateMemberPath
    }
}

public struct ReferenceDensityAtlasIdentity: Codable, Equatable, Sendable {
    public let identifier: String
    public let version: String
    public let metadataSha256: String
    public let resolutionMicrometres: [Double]?
    public let shapeVoxels: [Int]?
    public let orientation: String?

    public init(
        identifier: String,
        version: String,
        metadataSha256: String,
        resolutionMicrometres: [Double]? = nil,
        shapeVoxels: [Int]? = nil,
        orientation: String? = nil
    ) {
        self.identifier = identifier
        self.version = version
        self.metadataSha256 = metadataSha256
        self.resolutionMicrometres = resolutionMicrometres
        self.shapeVoxels = shapeVoxels
        self.orientation = orientation
    }
}

public struct ReferenceDensityPreparedField: Codable, Equatable, Sendable {
    public let valueUnits: String
    public let populationSubjectCount: Int
    public let rollingWindowMicrometres: Double
    public let outputShapeASR: [Int]
    public let outputResolutionMicrometres: Double
    public let templateCorrelation: Double
    public let minimumTemplateCorrelation: Double
    public let apAxisReversed: Bool
    public let mlSymmetrized: Bool
    public let subjectSpecific: Bool
    public let containsIndividualVesselPaths: Bool
    public let supportsVesselClearance: Bool
}

public struct ReferenceDensityPreparedCache: Codable, Equatable, Sendable {
    public let archiveSha256Verified: Bool
    public let preparedDensitySha256: String
    public let reusedPreparedCache: Bool
}

public struct ReferenceDensityPrepareResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let source: ReferenceDensitySourceIdentity
    public let atlas: ReferenceDensityAtlasIdentity
    public let density: ReferenceDensityPreparedField
    public let cache: ReferenceDensityPreparedCache
    public let disclosure: String
}

public struct ReferenceDensityOverlayParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int

    public init() {
        protocolVersion = BridgeProtocolVersion.current
    }
}

public struct ReferenceDensityDisplayState: Codable, Equatable, Sendable {
    public let visible: Bool
    public let opacity: Double

    public init(visible: Bool, opacity: Double) {
        self.visible = visible
        self.opacity = opacity
    }
}

public struct ReferenceDensityDisplayParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let visible: Bool
    public let opacity: Double

    public init(visible: Bool, opacity: Double) {
        protocolVersion = BridgeProtocolVersion.current
        self.visible = visible
        self.opacity = opacity
    }
}

public struct ReferenceDensityDisplayResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let display: ReferenceDensityDisplayState
}

public struct ReferenceDensityOverlayWindow: Codable, Equatable, Sendable {
    public let low: Double
    public let high: Double
    public let units: String
    public let opacity: Double
    public let colorMap: String
}

public struct ReferenceDensityOverlayResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let mimeType: String
    public let pngBase64: String
    public let width: Int
    public let height: Int
    public let rowAxis: String
    public let columnAxis: String
    public let projectionAxis: String
    public let projectionMethod: String
    public let atlasResolutionMicrometres: [Double]
    public let densityResolutionMicrometres: Double
    public let window: ReferenceDensityOverlayWindow
    public let display: ReferenceDensityDisplayState
    public let source: ReferenceDensitySourceIdentity
    public let atlas: ReferenceDensityAtlasIdentity
    public let subjectSpecific: Bool
    public let containsIndividualVesselPaths: Bool
    public let supportsVesselClearance: Bool
    public let displayLabel: String
    public let disclosure: String
}
