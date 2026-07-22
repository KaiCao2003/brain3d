import AppKit
import Brain3DCore
import Foundation
import SwiftUI
import UniformTypeIdentifiers

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
    @State private var probeAxialRotation = ""
    @State private var probeGeometryAcknowledged = false
    @State private var showingProbeRegionInspector = false
    @State private var showingMajorVesselConflictInspector = false
    @State private var confirmingProbeRemoval = false
    @State private var vesselAnalysisDraft = VesselAnalysisDraft()

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
        .sheet(isPresented: $showingMajorVesselConflictInspector) {
            MajorVesselConflictInspectorSheet(model: model)
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
            populateProbeDraft()
            populateVesselAnalysisDraftForCurrentPlan()
        }
        .onChange(of: model.backendState?.project?.projectId) { _, _ in
            populateVesselAnalysisDraftForCurrentPlan()
        }
        .onChange(of: model.selectedProbeVesselAnalysis?.analysis.inputSha256) { _, _ in
            guard let result = model.selectedProbeVesselAnalysis else { return }
            populateVesselAnalysisDraft(from: result)
        }
        .onChange(of: vesselAnalysisDraft) { _, draft in
            guard let result = model.selectedProbeVesselAnalysis,
                  !draft.matches(result.analysis)
            else { return }
            model.invalidateMajorVesselAnalysis()
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

            Picker("Model", selection: probeModelSelection) {
                if model.probeCatalog.isEmpty {
                    Text("No model available").tag("")
                }
                ForEach(model.probeCatalog) { probe in
                    Text(probe.displayName).tag(probe.id)
                }
            }
            .disabled(model.probeCatalog.isEmpty || model.probeOperationInProgress)

            Picker("Target", selection: $probeTargetId) {
                Text("Select implant target").tag("")
                ForEach(model.implantTargets) { target in
                    Text(target.label).tag(target.targetId)
                }
            }

            Picker("Mode", selection: $probePlacementMode) {
                ForEach(ProbePlacementMode.allCases, id: \.self) { mode in
                    Text(mode.displayName).tag(mode)
                }
            }
            .pickerStyle(.menu)
            .controlSize(.small)

            TextField("Probe plan name", text: $probeName)
                .textFieldStyle(.roundedBorder)

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
                    "Insertion depth (µm)",
                    sign: "Positive distance from entry toward tip",
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
                } else {
                    Button("Update plan", systemImage: "checkmark") {
                        Task { _ = await updateProbePlan() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSubmitProbeDraft)
                    Button("Remove", systemImage: "trash", role: .destructive) {
                        confirmingProbeRemoval = true
                    }
                    .disabled(!model.canRemoveSelectedProbePlan)
                }
            }
            .controlSize(.small)

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
        model.canManageProbePlanning
            && model.selectedProbeModel != nil
            && !probeName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !probeTargetId.isEmpty
            && validProbeNumber(probeAxialRotation, range: -180 ... 180)
            && entryFieldsAreValid
            && angleAndDepthFieldsAreValid
            && (model.selectedProbeModel.map {
                !$0.requiresExplicitAcknowledgement || probeGeometryAcknowledged
            } == true)
    }

    private var entryFieldsAreValid: Bool {
        !probePlacementMode.requiresEntryCoordinates
            || [probeEntryAP, probeEntryML, probeEntryDV].allSatisfy {
                validProbeNumber($0)
            }
    }

    private var angleAndDepthFieldsAreValid: Bool {
        !probePlacementMode.requiresAnglesAndDepth
            || (validProbeNumber(probeAzimuth, range: -180 ... 180)
                && validProbeNumber(probeElevation, range: -90 ... 90)
                && validProbeNumber(probeDepth, strictlyPositive: true))
    }

    private func validProbeNumber(
        _ text: String,
        range: ClosedRange<Double>? = nil,
        strictlyPositive: Bool = false
    ) -> Bool {
        guard let value = try? CalibrationNumberInput.parse(text, field: "Probe value")
        else { return false }
        if let range, !range.contains(value) { return false }
        return !strictlyPositive || value > 0
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
                TextField("", text: text)
                    .textFieldStyle(.roundedBorder)
                    .multilineTextAlignment(.trailing)
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
            TextField(axis, text: text)
                .textFieldStyle(.roundedBorder)
                .multilineTextAlignment(.trailing)
                .accessibilityLabel("Entry \(axis) in millimetres from bregma")
        }
        .frame(maxWidth: .infinity)
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
        probeDepth = draft.insertionDepthMicrometres.map(decimalText) ?? ""
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
        probeAxialRotation = ""
        probeGeometryAcknowledged = false
    }

    private func decimalText(_ value: Double) -> String {
        String(format: "%.12g", value)
    }

    private func populateVesselAnalysisDraftForCurrentPlan() {
        guard let projectId = model.backendState?.project?.projectId,
              let plan = model.selectedProbePlan,
              let result = model.selectedProbeVesselAnalysis,
              result.projectId == projectId,
              result.planId == plan.planId,
              result.planInputSha256 == plan.inputSha256
        else {
            vesselAnalysisDraft = VesselAnalysisDraft()
            return
        }
        vesselAnalysisDraft = VesselAnalysisDraft(analysis: result.analysis)
    }

    private func populateVesselAnalysisDraft(from result: MajorVesselAnalysisResult) {
        guard let projectId = model.backendState?.project?.projectId,
              let plan = model.selectedProbePlan,
              result.projectId == projectId,
              result.planId == plan.planId,
              result.planInputSha256 == plan.inputSha256
        else { return }
        vesselAnalysisDraft = VesselAnalysisDraft(analysis: result.analysis)
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
                StatusRow(label: "Source", value: "LAMBADA \(source.specimenId) · CC BY 4.0")
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
            if model.selectedProbePlan?.hasCurrentPlanningGeometry == true,
               model.majorVesselGeometry != nil
            {
                Divider()
                Text("Probe clearance")
                    .font(.caption.weight(.semibold))
                vesselDistanceField(
                    "Required margin (µm)",
                    text: $vesselAnalysisDraft.requiredMarginMicrometres
                )
                vesselDistanceField(
                    "Registration uncertainty (µm)",
                    text: $vesselAnalysisDraft.registrationUncertaintyMicrometres
                )
                Toggle(
                    "I reviewed these lab-defined inputs",
                    isOn: $vesselAnalysisDraft.riskProfileConfirmed
                )
                .font(.caption)
                Toggle(
                    "I understand this is a single fixed reference with missing vessels",
                    isOn: $vesselAnalysisDraft.referenceCoverageAcknowledged
                )
                .font(.caption)
                Button("Analyze probe", systemImage: "waveform.path.ecg") {
                    analyzeProbeMajorVessels()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(!canAnalyzeProbeMajorVessels)
                if model.majorVesselAnalysisInProgress {
                    ProgressView("Measuring tapered vessel surfaces…")
                        .controlSize(.small)
                }
                if let error = model.majorVesselAnalysisError {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let result = model.selectedProbeVesselAnalysis {
                    vesselAnalysisSummary(result.analysis)
                }
            }
        }
    }

    private func vesselDistanceField(_ label: String, text: Binding<String>) -> some View {
        HStack {
            Text(label)
                .font(.caption)
            TextField("0", text: text)
                .textFieldStyle(.roundedBorder)
                .multilineTextAlignment(.trailing)
        }
    }

    private var canAnalyzeProbeMajorVessels: Bool {
        model.canAnalyzeMajorVesselClearance
            && parsedVesselDistance(vesselAnalysisDraft.requiredMarginMicrometres) != nil
            && parsedVesselDistance(
                vesselAnalysisDraft.registrationUncertaintyMicrometres
            ) != nil
            && vesselAnalysisDraft.riskProfileConfirmed
            && vesselAnalysisDraft.referenceCoverageAcknowledged
    }

    private func analyzeProbeMajorVessels() {
        guard let margin = parsedVesselDistance(
            vesselAnalysisDraft.requiredMarginMicrometres
        ),
              let uncertainty = parsedVesselDistance(
                  vesselAnalysisDraft.registrationUncertaintyMicrometres
              )
        else { return }
        let riskProfileConfirmed = vesselAnalysisDraft.riskProfileConfirmed
        let referenceCoverageAcknowledged =
            vesselAnalysisDraft.referenceCoverageAcknowledged
        Task {
            _ = await model.analyzeSelectedProbeMajorVessels(
                requiredMarginMicrometres: margin,
                registrationUncertaintyMicrometres: uncertainty,
                riskProfileConfirmed: riskProfileConfirmed,
                referenceCoverageAcknowledged: referenceCoverageAcknowledged
            )
        }
    }

    private func parsedVesselDistance(_ text: String) -> Double? {
        guard let value = Double(text.trimmingCharacters(in: .whitespacesAndNewlines)),
              value.isFinite,
              value >= 0,
              value <= MajorVesselAnalysisContract.maximumDistanceMicrometres
        else { return nil }
        return value
    }

    private func vesselAnalysisSummary(
        _ analysis: MajorVesselClearanceAnalysis
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(
                vesselStatusLabel(analysis.resultStatus),
                systemImage: vesselStatusIcon(analysis.resultStatus)
            )
            .font(.caption.weight(.semibold))
            .foregroundStyle(vesselStatusColor(analysis.resultStatus))
            Text(analysis.statement)
                .font(.caption)
                .fixedSize(horizontal: false, vertical: true)
            if let adjusted = analysis.minimumAdjustedClearanceMicrometres {
                Text("Minimum adjusted clearance: \(signedMicrometres(adjusted))")
                    .font(.caption2.monospacedDigit())
            }
            if let nearest = analysis.nearestCenterlineDistanceMicrometres {
                Text("Nearest loaded centerline: \(nearest.formatted(.number.precision(.fractionLength(1)))) µm")
                    .font(.caption2.monospacedDigit())
            }
            if !analysis.conflicts.isEmpty {
                Button(
                    "Inspect \(analysis.conflicts.count) returned conflict"
                        + (analysis.conflicts.count == 1 ? "" : "s"),
                    systemImage: "list.bullet.rectangle"
                ) {
                    showingMajorVesselConflictInspector = true
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            }
            if analysis.conflictsTruncated {
                Text(
                    "The backend returned \(analysis.conflicts.count) conflicts; additional "
                        + "conflicts were truncated at the reviewed request limit."
                )
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
            if let error = model.majorVesselNavigationError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption2)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(analysis.warnings, id: \.self) { warning in
                Label(warning, systemImage: "info.circle")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(8)
        .background(.quaternary.opacity(0.65), in: RoundedRectangle(cornerRadius: 7))
    }

    private func vesselStatusLabel(_ status: MajorVesselResultStatus) -> String {
        switch status {
        case .intersection: "Intersection detected"
        case .marginViolation: "Margin violation"
        case .uncertaintyViolation: "Uncertainty-bound violation"
        case .noConflictDetected: "Loaded reference evaluated"
        case .insufficientGeometry: "Result not classifiable"
        }
    }

    private func vesselStatusIcon(_ status: MajorVesselResultStatus) -> String {
        switch status {
        case .intersection: "exclamationmark.octagon.fill"
        case .marginViolation, .uncertaintyViolation: "exclamationmark.triangle.fill"
        case .noConflictDetected: "magnifyingglass.circle"
        case .insufficientGeometry: "questionmark.circle"
        }
    }

    private func vesselStatusColor(_ status: MajorVesselResultStatus) -> Color {
        switch status {
        case .intersection: .red
        case .marginViolation, .uncertaintyViolation: .orange
        case .noConflictDetected: .secondary
        case .insufficientGeometry: .secondary
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
                value: "\(model.implantTargets.count) unprojected"
            )
            Button("Calibrations…", systemImage: "ruler") {
                showingCalibrationSheet = true
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(!model.canManageCalibration)
            VStack(alignment: .leading, spacing: 7) {
                TextField("Site label", text: $targetLabel)
                    .textFieldStyle(.roundedBorder)
                targetField("AP (mm)", sign: "−AP = posterior / back", text: $targetAPMillimetres)
                targetField("ML (mm)", sign: "−ML = left", text: $targetMLMillimetres)
                targetField("DV (mm)", sign: "−DV = deep / ventral", text: $targetDVMillimetres)
            }
            .disabled(!model.canStoreImplantTarget)
            Button("Store unprojected site", systemImage: "plus") {
                Task {
                    let added = await model.addUnprojectedImplantTarget(
                        label: targetLabel,
                        apText: targetAPMillimetres,
                        mlText: targetMLMillimetres,
                        dvText: targetDVMillimetres
                    )
                    if added {
                        targetLabel = "Implant site \(model.implantTargets.count + 1)"
                        targetAPMillimetres = ""
                        targetMLMillimetres = ""
                        targetDVMillimetres = ""
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
        return "Atlas AP \(signedMicrometres(point.apMicrometres)) · "
            + "DV \(signedMicrometres(point.dvMicrometres)) · "
            + "ML \(signedMicrometres(point.mlMicrometres))"
    }

    private func voxelSummary(_ result: CalibratedTargetProjectionResult) -> String {
        let voxel = result.containingVoxelIndex
        return "Voxel AP \(voxel.ap) · DV \(voxel.dv) · ML \(voxel.ml)"
    }

    private func signedMicrometres(_ value: Double) -> String {
        String(format: "%+.1f µm", value)
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
                TextField("0.000", text: text)
                    .textFieldStyle(.roundedBorder)
                    .multilineTextAlignment(.trailing)
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

private struct MajorVesselConflictInspectorSheet: View {
    @ObservedObject var model: PlannerViewModel
    @Environment(\.dismiss) private var dismiss

    private var result: MajorVesselAnalysisResult? {
        model.selectedProbeVesselAnalysis
    }

    private var selectedConflict: MajorVesselConflict? {
        guard let selected = model.selectedMajorVesselConflict,
              result?.analysis.conflicts.contains(selected) == true
        else { return nil }
        return selected
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if let result {
                provenanceBanner(result)
                Divider()
                HSplitView {
                    conflictList(result.analysis)
                        .frame(minWidth: 690, idealWidth: 760)
                    conflictDetail(result)
                        .frame(minWidth: 430, idealWidth: 500)
                }
            } else {
                ContentUnavailableView(
                    "No current vessel analysis",
                    systemImage: "drop.triangle",
                    description: Text("Run probe clearance analysis before inspecting conflicts.")
                )
            }
        }
        .frame(minWidth: 1_180, minHeight: 720)
    }

    private var header: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Major-vessel conflicts")
                    .font(.title2.weight(.semibold))
                Text("Select any returned row to atomically localize its probe point in all three atlas views.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if model.majorVesselNavigationInProgress {
                ProgressView("Navigating all views…")
                    .controlSize(.small)
            }
            if selectedConflict != nil {
                Button("Clear selection") {
                    model.clearMajorVesselConflictSelection()
                }
            }
            Button("Done") { dismiss() }
                .keyboardShortcut(.cancelAction)
        }
        .padding(16)
    }

    private func provenanceBanner(_ result: MajorVesselAnalysisResult) -> some View {
        let source = result.analysis.provenance
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Label(
                    "\(result.analysis.conflicts.count) returned"
                        + (result.analysis.conflictsTruncated ? " · response truncated" : ""),
                    systemImage: result.analysis.conflictsTruncated
                        ? "exclamationmark.triangle.fill" : "checklist"
                )
                .font(.callout.weight(.semibold))
                Spacer()
                Text("Project revision \(result.projectRevision) · plan v\(result.planVersion)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            Text("\(source.datasetTitle) · specimen \(source.specimenId) · \(source.sourceLicense)")
                .font(.caption)
            Text(
                "Reference-only, not subject-specific; pial and choroidal vessels are excluded. "
                    + "Registration and tissue-distortion bounds are not published."
            )
            .font(.caption)
            .foregroundStyle(.orange)
            .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 14) {
                if let dataset = URL(string: source.sourceRecordUrl) {
                    Link("Dataset", destination: dataset)
                }
                if let paper = URL(string: "https://doi.org/\(source.sourcePaperDoi)") {
                    Link("Paper", destination: paper)
                }
                Text("Asset \(String(source.derivedAssetSha256.prefix(14)))…")
                    .textSelection(.enabled)
            }
            .font(.caption.monospaced())
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.quaternary.opacity(0.45))
    }

    private func conflictList(_ analysis: MajorVesselClearanceAnalysis) -> some View {
        VStack(spacing: 0) {
            conflictColumnHeader
            Divider()
            List(analysis.conflicts) { conflict in
                Button {
                    Task { _ = await model.navigateToMajorVesselConflict(conflict) }
                } label: {
                    conflictRow(conflict)
                }
                .buttonStyle(.plain)
                .disabled(model.majorVesselNavigationInProgress)
                .listRowBackground(
                    selectedConflict?.conflictId == conflict.conflictId
                        ? Color.accentColor.opacity(0.20) : Color.clear
                )
                .accessibilityLabel(
                    "\(classificationLabel(conflict.classification)), shank "
                        + "\(conflict.shankId), depth \(micrometres(conflict.insertionDepthMicrometres))"
                )
                .accessibilityHint("Select and navigate all atlas views to this conflict")
            }
            .listStyle(.inset)
        }
    }

    private var conflictColumnHeader: some View {
        HStack(spacing: 8) {
            Text("Status").frame(width: 142, alignment: .leading)
            Text("Shank").frame(width: 80, alignment: .leading)
            Text("Depth µm").frame(width: 82, alignment: .trailing)
            Text("Adjusted µm").frame(width: 92, alignment: .trailing)
            Text("Centerline µm").frame(width: 100, alignment: .trailing)
            Text("Vessel Ø µm").frame(width: 90, alignment: .trailing)
            Spacer(minLength: 4)
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(.secondary)
        .padding(.horizontal, 18)
        .padding(.vertical, 8)
    }

    private func conflictRow(_ conflict: MajorVesselConflict) -> some View {
        HStack(spacing: 8) {
            HStack(spacing: 5) {
                if selectedConflict?.conflictId == conflict.conflictId {
                    Image(systemName: "location.fill")
                        .foregroundStyle(Color.accentColor)
                }
                Text(classificationLabel(conflict.classification))
                    .lineLimit(1)
            }
            .frame(width: 142, alignment: .leading)
            Text(conflict.shankId)
                .lineLimit(1)
                .frame(width: 80, alignment: .leading)
            numericCell(conflict.insertionDepthMicrometres, width: 82)
            numericCell(conflict.adjustedClearanceMicrometres, width: 92, signed: true)
            numericCell(conflict.centerlineDistanceMicrometres, width: 100)
            numericCell(conflict.vesselDiameterMicrometres, width: 90)
            Spacer(minLength: 4)
            Image(systemName: "chevron.right")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .font(.caption.monospacedDigit())
        .contentShape(Rectangle())
        .padding(.vertical, 4)
    }

    private func numericCell(
        _ value: Double,
        width: CGFloat,
        signed: Bool = false
    ) -> some View {
        Text(String(format: signed ? "%+.2f" : "%.2f", value))
            .frame(width: width, alignment: .trailing)
    }

    @ViewBuilder
    private func conflictDetail(_ result: MajorVesselAnalysisResult) -> some View {
        if let conflict = selectedConflict {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Label("Selected conflict", systemImage: "location.fill")
                        .font(.headline)
                        .foregroundStyle(Color.accentColor)
                    if let error = model.majorVesselNavigationError {
                        Label(error, systemImage: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundStyle(.red)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    detailSection("Identity") {
                        detailRow("Conflict ID", conflict.conflictId)
                        detailRow("Classification", classificationLabel(conflict.classification))
                        detailRow("Shank ID", conflict.shankId)
                        detailRow("Source edge", "\(conflict.vesselSourceEdgeIndex)")
                        detailRow("Vessel run", "\(conflict.vesselRunIndex)")
                        detailRow("Segment in run", "\(conflict.vesselSegmentIndexInRun)")
                    }
                    detailSection("Measured geometry") {
                        detailRow("Insertion depth", micrometres(conflict.insertionDepthMicrometres))
                        detailRow("Vessel diameter", micrometres(conflict.vesselDiameterMicrometres))
                        detailRow("Probe-envelope radius", micrometres(conflict.probeEnvelopeRadiusMicrometres))
                        detailRow("Centerline distance", micrometres(conflict.centerlineDistanceMicrometres))
                        detailRow("Geometric surface clearance", signedMicrometres(conflict.geometricSurfaceClearanceMicrometres))
                        detailRow("Required margin", micrometres(conflict.requiredMarginMicrometres))
                        detailRow("Registration uncertainty", micrometres(conflict.registrationUncertaintyMicrometres))
                        detailRow("Adjusted clearance", signedMicrometres(conflict.adjustedClearanceMicrometres))
                    }
                    detailSection("Closest points · physical ASR") {
                        detailRow("Probe point", pointDescription(conflict.probePoint))
                        detailRow("Vessel point", pointDescription(conflict.vesselPoint))
                        detailRow("Frame", conflict.probePoint.frameId)
                    }
                    detailSection("Source fields") {
                        detailRow("Source kind", conflict.sourceKind)
                        detailRow("Subject-specific", conflict.subjectSpecific ? "yes" : "no")
                        ForEach(Array(conflict.warnings.enumerated()), id: \.offset) { index, warning in
                            detailRow("Warning \(index + 1)", warning)
                        }
                    }
                    completeProvenance(result)
                }
                .padding(16)
            }
        } else {
            ContentUnavailableView(
                "Select a conflict",
                systemImage: "cursorarrow.click.2",
                description: Text(
                    "A selected row shows every returned field and moves Coronal, Sagittal, and Horizontal to its probe point in one revision."
                )
            )
        }
    }

    private func completeProvenance(_ result: MajorVesselAnalysisResult) -> some View {
        let analysis = result.analysis
        let source = analysis.provenance
        let profile = analysis.riskProfile
        return detailSection("Analysis and source provenance") {
            detailRow("Algorithm", analysis.algorithmVersion)
            detailRow("Analysis SHA-256", analysis.inputSha256)
            detailRow("Plan input SHA-256", result.planInputSha256)
            detailRow("Risk profile", profile.profileId)
            detailRow("Lab policy", profile.sourceOrLabPolicy)
            detailRow("Inputs confirmed", profile.confirmedByUser ? "yes" : "no")
            detailRow("Reference coverage acknowledged", profile.referenceOnlyCoverageAcknowledged ? "yes" : "no")
            detailRow("Candidate segments", "\(analysis.candidateSegmentCount)")
            detailRow("Measured segments", "\(analysis.measuredSegmentCount)")
            detailRow("Source ID", source.sourceId)
            detailRow("Dataset", source.datasetTitle)
            detailRow("Authors", source.authors.joined(separator: "; "))
            detailRow("Specimen", source.specimenId)
            detailRow("Dataset DOI", source.sourceDoi)
            detailRow("Paper DOI", source.sourcePaperDoi)
            detailRow("Source version", source.sourceVersion)
            detailRow("License", source.sourceLicense)
            detailRow("Archive digest", source.sourceArchiveDigest)
            detailRow("Derived asset SHA-256", source.derivedAssetSha256)
            detailRow("Extraction algorithm", source.extractionAlgorithmVersion)
            detailRow("Atlas", "\(source.atlasIdentifier) \(source.atlasVersion)")
            detailRow("Coordinate frame", source.coordinateFrameId)
            detailRow("Minimum included diameter", micrometres(source.minimumIncludedDiameterMicrometres))
            detailRow("Physical units declared", yesNo(source.physicalUnitsDeclared))
            detailRow("Atlas scale applied", yesNo(source.atlasScaleApplied))
            detailRow("Geometry source audited", yesNo(source.geometrySourceAudited))
            detailRow("Subject-specific source", yesNo(source.subjectSpecific))
            detailRow("Pial vessels excluded", yesNo(source.pialVesselsExcluded))
            detailRow("Choroidal vessels excluded", yesNo(source.choroidalVesselsExcluded))
            detailRow("Artery/vein classification", yesNo(source.arteryVeinClassificationAvailable))
            detailRow("Registration transform", source.registrationTransformId ?? "not published")
            detailRow("Registration bound", source.registrationUncertaintyBoundMicrometres.map(micrometres) ?? "not published")
            detailRow("Tissue-distortion bound", source.tissueDistortionUncertaintyBoundMicrometres.map(micrometres) ?? "not published")
            detailRow("Uncertainty bounds reviewed", yesNo(source.uncertaintyBoundsReviewed))
            ForEach(Array(result.limitations.enumerated()), id: \.offset) { index, limitation in
                detailRow("Limitation \(index + 1)", limitation)
            }
        }
    }

    private func detailSection<Content: View>(
        _ title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(.quaternary.opacity(0.55), in: RoundedRectangle(cornerRadius: 8))
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label)
                .font(.caption2.weight(.medium))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.monospacedDigit())
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func classificationLabel(
        _ classification: MajorVesselConflictClassification
    ) -> String {
        switch classification {
        case .intersection: "Intersection"
        case .marginViolation: "Margin violation"
        case .uncertaintyViolation: "Uncertainty violation"
        }
    }

    private func micrometres(_ value: Double) -> String {
        String(format: "%.3f µm", value)
    }

    private func signedMicrometres(_ value: Double) -> String {
        String(format: "%+.3f µm", value)
    }

    private func pointDescription(_ point: MajorVesselPhysicalPoint) -> String {
        "AP \(signedMicrometres(point.apMicrometres)) · "
            + "DV \(signedMicrometres(point.dvMicrometres)) · "
            + "ML \(signedMicrometres(point.mlMicrometres))"
    }

    private func yesNo(_ value: Bool) -> String { value ? "yes" : "no" }
}

private struct VesselAnalysisDraft: Equatable {
    var requiredMarginMicrometres = ""
    var registrationUncertaintyMicrometres = ""
    var riskProfileConfirmed = false
    var referenceCoverageAcknowledged = false

    init() {}

    init(analysis: MajorVesselClearanceAnalysis) {
        let profile = analysis.riskProfile
        requiredMarginMicrometres = String(profile.requiredMarginMicrometres)
        registrationUncertaintyMicrometres = String(
            profile.registrationUncertaintyMicrometres
        )
        riskProfileConfirmed = profile.confirmedByUser
        referenceCoverageAcknowledged = profile.referenceOnlyCoverageAcknowledged
    }

    func matches(_ analysis: MajorVesselClearanceAnalysis) -> Bool {
        let profile = analysis.riskProfile
        guard let margin = Double(requiredMarginMicrometres.trimmingCharacters(
            in: .whitespacesAndNewlines
        )),
              let uncertainty = Double(registrationUncertaintyMicrometres.trimmingCharacters(
                  in: .whitespacesAndNewlines
              ))
        else { return false }
        return margin == profile.requiredMarginMicrometres
            && uncertainty == profile.registrationUncertaintyMicrometres
            && riskProfileConfirmed == profile.confirmedByUser
            && referenceCoverageAcknowledged
                == profile.referenceOnlyCoverageAcknowledged
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
