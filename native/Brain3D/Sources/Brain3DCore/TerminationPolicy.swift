public enum TerminationDecision: Equatable, Sendable {
    case terminateNow
    case requireDiscardConfirmation
}

public enum TerminationPolicy {
    public static func decision(hasUnsavedChanges: Bool) -> TerminationDecision {
        hasUnsavedChanges ? .requireDiscardConfirmation : .terminateNow
    }
}
