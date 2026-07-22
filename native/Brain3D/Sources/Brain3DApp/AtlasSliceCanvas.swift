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

    private var imageData: Data?
    private var image: NSImage?
    private var imagePixelWidth = 0
    private var imagePixelHeight = 0
    private var selection: AtlasSliceSelection?
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
        pickHandler = onPick
        sliceStepHandler = onSliceStep
        setAccessibilityLabel(accessibilityLabel)
        setAccessibilityValue(accessibilityValue)
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
}
