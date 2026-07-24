import AppKit
import Brain3DCore
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

        let renderedPage = try SurgeryAtlasPageRenderer.overlay(
            atlasPDF: snapshot.sourcePDF,
            prefill: makePrefill(azimuthDegrees: 0, elevationDegrees: -90),
            plate: figure39,
            atlasSourceSHA256: snapshot.sha256
        )
        let renderedDocument = try #require(PDFDocument(data: renderedPage))
        #expect(renderedDocument.pageCount == 1)
        #expect(renderedDocument.string?.contains(figure39.displayName) == true)
        #expect(
            renderedDocument.string?.contains(
                String(snapshot.sha256.prefix(16))
            ) == true
        )
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
    @Test("Every flattened packet page carries stable audit identity")
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

        #expect(document.pageCount == 4)
        for index in 0 ..< document.pageCount {
            let page = try #require(document.page(at: index))
            let stamp = SurgeryPlanPacketRenderer.auditStamp(
                prefill: prefill,
                pageNumber: index + 1,
                pageCount: document.pageCount,
                targetId: targetId,
                vesselAssetSHA256: vesselDigest,
                protocolTemplateSHA256: protocolDigest,
                atlasSourceSHA256: atlasDigest
            )
            let text = page.string ?? ""
            #expect(
                SurgeryPlanPacketRenderer.auditText(
                    text,
                    contains: stamp
                )
            )
            #expect(text.contains("Brain3D-DRAFT"))
            #expect(text.contains("TID:\(targetId)"))
            #expect(text.contains("R:9"))
            #expect(text.contains("V:ffffffffffff"))
            #expect(text.contains("P:eeeeeeeeeeee"))
            #expect(text.contains("A:dddddddddddd"))
            #expect(text.contains("H:"))
            #expect(page.annotations.isEmpty)
            let expectedSize = index < 2
                ? CGSize(width: 612, height: 792)
                : CGSize(width: 792, height: 612)
            #expect(page.bounds(for: .mediaBox).size == expectedSize)
        }
    }

    @MainActor
    @Test("All five rendered planning views retain their packet audit identity")
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
        for index in 0 ..< document.pageCount {
            let page = try #require(document.page(at: index))
            let stamp = SurgeryPlanPacketRenderer.auditStamp(
                prefill: prefill,
                pageNumber: index + 1,
                pageCount: document.pageCount,
                targetId: targetId,
                vesselAssetSHA256: vesselDigest,
                protocolTemplateSHA256: protocolDigest,
                atlasSourceSHA256: atlasDigest
            )
            #expect(
                SurgeryPlanPacketRenderer.auditText(
                    page.string,
                    contains: stamp
                )
            )
            let wrongPageStamp = SurgeryPlanPacketRenderer.auditStamp(
                prefill: prefill,
                pageNumber: index == 0 ? 2 : 1,
                pageCount: document.pageCount,
                targetId: targetId,
                vesselAssetSHA256: vesselDigest,
                protocolTemplateSHA256: protocolDigest,
                atlasSourceSHA256: atlasDigest
            )
            #expect(
                !SurgeryPlanPacketRenderer.auditText(
                    page.string,
                    contains: wrongPageStamp
                )
            )
            let text = page.string ?? ""
            #expect(text.contains("Brain3D-FINAL"))
            #expect(text.contains("S:brain3d-ui-e2e-20260723"))
            #expect(text.contains("TID:\(targetId)"))
            #expect(text.contains("R:9"))
            #expect(text.contains("V:ffffffffffff"))
            #expect(text.contains("P:eeeeeeeeeeee"))
            #expect(text.contains("A:dddddddddddd"))
            #expect(text.contains("Pg:\(index + 1)/8"))
            #expect(text.contains("H:"))
        }
        let safetySelections = document.findString(
            "Animal research only",
            withOptions: []
        )
        #expect(safetySelections.count == SurgeryPlanView.allCases.count)
        for selection in safetySelections {
            let page = try #require(selection.pages.first)
            #expect(selection.bounds(for: page).minY >= 22)
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
            atlasOrientation: .sagittal
        )
    }

    @MainActor
    private func makeAtlasPDF() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(
            "Brain3D-SurgeryAtlasTests-\(UUID().uuidString).pdf"
        )
        let labels = SurgeryAtlasCatalog.canonicalPlates(sourceURL: url).map {
            plate in
            switch plate.orientation {
            case .coronal:
                String(
                    format:
                        "FIGURE %02d · Bregma %.2f mm · Interaural %.2f mm",
                    plate.figure,
                    plate.fixedCoordinateMillimetres,
                    plate.fixedCoordinateMillimetres + 3.80
                )
            case .sagittal:
                String(
                    format: "Figure %d · Lateral %.2f mm",
                    plate.figure,
                    plate.fixedCoordinateMillimetres
                )
            }
        }
        try vectorTextPDF(
            labels,
            size: CGSize(width: 792, height: 612)
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
}
