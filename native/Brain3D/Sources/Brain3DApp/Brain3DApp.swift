import AppKit
import Brain3DCore
import SwiftUI

@main
struct Brain3DApp: App {
    @NSApplicationDelegateAdaptor(Brain3DAppDelegate.self) private var appDelegate
    @StateObject private var model = PlannerViewModel(
        launchConfiguration: BridgeLaunchConfiguration.developmentDefault()
    )

    var body: some Scene {
        WindowGroup("Brain3D Animal Surgery Planner") {
            ContentView(model: model)
                .frame(minWidth: 1_080, minHeight: 720)
                .onAppear {
                    appDelegate.model = model
                }
        }
        .defaultSize(width: 1_360, height: 860)
        .windowResizability(.contentMinSize)
    }
}

@MainActor
private final class Brain3DAppDelegate: NSObject, NSApplicationDelegate {
    weak var model: PlannerViewModel?

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        switch TerminationPolicy.decision(hasUnsavedChanges: model?.hasUnsavedChanges == true) {
        case .terminateNow:
            return .terminateNow
        case .requireDiscardConfirmation:
            let alert = NSAlert()
            alert.alertStyle = .warning
            alert.messageText = "Quit and discard unsaved animal plan changes?"
            alert.informativeText =
                "This animal surgery plan has unsaved changes. Cancel to return to the plan, "
                + "or quit without saving and discard those changes."
            let cancelButton = alert.addButton(withTitle: "Cancel")
            cancelButton.keyEquivalent = "\u{1b}"
            let quitButton = alert.addButton(withTitle: "Quit Without Saving")
            quitButton.hasDestructiveAction = true
            return alert.runModal() == .alertSecondButtonReturn ? .terminateNow : .terminateCancel
        }
    }
}
