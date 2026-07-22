import CoreGraphics
import Foundation

/// One zero-based pixel in a rendered atlas slice.
public struct AtlasSlicePixel: Equatable, Sendable {
    public let column: Int
    public let row: Int

    public init(column: Int, row: Int) {
        self.column = column
        self.row = row
    }
}

/// Pure geometry for the AppKit atlas-slice viewport.
///
/// The type deliberately has no image or event dependencies. It is the single
/// source of truth for aspect-fit layout, pan limits, zoom anchoring, and the
/// half-open view-point-to-pixel mapping used by atlas picks.
public struct AtlasSliceViewport: Equatable, Sendable {
    public static let defaultContentInset: CGFloat = 6

    public let bounds: CGRect
    public let imagePixelWidth: Int
    public let imagePixelHeight: Int
    public let zoom: CGFloat
    public let pan: CGPoint
    public let contentInset: CGFloat

    public init(
        bounds: CGRect,
        imagePixelWidth: Int,
        imagePixelHeight: Int,
        zoom: CGFloat,
        pan: CGPoint,
        contentInset: CGFloat = Self.defaultContentInset
    ) {
        self.bounds = bounds
        self.imagePixelWidth = imagePixelWidth
        self.imagePixelHeight = imagePixelHeight
        self.zoom = zoom
        self.pan = pan
        self.contentInset = contentInset
    }

    /// The centered, unzoomed image rectangle.
    public var aspectFitImageRect: CGRect? {
        guard let metrics = metrics(zoom: 1) else { return nil }
        return centeredRect(size: metrics.contentSize, pan: .zero, available: metrics.available)
    }

    /// The displayed rectangle after zoom and a safely clamped pan.
    public var displayedImageRect: CGRect? {
        displayedImageRect(clampingPan: true)
    }

    /// Return a zero-based image pixel or nil for padding and the half-open max edges.
    public func pixel(at point: CGPoint) -> AtlasSlicePixel? {
        guard point.isFinite, let rect = displayedImageRect else { return nil }
        guard
            point.x >= rect.minX,
            point.x < rect.maxX,
            point.y >= rect.minY,
            point.y < rect.maxY
        else { return nil }

        let column = Int(floor((point.x - rect.minX) / rect.width * CGFloat(imagePixelWidth)))
        let row = Int(floor((point.y - rect.minY) / rect.height * CGFloat(imagePixelHeight)))
        guard
            column >= 0, column < imagePixelWidth,
            row >= 0, row < imagePixelHeight
        else { return nil }
        return AtlasSlicePixel(column: column, row: row)
    }

    /// Return the view-space center of a valid image pixel.
    public func pointForPixelCenter(column: Int, row: Int) -> CGPoint? {
        guard
            column >= 0, column < imagePixelWidth,
            row >= 0, row < imagePixelHeight,
            let rect = displayedImageRect
        else { return nil }
        let point = CGPoint(
            x: rect.minX + (CGFloat(column) + 0.5) / CGFloat(imagePixelWidth) * rect.width,
            y: rect.minY + (CGFloat(row) + 0.5) / CGFloat(imagePixelHeight) * rect.height
        )
        return point.isFinite ? point : nil
    }

    /// Clamp pan so a zoomed dimension cannot expose padding beyond its fit position.
    public func clampedPan(_ proposed: CGPoint) -> CGPoint {
        guard proposed.isFinite, let metrics = metrics(zoom: zoom) else { return .zero }
        let maximumX = max(0, (metrics.contentSize.width - metrics.available.width) / 2)
        let maximumY = max(0, (metrics.contentSize.height - metrics.available.height) / 2)
        return CGPoint(
            x: min(maximumX, max(-maximumX, proposed.x)),
            y: min(maximumY, max(-maximumY, proposed.y))
        )
    }

