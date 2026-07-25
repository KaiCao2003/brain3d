import Brain3DCore
import Foundation
import SwiftUI

enum ProbePlacementGuidance {
    static func text(for mode: ProbePlacementMode) -> String {
        switch mode {
        case .entryAndTarget:
            "Bregma frame: entry and selected target define the trajectory; angles and depth are derived."
        case .entryAnglesDepth:
            "Angle frame: calibrated subject stereotaxic AP/ML/DV. Entry is bregma-relative."
        case .targetAnglesDepth:
            "Angle frame: atlas AP/ML/DV after the active calibration transform, "
                + "not manipulator angles. The selected target is bregma-relative."
        case .stereotaxicTargetManipulator:
            "Angle frame: calibrated subject stereotaxic AP/ML/DV. The selected target is bregma-relative."
        }
    }
}

enum ProbeCatalogPresentation {
    static func containsNeuropixels2(_ models: [ProbeCatalogModel]) -> Bool {
        models.contains { model in
            isNeuropixels2(modelId: model.modelId)
        }
    }

    static func isNeuropixels2(modelId: String) -> Bool {
        modelId == ProbePlanningContract.neuropixels2SingleShankModelId
            || modelId == ProbePlanningContract.neuropixels2StandardFourShankModelId
    }

    static func simultaneousChannelCount(modelId: String) -> Int? {
        switch modelId {
        case ProbePlanningContract.neuropixels2SingleShankModelId:
            ProbePlanningContract.neuropixels2SingleShankSimultaneousChannelCount
        case ProbePlanningContract.neuropixels2StandardFourShankModelId:
            ProbePlanningContract.neuropixels2StandardFourShankSimultaneousChannelCount
        default:
            nil
        }
    }
}

enum ProbeOverlayPresentation {
    private static let sliceOverlayText =
        "Overlay active in Dorsal, Coronal, Sagittal, and Horizontal."

    static func text(
        threeDimensionalPhase: ThreeDimensionalLoadPhase,
        sceneContainsCurrentPlan: Bool
    ) -> String {
        if threeDimensionalPhase == .ready, sceneContainsCurrentPlan {
            return "Overlay active in Dorsal, Coronal, Sagittal, Horizontal, and 3D."
        }
        switch threeDimensionalPhase {
        case .unavailable, .failed:
            return "\(sliceOverlayText) 3D overlay unavailable."
        case .loadingDescriptor, .loadingGeometry:
            return "\(sliceOverlayText) 3D overlay pending."
        case .ready:
            return "\(sliceOverlayText) 3D overlay pending scene refresh."
        }
    }
}

enum ProbeDraftReadinessPolicy {
    static func blockingReason(
        planningUnavailableReason: String?,
        hasSelectedModel: Bool,
        availableTargetIds: [String],
        selectedTargetId: String,
        name: String,
        mode: ProbePlacementMode,
        entryAP: String,
        entryML: String,
        entryDV: String,
        azimuth: String,
        elevation: String,
        depth: String,
        axialRotation: String,
        requiresAcknowledgement: Bool,
        acknowledgementGiven: Bool
    ) -> String? {
        if let planningUnavailableReason {
            return planningUnavailableReason
        }
        guard hasSelectedModel else {
            return "Select a probe model from the connected catalog."
        }
        guard availableTargetIds.contains(selectedTargetId) else {
            return "Select a stored implant target."
        }
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return "Enter a probe plan name."
        }
        if mode.requiresEntryCoordinates {
            guard validNumber(entryAP), validNumber(entryML), validNumber(entryDV) else {
                return "Enter valid entry AP, ML, and DV values in millimetres."
            }
        }
        if mode.requiresAnglesAndDepth {
            guard validNumber(azimuth, range: -180 ... 180) else {
                return "Enter azimuth from −180° through 180°."
            }
            guard validNumber(elevation, range: -90 ... 90) else {
                return "Enter elevation from −90° through 90°."
            }
            guard validNumber(depth, strictlyPositive: true) else {
                return "Enter a positive insertion depth in millimetres."
            }
        }
        guard validNumber(axialRotation, range: -180 ... 180) else {
            return "Enter axial rotation from −180° through 180°."
        }
        guard !requiresAcknowledgement || acknowledgementGiven else {
            return "Acknowledge the selected probe geometry before continuing."
        }
        return nil
    }

    private static func validNumber(
        _ text: String,
        range: ClosedRange<Double>? = nil,
        strictlyPositive: Bool = false
    ) -> Bool {
        guard let value = try? CalibrationNumberInput.parse(text, field: "Probe value")
        else { return false }
        if let range, !range.contains(value) { return false }
        return !strictlyPositive || value > 0
    }
}

struct ProbeEditableDraftSnapshot: Equatable, Sendable {
    let modelId: String
    let modelVersion: String
    let name: String
    let targetId: String
    let mode: ProbePlacementMode
    let entryAPMillimetres: Double?
    let entryMLMillimetres: Double?
    let entryDVMillimetres: Double?
    let azimuthDegrees: Double?
    let elevationDegrees: Double?
    let insertionDepthMicrometres: Double?
    let axialRotationDegrees: Double
    let geometryAcknowledged: Bool?
}

struct ProbeDraftModelIdentity: Equatable, Sendable {
    let modelId: String
    let modelVersion: String
}

struct ProbeNewDraftSnapshot: Equatable, Sendable {
    let model: ProbeDraftModelIdentity?
    let name: String
    let targetId: String
    let mode: ProbePlacementMode
    let entryAP: String
    let entryML: String
    let entryDV: String
    let azimuth: String
    let elevation: String
    let depth: String
    let axialRotation: String
    let geometryAcknowledged: Bool
}

