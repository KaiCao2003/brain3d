import AppKit
import Brain3DCore
import Foundation
import SwiftUI

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

enum ProbeSurfaceEditorField: String, CaseIterable, Equatable, Sendable {
    case model
    case ap
    case ml
    case surfaceDepth
    case anteriorPosteriorAngle
    case layoutRotation
}

enum ProbeSurfaceEditorPresentation {
    static let visibleFields = ProbeSurfaceEditorField.allCases
    static let apLabel = "AP (+A / −P)"
    static let mlLabel = "ML (+R / −L)"
    static let depthLabel = "Shank 1 depth from surface"
    static let angleLabel = "A↔P angle (+ A→P)"
    static let explicitActionTitle: String? = nil

    static func modelLabel(modelId: String) -> String? {
        switch modelId {
        case ProbePlanningContract.neuropixels2SingleShankModelId:
            "NP2003 · 1 shank"
        case ProbePlanningContract.neuropixels2StandardFourShankModelId:
            "NP2013 · 4 shank"
        default:
            nil
        }
    }
}

enum ProbeLayoutRotation: String, CaseIterable, Identifiable, Sendable {
    case sagittal = "0"
    case clockwise90 = "90"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .sagittal: "Sagittal"
        case .clockwise90: "90° CW"
        }
    }

    var accessibilityValue: String {
        switch self {
        case .sagittal:
            "The four-shank plane is parallel to sagittal; shank 1 is most anterior."
        case .clockwise90:
            "Rotated 90 degrees clockwise when viewed from dorsal; shank 1 is leftmost."
        }
    }
}

