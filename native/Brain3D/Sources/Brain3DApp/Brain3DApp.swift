import AppKit
import Brain3DCore
import SwiftUI

enum MainPlanningWindowPolicy {
    static let sceneId = "main-planning-window"
    static let permitsMultipleMainWindows = false
}

@main
struct Brain3DApp: App {
    @NSApplicationDelegateAdaptor(Brain3DAppDelegate.self) private var appDelegate
    @StateObject private var model = PlannerViewModel(
        launchConfiguration: BridgeLaunchConfiguration.developmentDefault()
    )

    var body: some Scene {
        Window(
            "Brain3D Animal Surgery Planner",
            id: MainPlanningWindowPolicy.sceneId
        ) {
            ContentView(model: model)
                .frame(minWidth: 1_080, minHeight: 720)
                .onAppear {
                    appDelegate.model = model
                }
        }
        .defaultSize(width: 1_360, height: 860)
        .windowResizability(.contentMinSize)

        Settings {
            SurgeryPlanSettingsView()
        }
    }
}

@MainActor
private final class Brain3DAppDelegate: NSObject, NSApplicationDelegate {
    weak var model: PlannerViewModel?

    func applicationShouldTerminateAfterLastWindowClosed(
        _ sender: NSApplication
    ) -> Bool {
        false
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        switch TerminationPolicy.decision(
            hasUnsavedChanges: model?.hasPendingPlanChanges == true
        ) {
        case .terminateNow:
            return .terminateNow
        case .requireDiscardConfirmation:
            let alert = NSAlert()
            alert.alertStyle = .warning
            alert.messageText = "Quit and discard unsaved animal plan changes?"
            alert.informativeText =
                "This animal surgery plan has unsaved changes or an unfinished probe edit. "
                + "Cancel to return to the plan, or quit and discard those changes."
            let cancelButton = alert.addButton(withTitle: "Cancel")
            cancelButton.keyEquivalent = "\u{1b}"
            let quitButton = alert.addButton(withTitle: "Quit Without Saving")
            quitButton.hasDestructiveAction = true
            return alert.runModal() == .alertSecondButtonReturn ? .terminateNow : .terminateCancel
        }
    }
}
