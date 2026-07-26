import AppKit
import Brain3DCore
import CryptoKit
import Foundation
@preconcurrency import SceneKit
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
        #expect(selectedGeometryNode.renderingOrder == 0)
        #expect(material.lightingModel == .constant)
        #expect(abs(material.transparency - 0.94) < 0.0001)
        #expect(!material.readsFromDepthBuffer)
        #expect(!material.writesToDepthBuffer)
        #expect(changedPixelCount(before, after) >= 20)
    }

    @Test("Changing selected region refreshes 3D identity even when geometry is shared")
    @MainActor
    func changingSelectedRegionRefreshesSharedGeometry() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let rootMesh = try decodeMeshResult(fixture: fixture)
        let firstRegionMesh = try decodeRegionMeshResult(fixture: fixture)
        let secondRegionMesh = try decodeRegionMeshResult(
            fixture: fixture,
            region: [
                "structureId": 385,
                "acronym": "VISp",
                "name": "Primary visual area",
                "parentStructureId": 669,
                "structureIdPath": [997, 8, 567, 688, 695, 315, 669, 385],
                "rgb": [8, 133, 140],
            ]
        )
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let first = try AnimalSceneSnapshot(
            projectId: "region-refresh-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: rootMesh,
            highlightedRegionMesh: firstRegionMesh,
            selectedProbePlan: nil
        )
        let second = try AnimalSceneSnapshot(
            projectId: "region-refresh-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: rootMesh,
            highlightedRegionMesh: secondRegionMesh,
            selectedProbePlan: nil
        )
        let view = AtlasInteractiveSCNView(
            frame: CGRect(x: 0, y: 0, width: 320, height: 240)
        )
        let controller = AnimalSceneController(view: view)

        await controller.apply(snapshot: first) { _ in }
        await controller.apply(snapshot: second) { _ in }

        #expect(first.identity != second.identity)
        #expect(
            view.scene?.rootNode.childNode(
                withName: "allen-region-549",
                recursively: true
            ) == nil
        )
        let selectedRoot = try #require(
            view.scene?.rootNode.childNode(
                withName: "allen-region-385",
                recursively: true
            )
        )
        let selectedGeometry = try #require(
            selectedRoot.childNodes(passingTest: { node, _ in
                node.geometry != nil
            }).first
        )
        let selectedColor = try #require(
            selectedGeometry.geometry?.firstMaterial?.diffuse.contents as? NSColor
        ).usingColorSpace(.deviceRGB)
        let rgb = try #require(selectedColor)
        #expect(abs(rgb.redComponent - linearSRGBComponent(8)) < 0.01)
        #expect(abs(rgb.greenComponent - linearSRGBComponent(133)) < 0.01)
        #expect(abs(rgb.blueComponent - linearSRGBComponent(140)) < 0.01)
    }

    @Test("A selected cortical layer remains visible with the reviewed cached atlas meshes")
    @MainActor
    func selectedCorticalLayerRendersWithReviewedAtlasCache() async throws {
        let atlasRoot = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(
                ".brainglobe/allen_mouse_25um_v1.2",
                isDirectory: true
            )
            .standardizedFileURL
        let rootURL = atlasRoot.appendingPathComponent("meshes/997.obj")
        let regionURL = atlasRoot.appendingPathComponent("meshes/442.obj")
        guard FileManager.default.isReadableFile(atPath: rootURL.path),
              FileManager.default.isReadableFile(atPath: regionURL.path)
        else { return }

        let rootMesh = try decodeCachedMeshResult(
            target: "root",
            region: nil,
            meshURL: rootURL,
            atlasRoot: atlasRoot
        )
        let selectedRegion: [String: Any] = [
            "structureId": 442,
            "acronym": "RSPd1",
            "name": "Retrosplenial area, dorsal part, layer 1",
            "parentStructureId": 879,
            "structureIdPath": [997, 8, 567, 688, 695, 315, 254, 879, 442],
            "rgb": [26, 166, 152],
        ]
        let regionMesh = try decodeCachedMeshResult(
            target: "region",
            region: selectedRegion,
            meshURL: regionURL,
            atlasRoot: atlasRoot
        )
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let view = AtlasInteractiveSCNView(
            frame: CGRect(x: 0, y: 0, width: 640, height: 480)
        )
        let controller = AnimalSceneController(view: view)
        let rootOnly = try AnimalSceneSnapshot(
            projectId: "reviewed-cache-region-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: rootMesh,
            selectedProbePlan: nil
        )
        await controller.apply(snapshot: rootOnly) { _ in }
        let before = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 640, height: 480))
        )

        let highlighted = try AnimalSceneSnapshot(
            projectId: "reviewed-cache-region-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: rootMesh,
            highlightedRegionMesh: regionMesh,
            selectedProbePlan: nil
        )
        await controller.apply(snapshot: highlighted) { _ in }
        let after = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 640, height: 480))
        )

        let regionNode = try #require(
            view.scene?.rootNode.childNode(
                withName: "allen-region-442",
                recursively: true
            )
        )
        let regionGeometryNode = try #require(
            regionNode.childNodes(passingTest: { node, _ in
                node.geometry != nil
            }).first
        )
        let regionMaterial = try #require(
            regionGeometryNode.geometry?.firstMaterial
        )
        let rootLayer = try #require(
            view.scene?.rootNode.childNode(
                withName: "allen-mouse-root-mesh",
                recursively: false
            )
        )
        let brainGeometryNode = try #require(
            rootLayer.childNodes(passingTest: { node, _ in
                node.geometry != nil
            }).first
        )
        let selectedBrainMaterial = try #require(
            brainGeometryNode.geometry?.firstMaterial
        )

        #expect(regionGeometryNode.renderingOrder == 0)
        #expect(regionMaterial.name == "selected-allen-region")
        #expect(regionMaterial.lightingModel == .constant)
        #expect(abs(regionMaterial.transparency - 0.94) < 0.0001)
        #expect(!regionMaterial.readsFromDepthBuffer)
        #expect(!regionMaterial.writesToDepthBuffer)
        #expect(selectedBrainMaterial.fillMode == .lines)
        #expect(changedPixelCount(before, after) >= 100)
        #expect(
            selectedRegionPixelCount(after, rgb: (26, 166, 152)) >= 100
        )

        await controller.apply(snapshot: rootOnly) { _ in }
        let restoredBrainMaterial = try #require(
            brainGeometryNode.geometry?.firstMaterial
        )
        #expect(
            view.scene?.rootNode.childNode(
                withName: "allen-region-442",
                recursively: true
            ) == nil
        )
        #expect(restoredBrainMaterial.fillMode == .fill)
        #expect(abs(restoredBrainMaterial.transparency - 0.36) < 0.0001)
    }

    @Test("A selected deep TH mesh remains visibly colored inside the reviewed root shell")
    @MainActor
    func selectedThalamusRendersWithReviewedAtlasCache() async throws {
        let atlasRoot = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(
                ".brainglobe/allen_mouse_25um_v1.2",
                isDirectory: true
            )
            .standardizedFileURL
        let rootURL = atlasRoot.appendingPathComponent("meshes/997.obj")
        let regionURL = atlasRoot.appendingPathComponent("meshes/549.obj")
        guard FileManager.default.isReadableFile(atPath: rootURL.path),
              FileManager.default.isReadableFile(atPath: regionURL.path)
        else { return }

        let rootMesh = try decodeCachedMeshResult(
            target: "root",
            region: nil,
            meshURL: rootURL,
            atlasRoot: atlasRoot
        )
        let regionMesh = try decodeCachedMeshResult(
            target: "region",
            region: [
                "structureId": 549,
                "acronym": "TH",
                "name": "Thalamus",
                "parentStructureId": 1129,
                "structureIdPath": [997, 8, 343, 1129, 549],
                "rgb": [255, 112, 128],
            ],
            meshURL: regionURL,
            atlasRoot: atlasRoot
        )
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let snapshot = try AnimalSceneSnapshot(
            projectId: "reviewed-cache-thalamus-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: rootMesh,
            highlightedRegionMesh: regionMesh,
            selectedProbePlan: nil
        )
        let view = AtlasInteractiveSCNView(
            frame: CGRect(x: 0, y: 0, width: 640, height: 480)
        )
        let controller = AnimalSceneController(view: view)

        await controller.apply(snapshot: snapshot) { _ in }
        let rendered = try bitmap(
            from: controller.offscreenSnapshot(size: CGSize(width: 640, height: 480))
        )
        let thalamusRoot = try #require(
            view.scene?.rootNode.childNode(
                withName: "allen-region-549",
                recursively: true
            )
        )
        let thalamusGeometry = try #require(
            thalamusRoot.childNodes(passingTest: { node, _ in
                node.geometry != nil
            }).first
        )
        let material = try #require(
            thalamusGeometry.geometry?.firstMaterial
        )

        #expect(thalamusGeometry.geometry?.elements.first?.primitiveCount == 13_170)
        #expect(material.name == "selected-allen-region")
        #expect(material.lightingModel == .constant)
        #expect(abs(material.transparency - 0.94) < 0.0001)
        #expect(
            selectedRegionPixelCount(rendered, rgb: (255, 112, 128)) >= 100
        )
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

    @Test("Home camera visibly separates all four NP2013 shanks in both layouts")
    @MainActor
    func homeCameraSeparatesFourShankLayouts() async throws {
        let fixture = try makeFixture()
        defer { try? FileManager.default.removeItem(at: fixture.root) }
        let meshResult = try decodeMeshResult(fixture: fixture)
        let anchor = try decode(
            AtlasPhysicalPoint.self,
            object: physicalPoint(ap: 6_600, dv: 4_000, ml: 5_700)
        )
        let snapshot = try AnimalSceneSnapshot(
            projectId: "four-shank-camera-project",
            projectRevision: 1,
            rendererAnchor: anchor,
            meshResult: meshResult,
            selectedProbePlan: nil
        )
        let view = AtlasInteractiveSCNView(
            frame: CGRect(x: 0, y: 0, width: 640, height: 480)
        )
        let controller = AnimalSceneController(view: view)
        await controller.apply(snapshot: snapshot) { _ in }
        let probeLayer = try #require(
            view.scene?.rootNode.childNode(
                withName: "selected-probe-layer",
                recursively: false
            )
        )

        for layout in [0, 90] {
            probeLayer.childNodes.forEach { $0.removeFromParentNode() }
            let layoutShanks = np2013Shanks(layoutRotationDegrees: layout)
            let probe = try ProbeEnvelopeNodeFactory.makeNode(
                for: layoutShanks,
                usableForNavigation: false,
                transform: snapshot.transform
            )
            probeLayer.addChildNode(probe)
            controller.setCameraHome(for: snapshot, shanks: layoutShanks)
            _ = controller.offscreenSnapshot(
                size: CGSize(width: 640, height: 480)
            )

            let projected = probe.childNodes.map {
                view.projectPoint($0.worldPosition)
            }
            let adjacentDistances = zip(projected, projected.dropFirst()).map {
                hypot(
                    Double($1.x - $0.x),
                    Double($1.y - $0.y)
                )
            }
            #expect(projected.count == 4)
            #expect(adjacentDistances.count == 3)
            #expect(
                adjacentDistances.allSatisfy { $0 > 4 },
                "Layout \(layout) must show a visible gap between every adjacent shank."
            )

            var endpointProjections: [SCNVector3] = []
            for shank in layoutShanks {
                for point in [shank.renderedProximalEnd, shank.tip] {
                    let scenePoint = try snapshot.transform.scenePoint(point)
                    endpointProjections.append(
                        view.projectPoint(SCNVector3(scenePoint))
                    )
                }
            }
            let allEndpointsVisible = endpointProjections.allSatisfy {
                $0.x >= 0 && $0.x <= 640
                    && $0.y >= 0 && $0.y <= 480
                    && $0.z >= 0 && $0.z <= 1
            }
            #expect(
                allEndpointsVisible,
                "The complete 10 mm shanks must fit the default 3D camera."
            )

            let atlasMinimum = snapshot.meshResult.sourceCoordinateFrame
                .bounds.minimumInclusiveMicrometres
            let atlasMaximum = snapshot.meshResult.sourceCoordinateFrame
                .bounds.maximumExclusiveMicrometres
            var atlasCornerProjections: [SCNVector3] = []
            for ap in [atlasMinimum[0], atlasMaximum[0]] {
                for dv in [atlasMinimum[1], atlasMaximum[1]] {
                    for ml in [atlasMinimum[2], atlasMaximum[2]] {
                        let point = try snapshot.transform.scenePoint(
                            apMicrometres: ap,
                            dvMicrometres: dv,
                            mlMicrometres: ml
                        )
                        atlasCornerProjections.append(
                            view.projectPoint(SCNVector3(point))
                        )
                    }
                }
            }
            let atlasWidth = try #require(
                atlasCornerProjections.map(\.x).max()
            ) - (try #require(atlasCornerProjections.map(\.x).min()))
            let atlasHeight = try #require(
                atlasCornerProjections.map(\.y).max()
            ) - (try #require(atlasCornerProjections.map(\.y).min()))
            #expect(
                atlasWidth >= 180 && atlasHeight >= 100,
                "Framing the external shaft must not reduce the brain to an unusable speck."
            )
        }
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

    private func selectedRegionPixelCount(
        _ bitmap: NSBitmapImageRep,
        rgb: (red: Int, green: Int, blue: Int)
    ) -> Int {
        let expected = (
            red: CGFloat(rgb.red) / 255,
            green: CGFloat(rgb.green) / 255,
            blue: CGFloat(rgb.blue) / 255
        )
        var count = 0
        for y in 0 ..< bitmap.pixelsHigh {
            for x in 0 ..< bitmap.pixelsWide {
                guard let color = bitmap.colorAt(x: x, y: y)?
                    .usingColorSpace(.deviceRGB)
                else { continue }
                if abs(color.redComponent - expected.red) < 0.18,
                   abs(color.greenComponent - expected.green) < 0.18,
                   abs(color.blueComponent - expected.blue) < 0.18
                {
                    count += 1
                }
            }
        }
        return count
    }

    private func linearSRGBComponent(_ byte: Int) -> CGFloat {
        let value = Double(byte) / 255
        if value <= 0.04045 {
            return CGFloat(value / 12.92)
        }
        return CGFloat(pow((value + 0.055) / 1.055, 2.4))
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

    private func np2013Shanks(
        layoutRotationDegrees: Int
    ) -> [ProbePlacedShank] {
        (0 ..< 4).map { index in
            let offset = Double(index) * 250
            let ap = 5_200 + (layoutRotationDegrees == 0 ? offset : 0)
            let ml = 5_700 - (layoutRotationDegrees == 90 ? offset : 0)
            let surfaceEntry = ProbePhysicalPoint(
                apMicrometres: ap,
                dvMicrometres: 500,
                mlMicrometres: ml
            )
            return ProbePlacedShank(
                shankId: "shank-\(index)",
                entry: surfaceEntry,
                tip: ProbePhysicalPoint(
                    apMicrometres: ap,
                    dvMicrometres: 2_800,
                    mlMicrometres: ml
                ),
                widthMicrometres: 70,
                thicknessMicrometres: 24,
                conservativeEnvelopeRadiusMicrometres: 37,
                envelopeDefinition:
                    "circumscribed-radius-of-rectangular-cross-section",
                surfaceEntry: surfaceEntry,
                proximalEnd: ProbePhysicalPoint(
                    apMicrometres: ap,
                    dvMicrometres: -7_200,
                    mlMicrometres: ml,
                    insideAtlas: false
                ),
                totalLengthMicrometres: 10_000
            )
        }
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
        let sha = LowercaseHex.encode(SHA256.hash(data: data))
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
        let regionSHA = LowercaseHex.encode(SHA256.hash(data: regionData))
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
        return try decode(
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
        ),
        region: [String: Any]? = nil
    ) throws -> AtlasMeshResult {
        let resolvedRegion = region ?? [
            "structureId": 549,
            "acronym": "TH",
            "name": "Thalamus",
            "parentStructureId": 997,
            "structureIdPath": [997, 549],
            "rgb": [255, 112, 128],
        ]
        return try decode(
            AtlasMeshResult.self,
            object: [
                "protocolVersion": 1,
                "target": "region",
                "region": resolvedRegion,
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

    private func decodeCachedMeshResult(
        target: String,
        region: [String: Any]?,
        meshURL: URL,
        atlasRoot: URL
    ) throws -> AtlasMeshResult {
        let data = try Data(contentsOf: meshURL, options: [.mappedIfSafe])
        let sha256 = LowercaseHex.encode(SHA256.hash(data: data))
        return try decode(
            AtlasMeshResult.self,
            object: [
                "protocolVersion": 1,
                "target": target,
                "region": region.map { $0 as Any } ?? NSNull(),
                "mesh": [
                    "canonicalPath": meshURL.path,
                    "atlasRootCanonicalPath": atlasRoot.path,
                    "pathUnderAtlasRoot":
                        "meshes/\(meshURL.lastPathComponent)",
                    "sha256": sha256,
                    "byteSize": data.count,
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
