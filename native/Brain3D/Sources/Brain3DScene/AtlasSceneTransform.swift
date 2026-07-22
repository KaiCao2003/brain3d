import Brain3DCore
import Foundation
import simd

public struct AtlasSceneTransform: Equatable, Sendable {
    public static let sceneUnitsPerMicrometre = 0.001

    public let anchorApMicrometres: Double
    public let anchorDvMicrometres: Double
    public let anchorMlMicrometres: Double

    public init(anchor: AtlasPhysicalPoint) throws {
        try self.init(
            anchorApMicrometres: anchor.apMicrometres,
            anchorDvMicrometres: anchor.dvMicrometres,
            anchorMlMicrometres: anchor.mlMicrometres
        )
    }

    public init(
        anchorApMicrometres: Double,
        anchorDvMicrometres: Double,
        anchorMlMicrometres: Double
    ) throws {
        guard [anchorApMicrometres, anchorDvMicrometres, anchorMlMicrometres]
            .allSatisfy({ $0.isFinite && $0 >= 0 })
        else {
            throw AtlasSceneContractError.invalid(
                "Atlas scene anchor must contain finite nonnegative ASR coordinates."
            )
        }
        self.anchorApMicrometres = anchorApMicrometres
        self.anchorDvMicrometres = anchorDvMicrometres
        self.anchorMlMicrometres = anchorMlMicrometres
    }

    public func scenePoint(
        apMicrometres: Double,
        dvMicrometres: Double,
        mlMicrometres: Double
    ) throws -> SIMD3<Float> {
        let values = [apMicrometres, dvMicrometres, mlMicrometres]
        guard values.allSatisfy(\.isFinite) else {
            throw AtlasSceneContractError.invalid("Atlas scene points must be finite.")
        }
        let scaled = SIMD3<Double>(
            (anchorMlMicrometres - mlMicrometres) * Self.sceneUnitsPerMicrometre,
            (anchorDvMicrometres - dvMicrometres) * Self.sceneUnitsPerMicrometre,
            (apMicrometres - anchorApMicrometres) * Self.sceneUnitsPerMicrometre
        )
        guard [scaled.x, scaled.y, scaled.z].allSatisfy({
            $0.isFinite && abs($0) <= Double(Float.greatestFiniteMagnitude)
        }) else {
            throw AtlasSceneContractError.invalid("Atlas scene point exceeds renderer range.")
        }
        return SIMD3(Float(scaled.x), Float(scaled.y), Float(scaled.z))
    }

    public func scenePoint(_ point: ProbePhysicalPoint) throws -> SIMD3<Float> {
        try scenePoint(
            apMicrometres: point.apMicrometres,
            dvMicrometres: point.dvMicrometres,
            mlMicrometres: point.mlMicrometres
        )
    }

    public func atlasPoint(from scenePoint: SIMD3<Float>) throws -> AtlasRayPoint {
        guard [scenePoint.x, scenePoint.y, scenePoint.z].allSatisfy(\.isFinite) else {
            throw AtlasSceneContractError.invalid("Renderer ray points must be finite.")
        }
        let inverseScale = 1.0 / Self.sceneUnitsPerMicrometre
        return try AtlasRayPoint(
            apMicrometres: anchorApMicrometres + Double(scenePoint.z) * inverseScale,
            dvMicrometres: anchorDvMicrometres - Double(scenePoint.y) * inverseScale,
            mlMicrometres: anchorMlMicrometres - Double(scenePoint.x) * inverseScale
        )
    }

    public var sourceToSceneMatrix: simd_float4x4 {
        let scale = Float(Self.sceneUnitsPerMicrometre)
        return simd_float4x4(columns: (
            SIMD4<Float>(0, 0, scale, 0),
            SIMD4<Float>(0, -scale, 0, 0),
            SIMD4<Float>(-scale, 0, 0, 0),
            SIMD4<Float>(
                scale * Float(anchorMlMicrometres),
                scale * Float(anchorDvMicrometres),
                -scale * Float(anchorApMicrometres),
                1
            )
        ))
    }
}
