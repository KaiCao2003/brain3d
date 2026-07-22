import AppKit
import Brain3DCore
import SwiftUI

struct WorkspaceView: View {
    @ObservedObject var model: PlannerViewModel

    var body: some View {
        VStack(spacing: 0) {
            SafetyNotice(compact: false)
                .padding(.horizontal, 18)
                .padding(.vertical, 10)

            Divider()

            WorkspaceModeBar(selection: $model.workspaceMode)
                .padding(.horizontal, 18)
                .padding(.vertical, 12)

            PlanningCanvas(
                mode: model.workspaceMode,
                atlasStatus: model.atlasOperationalStatus,
                sliceStatus: model.sliceStatus,
                atlasPNG: model.atlasSlicePNG,
                subjectPreviewPNG: model.subjectPreviewPNG,
                populationDensityPNG: model.populationDensityPNG,
                populationDensityOverlay: model.populationDensityOverlay,
                populationDensityDisclosure: model.populationDensityDisclosure,
                subjectOverlayPNG: model.subjectOverlayPNG,
                subjectVesselsRegistered: model.backendState?.subjectVessels.primaryImage?.registered == true,
                populationDensityVisible: model.populationDensityVisible
            )
            .padding([.horizontal, .bottom], 18)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .navigationTitle(model.workspaceMode.rawValue)
    }
}

struct SafetyNotice: View {
    let compact: Bool

    var body: some View {
        Label(SafetyPolicy.animalResearchOnly, systemImage: "shield.lefthalf.filled")
            .font(compact ? .caption.weight(.semibold) : .callout.weight(.semibold))
            .foregroundStyle(.orange)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityLabel("Safety restriction")
            .accessibilityValue(SafetyPolicy.animalResearchOnly)
    }
}

private struct WorkspaceModeBar: View {
    @Binding var selection: WorkspaceMode

    var body: some View {
        HStack(spacing: 8) {
            ForEach(WorkspaceMode.allCases, id: \.self) { mode in
                Button {
                    selection = mode
                } label: {
                    Text(mode.rawValue)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(WorkspaceModeButtonStyle(isCurrent: selection == mode))
                .accessibilityLabel(mode.accessibilityDescription)
                .accessibilityValue(
                    selection == mode
                        ? "Current view"
                        : (mode == .threeDimensional ? "Unavailable view" : "Available view")
                )
                .help(
                    mode == .threeDimensional
                        ? "3D rendering is unavailable in this testing build."
                        : "Show the verified \(mode.rawValue.lowercased()) atlas view."
                )
            }
        }
    }
}

private struct WorkspaceModeButtonStyle: ButtonStyle {
    let isCurrent: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.callout.weight(isCurrent ? .semibold : .regular))
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .foregroundStyle(isCurrent ? Color.white : Color.primary)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(isCurrent ? Color.accentColor : Color.secondary.opacity(configuration.isPressed ? 0.18 : 0.10))
            )
            .overlay {
                if !isCurrent {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .strokeBorder(Color.secondary.opacity(0.18))
                }
            }
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.08), value: configuration.isPressed)
    }
}

private struct PlanningCanvas: View {
    let mode: WorkspaceMode
    let atlasStatus: String
    let sliceStatus: String
    let atlasPNG: Data?
    let subjectPreviewPNG: Data?
    let populationDensityPNG: Data?
    let populationDensityOverlay: ReferenceDensityOverlayResult?
    let populationDensityDisclosure: String
    let subjectOverlayPNG: Data?
    let subjectVesselsRegistered: Bool
    let populationDensityVisible: Bool

    private var atlasImage: NSImage? {
        atlasPNG.flatMap(NSImage.init(data:))
    }

    private var subjectImage: NSImage? {
        subjectPreviewPNG.flatMap(NSImage.init(data:))
    }

    private var subjectOverlayImage: NSImage? {
        subjectOverlayPNG.flatMap(NSImage.init(data:))
    }

    private var populationDensityImage: NSImage? {
        populationDensityPNG.flatMap(NSImage.init(data:))
    }

    var body: some View {
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                AtlasImagePanel(
                    mode: mode,
                    image: atlasImage,
                    populationDensityOverlay: mode == .dorsal && populationDensityVisible
                        ? populationDensityImage
                        : nil,
                    populationDensityResult: populationDensityOverlay,
                    populationDensityDisclosure: populationDensityDisclosure,
                    subjectOverlay: mode == .dorsal ? subjectOverlayImage : nil,
                    status: sliceStatus
                )
                if mode == .dorsal {
                    SubjectVesselPreviewPanel(
                        image: subjectImage,
                        registered: subjectVesselsRegistered
                    )
                    .frame(minWidth: 260, idealWidth: 340, maxWidth: 420)
                }
            }

