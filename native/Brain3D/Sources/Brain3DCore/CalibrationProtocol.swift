import Foundation

public enum CalibrationTransformMethod: String, Codable, CaseIterable, Equatable, Sendable {
    case rigid
    case similarity
    case affine
}

public enum CalibrationDVReference: String, Codable, Equatable, Sendable {
    case bregma
}

public enum CalibrationNumberInputError: Error, Equatable, LocalizedError, Sendable {
    case invalidDecimal(field: String)
    case outsideFiniteRange(field: String)

    public var errorDescription: String? {
        switch self {
        case let .invalidDecimal(field):
            "\(field) must be a plain decimal number."
        case let .outsideFiniteRange(field):
            "\(field) is outside the finite numeric range."
        }
    }
}

public enum CalibrationNumberInput {
    private static let decimalPattern = #"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$"#

    public static func parse(_ text: String, field: String) throws -> Double {
        let normalized = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard
            !normalized.isEmpty,
            normalized.range(of: decimalPattern, options: .regularExpression) != nil,
            let value = Double(normalized)
        else {
            throw CalibrationNumberInputError.invalidDecimal(field: field)
        }
        guard value.isFinite else {
            throw CalibrationNumberInputError.outsideFiniteRange(field: field)
        }
        return value == 0 ? 0 : value
    }
}

public struct CalibrationListParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String

    public init(projectId: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
    }
}

public struct CalibrationGetParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let calibrationId: String

    public init(projectId: String, calibrationId: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.calibrationId = calibrationId
    }
}

public struct CalibrationMutationParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let calibrationId: String

    public init(projectId: String, expectedProjectRevision: Int, calibrationId: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.expectedProjectRevision = expectedProjectRevision
        self.calibrationId = calibrationId
    }
}

public struct CalibrationProjectTargetParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let targetId: String

    public init(projectId: String, targetId: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.targetId = targetId
    }
}

public struct CalibrationSourceFrame: Codable, Equatable, Sendable {
    public let frameId: String
    public let kind: String
    public let originDescription: String
    public let apPositiveDirection: String
    public let mlPositiveDirection: String
    public let dvPositiveDirection: String
    public let componentOrder: [String]
    public let units: String

    public init(
        frameId: String,
        originDescription: String,
        apPositiveDirection: String,
        mlPositiveDirection: String,
        dvPositiveDirection: String
    ) {
        self.frameId = frameId
        kind = "skull"
        self.originDescription = originDescription
        self.apPositiveDirection = apPositiveDirection
        self.mlPositiveDirection = mlPositiveDirection
        self.dvPositiveDirection = dvPositiveDirection
        componentOrder = ["AP", "ML", "DV"]
        units = "micrometre"
    }
}

public struct CalibrationSkullPoint: Codable, Equatable, Sendable {
    public let frameId: String
    public let componentOrder: [String]
    public let units: String
    public let apMicrometres: Double
    public let mlMicrometres: Double
    public let dvMicrometres: Double

    public init(frameId: String, ap: Double, ml: Double, dv: Double) {
        self.frameId = frameId
        componentOrder = ["AP", "ML", "DV"]
        units = "micrometre"
        apMicrometres = ap
        mlMicrometres = ml
        dvMicrometres = dv
    }
}

public struct CalibrationAtlasPoint: Codable, Equatable, Sendable {
    public let frameId: String
    public let atlasIdentifier: String
    public let atlasVersion: String
    public let componentOrder: [String]
    public let units: String
    public let apMicrometres: Double
    public let dvMicrometres: Double
    public let mlMicrometres: Double

    public init(ap: Double, dv: Double, ml: Double) {
        frameId = CalibrationValidator.atlasPhysicalFrameId
        atlasIdentifier = SafetyPolicy.supportedAtlasIdentifier
        atlasVersion = SafetyPolicy.supportedAtlasVersion
        componentOrder = ["AP", "DV", "ML"]
        units = "micrometre"
        apMicrometres = ap
        dvMicrometres = dv
        mlMicrometres = ml
    }
}

