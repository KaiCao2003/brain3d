import Foundation
import simd

public struct MajorVesselSliceSegment: Equatable, Sendable {
    public let start: ProbeSliceImagePoint
    public let end: ProbeSliceImagePoint
    public let startRadiusMicrometres: Double
    public let endRadiusMicrometres: Double
    public let sourceEdgeIndex: Int32
    public let runIndex: Int
    public let segmentIndexInRun: Int

    public init(
        start: ProbeSliceImagePoint,
        end: ProbeSliceImagePoint,
        startRadiusMicrometres: Double,
        endRadiusMicrometres: Double,
        sourceEdgeIndex: Int32,
        runIndex: Int,
        segmentIndexInRun: Int
    ) {
        self.start = start
        self.end = end
        self.startRadiusMicrometres = startRadiusMicrometres
        self.endRadiusMicrometres = endRadiusMicrometres
        self.sourceEdgeIndex = sourceEdgeIndex
        self.runIndex = runIndex
        self.segmentIndexInRun = segmentIndexInRun
    }
}

public struct MajorVesselSegmentReference: Equatable, Sendable {
    public let runIndex: Int
    public let pointIndex: Int
}

/// Immutable radius-aware lookup built once per verified graph. Slice changes
/// then inspect only segments whose tapered volume can touch that plane.
public struct MajorVesselSliceSpatialIndex: Equatable, Sendable {
    public let assetSHA256: String
    public let atlasMetadataSHA256: String
    private let coronal: [[MajorVesselSegmentReference]]
    private let sagittal: [[MajorVesselSegmentReference]]
    private let horizontal: [[MajorVesselSegmentReference]]

    public init(geometry: MajorVesselGeometryResult) {
        self.init(
            graph: geometry.graph,
            atlas: geometry.atlas,
            assetSHA256: geometry.provenance.derivedAssetSha256
        )
    }

    public init(
        graph: MajorVesselGraph,
        atlas: ViewerAtlasIdentity,
        assetSHA256: String
    ) {
        self.assetSHA256 = assetSHA256
        atlasMetadataSHA256 = atlas.metadataSha256
        coronal = Self.makeBuckets(
            graph: graph,
            fixedAxis: .ap,
            resolutionMicrometres: atlas.resolutionMicrometres.apMicrometres,
            sliceCount: atlas.shapeVoxels.apVoxels
        )
        sagittal = Self.makeBuckets(
            graph: graph,
            fixedAxis: .ml,
            resolutionMicrometres: atlas.resolutionMicrometres.mlMicrometres,
            sliceCount: atlas.shapeVoxels.mlVoxels
        )
        horizontal = Self.makeBuckets(
            graph: graph,
            fixedAxis: .dv,
            resolutionMicrometres: atlas.resolutionMicrometres.dvMicrometres,
            sliceCount: atlas.shapeVoxels.dvVoxels
        )
    }

    public func references(
        for orientation: AtlasSliceOrientation,
        sliceIndex: Int
    ) -> [MajorVesselSegmentReference]? {
        let buckets = switch orientation {
        case .coronal: coronal
        case .sagittal: sagittal
        case .horizontal: horizontal
        }
        guard buckets.indices.contains(sliceIndex) else { return nil }
        return buckets[sliceIndex]
    }

