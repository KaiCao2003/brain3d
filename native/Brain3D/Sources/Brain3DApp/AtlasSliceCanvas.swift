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

/// Fixed viewport-edge labels for the atlas's ASR voxel convention.
///
/// Atlas rows and columns increase from anterior/superior/right toward
/// posterior/inferior/left. These labels remain fixed while the image pans or
/// zooms so laterality never depends on the user's current viewport transform.
struct AtlasCanvasAnatomicalLabels: Equatable, Sendable {
    let top: String
    let bottom: String
    let left: String
    let right: String

    static let dorsal = AtlasCanvasAnatomicalLabels(
        top: "A",
        bottom: "P",
        left: "R",
        right: "L"
    )

    static func slice(_ orientation: AtlasSliceOrientation) -> Self {
        switch orientation {
        case .coronal:
            AtlasCanvasAnatomicalLabels(top: "D", bottom: "V", left: "R", right: "L")
        case .sagittal:
            AtlasCanvasAnatomicalLabels(top: "D", bottom: "V", left: "A", right: "P")
        case .horizontal:
            dorsal
        }
    }

    var accessibilityDescription: String {
        "Anatomical orientation: \(expanded(top)) at top, "
            + "\(expanded(bottom)) at bottom, \(expanded(left)) at left edge, "
            + "and \(expanded(right)) at right edge."
    }

    private func expanded(_ label: String) -> String {
        switch label {
        case "A": "anterior"
        case "P": "posterior"
        case "D": "dorsal"
        case "V": "ventral"
        case "R": "right"
        case "L": "left"
        default: label
        }
    }
}

fileprivate struct MajorVesselRasterKey: Hashable, Sendable {
    let assetSHA256: String
    let orientation: AtlasSliceOrientation
    let sliceIndex: Int
    let imagePixelWidth: Int
    let imagePixelHeight: Int
    let segmentCount: Int
    let inPlaneResolutionBitPattern: UInt64
    let minimumVisibleDiameterBitPattern: UInt64

    init?(
        overlay: MajorVesselSliceOverlay?,
        imagePixelWidth: Int,
        imagePixelHeight: Int
    ) {
        guard let overlay, imagePixelWidth > 0, imagePixelHeight > 0 else { return nil }
        assetSHA256 = overlay.assetSHA256
        orientation = overlay.orientation
        sliceIndex = overlay.sliceIndex
        self.imagePixelWidth = imagePixelWidth
        self.imagePixelHeight = imagePixelHeight
        segmentCount = overlay.segments.count
        inPlaneResolutionBitPattern = overlay.inPlaneResolutionMicrometres.bitPattern
        minimumVisibleDiameterBitPattern =
            overlay.minimumVisibleDiameterMicrometres.bitPattern
    }

    var cacheIdentifier: NSString {
        [
            assetSHA256,
            orientation.rawValue,
            String(sliceIndex),
            String(imagePixelWidth),
            String(imagePixelHeight),
            String(segmentCount),
            String(inPlaneResolutionBitPattern),
            String(minimumVisibleDiameterBitPattern),
        ].joined(separator: ":") as NSString
    }
}

struct MajorVesselRasterResult: @unchecked Sendable {
    let image: CGImage
    let logicalWidth: Int
    let logicalHeight: Int
}

fileprivate final class MajorVesselRasterBox: NSObject, @unchecked Sendable {
    let result: MajorVesselRasterResult

    init(_ result: MajorVesselRasterResult) {
        self.result = result
    }
}

@MainActor
enum MajorVesselRasterCache {
    fileprivate static let storage: NSCache<NSString, MajorVesselRasterBox> = {
        let cache = NSCache<NSString, MajorVesselRasterBox>()
        cache.countLimit = 32
        cache.totalCostLimit = 128 * 1_024 * 1_024
        return cache
    }()

    fileprivate static func result(
        for key: MajorVesselRasterKey
    ) -> MajorVesselRasterResult? {
        storage.object(forKey: key.cacheIdentifier)?.result
    }

    fileprivate static func insert(
        _ result: MajorVesselRasterResult,
        for key: MajorVesselRasterKey
    ) {
        storage.setObject(
            MajorVesselRasterBox(result),
            forKey: key.cacheIdentifier,
            cost: result.image.bytesPerRow * result.image.height
        )
    }