public struct CalibrationSkullLandmarks: Codable, Equatable, Sendable {
    public let bregma: CalibrationSkullPoint
    public let lambdaPoint: CalibrationSkullPoint
    public let leftSkull: CalibrationSkullPoint
    public let rightSkull: CalibrationSkullPoint
    public let reportedBregmaLambdaDistanceMicrometres: Double
    public let lateralityConfirmedFromAnimal: Bool

    public init(
        bregma: CalibrationSkullPoint,
        lambdaPoint: CalibrationSkullPoint,
        leftSkull: CalibrationSkullPoint,
        rightSkull: CalibrationSkullPoint,
        reportedBregmaLambdaDistanceMicrometres: Double,
        lateralityConfirmedFromAnimal: Bool
    ) {
        self.bregma = bregma
        self.lambdaPoint = lambdaPoint
        self.leftSkull = leftSkull
        self.rightSkull = rightSkull
        self.reportedBregmaLambdaDistanceMicrometres =
            reportedBregmaLambdaDistanceMicrometres
        self.lateralityConfirmedFromAnimal = lateralityConfirmedFromAnimal
    }
}

public struct CalibrationAtlasLandmarks: Codable, Equatable, Sendable {
    public let bregma: CalibrationAtlasPoint
    public let lambdaPoint: CalibrationAtlasPoint
    public let leftSkull: CalibrationAtlasPoint
    public let rightSkull: CalibrationAtlasPoint

    public init(
        bregma: CalibrationAtlasPoint,
        lambdaPoint: CalibrationAtlasPoint,
        leftSkull: CalibrationAtlasPoint,
        rightSkull: CalibrationAtlasPoint
    ) {
        self.bregma = bregma
        self.lambdaPoint = lambdaPoint
        self.leftSkull = leftSkull
        self.rightSkull = rightSkull
    }
}

public struct CalibrationQualityLimits: Codable, Equatable, Sendable {
    public let minimumAxisBaselineMicrometres: Double
    public let distanceWarningMicrometres: Double
    public let distanceFailureMicrometres: Double
    public let lateralApWarningMicrometres: Double
    public let lateralApFailureMicrometres: Double
    public let transformRmsWarningMicrometres: Double
    public let transformRmsFailureMicrometres: Double

    public init(
        minimumAxisBaselineMicrometres: Double,
        distanceWarningMicrometres: Double,
        distanceFailureMicrometres: Double,
        lateralApWarningMicrometres: Double,
        lateralApFailureMicrometres: Double,
        transformRmsWarningMicrometres: Double,
        transformRmsFailureMicrometres: Double
    ) {
        self.minimumAxisBaselineMicrometres = minimumAxisBaselineMicrometres
        self.distanceWarningMicrometres = distanceWarningMicrometres
        self.distanceFailureMicrometres = distanceFailureMicrometres
        self.lateralApWarningMicrometres = lateralApWarningMicrometres
        self.lateralApFailureMicrometres = lateralApFailureMicrometres
        self.transformRmsWarningMicrometres = transformRmsWarningMicrometres
        self.transformRmsFailureMicrometres = transformRmsFailureMicrometres
    }
}

