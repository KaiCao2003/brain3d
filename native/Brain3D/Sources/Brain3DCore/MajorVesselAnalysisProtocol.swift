import Foundation

public enum MajorVesselAnalysisContract {
    public static let algorithmVersion = "major-vessel-aabb-tapered-surface-v3"
    public static let noConflictStatement =
        "No conflict detected within the loaded geometry and stated uncertainty assumptions."
    public static let maximumDistanceMicrometres = 10_000.0
    public static let maximumConflicts = 250
}

public struct MajorVesselAnalyzeParameters: Encodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let expectedProjectRevision: Int
    public let planId: String
    public let expectedPlanInputSha256: String
    public let requiredMarginMicrometres: Double
    public let registrationUncertaintyMicrometres: Double
    public let riskProfileConfirmed: Bool
    public let referenceCoverageAcknowledged: Bool
    public let maximumConflicts: Int

    public init(
        projectId: String,
        expectedProjectRevision: Int,
        planId: String,
        expectedPlanInputSha256: String,
        requiredMarginMicrometres: Double,
        registrationUncertaintyMicrometres: Double,
        riskProfileConfirmed: Bool,
        referenceCoverageAcknowledged: Bool,
        maximumConflicts: Int = 100
    ) throws {
        guard UUID(uuidString: projectId)?.uuidString.lowercased() == projectId.lowercased(),
              UUID(uuidString: planId)?.uuidString.lowercased() == planId.lowercased(),
              expectedProjectRevision >= 0,
              isClearanceSHA256(expectedPlanInputSha256),
              requiredMarginMicrometres.isFinite,
              requiredMarginMicrometres >= 0,
              requiredMarginMicrometres <= MajorVesselAnalysisContract.maximumDistanceMicrometres,
              registrationUncertaintyMicrometres.isFinite,
              registrationUncertaintyMicrometres >= 0,
              registrationUncertaintyMicrometres
                <= MajorVesselAnalysisContract.maximumDistanceMicrometres,
              (1 ... MajorVesselAnalysisContract.maximumConflicts).contains(maximumConflicts)
        else {
            throw MajorVesselContractError.invalid(
                "Major-vessel analysis inputs are incomplete or outside supported bounds."
            )
        }
        protocolVersion = BridgeProtocolVersion.current
        self.projectId = projectId
        self.expectedProjectRevision = expectedProjectRevision
        self.planId = planId
        self.expectedPlanInputSha256 = expectedPlanInputSha256
        self.requiredMarginMicrometres = requiredMarginMicrometres
        self.registrationUncertaintyMicrometres = registrationUncertaintyMicrometres
        self.riskProfileConfirmed = riskProfileConfirmed
        self.referenceCoverageAcknowledged = referenceCoverageAcknowledged
        self.maximumConflicts = maximumConflicts
    }
}

public enum MajorVesselConflictClassification: String, Decodable, Equatable, Sendable {
    case intersection
    case marginViolation
    case uncertaintyViolation
}

public enum MajorVesselResultStatus: String, Decodable, Equatable, Sendable {
    case intersection
    case marginViolation
    case uncertaintyViolation
    case noConflictDetected
    case insufficientGeometry
}

