import Testing

@testable import Brain3DApp

@Suite("SwiftUI view-update mutation boundary")
@MainActor
struct ViewUpdateMutationBoundaryTests {
    @Test("Synchronous publications cannot run in the requesting view-update job")
    func defersSynchronousMutation() async {
        var events = ["request"]

        let task = ViewUpdateMutationBoundary.perform {
            events.append("mutation")
        }
        events.append("callback-returned")

        #expect(events == ["request", "callback-returned"])
        await task.value
        #expect(events == ["request", "callback-returned", "mutation"])
    }

    @Test("Async publications also cross the boundary before starting")
    func defersAsyncMutation() async {
        var events = ["request"]

        let task = ViewUpdateMutationBoundary.performAsync {
            events.append("async-mutation")
        }
        events.append("callback-returned")

        #expect(events == ["request", "callback-returned"])
        await task.value
        #expect(events == ["request", "callback-returned", "async-mutation"])
    }

    @Test("Cancellation prevents a queued publication")
    func cancellationPreventsMutation() async {
        var mutationCount = 0
        let task = ViewUpdateMutationBoundary.perform {
            mutationCount += 1
        }

        task.cancel()
        await task.value

        #expect(mutationCount == 0)
    }
}