            HStack(spacing: 8) {
                StatusPill(text: atlasStatus, good: atlasStatus == "Loaded and verified")
                if mode == .dorsal {
                    StatusPill(
                        text: subjectVesselsRegistered
                            ? "Subject image registered"
                            : "Subject image not registered",
                        good: subjectVesselsRegistered
                    )
                    if populationDensityVisible, populationDensityImage != nil {
                        StatusPill(
                            text: "Published population density visible — not subject-specific",
                            good: false
                        )
                    }
                }
            }
        }
        .padding(12)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Color.secondary.opacity(0.24))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct AtlasImagePanel: View {
    let mode: WorkspaceMode
    let image: NSImage?
    let populationDensityOverlay: NSImage?
    let populationDensityResult: ReferenceDensityOverlayResult?
    let populationDensityDisclosure: String
    let subjectOverlay: NSImage?
    let status: String

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Label(
                    mode == .dorsal ? "Verified Allen dorsal surface" : "Verified atlas slice",
                    systemImage: "brain.head.profile"
                )
                .font(.headline)
                Spacer()
                Text(mode.rawValue)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            if let image {
                ZStack(alignment: .bottomLeading) {
                    Image(nsImage: image)
                        .resizable()
                        .interpolation(.none)
                        .aspectRatio(contentMode: .fit)
                    if let populationDensityOverlay {
                        Image(nsImage: populationDensityOverlay)
                            .resizable()
                            .interpolation(.high)
                            .aspectRatio(contentMode: .fit)
                            .accessibilityLabel(
                                "Published population reference vascular length density; not subject-specific vessels"
                            )
                    }
                    if let subjectOverlay {
                        Image(nsImage: subjectOverlay)
                            .resizable()
                            .interpolation(.high)
                            .aspectRatio(contentMode: .fit)
                            .accessibilityLabel("Registered user-supplied dorsal image overlay")
                    }
                    if populationDensityOverlay != nil, let result = populationDensityResult {
                        PopulationDensityLegend(
                            result: result,
                            disclosure: populationDensityDisclosure
                        )
                        .padding(10)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.black.opacity(0.88))
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            } else {
                ContentUnavailableView(
                    mode == .threeDimensional ? "3D renderer unavailable" : "No verified slice",
                    systemImage: mode == .threeDimensional ? "cube.transparent" : "brain.head.profile",
                    description: Text(status)
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            Text(status)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10)
        .background(.background.opacity(0.65), in: RoundedRectangle(cornerRadius: 10))
    }
}

private struct PopulationDensityLegend: View {
    let result: ReferenceDensityOverlayResult
    let disclosure: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("Published population vascular length density")
                .font(.caption.weight(.semibold))
            LinearGradient(
                colors: [.black.opacity(0.15), .red, Color(red: 1, green: 0, blue: 1)],
                startPoint: .leading,
                endPoint: .trailing
            )
            .frame(width: 190, height: 8)
            .clipShape(Capsule())
            Text(
                "\(result.window.low.formatted())–\(result.window.high.formatted()) "
                    + "\(result.window.units) · DV maximum projection"
            )
            .font(.caption2.monospacedDigit())
            Text(disclosure)
                .font(.caption2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(.white)
        .padding(9)
        .frame(maxWidth: 360, alignment: .leading)
        .background(.black.opacity(0.78), in: RoundedRectangle(cornerRadius: 8))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Population reference density legend")
        .accessibilityValue(disclosure)
    }
}

private struct SubjectVesselPreviewPanel: View {
    let image: NSImage?
    let registered: Bool

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Label("Subject dorsal image", systemImage: "photo")
                    .font(.headline)
                Spacer()
            }
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color.black.opacity(0.88))
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            } else {
                ContentUnavailableView(
                    "No subject dorsal image",
                    systemImage: "photo.badge.plus",
                    description: Text("Use Import image in the persistent project sidebar.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            Text(
                registered
                    ? "Registered user-supplied image — vessel segmentation is not validated"
                    : "Preview only — not registered; do not infer vessel clearance"
            )
            .font(.caption.weight(.medium))
            .foregroundStyle(registered ? .green : .orange)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10)
        .background(.background.opacity(0.65), in: RoundedRectangle(cornerRadius: 10))
    }
}

private struct StatusPill: View {
    let text: String
    let good: Bool

    var body: some View {
        Label(text, systemImage: good ? "checkmark.circle.fill" : "exclamationmark.circle")
            .font(.caption.weight(.medium))
            .foregroundStyle(good ? .green : .secondary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(.quaternary, in: Capsule())
    }
}
