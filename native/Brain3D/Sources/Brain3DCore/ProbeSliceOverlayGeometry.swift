import Foundation

public extension ProbePhysicalPoint {
    init(calibratedTargetProjection projection: CalibratedTargetProjectionResult) {
        self.init(
            apMicrometres: projection.atlasPoint.apMicrometres,
            dvMicrometres: projection.atlasPoint.dvMicrometres,
            mlMicrometres: projection.atlasPoint.mlMicrometres,
            insideAtlas: true,
            voxelIndex: ProbeVoxelIndex(
                ap: projection.containingVoxelIndex.ap,
                dv: projection.containingVoxelIndex.dv,
                ml: projection.containingVoxelIndex.ml
            )
        )
    }
}

public enum ProbeSliceMarkerRole: String, Equatable, Sendable {
    case entry
    case implantSite
    case target
    case tip
    case recordingSite
}

public struct ProbeSliceImagePoint: Equatable, Sendable {
    public let column: Double
    public let row: Double

    public init(column: Double, row: Double) {
        self.column = column
        self.row = row
    }
}

public struct ProbeSliceMarker: Equatable, Identifiable, Sendable {
    public let id: String
    public let role: ProbeSliceMarkerRole
    public let label: String
    public let imagePoint: ProbeSliceImagePoint

    public init(
        id: String,
        role: ProbeSliceMarkerRole,
        label: String,
        imagePoint: ProbeSliceImagePoint
    ) {
        self.id = id
        self.role = role
        self.label = label
        self.imagePoint = imagePoint
    }
}

public enum ProbeShankSliceIntersectionGeometry: Equatable, Sendable {
    case point(ProbeSliceImagePoint)
    case segment(start: ProbeSliceImagePoint, end: ProbeSliceImagePoint)
}

public struct ProbeShankSliceIntersection: Equatable, Identifiable, Sendable {
    public let shankId: String
    public let geometry: ProbeShankSliceIntersectionGeometry

    public init(shankId: String, geometry: ProbeShankSliceIntersectionGeometry) {
        self.shankId = shankId
        self.geometry = geometry
    }

    public var id: String { shankId }
}

public struct ProbeSliceOverlay: Equatable, Sendable {
    public let orientation: AtlasSliceOrientation
    public let sliceIndex: Int
    public let markers: [ProbeSliceMarker]
    public let shankIntersections: [ProbeShankSliceIntersection]

    public init(
        orientation: AtlasSliceOrientation,
        sliceIndex: Int,
        markers: [ProbeSliceMarker],
        shankIntersections: [ProbeShankSliceIntersection]
    ) {
        self.orientation = orientation
        self.sliceIndex = sliceIndex
        self.markers = markers
        self.shankIntersections = shankIntersections
    }
}

public enum ProbeSliceOverlayGeometry {
    /// Make the currently displayed implant site visible without requiring a
    /// probe plan. BrainGlobe physical AP/ML increase toward posterior/left,
    /// so these unflipped image coordinates place posterior at the bottom and
    /// animal-left at the screen-right edge of the labelled atlas canvas.
    public static func makeImplantSiteDorsalProjection(
        targetId: String,
        label: String,
        point: ProbePhysicalPoint,
        resolution: AtlasASRResolution,
        shape: AtlasASRShape
    ) -> ProbeSliceOverlay {
        let marker = dorsalImagePoint(
            point,
            resolution: resolution,
            shape: shape
        ).map {
            ProbeSliceMarker(
                id: "implant-site:\(targetId)",
                role: .implantSite,
                label: label,
                imagePoint: $0
            )
        }
        return ProbeSliceOverlay(
            orientation: .horizontal,
            sliceIndex: 0,
            markers: marker.map { [$0] } ?? [],
            shankIntersections: []
        )
    }

    public static func makeImplantSite(
        targetId: String,
        label: String,
        point: ProbePhysicalPoint,
        orientation: AtlasSliceOrientation,
        sliceIndex: Int,
        resolution: AtlasASRResolution,
        shape: AtlasASRShape
    ) -> ProbeSliceOverlay {
        let sliceCount = shape[orientation.fixedAxis]
        guard sliceIndex >= 0, sliceIndex < sliceCount else {
            return ProbeSliceOverlay(
                orientation: orientation,
                sliceIndex: sliceIndex,
                markers: [],
                shankIntersections: []
            )
        }
        let slab = Double(sliceIndex) * resolution[orientation.fixedAxis]
            ..< Double(sliceIndex + 1) * resolution[orientation.fixedAxis]
        var markers: [ProbeSliceMarker] = []
        appendMarker(
            point: point,
            id: "implant-site:\(targetId)",
            role: .implantSite,
            label: label,
            orientation: orientation,
            slab: slab,
            resolution: resolution,
            shape: shape,
            into: &markers
        )
        return ProbeSliceOverlay(
            orientation: orientation,
            sliceIndex: sliceIndex,
            markers: markers,
            shankIntersections: []
        )
    }

