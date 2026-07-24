import Brain3DCore
import Testing

@Suite("Exact probe slice overlays")
struct ProbeSliceOverlayGeometryTests {
    private let resolution = try! AtlasASRResolution(
        apMicrometres: 25,
        dvMicrometres: 25,
        mlMicrometres: 25
    )
    private let shape = try! AtlasASRShape(apVoxels: 8, dvVoxels: 8, mlVoxels: 8)

    @Test("Markers use the current half-open slice slab without projection")
    func markerSlab() {
        let overlay = ProbeSliceOverlayGeometry.make(
            orientation: .coronal,
            sliceIndex: 1,
            resolution: resolution,
            shape: shape,
            entry: point(ap: 25, dv: 37.5, ml: 62.5),
            target: point(ap: 50, dv: 37.5, ml: 62.5),
            tip: point(ap: 49.999, dv: 50, ml: 75),
            shanks: [],
            recordingSites: [
                ProbeRecordingSite(
                    shankId: "s1",
                    siteId: "inside",
                    role: "recording",
                    point: point(ap: 40, dv: 75, ml: 100)
                ),
                ProbeRecordingSite(
                    shankId: "s1",
                    siteId: "outside-flag",
                    role: "recording",
                    point: point(ap: 40, dv: 75, ml: 100, inside: false)
                ),
            ]
        )
        #expect(overlay.markers.map(\.id) == [
            "placement-entry", "placement-tip", "site:s1:inside",
        ])
        #expect(overlay.markers[0].imagePoint.column == 2.5)
        #expect(overlay.markers[0].imagePoint.row == 1.5)
    }

    @Test("Each view maps its own fixed, row, and column axes")
    func orientationMapping() {
        let physical = point(ap: 37.5, dv: 62.5, ml: 87.5)
        let coronal = overlay(orientation: .coronal, index: 1, marker: physical)
        #expect(coronal.markers[0].imagePoint == .init(column: 3.5, row: 2.5))

        let sagittal = overlay(orientation: .sagittal, index: 3, marker: physical)
        #expect(sagittal.markers[0].imagePoint == .init(column: 1.5, row: 2.5))

        let horizontal = overlay(orientation: .horizontal, index: 2, marker: physical)
        #expect(horizontal.markers[0].imagePoint == .init(column: 3.5, row: 1.5))
    }

    @Test("A crossing shank produces only its centerline-plane intersection")
    func crossingIntersection() {
        let shank = ProbePlacedShank(
            shankId: "s1",
            entry: point(ap: 0, dv: 25, ml: 25),
            tip: point(ap: 100, dv: 125, ml: 75),
            widthMicrometres: 70,
            thicknessMicrometres: 20,
            conservativeEnvelopeRadiusMicrometres: 36.4,
            envelopeDefinition: "conservative radius"
        )
        let overlay = ProbeSliceOverlayGeometry.make(
            orientation: .coronal,
            sliceIndex: 1,
            resolution: resolution,
            shape: shape,
            entry: outsidePoint,
            target: outsidePoint,
            tip: outsidePoint,
            shanks: [shank],
            recordingSites: []
        )
        #expect(overlay.shankIntersections.count == 1)
        guard case let .point(point) = overlay.shankIntersections[0].geometry else {
            Issue.record("A non-coplanar crossing must be a single point")
            return
        }
        #expect(abs(point.column - 1.75) < 1e-12)
        #expect(abs(point.row - 2.5) < 1e-12)

        let unrelated = ProbeSliceOverlayGeometry.make(
            orientation: .coronal,
            sliceIndex: 5,
            resolution: resolution,
            shape: shape,
            entry: outsidePoint,
            target: outsidePoint,
            tip: outsidePoint,
            shanks: [shank],
            recordingSites: []
        )
        #expect(unrelated.shankIntersections.isEmpty)
        #expect(unrelated.markers.isEmpty)
    }

    @Test("A centerline lying in the plane is clipped to the image, not projected elsewhere")
    func coplanarIntersection() {
        let shank = ProbePlacedShank(
            shankId: "s1",
            entry: point(ap: 37.5, dv: -25, ml: -25),
            tip: point(ap: 37.5, dv: 250, ml: 250),
            widthMicrometres: 70,
            thicknessMicrometres: 20,
            conservativeEnvelopeRadiusMicrometres: 36.4,
            envelopeDefinition: "conservative radius"
        )
        let current = ProbeSliceOverlayGeometry.make(
            orientation: .coronal,
            sliceIndex: 1,
            resolution: resolution,
            shape: shape,
            entry: outsidePoint,
            target: outsidePoint,
            tip: outsidePoint,
            shanks: [shank],
            recordingSites: []
        )
        guard case let .segment(start, end) = current.shankIntersections[0].geometry else {
            Issue.record("A coplanar centerline must remain a clipped segment")
            return
        }
        #expect(start.column == 0)
        #expect(start.row == 0)
        #expect(end.column < 8)
        #expect(end.row < 8)

        let otherSlice = ProbeSliceOverlayGeometry.make(
            orientation: .coronal,
            sliceIndex: 2,
            resolution: resolution,
            shape: shape,
            entry: outsidePoint,
            target: outsidePoint,
            tip: outsidePoint,
            shanks: [shank],
            recordingSites: []
        )
        #expect(otherSlice.shankIntersections.isEmpty)
    }

    @Test("Dorsal keeps every shank readable without a depth-collapsed site cloud")
    func dorsalProjection() {
        let diagonalShank = ProbePlacedShank(
            shankId: "s1",
            entry: point(ap: -25, dv: -500, ml: -25, inside: false),
            tip: point(ap: 250, dv: 500, ml: 250, inside: false),
            widthMicrometres: 70,
            thicknessMicrometres: 20,
            conservativeEnvelopeRadiusMicrometres: 36.4,
            envelopeDefinition: "conservative radius"
        )
        let depthOnlyShank = ProbePlacedShank(
            shankId: "s2",
            entry: point(ap: 50, dv: -500, ml: 125, inside: false),
            tip: point(ap: 50, dv: 5_000, ml: 125, inside: false),
            widthMicrometres: 70,
            thicknessMicrometres: 20,
            conservativeEnvelopeRadiusMicrometres: 36.4,
            envelopeDefinition: "conservative radius"
        )
        let overlay = ProbeSliceOverlayGeometry.makeDorsalProjection(
            resolution: resolution,
            shape: shape,
            entry: point(ap: 25, dv: -100, ml: 50, inside: false),
            target: point(ap: 50, dv: 100, ml: 75),
            tip: point(ap: 75, dv: 500, ml: 100, inside: false),
            shanks: [diagonalShank, depthOnlyShank],
            recordingSites: (0 ..< 960).map { index in
                ProbeRecordingSite(
                    shankId: index.isMultiple(of: 2) ? "s1" : "s2",
                    siteId: "site-\(index)",
                    role: "recording",
                    point: point(
                        ap: 50,
                        dv: Double(index) * 10,
                        ml: 75,
                        inside: false
                    )
                )
            }
        )
        #expect(overlay.orientation == .horizontal)
        #expect(overlay.markers.map(\.id) == [
            "placement-entry", "placement-target", "placement-tip",
        ])
        #expect(!overlay.markers.contains(where: { $0.role == .recordingSite }))
        #expect(overlay.shankIntersections.count == 2)
        #expect(overlay.markers[0].imagePoint == .init(column: 2, row: 1))
        guard case let .segment(start, end) = overlay.shankIntersections[0].geometry else {
            Issue.record("A nonvertical Dorsal probe must remain a clipped AP/ML segment")
            return
        }
        #expect(start == .init(column: 0, row: 0))
        #expect(end.column < 8)
        #expect(end.row < 8)
        guard case let .point(depthOnlyPoint) = overlay.shankIntersections[1].geometry else {
            Issue.record("A depth-only Dorsal probe must remain a visible AP/ML point")
            return
        }
        #expect(depthOnlyPoint == .init(column: 5, row: 2))
    }

    @Test("Negative bregma AP and ML move toward P and the screen-right L side")
    func negativeBregmaScreenDirections() throws {
        // In BrainGlobe physical ASR, posterior and animal-left are the
        // increasing AP and ML axes. This pair represents a target posterior
        // and left of an aligned bregma point at this compact test scale.
        let bregma = point(ap: 75, dv: 50, ml: 100)
        let negativeTarget = point(ap: 125, dv: 50, ml: 150)

        let bregmaDorsal = ProbeSliceOverlayGeometry.makeImplantSiteDorsalProjection(
            targetId: "bregma",
            label: "Bregma",
            point: bregma,
            resolution: resolution,
            shape: shape
        )
        let targetDorsal = ProbeSliceOverlayGeometry.makeImplantSiteDorsalProjection(
            targetId: "negative",
            label: "AP− / ML−",
            point: negativeTarget,
            resolution: resolution,
            shape: shape
        )
        let bregmaPoint = try #require(bregmaDorsal.markers.first?.imagePoint)
        let targetPoint = try #require(targetDorsal.markers.first?.imagePoint)
        #expect(targetPoint.row > bregmaPoint.row)
        #expect(targetPoint.column > bregmaPoint.column)
        #expect(targetPoint.column > Double(shape.mlVoxels) / 2)
        #expect(targetDorsal.markers.first?.role == .implantSite)

        let horizontalBregma = ProbeSliceOverlayGeometry.makeImplantSite(
            targetId: "bregma",
            label: "Bregma",
            point: bregma,
            orientation: .horizontal,
            sliceIndex: 2,
            resolution: resolution,
            shape: shape
        )
        let horizontalTarget = ProbeSliceOverlayGeometry.makeImplantSite(
            targetId: "negative",
            label: "AP− / ML−",
            point: negativeTarget,
            orientation: .horizontal,
            sliceIndex: 2,
            resolution: resolution,
            shape: shape
        )
        let horizontalBregmaPoint = try #require(
            horizontalBregma.markers.first?.imagePoint
        )
        let horizontalTargetPoint = try #require(
            horizontalTarget.markers.first?.imagePoint
        )
        #expect(horizontalTargetPoint.row > horizontalBregmaPoint.row)
        #expect(horizontalTargetPoint.column > horizontalBregmaPoint.column)

        let coronalTarget = ProbeSliceOverlayGeometry.makeImplantSite(
            targetId: "negative",
            label: "AP− / ML−",
            point: negativeTarget,
            orientation: .coronal,
            sliceIndex: 5,
            resolution: resolution,
            shape: shape
        )
        #expect(coronalTarget.markers.first?.imagePoint.column == 6)

        let sagittalTarget = ProbeSliceOverlayGeometry.makeImplantSite(
            targetId: "negative",
            label: "AP− / ML−",
            point: negativeTarget,
            orientation: .sagittal,
            sliceIndex: 6,
            resolution: resolution,
            shape: shape
        )
        #expect(sagittalTarget.markers.first?.imagePoint.column == 5)
    }

    @Test("Continuous image coordinates map through the viewport with half-open edges")
    func viewportContinuousMapping() throws {
        let viewport = AtlasSliceViewport(
            bounds: .init(x: 0, y: 0, width: 216, height: 116),
            imagePixelWidth: 4,
            imagePixelHeight: 2,
            zoom: 1,
            pan: .zero,
            contentInset: 8
        )
        let point = try #require(viewport.pointForImageCoordinate(column: 0.5, row: 0.5))
        #expect(point == viewport.pointForPixelCenter(column: 0, row: 0))
        #expect(viewport.pointForImageCoordinate(column: 4, row: 1) == nil)
        #expect(viewport.pointForImageCoordinate(column: 1, row: 2) == nil)
        #expect(viewport.pointForImageCoordinate(column: -0.001, row: 1) == nil)
    }

    private func overlay(
        orientation: AtlasSliceOrientation,
        index: Int,
        marker: ProbePhysicalPoint
    ) -> ProbeSliceOverlay {
        ProbeSliceOverlayGeometry.make(
            orientation: orientation,
            sliceIndex: index,
            resolution: resolution,
            shape: shape,
            entry: marker,
            target: outsidePoint,
            tip: outsidePoint,
            shanks: [],
            recordingSites: []
        )
    }

    private var outsidePoint: ProbePhysicalPoint {
        point(ap: -1, dv: -1, ml: -1, inside: false)
    }

    private func point(
        ap: Double,
        dv: Double,
        ml: Double,
        inside: Bool = true
    ) -> ProbePhysicalPoint {
        ProbePhysicalPoint(
            apMicrometres: ap,
            dvMicrometres: dv,
            mlMicrometres: ml,
            insideAtlas: inside,
            voxelIndex: inside ? ProbeVoxelIndex(ap: 0, dv: 0, ml: 0) : nil
        )
    }
}
