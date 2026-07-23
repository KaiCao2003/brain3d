import AppKit
import Brain3DCore
import SwiftUI

private enum RegistrationMethod: String, CaseIterable {
    case similarity
    case affine

    var title: String { rawValue.capitalized }
    var minimumLandmarks: Int { self == .similarity ? 2 : 3 }
}

private enum LandmarkKind: String, CaseIterable {
    case bregma
    case lambda
    case midline
    case vesselBifurcation = "vessel-bifurcation"
    case craniotomy
    case custom

    var title: String {
        switch self {
        case .bregma: "Bregma"
        case .lambda: "Lambda"
        case .midline: "Midline"
        case .vesselBifurcation: "Vessel bifurcation"
        case .craniotomy: "Craniotomy"
        case .custom: "Custom"
        }
    }
}

private struct LandmarkDraft: Identifiable {
    let id = UUID()
    var label: String
    var kind: LandmarkKind
    var imageColumnPixels = ""
    var imageRowPixels = ""
    var atlasApMillimetres = ""
    var atlasMlMillimetres = ""
    var enabled = true

    static func initial(_ kind: LandmarkKind) -> LandmarkDraft {
        LandmarkDraft(label: kind.title, kind: kind)
    }
}

struct VascularRegistrationSheet: View {
    @ObservedObject var model: PlannerViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var method: RegistrationMethod = .similarity
    @State private var landmarks = [
        LandmarkDraft.initial(.bregma),
        LandmarkDraft.initial(.lambda),
    ]
    @State private var lateralityConfirmed = false

    private var previewImage: NSImage? {
        model.subjectPreviewPNG.flatMap(NSImage.init(data:))
    }

    private var atlasDorsalImage: NSImage? {
        model.dorsalSurfacePNG.flatMap(NSImage.init(data:))
    }

    private var enabledCount: Int {
        landmarks.filter(\.enabled).count
    }

    private var parsedLandmarks: [VascularLandmarkParameters]? {
        let imageWidth = Double(model.subjectImageWidth)
        let imageHeight = Double(model.subjectImageHeight)
        let shape = model.atlasProvenance?.shapeVoxels ?? []
        guard imageWidth > 0, imageHeight > 0, shape.count == 3 else { return nil }
        let atlasApMaximumMillimetres = Double(shape[0]) * 25 / 1_000
        let atlasMlMaximumMillimetres = Double(shape[2]) * 25 / 1_000

        var parsed: [VascularLandmarkParameters] = []
        for draft in landmarks {
            guard draft.enabled else { continue }
            guard
                !draft.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                draft.label.count <= 200,
                let column = Double(draft.imageColumnPixels), column.isFinite,
                let row = Double(draft.imageRowPixels), row.isFinite,
                let atlasAPMillimetres = Double(draft.atlasApMillimetres),
                atlasAPMillimetres.isFinite,
                let atlasMLMillimetres = Double(draft.atlasMlMillimetres),
                atlasMLMillimetres.isFinite,
                column >= 0, column < imageWidth,
                row >= 0, row < imageHeight,
                atlasAPMillimetres >= 0,
                atlasAPMillimetres < atlasApMaximumMillimetres,
                atlasMLMillimetres >= 0,
                atlasMLMillimetres < atlasMlMaximumMillimetres
            else {
                return nil
            }
            parsed.append(
                VascularLandmarkParameters(
                    label: draft.label.trimmingCharacters(in: .whitespacesAndNewlines),
                    kind: draft.kind.rawValue,
                    imageColumnPixels: column,
                    imageRowPixels: row,
                    atlasApMicrometres: ProbeInputUnits.micrometres(
                        fromMillimetres: atlasAPMillimetres
                    ),
                    atlasMlMicrometres: ProbeInputUnits.micrometres(
                        fromMillimetres: atlasMLMillimetres
                    ),
                    enabled: true
                )
            )
        }
        return parsed
    }

