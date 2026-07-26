import AppKit
import Brain3DCore
import Combine
import Foundation
import SwiftUI
import Testing
@testable import Brain3DApp

@Suite("Probe creation workflow")
struct ProbeCreationWorkflowTests {
    @Test("The direct implant editor exposes only the six requested inputs")
    func directEditorFields() {
        #expect(ProbeSurfaceEditorPresentation.visibleFields == [
            .model,
            .ap,
            .ml,
            .surfaceDepth,
            .anteriorPosteriorAngle,
            .layoutRotation,
        ])
        #expect(ProbeSurfaceEditorPresentation.apLabel == "AP (+A / −P)")
        #expect(ProbeSurfaceEditorPresentation.mlLabel == "ML (+R / −L)")
        #expect(ProbeSurfaceEditorPresentation.depthLabel == "Shank 1 depth from surface")
        #expect(
            ProbeSurfaceEditorPresentation.angleLabel
                == "A↔P angle (+ A→P)"
        )
        #expect(ProbeSurfaceEditorPresentation.explicitActionTitle == nil)
    }

    @Test("The probe selector exposes only the requested product codes")
    func directEditorProbeLabels() {
        #expect(ProbeSurfaceEditorPresentation.modelLabel(
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId
        ) == "NP2003 · 1 shank")
        #expect(ProbeSurfaceEditorPresentation.modelLabel(
            modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId
        ) == "NP2013 · 4 shank")
        #expect(ProbeSurfaceEditorPresentation.modelLabel(
            modelId: ProbePlanningContract.neuropixels2QuadBaseFourShankModelId
        ) == nil)
        #expect(ProbeSurfaceEditorPresentation.modelLabel(
            modelId: ProbePlanningContract.neuropixelsModelId
        ) == nil)
    }

    @Test("Layout choices preserve the surgical orientation convention")
    func directEditorLayoutChoices() {
        #expect(ProbeLayoutRotation.allCases == [.sagittal, .clockwise90])
        #expect(ProbeLayoutRotation.sagittal.rawValue == "0")
        #expect(ProbeLayoutRotation.sagittal.label == "Sagittal")
        #expect(ProbeLayoutRotation.sagittal.accessibilityValue.contains(
            "shank 1 is most anterior"
        ))
        #expect(ProbeLayoutRotation.clockwise90.rawValue == "90")
        #expect(ProbeLayoutRotation.clockwise90.accessibilityValue.contains(
            "shank 1 is leftmost"
        ))
    }

    @Test("Only explicit numeric commit boundaries can enqueue typed values")
    func directEditorCommitPolicy() {
        #expect(autoCommitAction(.textChanged) == .ignore)
        #expect(autoCommitAction(.textChanged, focused: true) == .ignore)
        #expect(autoCommitAction(.textSubmitted, focused: true) == .enqueueMutation)
        #expect(autoCommitAction(.numericFocusLost) == .enqueueMutation)
    }

    @Test("Atomic selectors end numeric editing before they mutate a plan")
    func directEditorSelectorWhileTypingPolicy() {
        #expect(autoCommitAction(.modelChanged) == .enqueueMutation)
        #expect(autoCommitAction(.layoutChanged) == .enqueueMutation)
        #expect(autoCommitAction(.modelChanged, focused: true) == .endNumericEditing)
        #expect(autoCommitAction(.layoutChanged, focused: true) == .endNumericEditing)
    }

    @Test("Lifecycle readiness cannot submit partially typed numeric text")
    func directEditorLifecycleWhileTypingPolicy() {
        #expect(autoCommitAction(.planningBecameReady) == .enqueueMutation)
        #expect(autoCommitAction(.planningBecameReady, focused: true) == .ignore)
    }

    @MainActor
    @Test("The AppKit field delegate commits once at the real end-editing boundary")
    func directEditorAppKitEndEditingBoundary() {
        var value = "0"
        var commitCount = 0
        var beganCount = 0
        var endedCount = 0
        let coordinator = ProbeNumericTextFieldCoordinator(
            text: Binding(
                get: { value },
                set: { value = $0 }
            ),
            onBeginEditing: { _ in beganCount += 1 },
            onEndEditing: { _ in endedCount += 1 },
            onCommit: { commitCount += 1 }
        )
        let textField = NSTextField(string: value)

        coordinator.controlTextDidBeginEditing(Notification(
            name: NSControl.textDidBeginEditingNotification,
            object: textField
        ))
        textField.stringValue = "9"
        coordinator.controlTextDidChange(Notification(
            name: NSControl.textDidChangeNotification,
            object: textField
        ))
        #expect(value == "9")
        #expect(commitCount == 0)

        textField.stringValue = "90"
        coordinator.controlTextDidChange(Notification(
            name: NSControl.textDidChangeNotification,
            object: textField
        ))
        #expect(value == "90")
        #expect(commitCount == 0)

        let endNotification = Notification(
            name: NSControl.textDidEndEditingNotification,
            object: textField
        )
        coordinator.controlTextDidEndEditing(endNotification)
        coordinator.controlTextDidEndEditing(endNotification)

        #expect(beganCount == 1)
        #expect(endedCount == 1)
        #expect(commitCount == 1)
    }

    @Test("Auto-commit serializes mutations and coalesces to the latest pending edit")
    func directEditorAutoCommitQueue() {
        var queue = ProbeSurfaceAutoCommitQueue()
        let first = autoCommitRequest(angle: "9", revision: 1)
        let second = autoCommitRequest(angle: "90", revision: 2)
        let latest = autoCommitRequest(angle: "45", revision: 3)

        let startsWorker = queue.enqueue(first)
        #expect(startsWorker)
        let firstTicket = queue.beginNext()
        #expect(firstTicket?.request == first)
        let secondStartsWorker = queue.enqueue(second)
        let latestStartsWorker = queue.enqueue(latest)
        #expect(!secondStartsWorker)
        #expect(!latestStartsWorker)
        #expect(queue.pending?.request == latest)
        #expect(firstTicket.map(queue.isLatest) == false)
        let firstHasPending = firstTicket.map { queue.complete($0) }
        #expect(firstHasPending == true)

        let latestTicket = queue.beginNext()
        #expect(latestTicket?.request == latest)
        #expect(latestTicket.map(queue.isLatest) == true)
        let latestHasPending = latestTicket.map { queue.complete($0) }
        #expect(latestHasPending == false)
        #expect(queue.inFlight == nil)
        #expect(queue.pending == nil)
    }

    @Test("Repeated lifecycle events do not duplicate one auto-commit")
    func directEditorAutoCommitDeduplication() {
        var queue = ProbeSurfaceAutoCommitQueue()
        let request = autoCommitRequest(angle: "12", revision: 4)

        let startsWorker = queue.enqueue(request)
        let duplicateStartsWorker = queue.enqueue(request)
        #expect(startsWorker)
        #expect(!duplicateStartsWorker)
        let ticket = queue.beginNext()
        #expect(ticket?.request == request)
        let inFlightDuplicateStartsWorker = queue.enqueue(request)
        #expect(!inFlightDuplicateStartsWorker)
        let hasPending = ticket.map { queue.complete($0) }
        #expect(hasPending == false)
        let next = queue.beginNext()
        #expect(next == nil)
    }

    @Test("A completed request cannot overwrite text edited while it was in flight")
    func directEditorStaleCompletion() {
        let submitted = autoCommitRequest(angle: "9", revision: 5)
        #expect(ProbeSurfaceAutoCommitCompletionPolicy.mayPopulateDraft(
            completed: submitted,
            isLatestRequest: true,
            currentEditableRevision: 5,
            currentSnapshot: submitted.snapshot
        ))
        #expect(!ProbeSurfaceAutoCommitCompletionPolicy.mayPopulateDraft(
            completed: submitted,
            isLatestRequest: true,
            currentEditableRevision: 6,
            currentSnapshot: autoCommitRequest(angle: "90", revision: 6).snapshot
        ))
        #expect(!ProbeSurfaceAutoCommitCompletionPolicy.mayPopulateDraft(
            completed: submitted,
            isLatestRequest: false,
            currentEditableRevision: 5,
            currentSnapshot: submitted.snapshot
        ))
        #expect(!ProbeSurfaceAutoCommitCompletionPolicy.mayPopulateDraft(
            completed: submitted,
            isLatestRequest: true,
            currentEditableRevision: 7,
            currentSnapshot: submitted.snapshot
        ))
    }

    @MainActor
    @Test("A numeric keystroke emits no nested derived-state publication")
    func directEditorPublicationBoundary() {
        let session = ProbeDraftSession()
        var publicationCount = 0
        let observation = session.objectWillChange.sink {
            publicationCount += 1
        }

        session.sagittalAngle = "9"

        #expect(publicationCount == 1)
        #expect(session.editableRevision == 1)
        #expect(session.hasUnappliedChanges)
        withExtendedLifetime(observation) {}
    }

    @Test("Surface-relative readiness uses only the five operator values")
    func directEditorReadiness() {
        #expect(surfaceBlocker() == nil)
        #expect(surfaceBlocker(ap: "") ==
            "Enter valid AP and ML coordinates in millimetres.")
        #expect(surfaceBlocker(ml: "not-a-number") ==
            "Enter valid AP and ML coordinates in millimetres.")
        #expect(surfaceBlocker(surfaceDepth: "0") ==
            "Enter a depth greater than 0 and no more than the 10 mm shank length.")
        #expect(surfaceBlocker(surfaceDepth: "10.1") ==
            "Enter a depth greater than 0 and no more than the 10 mm shank length.")
        #expect(surfaceBlocker(anteriorPosteriorAngle: "91") ==
            "Enter an A↔P angle greater than −90° and less than 90°.")
        #expect(surfaceBlocker(anteriorPosteriorAngle: "90") ==
            "Enter an A↔P angle greater than −90° and less than 90°.")
        #expect(surfaceBlocker(layoutRotation: "45") ==
            "Choose the sagittal or 90° clockwise probe layout.")
        #expect(surfaceBlocker(layoutRotation: "90.0") == nil)
    }

    @Test("Direct surface planning has no calibration or registration prerequisite")
    func directEditorAvailability() {
        #expect(ProbeSurfacePlanningAvailabilityPolicy.blockingReason(
            connectionReady: true,
            hasProject: true,
            projectOperationInProgress: false,
            probeOperationInProgress: false
        ) == nil)
        #expect(ProbeSurfacePlanningAvailabilityPolicy.blockingReason(
            connectionReady: false,
            hasProject: true,
            projectOperationInProgress: false,
            probeOperationInProgress: false
        ) == "Connect to the planning service.")
        #expect(ProbeSurfacePlanningAvailabilityPolicy.blockingReason(
            connectionReady: true,
            hasProject: false,
            projectOperationInProgress: false,
            probeOperationInProgress: false
        ) == "Open or create an animal plan.")
    }

    @Test("The surface draft tracks only visible values and canonicalizes numbers")
    func directEditorDraftComparison() {
        let baseline = surfaceDraft()
        #expect(!ProbeSurfaceDraftComparisonPolicy.hasUnappliedEdits(
            current: surfaceDraft(
                ap: "-1.5000",
                ml: "0.800000",
                surfaceDepthMM: "3.200",
                sagittalAngle: "12.0",
                layoutRotation: "-0"
            ),
            baseline: baseline
        ))
        #expect(ProbeSurfaceDraftComparisonPolicy.hasUnappliedEdits(
            current: surfaceDraft(surfaceDepthMM: "3.3"),
            baseline: baseline
        ))
        #expect(ProbeSurfaceDraftComparisonPolicy.hasUnappliedEdits(
            current: surfaceDraft(
                modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId
            ),
            baseline: baseline
        ))
        #expect(ProbeSurfaceDraftComparisonPolicy.hasUnappliedEdits(
            current: baseline,
            baseline: nil
        ))
    }

    @Test("Operator depth is millimetres while the geometry protocol remains micrometres")
    func depthUnitConversion() {
        #expect(ProbeInputUnits.micrometres(fromMillimetres: 3.5) == 3_500)
        #expect(ProbeInputUnits.millimetres(fromMicrometres: 3_500) == 3.5)
    }

    @MainActor
    @Test("Unapplied probe edits participate in the app-wide dirty-state guard")
    func unappliedProbeDraftDirtyState() {
        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        let model = PlannerViewModel(
            launchConfiguration: nil,
            preferences: defaults
        )
        #expect(!model.hasPendingPlanChanges)
        model.probeDraftSession.setHasUnappliedChanges(true)
        #expect(model.hasUnappliedProbeDraftChanges)
        #expect(model.hasPendingPlanChanges)
        model.probeDraftSession.setHasUnappliedChanges(false)
        #expect(!model.hasPendingPlanChanges)
    }

    @MainActor
    @Test("The sole planning window reuses the app-owned unapplied draft after close")
    func singleWindowDraftRetention() {
        #expect(!MainPlanningWindowPolicy.permitsMultipleMainWindows)
        #expect(MainPlanningWindowPolicy.sceneId == "main-planning-window")

        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        let model = PlannerViewModel(
            launchConfiguration: nil,
            preferences: defaults
        )
        let firstWindowSession = model.probeDraftSession
        let context = ProbeDraftContext(
            projectId: "project-1",
            planId: "plan-1",
            planInputSha256: "input-1"
        )
        firstWindowSession.surfaceAP = "-1.5"
        firstWindowSession.surfaceML = "-0.8"
        firstWindowSession.surfaceDepthMM = "3.25"
        firstWindowSession.markSynchronized(with: context)
        #expect(firstWindowSession.hasUnappliedChanges)

        // Recreating ProjectSidebar after the red window closes receives this
        // same model-owned object instead of a fresh per-window @State draft.
        let reopenedWindowSession = model.probeDraftSession
        #expect(reopenedWindowSession === firstWindowSession)
        #expect(reopenedWindowSession.surfaceAP == "-1.5")
        #expect(reopenedWindowSession.surfaceDepthMM == "3.25")
        #expect(!ProbeDraftSynchronizationPolicy.shouldReplaceDraft(
            existingContext: reopenedWindowSession.synchronizedContext,
            incomingContext: context,
            hasUnappliedChanges: reopenedWindowSession.hasUnappliedChanges
        ))
        #expect(model.hasPendingPlanChanges)
        #expect(
            TerminationPolicy.decision(
                hasUnsavedChanges: model.hasPendingPlanChanges
            ) == .requireDiscardConfirmation
        )
    }

    @MainActor
    @Test("Only an explicit discard clears the retained probe draft session")
    func explicitDraftDiscard() {
        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        let model = PlannerViewModel(
            launchConfiguration: nil,
            preferences: defaults
        )
        let session = model.probeDraftSession
        session.surfaceAP = "-2"
        session.surfaceML = "-1"
        session.surfaceDepthMM = "3.5"
        session.sagittalAngle = "10"
        session.layoutRotation = "90"
        session.surfaceBaseline = surfaceDraft()
        session.pendingExplicitNewModel = ProbeDraftModelIdentity(
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId,
            modelVersion: ProbePlanningContract.neuropixels2ModelVersion
        )
        session.markSynchronized(with: ProbeDraftContext(
            projectId: "project-1",
            planId: nil,
            planInputSha256: nil
        ))
        session.setHasUnappliedChanges(true)

        model.discardProbeDraftSession()

        #expect(session.surfaceAP == "0")
        #expect(session.surfaceML == "0")
        #expect(session.surfaceDepthMM == "2.3")
        #expect(session.sagittalAngle == "0")
        #expect(session.layoutRotation == "0")
        #expect(session.surfaceBaseline == nil)
        #expect(session.pendingExplicitNewModel == nil)
        #expect(session.synchronizedContext == nil)
        #expect(!session.hasUnappliedChanges)
        #expect(!model.hasPendingPlanChanges)
    }

    @MainActor
    @Test("Model save and open calls cannot bypass an unapplied probe draft")
    func projectOperationsFailClosedForDraft() async {
        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        let model = PlannerViewModel(
            launchConfiguration: nil,
            preferences: defaults
        )
        model.probeDraftSession.surfaceAP = "-1.5"
        #expect(model.hasPendingPlanChanges)

        let destination = URL(fileURLWithPath: "/tmp/unreachable.mouseplan")
        #expect(!(await model.saveProject(to: destination)))
        #expect(
            model.projectOperationError
                == "Finish the numeric edit with Return or leave the field, then wait "
                + "for the probe update before saving the animal plan."
        )
        #expect(!(await model.openProject(at: destination)))
        #expect(
            model.projectOperationError
                == "Discard the probe draft before opening another animal plan."
        )
        #expect(model.probeDraftSession.surfaceAP == "-1.5")
        #expect(model.hasPendingPlanChanges)
    }

    @MainActor
    @Test("A direct reconnect cannot bypass explicit probe-draft discard")
    func reconnectFailsClosedForDraft() async {
        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        let model = PlannerViewModel(
            launchConfiguration: nil,
            preferences: defaults
        )
        model.probeDraftSession.surfaceML = "-0.8"
        #expect(model.hasPendingPlanChanges)

        await model.reconnect()

        #expect(model.probeDraftSession.surfaceML == "-0.8")
        #expect(model.hasUnappliedProbeDraftChanges)
        #expect(model.hasPendingPlanChanges)
        #expect(
            model.projectOperationError
                == "Discard the probe draft before reconnecting the planning service."
        )

        model.discardProbeDraftSession()
        await model.reconnect()

        #expect(model.probeDraftSession.surfaceML == "0")
        #expect(!model.hasUnappliedProbeDraftChanges)
    }

    @Test("Context changes replace only clean drafts")
    func draftContextSynchronization() {
        let old = ProbeDraftContext(
            projectId: "project-1",
            planId: "plan-1",
            planInputSha256: "input-1"
        )
        let updated = ProbeDraftContext(
            projectId: "project-1",
            planId: "plan-1",
            planInputSha256: "input-2"
        )
        #expect(!ProbeDraftSynchronizationPolicy.shouldReplaceDraft(
            existingContext: old,
            incomingContext: old,
            hasUnappliedChanges: true
        ))
        #expect(!ProbeDraftSynchronizationPolicy.shouldReplaceDraft(
            existingContext: old,
            incomingContext: updated,
            hasUnappliedChanges: true
        ))
        #expect(ProbeDraftSynchronizationPolicy.shouldReplaceDraft(
            existingContext: old,
            incomingContext: updated,
            hasUnappliedChanges: false
        ))
        #expect(ProbeDraftSynchronizationPolicy.shouldReplaceDraft(
            existingContext: nil,
            incomingContext: updated,
            hasUnappliedChanges: false
        ))
    }

    @Test("Neuropixels 2.0 catalog identities remain explicit")
    func neuropixels2Identity() {
        #expect(ProbeCatalogPresentation.isNeuropixels2(
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId
        ))
        #expect(ProbeCatalogPresentation.isNeuropixels2(
            modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId
        ))
        #expect(!ProbeCatalogPresentation.isNeuropixels2(
            modelId: ProbePlanningContract.neuropixels2QuadBaseFourShankModelId
        ))
        #expect(!ProbeCatalogPresentation.isNeuropixels2(
            modelId: ProbePlanningContract.neuropixelsModelId
        ))
        #expect(!ProbeCatalogPresentation.isNeuropixels2(
            modelId: "imec-neuropixels-2.0-lookalike"
        ))
        #expect(ProbeCatalogPresentation.simultaneousChannelCount(
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId
        ) == 384)
        #expect(ProbeCatalogPresentation.simultaneousChannelCount(
            modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId
        ) == 384)
        #expect(ProbeCatalogPresentation.simultaneousChannelCount(
            modelId: ProbePlanningContract.neuropixels2QuadBaseFourShankModelId
        ) == nil)
        #expect(ProbeCatalogPresentation.simultaneousChannelCount(
            modelId: ProbePlanningContract.neuropixelsModelId
        ) == nil)
    }

    @Test("3D overlay status is active only for the ready current scene")
    func overlayStatus() {
        let slicePrefix = "Overlay active in Dorsal, Coronal, Sagittal, and Horizontal."
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .ready,
            sceneContainsCurrentPlan: true
        ) == "Overlay active in Dorsal, Coronal, Sagittal, Horizontal, and 3D.")
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .loadingGeometry,
            sceneContainsCurrentPlan: true
        ) == "\(slicePrefix) 3D overlay pending.")
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .ready,
            sceneContainsCurrentPlan: false
        ) == "\(slicePrefix) 3D overlay pending scene refresh.")
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .failed("mesh missing"),
            sceneContainsCurrentPlan: true
        ) == "\(slicePrefix) 3D overlay unavailable.")
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .unavailable("service capability missing"),
            sceneContainsCurrentPlan: false
        ) == "\(slicePrefix) 3D overlay unavailable.")
    }

    @Test("3D render callbacks cannot publish a stale scene as ready")
    func threeDimensionalRenderPublication() {
        #expect(ThreeDimensionalRenderPhaseReducer.phaseAfterPreparing(
            snapshotIdentity: "scene-B",
            renderedSnapshotIdentity: "scene-B"
        ) == .ready)
        #expect(ThreeDimensionalRenderPhaseReducer.phaseAfterPreparing(
            snapshotIdentity: "scene-B",
            renderedSnapshotIdentity: "scene-A"
        ) == .loadingGeometry)
        #expect(ThreeDimensionalRenderPhaseReducer.acceptsCallback(
            snapshotIdentity: "scene-B",
            currentSnapshotIdentity: "scene-B"
        ))
        #expect(!ThreeDimensionalRenderPhaseReducer.acceptsCallback(
            snapshotIdentity: "scene-A",
            currentSnapshotIdentity: "scene-B"
        ))
    }

    @Test("Selecting a region invalidates 3D preparation before its mesh arrives")
    func pendingRegionMeshChangesPreparationIdentity() {
        #expect(
            ThreeDimensionalPreparationIdentityPolicy.highlightedRegionComponent(
                structureId: nil,
                meshSHA256: nil
            ) == "no-highlighted-region"
        )
        #expect(
            ThreeDimensionalPreparationIdentityPolicy.highlightedRegionComponent(
                structureId: 549,
                meshSHA256: nil
            ) == "549@mesh-pending"
        )
        #expect(
            ThreeDimensionalPreparationIdentityPolicy.highlightedRegionComponent(
                structureId: 385,
                meshSHA256: nil
            ) == "385@mesh-pending"
        )
        #expect(
            ThreeDimensionalPreparationIdentityPolicy.highlightedRegionComponent(
                structureId: 549,
                meshSHA256: String(repeating: "a", count: 64)
            ) == "549@\(String(repeating: "a", count: 64))"
        )
    }

    @Test("Live implant and probe overlays never mix different targets")
    func liveOverlayTargetCoherence() {
        #expect(LivePlanningOverlayCoherence.matches(
            probeTargetId: "target-a",
            displayedImplantTargetId: nil
        ))
        #expect(LivePlanningOverlayCoherence.matches(
            probeTargetId: "target-a",
            displayedImplantTargetId: "target-a"
        ))
        #expect(!LivePlanningOverlayCoherence.matches(
            probeTargetId: "target-b",
            displayedImplantTargetId: "target-a"
        ))
    }

    private func surfaceBlocker(
        planningUnavailableReason: String? = nil,
        hasSelectedModel: Bool = true,
        ap: String = "-1.5",
        ml: String = "0.8",
        surfaceDepth: String = "3.2",
        anteriorPosteriorAngle: String = "12",
        layoutRotation: String = "0"
    ) -> String? {
        ProbeSurfaceDraftReadinessPolicy.blockingReason(
            planningUnavailableReason: planningUnavailableReason,
            hasSelectedModel: hasSelectedModel,
            ap: ap,
            ml: ml,
            surfaceDepth: surfaceDepth,
            anteriorPosteriorAngle: anteriorPosteriorAngle,
            layoutRotation: layoutRotation
        )
    }

    private func surfaceDraft(
        modelId: String? = ProbePlanningContract.neuropixels2SingleShankModelId,
        modelVersion: String? = ProbePlanningContract.neuropixels2ModelVersion,
        ap: String = "-1.5",
        ml: String = "0.8",
        surfaceDepthMM: String = "3.2",
        sagittalAngle: String = "12",
        layoutRotation: String = "0"
    ) -> ProbeSurfaceDraftSnapshot {
        ProbeSurfaceDraftComparisonPolicy.snapshot(
            modelId: modelId,
            modelVersion: modelVersion,
            ap: ap,
            ml: ml,
            surfaceDepthMM: surfaceDepthMM,
            sagittalAngle: sagittalAngle,
            layoutRotation: layoutRotation
        )
    }

    private func autoCommitRequest(
        angle: String,
        revision: Int
    ) -> ProbeSurfaceAutoCommitRequest {
        ProbeSurfaceAutoCommitRequest(
            model: ProbeDraftModelIdentity(
                modelId: ProbePlanningContract.neuropixels2SingleShankModelId,
                modelVersion: ProbePlanningContract.neuropixels2ModelVersion
            ),
            ap: "-1.5",
            ml: "-0.8",
            surfaceDepthMM: "2.3",
            sagittalAngle: angle,
            layoutRotation: ProbeLayoutRotation.sagittal.rawValue,
            editableRevision: revision
        )
    }

    private func autoCommitAction(
        _ trigger: ProbeSurfaceAutoCommitTrigger,
        focused: Bool = false
    ) -> ProbeSurfaceAutoCommitAction {
        ProbeSurfaceAutoCommitPolicy.action(
            for: trigger,
            numericFieldIsFocused: focused
        )
    }

}

