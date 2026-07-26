import AppKit
import Brain3DCore
import CoreGraphics
import Foundation
import Testing
@testable import Brain3DApp

@Suite("Cached atlas vessel raster")
struct AtlasSliceRasterizerTests {
    @Test("A physical segment becomes a transparent, correctly sized vessel raster")
    func segmentRaster() throws {
        let overlay = MajorVesselSliceOverlay(
            orientation: .horizontal,
            sliceIndex: -1,
            assetSHA256: String(repeating: "a", count: 64),
            inPlaneResolutionMicrometres: 25,
            segments: [
                MajorVesselSliceSegment(
                    start: ProbeSliceImagePoint(column: 2, row: 3),
                    end: ProbeSliceImagePoint(column: 8, row: 3),
                    startRadiusMicrometres: 20,
                    endRadiusMicrometres: 20,
                    sourceEdgeIndex: 1,
                    runIndex: 0,
                    segmentIndexInRun: 0
                ),
            ]
        )

        let result = try #require(MajorVesselRasterizer.render(
            overlay: overlay,
            imagePixelWidth: 12,
            imagePixelHeight: 10
        ))
        #expect(result.logicalWidth == 12)
        #expect(result.logicalHeight == 10)
        #expect(result.image.width == 12)
        #expect(result.image.height == 10)

        let bytes = try rgbaBytes(result.image)
        #expect(alpha(in: bytes, image: result.image, x: 5, y: 3) > 0)
        let core = rgba(in: bytes, image: result.image, x: 5, y: 3)
        #expect(core.red > 220)
        #expect(Int(core.red) > Int(core.green) * 4)
        #expect(Int(core.red) > Int(core.blue) * 6)
        #expect(alpha(in: bytes, image: result.image, x: 0, y: 9) == 0)
    }

    @Test("Invalid raster inputs fail closed")
    func invalidInputs() {
        let invalid = MajorVesselSliceOverlay(
            orientation: .coronal,
            sliceIndex: 0,
            assetSHA256: "asset",
            inPlaneResolutionMicrometres: .nan,
            segments: []
        )
        #expect(MajorVesselRasterizer.render(
            overlay: invalid,
            imagePixelWidth: 12,
            imagePixelHeight: 10
        ) == nil)
        #expect(MajorVesselRasterizer.render(
            overlay: invalid,
            imagePixelWidth: 0,
            imagePixelHeight: 10
        ) == nil)
    }

    private func rgbaBytes(_ image: CGImage) throws -> [UInt8] {
        let provider = try #require(image.dataProvider)
        let data = try #require(provider.data)
        return Array(Data(referencing: data))
    }

    private func alpha(
        in bytes: [UInt8],
        image: CGImage,
        x: Int,
        y: Int
    ) -> UInt8 {
        bytes[y * image.bytesPerRow + x * 4 + 3]
    }

    private func rgba(
        in bytes: [UInt8],
        image: CGImage,
        x: Int,
        y: Int
    ) -> (red: UInt8, green: UInt8, blue: UInt8, alpha: UInt8) {
        let offset = y * image.bytesPerRow + x * 4
        return (
            bytes[offset],
            bytes[offset + 1],
            bytes[offset + 2],
            bytes[offset + 3]
        )
    }
}

