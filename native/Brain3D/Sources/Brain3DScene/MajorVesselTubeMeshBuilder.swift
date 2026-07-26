import Brain3DCore
import Foundation
import simd

struct MajorVesselTubeMeshData: Sendable {
    let vertexData: Data
    let normalData: Data
    let indexData: Data
    let vertexCount: Int
    let triangleCount: Int
    let visibleSourceSegmentCount: Int
}

enum MajorVesselTubeMeshBuilder {
    static let sideCount = 6

    static func buildAsync(
        pointsASRMicrometres: [SIMD3<Float>],
        radiiMicrometres: [Float],
        runOffsets: [Int],
        minimumVisibleDiameterMicrometres: Double = 0
    ) async throws -> MajorVesselTubeMeshData {
        let worker = Task.detached(priority: .userInitiated) {
            try build(
                pointsASRMicrometres: pointsASRMicrometres,
                radiiMicrometres: radiiMicrometres,
                runOffsets: runOffsets,
                minimumVisibleDiameterMicrometres:
                    minimumVisibleDiameterMicrometres
            )
        }
        return try await withTaskCancellationHandler {
            try await worker.value
        } onCancel: {
            worker.cancel()
        }
    }

    static func build(
        pointsASRMicrometres: [SIMD3<Float>],
        radiiMicrometres: [Float],
        runOffsets: [Int],
        minimumVisibleDiameterMicrometres: Double = 0
    ) throws -> MajorVesselTubeMeshData {
        try validate(
            pointsASRMicrometres: pointsASRMicrometres,
            radiiMicrometres: radiiMicrometres,
            runOffsets: runOffsets,
            minimumVisibleDiameterMicrometres:
                minimumVisibleDiameterMicrometres
        )
        let filtered = try filteredRuns(
            pointsASRMicrometres: pointsASRMicrometres,
            radiiMicrometres: radiiMicrometres,
            runOffsets: runOffsets,
            minimumVisibleDiameterMicrometres:
                minimumVisibleDiameterMicrometres
        )
        guard !filtered.points.isEmpty else {
            return MajorVesselTubeMeshData(
                vertexData: Data(),
                normalData: Data(),
                indexData: Data(),
                vertexCount: 0,
                triangleCount: 0,
                visibleSourceSegmentCount: 0
            )
        }

        let pointsASRMicrometres = filtered.points
        let radiiMicrometres = filtered.radii
        let runOffsets = filtered.runOffsets
        let segmentCount = filtered.visibleSourceSegmentCount
        var vertices = [PackedFloat3]()
        var normals = [PackedFloat3]()
        var indices = [UInt32]()
        vertices.reserveCapacity(pointsASRMicrometres.count * sideCount)
        normals.reserveCapacity(pointsASRMicrometres.count * sideCount)
        indices.reserveCapacity(segmentCount * sideCount * 6)

        for runIndex in 0 ..< runOffsets.count - 1 {
            try Task.checkCancellation()
            let start = runOffsets[runIndex]
            let end = runOffsets[runIndex + 1]
            let runPoints = Array(pointsASRMicrometres[start ..< end])
            let tangents = try makeTangents(runPoints)
            let runVertexStart = vertices.count
            var normal = initialNormal(for: tangents[0])

            for pointIndex in runPoints.indices {
                if pointIndex.isMultiple(of: 256) {
                    try Task.checkCancellation()
                }
                let tangent = tangents[pointIndex]
                if pointIndex > 0 {
                    normal = transportedNormal(normal, to: tangent)
                }
                let binormal = try normalizedOrThrow(
                    simd_cross(tangent, normal),
                    label: "major-vessel frame"
                )
                normal = try normalizedOrThrow(
                    simd_cross(binormal, tangent),
                    label: "major-vessel frame"
                )
                let radius = radiiMicrometres[start + pointIndex]
                for side in 0 ..< sideCount {
                    let angle = Float(side) / Float(sideCount) * 2 * .pi
                    let radial = cos(angle) * normal + sin(angle) * binormal
                    vertices.append(PackedFloat3(runPoints[pointIndex] + radius * radial))
                    normals.append(PackedFloat3(radial))
                }
            }

            for pointIndex in 0 ..< runPoints.count - 1 {
                if pointIndex.isMultiple(of: 256) {
                    try Task.checkCancellation()
                }
                let current = runVertexStart + pointIndex * sideCount
                let next = current + sideCount
                for side in 0 ..< sideCount {
                    let followingSide = (side + 1) % sideCount
                    let a = try checkedIndex(current + side)
                    let b = try checkedIndex(next + side)
                    let c = try checkedIndex(next + followingSide)
                    let d = try checkedIndex(current + followingSide)
                    indices.append(contentsOf: [a, b, d, d, b, c])
                }
            }
        }

        return MajorVesselTubeMeshData(
            vertexData: vertices.withUnsafeBytes { Data($0) },
            normalData: normals.withUnsafeBytes { Data($0) },
            indexData: indices.withUnsafeBytes { Data($0) },
            vertexCount: vertices.count,
            triangleCount: indices.count / 3,
            visibleSourceSegmentCount: filtered.visibleSourceSegmentCount
        )
    }

