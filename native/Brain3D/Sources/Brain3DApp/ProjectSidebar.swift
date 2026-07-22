import Brain3DCore
import Foundation
import SwiftUI

struct ProjectSidebar: View {
    @ObservedObject var model: PlannerViewModel
    let importVesselImage: () -> Void
    let registerVesselImage: () -> Void
    let saveProject: () -> Void
    let openProject: () -> Void
    let reconnect: () -> Void
    @State private var targetLabel = "Implant site 1"
    @State private var targetAPMillimetres = ""
    @State private var targetMLMillimetres = ""
    @State private var targetDVMillimetres = ""

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    projectHeader
                    backendSection
                    atlasSection
                    implantTargetSection
                    subjectVesselsSection
                    populationDensitySection
                }
                .padding(16)
            }
            SafetyNotice(compact: true)
                .padding(12)
                .background(.bar)
        }
        .background(.thinMaterial)
    }

    private var implantTargetSection: some View {
        SidebarSection(title: "Implant target", systemImage: "scope") {
            StatusRow(
                label: "Coordinate frame",
                value: "Bregma-relative AP / ML / DV in millimetres"
            )
            StatusRow(
                label: "Projection",
                value: "Locked — bregma/skull calibration is required"
            )
            StatusRow(
                label: "Stored sites",
                value: "\(model.implantTargets.count) unprojected"
            )
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
            ForEach(model.implantTargets) { target in
                implantTargetCard(target)
            }
            Text("No atlas position is inferred from these fields before calibration.")
                .font(.caption)
                .foregroundStyle(.orange)
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
            Text("From bregma · unprojected · not usable for navigation")
                .font(.caption2.weight(.medium))
                .foregroundStyle(.orange)
        }
        .padding(8)
        .background(.quaternary.opacity(0.7), in: RoundedRectangle(cornerRadius: 7))
        .accessibilityElement(children: .combine)
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
        VStack(alignment: .leading, spacing: 5) {
            Label("Untitled animal plan", systemImage: "cross.case")
                .font(.title3.weight(.semibold))
            Text("Mouse stereotaxic planning workspace")
                .font(.caption)
                .foregroundStyle(.secondary)
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

    private var subjectVesselsSection: some View {
        SidebarSection(title: "Subject dorsal image", systemImage: "photo") {
            Text("Optional user-supplied image of this animal. Import does not prove that pixels are blood vessels; use a transparent, independently reviewed vessel mask when available.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            StatusRow(label: "Image", value: model.subjectImportStatus)
            StatusRow(label: "Registration", value: model.subjectRegistrationStatus)
            StatusRow(label: "Residual", value: model.residualStatus)
            StatusRow(label: "Laterality", value: model.lateralityStatus)

            if let provenance = model.localVessel {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Local provenance")
                        .font(.caption.weight(.semibold))
                    Text(provenance.fileName)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Text(ByteCountFormatter.string(fromByteCount: Int64(provenance.byteCount), countStyle: .file))
                    Text("SHA-256 \(provenance.sha256)")
                        .font(.caption2.monospaced())
                        .lineLimit(2)
                        .textSelection(.enabled)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let imported = model.backendState?.subjectVessels.primaryImage {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Persisted backend byte provenance")
                        .font(.caption.weight(.semibold))
                    Text("\(imported.widthPixels) × \(imported.heightPixels) px · "
                        + ByteCountFormatter.string(
                            fromByteCount: Int64(imported.byteSize),
                            countStyle: .file
                        ))
                    Text("SHA-256 \(imported.sourceSha256)")
                        .font(.caption2.monospaced())
                        .lineLimit(2)
                        .textSelection(.enabled)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let error = model.vesselImportError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            HStack {
                Button("Import subject image", systemImage: "photo.badge.plus") {
                    importVesselImage()
                }
                .disabled(!model.canImportSubjectVessels)
                Button("Register") {
                    registerVesselImage()
                }
                    .disabled(!model.canRegisterSubjectVessels)
                    .help("Requires at least two enabled landmarks and explicit laterality confirmation.")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            if model.vesselImportInProgress {
                ProgressView("Importing and verifying subject image…")
                    .controlSize(.small)
            }
            if let error = model.registrationError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
            }
            Text("Registration remains locked until ≥2 enabled landmarks are entered and laterality is explicitly confirmed. Registration does not validate vessel segmentation.")
                .font(.caption)
                .foregroundStyle(.secondary)
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
