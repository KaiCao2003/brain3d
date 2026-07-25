import Brain3DCore
import Foundation
import Testing
@testable import Brain3DApp

@Suite("Probe creation workflow")
struct ProbeCreationWorkflowTests {
    @Test("A complete stereotaxic Neuropixels draft is actionable")
    func completeStereotaxicDraft() {
        #expect(blocker() == nil)
    }

    @Test("Each hidden prerequisite produces an operator-facing reason")
    func prerequisiteReasons() {
        #expect(blocker(planningUnavailableReason: "Activate calibration.")
            == "Activate calibration.")
        #expect(blocker(hasSelectedModel: false)
            == "Select a probe model from the connected catalog.")
        #expect(blocker(selectedTargetId: "")
            == "Select a stored implant target.")
        #expect(blocker(name: "   ")
            == "Enter a probe plan name.")
        #expect(blocker(azimuth: "181")
            == "Enter azimuth from −180° through 180°.")
        #expect(blocker(elevation: "-91")
            == "Enter elevation from −90° through 90°.")
        #expect(blocker(depth: "0")
            == "Enter a positive insertion depth in millimetres.")
        #expect(blocker(axialRotation: "")
            == "Enter axial rotation from −180° through 180°.")
        #expect(blocker(acknowledgementGiven: false)
            == "Acknowledge the selected probe geometry before continuing.")
    }

    @Test("Operator depth is millimetres while the geometry protocol remains micrometres")
    func depthUnitConversion() {
        #expect(ProbeInputUnits.micrometres(fromMillimetres: 3.5) == 3_500)
        #expect(ProbeInputUnits.millimetres(fromMicrometres: 3_500) == 3.5)
    }

    @Test("Equivalent number spelling does not create a false unapplied-edit warning")
    func equivalentProbeDraftNumbers() throws {
        let saved = try #require(draft(depth: "3", axialRotation: "0"))
        let current = try #require(draft(
            azimuth: "0.000000",
            elevation: "-90.0",
            depth: "3.000",
            axialRotation: "-0"
        ))
        #expect(!ProbeDraftComparisonPolicy.hasUnappliedEdits(
            current: current,
            saved: saved
        ))
    }

    @Test("Changed or invalid depth cannot silently export the applied trajectory")
    func unappliedProbeDraftDepth() throws {
        let saved = try #require(draft(depth: "3"))
        let changed = try #require(draft(depth: "2.5"))
        #expect(ProbeDraftComparisonPolicy.hasUnappliedEdits(
            current: changed,
            saved: saved
        ))
        #expect(ProbeDraftComparisonPolicy.hasUnappliedEdits(
            current: draft(depth: "not-a-number"),
            saved: saved
        ))
    }

    @Test("Hidden legacy fields do not make the simple NPX2 draft dirty")
    func hiddenProbeDraftFields() throws {
        let saved = try #require(draft(entryAP: "", entryML: "", entryDV: ""))
        let current = try #require(draft(
            entryAP: "999",
            entryML: "999",
            entryDV: "999"
        ))
        #expect(!ProbeDraftComparisonPolicy.hasUnappliedEdits(
            current: current,
            saved: saved
        ))
    }

    @Test("Revert restores the saved NPX2 model identity and clears the draft difference")
    func revertedProbeModelIdentity() throws {
        let saved = try #require(draft(
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId
        ))
        let switched = try #require(draft(
            modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId
        ))
        #expect(ProbeDraftComparisonPolicy.hasUnappliedEdits(
            current: switched,
            saved: saved
        ))

        let identity = try #require(
            ProbeDraftComparisonPolicy.modelIdentityToRestore(
                currentModelId: switched.modelId,
                currentModelVersion: switched.modelVersion,
                saved: saved
            )
        )
        #expect(identity.modelId == saved.modelId)
        #expect(identity.modelVersion == saved.modelVersion)

        let reverted = try #require(draft(
            modelId: identity.modelId,
            modelVersion: identity.modelVersion
        ))
        #expect(!ProbeDraftComparisonPolicy.hasUnappliedEdits(
            current: reverted,
            saved: saved
        ))
        #expect(ProbeDraftComparisonPolicy.modelIdentityToRestore(
            currentModelId: reverted.modelId,
            currentModelVersion: reverted.modelVersion,
            saved: saved
        ) == nil)
    }

    @MainActor
    @Test("A meaningful new probe draft is guarded but its pristine defaults are not")
    func newProbeDraftDirtyState() {
        let pristine = newDraft()
        #expect(!ProbeDraftComparisonPolicy.hasMeaningfulNewDraft(
            current: newDraft(axialRotation: "-0.000"),
            pristine: pristine
        ))

        let meaningful = newDraft(depth: "3")
        #expect(ProbeDraftComparisonPolicy.hasMeaningfulNewDraft(
            current: meaningful,
            pristine: pristine
        ))
        #expect(ProbeDraftComparisonPolicy.hasMeaningfulNewDraft(
            current: newDraft(
                modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId
            ),
            pristine: pristine
        ))

        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        let model = PlannerViewModel(
            launchConfiguration: nil,
            preferences: defaults
        )
        model.probeDraftSession.setHasUnappliedChanges(
            ProbeDraftComparisonPolicy.hasMeaningfulNewDraft(
                current: meaningful,
                pristine: pristine
            )
        )
        #expect(model.hasPendingPlanChanges)
        #expect(
            TerminationPolicy.decision(
                hasUnsavedChanges: model.hasPendingPlanChanges
            ) == .requireDiscardConfirmation
        )
        model.probeDraftSession.setHasUnappliedChanges(
            ProbeDraftComparisonPolicy.hasMeaningfulNewDraft(
                current: pristine,
                pristine: pristine
            )
        )
        #expect(!model.hasPendingPlanChanges)
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
        firstWindowSession.name = "Unapplied left V1"
        firstWindowSession.targetId = "target-1"
        firstWindowSession.depth = "3.25"
        firstWindowSession.markSynchronized(with: context)
        #expect(firstWindowSession.hasUnappliedChanges)

        // Recreating ProjectSidebar after the red window closes receives this
        // same model-owned object instead of a fresh per-window @State draft.
        let reopenedWindowSession = model.probeDraftSession
        #expect(reopenedWindowSession === firstWindowSession)
        #expect(reopenedWindowSession.name == "Unapplied left V1")
        #expect(reopenedWindowSession.depth == "3.25")
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
        session.name = "Uncreated probe"
        session.targetId = "target-1"
        session.depth = "4"
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

        #expect(session.name.isEmpty)
        #expect(session.targetId.isEmpty)
        #expect(session.depth.isEmpty)
        #expect(session.axialRotation == "0")
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
        model.probeDraftSession.name = "Immediate unapplied edit"
        #expect(model.hasPendingPlanChanges)

        let destination = URL(fileURLWithPath: "/tmp/unreachable.mouseplan")
        #expect(!(await model.saveProject(to: destination)))
        #expect(
            model.projectOperationError
                == "Apply or revert the probe draft before saving the animal plan."
        )
        #expect(!(await model.openProject(at: destination)))
        #expect(
            model.projectOperationError
                == "Discard the probe draft before opening another animal plan."
        )
        #expect(model.probeDraftSession.name == "Immediate unapplied edit")
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
        model.probeDraftSession.name = "Discard on reconnect"
        #expect(model.hasPendingPlanChanges)

        await model.reconnect()

        #expect(model.probeDraftSession.name == "Discard on reconnect")
        #expect(model.hasUnappliedProbeDraftChanges)
        #expect(model.hasPendingPlanChanges)
        #expect(
            model.projectOperationError
                == "Discard the probe draft before reconnecting the planning service."
        )

        model.discardProbeDraftSession()
        await model.reconnect()

        #expect(model.probeDraftSession.name.isEmpty)
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

    @Test("Saved-plan target survives asynchronous project and target loading")
    func savedPlanTargetSynchronization() {
        #expect(ProbeDraftSelectionPolicy.targetId(
            selectedPlanTargetId: "saved-target",
            currentTargetId: "",
            availableTargetIds: []
        ) == "saved-target")
        #expect(ProbeDraftSelectionPolicy.targetId(
            selectedPlanTargetId: "saved-target",
            currentTargetId: "other-target",
            availableTargetIds: ["other-target", "saved-target"]
        ) == "saved-target")
    }

    @Test("New probe draft chooses a usable implant target")
    func newDraftTargetSynchronization() {
        #expect(ProbeDraftSelectionPolicy.targetId(
            selectedPlanTargetId: nil,
            currentTargetId: "target-2",
            availableTargetIds: ["target-1", "target-2"]
        ) == "target-2")
        #expect(ProbeDraftSelectionPolicy.targetId(
            selectedPlanTargetId: nil,
            currentTargetId: "",
            availableTargetIds: ["target-1", "target-2"]
        ) == "target-1")
    }

    @Test("Placement modes require only the fields defined by their backend contract")
    func placementModeFields() {
        #expect(blocker(
            mode: .entryAndTarget,
            entryAP: "-1.25",
            entryML: "-0.8",
            entryDV: "-2.4",
            azimuth: "",
            elevation: "",
            depth: ""
        ) == nil)
        #expect(blocker(
            mode: .entryAndTarget,
            entryAP: "",
            entryML: "-0.8",
            entryDV: "-2.4",
            azimuth: "",
            elevation: "",
            depth: ""
        ) == "Enter valid entry AP, ML, and DV values in millimetres.")
        #expect(blocker(
            mode: .entryAnglesDepth,
            entryAP: "-1.25",
            entryML: "-0.8",
            entryDV: "0",
            azimuth: "-12",
            elevation: "-35",
            depth: "4.2"
        ) == nil)
        #expect(blocker(
            mode: .targetAnglesDepth,
            entryAP: "",
            entryML: "",
            entryDV: "",
            azimuth: "-12",
            elevation: "-35",
            depth: "4.2"
        ) == nil)
    }

    @Test("Placement guidance names the coordinate or angle frame")
    func placementGuidance() {
        #expect(ProbePlacementGuidance.text(for: .entryAndTarget)
            .hasPrefix("Bregma frame:"))
        #expect(ProbePlacementGuidance.text(for: .entryAnglesDepth)
            .contains("calibrated subject stereotaxic AP/ML/DV"))
        #expect(ProbePlacementGuidance.text(for: .targetAnglesDepth)
            .contains("atlas AP/ML/DV after the active calibration transform"))
        #expect(ProbePlacementGuidance.text(for: .targetAnglesDepth)
            .contains("not manipulator angles"))
        #expect(ProbePlacementGuidance.text(for: .stereotaxicTargetManipulator)
            .contains("calibrated subject stereotaxic AP/ML/DV"))
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

    private func blocker(
        planningUnavailableReason: String? = nil,
        hasSelectedModel: Bool = true,
        availableTargetIds: [String] = ["target-1"],
        selectedTargetId: String = "target-1",
        name: String = "NP2 left V1",
        mode: ProbePlacementMode = .stereotaxicTargetManipulator,
        entryAP: String = "",
        entryML: String = "",
        entryDV: String = "",
        azimuth: String = "-12",
        elevation: String = "-35",
        depth: String = "4.2",
        axialRotation: String = "0",
        requiresAcknowledgement: Bool = true,
        acknowledgementGiven: Bool = true
    ) -> String? {
        ProbeDraftReadinessPolicy.blockingReason(
            planningUnavailableReason: planningUnavailableReason,
            hasSelectedModel: hasSelectedModel,
            availableTargetIds: availableTargetIds,
            selectedTargetId: selectedTargetId,
            name: name,
            mode: mode,
            entryAP: entryAP,
            entryML: entryML,
            entryDV: entryDV,
            azimuth: azimuth,
            elevation: elevation,
            depth: depth,
            axialRotation: axialRotation,
            requiresAcknowledgement: requiresAcknowledgement,
            acknowledgementGiven: acknowledgementGiven
        )
    }

    private func draft(
        modelId: String = ProbePlanningContract.neuropixels2SingleShankModelId,
        modelVersion: String = ProbePlanningContract.neuropixels2ModelVersion,
        name: String = "NPX2 left V1",
        targetId: String = "target-1",
        mode: ProbePlacementMode = .stereotaxicTargetManipulator,
        entryAP: String = "",
        entryML: String = "",
        entryDV: String = "",
        azimuth: String = "0",
        elevation: String = "-90",
        depth: String = "3",
        axialRotation: String = "0",
        requiresAcknowledgement: Bool = true,
        acknowledgementGiven: Bool = true
    ) -> ProbeEditableDraftSnapshot? {
        ProbeDraftComparisonPolicy.snapshot(
            modelId: modelId,
            modelVersion: modelVersion,
            name: name,
            targetId: targetId,
            mode: mode,
            entryAP: entryAP,
            entryML: entryML,
            entryDV: entryDV,
            azimuth: azimuth,
            elevation: elevation,
            depth: depth,
            axialRotation: axialRotation,
            requiresAcknowledgement: requiresAcknowledgement,
            acknowledgementGiven: acknowledgementGiven
        )
    }

    private func newDraft(
        modelId: String? = ProbePlanningContract.neuropixels2SingleShankModelId,
        modelVersion: String? = ProbePlanningContract.neuropixels2ModelVersion,
        name: String = "NPX2 1-shank · V1",
        targetId: String = "target-1",
        mode: ProbePlacementMode = .stereotaxicTargetManipulator,
        entryAP: String = "",
        entryML: String = "",
        entryDV: String = "",
        azimuth: String = "",
        elevation: String = "",
        depth: String = "",
        axialRotation: String = "0",
        geometryAcknowledged: Bool = false
    ) -> ProbeNewDraftSnapshot {
        ProbeDraftComparisonPolicy.newDraftSnapshot(
            modelId: modelId,
            modelVersion: modelVersion,
            name: name,
            targetId: targetId,
            mode: mode,
            entryAP: entryAP,
            entryML: entryML,
            entryDV: entryDV,
            azimuth: azimuth,
            elevation: elevation,
            depth: depth,
            axialRotation: axialRotation,
            geometryAcknowledged: geometryAcknowledged
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