struct ProbeDraftContext: Equatable, Sendable {
    let projectId: String?
    let planId: String?
    let planInputSha256: String?
}

enum ProbeDraftSynchronizationPolicy {
    static func shouldReplaceDraft(
        existingContext: ProbeDraftContext?,
        incomingContext: ProbeDraftContext,
        hasUnappliedChanges: Bool
    ) -> Bool {
        guard existingContext != incomingContext else { return false }
        return existingContext == nil || !hasUnappliedChanges
    }
}

@MainActor
final class ProbeDraftSession: ObservableObject {
    @Published var name = "" { didSet { noteEditableMutation() } }
    @Published var targetId = "" { didSet { noteEditableMutation() } }
    @Published var placementMode: ProbePlacementMode = .stereotaxicTargetManipulator {
        didSet { noteEditableMutation() }
    }
    @Published var entryAP = "" { didSet { noteEditableMutation() } }
    @Published var entryML = "" { didSet { noteEditableMutation() } }
    @Published var entryDV = "" { didSet { noteEditableMutation() } }
    @Published var azimuth = "" { didSet { noteEditableMutation() } }
    @Published var elevation = "" { didSet { noteEditableMutation() } }
    @Published var depth = "" { didSet { noteEditableMutation() } }
    @Published var axialRotation = "0" { didSet { noteEditableMutation() } }
    @Published var geometryAcknowledged = false {
        didSet { noteEditableMutation() }
    }
    @Published private(set) var hasUnappliedChanges = false
    @Published private(set) var editableRevision = 0

    var pristineNewDraft: ProbeNewDraftSnapshot?
    var pendingExplicitNewModel: ProbeDraftModelIdentity?
    private(set) var synchronizedContext: ProbeDraftContext?

    func setHasUnappliedChanges(_ hasChanges: Bool) {
        guard hasUnappliedChanges != hasChanges else { return }
        hasUnappliedChanges = hasChanges
    }

    private func noteEditableMutation() {
        editableRevision &+= 1
        setHasUnappliedChanges(true)
    }

    func markSynchronized(with context: ProbeDraftContext) {
        synchronizedContext = context
    }

    func discard() {
        name = ""
        targetId = ""
        placementMode = .stereotaxicTargetManipulator
        entryAP = ""
        entryML = ""
        entryDV = ""
        azimuth = ""
        elevation = ""
        depth = ""
        axialRotation = "0"
        geometryAcknowledged = false
        pristineNewDraft = nil
        pendingExplicitNewModel = nil
        synchronizedContext = nil
        setHasUnappliedChanges(false)
    }
}

enum ProbeDraftComparisonPolicy {
    static func snapshot(
        modelId: String,
        modelVersion: String,
        name: String,
        targetId: String,
        mode: ProbePlacementMode,
        entryAP: String,
        entryML: String,
        entryDV: String,
        azimuth: String,
        elevation: String,
        depth: String,
        axialRotation: String,
        requiresAcknowledgement: Bool,
        acknowledgementGiven: Bool
    ) -> ProbeEditableDraftSnapshot? {
        let entryAPValue = mode.requiresEntryCoordinates ? number(entryAP) : nil
        let entryMLValue = mode.requiresEntryCoordinates ? number(entryML) : nil
        let entryDVValue = mode.requiresEntryCoordinates ? number(entryDV) : nil
        let azimuthValue = mode.requiresAnglesAndDepth ? number(azimuth) : nil
        let elevationValue = mode.requiresAnglesAndDepth ? number(elevation) : nil
        let depthMillimetres = mode.requiresAnglesAndDepth ? number(depth) : nil
        guard (!mode.requiresEntryCoordinates
                || (entryAPValue != nil && entryMLValue != nil && entryDVValue != nil)),
              (!mode.requiresAnglesAndDepth
                || (azimuthValue != nil
                    && elevationValue != nil
                    && depthMillimetres != nil)),
              let axialRotationValue = number(axialRotation)
        else {
            return nil
        }
        return ProbeEditableDraftSnapshot(
            modelId: modelId,
            modelVersion: modelVersion,
            name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            targetId: targetId,
            mode: mode,
            entryAPMillimetres: canonical(entryAPValue),
            entryMLMillimetres: canonical(entryMLValue),
            entryDVMillimetres: canonical(entryDVValue),
            azimuthDegrees: canonical(azimuthValue),
            elevationDegrees: canonical(elevationValue),
            insertionDepthMicrometres: canonical(
                depthMillimetres.map(ProbeInputUnits.micrometres)
            ),
            axialRotationDegrees: canonical(axialRotationValue),
            geometryAcknowledged: requiresAcknowledgement
                ? acknowledgementGiven
                : nil
        )
    }

    static func savedSnapshot(
        plan: ProbePlanDetail
    ) -> ProbeEditableDraftSnapshot {
        let draft = plan.placementDraft
        let requiresAcknowledgement =
            ProbePlanningContract.requiresExplicitAcknowledgement(
                verificationStatus: plan.verificationStatus
            )
        return ProbeEditableDraftSnapshot(
            modelId: plan.modelId,
            modelVersion: plan.modelVersion,
            name: plan.name.trimmingCharacters(in: .whitespacesAndNewlines),
            targetId: plan.targetId,
            mode: draft.mode,
            entryAPMillimetres: canonical(draft.entryAPMillimetres),
            entryMLMillimetres: canonical(draft.entryMLMillimetres),
            entryDVMillimetres: canonical(draft.entryDVMillimetres),
            azimuthDegrees: canonical(draft.azimuthDegrees),
            elevationDegrees: canonical(draft.elevationDegrees),
            insertionDepthMicrometres: canonical(
                draft.insertionDepthMicrometres
            ),
            axialRotationDegrees: canonical(draft.axialRotationDegrees),
            geometryAcknowledged: requiresAcknowledgement ? true : nil
        )
    }

