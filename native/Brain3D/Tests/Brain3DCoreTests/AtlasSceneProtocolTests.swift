import Brain3DCore
import Foundation
import Testing

@Suite("Strict 3D atlas bridge protocol")
struct AtlasSceneProtocolTests {
    @Test("Mesh and ray requests use only the reviewed protocol fields")
    func requestShapes() throws {
        let regionsData = try JSONEncoder().encode(
            try AtlasRegionsParameters(offset: 500, limit: 340)
        )
        let regions = try #require(
            JSONSerialization.jsonObject(with: regionsData) as? [String: Any]
        )
        #expect(Set(regions.keys) == Set(["protocolVersion", "offset", "limit"]))
        #expect(regions["offset"] as? Int == 500)
        #expect(regions["limit"] as? Int == 340)

        let searchData = try JSONEncoder().encode(
            try AtlasRegionSearchParameters(query: "thalamus", limit: 25)
        )
        let search = try #require(
            JSONSerialization.jsonObject(with: searchData) as? [String: Any]
        )
        #expect(Set(search.keys) == Set(["protocolVersion", "query", "limit"]))
        #expect(search["query"] as? String == "thalamus")
        #expect(search["limit"] as? Int == 25)

        let overlayData = try JSONEncoder().encode(
            try AtlasRegionOverlayParameters(
                structureId: 549,
                orientation: .sagittal,
                index: 228
            )
        )
        let overlay = try #require(
            JSONSerialization.jsonObject(with: overlayData) as? [String: Any]
        )
        #expect(Set(overlay.keys) == Set([
            "protocolVersion", "structureId", "orientation", "index",
        ]))
        #expect(overlay["structureId"] as? Int == 549)
        #expect(overlay["orientation"] as? String == "sagittal")
        #expect(overlay["index"] as? Int == 228)

        let meshData = try JSONEncoder().encode(try AtlasMeshParameters())
        let mesh = try #require(JSONSerialization.jsonObject(with: meshData) as? [String: Any])
        #expect(Set(mesh.keys) == Set(["protocolVersion", "target"]))
        #expect(mesh["target"] as? String == "root")

        let start = try AtlasRayPoint(
            apMicrometres: -10,
            dvMicrometres: 20,
            mlMicrometres: 30
        )
        let end = try AtlasRayPoint(
            apMicrometres: 100,
            dvMicrometres: 20,
            mlMicrometres: 30
        )
        let rayData = try JSONEncoder().encode(
            try AtlasRayPickParameters(start: start, end: end)
        )
        let ray = try #require(JSONSerialization.jsonObject(with: rayData) as? [String: Any])
        #expect(Set(ray.keys) == Set([
            "protocolVersion", "frameId",
            "startApMicrometres", "startDvMicrometres", "startMlMicrometres",
            "endApMicrometres", "endDvMicrometres", "endMlMicrometres",
        ]))
        #expect(ray["frameId"] as? String == AtlasSceneContract.physicalFrameId)
    }

    @Test("Annotation region overlays decode for dorsal and every orthogonal view")
    func regionOverlayDecoding() throws {
        let coronal = try decode(
            AtlasRegionOverlayResult.self,
            object: regionOverlayPayload(orientation: "coronal", index: 100)
        )
        #expect(coronal.orientation == .coronal)
        #expect(coronal.index == 100)
        #expect(coronal.fixedAxis == .ap)
        #expect(coronal.width == 456)
        #expect(coronal.height == 320)
        #expect(coronal.region.acronym == "TH")
        #expect(coronal.includedStructureIds == [549, 1_000_001])

        let dorsal = try decode(
            AtlasRegionOverlayResult.self,
            object: regionOverlayPayload(orientation: "dorsal", index: nil)
        )
        #expect(dorsal.orientation == .dorsal)
        #expect(dorsal.index == nil)
        #expect(dorsal.sliceCount == nil)
        #expect(dorsal.fixedAxis == nil)
        #expect(dorsal.rowAxis == .ap)
        #expect(dorsal.columnAxis == .ml)
        #expect(dorsal.width == 456)
        #expect(dorsal.height == 528)
    }

    @Test("Region overlays fail closed on wrong axes, duplicate descendants, or extra fields")
    func invalidRegionOverlayPayloads() throws {
        var wrongAxis = regionOverlayPayload(orientation: "horizontal", index: 10)
        wrongAxis["fixedAxis"] = "AP"
        #expect(throws: Error.self) {
            try decode(AtlasRegionOverlayResult.self, object: wrongAxis)
        }

        var duplicate = regionOverlayPayload(orientation: "dorsal", index: nil)
        duplicate["includedStructureIds"] = [549, 549]
        #expect(throws: Error.self) {
            try decode(AtlasRegionOverlayResult.self, object: duplicate)
        }

        var extra = regionOverlayPayload(orientation: "sagittal", index: 200)
        extra["approximate"] = true
        #expect(throws: Error.self) {
            try decode(AtlasRegionOverlayResult.self, object: extra)
        }
    }

    @Test("Two strict pages load all 840 structures and close the complete tree")
    func completePagedOntology() throws {
        let records = ontologyRegions()
        #expect(records.count == 840)

        let first = try decode(
            AtlasRegionsResult.self,
            object: regionsPage(
                records: Array(records.prefix(500)),
                offset: 0,
                totalCount: records.count
            )
        )
        let second = try decode(
            AtlasRegionsResult.self,
            object: regionsPage(
                records: Array(records.dropFirst(500)),
                offset: 500,
                totalCount: records.count
            )
        )

        var accumulator = AtlasRegionPageAccumulator()
        try accumulator.append(first)
        #expect(accumulator.nextOffset == 500)
        #expect(throws: AtlasSceneContractError.self) {
            try accumulator.finish()
        }
        try accumulator.append(second)

        let hierarchy = try accumulator.finish()
        #expect(hierarchy.regions.count == 840)
        #expect(hierarchy.roots.count == 1)
        #expect(hierarchy.roots[0].region.structureId == 997)
        #expect(hierarchy.roots[0].children.count == 839)
        #expect(hierarchy.children(of: 997).count == 839)
        #expect(hierarchy.region(structureId: 1_000_838)?.acronym == "R838")
        #expect(
            hierarchy.region(structureId: 1_000_838)?.structureIdPath
                == [997, 1_000_838]
        )
    }

    @Test("Paging rejects changed identity, duplicates, and an unclosed parent path")
    func invalidPagedOntology() throws {
        let root = ontologyRegions()[0]
        let child = ontologyRegions()[1]
        let first = try decode(
            AtlasRegionsResult.self,
            object: regionsPage(records: [root], offset: 0, totalCount: 2)
        )

        var changedAtlasPage = regionsPage(
            records: [child],
            offset: 1,
            totalCount: 2
        )
        var changedAtlas = try #require(changedAtlasPage["atlas"] as? [String: Any])
        changedAtlas["citation"] = "Different atlas citation"
        changedAtlasPage["atlas"] = changedAtlas
        let changedIdentity = try decode(
            AtlasRegionsResult.self,
            object: changedAtlasPage
        )
        var changedIdentityAccumulator = AtlasRegionPageAccumulator()
        try changedIdentityAccumulator.append(first)
        #expect(throws: AtlasSceneContractError.self) {
            try changedIdentityAccumulator.append(changedIdentity)
        }

        let duplicate = try decode(
            AtlasRegionsResult.self,
            object: regionsPage(records: [root], offset: 1, totalCount: 2)
        )
        var duplicateAccumulator = AtlasRegionPageAccumulator()
        try duplicateAccumulator.append(first)
        #expect(throws: AtlasSceneContractError.self) {
            try duplicateAccumulator.append(duplicate)
        }

        let orphan: [String: Any] = [
            "structureId": 2_000_000,
            "acronym": "ORPHAN",
            "name": "Orphan structure",
            "parentStructureId": 1_999_999,
            "structureIdPath": [1_999_999, 2_000_000],
            "rgb": [12, 34, 56],
        ]
        let orphanPage = try decode(
            AtlasRegionsResult.self,
            object: regionsPage(records: [root, orphan], offset: 0, totalCount: 2)
        )
        var orphanAccumulator = AtlasRegionPageAccumulator()
        try orphanAccumulator.append(orphanPage)
        #expect(throws: AtlasSceneContractError.self) {
            try orphanAccumulator.finish()
        }
    }

    @Test("Search decodes non-cortical Allen structures without a curated allow-list")
    func wholeOntologySearchDecoding() throws {
        let result = try decode(
            AtlasRegionSearchResult.self,
            object: [
                "protocolVersion": 1,
                "query": "thalamus",
                "matchingRule": AtlasSceneContract.regionSearchMatchingRule,
                "returnedCount": 1,
                "totalMatchCount": 1,
                "results": [
                    [
                        "matchKind": "nameExact",
                        "region": thalamusRegion(),
                    ],
                ],
                "atlas": atlas(),
            ]
        )

        #expect(result.results.count == 1)
        #expect(result.results[0].region.structureId == 549)
        #expect(result.results[0].region.acronym == "TH")
        #expect(result.results[0].matchKind == .nameExact)
    }

    @Test("Region mesh descriptor carries its exact full-ontology identity")
    func regionMeshDecoding() throws {
        var payload = meshPayload()
        payload["target"] = "region"
        payload["region"] = thalamusRegion()
        var descriptor = try #require(payload["mesh"] as? [String: Any])
        descriptor["canonicalPath"] = "/tmp/allen-atlas/meshes/549.obj"
        descriptor["pathUnderAtlasRoot"] = "meshes/549.obj"
        payload["mesh"] = descriptor

        let result = try decode(AtlasMeshResult.self, object: payload)

        #expect(result.target == .region)
        #expect(result.region?.acronym == "TH")
        #expect(result.mesh.pathUnderAtlasRoot == "meshes/549.obj")
    }

    @Test("Verified root mesh descriptor and provenance decode together")
    func meshDecoding() throws {
        let result = try decode(AtlasMeshResult.self, object: meshPayload())

        #expect(result.target == .root)
        #expect(result.region == nil)
        #expect(result.mesh.pathUnderAtlasRoot == "meshes/997.obj")
        #expect(result.mesh.byteSize == 4_728_758)
        #expect(result.atlas.shapeVoxels.apVoxels == 528)
    }

    @Test("Mesh payload fails closed on path escape, extra fields, or target mismatch")
    func invalidMeshPayloads() throws {
        var escaped = meshPayload()
        var escapedDescriptor = try #require(escaped["mesh"] as? [String: Any])
        escapedDescriptor["pathUnderAtlasRoot"] = "../outside.obj"
        escaped["mesh"] = escapedDescriptor
        #expect(throws: Error.self) {
            try decode(AtlasMeshResult.self, object: escaped)
        }

        var extra = meshPayload()
        extra["contents"] = "not-allowed"
        #expect(throws: Error.self) {
            try decode(AtlasMeshResult.self, object: extra)
        }

        var mismatched = meshPayload()
        mismatched["target"] = "region"
        #expect(throws: Error.self) {
            try decode(AtlasMeshResult.self, object: mismatched)
        }
    }

    @Test("Ray hit locks algorithm, annotation, region, and physical frame")
    func rayHitDecoding() throws {
        let result = try decode(AtlasRayPickResult.self, object: rayPayload(hit: true))
        let hit = try #require(result.hit)

        #expect(result.status == .hit)
        #expect(result.algorithmVersion == AtlasSceneContract.rayPickAlgorithmVersion)
        #expect(hit.annotationStructureId == hit.region.structureId)
        #expect(hit.region.acronym == "VISp")
        #expect(hit.hemisphere == .right)
        #expect(hit.containingVoxelIndex.ap == 1)
    }

    @Test("No-hit and hit status cannot contradict the optional payload")
    func rayStatusConsistency() throws {
        let noHit = try decode(AtlasRayPickResult.self, object: rayPayload(hit: false))
        #expect(noHit.status == .noAnnotatedVoxel)
        #expect(noHit.hit == nil)

        var inconsistent = rayPayload(hit: false)
        inconsistent["status"] = "hit"
        #expect(throws: Error.self) {
            try decode(AtlasRayPickResult.self, object: inconsistent)
        }
    }

    @Test("Project state carries the persisted renderer anchor")
    func projectRendererAnchor() throws {
        let project: [String: Any] = [
            "projectId": "project-1",
            "title": "Animal plan",
            "subjectId": NSNull(),
            "path": NSNull(),
            "requiresSaveAs": true,
            "recoveredFromBackup": false,
            "schemaVersion": 4,
            "revision": 2,
            "isDirty": true,
            "animalResearchOnlyAcknowledged": true,
            "calibrationCount": 1,
            "activeCalibrationId": NSNull(),
            "probePlanCount": 0,
            "probeRegionAnalysisCount": 0,
            "rendererAnchor": point(ap: 6_612.5, dv: 4_012.5, ml: 5_712.5),
        ]
        let result = try decode(ProjectBridgeState.self, object: project)

        #expect(result.rendererAnchor?.apMicrometres == 6_612.5)
        #expect(result.rendererAnchor?.dvMicrometres == 4_012.5)
        #expect(result.rendererAnchor?.mlMicrometres == 5_712.5)
    }

    private func decode<T: Decodable>(_ type: T.Type, object: Any) throws -> T {
        try JSONDecoder().decode(
            type,
            from: JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        )
    }

    private func meshPayload() -> [String: Any] {
        [
            "protocolVersion": 1,
            "target": "root",
            "region": NSNull(),
            "mesh": [
                "canonicalPath": "/tmp/allen-atlas/meshes/997.obj",
                "atlasRootCanonicalPath": "/tmp/allen-atlas",
                "pathUnderAtlasRoot": "meshes/997.obj",
                "sha256": String(repeating: "b", count: 64),
                "byteSize": 4_728_758,
                "fileExtension": ".obj",
                "contentsIncluded": false,
            ],
            "sourceCoordinateFrame": coordinateFrame(),
            "atlas": atlas(),
        ]
    }

    private func rayPayload(hit: Bool) -> [String: Any] {
        [
            "protocolVersion": 1,
            "status": hit ? "hit" : "noAnnotatedVoxel",
            "algorithmVersion": AtlasSceneContract.rayPickAlgorithmVersion,
            "hit": hit ? [
                "entryPoint": point(ap: 25, dv: 50, ml: 75),
                "voxelCenter": point(ap: 37.5, dv: 62.5, ml: 87.5),
                "containingVoxelIndex": [
                    "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
                    "ap": 1,
                    "dv": 2,
                    "ml": 3,
                ],
                "annotationStructureId": 385,
                "region": region(),
                "hemisphere": "right",
                "distanceFromRayStartMicrometres": 100.0,
                "distanceInsideVoxelMicrometres": 25.0,
            ] : NSNull(),
            "coordinateFrame": coordinateFrame(),
            "atlas": atlas(),
        ]
    }

    private func regionOverlayPayload(
        orientation: String,
        index: Int?
    ) -> [String: Any] {
        let sliceOrientation = AtlasSliceOrientation(rawValue: orientation)
        let width: Int
        let height: Int
        let sliceCount: Any
        let fixedAxis: Any
        let rowAxis: String
        let columnAxis: String
        if let sliceOrientation {
            switch sliceOrientation {
            case .coronal:
                width = 456
                height = 320
                sliceCount = 528
            case .sagittal:
                width = 528
                height = 320
                sliceCount = 456
            case .horizontal:
                width = 456
                height = 528
                sliceCount = 320
            }
            fixedAxis = sliceOrientation.fixedAxis.rawValue
            rowAxis = sliceOrientation.rowAxis.rawValue
            columnAxis = sliceOrientation.columnAxis.rawValue
        } else {
            width = 456
            height = 528
            sliceCount = NSNull()
            fixedAxis = NSNull()
            rowAxis = "AP"
            columnAxis = "ML"
        }
        return [
            "protocolVersion": 1,
            "algorithmVersion": AtlasSceneContract.regionOverlayAlgorithmVersion,
            "selectionRule": AtlasSceneContract.regionOverlaySelectionRule,
            "region": thalamusRegion(),
            "includedStructureIds": [549, 1_000_001],
            "visiblePixelCount": 100,
            "mimeType": "image/png",
            "colorModel": "RGBA",
            "alphaMode": "straight",
            "pngBase64": "AAAA",
            "width": width,
            "height": height,
            "orientation": orientation,
            "index": index.map { $0 as Any } ?? NSNull(),
            "sliceCount": sliceCount,
            "fixedAxis": fixedAxis,
            "rowAxis": rowAxis,
            "columnAxis": columnAxis,
            "atlas": atlas(),
        ]
    }

    private func regionsPage(
        records: [[String: Any]],
        offset: Int,
        totalCount: Int
    ) -> [String: Any] {
        [
            "protocolVersion": 1,
            "offset": offset,
            "limit": 500,
            "returnedCount": records.count,
            "totalCount": totalCount,
            "hasMore": offset + records.count < totalCount,
            "regions": records,
            "atlas": atlas(),
        ]
    }

    private func ontologyRegions() -> [[String: Any]] {
        let root: [String: Any] = [
            "structureId": 997,
            "acronym": "root",
            "name": "root",
            "parentStructureId": NSNull(),
            "structureIdPath": [997],
            "rgb": [255, 255, 255],
        ]
        return [root] + (0 ..< 839).map { index in
            let structureId = 1_000_000 + index
            return [
                "structureId": structureId,
                "acronym": "R\(index)",
                "name": "Region \(index)",
                "parentStructureId": 997,
                "structureIdPath": [997, structureId],
                "rgb": [index % 256, (index * 3) % 256, (index * 7) % 256],
            ]
        }
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

    private func point(ap: Double, dv: Double, ml: Double) -> [String: Any] {
        [
            "frameId": AtlasSceneContract.physicalFrameId,
            "apMicrometres": ap,
            "dvMicrometres": dv,
            "mlMicrometres": ml,
        ]
    }

    private func region() -> [String: Any] {
        [
            "structureId": 385,
            "acronym": "VISp",
            "name": "Primary visual area",
            "parentStructureId": 315,
            "structureIdPath": [997, 8, 567, 688, 695, 315, 385],
            "rgb": [8, 133, 140],
        ]
    }

    private func thalamusRegion() -> [String: Any] {
        [
            "structureId": 549,
            "acronym": "TH",
            "name": "Thalamus",
            "parentStructureId": 997,
            "structureIdPath": [997, 549],
            "rgb": [255, 112, 128],
        ]
    }
}