    private var validationMessage: String? {
        guard enabledCount >= method.minimumLandmarks else {
            return "\(method.title) registration needs at least \(method.minimumLandmarks) enabled landmarks."
        }
        guard let parsedLandmarks else {
            return "Enter finite coordinates inside the subject image and atlas AP/ML bounds."
        }
        guard haveDistinctPoints(parsedLandmarks) else {
            return "Enabled image and atlas points must be distinct; affine points must also be non-collinear."
        }
        guard lateralityConfirmed else {
            return "Explicitly confirm image left/right laterality before registration."
        }
        return nil
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Register subject dorsal image")
                        .font(.title2.weight(.semibold))
                    Text("Map image pixel column/row to the Allen atlas AP/ML dorsal plane.")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding(20)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    preview
                    methodControls
                    coordinateWarning
                    landmarksEditor
                    lateralityControl
                }
                .padding(20)
            }

            Divider()

            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    if let validationMessage {
                        Label(validationMessage, systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(.orange)
                    } else if enabledCount == method.minimumLandmarks {
                        Label(
                            "Minimum-point fit: no redundant landmark quality control; 3+ points are preferred.",
                            systemImage: "info.circle"
                        )
                        .foregroundStyle(.orange)
                    } else {
                        Label("Ready for redundant-control-point fit.", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    }
                    if let error = model.registrationError {
                        Text(error).foregroundStyle(.red)
                    }
                }
                .font(.caption)
                Spacer()
                if model.registrationInProgress {
                    ProgressView().controlSize(.small)
                }
                Button("Register and show overlay") {
                    submit()
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(validationMessage != nil || model.registrationInProgress)
            }
            .padding(20)
        }
        .frame(minWidth: 900, idealWidth: 1_000, minHeight: 720, idealHeight: 800)
        .interactiveDismissDisabled(model.registrationInProgress)
    }

    private var preview: some View {
        HStack(alignment: .top, spacing: 12) {
            RegistrationPreviewCard(title: "Verified subject image — pixel column/row") {
                if let previewImage {
                    Image(nsImage: previewImage)
                        .resizable()
                        .interpolation(.high)
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: .infinity, minHeight: 180, maxHeight: 260)
                        .background(Color.black.opacity(0.88))
                } else {
                    ContentUnavailableView("Preview unavailable", systemImage: "photo")
                        .frame(maxWidth: .infinity, minHeight: 180)
                }
            }
            RegistrationPreviewCard(title: "Allen dorsal surface — physical AP/ML") {
                if let atlasDorsalImage {
                    Image(nsImage: atlasDorsalImage)
                        .resizable()
                        .interpolation(.none)
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: .infinity, minHeight: 180, maxHeight: 260)
                        .background(Color.black.opacity(0.88))
                } else {
                    ContentUnavailableView("Dorsal atlas unavailable", systemImage: "brain.head.profile")
                        .frame(maxWidth: .infinity, minHeight: 180)
                }
            }
        }
    }

    private var methodControls: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Transform model").font(.headline)
            HStack(spacing: 8) {
                ForEach(RegistrationMethod.allCases, id: \.self) { option in
                    Button(option.title) { method = option }
                        .buttonStyle(MethodButtonStyle(current: method == option))
                        .accessibilityValue(method == option ? "Current method" : "Available method")
                }
            }
            Text("Similarity is the safer default. Affine requires at least three non-collinear points and can distort scale/shear.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var coordinateWarning: some View {
        Label {
            Text(
                "Atlas AP/ML values are absolute physical millimetres in the BrainGlobe ASR atlas dorsal plane. "
                    + "They are not official bregma-relative stereotaxic coordinates. Enter the matched "
                    + "subject pixel column/row and atlas AP/ML physical values in each row below."
            )
        } icon: {
            Image(systemName: "ruler")
        }
        .font(.callout.weight(.medium))
        .padding(12)
        .background(.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
    }

    private var landmarksEditor: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Landmark correspondences").font(.headline)
                Spacer()
                Button("Add landmark", systemImage: "plus") {
                    landmarks.append(.initial(.custom))
                }
            }
            ForEach($landmarks) { $landmark in
                LandmarkRow(
                    landmark: $landmark,
                    imageWidth: model.subjectImageWidth,
                    imageHeight: model.subjectImageHeight,
                    remove: {
                        landmarks.removeAll { $0.id == landmark.id }
                    }
                )
            }
        }
    }

    private var lateralityControl: some View {
        VStack(alignment: .leading, spacing: 6) {
            Toggle(
                "I confirm the subject image left/right laterality is correct for this atlas mapping",
                isOn: $lateralityConfirmed
            )
            .font(.headline)
            Text("No registered image overlay is displayed until this confirmation is stored by the backend. This transform does not validate vessel segmentation.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(12)
        .background(.red.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
    }

    private func haveDistinctPoints(_ points: [VascularLandmarkParameters]) -> Bool {
        guard points.count >= method.minimumLandmarks else { return false }
        let sourceUnique = Set(points.map { "\($0.imageColumnPixels),\($0.imageRowPixels)" })
        let targetUnique = Set(points.map { "\($0.atlasApMicrometres),\($0.atlasMlMicrometres)" })
        guard sourceUnique.count == points.count, targetUnique.count == points.count else {
            return false
        }
        guard method == .affine else { return true }
        return nonCollinear(points, source: true) && nonCollinear(points, source: false)
    }

    private func nonCollinear(_ points: [VascularLandmarkParameters], source: Bool) -> Bool {
        for first in 0..<(points.count - 2) {
            for second in (first + 1)..<(points.count - 1) {
                for third in (second + 1)..<points.count {
                    let a = coordinates(points[first], source: source)
                    let b = coordinates(points[second], source: source)
                    let c = coordinates(points[third], source: source)
                    let twiceArea = (b.0 - a.0) * (c.1 - a.1) - (b.1 - a.1) * (c.0 - a.0)
                    if abs(twiceArea) > 1e-9 { return true }
                }
            }
        }
        return false
    }

    private func coordinates(
        _ point: VascularLandmarkParameters,
        source: Bool
    ) -> (Double, Double) {
        source
            ? (point.imageColumnPixels, point.imageRowPixels)
            : (point.atlasApMicrometres, point.atlasMlMicrometres)
    }

    private func submit() {
        guard let parsedLandmarks, validationMessage == nil else { return }
        Task {
            if await model.registerSubjectVessels(
                method: method.rawValue,
                landmarks: parsedLandmarks,
                lateralityConfirmed: lateralityConfirmed
            ) {
                dismiss()
            }
        }
    }
}

private struct RegistrationPreviewCard<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    init(title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
            Divider()
            content
                .frame(maxWidth: .infinity)
        }
        .padding(12)
        .background(.background.opacity(0.72), in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(Color.secondary.opacity(0.20))
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }
}

private struct LandmarkRow: View {
    @Binding var landmark: LandmarkDraft
    let imageWidth: Int
    let imageHeight: Int
    let remove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Toggle("Enabled", isOn: $landmark.enabled)
                    .toggleStyle(.checkbox)
                    .frame(width: 90, alignment: .leading)
                TextField("Label", text: $landmark.label)
                    .textFieldStyle(.roundedBorder)
                Menu(landmark.kind.title) {
                    ForEach(LandmarkKind.allCases, id: \.self) { kind in
                        Button(kind.title) { landmark.kind = kind }
                    }
                }
                .frame(width: 160)
                Button("Remove", systemImage: "trash", role: .destructive, action: remove)
                    .labelStyle(.iconOnly)
            }
            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 5) {
                GridRow {
                    Text("Image column (px)")
                    Text("Image row (px)")
                    Text("Atlas AP (mm)")
                    Text("Atlas ML (mm)")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
                GridRow {
                    numericField("0…\(max(0, imageWidth - 1))", text: $landmark.imageColumnPixels)
                    numericField("0…\(max(0, imageHeight - 1))", text: $landmark.imageRowPixels)
                    numericField("Physical mm", text: $landmark.atlasApMillimetres)
                    numericField("Physical mm", text: $landmark.atlasMlMillimetres)
                }
            }
        }
        .padding(12)
        .background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 10))
    }

    private func numericField(_ prompt: String, text: Binding<String>) -> some View {
        TextField(prompt, text: text)
            .textFieldStyle(.roundedBorder)
            .frame(minWidth: 150)
    }
}

private struct MethodButtonStyle: ButtonStyle {
    let current: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.callout.weight(current ? .semibold : .regular))
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .foregroundStyle(current ? Color.white : Color.primary)
            .background(
                current ? Color.accentColor : Color.secondary.opacity(configuration.isPressed ? 0.18 : 0.10),
                in: RoundedRectangle(cornerRadius: 8)
            )
    }
}
