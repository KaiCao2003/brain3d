import Foundation

public enum BridgeTransportError: Error, Equatable, LocalizedError, Sendable {
    case invalidConfiguration(String)
    case launchFailed(String)
    case processTerminated(Int32, String)
    case timedOut(TimeInterval)
    case emptyResponse
    case inputClosed
    case truncatedFrame(Int)
    case frameTooLarge(Int)

    public var errorDescription: String? {
        switch self {
        case let .invalidConfiguration(message), let .launchFailed(message):
            message
        case let .processTerminated(status, diagnostics):
            "Bridge exited with status \(status). \(diagnostics)"
        case let .timedOut(timeout):
            "Bridge did not respond within \(timeout) seconds."
        case .emptyResponse:
            "Bridge closed its output without a response."
        case .inputClosed:
            "Bridge input is closed."
        case let .truncatedFrame(byteCount):
            "Bridge closed stdout with an unterminated \(byteCount)-byte NDJSON frame."
        case let .frameTooLarge(limit):
            "Bridge response exceeded the \(limit)-byte NDJSON frame limit."
        }
    }
}

public struct BridgeLaunchConfiguration: Equatable, Sendable {
    public static let bundledBridgeRelativePath = "Bridge/brain3d-bridge"

    public let executableURL: URL
    public let arguments: [String]
    public let workingDirectoryURL: URL?
    public let environment: [String: String]?

    public init(
        executableURL: URL,
        arguments: [String] = [],
        workingDirectoryURL: URL? = nil,
        environment: [String: String]? = nil
    ) {
        self.executableURL = executableURL
        self.arguments = arguments
        self.workingDirectoryURL = workingDirectoryURL
        self.environment = environment
    }