public struct CalibrationCreateParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let profileId: String
    public let sourceFrame: CalibrationSourceFrame
    public let skullLandmarks: CalibrationSkullLandmarks
    public let atlasLandmarks: CalibrationAtlasLandmarks
    public let qualityLimits: CalibrationQualityLimits
    public let dvReference: CalibrationDVReference
    public let dvReferenceDescription: String
    public let limitsSource: String
    public let atlasTransformMethod: CalibrationTransformMethod
    public let affineDistortionAcknowledged: Bool
    public let notes: String?

    public init(
        projectId: String,
        expectedProjectRevision: Int,
        profileId: String,
        sourceFrame: CalibrationSourceFrame,
        skullLandmarks: CalibrationSkullLandmarks,
        atlasLandmarks: CalibrationAtlasLandmarks,
        qualityLimits: CalibrationQualityLimits,
        dvReferenceDescription: String,
        limitsSource: String,
        atlasTransformMethod: CalibrationTransformMethod = .rigid,
        affineDistortionAcknowledged: Bool = false,
        notes: String? = nil
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.expectedProjectRevision = expectedProjectRevision
        self.profileId = profileId
        self.sourceFrame = sourceFrame
        self.skullLandmarks = skullLandmarks
        self.atlasLandmarks = atlasLandmarks
        self.qualityLimits = qualityLimits
        dvReference = .bregma
        self.dvReferenceDescription = dvReferenceDescription
        self.limitsSource = limitsSource
        self.atlasTransformMethod = atlasTransformMethod
        self.affineDistortionAcknowledged = affineDistortionAcknowledged
        self.notes = notes
    }
}

public struct CalibrationSummary: Codable, Equatable, Identifiable, Sendable {
    public let calibrationId: String
    public let schemaVersion: Int
    public let calibrationVersion: Int
    public let profileId: String
    public let mode: String
    public let quality: String
    public let permitsPlanning: Bool
    public let permitsFinalExport: Bool
    public let active: Bool
    public let skullQuality: String
    public let skullRmsResidualMicrometres: Double
    public let atlasRmsResidualMicrometres: Double
    public let atlasMaximumResidualMicrometres: Double
    public let atlasTransformMethod: String
    public let atlasMetadataSha256: String
    public let calibrationSha256: String
    public let qcMessages: [String]

    public var id: String { calibrationId }
}

public struct CalibrationListResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let activeCalibrationId: String?
    public let calibrationCount: Int
    public let calibrations: [CalibrationSummary]
}

public struct CalibrationGetResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let calibration: CalibrationSummary
}

public struct CalibrationMutationResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let activeCalibrationId: String?
    public let calibration: CalibrationSummary
}

public struct CalibrationValidationResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let calibration: CalibrationSummary
    public let storedLandmarksReproduced: Bool
}

public struct CalibrationRemoveResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let activeCalibrationId: String?
    public let calibrationId: String
    public let activeCalibrationCleared: Bool
    public let legacyTargetsPreserved: Bool
}

public struct CalibrationProjectedAnatomicalPoint: Codable, Equatable, Sendable {
    public let frameId: String
    public let componentOrder: [String]
    public let units: String
    public let apMicrometres: Double
    public let mlMicrometres: Double
    public let dvMicrometres: Double
}

public struct CalibrationProjectedAtlasPoint: Codable, Equatable, Sendable {
    public let frameId: String
    public let atlasIdentifier: String
    public let atlasVersion: String
    public let componentOrder: [String]
    public let units: String
    public let apMicrometres: Double
    public let dvMicrometres: Double
    public let mlMicrometres: Double
}

public struct CalibrationVoxelIndex: Codable, Equatable, Sendable {
    public let frameId: String
    public let componentOrder: [String]
    public let ap: Int
    public let dv: Int
    public let ml: Int
}

public struct CalibrationProjectionProvenance: Codable, Equatable, Sendable {
    public let calibrationId: String
    public let calibrationSchemaVersion: Int
    public let calibrationVersion: Int
    public let calibrationSha256: String
    public let atlasTransformId: String
    public let atlasTransformVersion: Int
    public let atlasTransformMethod: String
    public let atlasMetadataSha256: String
    public let projectionAlgorithm: String
    public let projectionSha256: String
}

public struct CalibrationTargetCoordinateSemantics: Codable, Equatable, Sendable {
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
}

public struct CalibratedTargetProjectionResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let projectId: String
    public let projectRevision: Int
    public let targetId: String
    public let sourceTargetPreserved: Bool
    public let projectionPersisted: Bool
    public let usableForPlanning: Bool
    public let usableForNavigation: Bool
    public let stereotaxicPoint: CalibrationProjectedAnatomicalPoint
    public let atlasPoint: CalibrationProjectedAtlasPoint
    public let containingVoxelIndex: CalibrationVoxelIndex
    public let provenance: CalibrationProjectionProvenance
    public let coordinateSemantics: CalibrationTargetCoordinateSemantics
    public let warning: String
}

public enum CalibrationValidationError: Error, Equatable, LocalizedError, Sendable {
    case malformedIdentifier(String)
    case malformedDigest(String)
    case invalidCreateInput(String)
    case protocolMismatch(Int)
    case unexpectedStatus(String)
    case projectMismatch
    case revisionMismatch
    case malformedCalibration
    case inconsistentCalibrationList
    case unsafeProjection
    case coordinateContractMismatch
    case projectionProvenanceMismatch

    public var errorDescription: String? {
        switch self {
        case let .malformedIdentifier(field): "\(field) is not a UUID."
        case let .malformedDigest(field): "\(field) is not a lowercase SHA-256 digest."
        case let .invalidCreateInput(message): message
        case let .protocolMismatch(version):
            "Calibration response uses protocol \(version); expected \(BridgeProtocolVersion.current)."
        case let .unexpectedStatus(status): "Unexpected calibration status ‘\(status)’."
        case .projectMismatch: "Calibration response belongs to a different project."
        case .revisionMismatch: "Calibration response contains an invalid project revision."
        case .malformedCalibration: "Calibration response contains invalid QC or transform data."
        case .inconsistentCalibrationList: "Calibration list and active selection are inconsistent."
        case .unsafeProjection: "Target projection did not remain read-only, planning-only output."
        case .coordinateContractMismatch: "Target projection changed the reviewed coordinate contract."
        case .projectionProvenanceMismatch: "Target projection provenance is incomplete or inconsistent."
        }
    }
}

public enum CalibrationValidator {
    public static let atlasPhysicalFrameId = "BRAINGLOBE_PHYSICAL_ASR_UM"
    public static let targetFrameId = "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"
    public static let projectionAlgorithm = "bregma-target-through-subject-atlas-calibration-v1"

