import AppKit
import Brain3DCore
import Brain3DScene
import SwiftUI

struct WorkspaceView: View {
    @ObservedObject var model: PlannerViewModel

    var body: some View {
        VStack(spacing: 0) {
            SafetyNotice()
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

            MajorVesselDisplayControl(model: model)
                .padding(.horizontal, 18)
                .padding(.bottom, 10)

            AtlasRegionBrowserBar(model: model)
                .padding(.horizontal, 18)
                .padding(.bottom, 10)

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
            DorsalAtlasWorkspace(model: model)
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

private struct MajorVesselDisplayControl: View {
    @ObservedObject var model: PlannerViewModel
    @State private var pendingDiameterMicrometres =
        MajorVesselDisplayFilter.defaultMinimumDiameterMicrometres
    @State private var isEditing = false

    var body: some View {
        HStack(spacing: 9) {
            Label("Vessels", systemImage: "point.3.connected.trianglepath.dotted")
                .font(.caption.weight(.semibold))

            Slider(
                value: $pendingDiameterMicrometres,
                in: MajorVesselDisplayFilter.allowedMinimumDiameterRange,
                step: MajorVesselDisplayFilter.adjustmentStepMicrometres,
                onEditingChanged: commitWhenEditingEnds
            )
            .frame(width: 150)
            .accessibilityLabel("Minimum visible major-vessel diameter")
            .accessibilityValue(pendingThresholdText)
            .accessibilityHint(
                "Filters display only. The verified VesSAP source remains unchanged."
            )

            Text(pendingThresholdText)
                .font(.caption.monospacedDigit().weight(.semibold))
                .frame(width: 58, alignment: .trailing)

            Text(model.majorVesselVisibleCountText)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)

            Spacer(minLength: 0)
        }
        .help(
            "Display filter only. VesSAP source data retain their verified "
                + "30 µm minimum diameter and provenance."
        )
        .onAppear {
            pendingDiameterMicrometres =
                model.minimumVisibleVesselDiameterMicrometres
        }
        .onChange(of: model.minimumVisibleVesselDiameterMicrometres) {
            _, newValue in
            if !isEditing {
                pendingDiameterMicrometres = newValue
            }
        }
    }

    private var pendingThresholdText: String {
        "≥\(Int(pendingDiameterMicrometres.rounded())) µm"
    }

    private func commitWhenEditingEnds(_ editing: Bool) {
        isEditing = editing
        guard !editing else { return }
        model.setMinimumVisibleVesselDiameterMicrometres(
            pendingDiameterMicrometres
        )
    }
}

struct SafetyNotice: View {
    var body: some View {
        Label(SafetyPolicy.planningOnlyNotice, systemImage: "shield.lefthalf.filled")
            .font(.callout.weight(.semibold))
            .foregroundStyle(.orange)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityLabel("Safety restriction")
            .accessibilityValue(SafetyPolicy.planningOnlyNotice)
    }
}

private struct AtlasRegionBrowserBar: View {
    @ObservedObject var model: PlannerViewModel
    @State private var isBrowserPresented = false

    var body: some View {
        HStack(spacing: 9) {
            Button {
                isBrowserPresented.toggle()
            } label: {
                HStack(spacing: 7) {
                    Image(systemName: "list.bullet.indent")
                    Text("Allen regions")
                    if let hierarchy = model.atlasRegionHierarchy {
                        Text(hierarchy.regions.count.formatted())
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    } else if model.atlasRegionHierarchyError == nil {
                        ProgressView()
                            .controlSize(.mini)
                    }
                    Image(systemName: "chevron.down")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .popover(isPresented: $isBrowserPresented, arrowEdge: .bottom) {
                browser
            }
            .accessibilityLabel("Browse complete Allen atlas ontology")

            if let region = model.highlightedAtlasRegion {
                selectedRegionChip(region)
            } else if let error = model.atlasRegionHierarchyError {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .lineLimit(1)
            }

            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var browser: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Allen atlas ontology")
                    .font(.headline)
                Spacer()
                if let count = model.atlasRegionHierarchy?.regions.count {
                    Text("\(count.formatted()) structures")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 7) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField(
                    "Search acronym, name, or structure ID",
                    text: $model.atlasRegionSearchText
                )
                .textFieldStyle(.plain)
                if model.atlasRegionSearchInProgress {
                    ProgressView()
                        .controlSize(.small)
                } else if !model.atlasRegionSearchText.isEmpty {
                    Button {
                        model.atlasRegionSearchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                    .accessibilityLabel("Clear Allen region search")
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
            .task(id: model.atlasRegionSearchText) {
                await model.searchAtlasRegions(query: model.atlasRegionSearchText)
            }

            Divider()

            browserContents
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(14)
        .frame(width: 420, height: 520)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Complete Allen atlas region browser")
    }

    @ViewBuilder
    private var browserContents: some View {
        if let hierarchy = model.atlasRegionHierarchy {
            if model.atlasRegionSearchText
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .isEmpty
            {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        OutlineGroup(
                            hierarchy.roots,
                            children: \.outlineChildren
                        ) { node in
                            regionButton(node.region)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } else if model.atlasRegionSearchInProgress {
                ProgressView("Searching complete ontology…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !model.atlasRegionSearchResults.isEmpty {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(model.atlasRegionSearchResults) { result in
                            regionButton(result.region)
                        }
                    }
                }
            } else if let error = model.atlasRegionSearchError {
                ContentUnavailableView(
                    "Region search unavailable",
                    systemImage: "exclamationmark.triangle",
                    description: Text(error)
                )
            } else {
                ContentUnavailableView.search(
                    text: model.atlasRegionSearchText
                )
            }
        } else if let error = model.atlasRegionHierarchyError {
            ContentUnavailableView(
                "Atlas ontology unavailable",
                systemImage: "exclamationmark.triangle",
                description: Text(error)
            )
        } else {
            ProgressView("Loading complete atlas ontology…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func regionButton(_ region: AtlasRegionSummary) -> some View {
        Button {
            isBrowserPresented = false
            Task {
                await model.selectAtlasRegion(region)
            }
        } label: {
            HStack(spacing: 8) {
                Circle()
                    .fill(atlasRegionColor(region.rgb))
                    .frame(width: 9, height: 9)
                Text(region.acronym)
                    .font(.caption.weight(.semibold))
                    .frame(minWidth: 72, alignment: .leading)
                Text(region.name)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Spacer(minLength: 8)
            }
            .contentShape(Rectangle())
            .padding(.horizontal, 7)
            .padding(.vertical, 5)
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityLabel("\(region.acronym), \(region.name)")
    }

    private func selectedRegionChip(_ region: AtlasRegionSummary) -> some View {
        HStack(spacing: 8) {
            Circle()
                .fill(atlasRegionColor(region.rgb))
                .frame(width: 9, height: 9)
            Text(region.acronym)
                .font(.caption.weight(.semibold))
            Text(region.name)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Button {
                model.clearAtlasRegionSelection()
            } label: {
                Image(systemName: "xmark.circle.fill")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .accessibilityLabel("Clear selected Allen region")
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(.quaternary, in: Capsule())
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Selected Allen atlas region")
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
                    anatomicalLabels: .slice(orientation),
                    selection: canvasSelection,
                    majorVesselOverlay: model.majorVesselSliceOverlay(for: orientation),
                    majorVesselConflictOverlay: model.majorVesselConflictOverlay(
                        for: orientation
                    ),
                    probeOverlay: model.probeSliceOverlay(for: orientation),
                    interactionHelp: "Click to identify a brain region. Drag to pan, pinch to zoom, and scroll to change slices.",
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
        guard let selection = currentSelection else { return nil }
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

    private var currentSelection: ViewerRegionSelection? {
        guard let selection = model.viewerRegionSelection,
              selection.orientation == orientation,
              selection.index == frame?.index
        else { return nil }
        return selection
    }

}

private struct DorsalAtlasWorkspace: View {
    @ObservedObject var model: PlannerViewModel
    @State private var resetGeneration = 0

    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Label("Dorsal atlas surface", systemImage: "brain.head.profile")
                    .font(.headline)
                Spacer()
                Button("Reset view", systemImage: "arrow.counterclockwise") {
                    resetGeneration &+= 1
                }
                .labelStyle(.iconOnly)
                .help("Reset pan and zoom")
            }

            if let dorsal = model.dorsalSurface, model.dorsalSurfacePNG != nil {
                ZStack {
                    AtlasSliceCanvas(
                        imageData: model.dorsalSurfacePNG,
                        imagePixelWidth: dorsal.width,
                        imagePixelHeight: dorsal.height,
                        viewportIdentity: "dorsal-atlas-surface",
                        anatomicalLabels: .dorsal,
                        selection: canvasSelection,
                        majorVesselOverlay: model.majorVesselDorsalOverlay,
                        majorVesselConflictOverlay: model.majorVesselDorsalConflictOverlay,
                        probeOverlay: model.probeDorsalOverlay,
                        interactionHelp: "Click to identify the dorsal-most annotated region. Drag to pan and pinch to zoom.",
                        accessibilityLabel: "Dorsal atlas surface",
                        accessibilityValue: accessibilityValue,
                        resetGeneration: resetGeneration,
                        onPick: { column, row in
                            model.pickDorsalRegion(column: column, row: row)
                        },
                        onSliceStep: { _ in }
                    )

                    if model.dorsalPickInProgress {
                        ProgressView()
                            .controlSize(.small)
                            .padding(7)
                            .background(.black.opacity(0.7), in: Circle())
                            .foregroundStyle(.white)
                            .frame(
                                maxWidth: .infinity,
                                maxHeight: .infinity,
                                alignment: .topTrailing
                            )
                            .padding(8)
                            .allowsHitTesting(false)
                    }
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

            if let error = model.dorsalPickError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .lineLimit(2)
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

    private var accessibilityValue: String {
        let region = model.dorsalRegionPick?.region?.acronym ?? "no selected region"
        let vesselStatus = model.majorVesselLoadError.map { "Unavailable: \($0)" }
            ?? model.majorVesselStatus
        return "\(vesselStatus), \(region)"
    }

    private var canvasSelection: AtlasSliceSelection? {
        guard let pick = model.dorsalRegionPick else { return nil }
        if let region = pick.region {
            return AtlasSliceSelection(
                column: pick.column,
                row: pick.row,
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
            column: pick.column,
            row: pick.row,
            acronym: "Outside",
            name: "Outside annotated brain",
            color: .secondaryLabelColor
        )
    }
}

private struct ThreeDimensionalWorkspace: View {
    @ObservedObject var model: PlannerViewModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var resetGeneration = 0

    var body: some View {
        ZStack {
            Color(nsColor: .controlBackgroundColor)

            if let snapshot = model.threeDimensionalSnapshot {
                AnimalAtlasSceneView(
                    snapshot: snapshot,
                    reduceMotion: reduceMotion,
                    resetGeneration: resetGeneration,
                    phaseChanged: model.updateThreeDimensionalRenderPhase,
                    rayPicked: { start, end in
                        model.pickThreeDimensionalRegion(start: start, end: end)
                    },
                    blankSelected: model.clearThreeDimensionalRegionSelection
                )
            } else {
                unavailableContent
            }

            if case .loadingDescriptor = model.threeDimensionalPhase {
                loadingHUD
            } else if case .loadingGeometry = model.threeDimensionalPhase {
                loadingHUD
            } else if case let .failed(message) = model.threeDimensionalPhase,
                      model.threeDimensionalSnapshot != nil
            {
                ContentUnavailableView(
                    "3D mouse atlas unavailable",
                    systemImage: "exclamationmark.triangle",
                    description: Text(message)
                )
                .padding(28)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
            }

            if model.threeDimensionalSnapshot != nil {
                controlsOverlay
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Color.secondary.opacity(0.24))
        }
        .task(id: model.threeDimensionalPreparationIdentity) {
            await model.prepareThreeDimensionalScene()
        }
        .accessibilityValue(model.threeDimensionalPhase.message)
    }

    @ViewBuilder
    private var unavailableContent: some View {
        ContentUnavailableView(
            "3D mouse atlas unavailable",
            systemImage: "cube.transparent",
            description: Text(model.threeDimensionalPhase.message)
        )
    }

    private var loadingHUD: some View {
        ProgressView(model.threeDimensionalPhase.message)
            .padding(.horizontal, 18)
            .padding(.vertical, 14)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
            .allowsHitTesting(false)
    }

    private var controlsOverlay: some View {
        VStack(spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                if model.threeDimensionalPickInProgress {
                    ProgressView("Resolving atlas region…")
                        .controlSize(.small)
                        .font(.caption)
                        .padding(.horizontal, 11)
                        .padding(.vertical, 8)
                        .background(.ultraThinMaterial, in: Capsule())
                } else if let error = model.threeDimensionalPickError {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                        .lineLimit(2)
                        .padding(.horizontal, 11)
                        .padding(.vertical, 8)
                        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
                }
                Spacer(minLength: 24)
                Button {
                    resetGeneration &+= 1
                } label: {
                    Label("Reset Camera", systemImage: "arrow.counterclockwise")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .background(.ultraThinMaterial, in: Capsule())
                .disabled(model.threeDimensionalPhase != .ready)
                .accessibilityHint("Returns to the initial whole-brain view")
            }
            Spacer()
            if model.majorVesselGeometry != nil {
                Label(
                    "Vessels \(model.majorVesselDisplayThresholdText) · "
                        + model.majorVesselVisibleCountText,
                    systemImage: "point.3.connected.trianglepath.dotted"
                )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 11)
                    .padding(.vertical, 7)
                    .background(.ultraThinMaterial, in: Capsule())
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityLabel("Reference major-vessel layer")
                    .accessibilityValue(model.majorVesselStatus)
            }
        }
        .padding(14)
    }
}

private func atlasRegionColor(_ rgb: [Int]) -> Color {
    guard rgb.count == 3 else { return .secondary }
    return Color(
        red: Double(rgb[0]) / 255,
        green: Double(rgb[1]) / 255,
        blue: Double(rgb[2]) / 255
    )
}

private extension AtlasSliceOrientation {
    var displayName: String { rawValue.capitalized }
}
