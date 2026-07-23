import Brain3DCore
import Foundation
import Testing

@Suite("Independent atlas-slice viewer protocol")
struct TriPlanarProtocolTests {
    @Test("Golden snapshot locks atlas identity, independent depths, and one region selection")
    func goldenSnapshot() throws {
        let snapshot = try JSONDecoder().decode(
            ViewerStateResult.self,
            from: try ViewerSnapshotFixture.data()
        ).snapshot

        #expect(snapshot.protocolVersion == 1)
        #expect(snapshot.projectRevision == 7)
        #expect(snapshot.projectId.uuidString.lowercased() == ViewerSnapshotFixture.projectId)
        #expect(snapshot.atlas.identifier == "allen_mouse_25um")
        #expect(snapshot.atlas.version == "1.2")
        #expect(snapshot.atlas.resolutionMicrometres == (try AtlasASRResolution(
            apMicrometres: 25,
            dvMicrometres: 25,
            mlMicrometres: 25
        )))
        #expect(snapshot.coordinateFrame.axisOrder == [.ap, .dv, .ml])
        #expect(snapshot.coordinateFrame.origin == [.anterior, .superior, .right])
        #expect(snapshot.coordinateFrame.positiveDirections == [.posterior, .inferior, .left])

        #expect(snapshot.slices.coronal.index == 1)
        #expect(snapshot.slices.sagittal.index == 5)
        #expect(snapshot.slices.horizontal.index == 2)
        #expect(snapshot.slices.coronal.fixedAxis == .ap)
        #expect(snapshot.slices.sagittal.fixedAxis == .ml)
        #expect(snapshot.slices.horizontal.fixedAxis == .dv)

        let selection = try #require(snapshot.selection)
        #expect(selection.orientation == .horizontal)
        #expect(selection.index == 2)
        #expect(selection.column == 3)
        #expect(selection.row == 1)
        #expect(selection.atlasPoint.apMicrometres == 37.5)
        #expect(selection.containingVoxelIndex == selectionVoxel(ap: 1, dv: 2, ml: 3))
        #expect(selection.hemisphere == .right)
        #expect(selection.region?.acronym == "VISp")
        #expect(selection.region?.structureIdPath == [997, 315, 385])
    }

    @Test("Selection may be null without coupling the three depths")
    func nullSelection() throws {
        let data = try ViewerSnapshotFixture.mutated { object in
            object["selection"] = NSNull()
        }
        let snapshot = try JSONDecoder().decode(ViewerStateResult.self, from: data).snapshot
        #expect(snapshot.selection == nil)
        let depths: [Int] = [
            snapshot.slices.coronal.index,
            snapshot.slices.sagittal.index,
            snapshot.slices.horizontal.index,
        ]
        #expect(depths == [1, 5, 2])
    }

    @Test("Replacing the selected ontology region cannot alter independent slice depths")
    func regionSelectionPreservesIndependentDepths() throws {
        let original = try JSONDecoder().decode(
            ViewerStateResult.self,
            from: try ViewerSnapshotFixture.data()
        ).snapshot
        let changedData = try ViewerSnapshotFixture.mutated { object in
            var selection = try nestedObject(object, "selection")
            selection["region"] = [
                "structureId": 549,
                "acronym": "TH",
                "name": "Thalamus",
                "parentStructureId": 997,
                "structureIdPath": [997, 549],
                "rgb": [255, 112, 128],
            ]
            try setNestedObject(&object, selection, "selection")
        }
        let changed = try JSONDecoder().decode(
            ViewerStateResult.self,
            from: changedData
        ).snapshot

        #expect(changed.selection?.region?.acronym == "TH")
        #expect(changed.slices == original.slices)
        let depths: [Int] = [
            changed.slices.coronal.index,
            changed.slices.sagittal.index,
            changed.slices.horizontal.index,
        ]
        #expect(depths == [1, 5, 2])
    }

    @Test("The supported methods encode exact protocol-v1 request fields")
    func exactRequestWireShapes() throws {
        let canonicalProjectId = "abcdefab-cdef-4abc-8def-abcdefabcdef"
        let projectId = try #require(UUID(uuidString: canonicalProjectId))

        let state = try jsonObject(ViewerStateParameters())
        #expect(Set(state.keys) == ["protocolVersion"])
        #expect(state["protocolVersion"] as? Int == 1)

        let sliceSet = try jsonObject(ViewerSliceSetParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            orientation: .sagittal,
            index: 5
        ))
        #expect(Set(sliceSet.keys) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "orientation", "index",
        ])
        #expect(sliceSet["projectId"] as? String == canonicalProjectId)
        #expect(sliceSet["orientation"] as? String == "sagittal")
        #expect(sliceSet["index"] as? Int == 5)

        let sliceRender = try jsonObject(ViewerSliceRenderParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            orientation: .coronal,
            index: 1
        ))
        #expect(Set(sliceRender.keys) == Set(sliceSet.keys))

        let pick = try jsonObject(ViewerRegionPickParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            orientation: .horizontal,
            index: 2,
            column: 3,
            row: 1
        ))
        #expect(Set(pick.keys) == [
            "protocolVersion", "projectId", "expectedProjectRevision",
            "orientation", "index", "column", "row",
        ])
        #expect(pick["projectId"] as? String == canonicalProjectId)

        let snapshot = try JSONDecoder().decode(
            ViewerStateResult.self,
            from: try ViewerSnapshotFixture.data()
        ).snapshot
        let navigation = try jsonObject(ViewerPointNavigationParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            atlas: snapshot.atlas,
            apMicrometres: 37.5,
            dvMicrometres: 62.5,
            mlMicrometres: 137.5
        ))
        #expect(Set(navigation.keys) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "point",
        ])
        let point = try #require(navigation["point"] as? [String: Any])
        #expect(Set(point.keys) == [
            "frameId", "atlasIdentifier", "atlasVersion", "componentOrder", "units",
            "apMicrometres", "dvMicrometres", "mlMicrometres",
        ])
        #expect(point["frameId"] as? String == "BRAINGLOBE_PHYSICAL_ASR_UM")
        #expect(point["atlasIdentifier"] as? String == "allen_mouse_25um")
        #expect(point["atlasVersion"] as? String == "1.2")
        #expect(point["componentOrder"] as? [String] == ["AP", "DV", "ML"])
        #expect(point["units"] as? String == "micrometre")

        #expect(ViewerBridgeMethod.allCases.map(\.rawValue) == [
            "viewer.state.get", "viewer.slice.set", "viewer.slice.render", "viewer.region.pick",
            "viewer.point.navigate",
        ])
    }

    @Test("Point navigation locks one point, one revision, and all three rendered frames")
    func pointNavigationResponse() throws {
        let data = try pointNavigationData()
        let result = try JSONDecoder().decode(ViewerPointNavigationResult.self, from: data)
        #expect(result.status == .pointNavigated)
        #expect(result.snapshot.selection == nil)
        #expect(result.navigatedPoint.apMicrometres == 37.5)
        #expect(result.containingVoxelIndex.ap == 1)
        #expect(result.containingVoxelIndex.dv == 2)
        #expect(result.containingVoxelIndex.ml == 5)
        #expect(result.renderedSlices.coronal.index == 1)
        #expect(result.renderedSlices.sagittal.index == 5)
        #expect(result.renderedSlices.horizontal.index == 2)

        let wrongStatus = try pointNavigationData { object in
            object["status"] = "sliceUpdated"
        }
        #expect(decodeFails(ViewerPointNavigationResult.self, from: wrongStatus))

        let wrongVoxel = try pointNavigationData { object in
            var voxel = try nestedObject(object, "containingVoxelIndex")
            voxel["ml"] = 4
            try setNestedObject(&object, voxel, "containingVoxelIndex")
        }
        #expect(decodeFails(ViewerPointNavigationResult.self, from: wrongVoxel))

        let partialDepths = try pointNavigationData { object in
            var sagittal = try nestedObject(object, "slices", "sagittal")
            sagittal["index"] = 4
            sagittal["sliceCenterMicrometres"] = 112.5
            try setNestedObject(&object, sagittal, "slices", "sagittal")
        }
        #expect(decodeFails(ViewerPointNavigationResult.self, from: partialDepths))

        let missingFrame = try pointNavigationData { object in
            var rendered = try nestedObject(object, "renderedSlices")
            rendered.removeValue(forKey: "horizontal")
            try setNestedObject(&object, rendered, "renderedSlices")
        }
        #expect(decodeFails(ViewerPointNavigationResult.self, from: missingFrame))

        let extraPointField = try pointNavigationData { object in
            var point = try nestedObject(object, "navigatedPoint")
            point["ambiguousX"] = 37.5
            try setNestedObject(&object, point, "navigatedPoint")
        }
        #expect(decodeFails(ViewerPointNavigationResult.self, from: extraPointField))

        let staleRenderedFrame = try pointNavigationData { object in
            var frame = try nestedObject(object, "renderedSlices", "coronal")
            frame["index"] = 0
            frame["sliceCenterMicrometres"] = 12.5
            try setNestedObject(&object, frame, "renderedSlices", "coronal")
        }
        #expect(decodeFails(ViewerPointNavigationResult.self, from: staleRenderedFrame))
    }

    @Test("Fused slice response locks its full-resolution frame to the changed view only")
    func fusedSliceResponse() throws {
        let data = try fusedSliceData(index: 1, center: 37.5, status: "sliceUpdated")
        let result = try JSONDecoder().decode(ViewerSliceRenderResult.self, from: data)
        #expect(result.status == .sliceUpdated)
        #expect(result.renderedSlice.index == result.snapshot.slices.coronal.index)
        #expect(result.snapshot.slices.sagittal.index == 5)
        #expect(result.snapshot.slices.horizontal.index == 2)

        #expect(decodeFails(
            ViewerSliceRenderResult.self,
            from: try fusedSliceData(index: 2, center: 62.5, status: "sliceUpdated")
        ))
        #expect(decodeFails(
            ViewerSliceRenderResult.self,
            from: try fusedSliceData(index: 1, center: 37.5, status: "regionSelected")
        ))
    }

    @Test("Slice and region mutations require their exact status and snapshot shape")
    func mutationResponses() throws {
        let sliceData = try ViewerSnapshotFixture.mutated { object in
            object["status"] = "sliceUpdated"
            object["selection"] = NSNull()
        }
        let slice = try JSONDecoder().decode(ViewerSliceUpdateResult.self, from: sliceData)
        #expect(slice.status == .sliceUpdated)
        #expect(slice.snapshot.selection == nil)

        let pickData = try ViewerSnapshotFixture.mutated { object in
            object["status"] = "regionSelected"
        }
        let pick = try JSONDecoder().decode(ViewerRegionPickResult.self, from: pickData)
        #expect(pick.status == .regionSelected)
        #expect(pick.snapshot.selection?.region?.acronym == "VISp")

        let missingSelection = try ViewerSnapshotFixture.mutated { object in
            object["status"] = "regionSelected"
            object["selection"] = NSNull()
        }
        #expect(decodeFails(ViewerRegionPickResult.self, from: missingSelection))
    }

    @Test("Unexpected or missing response fields fail closed")
    func exactResponseKeys() throws {
        let unexpected = try ViewerSnapshotFixture.mutated { object in
            object["opaqueConveniencePoint"] = ["x": 1, "y": 2, "z": 3]
        }
        #expect(decodeFails(ViewerStateResult.self, from: unexpected))

        let missing = try ViewerSnapshotFixture.mutated { object in
            object.removeValue(forKey: "projectRevision")
        }
        #expect(decodeFails(ViewerStateResult.self, from: missing))

        let nestedUnexpected = try ViewerSnapshotFixture.mutated { object in
            var coronal = try nestedObject(object, "slices", "coronal")
            coronal["legacyOverlayMarker"] = ["column": 3, "row": 2]
            try setNestedObject(&object, coronal, "slices", "coronal")
        }
        #expect(decodeFails(ViewerStateResult.self, from: nestedUnexpected))
    }

    @Test("Atlas identity and coordinate-frame substitutions fail closed")
    func atlasAndFrameIdentity() throws {
        let wrongAtlas = try ViewerSnapshotFixture.mutated { object in
            var atlas = try nestedObject(object, "atlas")
            atlas["version"] = "latest"
            try setNestedObject(&object, atlas, "atlas")
        }
        #expect(decodeFails(ViewerStateResult.self, from: wrongAtlas))

        let wrongHash = try ViewerSnapshotFixture.mutated { object in
            var atlas = try nestedObject(object, "atlas")
            atlas["metadataSha256"] = String(repeating: "A", count: 64)
            try setNestedObject(&object, atlas, "atlas")
        }
        #expect(decodeFails(ViewerStateResult.self, from: wrongHash))

        let wrongAxes = try ViewerSnapshotFixture.mutated { object in
            var frame = try nestedObject(object, "coordinateFrame")
            frame["axisOrder"] = ["ML", "DV", "AP"]
            try setNestedObject(&object, frame, "coordinateFrame")
        }
        #expect(decodeFails(ViewerStateResult.self, from: wrongAxes))

        let falseStereotaxy = try ViewerSnapshotFixture.mutated { object in
            var frame = try nestedObject(object, "coordinateFrame")
            frame["bregmaRelative"] = true
            try setNestedObject(&object, frame, "coordinateFrame")
        }
        #expect(decodeFails(ViewerStateResult.self, from: falseStereotaxy))
    }

    @Test("Independent slice and selection-derived metadata must agree")
    func canonicalDerivedState() throws {
        let wrongCenter = try ViewerSnapshotFixture.mutated { object in
            var sagittal = try nestedObject(object, "slices", "sagittal")
            sagittal["sliceCenterMicrometres"] = 87.5
            try setNestedObject(&object, sagittal, "slices", "sagittal")
        }
        #expect(decodeFails(ViewerStateResult.self, from: wrongCenter))

        let staleSelection = try ViewerSnapshotFixture.mutated { object in
            var selection = try nestedObject(object, "selection")
            selection["index"] = 1
            try setNestedObject(&object, selection, "selection")
        }
        #expect(decodeFails(ViewerStateResult.self, from: staleSelection))

        let wrongVoxel = try ViewerSnapshotFixture.mutated { object in
            var selection = try nestedObject(object, "selection")
            var voxel = try nestedObject(selection, "containingVoxelIndex")
            voxel["ap"] = 2
            try setNestedObject(&selection, voxel, "containingVoxelIndex")
            try setNestedObject(&object, selection, "selection")
        }
        #expect(decodeFails(ViewerStateResult.self, from: wrongVoxel))

        let wrongPoint = try ViewerSnapshotFixture.mutated { object in
            var selection = try nestedObject(object, "selection")
            var point = try nestedObject(selection, "atlasPoint")
            point["mlMicrometres"] = 88.0
            try setNestedObject(&selection, point, "atlasPoint")
            try setNestedObject(&object, selection, "selection")
        }
        #expect(decodeFails(ViewerStateResult.self, from: wrongPoint))

        let wrongHemisphere = try ViewerSnapshotFixture.mutated { object in
            var selection = try nestedObject(object, "selection")
            selection["hemisphere"] = "left"
            try setNestedObject(&object, selection, "selection")
        }
        #expect(decodeFails(ViewerStateResult.self, from: wrongHemisphere))

        let negativeRevision = try ViewerSnapshotFixture.mutated { object in
            object["projectRevision"] = -1
        }
        #expect(decodeFails(ViewerStateResult.self, from: negativeRevision))
    }

    @Test("Region hierarchy and color are validated within the selection")
    func regionValidation() throws {
        let wrongParent = try ViewerSnapshotFixture.mutated { object in
            var selection = try nestedObject(object, "selection")
            var region = try nestedObject(selection, "region")
            region["parentStructureId"] = 997
            try setNestedObject(&selection, region, "region")
            try setNestedObject(&object, selection, "selection")
        }
        #expect(decodeFails(ViewerStateResult.self, from: wrongParent))

        let invalidRGB = try ViewerSnapshotFixture.mutated { object in
            var selection = try nestedObject(object, "selection")
            var region = try nestedObject(selection, "region")
            region["rgb"] = [8, 133, 256]
            try setNestedObject(&selection, region, "region")
            try setNestedObject(&object, selection, "selection")
        }
        #expect(decodeFails(ViewerStateResult.self, from: invalidRGB))
    }

    @Test("Invalid outgoing mutation indices cannot be constructed")
    func invalidOutgoingValues() throws {
        let projectId = try #require(UUID(uuidString: ViewerSnapshotFixture.projectId))
        let atlas = try JSONDecoder().decode(
            ViewerStateResult.self,
            from: try ViewerSnapshotFixture.data()
        ).snapshot.atlas
        #expect(throws: ViewerContractError.invalid(
            "Expected project revision and slice index must be nonnegative."
        )) {
            try ViewerSliceSetParameters(
                projectId: projectId,
                expectedProjectRevision: 7,
                orientation: .coronal,
                index: -1
            )
        }
        #expect(throws: ViewerContractError.invalid(
            "Expected revision, slice index, column, and row must be nonnegative."
        )) {
            try ViewerRegionPickParameters(
                projectId: projectId,
                expectedProjectRevision: 7,
                orientation: .coronal,
                index: 1,
                column: -1,
                row: 2
            )
        }
        #expect(throws: ViewerContractError.self) {
            try ViewerPointNavigationParameters(
                projectId: projectId,
                expectedProjectRevision: 7,
                atlas: atlas,
                apMicrometres: 100,
                dvMicrometres: 50,
                mlMicrometres: 50
            )
        }
        #expect(throws: ViewerContractError.invalid(
            "Expected project revision must be nonnegative."
        )) {
            try ViewerPointNavigationParameters(
                projectId: projectId,
                expectedProjectRevision: -1,
                atlas: atlas,
                apMicrometres: 37.5,
                dvMicrometres: 62.5,
                mlMicrometres: 137.5
            )
        }
    }

    private func fusedSliceData(index: Int, center: Double, status: String) throws -> Data {
        try ViewerSnapshotFixture.mutated { object in
            let atlas = try #require(object["atlas"] as? [String: Any])
            object["status"] = status
            object["selection"] = NSNull()
            object["renderedSlice"] = [
                "protocolVersion": 1,
                "mimeType": "image/png",
                "pngBase64": "iVBORw0KGgo=",
                "width": 8,
                "height": 6,
                "orientation": "coronal",
                "index": index,
                "sliceCount": 4,
                "fixedAxis": "AP",
                "rowAxis": "DV",
                "columnAxis": "ML",
                "sliceCenterMicrometres": center,
                "atlas": atlas,
            ]
        }
    }

    private func pointNavigationData(
        mutate: ((inout [String: Any]) throws -> Void)? = nil
    ) throws -> Data {
        try ViewerSnapshotFixture.mutated { object in
            let atlas = try #require(object["atlas"] as? [String: Any])
            object["status"] = "pointNavigated"
            object["selection"] = NSNull()
            object["navigatedPoint"] = [
                "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
                "atlasIdentifier": "allen_mouse_25um",
                "atlasVersion": "1.2",
                "componentOrder": ["AP", "DV", "ML"],
                "units": "micrometre",
                "apMicrometres": 37.5,
                "dvMicrometres": 62.5,
                "mlMicrometres": 137.5,
            ]
            object["containingVoxelIndex"] = [
                "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
                "atlasIdentifier": "allen_mouse_25um",
                "atlasVersion": "1.2",
                "componentOrder": ["AP", "DV", "ML"],
                "ap": 1,
                "dv": 2,
                "ml": 5,
            ]
            object["renderedSlices"] = [
                "coronal": renderedSlice(
                    atlas: atlas,
                    orientation: "coronal",
                    index: 1,
                    count: 4,
                    fixed: "AP",
                    row: "DV",
                    column: "ML",
                    width: 8,
                    height: 6,
                    center: 37.5
                ),
                "sagittal": renderedSlice(
                    atlas: atlas,
                    orientation: "sagittal",
                    index: 5,
                    count: 8,
                    fixed: "ML",
                    row: "DV",
                    column: "AP",
                    width: 4,
                    height: 6,
                    center: 137.5
                ),
                "horizontal": renderedSlice(
                    atlas: atlas,
                    orientation: "horizontal",
                    index: 2,
                    count: 6,
                    fixed: "DV",
                    row: "AP",
                    column: "ML",
                    width: 8,
                    height: 4,
                    center: 62.5
                ),
            ]
            try mutate?(&object)
        }
    }
}