    public static func validateCreate(_ request: CalibrationCreateParameters) throws {
        try uuid(request.projectId, field: "projectId")
        guard request.expectedProjectRevision >= 0 else {
            throw CalibrationValidationError.invalidCreateInput(
                "Expected project revision cannot be negative."
            )
        }
        try nonempty(request.profileId, field: "Profile ID")
        let frame = request.sourceFrame
        try nonempty(frame.frameId, field: "Source frame ID")
        try nonempty(frame.originDescription, field: "Source frame origin")
        try nonempty(frame.apPositiveDirection, field: "AP positive direction")
        try nonempty(frame.mlPositiveDirection, field: "ML positive direction")
        try nonempty(frame.dvPositiveDirection, field: "DV positive direction")
        guard frame.kind == "skull", frame.componentOrder == ["AP", "ML", "DV"],
              frame.units == "micrometre"
        else { throw CalibrationValidationError.coordinateContractMismatch }

        let skull = request.skullLandmarks
        for point in [skull.bregma, skull.lambdaPoint, skull.leftSkull, skull.rightSkull] {
            guard point.frameId == frame.frameId,
                  point.componentOrder == ["AP", "ML", "DV"], point.units == "micrometre",
                  finite(point.apMicrometres, point.mlMicrometres, point.dvMicrometres)
            else { throw CalibrationValidationError.coordinateContractMismatch }
        }
        guard skull.reportedBregmaLambdaDistanceMicrometres.isFinite,
              skull.reportedBregmaLambdaDistanceMicrometres > 0,
              skull.lateralityConfirmedFromAnimal
        else {
            throw CalibrationValidationError.invalidCreateInput(
                "Bregma–lambda distance must be positive and laterality must be confirmed from the animal."
            )
        }

        let atlas = request.atlasLandmarks
        for point in [atlas.bregma, atlas.lambdaPoint, atlas.leftSkull, atlas.rightSkull] {
            guard point.frameId == atlasPhysicalFrameId,
                  point.atlasIdentifier == SafetyPolicy.supportedAtlasIdentifier,
                  point.atlasVersion == SafetyPolicy.supportedAtlasVersion,
                  point.componentOrder == ["AP", "DV", "ML"], point.units == "micrometre",
                  finite(point.apMicrometres, point.dvMicrometres, point.mlMicrometres)
            else { throw CalibrationValidationError.coordinateContractMismatch }
        }
        guard atlas.bregma.apMicrometres < atlas.lambdaPoint.apMicrometres else {
            throw CalibrationValidationError.invalidCreateInput(
                "Atlas bregma must be anterior to atlas lambda in BrainGlobe AP coordinates."
            )
        }
        guard atlas.rightSkull.mlMicrometres < atlas.leftSkull.mlMicrometres else {
            throw CalibrationValidationError.invalidCreateInput(
                "Atlas left/right landmarks do not match BrainGlobe ASR laterality."
            )
        }
        let limits = request.qualityLimits
        let values = [
            limits.minimumAxisBaselineMicrometres,
            limits.distanceWarningMicrometres,
            limits.distanceFailureMicrometres,
            limits.lateralApWarningMicrometres,
            limits.lateralApFailureMicrometres,
            limits.transformRmsWarningMicrometres,
            limits.transformRmsFailureMicrometres,
        ]
        guard values.allSatisfy({ $0.isFinite && $0 > 0 }),
              limits.distanceWarningMicrometres < limits.distanceFailureMicrometres,
              limits.lateralApWarningMicrometres < limits.lateralApFailureMicrometres,
              limits.transformRmsWarningMicrometres < limits.transformRmsFailureMicrometres
        else {
            throw CalibrationValidationError.invalidCreateInput(
                "QC limits must be positive, with each warning limit below its failure limit."
            )
        }
        try nonempty(request.dvReferenceDescription, field: "DV reference description")
        try nonempty(request.limitsSource, field: "QC limits source")
        if request.atlasTransformMethod == .affine && !request.affineDistortionAcknowledged {
            throw CalibrationValidationError.invalidCreateInput(
                "Affine calibration requires explicit distortion acknowledgement."
            )
        }
    }

    public static func validateList(_ result: CalibrationListResult, projectId: String) throws {
        try envelope(result.protocolVersion, result.status, expected: "listed",
                     result.projectId, projectId, revision: result.projectRevision)
        guard result.calibrationCount == result.calibrations.count else {
            throw CalibrationValidationError.inconsistentCalibrationList
        }
        var identifiers = Set<String>()
        for item in result.calibrations {
            try validate(item)
            guard identifiers.insert(item.calibrationId).inserted else {
                throw CalibrationValidationError.inconsistentCalibrationList
            }
        }
        let active = result.calibrations.filter(\.active)
        if let activeId = result.activeCalibrationId {
            try uuid(activeId, field: "activeCalibrationId")
            guard active.count == 1, active[0].calibrationId == activeId else {
                throw CalibrationValidationError.inconsistentCalibrationList
            }
        } else if !active.isEmpty {
            throw CalibrationValidationError.inconsistentCalibrationList
        }
    }

    public static func validateGet(_ result: CalibrationGetResult, projectId: String,
                                   calibrationId: String) throws {
        try envelope(result.protocolVersion, result.status, expected: "found",
                     result.projectId, projectId, revision: result.projectRevision)
        try validate(result.calibration)
        guard result.calibration.calibrationId == calibrationId else {
            throw CalibrationValidationError.inconsistentCalibrationList
        }
    }