@Suite("Probe planning prerequisites")
struct ProbePlanningAvailabilityPolicyTests {
    @Test("Availability distinguishes setup failures from in-flight work")
    func blockingReasons() {
        #expect(reason(connectionReady: false) == "Connect to the planning service.")
        #expect(reason(hasProject: false) == "Open or create an animal plan.")
        #expect(reason(hasActiveCalibration: false)
            == "Activate a passing subject calibration.")
        #expect(reason(calibrationPermitsPlanning: false)
            == "The active subject calibration does not pass planning checks.")
        #expect(reason(serviceSupportsProbePlanning: false)
            == "The connected service does not support calibrated probe planning.")
        #expect(reason(probeOperationInProgress: true)
            == "Wait for the probe operation to finish.")
        #expect(reason() == nil)
    }

    private func reason(
        connectionReady: Bool = true,
        hasProject: Bool = true,
        hasActiveCalibration: Bool = true,
        calibrationPermitsPlanning: Bool = true,
        serviceSupportsProbePlanning: Bool = true,
        projectOperationInProgress: Bool = false,
        calibrationOperationInProgress: Bool = false,
        probeOperationInProgress: Bool = false
    ) -> String? {
        ProbePlanningAvailabilityPolicy.blockingReason(
            connectionReady: connectionReady,
            hasProject: hasProject,
            hasActiveCalibration: hasActiveCalibration,
            calibrationPermitsPlanning: calibrationPermitsPlanning,
            serviceSupportsProbePlanning: serviceSupportsProbePlanning,
            projectOperationInProgress: projectOperationInProgress,
            calibrationOperationInProgress: calibrationOperationInProgress,
            probeOperationInProgress: probeOperationInProgress
        )
    }
}

@Suite("Project identity presentation")
struct ProjectStatusPresentationTests {
    @Test("Subject ID is never omitted from a loaded project")
    func subjectId() {
        #expect(ProjectStatusPresentation.text(
            title: "Left V1 plan",
            subjectId: "mouse-042",
            hasUnsavedChanges: false
        ) == "Left V1 plan · Subject ID mouse-042 · animal-only · saved")
        #expect(ProjectStatusPresentation.text(
            title: "Legacy plan",
            subjectId: " ",
            hasUnsavedChanges: true
        ) == "Legacy plan · Subject ID unavailable · animal-only · unsaved changes")
    }
}
