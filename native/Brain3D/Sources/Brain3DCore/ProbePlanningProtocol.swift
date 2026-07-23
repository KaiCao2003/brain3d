import CryptoKit
import Foundation

public enum ProbePlanningContract {
    public static let catalogVersion = "brain3d-probe-catalog-v5"
    public static let neuropixels2SingleShankModelId =
        "imec-neuropixels-2.0-single-shank-np2003-np2004"
    public static let neuropixels2StandardFourShankModelId =
        "imec-neuropixels-2.0-standard-four-shank-np2013-np2014"
    public static let neuropixels2QuadBaseFourShankModelId =
        "imec-neuropixels-2.0-quad-base-four-shank-np2020-np2021"
    public static let neuropixels2ModelVersion = "source-snapshot-2026-07-23"
    public static let neuropixels2SingleShankDisplayName =
        "Neuropixels 2.0 — single shank (NP2003 / NP2004)"
    public static let neuropixels2StandardFourShankDisplayName =
        "Neuropixels 2.0 — standard four shanks (NP2013 / NP2014)"
    public static let neuropixels2QuadBaseFourShankDisplayName =
        "Neuropixels 2.0 — Quad Base four shanks (NP2020 / NP2021)"
    public static let neuropixels2SingleShankProductCode = "NP2003 / NP2004"
    public static let neuropixels2StandardFourShankProductCode =
        "NP2013 / NP2014"
    public static let neuropixels2QuadBaseFourShankProductCode =
        "NP2020 / NP2021"
    public static let neuropixels2SingleShankSimultaneousChannelCount = 384
    public static let neuropixels2StandardFourShankSimultaneousChannelCount = 384
    public static let neuropixels2QuadBaseFourShankSimultaneousChannelCount = 1_536
    public static let neuropixels2SpecSHA256 =
        "bcd5a24e0f91c23c665f4fddfaad06ef6a8a1278a248ec3f5b4ebf17f1d0f6eb"
    public static let neuropixels2UserManualZipSHA256 =
        "99677abe3e052636894934170d7d70c12e327433e3749b38213f74ff7772d0a8"
    public static let neuropixels2ElectrodeMappingSHA256 =
        "85c1236e512be518f6706256c24a214fab7ff238e993149e242fd5ad69ba167f"
    public static let neuropixels2QuadBaseSpecSHA256 =
        "9a0b4566979acbad751c8f4fb72405f77e170e3963f16d1852709c83ce57c7a9"
    public static let neuropixelsModelId = "imec-neuropixels-1.0-np1000-prb-1-4-0480-1"
    public static let neuropixelsModelVersion = "source-snapshot-2026-07-22"
    public static let neuropixelsDisplayName = "Neuropixels 1.0 — NP1000 / PRB_1_4_0480_1"
    public static let sourceTranscribedReviewPendingStatus =
        "source-transcribed-review-pending"
    public static let sourceTranscribedReviewPendingWarning =
        "Source-transcribed manufacturer geometry — independent transcription review "
            + "pending; explicit acknowledgement required"
    public static let manufacturerSpecSHA256 =
        "73feccebeadf45c8e7062028588a5b36e9da9f25d10b5d943f33389c3e791f6f"
    public static let probeTableSHA256 =
        "6946867508341555960d0b8af2f8e88589f411fc5ff0e122371d377b71f6a3e4"
    public static let spikeGLXGeometrySHA256 =
        "59fa29406dc3f6ad38195157d6ddfecbf3b348e13bc3bfd827f50231adbde704"
    public static let spikeGLXMetadataSHA256 =
        "654706c021a6da502b10086390b22464567aad5a94ed0d77a4bc9a36c3b3637f"
    public static let genericModelId = "generic-linear-test-16"
    public static let genericModelVersion = "1.0"
    public static let genericDisplayName = "Generic test probe — one shank / 16 sites"
    public static let genericWarning =
        "Generic software-test geometry — not a verified Neuropixels device profile"
    public static let coordinateOrigin = "primary-shank-tip"
    public static let localAxisDefinition =
        "axial-from-tip-toward-base, lateral-right, normal-by-right-hand-rule"
    public static let insertionAxisDefinition = "entry-toward-tip"
    public static let atlasFrameId = "BRAINGLOBE_PHYSICAL_ASR_UM"
    public static let regionFrameId = "BRAINGLOBE_PHYSICAL_ASR_AP_ML_DV_UM"
    public static let bregmaEntryFrameId = "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"
    public static let planningAlgorithmVersion =
        "calibrated-explicit-placement-mode-v3"
    public static let stereotaxicPlanningAlgorithmVersion =
        "calibrated-stereotaxic-probe-transform-v2"
    public static let legacyPlanningAlgorithmVersion = "calibrated-target-angle-depth-v1"
    public static let planningPlacementMethod =
        "stereotaxic-target-plus-manipulator-angles"
    public static let legacyPlacementMethod = "target-plus-angles-depth"
    public static let regionAlgorithmVersion = "probe-region-analysis-bundle-v1"
    public static let angleConvention =
        "azimuth about +DV from +AP toward +ML; elevation from AP-ML plane toward +DV"

    public static func requiresExplicitAcknowledgement(
        verificationStatus: String
    ) -> Bool {
        verificationStatus != "verified"
    }

    public static func preferredCatalogModel(
        in models: [ProbeCatalogModel],
        preservingIdentity selectedIdentity: String?
    ) -> ProbeCatalogModel? {
        if let selectedIdentity,
           let selected = models.first(where: { $0.id == selectedIdentity })
        {
            return selected
        }
        return models.first {
            $0.modelId == neuropixels2SingleShankModelId
                && $0.modelVersion == neuropixels2ModelVersion
        }
    }
}

public enum ProbePlanningValidationError: Error, Equatable, LocalizedError, Sendable {
    case invalid(String)

    public var errorDescription: String? {
        switch self {
        case let .invalid(message): message
        }
    }
}

public enum ProbePlacementMode: String, Codable, CaseIterable, Equatable, Sendable {
    case entryAndTarget = "ENTRY_AND_TARGET"
    case entryAnglesDepth = "ENTRY_ANGLES_DEPTH"
    case targetAnglesDepth = "TARGET_ANGLES_DEPTH"
    case stereotaxicTargetManipulator = "STEREOTAXIC_TARGET_MANIPULATOR"

    public var displayName: String {
        switch self {
        case .entryAndTarget: "Entry + target"
        case .entryAnglesDepth: "Entry + angles + depth"
        case .targetAnglesDepth: "Target + angles + depth"
        case .stereotaxicTargetManipulator: "Stereotaxic target"
        }
    }

    public var requiresEntryCoordinates: Bool {
        self == .entryAndTarget || self == .entryAnglesDepth
    }

    public var requiresAnglesAndDepth: Bool {
        self != .entryAndTarget
    }

    public var normalizedPlacementMethod: String {
        switch self {
        case .entryAndTarget: "entry-plus-target"
        case .entryAnglesDepth: "entry-plus-angles-depth"
        case .targetAnglesDepth: "target-plus-angles-depth"
        case .stereotaxicTargetManipulator:
            ProbePlanningContract.planningPlacementMethod
        }
    }
}

public struct ProbeCatalogListParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int

    public init() { protocolVersion = BridgeProtocolVersion.current }
}

public struct ProbeCatalogGetParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let modelId: String
    public let modelVersion: String

    public init(modelId: String, modelVersion: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.modelId = modelId
        self.modelVersion = modelVersion
    }
}

public struct ProbePlanListParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String

    public init(projectId: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
    }
}

public struct ProbePlanGetParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let planId: String

    public init(projectId: String, planId: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.planId = planId
    }
}

public struct ProbePlanCreateParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let targetId: String
    public let modelId: String
    public let modelVersion: String
    public let name: String
    public let placementMode: ProbePlacementMode
    public let entryAPMillimetres: Double?
    public let entryMLMillimetres: Double?
    public let entryDVMillimetres: Double?
    public let azimuthDegrees: Double?
    public let elevationDegrees: Double?
    public let insertionDepthMicrometres: Double?
    public let axialRotationDegrees: Double
    public let customGeometryAcknowledged: Bool

    public init(
        projectId: String,
        expectedProjectRevision: Int,
        targetId: String,
        modelId: String,
        modelVersion: String,
        name: String,
        placementMode: ProbePlacementMode = .stereotaxicTargetManipulator,
        entryAPMillimetres: Double? = nil,
        entryMLMillimetres: Double? = nil,
        entryDVMillimetres: Double? = nil,
        azimuthDegrees: Double? = nil,
        elevationDegrees: Double? = nil,
        insertionDepthMicrometres: Double? = nil,
        axialRotationDegrees: Double,
        customGeometryAcknowledged: Bool
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.expectedProjectRevision = expectedProjectRevision
        self.targetId = targetId
        self.modelId = modelId
        self.modelVersion = modelVersion
        self.name = name
        self.placementMode = placementMode
        self.entryAPMillimetres = entryAPMillimetres
        self.entryMLMillimetres = entryMLMillimetres
        self.entryDVMillimetres = entryDVMillimetres
        self.azimuthDegrees = azimuthDegrees
        self.elevationDegrees = elevationDegrees
        self.insertionDepthMicrometres = insertionDepthMicrometres
        self.axialRotationDegrees = axialRotationDegrees
        self.customGeometryAcknowledged = customGeometryAcknowledged
    }
}

public struct ProbePlanUpdateParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let planId: String
    public let expectedPlanInputSha256: String
    public let targetId: String
    public let modelId: String
    public let modelVersion: String
    public let name: String
    public let placementMode: ProbePlacementMode
    public let entryAPMillimetres: Double?
    public let entryMLMillimetres: Double?
    public let entryDVMillimetres: Double?
    public let azimuthDegrees: Double?
    public let elevationDegrees: Double?
    public let insertionDepthMicrometres: Double?
    public let axialRotationDegrees: Double
    public let customGeometryAcknowledged: Bool

    public init(
        projectId: String,
        expectedProjectRevision: Int,
        planId: String,
        expectedPlanInputSha256: String,
        targetId: String,
        modelId: String,
        modelVersion: String,
        name: String,
        placementMode: ProbePlacementMode = .stereotaxicTargetManipulator,
        entryAPMillimetres: Double? = nil,
        entryMLMillimetres: Double? = nil,
        entryDVMillimetres: Double? = nil,
        azimuthDegrees: Double? = nil,
        elevationDegrees: Double? = nil,
        insertionDepthMicrometres: Double? = nil,
        axialRotationDegrees: Double,
        customGeometryAcknowledged: Bool
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.expectedProjectRevision = expectedProjectRevision
        self.planId = planId
        self.expectedPlanInputSha256 = expectedPlanInputSha256
        self.targetId = targetId
        self.modelId = modelId
        self.modelVersion = modelVersion
        self.name = name
        self.placementMode = placementMode
        self.entryAPMillimetres = entryAPMillimetres
        self.entryMLMillimetres = entryMLMillimetres
        self.entryDVMillimetres = entryDVMillimetres
        self.azimuthDegrees = azimuthDegrees
        self.elevationDegrees = elevationDegrees
        self.insertionDepthMicrometres = insertionDepthMicrometres
        self.axialRotationDegrees = axialRotationDegrees
        self.customGeometryAcknowledged = customGeometryAcknowledged
    }
}

public struct ProbePlanRemoveParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let planId: String
    public let expectedPlanInputSha256: String

    public init(
        projectId: String,
        expectedProjectRevision: Int,
        planId: String,
        expectedPlanInputSha256: String
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.expectedProjectRevision = expectedProjectRevision
        self.planId = planId
        self.expectedPlanInputSha256 = expectedPlanInputSha256
    }
}

public struct ProbeRegionGetParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let planId: String

    public init(projectId: String, planId: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.planId = planId
    }
}

public struct ProbeRegionAnalyzeParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let planId: String
    public let expectedPlanInputSha256: String

    public init(
        projectId: String,
        expectedProjectRevision: Int,
        planId: String,
        expectedPlanInputSha256: String
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.expectedProjectRevision = expectedProjectRevision
        self.planId = planId
        self.expectedPlanInputSha256 = expectedPlanInputSha256
    }
}

public enum ProbeRegionExportFormat: String, Codable, CaseIterable, Equatable, Sendable {
    case csv
    case json
}

public struct ProbeRegionExportParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let planId: String
    public let expectedPlanInputSha256: String
    public let format: ProbeRegionExportFormat

    public init(
        projectId: String,
        expectedProjectRevision: Int,
        planId: String,
        expectedPlanInputSha256: String,
        format: ProbeRegionExportFormat
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.expectedProjectRevision = expectedProjectRevision
        self.planId = planId
        self.expectedPlanInputSha256 = expectedPlanInputSha256
        self.format = format
    }
}

public struct ProbeRegionExportConfirmParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let planId: String
    public let expectedPlanInputSha256: String
    public let analysisSha256: String
    public let format: ProbeRegionExportFormat
    public let contentSha256: String

    public init(
        projectId: String,
        expectedProjectRevision: Int,
        planId: String,
        expectedPlanInputSha256: String,
        analysisSha256: String,
        format: ProbeRegionExportFormat,
        contentSha256: String
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.expectedProjectRevision = expectedProjectRevision
        self.planId = planId
        self.expectedPlanInputSha256 = expectedPlanInputSha256
        self.analysisSha256 = analysisSha256
        self.format = format
        self.contentSha256 = contentSha256
    }
}

public struct ProbeCatalogSourceArtifact: Codable, Equatable, Sendable {
    public let title: String
    public let sourceUrl: String
    public let documentRevision: String
    public let retrievedOn: String
    public let sha256: String
    public let citation: String
}

public struct ProbeCatalogSite: Codable, Equatable, Identifiable, Sendable {
    public let siteId: String
    public let role: String
    public let bank: String?
    public let axialFromTipMicrometres: Double
    public let lateralMicrometres: Double
    public let normalMicrometres: Double

    public var id: String { siteId }
}

public struct ProbeCatalogShank: Codable, Equatable, Identifiable, Sendable {
    public let shankId: String
    public let lengthMicrometres: Double
    public let widthMicrometres: Double
    public let thicknessMicrometres: Double
    public let tipGeometry: String
    public let tipLengthMicrometres: Double
    public let tipGeometryNotes: String
    public let centerLateralMicrometres: Double
    public let centerNormalMicrometres: Double
    public let siteCount: Int
    public let sites: [ProbeCatalogSite]

    public var id: String { shankId }
}

public struct ProbeCatalogModel: Codable, Equatable, Identifiable, Sendable {
    public let modelId: String
    public let modelVersion: String
    public let displayName: String
    public let manufacturer: String?
    public let productCode: String?
    public let hardwareRevision: String?
    public let verificationStatus: String
    public let verifiedDeviceLabelPermitted: Bool
    public let shankCount: Int
    public let siteCount: Int
    public let units: String
    public let warning: String?
    public let geometryNotes: String?
    public let reviewNotes: String?
    public let completeGeometryTranscribed: Bool?
    public let independentTranscriptionReviewCompleted: Bool?
    public let transcribedBy: String?
    public let independentlyReviewedBy: String?
    public let coordinateOrigin: String?
    public let localAxisDefinition: String?
    public let insertionAxisDefinition: String?
    public let primarySources: [ProbeCatalogSourceArtifact]?
    public let shanks: [ProbeCatalogShank]?

    public var id: String { "\(modelId)@\(modelVersion)" }

    public var requiresExplicitAcknowledgement: Bool {
        ProbePlanningContract.requiresExplicitAcknowledgement(
            verificationStatus: verificationStatus
        )
    }
}

public struct ProbeCatalogListResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let catalogVersion: String
    public let modelCount: Int
    public let models: [ProbeCatalogModel]
}

public struct ProbeCatalogGetResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let catalogVersion: String
    public let model: ProbeCatalogModel
}

public struct ProbeVoxelIndex: Codable, Equatable, Sendable {
    public let ap: Int
    public let dv: Int
    public let ml: Int

    public init(ap: Int, dv: Int, ml: Int) {
        self.ap = ap
        self.dv = dv
        self.ml = ml
    }
}

public struct ProbePhysicalPoint: Codable, Equatable, Sendable {
    public let apMicrometres: Double
    public let dvMicrometres: Double
    public let mlMicrometres: Double
    public let insideAtlas: Bool
    public let voxelIndex: ProbeVoxelIndex?

    public init(
        apMicrometres: Double,
        dvMicrometres: Double,
        mlMicrometres: Double,
        insideAtlas: Bool = true,
        voxelIndex: ProbeVoxelIndex? = nil
    ) {
        self.apMicrometres = apMicrometres
        self.dvMicrometres = dvMicrometres
        self.mlMicrometres = mlMicrometres
        self.insideAtlas = insideAtlas
        self.voxelIndex = voxelIndex
    }

    public subscript(axis: AtlasAnatomicalAxis) -> Double {
        switch axis {
        case .ap: apMicrometres
        case .dv: dvMicrometres
        case .ml: mlMicrometres
        }
    }
}

public struct ProbeSourceTarget: Codable, Equatable, Sendable {
    public let frameId: String
    public let origin: String
    public let componentOrder: [String]
    public let units: String
    public let apMillimetres: Double
    public let mlMillimetres: Double
    public let dvMillimetres: Double
}

public struct ProbeCanonicalPoint: Codable, Equatable, Sendable {
    public let apMicrometres: Double
    public let mlMicrometres: Double
    public let dvMicrometres: Double
}

public struct ProbeCanonicalFrame: Codable, Equatable, Sendable {
    public let frameId: String
    public let componentOrder: [String]
    public let units: String
    public let apPositiveDirection: String
    public let mlPositiveDirection: String
    public let dvPositiveDirection: String
    public let entry: ProbeCanonicalPoint
    public let target: ProbeCanonicalPoint
    public let tip: ProbeCanonicalPoint
}

public struct ProbeAtlasFrame: Codable, Equatable, Sendable {
    public let frameId: String
    public let componentOrder: [String]
    public let units: String
    public let origin: String
    public let entry: ProbePhysicalPoint
    public let target: ProbePhysicalPoint
    public let tip: ProbePhysicalPoint
}

public struct ProbeUnitDirection: Codable, Equatable, Sendable {
    public let frameId: String
    public let componentOrder: [String]
    public let units: String
    public let ap: Double
    public let ml: Double
    public let dv: Double
}

public struct ProbePlacement: Codable, Equatable, Sendable {
    public let placementId: String
    public let method: String
    public let azimuthDegrees: Double
    public let elevationDegrees: Double
    public let insertionDepthMicrometres: Double
    public let axialRotationDegrees: Double
    public let angleConvention: String
    public let inwardDirection: ProbeUnitDirection
    public let localLateralDirection: ProbeUnitDirection
    public let localNormalDirection: ProbeUnitDirection
    public let modelToPlacementUniformScale: Double
    public let canonicalFrame: ProbeCanonicalFrame
    public let atlasFrame: ProbeAtlasFrame
}

public struct ProbeManipulatorInput: Codable, Equatable, Sendable {
    public let frameId: String
    public let azimuthDegrees: Double
    public let elevationDegrees: Double
    public let insertionDepthMicrometres: Double
    public let axialRotationDegrees: Double
    public let angleConvention: String
}

public struct ProbeBregmaRelativeEntryInput: Codable, Equatable, Sendable {
    public let frameId: String
    public let origin: String
    public let componentOrder: [String]
    public let units: String
    public let apPositiveDirection: String
    public let apNegativeDirection: String
    public let mlPositiveDirection: String
    public let mlNegativeDirection: String
    public let dvPositiveDirection: String
    public let dvNegativeDirection: String
    public let apMillimetres: Double
    public let mlMillimetres: Double
    public let dvMillimetres: Double
}

public struct ProbePlacementInput: Codable, Equatable, Sendable {
    public let mode: ProbePlacementMode
    public let entry: ProbeBregmaRelativeEntryInput?
    public let angleFrameId: String?
    public let azimuthDegrees: Double?
    public let elevationDegrees: Double?
    public let insertionDepthMicrometres: Double?
    public let axialRotationDegrees: Double
    public let angleConvention: String?
}

public struct ProbeManipulatorDraft: Equatable, Sendable {
    public let azimuthDegrees: Double
    public let elevationDegrees: Double
    public let insertionDepthMicrometres: Double
    public let axialRotationDegrees: Double
}

public struct ProbePlacementDraft: Equatable, Sendable {
    public let mode: ProbePlacementMode
    public let entryAPMillimetres: Double?
    public let entryMLMillimetres: Double?
    public let entryDVMillimetres: Double?
    public let azimuthDegrees: Double?
    public let elevationDegrees: Double?
    public let insertionDepthMicrometres: Double?
    public let axialRotationDegrees: Double
}

public struct ProbePlacedShank: Codable, Equatable, Identifiable, Sendable {
    public let shankId: String
    public let entry: ProbePhysicalPoint
    public let tip: ProbePhysicalPoint
    public let widthMicrometres: Double
    public let thicknessMicrometres: Double
    public let conservativeEnvelopeRadiusMicrometres: Double
    public let envelopeDefinition: String

    public init(
        shankId: String,
        entry: ProbePhysicalPoint,
        tip: ProbePhysicalPoint,
        widthMicrometres: Double,
        thicknessMicrometres: Double,
        conservativeEnvelopeRadiusMicrometres: Double,
        envelopeDefinition: String
    ) {
        self.shankId = shankId
        self.entry = entry
        self.tip = tip
        self.widthMicrometres = widthMicrometres
        self.thicknessMicrometres = thicknessMicrometres
        self.conservativeEnvelopeRadiusMicrometres = conservativeEnvelopeRadiusMicrometres
        self.envelopeDefinition = envelopeDefinition
    }

    public var id: String { shankId }
}

public struct ProbeRecordingSite: Codable, Equatable, Identifiable, Sendable {
    public let shankId: String
    public let siteId: String
    public let role: String
    public let bank: String?
    public let point: ProbePhysicalPoint

    public init(
        shankId: String,
        siteId: String,
        role: String,
        bank: String? = nil,
        point: ProbePhysicalPoint
    ) {
        self.shankId = shankId
        self.siteId = siteId
        self.role = role
        self.bank = bank
        self.point = point
    }

    public var id: String { "\(shankId):\(siteId)" }
}

public struct ProbePlanProvenance: Codable, Equatable, Sendable {
    public let calibrationId: String
    public let calibrationVersion: Int
    public let calibrationSha256: String
    public let atlasMetadataSha256: String
    public let projectionSha256: String
    public let planningAlgorithmVersion: String
    public let planInputSha256: String
    public let catalogVersion: String
}

public struct ProbePlanSummary: Codable, Equatable, Identifiable, Sendable {
    public let planId: String
    public let planVersion: Int
    public let name: String
    public let targetId: String
    public let targetLabel: String
    public let modelId: String
    public let modelVersion: String
    public let modelDisplayName: String
    public let verificationStatus: String
    public let inputSha256: String
    public let calibrationId: String
    public let calibrationVersion: Int
    public let regionAnalysisAvailable: Bool
    public let regionAnalysisSha256: String?
    public let usableForNavigation: Bool

    public var id: String { planId }
}

public struct ProbePlanDetail: Codable, Equatable, Identifiable, Sendable {
    public let planId: String
    public let planVersion: Int
    public let name: String
    public let targetId: String
    public let targetLabel: String
    public let modelId: String
    public let modelVersion: String
    public let modelDisplayName: String
    public let verificationStatus: String
    public let inputSha256: String
    public let calibrationId: String
    public let calibrationVersion: Int
    public let regionAnalysisAvailable: Bool
    public let regionAnalysisSha256: String?
    public let usableForNavigation: Bool
    public let sourceTarget: ProbeSourceTarget
    public let manipulatorInput: ProbeManipulatorInput?
    public let placementInput: ProbePlacementInput?
    public let placement: ProbePlacement
    public let shanks: [ProbePlacedShank]
    public let recordingSites: [ProbeRecordingSite]
    public let provenance: ProbePlanProvenance
    public let warning: String

    public var id: String { planId }

    public var hasCurrentPlanningGeometry: Bool {
        provenance.planningAlgorithmVersion == ProbePlanningContract.planningAlgorithmVersion
            || provenance.planningAlgorithmVersion
                == ProbePlanningContract.stereotaxicPlanningAlgorithmVersion
    }

    public var requiresPlanningGeometryUpdate: Bool {
        provenance.planningAlgorithmVersion
            == ProbePlanningContract.legacyPlanningAlgorithmVersion
    }

