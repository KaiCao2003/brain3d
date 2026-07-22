import Foundation

/// Transient UI state for the animal-only use gate.
///
/// The only public initializer starts unacknowledged so a caller cannot create a
/// project request without first recording an explicit user action.
public struct AnimalOnlyAcknowledgementState: Equatable, Sendable {
    public private(set) var isExplicitlyAcknowledged = false

    public init() {}

    public mutating func setExplicitlyAcknowledged(_ isAcknowledged: Bool) {
        isExplicitlyAcknowledged = isAcknowledged
    }
}

public enum AnimalOnlyContract {
    public static func isValid(animalOnly: Bool?, warning: String?) -> Bool {
        animalOnly == true && warning == SafetyPolicy.animalResearchOnly
    }
}
