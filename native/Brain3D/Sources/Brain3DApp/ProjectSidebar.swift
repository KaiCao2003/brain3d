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
    @State private var probeAzimuth = ""
    @State private var probeElevation = ""
    @State private var probeDepth = ""
    @State private var probeAxialRotation = ""
    @State private var probeGeometryAcknowledged = false
    @State private var showingProbeRegionInspector = false
    @State private var confirmingProbeRemoval = false
    @State private var vesselMarginMicrometres = ""
    @State private var vesselUncertaintyMicrometres = ""
    @State private var vesselRiskProfileConfirmed = false
    @State private var vesselCoverageAcknowledged = false

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    projectHeader
                    backendSection
                    atlasSection
                    implantTargetSection
                    probeSection
                    majorVesselsSection
                }
                .padding(16)
            }
            SafetyNotice(compact: true)
                .padding(12)
                .background(.bar)
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
            populateProbeDraft()
            vesselRiskProfileConfirmed = false
            vesselCoverageAcknowledged = false
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

            TextField("Probe plan name", text: $probeName)
                .textFieldStyle(.roundedBorder)

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
                } else {
                    Button("Update plan", systemImage: "checkmark") {
                        Task { _ = await updateProbePlan() }
                    }
                    .buttonStyle(.borderedProminent)
                    Button("Remove", systemImage: "trash", role: .destructive) {
                        confirmingProbeRemoval = true
                    }
                }
            }
            .controlSize(.small)
            .disabled(!canSubmitProbeDraft)

            if let plan = model.selectedProbePlan {
                Text(
                    "v\(plan.planVersion) · \(plan.modelDisplayName) · planning only · not navigation"
                )
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

                HStack {
                    Button("Analyze regions", systemImage: "list.bullet.indent") {
                        Task { _ = await model.analyzeSelectedProbeRegions() }
                    }
                    .disabled(!model.canManageProbePlanning)

                    if model.selectedProbeRegionAnalysis != nil {
                        Button("Inspect…", systemImage: "tablecells") {
                            showingProbeRegionInspector = true
                        }
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                if model.selectedProbeRegionAnalysis != nil {
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
            && !probeAzimuth.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !probeElevation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !probeDepth.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !probeAxialRotation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && (model.selectedProbeModel.map {
                !$0.requiresExplicitAcknowledgement || probeGeometryAcknowledged
            } == true)
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

    private func createProbePlan() async -> Bool {
        guard let probe = model.selectedProbeModel else { return false }
        return await model.createProbePlan(
            name: probeName,
            targetId: probeTargetId,
            modelId: probe.modelId,
            modelVersion: probe.modelVersion,
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
            azimuthText: probeAzimuth,
            elevationText: probeElevation,
            insertionDepthText: probeDepth,
            axialRotationText: probeAxialRotation,
            customGeometryAcknowledged: probeGeometryAcknowledged
        )
    }

    private func populateProbeDraft() {
        guard let plan = model.selectedProbePlan else { return }
        probeName = plan.name
        probeTargetId = plan.targetId
        probeAzimuth = decimalText(plan.placement.azimuthDegrees)
        probeElevation = decimalText(plan.placement.elevationDegrees)
        probeDepth = decimalText(plan.placement.insertionDepthMicrometres)
        probeAxialRotation = decimalText(plan.placement.axialRotationDegrees)
        probeGeometryAcknowledged = ProbePlanningContract.requiresExplicitAcknowledgement(
            verificationStatus: plan.verificationStatus
        )
    }

    private func clearProbeDraft() {
        probeName = ""
        probeTargetId = ""
        probeAzimuth = ""
        probeElevation = ""
        probeDepth = ""
        probeAxialRotation = ""
        probeGeometryAcknowledged = false
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
            if model.selectedProbePlan != nil, model.majorVesselGeometry != nil {
                Divider()
                Text("Probe clearance")
                    .font(.caption.weight(.semibold))
                vesselDistanceField(
                    "Required margin (µm)",
                    text: $vesselMarginMicrometres
                )
                vesselDistanceField(
                    "Registration uncertainty (µm)",
                    text: $vesselUncertaintyMicrometres
                )
                Toggle(
                    "I reviewed these lab-defined inputs",
                    isOn: $vesselRiskProfileConfirmed
                )
                .font(.caption)
                .onChange(of: vesselRiskProfileConfirmed) { _, _ in
                    model.invalidateMajorVesselAnalysis()
                }
                Toggle(
                    "I understand this is a single fixed reference with missing vessels",
                    isOn: $vesselCoverageAcknowledged
                )
                .font(.caption)
                .onChange(of: vesselCoverageAcknowledged) { _, _ in
                    model.invalidateMajorVesselAnalysis()
                }
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
                .onChange(of: text.wrappedValue) { _, _ in
                    model.invalidateMajorVesselAnalysis()
                }
        }
    }

    private var canAnalyzeProbeMajorVessels: Bool {
        model.canAnalyzeMajorVesselClearance
            && parsedVesselDistance(vesselMarginMicrometres) != nil
            && parsedVesselDistance(vesselUncertaintyMicrometres) != nil
            && vesselRiskProfileConfirmed
            && vesselCoverageAcknowledged
    }

    private func analyzeProbeMajorVessels() {
        guard let margin = parsedVesselDistance(vesselMarginMicrometres),
              let uncertainty = parsedVesselDistance(vesselUncertaintyMicrometres)
        else { return }
        Task {
            _ = await model.analyzeSelectedProbeMajorVessels(
                requiredMarginMicrometres: margin,
                registrationUncertaintyMicrometres: uncertainty,
                riskProfileConfirmed: vesselRiskProfileConfirmed,
                referenceCoverageAcknowledged: vesselCoverageAcknowledged
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
            ForEach(Array(analysis.conflicts.prefix(3))) { conflict in
                Text(
                    "\(conflict.shankId) · depth "
                        + "\(conflict.insertionDepthMicrometres.formatted(.number.precision(.fractionLength(1)))) µm · "
                        + "adjusted \(signedMicrometres(conflict.adjustedClearanceMicrometres))"
                )
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
            }
            if analysis.conflictsTruncated {
                Text(
                    "Showing \(min(3, analysis.conflicts.count)) of at least "
                        + "\(analysis.conflicts.count) returned conflicts; additional conflicts "
                        + "were truncated."
                )
                .font(.caption2)
                .foregroundStyle(.secondary)
            } else if analysis.conflicts.count > 3 {
                Text("Additional conflicts: \(max(0, analysis.conflicts.count - 3))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
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
        case .insufficientGeometry: "Inputs not confirmed"
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

    private var projectHeader: some View {
        VStack(alignment: .leading, spacing: 0) {
            Label("Untitled animal plan", systemImage: "cross.case")
                .font(.title3.weight(.semibold))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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
            Text("25 µm testing mode. 10 µm is intentionally not offered.")
                .font(.caption)
                .foregroundStyle(.secondary)
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

    private var populationDensitySection: some View {
        SidebarSection(title: "Population density (optional)", systemImage: "circle.grid.cross") {
            StatusRow(label: "Reference", value: model.populationDensityStatus)
            StatusRow(
                label: "Published source",
                value: "\(SafetyPolicy.populationReferenceContributor) · "
                    + SafetyPolicy.populationReferenceRepository
            )
            StatusRow(label: "DOI", value: SafetyPolicy.populationReferenceDOI)
            StatusRow(label: "License", value: SafetyPolicy.populationReferenceLicense)
            StatusRow(label: "Study basis", value: "Four adult mice · 100 µm local window")
            HStack(spacing: 14) {
                Link(
                    "Open Mendeley dataset",
                    destination: URL(string: SafetyPolicy.populationReferenceLandingPage)!
                )
                Link(
                    "Open published paper",
                    destination: URL(string: SafetyPolicy.populationReferencePaperURL)!
                )
            }
            .font(.caption)

            if !model.populationDensityAvailable {
                Button(
                    "Download and prepare published reference (~311 MB)",
                    systemImage: "arrow.down.circle"
                ) {
                    Task { await model.preparePopulationDensity() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(!model.canPreparePopulationDensity)
                .help("Downloads the pinned Mendeley Data v1 archive, verifies SHA-256, and prepares the reviewed population density.")
            }
            if model.populationDensityPrepareInProgress {
                ProgressView("Verifying and preparing published density…")
                    .controlSize(.small)
            }

            Toggle(
                "Show population reference density",
                isOn: Binding(
                    get: { model.populationDensityVisible },
                    set: { shouldShow in
                        Task { await model.setPopulationDensityVisible(shouldShow) }
                    }
                )
            )
            .disabled(!model.populationDensityVisible && !model.canShowPopulationDensity)
            .help("The density projection is available only in the verified Dorsal view.")
            if model.populationDensityOverlayInProgress {
                ProgressView("Rendering dorsal population projection…")
                    .controlSize(.small)
            }
            if let error = model.populationDensityError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if model.populationDensityPreparation != nil || model.populationDensityOverlay != nil {
                Text(model.populationDensityProvenanceStatus)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(SafetyPolicy.populationDensityCaveat)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
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