public struct MajorVesselRiskProfile: Decodable, Equatable, Sendable {
    public let profileId: String
    public let minimumVesselDiameterMicrometres: Double
    public let requiredMarginMicrometres: Double
    public let registrationUncertaintyMicrometres: Double
    public let sourceOrLabPolicy: String
    public let confirmedByUser: Bool
    public let referenceOnlyCoverageAcknowledged: Bool

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case profileId
        case minimumVesselDiameterMicrometres
        case requiredMarginMicrometres
        case registrationUncertaintyMicrometres
        case sourceOrLabPolicy
        case confirmedByUser
        case referenceOnlyCoverageAcknowledged
    }

    public init(from decoder: any Decoder) throws {
        try requireClearanceExactKeys(decoder, CodingKeys.self, label: "vessel risk profile")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        profileId = try container.decode(String.self, forKey: .profileId)
        minimumVesselDiameterMicrometres = try container.decode(
            Double.self,
            forKey: .minimumVesselDiameterMicrometres
        )
        requiredMarginMicrometres = try container.decode(
            Double.self,
            forKey: .requiredMarginMicrometres
        )
        registrationUncertaintyMicrometres = try container.decode(
            Double.self,
            forKey: .registrationUncertaintyMicrometres
        )
        sourceOrLabPolicy = try container.decode(String.self, forKey: .sourceOrLabPolicy)
        confirmedByUser = try container.decode(Bool.self, forKey: .confirmedByUser)
        referenceOnlyCoverageAcknowledged = try container.decode(
            Bool.self,
            forKey: .referenceOnlyCoverageAcknowledged
        )
        guard profileId == "vessap-bl6j-no1-major-30um-v1",
              minimumVesselDiameterMicrometres
                == MajorVesselContract.minimumIncludedDiameterMicrometres,
              [requiredMarginMicrometres, registrationUncertaintyMicrometres]
                .allSatisfy({
                    $0.isFinite && $0 >= 0
                        && $0 <= MajorVesselAnalysisContract.maximumDistanceMicrometres
                }),
              !sourceOrLabPolicy.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw MajorVesselContractError.invalid("Vessel risk profile is inconsistent.")
        }
    }
}

public struct MajorVesselPhysicalPoint: Decodable, Equatable, Sendable {
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
        try requireClearanceExactKeys(decoder, CodingKeys.self, label: "vessel analysis point")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        frameId = try container.decode(String.self, forKey: .frameId)
        apMicrometres = try container.decode(Double.self, forKey: .apMicrometres)
        dvMicrometres = try container.decode(Double.self, forKey: .dvMicrometres)
        mlMicrometres = try container.decode(Double.self, forKey: .mlMicrometres)
        guard frameId == AtlasPhysicalCoordinateFrame.expectedFrameId,
              [apMicrometres, dvMicrometres, mlMicrometres].allSatisfy(\.isFinite)
        else {
            throw MajorVesselContractError.invalid(
                "Vessel analysis point is not finite physical ASR geometry."
            )
        }
    }
}

public struct MajorVesselConflict: Decodable, Equatable, Identifiable, Sendable {
    public let conflictId: String
    public let shankId: String
    public let vesselSourceEdgeIndex: Int
    public let vesselRunIndex: Int
    public let vesselSegmentIndexInRun: Int
    public let classification: MajorVesselConflictClassification
    public let vesselDiameterMicrometres: Double
    public let probeEnvelopeRadiusMicrometres: Double
    public let centerlineDistanceMicrometres: Double
    public let geometricSurfaceClearanceMicrometres: Double
    public let requiredMarginMicrometres: Double
    public let registrationUncertaintyMicrometres: Double
    public let adjustedClearanceMicrometres: Double
    public let probePoint: MajorVesselPhysicalPoint
    public let vesselPoint: MajorVesselPhysicalPoint
    public let insertionDepthMicrometres: Double
    public let sourceKind: String
    public let subjectSpecific: Bool
    public let warnings: [String]

