import Foundation

public enum BridgeTimeoutPolicy {
    /// The protocol-v1 subprocess is serialized, so its channel timeout must
    /// accommodate the largest supported request: pinned archive download,
    /// checksum verification, extraction, and 50 µm density preparation.
    public static let longRunningOperationSeconds: TimeInterval = 15 * 60
}
