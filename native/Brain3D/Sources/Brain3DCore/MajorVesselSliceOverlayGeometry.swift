import Foundation
import simd

public struct MajorVesselSliceSegment: Equatable, Sendable {
    public let start: ProbeSliceImagePoint
    public let end: ProbeSliceImagePoint
    public let startRadiusMicrometres: Double
    public let endRadiusMicrometres: Double
    public let sourceEdgeIndex: Int32

    public init(
        start: ProbeSliceImagePoint,
        end: ProbeSliceImagePoint,
        startRadiusMicrometres: Double,
        endRadiusMicrometres: Double,
        sourceEdgeIndex: Int32
    ) {
        self.start = start
        self.end = end
        self.startRadiusMicrometres = startRadiusMicrometres
        self.endRadiusMicrometres = endRadiusMicrometres
        self.sourceEdgeIndex = sourceEdgeIndex
    }
}

public struct MajorVesselSliceOverlay: Equatable, Sendable {
    public let orientation: AtlasSliceOrientation
    public let sliceIndex: Int
    public let assetSHA256: String
    public let inPlaneResolutionMicrometres: Double
    public let segments: [MajorVesselSliceSegment]

    public init(
        orientation: AtlasSliceOrientation,
        sliceIndex: Int,
        assetSHA256: String,
        inPlaneResolutionMicrometres: Double,
        segments: [MajorVesselSliceSegment]
    ) {
        self.orientation = orientation
        self.sliceIndex = sliceIndex
        self.assetSHA256 = assetSHA256
        self.inPlaneResolutionMicrometres = inPlaneResolutionMicrometres
        self.segments = segments
    }
}

public enum MajorVesselSliceOverlayGeometry {
    /// Project the complete reference graph onto the dorsal AP/ML plane.
    /// The result is explicitly a depth projection; it is not a pial-vessel map.
    public static func makeDorsalProjection(
        geometry: MajorVesselGeometryResult
    ) -> MajorVesselSliceOverlay {
        makeDorsalProjection(
            graph: geometry.graph,
            atlas: geometry.atlas,
            assetSHA256: geometry.provenance.derivedAssetSha256
        )
    }

    public static func makeDorsalProjection(
        graph: MajorVesselGraph,
        atlas: ViewerAtlasIdentity,
        assetSHA256: String
    ) -> MajorVesselSliceOverlay {
        let resolution = atlas.resolutionMicrometres
        var segments: [MajorVesselSliceSegment] = []
        segments.reserveCapacity(graph.segmentCount)
        for runIndex in 0 ..< graph.runCount {
            let runStart = graph.runOffsets[runIndex]
            let runEnd = graph.runOffsets[runIndex + 1]
            let sourceEdgeIndex = graph.sourceEdgeIndices[runIndex]
            for pointIndex in runStart ..< runEnd - 1 {
                let start = graph.pointsASRMicrometres[pointIndex]
                let end = graph.pointsASRMicrometres[pointIndex + 1]
                segments.append(
                    MajorVesselSliceSegment(
                        start: ProbeSliceImagePoint(
                            column: Double(start.z) / resolution.mlMicrometres,
                            row: Double(start.x) / resolution.apMicrometres
                        ),
                        end: ProbeSliceImagePoint(
                            column: Double(end.z) / resolution.mlMicrometres,
                            row: Double(end.x) / resolution.apMicrometres
                        ),
                        startRadiusMicrometres: Double(graph.radiiMicrometres[pointIndex]),
                        endRadiusMicrometres: Double(graph.radiiMicrometres[pointIndex + 1]),
                        sourceEdgeIndex: sourceEdgeIndex
                    )
                )
            }
        }
        return MajorVesselSliceOverlay(
            orientation: .horizontal,
            sliceIndex: -1,
            assetSHA256: assetSHA256,
            inPlaneResolutionMicrometres: (
                resolution.apMicrometres * resolution.mlMicrometres
            ).squareRoot(),
            segments: segments
        )
    }

    /// Project only tapered vessel portions whose radius-bearing volume intersects
    /// the current physical slice slab. Distant centerlines are never projected.
    public static func make(
        geometry: MajorVesselGeometryResult,
        orientation: AtlasSliceOrientation,
        sliceIndex: Int
    ) -> MajorVesselSliceOverlay {
        make(
            graph: geometry.graph,
            atlas: geometry.atlas,
            assetSHA256: geometry.provenance.derivedAssetSha256,
            orientation: orientation,
            sliceIndex: sliceIndex
        )
    }