    public static func combine(
        _ overlays: [ProbeSliceOverlay?],
        orientation: AtlasSliceOrientation,
        sliceIndex: Int
    ) -> ProbeSliceOverlay? {
        let present = overlays.compactMap { $0 }
        guard !present.isEmpty,
              present.allSatisfy({
                  $0.orientation == orientation && $0.sliceIndex == sliceIndex
              })
        else { return nil }

        var markerIds = Set<String>()
        var shankIds = Set<String>()
        return ProbeSliceOverlay(
            orientation: orientation,
            sliceIndex: sliceIndex,
            markers: present
                .flatMap(\.markers)
                .filter { markerIds.insert($0.id).inserted },
            shankIntersections: present
                .flatMap(\.shankIntersections)
                .filter { shankIds.insert($0.shankId).inserted }
        )
    }

    public static func makeDorsalProjection(
        plan: ProbePlanDetail,
        resolution: AtlasASRResolution,
        shape: AtlasASRShape
    ) -> ProbeSliceOverlay? {
        guard plan.hasCurrentPlanningGeometry else { return nil }
        return makeDorsalProjection(
            resolution: resolution,
            shape: shape,
            entry: plan.placement.atlasFrame.entry,
            target: plan.placement.atlasFrame.target,
            tip: plan.placement.atlasFrame.tip,
            shanks: plan.shanks,
            recordingSites: plan.recordingSites
        )
    }

    public static func makeDorsalProjection(
        resolution: AtlasASRResolution,
        shape: AtlasASRShape,
        entry: ProbePhysicalPoint,
        target: ProbePhysicalPoint,
        tip: ProbePhysicalPoint,
        shanks: [ProbePlacedShank],
        recordingSites _: [ProbeRecordingSite]
    ) -> ProbeSliceOverlay {
        var markers: [ProbeSliceMarker] = []
        for (point, id, role, label) in [
            (entry, "placement-entry", ProbeSliceMarkerRole.entry, "Entry"),
            (target, "placement-target", ProbeSliceMarkerRole.target, "Target"),
            (tip, "placement-tip", ProbeSliceMarkerRole.tip, "Tip"),
        ] {
            if let imagePoint = dorsalImagePoint(
                point,
                resolution: resolution,
                shape: shape
            ) {
                markers.append(
                    ProbeSliceMarker(id: id, role: role, label: label, imagePoint: imagePoint)
                )
            }
        }
        // A Dorsal AP/ML projection discards DV. Rendering hundreds of recording
        // sites after that collapse creates an opaque point cloud and implies false
        // site separation. Site markers remain available in the true depth slices;
        // Dorsal intentionally preserves only landmarks and every shank centerline.

        let width = Double(shape[.ml])
        let height = Double(shape[.ap])
        let shankProjections = shanks.compactMap { shank -> ProbeShankSliceIntersection? in
            guard let start = dorsalUnboundedImagePoint(
                shank.renderedProximalEnd,
                resolution: resolution
            ),
                  let end = dorsalUnboundedImagePoint(shank.tip, resolution: resolution)
            else { return nil }
            let distance = hypot(end.column - start.column, end.row - start.row)
            if distance <= 1e-9 {
                guard start.column >= 0, start.column < width,
                      start.row >= 0, start.row < height
                else { return nil }
                return ProbeShankSliceIntersection(
                    shankId: shank.shankId,
                    geometry: .point(start)
                )
            }
            guard let clipped = clip(start: start, end: end, width: width, height: height)
            else { return nil }
            return ProbeShankSliceIntersection(
                shankId: shank.shankId,
                geometry: .segment(start: clipped.start, end: clipped.end)
            )
        }
        return ProbeSliceOverlay(
            orientation: .horizontal,
            sliceIndex: 0,
            markers: markers,
            shankIntersections: shankProjections
        )
    }

    public static func make(
        plan: ProbePlanDetail,
        orientation: AtlasSliceOrientation,
        sliceIndex: Int,
        resolution: AtlasASRResolution,
        shape: AtlasASRShape
    ) -> ProbeSliceOverlay? {
        guard plan.hasCurrentPlanningGeometry else { return nil }
        return make(
            orientation: orientation,
            sliceIndex: sliceIndex,
            resolution: resolution,
            shape: shape,
            entry: plan.placement.atlasFrame.entry,
            target: plan.placement.atlasFrame.target,
            tip: plan.placement.atlasFrame.tip,
            shanks: plan.shanks,
            recordingSites: plan.recordingSites
        )
    }

