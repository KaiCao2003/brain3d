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
    let saveProject: () -> Void
    let openProject: () -> Void
    let reconnect: () -> Void
    @State private var targetLabel = "Implant site 1"
    @State private var targetAPMillimetres = ""
    @State private var targetMLMillimetres = ""
    @State private var targetDVMillimetres = ""
    @State private var showingCalibrationSheet = false
    @State private var probeName = ""
    @State private var probeTargetId = ""
    @State private var probePlacementMode: ProbePlacementMode = .stereotaxicTargetManipulator
    @State private var probeEntryAP = ""
    @State private var probeEntryML = ""
    @State private var probeEntryDV = ""
    @State private var probeAzimuth = ""
    @State private var probeElevation = ""
    @State private var probeDepth = ""
    @State private var probeAxialRotation = "0"
    @State private var probeGeometryAcknowledged = false
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
            SurgeryPlanExportSheet(model: model)
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
            if model.selectedProbePlan == nil {
                prepareNewProbeDraft()
            } else {
                populateProbeDraft()
            }
        }
        .onChange(of: model.backendState?.project?.projectId) { _, _ in
            clearTargetDraft()
            synchronizeProbeDraft()
        }
        .onChange(of: model.implantTargets.map(\.targetId), initial: true) {
            _, targetIds in
            probeTargetId = ProbeDraftSelectionPolicy.targetId(
                selectedPlanTargetId: model.selectedProbePlan?.targetId,
                currentTargetId: probeTargetId,
                availableTargetIds: targetIds
            )
            if model.selectedProbePlan == nil {
                fillSuggestedProbeNameIfNeeded()
            }
            if targetCoordinatesAreBlank {
                targetLabel = nextTargetLabel
            }
        }
        .onChange(of: model.selectedProbeModel?.id, initial: true) { _, _ in
            fillSuggestedProbeNameIfNeeded()
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
            .disabled(model.probeOperationInProgress)
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

            Picker("Implant site", selection: $probeTargetId) {
                Text("Choose a site").tag("")
                ForEach(model.implantTargets) { target in
                    Text(target.label).tag(target.targetId)
                }
            }
            .disabled(model.implantTargets.isEmpty || model.probeOperationInProgress)
            .accessibilityHint("Uses the selected bregma-relative AP, ML, and DV site.")

            TextField("Plan name", text: $probeName)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel("Probe plan name")

            if probePlacementMode.requiresEntryCoordinates {
                Label("Legacy entry-based plan", systemImage: "archivebox")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                probeEntryCoordinateFields
            }

            if probePlacementMode.requiresAnglesAndDepth {
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
                    isOn: $probeGeometryAcknowledged
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
                } else {
                    Button("Update plan", systemImage: "checkmark") {
                        Task { _ = await updateProbePlan() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSubmitProbeDraft)
                    .help(
                        probeDraftBlockingReason
                            ?? "Update this NPX2 plan."
                    )
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
                Task {
                    _ = await model.loadProbeModel(
                        modelId: probe.modelId,
                        modelVersion: probe.modelVersion
                    )
                    probeGeometryAcknowledged = false
                }
            }
        )
    }

    private var canSubmitProbeDraft: Bool {
        probeDraftBlockingReason == nil
    }

    private var probeDraftBlockingReason: String? {
        ProbeDraftReadinessPolicy.blockingReason(
            planningUnavailableReason: model.probePlanningUnavailableReason,
            hasSelectedModel: model.selectedProbeModel != nil,
            availableTargetIds: model.implantTargets.map(\.targetId),
            selectedTargetId: probeTargetId,
            name: probeName,
            mode: probePlacementMode,
            entryAP: probeEntryAP,
            entryML: probeEntryML,
            entryDV: probeEntryDV,
            azimuth: probeAzimuth,
            elevation: probeElevation,
            depth: probeDepth,
            axialRotation: probeAxialRotation,
            requiresAcknowledgement: model.selectedProbeModel?
                .requiresExplicitAcknowledgement == true,
            acknowledgementGiven: probeGeometryAcknowledged
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
                    text: $probeAzimuth,
                    accessibilityLabel: "Azimuth in degrees",
                    accessibilityHint: "Degrees from negative 180 through 180."
                )
                compactProbeNumberField(
                    "Elevation",
                    text: $probeElevation,
                    accessibilityLabel: "Elevation in degrees",
                    accessibilityHint: "Degrees from negative 90 through 90."
                )
            }
            HStack(spacing: 7) {
                compactProbeNumberField(
                    "Depth",
                    text: $probeDepth,
                    accessibilityLabel: "Insertion depth in millimetres",
                    accessibilityHint: "Positive insertion depth in millimetres."
                )
                compactProbeNumberField(
                    "Roll",
                    text: $probeAxialRotation,
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
                compactProbeNumberField("AP", text: $probeEntryAP)
                compactProbeNumberField("ML", text: $probeEntryML)
                compactProbeNumberField("DV", text: $probeEntryDV)
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
            name: probeName,
            targetId: probeTargetId,
            modelId: probe.modelId,
            modelVersion: probe.modelVersion,
            placementMode: probePlacementMode,
            entryAPText: probeEntryAP,
            entryMLText: probeEntryML,
            entryDVText: probeEntryDV,
            azimuthText: probeAzimuth,
            elevationText: probeElevation,
            insertionDepthText: probeDepth,
            axialRotationText: probeAxialRotation,
            customGeometryAcknowledged: probeGeometryAcknowledged
        )
    }

    private func updateProbePlan() async -> Bool {
        guard let probe = model.selectedProbeModel else { return false }
        return await model.updateSelectedProbePlan(
            name: probeName,
            targetId: probeTargetId,
            modelId: probe.modelId,
            modelVersion: probe.modelVersion,
            placementMode: probePlacementMode,
            entryAPText: probeEntryAP,
            entryMLText: probeEntryML,
            entryDVText: probeEntryDV,
            azimuthText: probeAzimuth,
            elevationText: probeElevation,
            insertionDepthText: probeDepth,
            axialRotationText: probeAxialRotation,
            customGeometryAcknowledged: probeGeometryAcknowledged
        )
    }

    private func populateProbeDraft() {
        guard let plan = model.selectedProbePlan else { return }
        let draft = plan.placementDraft
        probeName = plan.name
        probeTargetId = plan.targetId
        probePlacementMode = draft.mode
        probeEntryAP = draft.entryAPMillimetres.map(decimalText) ?? ""
        probeEntryML = draft.entryMLMillimetres.map(decimalText) ?? ""
        probeEntryDV = draft.entryDVMillimetres.map(decimalText) ?? ""
        probeAzimuth = draft.azimuthDegrees.map(decimalText) ?? ""
        probeElevation = draft.elevationDegrees.map(decimalText) ?? ""
        probeDepth = draft.insertionDepthMicrometres.map {
            decimalText(ProbeInputUnits.millimetres(fromMicrometres: $0))
        } ?? ""
        probeAxialRotation = decimalText(draft.axialRotationDegrees)
        probeGeometryAcknowledged = ProbePlanningContract.requiresExplicitAcknowledgement(
            verificationStatus: plan.verificationStatus
        )
    }

    private func clearProbeDraft() {
        probeName = ""
        probeTargetId = ""
        probePlacementMode = .stereotaxicTargetManipulator
        probeEntryAP = ""
        probeEntryML = ""
        probeEntryDV = ""
        probeAzimuth = ""
        probeElevation = ""
        probeDepth = ""
        probeAxialRotation = "0"
        probeGeometryAcknowledged = false
    }

    private func prepareNewProbeDraft() {
        clearProbeDraft()
        probeTargetId = model.implantTargets.first?.targetId ?? ""
        fillSuggestedProbeNameIfNeeded()
    }

    private func synchronizeProbeDraft() {
        if model.selectedProbePlan == nil {
            prepareNewProbeDraft()
        } else {
            populateProbeDraft()
        }
    }

    private func fillSuggestedProbeNameIfNeeded() {
        guard model.selectedProbePlan == nil,
              probeName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let probe = model.selectedProbeModel,
              let siteLabel = model.implantTargets.first(where: {
                  $0.targetId == probeTargetId
              })?.label
        else { return }

        probeName = "\(probePickerLabel(probe)) · \(siteLabel)"
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
                            probeTargetId = addedTargetId
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
                    .help("Show this site in Coronal, Sagittal, and Horizontal views.")
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
                Button("Save", systemImage: "square.and.arrow.down") { saveProject() }
                    .disabled(!model.canSaveProject)
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
            )
            .help(
                "Create a prefilled protocol PDF with selected planning views "
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