    public static func make(
        graph: MajorVesselGraph,
        atlas: ViewerAtlasIdentity,
        assetSHA256: String,
        orientation: AtlasSliceOrientation,
        sliceIndex: Int
    ) -> MajorVesselSliceOverlay {
        let resolution = atlas.resolutionMicrometres
        let shape = atlas.shapeVoxels
        let fixedAxis = orientation.fixedAxis
        guard sliceIndex >= 0, sliceIndex < shape[fixedAxis] else {
            return MajorVesselSliceOverlay(
                orientation: orientation,
                sliceIndex: sliceIndex,
                assetSHA256: assetSHA256,
                inPlaneResolutionMicrometres: (
                    resolution[orientation.rowAxis] * resolution[orientation.columnAxis]
                ).squareRoot(),
                segments: []
            )
        }
        let slabMinimum = Double(sliceIndex) * resolution[fixedAxis]
        let slabMaximum = Double(sliceIndex + 1) * resolution[fixedAxis]
        var segments: [MajorVesselSliceSegment] = []
        segments.reserveCapacity(max(64, graph.segmentCount / shape[fixedAxis]))
        for runIndex in 0 ..< graph.runCount {
            let runStart = graph.runOffsets[runIndex]
            let runEnd = graph.runOffsets[runIndex + 1]
            let sourceEdgeIndex = graph.sourceEdgeIndices[runIndex]
            for pointIndex in runStart ..< runEnd - 1 {
                let start = graph.pointsASRMicrometres[pointIndex]
                let end = graph.pointsASRMicrometres[pointIndex + 1]
                let startRadius = Double(graph.radiiMicrometres[pointIndex])
                let endRadius = Double(graph.radiiMicrometres[pointIndex + 1])
                guard let interval = radiusBearingSlabInterval(
                    startFixed: Double(axisValue(start, fixedAxis)),
                    endFixed: Double(axisValue(end, fixedAxis)),
                    startRadius: startRadius,
                    endRadius: endRadius,
                    slabMinimum: slabMinimum,
                    slabMaximum: slabMaximum
                ) else { continue }
                let clippedStart = interpolate(start, end, interval.lowerBound)
                let clippedEnd = interpolate(start, end, interval.upperBound)
                let clippedStartRadius = interpolate(
                    startRadius,
                    endRadius,
                    interval.lowerBound
                )
                let clippedEndRadius = interpolate(
                    startRadius,
                    endRadius,
                    interval.upperBound
                )
                segments.append(
                    MajorVesselSliceSegment(
                        start: imagePoint(
                            clippedStart,
                            orientation: orientation,
                            resolution: resolution
                        ),
                        end: imagePoint(
                            clippedEnd,
                            orientation: orientation,
                            resolution: resolution
                        ),
                        startRadiusMicrometres: clippedStartRadius,
                        endRadiusMicrometres: clippedEndRadius,
                        sourceEdgeIndex: sourceEdgeIndex
                    )
                )
            }
        }
        return MajorVesselSliceOverlay(
            orientation: orientation,
            sliceIndex: sliceIndex,
            assetSHA256: assetSHA256,
            inPlaneResolutionMicrometres: (
                resolution[orientation.rowAxis] * resolution[orientation.columnAxis]
            ).squareRoot(),
            segments: segments
        )
    }

    private static func radiusBearingSlabInterval(
        startFixed: Double,
        endFixed: Double,
        startRadius: Double,
        endRadius: Double,
        slabMinimum: Double,
        slabMaximum: Double
    ) -> ClosedRange<Double>? {
        var lower = 0.0
        var upper = 1.0
        // center(t) + radius(t) >= slabMinimum
        guard constrainNonnegativeLinear(
            intercept: startFixed + startRadius - slabMinimum,
            slope: (endFixed - startFixed) + (endRadius - startRadius),
            lower: &lower,
            upper: &upper
        ) else { return nil }
        // slabMaximum - center(t) + radius(t) >= 0
        guard constrainNonnegativeLinear(
            intercept: slabMaximum - startFixed + startRadius,
            slope: -(endFixed - startFixed) + (endRadius - startRadius),
            lower: &lower,
            upper: &upper
        ) else { return nil }
        lower = min(1, max(0, lower))
        upper = min(1, max(0, upper))
        return lower <= upper ? lower ... upper : nil
    }

    private static func constrainNonnegativeLinear(
        intercept: Double,
        slope: Double,
        lower: inout Double,
        upper: inout Double
    ) -> Bool {
        let scale = max(1, max(abs(intercept), abs(slope)))
        let epsilon = 1e-12 * scale
        if abs(slope) <= epsilon {
            return intercept >= -epsilon
        }
        let crossing = -intercept / slope
        if slope > 0 {
            lower = max(lower, crossing)
        } else {
            upper = min(upper, crossing)
        }
        return lower <= upper + epsilon
    }

    private static func imagePoint(
        _ point: SIMD3<Double>,
        orientation: AtlasSliceOrientation,
        resolution: AtlasASRResolution
    ) -> ProbeSliceImagePoint {
        ProbeSliceImagePoint(
            column: axisValue(point, orientation.columnAxis) / resolution[orientation.columnAxis],
            row: axisValue(point, orientation.rowAxis) / resolution[orientation.rowAxis]
        )
    }

    private static func axisValue<T: SIMDScalar>(
        _ point: SIMD3<T>,
        _ axis: AtlasAnatomicalAxis
    ) -> T {
        switch axis {
        case .ap: point.x
        case .dv: point.y
        case .ml: point.z
        }
    }

    private static func interpolate(
        _ start: SIMD3<Float>,
        _ end: SIMD3<Float>,
        _ fraction: Double
    ) -> SIMD3<Double> {
        let a = SIMD3<Double>(start)
        return a + (SIMD3<Double>(end) - a) * fraction
    }

    private static func interpolate(_ start: Double, _ end: Double, _ fraction: Double) -> Double {
        start + (end - start) * fraction
    }
}
