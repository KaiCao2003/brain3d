import Foundation

/// Moves model publication out of the SwiftUI/AppKit control transaction
/// that requested it.
///
/// macOS segmented controls and representable delegates can invoke their
/// bindings while SwiftUI is still updating the view graph. Mutating an
/// `ObservableObject` synchronously from that callback produces SwiftUI's
/// "Publishing changes from within view updates" runtime fault. The first
/// suspension is deliberately unconditional so the mutation cannot run in
/// the callback's executor job.
@MainActor
enum ViewUpdateMutationBoundary {
    static func nextTurn() async {
        await Task.yield()
    }

    @discardableResult
    static func perform(
        _ mutation: @escaping @MainActor () -> Void
    ) -> Task<Void, Never> {
        Task { @MainActor in
            await nextTurn()
            guard !Task.isCancelled else { return }
            mutation()
        }
    }

    @discardableResult
    static func performAsync(
        _ mutation: @escaping @MainActor () async -> Void
    ) -> Task<Void, Never> {
        Task { @MainActor in
            await nextTurn()
            guard !Task.isCancelled else { return }
            await mutation()
        }
    }
}