    static func hasUnappliedEdits(
        current: ProbeEditableDraftSnapshot?,
        saved: ProbeEditableDraftSnapshot
    ) -> Bool {
        current != saved
    }

    static func modelIdentityToRestore(
        currentModelId: String?,
        currentModelVersion: String?,
        saved: ProbeEditableDraftSnapshot
    ) -> ProbeDraftModelIdentity? {
        let savedIdentity = ProbeDraftModelIdentity(
            modelId: saved.modelId,
            modelVersion: saved.modelVersion
        )
        guard currentModelId != savedIdentity.modelId
            || currentModelVersion != savedIdentity.modelVersion
        else {
            return nil
        }
        return savedIdentity
    }

    static func newDraftSnapshot(
        modelId: String?,
        modelVersion: String?,
        name: String,
        targetId: String,
        mode: ProbePlacementMode,
        entryAP: String,
        entryML: String,
        entryDV: String,
        azimuth: String,
        elevation: String,
        depth: String,
        axialRotation: String,
        geometryAcknowledged: Bool
    ) -> ProbeNewDraftSnapshot {
        let model: ProbeDraftModelIdentity? = if let modelId, let modelVersion {
            ProbeDraftModelIdentity(
                modelId: modelId,
                modelVersion: modelVersion
            )
        } else {
            nil
        }
        return ProbeNewDraftSnapshot(
            model: model,
            name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            targetId: targetId,
            mode: mode,
            entryAP: normalizedNumber(entryAP),
            entryML: normalizedNumber(entryML),
            entryDV: normalizedNumber(entryDV),
            azimuth: normalizedNumber(azimuth),
            elevation: normalizedNumber(elevation),
            depth: normalizedNumber(depth),
            axialRotation: normalizedNumber(axialRotation),
            geometryAcknowledged: geometryAcknowledged
        )
    }

    static func hasMeaningfulNewDraft(
        current: ProbeNewDraftSnapshot,
        pristine: ProbeNewDraftSnapshot?
    ) -> Bool {
        guard let pristine else { return false }
        return current != pristine
    }

    private static func number(_ text: String) -> Double? {
        try? CalibrationNumberInput.parse(text, field: "Probe value")
    }

    private static func normalizedNumber(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "" }
        guard let value = number(trimmed) else { return "invalid:\(trimmed)" }
        let canonicalValue = canonical(value)
        return "number:\(canonicalValue == 0 ? 0 : canonicalValue)"
    }

    private static func canonical(_ value: Double?) -> Double? {
        value.map(canonical)
    }

    private static func canonical(_ value: Double) -> Double {
        (value * 1_000_000).rounded() / 1_000_000
    }
}

enum ProbeInputUnits {
    static let micrometresPerMillimetre = 1_000.0

    static func micrometres(fromMillimetres value: Double) -> Double {
        value * micrometresPerMillimetre
    }

    static func millimetres(fromMicrometres value: Double) -> Double {
        value / micrometresPerMillimetre
    }
}

enum ProbeDraftSelectionPolicy {
    static func targetId(
        selectedPlanTargetId: String?,
        currentTargetId: String,
        availableTargetIds: [String]
    ) -> String {
        if let selectedPlanTargetId {
            return selectedPlanTargetId
        }
        if availableTargetIds.contains(currentTargetId) {
            return currentTargetId
        }
        return availableTargetIds.first ?? ""
    }
}