    public static func make(
        orientation: AtlasSliceOrientation,
        sliceIndex: Int,
        resolution: AtlasASRResolution,
        shape: AtlasASRShape,
        entry: ProbePhysicalPoint,
        target: ProbePhysicalPoint,
        tip: ProbePhysicalPoint,
        shanks: [ProbePlacedShank],
        recordingSites: [ProbeRecordingSite]
    ) -> ProbeSliceOverlay {
        let fixedAxis = orientation.fixedAxis
        let sliceCount = shape[fixedAxis]
        guard sliceIndex >= 0, sliceIndex < sliceCount else {
            return ProbeSliceOverlay(
                orientation: orientation,
                sliceIndex: sliceIndex,
                markers: [],
                shankIntersections: []
            )
        }
        let slabMinimum = Double(sliceIndex) * resolution[fixedAxis]
        let slabMaximum = Double(sliceIndex + 1) * resolution[fixedAxis]
        let plane = (slabMinimum + slabMaximum) / 2

        var markers: [ProbeSliceMarker] = []
        appendMarker(
            point: entry,
            id: "placement-entry",
            role: .entry,
            label: "Entry",
            orientation: orientation,
            slab: slabMinimum ..< slabMaximum,
            resolution: resolution,
            shape: shape,
            into: &markers
        )
        appendMarker(
            point: target,
            id: "placement-target",
            role: .target,
            label: "Target",
            orientation: orientation,
            slab: slabMinimum ..< slabMaximum,
            resolution: resolution,
            shape: shape,
            into: &markers
        )
        appendMarker(
            point: tip,
            id: "placement-tip",
            role: .tip,
            label: "Tip",
            orientation: orientation,
            slab: slabMinimum ..< slabMaximum,
            resolution: resolution,
            shape: shape,
            into: &markers
        )
        for site in recordingSites {
            appendMarker(
                point: site.point,
                id: "site:\(site.shankId):\(site.siteId)",
                role: .recordingSite,
                label: site.siteId,
                orientation: orientation,
                slab: slabMinimum ..< slabMaximum,
                resolution: resolution,
                shape: shape,
                into: &markers
            )
        }

        let intersections = shanks.compactMap { shank in
            intersection(
                shank: shank,
                orientation: orientation,
                plane: plane,
                resolution: resolution,
                shape: shape
            )
        }
        return ProbeSliceOverlay(
            orientation: orientation,
            sliceIndex: sliceIndex,
            markers: markers,
            shankIntersections: intersections
        )
    }

    private static func appendMarker(
        point: ProbePhysicalPoint,
        id: String,
        role: ProbeSliceMarkerRole,
        label: String,
        orientation: AtlasSliceOrientation,
        slab: Range<Double>,
        resolution: AtlasASRResolution,
        shape: AtlasASRShape,
        into markers: inout [ProbeSliceMarker]
    ) {
        guard point.insideAtlas,
              slab.contains(point[orientation.fixedAxis]),
              let imagePoint = imagePoint(
                  point,
                  orientation: orientation,
                  resolution: resolution,
                  shape: shape
              )
        else { return }
        markers.append(ProbeSliceMarker(id: id, role: role, label: label, imagePoint: imagePoint))
    }

