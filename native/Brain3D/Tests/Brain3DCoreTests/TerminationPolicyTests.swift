import Brain3DCore
import Testing

@Suite("Application termination safety")
struct TerminationPolicyTests {
    @Test("A clean animal plan may terminate immediately")
    func cleanPlan() {
        #expect(TerminationPolicy.decision(hasUnsavedChanges: false) == .terminateNow)
    }

    @Test("Unsaved animal plan changes require explicit discard confirmation")
    func dirtyPlan() {
        #expect(
            TerminationPolicy.decision(hasUnsavedChanges: true)
                == .requireDiscardConfirmation
        )
    }
}