    public static func validateMutation(
        _ result: CalibrationMutationResult,
        projectId: String,
        expectedStatus: String,
        expectedRevision: Int
    ) throws {
        try envelope(result.protocolVersion, result.status, expected: expectedStatus,
                     result.projectId, projectId, revision: result.projectRevision)
        guard result.projectRevision == expectedRevision else {
            throw CalibrationValidationError.revisionMismatch
        }
        try validate(result.calibration)
        if expectedStatus == "activeCalibrationSet" {
            guard result.calibration.active,
                  result.activeCalibrationId == result.calibration.calibrationId
            else { throw CalibrationValidationError.inconsistentCalibrationList }
        }
    }

    public static func validateValidation(_ result: CalibrationValidationResult,
                                          projectId: String,
                                          calibrationId: String) throws {
        try envelope(result.protocolVersion, result.status, expected: "validated",
                     result.projectId, projectId, revision: result.projectRevision)
        try validate(result.calibration)
        guard result.calibration.calibrationId == calibrationId,
              result.storedLandmarksReproduced
        else { throw CalibrationValidationError.malformedCalibration }
    }

    public static func validateRemove(_ result: CalibrationRemoveResult,
                                      projectId: String,
                                      calibrationId: String,
                                      expectedRevision: Int) throws {
        try envelope(result.protocolVersion, result.status, expected: "removed",
                     result.projectId, projectId, revision: result.projectRevision)
        try uuid(result.calibrationId, field: "calibrationId")
        guard result.calibrationId == calibrationId,
              result.projectRevision == expectedRevision,
              result.legacyTargetsPreserved,
              !result.activeCalibrationCleared || result.activeCalibrationId == nil
        else { throw CalibrationValidationError.inconsistentCalibrationList }
    }

    public static func validateProjection(_ result: CalibratedTargetProjectionResult,
                                          projectId: String,
                                          targetId: String,
                                          activeCalibrationId: String) throws {
        try envelope(result.protocolVersion, result.status, expected: "projectedReadOnly",
                     result.projectId, projectId, revision: result.projectRevision)
        try uuid(result.targetId, field: "targetId")
        guard result.targetId == targetId,
              result.sourceTargetPreserved, !result.projectionPersisted,
              result.usableForPlanning, !result.usableForNavigation,
              !result.warning.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { throw CalibrationValidationError.unsafeProjection }
        let stereo = result.stereotaxicPoint
        guard !stereo.frameId.isEmpty, stereo.componentOrder == ["AP", "ML", "DV"],
              stereo.units == "micrometre",
              finite(stereo.apMicrometres, stereo.mlMicrometres, stereo.dvMicrometres)
        else { throw CalibrationValidationError.coordinateContractMismatch }
        let atlas = result.atlasPoint
        guard atlas.frameId == atlasPhysicalFrameId,
              atlas.atlasIdentifier == SafetyPolicy.supportedAtlasIdentifier,
              atlas.atlasVersion == SafetyPolicy.supportedAtlasVersion,
              atlas.componentOrder == ["AP", "DV", "ML"], atlas.units == "micrometre",
              finite(atlas.apMicrometres, atlas.dvMicrometres, atlas.mlMicrometres)
        else { throw CalibrationValidationError.coordinateContractMismatch }
        let voxel = result.containingVoxelIndex
        guard voxel.frameId == "BRAINGLOBE_VOXEL_INDEX_ASR",
              voxel.componentOrder == ["AP", "DV", "ML"],
              voxel.ap >= 0, voxel.dv >= 0, voxel.ml >= 0
        else { throw CalibrationValidationError.coordinateContractMismatch }
        let semantics = result.coordinateSemantics
        guard semantics.frameId == targetFrameId, semantics.origin == "bregma",
              semantics.componentOrder == ["AP", "ML", "DV"], semantics.units == "millimetre",
              semantics.apPositiveDirection == "anterior",
              semantics.apNegativeDirection == "posterior/back",
              semantics.mlPositiveDirection == "right", semantics.mlNegativeDirection == "left",
              semantics.dvPositiveDirection == "dorsal/up",
              semantics.dvNegativeDirection == "deep/ventral"
        else { throw CalibrationValidationError.coordinateContractMismatch }
        let provenance = result.provenance
        try uuid(provenance.calibrationId, field: "provenance.calibrationId")
        try uuid(provenance.atlasTransformId, field: "provenance.atlasTransformId")
        try digest(provenance.calibrationSha256, field: "provenance.calibrationSha256")
        try digest(provenance.atlasMetadataSha256, field: "provenance.atlasMetadataSha256")
        try digest(provenance.projectionSha256, field: "provenance.projectionSha256")
        guard provenance.calibrationId == activeCalibrationId,
              provenance.calibrationSchemaVersion == 1,
              provenance.calibrationVersion > 0,
              provenance.atlasTransformVersion == provenance.calibrationVersion,
              ["rigid", "similarity", "affine"].contains(provenance.atlasTransformMethod),
              provenance.projectionAlgorithm == projectionAlgorithm
        else { throw CalibrationValidationError.projectionProvenanceMismatch }
    }

