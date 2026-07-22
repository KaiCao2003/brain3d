import Brain3DCore
import Foundation
import Testing

@Suite("Bounded major-vessel analysis protocol")
struct MajorVesselAnalysisProtocolTests {
    @Test("Reviewed no-conflict wording and acknowledged assumptions decode")
    func validNoConflict() throws {
        let result = try decode(payload())

        #expect(result.analysis.resultStatus == .noConflictDetected)
        #expect(result.analysis.statement == MajorVesselAnalysisContract.noConflictStatement)
        #expect(result.analysis.minimumAdjustedClearanceMicrometres == 125)
        #expect(result.analysis.conflicts.isEmpty)
        #expect(result.analysis.usableForNavigation == false)
        #expect(result.analysis.algorithmVersion == "major-vessel-aabb-tapered-surface-v3")
        #expect(result.analysis.provenance.registrationTransformId == nil)
        #expect(result.analysis.provenance.uncertaintyBoundsReviewed == false)
    }

    @Test("Current project and plan identity gates restored analysis")
    func restoredIdentityValidation() throws {
        let result = try decode(payload())
        try MajorVesselAnalysisValidator.validateCurrent(
            result,
            projectId: "00000000-0000-0000-0000-000000000001",
            projectRevision: 7,
            planId: "00000000-0000-0000-0000-000000000002",
            planVersion: 2,
            planInputSha256: String(repeating: "c", count: 64)
        )
        #expect(throws: MajorVesselContractError.self) {
            try MajorVesselAnalysisValidator.validateCurrent(
                result,
                projectId: result.projectId,
                projectRevision: 8,
                planId: result.planId,
                planVersion: result.planVersion,
                planInputSha256: result.planInputSha256
            )
        }
    }

    @Test("Reviewed inputs may still produce an unclassifiable result")
    func reviewedButUnclassifiable() throws {
        var object = payload()
        var analysis = try #require(object["analysis"] as? [String: Any])
        analysis["resultStatus"] = "insufficientGeometry"
        analysis["statement"] =
            "The source does not provide reviewed registration and tissue-distortion bounds."
        object["analysis"] = analysis

        let result = try decode(object)
        #expect(result.analysis.riskProfile.confirmedByUser)
        #expect(result.analysis.riskProfile.referenceOnlyCoverageAcknowledged)
        #expect(result.analysis.resultStatus == .insufficientGeometry)
    }

    @Test("Unbounded result wording is rejected")
    func rejectsUnboundedWording() throws {
        var object = payload()
        var analysis = try #require(object["analysis"] as? [String: Any])
        analysis["statement"] = "This path is safe."
        object["analysis"] = analysis

        #expect(throws: (any Error).self) {
            try decode(object)
        }
    }

    @Test("Analysis request validates finite lab inputs")
    func requestValidation() throws {
        let request = try MajorVesselAnalyzeParameters(
            projectId: "00000000-0000-0000-0000-000000000001",
            expectedProjectRevision: 7,
            planId: "00000000-0000-0000-0000-000000000002",
            expectedPlanInputSha256: String(repeating: "c", count: 64),
            requiredMarginMicrometres: 100,
            registrationUncertaintyMicrometres: 75,
            riskProfileConfirmed: true,
            referenceCoverageAcknowledged: true
        )
        #expect(request.maximumConflicts == 100)
        #expect(throws: (any Error).self) {
            try MajorVesselAnalyzeParameters(
                projectId: request.projectId,
                expectedProjectRevision: 7,
                planId: request.planId,
                expectedPlanInputSha256: request.expectedPlanInputSha256,
                requiredMarginMicrometres: -.infinity,
                registrationUncertaintyMicrometres: 75,
                riskProfileConfirmed: true,
                referenceCoverageAcknowledged: true
            )
        }
    }

    private func decode(_ object: [String: Any]) throws -> MajorVesselAnalysisResult {
        let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        return try JSONDecoder().decode(MajorVesselAnalysisResult.self, from: data)
    }

    private func payload() -> [String: Any] {
        [
            "protocolVersion": 1,
            "projectId": "00000000-0000-0000-0000-000000000001",
            "projectRevision": 7,
            "planId": "00000000-0000-0000-0000-000000000002",
            "planVersion": 2,
            "planInputSha256": String(repeating: "c", count: 64),
            "analysis": [
                "algorithmVersion": MajorVesselAnalysisContract.algorithmVersion,
                "inputSha256": String(repeating: "b", count: 64),
                "resultStatus": "noConflictDetected",
                "statement": MajorVesselAnalysisContract.noConflictStatement,
                "nearestCenterlineDistanceMicrometres": 300,
                "minimumGeometricClearanceMicrometres": 300,
                "minimumAdjustedClearanceMicrometres": 125,
                "candidateSegmentCount": 0,
                "measuredSegmentCount": MajorVesselContract.expectedSegmentCount,
                "conflicts": [],
                "conflictsTruncated": false,
                "riskProfile": [
                    "profileId": "lambada-p60-606-major-30um-v1",
                    "minimumVesselDiameterMicrometres": 30,
                    "requiredMarginMicrometres": 100,
                    "registrationUncertaintyMicrometres": 75,
                    "sourceOrLabPolicy": "Lab-reviewed inputs",
                    "confirmedByUser": true,
                    "referenceOnlyCoverageAcknowledged": true,
                ],
                "provenance": provenance,
                "warnings": ["Single-specimen reference only."],
                "usableForNavigation": false,
            ],
            "limitations": [
                "Single cleared reference; not subject-specific anatomy.",
                "Pial and choroidal vessels are excluded.",
            ],
        ]
    }

    private var provenance: [String: Any] {
        [
            "sourceId": MajorVesselContract.sourceId,
            "sourceKind": "reference-individual-vessel-graph",
            "datasetTitle": "Vascular graphs of the developing post-natal mouse brain",
            "authors": ["Nicolas Renier", "Elisa de Launoit", "Sophie Skriabine"],
            "specimenId": MajorVesselContract.specimenId,
            "sourceDoi": MajorVesselContract.sourceDoi,
            "sourceRecordUrl": MajorVesselContract.sourceRecordURL,
            "sourcePaperDoi": MajorVesselContract.sourcePaperDoi,
            "sourceVersion": "P60_606 / 606_graph_2024-12-03.gt",
            "sourceLicense": "CC BY 4.0",
            "sourceArchiveDigest": MajorVesselContract.sourceArchiveDigest,
            "derivedAssetSha256": MajorVesselContract.derivedAssetSHA256,
            "extractionAlgorithmVersion": MajorVesselContract.extractionAlgorithmVersion,
            "atlasIdentifier": "allen_mouse_25um",
            "atlasVersion": "1.2",
            "coordinateFrameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
            "minimumIncludedDiameterMicrometres": 30,
            "physicalUnitsDeclared": true,
            "atlasScaleApplied": true,
            "geometrySourceAudited": true,
            "subjectSpecific": false,
            "pialVesselsExcluded": true,
            "choroidalVesselsExcluded": true,
            "arteryVeinClassificationAvailable": false,
            "registrationTransformId": NSNull(),
            "registrationUncertaintyBoundMicrometres": NSNull(),
            "tissueDistortionUncertaintyBoundMicrometres": NSNull(),
            "uncertaintyBoundsReviewed": false,
        ]
    }
}