    public var manipulatorDraft: ProbeManipulatorDraft {
        if let manipulatorInput {
            return ProbeManipulatorDraft(
                azimuthDegrees: manipulatorInput.azimuthDegrees,
                elevationDegrees: manipulatorInput.elevationDegrees,
                insertionDepthMicrometres: manipulatorInput.insertionDepthMicrometres,
                axialRotationDegrees: manipulatorInput.axialRotationDegrees
            )
        }
        // Legacy v1 serialized these exact operator inputs on the placement.
        // They are exposed only to let the user review and explicitly update;
        // the legacy projected geometry itself remains unusable.
        return ProbeManipulatorDraft(
            azimuthDegrees: placement.azimuthDegrees,
            elevationDegrees: placement.elevationDegrees,
            insertionDepthMicrometres: placement.insertionDepthMicrometres,
            axialRotationDegrees: placement.axialRotationDegrees
        )
    }

    public var placementDraft: ProbePlacementDraft {
        if let placementInput {
            return ProbePlacementDraft(
                mode: placementInput.mode,
                entryAPMillimetres: placementInput.entry?.apMillimetres,
                entryMLMillimetres: placementInput.entry?.mlMillimetres,
                entryDVMillimetres: placementInput.entry?.dvMillimetres,
                azimuthDegrees: placementInput.azimuthDegrees,
                elevationDegrees: placementInput.elevationDegrees,
                insertionDepthMicrometres: placementInput.insertionDepthMicrometres,
                axialRotationDegrees: placementInput.axialRotationDegrees
            )
        }
        let fallback = manipulatorDraft
        return ProbePlacementDraft(
            mode: .stereotaxicTargetManipulator,
            entryAPMillimetres: nil,
            entryMLMillimetres: nil,
            entryDVMillimetres: nil,
            azimuthDegrees: fallback.azimuthDegrees,
            elevationDegrees: fallback.elevationDegrees,
            insertionDepthMicrometres: fallback.insertionDepthMicrometres,
            axialRotationDegrees: fallback.axialRotationDegrees
        )
    }
}

public struct ProbePlanListResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let planCount: Int
    public let plans: [ProbePlanSummary]
}

public struct ProbePlanGetResult: Decodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let plan: ProbePlanDetail
    public let regionAnalysis: ProbeRegionAnalysisBundle?
    public let majorVesselAnalysis: MajorVesselAnalysisResult?

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case protocolVersion
        case status
        case projectId
        case projectRevision
        case plan
        case regionAnalysis
        case majorVesselAnalysis
    }

    public init(from decoder: any Decoder) throws {
        let dynamic = try decoder.container(keyedBy: ProbePlanGetDynamicCodingKey.self)
        let actual = Set(dynamic.allKeys.map(\.stringValue))
        let expected = Set(CodingKeys.allCases.map(\.stringValue))
        guard actual == expected else {
            throw ProbePlanningValidationError.invalid(
                "Probe-plan detail keys do not match protocol v1 exactly."
            )
        }
        let container = try decoder.container(keyedBy: CodingKeys.self)
        protocolVersion = try container.decode(Int.self, forKey: .protocolVersion)
        status = try container.decode(String.self, forKey: .status)
        projectId = try container.decode(String.self, forKey: .projectId)
        projectRevision = try container.decode(Int.self, forKey: .projectRevision)
        plan = try container.decode(ProbePlanDetail.self, forKey: .plan)
        regionAnalysis = try container.decodeIfPresent(
            ProbeRegionAnalysisBundle.self,
            forKey: .regionAnalysis
        )
        majorVesselAnalysis = try container.decodeIfPresent(
            MajorVesselAnalysisResult.self,
            forKey: .majorVesselAnalysis
        )
    }
}

private struct ProbePlanGetDynamicCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int? = nil

    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}

public struct ProbePlanMutationResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let plan: ProbePlanDetail
    public let priorAnalysisCleared: Bool?
}

public struct ProbePlanRemoveResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let planId: String
    public let regionAnalysisRemoved: Bool
}

public struct ProbeRegionPoint: Codable, Equatable, Sendable {
    public let frameId: String
    public let componentOrder: [String]
    public let units: String
    public let apMicrometres: Double
    public let mlMicrometres: Double
    public let dvMicrometres: Double
}

public struct ProbeRegionSegment: Codable, Equatable, Identifiable, Sendable {
    public let structureId: Int
    public let acronym: String
    public let name: String
    public let hemisphere: String
    public let location: String
    public let entryDepthMicrometres: Double
    public let exitDepthMicrometres: Double
    public let lengthMicrometres: Double
    public let entryPoint: ProbeRegionPoint
    public let exitPoint: ProbeRegionPoint
    public let voxelCount: Int
    public let rgb: [Int]

    public var id: String {
        "\(structureId):\(entryDepthMicrometres):\(exitDepthMicrometres)"
    }
}

public struct ProbeRegionSiteAssignment: Codable, Equatable, Identifiable, Sendable {
    public let siteId: String
    public let structureId: Int
    public let acronym: String
    public let name: String
    public let location: String
    public let insideAtlas: Bool
    public let insideBrain: Bool
    public let point: ProbeRegionPoint
    public let voxelIndex: ProbeVoxelIndex?

    public var id: String { siteId }
}

public struct ProbeRegionProvenance: Codable, Equatable, Sendable {
    public let atlasIdentifier: String
    public let atlasVersion: String
    public let atlasMetadataSha256: String
    public let annotationSha256: String
    public let annotationVersion: String
    public let algorithmVersion: String
    public let inputDigest: String
    public let tieBreakRule: String
}

public struct ProbeShankRegionAnalysis: Codable, Equatable, Identifiable, Sendable {
    public let analysisId: String
    public let shankId: String
    public let totalPathLengthMicrometres: Double
    public let clippedPathLengthMicrometres: Double
    public let outsideAtlasPathLengthMicrometres: Double
    public let intersectsAtlas: Bool
    public let segments: [ProbeRegionSegment]
    public let recordingSiteAssignments: [ProbeRegionSiteAssignment]
    public let provenance: ProbeRegionProvenance

    public var id: String { shankId }
}

public struct ProbeRegionAnalysisBundle: Codable, Equatable, Identifiable, Sendable {
    public let analysisId: String
    public let planId: String
    public let planVersion: Int
    public let planInputSha256: String
    public let algorithmVersion: String
    public let analysisSha256: String
    public let computedAt: String
    public let usableForNavigation: Bool
    public let shanks: [ProbeShankRegionAnalysis]

    public var id: String { analysisId }
}

public struct ProbeRegionResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let regionAnalysis: ProbeRegionAnalysisBundle
}

public struct ProbeRegionExportResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let planId: String
    public let planInputSha256: String
    public let analysisSha256: String
    public let format: ProbeRegionExportFormat
    public let mimeType: String
    public let suggestedFileName: String
    public let content: String
    public let contentSha256: String
    public let projectMutated: Bool
}

public struct ProbeRegionExportConfirmationResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let planId: String
    public let planInputSha256: String
    public let analysisSha256: String
    public let format: ProbeRegionExportFormat
    public let contentSha256: String
    public let projectMutated: Bool
}

public enum ProbePlanningValidator {
    private struct PlanSiteIdentity: Hashable {
        let shankId: String
        let siteId: String
        let role: String
        let bank: String?
    }

    private struct Vector3 {
        let ap: Double
        let ml: Double
        let dv: Double

        var magnitude: Double {
            sqrt(ap * ap + ml * ml + dv * dv)
        }

        func adding(_ other: Vector3) -> Vector3 {
            Vector3(ap: ap + other.ap, ml: ml + other.ml, dv: dv + other.dv)
        }

        func subtracting(_ other: Vector3) -> Vector3 {
            Vector3(ap: ap - other.ap, ml: ml - other.ml, dv: dv - other.dv)
        }

        func scaled(by factor: Double) -> Vector3 {
            Vector3(ap: ap * factor, ml: ml * factor, dv: dv * factor)
        }

        func dot(_ other: Vector3) -> Double {
            ap * other.ap + ml * other.ml + dv * other.dv
        }

        func cross(_ other: Vector3) -> Vector3 {
            Vector3(
                ap: ml * other.dv - dv * other.ml,
                ml: dv * other.ap - ap * other.dv,
                dv: ap * other.ml - ml * other.ap
            )
        }
    }

    private static let directionTolerance = 1e-9
    private static let coordinateToleranceMicrometres = 1e-6

    private static let acceptedVerificationStatuses: Set<String> = [
        "verified",
        ProbePlanningContract.sourceTranscribedReviewPendingStatus,
        "user-defined-unverified",
    ]

    private static let neuropixelsSourceIdentities: [(url: String, sha256: String)] = [
        (
            "https://www.neuropixels.org/_files/ugd/"
                + "328966_c5e4d31e8a974962b5eb8ec975408c9f.pdf",
            ProbePlanningContract.manufacturerSpecSHA256
        ),
        (
            "https://raw.githubusercontent.com/billkarsh/ProbeTable/"
                + "207f7bf424b0fa26f271700b970e27a58a9a1111/Tables/probe_features.json",
            ProbePlanningContract.probeTableSHA256
        ),
        (
            "https://raw.githubusercontent.com/billkarsh/SpikeGLX/"
                + "d67bee45fa2635873456eb5d3f5e5a051690e64f/Src-imro/IMROTbl.cpp",
            ProbePlanningContract.spikeGLXGeometrySHA256
        ),
        (
            "https://raw.githubusercontent.com/billkarsh/SpikeGLX/"
                + "d67bee45fa2635873456eb5d3f5e5a051690e64f/Markdown/Metadata_Help.md",
            ProbePlanningContract.spikeGLXMetadataSHA256
        ),
    ]

    private static let neuropixels2TipGeometryNotes =
        "The official imec specifications report a 175 micrometre physical "
            + "chisel tip at approximately 20 degrees. ProbeTable and SpikeGLX "
            + "separately report 206 micrometres from the physical tip to the center "
            + "of the lowest electrode row."

    private static let neuropixels2CommonSources: [ProbeCatalogSourceArtifact] = [
        ProbeCatalogSourceArtifact(
            title: "Neuropixels 2.0 small-animal probe data sheet",
            sourceUrl: "https://www.neuropixels.org/_files/ugd/"
                + "328966_2b39661f072d405b8d284c3c73588bc6.pdf",
            documentRevision: "No printed revision identifier; PDF metadata modification "
                + "date 2024-09-18",
            retrievedOn: "2026-07-23",
            sha256: ProbePlanningContract.neuropixels2SpecSHA256,
            citation: "imec, Neuropixels 2.0 data sheet, pp. 1-3: one or four 10 mm by "
                + "70 micrometre by 24 micrometre shanks; 1280 sites per shank; "
                + "15 micrometre axial and 32 micrometre lateral pitches; 175 "
                + "micrometre chisel tip; and NP2003/NP2004/NP2013/NP2014 order codes."
        ),
        ProbeCatalogSourceArtifact(
            title: "Neuropixels 2.0 User Manual V1.0.6 archive",
            sourceUrl: "https://www.neuropixels.org/_files/archives/"
                + "328966_021470f37e3a4a4a88a256ab11639765.zip"
                + "?dn=Neuropixels_2-0_User_Manual_V1-0-6.zip",
            documentRevision: "Neuropixels 2.0 User Manual V1.0.6",
            retrievedOn: "2026-07-23",
            sha256: ProbePlanningContract.neuropixels2UserManualZipSHA256,
            citation: "imec, Neuropixels 2.0 User Manual V1.0.6, pp. 14 and 41-43: "
                + "physical dimensions, two-column site layout, 1280 electrode "
                + "identities per shank, virtual banks, and left-to-right shank "
                + "numbering at 250 micrometre pitch."
        ),
        ProbeCatalogSourceArtifact(
            title: "Neuropixels 2.0 Electrode-Channel Mapping workbook",
            sourceUrl: "https://www.neuropixels.org/_files/ugd/"
                + "328966_43eea6555fa94a5bb1ddb51f00696fc3.xlsx"
                + "?dn=Neuropix_2_0_Electrode-Channel-mapping.xlsx",
            documentRevision: "Official workbook retrieved 2026-07-23; sheets for "
                + "single shank and multi-shank shanks 0-3",
            retrievedOn: "2026-07-23",
            sha256: ProbePlanningContract.neuropixels2ElectrodeMappingSHA256,
            citation: "imec, Neuropixels 2.0 Electrode-Channel Mapping: electrode "
                + "identities 0-1279 and bank/channel connectivity for the single- "
                + "and four-shank products."
        ),
        ProbeCatalogSourceArtifact(
            title: "ProbeTable 1.8 probe_features.json",
            sourceUrl: "https://raw.githubusercontent.com/billkarsh/ProbeTable/"
                + "207f7bf424b0fa26f271700b970e27a58a9a1111/Tables/probe_features.json",
            documentRevision: "table_version 1.8; git commit "
                + "207f7bf424b0fa26f271700b970e27a58a9a1111",
            retrievedOn: "2026-07-23",
            sha256: ProbePlanningContract.probeTableSHA256,
            citation: "Bill Karsh, ProbeTable entries NP2003, NP2004, NP2013, NP2014, "
                + "NP2020, and NP2021: shank/site counts, 206 micrometre "
                + "tip-to-lowest-row-center distance, pitches, left-edge site "
                + "offset, and 250 micrometre shank pitch."
        ),
        ProbeCatalogSourceArtifact(
            title: "SpikeGLX Neuropixels geometry implementation",
            sourceUrl: "https://raw.githubusercontent.com/billkarsh/SpikeGLX/"
                + "d67bee45fa2635873456eb5d3f5e5a051690e64f/Src-imro/IMROTbl.cpp",
            documentRevision: "git commit "
                + "d67bee45fa2635873456eb5d3f5e5a051690e64f",
            retrievedOn: "2026-07-23",
            sha256: ProbePlanningContract.spikeGLXGeometrySHA256,
            citation: "SpikeGLX IMROTbl.cpp cases NP2003/NP2004, NP2013/NP2014, "
                + "and NP2020/NP2021: 206 micrometre tip offset, x0=27, lateral "
                + "pitch=32, axial pitch=15, shank width=70, and shank pitch=250."
        ),
    ]

