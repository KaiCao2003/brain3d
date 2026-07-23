import AppKit
import Brain3DCore
import Foundation
import SwiftUI
import UniformTypeIdentifiers

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
    @State private var showingProbeRegionInspector = false
    @State private var confirmingProbeRemoval = false

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    backendSection
                    atlasSection
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
        .sheet(isPresented: $showingProbeRegionInspector) {
            if let plan = model.selectedProbePlan,
               let analysis = model.selectedProbeRegionAnalysis
            {
                ProbeRegionInspectorSheet(plan: plan, analysis: analysis)
            }
        }
        .confirmationDialog(
            "Remove this probe plan and its region analysis?",
            isPresented: $confirmingProbeRemoval,
            titleVisibility: .visible
        ) {
            Button("Remove Probe Plan", role: .destructive) {
                Task {
                    if await model.removeSelectedProbePlan() {
                        clearProbeDraft()
                    }
                }
            }
            Button("Cancel", role: .cancel) {}
        }
        .onChange(of: model.selectedProbePlan?.inputSha256, initial: true) {
            _, _ in
            if model.selectedProbePlan == nil {
                clearProbeDraft()
            } else {
                populateProbeDraft()
            }
        }
        .onChange(of: model.backendState?.project?.projectId) { _, _ in
            resetPlanningDraftsForProject()
        }
        .onChange(of: model.implantTargets.map(\.targetId), initial: true) {
            _, targetIds in
            if !probeTargetId.isEmpty, !targetIds.contains(probeTargetId) {
                probeTargetId = ""
            }
            if targetCoordinatesAreBlank {
                targetLabel = nextTargetLabel
            }
        }
    }

    private var probeSection: some View {
        SidebarSection(title: "Probe", systemImage: "line.diagonal.arrow") {
            Picker("Plan", selection: probePlanSelection) {
                Text("New probe plan").tag("")
                ForEach(model.probePlans) { plan in
                    Text(plan.name).tag(plan.planId)
                }
            }
            .disabled(model.probeOperationInProgress)
            .accessibilityLabel("Probe plan")

            Picker("Probe model", selection: probeModelSelection) {
                if model.probeCatalog.isEmpty {
                    Text("No model available").tag("")
                } else if model.selectedProbePlan != nil,
                          model.selectedProbeModel == nil
                {
                    Text("Archived model (read-only)").tag("")
                }
                ForEach(model.probeCatalog) { probe in
                    Text(probe.displayName).tag(probe.id)
                }
            }
            .disabled(
                model.probeCatalog.isEmpty
                    || model.probeOperationInProgress
                    || (model.selectedProbePlan != nil && model.selectedProbeModel == nil)
            )
            .accessibilityHint("Selects the exact hardware geometry used by this plan.")

            if let probe = model.selectedProbeModel {
                selectedProbeModelCard(probe)
            } else if let plan = model.selectedProbePlan {
                Label(
                    "\(plan.modelDisplayName) is archived and read-only. "
                        + "Only NP2 single- and standard four-shank models are supported.",
                    systemImage: "archivebox"
                )
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            } else if !model.probeCatalog.isEmpty {
                Label("Select the hardware model to continue.", systemImage: "cpu")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if !model.probeCatalog.isEmpty,
               !ProbeCatalogPresentation.containsNeuropixels2(model.probeCatalog)
            {
                Label(
                    "Neuropixels 2.0 is not available from this connected catalog.",
                    systemImage: "exclamationmark.triangle"
                )
                .font(.caption)
                .foregroundStyle(.orange)
                .fixedSize(horizontal: false, vertical: true)
            }

            Picker("Implant target", selection: $probeTargetId) {
                Text("Select implant target").tag("")
                ForEach(model.implantTargets) { target in
                    Text(target.label).tag(target.targetId)
                }
            }
            .disabled(model.implantTargets.isEmpty || model.probeOperationInProgress)
            .accessibilityHint("Uses the selected bregma-relative AP, ML, and DV site.")

            Picker("Placement", selection: $probePlacementMode) {
                ForEach(ProbePlacementMode.allCases, id: \.self) { mode in
                    Text(mode.displayName).tag(mode)
                }
            }
            .pickerStyle(.menu)
            .controlSize(.small)
            .accessibilityLabel("Probe placement mode")

            Text(ProbePlacementGuidance.text(for: probePlacementMode))
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            TextField("Required plan name", text: $probeName)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel("Probe plan name")
                .accessibilityHint("Names this plan; it does not select the hardware model.")

            if probePlacementMode.requiresEntryCoordinates {
                probeEntryCoordinateFields
            }

            if probePlacementMode.requiresAnglesAndDepth {
                probeNumberField(
                    "Azimuth (°)",
                    sign: "+ rotates anterior → right; − rotates toward left",
                    text: $probeAzimuth
                )
                probeNumberField(
                    "Elevation (°)",
                    sign: "+ dorsal / up; − deep / ventral",
                    text: $probeElevation
                )
                probeNumberField(
                    "Insertion depth (mm)",
                    sign: "Positive distance in millimetres from entry toward tip",
                    text: $probeDepth
                )
            }
            probeNumberField(
                "Axial rotation (°)",
                sign: "Right-hand rotation about the entry → tip axis",
                text: $probeAxialRotation
            )

            if let probe = model.selectedProbeModel,
               probe.requiresExplicitAcknowledgement
            {
                if let warning = probe.warning {
                    Text(warning)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Toggle(
                    probe.verificationStatus
                        == ProbePlanningContract.sourceTranscribedReviewPendingStatus
                        ? "I understand independent transcription review is pending"
                        : "I acknowledge this synthetic software-test geometry",
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
                            ?? "Create the probe plan and publish its trajectory preview."
                    )
                } else {
                    Button("Update plan", systemImage: "checkmark") {
                        Task { _ = await updateProbePlan() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSubmitProbeDraft)
                    .help(
                        probeDraftBlockingReason
                            ?? "Update the probe plan and recompute its trajectory preview."
                    )
                    Button("Remove", systemImage: "trash", role: .destructive) {
                        confirmingProbeRemoval = true
                    }
                    .disabled(!model.canRemoveSelectedProbePlan)
                }
            }
            .controlSize(.small)

            if let probeDraftBlockingReason {
                Label(probeDraftBlockingReason, systemImage: "info.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("Cannot submit probe plan")
                    .accessibilityValue(probeDraftBlockingReason)
            }

            if let plan = model.selectedProbePlan {
                Text(plan.requiresPlanningGeometryUpdate
                    ? "v\(plan.planVersion) · legacy geometry hidden · update required"
                    : "v\(plan.planVersion) · \(plan.modelDisplayName) · planning only · not navigation")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

                if plan.requiresPlanningGeometryUpdate {
                    Label(
                        "This legacy plan uses obsolete projection geometry. Review the restored inputs and choose Update plan to recompute it. Slice, 3D, region, and vessel analysis are disabled until then.",
                        systemImage: "arrow.triangle.2.circlepath"
                    )
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
                }

                if plan.hasCurrentPlanningGeometry {
                    probeTrajectoryPreview(plan)
                }

                HStack {
                    Button("Analyze regions", systemImage: "list.bullet.indent") {
                        Task { _ = await model.analyzeSelectedProbeRegions() }
                    }
                    .disabled(!model.canAnalyzeSelectedProbeRegions)

                    if plan.hasCurrentPlanningGeometry,
                       model.selectedProbeRegionAnalysis != nil
                    {
                        Button("Inspect…", systemImage: "tablecells") {
                            showingProbeRegionInspector = true
                        }
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                if plan.hasCurrentPlanningGeometry,
                   model.selectedProbeRegionAnalysis != nil
                {
                    HStack {
                        Button("Save CSV…") { saveProbeRegions(.csv) }
                        Button("Save JSON…") { saveProbeRegions(.json) }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }

            if model.probeOperationInProgress {
                ProgressView("Updating probe planning data…")
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
                        clearProbeDraft()
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

    private func selectedProbeModelCard(_ probe: ProbeCatalogModel) -> some View {
        let productIdentity = [probe.manufacturer, probe.productCode]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
        let shanks = probe.shankCount == 1
            ? "1 shank"
            : "\(probe.shankCount) shanks"
        let siteCount = probe.siteCount.formatted(.number.grouping(.automatic))
        let simultaneousChannelCount = ProbeCatalogPresentation.simultaneousChannelCount(
            modelId: probe.modelId
        )
        let channelIdentity = simultaneousChannelCount.map {
            "\($0.formatted(.number.grouping(.automatic))) simultaneous channels"
        }

        return VStack(alignment: .leading, spacing: 3) {
            Text(probe.displayName)
                .font(.caption.weight(.semibold))
            if !productIdentity.isEmpty {
                Text(productIdentity)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Text("\(shanks) · \(siteCount) physical/addressable sites")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
            if let channelIdentity {
                Text("\(channelIdentity) · IMRO/channel selection is not configured here")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(7)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.7), in: RoundedRectangle(cornerRadius: 7))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Selected probe model")
        .accessibilityValue(
            [
                probe.displayName,
                productIdentity,
                shanks,
                "\(siteCount) physical/addressable sites",
                channelIdentity.map {
                    "\($0); IMRO/channel selection is not configured here"
                } ?? "",
            ]
                .filter { !$0.isEmpty }
                .joined(separator: ", ")
        )
    }

    private func probeTrajectoryPreview(_ plan: ProbePlanDetail) -> some View {
        let source = plan.sourceTarget
        let placement = plan.placement
        let scenePlan = model.threeDimensionalSnapshot?.selectedProbePlan
        let sceneContainsCurrentPlan = scenePlan?.planId == plan.planId
            && scenePlan?.inputSha256 == plan.inputSha256

        return VStack(alignment: .leading, spacing: 4) {
            Label("Trajectory preview", systemImage: "line.diagonal.arrow")
                .font(.caption.weight(.semibold))
            Text(
                "Bregma target · AP \(signed(source.apMillimetres)) mm · "
                    + "ML \(signed(source.mlMillimetres)) mm · "
                    + "DV \(signed(source.dvMillimetres)) mm"
            )
            .font(.caption2.monospacedDigit())
            Text("Atlas physical · corner origin · AP / DV / ML · mm")
                .font(.caption2.weight(.medium))
                .foregroundStyle(.secondary)
            Text(probeAtlasPhysicalPointSummary("Entry", placement.atlasFrame.entry))
                .font(.caption2.monospacedDigit())
            Text(probeAtlasPhysicalPointSummary("Tip", placement.atlasFrame.tip))
                .font(.caption2.monospacedDigit())
            Text(
                String(
                    format: "Az %+.1f° · El %+.1f° · depth %.3f mm · roll %+.1f°",
                    placement.azimuthDegrees,
                    placement.elevationDegrees,
                    ProbeInputUnits.millimetres(
                        fromMicrometres: placement.insertionDepthMicrometres
                    ),
                    placement.axialRotationDegrees
                )
            )
            .font(.caption2.monospacedDigit())
            Text(
                ProbeOverlayPresentation.text(
                    threeDimensionalPhase: model.threeDimensionalPhase,
                    sceneContainsCurrentPlan: sceneContainsCurrentPlan
                )
            )
                .font(.caption2.weight(.medium))
                .foregroundStyle(.secondary)
        }
        .padding(7)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 7))
        .accessibilityElement(children: .combine)
    }

    private func probeAtlasPhysicalPointSummary(
        _ label: String,
        _ point: ProbePhysicalPoint
    ) -> String {
        "\(label) · AP \(signedMillimetres(point.apMicrometres)) · "
            + "DV \(signedMillimetres(point.dvMicrometres)) · "
            + "ML \(signedMillimetres(point.mlMicrometres))"
    }

    private func probeNumberField(
        _ label: String,
        sign: String,
        text: Binding<String>
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label)
                    .font(.caption.weight(.semibold))
                TextField("Required", text: text)
                    .textFieldStyle(.roundedBorder)
                    .multilineTextAlignment(.trailing)
                    .accessibilityLabel(label)
                    .accessibilityHint(sign)
            }
            Text(sign)
                .font(.caption2)
                .foregroundStyle(.secondary)
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
        text: Binding<String>
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(axis)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            TextField("Required", text: text)
                .textFieldStyle(.roundedBorder)
                .multilineTextAlignment(.trailing)
                .accessibilityLabel("Entry \(axis) in millimetres from bregma")
                .accessibilityHint(probeEntryAccessibilityHint(axis))
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

    private func resetPlanningDraftsForProject() {
        clearProbeDraft()
        clearTargetDraft()
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

    private func saveProbeRegions(_ format: ProbeRegionExportFormat) {
        Task {
            guard let export = await model.exportSelectedProbeRegions(format: format) else {
                return
            }
            let panel = NSSavePanel()
            panel.title = "Save exact probe-region analysis"
            panel.prompt = "Save"
            panel.nameFieldStringValue = export.suggestedFileName
            panel.canCreateDirectories = true
            panel.allowedContentTypes = [format == .csv ? .commaSeparatedText : .json]
            guard panel.runModal() == .OK, let url = panel.url else { return }
            do {
                try Data(export.content.utf8).write(to: url, options: .atomic)
                _ = await model.confirmProbeRegionExport(export)
            } catch {
                model.recordProbeFileError(error)
            }
        }
    }

    private var majorVesselsSection: some View {
        SidebarSection(title: "Major vessels", systemImage: "drop.triangle") {
            StatusRow(label: "Geometry", value: model.majorVesselStatus)
            if model.majorVesselLoadInProgress {
                ProgressView("Verifying vessel geometry…")
                    .controlSize(.small)
            }
            if let error = model.majorVesselLoadError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let source = model.majorVesselGeometry?.provenance {
                StatusRow(
                    label: "Source",
                    value: "VesSAP \(source.specimenId) · \(source.sourceLicense)"
                )
                Text(model.majorVesselDisclosure)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 14) {
                    if let recordURL = URL(string: source.sourceRecordUrl) {
                        Link("Dataset", destination: recordURL)
                    }
                    if let paperURL = URL(
                        string: "https://doi.org/\(source.sourcePaperDoi)"
                    ) {
                        Link("Paper", destination: paperURL)
                    }
                }
                .font(.caption)
            }
            if model.majorVesselGeometry != nil {
                Text(
                    "Display overlay only · population reference · clearance "
                        + "classification is unavailable."
                )
                .font(.caption.weight(.medium))
                .foregroundStyle(.orange)
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var implantTargetSection: some View {
        SidebarSection(title: "Implant target", systemImage: "scope") {
            StatusRow(
                label: "Coordinate frame",
                value: "Bregma-relative AP / ML / DV in millimetres"
            )
            StatusRow(
                label: "Projection",
                value: projectionStatus
            )
            StatusRow(
                label: "Stored sites",
                value: "\(model.implantTargets.count)"
            )
            Button("Calibrations…", systemImage: "ruler") {
                showingCalibrationSheet = true
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(!model.canManageCalibration)
            VStack(alignment: .leading, spacing: 7) {
                TextField("Required site label", text: $targetLabel)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityLabel("Implant site label")
                targetField("AP (mm)", sign: "−AP = posterior / back", text: $targetAPMillimetres)
                targetField("ML (mm)", sign: "−ML = left", text: $targetMLMillimetres)
                targetField(
                    "DV / depth (mm)",
                    sign: "−DV = deep / ventral",
                    text: $targetDVMillimetres
                )
            }
            .disabled(!model.canStoreImplantTarget)
            Button("Store unprojected site", systemImage: "plus") {
                Task {
                    let existingTargetIds = Set(model.implantTargets.map(\.targetId))
                    let added = await model.addUnprojectedImplantTarget(
                        label: targetLabel,
                        apText: targetAPMillimetres,
                        mlText: targetMLMillimetres,
                        dvText: targetDVMillimetres
                    )
                    if added {
                        probeTargetId = model.implantTargets.first {
                            !existingTargetIds.contains($0.targetId)
                        }?.targetId ?? ""
                        clearTargetDraft()
                    }
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .disabled(
                !model.canStoreImplantTarget
                    || targetLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || targetAPMillimetres.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || targetMLMillimetres.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || targetDVMillimetres.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            )
            .help("Stores the signed values from bregma without creating an atlas marker.")
            if model.implantOperationInProgress {
                ProgressView("Updating stored implant sites…")
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
            HStack(alignment: .firstTextBaseline) {
                Text(target.label)
                    .font(.caption.weight(.semibold))
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
            Text(targetCoordinateSummary(target))
            .font(.caption2.monospacedDigit())
            .fixedSize(horizontal: false, vertical: true)
            if let projection = model.projection(for: target.targetId) {
                Text(atlasCoordinateSummary(projection))
                    .font(.caption2.monospacedDigit())
                Text(voxelSummary(projection))
                    .font(.caption2.monospacedDigit())
                Text(
                    "Calibration \(String(projection.provenance.calibrationSha256.prefix(10)))… "
                        + "· planning only · not navigation"
                )
                .font(.caption2.weight(.medium))
                .foregroundStyle(.orange)
            } else {
                Text("From bregma · unprojected · not navigation")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.orange)
                if model.activeCalibration != nil {
                    Button("Project to atlas") {
                        Task { _ = await model.projectImplantTarget(targetId: target.targetId) }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.mini)
                    .disabled(model.calibrationOperationInProgress)
                }
            }
        }
        .padding(8)
        .background(.quaternary.opacity(0.7), in: RoundedRectangle(cornerRadius: 7))
        .accessibilityElement(children: .contain)
    }

    private var projectionStatus: String {
        guard let calibration = model.activeCalibration else {
            return "Locked — subject calibration required"
        }
        return "Active v\(calibration.calibrationVersion) · \(calibration.quality.uppercased())"
    }

    private func atlasCoordinateSummary(_ result: CalibratedTargetProjectionResult) -> String {
        let point = result.atlasPoint
        return "Atlas AP \(signedMillimetres(point.apMicrometres)) · "
            + "DV \(signedMillimetres(point.dvMicrometres)) · "
            + "ML \(signedMillimetres(point.mlMicrometres))"
    }

    private func voxelSummary(_ result: CalibratedTargetProjectionResult) -> String {
        let voxel = result.containingVoxelIndex
        return "Voxel AP \(voxel.ap) · DV \(voxel.dv) · ML \(voxel.ml)"
    }

    private func signedMillimetres(_ micrometres: Double) -> String {
        String(
            format: "%+.3f mm",
            ProbeInputUnits.millimetres(fromMicrometres: micrometres)
        )
    }

    private func signed(_ value: Double) -> String {
        if value == 0 { return "0.000" }
        return String(format: "%+.3f", value)
    }

    private func targetCoordinateSummary(_ target: UnprojectedImplantTarget) -> String {
        let apDirection = direction(
            target.apMillimetres,
            positive: "anterior",
            negative: "posterior/back"
        )
        let mlDirection = direction(target.mlMillimetres, positive: "right", negative: "left")
        let dvDirection = direction(
            target.dvMillimetres,
            positive: "dorsal/up",
            negative: "deep/ventral"
        )
        return "AP \(signed(target.apMillimetres)) mm (\(apDirection)) · "
            + "ML \(signed(target.mlMillimetres)) mm (\(mlDirection)) · "
            + "DV \(signed(target.dvMillimetres)) mm (\(dvDirection))"
    }

    private func direction(_ value: Double, positive: String, negative: String) -> String {
        if value > 0 { return positive }
        if value < 0 { return negative }
        return "zero"
    }

    private func targetField(
        _ label: String,
        sign: String,
        text: Binding<String>
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.caption.weight(.semibold))
                TextField("Required", text: text)
                    .textFieldStyle(.roundedBorder)
                    .multilineTextAlignment(.trailing)
                    .accessibilityLabel("\(label) from bregma")
                    .accessibilityHint(sign)
            }
            Text(sign)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private var backendSection: some View {
        SidebarSection(title: "Planning service", systemImage: "point.3.connected.trianglepath.dotted") {
            StatusRow(label: "Connection", value: model.connection.title)
            StatusRow(label: "Project", value: model.projectStatus)
            HStack {
                Button("Reconnect") {
                    reconnect()
                }
                .disabled(model.connection == .connecting)

                Button("Refresh state") {
                    Task { await model.refreshState() }
                }
                .disabled(!model.connection.isReady)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            HStack {
                Button("Open…", systemImage: "folder") { openProject() }
                    .disabled(!model.canOpenProject)
                Button("Save As…", systemImage: "square.and.arrow.down") { saveProject() }
                    .disabled(!model.canSaveProject)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            if model.projectOperationInProgress {
                ProgressView("Validating project package…")
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

    private var atlasSection: some View {
        SidebarSection(title: "Atlas", systemImage: "square.stack.3d.up") {
            StatusRow(label: "Supported", value: SafetyPolicy.supportedAtlasDisplayName)
            StatusRow(label: "Operational", value: model.atlasOperationalStatus)
            if model.canDownloadAtlas {
                Button("Download reviewed 25 µm atlas", systemImage: "arrow.down.circle") {
                    Task { await model.downloadAndOpenAtlas() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .help("Downloads only allen_mouse_25um v1.2, then validates it before use.")
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

struct StatusRow: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.callout)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
