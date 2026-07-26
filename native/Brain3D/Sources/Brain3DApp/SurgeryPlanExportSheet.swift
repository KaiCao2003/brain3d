import AppKit
import Brain3DCore
import SwiftUI

struct SurgeryPlanExportSheet: View {
    @ObservedObject var model: PlannerViewModel
    let hasUnappliedProbeEdits: Bool
    @Environment(\.dismiss) private var dismiss

    @AppStorage(SurgeryPlanPDFPreferences.protocolTemplatePathKey)
    private var protocolTemplatePath = ""
    @AppStorage(SurgeryPlanPDFPreferences.atlasPDFPathKey)
    private var atlasPDFPath = ""

    @State private var selectedTargetId: String
    @State private var targetLabel: String
    @State private var surgeryDate = Date()
    @State private var cageId = ""
    @State private var mouseNumber: String
    @State private var weightGrams = ""
    @State private var operatorName = ""
    @State private var viewSelection: SurgeryPlanViewSelection
    @State private var atlasOrientation: SurgeryAtlasOrientation
    @State private var protocolPDFStatus = SurgeryPlanPDFLocationStatus(
        state: .missing,
        detail: "Choose this PDF once in Settings."
    )
    @State private var atlasPDFStatus = SurgeryPlanPDFLocationStatus(
        state: .missing,
        detail: "Choose this PDF once in Settings."
    )
    @State private var resolvedAtlasPDFURL: URL?
    @State private var resolvedAtlasRequiredSHA256: String?
    @State private var atlasIsBundled = false
    @State private var resolvedAtlasPlate: SurgeryAtlasPlate?
    @State private var atlasResolutionError: String?
    @State private var isExporting = false
    @State private var exportError: String?
    @State private var exportedResult: SurgeryPlanExportResult?

