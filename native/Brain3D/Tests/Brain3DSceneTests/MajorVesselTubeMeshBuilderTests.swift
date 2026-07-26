import Brain3DCore
import Foundation
import Testing
import simd

@testable import Brain3DScene

@Suite("Radius-bearing reference major-vessel tubes")
struct MajorVesselTubeMeshBuilderTests {
    @Test("Six-sided rings preserve every point radius and never join runs")
    func taperedRuns() throws {
        let points: [SIMD3<Float>] = [
            SIMD3(100, 200, 300),
            SIMD3(200, 200, 300),
            SIMD3(500, 600, 700),
            SIMD3(500, 700, 700),
        ]
        let radii: [Float] = [10, 20, 30, 40]
        let mesh = try MajorVesselTubeMeshBuilder.build(
            pointsASRMicrometres: points,
            radiiMicrometres: radii,
            runOffsets: [0, 2, 4]
        )

        #expect(mesh.vertexCount == points.count * 6)
        #expect(mesh.triangleCount == 24)
        #expect(mesh.vertexData.count == mesh.vertexCount * 3 * MemoryLayout<Float>.size)
        #expect(mesh.normalData.count == mesh.vertexData.count)
        #expect(mesh.indexData.count == mesh.triangleCount * 3 * MemoryLayout<UInt32>.size)

        for pointIndex in points.indices {
            for side in 0 ..< 6 {
                let vertex = vector(
                    from: mesh.vertexData,
                    at: pointIndex * 6 + side
                )
                #expect(abs(simd_distance(vertex, points[pointIndex]) - radii[pointIndex]) < 0.001)
            }
        }

        let indices = uint32Values(mesh.indexData)
        #expect(indices[0 ..< 36].allSatisfy { $0 < 12 })
        #expect(indices[36 ..< 72].allSatisfy { $0 >= 12 && $0 < 24 })
    }

    @Test("3D mesh clips tapered runs at the display diameter")
    func displayDiameterFilter() throws {
        let mesh = try MajorVesselTubeMeshBuilder.build(
            pointsASRMicrometres: [
                SIMD3(0, 0, 0),
                SIMD3(100, 0, 0),
                SIMD3(200, 0, 0),
            ],
            radiiMicrometres: [15, 35, 15],
            runOffsets: [0, 3],
            minimumVisibleDiameterMicrometres: 50
        )

        #expect(mesh.visibleSourceSegmentCount == 2)
        #expect(mesh.vertexCount == 3 * MajorVesselTubeMeshBuilder.sideCount)
        #expect(mesh.triangleCount == 24)
        let first = vector(from: mesh.vertexData, at: 0)
        let last = vector(
            from: mesh.vertexData,
            at: mesh.vertexCount - MajorVesselTubeMeshBuilder.sideCount
        )
        #expect(abs(simd_distance(first, SIMD3<Float>(50, 0, 0)) - 25) < 0.001)
        #expect(abs(simd_distance(last, SIMD3<Float>(150, 0, 0)) - 25) < 0.001)

        let hidden = try MajorVesselTubeMeshBuilder.build(
            pointsASRMicrometres: [SIMD3(0, 0, 0), SIMD3(100, 0, 0)],
            radiiMicrometres: [15, 35],
            runOffsets: [0, 2],
            minimumVisibleDiameterMicrometres: 80
        )
        #expect(hidden.visibleSourceSegmentCount == 0)
        #expect(hidden.vertexCount == 0)
        #expect(hidden.triangleCount == 0)
    }