@Suite("Atlas viewer interaction policy")
struct AtlasViewerInteractionPolicyTests {
    @Test("Only the current authoritative displayed slice accepts a region pick")
    func authoritativePickGate() {
        #expect(ViewerInteractionPolicy.allowsRegionPick(
            orientation: .coronal,
            displayedSliceIndex: 17,
            authoritativeSliceIndex: 17,
            pendingSliceOrientation: nil,
            atomicNavigationInProgress: false
        ))
        #expect(!ViewerInteractionPolicy.allowsRegionPick(
            orientation: .coronal,
            displayedSliceIndex: 17,
            authoritativeSliceIndex: 18,
            pendingSliceOrientation: nil,
            atomicNavigationInProgress: false
        ))
        #expect(!ViewerInteractionPolicy.allowsRegionPick(
            orientation: .coronal,
            displayedSliceIndex: 17,
            authoritativeSliceIndex: 17,
            pendingSliceOrientation: .coronal,
            atomicNavigationInProgress: false
        ))
        #expect(!ViewerInteractionPolicy.allowsRegionPick(
            orientation: .coronal,
            displayedSliceIndex: 17,
            authoritativeSliceIndex: 17,
            pendingSliceOrientation: nil,
            atomicNavigationInProgress: true
        ))
    }

    @Test("A pending slice in another orientation does not block the visible slice")
    func otherOrientationPendingStillAllowsPick() {
        #expect(ViewerInteractionPolicy.allowsRegionPick(
            orientation: .sagittal,
            displayedSliceIndex: 23,
            authoritativeSliceIndex: 23,
            pendingSliceOrientation: .coronal,
            atomicNavigationInProgress: false
        ))
    }

    @Test("A superseded region pick cannot replace the visible selection")
    func supersededRegionPickDoesNotPublish() {
        var visibleSelection: String? = "current"
        let staleWasPublished = ViewerMutationPublicationPolicy.publishRegionSelection(
            "stale" as String?,
            requestGeneration: 4,
            currentGeneration: 5,
            into: &visibleSelection
        )
        #expect(!staleWasPublished)
        #expect(visibleSelection == "current")

        let latestWasPublished = ViewerMutationPublicationPolicy.publishRegionSelection(
            "latest" as String?,
            requestGeneration: 5,
            currentGeneration: 5,
            into: &visibleSelection
        )

        #expect(latestWasPublished)
        #expect(visibleSelection == "latest")
    }

    @Test("A superseded orientation response still retains its canonical pixels")
    func supersededOrientationRetainsFrame() {
        var frames = TriPlanarFrameSet()
        frames[.coronal] = frame(.coronal, index: 10)
        frames[.sagittal] = frame(.sagittal, index: 20)

        let coronalWasLatest = ViewerMutationPublicationPolicy.publishSlice(
            frame(.coronal, index: 11),
            requestGeneration: 1,
            currentGeneration: 2,
            into: &frames
        )
        let sagittalWasLatest = ViewerMutationPublicationPolicy.publishSlice(
            frame(.sagittal, index: 21),
            requestGeneration: 2,
            currentGeneration: 2,
            into: &frames
        )

        #expect(!coronalWasLatest)
        #expect(sagittalWasLatest)
        #expect(frames.coronal?.index == 11)
        #expect(frames.sagittal?.index == 21)
    }

    @Test("A depth change refreshes only its view and retains the shared region")
    func regionOverlayDepthRefreshCoherence() throws {
        let selected = try region(
            structureId: 549,
            acronym: "TH",
            name: "Thalamus"
        )
        let other = try region(
            structureId: 385,
            acronym: "VISp",
            name: "Primary visual area"
        )

        #expect(
            AtlasRegionOverlayRefreshPolicy.targets(afterSliceChange: .sagittal)
                == [.sagittal]
        )
        #expect(AtlasRegionOverlayRefreshPolicy.accepts(
            candidateRegion: selected,
            candidateIndex: 231,
            selectedRegion: selected,
            displayedIndex: 231
        ))
        #expect(!AtlasRegionOverlayRefreshPolicy.accepts(
            candidateRegion: selected,
            candidateIndex: 230,
            selectedRegion: selected,
            displayedIndex: 231
        ))
        #expect(!AtlasRegionOverlayRefreshPolicy.accepts(
            candidateRegion: other,
            candidateIndex: 231,
            selectedRegion: selected,
            displayedIndex: 231
        ))
    }

    private func frame(
        _ orientation: AtlasSliceOrientation,
        index: Int
    ) -> VerifiedAtlasSliceFrame {
        let axes: (
            fixed: AtlasAnatomicalAxis,
            row: AtlasAnatomicalAxis,
            column: AtlasAnatomicalAxis
        ) = switch orientation {
        case .coronal: (.ap, .dv, .ml)
        case .sagittal: (.ml, .dv, .ap)
        case .horizontal: (.dv, .ap, .ml)
        }
        return VerifiedAtlasSliceFrame(
            orientation: orientation,
            index: index,
            sliceCount: 100,
            width: 20,
            height: 10,
            fixedAxis: axes.fixed,
            rowAxis: axes.row,
            columnAxis: axes.column,
            sliceCenterMicrometres: Double(index) * 25 + 12.5,
            png: Data([UInt8(index & 0xFF)])
        )
    }

    private func region(
        structureId: Int,
        acronym: String,
        name: String
    ) throws -> AtlasRegionSummary {
        try JSONDecoder().decode(
            AtlasRegionSummary.self,
            from: JSONSerialization.data(withJSONObject: [
                "structureId": structureId,
                "acronym": acronym,
                "name": name,
                "parentStructureId": 997,
                "structureIdPath": [997, structureId],
                "rgb": [255, 112, 128],
            ])
        )
    }
}

