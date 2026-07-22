import Foundation

public enum BregmaCoordinateInputError: Error, Equatable, LocalizedError, Sendable {
    case invalidDecimal(axis: String)
    case outsideFiniteRange(axis: String)

    public var errorDescription: String? {
        switch self {
        case let .invalidDecimal(axis):
            "\(axis) must be a plain decimal number in millimetres."
        case let .outsideFiniteRange(axis):
            "\(axis) is outside the finite numeric range."
        }
    }
}

public struct ParsedBregmaCoordinates: Equatable, Sendable {
    public let apMillimetres: Double
    public let mlMillimetres: Double
    public let dvMillimetres: Double
}

public enum BregmaCoordinateInput {
    private static let decimalPattern = #"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$"#

    public static func parse(_ text: String, axis: String) throws -> Double {
        let normalized = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard
            !normalized.isEmpty,
            normalized.range(of: decimalPattern, options: .regularExpression) != nil,
            let value = Double(normalized)
        else {
            throw BregmaCoordinateInputError.invalidDecimal(axis: axis)
        }
        guard value.isFinite else {
            throw BregmaCoordinateInputError.outsideFiniteRange(axis: axis)
        }
        return value == 0 ? 0 : value
    }

    public static func parse(ap: String, ml: String, dv: String) throws
        -> ParsedBregmaCoordinates
    {
        ParsedBregmaCoordinates(
            apMillimetres: try parse(ap, axis: "AP"),
            mlMillimetres: try parse(ml, axis: "ML"),
            dvMillimetres: try parse(dv, axis: "DV")
        )
    }
}

public struct ImplantListParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int

    public init() {
        protocolVersion = BridgeProtocolVersion.current
    }
}

public struct ImplantAddParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let label: String
    public let apMillimetres: Double
    public let mlMillimetres: Double
    public let dvMillimetres: Double
    public let notes: String?

    public init(
        label: String,
        apMillimetres: Double,
        mlMillimetres: Double,
        dvMillimetres: Double,
        notes: String? = nil
    ) {
        protocolVersion = BridgeProtocolVersion.current
        self.label = label
        self.apMillimetres = apMillimetres
        self.mlMillimetres = mlMillimetres
        self.dvMillimetres = dvMillimetres
        self.notes = notes
    }
}

public struct ImplantRemoveParameters: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let targetId: String

    public init(targetId: String) {
        protocolVersion = BridgeProtocolVersion.current
        self.targetId = targetId
    }
}

public struct BregmaSignConvention: Codable, Equatable, Sendable {
    public let apPositive: String
    public let apNegative: String
    public let mlPositive: String
    public let mlNegative: String
    public let dvPositive: String
    public let dvNegative: String
}

public struct BregmaCoordinateFrame: Codable, Equatable, Sendable {
    public let frameId: String
    public let origin: String
    public let componentOrder: [String]
    public let units: String
    public let signConvention: BregmaSignConvention
}

public struct UnprojectedImplantTarget: Codable, Equatable, Sendable, Identifiable {
    public let targetId: String
    public let schemaVersion: Int
    public let label: String
    public let apMillimetres: Double
    public let mlMillimetres: Double
    public let dvMillimetres: Double
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
    public let createdAt: String
    public let notes: String
    public let projected: Bool
    public let usableForNavigation: Bool
    public let projectionStatus: String

    public var id: String { targetId }
}

public struct ImplantListResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let targetCount: Int
    public let coordinateFrame: BregmaCoordinateFrame
    public let projected: Bool
    public let usableForNavigation: Bool
    public let projectionStatus: String
    public let targets: [UnprojectedImplantTarget]
}

public struct ImplantMutationResult: Codable, Equatable, Sendable {
    public let protocolVersion: Int
    public let status: String
    public let targetCount: Int
    public let coordinateFrame: BregmaCoordinateFrame
    public let projected: Bool
    public let usableForNavigation: Bool
    public let projectionStatus: String
    public let target: UnprojectedImplantTarget
}

public enum ImplantTargetValidationError: Error, Equatable, LocalizedError, Sendable {
    case protocolMismatch(Int)
    case unexpectedStatus(String)
    case targetCountMismatch
    case coordinateFrameMismatch
    case projectionWasNotLocked
    case malformedTarget