    @Test("Zero-length vessel segments fail closed")
    func zeroLengthRejected() {
        #expect(throws: AtlasSceneContractError.self) {
            try MajorVesselTubeMeshBuilder.build(
                pointsASRMicrometres: [SIMD3(1, 2, 3), SIMD3(1, 2, 3)],
                radiiMicrometres: [10, 10],
                runOffsets: [0, 2]
            )
        }
    }

    @Test("Scene node uses one batched triangle geometry and the atlas transform")
    @MainActor
    func batchedSceneNode() throws {
        let mesh = try MajorVesselTubeMeshBuilder.build(
            pointsASRMicrometres: [SIMD3(0, 0, 0), SIMD3(100, 0, 0)],
            radiiMicrometres: [15, 25],
            runOffsets: [0, 2]
        )
        let transform = try AtlasSceneTransform(
            anchorApMicrometres: 50,
            anchorDvMicrometres: 60,
            anchorMlMicrometres: 70
        )

        let node = MajorVesselNodeFactory.makeNode(mesh: mesh, transform: transform)

        #expect(node.geometry?.elementCount == 1)
        #expect(node.geometry?.elements.first?.primitiveType == .triangles)
        #expect(node.categoryBitMask == SceneCategory.majorVessel.rawValue)
        #expect(node.simdTransform == transform.sourceToSceneMatrix)
    }

    @Test("Cancelling an async rebuild stops its detached mesh worker")
    func asyncCancellation() async {
        let pointCount = 100_000
        let points = (0..<pointCount).map {
            SIMD3<Float>(Float($0), 0, 0)
        }
        let radii = [Float](repeating: 25, count: pointCount)
        let worker = Task {
            try await MajorVesselTubeMeshBuilder.buildAsync(
                pointsASRMicrometres: points,
                radiiMicrometres: radii,
                runOffsets: [0, pointCount],
                minimumVisibleDiameterMicrometres: 30
            )
        }

        await Task.yield()
        worker.cancel()

        await #expect(throws: CancellationError.self) {
            try await worker.value
        }
    }

    @Test("Production cardinality fits one deterministic batch")
    func productionCardinality() throws {
        let pointCount = MajorVesselContract.expectedPointCount
        let runCount = MajorVesselContract.expectedRunCount
        let segmentCount = MajorVesselContract.expectedSegmentCount
        let longRunPointCount = segmentCount - (runCount - 1) + 1
        var points = (0 ..< longRunPointCount).map {
            SIMD3<Float>(Float($0), 0, 0)
        }
        var runOffsets = [0, longRunPointCount]
        points.reserveCapacity(pointCount)
        runOffsets.reserveCapacity(runCount + 1)
        for run in 1 ..< runCount {
            let coordinate = Float(run)
            points.append(SIMD3<Float>(0, coordinate, 0))
            points.append(SIMD3<Float>(1, coordinate, 0))
            runOffsets.append(points.count)
        }
        let radii = points.indices.map { Float(15 + $0 % 27) }

        let mesh = try MajorVesselTubeMeshBuilder.build(
            pointsASRMicrometres: points,
            radiiMicrometres: radii,
            runOffsets: runOffsets
        )

        #expect(points.count == pointCount)
        #expect(runOffsets.count - 1 == runCount)
        #expect(mesh.vertexCount == pointCount * MajorVesselTubeMeshBuilder.sideCount)
        #expect(
            mesh.triangleCount
                == segmentCount * MajorVesselTubeMeshBuilder.sideCount * 2
        )
        #expect(
            mesh.vertexData.count + mesh.normalData.count + mesh.indexData.count
                == pointCount * MajorVesselTubeMeshBuilder.sideCount
                    * MemoryLayout<Float>.size * 3 * 2
                    + segmentCount * MajorVesselTubeMeshBuilder.sideCount
                    * 6 * MemoryLayout<UInt32>.size
        )
        #expect(
            mesh.vertexData.count + mesh.normalData.count + mesh.indexData.count
                < 48 * 1_024 * 1_024
        )
    }

    private func vector(from data: Data, at index: Int) -> SIMD3<Float> {
        let byteOffset = index * 3 * MemoryLayout<Float>.size
        return data.withUnsafeBytes { bytes in
            SIMD3(
                bytes.loadUnaligned(fromByteOffset: byteOffset, as: Float.self),
                bytes.loadUnaligned(
                    fromByteOffset: byteOffset + MemoryLayout<Float>.size,
                    as: Float.self
                ),
                bytes.loadUnaligned(
                    fromByteOffset: byteOffset + 2 * MemoryLayout<Float>.size,
                    as: Float.self
                )
            )
        }
    }

    private func uint32Values(_ data: Data) -> [UInt32] {
        stride(from: 0, to: data.count, by: MemoryLayout<UInt32>.size).map { offset in
            data.withUnsafeBytes { bytes in
                bytes.loadUnaligned(fromByteOffset: offset, as: UInt32.self)
            }
        }
    }
}