    public static func fromEnvironment(
        _ environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> BridgeLaunchConfiguration? {
        guard let path = environment["BRAIN3D_BRIDGE_EXECUTABLE"], !path.isEmpty else {
            return nil
        }
        let arguments = environment["BRAIN3D_BRIDGE_ARGUMENTS"]
            .flatMap { try? JSONDecoder().decode([String].self, from: Data($0.utf8)) }
            ?? []
        let workingDirectory = environment["BRAIN3D_BRIDGE_WORKING_DIRECTORY"]
            .map { URL(fileURLWithPath: $0, isDirectory: true) }
        return BridgeLaunchConfiguration(
            executableURL: URL(fileURLWithPath: path),
            arguments: arguments,
            workingDirectoryURL: workingDirectory
        )
    }

    public static func developmentDefault(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        currentDirectoryURL: URL = URL(
            fileURLWithPath: FileManager.default.currentDirectoryPath,
            isDirectory: true
        ),
        executableURL: URL? = Bundle.main.executableURL,
        resourceURL: URL? = Bundle.main.resourceURL,
        sourceFileURL: URL = URL(fileURLWithPath: #filePath),
        fileManager: FileManager = .default
    ) -> BridgeLaunchConfiguration? {
        if let configured = fromEnvironment(environment) {
            return configured
        }

        if let bundled = bundledDefault(
            resourceURL: resourceURL,
            fileManager: fileManager
        ) {
            return bundled
        }

        var seeds = [currentDirectoryURL, sourceFileURL.deletingLastPathComponent()]
        if let executableURL {
            seeds.append(executableURL.deletingLastPathComponent())
        }
        var visited = Set<String>()
        for seed in seeds {
            var candidate = seed.standardizedFileURL
            for _ in 0..<16 {
                let path = candidate.path
                guard visited.insert(path).inserted else { break }
                let python = candidate.appendingPathComponent(".venv/bin/python")
                let server = candidate.appendingPathComponent(
                    "src/mouse_brain_planner/bridge/server.py"
                )
                if
                    fileManager.isExecutableFile(atPath: python.path),
                    fileManager.fileExists(atPath: server.path)
                {
                    return BridgeLaunchConfiguration(
                        executableURL: python,
                        arguments: ["-u", "-m", "mouse_brain_planner.bridge.server"],
                        workingDirectoryURL: candidate,
                        environment: [
                            "PYTHONPATH": candidate.appendingPathComponent("src").path
                        ]
                    )
                }
                let parent = candidate.deletingLastPathComponent()
                if parent.path == candidate.path { break }
                candidate = parent
            }
        }
        return nil
    }

    public static func bundledDefault(
        resourceURL: URL? = Bundle.main.resourceURL,
        fileManager: FileManager = .default
    ) -> BridgeLaunchConfiguration? {
        guard let resourceURL, resourceURL.isFileURL else {
            return nil
        }

        let resourceRoot = resourceURL.resolvingSymlinksInPath().standardizedFileURL
        let candidate = resourceRoot
            .appendingPathComponent(bundledBridgeRelativePath, isDirectory: false)
            .resolvingSymlinksInPath()
            .standardizedFileURL
        let rootPath = resourceRoot.path.hasSuffix("/")
            ? resourceRoot.path
            : resourceRoot.path + "/"
        guard candidate.path.hasPrefix(rootPath) else {
            return nil
        }

        var isDirectory = ObjCBool(false)
        guard
            fileManager.fileExists(atPath: candidate.path, isDirectory: &isDirectory),
            !isDirectory.boolValue,
            fileManager.isExecutableFile(atPath: candidate.path)
        else {
            return nil
        }

        return BridgeLaunchConfiguration(executableURL: candidate)
    }
}

public protocol NDJSONTransport: Sendable {
    func exchange(_ requestLine: Data) async throws -> Data
    func close() async
}

public final class SubprocessNDJSONTransport: NDJSONTransport, @unchecked Sendable {
    private let channel: ProcessChannel
    private let timeout: TimeInterval

    public init(
        configuration: BridgeLaunchConfiguration,
        timeout: TimeInterval = 8,
        maximumFrameBytes: Int = 8 * 1_024 * 1_024
    ) {
        channel = ProcessChannel(
            configuration: configuration,
            maximumFrameBytes: maximumFrameBytes
        )
        self.timeout = timeout
    }

    public func exchange(_ requestLine: Data) async throws -> Data {
        let channel = channel
        let timeout = timeout
        return try await Task.detached(priority: .userInitiated) {
            try channel.exchange(requestLine, timeout: timeout)
        }.value
    }

    public func close() async {
        let channel = channel
        await Task.detached {
            channel.close()
        }.value
    }
}

private final class ProcessChannel: @unchecked Sendable {
    private let configuration: BridgeLaunchConfiguration
    private let maximumFrameBytes: Int
    private let condition = NSCondition()
    private var process: Process?
    private var inputHandle: FileHandle?
    private var outputHandle: FileHandle?
    private var errorHandle: FileHandle?
    private var pendingOutput = Data()
    private var responseLines: [Data] = []
    private var diagnostics = Data()
    private var terminalStatus: Int32?
    private var outputReachedEOF = false
    private var framingFailure: BridgeTransportError?
    private var isClosed = false
    private var hasStarted = false
    private let exchangeLock = NSLock()

    init(configuration: BridgeLaunchConfiguration, maximumFrameBytes: Int) {
        self.configuration = configuration
        self.maximumFrameBytes = max(1, maximumFrameBytes)
    }

    func exchange(_ line: Data, timeout: TimeInterval) throws -> Data {
        exchangeLock.lock()
        defer { exchangeLock.unlock() }

        try startIfNeeded()
        guard let inputHandle else {
            throw BridgeTransportError.inputClosed
        }

        var framedLine = line
        if framedLine.last != 0x0A {
            framedLine.append(0x0A)
        }
        do {
            try inputHandle.write(contentsOf: framedLine)
        } catch {
            throw BridgeTransportError.inputClosed
        }

        let deadline = Date(timeIntervalSinceNow: timeout)
        condition.lock()
        while
            responseLines.isEmpty,
            !outputReachedEOF,
            framingFailure == nil,
            !isClosed
        {
            if !condition.wait(until: deadline) {
                isClosed = true
                condition.broadcast()
                condition.unlock()
                shutDownProcessLocked()
                throw BridgeTransportError.timedOut(timeout)
            }
        }
        if !responseLines.isEmpty {
            let response = responseLines.removeFirst()
            condition.unlock()
            return response
        }
        if let framingFailure {
            isClosed = true
            condition.unlock()
            shutDownProcessLocked()
            throw framingFailure
        }
        if outputReachedEOF, !pendingOutput.isEmpty {
            let byteCount = pendingOutput.count
            isClosed = true
            condition.unlock()
            shutDownProcessLocked()
            throw BridgeTransportError.truncatedFrame(byteCount)
        }
        if isClosed {
            condition.unlock()
            throw BridgeTransportError.inputClosed
        }
        if let terminalStatus {
            let diagnostics = String(decoding: diagnostics, as: UTF8.self)
            condition.unlock()
            throw BridgeTransportError.processTerminated(
                terminalStatus,
                diagnostics
            )
        }
        condition.unlock()
        throw BridgeTransportError.emptyResponse
    }

    func close() {
        // Wake an exchange before waiting for its serialization lock. Waiting first would
        // deadlock shutdown until the request timeout elapsed.
        condition.lock()
        isClosed = true
        condition.broadcast()
        condition.unlock()

        exchangeLock.lock()
        defer { exchangeLock.unlock() }
        shutDownProcessLocked()
    }

    private func shutDownProcessLocked() {
        outputHandle?.readabilityHandler = nil
        errorHandle?.readabilityHandler = nil
        try? inputHandle?.close()
        if let process, process.isRunning {
            process.terminate()
        }
        inputHandle = nil
        outputHandle = nil
        errorHandle = nil
    }

    private func startIfNeeded() throws {
        if process?.isRunning == true {
            return
        }
        condition.lock()
        let closed = isClosed
        let priorStatus = terminalStatus
        condition.unlock()
        if closed {
            throw BridgeTransportError.inputClosed
        }
        if hasStarted {
            throw BridgeTransportError.processTerminated(
                priorStatus ?? process?.terminationStatus ?? -1,
                String(decoding: diagnostics, as: UTF8.self)
            )
        }
        guard configuration.executableURL.isFileURL else {
            throw BridgeTransportError.invalidConfiguration(
                "Bridge executable must be a local file URL."
            )
        }

        let process = Process()
        let inputPipe = Pipe()
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        process.executableURL = configuration.executableURL
        process.arguments = configuration.arguments
        process.currentDirectoryURL = configuration.workingDirectoryURL
        if let environment = configuration.environment {
            process.environment = ProcessInfo.processInfo.environment.merging(environment) { _, new in new }
        }
        process.standardInput = inputPipe
        process.standardOutput = outputPipe
        process.standardError = errorPipe

        let outputHandle = outputPipe.fileHandleForReading
        let errorHandle = errorPipe.fileHandleForReading
        outputHandle.readabilityHandler = { [weak self] handle in
            self?.ingestOutput(handle.availableData)
        }
        errorHandle.readabilityHandler = { [weak self] handle in
            self?.ingestDiagnostics(handle.availableData)
        }
        process.terminationHandler = { [weak self] process in
            self?.recordTermination(process.terminationStatus)
        }

        condition.lock()
        terminalStatus = nil
        outputReachedEOF = false
        framingFailure = nil
        pendingOutput.removeAll(keepingCapacity: true)
        responseLines.removeAll(keepingCapacity: true)
        diagnostics.removeAll(keepingCapacity: true)
        isClosed = false
        condition.unlock()

        do {
            try process.run()
        } catch {
            outputHandle.readabilityHandler = nil
            errorHandle.readabilityHandler = nil
            throw BridgeTransportError.launchFailed(
                "Could not launch bridge at \(configuration.executableURL.path): \(error.localizedDescription)"
            )
        }
        hasStarted = true
        self.process = process
        inputHandle = inputPipe.fileHandleForWriting
        self.outputHandle = outputHandle
        self.errorHandle = errorHandle
    }

    private func ingestOutput(_ data: Data) {
        condition.lock()
        defer { condition.unlock() }
        guard !data.isEmpty else {
            outputReachedEOF = true
            condition.broadcast()
            return
        }
        pendingOutput.append(data)
        while let newline = pendingOutput.firstIndex(of: 0x0A) {
            let line = pendingOutput[..<newline]
            if line.count > maximumFrameBytes {
                framingFailure = .frameTooLarge(maximumFrameBytes)
            } else {
                responseLines.append(Data(line))
            }
            pendingOutput.removeSubrange(...newline)
        }
        if pendingOutput.count > maximumFrameBytes {
            framingFailure = .frameTooLarge(maximumFrameBytes)
        }
        condition.broadcast()
    }

    private func ingestDiagnostics(_ data: Data) {
        guard !data.isEmpty else { return }
        condition.lock()
        diagnostics.append(data)
        if diagnostics.count > 8_192 {
            diagnostics.removeFirst(diagnostics.count - 8_192)
        }
        condition.unlock()
    }

    private func recordTermination(_ status: Int32) {
        condition.lock()
        terminalStatus = status
        condition.broadcast()
        condition.unlock()
    }
}

public enum BridgeClientError: Error, Equatable, LocalizedError, Sendable {
    case malformedResponse(String)
    case mismatchedIdentifier(expected: String, actual: String)
    case remote(BridgeRemoteError)

    public var errorDescription: String? {
        switch self {
        case let .malformedResponse(message):
            message
        case let .mismatchedIdentifier(expected, actual):
            "Bridge response id \(actual) did not match request id \(expected)."
        case let .remote(error):
            if case let .object(details) = error.details,
               case let .string(exceptionType) = details["exceptionType"]
            {
                "\(error.code): \(error.message) (\(exceptionType))"
            } else {
                "\(error.code): \(error.message)"
            }
        }
    }
}

public actor BridgeClient {
    private let transport: any NDJSONTransport
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(transport: any NDJSONTransport) {
        self.transport = transport
        encoder = JSONEncoder()
        decoder = JSONDecoder()
    }

    public func request<Parameters, Result>(
        method: String,
        params: Parameters,
        resultType: Result.Type = Result.self,
        id: String = UUID().uuidString
    ) async throws -> Result
    where Parameters: Encodable & Sendable, Result: Decodable & Sendable {
        let request = BridgeRequest(id: id, method: method, params: params)
        let encoded: Data
        do {
            encoded = try encoder.encode(request)
        } catch {
            throw BridgeClientError.malformedResponse(
                "Could not encode bridge request: \(error.localizedDescription)"
            )
        }
        let line = try await transport.exchange(encoded)
        let response: BridgeResponse<Result>
        do {
            response = try decoder.decode(BridgeResponse<Result>.self, from: line)
        } catch {
            throw BridgeClientError.malformedResponse(
                "Could not decode bridge response: \(error.localizedDescription)"
            )
        }
        guard response.id == id else {
            throw BridgeClientError.mismatchedIdentifier(expected: id, actual: response.id)
        }
        switch (response.result, response.error) {
        case let (.some(result), .none):
            return result
        case let (.none, .some(error)):
            throw BridgeClientError.remote(error)
        default:
            throw BridgeClientError.malformedResponse(
                "Bridge response must contain exactly one of result or error."
            )
        }
    }

    public func close() async {
        await transport.close()
    }
}