@Suite("Atlas canvas anatomical orientation labels")
struct AtlasCanvasAnatomicalLabelTests {
    @Test("Dorsal and horizontal preserve anterior-posterior and right-left edges")
    func dorsalAndHorizontal() {
        #expect(AtlasCanvasAnatomicalLabels.dorsal == AtlasCanvasAnatomicalLabels(
            top: "A",
            bottom: "P",
            left: "R",
            right: "L"
        ))
        #expect(AtlasCanvasAnatomicalLabels.slice(.horizontal) == .dorsal)
    }

    @Test("Coronal and sagittal labels preserve laterality and depth")
    func coronalAndSagittal() {
        #expect(AtlasCanvasAnatomicalLabels.slice(.coronal) == AtlasCanvasAnatomicalLabels(
            top: "D",
            bottom: "V",
            left: "R",
            right: "L"
        ))
        #expect(AtlasCanvasAnatomicalLabels.slice(.sagittal) == AtlasCanvasAnatomicalLabels(
            top: "D",
            bottom: "V",
            left: "A",
            right: "P"
        ))
    }

    @Test("Accessible orientation text expands every edge label")
    func accessibilityDescription() {
        #expect(AtlasCanvasAnatomicalLabels.dorsal.accessibilityDescription ==
            "Anatomical orientation: anterior at top, posterior at bottom, "
                + "right at left edge, and left at right edge.")
    }
}

@Suite("Atlas canvas rendered coordinate direction")
struct AtlasCanvasRenderedDirectionTests {
    @Test("A posterior-left implant site renders below and screen-right of centre")
    @MainActor
    func posteriorLeftImplantSite() throws {
        let imageSize = 100
        let view = AtlasSliceNSView(
            frame: NSRect(x: 0, y: 0, width: 260, height: 260)
        )
        let overlay = ProbeSliceOverlay(
            orientation: .horizontal,
            sliceIndex: 0,
            markers: [
                ProbeSliceMarker(
                    id: "implant-site:posterior-left",
                    role: .implantSite,
                    label: "AP− / ML−",
                    imagePoint: ProbeSliceImagePoint(column: 75, row: 75)
                ),
            ],
            shankIntersections: []
        )
        view.configure(
            imageData: try solidPNG(width: imageSize, height: imageSize),
            regionOverlayData: nil,
            imagePixelWidth: imageSize,
            imagePixelHeight: imageSize,
            viewportIdentity: "direction-test",
            anatomicalLabels: .dorsal,
            selection: nil,
            majorVesselOverlay: nil,
            majorVesselConflictOverlay: nil,
            probeOverlay: overlay,
            interactionHelp: "Direction test",
            accessibilityLabel: "Direction test",
            accessibilityValue: "Direction test",
            resetGeneration: 0,
            onPick: { _, _ in },
            onSliceStep: { _ in }
        )

        let rendered = try render(view)
        let pinkPixels = try matchingPixels(in: rendered) { red, green, blue, alpha in
            alpha > 200 && red > 180 && green < 145 && blue > 70
        }
        #expect(!pinkPixels.isEmpty)
        let meanX = pinkPixels.map(\.x).reduce(0, +) / pinkPixels.count
        let meanY = pinkPixels.map(\.y).reduce(0, +) / pinkPixels.count
        #expect(meanX > rendered.width / 2)
        #expect(meanY > rendered.height / 2)
    }