    static func insert(
        _ result: MajorVesselRasterResult,
        overlay: MajorVesselSliceOverlay,
        imagePixelWidth: Int,
        imagePixelHeight: Int
    ) {
        guard let key = MajorVesselRasterKey(
            overlay: overlay,
            imagePixelWidth: imagePixelWidth,
            imagePixelHeight: imagePixelHeight
        ) else { return }
        insert(result, for: key)
    }
}

enum MajorVesselRasterizer {
    // These are intrinsic-image-pixel display minima. At a typical 1.5-point
    // aspect-fit scale they reproduce the prior 2.25/3.25/3-point screen aids,
    // while the measured physical vessel diameter remains the core authority.
    private static let minimumCoreWidth: CGFloat = 2
    private static let minimumPointDiameter: CGFloat = 3
    private static let haloExpansion: CGFloat = 2
    // The MVP intentionally matches the reviewed 25 µm atlas raster. A denser
    // supersample multiplied initial preparation cost without adding source
    // information and delayed the first trustworthy vessel display.
    private static let rasterScale = 1

    static func render(
        overlay: MajorVesselSliceOverlay,
        imagePixelWidth: Int,
        imagePixelHeight: Int
    ) -> MajorVesselRasterResult? {
        guard imagePixelWidth > 0,
              imagePixelHeight > 0,
              overlay.inPlaneResolutionMicrometres.isFinite,
              overlay.inPlaneResolutionMicrometres > 0,
              !Task.isCancelled
        else { return nil }

        let widthProduct = imagePixelWidth.multipliedReportingOverflow(by: rasterScale)
        let heightProduct = imagePixelHeight.multipliedReportingOverflow(by: rasterScale)
        guard !widthProduct.overflow, !heightProduct.overflow else { return nil }
        let pixelWidth = widthProduct.partialValue
        let pixelHeight = heightProduct.partialValue
        let pixelCountProduct = pixelWidth.multipliedReportingOverflow(by: pixelHeight)
        guard !pixelCountProduct.overflow, pixelCountProduct.partialValue > 0 else { return nil }
        let pixelCount = pixelCountProduct.partialValue
        var haloCoverage = [UInt8](repeating: 0, count: pixelCount)
        var coreCoverage = [UInt8](repeating: 0, count: pixelCount)

        for (offset, segment) in overlay.segments.enumerated() {
            if offset.isMultiple(of: 1_024), Task.isCancelled { return nil }
            let values = [
                segment.start.column,
                segment.start.row,
                segment.end.column,
                segment.end.row,
                segment.startRadiusMicrometres,
                segment.endRadiusMicrometres,
            ]
            guard values.allSatisfy(\.isFinite) else { continue }
            let start = CGPoint(
                x: segment.start.column * Double(rasterScale),
                y: segment.start.row * Double(rasterScale)
            )
            let end = CGPoint(
                x: segment.end.column * Double(rasterScale),
                y: segment.end.row * Double(rasterScale)
            )
            let averageRadius = (
                segment.startRadiusMicrometres + segment.endRadiusMicrometres
            ) / 2
            let physicalWidth = 2 * averageRadius / overlay.inPlaneResolutionMicrometres
            var coreWidth = max(minimumCoreWidth, CGFloat(physicalWidth))
            if hypot(
                segment.end.column - segment.start.column,
                segment.end.row - segment.start.row
            ) < 0.25 {
                coreWidth = max(minimumPointDiameter, coreWidth)
            }
            // Keep the prior conservative quarter-pixel upward width bucket.
            coreWidth = (coreWidth * 4).rounded(.up) / 4
            drawCoverage(
                from: start,
                to: end,
                radius: (coreWidth + haloExpansion) * CGFloat(rasterScale) / 2,
                width: pixelWidth,
                height: pixelHeight,
                into: &haloCoverage
            )
            drawCoverage(
                from: start,
                to: end,
                radius: coreWidth * CGFloat(rasterScale) / 2,
                width: pixelWidth,
                height: pixelHeight,
                into: &coreCoverage
            )
        }
        guard !Task.isCancelled else { return nil }

        let byteCountProduct = pixelCount.multipliedReportingOverflow(by: 4)
        guard !byteCountProduct.overflow else { return nil }
        var rgba = [UInt8](repeating: 0, count: byteCountProduct.partialValue)
        for pixelIndex in 0 ..< pixelCount {
            let haloAlpha = 0.88 * Double(haloCoverage[pixelIndex]) / 255
            let coreAlpha = 0.98 * Double(coreCoverage[pixelIndex]) / 255
            let outputAlpha = coreAlpha + haloAlpha * (1 - coreAlpha)
            let byteOffset = pixelIndex * 4
            // Use a saturated surgical-overlay red instead of an achromatic
            // core. The surrounding halo remains black because its RGB
            // contribution is intentionally zero; it separates the reference
            // vessel from both bright and dark atlas pixels.
            rgba[byteOffset] = premultipliedByte(coreAlpha)
            rgba[byteOffset + 1] = premultipliedByte(coreAlpha * 0.16)
            rgba[byteOffset + 2] = premultipliedByte(coreAlpha * 0.10)
            rgba[byteOffset + 3] = UInt8(
                min(255, max(0, Int((outputAlpha * 255).rounded())))
            )
        }

        guard !Task.isCancelled else { return nil }
        let data = Data(rgba)
        guard let provider = CGDataProvider(data: data as CFData),
              let image = CGImage(
                  width: pixelWidth,
                  height: pixelHeight,
                  bitsPerComponent: 8,
                  bitsPerPixel: 32,
                  bytesPerRow: pixelWidth * 4,
                  space: CGColorSpaceCreateDeviceRGB(),
                  bitmapInfo: CGBitmapInfo(
                      rawValue: CGImageAlphaInfo.premultipliedLast.rawValue
                  ),
                  provider: provider,
                  decode: nil,
                  shouldInterpolate: true,
                  intent: .defaultIntent
              )
        else { return nil }
        return MajorVesselRasterResult(
            image: image,
            logicalWidth: imagePixelWidth,
            logicalHeight: imagePixelHeight
        )
    }