    private static let neuropixels2QuadBaseSource = ProbeCatalogSourceArtifact(
        title: "Neuropixels 2.0 Quad Base multishank data sheet",
        sourceUrl: "https://www.neuropixels.org/_files/ugd/"
            + "328966_4e39ab2e46424dc9b3efa446d286ab0f.pdf",
        documentRevision: "No printed revision identifier; PDF metadata modification "
            + "date 2025-06-16",
        retrievedOn: "2026-07-23",
        sha256: ProbePlanningContract.neuropixels2QuadBaseSpecSHA256,
        citation: "imec, Neuropixels 2.0 Quad Base data sheet, pp. 1-3: four "
            + "10 mm shanks at 250 micrometre pitch, 5120 sites, 70 by 24 "
            + "micrometre cross-section, 175 micrometre chisel tip, and "
            + "NP2020/NP2021 order codes."
    )

    public static func validateCreate(_ request: ProbePlanCreateParameters) throws {
        try validateInput(
            protocolVersion: request.protocolVersion,
            projectId: request.projectId,
            revision: request.expectedProjectRevision,
            targetId: request.targetId,
            modelId: request.modelId,
            modelVersion: request.modelVersion,
            name: request.name,
            placementMode: request.placementMode,
            entryAP: request.entryAPMillimetres,
            entryML: request.entryMLMillimetres,
            entryDV: request.entryDVMillimetres,
            azimuth: request.azimuthDegrees,
            elevation: request.elevationDegrees,
            depth: request.insertionDepthMicrometres,
            rotation: request.axialRotationDegrees,
            acknowledged: request.customGeometryAcknowledged
        )
    }

    public static func validateUpdate(_ request: ProbePlanUpdateParameters) throws {
        try validateInput(
            protocolVersion: request.protocolVersion,
            projectId: request.projectId,
            revision: request.expectedProjectRevision,
            targetId: request.targetId,
            modelId: request.modelId,
            modelVersion: request.modelVersion,
            name: request.name,
            placementMode: request.placementMode,
            entryAP: request.entryAPMillimetres,
            entryML: request.entryMLMillimetres,
            entryDV: request.entryDVMillimetres,
            azimuth: request.azimuthDegrees,
            elevation: request.elevationDegrees,
            depth: request.insertionDepthMicrometres,
            rotation: request.axialRotationDegrees,
            acknowledged: request.customGeometryAcknowledged
        )
        try requireUUID(request.planId, "planId")
        try requireSha(request.expectedPlanInputSha256, "expectedPlanInputSha256")
    }

    public static func validateCatalogList(_ result: ProbeCatalogListResult) throws {
        try requireEnvelope(result.protocolVersion, result.status, "listed")
        guard result.catalogVersion == ProbePlanningContract.catalogVersion,
              result.modelCount == result.models.count,
              result.modelCount == 2,
              result.models[0].modelId
                == ProbePlanningContract.neuropixels2SingleShankModelId,
              result.models[0].modelVersion
                == ProbePlanningContract.neuropixels2ModelVersion,
              result.models[1].modelId
                == ProbePlanningContract.neuropixels2StandardFourShankModelId,
              result.models[1].modelVersion
                == ProbePlanningContract.neuropixels2ModelVersion
        else {
            throw invalid(
                "Probe catalog must contain only NP2 single and standard four-shank "
                    + "models in that order."
            )
        }
        for model in result.models { try validateCatalogModel(model, detailed: false) }
    }

    public static func validateCatalogGet(
        _ result: ProbeCatalogGetResult,
        modelId: String,
        modelVersion: String
    ) throws {
        try requireEnvelope(result.protocolVersion, result.status, "found")
        guard result.catalogVersion == ProbePlanningContract.catalogVersion,
              result.model.modelId == modelId,
              result.model.modelVersion == modelVersion
        else { throw invalid("Probe catalog detail does not match the requested identity.") }
        try validateCatalogModel(result.model, detailed: true)
    }

    public static func validateCatalogModel(
        _ model: ProbeCatalogModel,
        matches plan: ProbePlanDetail
    ) throws {
        try validateCatalogModel(model, detailed: true)
        guard model.modelId == plan.modelId,
              model.modelVersion == plan.modelVersion,
              model.displayName == plan.modelDisplayName,
              model.verificationStatus == plan.verificationStatus
        else {
            throw invalid("Selected probe catalog model does not match the plan being edited.")
        }
        try validatePlacedGeometry(plan, matches: model)
    }

    public static func validatePlanList(
        _ result: ProbePlanListResult,
        projectId: String,
        projectRevision: Int
    ) throws {
        try requireEnvelope(result.protocolVersion, result.status, "listed")
        guard result.projectId == projectId,
              result.projectRevision == projectRevision,
              result.planCount == result.plans.count
        else { throw invalid("Probe-plan list is inconsistent with current project state.") }
        var ids = Set<String>()
        for plan in result.plans {
            try validateSummary(plan)
            guard ids.insert(plan.planId).inserted else {
                throw invalid("Probe-plan list contains duplicate plan IDs.")
            }
        }
    }

    public static func validatePlanGet(
        _ result: ProbePlanGetResult,
        projectId: String,
        projectRevision: Int,
        planId: String
    ) throws {
        try requireEnvelope(result.protocolVersion, result.status, "found")
        guard result.projectId == projectId,
              result.projectRevision == projectRevision,
              result.plan.planId == planId
        else { throw invalid("Probe-plan detail is stale or belongs to another project.") }
        try validatePlan(result.plan)
        if let analysis = result.regionAnalysis {
            try validateRegionBundle(analysis, plan: result.plan)
        }
        if let analysis = result.majorVesselAnalysis {
            try MajorVesselAnalysisValidator.validateCurrent(
                analysis,
                projectId: result.projectId,
                projectRevision: result.projectRevision,
                planId: result.plan.planId,
                planVersion: result.plan.planVersion,
                planInputSha256: result.plan.inputSha256
            )
        }
    }

    public static func validateMutation(
        _ result: ProbePlanMutationResult,
        projectId: String,
        expectedStatus: String,
        expectedRevision: Int
    ) throws {
        try requireEnvelope(result.protocolVersion, result.status, expectedStatus)
        guard result.projectId == projectId, result.projectRevision == expectedRevision else {
            throw invalid("Probe-plan mutation revision or project identity is inconsistent.")
        }
        if expectedStatus == "updated", result.priorAnalysisCleared != true {
            throw invalid("A probe-plan update must explicitly clear its stale region analysis.")
        }
        try validatePlan(result.plan)
        guard result.plan.hasCurrentPlanningGeometry else {
            throw invalid("A probe-plan mutation must publish current recomputed geometry.")
        }
    }

    public static func validateCreatedMutation(
        _ result: ProbePlanMutationResult,
        request: ProbePlanCreateParameters,
        catalogModel: ProbeCatalogModel
    ) throws {
        try validateMutation(
            result,
            projectId: request.projectId,
            expectedStatus: "created",
            expectedRevision: request.expectedProjectRevision + 1
        )
        try validateMutationPlan(
            result.plan,
            expectedPlanId: nil,
            targetId: request.targetId,
            modelId: request.modelId,
            modelVersion: request.modelVersion,
            name: request.name,
            placementMode: request.placementMode,
            entryAP: request.entryAPMillimetres,
            entryML: request.entryMLMillimetres,
            entryDV: request.entryDVMillimetres,
            azimuth: request.azimuthDegrees,
            elevation: request.elevationDegrees,
            depth: request.insertionDepthMicrometres,
            rotation: request.axialRotationDegrees
        )
        try validateCatalogModel(catalogModel, matches: result.plan)
    }

    public static func validateUpdatedMutation(
        _ result: ProbePlanMutationResult,
        request: ProbePlanUpdateParameters,
        catalogModel: ProbeCatalogModel
    ) throws {
        try validateMutation(
            result,
            projectId: request.projectId,
            expectedStatus: "updated",
            expectedRevision: request.expectedProjectRevision + 1
        )
        try validateMutationPlan(
            result.plan,
            expectedPlanId: request.planId,
            targetId: request.targetId,
            modelId: request.modelId,
            modelVersion: request.modelVersion,
            name: request.name,
            placementMode: request.placementMode,
            entryAP: request.entryAPMillimetres,
            entryML: request.entryMLMillimetres,
            entryDV: request.entryDVMillimetres,
            azimuth: request.azimuthDegrees,
            elevation: request.elevationDegrees,
            depth: request.insertionDepthMicrometres,
            rotation: request.axialRotationDegrees
        )
        try validateCatalogModel(catalogModel, matches: result.plan)
    }

    public static func validateRemove(
        _ result: ProbePlanRemoveResult,
        projectId: String,
        planId: String,
        expectedRevision: Int
    ) throws {
        try requireEnvelope(result.protocolVersion, result.status, "removed")
        guard result.projectId == projectId,
              result.planId == planId,
              result.projectRevision == expectedRevision
        else { throw invalid("Probe-plan removal acknowledgement is inconsistent.") }
    }

    public static func validateRegionResult(
        _ result: ProbeRegionResult,
        projectId: String,
        plan: ProbePlanDetail,
        expectedStatus: String,
        expectedRevision: Int
    ) throws {
        try requireEnvelope(result.protocolVersion, result.status, expectedStatus)
        guard result.projectId == projectId, result.projectRevision == expectedRevision else {
            throw invalid("Probe-region result is stale or belongs to another project.")
        }
        try validateRegionBundle(result.regionAnalysis, plan: plan)
    }

    public static func validateExportGeneration(
        _ result: ProbeRegionExportResult,
        request: ProbeRegionExportParameters,
        plan: ProbePlanDetail,
        analysis: ProbeRegionAnalysisBundle
    ) throws {
        try requireEnvelope(result.protocolVersion, result.status, "generated")
        let expectedMime = request.format == .csv ? "text/csv" : "application/json"
        let expectedSuffix = ".\(request.format.rawValue)"
        guard request.protocolVersion == BridgeProtocolVersion.current,
              result.projectId == request.projectId,
              result.projectRevision == request.expectedProjectRevision,
              result.planId == request.planId,
              result.planId == plan.planId,
              result.planInputSha256 == request.expectedPlanInputSha256,
              result.planInputSha256 == plan.inputSha256,
              result.analysisSha256 == analysis.analysisSha256,
              result.format == request.format,
              result.mimeType == expectedMime,
              result.suggestedFileName.hasSuffix(expectedSuffix),
              !result.content.isEmpty,
              !result.projectMutated
        else { throw invalid("Generated probe-region export identity or format is invalid.") }
        let digest = SHA256.hash(data: Data(result.content.utf8)).map {
            String(format: "%02x", $0)
        }.joined()
        guard result.contentSha256 == digest else {
            throw invalid("Probe-region export content SHA-256 does not match its content.")
        }
    }

    public static func validateExportConfirmation(
        _ result: ProbeRegionExportConfirmationResult,
        request: ProbeRegionExportConfirmParameters
    ) throws {
        try requireEnvelope(result.protocolVersion, result.status, "exported")
        guard request.protocolVersion == BridgeProtocolVersion.current,
              result.projectId == request.projectId,
              result.projectRevision == request.expectedProjectRevision + 1,
              result.planId == request.planId,
              result.planInputSha256 == request.expectedPlanInputSha256,
              result.analysisSha256 == request.analysisSha256,
              result.format == request.format,
              result.contentSha256 == request.contentSha256,
              result.projectMutated
        else {
            throw invalid("Probe-region export confirmation is stale or inconsistent.")
        }
    }

