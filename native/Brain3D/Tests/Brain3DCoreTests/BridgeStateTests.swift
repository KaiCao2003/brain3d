import Brain3DCore
import Foundation
import Testing

@Suite("Bridge state honesty")
struct BridgeStateTests {
    @Test("Only the exact supported, loaded atlas becomes operational")
    func exactAtlasGate() {
        #expect(
            AtlasBridgeState(
                identifier: "allen_mouse_25um",
                version: "1.2",
                loaded: true,
                status: "ready"
            ).isSupportedAndLoaded
        )
        #expect(
            !AtlasBridgeState(
                identifier: "allen_mouse_10um",
                version: "1.2",
                loaded: true,
                status: "ready"
            ).isSupportedAndLoaded
        )
        #expect(
            !AtlasBridgeState(
                identifier: "allen_mouse_25um",
                version: "1.2",
                loaded: false,
                status: "not loaded"
            ).isSupportedAndLoaded
        )
    }

    @Test("An unloaded bridge state decodes without inventing vessels")
    func unloadedState() throws {
        let data = Data(
            """
            {"protocolVersion":1,"animalOnly":true,"warning":"Animal research only — not for human or clinical use","atlas":{"identifier":"allen_mouse_25um","version":"1.2","loaded":false,"status":"notLoaded"},"project":null,"subjectVessels":{"imported":false,"registered":false,"images":[]},"populationDensity":{"available":false,"visible":false,"opacity":0.65,"status":"notLoaded"}}
            """.utf8
        )

        let state = try JSONDecoder().decode(PlannerBridgeState.self, from: data)

        #expect(!state.atlas.isSupportedAndLoaded)
        #expect(!state.subjectVessels.imported)
        #expect(!state.subjectVessels.registered)
        #expect(state.subjectVessels.primaryImage == nil)
        #expect(!state.populationDensity.available)
        #expect(!state.populationDensity.visible)
        #expect(state.populationDensity.opacity == 0.65)
        try ReferenceDensityValidator.validateBridgeState(state.populationDensity)
    }

    @Test("The newest imported vessel image is the active image")
    func newestVesselImageIsPrimary() {
        let first = SubjectVesselImageBridgeState(
            imageId: "first",
            sourceName: "first.png",
            sourceSha256: String(repeating: "a", count: 64),
            byteSize: 10,
            widthPixels: 10,
            heightPixels: 10,
            registered: false,
            residualMicrometres: nil,
            lateralityConfirmed: false
        )
        let last = SubjectVesselImageBridgeState(
            imageId: "last",
            sourceName: "last.png",
            sourceSha256: String(repeating: "b", count: 64),
            byteSize: 20,
            widthPixels: 20,
            heightPixels: 20,
            registered: true,
            residualMicrometres: 2,
            lateralityConfirmed: true
        )

        let state = SubjectVesselsBridgeState(
            imported: true,
            registered: true,
            images: [first, last]
        )

        #expect(state.primaryImage?.imageId == "last")
    }

    @Test("Project dirty state and revision decode from the backend authority")
    func projectDirtyRevisionDecodes() throws {
        let data = Data(
            """
            {"protocolVersion":1,"animalOnly":true,"warning":"Animal research only — not for human or clinical use","atlas":{"identifier":"allen_mouse_25um","version":"1.2","loaded":true,"status":"loaded"},"project":{"projectId":"00000000-0000-0000-0000-000000000001","title":"Animal plan","subjectId":"mouse-a","path":null,"requiresSaveAs":true,"recoveredFromBackup":false,"schemaVersion":3,"revision":7,"isDirty":true,"animalResearchOnlyAcknowledged":true},"subjectVessels":{"imported":false,"registered":false,"images":[]},"populationDensity":{"available":false,"visible":false,"opacity":0.65,"status":"notLoaded"}}
            """.utf8
        )

        let state = try JSONDecoder().decode(PlannerBridgeState.self, from: data)

        #expect(state.project?.revision == 7)
        #expect(state.project?.isDirty == true)
        #expect(state.project?.animalResearchOnlyAcknowledged == true)
    }

    @Test("Viewer revisions reconcile without discarding project metadata or regressing")
    func viewerRevisionReconciliation() throws {
        let data = Data(
            """
            {"protocolVersion":1,"animalOnly":true,"warning":"Animal research only — not for human or clinical use","atlas":{"identifier":"allen_mouse_25um","version":"1.2","loaded":true,"status":"loaded"},"project":{"projectId":"00000000-0000-0000-0000-000000000001","title":"Animal plan","subjectId":"mouse-a","path":"/tmp/animal.brain3d","requiresSaveAs":false,"recoveredFromBackup":false,"schemaVersion":5,"revision":7,"isDirty":false,"animalResearchOnlyAcknowledged":true,"calibrationCount":2,"activeCalibrationId":"cal-1","probePlanCount":3,"probeRegionAnalysisCount":1},"subjectVessels":{"imported":false,"registered":false,"images":[]},"populationDensity":{"available":false,"visible":false,"opacity":0.65,"status":"notLoaded"}}
            """.utf8
        )
        let original = try JSONDecoder().decode(PlannerBridgeState.self, from: data)

        let advanced = original.updatingProjectRevision(8, isDirty: true)
        #expect(advanced.project?.revision == 8)
        #expect(advanced.project?.isDirty == true)
        #expect(advanced.project?.title == original.project?.title)
        #expect(advanced.project?.subjectId == original.project?.subjectId)
        #expect(advanced.project?.path == original.project?.path)
        #expect(advanced.project?.calibrationCount == original.project?.calibrationCount)
        #expect(advanced.project?.probePlanCount == original.project?.probePlanCount)

        let stale = advanced.updatingProjectRevision(6, isDirty: false)
        #expect(stale.project?.revision == 8)
        #expect(stale.project?.isDirty == true)
    }
}