enum ProbeSurfaceDraftReadinessPolicy {
    static func blockingReason(
        planningUnavailableReason: String?,
        hasSelectedModel: Bool,
        ap: String,
        ml: String,
        surfaceDepth: String,
        anteriorPosteriorAngle: String,
        layoutRotation: String
    ) -> String? {
        if let planningUnavailableReason {
            return planningUnavailableReason
        }
        guard hasSelectedModel else {
            return "Choose NP2003 or NP2013."
        }
        guard validNumber(ap), validNumber(ml) else {
            return "Enter valid AP and ML coordinates in millimetres."
        }
        guard let depth = try? CalibrationNumberInput.parse(
            surfaceDepth,
            field: "Depth from surface"
        ),
            depth > 0,
            depth <= 10
        else {
            return "Enter a depth greater than 0 and no more than the 10 mm shank length."
        }
        guard validNumber(anteriorPosteriorAngle),
              let angle = try? CalibrationNumberInput.parse(
                  anteriorPosteriorAngle,
                  field: "A↔P angle"
              ),
              abs(angle) < 90
        else {
            return "Enter an A↔P angle greater than −90° and less than 90°."
        }
        guard ProbeLayoutRotation(rawValue: normalized(layoutRotation)) != nil else {
            return "Choose the sagittal or 90° clockwise probe layout."
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

    private static func normalized(_ text: String) -> String {
        guard let value = try? CalibrationNumberInput.parse(text, field: "Probe value")
        else { return text }
        return String(format: "%.12g", value == 0 ? 0 : value)
    }
}

enum ProbeSurfacePlanningAvailabilityPolicy {
    static func blockingReason(
        connectionReady: Bool,
        hasProject: Bool,
        atlasReady: Bool = true,
        serviceSupportsPlanning: Bool = true,
        projectOperationInProgress: Bool,
        probeOperationInProgress: Bool
    ) -> String? {
        if !connectionReady {
            return "Connect to the planning service."
        }
        if !hasProject {
            return "Open or create an animal plan."
        }
        if !atlasReady {
            return "Wait for the Allen atlas to finish opening."
        }
        if !serviceSupportsPlanning {
            return "The connected service does not support atlas-surface probe planning."
        }
        if projectOperationInProgress || probeOperationInProgress {
            return "Wait for the current plan operation to finish."
        }
        return nil
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

struct ProbeDraftModelIdentity: Equatable, Sendable {
    let modelId: String
    let modelVersion: String
}

struct ProbeSurfaceDraftSnapshot: Equatable, Sendable {
    let model: ProbeDraftModelIdentity?
    let ap: String
    let ml: String
    let surfaceDepthMM: String
    let sagittalAngle: String
    let layoutRotation: String
}

enum ProbeSurfaceDraftComparisonPolicy {
    static func snapshot(
        modelId: String?,
        modelVersion: String?,
        ap: String,
        ml: String,
        surfaceDepthMM: String,
        sagittalAngle: String,
        layoutRotation: String
    ) -> ProbeSurfaceDraftSnapshot {
        let model: ProbeDraftModelIdentity? = if let modelId, let modelVersion {
            ProbeDraftModelIdentity(modelId: modelId, modelVersion: modelVersion)
        } else {
            nil
        }
        return ProbeSurfaceDraftSnapshot(
            model: model,
            ap: normalizedNumber(ap),
            ml: normalizedNumber(ml),
            surfaceDepthMM: normalizedNumber(surfaceDepthMM),
            sagittalAngle: normalizedNumber(sagittalAngle),
            layoutRotation: normalizedNumber(layoutRotation)
        )
    }

    static func hasUnappliedEdits(
        current: ProbeSurfaceDraftSnapshot,
        baseline: ProbeSurfaceDraftSnapshot?
    ) -> Bool {
        guard let baseline else { return true }
        return current != baseline
    }

    private static func normalizedNumber(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "" }
        guard let value = try? CalibrationNumberInput.parse(
            trimmed,
            field: "Probe value"
        ) else {
            return "invalid:\(trimmed)"
        }
        let canonical = (value * 1_000_000).rounded() / 1_000_000
        return "number:\(canonical == 0 ? 0 : canonical)"
    }
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

enum ProbeSurfaceAutoCommitTrigger: Equatable, Sendable {
    case textChanged
    case textSubmitted
    case numericFocusLost
    case modelChanged
    case layoutChanged
    case planningBecameReady
}

enum ProbeSurfaceAutoCommitAction: Equatable, Sendable {
    case ignore
    case endNumericEditing
    case enqueueMutation
}

enum ProbeSurfaceAutoCommitPolicy {
    static func action(
        for trigger: ProbeSurfaceAutoCommitTrigger,
        numericFieldIsFocused: Bool
    ) -> ProbeSurfaceAutoCommitAction {
        switch trigger {
        case .textChanged:
            .ignore
        case .textSubmitted, .numericFocusLost:
            .enqueueMutation
        case .modelChanged, .layoutChanged:
            numericFieldIsFocused ? .endNumericEditing : .enqueueMutation
        case .planningBecameReady:
            numericFieldIsFocused ? .ignore : .enqueueMutation
        }
    }
}

struct ProbeSurfaceAutoCommitRequest: Equatable, Sendable {
    let model: ProbeDraftModelIdentity
    let ap: String
    let ml: String
    let surfaceDepthMM: String
    let sagittalAngle: String
    let layoutRotation: String
    let editableRevision: Int

    var snapshot: ProbeSurfaceDraftSnapshot {
        ProbeSurfaceDraftComparisonPolicy.snapshot(
            modelId: model.modelId,
            modelVersion: model.modelVersion,
            ap: ap,
            ml: ml,
            surfaceDepthMM: surfaceDepthMM,
            sagittalAngle: sagittalAngle,
            layoutRotation: layoutRotation
        )
    }
}

struct ProbeSurfaceAutoCommitTicket: Equatable, Sendable {
    let generation: Int
    let request: ProbeSurfaceAutoCommitRequest
}

struct ProbeSurfaceAutoCommitQueue: Equatable, Sendable {
    private(set) var newestGeneration = 0
    private(set) var inFlight: ProbeSurfaceAutoCommitTicket?
    private(set) var pending: ProbeSurfaceAutoCommitTicket?

    /// Keeps at most one request in flight and one latest pending request.
    /// Duplicate lifecycle notifications for the same edit do not trigger
    /// redundant bridge mutations.
    mutating func enqueue(_ request: ProbeSurfaceAutoCommitRequest) -> Bool {
        if pending?.request == request || (pending == nil && inFlight?.request == request) {
            return false
        }
        newestGeneration &+= 1
        pending = ProbeSurfaceAutoCommitTicket(
            generation: newestGeneration,
            request: request
        )
        return inFlight == nil
    }

    mutating func beginNext() -> ProbeSurfaceAutoCommitTicket? {
        guard inFlight == nil, let pending else { return nil }
        self.pending = nil
        inFlight = pending
        return pending
    }

    func isLatest(_ ticket: ProbeSurfaceAutoCommitTicket) -> Bool {
        ticket.generation == newestGeneration
    }

    @discardableResult
    mutating func complete(_ ticket: ProbeSurfaceAutoCommitTicket) -> Bool {
        guard inFlight == ticket else { return pending != nil }
        inFlight = nil
        return pending != nil
    }
}

enum ProbeSurfaceAutoCommitCompletionPolicy {
    static func mayPopulateDraft(
        completed request: ProbeSurfaceAutoCommitRequest,
        isLatestRequest: Bool,
        currentEditableRevision: Int,
        currentSnapshot: ProbeSurfaceDraftSnapshot
    ) -> Bool {
        isLatestRequest
            && currentEditableRevision == request.editableRevision
            && currentSnapshot == request.snapshot
    }
}

struct ProbeNumericEditingBoundary: Equatable, Sendable {
    private(set) var isEditing = false

    mutating func beginEditing() {
        isEditing = true
    }

    /// Returns true exactly once for each editing session. AppKit can deliver
    /// more than one end notification while a text field is being removed or
    /// its window is closing; only the first one is a probe commit boundary.
    mutating func consumeEndEditing() -> Bool {
        guard isEditing else { return false }
        isEditing = false
        return true
    }
}

@MainActor
final class ProbeSurfaceNumericEditingSession: ObservableObject {
    private weak var activeControl: NSTextField?
    private(set) var activeField: ProbeSurfaceEditorField?

    var isEditing: Bool {
        activeControl?.currentEditor() != nil
    }

    func beganEditing(
        field: ProbeSurfaceEditorField,
        control: NSTextField
    ) {
        activeField = field
        activeControl = control
    }

    func endedEditing(
        field: ProbeSurfaceEditorField,
        control: NSTextField
    ) {
        guard activeField == field, activeControl === control else { return }
        activeField = nil
        activeControl = nil
    }

    /// Ends the actual AppKit field-editor session synchronously. This is used
    /// before a segmented model/layout choice so its request can only be built
    /// after the final numeric text has crossed the same authoritative commit
    /// boundary as a pointer or Tab focus change.
    @discardableResult
    func endActiveEditing() -> Bool {
        guard let control = activeControl else {
            activeField = nil
            return false
        }
        guard control.currentEditor() != nil else {
            activeField = nil
            activeControl = nil
            return false
        }
        return control.window?.makeFirstResponder(nil) == true
    }
}

@MainActor
final class ProbeNumericTextFieldCoordinator: NSObject, NSTextFieldDelegate {
    private var text: Binding<String>
    private var onBeginEditing: (NSTextField) -> Void
    private var onEndEditing: (NSTextField) -> Void
    private var onCommit: () -> Void
    private var boundary = ProbeNumericEditingBoundary()

    init(
        text: Binding<String>,
        onBeginEditing: @escaping (NSTextField) -> Void,
        onEndEditing: @escaping (NSTextField) -> Void,
        onCommit: @escaping () -> Void
    ) {
        self.text = text
        self.onBeginEditing = onBeginEditing
        self.onEndEditing = onEndEditing
        self.onCommit = onCommit
    }

    func update(
        text: Binding<String>,
        onBeginEditing: @escaping (NSTextField) -> Void,
        onEndEditing: @escaping (NSTextField) -> Void,
        onCommit: @escaping () -> Void
    ) {
        self.text = text
        self.onBeginEditing = onBeginEditing
        self.onEndEditing = onEndEditing
        self.onCommit = onCommit
    }

    func controlTextDidBeginEditing(_ notification: Notification) {
        guard let control = notification.object as? NSTextField else { return }
        boundary.beginEditing()
        onBeginEditing(control)
    }

    func controlTextDidChange(_ notification: Notification) {
        guard let control = notification.object as? NSTextField else { return }
        let currentText = control.stringValue
        guard text.wrappedValue != currentText else { return }
        text.wrappedValue = currentText
    }

    func controlTextDidEndEditing(_ notification: Notification) {
        guard let control = notification.object as? NSTextField else { return }
        synchronizeText(from: control)
        guard boundary.consumeEndEditing() else { return }
        onEndEditing(control)
        onCommit()
    }

    func control(
        _ control: NSControl,
        textView: NSTextView,
        doCommandBy commandSelector: Selector
    ) -> Bool {
        guard commandSelector == #selector(NSResponder.insertNewline(_:))
                || commandSelector
                    == #selector(NSResponder.insertNewlineIgnoringFieldEditor(_:)),
              let textField = control as? NSTextField
        else {
            return false
        }
        synchronizeText(from: textField)
        if textField.window?.makeFirstResponder(nil) != true {
            finishEditing(textField)
        }
        return true
    }

    private func synchronizeText(from control: NSTextField) {
        let currentText = control.stringValue
        guard text.wrappedValue != currentText else { return }
        text.wrappedValue = currentText
    }

    private func finishEditing(_ control: NSTextField) {
        guard boundary.consumeEndEditing() else { return }
        onEndEditing(control)
        onCommit()
    }
}

struct ProbeSurfaceNumericTextField: NSViewRepresentable {
    @Binding var text: String
    let placeholder: String
    let accessibilityLabel: String
    let accessibilityHint: String
    let onBeginEditing: (NSTextField) -> Void
    let onEndEditing: (NSTextField) -> Void
    let onCommit: () -> Void

    func makeCoordinator() -> ProbeNumericTextFieldCoordinator {
        ProbeNumericTextFieldCoordinator(
            text: $text,
            onBeginEditing: onBeginEditing,
            onEndEditing: onEndEditing,
            onCommit: onCommit
        )
    }

    func makeNSView(context: Context) -> NSTextField {
        let textField = NSTextField(string: text)
        textField.delegate = context.coordinator
        textField.placeholderString = placeholder
        textField.alignment = .right
        textField.isBezeled = true
        textField.isBordered = true
        textField.drawsBackground = true
        textField.bezelStyle = .roundedBezel
        textField.focusRingType = .default
        textField.usesSingleLineMode = true
        textField.lineBreakMode = .byClipping
        textField.font = .monospacedDigitSystemFont(
            ofSize: NSFont.systemFontSize,
            weight: .regular
        )
        textField.setAccessibilityLabel(accessibilityLabel)
        textField.setAccessibilityHelp(accessibilityHint)
        return textField
    }

    func updateNSView(_ textField: NSTextField, context: Context) {
        context.coordinator.update(
            text: $text,
            onBeginEditing: onBeginEditing,
            onEndEditing: onEndEditing,
            onCommit: onCommit
        )
        textField.placeholderString = placeholder
        textField.setAccessibilityLabel(accessibilityLabel)
        textField.setAccessibilityHelp(accessibilityHint)
        guard textField.currentEditor() == nil,
              textField.stringValue != text
        else {
            return
        }
        textField.stringValue = text
    }
}

@MainActor
final class ProbeSurfaceAutoCommitCoordinator {
    private var queue = ProbeSurfaceAutoCommitQueue()

    func enqueue(_ request: ProbeSurfaceAutoCommitRequest) -> Bool {
        queue.enqueue(request)
    }

    func beginNext() -> ProbeSurfaceAutoCommitTicket? {
        queue.beginNext()
    }

    func isLatest(_ ticket: ProbeSurfaceAutoCommitTicket) -> Bool {
        queue.isLatest(ticket)
    }

    @discardableResult
    func complete(_ ticket: ProbeSurfaceAutoCommitTicket) -> Bool {
        queue.complete(ticket)
    }
}

@MainActor
final class ProbeDraftSession: ObservableObject {
    @Published var surfaceAP = "0" { didSet { noteEditableMutation() } }
    @Published var surfaceML = "0" { didSet { noteEditableMutation() } }
    @Published var surfaceDepthMM = "2.3" { didSet { noteEditableMutation() } }
    @Published var sagittalAngle = "0" { didSet { noteEditableMutation() } }
    @Published var layoutRotation = ProbeLayoutRotation.sagittal.rawValue {
        didSet { noteEditableMutation() }
    }
    // These values are changed from the `didSet` observers above. Keeping
    // them as separate `@Published` properties would emit nested
    // `objectWillChange` notifications while SwiftUI is applying a text-field
    // or segmented-control binding. AppKit reports that as "Publishing
    // changes from within view updates" and the resulting undefined update
    // order can drop a simultaneous 3D scene refresh. The edited field's own
    // publication already invalidates observers, so the derived values remain
    // ordinary stored state. Explicit state-only changes publish once through
    // `setHasUnappliedChanges`.
    private(set) var hasUnappliedChanges = false
    private(set) var editableRevision = 0

    var surfaceBaseline: ProbeSurfaceDraftSnapshot?
    var pendingExplicitNewModel: ProbeDraftModelIdentity?
    private(set) var synchronizedContext: ProbeDraftContext?
    let autoCommitCoordinator = ProbeSurfaceAutoCommitCoordinator()
    private var isReplacingEditableValues = false

    func setHasUnappliedChanges(_ hasChanges: Bool) {
        guard hasUnappliedChanges != hasChanges else { return }
        objectWillChange.send()
        hasUnappliedChanges = hasChanges
    }

    private func noteEditableMutation() {
        guard !isReplacingEditableValues else { return }
        editableRevision &+= 1
        // Each editable property is already @Published. Sending an additional
        // objectWillChange from its didSet would be a nested publication while
        // SwiftUI is applying the field binding.
        hasUnappliedChanges = true
    }

    func replaceEditableValues(
        ap: String,
        ml: String,
        surfaceDepthMM: String,
        sagittalAngle: String,
        layoutRotation: String
    ) {
        isReplacingEditableValues = true
        surfaceAP = ap
        surfaceML = ml
        self.surfaceDepthMM = surfaceDepthMM
        self.sagittalAngle = sagittalAngle
        self.layoutRotation = layoutRotation
        isReplacingEditableValues = false
    }

    func markSynchronized(with context: ProbeDraftContext) {
        synchronizedContext = context
    }

    func discard() {
        replaceEditableValues(
            ap: "0",
            ml: "0",
            surfaceDepthMM: "2.3",
            sagittalAngle: "0",
            layoutRotation: ProbeLayoutRotation.sagittal.rawValue
        )
        surfaceBaseline = nil
        pendingExplicitNewModel = nil
        synchronizedContext = nil
        setHasUnappliedChanges(false)
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

struct ProjectSidebar: View {
    @ObservedObject var model: PlannerViewModel
    @ObservedObject var draft: ProbeDraftSession
    let saveProject: () -> Void
    let openProject: () -> Void
    let reconnect: () -> Void
    @State private var showingSurgeryPlanExport = false
    @StateObject private var numericEditingSession =
        ProbeSurfaceNumericEditingSession()

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    projectSection
                    probeSection
                    majorVesselsSection
                }
                .padding(16)
            }
        }
        .background(.thinMaterial)
        .sheet(isPresented: $showingSurgeryPlanExport) {
            SurgeryPlanExportSheet(
                model: model,
                hasUnappliedProbeEdits: hasUnappliedProbeEdits
            )
        }
        .onChange(of: model.selectedProbePlan?.planId, initial: true) {
            _, _ in
            ViewUpdateMutationBoundary.perform {
                synchronizeProbeDraft()
            }
        }
        .onChange(of: model.selectedProbePlan?.inputSha256) {
            _, _ in
            ViewUpdateMutationBoundary.perform {
                synchronizeProbeDraft()
            }
        }
        .onChange(of: model.backendState?.project?.projectId) { _, _ in
            ViewUpdateMutationBoundary.perform {
                synchronizeProbeDraft()
            }
        }
        .onChange(of: model.selectedProbeModel?.id, initial: true) { _, _ in
            ViewUpdateMutationBoundary.perform {
                let selectedIdentity = model.selectedProbeModel.map {
                    ProbeDraftModelIdentity(
                        modelId: $0.modelId,
                        modelVersion: $0.modelVersion
                    )
                }
                let isExplicitNewDraftSelection =
                    draft.pendingExplicitNewModel == selectedIdentity
                if model.selectedProbePlan == nil,
                   !isExplicitNewDraftSelection,
                   !draft.hasUnappliedChanges
                {
                    draft.surfaceBaseline = currentSurfaceProbeDraftSnapshot
                    draft.setHasUnappliedChanges(false)
                }
                if isExplicitNewDraftSelection {
                    requestProbeAutoCommit(.modelChanged)
                }
            }
        }
        .onChange(of: hasUnappliedProbeEdits, initial: true) { _, _ in
            ViewUpdateMutationBoundary.perform {
                // Re-read after crossing the boundary. Several field changes
                // can arrive in one control transaction, and an older
                // callback must not publish its captured derived value after
                // the latest edit.
                let currentHasChanges = hasUnappliedProbeEdits
                draft.setHasUnappliedChanges(currentHasChanges)
                if !currentHasChanges {
                    synchronizeProbeDraft()
                }
            }
        }
        .onChange(of: draft.editableRevision) { _, _ in
            ViewUpdateMutationBoundary.perform {
                let hasChanges = hasUnappliedProbeEdits
                draft.setHasUnappliedChanges(hasChanges)
                if !hasChanges {
                    synchronizeProbeDraft()
                }
            }
        }
        .onChange(of: autoCommitReadinessFingerprint, initial: true) { _, _ in
            requestProbeAutoCommit(.planningBecameReady)
        }
    }

    private var probeSection: some View {
        SidebarSection(title: "Neuropixels 2.0", systemImage: "line.diagonal.arrow") {
            Picker("Probe", selection: probeModelSelection) {
                if supportedProbeCatalog.isEmpty {
                    Text("Unavailable").tag("")
                }
                ForEach(supportedProbeCatalog) { probe in
                    Text(probePickerLabel(probe)).tag(probe.id)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .disabled(
                supportedProbeCatalog.isEmpty
                    || model.probeOperationInProgress
            )
            .accessibilityLabel("Neuropixels model")
            .accessibilityHint("Choose NP2003 with one shank or NP2013 with four shanks.")

            VStack(alignment: .leading, spacing: 6) {
                Text("Surface insertion site from bregma")
                    .font(.caption.weight(.semibold))
                HStack(spacing: 7) {
                    surfaceProbeNumberField(
                        .ap,
                        ProbeSurfaceEditorPresentation.apLabel,
                        unit: "mm",
                        text: $draft.surfaceAP,
                        accessibilityLabel: "Insertion AP in millimetres from bregma"
                    )
                    surfaceProbeNumberField(
                        .ml,
                        ProbeSurfaceEditorPresentation.mlLabel,
                        unit: "mm",
                        text: $draft.surfaceML,
                        accessibilityLabel:
                            "Surface insertion ML in millimetres from bregma; "
                            + "positive right, negative left"
                    )
                }
            }

            surfaceProbeNumberField(
                .surfaceDepth,
                ProbeSurfaceEditorPresentation.depthLabel,
                unit: "mm",
                text: $draft.surfaceDepthMM,
                accessibilityLabel:
                    "Shank 1 depth from the insertion-site brain surface in millimetres",
                accessibilityHint:
                    "Enter the path length along shank 1 from its brain-surface insertion point "
                    + "to its target."
            )

            surfaceProbeNumberField(
                .anteriorPosteriorAngle,
                ProbeSurfaceEditorPresentation.angleLabel,
                unit: "°",
                text: $draft.sagittalAngle,
                accessibilityLabel: "Anterior posterior insertion angle in degrees",
                accessibilityHint:
                    "Positive advances from anterior to posterior; negative advances "
                    + "from posterior to anterior."
            )

            VStack(alignment: .leading, spacing: 4) {
                Text("Probe layout")
                    .font(.caption.weight(.semibold))
                Picker("Probe layout", selection: probeLayoutSelection) {
                    ForEach(ProbeLayoutRotation.allCases) { rotation in
                        Text(rotation.label).tag(rotation.rawValue)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .accessibilityLabel("Probe layout rotation")
                .accessibilityValue(
                    ProbeLayoutRotation(rawValue: draft.layoutRotation)?
                        .accessibilityValue ?? "No valid layout selected."
                )
            }

            if model.probeOperationInProgress {
                ProgressView("Updating probe…")
                    .controlSize(.small)
            }
            if draft.hasUnappliedChanges,
               let reason = probeDraftBlockingReason,
               !model.probeOperationInProgress
            {
                Label(reason, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let error = model.probeOperationError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var probeModelSelection: Binding<String> {
        Binding(
            get: {
                if let pending = draft.pendingExplicitNewModel,
                   let probe = supportedProbeCatalog.first(where: {
                       $0.modelId == pending.modelId
                           && $0.modelVersion == pending.modelVersion
                   })
                {
                    return probe.id
                }
                return model.selectedProbeModel?.id ?? ""
            },
            set: { identity in
                guard let probe = model.probeCatalog.first(where: { $0.id == identity }) else {
                    return
                }
                let requestedIdentity = ProbeDraftModelIdentity(
                    modelId: probe.modelId,
                    modelVersion: probe.modelVersion
                )
                draft.pendingExplicitNewModel = requestedIdentity
                ViewUpdateMutationBoundary.perform {
                    numericEditingSession.endActiveEditing()
                    requestProbeAutoCommit(
                        .modelChanged,
                        modelOverride: requestedIdentity
                    )
                }
            }
        )
    }

    private var probeLayoutSelection: Binding<String> {
        Binding(
            get: { draft.layoutRotation },
            set: { rotation in
                guard ProbeLayoutRotation(rawValue: rotation) != nil else { return }
                ViewUpdateMutationBoundary.perform {
                    numericEditingSession.endActiveEditing()
                    draft.layoutRotation = rotation
                    requestProbeAutoCommit(.layoutChanged)
                }
            }
        )
    }

    private var editableSurfacePlan: ProbePlanDetail? {
        guard let plan = model.selectedProbePlan,
              plan.placementMode == .atlasSurfaceAPML,
              plan.surfaceRelativeInput != nil
        else { return nil }
        return plan
    }

    private var hasUnappliedProbeEdits: Bool {
        ProbeSurfaceDraftComparisonPolicy.hasUnappliedEdits(
            current: currentSurfaceProbeDraftSnapshot,
            baseline: draft.surfaceBaseline
        )
    }

    private var currentSurfaceProbeDraftSnapshot: ProbeSurfaceDraftSnapshot {
        let identity = effectiveProbeModelIdentity
        return ProbeSurfaceDraftComparisonPolicy.snapshot(
            modelId: identity?.modelId,
            modelVersion: identity?.modelVersion,
            ap: draft.surfaceAP,
            ml: draft.surfaceML,
            surfaceDepthMM: draft.surfaceDepthMM,
            sagittalAngle: draft.sagittalAngle,
            layoutRotation: draft.layoutRotation
        )
    }

    private var effectiveProbeModelIdentity: ProbeDraftModelIdentity? {
        draft.pendingExplicitNewModel
            ?? model.selectedProbeModel.map {
                ProbeDraftModelIdentity(
                    modelId: $0.modelId,
                    modelVersion: $0.modelVersion
                )
            }
    }

    private var probeDraftBlockingReason: String? {
        ProbeSurfaceDraftReadinessPolicy.blockingReason(
            planningUnavailableReason: directProbePlanningUnavailableReason,
            hasSelectedModel: model.selectedProbeModel != nil,
            ap: draft.surfaceAP,
            ml: draft.surfaceML,
            surfaceDepth: draft.surfaceDepthMM,
            anteriorPosteriorAngle: draft.sagittalAngle,
            layoutRotation: draft.layoutRotation
        )
    }

    private var directProbePlanningUnavailableReason: String? {
        ProbeSurfacePlanningAvailabilityPolicy.blockingReason(
            connectionReady: model.connection.isReady,
            hasProject: model.backendState?.project != nil,
            atlasReady: model.atlasLoadPhase == .ready,
            serviceSupportsPlanning: model.supportsAtlasSurfaceProbePlanning,
            projectOperationInProgress: model.projectOperationInProgress,
            probeOperationInProgress: model.probeOperationInProgress
        )
    }

    private var supportedProbeCatalog: [ProbeCatalogModel] {
        model.probeCatalog.filter {
            ProbeCatalogPresentation.isNeuropixels2(modelId: $0.modelId)
        }
    }

    private func probePickerLabel(_ probe: ProbeCatalogModel) -> String {
        ProbeSurfaceEditorPresentation.modelLabel(modelId: probe.modelId)
            ?? "Unsupported"
    }

    private func surfaceProbeNumberField(
        _ field: ProbeSurfaceEditorField,
        _ label: String,
        unit: String,
        text: Binding<String>,
        accessibilityLabel: String,
        accessibilityHint: String? = nil
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(label) (\(unit))")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            ProbeSurfaceNumericTextField(
                text: text,
                placeholder: unit,
                accessibilityLabel: accessibilityLabel,
                accessibilityHint: accessibilityHint ?? "Enter a decimal value.",
                onBeginEditing: { control in
                    numericEditingSession.beganEditing(
                        field: field,
                        control: control
                    )
                },
                onEndEditing: { control in
                    numericEditingSession.endedEditing(
                        field: field,
                        control: control
                    )
                },
                onCommit: {
                    requestProbeAutoCommit(.numericFocusLost)
                }
            )
            .frame(maxWidth: .infinity, minHeight: 22)
        }
        .frame(maxWidth: .infinity)
    }

    private func requestProbeAutoCommit(
        _ trigger: ProbeSurfaceAutoCommitTrigger,
        modelOverride: ProbeDraftModelIdentity? = nil
    ) {
        switch ProbeSurfaceAutoCommitPolicy.action(
            for: trigger,
            numericFieldIsFocused: numericEditingSession.isEditing
        ) {
        case .ignore:
            return
        case .endNumericEditing:
            // AppKit may deliver a segmented-picker change before it publishes
            // the text field's focus loss. Ending editing here makes the focus
            // transition the sole commit boundary, so an atomic model/layout
            // choice can never smuggle an intermediate "9" into a planned
            // "90" numeric edit.
            numericEditingSession.endActiveEditing()
            return
        case .enqueueMutation:
            break
        }
        guard let identity = modelOverride ?? effectiveProbeModelIdentity else {
            return
        }
        let request = ProbeSurfaceAutoCommitRequest(
            model: identity,
            ap: draft.surfaceAP,
            ml: draft.surfaceML,
            surfaceDepthMM: draft.surfaceDepthMM,
            sagittalAngle: draft.sagittalAngle,
            layoutRotation: draft.layoutRotation,
            editableRevision: draft.editableRevision
        )
        guard draft.autoCommitCoordinator.enqueue(request) else { return }
        ViewUpdateMutationBoundary.performAsync {
            await drainProbeAutoCommitQueue()
        }
    }

    private func drainProbeAutoCommitQueue() async {
        while let ticket = draft.autoCommitCoordinator.beginNext() {
            let succeeded = await performProbeAutoCommit(ticket)
            if succeeded {
                publishProbeAutoCommitCompletionIfCurrent(ticket)
            }
            let hasPending = draft.autoCommitCoordinator.complete(ticket)
            if !hasPending { return }
        }
    }

    private func performProbeAutoCommit(
        _ ticket: ProbeSurfaceAutoCommitTicket
    ) async -> Bool {
        let request = ticket.request
        let loadedIdentity = model.selectedProbeModel.map {
            ProbeDraftModelIdentity(
                modelId: $0.modelId,
                modelVersion: $0.modelVersion
            )
        }
        if loadedIdentity != request.model {
            let loaded = await model.loadProbeModel(
                modelId: request.model.modelId,
                modelVersion: request.model.modelVersion
            )
            guard loaded else {
                if draft.autoCommitCoordinator.isLatest(ticket),
                   draft.pendingExplicitNewModel == request.model
                {
                    draft.pendingExplicitNewModel = nil
                }
                return false
            }
        }

        // A later focus commit or atomic selector choice supersedes this
        // request. Do not write its stale values after the model fetch.
        guard draft.autoCommitCoordinator.isLatest(ticket) else { return false }

        let executionUnavailableReason =
            ProbeSurfacePlanningAvailabilityPolicy.blockingReason(
                connectionReady: model.connection.isReady,
                hasProject: model.backendState?.project != nil,
                atlasReady: model.atlasLoadPhase == .ready,
                serviceSupportsPlanning: model.supportsAtlasSurfaceProbePlanning,
                projectOperationInProgress: model.projectOperationInProgress,
                probeOperationInProgress: false
            )
        guard ProbeSurfaceDraftReadinessPolicy.blockingReason(
            planningUnavailableReason: executionUnavailableReason,
            hasSelectedModel: true,
            ap: request.ap,
            ml: request.ml,
            surfaceDepth: request.surfaceDepthMM,
            anteriorPosteriorAngle: request.sagittalAngle,
            layoutRotation: request.layoutRotation
        ) == nil else {
            return false
        }

        if editableSurfacePlan != nil,
           draft.surfaceBaseline == request.snapshot
        {
            return true
        }
        return if editableSurfacePlan == nil {
            await createProbePlan(request: request)
        } else {
            await updateProbePlan(request: request)
        }
    }

    private func publishProbeAutoCommitCompletionIfCurrent(
        _ ticket: ProbeSurfaceAutoCommitTicket
    ) {
        guard ProbeSurfaceAutoCommitCompletionPolicy.mayPopulateDraft(
            completed: ticket.request,
            isLatestRequest: draft.autoCommitCoordinator.isLatest(ticket),
            currentEditableRevision: draft.editableRevision,
            currentSnapshot: currentSurfaceProbeDraftSnapshot
        ) else {
            return
        }
        if draft.pendingExplicitNewModel == ticket.request.model {
            draft.pendingExplicitNewModel = nil
        }
        populateProbeDraft()
    }

    private func createProbePlan(
        request: ProbeSurfaceAutoCommitRequest
    ) async -> Bool {
        return await model.createAtlasSurfaceProbePlan(
            modelId: request.model.modelId,
            modelVersion: request.model.modelVersion,
            insertionAPText: request.ap,
            insertionMLText: request.ml,
            surfaceDepthText: request.surfaceDepthMM,
            sagittalAngleText: request.sagittalAngle,
            layoutRotationText: request.layoutRotation
        )
    }

    private func updateProbePlan(
        request: ProbeSurfaceAutoCommitRequest
    ) async -> Bool {
        guard editableSurfacePlan != nil else { return false }
        return await model.updateSelectedAtlasSurfaceProbePlan(
            modelId: request.model.modelId,
            modelVersion: request.model.modelVersion,
            insertionAPText: request.ap,
            insertionMLText: request.ml,
            surfaceDepthText: request.surfaceDepthMM,
            sagittalAngleText: request.sagittalAngle,
            layoutRotationText: request.layoutRotation
        )
    }

    private func populateProbeDraft() {
        guard let plan = editableSurfacePlan,
              let input = plan.surfaceRelativeInput
        else {
            prepareNewProbeDraft()
            return
        }
        draft.replaceEditableValues(
            ap: decimalText(input.insertionAPMillimetres),
            ml: decimalText(input.insertionMLMillimetres),
            surfaceDepthMM: decimalText(input.surfaceDepthMillimetres),
            sagittalAngle: decimalText(input.sagittalAngleDegrees),
            layoutRotation: String(input.probeLayoutRotationDegrees)
        )
        draft.surfaceBaseline = currentSurfaceProbeDraftSnapshot
        draft.markSynchronized(with: currentProbeDraftContext)
        draft.setHasUnappliedChanges(false)
    }

    private func clearProbeDraft() {
        draft.replaceEditableValues(
            ap: "0",
            ml: "0",
            surfaceDepthMM: "2.3",
            sagittalAngle: "0",
            layoutRotation: ProbeLayoutRotation.sagittal.rawValue
        )
    }

    private func prepareNewProbeDraft() {
        clearProbeDraft()
        draft.surfaceBaseline = currentSurfaceProbeDraftSnapshot
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
        if editableSurfacePlan == nil {
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

    private func decimalText(_ value: Double) -> String {
        String(format: "%.12g", value)
    }

    private var autoCommitReadinessFingerprint: String {
        [
            model.connection.isReady ? "connected" : "disconnected",
            model.backendState?.project?.projectId ?? "no-project",
            model.backendState?.project.map { String($0.revision) } ?? "no-revision",
            String(describing: model.atlasLoadPhase),
            model.supportsAtlasSurfaceProbePlanning ? "surface-plan" : "no-surface-plan",
            model.projectOperationInProgress ? "project-busy" : "project-idle",
            model.probeOperationInProgress ? "probe-busy" : "probe-idle",
            model.selectedProbeModel?.id ?? "no-model",
            model.selectedProbePlan?.planId ?? "no-plan",
            model.selectedProbePlan?.inputSha256 ?? "no-input",
        ].joined(separator: "|")
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
                        ? "Finish the numeric edit and wait for the probe to update."
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
                    || editableSurfacePlan == nil
                    || hasUnappliedProbeEdits
            )
            .help(
                hasUnappliedProbeEdits
                    ? "Finish the numeric edit and wait for the probe to update."
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