    @Test("Annotation region RGBA is visibly composited over the atlas pixels")
    @MainActor
    func regionOverlayComposition() throws {
        let imageSize = 40
        let view = AtlasSliceNSView(
            frame: NSRect(x: 0, y: 0, width: 240, height: 240)
        )
        view.configure(
            imageData: try solidPNG(width: imageSize, height: imageSize),
            regionOverlayData: try regionOverlayPNG(
                width: imageSize,
                height: imageSize
            ),
            imagePixelWidth: imageSize,
            imagePixelHeight: imageSize,
            viewportIdentity: "region-overlay-test",
            anatomicalLabels: .dorsal,
            selection: nil,
            majorVesselOverlay: nil,
            majorVesselConflictOverlay: nil,
            probeOverlay: nil,
            interactionHelp: "Region overlay test",
            accessibilityLabel: "Region overlay test",
            accessibilityValue: "Selected thalamus",
            resetGeneration: 0,
            onPick: { _, _ in },
            onSliceStep: { _ in }
        )

        let rendered = try render(view)
        let selectedPixels = try matchingPixels(in: rendered) {
            red, green, blue, alpha in
            alpha > 200
                && green > 130
                && Int(green) > Int(red) * 2
                && green > blue
        }
        #expect(selectedPixels.count > 1_000)
        #expect(selectedPixels.count < rendered.width * rendered.height / 2)
    }

    @MainActor
    private func render(_ view: NSView) throws -> CGImage {
        let representation = try #require(
            view.bitmapImageRepForCachingDisplay(in: view.bounds)
        )
        view.cacheDisplay(in: view.bounds, to: representation)
        return try #require(representation.cgImage)
    }

    @MainActor
    private func solidPNG(width: Int, height: Int) throws -> Data {
        let representation = try #require(NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: width,
            pixelsHigh: height,
            bitsPerSample: 8,
            samplesPerPixel: 4,
            hasAlpha: true,
            isPlanar: false,
            colorSpaceName: .deviceRGB,
            bytesPerRow: 0,
            bitsPerPixel: 0
        ))
        let context = try #require(NSGraphicsContext(bitmapImageRep: representation))
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context
        NSColor(calibratedWhite: 0.12, alpha: 1).setFill()
        NSRect(x: 0, y: 0, width: width, height: height).fill()
        context.flushGraphics()
        NSGraphicsContext.restoreGraphicsState()
        return try #require(representation.representation(using: .png, properties: [:]))
    }

    @MainActor
    private func regionOverlayPNG(width: Int, height: Int) throws -> Data {
        let representation = try #require(NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: width,
            pixelsHigh: height,
            bitsPerSample: 8,
            samplesPerPixel: 4,
            hasAlpha: true,
            isPlanar: false,
            colorSpaceName: .deviceRGB,
            bytesPerRow: 0,
            bitsPerPixel: 0
        ))
        let context = try #require(NSGraphicsContext(bitmapImageRep: representation))
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context
        NSColor.clear.setFill()
        NSRect(x: 0, y: 0, width: width, height: height).fill()
        NSColor(
            srgbRed: 0.08,
            green: 0.85,
            blue: 0.28,
            alpha: 0.9
        ).setFill()
        NSRect(
            x: width / 4,
            y: height / 4,
            width: width / 2,
            height: height / 2
        ).fill()
        context.flushGraphics()
        NSGraphicsContext.restoreGraphicsState()
        return try #require(representation.representation(using: .png, properties: [:]))
    }

    private func matchingPixels(
        in image: CGImage,
        predicate: (_ red: UInt8, _ green: UInt8, _ blue: UInt8, _ alpha: UInt8) -> Bool
    ) throws -> [(x: Int, y: Int)] {
        let bytesPerRow = image.width * 4
        var bytes = [UInt8](repeating: 0, count: bytesPerRow * image.height)
        let context = try #require(CGContext(
            data: &bytes,
            width: image.width,
            height: image.height,
            bitsPerComponent: 8,
            bytesPerRow: bytesPerRow,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ))
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))

        var matches: [(x: Int, y: Int)] = []
        for y in 0 ..< image.height {
            for x in 0 ..< image.width {
                let offset = y * bytesPerRow + x * 4
                if predicate(
                    bytes[offset],
                    bytes[offset + 1],
                    bytes[offset + 2],
                    bytes[offset + 3]
                ) {
                    matches.append((x, y))
                }
            }
        }
        return matches
    }
}