    private static func makeBuckets(
        graph: MajorVesselGraph,
        fixedAxis: AtlasAnatomicalAxis,
        resolutionMicrometres: Double,
        sliceCount: Int
    ) -> [[MajorVesselSegmentReference]] {
        var buckets = [[MajorVesselSegmentReference]](
            repeating: [],
            count: sliceCount
        )
        for runIndex in 0 ..< graph.runCount {
            let runStart = graph.runOffsets[runIndex]
            let runEnd = graph.runOffsets[runIndex + 1]
            for pointIndex in runStart ..< runEnd - 1 {
                let start = Double(axisValue(graph.pointsASRMicrometres[pointIndex], fixedAxis))
                let end = Double(axisValue(graph.pointsASRMicrometres[pointIndex + 1], fixedAxis))
                let startRadius = Double(graph.radiiMicrometres[pointIndex])
                let endRadius = Double(graph.radiiMicrometres[pointIndex + 1])
                let minimum = min(start - startRadius, end - endRadius)
                let maximum = max(start + startRadius, end + endRadius)
                let first = max(0, Int(floor(minimum / resolutionMicrometres)))
                let last = min(
                    sliceCount - 1,
                    Int(floor(maximum / resolutionMicrometres))
                )
                guard first <= last else { continue }
                let reference = MajorVesselSegmentReference(
                    runIndex: runIndex,
                    pointIndex: pointIndex
                )
                for sliceIndex in first ... last {
                    buckets[sliceIndex].append(reference)
                }
            }
        }
        return buckets
    }

    private static func axisValue(
        _ point: SIMD3<Float>,
        _ axis: AtlasAnatomicalAxis
    ) -> Float {
        switch axis {
        case .ap: point.x
        case .dv: point.y
        case .ml: point.z
        }
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
                        sourceEdgeIndex: sourceEdgeIndex,
                        runIndex: runIndex,
                        segmentIndexInRun: pointIndex - runStart
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
        sliceIndex: Int,
        spatialIndex: MajorVesselSliceSpatialIndex? = nil
    ) -> MajorVesselSliceOverlay {
        let references: [MajorVesselSegmentReference]? = if let spatialIndex,
                            spatialIndex.assetSHA256
                            == geometry.provenance.derivedAssetSha256,
                            spatialIndex.atlasMetadataSHA256 == geometry.atlas.metadataSha256
        {
            spatialIndex.references(for: orientation, sliceIndex: sliceIndex)
        } else {
            nil
        }
        return make(
            graph: geometry.graph,
            atlas: geometry.atlas,
            assetSHA256: geometry.provenance.derivedAssetSha256,
            orientation: orientation,
            sliceIndex: sliceIndex,
            segmentReferences: references
        )
    }

    public static func make(
        graph: MajorVesselGraph,
        atlas: ViewerAtlasIdentity,
        assetSHA256: String,
        orientation: AtlasSliceOrientation,
        sliceIndex: Int,
        spatialIndex: MajorVesselSliceSpatialIndex? = nil
    ) -> MajorVesselSliceOverlay {
        let references: [MajorVesselSegmentReference]? = if let spatialIndex,
                            spatialIndex.assetSHA256 == assetSHA256,
                            spatialIndex.atlasMetadataSHA256 == atlas.metadataSha256
        {
            spatialIndex.references(for: orientation, sliceIndex: sliceIndex)
        } else {
            nil
        }
        return make(
            graph: graph,
            atlas: atlas,
            assetSHA256: assetSHA256,
            orientation: orientation,
            sliceIndex: sliceIndex,
            segmentReferences: references
        )
    }

    private static func make(
        graph: MajorVesselGraph,
        atlas: ViewerAtlasIdentity,
        assetSHA256: String,
        orientation: AtlasSliceOrientation,
        sliceIndex: Int,
        segmentReferences: [MajorVesselSegmentReference]?
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
        func appendSegment(runIndex: Int, pointIndex: Int) {
            let runStart = graph.runOffsets[runIndex]
            let sourceEdgeIndex = graph.sourceEdgeIndices[runIndex]
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
            ) else { return }
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
                    sourceEdgeIndex: sourceEdgeIndex,
                    runIndex: runIndex,
                    segmentIndexInRun: pointIndex - runStart
                )
            )
        }
        if let segmentReferences {
            for reference in segmentReferences {
                appendSegment(
                    runIndex: reference.runIndex,
                    pointIndex: reference.pointIndex
                )
            }
        } else {
            for runIndex in 0 ..< graph.runCount {
                let runStart = graph.runOffsets[runIndex]
                let runEnd = graph.runOffsets[runIndex + 1]
                for pointIndex in runStart ..< runEnd - 1 {
                    appendSegment(runIndex: runIndex, pointIndex: pointIndex)
                }
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