    public var id: String { conflictId }

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case conflictId
        case shankId
        case vesselSourceEdgeIndex
        case vesselRunIndex
        case vesselSegmentIndexInRun
        case classification
        case vesselDiameterMicrometres
        case probeEnvelopeRadiusMicrometres
        case centerlineDistanceMicrometres
        case geometricSurfaceClearanceMicrometres
        case requiredMarginMicrometres
        case registrationUncertaintyMicrometres
        case adjustedClearanceMicrometres
        case probePoint
        case vesselPoint
        case insertionDepthMicrometres
        case sourceKind
        case subjectSpecific
        case warnings
    }

    public init(from decoder: any Decoder) throws {
        try requireClearanceExactKeys(decoder, CodingKeys.self, label: "vessel conflict")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        conflictId = try container.decode(String.self, forKey: .conflictId)
        shankId = try container.decode(String.self, forKey: .shankId)
        vesselSourceEdgeIndex = try container.decode(Int.self, forKey: .vesselSourceEdgeIndex)
        vesselRunIndex = try container.decode(Int.self, forKey: .vesselRunIndex)
        vesselSegmentIndexInRun = try container.decode(
            Int.self,
            forKey: .vesselSegmentIndexInRun
        )
        classification = try container.decode(
            MajorVesselConflictClassification.self,
            forKey: .classification
        )
        vesselDiameterMicrometres = try container.decode(
            Double.self,
            forKey: .vesselDiameterMicrometres
        )
        probeEnvelopeRadiusMicrometres = try container.decode(
            Double.self,
            forKey: .probeEnvelopeRadiusMicrometres
        )
        centerlineDistanceMicrometres = try container.decode(
            Double.self,
            forKey: .centerlineDistanceMicrometres
        )
        geometricSurfaceClearanceMicrometres = try container.decode(
            Double.self,
            forKey: .geometricSurfaceClearanceMicrometres
        )
        requiredMarginMicrometres = try container.decode(
            Double.self,
            forKey: .requiredMarginMicrometres
        )
        registrationUncertaintyMicrometres = try container.decode(
            Double.self,
            forKey: .registrationUncertaintyMicrometres
        )
        adjustedClearanceMicrometres = try container.decode(
            Double.self,
            forKey: .adjustedClearanceMicrometres
        )
        probePoint = try container.decode(MajorVesselPhysicalPoint.self, forKey: .probePoint)
        vesselPoint = try container.decode(MajorVesselPhysicalPoint.self, forKey: .vesselPoint)
        insertionDepthMicrometres = try container.decode(
            Double.self,
            forKey: .insertionDepthMicrometres
        )
        sourceKind = try container.decode(String.self, forKey: .sourceKind)
        subjectSpecific = try container.decode(Bool.self, forKey: .subjectSpecific)
        warnings = try container.decode([String].self, forKey: .warnings)
        let finiteValues = [
            vesselDiameterMicrometres,
            probeEnvelopeRadiusMicrometres,
            centerlineDistanceMicrometres,
            geometricSurfaceClearanceMicrometres,
            requiredMarginMicrometres,
            registrationUncertaintyMicrometres,
            adjustedClearanceMicrometres,
            insertionDepthMicrometres,
        ]
        guard !conflictId.isEmpty,
              !shankId.isEmpty,
              vesselSourceEdgeIndex >= 0,
              vesselRunIndex >= 0,
              vesselSegmentIndexInRun >= 0,
              finiteValues.allSatisfy(\.isFinite),
              vesselDiameterMicrometres >= MajorVesselContract.minimumIncludedDiameterMicrometres,
              probeEnvelopeRadiusMicrometres > 0,
              centerlineDistanceMicrometres >= 0,
              requiredMarginMicrometres >= 0,
              registrationUncertaintyMicrometres >= 0,
              insertionDepthMicrometres >= 0,
              sourceKind == "reference-individual-vessel-graph",
              !subjectSpecific,
              !warnings.isEmpty
        else {
            throw MajorVesselContractError.invalid("Vessel conflict metadata is inconsistent.")
        }
    }
}