struct ProjectSidebar: View {
    @ObservedObject var model: PlannerViewModel
    @ObservedObject var draft: ProbeDraftSession
    let saveProject: () -> Void
    let openProject: () -> Void
    let reconnect: () -> Void
    @State private var targetLabel = "Implant site 1"
    @State private var targetAPMillimetres = ""
    @State private var targetMLMillimetres = ""
    @State private var targetDVMillimetres = ""
    @State private var showingCalibrationSheet = false
    @State private var confirmingProbeRemoval = false
    @State private var showingSurgeryPlanExport = false

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    projectSection
                    implantTargetSection
                    probeSection
                    majorVesselsSection
                }
                .padding(16)
            }
        }
        .background(.thinMaterial)
        .sheet(isPresented: $showingCalibrationSheet) {
            CalibrationSheet(model: model)
        }
        .sheet(isPresented: $showingSurgeryPlanExport) {
            SurgeryPlanExportSheet(
                model: model,
                hasUnappliedProbeEdits: hasUnappliedProbeEdits
            )
        }
        .confirmationDialog(
            "Remove this probe plan?",
            isPresented: $confirmingProbeRemoval,
            titleVisibility: .visible
        ) {
            Button("Remove Probe Plan", role: .destructive) {
                Task {
                    if await model.removeSelectedProbePlan() {
                        prepareNewProbeDraft()
                    }
                }
            }
            Button("Cancel", role: .cancel) {}
        }
        .onChange(of: model.selectedProbePlan?.planId, initial: true) {
            _, _ in
            synchronizeProbeDraft()
        }
        .onChange(of: model.selectedProbePlan?.inputSha256) {
            _, _ in
            synchronizeProbeDraft()
        }
        .onChange(of: model.backendState?.project?.projectId) { _, _ in
            clearTargetDraft()
            synchronizeProbeDraft()
        }
        .onChange(of: model.implantTargets.map(\.targetId), initial: true) {
            _, targetIds in
            let retainedDirtyDraft =
                draft.hasUnappliedChanges || hasUnappliedProbeEdits
            let wasPristineNewDraft = model.selectedProbePlan == nil
                && !retainedDirtyDraft
            if !retainedDirtyDraft {
                draft.targetId = ProbeDraftSelectionPolicy.targetId(
                    selectedPlanTargetId: model.selectedProbePlan?.targetId,
                    currentTargetId: draft.targetId,
                    availableTargetIds: targetIds
                )
                if model.selectedProbePlan == nil {
                    fillSuggestedProbeNameIfNeeded()
                }
            }
            if targetCoordinatesAreBlank {
                targetLabel = nextTargetLabel
            }
            if wasPristineNewDraft {
                draft.pristineNewDraft = currentNewProbeDraftSnapshot
                draft.setHasUnappliedChanges(false)
            }
        }
        .onChange(of: model.selectedProbeModel?.id, initial: true) { _, _ in
            let selectedIdentity = model.selectedProbeModel.map {
                ProbeDraftModelIdentity(
                    modelId: $0.modelId,
                    modelVersion: $0.modelVersion
                )
            }
            let isExplicitNewDraftSelection =
                model.selectedProbePlan == nil
                    && draft.pendingExplicitNewModel == selectedIdentity
            let retainedDirtyDraft = draft.hasUnappliedChanges
            let wasPristineNewDraft = model.selectedProbePlan == nil
                && !isExplicitNewDraftSelection
                && (!hasUnappliedProbeEdits || draft.pristineNewDraft?.model == nil)
                && !retainedDirtyDraft
            if !retainedDirtyDraft || isExplicitNewDraftSelection {
                fillSuggestedProbeNameIfNeeded()
            }
            if wasPristineNewDraft {
                draft.pristineNewDraft = currentNewProbeDraftSnapshot
                draft.setHasUnappliedChanges(false)
            }
            if isExplicitNewDraftSelection {
                draft.pendingExplicitNewModel = nil
            }
        }
        .onChange(of: hasUnappliedProbeEdits, initial: true) { _, hasChanges in
            draft.setHasUnappliedChanges(hasChanges)
            if !hasChanges {
                synchronizeProbeDraft()
            }
        }
        .onChange(of: draft.editableRevision) { _, _ in
            let hasChanges = hasUnappliedProbeEdits
            draft.setHasUnappliedChanges(hasChanges)
            if !hasChanges {
                synchronizeProbeDraft()
            }
        }
    }

    private var probeSection: some View {
        SidebarSection(title: "Neuropixels 2.0", systemImage: "line.diagonal.arrow") {
            Picker("Plan", selection: probePlanSelection) {
                Text("New plan").tag("")
                ForEach(model.probePlans) { plan in
                    Text(plan.name).tag(plan.planId)
                }
            }
            .disabled(model.probeOperationInProgress || hasUnappliedProbeEdits)
            .help(
                hasUnappliedProbeEdits
                    ? model.selectedProbePlan == nil
                        ? "Create or discard the current draft before switching plans."
                        : "Apply or revert the current edits before switching plans."
                    : "Choose an existing plan or start a new plan."
            )
            .accessibilityLabel("Probe plan")

            Picker("Probe", selection: probeModelSelection) {
                if supportedProbeCatalog.isEmpty {
                    Text("NPX2 unavailable").tag("")
                } else if model.selectedProbePlan != nil,
                          model.selectedProbeModel == nil
                {
                    Text("Archived model (read-only)").tag("")
                }
                ForEach(supportedProbeCatalog) { probe in
                    Text(probePickerLabel(probe)).tag(probe.id)
                }
            }
            .disabled(
                supportedProbeCatalog.isEmpty
                    || model.probeOperationInProgress
                    || (model.selectedProbePlan != nil && model.selectedProbeModel == nil)
            )
            .accessibilityHint("Choose the NPX2 single- or four-shank geometry.")

            if let plan = model.selectedProbePlan,
               model.selectedProbeModel == nil
            {
                Label(
                    "\(plan.modelDisplayName) is archived and read-only.",
                    systemImage: "archivebox"
                )
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }

            Picker("Implant site", selection: $draft.targetId) {
                Text("Choose a site").tag("")
                ForEach(model.implantTargets) { target in
                    Text(target.label).tag(target.targetId)
                }
            }
            .disabled(model.implantTargets.isEmpty || model.probeOperationInProgress)
            .accessibilityHint("Uses the selected bregma-relative AP, ML, and DV site.")

            TextField("Plan name", text: $draft.name)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel("Probe plan name")

            if draft.placementMode.requiresEntryCoordinates {
                Label("Legacy entry-based plan", systemImage: "archivebox")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                probeEntryCoordinateFields
            }

            if draft.placementMode.requiresAnglesAndDepth {
                probeAngleAndDepthFields
            }

            if let probe = model.selectedProbeModel,
               probe.requiresExplicitAcknowledgement
            {
                Label("Verify the selected NPX2 geometry before animal use.",
                      systemImage: "exclamationmark.triangle")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.orange)
                Toggle(
                    "Geometry checked",
                    isOn: $draft.geometryAcknowledged
                )
                .font(.caption)
            }

            HStack {
                if model.selectedProbePlan == nil {
                    Button("Create plan", systemImage: "plus") {
                        Task { _ = await createProbePlan() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSubmitProbeDraft)
                    .help(
                        probeDraftBlockingReason
                            ?? "Create this NPX2 plan."
                    )
                    if hasUnappliedProbeEdits {
                        Button("Discard draft", systemImage: "xmark") {
                            discardNewProbeDraft()
                        }
                        .help("Clear this uncreated probe plan and restore its defaults.")
                    }
                } else {
                    Button("Apply changes", systemImage: "checkmark") {
                        Task { _ = await updateProbePlan() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSubmitProbeDraft)
                    .help(
                        probeDraftBlockingReason
                            ?? "Apply these values to the NPX2 overlays and PDF."
                    )
                    if hasUnappliedProbeEdits {
                        Button("Revert", systemImage: "arrow.uturn.backward") {
                            Task { await revertProbeDraft() }
                        }
                        .help("Restore the last applied probe values.")
                    }
                    Button("Remove", systemImage: "trash", role: .destructive) {
                        confirmingProbeRemoval = true
                    }
                    .disabled(!model.canRemoveSelectedProbePlan)
                }
            }
            .controlSize(.small)

            if model.backendState?.project != nil,
               let probeDraftBlockingReason
            {
                Text(probeDraftBlockingReason)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("Cannot submit probe plan")
                    .accessibilityValue(probeDraftBlockingReason)
            }

            if hasUnappliedProbeEdits {
                Label(
                    model.selectedProbePlan == nil
                        ? "Uncreated probe draft — create the plan or discard it before "
                            + "opening, reconnecting, or quitting."
                        : "Unapplied probe edits — brain views and PDF still use the last "
                            + "applied values.",
                    systemImage: "exclamationmark.triangle.fill"
                )
                .font(.caption.weight(.semibold))
                .foregroundStyle(.orange)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityLabel("Unapplied probe edits")
                .accessibilityValue(
                    model.selectedProbePlan == nil
                        ? "Create or clear this draft before leaving the current plan."
                        : "Apply or revert changes before exporting the surgery plan."
                )
            }

            if let plan = model.selectedProbePlan {
                if plan.requiresPlanningGeometryUpdate {
                    Label(
                        "Review this older plan, then choose Update.",
                        systemImage: "arrow.triangle.2.circlepath"
                    )
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
                }
            }

            if model.probeOperationInProgress {
                ProgressView("Updating probe…")
                    .controlSize(.small)
            }
            if let error = model.probeOperationError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var probePlanSelection: Binding<String> {
        Binding(
            get: { model.selectedProbePlanId ?? "" },
            set: { planId in
                if planId.isEmpty {
                    Task {
                        _ = await model.selectProbePlan(nil)
                        prepareNewProbeDraft()
                    }
                } else if planId != model.selectedProbePlanId {
                    Task {
                        if await model.selectProbePlan(planId) {
                            populateProbeDraft()
                        }
                    }
                }
            }
        )
    }

    private var probeModelSelection: Binding<String> {
        Binding(
            get: { model.selectedProbeModel?.id ?? "" },
            set: { identity in
                guard let probe = model.probeCatalog.first(where: { $0.id == identity }) else {
                    return
                }
                let requestedIdentity = ProbeDraftModelIdentity(
                    modelId: probe.modelId,
                    modelVersion: probe.modelVersion
                )
                if model.selectedProbePlan == nil {
                    draft.pendingExplicitNewModel = requestedIdentity
                }
                Task {
                    let loaded = await model.loadProbeModel(
                        modelId: probe.modelId,
                        modelVersion: probe.modelVersion
                    )
                    if !loaded, draft.pendingExplicitNewModel == requestedIdentity {
                        draft.pendingExplicitNewModel = nil
                    }
                    draft.geometryAcknowledged = false
                }
            }
        )
    }

    private var canSubmitProbeDraft: Bool {
        probeDraftBlockingReason == nil
    }

    private var hasUnappliedProbeEdits: Bool {
        guard let plan = model.selectedProbePlan else {
            return ProbeDraftComparisonPolicy.hasMeaningfulNewDraft(
                current: currentNewProbeDraftSnapshot,
                pristine: draft.pristineNewDraft
            )
        }
        let selectedModel = model.selectedProbeModel
        let current = ProbeDraftComparisonPolicy.snapshot(
            modelId: selectedModel?.modelId ?? plan.modelId,
            modelVersion: selectedModel?.modelVersion ?? plan.modelVersion,
            name: draft.name,
            targetId: draft.targetId,
            mode: draft.placementMode,
            entryAP: draft.entryAP,
            entryML: draft.entryML,
            entryDV: draft.entryDV,
            azimuth: draft.azimuth,
            elevation: draft.elevation,
            depth: draft.depth,
            axialRotation: draft.axialRotation,
            requiresAcknowledgement:
                selectedModel?.requiresExplicitAcknowledgement
                    ?? ProbePlanningContract.requiresExplicitAcknowledgement(
                        verificationStatus: plan.verificationStatus
                    ),
            acknowledgementGiven: draft.geometryAcknowledged
        )
        return ProbeDraftComparisonPolicy.hasUnappliedEdits(
            current: current,
            saved: ProbeDraftComparisonPolicy.savedSnapshot(plan: plan)
        )
    }

    private var currentNewProbeDraftSnapshot: ProbeNewDraftSnapshot {
        ProbeDraftComparisonPolicy.newDraftSnapshot(
            modelId: model.selectedProbeModel?.modelId,
            modelVersion: model.selectedProbeModel?.modelVersion,
            name: draft.name,
            targetId: draft.targetId,
            mode: draft.placementMode,
            entryAP: draft.entryAP,
            entryML: draft.entryML,
            entryDV: draft.entryDV,
            azimuth: draft.azimuth,
            elevation: draft.elevation,
            depth: draft.depth,
            axialRotation: draft.axialRotation,
            geometryAcknowledged: draft.geometryAcknowledged
        )
    }

    private var probeDraftBlockingReason: String? {
        ProbeDraftReadinessPolicy.blockingReason(
            planningUnavailableReason: model.probePlanningUnavailableReason,
            hasSelectedModel: model.selectedProbeModel != nil,
            availableTargetIds: model.implantTargets.map(\.targetId),
            selectedTargetId: draft.targetId,
            name: draft.name,
            mode: draft.placementMode,
            entryAP: draft.entryAP,
            entryML: draft.entryML,
            entryDV: draft.entryDV,
            azimuth: draft.azimuth,
            elevation: draft.elevation,
            depth: draft.depth,
            axialRotation: draft.axialRotation,
            requiresAcknowledgement: model.selectedProbeModel?
                .requiresExplicitAcknowledgement == true,
            acknowledgementGiven: draft.geometryAcknowledged
        )
    }

    private var supportedProbeCatalog: [ProbeCatalogModel] {
        model.probeCatalog.filter {
            ProbeCatalogPresentation.isNeuropixels2(modelId: $0.modelId)
        }
    }

    private func probePickerLabel(_ probe: ProbeCatalogModel) -> String {
        probe.shankCount == 1 ? "NPX2 1-shank" : "NPX2 4-shank"
    }

    private var probeAngleAndDepthFields: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Angles (°) · depth (mm)")
                .font(.caption.weight(.semibold))
            HStack(spacing: 7) {
                compactProbeNumberField(
                    "Azimuth",
                    text: $draft.azimuth,
                    accessibilityLabel: "Azimuth in degrees",
                    accessibilityHint: "Degrees from negative 180 through 180."
                )
                compactProbeNumberField(
                    "Elevation",
                    text: $draft.elevation,
                    accessibilityLabel: "Elevation in degrees",
                    accessibilityHint: "Degrees from negative 90 through 90."
                )
            }
            HStack(spacing: 7) {
                compactProbeNumberField(
                    "Depth",
                    text: $draft.depth,
                    accessibilityLabel: "Insertion depth in millimetres",
                    accessibilityHint: "Positive insertion depth in millimetres."
                )
                compactProbeNumberField(
                    "Roll",
                    text: $draft.axialRotation,
                    accessibilityLabel: "Axial rotation in degrees",
                    accessibilityHint: "Axial rotation in degrees."
                )
            }
        }
    }

    private var probeEntryCoordinateFields: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Entry from bregma (mm)")
                .font(.caption.weight(.semibold))
            HStack(spacing: 8) {
                compactProbeNumberField("AP", text: $draft.entryAP)
                compactProbeNumberField("ML", text: $draft.entryML)
                compactProbeNumberField("DV", text: $draft.entryDV)
            }
            Text(
                "+AP anterior · −AP posterior/back · +ML right · −ML left · "
                    + "+DV dorsal/up · −DV deep/ventral"
            )
            .font(.caption2)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func compactProbeNumberField(
        _ axis: String,
        text: Binding<String>,
        accessibilityLabel: String? = nil,
        accessibilityHint: String? = nil
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(axis)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            TextField("Required", text: text)
                .textFieldStyle(.roundedBorder)
                .multilineTextAlignment(.trailing)
                .accessibilityLabel(
                    accessibilityLabel ?? "Entry \(axis) in millimetres from bregma"
                )
                .accessibilityHint(
                    accessibilityHint ?? probeEntryAccessibilityHint(axis)
                )
        }
        .frame(maxWidth: .infinity)
    }

    private func probeEntryAccessibilityHint(_ axis: String) -> String {
        switch axis {
        case "AP":
            "Positive is anterior; negative is posterior or back."
        case "ML":
            "Positive is right; negative is left."
        case "DV":
            "Positive is dorsal or up; negative is deep or ventral."
        default:
            "Signed coordinate from bregma."
        }
    }

    private func createProbePlan() async -> Bool {
        guard let probe = model.selectedProbeModel else { return false }
        return await model.createProbePlan(
            name: draft.name,
            targetId: draft.targetId,
            modelId: probe.modelId,
            modelVersion: probe.modelVersion,
            placementMode: draft.placementMode,
            entryAPText: draft.entryAP,
            entryMLText: draft.entryML,
            entryDVText: draft.entryDV,
            azimuthText: draft.azimuth,
            elevationText: draft.elevation,
            insertionDepthText: draft.depth,
            axialRotationText: draft.axialRotation,
            customGeometryAcknowledged: draft.geometryAcknowledged
        )
    }

    private func updateProbePlan() async -> Bool {
        guard let probe = model.selectedProbeModel else { return false }
        return await model.updateSelectedProbePlan(
            name: draft.name,
            targetId: draft.targetId,
            modelId: probe.modelId,
            modelVersion: probe.modelVersion,
            placementMode: draft.placementMode,
            entryAPText: draft.entryAP,
            entryMLText: draft.entryML,
            entryDVText: draft.entryDV,
            azimuthText: draft.azimuth,
            elevationText: draft.elevation,
            insertionDepthText: draft.depth,
            axialRotationText: draft.axialRotation,
            customGeometryAcknowledged: draft.geometryAcknowledged
        )
    }

    private func revertProbeDraft() async {
        guard let plan = model.selectedProbePlan else { return }
        let saved = ProbeDraftComparisonPolicy.savedSnapshot(plan: plan)
        if let identity = ProbeDraftComparisonPolicy.modelIdentityToRestore(
            currentModelId: model.selectedProbeModel?.modelId ?? plan.modelId,
            currentModelVersion: model.selectedProbeModel?.modelVersion
                ?? plan.modelVersion,
            saved: saved
        ) {
            guard model.probeCatalog.contains(where: {
                $0.modelId == identity.modelId
                    && $0.modelVersion == identity.modelVersion
            }) else { return }
            guard await model.loadProbeModel(
                modelId: identity.modelId,
                modelVersion: identity.modelVersion
            ) else { return }
            guard model.selectedProbeModel?.modelId == identity.modelId,
                  model.selectedProbeModel?.modelVersion == identity.modelVersion
            else { return }
        }
        guard model.selectedProbePlan?.planId == plan.planId,
              model.selectedProbePlan?.inputSha256 == plan.inputSha256
        else { return }
        populateProbeDraft()
    }

    private func discardNewProbeDraft() {
        guard model.selectedProbePlan == nil else { return }
        draft.pendingExplicitNewModel = nil
        prepareNewProbeDraft()
        draft.setHasUnappliedChanges(false)
    }

    private func populateProbeDraft() {
        guard let plan = model.selectedProbePlan else { return }
        let placement = plan.placementDraft
        draft.name = plan.name
        draft.targetId = plan.targetId
        draft.placementMode = placement.mode
        draft.entryAP = placement.entryAPMillimetres.map(decimalText) ?? ""
        draft.entryML = placement.entryMLMillimetres.map(decimalText) ?? ""
        draft.entryDV = placement.entryDVMillimetres.map(decimalText) ?? ""
        draft.azimuth = placement.azimuthDegrees.map(decimalText) ?? ""
        draft.elevation = placement.elevationDegrees.map(decimalText) ?? ""
        draft.depth = placement.insertionDepthMicrometres.map {
            decimalText(ProbeInputUnits.millimetres(fromMicrometres: $0))
        } ?? ""
        draft.axialRotation = decimalText(placement.axialRotationDegrees)
        draft.geometryAcknowledged = ProbePlanningContract.requiresExplicitAcknowledgement(
            verificationStatus: plan.verificationStatus
        )
        draft.markSynchronized(with: currentProbeDraftContext)
        draft.setHasUnappliedChanges(false)
    }

    private func clearProbeDraft() {
        draft.name = ""
        draft.targetId = ""
        draft.placementMode = .stereotaxicTargetManipulator
        draft.entryAP = ""
        draft.entryML = ""
        draft.entryDV = ""
        draft.azimuth = ""
        draft.elevation = ""
        draft.depth = ""
        draft.axialRotation = "0"
        draft.geometryAcknowledged = false
    }

    private func prepareNewProbeDraft() {
        clearProbeDraft()
        draft.targetId = model.implantTargets.first?.targetId ?? ""
        fillSuggestedProbeNameIfNeeded()
        draft.pristineNewDraft = currentNewProbeDraftSnapshot
        draft.markSynchronized(with: currentProbeDraftContext)
        draft.setHasUnappliedChanges(false)
    }

    private func synchronizeProbeDraft() {
        let incomingContext = currentProbeDraftContext
        guard ProbeDraftSynchronizationPolicy.shouldReplaceDraft(
            existingContext: draft.synchronizedContext,
            incomingContext: incomingContext,
            hasUnappliedChanges: hasUnappliedProbeEdits
        ) else { return }
        if model.selectedProbePlan == nil {
            prepareNewProbeDraft()
        } else {
            populateProbeDraft()
        }
    }

    private var currentProbeDraftContext: ProbeDraftContext {
        ProbeDraftContext(
            projectId: model.backendState?.project?.projectId,
            planId: model.selectedProbePlan?.planId,
            planInputSha256: model.selectedProbePlan?.inputSha256
        )
    }

    private func fillSuggestedProbeNameIfNeeded() {
        guard model.selectedProbePlan == nil,
              draft.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let probe = model.selectedProbeModel,
              let siteLabel = model.implantTargets.first(where: {
                  $0.targetId == draft.targetId
              })?.label
        else { return }

        draft.name = "\(probePickerLabel(probe)) · \(siteLabel)"
    }

    private func clearTargetDraft() {
        targetLabel = nextTargetLabel
        targetAPMillimetres = ""
        targetMLMillimetres = ""
        targetDVMillimetres = ""
    }

    private var targetCoordinatesAreBlank: Bool {
        [targetAPMillimetres, targetMLMillimetres, targetDVMillimetres]
            .allSatisfy {
                $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            }
    }

    private var nextTargetLabel: String {
        "Implant site \(model.implantTargets.count + 1)"
    }

    private func decimalText(_ value: Double) -> String {
        String(format: "%.12g", value)
    }

    private var majorVesselsSection: some View {
        SidebarSection(title: "Major vessels", systemImage: "drop.triangle") {
            if model.majorVesselLoadInProgress {
                ProgressView("Loading vessels…")
                    .controlSize(.small)
            } else if let error = model.majorVesselLoadError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            } else if let source = model.majorVesselGeometry?.provenance {
                Label("Visible in every brain view", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                Text("VesSAP \(source.specimenId)")
                    .font(.caption)
                HStack(spacing: 14) {
                    if let recordURL = URL(string: source.sourceRecordUrl) {
                        Link("Dataset source", destination: recordURL)
                    }
                    if let paperURL = URL(
                        string: "https://doi.org/\(source.sourcePaperDoi)"
                    ) {
                        Link("Paper", destination: paperURL)
                    }
                }
                .font(.caption)
                Text("Reference anatomy—verify against the individual animal.")
                .font(.caption.weight(.medium))
                .foregroundStyle(.orange)
                .fixedSize(horizontal: false, vertical: true)
            } else {
                Label(model.majorVesselStatus, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
    }

    private var implantTargetSection: some View {
        SidebarSection(title: "Implant site", systemImage: "scope") {
            Text("From bregma (mm) · −AP back · −ML left · −DV deep")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(spacing: 7) {
                compactTargetField("AP", text: $targetAPMillimetres)
                compactTargetField("ML", text: $targetMLMillimetres)
                compactTargetField("DV", text: $targetDVMillimetres)
            }
            .disabled(!model.canStoreImplantTarget)
            HStack {
                Button("Add site", systemImage: "plus") {
                    Task {
                        let existingTargetIds = Set(model.implantTargets.map(\.targetId))
                        let added = await model.addUnprojectedImplantTarget(
                            label: targetLabel,
                            apText: targetAPMillimetres,
                            mlText: targetMLMillimetres,
                            dvText: targetDVMillimetres
                        )
                        if added {
                            let addedTargetId = model.implantTargets.first {
                                !existingTargetIds.contains($0.targetId)
                            }?.targetId ?? ""
                            draft.targetId = addedTargetId
                            if !addedTargetId.isEmpty, model.activeCalibration != nil {
                                _ = await model.projectImplantTarget(
                                    targetId: addedTargetId
                                )
                            }
                            clearTargetDraft()
                            fillSuggestedProbeNameIfNeeded()
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(
                    !model.canStoreImplantTarget
                        || targetLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || targetAPMillimetres.trimmingCharacters(in: .whitespacesAndNewlines)
                            .isEmpty
                        || targetMLMillimetres.trimmingCharacters(in: .whitespacesAndNewlines)
                            .isEmpty
                        || targetDVMillimetres.trimmingCharacters(in: .whitespacesAndNewlines)
                            .isEmpty
                )
                if model.activeCalibration == nil {
                    Button("Set up atlas mapping…", systemImage: "ruler") {
                        showingCalibrationSheet = true
                    }
                    .buttonStyle(.bordered)
                    .disabled(!model.canManageCalibration)
                }
            }
            .controlSize(.small)
            if model.implantOperationInProgress {
                ProgressView("Updating site…")
                    .controlSize(.small)
            }
            if let error = model.implantOperationError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let error = model.calibrationOperationError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(model.implantTargets) { target in
                implantTargetCard(target)
            }
        }
    }

    private func implantTargetCard(_ target: UnprojectedImplantTarget) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(target.label)
                .font(.caption.weight(.semibold))
            Text(targetCoordinateSummary(target))
                .font(.caption2.monospacedDigit())
            HStack(spacing: 8) {
                if model.projection(for: target.targetId) != nil {
                    Button("Show", systemImage: "eye") {
                        Task {
                            await model.navigateToImplantTarget(targetId: target.targetId)
                        }
                    }
                    .help(
                        "Show this site in Dorsal, Coronal, Sagittal, Horizontal, and 3D views."
                    )
                } else if model.activeCalibration != nil {
                    Button("Project", systemImage: "scope") {
                        Task { _ = await model.projectImplantTarget(targetId: target.targetId) }
                    }
                    .disabled(model.calibrationOperationInProgress)
                }
                Spacer(minLength: 4)
                Button(role: .destructive) {
                    Task {
                        _ = await model.removeUnprojectedImplantTarget(
                            targetId: target.targetId
                        )
                    }
                } label: {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .disabled(model.implantOperationInProgress)
                .help("Remove this stored unprojected site")
                .accessibilityLabel("Remove \(target.label)")
            }
            .buttonStyle(.borderless)
            .controlSize(.small)
        }
        .padding(8)
        .background(.quaternary.opacity(0.7), in: RoundedRectangle(cornerRadius: 7))
        .accessibilityElement(children: .contain)
    }

    private func signed(_ value: Double) -> String {
        if value == 0 { return "0.000" }
        return String(format: "%+.3f", value)
    }

    private func targetCoordinateSummary(_ target: UnprojectedImplantTarget) -> String {
        "AP \(signed(target.apMillimetres)) · "
            + "ML \(signed(target.mlMillimetres)) · "
            + "DV \(signed(target.dvMillimetres)) mm"
    }

    private func compactTargetField(_ label: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            TextField("mm", text: text)
                .textFieldStyle(.roundedBorder)
                .multilineTextAlignment(.trailing)
                .accessibilityLabel("\(label) in millimetres from bregma")
        }
        .frame(maxWidth: .infinity)
    }

    private var projectSection: some View {
        SidebarSection(title: "Surgery plan", systemImage: "doc") {
            HStack {
                Button("Open", systemImage: "folder") { openProject() }
                    .disabled(!model.canOpenProject)
                Button("Save", systemImage: "square.and.arrow.down") {
                    saveProject()
                }
                .disabled(!model.canSaveProject || hasUnappliedProbeEdits)
                .help(
                    hasUnappliedProbeEdits
                        ? "Apply or revert probe edits before saving."
                        : "Save the current animal surgery plan."
                )
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            Button("Export PDF…", systemImage: "doc.richtext") {
                showingSurgeryPlanExport = true
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .frame(maxWidth: .infinity, alignment: .leading)
            .disabled(
                model.backendState?.project == nil
                    || model.implantTargets.isEmpty
                    || hasUnappliedProbeEdits
            )
            .help(
                hasUnappliedProbeEdits
                    ? "Apply or revert probe edits before exporting."
                    : "Create a prefilled protocol PDF with selected planning views "
                        + "and a matched Mouse Brain atlas plate."
            )
            if model.canDownloadAtlas {
                Button("Download atlas", systemImage: "arrow.down.circle") {
                    Task { await model.downloadAndOpenAtlas() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            }
            if !model.connection.isReady {
                HStack {
                    Label("Connection unavailable", systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                    Button("Retry") { reconnect() }
                        .disabled(model.connection == .connecting)
                }
            }
            if model.projectOperationInProgress {
                ProgressView("Working…")
                    .controlSize(.small)
            }
            if let error = model.projectOperationError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
            }
            if let notice = model.projectRecoveryNotice {
                Label(notice, systemImage: "externaldrive.badge.exclamationmark")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
    }

}

private struct SidebarSection<Content: View>: View {
    let title: String
    let systemImage: String
    @ViewBuilder let content: Content

    init(title: String, systemImage: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.systemImage = systemImage
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 7) {
                Image(systemName: systemImage)
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
                Text(title)
                    .font(.headline)
            }
            Divider()
            VStack(alignment: .leading, spacing: 9) {
                content
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(12)
        .background(.background.opacity(0.72), in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(Color.secondary.opacity(0.20))
        }
    }
}
