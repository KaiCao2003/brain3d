import Brain3DCore
import SwiftUI

private enum ProbeRegionInspectorMode: String, CaseIterable {
    case segments = "Segments"
    case sites = "Sites"
}

struct ProbeRegionInspectorSheet: View {
    let plan: ProbePlanDetail
    let analysis: ProbeRegionAnalysisBundle
    @Environment(\.dismiss) private var dismiss
    @State private var mode: ProbeRegionInspectorMode = .segments
    @State private var selectedShankId = ""

    private var shank: ProbeShankRegionAnalysis? {
        analysis.shanks.first(where: { $0.shankId == selectedShankId })
            ?? analysis.shanks.first
    }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(plan.name)
                        .font(.headline)
                    Text("Exact atlas traversal · planning only · not navigation")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Close") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }

            HStack {
                if analysis.shanks.count > 1 {
                    Picker("Shank", selection: $selectedShankId) {
                        ForEach(analysis.shanks) { item in
                            Text(item.shankId).tag(item.shankId)
                        }
                    }
                    .frame(maxWidth: 220)
                } else if let shank {
                    Text(shank.shankId)
                        .font(.callout.weight(.medium))
                }
                Spacer()
                Picker("Rows", selection: $mode) {
                    ForEach(ProbeRegionInspectorMode.allCases, id: \.self) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 190)
            }

            Divider()

            if let shank {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        switch mode {
                        case .segments:
                            ForEach(shank.segments) { segment in
                                segmentRow(segment)
                                Divider()
                            }
                        case .sites:
                            ForEach(shank.recordingSiteAssignments) { site in
                                siteRow(site)
                                Divider()
                            }
                        }
                    }
                }
                .overlay {
                    if mode == .segments, shank.segments.isEmpty {
                        ContentUnavailableView("No atlas segments", systemImage: "square.dashed")
                    } else if mode == .sites, shank.recordingSiteAssignments.isEmpty {
                        ContentUnavailableView("No site assignments", systemImage: "circle.dashed")
                    }
                }
            }
        }
        .padding(16)
        .frame(minWidth: 560, minHeight: 440)
        .onAppear {
            if selectedShankId.isEmpty {
                selectedShankId = analysis.shanks.first?.shankId ?? ""
            }
        }
    }

    private func segmentRow(_ segment: ProbeRegionSegment) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Circle()
                .fill(segmentColor(segment))
                .frame(width: 10, height: 10)
                .padding(.top, 4)
            VStack(alignment: .leading, spacing: 3) {
                Text("\(segment.acronym) · \(segment.name)")
                    .font(.callout.weight(.medium))
                Text("\(segment.hemisphere) · \(segment.location)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 12)
            VStack(alignment: .trailing, spacing: 3) {
                Text(
                    "\(micrometres(segment.entryDepthMicrometres))–"
                        + "\(micrometres(segment.exitDepthMicrometres))"
                )
                .font(.caption.monospacedDigit())
                Text("length \(micrometres(segment.lengthMicrometres))")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 8)
    }

    private func siteRow(_ site: ProbeRegionSiteAssignment) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: site.insideBrain ? "circle.inset.filled" : "circle")
                .foregroundStyle(site.insideBrain ? .cyan : .secondary)
                .frame(width: 12)
            VStack(alignment: .leading, spacing: 3) {
                Text("\(site.siteId) · \(site.acronym)")
                    .font(.callout.weight(.medium))
                Text(site.name)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 12)
            VStack(alignment: .trailing, spacing: 3) {
                Text(site.insideBrain ? "inside brain" : (site.insideAtlas ? "outside brain" : "outside atlas"))
                    .font(.caption)
                if let voxel = site.voxelIndex {
                    Text("voxel \(voxel.ap), \(voxel.dv), \(voxel.ml)")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 8)
    }

    private func segmentColor(_ segment: ProbeRegionSegment) -> Color {
        guard segment.rgb.count == 3 else { return .secondary }
        return Color(
            red: Double(segment.rgb[0]) / 255,
            green: Double(segment.rgb[1]) / 255,
            blue: Double(segment.rgb[2]) / 255
        )
    }

    private func micrometres(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(1))) + " µm"
    }
}
