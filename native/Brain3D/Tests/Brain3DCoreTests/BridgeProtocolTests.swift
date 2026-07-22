import Brain3DCore
import Foundation
import Testing

@Suite("NDJSON bridge protocol v1")
struct BridgeProtocolTests {
    @Test("Long bridge timeout covers reference download and preparation")
    func longRunningOperationTimeout() {
        #expect(BridgeTimeoutPolicy.longRunningOperationSeconds == 900)
    }

    @Test("Request wire shape is exactly id, method, params")
    func requestShape() throws {
        let request = BridgeRequest(
            id: "request-1",
            method: "hello",
            params: HelloParameters()
        )
        let data = try JSONEncoder().encode(request)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])

        #expect(Set(object.keys) == Set(["id", "method", "params"]))
        #expect(object["id"] as? String == "request-1")
        #expect(object["method"] as? String == "hello")
        let params = try #require(object["params"] as? [String: Any])
        #expect(Set(params.keys) == Set(["protocolVersion", "client"]))
        #expect(params["protocolVersion"] as? Int == 1)
        #expect(params["client"] as? String == "Brain3DSwiftUI")
    }

    @Test("Project save is scoped to one project revision")
    func projectSaveShape() throws {
        let parameters = ProjectSaveParameters(
            projectId: "10000000-0000-0000-0000-000000000001",
            expectedProjectRevision: 14,
            path: "/tmp/animal.brain3d"
        )
        let data = try JSONEncoder().encode(parameters)
        let object = try #require(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        #expect(Set(object.keys) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "path",
        ])
        #expect(object["expectedProjectRevision"] as? Int == 14)

        let result = try JSONDecoder().decode(
            ProjectSaveResult.self,
            from: Data(
                #"{"protocolVersion":1,"status":"saved","path":"/tmp/animal.brain3d","projectId":"10000000-0000-0000-0000-000000000001","projectRevision":15}"#.utf8
            )
        )
        #expect(result.projectRevision == 15)
    }

    @Test("Typed success response returns the requested result")
    func successResponse() async throws {
        let transport = ScriptedTransport { request in
            let object = try JSONSerialization.jsonObject(with: request) as? [String: Any]
            let id = object?["id"] as? String ?? "missing"
            return Data(
                """
                {"id":"\(id)","result":{"protocolVersion":1,"service":"mouse-brain-planner","applicationVersion":"0.1.0","capabilities":{"atlas25Micrometre":true,"atlasDownload":true,"atlasSlicePng":true,"animalOnly":true,"projectPersistence":true,"subjectVascularImport":true,"subjectVascularOverlay":true,"subjectVascularRegistration":true,"atomicAtlasPointNavigation":true}}}
                """.utf8
            )
        }
        let client = BridgeClient(transport: transport)

        let result: HelloResult = try await client.request(
            method: "hello",
            params: HelloParameters(),
            id: "success-1"
        )

        #expect(result.protocolVersion == 1)
        #expect(result.service == "mouse-brain-planner")
        #expect(result.capabilities.animalOnly)
        #expect(result.capabilities.atomicAtlasPointNavigation == true)
    }

    @Test("Archived vascular capability keys may be omitted")
    func archivedCapabilitiesDefaultToFalse() throws {
        let result = try JSONDecoder().decode(
            HelloResult.self,
            from: Data(
                #"{"protocolVersion":1,"service":"mouse-brain-planner","applicationVersion":"0.1.0","capabilities":{"atlas25Micrometre":true,"atlasDownload":true,"atlasSlicePng":true,"animalOnly":true,"projectPersistence":true}}"#.utf8
            )
        )

        #expect(!result.capabilities.subjectVascularImport)
        #expect(!result.capabilities.subjectVascularOverlay)
        #expect(!result.capabilities.subjectVascularRegistration)
    }

    @Test("Typed remote errors remain errors and preserve details")
    func remoteError() async {
        let response = Data(
            """
            {"id":"error-1","error":{"code":"atlas_unavailable","message":"No verified atlas is loaded","details":{"atlas":"allen_mouse_25um"}}}
            """.utf8
        )
        let client = BridgeClient(transport: ScriptedTransport(response: response))

        do {
            let _: PlannerBridgeState = try await client.request(
                method: "state.get",
                params: StateParameters(),
                id: "error-1"
            )
            Issue.record("Expected the remote error to be thrown")
        } catch let error as BridgeClientError {
            guard case let .remote(remote) = error else {
                Issue.record("Unexpected bridge error: \(error)")
                return
            }
            #expect(remote.code == "atlas_unavailable")
            #expect(remote.details == .object(["atlas": .string("allen_mouse_25um")]))
        } catch {
            Issue.record("Unexpected error type: \(error)")
        }
    }

    @Test("Mismatched response ids are rejected")
    func mismatchedIdentifier() async {
        let response = Data(
            """
            {"id":"other","result":{"protocolVersion":1,"service":"mouse-brain-planner","applicationVersion":"0.1.0","capabilities":{"atlas25Micrometre":true,"atlasDownload":true,"atlasSlicePng":true,"animalOnly":true,"projectPersistence":true,"subjectVascularImport":true,"subjectVascularOverlay":true,"subjectVascularRegistration":true}}}
            """.utf8
        )
        let client = BridgeClient(transport: ScriptedTransport(response: response))

        do {
            let _: HelloResult = try await client.request(
                method: "hello",
                params: HelloParameters(),
                id: "expected"
            )
            Issue.record("Expected a mismatched-id error")
        } catch let error as BridgeClientError {
            #expect(
                error == .mismatchedIdentifier(expected: "expected", actual: "other")
            )
        } catch {
            Issue.record("Unexpected error type: \(error)")
        }
    }

    @Test("A response cannot contain both result and error")
    func mutuallyExclusiveResponseFields() async {
        let response = Data(
            """
            {"id":"both","result":{"protocolVersion":1,"service":"mouse-brain-planner","applicationVersion":"0.1.0","capabilities":{"atlas25Micrometre":true,"atlasDownload":true,"atlasSlicePng":true,"animalOnly":true,"projectPersistence":true,"subjectVascularImport":true,"subjectVascularOverlay":true,"subjectVascularRegistration":true}},"error":{"code":"bad","message":"bad"}}
            """.utf8
        )
        let client = BridgeClient(transport: ScriptedTransport(response: response))

        do {
            let _: HelloResult = try await client.request(
                method: "hello",
                params: HelloParameters(),
                id: "both"
            )
            Issue.record("Expected malformed response rejection")
        } catch let error as BridgeClientError {
            guard case .malformedResponse = error else {
                Issue.record("Unexpected bridge error: \(error)")
                return
            }
        } catch {
            Issue.record("Unexpected error type: \(error)")
        }
    }

    @Test("Subprocess transport exchanges one NDJSON frame")
    func subprocessRoundTrip() async throws {
        let transport = SubprocessNDJSONTransport(
            configuration: BridgeLaunchConfiguration(
                executableURL: URL(fileURLWithPath: "/bin/cat")
            ),
            timeout: 2
        )
        let line = Data(#"{"id":"cat","method":"hello","params":{"protocolVersion":1}}"#.utf8)

        let response = try await transport.exchange(line)
        await transport.close()

        #expect(response == line)
    }

    @Test("Close wakes an in-flight exchange promptly")
    func promptClose() async throws {
        let transport = SubprocessNDJSONTransport(
            configuration: BridgeLaunchConfiguration(
                executableURL: URL(fileURLWithPath: "/bin/sh"),
                arguments: ["-c", "IFS= read -r line; sleep 5"]
            ),
            timeout: 3
        )
        let request = Data(#"{"id":"blocked","method":"hello","params":{}}"#.utf8)
        let exchange = Task {
            try await transport.exchange(request)
        }
        try await Task.sleep(for: .milliseconds(75))
        let clock = ContinuousClock()
        let started = clock.now

        await transport.close()
        let closeDuration = started.duration(to: clock.now)

        do {
            _ = try await exchange.value
            Issue.record("Expected close to interrupt the exchange")
        } catch let error as BridgeTransportError {
            #expect(error == .inputClosed)
        } catch {
            Issue.record("Unexpected close error: \(error)")
        }
        #expect(closeDuration < .milliseconds(500))
    }

    @Test("A timeout poisons the channel so a late response cannot satisfy another request")
    func timeoutPoisonsChannel() async throws {
        let transport = SubprocessNDJSONTransport(
            configuration: BridgeLaunchConfiguration(
                executableURL: URL(fileURLWithPath: "/bin/sh"),
                arguments: [
                    "-c",
                    "IFS= read -r first; sleep 0.3; printf '%s\\n' \"$first\"; IFS= read -r second; printf '%s\\n' \"$second\"",
                ]
            ),
            timeout: 0.05
        )
        let first = Data(#"{"id":"first","method":"hello","params":{}}"#.utf8)
        let second = Data(#"{"id":"second","method":"hello","params":{}}"#.utf8)

        do {
            _ = try await transport.exchange(first)
            Issue.record("Expected the first request to time out")
        } catch let error as BridgeTransportError {
            #expect(error == .timedOut(0.05))
        } catch {
            Issue.record("Unexpected timeout error: \(error)")
        }

        do {
            _ = try await transport.exchange(second)
            Issue.record("A poisoned transport must not be reused")
        } catch let error as BridgeTransportError {
            #expect(error == .inputClosed)
        } catch {
            Issue.record("Unexpected poisoned-channel error: \(error)")
        }
        await transport.close()
    }

    @Test("EOF with an unterminated response is a framing error")
    func truncatedFrame() async throws {
        let transport = SubprocessNDJSONTransport(
            configuration: BridgeLaunchConfiguration(
                executableURL: URL(fileURLWithPath: "/bin/sh"),
                arguments: ["-c", "IFS= read -r line; printf '{\\\"id\\\":\\\"partial\\\"}'"]
            ),
            timeout: 2
        )
        let request = Data(#"{"id":"partial","method":"hello","params":{}}"#.utf8)

        do {
            _ = try await transport.exchange(request)
            Issue.record("Expected an unterminated-frame error")
        } catch let error as BridgeTransportError {
            guard case let .truncatedFrame(byteCount) = error else {
                Issue.record("Unexpected framing error: \(error)")
                return
            }
            #expect(byteCount > 0)
        } catch {
            Issue.record("Unexpected framing error type: \(error)")
        }
        await transport.close()
    }

    @Test("Oversized NDJSON frames are rejected at the configured boundary")
    func oversizedFrame() async throws {
        let transport = SubprocessNDJSONTransport(
            configuration: BridgeLaunchConfiguration(
                executableURL: URL(fileURLWithPath: "/bin/sh"),
                arguments: ["-c", "IFS= read -r line; printf '12345678901234567\\n'"]
            ),
            timeout: 2,
            maximumFrameBytes: 16
        )
        let request = Data(#"{"id":"large","method":"hello","params":{}}"#.utf8)

        do {
            _ = try await transport.exchange(request)
            Issue.record("Expected a frame-size error")
        } catch let error as BridgeTransportError {
            #expect(error == .frameTooLarge(16))
        } catch {
            Issue.record("Unexpected frame-size error: \(error)")
        }
        await transport.close()
    }

    @Test("Environment configuration requires an explicit executable")
    func environmentConfiguration() {
        #expect(BridgeLaunchConfiguration.fromEnvironment([:]) == nil)
        let configuration = BridgeLaunchConfiguration.fromEnvironment([
            "BRAIN3D_BRIDGE_EXECUTABLE": "/usr/bin/python3",
            "BRAIN3D_BRIDGE_ARGUMENTS": #"["-m","mouse_brain_planner.bridge"]"#,
            "BRAIN3D_BRIDGE_WORKING_DIRECTORY": "/tmp/brain3d",
        ])
        #expect(configuration?.executableURL.path == "/usr/bin/python3")
        #expect(configuration?.arguments == ["-m", "mouse_brain_planner.bridge"])
        #expect(configuration?.workingDirectoryURL?.path == "/tmp/brain3d")
    }

    @Test("Development discovery finds the repository backend without shell environment")
    func developmentDiscovery() throws {
        let fileManager = FileManager.default
        let root = fileManager.temporaryDirectory
            .appendingPathComponent("brain3d-swift-discovery-\(UUID().uuidString)")
        defer { try? fileManager.removeItem(at: root) }
        let python = root.appendingPathComponent(".venv/bin/python")
        let server = root.appendingPathComponent("src/mouse_brain_planner/bridge/server.py")
        try fileManager.createDirectory(
            at: python.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(
            at: server.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data("#!/bin/sh\n".utf8).write(to: python)
        try fileManager.setAttributes(
            [.posixPermissions: 0o755],
            ofItemAtPath: python.path
        )
        try Data("# fixture\n".utf8).write(to: server)
        let nestedExecutable = root.appendingPathComponent(
            "native/Brain3D/build/Brain3D.app/Contents/MacOS/Brain3D"
        )

        let discovered = BridgeLaunchConfiguration.developmentDefault(
            environment: [:],
            currentDirectoryURL: root.appendingPathComponent("native/Brain3D"),
            executableURL: nestedExecutable,
            sourceFileURL: root.appendingPathComponent(
                "native/Brain3D/Sources/Brain3DCore/BridgeClient.swift"
            ),
            fileManager: fileManager
        )

        #expect(discovered?.executableURL == python)
        #expect(discovered?.arguments == ["-u", "-m", "mouse_brain_planner.bridge.server"])
        #expect(discovered?.workingDirectoryURL?.standardizedFileURL.path == root.standardizedFileURL.path)
        #expect(discovered?.environment?["PYTHONPATH"] == root.appendingPathComponent("src").path)
    }

    @Test("An environment override wins over development discovery")
    func environmentOverrideWins() {
        let configured = BridgeLaunchConfiguration.developmentDefault(
            environment: [
                "BRAIN3D_BRIDGE_EXECUTABLE": "/custom/bridge",
                "BRAIN3D_BRIDGE_ARGUMENTS": #"["--stdio"]"#,
            ],
            currentDirectoryURL: URL(fileURLWithPath: "/tmp"),
            executableURL: nil,
            sourceFileURL: URL(fileURLWithPath: "/tmp/BridgeClient.swift")
        )

        #expect(configured?.executableURL.path == "/custom/bridge")
        #expect(configured?.arguments == ["--stdio"])
    }
}

private final class ScriptedTransport: NDJSONTransport, @unchecked Sendable {
    private let handler: @Sendable (Data) throws -> Data

    init(response: Data) {
        handler = { _ in response }
    }

    init(handler: @escaping @Sendable (Data) throws -> Data) {
        self.handler = handler
    }

    func exchange(_ requestLine: Data) async throws -> Data {
        try handler(requestLine)
    }

    func close() async {}
}