public struct MajorVesselClearanceAnalysis: Decodable, Equatable, Sendable {
    public let algorithmVersion: String
    public let inputSha256: String
    public let resultStatus: MajorVesselResultStatus
    public let statement: String
    public let nearestCenterlineDistanceMicrometres: Double?
    public let minimumGeometricClearanceMicrometres: Double?
    public let minimumAdjustedClearanceMicrometres: Double?
    public let candidateSegmentCount: Int
    public let measuredSegmentCount: Int
    public let conflicts: [MajorVesselConflict]
    public let conflictsTruncated: Bool
    public let riskProfile: MajorVesselRiskProfile
    public let provenance: MajorVesselSourceProvenance
    public let warnings: [String]
    public let usableForNavigation: Bool

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case algorithmVersion
        case inputSha256
        case resultStatus
        case statement
        case nearestCenterlineDistanceMicrometres
        case minimumGeometricClearanceMicrometres
        case minimumAdjustedClearanceMicrometres
        case candidateSegmentCount
        case measuredSegmentCount
        case conflicts
        case conflictsTruncated
        case riskProfile
        case provenance
        case warnings
        case usableForNavigation
    }

    public init(from decoder: any Decoder) throws {
        try requireClearanceExactKeys(decoder, CodingKeys.self, label: "vessel analysis")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        algorithmVersion = try container.decode(String.self, forKey: .algorithmVersion)
        inputSha256 = try container.decode(String.self, forKey: .inputSha256)
        resultStatus = try container.decode(MajorVesselResultStatus.self, forKey: .resultStatus)
        statement = try container.decode(String.self, forKey: .statement)
        nearestCenterlineDistanceMicrometres = try container.decodeIfPresent(
            Double.self,
            forKey: .nearestCenterlineDistanceMicrometres
        )
        minimumGeometricClearanceMicrometres = try container.decodeIfPresent(
            Double.self,
            forKey: .minimumGeometricClearanceMicrometres
        )
        minimumAdjustedClearanceMicrometres = try container.decodeIfPresent(
            Double.self,
            forKey: .minimumAdjustedClearanceMicrometres
        )
        candidateSegmentCount = try container.decode(Int.self, forKey: .candidateSegmentCount)
        measuredSegmentCount = try container.decode(Int.self, forKey: .measuredSegmentCount)
        conflicts = try container.decode([MajorVesselConflict].self, forKey: .conflicts)
        conflictsTruncated = try container.decode(Bool.self, forKey: .conflictsTruncated)
        riskProfile = try container.decode(MajorVesselRiskProfile.self, forKey: .riskProfile)
        provenance = try container.decode(MajorVesselSourceProvenance.self, forKey: .provenance)
        warnings = try container.decode([String].self, forKey: .warnings)
        usableForNavigation = try container.decode(Bool.self, forKey: .usableForNavigation)
        let optionalDistances = [
            nearestCenterlineDistanceMicrometres,
            minimumGeometricClearanceMicrometres,
            minimumAdjustedClearanceMicrometres,
        ].compactMap { $0 }
        guard algorithmVersion == MajorVesselAnalysisContract.algorithmVersion,
              isClearanceSHA256(inputSha256),
              !statement.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !statement.localizedCaseInsensitiveContains("safe"),
              optionalDistances.count == 3,
              optionalDistances.allSatisfy(\.isFinite),
              nearestCenterlineDistanceMicrometres.map({ $0 >= 0 }) == true,
              candidateSegmentCount > 0,
              measuredSegmentCount == candidateSegmentCount,
              conflicts.count <= MajorVesselAnalysisContract.maximumConflicts,
              !warnings.isEmpty,
              !usableForNavigation
        else {
            throw MajorVesselContractError.invalid("Vessel analysis metadata is inconsistent.")
        }
        switch resultStatus {
        case .insufficientGeometry:
            guard conflicts.isEmpty else {
                throw MajorVesselContractError.invalid(
                    "An unclassified vessel analysis cannot publish conflicts."
                )
            }
        case .noConflictDetected:
            let reviewedSourceBound = reviewedSourceUncertaintyBound
            guard riskProfile.confirmedByUser,
                  riskProfile.referenceOnlyCoverageAcknowledged,
                  conflicts.isEmpty,
                  !conflictsTruncated,
                  statement == MajorVesselAnalysisContract.noConflictStatement,
                  reviewedSourceBound != nil,
                  riskProfile.registrationUncertaintyMicrometres + 1e-6
                    >= (reviewedSourceBound ?? .infinity),
                  minimumAdjustedClearanceMicrometres.map({ $0 > 1e-6 }) == true
            else {
                throw MajorVesselContractError.invalid(
                    "No-conflict vessel result is not bounded by the required contract."
                )
            }
        case .intersection, .marginViolation, .uncertaintyViolation:
            guard riskProfile.confirmedByUser,
                  riskProfile.referenceOnlyCoverageAcknowledged,
                  !conflicts.isEmpty,
                  minimumAdjustedClearanceMicrometres.map({ $0 <= 1e-6 }) == true
            else {
                throw MajorVesselContractError.invalid(
                    "Classified vessel result requires acknowledged inputs and conflicts."
                )
            }
        }
        try validateNumericalIdentities()
    }

    private var reviewedSourceUncertaintyBound: Double? {
        guard provenance.uncertaintyBoundsReviewed,
              provenance.registrationTransformId != nil,
              let registration = provenance.registrationUncertaintyBoundMicrometres,
              let distortion = provenance.tissueDistortionUncertaintyBoundMicrometres,
              registration.isFinite, registration >= 0,
              distortion.isFinite, distortion >= 0
        else { return nil }
        return registration + distortion
    }

    private func validateNumericalIdentities() throws {
        guard let minimumGeometricClearanceMicrometres,
              let minimumAdjustedClearanceMicrometres,
              approximatelyEqual(
                  minimumAdjustedClearanceMicrometres,
                  minimumGeometricClearanceMicrometres
                    - riskProfile.requiredMarginMicrometres
                    - riskProfile.registrationUncertaintyMicrometres
              )
        else {
            throw MajorVesselContractError.invalid(
                "Vessel-analysis minimum clearance values are inconsistent."
            )
        }

        for conflict in conflicts {
            let dx = conflict.probePoint.apMicrometres - conflict.vesselPoint.apMicrometres
            let dy = conflict.probePoint.dvMicrometres - conflict.vesselPoint.dvMicrometres
            let dz = conflict.probePoint.mlMicrometres - conflict.vesselPoint.mlMicrometres
            let pointDistance = (dx * dx + dy * dy + dz * dz).squareRoot()
            let expectedGeometric = conflict.centerlineDistanceMicrometres
                - conflict.vesselDiameterMicrometres / 2
                - conflict.probeEnvelopeRadiusMicrometres
            let expectedAdjusted = expectedGeometric
                - conflict.requiredMarginMicrometres
                - conflict.registrationUncertaintyMicrometres
            guard approximatelyEqual(pointDistance, conflict.centerlineDistanceMicrometres),
                  approximatelyEqual(
                      conflict.requiredMarginMicrometres,
                      riskProfile.requiredMarginMicrometres
                  ),
                  approximatelyEqual(
                      conflict.registrationUncertaintyMicrometres,
                      riskProfile.registrationUncertaintyMicrometres
                  ),
                  approximatelyEqual(
                      conflict.geometricSurfaceClearanceMicrometres,
                      expectedGeometric
                  ),
                  approximatelyEqual(conflict.adjustedClearanceMicrometres, expectedAdjusted),
                  conflict.adjustedClearanceMicrometres <= 1e-6,
                  conflict.adjustedClearanceMicrometres
                    >= minimumAdjustedClearanceMicrometres - 1e-6,
                  classificationMatchesGeometry(conflict)
            else {
                throw MajorVesselContractError.invalid(
                    "Vessel-conflict distances, thresholds, or classification are inconsistent."
                )
            }
        }

        if let first = conflicts.first {
            guard approximatelyEqual(
                first.adjustedClearanceMicrometres,
                minimumAdjustedClearanceMicrometres
            ) else {
                throw MajorVesselContractError.invalid(
                    "Vessel conflicts are not ordered from the global minimum clearance."
                )
            }
            let expectedStatus: MajorVesselResultStatus
            if conflicts.contains(where: { $0.classification == .intersection }) {
                expectedStatus = .intersection
            } else if conflicts.contains(where: { $0.classification == .marginViolation }) {
                expectedStatus = .marginViolation
            } else {
                expectedStatus = .uncertaintyViolation
            }
            guard resultStatus == expectedStatus else {
                throw MajorVesselContractError.invalid(
                    "Overall vessel status does not match the published conflicts."
                )
            }
        }
    }

    private func classificationMatchesGeometry(_ conflict: MajorVesselConflict) -> Bool {
        let geometric = conflict.geometricSurfaceClearanceMicrometres
        let afterMargin = geometric - conflict.requiredMarginMicrometres
        switch conflict.classification {
        case .intersection:
            return geometric <= 1e-6
        case .marginViolation:
            return geometric > 1e-6 && afterMargin <= 1e-6
        case .uncertaintyViolation:
            return afterMargin > 1e-6 && conflict.adjustedClearanceMicrometres <= 1e-6
        }
    }

    private func approximatelyEqual(_ lhs: Double, _ rhs: Double) -> Bool {
        abs(lhs - rhs) <= max(1e-6, max(abs(lhs), abs(rhs)) * 1e-10)
    }
}

