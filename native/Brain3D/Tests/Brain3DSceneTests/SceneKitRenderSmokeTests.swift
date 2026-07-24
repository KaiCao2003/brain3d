import AppKit
import Brain3DCore
import CryptoKit
import Foundation
import simd
@testable import Brain3DScene
import Testing

@Suite("Offscreen 3D mouse-atlas rendering", .serialized)
struct SceneKitRenderSmokeTests {
    @Test("Verified OBJ and radius-bearing vessel graph render together")
    @MainActor
    func rendersPixels() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let meshResult = try decodeMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: [
                "frameId": AtlasSceneContract.physicalFrameId,
                "apMicrometres": 6_600.0,
                "dvMicrometres": 4_000.0,
                "mlMicrometres": 5_700.0,
            ]
        )
        let snapshot = try AnimalSceneSnapshot(
            projectId: "render-smoke-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil
        )
        let view = AtlasInteractiveSCNView(frame: CGRect(x: 0, y: 0, width: 320, height: 240))
        let controller = AnimalSceneController(view: view)
        var phase = AnimalScenePhase.idle

        await controller.apply(snapshot: snapshot) { phase = $0 }
        let brainOnlyBitmap = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        )
        let vesselGraph = try makeMajorVesselGraph(atlas: meshResult.atlas)
        let vesselMesh = try MajorVesselTubeMeshBuilder.build(
            pointsASRMicrometres: vesselGraph.pointsASRMicrometres,
            radiiMicrometres: vesselGraph.radiiMicrometres,
            runOffsets: vesselGraph.runOffsets
        )
        let vesselNode = MajorVesselNodeFactory.makeNode(
            mesh: vesselMesh,
            transform: snapshot.transform
        )
        let vesselLayer = try #require(
            view.scene?.rootNode.childNode(
                withName: "reviewed-major-vessel-layer",
                recursively: false
            )
        )
        vesselLayer.addChildNode(vesselNode)

        let image = controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        let bitmap = try bitmap(from: image)
        let data = try #require(bitmap.bitmapData)
        let bytes = UnsafeBufferPointer(
            start: data,
            count: bitmap.bytesPerRow * bitmap.pixelsHigh
        )
        let brainLayer = try #require(
            view.scene?.rootNode.childNode(
                withName: "allen-mouse-root-mesh",
                recursively: false
            )
        )
        brainLayer.isHidden = true
        let unobscuredVesselBitmap = try self.bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        )
        brainLayer.isHidden = false

        #expect(phase == .ready)
        #expect(vesselGraph.pointCount == 3)
        #expect(vesselGraph.runCount == 1)
        #expect(vesselGraph.segmentCount == 2)
        #expect(vesselNode.parent === vesselLayer)
        #expect(vesselNode.geometry?.name == "radius-bearing-reference-major-vessels")
        #expect(vesselNode.geometry?.elements.first?.primitiveType == .triangles)
        #expect(vesselNode.geometry?.elements.first?.primitiveCount == 24)
        #expect(vesselNode.renderingOrder == 10)
        #expect(vesselNode.opacity == 1)
        let vesselMaterial = try #require(vesselNode.geometry?.firstMaterial)
        #expect(vesselMaterial.lightingModel == .constant)
        #expect(!vesselMaterial.readsFromDepthBuffer)
        #expect(!vesselMaterial.writesToDepthBuffer)
        let importedBrainRoot = try #require(
            view.scene?.rootNode.childNode(withName: "verified-atlas-obj", recursively: true)
        )
        let brainNode = try #require(
            importedBrainRoot.childNodes(passingTest: { node, _ in
                node.geometry != nil
            }).first
        )
        let brainMaterial = try #require(brainNode.geometry?.firstMaterial)
        #expect(brainNode.renderingOrder == -10_000)
        #expect(abs(brainNode.opacity - 1) < 0.0001)
        #expect(brainMaterial.lightingModel == .blinn)
        #expect(abs(brainMaterial.transparency - 0.36) < 0.0001)
        #expect(brainMaterial.transparencyMode == .dualLayer)
        #expect(!brainMaterial.readsFromDepthBuffer)
        #expect(!brainMaterial.writesToDepthBuffer)
        #expect(bytes.min() != bytes.max())
        let background = try #require(
            view.scene?.background.contents as? NSColor
        ).usingColorSpace(.deviceRGB)
        #expect(try #require(background).redComponent > 0.85)
        #expect(nearBlackPixelCount(brainOnlyBitmap) < 100)
        #expect(visibleVesselPixelCount(brainOnlyBitmap) == 0)
        let visibleThroughShell = visibleVesselPixelCount(bitmap)
        let visibleWithoutShell = visibleVesselPixelCount(unobscuredVesselBitmap)
        #expect(visibleWithoutShell >= 20)
        #expect(visibleThroughShell * 10 >= visibleWithoutShell * 9)
    }

    @Test("Selected probe remains visible through the atlas shell")
    @MainActor
    func selectedProbeRendersAsXRayOverlay() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let meshResult = try decodeMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: [
                "frameId": AtlasSceneContract.physicalFrameId,
                "apMicrometres": 6_600.0,
                "dvMicrometres": 4_000.0,
                "mlMicrometres": 5_700.0,
            ]
        )
        let snapshot = try AnimalSceneSnapshot(
            projectId: "render-probe-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil
        )
        let view = AtlasInteractiveSCNView(
            frame: CGRect(x: 0, y: 0, width: 320, height: 240)
        )
        let controller = AnimalSceneController(view: view)

        await controller.apply(snapshot: snapshot) { _ in }
        let brainOnly = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        )
        let probe = try ProbeEnvelopeNodeFactory.makeNode(
            for: [
                ProbePlacedShank(
                    shankId: "shank-0",
                    entry: ProbePhysicalPoint(
                        apMicrometres: 6_600,
                        dvMicrometres: 2_000,
                        mlMicrometres: 5_700
                    ),
                    tip: ProbePhysicalPoint(
                        apMicrometres: 6_600,
                        dvMicrometres: 6_000,
                        mlMicrometres: 5_700
                    ),
                    widthMicrometres: 70,
                    thicknessMicrometres: 24,
                    conservativeEnvelopeRadiusMicrometres: 35,
                    envelopeDefinition: "half maximum shank width"
                ),
            ],
            usableForNavigation: false,
            transform: snapshot.transform
        )
        let probeLayer = try #require(
            view.scene?.rootNode.childNode(
                withName: "selected-probe-layer",
                recursively: false
            )
        )
        probeLayer.addChildNode(probe)
        let rendered = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        )
        let shankNode = try #require(
            probe.childNode(withName: "probe-shank-shank-0", recursively: true)
        )
        let material = try #require(shankNode.geometry?.firstMaterial)

        #expect(shankNode.renderingOrder == 20)
        #expect(material.lightingModel == .constant)
        #expect(!material.readsFromDepthBuffer)
        #expect(!material.writesToDepthBuffer)
        #expect(changedPixelCount(brainOnly, rendered) >= 20)
    }

    @Test("Displayed implant site remains visible through the shell and clears")
    @MainActor
    func implantSiteRendersAndClears() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let meshResult = try decodeMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let withoutMarker = try AnimalSceneSnapshot(
            projectId: "render-implant-site-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil
        )
        let marker = ImplantSiteSceneMarker(
            targetId: "direction-target",
            label: "AP- posterior / ML- animal-left",
            point: ProbePhysicalPoint(
                apMicrometres: 6_600,
                dvMicrometres: 4_000,
                mlMicrometres: 6_200,
                voxelIndex: ProbeVoxelIndex(ap: 264, dv: 160, ml: 248)
            )
        )
        let withMarker = try AnimalSceneSnapshot(
            projectId: "render-implant-site-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil,
            implantSite: marker
        )
        let view = AtlasInteractiveSCNView(
            frame: CGRect(x: 0, y: 0, width: 320, height: 240)
        )
        let controller = AnimalSceneController(view: view)

        await controller.apply(snapshot: withoutMarker) { _ in }
        let baseline = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        )
        await controller.apply(snapshot: withMarker) { _ in }
        let rendered = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        )
        let layer = try #require(
            view.scene?.rootNode.childNode(
                withName: "displayed-implant-site-layer",
                recursively: false
            )
        )
        let node = try #require(
            layer.childNode(withName: "implant-site-direction-target", recursively: false)
        )

        #expect(node.categoryBitMask == SceneCategory.implantSite.rawValue)
        #expect(changedPixelCount(baseline, rendered) >= 20)

        await controller.apply(snapshot: withoutMarker) { _ in }
        #expect(layer.childNodes.isEmpty)
    }

    @Test("Snapshot rejects stale or out-of-bounds implant projections")
    func implantSiteSnapshotContract() throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let meshResult = try decodeMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let validMarker = ImplantSiteSceneMarker(
            targetId: "direction-target",
            label: "AP- posterior / ML- animal-left",
            point: ProbePhysicalPoint(
                apMicrometres: 6_600,
                dvMicrometres: 4_000,
                mlMicrometres: 6_200,
                voxelIndex: ProbeVoxelIndex(ap: 264, dv: 160, ml: 248)
            )
        )
        let valid = try AnimalSceneSnapshot(
            projectId: "implant-site-contract-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil,
            implantSite: validMarker
        )
        let changedTarget = try AnimalSceneSnapshot(
            projectId: "implant-site-contract-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil,
            implantSite: ImplantSiteSceneMarker(
                targetId: "another-target",
                label: validMarker.label,
                point: validMarker.point
            )
        )
        #expect(valid.identity != changedTarget.identity)

        #expect(throws: AtlasSceneContractError.self) {
            _ = try AnimalSceneSnapshot(
                projectId: "implant-site-contract-project",
                projectRevision: 1,
                rendererAnchor: anchor,
                meshResult: meshResult,
                selectedProbePlan: nil,
                implantSite: ImplantSiteSceneMarker(
                    targetId: validMarker.targetId,
                    label: validMarker.label,
                    point: ProbePhysicalPoint(
                        apMicrometres: 13_200,
                        dvMicrometres: 4_000,
                        mlMicrometres: 6_200,
                        voxelIndex: ProbeVoxelIndex(ap: 528, dv: 160, ml: 248)
                    )
                )
            )
        }
        #expect(throws: AtlasSceneContractError.self) {
            _ = try AnimalSceneSnapshot(
                projectId: "implant-site-contract-project",
                projectRevision: 1,
                rendererAnchor: anchor,
                meshResult: meshResult,
                selectedProbePlan: nil,
                implantSite: ImplantSiteSceneMarker(
                    targetId: validMarker.targetId,
                    label: validMarker.label,
                    point: ProbePhysicalPoint(
                        apMicrometres: 6_600,
                        dvMicrometres: 4_000,
                        mlMicrometres: 6_200,
                        insideAtlas: false,
                        voxelIndex: ProbeVoxelIndex(ap: 264, dv: 160, ml: 248)
                    )
                )
            )
        }
        #expect(throws: AtlasSceneContractError.self) {
            _ = try AnimalSceneSnapshot(
                projectId: "implant-site-contract-project",
                projectRevision: 1,
                rendererAnchor: anchor,
                meshResult: meshResult,
                selectedProbePlan: nil,
                implantSite: ImplantSiteSceneMarker(
                    targetId: validMarker.targetId,
                    label: validMarker.label,
                    point: ProbePhysicalPoint(
                        apMicrometres: 6_600,
                        dvMicrometres: 4_000,
                        mlMicrometres: 6_200,
                        voxelIndex: ProbeVoxelIndex(ap: 264, dv: 160, ml: 247)
                    )
                )
            )
        }
    }

    @Test("A non-cortical Allen region mesh highlights inside the whole-brain shell")
    @MainActor
    func selectedWholeOntologyRegionRenders() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let rootMesh = try decodeMeshResult(fixture: fixture)
        let regionMesh = try decodeRegionMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let view = AtlasInteractiveSCNView(
            frame: CGRect(x: 0, y: 0, width: 320, height: 240)
        )
        let controller = AnimalSceneController(view: view)
        let rootOnly = try AnimalSceneSnapshot(
            projectId: "whole-ontology-region-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: rootMesh,
            selectedProbePlan: nil
        )
        await controller.apply(snapshot: rootOnly) { _ in }
        let before = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        )

        let highlighted = try AnimalSceneSnapshot(
            projectId: "whole-ontology-region-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: rootMesh,
            highlightedRegionMesh: regionMesh,
            selectedProbePlan: nil
        )
        var phase = AnimalScenePhase.idle
        await controller.apply(snapshot: highlighted) { phase = $0 }
        let after = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 320, height: 240))
        )
        let selectedRoot = try #require(
            view.scene?.rootNode.childNode(withName: "allen-region-549", recursively: true)
        )
        let selectedGeometryNode = try #require(
            selectedRoot.childNodes(passingTest: { node, _ in
                node.geometry != nil
            }).first
        )
        let material = try #require(selectedGeometryNode.geometry?.firstMaterial)

        #expect(phase == .ready)
        #expect(highlighted.highlightedRegionMesh?.region?.acronym == "TH")
        #expect(selectedGeometryNode.categoryBitMask == SceneCategory.highlightedRegion.rawValue)
        #expect(selectedGeometryNode.renderingOrder == -5_000)
        #expect(material.lightingModel == .constant)
        #expect(abs(material.transparency - 0.82) < 0.0001)
        #expect(material.readsFromDepthBuffer)
        #expect(material.writesToDepthBuffer)
        #expect(changedPixelCount(before, after) >= 20)
    }

    @Test("Whole-brain, region, NP2 four-shank probe, and VesSAP vessels coexist")
    @MainActor
    func completePlanningCompositeRenders() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let rootMesh = try decodeMeshResult(fixture: fixture)
        let regionMesh = try decodeRegionMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let view = AtlasInteractiveSCNView(
            frame: CGRect(x: 0, y: 0, width: 400, height: 300)
        )
        let controller = AnimalSceneController(view: view)
        let rootOnly = try AnimalSceneSnapshot(
            projectId: "complete-composite-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: rootMesh,
            selectedProbePlan: nil
        )
        await controller.apply(snapshot: rootOnly) { _ in }
        let rootBitmap = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 400, height: 300))
        )

        let highlighted = try AnimalSceneSnapshot(
            projectId: "complete-composite-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: rootMesh,
            highlightedRegionMesh: regionMesh,
            selectedProbePlan: nil
        )
        var phase = AnimalScenePhase.idle
        await controller.apply(snapshot: highlighted) { phase = $0 }
        let regionBitmap = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 400, height: 300))
        )

        let np2Shanks = (0 ..< 4).map { index in
            let ml = 5_325.0 + Double(index) * 250
            return ProbePlacedShank(
                shankId: "shank-\(index)",
                entry: ProbePhysicalPoint(
                    apMicrometres: 6_600,
                    dvMicrometres: 2_000,
                    mlMicrometres: ml
                ),
                tip: ProbePhysicalPoint(
                    apMicrometres: 6_600,
                    dvMicrometres: 6_000,
                    mlMicrometres: ml
                ),
                widthMicrometres: 70,
                thicknessMicrometres: 24,
                conservativeEnvelopeRadiusMicrometres: 35,
                envelopeDefinition: "half maximum shank width"
            )
        }
        let probe = try ProbeEnvelopeNodeFactory.makeNode(
            for: np2Shanks,
            usableForNavigation: true,
            transform: highlighted.transform
        )
        let probeLayer = try #require(
            view.scene?.rootNode.childNode(
                withName: "selected-probe-layer",
                recursively: false
            )
        )
        probeLayer.addChildNode(probe)
        let probeBitmap = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 400, height: 300))
        )

        // A compact graph keeps the smoke test fast while exercising the exact
        // production tube builder, material, transform, and scene layer used by
        // the pinned VesSAP major-vessel reference.
        let vesselGraph = try makeMajorVesselGraph(atlas: rootMesh.atlas)
        let vesselMesh = try MajorVesselTubeMeshBuilder.build(
            pointsASRMicrometres: vesselGraph.pointsASRMicrometres,
            radiiMicrometres: vesselGraph.radiiMicrometres,
            runOffsets: vesselGraph.runOffsets
        )
        let vessel = MajorVesselNodeFactory.makeNode(
            mesh: vesselMesh,
            transform: highlighted.transform
        )
        let vesselLayer = try #require(
            view.scene?.rootNode.childNode(
                withName: "reviewed-major-vessel-layer",
                recursively: false
            )
        )
        vesselLayer.addChildNode(vessel)
        let compositeBitmap = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 400, height: 300))
        )

        let brain = try #require(
            view.scene?.rootNode.childNode(withName: "verified-atlas-obj", recursively: true)
        )
        let region = try #require(
            view.scene?.rootNode.childNode(withName: "allen-region-549", recursively: true)
        )
        let shanks = (0 ..< 4).compactMap { index in
            probe.childNode(
                withName: "probe-shank-shank-\(index)",
                recursively: true
            )
        }
        #expect(phase == .ready)
        #expect(brain.parent != nil)
        #expect(region.parent != nil)
        #expect(shanks.count == 4)
        #expect(shanks.allSatisfy { $0.parent != nil })
        #expect(vessel.parent === vesselLayer)
        #expect(np2Shanks.allSatisfy { $0.widthMicrometres == 70 })
        #expect(np2Shanks.allSatisfy { $0.thicknessMicrometres == 24 })
        #expect(shanks.allSatisfy {
            $0.categoryBitMask == SceneCategory.probe.rawValue
        })
        #expect(vessel.categoryBitMask == SceneCategory.majorVessel.rawValue)
        #expect(changedPixelCount(rootBitmap, regionBitmap) >= 20)
        #expect(changedPixelCount(regionBitmap, probeBitmap) >= 20)
        #expect(changedPixelCount(probeBitmap, compositeBitmap) >= 20)
        #expect(visibleVesselPixelCount(compositeBitmap) >= 20)
    }

    @Test("Snapshot requires current vessel geometry before accepting a selected conflict")
    func selectedConflictSnapshotContract() throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let meshResult = try decodeMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let conflict = try decodeConflict()
        let withoutConflict = try AnimalSceneSnapshot(
            projectId: "render-smoke-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil
        )
        #expect(throws: AtlasSceneContractError.self) {
            _ = try AnimalSceneSnapshot(
                projectId: "render-smoke-project",
                projectRevision: 1,
                rendererAnchor: anchor,
                meshResult: meshResult,
                selectedProbePlan: nil,
                selectedVesselConflict: conflict
            )
        }
        #expect(withoutConflict.selectedVesselConflict == nil)
        try AnimalSceneSnapshot.validateSelectedVesselConflict(
            conflict,
            bounds: meshResult.sourceCoordinateFrame.bounds,
            selectedProbeShankIds: ["shank-1"]
        )
        #expect(throws: AtlasSceneContractError.self) {
            try AnimalSceneSnapshot.validateSelectedVesselConflict(
                conflict,
                bounds: meshResult.sourceCoordinateFrame.bounds,
                selectedProbeShankIds: ["another-shank"]
            )
        }

        let outOfBounds = try decodeConflict(overrides: [
            "vesselPoint": physicalPoint(ap: 13_200, dv: 4_000, ml: 5_700),
        ])
        #expect(throws: AtlasSceneContractError.self) {
            try AnimalSceneSnapshot.validateSelectedVesselConflict(
                outOfBounds,
                bounds: meshResult.sourceCoordinateFrame.bounds,
                selectedProbeShankIds: ["shank-1"]
            )
        }
    }

    private func bitmap(from image: NSImage) throws -> NSBitmapImageRep {
        let tiff = try #require(image.tiffRepresentation)
        return try #require(NSBitmapImageRep(data: tiff))
    }

    private func makeMajorVesselGraph(atlas: ViewerAtlasIdentity) throws -> MajorVesselGraph {
        try MajorVesselGraph(
            pointsASRMicrometres: [
                SIMD3(6_100, 4_000, 5_700),
                SIMD3(6_600, 4_000, 5_700),
                SIMD3(7_100, 4_000, 5_700),
            ],
            radiiMicrometres: [220, 260, 220],
            runOffsets: [0, 3],
            sourceEdgeIndices: [0],
            atlas: atlas,
            minimumIncludedDiameterMicrometres:
                MajorVesselContract.minimumIncludedDiameterMicrometres
        )
    }

    private func visibleVesselPixelCount(_ bitmap: NSBitmapImageRep) -> Int {
        var count = 0
        for y in 0 ..< bitmap.pixelsHigh {
            for x in 0 ..< bitmap.pixelsWide {
                guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB)
                else { continue }
                if color.redComponent > 0.45,
                   color.redComponent > color.greenComponent * 1.5,
                   color.redComponent > color.blueComponent * 1.3
                {
                    count += 1
                }
            }
        }
        return count
    }

    private func nearBlackPixelCount(_ bitmap: NSBitmapImageRep) -> Int {
        var count = 0
        for y in 0 ..< bitmap.pixelsHigh {
            for x in 0 ..< bitmap.pixelsWide {
                guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB)
                else { continue }
                let luminance =
                    color.redComponent * 0.2126
                        + color.greenComponent * 0.7152
                        + color.blueComponent * 0.0722
                if luminance < 0.12 {
                    count += 1
                }
            }
        }
        return count
    }

    private func changedPixelCount(
        _ baseline: NSBitmapImageRep,
        _ rendered: NSBitmapImageRep
    ) -> Int {
        guard baseline.pixelsWide == rendered.pixelsWide,
              baseline.pixelsHigh == rendered.pixelsHigh
        else { return 0 }
        var count = 0
        for y in 0 ..< rendered.pixelsHigh {
            for x in 0 ..< rendered.pixelsWide {
                guard let before = baseline.colorAt(x: x, y: y)?
                    .usingColorSpace(.deviceRGB),
                    let after = rendered.colorAt(x: x, y: y)?
                    .usingColorSpace(.deviceRGB)
                else { continue }
                let difference =
                    abs(before.redComponent - after.redComponent)
                        + abs(before.greenComponent - after.greenComponent)
                        + abs(before.blueComponent - after.blueComponent)
                if difference > 0.15 {
                    count += 1
                }
            }
        }
        return count
    }

    private func decodeConflict(
        overrides: [String: Any] = [:]
    ) throws -> MajorVesselConflict {
        var object: [String: Any] = [
            "conflictId": "shank-1:edge-7:run-0:segment-0",
            "shankId": "shank-1",
            "vesselSourceEdgeIndex": 7,
            "vesselRunIndex": 0,
            "vesselSegmentIndexInRun": 0,
            "classification": "intersection",
            "vesselDiameterMicrometres": 30.0,
            "probeEnvelopeRadiusMicrometres": 35.0,
            "centerlineDistanceMicrometres": 200.0,
            "geometricSurfaceClearanceMicrometres": 150.0,
            "requiredMarginMicrometres": 100.0,
            "registrationUncertaintyMicrometres": 75.0,
            "adjustedClearanceMicrometres": -25.0,
            "probePoint": physicalPoint(ap: 6_600, dv: 3_900, ml: 5_700),
            "vesselPoint": physicalPoint(ap: 6_600, dv: 4_100, ml: 5_700),
            "insertionDepthMicrometres": 100.0,
            "sourceKind": "reference-individual-vessel-graph",
            "subjectSpecific": false,
            "warnings": ["Single-specimen reference only."],
        ]
        overrides.forEach { object[$0.key] = $0.value }
        return try decode(MajorVesselConflict.self, object: object)
    }

    private func physicalPoint(ap: Double, dv: Double, ml: Double) -> [String: Any] {
        [
            "frameId": AtlasPhysicalCoordinateFrame.expectedFrameId,
            "apMicrometres": ap,
            "dvMicrometres": dv,
            "mlMicrometres": ml,
        ]
    }

    private func makeFixture() throws -> (
        root: URL,
        obj: URL,
        sha256: String,
        byteSize: Int,
        regionObj: URL,
        regionSHA256: String,
        regionByteSize: Int
    ) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("brain3d-render-\(UUID().uuidString)", isDirectory: true)
        let meshes = root.appendingPathComponent("meshes", isDirectory: true)
        try FileManager.default.createDirectory(at: meshes, withIntermediateDirectories: true)
        let obj = meshes.appendingPathComponent("997.obj")
        let data = Data(
            """
            o brain
            v 1800 1600 1600
            v 11400 1600 1600
            v 11400 6400 1600
            v 1800 6400 1600
            v 1800 1600 9800
            v 11400 1600 9800
            v 11400 6400 9800
            v 1800 6400 9800
            f 1 2 3
            f 1 3 4
            f 5 8 7
            f 5 7 6
            f 1 5 6
            f 1 6 2
            f 2 6 7
            f 2 7 3
            f 3 7 8
            f 3 8 4
            f 5 1 4
            f 5 4 8
            """.utf8
        )
        try data.write(to: obj, options: .atomic)
        let sha = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        let regionObj = meshes.appendingPathComponent("549.obj")
        let regionData = Data(
            """
            o thalamus
            v 4800 3000 4200
            v 8200 3000 4200
            v 8200 5000 4200
            v 4800 5000 4200
            v 4800 3000 7200
            v 8200 3000 7200
            v 8200 5000 7200
            v 4800 5000 7200
            f 1 2 3
            f 1 3 4
            f 5 8 7
            f 5 7 6
            f 1 5 6
            f 1 6 2
            f 2 6 7
            f 2 7 3
            f 3 7 8
            f 3 8 4
            f 5 1 4
            f 5 4 8
            """.utf8
        )
        try regionData.write(to: regionObj, options: .atomic)
        let regionSHA = SHA256.hash(data: regionData)
            .map { String(format: "%02x", $0) }
            .joined()
        return (
            root.standardizedFileURL,
            obj.standardizedFileURL,
            sha,
            data.count,
            regionObj.standardizedFileURL,
            regionSHA,
            regionData.count
        )
    }

    private func decodeMeshResult(
        fixture: (
            root: URL,
            obj: URL,
            sha256: String,
            byteSize: Int,
            regionObj: URL,
            regionSHA256: String,
            regionByteSize: Int
        )
    ) throws -> AtlasMeshResult {
        try decode(
            AtlasMeshResult.self,
            object: [
                "protocolVersion": 1,
                "target": "root",
                "region": NSNull(),
                "mesh": [
                    "canonicalPath": fixture.obj.path,
                    "atlasRootCanonicalPath": fixture.root.path,
                    "pathUnderAtlasRoot": "meshes/997.obj",
                    "sha256": fixture.sha256,
                    "byteSize": fixture.byteSize,
                    "fileExtension": ".obj",
                    "contentsIncluded": false,
                ],
                "sourceCoordinateFrame": coordinateFrame(),
                "atlas": atlas(),
            ]
        )
    }

    private func decodeRegionMeshResult(
        fixture: (
            root: URL,
            obj: URL,
            sha256: String,
            byteSize: Int,
            regionObj: URL,
            regionSHA256: String,
            regionByteSize: Int
        )
    ) throws -> AtlasMeshResult {
        try decode(
            AtlasMeshResult.self,
            object: [
                "protocolVersion": 1,
                "target": "region",
                "region": [
                    "structureId": 549,
                    "acronym": "TH",
                    "name": "Thalamus",
                    "parentStructureId": 997,
                    "structureIdPath": [997, 549],
                    "rgb": [255, 112, 128],
                ],
                "mesh": [
                    "canonicalPath": fixture.regionObj.path,
                    "atlasRootCanonicalPath": fixture.root.path,
                    "pathUnderAtlasRoot": "meshes/549.obj",
                    "sha256": fixture.regionSHA256,
                    "byteSize": fixture.regionByteSize,
                    "fileExtension": ".obj",
                    "contentsIncluded": false,
                ],
                "sourceCoordinateFrame": coordinateFrame(),
                "atlas": atlas(),
            ]
        )
    }

    private func decode<T: Decodable>(_ type: T.Type, object: Any) throws -> T {
        try JSONDecoder().decode(
            type,
            from: JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        )
    }

    private func atlas() -> [String: Any] {
        [
            "identifier": "allen_mouse_25um",
            "version": "1.2",
            "metadataSha256": String(repeating: "a", count: 64),
            "resolutionMicrometres": [25.0, 25.0, 25.0],
            "shapeVoxels": [528, 320, 456],
            "orientation": "asr",
            "frameworkName": "brainglobe-atlasapi",
            "sourceAnnotation": "annotation.tiff",
            "citation": "Allen Mouse Brain Common Coordinate Framework",
            "brainGlobeAtlasApiVersion": "2.3.0",
        ]
    }

    private func coordinateFrame() -> [String: Any] {
        [
            "frameId": AtlasSceneContract.physicalFrameId,
            "unit": "micrometres",
            "coordinateKind": "continuousPhysical",
            "axisOrder": ["AP", "DV", "ML"],
            "origin": ["anterior", "superior", "right"],
            "positiveDirections": ["posterior", "inferior", "left"],
            "axes": [
                axis(0, "AP", "anterior", "posterior"),
                axis(1, "DV", "superior", "inferior"),
                axis(2, "ML", "right", "left"),
            ],
            "bregmaRelative": false,
            "stereotaxicCalibrationApplied": false,
            "voxelAnchorOffsetApplied": false,
            "bounds": [
                "minimumInclusiveMicrometres": [0.0, 0.0, 0.0],
                "maximumExclusiveMicrometres": [13_200.0, 8_000.0, 11_400.0],
            ],
        ]
    }

    private func axis(
        _ index: Int,
        _ anatomical: String,
        _ origin: String,
        _ positive: String
    ) -> [String: Any] {
        [
            "arrayAxis": index,
            "anatomicalAxis": anatomical,
            "originDirection": origin,
            "positiveDirection": positive,
            "voxelSizeMicrometres": 25.0,
        ]
    }
}