    public static func validatePlan(_ plan: ProbePlanDetail) throws {
        try validateSummaryFields(
            planId: plan.planId,
            planVersion: plan.planVersion,
            name: plan.name,
            targetId: plan.targetId,
            modelId: plan.modelId,
            modelVersion: plan.modelVersion,
            modelDisplayName: plan.modelDisplayName,
            verificationStatus: plan.verificationStatus,
            inputSha256: plan.inputSha256,
            calibrationId: plan.calibrationId,
            calibrationVersion: plan.calibrationVersion,
            regionAnalysisAvailable: plan.regionAnalysisAvailable,
            regionAnalysisSha256: plan.regionAnalysisSha256,
            usableForNavigation: plan.usableForNavigation
        )
        guard plan.sourceTarget.componentOrder == ["AP", "ML", "DV"],
              plan.sourceTarget.units == "millimetre",
              [plan.sourceTarget.apMillimetres, plan.sourceTarget.mlMillimetres,
               plan.sourceTarget.dvMillimetres].allSatisfy(\.isFinite)
        else { throw invalid("Probe source target must preserve finite AP/ML/DV millimetres.") }
        let placement = plan.placement
        try requireUUID(placement.placementId, "placementId")
        switch plan.provenance.planningAlgorithmVersion {
        case ProbePlanningContract.planningAlgorithmVersion:
            guard let placementInput = plan.placementInput,
                  placement.method == placementInput.mode.normalizedPlacementMethod
            else {
                throw invalid("V3 probe plan does not preserve its explicit placement mode.")
            }
            try validatePlacementInput(placementInput)
            if placementInput.mode == .targetAnglesDepth {
                guard placementInput.angleFrameId == placement.canonicalFrame.frameId else {
                    throw invalid(
                        "Target-angle placement must use the normalized canonical target frame."
                    )
                }
            } else if placementInput.mode == .entryAnglesDepth {
                guard placementInput.angleFrameId?.hasPrefix("STEREOTAXIC:") == true else {
                    throw invalid(
                        "Entry-angle placement must preserve its calibrated stereotaxic source frame."
                    )
                }
            } else if placementInput.mode == .stereotaxicTargetManipulator {
                guard let manipulator = plan.manipulatorInput,
                      manipulator.frameId == placementInput.angleFrameId,
                      manipulator.azimuthDegrees == placementInput.azimuthDegrees,
                      manipulator.elevationDegrees == placementInput.elevationDegrees,
                      manipulator.insertionDepthMicrometres
                        == placementInput.insertionDepthMicrometres,
                      manipulator.axialRotationDegrees == placementInput.axialRotationDegrees,
                      manipulator.angleConvention == placementInput.angleConvention
                else {
                    throw invalid("V3 stereotaxic placement and manipulator inputs disagree.")
                }
            } else if plan.manipulatorInput != nil {
                throw invalid("V3 non-manipulator placement includes obsolete manipulator input.")
            }
        case ProbePlanningContract.stereotaxicPlanningAlgorithmVersion:
            guard let manipulator = plan.manipulatorInput,
                  plan.placementInput == nil,
                  !manipulator.frameId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  manipulator.azimuthDegrees.isFinite,
                  (-180 ... 180).contains(manipulator.azimuthDegrees),
                  manipulator.elevationDegrees.isFinite,
                  (-90 ... 90).contains(manipulator.elevationDegrees),
                  manipulator.insertionDepthMicrometres.isFinite,
                  manipulator.insertionDepthMicrometres > 0,
                  manipulator.axialRotationDegrees.isFinite,
                  (-180 ... 180).contains(manipulator.axialRotationDegrees),
                  manipulator.angleConvention == ProbePlanningContract.angleConvention,
                  placement.method == ProbePlanningContract.planningPlacementMethod
            else {
                throw invalid("Current probe plan does not preserve valid manipulator inputs.")
            }
        case ProbePlanningContract.legacyPlanningAlgorithmVersion:
            guard plan.manipulatorInput == nil,
                  plan.placementInput == nil,
                  placement.method == ProbePlanningContract.legacyPlacementMethod
            else {
                throw invalid("Legacy probe plan mixes current and obsolete geometry fields.")
            }
        default:
            throw invalid("Probe plan uses an unsupported planning algorithm version.")
        }
        guard placement.angleConvention == ProbePlanningContract.angleConvention,
              placement.azimuthDegrees.isFinite, (-180 ... 180).contains(placement.azimuthDegrees),
              placement.elevationDegrees.isFinite, (-90 ... 90).contains(placement.elevationDegrees),
              placement.insertionDepthMicrometres.isFinite,
              placement.insertionDepthMicrometres > 0,
              placement.axialRotationDegrees.isFinite,
              (-180 ... 180).contains(placement.axialRotationDegrees)
        else { throw invalid("Probe placement angles, depth, method, or convention are invalid.") }
        guard placement.canonicalFrame.componentOrder == ["AP", "ML", "DV"],
              placement.canonicalFrame.units == "micrometre",
              placement.canonicalFrame.apPositiveDirection == "anterior",
              placement.canonicalFrame.mlPositiveDirection == "right",
              placement.canonicalFrame.dvPositiveDirection == "dorsal/up",
              placement.atlasFrame.frameId == ProbePlanningContract.atlasFrameId,
              placement.atlasFrame.componentOrder == ["AP", "DV", "ML"],
              placement.atlasFrame.units == "micrometre",
              placement.atlasFrame.origin == "anterior/superior/right atlas corner"
        else { throw invalid("Probe placement coordinate frames are not the reviewed frames.") }
        try validatePhysicalPoint(placement.atlasFrame.entry)
        try validatePhysicalPoint(placement.atlasFrame.target)
        try validatePhysicalPoint(placement.atlasFrame.tip)
        try validatePlacementSpatialContract(plan)
        guard !plan.shanks.isEmpty else { throw invalid("Probe plan must contain a shank.") }
        var shankIds = Set<String>()
        for shank in plan.shanks {
            guard !shank.shankId.isEmpty, shankIds.insert(shank.shankId).inserted,
                  [shank.widthMicrometres, shank.thicknessMicrometres,
                   shank.conservativeEnvelopeRadiusMicrometres]
                    .allSatisfy({ $0.isFinite && $0 > 0 }),
                  !shank.envelopeDefinition.isEmpty
            else { throw invalid("Probe shank geometry is missing, duplicate, or non-positive.") }
            try validatePhysicalPoint(shank.entry)
            try validatePhysicalPoint(shank.tip)
        }
        var sites = Set<String>()
        for site in plan.recordingSites {
            guard shankIds.contains(site.shankId), !site.siteId.isEmpty,
                  sites.insert(site.id).inserted,
                  ["recording", "reference", "other"].contains(site.role)
            else { throw invalid("Probe recording-site identity or role is invalid.") }
            try validatePhysicalPoint(site.point)
        }
        guard plan.provenance.calibrationId == plan.calibrationId,
              plan.provenance.calibrationVersion == plan.calibrationVersion,
              plan.provenance.planInputSha256 == plan.inputSha256,
              plan.provenance.catalogVersion == ProbePlanningContract.catalogVersion
        else { throw invalid("Probe plan provenance does not match the displayed plan.") }
        try requireSha(plan.provenance.calibrationSha256, "calibrationSha256")
        try requireSha(plan.provenance.atlasMetadataSha256, "atlasMetadataSha256")
        try requireSha(plan.provenance.projectionSha256, "projectionSha256")
        guard !plan.warning.isEmpty else {
            throw invalid("Probe plan must retain its animal-planning warning.")
        }
    }

    public static func validateRegionBundle(
        _ bundle: ProbeRegionAnalysisBundle,
        plan: ProbePlanDetail
    ) throws {
        try requireUUID(bundle.analysisId, "analysisId")
        guard bundle.planId == plan.planId,
              bundle.planVersion == plan.planVersion,
              bundle.planInputSha256 == plan.inputSha256,
              bundle.algorithmVersion == ProbePlanningContract.regionAlgorithmVersion,
              bundle.usableForNavigation == false,
              !bundle.shanks.isEmpty,
              ISO8601DateFormatter().date(from: bundle.computedAt) != nil
        else { throw invalid("Probe-region bundle is stale, navigational, or malformed.") }
        try requireSha(bundle.analysisSha256, "analysisSha256")
        var shankIds = Set<String>()
        let planShanks = Set(plan.shanks.map(\.shankId))
        for shank in bundle.shanks {
            try requireUUID(shank.analysisId, "shank analysisId")
            guard planShanks.contains(shank.shankId), shankIds.insert(shank.shankId).inserted,
                  shank.totalPathLengthMicrometres.isFinite,
                  shank.clippedPathLengthMicrometres.isFinite,
                  shank.outsideAtlasPathLengthMicrometres.isFinite,
                  shank.totalPathLengthMicrometres >= 0,
                  shank.clippedPathLengthMicrometres >= 0,
                  shank.outsideAtlasPathLengthMicrometres >= 0,
                  abs(shank.totalPathLengthMicrometres
                        - shank.clippedPathLengthMicrometres
                        - shank.outsideAtlasPathLengthMicrometres) < 1e-5
            else { throw invalid("Probe-region shank lengths or identity are inconsistent.") }
            var priorExit = -Double.infinity
            for segment in shank.segments {
                guard segment.structureId >= 0,
                      !segment.acronym.isEmpty, !segment.name.isEmpty,
                      segment.entryDepthMicrometres.isFinite,
                      segment.exitDepthMicrometres.isFinite,
                      segment.lengthMicrometres.isFinite,
                      segment.entryDepthMicrometres >= priorExit - 1e-7,
                      segment.exitDepthMicrometres >= segment.entryDepthMicrometres,
                      abs(segment.lengthMicrometres
                        - (segment.exitDepthMicrometres - segment.entryDepthMicrometres)) < 1e-5,
                      segment.voxelCount > 0,
                      segment.rgb.count == 3,
                      segment.rgb.allSatisfy({ (0 ... 255).contains($0) })
                else { throw invalid("Probe-region segment intervals or RGB values are invalid.") }
                try validateRegionPoint(segment.entryPoint)
                try validateRegionPoint(segment.exitPoint)
                priorExit = segment.exitDepthMicrometres
            }
            var siteIds = Set<String>()
            for site in shank.recordingSiteAssignments {
                guard !site.siteId.isEmpty, siteIds.insert(site.siteId).inserted,
                      !site.acronym.isEmpty, !site.name.isEmpty,
                      !site.insideBrain || site.insideAtlas,
                      site.insideAtlas == (site.voxelIndex != nil)
                else { throw invalid("Probe recording-site region assignment is inconsistent.") }
                try validateRegionPoint(site.point)
            }
            let provenance = shank.provenance
            guard provenance.atlasIdentifier == SafetyPolicy.supportedAtlasIdentifier,
                  provenance.atlasVersion == SafetyPolicy.supportedAtlasVersion,
                  !provenance.annotationVersion.isEmpty,
                  !provenance.algorithmVersion.isEmpty,
                  !provenance.tieBreakRule.isEmpty
            else { throw invalid("Probe-region provenance is incomplete or uses another atlas.") }
            try requireSha(provenance.atlasMetadataSha256, "atlasMetadataSha256")
            try requireSha(provenance.annotationSha256, "annotationSha256")
            try requireSha(provenance.inputDigest, "inputDigest")
        }
    }

    private static func validateSummary(_ plan: ProbePlanSummary) throws {
        try validateSummaryFields(
            planId: plan.planId,
            planVersion: plan.planVersion,
            name: plan.name,
            targetId: plan.targetId,
            modelId: plan.modelId,
            modelVersion: plan.modelVersion,
            modelDisplayName: plan.modelDisplayName,
            verificationStatus: plan.verificationStatus,
            inputSha256: plan.inputSha256,
            calibrationId: plan.calibrationId,
            calibrationVersion: plan.calibrationVersion,
            regionAnalysisAvailable: plan.regionAnalysisAvailable,
            regionAnalysisSha256: plan.regionAnalysisSha256,
            usableForNavigation: plan.usableForNavigation
        )
    }