    /// Return a new viewport zoomed around a stable view-space anchor.
    ///
    /// The image coordinate under `anchor` remains fixed unless pan reaches a boundary.
    public func zoomed(
        to proposedZoom: CGFloat,
        around anchor: CGPoint,
        allowedZoom: ClosedRange<CGFloat>
    ) -> AtlasSliceViewport {
        guard
            proposedZoom.isFinite,
            anchor.isFinite,
            allowedZoom.lowerBound.isFinite,
            allowedZoom.upperBound.isFinite,
            allowedZoom.lowerBound > 0,
            let oldRect = displayedImageRect
        else { return self }

        let newZoom = min(allowedZoom.upperBound, max(allowedZoom.lowerBound, proposedZoom))
        let effectivePan = clampedPan(pan)
        guard abs(newZoom - zoom) > 1e-9 else {
            return AtlasSliceViewport(
                bounds: bounds,
                imagePixelWidth: imagePixelWidth,
                imagePixelHeight: imagePixelHeight,
                zoom: zoom,
                pan: effectivePan,
                contentInset: contentInset
            )
        }

        let imageAnchor = CGPoint(
            x: min(oldRect.maxX, max(oldRect.minX, anchor.x)),
            y: min(oldRect.maxY, max(oldRect.minY, anchor.y))
        )
        let unitX = (imageAnchor.x - oldRect.minX) / oldRect.width
        let unitY = (imageAnchor.y - oldRect.minY) / oldRect.height
        let provisional = AtlasSliceViewport(
            bounds: bounds,
            imagePixelWidth: imagePixelWidth,
            imagePixelHeight: imagePixelHeight,
            zoom: newZoom,
            pan: effectivePan,
            contentInset: contentInset
        )
        guard let provisionalRect = provisional.displayedImageRect(clampingPan: false) else {
            return self
        }
        let correction = CGPoint(
            x: imageAnchor.x - (provisionalRect.minX + unitX * provisionalRect.width),
            y: imageAnchor.y - (provisionalRect.minY + unitY * provisionalRect.height)
        )
        let correctedPan = provisional.clampedPan(
            CGPoint(x: effectivePan.x + correction.x, y: effectivePan.y + correction.y)
        )
        return AtlasSliceViewport(
            bounds: bounds,
            imagePixelWidth: imagePixelWidth,
            imagePixelHeight: imagePixelHeight,
            zoom: newZoom,
            pan: correctedPan,
            contentInset: contentInset
        )
    }

    private func displayedImageRect(clampingPan: Bool) -> CGRect? {
        guard let metrics = metrics(zoom: zoom) else { return nil }
        let effectivePan = clampingPan ? clampedPan(pan) : pan
        guard effectivePan.isFinite else { return nil }
        return centeredRect(
            size: metrics.contentSize,
            pan: effectivePan,
            available: metrics.available
        )
    }

    private func metrics(zoom: CGFloat) -> (available: CGRect, contentSize: CGSize)? {
        guard
            bounds.isFinite,
            contentInset.isFinite,
            contentInset >= 0,
            imagePixelWidth > 0,
            imagePixelHeight > 0,
            zoom.isFinite,
            zoom > 0
        else { return nil }
        let available = bounds.insetBy(dx: contentInset, dy: contentInset)
        guard available.width > 0, available.height > 0 else { return nil }
        let fitScale = min(
            available.width / CGFloat(imagePixelWidth),
            available.height / CGFloat(imagePixelHeight)
        )
        guard fitScale.isFinite, fitScale > 0 else { return nil }
        let contentSize = CGSize(
            width: CGFloat(imagePixelWidth) * fitScale * zoom,
            height: CGFloat(imagePixelHeight) * fitScale * zoom
        )
        guard
            contentSize.width.isFinite,
            contentSize.height.isFinite,
            contentSize.width > 0,
            contentSize.height > 0,
            available.minX.isFinite,
            available.minY.isFinite,
            available.maxX.isFinite,
            available.maxY.isFinite
        else { return nil }
        return (
            available,
            contentSize
        )
    }

    private func centeredRect(size: CGSize, pan: CGPoint, available: CGRect) -> CGRect {
        CGRect(
            x: available.midX - size.width / 2 + pan.x,
            y: available.midY - size.height / 2 + pan.y,
            width: size.width,
            height: size.height
        )
    }
}

