import AppKit
import Foundation
import SwiftUI
import UniformTypeIdentifiers

enum SurgeryPlanPDFResource: Sendable {
    case protocolTemplate
    case mouseBrainAtlas

    var title: String {
        switch self {
        case .protocolTemplate:
            "Headplate protocol PDF"
        case .mouseBrainAtlas:
            "Mouse Brain atlas PDF"
        }
    }

    var requiredFileName: String {
        switch self {
        case .protocolTemplate:
            "Headplate Protocol.pdf"
        case .mouseBrainAtlas:
            "MBSC_Figs_with_Layers.pdf"
        }
    }
}

struct SurgeryPlanPDFLocationStatus: Equatable, Sendable {
    enum State: Equatable, Sendable {
        case missing
        case invalid
        case ready
    }

    let state: State
    let detail: String

    var isReady: Bool {
        state == .ready
    }

    var shortLabel: String {
        switch state {
        case .missing:
            "Missing"
        case .invalid:
            "Invalid"
        case .ready:
            "Ready"
        }
    }
}

enum SurgeryPlanPDFPreferences {
    static let protocolTemplatePathKey = "surgeryProtocolTemplatePath"
    static let atlasPDFPathKey = "surgeryAtlasPDFPath"

    static func status(
        for resource: SurgeryPlanPDFResource,
        path: String
    ) -> SurgeryPlanPDFLocationStatus {
        let trimmedPath = path.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !trimmedPath.isEmpty else {
            return SurgeryPlanPDFLocationStatus(
                state: .missing,
                detail: "Choose this PDF once in Settings."
            )
        }

        let url = URL(fileURLWithPath: trimmedPath).standardizedFileURL
        guard (try? url.resourceValues(
            forKeys: [.isRegularFileKey]
        ).isRegularFile) == true else {
            return SurgeryPlanPDFLocationStatus(
                state: .missing,
                detail:
                    "The saved file is unavailable. Reconnect its volume or choose it again."
            )
        }
        guard url.pathExtension.lowercased() == "pdf" else {
            return SurgeryPlanPDFLocationStatus(
                state: .invalid,
                detail: "Choose a PDF file."
            )
        }
        guard url.lastPathComponent == resource.requiredFileName else {
            return SurgeryPlanPDFLocationStatus(
                state: .invalid,
                detail: "Choose \(resource.requiredFileName)."
            )
        }

        do {
            switch resource {
            case .protocolTemplate:
                try SurgeryProtocolPDFTemplate.validate(
                    Data(contentsOf: url)
                )
            case .mouseBrainAtlas:
                _ = try SurgeryAtlasCatalog.plates(in: url)
            }
        } catch {
            return SurgeryPlanPDFLocationStatus(
                state: .invalid,
                detail: error.localizedDescription
            )
        }

        return SurgeryPlanPDFLocationStatus(
            state: .ready,
            detail: url.path
        )
    }
}

struct SurgeryPlanSettingsView: View {
    @AppStorage(SurgeryPlanPDFPreferences.protocolTemplatePathKey)
    private var protocolTemplatePath = ""
    @AppStorage(SurgeryPlanPDFPreferences.atlasPDFPathKey)
    private var atlasPDFPath = ""

    @State private var selectionError: String?

    var body: some View {
        Form {
            Section("Surgery plan PDFs") {
                Text(
                    "Set these once. Every surgery-plan export reuses them "
                        + "until you replace them here."
                )
                .font(.callout)
                .foregroundStyle(.secondary)

                resourceRow(
                    resource: .protocolTemplate,
                    path: protocolTemplatePath
                )
                resourceRow(
                    resource: .mouseBrainAtlas,
                    path: atlasPDFPath
                )

                if let selectionError {
                    Label(
                        selectionError,
                        systemImage: "exclamationmark.triangle.fill"
                    )
                    .font(.caption)
                    .foregroundStyle(.orange)
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 620, height: 390)
    }

    @ViewBuilder
    private func resourceRow(
        resource: SurgeryPlanPDFResource,
        path: String
    ) -> some View {
        let status = SurgeryPlanPDFPreferences.status(
            for: resource,
            path: path
        )
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(resource.title)
                        .font(.callout.weight(.medium))
                    Text(resource.requiredFileName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                statusLabel(status)
                Button(status.isReady ? "Replace…" : "Choose PDF…") {
                    choosePDF(for: resource, currentPath: path)
                }
                .controlSize(.small)
            }

            Text(path.isEmpty ? "Not set" : path)
                .font(.caption2.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .textSelection(.enabled)

            if !status.isReady {
                Text(status.detail)
                    .font(.caption)
                    .foregroundStyle(
                        status.state == .invalid ? Color.orange : Color.secondary
                    )
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func statusLabel(
        _ status: SurgeryPlanPDFLocationStatus
    ) -> some View {
        Label(
            status.shortLabel,
            systemImage: status.isReady
                ? "checkmark.circle.fill"
                : "exclamationmark.circle.fill"
        )
        .font(.caption.weight(.semibold))
        .foregroundStyle(status.isReady ? Color.green : Color.orange)
    }

    private func choosePDF(
        for resource: SurgeryPlanPDFResource,
        currentPath: String
    ) {
        let panel = NSOpenPanel()
        panel.title = "Choose \(resource.title)"
        panel.prompt = "Use PDF"
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.pdf]
        if !currentPath.isEmpty {
            panel.directoryURL = URL(fileURLWithPath: currentPath)
                .deletingLastPathComponent()
        }
        guard panel.runModal() == .OK, let url = panel.url else { return }

        let status = SurgeryPlanPDFPreferences.status(
            for: resource,
            path: url.path
        )
        guard status.isReady else {
            selectionError = status.detail
            return
        }

        switch resource {
        case .protocolTemplate:
            protocolTemplatePath = url.standardizedFileURL.path
        case .mouseBrainAtlas:
            atlasPDFPath = url.standardizedFileURL.path
        }
        selectionError = nil
    }
}