    private static func validateSummaryFields(
        planId: String,
        planVersion: Int,
        name: String,
        targetId: String,
        modelId: String,
        modelVersion: String,
        modelDisplayName: String,
        verificationStatus: String,
        inputSha256: String,
        calibrationId: String,
        calibrationVersion: Int,
        regionAnalysisAvailable: Bool,
        regionAnalysisSha256: String?,
        usableForNavigation: Bool
    ) throws {
        try requireUUID(planId, "planId")
        try requireUUID(targetId, "targetId")
        try requireUUID(calibrationId, "calibrationId")
        try requireSha(inputSha256, "inputSha256")
        guard planVersion > 0, calibrationVersion > 0,
              !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !modelId.isEmpty, !modelVersion.isEmpty, !modelDisplayName.isEmpty,
              acceptedVerificationStatuses.contains(verificationStatus),
              usableForNavigation == false,
              regionAnalysisAvailable == (regionAnalysisSha256 != nil)
        else { throw invalid("Probe-plan summary identity, status, or safety flag is invalid.") }
        let isNeuropixels2Single =
            modelId == ProbePlanningContract.neuropixels2SingleShankModelId
            && modelVersion == ProbePlanningContract.neuropixels2ModelVersion
            && modelDisplayName == ProbePlanningContract.neuropixels2SingleShankDisplayName
            && verificationStatus
                == ProbePlanningContract.sourceTranscribedReviewPendingStatus
        let isNeuropixels2StandardFour =
            modelId == ProbePlanningContract.neuropixels2StandardFourShankModelId
            && modelVersion == ProbePlanningContract.neuropixels2ModelVersion
            && modelDisplayName
                == ProbePlanningContract.neuropixels2StandardFourShankDisplayName
            && verificationStatus
                == ProbePlanningContract.sourceTranscribedReviewPendingStatus
        let isNeuropixels2QuadBaseFour =
            modelId == ProbePlanningContract.neuropixels2QuadBaseFourShankModelId
            && modelVersion == ProbePlanningContract.neuropixels2ModelVersion
            && modelDisplayName
                == ProbePlanningContract.neuropixels2QuadBaseFourShankDisplayName
            && verificationStatus
                == ProbePlanningContract.sourceTranscribedReviewPendingStatus
        let isNeuropixels1 = modelId == ProbePlanningContract.neuropixelsModelId
            && modelVersion == ProbePlanningContract.neuropixelsModelVersion
            && modelDisplayName == ProbePlanningContract.neuropixelsDisplayName
            && verificationStatus
                == ProbePlanningContract.sourceTranscribedReviewPendingStatus
        let isGenericTestFixture = modelId == ProbePlanningContract.genericModelId
            && modelVersion == ProbePlanningContract.genericModelVersion
            && modelDisplayName == ProbePlanningContract.genericDisplayName
            && verificationStatus == "user-defined-unverified"
        guard isNeuropixels2Single
            || isNeuropixels2StandardFour
            || isNeuropixels2QuadBaseFour
            || isNeuropixels1
            || isGenericTestFixture
        else {
            throw invalid("Probe-plan model identity and verification status do not match.")
        }
        if let regionAnalysisSha256 {
            try requireSha(regionAnalysisSha256, "regionAnalysisSha256")
        }
    }

    private static func validateCatalogModel(
        _ model: ProbeCatalogModel,
        detailed: Bool
    ) throws {
        guard !model.modelId.isEmpty, !model.modelVersion.isEmpty, !model.displayName.isEmpty,
              model.shankCount > 0, model.siteCount >= 0,
              model.units == "micrometre",
              acceptedVerificationStatuses.contains(model.verificationStatus),
              model.verifiedDeviceLabelPermitted == (model.verificationStatus == "verified")
        else { throw invalid("Probe catalog model identity, units, or verification gate is invalid.") }

        switch model.modelId {
        case ProbePlanningContract.neuropixels2SingleShankModelId:
            guard model.modelVersion == ProbePlanningContract.neuropixels2ModelVersion,
                  model.displayName
                    == ProbePlanningContract.neuropixels2SingleShankDisplayName,
                  model.manufacturer == "imec",
                  model.productCode
                    == ProbePlanningContract.neuropixels2SingleShankProductCode,
                  model.hardwareRevision == nil,
                  model.verificationStatus
                    == ProbePlanningContract.sourceTranscribedReviewPendingStatus,
                  model.verifiedDeviceLabelPermitted == false,
                  model.shankCount == 1,
                  model.siteCount == 1_280,
                  model.warning == ProbePlanningContract.sourceTranscribedReviewPendingWarning
            else {
                throw invalid("Neuropixels NP2 single-shank identity or warning changed.")
            }
        case ProbePlanningContract.neuropixels2StandardFourShankModelId:
            guard model.modelVersion == ProbePlanningContract.neuropixels2ModelVersion,
                  model.displayName
                    == ProbePlanningContract.neuropixels2StandardFourShankDisplayName,
                  model.manufacturer == "imec",
                  model.productCode
                    == ProbePlanningContract.neuropixels2StandardFourShankProductCode,
                  model.hardwareRevision == nil,
                  model.verificationStatus
                    == ProbePlanningContract.sourceTranscribedReviewPendingStatus,
                  model.verifiedDeviceLabelPermitted == false,
                  model.shankCount == 4,
                  model.siteCount == 5_120,
                  model.warning == ProbePlanningContract.sourceTranscribedReviewPendingWarning
            else {
                throw invalid(
                    "Neuropixels NP2 standard four-shank identity or warning changed."
                )
            }
        case ProbePlanningContract.neuropixels2QuadBaseFourShankModelId:
            guard model.modelVersion == ProbePlanningContract.neuropixels2ModelVersion,
                  model.displayName
                    == ProbePlanningContract.neuropixels2QuadBaseFourShankDisplayName,
                  model.manufacturer == "imec",
                  model.productCode
                    == ProbePlanningContract.neuropixels2QuadBaseFourShankProductCode,
                  model.hardwareRevision == nil,
                  model.verificationStatus
                    == ProbePlanningContract.sourceTranscribedReviewPendingStatus,
                  model.verifiedDeviceLabelPermitted == false,
                  model.shankCount == 4,
                  model.siteCount == 5_120,
                  model.warning == ProbePlanningContract.sourceTranscribedReviewPendingWarning
            else {
                throw invalid(
                    "Neuropixels NP2 Quad Base four-shank identity or warning changed."
                )
            }
        case ProbePlanningContract.neuropixelsModelId:
            guard model.modelVersion == ProbePlanningContract.neuropixelsModelVersion,
                  model.displayName == ProbePlanningContract.neuropixelsDisplayName,
                  model.manufacturer == "imec",
                  model.productCode == "PRB_1_4_0480_1",
                  model.hardwareRevision == nil,
                  model.verificationStatus
                    == ProbePlanningContract.sourceTranscribedReviewPendingStatus,
                  model.verifiedDeviceLabelPermitted == false,
                  model.shankCount == 1,
                  model.siteCount == 960,
                  model.warning == ProbePlanningContract.sourceTranscribedReviewPendingWarning
            else {
                throw invalid("Neuropixels NP1 identity or review-pending warning changed.")
            }
        case ProbePlanningContract.genericModelId:
            guard model.modelVersion == ProbePlanningContract.genericModelVersion,
                  model.displayName == ProbePlanningContract.genericDisplayName,
                  model.manufacturer == nil,
                  model.productCode == nil,
                  model.hardwareRevision == nil,
                  model.verificationStatus == "user-defined-unverified",
                  model.verifiedDeviceLabelPermitted == false,
                  model.shankCount == 1,
                  model.siteCount == 16,
                  model.warning == ProbePlanningContract.genericWarning
            else { throw invalid("Generic test probe identity or unverified warning changed.") }
        default:
            throw invalid("Probe catalog contains an unsupported model identity.")
        }

        guard detailed == (model.shanks != nil) else {
            throw invalid("Probe catalog detail level is inconsistent with the response method.")
        }
        guard detailed else {
            guard model.geometryNotes == nil,
                  model.reviewNotes == nil,
                  model.completeGeometryTranscribed == nil,
                  model.independentTranscriptionReviewCompleted == nil,
                  model.transcribedBy == nil,
                  model.independentlyReviewedBy == nil,
                  model.coordinateOrigin == nil,
                  model.localAxisDefinition == nil,
                  model.insertionAxisDefinition == nil,
                  model.primarySources == nil
            else { throw invalid("Probe catalog list unexpectedly contains detail metadata.") }
            return
        }

        guard let shanks = model.shanks,
              let geometryNotes = model.geometryNotes,
              !geometryNotes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let reviewNotes = model.reviewNotes,
              !reviewNotes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              model.completeGeometryTranscribed != nil,
              model.independentTranscriptionReviewCompleted != nil,
              model.coordinateOrigin == ProbePlanningContract.coordinateOrigin,
              model.localAxisDefinition == ProbePlanningContract.localAxisDefinition,
              model.insertionAxisDefinition == ProbePlanningContract.insertionAxisDefinition,
              let primarySources = model.primarySources
        else { throw invalid("Probe catalog detail provenance or coordinate frame is incomplete.") }

        guard shanks.count == model.shankCount,
              shanks.reduce(0, { $0 + $1.sites.count }) == model.siteCount
        else { throw invalid("Probe catalog shank or site counts are inconsistent.") }
        var shankIds = Set<String>(), siteIds = Set<String>()
        for shank in shanks {
            guard !shank.shankId.isEmpty, shankIds.insert(shank.shankId).inserted,
                  [shank.lengthMicrometres, shank.widthMicrometres,
                   shank.thicknessMicrometres].allSatisfy({ $0.isFinite && $0 > 0 }),
                  ["chisel", "flat", "triangular", "tapered", "user-defined"]
                    .contains(shank.tipGeometry),
                  shank.tipLengthMicrometres.isFinite,
                  shank.tipLengthMicrometres >= 0,
                  shank.tipLengthMicrometres < shank.lengthMicrometres,
                  !shank.tipGeometryNotes
                    .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  shank.centerLateralMicrometres.isFinite,
                  shank.centerNormalMicrometres.isFinite,
                  shank.siteCount == shank.sites.count
            else { throw invalid("Probe catalog shank geometry is invalid.") }
            for site in shank.sites {
                guard !site.siteId.isEmpty, siteIds.insert(site.siteId).inserted,
                      ["recording", "reference", "other"].contains(site.role),
                      site.axialFromTipMicrometres.isFinite,
                      (0 ... shank.lengthMicrometres).contains(site.axialFromTipMicrometres),
                      site.lateralMicrometres.isFinite,
                      abs(site.lateralMicrometres) <= shank.widthMicrometres / 2,
                      site.normalMicrometres.isFinite,
                      abs(site.normalMicrometres) <= shank.thicknessMicrometres / 2
                else { throw invalid("Probe catalog recording-site geometry is invalid.") }
            }
        }

        for source in primarySources {
            guard !source.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  source.sourceUrl.hasPrefix("https://"),
                  !source.documentRevision.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  !source.retrievedOn.isEmpty,
                  !source.citation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            else { throw invalid("Probe primary-source provenance is incomplete.") }
            try requireSha(source.sha256, "primary source sha256")
        }

        switch model.modelId {
        case ProbePlanningContract.neuropixels2SingleShankModelId:
            try validateNeuropixels2CatalogDetail(
                model,
                shanks: shanks,
                primarySources: primarySources,
                expectedShankCount: 1,
                expectedSimultaneousChannelCount:
                    ProbePlanningContract.neuropixels2SingleShankSimultaneousChannelCount,
                includesQuadBaseSource: false
            )
        case ProbePlanningContract.neuropixels2StandardFourShankModelId:
            try validateNeuropixels2CatalogDetail(
                model,
                shanks: shanks,
                primarySources: primarySources,
                expectedShankCount: 4,
                expectedSimultaneousChannelCount:
                    ProbePlanningContract.neuropixels2StandardFourShankSimultaneousChannelCount,
                includesQuadBaseSource: false
            )
        case ProbePlanningContract.neuropixels2QuadBaseFourShankModelId:
            try validateNeuropixels2CatalogDetail(
                model,
                shanks: shanks,
                primarySources: primarySources,
                expectedShankCount: 4,
                expectedSimultaneousChannelCount:
                    ProbePlanningContract.neuropixels2QuadBaseFourShankSimultaneousChannelCount,
                includesQuadBaseSource: true
            )
        case ProbePlanningContract.neuropixelsModelId:
            try validateNeuropixelsCatalogDetail(
                model,
                shanks: shanks,
                primarySources: primarySources
            )
        case ProbePlanningContract.genericModelId:
            try validateGenericCatalogDetail(
                model,
                shanks: shanks,
                primarySources: primarySources
            )
        default:
            throw invalid("Probe catalog contains an unsupported detailed model.")
        }
    }

