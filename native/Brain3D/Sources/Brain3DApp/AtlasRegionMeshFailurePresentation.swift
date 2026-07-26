import Brain3DCore
import Foundation

enum AtlasRegionMeshFailurePresentation {
    static let noAnnotatedVoxelsCode = "ATLAS_REGION_HAS_NO_ANNOTATED_VOXELS"

    static func message(
        for error: any Error,
        selectedRegion: AtlasRegionSummary
    ) -> String {
        if let bridgeError = error as? BridgeClientError,
           case let .remote(remote) = bridgeError,
           remote.code == noAnnotatedVoxelsCode
        {
            return "\(selectedRegion.acronym) is present in the Allen ontology, but its "
                + "branch has no voxels in the reviewed 25 µm annotation. There is no "
                + "reviewed 3D geometry to show; the selected region remains active."
        }
        return error.localizedDescription
    }
}