    init(
        model: PlannerViewModel,
        hasUnappliedProbeEdits: Bool = false
    ) {
        self.model = model
        self.hasUnappliedProbeEdits = hasUnappliedProbeEdits
        let defaultTargetId = model.selectedProbePlan?.surfaceRelativeInput == nil
            ? (model.selectedProbePlan?.targetId
            ?? model.implantTargets.first?.targetId
            ?? "")
            : (model.selectedProbePlan?.planId ?? "")
        let defaultTarget = model.implantTargets.first {
            $0.targetId == defaultTargetId
        }
        _selectedTargetId = State(initialValue: defaultTargetId)
        _targetLabel = State(
            initialValue: model.selectedProbePlan?.surfaceRelativeInput == nil
                ? (defaultTarget?.label ?? "")
                : (model.selectedProbePlan?.name ?? "")
        )
        _mouseNumber = State(initialValue: "")
        _viewSelection = State(
            initialValue: SurgeryPlanViewSelection(
                workspaceMode: model.workspaceMode
            )
        )
        _atlasOrientation = State(
            initialValue: model.workspaceMode == .sagittal
                ? .sagittal
                : .coronal
        )
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Export Surgery Plan")
                        .font(.title2.weight(.semibold))
                    Text("Prefilled protocol, selected planning views, and one matched atlas plate")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.borderless)
                .disabled(isExporting)
                .accessibilityLabel("Close surgery plan export")
            }
            .padding(20)

            Divider()

            Form {
                Section("Plan") {
                    if let directSurfacePlan {
                        LabeledContent("Probe") {
                            Text(
                                "\(directSurfacePlan.modelDisplayName) · "
                                    + "\(directSurfacePlan.name)"
                            )
                            .font(.caption)
                            .multilineTextAlignment(.trailing)
                        }
                    } else {
                        Picker("Archived implant target", selection: $selectedTargetId) {
                            ForEach(model.implantTargets) { target in
                                Text(target.label).tag(target.targetId)
                            }
                        }
                    }
                    TextField("Target region / label", text: $targetLabel)
                    DatePicker(
                        "Date",
                        selection: $surgeryDate,
                        displayedComponents: .date
                    )
                    LabeledContent("Export status") {
                        Text(exportClass.rawValue)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(
                                exportClass == .final ? .green : .orange
                            )
                    }
                    if exportClass == .draft {
                        Text(
                            "DRAFT — save the current animal plan before final export."
                        )
                        .font(.caption)
                        .foregroundStyle(.orange)
                    }
                }

                Section("Animal record") {
                    LabeledContent("Subject ID") {
                        Text(model.backendState?.project?.subjectId ?? "Unavailable")
                            .textSelection(.enabled)
                    }
                    TextField("Mouse number", text: $mouseNumber)
                    TextField("Cage ID", text: $cageId)
                    TextField("Weight (g)", text: $weightGrams)
                    TextField("Operator", text: $operatorName)
                }

                Section("Planning pages") {
                    Picker("Views", selection: $viewSelection) {
                        ForEach(SurgeryPlanViewSelection.allCases) { selection in
                            Text(selection.rawValue).tag(selection)
                        }
                    }
                    Text(viewReadinessText)
                        .font(.caption)
                        .foregroundStyle(
                            unavailableSelectedViews.isEmpty
                                ? Color.secondary
                                : Color.orange
                        )
                    if model.majorVesselGeometry != nil {
                        Label(
                            "Every page is bound to VesSAP; target slices report the "
                                + "actual intersecting segment count.",
                            systemImage: "drop.fill"
                        )
                        .font(.caption)
                        .foregroundStyle(.red)
                    } else {
                        Label(
                            "Waiting for the reviewed major-vessel layer.",
                            systemImage: "exclamationmark.triangle"
                        )
                        .font(.caption)
                        .foregroundStyle(.orange)
                    }
                }

                Section("PDF sources") {
                    pdfStatusRow(
                        title: "Headplate protocol PDF",
                        status: protocolPDFStatus
                    )
                    pdfStatusRow(
                        title: "Mouse Brain atlas PDF",
                        status: atlasPDFStatus,
                        readyLabel: atlasIsBundled ? "Included" : "Ready"
                    )
                    SettingsLink {
                        Label("PDF Locations…", systemImage: "gearshape")
                    }
                    .controlSize(.small)
                }

                Section("Atlas page") {
                    Picker("Plate orientation", selection: $atlasOrientation) {
                        ForEach(SurgeryAtlasOrientation.allCases) { orientation in
                            Text(orientation.rawValue).tag(orientation)
                        }
                    }
                    if let resolvedAtlasPlate {
                        LabeledContent("Matched plate") {
                            Text(resolvedAtlasPlate.displayName)
                                .font(.caption.monospacedDigit())
                        }
                        if let coordinates = selectedCoordinates {
                            let requested = atlasOrientation == .coronal
                                ? coordinates.ap
                                : abs(coordinates.ml)
                            Text(
                                String(
                                    format:
                                        "Requested %.3f mm · plate %.2f mm · Δ %+.3f mm",
                                    requested,
                                    resolvedAtlasPlate.fixedCoordinateMillimetres,
                                    resolvedAtlasPlate.fixedCoordinateMillimetres
                                        - requested
                                )
                            )
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                            if atlasOrientation == .sagittal {
                                Text(
                                    "The plate is matched by |ML|. "
                                        + (directSurfacePlan != nil
                                            ? (coordinates.ml < 0
                                                ? "This insertion remains explicitly left (ML−)."
                                                : "This insertion remains explicitly right (ML+).")
                                            : (coordinates.ml < 0
                                                ? "This target remains explicitly left (ML−)."
                                                : "This target remains explicitly right (ML+)."))
                                )
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            }
                        }
                    } else if let atlasResolutionError {
                        Label(
                            atlasResolutionError,
                            systemImage: "exclamationmark.triangle"
                        )
                        .font(.caption)
                        .foregroundStyle(.orange)
                    }
                }
            }
            .formStyle(.grouped)
            .scrollContentBackground(.hidden)

            Divider()

            HStack(spacing: 12) {
                if isExporting {
                    ProgressView()
                        .controlSize(.small)
                    Text("Rendering and verifying PDF…")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if let result = exportedResult {
                    Label(
                        "\(result.pageCount) pages · \(result.atlasPlate.displayName)",
                        systemImage: "checkmark.circle.fill"
                    )
                    .font(.caption)
                    .foregroundStyle(.green)
                    Button("Reveal") {
                        NSWorkspace.shared.activateFileViewerSelecting([
                            result.outputURL,
                        ])
                    }
                    .controlSize(.small)
                } else if let exportError {
                    Label(exportError, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                        .lineLimit(3)
                } else if let blockingReason {
                    Text(blockingReason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Spacer()

                Button("Cancel") {
                    dismiss()
                }
                .disabled(isExporting)

                Button("Export PDF…", systemImage: "doc.richtext") {
                    beginExport()
                }
                .buttonStyle(.borderedProminent)
                .disabled(isExporting || blockingReason != nil)
            }
            .padding(16)
        }
        .frame(width: 680, height: 760)
        .interactiveDismissDisabled(isExporting)
        .onChange(of: selectedTargetId, initial: true) { _, _ in
            if let selectedTarget {
                targetLabel = selectedTarget.label
            }
            resolveAtlasPlate()
        }
        .onChange(of: atlasOrientation) { _, _ in
            resolveAtlasPlate()
        }
        .onChange(of: protocolTemplatePath, initial: true) { _, _ in
            refreshProtocolPDFStatus()
        }
        .onChange(of: atlasPDFPath, initial: true) { _, _ in
            resolveAtlasPlate()
        }
        .onChange(of: viewSelection) { _, selection in
            switch selection {
            case .coronal:
                atlasOrientation = .coronal
            case .sagittal:
                atlasOrientation = .sagittal
            default:
                break
            }
        }
        .task(id: viewSelection) {
            if viewSelection.views.contains(.threeDimensional),
               model.threeDimensionalSnapshot == nil
            {
                await model.prepareThreeDimensionalScene()
            }
        }
    }

    private var selectedTarget: UnprojectedImplantTarget? {
        model.implantTargets.first { $0.targetId == selectedTargetId }
    }

    private var directSurfacePlan: ProbePlanDetail? {
        guard let atlas = model.viewerSnapshot?.atlas else { return nil }
        return SurgeryPlanReadiness.currentSurfaceProbePlan(
            model.selectedProbePlan,
            atlas: atlas
        )
    }

    private var selectedCoordinates: (ap: Double, ml: Double)? {
        if let input = directSurfacePlan?.surfaceRelativeInput {
            return (
                ap: input.insertionAPMillimetres,
                ml: input.insertionMLMillimetres
            )
        }
        guard let selectedTarget else { return nil }
        return (
            ap: selectedTarget.apMillimetres,
            ml: selectedTarget.mlMillimetres
        )
    }

    private var matchingPlan: ProbePlanDetail? {
        if let directSurfacePlan {
            return directSurfacePlan
        }
        guard let project = model.backendState?.project,
              let target = selectedTarget,
              let atlas = model.viewerSnapshot?.atlas,
              let calibration = model.activeCalibration,
              let projection = SurgeryPlanReadiness.currentProjection(
                  model.projection(for: target.targetId),
                  project: project,
                  target: target,
                  calibration: calibration,
                  atlas: atlas
              )
        else { return nil }
        return SurgeryPlanReadiness.currentProbePlan(
            model.selectedProbePlan,
            target: target,
            projection: projection,
            calibration: calibration,
            atlas: atlas
        )
    }

    private var exportClass: SurgeryPlanExportClass {
        if let directSurfacePlan,
           let project = model.backendState?.project
        {
            return SurgeryPlanReadiness.exportClass(
                project: project,
                hasUnsavedChanges: model.hasUnsavedChanges,
                surfaceProbePlan: directSurfacePlan
            )
        }
        guard let project = model.backendState?.project,
              let target = selectedTarget,
              let atlas = model.viewerSnapshot?.atlas,
              let calibration = model.activeCalibration,
              let projection = SurgeryPlanReadiness.currentProjection(
                  model.projection(for: target.targetId),
                  project: project,
                  target: target,
                  calibration: calibration,
                  atlas: atlas
              )
        else { return .draft }
        return SurgeryPlanReadiness.exportClass(
            project: project,
            hasUnsavedChanges: model.hasUnsavedChanges,
            calibration: calibration,
            projection: projection,
            probePlan: matchingPlan
        )
    }

    private var unavailableSelectedViews: [SurgeryPlanView] {
        viewSelection.views.filter { view in
            switch view {
            case .dorsal:
                model.dorsalSurface == nil || model.dorsalSurfacePNG == nil
            case .coronal:
                model.viewerSnapshot == nil
            case .sagittal:
                model.viewerSnapshot == nil
            case .horizontal:
                model.viewerSnapshot == nil
            case .threeDimensional:
                model.threeDimensionalSnapshot == nil
            }
        }
    }

    private var viewReadinessText: String {
        if unavailableSelectedViews.isEmpty {
            return viewSelection.views.map(\.rawValue).joined(separator: " · ")
        }
        return "Not ready: "
            + unavailableSelectedViews.map(\.rawValue).joined(separator: ", ")
    }

    private var blockingReason: String? {
        guard !hasUnappliedProbeEdits else {
            return "Finish the numeric edit with Return or leave the field, then wait "
                + "for the probe update before exporting."
        }
        guard model.backendState?.project != nil else {
            return "Open an animal plan first."
        }
        guard directSurfacePlan != nil || selectedTarget != nil else {
            return "Create an NP2003 or NP2013 probe plan first."
        }
        if directSurfacePlan != nil {
            guard model.majorVesselGeometry != nil else {
                return "Wait for the reviewed major-vessel layer to finish loading."
            }
        } else {
        guard let project = model.backendState?.project,
              let target = selectedTarget,
              let atlas = model.viewerSnapshot?.atlas,
              SurgeryPlanReadiness.currentProjection(
                  model.projection(for: target.targetId),
                  project: project,
                  target: target,
                  calibration: model.activeCalibration,
                  atlas: atlas
              ) != nil
        else {
            return "Project the selected target with the active calibration."
        }
        }
        guard model.majorVesselGeometry != nil else {
            return "Wait for the reviewed major-vessel layer to finish loading."
        }
        guard unavailableSelectedViews.isEmpty else {
            return "Load every selected view or choose a ready view."
        }
        guard protocolPDFStatus.isReady else {
            return "Set the Headplate protocol PDF in Settings."
        }
        guard atlasPDFStatus.isReady else {
            return atlasPDFStatus.detail
        }
        guard resolvedAtlasPlate != nil else {
            return atlasResolutionError ?? "Resolve a matching atlas plate."
        }
        return nil
    }

    @ViewBuilder
    private func pdfStatusRow(
        title: String,
        status: SurgeryPlanPDFLocationStatus,
        readyLabel: String = "Ready"
    ) -> some View {
        LabeledContent(title) {
            Label(
                status.isReady ? readyLabel : status.shortLabel,
                systemImage: status.isReady
                    ? "checkmark.circle.fill"
                    : "exclamationmark.circle.fill"
            )
            .font(.caption.weight(.semibold))
            .foregroundStyle(status.isReady ? Color.green : Color.orange)
            .help(status.detail)
        }
    }

    private func refreshProtocolPDFStatus() {
        protocolPDFStatus = SurgeryPlanPDFPreferences.status(
            for: .protocolTemplate,
            path: protocolTemplatePath
        )
        exportedResult = nil
        exportError = nil
    }

    private func resolveAtlasPlate() {
        resolvedAtlasPlate = nil
        resolvedAtlasPDFURL = nil
        resolvedAtlasRequiredSHA256 = nil
        atlasIsBundled = false
        atlasResolutionError = nil
        let location = SurgeryPlanPDFPreferences.atlasLocation(
            savedPath: atlasPDFPath
        )
        atlasPDFStatus = location.status
        resolvedAtlasPDFURL = location.url
        resolvedAtlasRequiredSHA256 = location.requiredSourceSHA256
        atlasIsBundled = location.isBundled
        guard atlasPDFStatus.isReady else {
            atlasResolutionError = atlasPDFStatus.detail
            return
        }
        guard let atlasPDFURL = resolvedAtlasPDFURL,
              let coordinates = selectedCoordinates
        else { return }
        do {
            resolvedAtlasPlate = try SurgeryAtlasCatalog.nearestPlate(
                in: atlasPDFURL,
                orientation: atlasOrientation,
                apMillimetres: coordinates.ap,
                mlMillimetres: coordinates.ml
            )
        } catch {
            atlasResolutionError = error.localizedDescription
        }
    }

    private func beginExport() {
        refreshProtocolPDFStatus()
        resolveAtlasPlate()
        guard blockingReason == nil,
              let atlasPDFURL = resolvedAtlasPDFURL
        else { return }
        let panel = NSSavePanel()
        panel.title = "Save Surgery Plan"
        panel.prompt = "Export"
        panel.allowedContentTypes = [.pdf]
        panel.canCreateDirectories = true
        panel.nameFieldStringValue = suggestedFileName
        guard panel.runModal() == .OK, let outputURL = panel.url else { return }

        isExporting = true
        exportError = nil
        exportedResult = nil
        let configuration = SurgeryPlanExportConfiguration(
            targetId: selectedTargetId,
            targetLabel: targetLabel,
            date: surgeryDate,
            cageId: cageId,
            mouseNumber: mouseNumber,
            weightGrams: weightGrams,
            operatorName: operatorName,
            viewSelection: viewSelection,
            protocolTemplateURL: URL(fileURLWithPath: protocolTemplatePath),
            atlasPDFURL: atlasPDFURL,
            requiredAtlasSourceSHA256: resolvedAtlasRequiredSHA256,
            atlasOrientation: atlasOrientation
        )
        Task {
            defer { isExporting = false }
            do {
                exportedResult = try await SurgeryPlanExporter.export(
                    model: model,
                    configuration: configuration,
                    outputURL: outputURL
                )
            } catch {
                exportError = error.localizedDescription
            }
        }
    }

    private var suggestedFileName: String {
        let subject = model.backendState?.project?.subjectId ?? "mouse"
        let sanitized = subject
            .replacingOccurrences(
                of: #"[^A-Za-z0-9._-]+"#,
                with: "-",
                options: .regularExpression
            )
            .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        return "\(sanitized.isEmpty ? "mouse" : sanitized)-surgery-plan.pdf"
    }
}
