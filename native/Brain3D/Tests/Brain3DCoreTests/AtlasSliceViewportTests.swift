import Brain3DCore
import CoreGraphics
import Testing

@Suite("Atlas slice viewport geometry")
struct AtlasSliceViewportTests {
    @Test("Aspect fit is centered and letterbox space is never pickable")
    func aspectFitAndLetterboxRejection() throws {
        let viewport = AtlasSliceViewport(
            bounds: CGRect(x: 0, y: 0, width: 200, height: 200),
            imagePixelWidth: 100,
            imagePixelHeight: 50,
            zoom: 1,
            pan: .zero,
            contentInset: 0
        )
        let rect = try #require(viewport.aspectFitImageRect)
        #expect(rect == CGRect(x: 0, y: 50, width: 200, height: 100))
        #expect(viewport.displayedImageRect == rect)

        #expect(viewport.pixel(at: CGPoint(x: 100, y: 49.999)) == nil)
        #expect(viewport.pixel(at: CGPoint(x: 100, y: 150)) == nil)
        #expect(viewport.pixel(at: CGPoint(x: -0.001, y: 100)) == nil)
        #expect(viewport.pixel(at: CGPoint(x: 200, y: 100)) == nil)
        #expect(viewport.pixel(at: CGPoint(x: 0, y: 50)) == AtlasSlicePixel(column: 0, row: 0))
        #expect(
            viewport.pixel(at: CGPoint(x: 199.999, y: 149.999))
                == AtlasSlicePixel(column: 99, row: 49)
        )
    }

    @Test("Pixel centers round-trip and invalid pixels are rejected")
    func pixelCentersAndBounds() throws {
        let viewport = AtlasSliceViewport(
            bounds: CGRect(x: 0, y: 0, width: 400, height: 200),
            imagePixelWidth: 4,
            imagePixelHeight: 2,
            zoom: 1,
            pan: .zero,
            contentInset: 0
        )

        let first = try #require(viewport.pointForPixelCenter(column: 0, row: 0))
        let last = try #require(viewport.pointForPixelCenter(column: 3, row: 1))
        #expect(first == CGPoint(x: 50, y: 50))
        #expect(last == CGPoint(x: 350, y: 150))
        #expect(viewport.pixel(at: first) == AtlasSlicePixel(column: 0, row: 0))
        #expect(viewport.pixel(at: last) == AtlasSlicePixel(column: 3, row: 1))
        #expect(viewport.pointForPixelCenter(column: -1, row: 0) == nil)
        #expect(viewport.pointForPixelCenter(column: 4, row: 0) == nil)
        #expect(viewport.pointForPixelCenter(column: 0, row: 2) == nil)
    }

    @Test("Zoom keeps the image coordinate below its anchor stable")
    func zoomAroundAnchor() throws {
        let original = AtlasSliceViewport(
            bounds: CGRect(x: 0, y: 0, width: 300, height: 200),
            imagePixelWidth: 100,
            imagePixelHeight: 100,
            zoom: 1,
            pan: .zero,
            contentInset: 0
        )
        let anchor = CGPoint(x: 125, y: 75)
        let originalPixel = try #require(original.pixel(at: anchor))

        let zoomed = original.zoomed(to: 2, around: anchor, allowedZoom: 1 ... 12)
        #expect(zoomed.zoom == 2)
        #expect(zoomed.pan == CGPoint(x: 25, y: 25))
        #expect(zoomed.pixel(at: anchor) == originalPixel)
    }

    @Test("A zoom anchor in letterbox space is clamped to the nearest image edge")
    func letterboxZoomAnchor() {
        let viewport = AtlasSliceViewport(
            bounds: CGRect(x: 0, y: 0, width: 200, height: 200),
            imagePixelWidth: 100,
            imagePixelHeight: 50,
            zoom: 1,
            pan: .zero,
            contentInset: 0
        )
        let fromLetterbox = viewport.zoomed(
            to: 3,
            around: CGPoint(x: 100, y: 0),
            allowedZoom: 1 ... 12
        )
        let fromNearestEdge = viewport.zoomed(
            to: 3,
            around: CGPoint(x: 100, y: 50),
            allowedZoom: 1 ... 12
        )
        #expect(fromLetterbox == fromNearestEdge)
    }

    @Test("Pan is clamped and zoomed/panned pixel mapping remains invertible")
    func panClampAndInversion() throws {
        let base = AtlasSliceViewport(
            bounds: CGRect(x: 0, y: 0, width: 300, height: 200),
            imagePixelWidth: 100,
            imagePixelHeight: 100,
            zoom: 2,
            pan: .zero,
            contentInset: 0
        )
        #expect(base.clampedPan(CGPoint(x: 500, y: -500)) == CGPoint(x: 50, y: -100))

        let panned = AtlasSliceViewport(
            bounds: base.bounds,
            imagePixelWidth: base.imagePixelWidth,
            imagePixelHeight: base.imagePixelHeight,
            zoom: base.zoom,
            pan: CGPoint(x: 40, y: -70),
            contentInset: 0
        )
        let center = try #require(panned.pointForPixelCenter(column: 23, row: 77))
        #expect(panned.pixel(at: center) == AtlasSlicePixel(column: 23, row: 77))
    }

    @Test("Zoom limits are enforced without moving an unchanged viewport")
    func zoomLimits() {
        let viewport = AtlasSliceViewport(
            bounds: CGRect(x: 0, y: 0, width: 200, height: 200),
            imagePixelWidth: 100,
            imagePixelHeight: 100,
            zoom: 1,
            pan: .zero,
            contentInset: 0
        )
        let anchor = CGPoint(x: 100, y: 100)
        #expect(viewport.zoomed(to: 0, around: anchor, allowedZoom: 1 ... 12) == viewport)
        #expect(viewport.zoomed(to: 99, around: anchor, allowedZoom: 1 ... 12).zoom == 12)
        #expect(viewport.zoomed(to: .nan, around: anchor, allowedZoom: 1 ... 12) == viewport)

        let panned = AtlasSliceViewport(
            bounds: viewport.bounds,
            imagePixelWidth: viewport.imagePixelWidth,
            imagePixelHeight: viewport.imagePixelHeight,
            zoom: 2,
            pan: CGPoint(x: 50, y: -50),
            contentInset: 0
        )
        let fit = panned.zoomed(to: 1, around: anchor, allowedZoom: 1 ... 12)
        #expect(fit.zoom == 1)
        #expect(fit.pan == .zero)
    }

    @Test("Drag classification uses an inclusive radial threshold")
    func dragThreshold() {
        let origin = CGPoint(x: 10, y: 10)
        #expect(!AtlasSlicePointerIntent.isDrag(
            from: origin,
            to: CGPoint(x: 12, y: 13),
            threshold: 4
        ))
        #expect(AtlasSlicePointerIntent.isDrag(
            from: origin,
            to: CGPoint(x: 14, y: 10),
            threshold: 4
        ))
        #expect(!AtlasSlicePointerIntent.isDrag(
            from: origin,
            to: CGPoint(x: 20, y: 20),
            threshold: 0
        ))
    }

    @Test("Precise scroll deltas accumulate while wheel and momentum remain deterministic")
    func scrollAccumulation() {
        var accumulator = AtlasSliceScrollAccumulator(preciseThreshold: 12)

        #expect(accumulator.consume(deltaY: 5, isPrecise: true, isMomentum: false) == 0)
        #expect(accumulator.remainder == 5)
        #expect(accumulator.consume(deltaY: 6, isPrecise: true, isMomentum: false) == 0)
        #expect(accumulator.remainder == 11)
        #expect(accumulator.consume(deltaY: 1, isPrecise: true, isMomentum: false) == -1)
        #expect(accumulator.remainder == 0)

        #expect(accumulator.consume(deltaY: -25, isPrecise: true, isMomentum: false) == 2)
        #expect(accumulator.remainder == -1)
        #expect(accumulator.consume(deltaY: 24, isPrecise: true, isMomentum: true) == 0)
        #expect(accumulator.remainder == 0)

        #expect(accumulator.consume(deltaY: -0.1, isPrecise: false, isMomentum: false) == 1)
        #expect(accumulator.remainder == 0)
        #expect(accumulator.consume(deltaY: 0.1, isPrecise: false, isMomentum: false) == -1)
        #expect(accumulator.consume(deltaY: .nan, isPrecise: true, isMomentum: false) == 0)

        accumulator.reset()
        #expect(accumulator.remainder == 0)
    }

    @Test("Scroll gesture boundaries, reversals, gaps, and huge deltas clear stale remainder")
    func scrollResetRules() {
        var accumulator = AtlasSliceScrollAccumulator(preciseThreshold: 12)

        #expect(accumulator.consume(
            deltaY: 5,
            isPrecise: true,
            isMomentum: false,
            phase: .began,
            timestamp: 1
        ) == 0)
        #expect(accumulator.remainder == 5)
        #expect(accumulator.consume(
            deltaY: -1,
            isPrecise: true,
            isMomentum: false,
            phase: .changed,
            timestamp: 1.01
        ) == 0)
        #expect(accumulator.remainder == -1)

        #expect(accumulator.consume(
            deltaY: 0,
            isPrecise: true,
            isMomentum: false,
            phase: .ended,
            timestamp: 1.02
        ) == 0)
        #expect(accumulator.remainder == 0)

        #expect(accumulator.consume(
            deltaY: 6,
            isPrecise: true,
            isMomentum: false,
            timestamp: 2
        ) == 0)
        #expect(accumulator.remainder == 6)
        #expect(accumulator.consume(
            deltaY: 6,
            isPrecise: true,
            isMomentum: false,
            timestamp: 2.3
        ) == 0)
        #expect(accumulator.remainder == 6)

        #expect(accumulator.consume(
            deltaY: 10_000,
            isPrecise: true,
            isMomentum: false,
            timestamp: 2.31
        ) == -AtlasSliceScrollAccumulator.defaultMaximumStepsPerEvent)
        #expect(accumulator.remainder == 0)

        let invalidThreshold = AtlasSliceScrollAccumulator(preciseThreshold: .nan)
        #expect(
            invalidThreshold.preciseThreshold
                == AtlasSliceScrollAccumulator.defaultPreciseThreshold
        )
    }

    @Test("Invalid dimensions and nonfinite points fail closed")
    func invalidGeometry() {
        let viewport = AtlasSliceViewport(
            bounds: CGRect(x: 0, y: 0, width: 100, height: 100),
            imagePixelWidth: 0,
            imagePixelHeight: 100,
            zoom: 1,
            pan: .zero
        )
        #expect(viewport.aspectFitImageRect == nil)
        #expect(viewport.displayedImageRect == nil)
        #expect(viewport.pixel(at: CGPoint(x: 50, y: 50)) == nil)

        let valid = AtlasSliceViewport(
            bounds: CGRect(x: 0, y: 0, width: 100, height: 100),
            imagePixelWidth: 10,
            imagePixelHeight: 10,
            zoom: 1,
            pan: .zero,
            contentInset: 0
        )
        #expect(valid.pixel(at: CGPoint(x: CGFloat.nan, y: 50)) == nil)
        #expect(valid.pixel(at: CGPoint(x: 50, y: CGFloat.infinity)) == nil)
    }
}