    private static func premultipliedByte(_ value: Double) -> UInt8 {
        UInt8(min(255, max(0, Int((value * 255).rounded()))))
    }

    private static func drawCoverage(
        from start: CGPoint,
        to end: CGPoint,
        radius: CGFloat,
        width: Int,
        height: Int,
        into coverage: inout [UInt8]
    ) {
        guard start.x.isFinite,
              start.y.isFinite,
              end.x.isFinite,
              end.y.isFinite,
              radius.isFinite,
              radius > 0
        else { return }
        let minimumX = max(0, Int(floor(min(start.x, end.x) - radius - 0.5)))
        let maximumX = min(width - 1, Int(ceil(max(start.x, end.x) + radius + 0.5)))
        let minimumY = max(0, Int(floor(min(start.y, end.y) - radius - 0.5)))
        let maximumY = min(height - 1, Int(ceil(max(start.y, end.y) + radius + 0.5)))
        guard minimumX <= maximumX, minimumY <= maximumY else { return }

        let deltaX = end.x - start.x
        let deltaY = end.y - start.y
        let lengthSquared = deltaX * deltaX + deltaY * deltaY
        for y in minimumY ... maximumY {
            let sampleY = CGFloat(y) + 0.5
            for x in minimumX ... maximumX {
                let sampleX = CGFloat(x) + 0.5
                let parameter: CGFloat
                if lengthSquared > 1e-12 {
                    parameter = min(
                        1,
                        max(
                            0,
                            ((sampleX - start.x) * deltaX
                                + (sampleY - start.y) * deltaY) / lengthSquared
                        )
                    )
                } else {
                    parameter = 0
                }
                let nearestX = start.x + parameter * deltaX
                let nearestY = start.y + parameter * deltaY
                let distance = hypot(sampleX - nearestX, sampleY - nearestY)
                let fractionalCoverage = min(1, max(0, radius + 0.5 - distance))
                guard fractionalCoverage > 0 else { continue }
                let value = UInt8((fractionalCoverage * 255).rounded())
                let index = y * width + x
                if value > coverage[index] {
                    coverage[index] = value
                }
            }
        }
    }
}

/// AppKit-backed scientific image viewport.
///
/// The view owns display-only pan and zoom state. Pixel picks are returned to
/// the caller; the Python bridge remains the only authority that maps those
/// pixels into atlas coordinates.
struct AtlasSliceCanvas: NSViewRepresentable {
    let imageData: Data?
    let regionOverlayData: Data?
    let imagePixelWidth: Int
    let imagePixelHeight: Int
    let viewportIdentity: String
    let anatomicalLabels: AtlasCanvasAnatomicalLabels
    let selection: AtlasSliceSelection?
    let majorVesselOverlay: MajorVesselSliceOverlay?
    let majorVesselConflictOverlay: MajorVesselConflictCanvasOverlay?
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

    static func dismantleNSView(_ nsView: AtlasSliceNSView, coordinator: ()) {
        nsView.prepareForDismantling()
    }

