import Foundation
import Testing

@testable import Brain3DApp

private actor DebouncedTaskRecorder {
    private var startedValues: [Int] = []

    func recordStart(_ value: Int) {
        startedValues.append(value)
    }

    func values() -> [Int] {
        startedValues
    }
}

@Suite("Latest debounced task")
@MainActor
struct LatestDebouncedTaskTests {
    @Test("Rapid changes derive and publish only the final value")
    func coalescesRapidChanges() async throws {
        let coordinator = LatestDebouncedTask()
        let recorder = DebouncedTaskRecorder()
        var published: [Int] = []

        // Keep the superseded task comfortably beyond any suite-load jitter;
        // this test is about latest-only semantics, not scheduler precision.
        coordinator.schedule(after: .seconds(1)) {
            await recorder.recordStart(1)
            return 1
        } publish: { value in
            published.append(value)
        } fail: { error in
            Issue.record("Unexpected first-operation failure: \(error)")
        }

        coordinator.schedule(after: .milliseconds(10)) {
            await recorder.recordStart(2)
            return 2
        } publish: { value in
            published.append(value)
        } fail: { error in
            Issue.record("Unexpected final-operation failure: \(error)")
        }

        for _ in 0 ..< 200 {
            if published == [2], !coordinator.isPending { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        let started = await recorder.values()

        #expect(started == [2])
        #expect(published == [2])
        #expect(!coordinator.isPending)
    }

    @Test("A superseded in-flight operation cannot publish")
    func cancelsInFlightOperation() async throws {
        let coordinator = LatestDebouncedTask()
        let recorder = DebouncedTaskRecorder()
        var published: [Int] = []

        coordinator.schedule(after: .zero) {
            await recorder.recordStart(1)
            try await Task.sleep(for: .seconds(2))
            return 1
        } publish: { value in
            published.append(value)
        } fail: { error in
            Issue.record("Unexpected superseded-operation failure: \(error)")
        }

        for _ in 0 ..< 1_000 {
            if await recorder.values().count == 1 { break }
            try await Task.sleep(for: .milliseconds(2))
        }
        let startedBeforeReplacement = await recorder.values()
        #expect(startedBeforeReplacement == [1])

        coordinator.schedule(after: .zero) {
            await recorder.recordStart(2)
            return 2
        } publish: { value in
            published.append(value)
        } fail: { error in
            Issue.record("Unexpected replacement-operation failure: \(error)")
        }

        for _ in 0 ..< 200 {
            if published == [2], !coordinator.isPending { break }
            try await Task.sleep(for: .milliseconds(10))
        }
        let started = await recorder.values()

        #expect(started == [1, 2])
        #expect(published == [2])
        #expect(!coordinator.isPending)
    }
}
