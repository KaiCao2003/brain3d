import Brain3DCore
import Foundation
import SwiftUI

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

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    projectHeader
                    backendSection
                    atlasSection
                    implantTargetSection
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
    }

    private var majorVesselsSection: some View {
        SidebarSection(title: "Major vessels", systemImage: "drop.triangle") {
            StatusRow(label: "Geometry", value: "No reviewed 3D vessel graph loaded")
            StatusRow(label: "Display", value: "Major vessels only — capillaries excluded")
            StatusRow(label: "Deep clearance", value: "Unavailable until radius-bearing geometry is loaded")
            Text(
                "This product path accepts published or subject-specific 3D centerlines only when "
                    + "their physical radii, atlas registration, version, and source hash are known."
            )
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
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
