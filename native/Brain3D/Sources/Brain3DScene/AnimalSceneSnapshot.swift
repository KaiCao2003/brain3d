import Brain3DCore
import Foundation

public struct AnimalSceneSnapshot: Equatable, Sendable {
    public let projectId: String
    public let projectRevision: Int
    public let meshResult: AtlasMeshResult
    public let transform: AtlasSceneTransform
    public let selectedProbePlan: ProbePlanDetail?
    public let majorVessels: MajorVesselGeometryResult?

    public init(
        projectId: String,
        projectRevision: Int,
        rendererAnchor: AtlasPhysicalPoint,
        meshResult: AtlasMeshResult,
        selectedProbePlan: ProbePlanDetail?,
        majorVessels: MajorVesselGeometryResult? = nil
    ) throws {
        guard !projectId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              projectRevision >= 0,
              meshResult.target == .root
        else {
            throw AtlasSceneContractError.invalid(
                "3D scene requires a current project revision and the root atlas mesh."
            )
        }
        let bounds = meshResult.sourceCoordinateFrame.bounds
        let anchorValues = [
            rendererAnchor.apMicrometres,
            rendererAnchor.dvMicrometres,
            rendererAnchor.mlMicrometres,
        ]
        guard zip(anchorValues, bounds.minimumInclusiveMicrometres).allSatisfy({ pair in
            pair.0 >= pair.1
        }), zip(anchorValues, bounds.maximumExclusiveMicrometres).allSatisfy({ pair in
            pair.0 < pair.1
        }) else {
            throw AtlasSceneContractError.invalid(
                "Persisted renderer anchor lies outside the verified atlas bounds."
            )
        }
        if let selectedProbePlan {
            try ProbePlanningValidator.validatePlan(selectedProbePlan)
            guard selectedProbePlan.hasCurrentPlanningGeometry,
                  selectedProbePlan.provenance.atlasMetadataSha256
                    == meshResult.atlas.metadataSha256
            else {
                throw AtlasSceneContractError.invalid(
                    "The selected probe requires current geometry matching the 3D atlas."
                )
            }
        }
        if let majorVessels {
            guard majorVessels.atlas == meshResult.atlas,
                  majorVessels.provenance.atlasIdentifier == meshResult.atlas.identifier,
                  majorVessels.provenance.atlasVersion == meshResult.atlas.version,
                  majorVessels.graph.sourceEdgeIndices.count
                    == majorVessels.graph.runOffsets.count - 1
            else {
                throw AtlasSceneContractError.invalid(
                    "Reference major vessels and 3D atlas provenance do not match."
                )
            }
        }
        self.projectId = projectId
        self.projectRevision = projectRevision
        self.meshResult = meshResult
        transform = try AtlasSceneTransform(anchor: rendererAnchor)
        self.selectedProbePlan = selectedProbePlan
        self.majorVessels = majorVessels
    }

    public var identity: String {
        [
            projectId,
            String(projectRevision),
            meshResult.mesh.sha256,
            selectedProbePlan?.inputSha256 ?? "no-probe",
            majorVessels?.provenance.derivedAssetSha256 ?? "no-vessels",
        ].joined(separator: ":")
    }
}