    public static func validate(_ summary: CalibrationSummary) throws {
        try uuid(summary.calibrationId, field: "calibrationId")
        try digest(summary.atlasMetadataSha256, field: "atlasMetadataSha256")
        try digest(summary.calibrationSha256, field: "calibrationSha256")
        let qualities = ["pass", "warning", "fail"]
        guard summary.schemaVersion == 1, summary.calibrationVersion > 0,
              !summary.profileId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              summary.mode == "subject-calibrated",
              qualities.contains(summary.quality), qualities.contains(summary.skullQuality),
              finite(summary.skullRmsResidualMicrometres,
                     summary.atlasRmsResidualMicrometres,
                     summary.atlasMaximumResidualMicrometres),
              summary.skullRmsResidualMicrometres >= 0,
              summary.atlasRmsResidualMicrometres >= 0,
              summary.atlasMaximumResidualMicrometres >= summary.atlasRmsResidualMicrometres,
              ["rigid", "similarity", "affine"].contains(summary.atlasTransformMethod),
              summary.qcMessages.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
              summary.quality != "fail" || (!summary.permitsPlanning && !summary.permitsFinalExport),
              !summary.active || summary.permitsPlanning
        else { throw CalibrationValidationError.malformedCalibration }
    }

    private static func envelope(_ version: Int, _ status: String, expected: String,
                                 _ actualProjectId: String, _ expectedProjectId: String,
                                 revision: Int) throws {
        guard version == BridgeProtocolVersion.current else {
            throw CalibrationValidationError.protocolMismatch(version)
        }
        guard status == expected else { throw CalibrationValidationError.unexpectedStatus(status) }
        try uuid(actualProjectId, field: "projectId")
        guard actualProjectId == expectedProjectId else {
            throw CalibrationValidationError.projectMismatch
        }
        guard revision >= 0 else { throw CalibrationValidationError.revisionMismatch }
    }

    private static func uuid(_ value: String, field: String) throws {
        guard UUID(uuidString: value) != nil else {
            throw CalibrationValidationError.malformedIdentifier(field)
        }
    }

    private static func digest(_ value: String, field: String) throws {
        guard value.count == 64,
              value.unicodeScalars.allSatisfy({ scalar in
                  (48...57).contains(scalar.value) || (97...102).contains(scalar.value)
              })
        else { throw CalibrationValidationError.malformedDigest(field) }
    }

    private static func nonempty(_ value: String, field: String) throws {
        guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw CalibrationValidationError.invalidCreateInput("\(field) cannot be blank.")
        }
    }

    private static func finite(_ values: Double...) -> Bool {
        values.allSatisfy(\.isFinite)
    }
}
