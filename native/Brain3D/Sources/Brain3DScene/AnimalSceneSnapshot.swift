import Brain3DCore
import Foundation

public struct AnimalSceneSnapshot: Equatable, Sendable {
    public let projectId: String
    public let projectRevision: Int
    public let meshResult: AtlasMeshResult
    public let highlightedRegionMesh: AtlasMeshResult?
    public let transform: AtlasSceneTransform
    public let selectedProbePlan: ProbePlanDetail?
    public let majorVessels: MajorVesselGeometryResult?
    public let minimumVisibleVesselDiameterMicrometres: Double
    public let selectedVesselConflict: MajorVesselConflict?

    public init(
        projectId: String,
        projectRevision: Int,
        rendererAnchor: AtlasPhysicalPoint,
        meshResult: AtlasMeshResult,
        highlightedRegionMesh: AtlasMeshResult? = nil,
        selectedProbePlan: ProbePlanDetail?,
        majorVessels: MajorVesselGeometryResult? = nil,
        minimumVisibleVesselDiameterMicrometres: Double =
            MajorVesselContract.minimumIncludedDiameterMicrometres,
        selectedVesselConflict: MajorVesselConflict? = nil
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
        if let highlightedRegionMesh {
            guard highlightedRegionMesh.target == .region,
                  highlightedRegionMesh.region != nil,
                  highlightedRegionMesh.atlas == meshResult.atlas,
                  highlightedRegionMesh.sourceCoordinateFrame
                    == meshResult.sourceCoordinateFrame
            else {
                throw AtlasSceneContractError.invalid(
                    "A highlighted region mesh must belong to the current 3D atlas."
                )
            }
        }
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
                    == majorVessels.graph.runOffsets.count - 1,
                  MajorVesselDisplayFilter.clampedMinimumDiameterMicrometres(
                      minimumVisibleVesselDiameterMicrometres
                  ) == minimumVisibleVesselDiameterMicrometres
            else {
                throw AtlasSceneContractError.invalid(
                    "Reference major vessels and 3D atlas provenance do not match."
                )
            }
        }
        if let selectedVesselConflict {
            guard let majorVessels else {
                throw AtlasSceneContractError.invalid(
                    "A selected vessel conflict requires its current reviewed vessel graph."
                )
            }
            try Self.validateSelectedVesselConflict(
                selectedVesselConflict,
                bounds: bounds,
                selectedProbeShankIds: selectedProbePlan.map {
                    Set($0.shanks.map(\.shankId))
                }
            )
            guard MajorVesselConflictNodeFactory.selectedSegment(
                for: selectedVesselConflict,
                in: majorVessels.graph
            ) != nil else {
                throw AtlasSceneContractError.invalid(
                    "The selected vessel conflict does not resolve to its reviewed source segment."
                )
            }
        }
        self.projectId = projectId
        self.projectRevision = projectRevision
        self.meshResult = meshResult
        self.highlightedRegionMesh = highlightedRegionMesh
        transform = try AtlasSceneTransform(anchor: rendererAnchor)
        self.selectedProbePlan = selectedProbePlan
        self.majorVessels = majorVessels
        self.minimumVisibleVesselDiameterMicrometres =
            minimumVisibleVesselDiameterMicrometres
        self.selectedVesselConflict = selectedVesselConflict
    }

    public var identity: String {
        [
            projectId,
            String(projectRevision),
            meshResult.mesh.sha256,
            highlightedRegionMesh?.mesh.sha256 ?? "no-highlighted-region",
            selectedProbePlan?.inputSha256 ?? "no-probe",
            majorVessels?.provenance.derivedAssetSha256 ?? "no-vessels",
            String(minimumVisibleVesselDiameterMicrometres.bitPattern, radix: 16),
            selectedVesselConflict.map(Self.conflictIdentity) ?? "no-vessel-conflict",
        ].joined(separator: ":")
    }

    static func validateSelectedVesselConflict(
        _ conflict: MajorVesselConflict,
        bounds: AtlasCoordinateBounds,
        selectedProbeShankIds: Set<String>?
    ) throws {
        if let selectedProbeShankIds,
           !selectedProbeShankIds.contains(conflict.shankId)
        {
            throw AtlasSceneContractError.invalid(
                "The selected vessel conflict does not belong to a displayed probe shank."
            )
        }
        for point in [conflict.probePoint, conflict.vesselPoint] {
            let values = [
                point.apMicrometres,
                point.dvMicrometres,
                point.mlMicrometres,
            ]
            guard point.frameId == AtlasPhysicalCoordinateFrame.expectedFrameId,
                  values.allSatisfy(\.isFinite),
                  zip(values, bounds.minimumInclusiveMicrometres).allSatisfy({ pair in
                      pair.0 >= pair.1
                  }),
                  zip(values, bounds.maximumExclusiveMicrometres).allSatisfy({ pair in
                      pair.0 < pair.1
                  })
            else {
                throw AtlasSceneContractError.invalid(
                    "Selected vessel-conflict points must be in-bounds physical ASR geometry."
                )
            }
        }
    }

    private static func conflictIdentity(_ conflict: MajorVesselConflict) -> String {
        let pointBits = [conflict.probePoint, conflict.vesselPoint].flatMap { point in
            [
                String(point.apMicrometres.bitPattern, radix: 16),
                String(point.dvMicrometres.bitPattern, radix: 16),
                String(point.mlMicrometres.bitPattern, radix: 16),
            ]
        }
        return ([
            conflict.conflictId,
            conflict.shankId,
            String(conflict.vesselSourceEdgeIndex),
            String(conflict.vesselRunIndex),
            String(conflict.vesselSegmentIndexInRun),
            conflict.classification.rawValue,
        ] + pointBits).joined(separator: "@")
    }
}