    private static func validateNeuropixels2CatalogDetail(
        _ model: ProbeCatalogModel,
        shanks: [ProbeCatalogShank],
        primarySources: [ProbeCatalogSourceArtifact],
        expectedShankCount: Int,
        expectedSimultaneousChannelCount: Int,
        includesQuadBaseSource: Bool
    ) throws {
        var expectedSources = neuropixels2CommonSources
        if includesQuadBaseSource {
            expectedSources.append(neuropixels2QuadBaseSource)
        }
        guard model.completeGeometryTranscribed == true,
              model.independentTranscriptionReviewCompleted == false,
              model.transcribedBy == "Brain3D automated source transcription",
              model.independentlyReviewedBy == nil,
              model.geometryNotes?.contains(
                "\(expectedSimultaneousChannelCount) simultaneously configurable"
              ) == true,
              primarySources == expectedSources
        else {
            throw invalid(
                "Review-pending NP2 geometry or exact primary-source provenance changed."
            )
        }

        guard shanks.count == expectedShankCount else {
            throw invalid("Neuropixels NP2 shank count changed.")
        }
        for (shankIndex, shank) in shanks.enumerated() {
            guard shank.shankId == "shank-\(shankIndex)",
                  shank.lengthMicrometres == 10_000,
                  shank.widthMicrometres == 70,
                  shank.thicknessMicrometres == 24,
                  shank.tipGeometry == "chisel",
                  shank.tipLengthMicrometres == 175,
                  shank.tipGeometryNotes == neuropixels2TipGeometryNotes,
                  shank.centerLateralMicrometres == Double(250 * shankIndex),
                  shank.centerNormalMicrometres == 0,
                  shank.siteCount == 1_280
            else { throw invalid("Neuropixels NP2 shank or tip geometry changed.") }

            for (siteIndex, site) in shank.sites.enumerated() {
                let row = siteIndex / 2
                let column = siteIndex % 2
                guard site.siteId == String(
                    format: "shank-%d-electrode-%04d",
                    shankIndex,
                    siteIndex
                ),
                    site.role == "recording",
                    site.bank == "virtual-bank-\(siteIndex / 384)",
                    site.axialFromTipMicrometres == Double(206 + 15 * row),
                    site.lateralMicrometres == Double(-8 + 32 * column),
                    site.normalMicrometres == 0
                else {
                    throw invalid(
                        "Neuropixels NP2 site table changed at shank "
                            + "\(shankIndex), electrode \(siteIndex)."
                    )
                }
            }
        }
    }

    private static func validateNeuropixelsCatalogDetail(
        _ model: ProbeCatalogModel,
        shanks: [ProbeCatalogShank],
        primarySources: [ProbeCatalogSourceArtifact]
    ) throws {
        guard model.completeGeometryTranscribed == true,
              model.independentTranscriptionReviewCompleted == false,
              model.transcribedBy == "Brain3D automated source transcription",
              model.independentlyReviewedBy == nil,
              primarySources.count == neuropixelsSourceIdentities.count
        else {
            throw invalid(
                "Review-pending NP1 geometry cannot claim independent verification."
            )
        }
        for (source, expected) in zip(primarySources, neuropixelsSourceIdentities) {
            guard source.sourceUrl == expected.url,
                  source.sha256 == expected.sha256,
                  source.retrievedOn == "2026-07-22"
            else { throw invalid("Neuropixels NP1 primary-source identity changed.") }
        }

        guard let shank = shanks.first,
              shank.shankId == "shank-0",
              shank.lengthMicrometres == 10_000,
              shank.widthMicrometres == 70,
              shank.thicknessMicrometres == 24,
              shank.tipGeometry == "chisel",
              shank.tipLengthMicrometres == 175,
              shank.tipGeometryNotes.contains("175"),
              shank.tipGeometryNotes.contains("209"),
              shank.centerLateralMicrometres == 0,
              shank.centerNormalMicrometres == 0,
              shank.siteCount == 960
        else { throw invalid("Neuropixels NP1 shank or tip geometry changed.") }

        let referenceSites: Set<Int> = [191, 575, 959]
        for (index, site) in shank.sites.enumerated() {
            let row = index / 2
            let column = index % 2
            let expectedLateral: Double
            if row.isMultiple(of: 2) {
                expectedLateral = column == 0 ? -8 : 24
            } else {
                expectedLateral = column == 0 ? -24 : 8
            }
            guard site.siteId == String(format: "electrode-%03d", index),
                  site.role == (referenceSites.contains(index) ? "reference" : "recording"),
                  site.bank == "bank-\(index / 384)",
                  site.axialFromTipMicrometres == Double(209 + 20 * row),
                  site.lateralMicrometres == expectedLateral,
                  site.normalMicrometres == 0
            else {
                throw invalid("Neuropixels NP1 site table changed at electrode \(index).")
            }
        }
    }

    private static func validateGenericCatalogDetail(
        _ model: ProbeCatalogModel,
        shanks: [ProbeCatalogShank],
        primarySources: [ProbeCatalogSourceArtifact]
    ) throws {
        guard model.completeGeometryTranscribed == false,
              model.independentTranscriptionReviewCompleted == false,
              model.transcribedBy == nil,
              model.independentlyReviewedBy == nil,
              primarySources.isEmpty,
              let shank = shanks.first,
              shank.shankId == "test-shank-1",
              shank.lengthMicrometres == 10_000,
              shank.widthMicrometres == 70,
              shank.thicknessMicrometres == 20,
              shank.tipGeometry == "triangular",
              shank.tipLengthMicrometres == 200,
              shank.centerLateralMicrometres == 0,
              shank.centerNormalMicrometres == 0,
              shank.siteCount == 16
        else { throw invalid("Generic software-test probe geometry changed.") }
        for (index, site) in shank.sites.enumerated() {
            guard site.siteId == String(format: "test-site-%02d", index + 1),
                  site.role == "recording",
                  site.bank == "software-test",
                  site.axialFromTipMicrometres == Double(index + 1) * 250,
                  site.lateralMicrometres == 0,
                  site.normalMicrometres == 0
            else { throw invalid("Generic software-test site table changed.") }
        }
    }

    private static func validatePlacementSpatialContract(
        _ plan: ProbePlanDetail
    ) throws {
        let placement = plan.placement
        let canonicalFrame = placement.canonicalFrame
        let entry = vector(canonicalFrame.entry)
        let target = vector(canonicalFrame.target)
        let tip = vector(canonicalFrame.tip)
        guard [entry.ap, entry.ml, entry.dv, target.ap, target.ml, target.dv,
               tip.ap, tip.ml, tip.dv].allSatisfy(\.isFinite),
              placement.modelToPlacementUniformScale.isFinite,
              placement.modelToPlacementUniformScale > 0
        else {
            throw invalid(
                "Probe placement canonical points and model scale must be finite and positive."
            )
        }

        try validateAtlasPoint(
            placement.atlasFrame.entry,
            matchesCanonical: entry,
            label: "entry"
        )
        try validateAtlasPoint(
            placement.atlasFrame.target,
            matchesCanonical: target,
            label: "target"
        )
        try validateAtlasPoint(
            placement.atlasFrame.tip,
            matchesCanonical: tip,
            label: "tip"
        )

        let inward = try validateUnitDirection(
            placement.inwardDirection,
            frameId: canonicalFrame.frameId,
            label: "inward"
        )
        let entryToTip = tip.subtracting(entry)
        let entryToTipDistance = entryToTip.magnitude
        guard entryToTipDistance.isFinite,
              entryToTipDistance > 0,
              approximatelyEqual(
                  entryToTipDistance,
                  placement.insertionDepthMicrometres,
                  absoluteTolerance: coordinateToleranceMicrometres
              )
        else {
            throw invalid(
                "Probe placement insertion depth does not match canonical entry-to-tip geometry."
            )
        }
        let expectedInward = entryToTip.scaled(by: 1 / entryToTipDistance)
        guard vectorsApproximatelyEqual(
            inward,
            expectedInward,
            tolerance: directionTolerance
        ) else {
            throw invalid(
                "Probe placement inward direction does not match canonical entry-to-tip geometry."
            )
        }

        let lateral = try validateUnitDirection(
            placement.localLateralDirection,
            frameId: canonicalFrame.frameId,
            label: "local lateral"
        )
        let normal = try validateUnitDirection(
            placement.localNormalDirection,
            frameId: canonicalFrame.frameId,
            label: "local normal"
        )
        guard abs(inward.dot(lateral)) <= directionTolerance,
              abs(inward.dot(normal)) <= directionTolerance,
              abs(lateral.dot(normal)) <= directionTolerance
        else {
            throw invalid("Probe placement local directions must form an orthogonal basis.")
        }
        let expectedNormal = inward.scaled(by: -1).cross(lateral)
        guard vectorsApproximatelyEqual(
            normal,
            expectedNormal,
            tolerance: directionTolerance
        ) else {
            throw invalid("Probe placement local basis violates the probe right-hand rule.")
        }
    }

    private static func validatePlacedGeometry(
        _ plan: ProbePlanDetail,
        matches model: ProbeCatalogModel
    ) throws {
        guard let catalogShanks = model.shanks else {
            throw invalid("Exact probe-plan geometry requires detailed catalog shanks.")
        }

        let expectedShankIds = Set(catalogShanks.map(\.shankId))
        let actualShankIds = Set(plan.shanks.map(\.shankId))
        guard plan.shanks.count == catalogShanks.count,
              actualShankIds.count == plan.shanks.count,
              actualShankIds == expectedShankIds
        else {
            throw invalid(
                "Probe plan does not contain the exact shanks from its detailed catalog model."
            )
        }

        let expectedSites = Set(catalogShanks.flatMap { shank in
            shank.sites.map { site in
                PlanSiteIdentity(
                    shankId: shank.shankId,
                    siteId: site.siteId,
                    role: site.role,
                    bank: site.bank
                )
            }
        })
        let actualSites = Set(plan.recordingSites.map { site in
            PlanSiteIdentity(
                shankId: site.shankId,
                siteId: site.siteId,
                role: site.role,
                bank: site.bank
            )
        })
        guard plan.recordingSites.count == model.siteCount,
              actualSites.count == plan.recordingSites.count,
              actualSites == expectedSites
        else {
            throw invalid(
                "Probe plan does not contain every exact recording-site identity, role, "
                    + "and bank from its detailed catalog model."
            )
        }

        let placement = plan.placement
        let scale = placement.modelToPlacementUniformScale
        let canonicalEntry = vector(placement.canonicalFrame.entry)
        let canonicalTip = vector(placement.canonicalFrame.tip)
        let inward = vector(placement.inwardDirection)
        let axialTowardBase = inward.scaled(by: -1)
        let lateral = vector(placement.localLateralDirection)
        let normal = vector(placement.localNormalDirection)
        let placedShanksById = Dictionary(
            uniqueKeysWithValues: plan.shanks.map { ($0.shankId, $0) }
        )
        let placedSitesByIdentity = Dictionary(
            uniqueKeysWithValues: plan.recordingSites.map { site in
                (
                    PlanSiteIdentity(
                        shankId: site.shankId,
                        siteId: site.siteId,
                        role: site.role,
                        bank: site.bank
                    ),
                    site
                )
            }
        )

        for catalogShank in catalogShanks {
            guard let placedShank = placedShanksById[catalogShank.shankId] else {
                throw invalid("Probe plan is missing a catalogued placed shank.")
            }
            let shankOffset = lateral
                .scaled(by: catalogShank.centerLateralMicrometres * scale)
                .adding(
                    normal.scaled(
                        by: catalogShank.centerNormalMicrometres * scale
                    )
                )
            try validateAtlasPoint(
                placedShank.entry,
                matchesCanonical: canonicalEntry.adding(shankOffset),
                label: "\(catalogShank.shankId) entry"
            )
            try validateAtlasPoint(
                placedShank.tip,
                matchesCanonical: canonicalTip.adding(shankOffset),
                label: "\(catalogShank.shankId) tip"
            )

            let expectedWidth = catalogShank.widthMicrometres * scale
            let expectedThickness = catalogShank.thicknessMicrometres * scale
            let expectedEnvelopeRadius = hypot(
                expectedWidth / 2,
                expectedThickness / 2
            )
            guard approximatelyEqual(
                placedShank.widthMicrometres,
                expectedWidth,
                absoluteTolerance: coordinateToleranceMicrometres
            ),
                approximatelyEqual(
                    placedShank.thicknessMicrometres,
                    expectedThickness,
                    absoluteTolerance: coordinateToleranceMicrometres
                ),
                approximatelyEqual(
                    placedShank.conservativeEnvelopeRadiusMicrometres,
                    expectedEnvelopeRadius,
                    absoluteTolerance: coordinateToleranceMicrometres
                ),
                placedShank.envelopeDefinition
                    == "circumscribed-radius-of-rectangular-cross-section"
            else {
                throw invalid(
                    "Probe placed-shank dimensions or conservative envelope "
                        + "do not match the scaled catalog geometry."
                )
            }

            for catalogSite in catalogShank.sites {
                let identity = PlanSiteIdentity(
                    shankId: catalogShank.shankId,
                    siteId: catalogSite.siteId,
                    role: catalogSite.role,
                    bank: catalogSite.bank
                )
                guard let placedSite = placedSitesByIdentity[identity] else {
                    throw invalid("Probe plan is missing a catalogued placed recording site.")
                }
                let expectedCanonicalPoint = canonicalTip
                    .adding(
                        axialTowardBase.scaled(
                            by: catalogSite.axialFromTipMicrometres * scale
                        )
                    )
                    .adding(
                        lateral.scaled(
                            by: (
                                catalogShank.centerLateralMicrometres
                                    + catalogSite.lateralMicrometres
                            ) * scale
                        )
                    )
                    .adding(
                        normal.scaled(
                            by: (
                                catalogShank.centerNormalMicrometres
                                    + catalogSite.normalMicrometres
                            ) * scale
                        )
                    )
                try validateAtlasPoint(
                    placedSite.point,
                    matchesCanonical: expectedCanonicalPoint,
                    label: "\(catalogShank.shankId) \(catalogSite.siteId)"
                )
            }
        }
    }

