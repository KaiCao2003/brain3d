import Brain3DCore
import SwiftUI

private enum CalibrationSheetPage: String, CaseIterable, Identifiable {
    case saved = "Saved"
    case new = "New"

    var id: String { rawValue }
}

private struct CalibrationLandmarkDraft: Identifiable {
    let id: String
    let label: String
    var skullAP = ""
    var skullML = ""
    var skullDV = ""
    var atlasAP = ""
    var atlasDV = ""
    var atlasML = ""

    static let blank = [
        CalibrationLandmarkDraft(id: "bregma", label: "Bregma"),
        CalibrationLandmarkDraft(id: "lambda", label: "Lambda"),
        CalibrationLandmarkDraft(id: "left-skull", label: "Left skull"),
        CalibrationLandmarkDraft(id: "right-skull", label: "Right skull"),
    ]
}

private struct CalibrationFormError: Error, LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

struct CalibrationSheet: View {
    @ObservedObject var model: PlannerViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var page: CalibrationSheetPage = .saved
    @State private var selectedId: String?
    @State private var pendingRemovalId: String?
    @State private var profileId = ""
    @State private var sourceFrameId = ""
    @State private var sourceOrigin = ""
    @State private var apPositiveDirection = ""
    @State private var mlPositiveDirection = ""
    @State private var dvPositiveDirection = ""
    @State private var rows = CalibrationLandmarkDraft.blank
    @State private var reportedDistance = ""
    @State private var lateralityConfirmed = false
    @State private var dvReferenceDescription = ""
    @State private var minimumAxisBaseline = ""
    @State private var distanceWarning = ""
    @State private var distanceFailure = ""
    @State private var lateralAPWarning = ""
    @State private var lateralAPFailure = ""
    @State private var transformRMSWarning = ""
    @State private var transformRMSFailure = ""
    @State private var limitsSource = ""
    @State private var transformMethod: CalibrationTransformMethod = .rigid
    @State private var notes = ""
    @State private var formError: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Subject calibration")
                    .font(.title2.weight(.semibold))
                Spacer()
                Picker("Page", selection: $page) {
                    ForEach(CalibrationSheetPage.allCases) { page in
                        Text(page.rawValue).tag(page)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 180)
                Button("Close") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding(16)

            Divider()

            Group {
                switch page {
                case .saved: savedPage
                case .new: newPage
                }
            }
        }
        .frame(minWidth: 960, idealWidth: 1_020, minHeight: 640, idealHeight: 720)
        .onAppear {
            selectedId = model.activeCalibrationId ?? model.calibrations.first?.calibrationId
            loadSelected()
        }
        .onChange(of: selectedId) { _, _ in loadSelected() }
        .confirmationDialog(
            "Remove this calibration?",
            isPresented: Binding(
                get: { pendingRemovalId != nil },
                set: { if !$0 { pendingRemovalId = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("Remove calibration", role: .destructive) {
                guard let id = pendingRemovalId else { return }
                pendingRemovalId = nil
                Task {
                    if await model.removeCalibration(calibrationId: id) {
                        selectedId = model.activeCalibrationId
                            ?? model.calibrations.first?.calibrationId
                    }
                }
            }
            Button("Cancel", role: .cancel) { pendingRemovalId = nil }
        }
    }

    private var savedPage: some View {
        HSplitView {
            List(model.calibrations, selection: $selectedId) { calibration in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(calibration.profileId)
                            .font(.body.weight(.medium))
                        if calibration.active {
                            Text("ACTIVE")
                                .font(.caption2.weight(.bold))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 2)
                                .background(.tint.opacity(0.16), in: Capsule())
                        }
                    }
                    Text("v\(calibration.calibrationVersion) · \(calibration.quality.uppercased())")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(qualityColor(calibration.quality))
                }
                .tag(calibration.calibrationId)
                .padding(.vertical, 3)
            }
            .frame(minWidth: 240, idealWidth: 270)

            Group {
                if let calibration = selectedCalibration {
                    calibrationDetail(calibration)
                } else {
                    ContentUnavailableView(
                        "No calibration selected",
                        systemImage: "ruler",
                        description: Text("Create or select a subject calibration.")
                    )
                }
            }
            .frame(minWidth: 560, maxWidth: .infinity, maxHeight: .infinity)
        }
        .overlay(alignment: .bottom) { operationStatus }
    }

    private var selectedCalibration: CalibrationSummary? {
        if let selectedId,
           let loaded = model.selectedCalibration,
           loaded.calibrationId == selectedId
        {
            return loaded
        }
        return model.calibrations.first { $0.calibrationId == selectedId }
    }

    private func calibrationDetail(_ calibration: CalibrationSummary) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(calibration.profileId)
                            .font(.title3.weight(.semibold))
                        Text("Calibration v\(calibration.calibrationVersion) · \(calibration.atlasTransformMethod)")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(calibration.quality.uppercased())
                        .font(.caption.weight(.bold))
                        .foregroundStyle(qualityColor(calibration.quality))
                }

                Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 8) {
                    detailRow("Skull RMS", micrometres(calibration.skullRmsResidualMicrometres))
                    detailRow("Atlas RMS", micrometres(calibration.atlasRmsResidualMicrometres))
                    detailRow("Atlas max", micrometres(calibration.atlasMaximumResidualMicrometres))
                    detailRow("Planning", calibration.permitsPlanning ? "Permitted" : "Blocked")
                    detailRow("Final export", calibration.permitsFinalExport ? "Permitted" : "Blocked")
                    detailRow("Calibration SHA-256", shortDigest(calibration.calibrationSha256))
                    detailRow("Atlas metadata SHA-256", shortDigest(calibration.atlasMetadataSha256))
                }

                if !calibration.qcMessages.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("QC")
                            .font(.headline)
                        ForEach(calibration.qcMessages, id: \.self) { message in
                            Text(message)
                                .font(.caption)
                                .textSelection(.enabled)
                        }
                    }
                }

                HStack {
                    Button("Use for planning") {
                        Task { _ = await model.setActiveCalibration(calibrationId: calibration.id) }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(
                        calibration.active || !calibration.permitsPlanning
                            || model.calibrationOperationInProgress
                    )

                    Button("Revalidate") {
                        Task { _ = await model.validateCalibration(calibrationId: calibration.id) }
                    }
                    .disabled(model.calibrationOperationInProgress)

                    Spacer()

                    Button("Remove", role: .destructive) {
                        pendingRemovalId = calibration.id
                    }
                    .disabled(model.calibrationOperationInProgress)
                }
                .buttonStyle(.bordered)
            }
            .padding(20)
        }
    }

    private var newPage: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    GroupBox("Measured skull frame · AP / ML / DV · µm") {
                        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 8) {
                            formTextRow("Profile ID", text: $profileId)
                            formTextRow("Frame ID", text: $sourceFrameId)
                            formTextRow("Origin", text: $sourceOrigin)
                            formTextRow("+AP direction", text: $apPositiveDirection)
                            formTextRow("+ML direction", text: $mlPositiveDirection)
                            formTextRow("+DV direction", text: $dvPositiveDirection)
                            GridRow {
                                Text("Atlas fit")
                                Picker("Atlas fit", selection: $transformMethod) {
                                    Text("Rigid").tag(CalibrationTransformMethod.rigid)
                                    Text("Similarity").tag(CalibrationTransformMethod.similarity)
                                }
                                .labelsHidden()
                                .pickerStyle(.segmented)
                                .frame(maxWidth: 260)
                            }
                        }
                        .padding(8)
                    }

                    GroupBox("Four matched landmarks") {
                        ScrollView(.horizontal) {
                            Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 8) {
                                GridRow {
                                    Text("Landmark").frame(width: 88, alignment: .leading)
                                    Text("Skull AP").frame(width: 82)
                                    Text("Skull ML").frame(width: 82)
                                    Text("Skull DV").frame(width: 82)
                                    Divider().frame(height: 20)
                                    Text("Atlas AP").frame(width: 82)
                                    Text("Atlas DV").frame(width: 82)
                                    Text("Atlas ML").frame(width: 82)
                                }
                                .font(.caption.weight(.semibold))
                                ForEach($rows) { $row in
                                    GridRow {
                                        Text(row.label).frame(width: 88, alignment: .leading)
                                        coordinateField($row.skullAP)
                                        coordinateField($row.skullML)
                                        coordinateField($row.skullDV)
                                        Divider().frame(height: 24)
                                        coordinateField($row.atlasAP)
                                        coordinateField($row.atlasDV)
                                        coordinateField($row.atlasML)
                                    }
                                }
                            }
                            .padding(8)
                        }
                        Text("Skull order AP / ML / DV · BrainGlobe physical order AP / DV / ML · µm")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 8)
                            .padding(.bottom, 6)
                    }

                    GroupBox("Animal measurement") {
                        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 8) {
                            formTextRow("Reported bregma–lambda distance (µm)", text: $reportedDistance)
                            formTextRow("DV reference description", text: $dvReferenceDescription)
                            GridRow {
                                Text("Laterality")
                                Toggle("Confirmed from this animal", isOn: $lateralityConfirmed)
                            }
                        }
                        .padding(8)
                    }

                    GroupBox("User-defined QC limits · µm") {
                        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 8) {
                            formTextRow("Minimum axis baseline", text: $minimumAxisBaseline)
                            formTextRow("Distance warning", text: $distanceWarning)
                            formTextRow("Distance failure", text: $distanceFailure)
                            formTextRow("Lateral AP warning", text: $lateralAPWarning)
                            formTextRow("Lateral AP failure", text: $lateralAPFailure)
                            formTextRow("Transform RMS warning", text: $transformRMSWarning)
                            formTextRow("Transform RMS failure", text: $transformRMSFailure)
                            formTextRow("Limits source", text: $limitsSource)
                        }
                        .padding(8)
                    }

                    GroupBox("Notes") {
                        TextField("", text: $notes, axis: .vertical)
                            .lineLimit(2...5)
                            .textFieldStyle(.roundedBorder)
                            .padding(8)
                    }
                }
                .padding(18)
            }

            Divider()
            HStack {
                if let error = formError ?? model.calibrationOperationError {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
                Spacer()
                if model.calibrationOperationInProgress {
                    ProgressView().controlSize(.small)
                }
                Button("Create calibration") { submit() }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.calibrationOperationInProgress || !model.canManageCalibration)
            }
            .padding(14)
        }
    }

    @ViewBuilder
    private var operationStatus: some View {
        if model.calibrationOperationInProgress {
            ProgressView("Updating calibration…")
                .controlSize(.small)
                .padding(8)
                .background(.regularMaterial, in: Capsule())
                .padding(12)
        } else if let error = model.calibrationOperationError {
            Label(error, systemImage: "exclamationmark.triangle.fill")
                .font(.caption)
                .foregroundStyle(.red)
                .padding(8)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
                .padding(12)
        }
    }

    private func formTextRow(_ label: String, text: Binding<String>) -> some View {
        GridRow {
            Text(label)
                .frame(minWidth: 180, alignment: .leading)
            TextField("", text: text)
                .textFieldStyle(.roundedBorder)
        }
    }

    private func coordinateField(_ text: Binding<String>) -> some View {
        TextField("", text: text)
            .textFieldStyle(.roundedBorder)
            .multilineTextAlignment(.trailing)
            .frame(width: 82)
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        GridRow {
            Text(label).foregroundStyle(.secondary)
            Text(value).textSelection(.enabled)
        }
    }

    private func qualityColor(_ quality: String) -> Color {
        switch quality {
        case "pass": .green
        case "warning": .orange
        default: .red
        }
    }

    private func micrometres(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(1))) + " µm"
    }

    private func shortDigest(_ digest: String) -> String {
        String(digest.prefix(12)) + "…"
    }

    private func loadSelected() {
        guard let selectedId else { return }
        Task { _ = await model.loadCalibration(calibrationId: selectedId) }
    }

    private func submit() {
        formError = nil
        do {
            let request = try makeRequest()
            Task {
                if await model.createCalibration(request) {
                    selectedId = model.selectedCalibration?.calibrationId
                    page = .saved
                    resetForm()
                }
            }
        } catch {
            formError = error.localizedDescription
        }
    }

    private func makeRequest() throws -> CalibrationCreateParameters {
        guard let projectId = model.calibrationProjectId,
              let projectRevision = model.calibrationProjectRevision
        else { throw CalibrationFormError(message: "No current animal plan is open.") }
        guard rows.count == 4 else {
            throw CalibrationFormError(message: "Exactly four matched landmarks are required.")
        }
        let frameId = sourceFrameId.trimmingCharacters(in: .whitespacesAndNewlines)
        let skull = try rows.map { row in
            CalibrationSkullPoint(
                frameId: frameId,
                ap: try CalibrationNumberInput.parse(row.skullAP, field: "\(row.label) skull AP"),
                ml: try CalibrationNumberInput.parse(row.skullML, field: "\(row.label) skull ML"),
                dv: try CalibrationNumberInput.parse(row.skullDV, field: "\(row.label) skull DV")
            )
        }
        let atlas = try rows.map { row in
            CalibrationAtlasPoint(
                ap: try CalibrationNumberInput.parse(row.atlasAP, field: "\(row.label) atlas AP"),
                dv: try CalibrationNumberInput.parse(row.atlasDV, field: "\(row.label) atlas DV"),
                ml: try CalibrationNumberInput.parse(row.atlasML, field: "\(row.label) atlas ML")
            )
        }
        let request = CalibrationCreateParameters(
            projectId: projectId,
            expectedProjectRevision: projectRevision,
            profileId: profileId.trimmingCharacters(in: .whitespacesAndNewlines),
            sourceFrame: CalibrationSourceFrame(
                frameId: frameId,
                originDescription: sourceOrigin.trimmingCharacters(in: .whitespacesAndNewlines),
                apPositiveDirection: apPositiveDirection.trimmingCharacters(in: .whitespacesAndNewlines),
                mlPositiveDirection: mlPositiveDirection.trimmingCharacters(in: .whitespacesAndNewlines),
                dvPositiveDirection: dvPositiveDirection.trimmingCharacters(in: .whitespacesAndNewlines)
            ),
            skullLandmarks: CalibrationSkullLandmarks(
                bregma: skull[0],
                lambdaPoint: skull[1],
                leftSkull: skull[2],
                rightSkull: skull[3],
                reportedBregmaLambdaDistanceMicrometres: try CalibrationNumberInput.parse(
                    reportedDistance,
                    field: "Reported bregma–lambda distance"
                ),
                lateralityConfirmedFromAnimal: lateralityConfirmed
            ),
            atlasLandmarks: CalibrationAtlasLandmarks(
                bregma: atlas[0],
                lambdaPoint: atlas[1],
                leftSkull: atlas[2],
                rightSkull: atlas[3]
            ),
            qualityLimits: CalibrationQualityLimits(
                minimumAxisBaselineMicrometres: try number(minimumAxisBaseline, "Minimum axis baseline"),
                distanceWarningMicrometres: try number(distanceWarning, "Distance warning"),
                distanceFailureMicrometres: try number(distanceFailure, "Distance failure"),
                lateralApWarningMicrometres: try number(lateralAPWarning, "Lateral AP warning"),
                lateralApFailureMicrometres: try number(lateralAPFailure, "Lateral AP failure"),
                transformRmsWarningMicrometres: try number(transformRMSWarning, "Transform RMS warning"),
                transformRmsFailureMicrometres: try number(transformRMSFailure, "Transform RMS failure")
            ),
            dvReferenceDescription: dvReferenceDescription.trimmingCharacters(in: .whitespacesAndNewlines),
            limitsSource: limitsSource.trimmingCharacters(in: .whitespacesAndNewlines),
            atlasTransformMethod: transformMethod,
            notes: notes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? nil : notes.trimmingCharacters(in: .whitespacesAndNewlines)
        )
        try CalibrationValidator.validateCreate(request)
        return request
    }

    private func number(_ text: String, _ field: String) throws -> Double {
        try CalibrationNumberInput.parse(text, field: field)
    }

    private func resetForm() {
        profileId = ""
        sourceFrameId = ""
        sourceOrigin = ""
        apPositiveDirection = ""
        mlPositiveDirection = ""
        dvPositiveDirection = ""
        rows = CalibrationLandmarkDraft.blank
        reportedDistance = ""
        lateralityConfirmed = false
        dvReferenceDescription = ""
        minimumAxisBaseline = ""
        distanceWarning = ""
        distanceFailure = ""
        lateralAPWarning = ""
        lateralAPFailure = ""
        transformRMSWarning = ""
        transformRMSFailure = ""
        limitsSource = ""
        transformMethod = .rigid
        notes = ""
        formError = nil
    }
}