public struct MajorVesselAnalysisResult: Decodable, Equatable, Sendable {
    public let protocolVersion: Int
    public let projectId: String
    public let projectRevision: Int
    public let planId: String
    public let planVersion: Int
    public let planInputSha256: String
    public let analysis: MajorVesselClearanceAnalysis
    public let limitations: [String]

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case protocolVersion
        case projectId
        case projectRevision
        case planId
        case planVersion
        case planInputSha256
        case analysis
        case limitations
    }

    public init(from decoder: any Decoder) throws {
        try requireClearanceExactKeys(decoder, CodingKeys.self, label: "vessel analysis result")
        let container = try decoder.container(keyedBy: CodingKeys.self)
        protocolVersion = try container.decode(Int.self, forKey: .protocolVersion)
        projectId = try container.decode(String.self, forKey: .projectId)
        projectRevision = try container.decode(Int.self, forKey: .projectRevision)
        planId = try container.decode(String.self, forKey: .planId)
        planVersion = try container.decode(Int.self, forKey: .planVersion)
        planInputSha256 = try container.decode(String.self, forKey: .planInputSha256)
        analysis = try container.decode(MajorVesselClearanceAnalysis.self, forKey: .analysis)
        limitations = try container.decode([String].self, forKey: .limitations)
        guard protocolVersion == BridgeProtocolVersion.current,
              UUID(uuidString: projectId) != nil,
              UUID(uuidString: planId) != nil,
              projectRevision >= 0,
              planVersion > 0,
              isClearanceSHA256(planInputSha256),
              !limitations.isEmpty,
              limitations.contains(where: { $0.localizedCaseInsensitiveContains("pial") }),
              analysis.provenance.derivedAssetSha256
                == MajorVesselContract.derivedAssetSHA256
        else {
            throw MajorVesselContractError.invalid(
                "Vessel analysis result identity or limitations are inconsistent."
            )
        }
    }
}

