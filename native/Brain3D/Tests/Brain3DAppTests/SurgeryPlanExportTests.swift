import AppKit
import Brain3DCore
import CryptoKit
import Foundation
import PDFKit
import Testing
@testable import Brain3DApp

@Suite("Surgery plan export contracts", .serialized)
struct SurgeryPlanExportTests {
    @Test("Single-view and All selections preserve the requested page order")
    func viewSelection() {
        #expect(SurgeryPlanViewSelection.dorsal.views == [.dorsal])
        #expect(SurgeryPlanViewSelection.coronal.views == [.coronal])
        #expect(SurgeryPlanViewSelection.sagittal.views == [.sagittal])
        #expect(SurgeryPlanViewSelection.horizontal.views == [.horizontal])
        #expect(SurgeryPlanViewSelection.threeDimensional.views == [.threeDimensional])
        #expect(
            SurgeryPlanViewSelection.all.views
                == [.dorsal, .coronal, .sagittal, .horizontal, .threeDimensional]
        )
        #expect(SurgeryPlanViewSelection.all.views == SurgeryPlanView.allCases)
    }

    @Test("Surface plan text preserves the four operator inputs")
    func surfacePlanPrefillText() {
        let prefill = makeSurfacePrefill()

        #expect(
            prefill.targetCoordinateText
                == "AP -1.250 mm · ML +0.800 mm · depth 2.300 mm from local atlas surface"
        )
        #expect(prefill.templateAngleText == "A↔P +20.0° (A→P)")
        #expect(prefill.probeText.contains("depth 2.300 mm from surface"))
        #expect(prefill.probeText.contains("A↔P +20.0° (A→P)"))
        #expect(prefill.probeText.contains("layout 90° CW from dorsal"))
        #expect(!prefill.probeText.contains("Az "))
        #expect(!prefill.probeText.contains("El "))
        #expect(!prefill.probeText.contains("Roll "))
        #expect(
            prefill.probeReviewText?.contains(
                "source-transcribed-review-pending"
            ) == true
        )
        #expect(
            prefill.surfaceProvenanceText?.contains("annotation 2222222222…")
                == true
        )
        #expect(
            SurgeryPlanSurfaceAnglePresentation.text(0)
                == "A↔P 0.0° (vertical)"
        )
        #expect(
            SurgeryPlanSurfaceAnglePresentation.text(-20)
                == "A↔P -20.0° (P→A)"
        )
        let audit = SurgeryPlanPacketRenderer.auditManifest(
            prefill: prefill,
            pageCount: 4,
            targetId: "plan-1",
            vesselAssetSHA256: String(repeating: "3", count: 64),
            protocolTemplateSHA256: String(repeating: "4", count: 64),
            atlasSourceSHA256: String(repeating: "5", count: 64)
        )
        #expect(audit.contains("PI:1111111111"))
        #expect(audit.contains("AN:2222222222"))
        #expect(
            audit.contains(
                "BR:\(ProbePlanningContract.surfaceBregmaSourceSHA256.prefix(10))"
            )
        )
    }

    @MainActor
    @Test("The consolidated PDF resolves to exactly 132 canonical pages")
    func atlasCatalog() async throws {
        let atlasPDF = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: atlasPDF) }

        let plates = try SurgeryAtlasCatalog.plates(in: atlasPDF)

        #expect(plates.count == 132)
        #expect(Set(plates.map(\.figure)) == Set(1 ... 132))
        #expect(plates.filter { $0.orientation == .coronal }.count == 100)
        #expect(plates.filter { $0.orientation == .sagittal }.count == 32)
        #expect(plates.allSatisfy { $0.sourceURL == atlasPDF })

        let figure39 = try #require(plates.first { $0.figure == 39 })
        let snapshot = try await SurgeryAtlasPDFSource.shared.capture(figure39)
        #expect(snapshot.sourcePDF.starts(with: Data("%PDF-".utf8)))
        #expect(snapshot.sha256.count == 64)
        let capturedDocument = try #require(PDFDocument(data: snapshot.sourcePDF))
        #expect(capturedDocument.pageCount == 132)
    }

    @MainActor
    @Test("Every page of the available 132-page atlas resolves its own coordinate map")
    func everyAtlasPageResolvesCoordinateMap() throws {
        let syntheticURL = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: syntheticURL) }
        var sources = [syntheticURL]
        let realAtlasURL = URL(
            fileURLWithPath:
                "/Volumes/senzailab/Shared/Books/The Mouse Brain CD/MBSC_Figs_with_Layers.pdf"
        )
        if FileManager.default.isReadableFile(atPath: realAtlasURL.path) {
            sources.append(realAtlasURL)
        }

        for sourceURL in sources {
            let document = try #require(PDFDocument(url: sourceURL))
            let plates = try SurgeryAtlasCatalog.plates(in: sourceURL)
            #expect(document.pageCount == 132)
            #expect(plates.count == 132)
            for plate in plates {
                let page = try #require(document.page(at: plate.figure - 1))
                do {
                    let map = try SurgeryAtlasCoordinateMap.historicalAtlas(
                        page: page,
                        plate: plate
                    )
                    #expect(map.orientation == plate.orientation)
                    #expect(!map.plotRect.isEmpty)
                    #expect(SurgeryAtlasCoordinateMap.viewBox.contains(map.plotRect))
                    #expect(map.horizontalPointsPerMillimetre.isFinite)
                    #expect(map.horizontalPointsPerMillimetre > 0)
                    #expect(map.dvPointsPerMillimetre.isFinite)
                    #expect(map.dvPointsPerMillimetre > 0)
                } catch {
                    Issue.record(
                        "\(sourceURL.lastPathComponent) Figure \(plate.figure): \(error)"
                    )
                }
            }
        }
    }

    @MainActor
    @Test("Direct atlas page retains source artwork and adds only the probe overlay")
    func directAtlasPageRetainsSourceArtworkAndProbeOverlay() throws {
        let atlasPDF = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: atlasPDF) }
        let plate = try #require(
            SurgeryAtlasCatalog.canonicalPlates(sourceURL: atlasPDF)
                .first { $0.figure == 39 }
        )
        let fixture = try makeOverlayFixture(
            modelProductCode: "NP2013",
            apMillimetres: -1.25,
            mlMillimetres: -0.8,
            depthMillimetres: 2.3,
            angleDegrees: -20,
            layoutDegrees: 90
        )
        let rendered = try SurgeryAtlasPageRenderer.overlay(
            atlasPDF: Data(contentsOf: atlasPDF),
            plan: fixture.plan,
            prefill: fixture.prefill,
            plate: plate
        )
        let document = try #require(PDFDocument(data: rendered))
        let text = document.string ?? ""

        #expect(document.pageCount == 1)
        #expect(document.page(at: 0)?.bounds(for: .mediaBox).size == CGSize(width: 792, height: 612))
        #expect(text.localizedCaseInsensitiveContains("Figure 39"))
        #expect(text.localizedCaseInsensitiveContains("Bregma -0.94 mm"))
        #expect(!text.contains("DRAFT"))
        #expect(!text.contains("Brain3D-"))
        #expect(!text.contains("source-transcribed-review-pending"))
        #expect(!text.contains("annotation 2222222222"))
        #expect(!text.contains("Urchin@57be3cdc7d62"))
        #expect(!text.contains("Historical plate"))
    }

    @MainActor
    @Test("Direct atlas page never prints draft, provenance, or audit text")
    func directAtlasPageOmitsDraftProvenanceAndAuditText() throws {
        let atlasPDF = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: atlasPDF) }
        let plate = try #require(
            SurgeryAtlasCatalog.canonicalPlates(sourceURL: atlasPDF)
                .first { $0.figure == 39 }
        )
        let fixture = try makeOverlayFixture(
            modelProductCode: "NP2013",
            apMillimetres: -1.25,
            mlMillimetres: -0.8,
            depthMillimetres: 2.3,
            angleDegrees: 0,
            layoutDegrees: 0,
            bregmaSourceRevision: String(repeating: "r", count: 300)
        )
        let provenance = try #require(fixture.prefill.surfaceProvenanceText)
        #expect(provenance.contains("…#"))
        #expect(!provenance.contains(String(repeating: "r", count: 300)))

        let rendered = try SurgeryAtlasPageRenderer.overlay(
            atlasPDF: Data(contentsOf: atlasPDF),
            plan: fixture.plan,
            prefill: fixture.prefill,
            plate: plate
        )
        let document = try #require(PDFDocument(data: rendered))
        let normalizedText = (document.string ?? "")
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")
        #expect(!normalizedText.contains(provenance))
        #expect(!normalizedText.localizedCaseInsensitiveContains("draft"))
        #expect(!normalizedText.localizedCaseInsensitiveContains("provenance"))
        #expect(!normalizedText.localizedCaseInsensitiveContains("audit"))
        #expect(!normalizedText.contains("Brain3D-"))
    }

    @MainActor
    @Test("Atlas overlay preserves nonzero MediaBox source corners")
    func atlasOverlayPreservesNonzeroMediaBoxCorners() throws {
        let atlasPDF = try makeAtlasPDF(
            mediaBoxOrigin: CGPoint(x: 71.5, y: 198.5),
            sentinelFigure: 39
        )
        defer { try? FileManager.default.removeItem(at: atlasPDF) }
        let plate = try #require(
            SurgeryAtlasCatalog.canonicalPlates(sourceURL: atlasPDF)
                .first { $0.figure == 39 }
        )
        let fixture = try makeOverlayFixture(
            modelProductCode: "NP2013",
            apMillimetres: -1.25,
            mlMillimetres: -0.8,
            depthMillimetres: 2.3,
            angleDegrees: 0,
            layoutDegrees: 0
        )
        let rendered = try SurgeryAtlasPageRenderer.overlay(
            atlasPDF: Data(contentsOf: atlasPDF),
            plan: fixture.plan,
            prefill: fixture.prefill,
            plate: plate
        )
        let document = try #require(PDFDocument(data: rendered))
        let page = try #require(document.page(at: 0))
        let topSelection = try #require(
            document.findString("TOPLEFTSENTINEL", withOptions: []).first
        )
        let bottomSelection = try #require(
            document.findString("BOTTOMRIGHTSENTINEL", withOptions: []).first
        )
        let topBounds = topSelection.bounds(for: page)
        let bottomBounds = bottomSelection.bounds(for: page)

        #expect(page.bounds(for: .mediaBox) == CGRect(x: 0, y: 0, width: 792, height: 612))
        #expect(topBounds.minX >= 0)
        #expect(topBounds.minX < 100)
        #expect(topBounds.maxY > 520)
        #expect(bottomBounds.maxX > 700)
        #expect(bottomBounds.maxX <= 792)
        #expect(bottomBounds.minY >= 0)
        #expect(bottomBounds.minY < 80)
    }

    @Test("NP2003 and NP2013 emit complete one-line and four-line SVG overlays")
    func probeOverlaySVGLineCountsAndCoordinateRow() throws {
        let cases = [(model: "NP2003", count: 1), (model: "NP2013", count: 4)]
        for testCase in cases {
            let fixture = try makeOverlayFixture(
                modelProductCode: testCase.model,
                apMillimetres: -1.25,
                mlMillimetres: -0.8,
                depthMillimetres: 2.3,
                angleDegrees: 0,
                layoutDegrees: 0
            )
            let plate = try testAtlasPlate(.sagittal)
            let map = try testCoordinateMap(.sagittal)
            let overlay = try SurgeryAtlasProbeOverlay(
                plan: fixture.plan,
                prefill: fixture.prefill,
                plate: plate,
                coordinateMap: map
            )
            let xml = try XMLDocument(data: overlay.svgData, options: [])
            let root = try #require(xml.rootElement())
            let paths = try xml.nodes(
                forXPath: "//*[local-name()='path' and starts-with(@id,'shank-')]"
            )
            let coordinateNodes = try xml.nodes(
                forXPath: "//*[@id='probe-coordinates']"
            )
            let allTextNodes = try xml.nodes(
                forXPath: "//*[local-name()='text']"
            )

            #expect(root.name == "svg")
            #expect(root.attribute(forName: "width")?.stringValue == "792")
            #expect(root.attribute(forName: "height")?.stringValue == "612")
            #expect(root.attribute(forName: "viewBox")?.stringValue == "0 0 792 612")
            #expect(paths.count == testCase.count)
            #expect(overlay.shanks.count == testCase.count)
            #expect(coordinateNodes.count == 1)
            #expect(allTextNodes.count == 1)
            #expect(try xml.nodes(forXPath: "//*[local-name()='line']").isEmpty)
            #expect(try xml.nodes(forXPath: "//*[@id='layout-schematic']").isEmpty)
            #expect(
                coordinateNodes.first?.stringValue
                    == "AP -1.250 mm · ML -0.800 mm · depth 2.300 mm · "
                    + "angle +0.0° (vertical) · layout 0° sagittal"
            )
            #expect(!overlay.svgString.contains("<image"))
            #expect(!overlay.svgString.localizedCaseInsensitiveContains("draft"))
            #expect(!overlay.svgString.localizedCaseInsensitiveContains("provenance"))
            #expect(!overlay.svgString.localizedCaseInsensitiveContains("audit"))
            #expect(!overlay.svgString.contains("source-transcribed-review-pending"))
            #expect(!overlay.svgString.contains("Brain3D-"))
            #expect(
                overlay.svgString.range(
                    of: #"\b[0-9a-fA-F]{16,}\b"#,
                    options: .regularExpression
                ) == nil
            )
            #expect(!overlay.svgString.lowercased().contains("nan"))
            #expect(!overlay.svgString.lowercased().contains("infinity"))

            for (index, shank) in overlay.shanks.enumerated() {
                #expect(shank.id == "shank-\(index + 1)")
                #expect(!shank.svgPathData.isEmpty)
                #expect(!shank.clippedSegments.isEmpty)
                #expect(shank.projectedProximalEnd != shank.projectedSurfaceAnchor)
                #expect(shank.projectedSurfaceAnchor != shank.projectedTip)
                #expect(shank.projectedProximalEnd.y < map.plotRect.minY)
                #expect(map.plotRect.contains(shank.projectedSurfaceAnchor))
                #expect(map.plotRect.contains(shank.projectedTip))
                #expect(pointIsFinite(shank.projectedProximalEnd))
                #expect(pointIsFinite(shank.projectedSurfaceAnchor))
                #expect(pointIsFinite(shank.projectedTip))
            }
        }
    }

    @Test("Negative ML and AP project page-right from the surface insertion site")
    func probeOverlayCoordinateDirections() throws {
        let fixture = try makeOverlayFixture(
            modelProductCode: "NP2003",
            apMillimetres: -1.25,
            mlMillimetres: -0.8,
            depthMillimetres: 2.3,
            angleDegrees: 0,
            layoutDegrees: 0
        )
        let coronalMap = try testCoordinateMap(.coronal)
        let coronal = try SurgeryAtlasProbeOverlay(
            plan: fixture.plan,
            prefill: fixture.prefill,
            plate: testAtlasPlate(.coronal),
            coordinateMap: coronalMap
        )
        let sagittalMap = try testCoordinateMap(.sagittal)
        let sagittal = try SurgeryAtlasProbeOverlay(
            plan: fixture.plan,
            prefill: fixture.prefill,
            plate: testAtlasPlate(.sagittal),
            coordinateMap: sagittalMap
        )
        let coronalShank = try #require(coronal.shanks.first)
        let sagittalShank = try #require(sagittal.shanks.first)

        #expect(coronalShank.projectedSurfaceAnchor.x > coronalMap.horizontalZeroX)
        #expect(sagittalShank.projectedSurfaceAnchor.x > sagittalMap.horizontalZeroX)
        #expect(abs(coronalShank.projectedSurfaceAnchor.x - 436) < 0.001)
        #expect(abs(sagittalShank.projectedSurfaceAnchor.x - 458.5) < 0.001)
        #expect(coronalShank.projectedTip.x == coronalShank.projectedSurfaceAnchor.x)
        #expect(sagittalShank.projectedTip.x == sagittalShank.projectedSurfaceAnchor.x)
        #expect(coronalShank.projectedTip.y > coronalShank.projectedSurfaceAnchor.y)
        #expect(sagittalShank.projectedTip.y > sagittalShank.projectedSurfaceAnchor.y)
    }

    @MainActor
    @Test("Collapsed four-shank projections display four centered paths without a legend")
    func collapsedProjectionUsesCenteredDisplayOffsets() throws {
        let fixture = try makeOverlayFixture(
            modelProductCode: "NP2013",
            apMillimetres: -1.25,
            mlMillimetres: -0.8,
            depthMillimetres: 2.3,
            angleDegrees: 0,
            layoutDegrees: 0
        )
        let coronal = try SurgeryAtlasProbeOverlay(
            plan: fixture.plan,
            prefill: fixture.prefill,
            plate: testAtlasPlate(.coronal),
            coordinateMap: testCoordinateMap(.coronal)
        )
        let sagittal = try SurgeryAtlasProbeOverlay(
            plan: fixture.plan,
            prefill: fixture.prefill,
            plate: testAtlasPlate(.sagittal),
            coordinateMap: testCoordinateMap(.sagittal)
        )
        let coronalXML = try XMLDocument(data: coronal.svgData, options: [])
        let coronalPaths = try coronalXML.nodes(
            forXPath: "//*[local-name()='path' and starts-with(@id,'shank-')]"
        ).compactMap { $0 as? XMLElement }
        let offsets = try coronalPaths.map { path -> CGPoint in
            let x = try #require(
                Double(path.attribute(forName: "data-display-offset-x")?.stringValue ?? "")
            )
            let y = try #require(
                Double(path.attribute(forName: "data-display-offset-y")?.stringValue ?? "")
            )
            return CGPoint(x: x, y: y)
        }

        #expect(coronal.projectedPathsCollapse)
        #expect(coronal.shanks.count == 4)
        #expect(Set(coronal.shanks.map(\.svgPathData)).count == 1)
        #expect(coronalPaths.count == 4)
        #expect(
            Set(coronalPaths.compactMap {
                $0.attribute(forName: "d")?.stringValue
            }).count == 1
        )
        #expect(
            Set(coronalPaths.compactMap {
                $0.attribute(forName: "transform")?.stringValue
            }).count == 4
        )
        #expect(
            coronalPaths.allSatisfy {
                $0.attribute(forName: "data-projection-display")?.stringValue
                    == "offset-only"
            }
        )
        #expect(offsets.allSatisfy { $0.x.isFinite && $0.y.isFinite })
        #expect(abs(offsets.reduce(0) { $0 + $1.x }) < 0.001)
        #expect(abs(offsets.reduce(0) { $0 + $1.y }) < 0.001)
        #expect(try coronalXML.nodes(forXPath: "//*[@id='layout-schematic']").isEmpty)
        #expect(try coronalXML.nodes(forXPath: "//*[local-name()='line']").isEmpty)
        #expect(try coronalXML.nodes(forXPath: "//*[local-name()='text']").count == 1)
        #expect(!coronal.svgString.contains("4-shank layout only"))
        #expect(!coronal.svgString.contains("Layout only — not registered"))
        #expect(
            try rasterizedProbePalettePixelCounts(coronal)
                .allSatisfy { $0 > 100 }
        )
        #expect(!sagittal.projectedPathsCollapse)
        #expect(!sagittal.svgString.contains("layout-schematic"))
    }

    @MainActor
    @Test("Atlas catalog rejects non-PDF and incomplete PDF sources")
    func atlasCatalogSourceValidation() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
            "Brain3D-SurgeryAtlasSourceTests-\(UUID().uuidString)",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: directory) }
        let nonPDF = directory.appendingPathComponent("atlas.txt")
        try Data("not a PDF".utf8).write(to: nonPDF)
        let incompletePDF = directory.appendingPathComponent("atlas.pdf")
        try vectorTextPDF(
            ["FIGURE 01 Bregma 4.28 mm Interaural 8.08 mm"],
            size: CGSize(width: 792, height: 612)
        ).write(to: incompletePDF)

        for source in [nonPDF, incompletePDF] {
            do {
                _ = try SurgeryAtlasCatalog.plates(in: source)
                Issue.record("Expected an invalid consolidated atlas source.")
            } catch SurgeryPlanExportError.invalidAtlasSource {
                // Expected.
            } catch {
                Issue.record("Unexpected atlas-source error: \(error)")
            }
        }
    }

    @Test("Animal record fields are bounded, single-line, and weight-checked")
    func animalRecordValidation() throws {
        let validated = try exportConfiguration(
            targetLabel: "  left V1  ",
            weightGrams: " 24.1 ",
            operatorName: " operator "
        ).validated()
        #expect(validated.targetLabel == "left V1")
        #expect(validated.weightGrams == "24.1")
        #expect(validated.operatorName == "operator")

        let invalidConfigurations = [
            exportConfiguration(targetLabel: "left\nV1"),
            exportConfiguration(targetLabel: String(repeating: "x", count: 81)),
            exportConfiguration(weightGrams: "0"),
            exportConfiguration(weightGrams: "-1"),
            exportConfiguration(weightGrams: "nan"),
            exportConfiguration(weightGrams: "201"),
            exportConfiguration(weightGrams: "mouse"),
        ]
        for configuration in invalidConfigurations {
            do {
                _ = try configuration.validated()
                Issue.record("Expected invalid animal-record input to be rejected.")
            } catch SurgeryPlanExportError.invalidAnimalRecord {
                // Expected.
            } catch {
                Issue.record("Unexpected animal-record error: \(error)")
            }
        }
    }

    @Test("Sagittal 0.36 mm resolves to Figure 104")
    @MainActor
    func nearestSagittalPlate() throws {
        let atlasPDF = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: atlasPDF) }
        let implant = try target(apMillimetres: -1.5, mlMillimetres: -0.36)

        let plate = try SurgeryAtlasCatalog.nearestPlate(
            in: atlasPDF,
            orientation: .sagittal,
            target: implant
        )

        #expect(plate.figure == 104)
        #expect(plate.orientation == .sagittal)
        #expect(plate.fixedCoordinateMillimetres == 0.36)
        #expect(plate.coordinateLabel == "Lateral 0.36 mm")
    }

    @Test("Coordinates outside either atlas axis are rejected")
    @MainActor
    func atlasRangeRejection() throws {
        let atlasPDF = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: atlasPDF) }

        do {
            _ = try SurgeryAtlasCatalog.nearestPlate(
                in: atlasPDF,
                orientation: .coronal,
                target: try target(apMillimetres: 4.5, mlMillimetres: 0)
            )
            Issue.record("Expected AP 4.5 mm to be rejected.")
        } catch SurgeryPlanExportError.atlasCoordinateOutsideRange(let coordinate) {
            #expect(coordinate.contains("AP"))
            #expect(coordinate.contains("+4.500"))
        } catch {
            Issue.record("Unexpected coronal range error: \(error)")
        }

        do {
            _ = try SurgeryAtlasCatalog.nearestPlate(
                in: atlasPDF,
                orientation: .sagittal,
                target: try target(apMillimetres: 0, mlMillimetres: -4.0)
            )
            Issue.record("Expected |ML| 4.0 mm to be rejected.")
        } catch SurgeryPlanExportError.atlasCoordinateOutsideRange(let coordinate) {
            #expect(coordinate.contains("|ML|"))
            #expect(coordinate.contains("+4.000"))
        } catch {
            Issue.record("Unexpected sagittal range error: \(error)")
        }
    }

    @Test("Atlas PDF text accepts historical spacing and coordinate quirks")
    func atlasPageTextCompatibility() {
        let sagittal = SurgeryAtlasPlate(
            figure: 101,
            orientation: .sagittal,
            fixedCoordinateMillimetres: -0.04,
            sourceURL: URL(fileURLWithPath: "/tmp/MBSC_Figs_with_Layers.pdf")
        )
        #expect(
            SurgeryAtlasPDFSource.validatesPageText(
                "Figure  101\nLateral -0.04",
                plate: sagittal
            )
        )
        #expect(
            SurgeryAtlasPDFSource.validatesPageText(
                "Figure 101   Lateral -0.04 mm",
                plate: sagittal
            )
        )
        #expect(
            !SurgeryAtlasPDFSource.validatesPageText(
                "Figure 101   Lateral 0.12",
                plate: sagittal
            )
        )

        let coronal = SurgeryAtlasPlate(
            figure: 58,
            orientation: .coronal,
            fixedCoordinateMillimetres: -3.28,
            sourceURL: URL(fileURLWithPath: "/tmp/MBSC_Figs_with_Layers.pdf")
        )
        #expect(
            SurgeryAtlasPDFSource.validatesPageText(
                "Figure 58\nBregma -3.28 mm\nInteraural 0.52 mm",
                plate: coronal
            )
        )
        #expect(
            !SurgeryAtlasPDFSource.validatesPageText(
                "Figure 58\nBregma -3.28 mm\nInteraural 0.50 mm",
                plate: coronal
            )
        )
        #expect(
            !SurgeryAtlasPDFSource.validatesPageText(
                "Figure 58\nBregma -3.40 mm\nInteraural 0.40 mm",
                plate: coronal
            )
        )

        let posteriorCoronal = SurgeryAtlasPlate(
            figure: 100,
            orientation: .coronal,
            fixedCoordinateMillimetres: -8.24,
            sourceURL: URL(fileURLWithPath: "/tmp/atlas.pdf")
        )
        #expect(
            SurgeryAtlasPDFSource.validatesPageText(
                "FIGURE 100\nBregma - 8.24 mm\nInteraural - 4.44 mm",
                plate: posteriorCoronal
            )
        )
    }

    @MainActor
    @Test("Protocol PDF overlay preserves two Letter pages and unit semantics")
    func protocolPDFOverlay() throws {
        let source = try vectorTextPDF([
            "protocol-source-page-one",
            "protocol-source-page-two",
            "atlas-placeholder-page-three",
        ])
        let prefill = makePrefill(
            azimuthDegrees: 0,
            elevationDegrees: 0
        )

        let rendered = try SurgeryProtocolPDFRenderer.overlay(
            protocolPDF: source,
            prefill: prefill
        )
        let document = try #require(PDFDocument(data: rendered))
        let firstPage = try #require(document.page(at: 0))
        let secondPage = try #require(document.page(at: 1))
        let firstText = firstPage.string ?? ""
        let secondText = secondPage.string ?? ""

        #expect(document.pageCount == 2)
        #expect(firstPage.bounds(for: .mediaBox).size == CGSize(width: 612, height: 792))
        #expect(secondPage.bounds(for: .mediaBox).size == CGSize(width: 612, height: 792))
        #expect(firstText.contains("protocol-source-page-one"))
        #expect(!firstText.contains("protocol-source-page-two"))
        #expect(secondText.contains("protocol-source-page-two"))
        #expect(!secondText.contains("protocol-source-page-one"))
        #expect(!(document.string ?? "").contains("atlas-placeholder-page-three"))
        #expect(firstText.contains("-1.250 mm"))
        #expect(firstText.contains("-0.800 mm"))
        #expect(firstText.contains("-2.400 mm"))
        #expect(firstText.contains("Az +0.0° · El +0.0°"))
        #expect(!secondText.contains("-1.250 mm"))
        #expect(!secondText.contains("Az +0.0°"))
    }

    @MainActor
    @Test("Protocol PDF verifies the exact rendered subject line")
    func protocolPDFLongSubjectVerification() throws {
        let source = try vectorTextPDF([
            "protocol-source-page-one",
            "protocol-source-page-two",
            "atlas-placeholder-page-three",
        ])
        let runtimeSubject = "brain3d-direction-qa-20260724"
        let truncatedSubject = String(repeating: "mouse-", count: 8)
        let cases = [
            (
                runtimeSubject,
                "Mouse / subject: \(runtimeSubject)"
            ),
            (
                truncatedSubject,
                "Mouse / subject: "
                    + String(truncatedSubject.prefix(29))
                    + "…"
            ),
        ]

        for (subjectId, expectedLine) in cases {
            let rendered = try SurgeryProtocolPDFRenderer.overlay(
                protocolPDF: source,
                prefill: makePrefill(
                    azimuthDegrees: 0,
                    elevationDegrees: -90,
                    subjectId: subjectId
                )
            )
            let document = try #require(PDFDocument(data: rendered))
            let firstPage = try #require(document.page(at: 0))

            #expect(firstPage.string?.contains(expectedLine) == true)
        }
    }

    @Test("Protocol header fields are width-bounded before drawing")
    func protocolHeaderFieldWidths() {
        let font = NSFont.systemFont(ofSize: 9, weight: .medium)
        let attributes: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.black,
        ]
        let cases = [
            ("Cage #: " + String(repeating: "W", count: 80), CGFloat(235)),
            ("Operator: " + String(repeating: "W", count: 80), CGFloat(270)),
            (
                "Mouse #: " + String(repeating: "W", count: 80)
                    + " · Weight: 200.0 g",
                CGFloat(520)
            ),
        ]

        for (text, maximumWidth) in cases {
            let fitted = SurgeryProtocolPDFRenderer.textFittedToWidth(
                text,
                maximumWidth: maximumWidth,
                attributes: attributes
            )
            let renderedWidth = NSAttributedString(
                string: fitted,
                attributes: attributes
            ).size().width
            #expect(fitted.hasSuffix("…"))
            #expect(renderedWidth <= maximumWidth)
        }
    }

    @MainActor
    @Test("Maximum identity fields cannot displace planning coordinates")
    func planningPageMaximumIdentityKeepsCoordinates() throws {
        let subjectId = String(repeating: "S", count: 200)
        let targetLabel = String(repeating: "T", count: 80)
        let prefill = makePrefill(
            azimuthDegrees: 0,
            elevationDegrees: -90,
            subjectId: subjectId,
            targetLabel: targetLabel
        )
        let visibleIdentity = SurgeryPlanningPageRenderer
            .fittedPlanningIdentityText(
                subjectId: subjectId,
                targetLabel: targetLabel,
                maximumWidth: 716
            )
        #expect(visibleIdentity.hasSuffix("…"))
        #expect(!visibleIdentity.contains(subjectId))

        let digest = String(repeating: "a", count: 64)
        let artifact = SurgeryPlanningViewArtifact(
            view: .dorsal,
            pngData: try solidPNG(),
            subtitle: "Allen atlas dorsal surface projection",
            vesselAssetSHA256: digest,
            vesselSegmentCount: 321,
            vesselScope: "dorsal depth projection",
            minimumVisibleVesselDiameterMicrometres: 50
        )
        let plate = SurgeryAtlasPlate(
            figure: 105,
            orientation: .sagittal,
            fixedCoordinateMillimetres: 0.48,
            sourceURL: URL(fileURLWithPath: "/tmp/MBSC_Figs_with_Layers.pdf")
        )
        let rendered = try SurgeryPlanningPageRenderer.render(
            artifact: artifact,
            prefill: prefill,
            atlasPlate: plate,
            atlasSourceSHA256: String(repeating: "b", count: 64),
            protocolSourceSHA256: String(repeating: "c", count: 64),
            vesselSource: "VesSAP specimen-test, diameter ≥30 µm"
        )
        let document = try #require(PDFDocument(data: rendered))
        let page = try #require(document.page(at: 0))
        let coordinateSelections = document.findString(
            prefill.targetCoordinateText,
            withOptions: []
        )
        let coordinateSelection = try #require(coordinateSelections.first)
        let coordinateBounds = coordinateSelection.bounds(for: page)

        #expect(coordinateSelections.count == 1)
        #expect(page.string?.contains(prefill.targetCoordinateText) == true)
        #expect(coordinateBounds.minX >= 37)
        #expect(coordinateBounds.maxX <= 755)
        #expect(coordinateBounds.minY >= 520)
        #expect(coordinateBounds.maxY <= 550)
    }

    @Test("Planning identity text is deterministically width-bounded")
    func planningPageIdentityWidth() {
        let visibleIdentity = SurgeryPlanningPageRenderer
            .fittedPlanningIdentityText(
                subjectId: String(repeating: "subject", count: 30),
                targetLabel: String(repeating: "target", count: 14),
                maximumWidth: 716
            )
        let renderedWidth = NSAttributedString(
            string: visibleIdentity,
            attributes: [
                .font: NSFont.monospacedSystemFont(
                    ofSize: 9.5,
                    weight: .semibold
                ),
            ]
        ).size().width

        #expect(renderedWidth <= 716)
        #expect(visibleIdentity.hasSuffix("…"))
    }

    @MainActor
    @Test("Prepared PDF has two protocol pages plus one atlas placeholder")
    func protocolTemplateValidation() throws {
        let templatePDF = try vectorTextPDF([
            "Surgery Record",
            "Surgery procedure",
            "atlas placeholder",
        ])
        try SurgeryProtocolPDFTemplate.validate(templatePDF)

        let invalidTemplates = [
            Data(),
            try vectorTextPDF(["Surgery Record"]),
            try vectorTextPDF(["Surgery Record", "Surgery procedure"]),
            try vectorTextPDF([
                "wrong page one",
                "wrong page two",
                "atlas placeholder",
            ]),
        ]
        for invalid in invalidTemplates {
            do {
                try SurgeryProtocolPDFTemplate.validate(invalid)
                Issue.record("Expected invalid protocol PDF to be rejected.")
            } catch SurgeryPlanExportError.invalidProtocolTemplate {
                // Expected.
            } catch {
                Issue.record("Unexpected protocol-template error: \(error)")
            }
        }
    }

    @MainActor
    @Test("PDF locations validate once and persist exact reusable paths")
    func persistentPDFLocations() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "Brain3D-SurgeryPDFSettings-\(UUID().uuidString)",
                isDirectory: true
            )
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: directory) }

        let protocolURL = directory.appendingPathComponent(
            "Headplate Protocol.pdf"
        )
        try vectorTextPDF([
            "Surgery Record",
            "Surgery procedure",
            "atlas placeholder",
        ]).write(to: protocolURL, options: .atomic)
        let wrongProtocolNameURL = directory.appendingPathComponent(
            "protocol.pdf"
        )
        try FileManager.default.copyItem(
            at: protocolURL,
            to: wrongProtocolNameURL
        )

        let generatedAtlasURL = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: generatedAtlasURL) }
        let atlasURL = directory.appendingPathComponent(
            "MBSC_Figs_with_Layers.pdf"
        )
        try FileManager.default.copyItem(
            at: generatedAtlasURL,
            to: atlasURL
        )
        let wrongNameURL = directory.appendingPathComponent("atlas.pdf")
        try FileManager.default.copyItem(at: atlasURL, to: wrongNameURL)
        let incompleteAtlasURL = directory.appendingPathComponent(
            "incomplete",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: incompleteAtlasURL,
            withIntermediateDirectories: true
        )
        let incompletePDFURL = incompleteAtlasURL.appendingPathComponent(
            "MBSC_Figs_with_Layers.pdf"
        )
        try vectorTextPDF(
            ["Figure 1 Bregma 4.28 mm"],
            size: CGSize(width: 792, height: 612)
        ).write(to: incompletePDFURL, options: .atomic)

        #expect(
            SurgeryPlanPDFPreferences.status(
                for: .protocolTemplate,
                path: ""
            ).state == .missing
        )
        #expect(
            SurgeryPlanPDFPreferences.status(
                for: .protocolTemplate,
                path: protocolURL.path
            ).isReady
        )
        #expect(
            SurgeryPlanPDFPreferences.status(
                for: .protocolTemplate,
                path: wrongProtocolNameURL.path
            ).state == .invalid
        )
        #expect(
            SurgeryPlanPDFPreferences.status(
                for: .mouseBrainAtlas,
                path: atlasURL.path
            ).isReady
        )
        #expect(
            SurgeryPlanPDFPreferences.status(
                for: .mouseBrainAtlas,
                path: wrongNameURL.path
            ).state == .invalid
        )
        #expect(
            SurgeryPlanPDFPreferences.status(
                for: .mouseBrainAtlas,
                path: incompletePDFURL.path
            ).state == .invalid
        )

        let suiteName = "Brain3D-SurgeryPDFSettings-\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        defaults.set(
            protocolURL.standardizedFileURL.path,
            forKey: SurgeryPlanPDFPreferences.protocolTemplatePathKey
        )
        defaults.set(
            atlasURL.standardizedFileURL.path,
            forKey: SurgeryPlanPDFPreferences.atlasPDFPathKey
        )

        #expect(
            defaults.string(
                forKey: SurgeryPlanPDFPreferences.protocolTemplatePathKey
            ) == protocolURL.standardizedFileURL.path
        )
        #expect(
            defaults.string(
                forKey: SurgeryPlanPDFPreferences.atlasPDFPathKey
            ) == atlasURL.standardizedFileURL.path
        )
    }

    @MainActor
    @Test("Included atlas resolves only with its pinned file identity")
    func bundledAtlasIdentity() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "Brain3D-BundledAtlas-\(UUID().uuidString)",
                isDirectory: true
            )
        let resources = directory.appendingPathComponent(
            "Resources",
            isDirectory: true
        )
        let surgeryAtlasDirectory = resources.appendingPathComponent(
            "SurgeryAtlas",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: surgeryAtlasDirectory,
            withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: directory) }

        let generatedAtlasURL = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: generatedAtlasURL) }
        let bundledURL = surgeryAtlasDirectory.appendingPathComponent(
            "MBSC_Figs_with_Layers.pdf"
        )
        try FileManager.default.copyItem(at: generatedAtlasURL, to: bundledURL)
        let data = try Data(contentsOf: bundledURL)
        let identity = SurgeryAtlasBundleIdentity(
            byteCount: data.count,
            pageCount: 132,
            sha256: LowercaseHex.encode(SHA256.hash(data: data))
        )

        let ready = SurgeryAtlasBundle.inspect(
            resourceURL: resources,
            identity: identity
        )
        #expect(
            ready == .ready(
                bundledURL.standardizedFileURL,
                sha256: identity.sha256
            )
        )
        #expect(
            SurgeryAtlasBundle.inspect(
                resourceURL: directory.appendingPathComponent("Missing"),
                identity: identity
            ) == .absent
        )

        let wrongDigest = SurgeryAtlasBundleIdentity(
            byteCount: data.count,
            pageCount: 132,
            sha256: String(repeating: "0", count: 64)
        )
        guard case .invalid = SurgeryAtlasBundle.inspect(
            resourceURL: resources,
            identity: wrongDigest
        ) else {
            Issue.record("A wrong included-atlas digest must fail closed.")
            return
        }

        let wrongPageCount = SurgeryAtlasBundleIdentity(
            byteCount: data.count,
            pageCount: 131,
            sha256: identity.sha256
        )
        guard case .invalid = SurgeryAtlasBundle.inspect(
            resourceURL: resources,
            identity: wrongPageCount
        ) else {
            Issue.record("A wrong included-atlas page count must fail closed.")
            return
        }
    }

    @MainActor
    @Test("Included atlas cannot escape Resources and takes priority over a saved path")
    func bundledAtlasResolutionPriority() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "Brain3D-BundledAtlasResolution-\(UUID().uuidString)",
                isDirectory: true
            )
        let resources = directory.appendingPathComponent(
            "Resources",
            isDirectory: true
        )
        let surgeryAtlasDirectory = resources.appendingPathComponent(
            "SurgeryAtlas",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: surgeryAtlasDirectory,
            withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: directory) }

        let externalAtlasURL = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: externalAtlasURL) }
        let data = try Data(contentsOf: externalAtlasURL)
        let identity = SurgeryAtlasBundleIdentity(
            byteCount: data.count,
            pageCount: 132,
            sha256: LowercaseHex.encode(SHA256.hash(data: data))
        )
        let symlink = surgeryAtlasDirectory.appendingPathComponent(
            "MBSC_Figs_with_Layers.pdf"
        )
        try FileManager.default.createSymbolicLink(
            at: symlink,
            withDestinationURL: externalAtlasURL
        )
        guard case .invalid = SurgeryAtlasBundle.inspect(
            resourceURL: resources,
            identity: identity
        ) else {
            Issue.record("An included atlas symlink may not escape Resources.")
            return
        }

        try FileManager.default.removeItem(at: symlink)
        try FileManager.default.createSymbolicLink(
            at: symlink,
            withDestinationURL: directory.appendingPathComponent(
                "missing-atlas.pdf"
            )
        )
        guard case .invalid = SurgeryAtlasBundle.inspect(
            resourceURL: resources,
            identity: identity
        ) else {
            Issue.record("A dangling included-atlas symlink must fail closed.")
            return
        }

        let bundledURL = resources.appendingPathComponent(
            SurgeryAtlasBundle.relativePath
        )
        let readyInspection = SurgeryAtlasBundleInspection.ready(
            bundledURL,
            sha256: identity.sha256
        )
        let bundled = SurgeryPlanPDFPreferences.atlasLocation(
            savedPath: "/definitely/not/the/saved/atlas.pdf",
            bundleInspection: readyInspection
        )
        #expect(bundled.origin == .bundled)
        #expect(bundled.url == bundledURL)
        #expect(bundled.requiredSourceSHA256 == identity.sha256)
        #expect(bundled.status.isReady)

        let savedDirectory = directory.appendingPathComponent(
            "Saved",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: savedDirectory,
            withIntermediateDirectories: true
        )
        let savedAtlasURL = savedDirectory.appendingPathComponent(
            "MBSC_Figs_with_Layers.pdf"
        )
        try FileManager.default.copyItem(
            at: externalAtlasURL,
            to: savedAtlasURL
        )
        let savedFallback = SurgeryPlanPDFPreferences.atlasLocation(
            savedPath: savedAtlasURL.path,
            bundleInspection: .absent
        )
        #expect(savedFallback.origin == .savedPreference)
        #expect(savedFallback.url == savedAtlasURL.standardizedFileURL)
        #expect(savedFallback.requiredSourceSHA256 == nil)
        #expect(savedFallback.status.isReady)

        let invalidBundled = SurgeryPlanPDFPreferences.atlasLocation(
            savedPath: savedAtlasURL.path,
            bundleInspection: .invalid("bad included atlas")
        )
        #expect(invalidBundled.origin == .invalidBundle)
        #expect(invalidBundled.url == nil)
        #expect(!invalidBundled.status.isReady)
    }

    @MainActor
    @Test("Included atlas mutation after resolution is rejected at export capture")
    func bundledAtlasMutationAfterResolution() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "Brain3D-BundledAtlasMutation-\(UUID().uuidString)",
                isDirectory: true
            )
        let resources = directory.appendingPathComponent(
            "Resources",
            isDirectory: true
        )
        let surgeryAtlasDirectory = resources.appendingPathComponent(
            "SurgeryAtlas",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: surgeryAtlasDirectory,
            withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: directory) }

        let generatedAtlasURL = try makeAtlasPDF()
        defer { try? FileManager.default.removeItem(at: generatedAtlasURL) }
        let bundledURL = surgeryAtlasDirectory.appendingPathComponent(
            "MBSC_Figs_with_Layers.pdf"
        )
        try FileManager.default.copyItem(at: generatedAtlasURL, to: bundledURL)
        let initialData = try Data(contentsOf: bundledURL)
        let identity = SurgeryAtlasBundleIdentity(
            byteCount: initialData.count,
            pageCount: 132,
            sha256: LowercaseHex.encode(SHA256.hash(data: initialData))
        )
        let inspection = SurgeryAtlasBundle.inspect(
            resourceURL: resources,
            identity: identity
        )
        guard case let .ready(resolvedURL, requiredSHA256) = inspection else {
            Issue.record("Expected the initial included atlas to resolve.")
            return
        }

        let handle = try FileHandle(forWritingTo: resolvedURL)
        try handle.seekToEnd()
        try handle.write(contentsOf: Data("\n% changed after resolution\n".utf8))
        try handle.close()

        let plate = try #require(
            SurgeryAtlasCatalog.canonicalPlates(sourceURL: resolvedURL)
                .first { $0.figure == 39 }
        )
        let capture = try await SurgeryAtlasPDFSource.shared.capture(plate)
        #expect(capture.sha256 != requiredSHA256)
        do {
            try SurgeryAtlasBundle.validateCapturedSHA256(
                capture.sha256,
                requiredSHA256: requiredSHA256
            )
            Issue.record("A changed included atlas must fail at export capture.")
        } catch SurgeryPlanExportError.invalidAtlasSource {
            // Expected.
        } catch {
            Issue.record("Unexpected included-atlas identity error: \(error)")
        }
    }

    @MainActor
    @Test("Planning PDF carries auditable vessel identity and animal limitation")
    func planningPDFVesselIdentity() throws {
        let digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        let artifact = SurgeryPlanningViewArtifact(
            view: .sagittal,
            pngData: try solidPNG(),
            subtitle: "Target-centred sagittal slice",
            vesselAssetSHA256: digest,
            vesselSegmentCount: 321,
            vesselScope: "target-slice slab",
            minimumVisibleVesselDiameterMicrometres: 80
        )
        let plate = SurgeryAtlasPlate(
            figure: 104,
            orientation: .sagittal,
            fixedCoordinateMillimetres: 0.36,
            sourceURL: URL(fileURLWithPath: "/tmp/MBSC_Figs_with_Layers.pdf")
        )

        let rendered = try SurgeryPlanningPageRenderer.render(
            artifact: artifact,
            prefill: makePrefill(
                azimuthDegrees: -12.5,
                elevationDegrees: -35
            ),
            atlasPlate: plate,
            atlasSourceSHA256: String(repeating: "a", count: 64),
            protocolSourceSHA256: String(repeating: "b", count: 64),
            vesselSource: "VesSAP specimen-test, diameter >=30 um"
        )
        let document = try #require(PDFDocument(data: rendered))
        let text = document.string ?? ""
        let normalizedText = text
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")

        #expect(document.pageCount == 1)
        #expect(text.contains("321 target-slice slab segments"))
        #expect(text.contains("display ≥80 µm"))
        #expect(text.contains("asset 0123456789ab"))
        #expect(text.contains("Single ex-vivo reference, not this animal"))
        #expect(text.contains("source <30 µm omitted"))
        #expect(text.contains("display filter does not alter provenance"))
        #expect(
            normalizedText.contains(
                "zero visible intersections never establishes vessel absence or clearance"
            )
        )
        #expect(text.contains("Animal research only"))
    }

    @Test("Readiness binds provenance while allowing unrelated revision increments")
    func strictReadiness() throws {
        let project = try readinessProject(revision: 7)
        let implant = try target(
            targetId: readinessTargetId,
            apMillimetres: -1.25,
            mlMillimetres: -0.8
        )
        let atlas = try readinessAtlas()
        let calibration = try readinessCalibration()
        let projection = try readinessProjection(projectRevision: 7)

        let currentProjection = try #require(
            SurgeryPlanReadiness.currentProjection(
                projection,
                project: project,
                target: implant,
                calibration: calibration,
                atlas: atlas
            )
        )
        let plan = try readinessProbePlan()
        let currentPlan = try #require(
            SurgeryPlanReadiness.currentProbePlan(
                plan,
                target: implant,
                projection: currentProjection,
                calibration: calibration,
                atlas: atlas
            )
        )
        #expect(
            SurgeryPlanReadiness.exportClass(
                project: project,
                hasUnsavedChanges: false,
                calibration: calibration,
                projection: currentProjection,
                probePlan: currentPlan
            ) == .final
        )

        #expect(
            SurgeryPlanReadiness.currentProjection(
                projection,
                project: project,
                target: implant,
                calibration: try readinessCalibration(
                    calibrationVersion: 2
                ),
                atlas: atlas
            ) == nil
        )
        #expect(
            SurgeryPlanReadiness.currentProjection(
                try readinessProjection(projectRevision: 6),
                project: project,
                target: implant,
                calibration: calibration,
                atlas: atlas
            ) != nil
        )
        #expect(
            SurgeryPlanReadiness.currentProjection(
                try readinessProjection(
                    projectRevision: 7,
                    calibrationSHA256: String(repeating: "d", count: 64)
                ),
                project: project,
                target: implant,
                calibration: calibration,
                atlas: atlas
            ) == nil
        )
        #expect(
            SurgeryPlanReadiness.currentProjection(
                try readinessProjection(
                    projectRevision: 7,
                    atlasSHA256: String(repeating: "d", count: 64)
                ),
                project: project,
                target: implant,
                calibration: calibration,
                atlas: atlas
            ) == nil
        )
        #expect(
            SurgeryPlanReadiness.currentProjection(
                try readinessProjection(
                    projectRevision: 7,
                    targetId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
                ),
                project: project,
                target: implant,
                calibration: calibration,
                atlas: atlas
            ) == nil
        )
        #expect(
            SurgeryPlanReadiness.currentProbePlan(
                try readinessProbePlan(
                    projectionSHA256: String(repeating: "d", count: 64)
                ),
                target: implant,
                projection: currentProjection,
                calibration: calibration,
                atlas: atlas
            ) == nil
        )
        #expect(
            SurgeryPlanReadiness.currentProbePlan(
                try readinessProbePlan(
                    sourceAPMillimetres: -1.30
                ),
                target: implant,
                projection: currentProjection,
                calibration: calibration,
                atlas: atlas
            ) == nil
        )
        #expect(
            SurgeryPlanReadiness.currentProbePlan(
                try readinessProbePlan(
                    calibrationSHA256: String(repeating: "d", count: 64)
                ),
                target: implant,
                projection: currentProjection,
                calibration: calibration,
                atlas: atlas
            ) == nil
        )
        #expect(
            SurgeryPlanReadiness.currentProbePlan(
                try readinessProbePlan(
                    atlasSHA256: String(repeating: "d", count: 64)
                ),
                target: implant,
                projection: currentProjection,
                calibration: calibration,
                atlas: atlas
            ) == nil
        )
        #expect(
            SurgeryPlanReadiness.exportClass(
                project: project,
                hasUnsavedChanges: true,
                calibration: calibration,
                projection: currentProjection,
                probePlan: currentPlan
            ) == .draft
        )
    }

    @MainActor
    @Test("Direct export capture rejects an unfinished probe edit")
    func directExportRejectsProbeDraft() {
        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        let model = PlannerViewModel(
            launchConfiguration: nil,
            preferences: defaults
        )
        model.probeDraftSession.surfaceAP = "-1.25"

        do {
            _ = try SurgeryPlanDraftSafety.captureCurrent(in: model)
            Issue.record("Expected the direct export boundary to reject the draft.")
        } catch let error as SurgeryPlanExportError {
            #expect(
                error.errorDescription
                    == "Finish the numeric edit with Return or leave the field, then wait "
                    + "for the probe update before exporting the surgery plan."
            )
        } catch {
            Issue.record("Unexpected export safety error: \(error)")
        }
    }

    @MainActor
    @Test("Any probe draft mutation invalidates an in-flight export identity")
    func probeDraftMutationInvalidatesCapture() throws {
        let defaults = UserDefaults(suiteName: UUID().uuidString)!
        let model = PlannerViewModel(
            launchConfiguration: nil,
            preferences: defaults
        )
        let captured = try SurgeryPlanDraftSafety.captureCurrent(in: model)
        #expect(captured.isCurrent(in: model))

        model.probeDraftSession.surfaceDepthMM = "3.25"

        #expect(!captured.isCurrent(in: model))
        #expect(model.hasUnappliedProbeDraftChanges)
    }

    @MainActor
    @Test("PDF assembly keeps protocol, selected views, then atlas")
    func pdfAssemblyOrder() throws {
        let protocolPDF = try labeledPDF(["protocol-1", "protocol-2"])
        let planningPages = try [
            labeledPDF(["planning-dorsal"]),
            labeledPDF(["planning-sagittal"]),
        ]
        let atlasPDF = try labeledPDF(["atlas-final"])

        let assembled = try SurgeryPlanPDFAssembler.assemble(
            protocolPDF: protocolPDF,
            planningPages: planningPages,
            atlasPDF: atlasPDF
        )
        let document = try #require(PDFDocument(data: assembled))

        #expect(document.pageCount == 5)
        #expect(
            (0 ..< document.pageCount).compactMap {
                document.page(at: $0)?.annotations
                    .first { $0.userName == markerAuthor }?
                    .contents
            } == [
                "protocol-1",
                "protocol-2",
                "planning-dorsal",
                "planning-sagittal",
                "atlas-final",
            ]
        )
    }

    @MainActor
    @Test("Packet preserves every page and stores audit identity only in metadata")
    func packetAuditStamp() throws {
        let protocolPDF = try labeledPDF(
            ["protocol-1", "protocol-2"],
            size: CGSize(width: 612, height: 792)
        )
        let planningPDF = try labeledPDF(
            ["planning-sagittal"],
            size: CGSize(width: 792, height: 612)
        )
        let atlasPDF = try labeledPDF(
            ["atlas-final"],
            size: CGSize(width: 792, height: 612)
        )
        let assembled = try SurgeryPlanPDFAssembler.assemble(
            protocolPDF: protocolPDF,
            planningPages: [planningPDF],
            atlasPDF: atlasPDF
        )
        let prefill = makePrefill(
            azimuthDegrees: 0,
            elevationDegrees: -90,
            subjectId: "brain3d-ui-e2e-20260723",
            targetLabel: "Left V1 QA target"
        )
        let targetId = "22222222-2222-4222-8222-222222222222"
        let vesselDigest = String(repeating: "f", count: 64)
        let protocolDigest = String(repeating: "e", count: 64)
        let atlasDigest = String(repeating: "d", count: 64)

        let stamped = try SurgeryPlanPacketRenderer.stamp(
            packetPDF: assembled,
            prefill: prefill,
            targetId: targetId,
            vesselAssetSHA256: vesselDigest,
            protocolTemplateSHA256: protocolDigest,
            atlasSourceSHA256: atlasDigest
        )
        let document = try #require(PDFDocument(data: stamped))
        let manifest = SurgeryPlanPacketRenderer.auditManifest(
            prefill: prefill,
            pageCount: document.pageCount,
            targetId: targetId,
            vesselAssetSHA256: vesselDigest,
            protocolTemplateSHA256: protocolDigest,
            atlasSourceSHA256: atlasDigest
        )

        #expect(document.pageCount == 4)
        #expect(
            SurgeryPlanPacketRenderer.auditMetadata(
                document,
                contains: manifest
            )
        )
        let preservedAnnotationContents = [
            "protocol-1",
            "protocol-2",
            "planning-sagittal",
            "atlas-final",
        ]
        for index in 0 ..< document.pageCount {
            let page = try #require(document.page(at: index))
            let text = page.string ?? ""
            #expect(!text.contains("DRAFT"))
            #expect(!text.contains("Brain3D-"))
            #expect(!text.contains("TID:"))
            #expect(!text.contains("H:"))
            #expect(page.annotations.count == 1)
            #expect(page.annotations.first?.contents == preservedAnnotationContents[index])
            let expectedSize = index < 2
                ? CGSize(width: 612, height: 792)
                : CGSize(width: 792, height: 612)
            #expect(page.bounds(for: .mediaBox).size == expectedSize)
        }
    }

    @MainActor
    @Test("All five planning views retain content while audit stays in metadata")
    func allPlanningViewsRetainPacketAuditIdentity() throws {
        let protocolPDF = try vectorTextPDF(
            ["Surgery Record", "Surgery procedure"],
            size: CGSize(width: 612, height: 792)
        )
        let prefill = makePrefill(
            azimuthDegrees: 0,
            elevationDegrees: -90,
            subjectId: "brain3d-ui-e2e-20260723",
            targetLabel: "Left V1 QA target",
            exportClass: .final
        )
        let vesselDigest = String(repeating: "f", count: 64)
        let protocolDigest = String(repeating: "e", count: 64)
        let atlasDigest = String(repeating: "d", count: 64)
        let targetId = "22222222-2222-4222-8222-222222222222"
        let plate = SurgeryAtlasPlate(
            figure: 39,
            orientation: .coronal,
            fixedCoordinateMillimetres: -0.94,
            sourceURL: URL(fileURLWithPath: "/tmp/MBSC_Figs_with_Layers.pdf")
        )
        let subtitles: [SurgeryPlanView: String] = [
            .dorsal:
                "Allen atlas dorsal surface projection · not a subject skull surface",
            .coronal:
                "Target-centred slice 161 of 528 · AP 4.013 mm in atlas physical space",
            .sagittal:
                "Target-centred slice 201 of 456 · ML 5.013 mm in atlas physical space",
            .horizontal:
                "Target-centred slice 141 of 320 · DV 3.513 mm in atlas physical space",
            .threeDimensional:
                "Standard home-camera snapshot · captured target/probe state",
        ]
        let planningPages = try SurgeryPlanView.allCases.map { view in
            try SurgeryPlanningPageRenderer.render(
                artifact: SurgeryPlanningViewArtifact(
                    view: view,
                    pngData: try solidPNG(),
                    subtitle: try #require(subtitles[view]),
                    vesselAssetSHA256: vesselDigest,
                    vesselSegmentCount: 119_755,
                    vesselScope: view == .dorsal
                        ? "dorsal depth projection"
                        : view == .threeDimensional
                            ? "whole-brain reference"
                            : "target-slice slab",
                    minimumVisibleVesselDiameterMicrometres: 50
                ),
                prefill: prefill,
                atlasPlate: plate,
                atlasSourceSHA256: atlasDigest,
                protocolSourceSHA256: protocolDigest,
                vesselSource: "VesSAP BL6J-no1, diameter ≥30 µm"
            )
        }
        let atlasPDF = try vectorTextPDF(
            ["Figure 39 Bregma -0.94 mm"],
            size: CGSize(width: 792, height: 612)
        )
        let assembled = try SurgeryPlanPDFAssembler.assemble(
            protocolPDF: protocolPDF,
            planningPages: planningPages,
            atlasPDF: atlasPDF
        )

        let stamped = try SurgeryPlanPacketRenderer.stamp(
            packetPDF: assembled,
            prefill: prefill,
            targetId: targetId,
            vesselAssetSHA256: vesselDigest,
            protocolTemplateSHA256: protocolDigest,
            atlasSourceSHA256: atlasDigest
        )
        let document = try #require(PDFDocument(data: stamped))

        #expect(document.pageCount == 8)
        for (offset, view) in SurgeryPlanView.allCases.enumerated() {
            let planningPage = try #require(document.page(at: offset + 2))
            let text = planningPage.string ?? ""
            #expect(
                text.contains(
                    "Surgery planning view — \(view.rawValue)"
                )
            )
            #expect(text.contains(prefill.targetCoordinateText))
        }
        let manifest = SurgeryPlanPacketRenderer.auditManifest(
            prefill: prefill,
            pageCount: document.pageCount,
            targetId: targetId,
            vesselAssetSHA256: vesselDigest,
            protocolTemplateSHA256: protocolDigest,
            atlasSourceSHA256: atlasDigest
        )
        #expect(
            SurgeryPlanPacketRenderer.auditMetadata(
                document,
                contains: manifest
            )
        )
        for index in 0 ..< document.pageCount {
            let page = try #require(document.page(at: index))
            let text = page.string ?? ""
            #expect(!text.contains("DRAFT"))
            #expect(!text.contains("Brain3D-"))
            #expect(!text.contains("TID:"))
            #expect(!text.contains("H:"))
        }
        let safetySelections = document.findString(
            "Animal research only",
            withOptions: []
        )
        #expect(safetySelections.count == SurgeryPlanView.allCases.count)
        for selection in safetySelections {
            let page = try #require(selection.pages.first)
            #expect(selection.bounds(for: page).minY >= 0)
        }
    }

    private func makeSurfacePrefill(
        angleDegrees: Double = 20,
        layoutDegrees: Int = 90,
        bregmaSourceRevision: String = "Urchin@57be3cdc7d62",
        apMillimetres: Double = -1.25,
        mlMillimetres: Double = 0.8,
        depthMillimetres: Double = 2.3,
        modelProductCode: String = "NP2013"
    ) -> SurgeryPlanPrefill {
        let isFourShank = modelProductCode == "NP2013"
        return SurgeryPlanPrefill(
            exportClass: .draft,
            date: "2026-07-25",
            projectTitle: "m13 planning",
            projectRevision: 1,
            subjectId: "m13",
            targetLabel: modelProductCode,
            apMillimetres: apMillimetres,
            mlMillimetres: mlMillimetres,
            dvMillimetres: nil,
            cageId: "",
            mouseNumber: "",
            weightGrams: "",
            operatorName: "",
            probePlanName: modelProductCode,
            probeModelName: isFourShank
                ? ProbePlanningContract.neuropixels2StandardFourShankDisplayName
                : ProbePlanningContract.neuropixels2SingleShankDisplayName,
            insertionDepthMillimetres: depthMillimetres,
            azimuthDegrees: 180,
            elevationDegrees: -70,
            axialRotationDegrees: 180,
            surfaceDepthMillimetres: depthMillimetres,
            sagittalAngleDegrees: angleDegrees,
            probeLayoutRotationDegrees: layoutDegrees,
            probeVerificationStatus: "source-transcribed-review-pending",
            probeWarning:
                ProbePlanningContract.sourceTranscribedReviewPendingWarning,
            planInputSHA256: String(repeating: "1", count: 64),
            surfaceAnnotationSHA256: String(repeating: "2", count: 64),
            surfaceDefinitionVersion:
                ProbePlanningContract.surfaceDefinitionVersion,
            bregmaReferenceId:
                ProbePlanningContract.surfaceBregmaReferenceId,
            bregmaSourceRevision: bregmaSourceRevision,
            bregmaSourceSHA256:
                ProbePlanningContract.surfaceBregmaSourceSHA256,
            draftReason: "test"
        )
    }

    private func makeOverlayFixture(
        modelProductCode: String,
        apMillimetres: Double,
        mlMillimetres: Double,
        depthMillimetres: Double,
        angleDegrees: Double,
        layoutDegrees: Int,
        bregmaSourceRevision: String = "Urchin@57be3cdc7d62"
    ) throws -> (plan: ProbePlanDetail, prefill: SurgeryPlanPrefill) {
        let isFourShank = modelProductCode == "NP2013"
        let shankCount = isFourShank ? 4 : 1
        let bregmaAP = 5_200.0
        let bregmaDV = 332.0
        let bregmaML = 5_700.0
        let surfaceAP = bregmaAP - apMillimetres * 1_000
        let surfaceDV = bregmaDV + 200
        let surfaceML = bregmaML - mlMillimetres * 1_000
        let angleRadians = angleDegrees * .pi / 180
        let inwardAP = sin(angleRadians)
        let inwardDV = cos(angleRadians)
        let totalLengthMillimetres = 10.0

        func point(
            ap: Double,
            dv: Double,
            ml: Double,
            insideAtlas: Bool
        ) -> [String: Any] {
            [
                "apMicrometres": ap,
                "dvMicrometres": dv,
                "mlMicrometres": ml,
                "insideAtlas": insideAtlas,
                "voxelIndex": insideAtlas
                    ? ["ap": 1, "dv": 1, "ml": 1]
                    : NSNull(),
            ]
        }

        let shanks: [[String: Any]] = (0 ..< shankCount).map { index in
            let offsetMicrometres = Double(index) * 250
            let shankSurfaceAP = surfaceAP
                + (layoutDegrees == 0 ? offsetMicrometres : 0)
            let shankSurfaceML = surfaceML
                - (layoutDegrees == 90 ? offsetMicrometres : 0)
            let tipAP = shankSurfaceAP
                + inwardAP * depthMillimetres * 1_000
            let tipDV = surfaceDV
                + inwardDV * depthMillimetres * 1_000
            let proximalAP = shankSurfaceAP
                + inwardAP * (depthMillimetres - totalLengthMillimetres) * 1_000
            let proximalDV = surfaceDV
                + inwardDV * (depthMillimetres - totalLengthMillimetres) * 1_000
            let surfacePoint = point(
                ap: shankSurfaceAP,
                dv: surfaceDV,
                ml: shankSurfaceML,
                insideAtlas: true
            )
            return [
                "shankId": "shank-\(index)",
                "entry": surfacePoint,
                "surfaceEntry": surfacePoint,
                "tip": point(
                    ap: tipAP,
                    dv: tipDV,
                    ml: shankSurfaceML,
                    insideAtlas: true
                ),
                "proximalEnd": point(
                    ap: proximalAP,
                    dv: proximalDV,
                    ml: shankSurfaceML,
                    insideAtlas: false
                ),
                "totalLengthMicrometres": totalLengthMillimetres * 1_000,
                "widthMicrometres": 70.0,
                "thicknessMicrometres": 24.0,
                "conservativeEnvelopeRadiusMicrometres": hypot(35.0, 12.0),
                "envelopeDefinition":
                    "circumscribed-radius-of-rectangular-cross-section",
            ]
        }
        let firstShank = try #require(shanks.first)
        let firstSurface = try #require(firstShank["surfaceEntry"] as? [String: Any])
        let firstTip = try #require(firstShank["tip"] as? [String: Any])
        let prefill = makeSurfacePrefill(
            angleDegrees: angleDegrees,
            layoutDegrees: layoutDegrees,
            bregmaSourceRevision: bregmaSourceRevision,
            apMillimetres: apMillimetres,
            mlMillimetres: mlMillimetres,
            depthMillimetres: depthMillimetres,
            modelProductCode: modelProductCode
        )
        let modelId = isFourShank
            ? ProbePlanningContract.neuropixels2StandardFourShankModelId
            : ProbePlanningContract.neuropixels2SingleShankModelId
        let modelDisplayName = isFourShank
            ? ProbePlanningContract.neuropixels2StandardFourShankDisplayName
            : ProbePlanningContract.neuropixels2SingleShankDisplayName
        let plan = try decode(
            ProbePlanDetail.self,
            [
                "planId": "55555555-5555-4555-8555-555555555555",
                "planVersion": 1,
                "name": "\(modelProductCode) overlay fixture",
                "targetId": NSNull(),
                "targetLabel": modelProductCode,
                "modelId": modelId,
                "modelVersion": ProbePlanningContract.neuropixels2ModelVersion,
                "modelDisplayName": modelDisplayName,
                "verificationStatus":
                    ProbePlanningContract.sourceTranscribedReviewPendingStatus,
                "inputSha256": String(repeating: "1", count: 64),
                "placementMode": ProbePlacementMode.atlasSurfaceAPML.rawValue,
                "calibrationId": NSNull(),
                "calibrationVersion": NSNull(),
                "regionAnalysisAvailable": false,
                "regionAnalysisSha256": NSNull(),
                "usableForNavigation": false,
                "sourceTarget": NSNull(),
                "manipulatorInput": NSNull(),
                "placementInput": NSNull(),
                "surfaceRelativeInput": [
                    "mode": ProbePlacementMode.atlasSurfaceAPML.rawValue,
                    "bregmaReference": [
                        "referenceId": ProbePlanningContract.surfaceBregmaReferenceId,
                        "atlasIdentifier": SafetyPolicy.supportedAtlasIdentifier,
                        "atlasVersion": SafetyPolicy.supportedAtlasVersion,
                        "frameId": ProbePlanningContract.atlasFrameId,
                        "componentOrder": ["AP", "DV", "ML"],
                        "units": "micrometre",
                        "apMicrometres": bregmaAP,
                        "dvMicrometres": bregmaDV,
                        "mlMicrometres": bregmaML,
                        "sourceTitle": "Pinned bregma fixture",
                        "sourceUrl": "https://example.invalid/bregma",
                        "sourceRevision": bregmaSourceRevision,
                        "sourceSha256":
                            ProbePlanningContract.surfaceBregmaSourceSHA256,
                        "retrievedOn": "2026-07-25",
                        "limitation": "Synthetic test fixture",
                    ],
                    "insertionAPMillimetres": apMillimetres,
                    "insertionMLMillimetres": mlMillimetres,
                    "surfaceDepthMillimetres": depthMillimetres,
                    "sagittalAngleDegrees": angleDegrees,
                    "probeLayoutRotationDegrees": layoutDegrees,
                    "surfaceEntry": [
                        "atlasIdentifier": SafetyPolicy.supportedAtlasIdentifier,
                        "atlasVersion": SafetyPolicy.supportedAtlasVersion,
                        "frameId": ProbePlanningContract.atlasFrameId,
                        "componentOrder": ["AP", "DV", "ML"],
                        "units": "micrometre",
                        "apMicrometres": surfaceAP,
                        "dvMicrometres": surfaceDV,
                        "mlMicrometres": surfaceML,
                    ],
                    "surfaceDVIndex": 1,
                    "surfaceDVResolutionMicrometres": 25.0,
                    "annotationSource": "synthetic test fixture",
                    "annotationSha256": String(repeating: "2", count: 64),
                    "surfaceDefinitionVersion":
                        ProbePlanningContract.surfaceDefinitionVersion,
                    "apSignConvention": ProbePlanningContract.surfaceAPSignConvention,
                    "mlSignConvention": ProbePlanningContract.surfaceMLSignConvention,
                    "depthConvention": ProbePlanningContract.surfaceDepthConvention,
                    "angleConvention": ProbePlanningContract.surfaceAngleConvention,
                    "layoutConvention": ProbePlanningContract.surfaceLayoutConvention,
                ],
                "placement": [
                    "placementId": "66666666-6666-4666-8666-666666666666",
                    "method": ProbePlanningContract.surfacePlacementMethod,
                    "azimuthDegrees": 0.0,
                    "elevationDegrees": -90.0 + abs(angleDegrees),
                    "insertionDepthMicrometres": depthMillimetres * 1_000,
                    "axialRotationDegrees": Double(layoutDegrees),
                    "angleConvention": ProbePlanningContract.angleConvention,
                    "inwardDirection": direction(
                        ap: inwardAP,
                        ml: 0,
                        dv: inwardDV
                    ),
                    "localLateralDirection": direction(ap: 0, ml: 1, dv: 0),
                    "localNormalDirection": direction(ap: -1, ml: 0, dv: 0),
                    "modelToPlacementUniformScale": 1.0,
                    "canonicalFrame": [
                        "frameId": "ATLAS_CANONICAL_AP_ML_DV_UM:test",
                        "componentOrder": ["AP", "ML", "DV"],
                        "units": "micrometre",
                        "apPositiveDirection": "anterior",
                        "mlPositiveDirection": "right",
                        "dvPositiveDirection": "dorsal/up",
                        "entry": canonicalPoint(ap: 0, ml: 0, dv: 0),
                        "target": canonicalPoint(
                            ap: inwardAP * depthMillimetres * 1_000,
                            ml: 0,
                            dv: inwardDV * depthMillimetres * 1_000
                        ),
                        "tip": canonicalPoint(
                            ap: inwardAP * depthMillimetres * 1_000,
                            ml: 0,
                            dv: inwardDV * depthMillimetres * 1_000
                        ),
                    ],
                    "atlasFrame": [
                        "frameId": ProbePlanningContract.atlasFrameId,
                        "componentOrder": ["AP", "DV", "ML"],
                        "units": "micrometre",
                        "origin": "anterior/superior/right atlas corner",
                        "entry": firstSurface,
                        "target": firstTip,
                        "tip": firstTip,
                    ],
                ],
                "shanks": shanks,
                "recordingSites": [],
                "provenance": [
                    "calibrationId": NSNull(),
                    "calibrationVersion": NSNull(),
                    "calibrationSha256": NSNull(),
                    "atlasMetadataSha256": String(repeating: "3", count: 64),
                    "projectionSha256": String(repeating: "4", count: 64),
                    "planningAlgorithmVersion":
                        ProbePlanningContract.surfacePlanningAlgorithmVersion,
                    "planInputSha256": String(repeating: "1", count: 64),
                    "catalogVersion": ProbePlanningContract.catalogVersion,
                ],
                "warning": "Animal research planning only",
            ]
        )
        return (plan, prefill)
    }

    private func testAtlasPlate(
        _ orientation: SurgeryAtlasOrientation
    ) throws -> SurgeryAtlasPlate {
        let figure = orientation == .coronal ? 39 : 101
        return try #require(
            SurgeryAtlasCatalog.canonicalPlates(
                sourceURL: URL(fileURLWithPath: "/tmp/atlas.pdf")
            ).first { $0.figure == figure }
        )
    }

    private func testCoordinateMap(
        _ orientation: SurgeryAtlasOrientation
    ) throws -> SurgeryAtlasCoordinateMap {
        try SurgeryAtlasCoordinateMap(
            orientation: orientation,
            plotRect: CGRect(x: 40, y: 40, width: 712, height: 532),
            horizontalZeroX: 396,
            dvZeroY: 80,
            horizontalPointsPerMillimetre: 50,
            dvPointsPerMillimetre: 50
        )
    }

    private func pointIsFinite(_ point: CGPoint) -> Bool {
        point.x.isFinite && point.y.isFinite
    }

    @MainActor
    private func rasterizedProbePalettePixelCounts(
        _ overlay: SurgeryAtlasProbeOverlay
    ) throws -> [Int] {
        let width = 792
        let height = 612
        let bytesPerRow = width * 4
        var pixels = [UInt8](
            repeating: 0,
            count: bytesPerRow * height
        )
        let palette: [(red: UInt8, green: UInt8, blue: UInt8)] = [
            (255, 0, 93),
            (0, 108, 255),
            (0, 168, 107),
            (255, 122, 0),
        ]
        return try pixels.withUnsafeMutableBytes { bytes in
            let bitmapInfo = CGBitmapInfo.byteOrder32Big.rawValue
                | CGImageAlphaInfo.premultipliedLast.rawValue
            let context = try #require(
                CGContext(
                    data: bytes.baseAddress,
                    width: width,
                    height: height,
                    bitsPerComponent: 8,
                    bytesPerRow: bytesPerRow,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: bitmapInfo
                )
            )
            context.clear(CGRect(x: 0, y: 0, width: width, height: height))
            try overlay.drawSVG(
                in: CGRect(x: 0, y: 0, width: width, height: height),
                context: context
            )
            context.flush()

            var counts = Array(repeating: 0, count: palette.count)
            let tolerance = 12
            for index in stride(from: 0, to: bytes.count, by: 4) {
                guard bytes[index + 3] > 220 else { continue }
                let red = Int(bytes[index])
                let green = Int(bytes[index + 1])
                let blue = Int(bytes[index + 2])
                for (paletteIndex, target) in palette.enumerated()
                where abs(red - Int(target.red)) <= tolerance
                    && abs(green - Int(target.green)) <= tolerance
                    && abs(blue - Int(target.blue)) <= tolerance
                {
                    counts[paletteIndex] += 1
                }
            }
            return counts
        }
    }

    private func makePrefill(
        azimuthDegrees: Double?,
        elevationDegrees: Double?,
        subjectId: String = "m13",
        targetLabel: String = "left V1",
        exportClass: SurgeryPlanExportClass = .draft
    ) -> SurgeryPlanPrefill {
        SurgeryPlanPrefill(
            exportClass: exportClass,
            date: "2026-07-23",
            projectTitle: "m13 planning",
            projectRevision: 9,
            subjectId: subjectId,
            targetLabel: targetLabel,
            apMillimetres: -1.25,
            mlMillimetres: -0.8,
            dvMillimetres: -2.4,
            cageId: "cage-7",
            mouseNumber: "3",
            weightGrams: "24.1",
            operatorName: "operator",
            probePlanName: nil,
            probeModelName: nil,
            insertionDepthMillimetres: nil,
            azimuthDegrees: azimuthDegrees,
            elevationDegrees: elevationDegrees,
            axialRotationDegrees: nil,
            surfaceDepthMillimetres: nil,
            sagittalAngleDegrees: nil,
            probeLayoutRotationDegrees: nil,
            probeVerificationStatus: nil,
            probeWarning: nil,
            planInputSHA256: nil,
            surfaceAnnotationSHA256: nil,
            surfaceDefinitionVersion: nil,
            bregmaReferenceId: nil,
            bregmaSourceRevision: nil,
            bregmaSourceSHA256: nil,
            draftReason: "test"
        )
    }

    private func exportConfiguration(
        targetLabel: String = "left V1",
        weightGrams: String = "",
        operatorName: String = ""
    ) -> SurgeryPlanExportConfiguration {
        SurgeryPlanExportConfiguration(
            targetId: "target-1",
            targetLabel: targetLabel,
            date: Date(timeIntervalSince1970: 0),
            cageId: "cage-7",
            mouseNumber: "3",
            weightGrams: weightGrams,
            operatorName: operatorName,
            viewSelection: .sagittal,
            protocolTemplateURL: URL(fileURLWithPath: "/tmp/protocol.pdf"),
            atlasPDFURL: URL(fileURLWithPath: "/tmp/atlas.pdf"),
            requiredAtlasSourceSHA256: nil,
            atlasOrientation: .sagittal
        )
    }

    @MainActor
    private func makeAtlasPDF(
        mediaBoxOrigin: CGPoint = .zero,
        sentinelFigure: Int? = nil
    ) throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(
            "Brain3D-SurgeryAtlasTests-\(UUID().uuidString).pdf"
        )
        let labels = SurgeryAtlasCatalog.canonicalPlates(sourceURL: url).map {
            plate in
            switch plate.orientation {
            case .coronal:
                "FIGURE \(zeroPaddedDecimal(plate.figure, width: 2)) · "
                    + String(
                    format: "Bregma %.2f mm · Interaural %.2f mm",
                    plate.fixedCoordinateMillimetres,
                    plate.fixedCoordinateMillimetres + 3.80
                )
            case .sagittal:
                "Figure \(plate.figure) · "
                    + String(
                    format: "Lateral %.2f mm",
                    plate.fixedCoordinateMillimetres
                )
            }
        }
        try atlasGridPDF(
            labels,
            mediaBoxOrigin: mediaBoxOrigin,
            sentinelFigure: sentinelFigure
        ).write(to: url, options: .atomic)
        return url
    }

    private func target(
        targetId: String = "target-1",
        apMillimetres: Double,
        mlMillimetres: Double,
        dvMillimetres: Double = -2.4
    ) throws -> UnprojectedImplantTarget {
        let json: [String: Any] = [
            "targetId": targetId,
            "schemaVersion": 1,
            "label": "left V1",
            "apMillimetres": apMillimetres,
            "mlMillimetres": mlMillimetres,
            "dvMillimetres": dvMillimetres,
            "frameId": "bregma",
            "origin": "Bregma",
            "componentOrder": ["AP", "ML", "DV"],
            "units": "mm",
            "apPositiveDirection": "anterior",
            "apNegativeDirection": "posterior",
            "mlPositiveDirection": "right",
            "mlNegativeDirection": "left",
            "dvPositiveDirection": "superficial",
            "dvNegativeDirection": "deep",
            "createdAt": "2026-07-23T00:00:00Z",
            "notes": "",
            "projected": false,
            "usableForNavigation": false,
            "projectionStatus": "unprojected",
        ]
        return try JSONDecoder().decode(
            UnprojectedImplantTarget.self,
            from: JSONSerialization.data(withJSONObject: json)
        )
    }

    private var readinessProjectId: String {
        "11111111-1111-4111-8111-111111111111"
    }

    private var readinessTargetId: String {
        "22222222-2222-4222-8222-222222222222"
    }

    private var readinessCalibrationId: String {
        "33333333-3333-4333-8333-333333333333"
    }

    private var readinessAtlasSHA256: String {
        String(repeating: "a", count: 64)
    }

    private var readinessCalibrationSHA256: String {
        String(repeating: "b", count: 64)
    }

    private var readinessProjectionSHA256: String {
        String(repeating: "c", count: 64)
    }

    private func readinessProject(revision: Int) throws -> ProjectBridgeState {
        try decode(
            ProjectBridgeState.self,
            [
                "projectId": readinessProjectId,
                "title": "m13 planning",
                "subjectId": "m13",
                "path": "/tmp/m13.brain3d",
                "requiresSaveAs": false,
                "recoveredFromBackup": false,
                "schemaVersion": 1,
                "revision": revision,
                "isDirty": false,
                "animalResearchOnlyAcknowledged": true,
                "calibrationCount": 1,
                "activeCalibrationId": readinessCalibrationId,
                "probePlanCount": 1,
                "probeRegionAnalysisCount": 0,
                "rendererAnchor": NSNull(),
            ]
        )
    }

    private func readinessAtlas() throws -> ViewerAtlasIdentity {
        try decode(
            ViewerAtlasIdentity.self,
            [
                "identifier": SafetyPolicy.supportedAtlasIdentifier,
                "version": SafetyPolicy.supportedAtlasVersion,
                "metadataSha256": readinessAtlasSHA256,
                "resolutionMicrometres": [25.0, 25.0, 25.0],
                "shapeVoxels": [528, 320, 456],
                "orientation": "asr",
                "frameworkName": "BrainGlobe Atlas API",
                "sourceAnnotation": "Allen CCF annotation",
                "citation": "Allen Mouse Brain CCF",
                "brainGlobeAtlasApiVersion": "2.3.0",
            ]
        )
    }

    private func readinessCalibration(
        calibrationVersion: Int = 1
    ) throws -> CalibrationSummary {
        try decode(
            CalibrationSummary.self,
            [
                "calibrationId": readinessCalibrationId,
                "schemaVersion": 1,
                "calibrationVersion": calibrationVersion,
                "profileId": "m13-rig",
                "mode": "subject-calibrated",
                "quality": "pass",
                "permitsPlanning": true,
                "permitsFinalExport": true,
                "active": true,
                "skullQuality": "pass",
                "skullRmsResidualMicrometres": 12.0,
                "atlasRmsResidualMicrometres": 15.0,
                "atlasMaximumResidualMicrometres": 21.0,
                "atlasTransformMethod": "rigid",
                "atlasMetadataSha256": readinessAtlasSHA256,
                "calibrationSha256": readinessCalibrationSHA256,
                "qcMessages": ["PASS"],
            ]
        )
    }

    private func readinessProjection(
        projectRevision: Int,
        targetId: String? = nil,
        calibrationSHA256: String? = nil,
        atlasSHA256: String? = nil
    ) throws -> CalibratedTargetProjectionResult {
        try decode(
            CalibratedTargetProjectionResult.self,
            [
                "protocolVersion": 1,
                "status": "projectedReadOnly",
                "projectId": readinessProjectId,
                "projectRevision": projectRevision,
                "targetId": targetId ?? readinessTargetId,
                "sourceTargetPreserved": true,
                "projectionPersisted": false,
                "usableForPlanning": true,
                "usableForNavigation": false,
                "stereotaxicPoint": [
                    "frameId": "STEREOTAXIC_BREGMA_AP_ML_DV_UM:m13-rig",
                    "componentOrder": ["AP", "ML", "DV"],
                    "units": "micrometre",
                    "apMicrometres": -1_250.0,
                    "mlMicrometres": -800.0,
                    "dvMicrometres": -2_400.0,
                ],
                "atlasPoint": [
                    "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
                    "atlasIdentifier": SafetyPolicy.supportedAtlasIdentifier,
                    "atlasVersion": SafetyPolicy.supportedAtlasVersion,
                    "componentOrder": ["AP", "DV", "ML"],
                    "units": "micrometre",
                    "apMicrometres": 6_000.0,
                    "dvMicrometres": 2_000.0,
                    "mlMicrometres": 2_000.0,
                ],
                "containingVoxelIndex": [
                    "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
                    "componentOrder": ["AP", "DV", "ML"],
                    "ap": 240,
                    "dv": 80,
                    "ml": 80,
                ],
                "provenance": [
                    "calibrationId": readinessCalibrationId,
                    "calibrationSchemaVersion": 1,
                    "calibrationVersion": 1,
                    "calibrationSha256":
                        calibrationSHA256 ?? readinessCalibrationSHA256,
                    "atlasTransformId":
                        "44444444-4444-4444-8444-444444444444",
                    "atlasTransformVersion": 1,
                    "atlasTransformMethod": "rigid",
                    "atlasMetadataSha256":
                        atlasSHA256 ?? readinessAtlasSHA256,
                    "projectionAlgorithm":
                        "bregma-target-through-subject-atlas-calibration-v1",
                    "projectionSha256": readinessProjectionSHA256,
                ],
                "coordinateSemantics": [
                    "frameId": "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED",
                    "origin": "bregma",
                    "componentOrder": ["AP", "ML", "DV"],
                    "units": "millimetre",
                    "apPositiveDirection": "anterior",
                    "apNegativeDirection": "posterior/back",
                    "mlPositiveDirection": "right",
                    "mlNegativeDirection": "left",
                    "dvPositiveDirection": "dorsal/up",
                    "dvNegativeDirection": "deep/ventral",
                ],
                "warning": "Animal research planning only",
            ]
        )
    }

    private func readinessProbePlan(
        projectionSHA256: String? = nil,
        sourceAPMillimetres: Double = -1.25,
        calibrationSHA256: String? = nil,
        atlasSHA256: String? = nil
    ) throws -> ProbePlanDetail {
        let atlasTarget = physicalPoint(
            ap: 6_000,
            dv: 2_000,
            ml: 2_000,
            voxel: [240, 80, 80]
        )
        let atlasEntry = physicalPoint(
            ap: 6_000,
            dv: 1_000,
            ml: 2_000,
            voxel: [240, 40, 80]
        )
        let atlasTip = physicalPoint(
            ap: 6_000,
            dv: 4_200,
            ml: 2_000,
            voxel: [240, 168, 80]
        )
        return try decode(
            ProbePlanDetail.self,
            [
                "planId": "55555555-5555-4555-8555-555555555555",
                "planVersion": 1,
                "name": "m13 left V1 NP2",
                "targetId": readinessTargetId,
                "targetLabel": "left V1",
                "modelId":
                    ProbePlanningContract.neuropixels2SingleShankModelId,
                "modelVersion": "2.0",
                "modelDisplayName": "Neuropixels 2.0 1-shank",
                "verificationStatus": "verified",
                "inputSha256": String(repeating: "e", count: 64),
                "calibrationId": readinessCalibrationId,
                "calibrationVersion": 1,
                "regionAnalysisAvailable": false,
                "regionAnalysisSha256": NSNull(),
                "usableForNavigation": false,
                "sourceTarget": [
                    "frameId": "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED",
                    "origin": "bregma",
                    "componentOrder": ["AP", "ML", "DV"],
                    "units": "millimetre",
                    "apMillimetres": sourceAPMillimetres,
                    "mlMillimetres": -0.8,
                    "dvMillimetres": -2.4,
                ],
                "manipulatorInput": NSNull(),
                "placementInput": NSNull(),
                "placement": [
                    "placementId":
                        "66666666-6666-4666-8666-666666666666",
                    "method": "stereotaxic-target-plus-manipulator-angles",
                    "azimuthDegrees": 0.0,
                    "elevationDegrees": -90.0,
                    "insertionDepthMicrometres": 3_200.0,
                    "axialRotationDegrees": 0.0,
                    "angleConvention": ProbePlanningContract.angleConvention,
                    "inwardDirection": direction(ap: 0, ml: 0, dv: -1),
                    "localLateralDirection": direction(ap: 0, ml: 1, dv: 0),
                    "localNormalDirection": direction(ap: -1, ml: 0, dv: 0),
                    "modelToPlacementUniformScale": 1.0,
                    "canonicalFrame": [
                        "frameId": "ATLAS_CANONICAL_AP_ML_DV_UM:test",
                        "componentOrder": ["AP", "ML", "DV"],
                        "units": "micrometre",
                        "apPositiveDirection": "anterior",
                        "mlPositiveDirection": "right",
                        "dvPositiveDirection": "dorsal/up",
                        "entry": canonicalPoint(ap: 0, ml: 0, dv: 0),
                        "target": canonicalPoint(ap: 0, ml: 0, dv: -1_000),
                        "tip": canonicalPoint(ap: 0, ml: 0, dv: -3_200),
                    ],
                    "atlasFrame": [
                        "frameId": ProbePlanningContract.atlasFrameId,
                        "componentOrder": ["AP", "DV", "ML"],
                        "units": "micrometre",
                        "origin": "anterior/superior/right atlas corner",
                        "entry": atlasEntry,
                        "target": atlasTarget,
                        "tip": atlasTip,
                    ],
                ],
                "shanks": [],
                "recordingSites": [],
                "provenance": [
                    "calibrationId": readinessCalibrationId,
                    "calibrationVersion": 1,
                    "calibrationSha256":
                        calibrationSHA256 ?? readinessCalibrationSHA256,
                    "atlasMetadataSha256":
                        atlasSHA256 ?? readinessAtlasSHA256,
                    "projectionSha256":
                        projectionSHA256 ?? readinessProjectionSHA256,
                    "planningAlgorithmVersion":
                        ProbePlanningContract.planningAlgorithmVersion,
                    "planInputSha256": String(repeating: "e", count: 64),
                    "catalogVersion": ProbePlanningContract.catalogVersion,
                ],
                "warning": "Animal research planning only",
            ]
        )
    }

    private func direction(
        ap: Double,
        ml: Double,
        dv: Double
    ) -> [String: Any] {
        [
            "frameId": "ATLAS_CANONICAL_AP_ML_DV_UM:test",
            "componentOrder": ["AP", "ML", "DV"],
            "units": "unitless",
            "ap": ap,
            "ml": ml,
            "dv": dv,
        ]
    }

    private func canonicalPoint(
        ap: Double,
        ml: Double,
        dv: Double
    ) -> [String: Any] {
        [
            "apMicrometres": ap,
            "mlMicrometres": ml,
            "dvMicrometres": dv,
        ]
    }

    private func physicalPoint(
        ap: Double,
        dv: Double,
        ml: Double,
        voxel: [Int]
    ) -> [String: Any] {
        [
            "apMicrometres": ap,
            "dvMicrometres": dv,
            "mlMicrometres": ml,
            "insideAtlas": true,
            "voxelIndex": [
                "ap": voxel[0],
                "dv": voxel[1],
                "ml": voxel[2],
            ],
        ]
    }

    private func decode<T: Decodable>(
        _ type: T.Type,
        _ payload: [String: Any]
    ) throws -> T {
        try JSONDecoder().decode(
            type,
            from: JSONSerialization.data(
                withJSONObject: payload,
                options: [.sortedKeys]
            )
        )
    }

    @MainActor
    private func atlasGridPDF(
        _ labels: [String],
        mediaBoxOrigin: CGPoint = .zero,
        sentinelFigure: Int? = nil
    ) throws -> Data {
        let output = NSMutableData()
        var mediaBox = CGRect(
            origin: mediaBoxOrigin,
            size: CGSize(width: 792, height: 612)
        )
        let consumer = try #require(
            CGDataConsumer(data: output as CFMutableData)
        )
        let context = try #require(
            CGContext(consumer: consumer, mediaBox: &mediaBox, nil)
        )
        for (index, label) in labels.enumerated() {
            context.beginPDFPage(nil)
            let graphics = NSGraphicsContext(cgContext: context, flipped: false)
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = graphics
            NSColor.white.setFill()
            mediaBox.fill()
            NSAttributedString(
                string: label,
                attributes: [
                    .font: NSFont.systemFont(ofSize: 18),
                    .foregroundColor: NSColor.black,
                ]
            ).draw(
                at: CGPoint(
                    x: mediaBox.minX + 36,
                    y: mediaBox.maxY - 44
                )
            )
            NSAttributedString(
                string: "Bregma",
                attributes: [
                    .font: NSFont.systemFont(ofSize: 9),
                    .foregroundColor: NSColor.black,
                ]
            ).draw(
                at: CGPoint(
                    x: mediaBox.minX + 374,
                    y: mediaBox.maxY - 24
                )
            )
            for (value, yOffset) in [("0", 120.0), ("1", 170.0)] {
                NSAttributedString(
                    string: value,
                    attributes: [
                        .font: NSFont.monospacedDigitSystemFont(
                            ofSize: 9,
                            weight: .regular
                        ),
                        .foregroundColor: NSColor.black,
                    ]
                ).draw(
                    at: CGPoint(
                        x: mediaBox.maxX - 8,
                        y: mediaBox.maxY - yOffset
                    )
                )
            }
            if sentinelFigure == index + 1 {
                NSAttributedString(
                    string: "TOPLEFTSENTINEL",
                    attributes: [
                        .font: NSFont.systemFont(ofSize: 9),
                        .foregroundColor: NSColor.black,
                    ]
                ).draw(
                    at: CGPoint(
                        x: mediaBox.minX + 18,
                        y: mediaBox.maxY - 70
                    )
                )
                NSAttributedString(
                    string: "BOTTOMRIGHTSENTINEL",
                    attributes: [
                        .font: NSFont.systemFont(ofSize: 9),
                        .foregroundColor: NSColor.black,
                    ]
                ).draw(
                    at: CGPoint(
                        x: mediaBox.maxX - 135,
                        y: mediaBox.minY + 18
                    )
                )
            }
            NSGraphicsContext.restoreGraphicsState()
            context.endPDFPage()
        }
        context.closePDF()
        let data = output as Data
        #expect(PDFDocument(data: data)?.pageCount == labels.count)
        return data
    }

    @MainActor
    private func vectorTextPDF(
        _ labels: [String],
        size: CGSize = CGSize(width: 612, height: 792)
    ) throws -> Data {
        let output = NSMutableData()
        var mediaBox = CGRect(origin: .zero, size: size)
        let consumer = try #require(
            CGDataConsumer(data: output as CFMutableData)
        )
        let context = try #require(
            CGContext(consumer: consumer, mediaBox: &mediaBox, nil)
        )
        for label in labels {
            context.beginPDFPage(nil)
            let graphics = NSGraphicsContext(cgContext: context, flipped: false)
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = graphics
            NSColor.white.setFill()
            mediaBox.fill()
            NSAttributedString(
                string: label,
                attributes: [
                    .font: NSFont.systemFont(ofSize: 18),
                    .foregroundColor: NSColor.black,
                ]
            ).draw(at: CGPoint(x: 36, y: size.height - 44))
            NSGraphicsContext.restoreGraphicsState()
            context.endPDFPage()
        }
        context.closePDF()
        let data = output as Data
        #expect(PDFDocument(data: data)?.pageCount == labels.count)
        return data
    }

    @MainActor
    private func solidPNG() throws -> Data {
        let image = NSImage(size: NSSize(width: 320, height: 200))
        image.lockFocus()
        NSColor(calibratedRed: 0.12, green: 0.28, blue: 0.45, alpha: 1).setFill()
        NSRect(x: 0, y: 0, width: 320, height: 200).fill()
        image.unlockFocus()
        let tiff = try #require(image.tiffRepresentation)
        let representation = try #require(NSBitmapImageRep(data: tiff))
        return try #require(
            representation.representation(using: .png, properties: [:])
        )
    }

    @MainActor
    private func labeledPDF(
        _ labels: [String],
        size: CGSize = CGSize(width: 612, height: 792)
    ) throws -> Data {
        let document = PDFDocument()
        for (index, label) in labels.enumerated() {
            let image = NSImage(size: size)
            image.lockFocus()
            NSColor.white.setFill()
            NSRect(origin: .zero, size: size).fill()
            NSAttributedString(
                string: label,
                attributes: [
                    .font: NSFont.systemFont(ofSize: 24),
                    .foregroundColor: NSColor.black,
                ]
            ).draw(at: NSPoint(x: 40, y: 700))
            image.unlockFocus()
            let page = try #require(PDFPage(image: image))
            let marker = PDFAnnotation(
                bounds: CGRect(x: 36, y: 36, width: 220, height: 24),
                forType: .freeText,
                withProperties: nil
            )
            marker.userName = markerAuthor
            marker.contents = label
            page.addAnnotation(marker)
            document.insert(page, at: index)
        }
        return try #require(document.dataRepresentation())
    }

    private var markerAuthor: String {
        "Brain3D-SurgeryPlanExportTests"
    }

    private func zeroPaddedDecimal(_ value: Int, width: Int) -> String {
        let text = String(value)
        return String(repeating: "0", count: max(0, width - text.count)) + text
    }
}