    private static func intersection(
        shank: ProbePlacedShank,
        orientation: AtlasSliceOrientation,
        plane: Double,
        resolution: AtlasASRResolution,
        shape: AtlasASRShape
    ) -> ProbeShankSliceIntersection? {
        let fixedAxis = orientation.fixedAxis
        let proximalEnd = shank.renderedProximalEnd
        let aFixed = proximalEnd[fixedAxis]
        let bFixed = shank.tip[fixedAxis]
        let delta = bFixed - aFixed
        let scale = [1, abs(aFixed), abs(bFixed), abs(plane)].max() ?? 1
        let epsilon = 1e-9 * scale
        if abs(delta) <= epsilon {
            guard abs(aFixed - plane) <= epsilon,
                  let start = unboundedImagePoint(
                      proximalEnd,
                      orientation: orientation,
                      resolution: resolution
                  ),
                  let end = unboundedImagePoint(
                      shank.tip,
                      orientation: orientation,
                      resolution: resolution
                  ),
                  let clipped = clip(
                      start: start,
                      end: end,
                      width: Double(shape[orientation.columnAxis]),
                      height: Double(shape[orientation.rowAxis])
                  )
            else { return nil }
            return ProbeShankSliceIntersection(
                shankId: shank.shankId,
                geometry: .segment(start: clipped.start, end: clipped.end)
            )
        }

        let t = (plane - aFixed) / delta
        guard t.isFinite, t >= 0, t <= 1 else { return nil }
        let point = ProbePhysicalPoint(
            apMicrometres: interpolate(
                proximalEnd.apMicrometres,
                shank.tip.apMicrometres,
                t
            ),
            dvMicrometres: interpolate(
                proximalEnd.dvMicrometres,
                shank.tip.dvMicrometres,
                t
            ),
            mlMicrometres: interpolate(
                proximalEnd.mlMicrometres,
                shank.tip.mlMicrometres,
                t
            )
        )
        guard let imagePoint = imagePoint(
            point,
            orientation: orientation,
            resolution: resolution,
            shape: shape
        ) else { return nil }
        return ProbeShankSliceIntersection(
            shankId: shank.shankId,
            geometry: .point(imagePoint)
        )
    }

    private static func imagePoint(
        _ point: ProbePhysicalPoint,
        orientation: AtlasSliceOrientation,
        resolution: AtlasASRResolution,
        shape: AtlasASRShape
    ) -> ProbeSliceImagePoint? {
        guard let candidate = unboundedImagePoint(
            point,
            orientation: orientation,
            resolution: resolution
        ) else { return nil }
        let width = Double(shape[orientation.columnAxis])
        let height = Double(shape[orientation.rowAxis])
        guard candidate.column >= 0, candidate.column < width,
              candidate.row >= 0, candidate.row < height
        else { return nil }
        return candidate
    }

    private static func dorsalImagePoint(
        _ point: ProbePhysicalPoint,
        resolution: AtlasASRResolution,
        shape: AtlasASRShape
    ) -> ProbeSliceImagePoint? {
        guard let candidate = dorsalUnboundedImagePoint(point, resolution: resolution),
              candidate.column >= 0,
              candidate.column < Double(shape[.ml]),
              candidate.row >= 0,
              candidate.row < Double(shape[.ap])
        else { return nil }
        return candidate
    }

    private static func dorsalUnboundedImagePoint(
        _ point: ProbePhysicalPoint,
        resolution: AtlasASRResolution
    ) -> ProbeSliceImagePoint? {
        let column = point.mlMicrometres / resolution[.ml]
        let row = point.apMicrometres / resolution[.ap]
        guard column.isFinite, row.isFinite else { return nil }
        return ProbeSliceImagePoint(column: column, row: row)
    }

    private static func unboundedImagePoint(
        _ point: ProbePhysicalPoint,
        orientation: AtlasSliceOrientation,
        resolution: AtlasASRResolution
    ) -> ProbeSliceImagePoint? {
        let column = point[orientation.columnAxis] / resolution[orientation.columnAxis]
        let row = point[orientation.rowAxis] / resolution[orientation.rowAxis]
        guard column.isFinite, row.isFinite else { return nil }
        return ProbeSliceImagePoint(column: column, row: row)
    }

    private static func interpolate(_ a: Double, _ b: Double, _ t: Double) -> Double {
        a + (b - a) * t
    }

    /// Liang-Barsky line clipping against the exact half-open atlas image extent.
    private static func clip(
        start: ProbeSliceImagePoint,
        end: ProbeSliceImagePoint,
        width: Double,
        height: Double
    ) -> (start: ProbeSliceImagePoint, end: ProbeSliceImagePoint)? {
        guard width.isFinite, height.isFinite, width > 0, height > 0 else { return nil }
        let maxX = width.nextDown
        let maxY = height.nextDown
        let dx = end.column - start.column
        let dy = end.row - start.row
        var lower = 0.0
        var upper = 1.0
        for (p, q) in [
            (-dx, start.column),
            (dx, maxX - start.column),
            (-dy, start.row),
            (dy, maxY - start.row),
        ] {
            if p == 0 {
                if q < 0 { return nil }
            } else {
                let ratio = q / p
                if p < 0 {
                    lower = max(lower, ratio)
                } else {
                    upper = min(upper, ratio)
                }
                if lower > upper { return nil }
            }
        }
        func clippedPoint(_ t: Double) -> ProbeSliceImagePoint {
            ProbeSliceImagePoint(
                column: min(maxX, max(0, start.column + t * dx)),
                row: min(maxY, max(0, start.row + t * dy))
            )
        }
        return (clippedPoint(lower), clippedPoint(upper))
    }
}
