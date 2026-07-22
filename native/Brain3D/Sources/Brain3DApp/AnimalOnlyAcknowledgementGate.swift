import Brain3DCore
import SwiftUI

struct AnimalOnlyAcknowledgementGate: View {
    @ObservedObject var model: PlannerViewModel
    let openExistingProject: () -> Void

    @State private var acknowledgement = AnimalOnlyAcknowledgementState()
    @State private var subjectId = ""

    var body: some View {
        ZStack {
            Color.black.opacity(0.32)
                .ignoresSafeArea()

            VStack(alignment: .leading, spacing: 18) {
                Label("Confirm animal-only use", systemImage: "shield.lefthalf.filled")
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(.orange)

                Text(SafetyPolicy.animalResearchOnly)
                    .font(.headline)

                Text(
                    "Before creating or opening a plan, confirm that every use in this "
                        + "session is limited to animal research. Brain3D must never be used "
                        + "for a human or for clinical care."
                )
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

                Toggle(isOn: explicitAcknowledgement) {
                    Text(
                        "I explicitly acknowledge that this application is for animal "
                            + "research only — not for human or clinical use."
                    )
                    .fixedSize(horizontal: false, vertical: true)
                }
                .toggleStyle(.checkbox)
                .disabled(model.projectOperationInProgress)
                .accessibilityHint(
                    "Required before a new animal plan can be created or an existing one opened."
                )

                VStack(alignment: .leading, spacing: 5) {
                    Text("Animal subject ID")
                        .font(.caption.weight(.semibold))
                    TextField("Required, for example mouse-001", text: $subjectId)
                        .textFieldStyle(.roundedBorder)
                        .disabled(model.projectOperationInProgress)
                    Text("Stored with calibrations, targets, probe plans, and analyses.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Text(
                    "Acknowledgement does not establish surgical accuracy, vessel clearance, "
                        + "or authorization for navigation."
                )
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    Button("Acknowledge and Create Animal Plan") {
                        Task {
                            _ = await model.createNewAnimalProject(
                                acknowledgement: acknowledgement,
                                subjectId: subjectId
                            )
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(
                        !acknowledgement.isExplicitlyAcknowledged
                            || subjectId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            || model.projectOperationInProgress
                    )

                    Button("Open Existing Animal Plan…") {
                        openExistingProject()
                    }
                    .buttonStyle(.bordered)
                    .disabled(
                        !acknowledgement.isExplicitlyAcknowledged
                            || model.projectOperationInProgress
                    )
                }

                if model.projectOperationInProgress {
                    ProgressView("Validating animal-only project…")
                        .controlSize(.small)
                }

                if let error = model.projectOperationError {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(28)
            .frame(width: 560)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(Color.secondary.opacity(0.24))
            }
            .shadow(color: .black.opacity(0.24), radius: 24, y: 10)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Animal-only use acknowledgement")
    }

    private var explicitAcknowledgement: Binding<Bool> {
        Binding(
            get: { acknowledgement.isExplicitlyAcknowledged },
            set: { acknowledgement.setExplicitlyAcknowledged($0) }
        )
    }
}