private func renderedSlice(
    atlas: [String: Any],
    orientation: String,
    index: Int,
    count: Int,
    fixed: String,
    row: String,
    column: String,
    width: Int,
    height: Int,
    center: Double
) -> [String: Any] {
    [
        "protocolVersion": 1,
        "mimeType": "image/png",
        "pngBase64": "iVBORw0KGgo=",
        "width": width,
        "height": height,
        "orientation": orientation,
        "index": index,
        "sliceCount": count,
        "fixedAxis": fixed,
        "rowAxis": row,
        "columnAxis": column,
        "sliceCenterMicrometres": center,
        "atlas": atlas,
    ]
}

private enum ViewerSnapshotFixture {
    static let projectId = "00000000-0000-0000-0000-000000000001"

    static func data() throws -> Data {
        guard let fixture = Bundle.module.url(
            forResource: "viewer_snapshot_v1",
            withExtension: "json",
            subdirectory: "Fixtures"
        ) else {
            throw FixtureError.missingResource("Fixtures/viewer_snapshot_v1.json")
        }
        return try Data(contentsOf: fixture)
    }

    static func object() throws -> [String: Any] {
        guard let object = try JSONSerialization.jsonObject(with: data()) as? [String: Any] else {
            throw FixtureError.invalidShape
        }
        return object
    }

