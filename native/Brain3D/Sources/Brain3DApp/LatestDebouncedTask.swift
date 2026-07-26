import Foundation

/// Runs only the latest value-producing operation after a short quiet period.
///
/// The operation itself remains responsible for doing CPU-heavy work away from
/// the main actor. This coordinator supplies deterministic debounce,
/// cancellation, and latest-result publication semantics.
@MainActor
final class LatestDebouncedTask {
    private var generation = 0
    private var worker: Task<Void, Never>?

    private(set) var isPending = false

    func schedule<Value: Sendable>(
        after delay: Duration,
        operation: @escaping @Sendable () async throws -> Value,
        publish: @escaping @MainActor (Value) -> Void,
        fail: @escaping @MainActor (any Error) -> Void
    ) {
        generation &+= 1
        let scheduledGeneration = generation
        worker?.cancel()
        isPending = true
        worker = Task { [weak self] in
            do {
                try await Task.sleep(for: delay)
                try Task.checkCancellation()
                let value = try await operation()
                try Task.checkCancellation()
                guard let self,
                      scheduledGeneration == self.generation
                else { return }
                self.worker = nil
                self.isPending = false
                publish(value)
            } catch is CancellationError {
                guard let self,
                      scheduledGeneration == self.generation
                else { return }
                self.worker = nil
                self.isPending = false
            } catch {
                guard let self,
                      scheduledGeneration == self.generation
                else { return }
                self.worker = nil
                self.isPending = false
                fail(error)
            }
        }
    }

    func cancel() {
        generation &+= 1
        worker?.cancel()
        worker = nil
        isPending = false
    }
}