/// Pure pointer-intent classification shared by the canvas and its tests.
public enum AtlasSlicePointerIntent {
    public static func isDrag(
        from origin: CGPoint,
        to point: CGPoint,
        threshold: CGFloat
    ) -> Bool {
        guard origin.isFinite, point.isFinite, threshold.isFinite, threshold > 0 else {
            return false
        }
        return hypot(point.x - origin.x, point.y - origin.y) >= threshold
    }
}

/// Platform-neutral phases used to delimit precise-scroll gestures.
public enum AtlasSliceScrollPhase: Equatable, Sendable {
    case none
    case began
    case changed
    case ended
    case cancelled
}

/// Deterministic wheel/trackpad delta accumulation independent of `NSEvent`.
public struct AtlasSliceScrollAccumulator: Equatable, Sendable {
    public static let defaultPreciseThreshold: CGFloat = 12
    public static let defaultMaximumStepsPerEvent = 8
    public static let defaultResetInterval: TimeInterval = 0.25

    public let preciseThreshold: CGFloat
    public private(set) var remainder: CGFloat
    private var lastTimestamp: TimeInterval?
    private var lastEventWasPrecise: Bool?

    public init(preciseThreshold: CGFloat = Self.defaultPreciseThreshold) {
        self.preciseThreshold = preciseThreshold.isFinite && preciseThreshold > 0
            ? preciseThreshold
            : Self.defaultPreciseThreshold
        remainder = 0
        lastTimestamp = nil
        lastEventWasPrecise = nil
    }

    public mutating func reset() {
        remainder = 0
        lastTimestamp = nil
        lastEventWasPrecise = nil
    }

    /// Consume one vertical scroll event and return a signed slice-index delta.
    /// Positive macOS scroll deltas step toward lower slice indices.
    public mutating func consume(
        deltaY: CGFloat,
        isPrecise: Bool,
        isMomentum: Bool,
        phase: AtlasSliceScrollPhase = .none,
        timestamp: TimeInterval = 0
    ) -> Int {
        if phase == .began {
            reset()
        }
        guard
            deltaY.isFinite,
            timestamp.isFinite,
            !isMomentum,
            phase != .cancelled
        else {
            reset()
            return 0
        }

        if let lastTimestamp,
           timestamp < lastTimestamp || timestamp - lastTimestamp > Self.defaultResetInterval
        {
            reset()
        }
        if let lastEventWasPrecise, lastEventWasPrecise != isPrecise {
            reset()
        }
        if isPrecise, remainder != 0, deltaY != 0, remainder.sign != deltaY.sign {
            remainder = 0
        }
        lastTimestamp = timestamp
        lastEventWasPrecise = isPrecise

        let shouldResetAfterEvent = phase == .ended
        guard deltaY != 0 else {
            if shouldResetAfterEvent { reset() }
            return 0
        }
        guard isPrecise else {
            remainder = 0
            let steps = deltaY > 0 ? -1 : 1
            if shouldResetAfterEvent { reset() }
            return steps
        }

        let accumulated = remainder + deltaY
        guard accumulated.isFinite else {
            remainder = 0
            return 0
        }
        let quotient = accumulated / preciseThreshold
        let maximumSteps = Self.defaultMaximumStepsPerEvent
        let rawSteps: Int
        if quotient >= CGFloat(maximumSteps) {
            rawSteps = maximumSteps
            remainder = 0
        } else if quotient <= -CGFloat(maximumSteps) {
            rawSteps = -maximumSteps
            remainder = 0
        } else {
            rawSteps = Int(quotient.rounded(.towardZero))
        }
        guard rawSteps != 0 else {
            remainder = accumulated
            if shouldResetAfterEvent { reset() }
            return 0
        }
        if abs(rawSteps) < maximumSteps {
            remainder = accumulated - CGFloat(rawSteps) * preciseThreshold
        }
        let steps = -rawSteps
        if shouldResetAfterEvent { reset() }
        return steps
    }
}

private extension CGPoint {
    var isFinite: Bool { x.isFinite && y.isFinite }
}

private extension CGRect {
    var isFinite: Bool {
        origin.x.isFinite && origin.y.isFinite && width.isFinite && height.isFinite
    }
}