    public var errorDescription: String? {
        switch self {
        case let .protocolMismatch(version):
            "Implant response uses protocol \(version); expected \(BridgeProtocolVersion.current)."
        case let .unexpectedStatus(status):
            "Implant response has unexpected status ‘\(status)’"
        case .targetCountMismatch:
            "Implant response target count is inconsistent."
        case .coordinateFrameMismatch:
            "Implant response changed the reviewed bregma AP/ML/DV frame or sign convention."
        case .projectionWasNotLocked:
            "Implant response did not keep atlas projection and navigation locked."
        case .malformedTarget:
            "Implant response contains a malformed unprojected target."
        }
    }
}

public enum ImplantTargetValidator {
    public static let frameId = "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED"
    public static let projectionStatus = "lockedUntilExplicitBregmaSkullCalibration"

    public static func validateList(_ result: ImplantListResult) throws {
        try validateEnvelope(
            protocolVersion: result.protocolVersion,
            status: result.status,
            expectedStatuses: ["listed"],
            targetCount: result.targetCount,
            frame: result.coordinateFrame,
            projected: result.projected,
            usableForNavigation: result.usableForNavigation,
            declaredProjectionStatus: result.projectionStatus,
            returnedTargets: result.targets.count
        )
        for target in result.targets {
            try validate(target)
        }
    }

    public static func validateMutation(
        _ result: ImplantMutationResult,
        expectedStatus: String
    ) throws {
        try validateEnvelope(
            protocolVersion: result.protocolVersion,
            status: result.status,
            expectedStatuses: [expectedStatus],
            targetCount: result.targetCount,
            frame: result.coordinateFrame,
            projected: result.projected,
            usableForNavigation: result.usableForNavigation,
            declaredProjectionStatus: result.projectionStatus,
            returnedTargets: nil
        )
        try validate(result.target)
    }

    private static func validateEnvelope(
        protocolVersion: Int,
        status: String,
        expectedStatuses: Set<String>,
        targetCount: Int,
        frame: BregmaCoordinateFrame,
        projected: Bool,
        usableForNavigation: Bool,
        declaredProjectionStatus: String,
        returnedTargets: Int?
    ) throws {
        guard protocolVersion == BridgeProtocolVersion.current else {
            throw ImplantTargetValidationError.protocolMismatch(protocolVersion)
        }
        guard expectedStatuses.contains(status) else {
            throw ImplantTargetValidationError.unexpectedStatus(status)
        }
        guard targetCount >= 0, returnedTargets == nil || returnedTargets == targetCount else {
            throw ImplantTargetValidationError.targetCountMismatch
        }
        try validate(frame)
        guard
            !projected,
            !usableForNavigation,
            declaredProjectionStatus == projectionStatus
        else {
            throw ImplantTargetValidationError.projectionWasNotLocked
        }
    }

    private static func validate(_ frame: BregmaCoordinateFrame) throws {
        guard
            frame.frameId == frameId,
            frame.origin == "bregma",
            frame.componentOrder == ["AP", "ML", "DV"],
            frame.units == "millimetre",
            frame.signConvention.apPositive == "anterior",
            frame.signConvention.apNegative == "posterior/back",
            frame.signConvention.mlPositive == "right",
            frame.signConvention.mlNegative == "left",
            frame.signConvention.dvPositive == "dorsal/up",
            frame.signConvention.dvNegative == "deep/ventral"
        else {
            throw ImplantTargetValidationError.coordinateFrameMismatch
        }
    }

    private static func validate(_ target: UnprojectedImplantTarget) throws {
        guard
            UUID(uuidString: target.targetId) != nil,
            target.schemaVersion == 1,
            !target.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
            target.apMillimetres.isFinite,
            target.mlMillimetres.isFinite,
            target.dvMillimetres.isFinite,
            target.frameId == frameId,
            target.origin == "bregma",
            target.componentOrder == ["AP", "ML", "DV"],
            target.units == "millimetre",
            target.apPositiveDirection == "anterior",
            target.apNegativeDirection == "posterior/back",
            target.mlPositiveDirection == "right",
            target.mlNegativeDirection == "left",
            target.dvPositiveDirection == "dorsal/up",
            target.dvNegativeDirection == "deep/ventral",
            !target.createdAt.isEmpty
        else {
            throw ImplantTargetValidationError.malformedTarget
        }
        guard
            !target.projected,
            !target.usableForNavigation,
            target.projectionStatus == projectionStatus
        else {
            throw ImplantTargetValidationError.projectionWasNotLocked
        }
    }
}