    private static func validateInput(
        protocolVersion: Int,
        projectId: String,
        revision: Int,
        targetId: String,
        modelId: String,
        modelVersion: String,
        name: String,
        placementMode: ProbePlacementMode,
        entryAP: Double?,
        entryML: Double?,
        entryDV: Double?,
        azimuth: Double?,
        elevation: Double?,
        depth: Double?,
        rotation: Double,
        acknowledged: Bool
    ) throws {
        guard protocolVersion == BridgeProtocolVersion.current else {
            throw invalid("Probe request protocol version is unsupported.")
        }
        try requireUUID(projectId, "projectId")
        try requireUUID(targetId, "targetId")
        guard revision >= 0,
              !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              name.count <= 200,
              !modelId.isEmpty, !modelVersion.isEmpty,
              rotation.isFinite, (-180 ... 180).contains(rotation)
        else { throw invalid("Probe-plan name, rotation, or revision is invalid.") }
        let entryValues = [entryAP, entryML, entryDV]
        let entryShapeIsValid = placementMode.requiresEntryCoordinates
            ? entryValues.allSatisfy({ $0 != nil })
            : entryValues.allSatisfy({ $0 == nil })
        guard entryShapeIsValid,
              entryValues.compactMap({ $0 }).allSatisfy(\.isFinite)
        else {
            throw invalid("Probe placement mode and entry AP/ML/DV fields are inconsistent.")
        }
        let angleValues = [azimuth, elevation, depth]
        let angleShapeIsValid = placementMode.requiresAnglesAndDepth
            ? angleValues.allSatisfy({ $0 != nil })
            : angleValues.allSatisfy({ $0 == nil })
        guard angleShapeIsValid else {
            throw invalid("Probe placement mode and angle/depth fields are inconsistent.")
        }
        if placementMode.requiresAnglesAndDepth {
            guard let azimuth, let elevation, let depth,
                  azimuth.isFinite, (-180 ... 180).contains(azimuth),
                  elevation.isFinite, (-90 ... 90).contains(elevation),
                  depth.isFinite, depth > 0
            else { throw invalid("Probe placement angles or insertion depth are invalid.") }
        }
        let requiresAcknowledgement: Bool
        switch modelId {
        case ProbePlanningContract.neuropixels2SingleShankModelId,
             ProbePlanningContract.neuropixels2StandardFourShankModelId,
             ProbePlanningContract.neuropixels2QuadBaseFourShankModelId:
            guard modelVersion == ProbePlanningContract.neuropixels2ModelVersion else {
                throw invalid("The requested Neuropixels 2.0 model version is not catalogued.")
            }
            requiresAcknowledgement = true
        case ProbePlanningContract.neuropixelsModelId:
            guard modelVersion == ProbePlanningContract.neuropixelsModelVersion else {
                throw invalid("The requested Neuropixels model version is not catalogued.")
            }
            requiresAcknowledgement = true
        case ProbePlanningContract.genericModelId:
            guard modelVersion == ProbePlanningContract.genericModelVersion else {
                throw invalid("The requested generic test model version is not catalogued.")
            }
            requiresAcknowledgement = true
        default:
            throw invalid("The requested probe model identity is not in this catalog.")
        }
        if requiresAcknowledgement, !acknowledged {
            throw invalid(
                "This probe geometry requires explicit acknowledgement before animal planning."
            )
        }
    }

    private static func validateMutationPlan(
        _ plan: ProbePlanDetail,
        expectedPlanId: String?,
        targetId: String,
        modelId: String,
        modelVersion: String,
        name: String,
        placementMode: ProbePlacementMode,
        entryAP: Double?,
        entryML: Double?,
        entryDV: Double?,
        azimuth: Double?,
        elevation: Double?,
        depth: Double?,
        rotation: Double
    ) throws {
        let draft = plan.placementDraft
        guard expectedPlanId == nil || plan.planId == expectedPlanId,
              plan.targetId == targetId,
              plan.modelId == modelId,
              plan.modelVersion == modelVersion,
              plan.name == name,
              draft.mode == placementMode,
              draft.entryAPMillimetres == entryAP,
              draft.entryMLMillimetres == entryML,
              draft.entryDVMillimetres == entryDV,
              draft.azimuthDegrees == azimuth,
              draft.elevationDegrees == elevation,
              draft.insertionDepthMicrometres == depth,
              draft.axialRotationDegrees == rotation
        else {
            throw invalid(
                "Probe-plan mutation does not acknowledge the submitted plan identity and placement inputs."
            )
        }
    }

    private static func validatePlacementInput(_ input: ProbePlacementInput) throws {
        guard input.axialRotationDegrees.isFinite,
              (-180 ... 180).contains(input.axialRotationDegrees)
        else { throw invalid("Placement input axial rotation is invalid.") }

        if input.mode.requiresEntryCoordinates {
            guard let entry = input.entry,
                  entry.frameId == ProbePlanningContract.bregmaEntryFrameId,
                  entry.origin == "bregma",
                  entry.componentOrder == ["AP", "ML", "DV"],
                  entry.units == "millimetre",
                  entry.apPositiveDirection == "anterior",
                  entry.apNegativeDirection == "posterior/back",
                  entry.mlPositiveDirection == "right",
                  entry.mlNegativeDirection == "left",
                  entry.dvPositiveDirection == "dorsal/up",
                  entry.dvNegativeDirection == "deep/ventral",
                  [entry.apMillimetres, entry.mlMillimetres, entry.dvMillimetres]
                    .allSatisfy(\.isFinite)
            else { throw invalid("Placement entry AP/ML/DV semantics are invalid.") }
        } else if input.entry != nil {
            throw invalid("Placement mode cannot contain entry coordinates.")
        }

        let angleValues = [
            input.azimuthDegrees,
            input.elevationDegrees,
            input.insertionDepthMicrometres,
        ]
        if input.mode.requiresAnglesAndDepth {
            guard let frameId = input.angleFrameId,
                  !frameId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  let azimuth = input.azimuthDegrees,
                  azimuth.isFinite, (-180 ... 180).contains(azimuth),
                  let elevation = input.elevationDegrees,
                  elevation.isFinite, (-90 ... 90).contains(elevation),
                  let depth = input.insertionDepthMicrometres,
                  depth.isFinite, depth > 0,
                  input.angleConvention == ProbePlanningContract.angleConvention
            else { throw invalid("Placement angle frame, angles, depth, or convention is invalid.") }
        } else {
            guard input.angleFrameId == nil,
                  angleValues.allSatisfy({ $0 == nil }),
                  input.angleConvention == nil
            else { throw invalid("Entry-and-target mode cannot contain angle or depth inputs.") }
        }
    }

    private static func vector(_ point: ProbeCanonicalPoint) -> Vector3 {
        Vector3(
            ap: point.apMicrometres,
            ml: point.mlMicrometres,
            dv: point.dvMicrometres
        )
    }

    private static func vector(_ direction: ProbeUnitDirection) -> Vector3 {
        Vector3(ap: direction.ap, ml: direction.ml, dv: direction.dv)
    }

    private static func validateUnitDirection(
        _ direction: ProbeUnitDirection,
        frameId: String,
        label: String
    ) throws -> Vector3 {
        let value = vector(direction)
        guard direction.frameId == frameId,
              direction.componentOrder == ["AP", "ML", "DV"],
              direction.units == "dimensionless",
              [value.ap, value.ml, value.dv].allSatisfy(\.isFinite),
              approximatelyEqual(
                  value.magnitude,
                  1,
                  absoluteTolerance: directionTolerance
              )
        else {
            throw invalid(
                "Probe placement \(label) direction is not a unit vector "
                    + "in the canonical AP/ML/DV frame."
            )
        }
        return value
    }

    private static func validateAtlasPoint(
        _ point: ProbePhysicalPoint,
        matchesCanonical canonical: Vector3,
        label: String
    ) throws {
        try validatePhysicalPoint(point)
        guard approximatelyEqual(
            point.apMicrometres,
            -canonical.ap,
            absoluteTolerance: coordinateToleranceMicrometres
        ),
            approximatelyEqual(
                point.dvMicrometres,
                -canonical.dv,
                absoluteTolerance: coordinateToleranceMicrometres
            ),
            approximatelyEqual(
                point.mlMicrometres,
                -canonical.ml,
                absoluteTolerance: coordinateToleranceMicrometres
            )
        else {
            throw invalid(
                "Probe \(label) does not exactly convert canonical AP/ML/DV "
                    + "to BrainGlobe physical AP/DV/ML coordinates."
            )
        }
    }

    private static func vectorsApproximatelyEqual(
        _ first: Vector3,
        _ second: Vector3,
        tolerance: Double
    ) -> Bool {
        abs(first.ap - second.ap) <= tolerance
            && abs(first.ml - second.ml) <= tolerance
            && abs(first.dv - second.dv) <= tolerance
    }

    private static func approximatelyEqual(
        _ first: Double,
        _ second: Double,
        absoluteTolerance: Double
    ) -> Bool {
        guard first.isFinite, second.isFinite else { return false }
        let relativeTolerance = max(abs(first), abs(second)) * 1e-12
        return abs(first - second) <= max(absoluteTolerance, relativeTolerance)
    }

    private static func validatePhysicalPoint(_ point: ProbePhysicalPoint) throws {
        guard [point.apMicrometres, point.dvMicrometres, point.mlMicrometres]
            .allSatisfy(\.isFinite), point.insideAtlas == (point.voxelIndex != nil)
        else { throw invalid("Probe atlas point or inside-atlas voxel state is inconsistent.") }
    }

    private static func validateRegionPoint(_ point: ProbeRegionPoint) throws {
        guard point.frameId == ProbePlanningContract.regionFrameId,
              point.componentOrder == ["AP", "ML", "DV"],
              point.units == "micrometre",
              [point.apMicrometres, point.mlMicrometres, point.dvMicrometres]
                .allSatisfy(\.isFinite)
        else { throw invalid("Probe-region point does not use exact AP/ML/DV physical units.") }
    }

    private static func requireEnvelope(
        _ protocolVersion: Int,
        _ status: String,
        _ expectedStatus: String
    ) throws {
        guard protocolVersion == BridgeProtocolVersion.current, status == expectedStatus else {
            throw invalid("Probe bridge protocol version or status is invalid.")
        }
    }

    private static func requireUUID(_ value: String, _ field: String) throws {
        guard UUID(uuidString: value) != nil else { throw invalid("\(field) must be a UUID.") }
    }

    private static func requireSha(_ value: String, _ field: String) throws {
        guard value.utf8.count == 64,
              value.utf8.allSatisfy({
                  ($0 >= 48 && $0 <= 57) || ($0 >= 97 && $0 <= 102)
              })
        else { throw invalid("\(field) must be 64 lowercase hexadecimal characters.") }
    }

    private static func invalid(_ message: String) -> ProbePlanningValidationError {
        .invalid(message)
    }
}
