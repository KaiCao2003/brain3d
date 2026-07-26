import AppKit
import Brain3DCore
import CryptoKit
import Darwin
import Foundation
import PDFKit
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

struct SurgeryAtlasBundleIdentity: Equatable, Sendable {
    let byteCount: Int
    let pageCount: Int
    let sha256: String

    static let production = SurgeryAtlasBundleIdentity(
        byteCount: 12_461_500,
        pageCount: 132,
        sha256: "27b34540d9418bd6e4954f67dc99d342502216cb8d36fcc2e1ddde30671aeef8"
    )
}

enum SurgeryAtlasBundleInspection: Equatable, Sendable {
    case absent
    case invalid(String)
    case ready(URL, sha256: String)
}

enum SurgeryAtlasLocationOrigin: Equatable, Sendable {
    case bundled
    case savedPreference
    case invalidBundle
    case unavailable
}

struct SurgeryAtlasLocationResolution: Equatable, Sendable {
    let url: URL?
    let requiredSourceSHA256: String?
    let status: SurgeryPlanPDFLocationStatus
    let origin: SurgeryAtlasLocationOrigin

    var isBundled: Bool {
        origin == .bundled
    }
}

enum SurgeryAtlasBundle {
    static let relativePath = "SurgeryAtlas/MBSC_Figs_with_Layers.pdf"

    static let mainInspection = inspect(
        resourceURL: Bundle.main.resourceURL
    )

    static func inspect(
        resourceURL: URL?,
        identity: SurgeryAtlasBundleIdentity = .production
    ) -> SurgeryAtlasBundleInspection {
        guard let resourceURL, resourceURL.isFileURL else {
            return .absent
        }

        let unresolvedCandidate = resourceURL.appendingPathComponent(
            relativePath,
            isDirectory: false
        )
        var fileStatus = stat()
        let statusResult = unresolvedCandidate.path.withCString {
            lstat($0, &fileStatus)
        }
        guard statusResult == 0 else {
            return errno == ENOENT
                ? .absent
                : .invalid("The included atlas path could not be inspected.")
        }

        let resourceRoot = resourceURL
            .resolvingSymlinksInPath()
            .standardizedFileURL
        let candidate = unresolvedCandidate
            .resolvingSymlinksInPath()
            .standardizedFileURL
        let rootPath = resourceRoot.path.hasSuffix("/")
            ? resourceRoot.path
            : resourceRoot.path + "/"
        guard candidate.path.hasPrefix(rootPath) else {
            return .invalid("The included atlas resolves outside the app bundle.")
        }

        guard let values = try? candidate.resourceValues(
            forKeys: [.isRegularFileKey, .fileSizeKey]
        ), values.isRegularFile == true else {
            return .invalid("The included atlas is not a regular file.")
        }
        guard values.fileSize == identity.byteCount else {
            return .invalid("The included atlas has an unexpected file size.")
        }
        guard let data = try? Data(contentsOf: candidate, options: [.mappedIfSafe]) else {
            return .invalid("The included atlas could not be read.")
        }
        let digest = LowercaseHex.encode(SHA256.hash(data: data))
        guard digest == identity.sha256 else {
            return .invalid("The included atlas failed its SHA-256 identity check.")
        }
        guard let document = PDFDocument(data: data),
              document.pageCount == identity.pageCount
        else {
            return .invalid(
                "The included atlas is not the expected \(identity.pageCount)-page PDF."
            )
        }
        return .ready(candidate, sha256: identity.sha256)
    }

    static func validateCapturedSHA256(
        _ capturedSHA256: String,
        requiredSHA256: String?
    ) throws {
        guard let requiredSHA256 else { return }
        guard capturedSHA256 == requiredSHA256 else {
            throw SurgeryPlanExportError.invalidAtlasSource(
                "The included atlas changed after its bundle identity was verified."
            )
        }
    }
}

enum SurgeryPlanPDFPreferences {
    static let protocolTemplatePathKey = "surgeryProtocolTemplatePath"
    static let atlasPDFPathKey = "surgeryAtlasPDFPath"

    static func atlasLocation(
        savedPath: String,
        bundleInspection: SurgeryAtlasBundleInspection =
            SurgeryAtlasBundle.mainInspection
    ) -> SurgeryAtlasLocationResolution {
        switch bundleInspection {
        case let .ready(url, sha256):
            return SurgeryAtlasLocationResolution(
                url: url,
                requiredSourceSHA256: sha256,
                status: SurgeryPlanPDFLocationStatus(
                    state: .ready,
                    detail: "Included in this Brain3D app · 132 pages."
                ),
                origin: .bundled
            )
        case let .invalid(detail):
            return SurgeryAtlasLocationResolution(
                url: nil,
                requiredSourceSHA256: nil,
                status: SurgeryPlanPDFLocationStatus(
                    state: .invalid,
                    detail: detail
                ),
                origin: .invalidBundle
            )
        case .absent:
            let status = status(for: .mouseBrainAtlas, path: savedPath)
            return SurgeryAtlasLocationResolution(
                url: status.isReady
                    ? URL(fileURLWithPath: savedPath).standardizedFileURL
                    : nil,
                requiredSourceSHA256: nil,
                status: status,
                origin: status.isReady ? .savedPreference : .unavailable
            )
        }
    }

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
        let atlasLocation = SurgeryPlanPDFPreferences.atlasLocation(
            savedPath: atlasPDFPath
        )
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
                if atlasLocation.isBundled {
                    includedAtlasRow(atlasLocation)
                } else if atlasLocation.origin == .invalidBundle {
                    invalidIncludedAtlasRow(atlasLocation)
                } else {
                    resourceRow(
                        resource: .mouseBrainAtlas,
                        path: atlasPDFPath
                    )
                }

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
    private func includedAtlasRow(
        _ location: SurgeryAtlasLocationResolution
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(SurgeryPlanPDFResource.mouseBrainAtlas.title)
                        .font(.callout.weight(.medium))
                    Text("Included in Brain3D")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Label("Included", systemImage: "checkmark.circle.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.green)
            }
            Text(location.url?.path ?? SurgeryAtlasBundle.relativePath)
                .font(.caption2.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .textSelection(.enabled)
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func invalidIncludedAtlasRow(
        _ location: SurgeryAtlasLocationResolution
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text(SurgeryPlanPDFResource.mouseBrainAtlas.title)
                    .font(.callout.weight(.medium))
                Spacer()
                statusLabel(location.status)
            }
            Text(location.status.detail)
                .font(.caption)
                .foregroundStyle(.orange)
        }
        .padding(.vertical, 4)
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