    private static func validate(
        pointsASRMicrometres: [SIMD3<Float>],
        radiiMicrometres: [Float],
        runOffsets: [Int],
        minimumVisibleDiameterMicrometres: Double
    ) throws {
        guard pointsASRMicrometres.count == radiiMicrometres.count,
              !pointsASRMicrometres.isEmpty,
              runOffsets.count >= 2,
              runOffsets.first == 0,
              runOffsets.last == pointsASRMicrometres.count,
              pointsASRMicrometres.count <= Int(UInt32.max) / sideCount,
              pointsASRMicrometres.allSatisfy({ point in
                  point.x.isFinite && point.y.isFinite && point.z.isFinite
              }),
              radiiMicrometres.allSatisfy({ $0.isFinite && $0 > 0 }),
              minimumVisibleDiameterMicrometres.isFinite,
              minimumVisibleDiameterMicrometres >= 0
        else {
            throw AtlasSceneContractError.invalid(
                "Major-vessel points, radii, or run boundaries are inconsistent."
            )
        }
        for pair in zip(runOffsets, runOffsets.dropFirst()) {
            guard pair.0 >= 0,
                  pair.1 <= pointsASRMicrometres.count,
                  pair.1 - pair.0 >= 2
            else {
                throw AtlasSceneContractError.invalid(
                    "Each major-vessel run must contain at least two in-bounds points."
                )
            }
            for index in pair.0 ..< pair.1 - 1 {
                guard simd_distance_squared(
                    pointsASRMicrometres[index],
                    pointsASRMicrometres[index + 1]
                ) > 0 else {
                    throw AtlasSceneContractError.invalid(
                        "Major-vessel runs cannot contain zero-length segments."
                    )
                }
            }
        }
    }

    private struct FilteredRuns {
        let points: [SIMD3<Float>]
        let radii: [Float]
        let runOffsets: [Int]
        let visibleSourceSegmentCount: Int
    }

