import AppKit
import Brain3DCore
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @ObservedObject var model: PlannerViewModel
    @State private var isImportingVesselImage = false
    @State private var isRegisteringVesselImage = false
    @State private var isConfirmingReconnect = false
    @State private var isConfirmingOpen = false

    var body: some View {
        ZStack {
            NavigationSplitView(columnVisibility: .constant(.all)) {
                ProjectSidebar(
                    model: model,
                    importVesselImage: { isImportingVesselImage = true },
                    registerVesselImage: { isRegisteringVesselImage = true },
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
                    openExistingProject: showOpenProjectPanel
                )
                .transition(.opacity)
                .zIndex(1)
            }
        }
        .fileImporter(
            isPresented: $isImportingVesselImage,
            allowedContentTypes: [.png, .jpeg, .tiff],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case let .success(urls):
                guard let url = urls.first else { return }
                Task { await model.importSubjectVesselImage(from: url) }
            case .failure:
                break
            }
        }
        .task {
            await model.connectIfNeeded()
        }
        .onChange(of: model.workspaceMode) { _, mode in
            Task { await model.loadSlice(for: mode) }
        }
        .sheet(isPresented: $isRegisteringVesselImage) {
            VascularRegistrationSheet(model: model)
        }
        .confirmationDialog(
            "Discard unsaved animal plan changes and reconnect?",
            isPresented: $isConfirmingReconnect,
            titleVisibility: .visible
        ) {
            Button("Discard Changes and Reconnect", role: .destructive) {
                Task { await model.reconnect() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Save As first if you need this project, imported vessel image, or registration.")
        }
        .confirmationDialog(
            "Discard unsaved animal plan changes and open another project?",
            isPresented: $isConfirmingOpen,
            titleVisibility: .visible
        ) {
            Button("Discard Changes and Open…", role: .destructive) {
                showOpenProjectPanel()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Save As first if you need this project, imported vessel image, or registration.")
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

    private func showOpenProjectPanel() {
        let panel = NSOpenPanel()
        panel.title = "Open animal surgery plan"
        panel.prompt = "Open Project"
        panel.canChooseFiles = true
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.treatsFilePackagesAsDirectories = false
        panel.allowedContentTypes = [mousePlanType]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        Task { _ = await model.openProject(at: url) }
    }

    private func requestReconnect() {
        if model.hasUnsavedChanges {
            isConfirmingReconnect = true
        } else {
            Task { await model.reconnect() }
        }
    }

    private func requestOpenProject() {
        if model.hasUnsavedChanges {
            isConfirmingOpen = true
        } else {
            showOpenProjectPanel()
        }
    }

    private var mousePlanType: UTType {
        UTType(exportedAs: "org.mousebrainplanner.mouseplan", conformingTo: .package)
    }
}
