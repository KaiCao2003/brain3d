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

            Picker("View", selection: $model.workspaceMode) {
                ForEach(WorkspaceMode.allCases, id: \.self) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 18)
            .padding(.vertical, 12)

            selectedWorkspace
                .padding([.horizontal, .bottom], 18)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .navigationTitle(model.workspaceMode.rawValue)
    }

    @ViewBuilder
    private var selectedWorkspace: some View {
        switch model.workspaceMode {
        case .dorsal:
            DorsalVesselWorkspace(model: model)
        case .coronal:
            AtlasSliceWorkspace(model: model, orientation: .coronal)
        case .sagittal:
            AtlasSliceWorkspace(model: model, orientation: .sagittal)
        case .horizontal:
            AtlasSliceWorkspace(model: model, orientation: .horizontal)
        case .threeDimensional:
            ThreeDimensionalWorkspace(model: model)
        }
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

private struct AtlasSliceWorkspace: View {
    @ObservedObject var model: PlannerViewModel
    let orientation: AtlasSliceOrientation
    @State private var resetGeneration = 0

    private var frame: VerifiedAtlasSliceFrame? {
        model.viewerFrame(for: orientation)
    }

    private var requestedIndex: Int {
        model.requestedViewerIndex(for: orientation) ?? frame?.index ?? 0
    }

    var body: some View {
        VStack(spacing: 10) {
            header

            ZStack {
                AtlasSliceCanvas(
                    imageData: frame?.png,
                    imagePixelWidth: frame?.width ?? 0,
                    imagePixelHeight: frame?.height ?? 0,
                    viewportIdentity: orientation.rawValue,
                    selection: canvasSelection,
                    accessibilityLabel: "\(orientation.displayName) atlas slice",
                    accessibilityValue: accessibilityValue,
                    resetGeneration: resetGeneration,
                    onPick: { column, row in
                        model.pickViewerRegion(
                            orientation: orientation,
                            column: column,
                            row: row
                        )
                    },
                    onSliceStep: { delta in
                        model.stepViewerSlice(orientation, delta: delta)
                    }
                )
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))

                if frame == nil {
                    ContentUnavailableView(
                        "No verified \(orientation.displayName.lowercased()) slice",
                        systemImage: "brain.head.profile",
                        description: Text(model.viewerPhase.message)
                    )
                    .allowsHitTesting(false)
                } else if isPending {
                    ProgressView()
                        .controlSize(.small)
                        .padding(7)
                        .background(.black.opacity(0.7), in: Circle())
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
                        .padding(8)
                        .allowsHitTesting(false)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.black, in: RoundedRectangle(cornerRadius: 9))

            sliceControl
            if case let .failed(message) = model.viewerPhase {
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .lineLimit(3)
                    .accessibilityLabel("Atlas view error")
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

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Label("\(orientation.displayName) atlas slice", systemImage: "brain.head.profile")
                .font(.headline)
            if let frame {
                Text(
                    "\(frame.fixedAxis.rawValue) "
                        + "\((frame.sliceCenterMicrometres / 1000).formatted(.number.precision(.fractionLength(3)))) mm"
                )
                .font(.callout.monospacedDigit())
                .foregroundStyle(.secondary)
                Spacer()
            } else {
                Spacer()
            }
            Button("Reset view", systemImage: "arrow.counterclockwise") {
                resetGeneration += 1
            }
            .labelStyle(.iconOnly)
            .help("Reset pan and zoom")
        }
    }

    @ViewBuilder
    private var sliceControl: some View {
        if let frame {
            HStack(spacing: 10) {
                Button {
                    model.stepViewerSlice(orientation, delta: -1)
                } label: {
                    Image(systemName: "chevron.left")
                }
                .disabled(requestedIndex <= 0)
                .accessibilityLabel("Previous \(orientation.displayName) slice")

                Slider(
                    value: Binding(
                        get: { Double(requestedIndex) },
                        set: { model.requestViewerSlice(orientation, index: Int($0.rounded())) }
                    ),
                    in: 0 ... Double(frame.sliceCount - 1),
                    step: 1
                )
                .accessibilityLabel("\(orientation.displayName) slice index")
                .accessibilityValue("\(requestedIndex + 1) of \(frame.sliceCount)")

                Button {
                    model.stepViewerSlice(orientation, delta: 1)
                } label: {
                    Image(systemName: "chevron.right")
                }
                .disabled(requestedIndex >= frame.sliceCount - 1)
                .accessibilityLabel("Next \(orientation.displayName) slice")

                Text("\(requestedIndex + 1) / \(frame.sliceCount)")
                    .font(.callout.monospacedDigit())
                    .frame(minWidth: 84, alignment: .trailing)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        } else {
            Text(model.viewerPhase.message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var isPending: Bool {
        guard let pending = model.pendingViewerSlice else { return false }
        return pending.orientation == orientation && pending.index != frame?.index
    }

    private var accessibilityValue: String {
        guard let frame else { return model.viewerPhase.message }
        let region = canvasSelection?.acronym ?? "no selected region"
        return "Slice \(frame.index + 1) of \(frame.sliceCount), \(region)"
    }

    private var canvasSelection: AtlasSliceSelection? {
        guard
            let selection = model.viewerRegionSelection,
            selection.orientation == orientation,
            selection.index == frame?.index
        else { return nil }
        if let region = selection.region {
            return AtlasSliceSelection(
                column: selection.column,
                row: selection.row,
                acronym: region.acronym,
                name: region.name,
                color: NSColor(
                    srgbRed: CGFloat(region.rgb[0]) / 255,
                    green: CGFloat(region.rgb[1]) / 255,
                    blue: CGFloat(region.rgb[2]) / 255,
                    alpha: 1
                )
            )
        }
        return AtlasSliceSelection(
            column: selection.column,
            row: selection.row,
            acronym: "Outside",
            name: "Outside annotated brain",
            color: .secondaryLabelColor
        )
    }
}

private struct DorsalVesselWorkspace: View {
    @ObservedObject var model: PlannerViewModel

    private var atlasImage: NSImage? {
        model.dorsalSurfacePNG.flatMap(NSImage.init(data:))
    }

    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Label("Dorsal atlas surface", systemImage: "brain.head.profile")
                    .font(.headline)
                Spacer()
                Text("Major vessels only")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.orange)
            }

            if let atlasImage {
                ZStack(alignment: .bottomLeading) {
                    Image(nsImage: atlasImage)
                        .resizable()
                        .interpolation(.none)
                        .aspectRatio(contentMode: .fit)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.black)
                .clipShape(RoundedRectangle(cornerRadius: 9))
            } else {
                ContentUnavailableView(
                    "No verified dorsal surface",
                    systemImage: "brain.head.profile",
                    description: Text(model.dorsalSurfaceStatus)
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
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

private struct ThreeDimensionalWorkspace: View {
    @ObservedObject var model: PlannerViewModel

    var body: some View {
        ContentUnavailableView(
            "3D scene is not implemented yet",
            systemImage: "cube.transparent",
            description: Text(
                "This mode will render the same verified slice depths, selected region, probe, and radius-bearing vessel geometry. It will not invent geometry from the 2D dorsal image or density layer."
            )
        )
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(12)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Color.secondary.opacity(0.24))
        }
        .accessibilityValue(model.viewerPhase.message)
    }
}

private extension AtlasSliceOrientation {
    var displayName: String { rawValue.capitalized }
}
