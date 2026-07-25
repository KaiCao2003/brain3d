import AppKit
import Brain3DCore
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @ObservedObject var model: PlannerViewModel
    @State private var isConfirmingReconnect = false
    @State private var isConfirmingOpen = false

    var body: some View {
        ZStack {
            NavigationSplitView(columnVisibility: .constant(.all)) {
                ProjectSidebar(
                    model: model,
                    draft: model.probeDraftSession,
                    saveProject: showSaveProjectPanel,
                    openProject: requestOpenProject,
                    reconnect: requestReconnect
                )
                .navigationSplitViewColumnWidth(min: 280, ideal: 320, max: 380)
            } detail: {
                WorkspaceView(model: model)
            }
            .navigationSplitViewStyle(.balanced)
            .disabled(model.requiresAnimalOnlyAcknowledgement)
            .accessibilityHidden(model.requiresAnimalOnlyAcknowledgement)

            if model.requiresAnimalOnlyAcknowledgement {
                AnimalOnlyAcknowledgementGate(
                    model: model,
                    openExistingProject: { showOpenProjectPanel() }
                )
                .transition(.opacity)
                .zIndex(1)
            }
        }
        .task {
            await model.connectIfNeeded()
        }
        .confirmationDialog(
            "Discard unsaved animal plan changes and reconnect?",
            isPresented: $isConfirmingReconnect,
            titleVisibility: .visible
        ) {
            Button("Discard Changes and Reconnect", role: .destructive) {
                model.discardProbeDraftSession()
                Task { await model.reconnect() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(
                "Apply or revert probe edits, then save the plan, "
                    + "to keep all current changes."
            )
        }
        .confirmationDialog(
            "Discard unsaved animal plan changes and open another project?",
            isPresented: $isConfirmingOpen,
            titleVisibility: .visible
        ) {
            Button("Discard Changes and Open…", role: .destructive) {
                showOpenProjectPanel(discardPendingChanges: true)
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(
                "Apply or revert probe edits, then save the plan, "
                    + "to keep all current changes."
            )
        }
    }

    private func showSaveProjectPanel() {
        let panel = NSSavePanel()
        panel.title = "Save animal surgery plan"
        panel.prompt = "Save Project"
        panel.nameFieldStringValue = "animal-surgery-plan.mouseplan"
        panel.canCreateDirectories = true
        panel.allowedContentTypes = [mousePlanType]
        guard panel.runModal() == .OK, var url = panel.url else { return }
        if url.pathExtension.lowercased() != "mouseplan" {
            url.appendPathExtension("mouseplan")
        }
        Task { _ = await model.saveProject(to: url) }
    }

    private func showOpenProjectPanel(discardPendingChanges: Bool = false) {
        let panel = NSOpenPanel()
        panel.title = "Open animal surgery plan"
        panel.prompt = "Open Project"
        panel.canChooseFiles = true
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.treatsFilePackagesAsDirectories = false
        panel.allowedContentTypes = [mousePlanType]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        if discardPendingChanges {
            model.discardProbeDraftSession()
        }
        Task { _ = await model.openProject(at: url) }
    }

    private func requestReconnect() {
        if model.hasPendingPlanChanges {
            isConfirmingReconnect = true
        } else {
            Task { await model.reconnect() }
        }
    }

    private func requestOpenProject() {
        if model.hasPendingPlanChanges {
            isConfirmingOpen = true
        } else {
            showOpenProjectPanel()
        }
    }

    private var mousePlanType: UTType {
        UTType(exportedAs: "org.mousebrainplanner.mouseplan", conformingTo: .package)
    }
}