    private static func filteredRuns(
        pointsASRMicrometres: [SIMD3<Float>],
        radiiMicrometres: [Float],
        runOffsets: [Int],
        minimumVisibleDiameterMicrometres: Double
    ) throws -> FilteredRuns {
        try Task.checkCancellation()
        guard minimumVisibleDiameterMicrometres > 0 else {
            return FilteredRuns(
                points: pointsASRMicrometres,
                radii: radiiMicrometres,
                runOffsets: runOffsets,
                visibleSourceSegmentCount:
                    pointsASRMicrometres.count - (runOffsets.count - 1)
            )
        }

        let threshold = MajorVesselDisplayFilter.clampedMinimumDiameterMicrometres(
            minimumVisibleDiameterMicrometres
        )
        var points: [SIMD3<Float>] = []
        var radii: [Float] = []
        var filteredOffsets = [0]
        var visibleSourceSegmentCount = 0

        func appendInterpolated(
            pointIndex: Int,
            fraction: Double
        ) {
            let start = pointsASRMicrometres[pointIndex]
            let end = pointsASRMicrometres[pointIndex + 1]
            let startRadius = radiiMicrometres[pointIndex]
            let endRadius = radiiMicrometres[pointIndex + 1]
            let fraction = Float(fraction)
            points.append(start + (end - start) * fraction)
            radii.append(startRadius + (endRadius - startRadius) * fraction)
        }

        func finishRun() {
            guard filteredOffsets.last != points.count else { return }
            filteredOffsets.append(points.count)
        }

        for runIndex in 0 ..< runOffsets.count - 1 {
            if runIndex.isMultiple(of: 256) {
                try Task.checkCancellation()
            }
            let runStart = runOffsets[runIndex]
            let runEnd = runOffsets[runIndex + 1]
            var previousReachedSourceEndpoint = false
            for pointIndex in runStart ..< runEnd - 1 {
                guard let interval = MajorVesselDisplayFilter.visibleInterval(
                    startRadiusMicrometres: Double(radiiMicrometres[pointIndex]),
                    endRadiusMicrometres: Double(radiiMicrometres[pointIndex + 1]),
                    minimumDiameterMicrometres: threshold
                ) else {
                    finishRun()
                    previousReachedSourceEndpoint = false
                    continue
                }

                let continuesPrevious = previousReachedSourceEndpoint
                    && interval.lowerBound <= 1e-12
                    && filteredOffsets.last != points.count
                if !continuesPrevious {
                    finishRun()
                    appendInterpolated(
                        pointIndex: pointIndex,
                        fraction: interval.lowerBound
                    )
                }
                appendInterpolated(
                    pointIndex: pointIndex,
                    fraction: interval.upperBound
                )
                visibleSourceSegmentCount += 1
                previousReachedSourceEndpoint = interval.upperBound >= 1 - 1e-12
                if !previousReachedSourceEndpoint {
                    finishRun()
                }
            }
            finishRun()
        }

        return FilteredRuns(
            points: points,
            radii: radii,
            runOffsets: filteredOffsets,
            visibleSourceSegmentCount: visibleSourceSegmentCount
        )
    }

    private static func makeTangents(_ points: [SIMD3<Float>]) throws -> [SIMD3<Float>] {
        var tangents = [SIMD3<Float>]()
        tangents.reserveCapacity(points.count)
        for index in points.indices {
            let tangent: SIMD3<Float>
            if index == points.startIndex {
                tangent = points[index + 1] - points[index]
            } else if index == points.index(before: points.endIndex) {
                tangent = points[index] - points[index - 1]
            } else {
                let incoming = try normalizedOrThrow(
                    points[index] - points[index - 1],
                    label: "major-vessel tangent"
                )
                let outgoing = try normalizedOrThrow(
                    points[index + 1] - points[index],
                    label: "major-vessel tangent"
                )
                let average = incoming + outgoing
                tangent = simd_length_squared(average) > 1e-12 ? average : outgoing
            }
            tangents.append(
                try normalizedOrThrow(tangent, label: "major-vessel tangent")
            )
        }
        return tangents
    }

    private static func initialNormal(for tangent: SIMD3<Float>) -> SIMD3<Float> {
        let absolute = simd_abs(tangent)
        let reference: SIMD3<Float>
        if absolute.x <= absolute.y, absolute.x <= absolute.z {
            reference = SIMD3(1, 0, 0)
        } else if absolute.y <= absolute.z {
            reference = SIMD3(0, 1, 0)
        } else {
            reference = SIMD3(0, 0, 1)
        }
        return simd_normalize(simd_cross(tangent, reference))
    }

    private static func transportedNormal(
        _ previous: SIMD3<Float>,
        to tangent: SIMD3<Float>
    ) -> SIMD3<Float> {
        let projected = previous - tangent * simd_dot(previous, tangent)
        if simd_length_squared(projected) > 1e-12 {
            return simd_normalize(projected)
        }
        return initialNormal(for: tangent)
    }

    private static func normalizedOrThrow(
        _ vector: SIMD3<Float>,
        label: String
    ) throws -> SIMD3<Float> {
        let squaredLength = simd_length_squared(vector)
        guard squaredLength.isFinite, squaredLength > 1e-12 else {
            throw AtlasSceneContractError.invalid("\(label) is degenerate.")
        }
        return vector / squaredLength.squareRoot()
    }

    private static func checkedIndex(_ value: Int) throws -> UInt32 {
        guard let index = UInt32(exactly: value) else {
            throw AtlasSceneContractError.invalid(
                "Major-vessel tube mesh exceeds the supported index range."
            )
        }
        return index
    }
}

private struct PackedFloat3: Sendable {
    let x: Float
    let y: Float
    let z: Float

    init(_ value: SIMD3<Float>) {
        x = value.x
        y = value.y
        z = value.z
    }
}