    private func update(_ view: AtlasSliceNSView) {
        view.configure(
            imageData: imageData,
            regionOverlayData: regionOverlayData,
            imagePixelWidth: imagePixelWidth,
            imagePixelHeight: imagePixelHeight,
            viewportIdentity: viewportIdentity,
            anatomicalLabels: anatomicalLabels,
            selection: selection,
            majorVesselOverlay: majorVesselOverlay,
            majorVesselConflictOverlay: majorVesselConflictOverlay,
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
    private var imageData: Data?
    private var image: NSImage?
    private var regionOverlayData: Data?
    private var regionOverlayImage: NSImage?
    private var imagePixelWidth = 0
    private var imagePixelHeight = 0
    private var anatomicalLabels: AtlasCanvasAnatomicalLabels?
    private var selection: AtlasSliceSelection?
    private var majorVesselRasterKey: MajorVesselRasterKey?
    private var majorVesselRasterImage: NSImage?
    private var majorVesselRasterWorker: Task<Void, Never>?
    private var majorVesselRasterGeneration = 0
    private var majorVesselConflictOverlay: MajorVesselConflictCanvasOverlay?
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
        regionOverlayData: Data? = nil,
        imagePixelWidth: Int,
        imagePixelHeight: Int,
        viewportIdentity: String,
        anatomicalLabels: AtlasCanvasAnatomicalLabels,
        selection: AtlasSliceSelection?,
        majorVesselOverlay: MajorVesselSliceOverlay?,
        majorVesselConflictOverlay: MajorVesselConflictCanvasOverlay?,
        probeOverlay: ProbeSliceOverlay?,
        interactionHelp: String,
        accessibilityLabel: String,
        accessibilityValue: String,
        resetGeneration: Int,
        onPick: @escaping (Int, Int) -> Void,
        onSliceStep: @escaping (Int) -> Void
    ) {
        var visualContentChanged = false
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
            visualContentChanged = true
        }
        if self.regionOverlayData != regionOverlayData {
            self.regionOverlayData = regionOverlayData
            regionOverlayImage = regionOverlayData.flatMap(NSImage.init(data:))
            visualContentChanged = true
        }
        if self.imagePixelWidth != sanitizedWidth || self.imagePixelHeight != sanitizedHeight {
            visualContentChanged = true
        }
        self.imagePixelWidth = sanitizedWidth
        self.imagePixelHeight = sanitizedHeight
        if self.anatomicalLabels != anatomicalLabels {
            visualContentChanged = true
        }
        self.anatomicalLabels = anatomicalLabels
        if !sameSelection(self.selection, selection) {
            visualContentChanged = true
        }
        self.selection = selection
        updateMajorVesselRaster(
            overlay: majorVesselOverlay,
            imagePixelWidth: sanitizedWidth,
            imagePixelHeight: sanitizedHeight
        )
        if self.majorVesselConflictOverlay != majorVesselConflictOverlay {
            visualContentChanged = true
        }
        self.majorVesselConflictOverlay = majorVesselConflictOverlay
        if self.probeOverlay != probeOverlay {
            visualContentChanged = true
        }
        self.probeOverlay = probeOverlay
        pickHandler = onPick
        sliceStepHandler = onSliceStep
        setAccessibilityLabel(accessibilityLabel)
        setAccessibilityValue(
            "\(accessibilityValue). \(anatomicalLabels.accessibilityDescription)"
        )
        setAccessibilityHelp(interactionHelp)
        if resetGeneration != lastResetGeneration {
            lastResetGeneration = resetGeneration
            resetViewport()
        }
        if visualContentChanged {
            needsDisplay = true
        }
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        NSColor.black.setFill()
        dirtyRect.fill()

        guard let image, let rect = viewport.displayedImageRect else {
            drawPlaceholder()
            drawAnatomicalLabelsIfPresent()
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
        drawRegionOverlayIfPresent(in: rect)
        drawMajorVesselsIfPresent(in: rect)
        drawProbeOverlayIfPresent()
        drawMajorVesselConflictIfPresent()
        drawSelectionIfPresent()
        drawAnatomicalLabelsIfPresent()
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
        let eventPhase = event.momentumPhase.isEmpty ? event.phase : event.momentumPhase
        let steps = scrollAccumulator.consume(
            deltaY: event.scrollingDeltaY,
            isPrecise: event.hasPreciseScrollingDeltas,
            isMomentum: !event.momentumPhase.isEmpty,
            phase: scrollPhase(for: eventPhase),
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

    func prepareForDismantling() {
        majorVesselRasterGeneration &+= 1
        majorVesselRasterWorker?.cancel()
        majorVesselRasterWorker = nil
        pickHandler = nil
        sliceStepHandler = nil
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

    private func updateMajorVesselRaster(
        overlay: MajorVesselSliceOverlay?,
        imagePixelWidth: Int,
        imagePixelHeight: Int
    ) {
        let nextKey = MajorVesselRasterKey(
            overlay: overlay,
            imagePixelWidth: imagePixelWidth,
            imagePixelHeight: imagePixelHeight
        )
        guard nextKey != majorVesselRasterKey else { return }

        majorVesselRasterGeneration &+= 1
        let generation = majorVesselRasterGeneration
        majorVesselRasterWorker?.cancel()
        majorVesselRasterWorker = nil
        majorVesselRasterKey = nextKey
        majorVesselRasterImage = nil
        needsDisplay = true

        guard let overlay, let nextKey else { return }
        if let cached = MajorVesselRasterCache.result(for: nextKey) {
            majorVesselRasterImage = NSImage(
                cgImage: cached.image,
                size: NSSize(width: cached.logicalWidth, height: cached.logicalHeight)
            )
            return
        }

        majorVesselRasterWorker = Task.detached(priority: .userInitiated) { [weak self] in
            let raster = MajorVesselRasterizer.render(
                overlay: overlay,
                imagePixelWidth: imagePixelWidth,
                imagePixelHeight: imagePixelHeight
            )
            guard !Task.isCancelled else { return }
            await MainActor.run { [weak self] in
                guard let self,
                      generation == self.majorVesselRasterGeneration,
                      nextKey == self.majorVesselRasterKey
                else { return }
                self.majorVesselRasterWorker = nil
                if let raster {
                    MajorVesselRasterCache.insert(raster, for: nextKey)
                    self.majorVesselRasterImage = NSImage(
                        cgImage: raster.image,
                        size: NSSize(
                            width: raster.logicalWidth,
                            height: raster.logicalHeight
                        )
                    )
                }
                self.needsDisplay = true
            }
        }
    }

    private func sameSelection(
        _ lhs: AtlasSliceSelection?,
        _ rhs: AtlasSliceSelection?
    ) -> Bool {
        switch (lhs, rhs) {
        case (.none, .none):
            true
        case let (.some(lhs), .some(rhs)):
            lhs.column == rhs.column
                && lhs.row == rhs.row
                && lhs.acronym == rhs.acronym
                && lhs.name == rhs.name
                && lhs.color.isEqual(rhs.color)
        default:
            false
        }
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

    private func drawAnatomicalLabelsIfPresent() {
        guard let anatomicalLabels, bounds.width >= 48, bounds.height >= 48 else { return }
        let edgeInset: CGFloat = 14
        drawAnatomicalLabel(
            anatomicalLabels.top,
            centeredAt: CGPoint(x: bounds.midX, y: bounds.minY + edgeInset)
        )
        drawAnatomicalLabel(
            anatomicalLabels.bottom,
            centeredAt: CGPoint(x: bounds.midX, y: bounds.maxY - edgeInset)
        )
        drawAnatomicalLabel(
            anatomicalLabels.left,
            centeredAt: CGPoint(x: bounds.minX + edgeInset, y: bounds.midY)
        )
        drawAnatomicalLabel(
            anatomicalLabels.right,
            centeredAt: CGPoint(x: bounds.maxX - edgeInset, y: bounds.midY)
        )
    }

    private func drawAnatomicalLabel(_ label: String, centeredAt center: CGPoint) {
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedSystemFont(ofSize: 11, weight: .semibold),
            .foregroundColor: NSColor.white.withAlphaComponent(0.92),
        ]
        let textSize = label.size(withAttributes: attributes)
        let backgroundRect = CGRect(
            x: center.x - textSize.width / 2 - 5,
            y: center.y - textSize.height / 2 - 3,
            width: textSize.width + 10,
            height: textSize.height + 6
        ).integral
        NSColor.black.withAlphaComponent(0.62).setFill()
        NSColor.white.withAlphaComponent(0.14).setStroke()
        let background = NSBezierPath(
            roundedRect: backgroundRect,
            xRadius: 5,
            yRadius: 5
        )
        background.lineWidth = 1
        background.fill()
        background.stroke()
        label.draw(
            at: CGPoint(
                x: backgroundRect.midX - textSize.width / 2,
                y: backgroundRect.midY - textSize.height / 2
            ),
            withAttributes: attributes
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
            case .implantSite:
                path = diamond(at: point, radius: 7)
                color = .systemPink
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

    private func drawMajorVesselsIfPresent(in imageRect: CGRect) {
        guard let majorVesselRasterImage else { return }
        let context = NSGraphicsContext.current
        let previousInterpolation = context?.imageInterpolation
        // The source is a reviewed 25 µm raster. Nearest-neighbour display keeps
        // it registered to the atlas pixels and avoids a resampling stall while
        // the user directly manipulates the viewport.
        context?.imageInterpolation = .none
        majorVesselRasterImage.draw(
            in: imageRect,
            from: .zero,
            operation: .sourceOver,
            fraction: 1,
            respectFlipped: true,
            hints: nil
        )
        context?.imageInterpolation = previousInterpolation ?? .default
    }

    private func drawRegionOverlayIfPresent(in imageRect: CGRect) {
        guard let regionOverlayImage else { return }
        let context = NSGraphicsContext.current
        let previousInterpolation = context?.imageInterpolation
        // The mask is generated on the exact annotation voxel grid. Nearest
        // neighbour display keeps the filled region and its boundary aligned
        // with the underlying atlas slice at every zoom level.
        context?.imageInterpolation = .none
        regionOverlayImage.draw(
            in: imageRect,
            from: .zero,
            operation: .sourceOver,
            fraction: 1,
            respectFlipped: true,
            hints: nil
        )
        context?.imageInterpolation = previousInterpolation ?? .default
    }

    private func drawMajorVesselConflictIfPresent() {
        guard let conflict = majorVesselConflictOverlay,
              let probePoint = viewport.pointForImageCoordinate(
                  column: conflict.probePoint.column,
                  row: conflict.probePoint.row
              ),
              let vesselPoint = viewport.pointForImageCoordinate(
                  column: conflict.vesselPoint.column,
                  row: conflict.vesselPoint.row
              )
        else { return }

        if let segment = conflict.exactVesselSegment,
           let start = viewport.pointForImageCoordinate(
               column: segment.start.column,
               row: segment.start.row
           ),
           let end = viewport.pointForImageCoordinate(
               column: segment.end.column,
               row: segment.end.row
           )
        {
            let highlightedSegment = NSBezierPath()
            highlightedSegment.move(to: start)
            highlightedSegment.line(to: end)
            highlightedSegment.lineCapStyle = .round
            NSColor.black.withAlphaComponent(0.92).setStroke()
            highlightedSegment.lineWidth = 9
            highlightedSegment.stroke()
            NSColor.systemPink.setStroke()
            highlightedSegment.lineWidth = 5
            highlightedSegment.stroke()
        }

        let closestPointLine = NSBezierPath()
        closestPointLine.move(to: probePoint)
        closestPointLine.line(to: vesselPoint)
        closestPointLine.lineCapStyle = .round
        NSColor.black.withAlphaComponent(0.9).setStroke()
        closestPointLine.lineWidth = 6
        closestPointLine.stroke()
        NSColor.systemYellow.setStroke()
        closestPointLine.lineWidth = 2.5
        closestPointLine.setLineDash([6, 4], count: 2, phase: 0)
        closestPointLine.stroke()

        let probeMarker = diamond(at: probePoint, radius: 7)
        NSColor.black.withAlphaComponent(0.9).setStroke()
        NSColor.systemOrange.setFill()
        probeMarker.lineWidth = 2
        probeMarker.fill()
        probeMarker.stroke()

        let vesselMarker = NSBezierPath(
            ovalIn: CGRect(
                x: vesselPoint.x - 7,
                y: vesselPoint.y - 7,
                width: 14,
                height: 14
            )
        )
        NSColor.black.withAlphaComponent(0.9).setStroke()
        NSColor.systemPink.setFill()
        vesselMarker.lineWidth = 2
        vesselMarker.fill()
        vesselMarker.stroke()

        let labelAttributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedSystemFont(ofSize: 10, weight: .bold),
            .foregroundColor: NSColor.white,
            .strokeColor: NSColor.black,
            .strokeWidth: -3,
        ]
        "P".draw(
            at: CGPoint(x: probePoint.x + 9, y: probePoint.y - 8),
            withAttributes: labelAttributes
        )
        "V".draw(
            at: CGPoint(x: vesselPoint.x + 9, y: vesselPoint.y - 8),
            withAttributes: labelAttributes
        )
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
