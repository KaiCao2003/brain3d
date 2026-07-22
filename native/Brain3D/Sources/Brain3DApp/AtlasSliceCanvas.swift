import AppKit
import Brain3DCore
import SwiftUI

struct AtlasSliceSelection {
    let column: Int
    let row: Int
    let acronym: String
    let name: String
    let color: NSColor
}

/// AppKit-backed scientific image viewport.
///
/// The view owns display-only pan and zoom state. Pixel picks are returned to
/// the caller; the Python bridge remains the only authority that maps those
/// pixels into atlas coordinates.
struct AtlasSliceCanvas: NSViewRepresentable {
    let imageData: Data?
    let imagePixelWidth: Int
    let imagePixelHeight: Int
    let viewportIdentity: String
    let selection: AtlasSliceSelection?
    let majorVesselOverlay: MajorVesselSliceOverlay?
    let probeOverlay: ProbeSliceOverlay?
    let interactionHelp: String
    let accessibilityLabel: String
    let accessibilityValue: String
    let resetGeneration: Int
    let onPick: (_ column: Int, _ row: Int) -> Void
    let onSliceStep: (_ delta: Int) -> Void

    func makeNSView(context: Context) -> AtlasSliceNSView {
        let view = AtlasSliceNSView()
        update(view)
        return view
    }

    func updateNSView(_ nsView: AtlasSliceNSView, context: Context) {
        update(nsView)
    }

    private func update(_ view: AtlasSliceNSView) {
        view.configure(
            imageData: imageData,
            imagePixelWidth: imagePixelWidth,
            imagePixelHeight: imagePixelHeight,
            viewportIdentity: viewportIdentity,
            selection: selection,
            majorVesselOverlay: majorVesselOverlay,
            probeOverlay: probeOverlay,
            interactionHelp: interactionHelp,
            accessibilityLabel: accessibilityLabel,
            accessibilityValue: accessibilityValue,
            resetGeneration: resetGeneration,
            onPick: onPick,
            onSliceStep: onSliceStep
        )
    }
}

@MainActor
final class AtlasSliceNSView: NSView {
    private static let minimumZoom: CGFloat = 1.0
    private static let maximumZoom: CGFloat = 12.0
    private static let dragThreshold: CGFloat = 4.0
    // The core still scales from the measured vessel diameter. These lower
    // bounds and the achromatic halo are display aids only: they keep a real
    // subpixel intersection visible without changing path coordinates or
    // source radius data.
    private static let minimumVesselCoreWidth: CGFloat = 2.25
    private static let minimumVesselPointDiameter: CGFloat = 3.25
    private static let vesselHaloExpansion: CGFloat = 3.0
    private static let vesselCoreColor = NSColor(
        calibratedWhite: 0.98,
        alpha: 0.98
    )
    private static let vesselHaloColor = NSColor.black.withAlphaComponent(0.88)

    private var imageData: Data?
    private var image: NSImage?
    private var imagePixelWidth = 0
    private var imagePixelHeight = 0
    private var selection: AtlasSliceSelection?
    private var majorVesselOverlay: MajorVesselSliceOverlay?
    private var probeOverlay: ProbeSliceOverlay?
    private var lastViewportIdentity: String?
    private var lastPositiveImagePixelSize: (width: Int, height: Int)?
    private var pickHandler: ((Int, Int) -> Void)?
    private var sliceStepHandler: ((Int) -> Void)?

    private var zoom: CGFloat = 1.0
    private var pan = CGPoint.zero
    private var mouseDownPoint: CGPoint?
    private var mouseDownPan = CGPoint.zero
    private var isPanning = false
    private var scrollAccumulator = AtlasSliceScrollAccumulator()
    private var lastResetGeneration = 0