    static func mutated(_ change: (inout [String: Any]) throws -> Void) throws -> Data {
        var object = try object()
        try change(&object)
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }
}

private enum FixtureError: Error {
    case invalidShape
    case missingObject(String)
    case missingResource(String)
}

private func jsonObject<Value: Encodable>(_ value: Value) throws -> [String: Any] {
    guard let object = try JSONSerialization.jsonObject(
        with: JSONEncoder().encode(value)
    ) as? [String: Any] else {
        throw FixtureError.invalidShape
    }
    return object
}

private func decodeFails<Value: Decodable>(_: Value.Type, from data: Data) -> Bool {
    do {
        _ = try JSONDecoder().decode(Value.self, from: data)
        return false
    } catch {
        return true
    }
}

private func nestedObject(_ root: [String: Any], _ path: String...) throws -> [String: Any] {
    var current = root
    for component in path {
        guard let next = current[component] as? [String: Any] else {
            throw FixtureError.missingObject(path.joined(separator: "."))
        }
        current = next
    }
    return current
}

private func setNestedObject(
    _ root: inout [String: Any],
    _ value: [String: Any],
    _ path: String...
) throws {
    try setNestedObject(&root, value, path)
}

private func setNestedObject(
    _ root: inout [String: Any],
    _ value: [String: Any],
    _ path: [String]
) throws {
    guard let head = path.first else {
        throw FixtureError.missingObject("empty path")
    }
    if path.count == 1 {
        root[head] = value
        return
    }
    guard var child = root[head] as? [String: Any] else {
        throw FixtureError.missingObject(path.joined(separator: "."))
    }
    try setNestedObject(&child, value, Array(path.dropFirst()))
    root[head] = child
}

private func selectionVoxel(ap: Int, dv: Int, ml: Int) -> AtlasVoxelIndex? {
    let data = try? JSONSerialization.data(withJSONObject: [
        "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
        "ap": ap,
        "dv": dv,
        "ml": ml,
    ])
    return data.flatMap { try? JSONDecoder().decode(AtlasVoxelIndex.self, from: $0) }
}