public enum MajorVesselAnalysisValidator {
    public static func validateCurrent(
        _ result: MajorVesselAnalysisResult,
        projectId: String,
        projectRevision: Int,
        planId: String,
        planVersion: Int,
        planInputSha256: String
    ) throws {
        guard result.projectId == projectId,
              result.projectRevision == projectRevision,
              result.planId == planId,
              result.planVersion == planVersion,
              result.planInputSha256 == planInputSha256,
              result.analysis.provenance.derivedAssetSha256
                == MajorVesselContract.derivedAssetSHA256
        else {
            throw MajorVesselContractError.invalid(
                "Vessel analysis is stale or belongs to another project, plan, or vessel asset."
            )
        }
    }
}

private func requireClearanceExactKeys<Keys: CodingKey & CaseIterable>(
    _ decoder: any Decoder,
    _ keyType: Keys.Type,
    label: String
) throws {
    let dynamic = try decoder.container(keyedBy: ClearanceDynamicCodingKey.self)
    let actual = Set(dynamic.allKeys.map(\.stringValue))
    let expected = Set(Keys.allCases.map(\.stringValue))
    guard actual == expected else {
        throw MajorVesselContractError.invalid("\(label) keys do not match protocol v1 exactly.")
    }
}

private struct ClearanceDynamicCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int? = nil

    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}

private func isClearanceSHA256(_ value: String) -> Bool {
    value.utf8.count == 64 && value.utf8.allSatisfy {
        ($0 >= 48 && $0 <= 57) || ($0 >= 97 && $0 <= 102)
    }
}