    private var viewport: AtlasSliceViewport {
        AtlasSliceViewport(
            bounds: bounds,
            imagePixelWidth: imagePixelWidth,
            imagePixelHeight: imagePixelHeight,
            zoom: zoom,
            pan: pan
        )
    }

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.black.cgColor
        setAccessibilityElement(true)
        setAccessibilityRole(.image)
        setAccessibilityHelp(
            "Click to identify a brain region. Drag to pan, pinch to zoom, and scroll to change slices."
        )
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not supported")
    }

    func configure(
        imageData: Data?,
        imagePixelWidth: Int,
        imagePixelHeight: Int,
        viewportIdentity: String,
        selection: AtlasSliceSelection?,
        majorVesselOverlay: MajorVesselSliceOverlay?,
        probeOverlay: ProbeSliceOverlay?,
        interactionHelp: String,
        accessibilityLabel: String,
        accessibilityValue: String,
        resetGeneration: Int,
        onPick: @escaping (Int, Int) -> Void,
        onSliceStep: @escaping (Int) -> Void
    ) {
        if let previousIdentity = lastViewportIdentity, previousIdentity != viewportIdentity {
            resetViewport()
        }
        lastViewportIdentity = viewportIdentity
        let sanitizedWidth = max(0, imagePixelWidth)
        let sanitizedHeight = max(0, imagePixelHeight)
        if sanitizedWidth > 0, sanitizedHeight > 0 {
            if let previous = lastPositiveImagePixelSize,
               previous.width != sanitizedWidth || previous.height != sanitizedHeight
            {
                resetViewport()
            }
            lastPositiveImagePixelSize = (sanitizedWidth, sanitizedHeight)
        }
        if self.imageData != imageData {
            self.imageData = imageData
            image = imageData.flatMap(NSImage.init(data:))
        }
        self.imagePixelWidth = sanitizedWidth
        self.imagePixelHeight = sanitizedHeight
        self.selection = selection
        self.majorVesselOverlay = majorVesselOverlay
        self.probeOverlay = probeOverlay
        pickHandler = onPick
        sliceStepHandler = onSliceStep
        setAccessibilityLabel(accessibilityLabel)
        setAccessibilityValue(accessibilityValue)
        setAccessibilityHelp(interactionHelp)
        if resetGeneration != lastResetGeneration {
            lastResetGeneration = resetGeneration
            resetViewport()
        }
        needsDisplay = true
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        NSColor.black.setFill()
        dirtyRect.fill()

        guard let image, let rect = viewport.displayedImageRect else {
            drawPlaceholder()
            return
        }

        let context = NSGraphicsContext.current
        let previousInterpolation = context?.imageInterpolation
        context?.imageInterpolation = .none
        image.draw(
            in: rect,
            from: .zero,
            operation: .copy,
            fraction: 1,
            respectFlipped: true,
            hints: nil
        )
        context?.imageInterpolation = previousInterpolation ?? .default
        drawMajorVesselsIfPresent()
        drawProbeOverlayIfPresent()
        drawSelectionIfPresent()
    }

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        mouseDownPoint = convert(event.locationInWindow, from: nil)
        mouseDownPan = pan
        isPanning = false
    }

    override func mouseDragged(with event: NSEvent) {
        guard let origin = mouseDownPoint else { return }
        let point = convert(event.locationInWindow, from: nil)
        let delta = CGPoint(x: point.x - origin.x, y: point.y - origin.y)
        if !isPanning,
           AtlasSlicePointerIntent.isDrag(
               from: origin,
               to: point,
               threshold: Self.dragThreshold
           )
        {
            isPanning = true
        }
        guard isPanning else { return }
        pan = viewport.clampedPan(
            CGPoint(x: mouseDownPan.x + delta.x, y: mouseDownPan.y + delta.y)
        )
        needsDisplay = true
    }

    override func mouseUp(with event: NSEvent) {
        defer {
            mouseDownPoint = nil
            isPanning = false
        }
        guard !isPanning else { return }
        let point = convert(event.locationInWindow, from: nil)
        if let origin = mouseDownPoint,
           AtlasSlicePointerIntent.isDrag(
               from: origin,
               to: point,
               threshold: Self.dragThreshold
           )
        {
            return
        }
        guard let pixel = viewport.pixel(at: point) else { return }
        pickHandler?(pixel.column, pixel.row)
    }

    override func scrollWheel(with event: NSEvent) {
        let steps = scrollAccumulator.consume(
            deltaY: event.scrollingDeltaY,
            isPrecise: event.hasPreciseScrollingDeltas,
            isMomentum: !event.momentumPhase.isEmpty,
            phase: scrollPhase(for: event.phase),
            timestamp: event.timestamp
        )
        guard steps != 0 else { return }
        sliceStepHandler?(steps)
    }

    override func magnify(with event: NSEvent) {
        guard event.magnification.isFinite else { return }
        let anchor = convert(event.locationInWindow, from: nil)
        setZoom(zoom * (1 + event.magnification), around: anchor)
    }

    override func keyDown(with event: NSEvent) {
        let step = event.modifierFlags.contains(.shift) ? 10 : 1
        switch event.keyCode {
        case 123, 125: // Left / down
            sliceStepHandler?(-step)
        case 124, 126: // Right / up
            sliceStepHandler?(step)
        case 24, 69: // + / keypad +
            setZoom(zoom * 1.2, around: CGPoint(x: bounds.midX, y: bounds.midY))
        case 27, 78: // - / keypad -
            setZoom(zoom / 1.2, around: CGPoint(x: bounds.midX, y: bounds.midY))
        case 29 where event.modifierFlags.contains(.command): // Command-0
            resetViewport()
        default:
            super.keyDown(with: event)
        }
    }

    override func accessibilityPerformIncrement() -> Bool {
        sliceStepHandler?(1)
        return true
    }

    override func accessibilityPerformDecrement() -> Bool {
        sliceStepHandler?(-1)
        return true
    }

    override func resizeSubviews(withOldSize oldSize: NSSize) {
        super.resizeSubviews(withOldSize: oldSize)
        pan = viewport.clampedPan(pan)
        needsDisplay = true
    }

    private func resetViewport() {
        zoom = Self.minimumZoom
        pan = .zero
        scrollAccumulator.reset()
        needsDisplay = true
    }

    private func setZoom(_ proposed: CGFloat, around anchor: CGPoint) {
        let updated = viewport.zoomed(
            to: proposed,
            around: anchor,
            allowedZoom: Self.minimumZoom ... Self.maximumZoom
        )
        zoom = updated.zoom
        pan = updated.pan
        needsDisplay = true
    }

    private func scrollPhase(for phase: NSEvent.Phase) -> AtlasSliceScrollPhase {
        if phase.contains(.cancelled) { return .cancelled }
        if phase.contains(.ended) { return .ended }
        if phase.contains(.began) { return .began }
        if phase.contains(.changed) { return .changed }
        return .none
    }

    private func drawPlaceholder() {
        let text = "Waiting for verified atlas slice"
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 13, weight: .medium),
            .foregroundColor: NSColor.secondaryLabelColor,
        ]
        let size = text.size(withAttributes: attributes)
        text.draw(
            at: CGPoint(x: bounds.midX - size.width / 2, y: bounds.midY - size.height / 2),
            withAttributes: attributes
        )
    }

    private func drawSelectionIfPresent() {
        guard
            let selection,
            let anchor = viewport.pointForPixelCenter(
                column: selection.column,
                row: selection.row
            )
        else { return }

        let markerRect = CGRect(x: anchor.x - 4, y: anchor.y - 4, width: 8, height: 8)
        NSColor.black.withAlphaComponent(0.8).setStroke()
        selection.color.setFill()
        let marker = NSBezierPath(ovalIn: markerRect)
        marker.lineWidth = 2
        marker.fill()
        marker.stroke()

        let title = selection.acronym
        let subtitle = selection.name
        let titleAttributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 12, weight: .semibold),
            .foregroundColor: NSColor.white,
        ]
        let subtitleAttributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 11, weight: .regular),
            .foregroundColor: NSColor.white.withAlphaComponent(0.82),
        ]
        let titleSize = title.size(withAttributes: titleAttributes)
        let subtitleSize = subtitle.size(withAttributes: subtitleAttributes)
        let width = min(280, max(titleSize.width, subtitleSize.width) + 18)
        let height: CGFloat = 42
        let available = bounds.insetBy(dx: 8, dy: 8)
        var originX = anchor.x + 12
        if originX + width > available.maxX {
            originX = anchor.x - width - 12
        }
        originX = min(max(available.minX, originX), max(available.minX, available.maxX - width))
        let originY = min(
            max(available.minY, anchor.y - height / 2),
            max(available.minY, available.maxY - height)
        )
        let bubbleRect = CGRect(x: originX, y: originY, width: width, height: height)
        NSColor.black.withAlphaComponent(0.84).setFill()
        NSColor.white.withAlphaComponent(0.16).setStroke()
        let bubble = NSBezierPath(roundedRect: bubbleRect, xRadius: 7, yRadius: 7)
        bubble.lineWidth = 1
        bubble.fill()
        bubble.stroke()
        title.draw(
            at: CGPoint(x: bubbleRect.minX + 9, y: bubbleRect.minY + 5),
            withAttributes: titleAttributes
        )
        subtitle.draw(
            at: CGPoint(x: bubbleRect.minX + 9, y: bubbleRect.minY + 21),
            withAttributes: subtitleAttributes
        )
    }

    private func drawProbeOverlayIfPresent() {
        guard let probeOverlay else { return }

        for intersection in probeOverlay.shankIntersections {
            switch intersection.geometry {
            case let .point(imagePoint):
                guard let point = viewport.pointForImageCoordinate(
                    column: imagePoint.column,
                    row: imagePoint.row
                ) else { continue }
                let outer = NSBezierPath(
                    ovalIn: CGRect(x: point.x - 5, y: point.y - 5, width: 10, height: 10)
                )
                NSColor.black.withAlphaComponent(0.8).setStroke()
                outer.lineWidth = 4
                outer.stroke()
                NSColor.systemOrange.setStroke()
                outer.lineWidth = 2
                outer.stroke()
            case let .segment(start, end):
                guard
                    let startPoint = viewport.pointForImageCoordinate(
                        column: start.column,
                        row: start.row
                    ),
                    let endPoint = viewport.pointForImageCoordinate(
                        column: end.column,
                        row: end.row
                    )
                else { continue }
                let line = NSBezierPath()
                line.move(to: startPoint)
                line.line(to: endPoint)
                line.lineCapStyle = .round
                NSColor.black.withAlphaComponent(0.75).setStroke()
                line.lineWidth = 5
                line.stroke()
                NSColor.systemOrange.setStroke()
                line.lineWidth = 2.5
                line.stroke()
            }
        }

        for marker in probeOverlay.markers where marker.role == .recordingSite {
            guard let point = viewport.pointForImageCoordinate(
                column: marker.imagePoint.column,
                row: marker.imagePoint.row
            ) else { continue }
            let rect = CGRect(x: point.x - 2.5, y: point.y - 2.5, width: 5, height: 5)
            NSColor.black.withAlphaComponent(0.8).setStroke()
            NSColor.systemCyan.setFill()
            let path = NSBezierPath(roundedRect: rect, xRadius: 1, yRadius: 1)
            path.lineWidth = 1.5
            path.fill()
            path.stroke()
        }

        for marker in probeOverlay.markers where marker.role != .recordingSite {
            guard let point = viewport.pointForImageCoordinate(
                column: marker.imagePoint.column,
                row: marker.imagePoint.row
            ) else { continue }
            let path: NSBezierPath
            let color: NSColor
            switch marker.role {
            case .entry:
                path = triangle(at: point, radius: 6, pointsUp: true)
                color = .systemGreen
            case .target:
                path = diamond(at: point, radius: 6)
                color = .systemYellow
            case .tip:
                path = triangle(at: point, radius: 6, pointsUp: false)
                color = .systemRed
            case .recordingSite:
                continue
            }
            NSColor.black.withAlphaComponent(0.85).setStroke()
            color.setFill()
            path.lineWidth = 2
            path.fill()
            path.stroke()
        }
    }

    private func drawMajorVesselsIfPresent() {
        guard let overlay = majorVesselOverlay,
              overlay.inPlaneResolutionMicrometres.isFinite,
              overlay.inPlaneResolutionMicrometres > 0,
              let imageRect = viewport.displayedImageRect,
              imagePixelWidth > 0
        else { return }
        let pointsPerImagePixel = imageRect.width / CGFloat(imagePixelWidth)
        var paths: [Int: NSBezierPath] = [:]
        var pointMarkers: [(CGPoint, CGFloat)] = []
        for segment in overlay.segments {
            guard let start = viewport.pointForImageCoordinate(
                column: segment.start.column,
                row: segment.start.row
            ), let end = viewport.pointForImageCoordinate(
                column: segment.end.column,
                row: segment.end.row
            ) else { continue }
            let averageRadius = (segment.startRadiusMicrometres
                + segment.endRadiusMicrometres) / 2
            let physicalWidth = 2 * averageRadius / overlay.inPlaneResolutionMicrometres
            let lineWidth = max(
                Self.minimumVesselCoreWidth,
                CGFloat(physicalWidth) * pointsPerImagePixel
            )
            if hypot(end.x - start.x, end.y - start.y) < 0.25 {
                pointMarkers.append((start, lineWidth))
                continue
            }
            // Round upward so batching never draws a radius-bearing segment
            // narrower than its physical display width.
            let widthBucket = Int((lineWidth * 4).rounded(.up))
            let path = paths[widthBucket] ?? NSBezierPath()
            path.move(to: start)
            path.line(to: end)
            path.lineCapStyle = .round
            paths[widthBucket] = path
        }
        let sortedWidthBuckets = paths.keys.sorted()
        for widthBucket in sortedWidthBuckets {
            guard let path = paths[widthBucket] else { continue }
            let lineWidth = CGFloat(widthBucket) / 4
            Self.vesselHaloColor.setStroke()
            path.lineWidth = lineWidth + Self.vesselHaloExpansion
            path.stroke()
        }
        let pointDiameters = pointMarkers.map { point, lineWidth in
            (point, max(Self.minimumVesselPointDiameter, lineWidth))
        }
        for (point, coreDiameter) in pointDiameters {
            let haloDiameter = coreDiameter + Self.vesselHaloExpansion
            let halo = NSBezierPath(
                ovalIn: CGRect(
                    x: point.x - haloDiameter / 2,
                    y: point.y - haloDiameter / 2,
                    width: haloDiameter,
                    height: haloDiameter
                )
            )
            Self.vesselHaloColor.setFill()
            halo.fill()
        }
        // Draw every neutral core after every halo so dense Dorsal paths do
        // not lose a thinner branch underneath a later width bucket's halo.
        for widthBucket in sortedWidthBuckets {
            guard let path = paths[widthBucket] else { continue }
            let lineWidth = CGFloat(widthBucket) / 4
            Self.vesselCoreColor.setStroke()
            path.lineWidth = lineWidth
            path.stroke()
        }
        for (point, coreDiameter) in pointDiameters {
            let core = NSBezierPath(
                ovalIn: CGRect(
                    x: point.x - coreDiameter / 2,
                    y: point.y - coreDiameter / 2,
                    width: coreDiameter,
                    height: coreDiameter
                )
            )
            Self.vesselCoreColor.setFill()
            core.fill()
        }
    }

    private func triangle(at point: CGPoint, radius: CGFloat, pointsUp: Bool) -> NSBezierPath {
        let sign: CGFloat = pointsUp ? -1 : 1
        let path = NSBezierPath()
        path.move(to: CGPoint(x: point.x, y: point.y + sign * radius))
        path.line(to: CGPoint(x: point.x - radius, y: point.y - sign * radius * 0.75))
        path.line(to: CGPoint(x: point.x + radius, y: point.y - sign * radius * 0.75))
        path.close()
        return path
    }

    private func diamond(at point: CGPoint, radius: CGFloat) -> NSBezierPath {
        let path = NSBezierPath()
        path.move(to: CGPoint(x: point.x, y: point.y - radius))
        path.line(to: CGPoint(x: point.x + radius, y: point.y))
        path.line(to: CGPoint(x: point.x, y: point.y + radius))
        path.line(to: CGPoint(x: point.x - radius, y: point.y))
        path.close()
        return path
    }
}
