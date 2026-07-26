import Brain3DCore
import Foundation
import Testing
@testable import Brain3DApp

@Suite("Atlas region mesh failure presentation")
struct AtlasRegionMeshFailurePresentationTests {
    @Test("Ontology-only regions explain absent reviewed geometry without clearing selection")
    func ontologyOnlyMessage() throws {
        let region = try rspd4()
        let error = BridgeClientError.remote(BridgeRemoteError(
            code: AtlasRegionMeshFailurePresentation.noAnnotatedVoxelsCode,
            message: "No reviewed geometry",
            details: .object([
                "structureId": .number(545),
                "annotationVoxelCount": .number(0),
            ])
        ))

        let message = AtlasRegionMeshFailurePresentation.message(
            for: error,
            selectedRegion: region
        )

        #expect(message.contains("RSPd4"))
        #expect(message.contains("no voxels in the reviewed 25 µm annotation"))
        #expect(message.contains("no reviewed 3D geometry"))
        #expect(message.contains("selected region remains active"))
    }

    @Test("Unrelated mesh failures retain their diagnostic")
    func genericMessage() throws {
        let region = try rspd4()
        let error = BridgeClientError.remote(BridgeRemoteError(
            code: "ATLAS_MESH_UNAVAILABLE",
            message: "The mesh could not be read."
        ))

        #expect(
            AtlasRegionMeshFailurePresentation.message(
                for: error,
                selectedRegion: region
            ) == "ATLAS_MESH_UNAVAILABLE: The mesh could not be read."
        )
    }

    private func rspd4() throws -> AtlasRegionSummary {
        try JSONDecoder().decode(
            AtlasRegionSummary.self,
            from: JSONSerialization.data(withJSONObject: [
                "structureId": 545,
                "acronym": "RSPd4",
                "name": "Retrosplenial area, dorsal part, layer 4",
                "parentStructureId": 879,
                "structureIdPath": [997, 8, 567, 688, 695, 315, 254, 879, 545],
                "rgb": [26, 166, 152],
            ])
        )
    }
}
