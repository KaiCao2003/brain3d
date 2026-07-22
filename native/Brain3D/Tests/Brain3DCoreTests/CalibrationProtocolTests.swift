import Brain3DCore
import Foundation
import Testing

@Suite("Subject calibration bridge")
struct CalibrationProtocolTests {
    private let projectId = "00000000-0000-0000-0000-000000000001"
    private let calibrationId = "00000000-0000-0000-0000-000000000002"
    private let targetId = "00000000-0000-0000-0000-000000000003"
    private let transformId = "00000000-0000-0000-0000-000000000004"
    private let digest = String(repeating: "a", count: 64)

    @Test("Calibration decimal input rejects ambiguous notation")
    func decimalInput() throws {
        #expect(try CalibrationNumberInput.parse(" -12.50 ", field: "AP") == -12.5)
        #expect(throws: CalibrationNumberInputError.invalidDecimal(field: "AP")) {
            try CalibrationNumberInput.parse("1e3", field: "AP")
        }
        #expect(throws: CalibrationNumberInputError.invalidDecimal(field: "AP")) {
            try CalibrationNumberInput.parse("nan", field: "AP")
        }
    }

    @Test("Create request carries exact skull and BrainGlobe coordinate contracts")
    func createRequestShape() throws {
        let request = validCreateRequest()
        try CalibrationValidator.validateCreate(request)

        let data = try JSONEncoder().encode(request)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(Set(object.keys) == Set([
            "protocolVersion", "projectId", "expectedProjectRevision", "profileId",
            "sourceFrame", "skullLandmarks", "atlasLandmarks", "qualityLimits",
            "dvReference", "dvReferenceDescription", "limitsSource",
            "atlasTransformMethod", "affineDistortionAcknowledged",
        ]))
        let source = try #require(object["sourceFrame"] as? [String: Any])
        #expect(source["componentOrder"] as? [String] == ["AP", "ML", "DV"])
        #expect(source["units"] as? String == "micrometre")
        #expect(source["kind"] as? String == "skull")
        let atlasLandmarks = try #require(object["atlasLandmarks"] as? [String: Any])
        let bregma = try #require(atlasLandmarks["bregma"] as? [String: Any])
        #expect(bregma["frameId"] as? String == "BRAINGLOBE_PHYSICAL_ASR_UM")
        #expect(bregma["componentOrder"] as? [String] == ["AP", "DV", "ML"])
        #expect(bregma["atlasIdentifier"] as? String == SafetyPolicy.supportedAtlasIdentifier)
        #expect(bregma["atlasVersion"] as? String == SafetyPolicy.supportedAtlasVersion)
        #expect(object["atlasTransformMethod"] as? String == "rigid")
        #expect(object["affineDistortionAcknowledged"] as? Bool == false)
    }

    @Test("Create validation fails closed on animal laterality and atlas ordering")
    func invalidCreateInput() {
        let base = validCreateRequest()
        let notConfirmed = CalibrationCreateParameters(
            projectId: base.projectId,
            expectedProjectRevision: base.expectedProjectRevision,
            profileId: base.profileId,
            sourceFrame: base.sourceFrame,
            skullLandmarks: CalibrationSkullLandmarks(
                bregma: base.skullLandmarks.bregma,
                lambdaPoint: base.skullLandmarks.lambdaPoint,
                leftSkull: base.skullLandmarks.leftSkull,
                rightSkull: base.skullLandmarks.rightSkull,
                reportedBregmaLambdaDistanceMicrometres: 4_000,
                lateralityConfirmedFromAnimal: false
            ),
            atlasLandmarks: base.atlasLandmarks,
            qualityLimits: base.qualityLimits,
            dvReferenceDescription: base.dvReferenceDescription,
            limitsSource: base.limitsSource
        )
        #expect(throws: CalibrationValidationError.self) {
            try CalibrationValidator.validateCreate(notConfirmed)
        }

        let wrongAtlasOrder = CalibrationCreateParameters(
            projectId: base.projectId,
            expectedProjectRevision: base.expectedProjectRevision,
            profileId: base.profileId,
            sourceFrame: base.sourceFrame,
            skullLandmarks: base.skullLandmarks,
            atlasLandmarks: CalibrationAtlasLandmarks(
                bregma: CalibrationAtlasPoint(ap: 7_000, dv: 1_000, ml: 2_800),
                lambdaPoint: CalibrationAtlasPoint(ap: 5_000, dv: 1_000, ml: 2_800),
                leftSkull: base.atlasLandmarks.leftSkull,
                rightSkull: base.atlasLandmarks.rightSkull
            ),
            qualityLimits: base.qualityLimits,
            dvReferenceDescription: base.dvReferenceDescription,
            limitsSource: base.limitsSource
        )
        #expect(throws: CalibrationValidationError.self) {
            try CalibrationValidator.validateCreate(wrongAtlasOrder)
        }
    }

    @Test("List requires one coherent active calibration")
    func listContract() throws {
        let result = try decode(CalibrationListResult.self, payload: [
            "protocolVersion": 1,
            "status": "listed",
            "projectId": projectId,
            "projectRevision": 7,
            "activeCalibrationId": calibrationId,
            "calibrationCount": 1,
            "calibrations": [summary(active: true)],
        ])
        try CalibrationValidator.validateList(result, projectId: projectId)

        var badPayload: [String: Any] = [
            "protocolVersion": 1,
            "status": "listed",
            "projectId": projectId,
            "projectRevision": 7,
            "activeCalibrationId": calibrationId,
            "calibrationCount": 1,
            "calibrations": [summary(active: false)],
        ]
        let inconsistent = try decode(CalibrationListResult.self, payload: badPayload)
        #expect(throws: CalibrationValidationError.inconsistentCalibrationList) {
            try CalibrationValidator.validateList(inconsistent, projectId: projectId)
        }
        badPayload["calibrationCount"] = 2
        let wrongCount = try decode(CalibrationListResult.self, payload: badPayload)
        #expect(throws: CalibrationValidationError.inconsistentCalibrationList) {
            try CalibrationValidator.validateList(wrongCount, projectId: projectId)
        }
    }

    @Test("Projection validates atlas voxel and planning-only provenance")
    func projectionContract() throws {
        let result = try decode(
            CalibratedTargetProjectionResult.self,
            payload: projectionPayload()
        )
        try CalibrationValidator.validateProjection(
            result,
            projectId: projectId,
            targetId: targetId,
            activeCalibrationId: calibrationId
        )

        var unsafe = projectionPayload()
        unsafe["usableForNavigation"] = true
        let unsafeResult = try decode(CalibratedTargetProjectionResult.self, payload: unsafe)
        #expect(throws: CalibrationValidationError.unsafeProjection) {
            try CalibrationValidator.validateProjection(
                unsafeResult,
                projectId: projectId,
                targetId: targetId,
                activeCalibrationId: calibrationId
            )
        }
    }

    private func validCreateRequest() -> CalibrationCreateParameters {
        let frame = CalibrationSourceFrame(
            frameId: "rig-2026-07-22",
            originDescription: "animal bregma measured on the rig",
            apPositiveDirection: "toward the animal nose",
            mlPositiveDirection: "animal right",
            dvPositiveDirection: "up from skull"
        )
        return CalibrationCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 6,
            profileId: "subject-01-run-01",
            sourceFrame: frame,
            skullLandmarks: CalibrationSkullLandmarks(
                bregma: CalibrationSkullPoint(frameId: frame.frameId, ap: 0, ml: 0, dv: 0),
                lambdaPoint: CalibrationSkullPoint(frameId: frame.frameId, ap: -4_000, ml: 0, dv: -40),
                leftSkull: CalibrationSkullPoint(frameId: frame.frameId, ap: -2_000, ml: -2_000, dv: -25),
                rightSkull: CalibrationSkullPoint(frameId: frame.frameId, ap: -2_000, ml: 2_000, dv: -20),
                reportedBregmaLambdaDistanceMicrometres: 4_000,
                lateralityConfirmedFromAnimal: true
            ),
            atlasLandmarks: CalibrationAtlasLandmarks(
                bregma: CalibrationAtlasPoint(ap: 5_000, dv: 1_000, ml: 2_800),
                lambdaPoint: CalibrationAtlasPoint(ap: 9_000, dv: 1_040, ml: 2_800),
                leftSkull: CalibrationAtlasPoint(ap: 7_000, dv: 1_020, ml: 4_800),
                rightSkull: CalibrationAtlasPoint(ap: 7_000, dv: 1_020, ml: 800)
            ),
            qualityLimits: CalibrationQualityLimits(
                minimumAxisBaselineMicrometres: 500,
                distanceWarningMicrometres: 100,
                distanceFailureMicrometres: 200,
                lateralApWarningMicrometres: 100,
                lateralApFailureMicrometres: 200,
                transformRmsWarningMicrometres: 100,
                transformRmsFailureMicrometres: 200
            ),
            dvReferenceDescription: "DV zero measured at bregma on this animal",
            limitsSource: "lab protocol revision 3"
        )
    }

    private func summary(active: Bool) -> [String: Any] {
        [
            "calibrationId": calibrationId,
            "schemaVersion": 1,
            "calibrationVersion": 1,
            "profileId": "subject-01-run-01",
            "mode": "subject-calibrated",
            "quality": "pass",
            "permitsPlanning": true,
            "permitsFinalExport": true,
            "active": active,
            "skullQuality": "pass",
            "skullRmsResidualMicrometres": 12.0,
            "atlasRmsResidualMicrometres": 15.0,
            "atlasMaximumResidualMicrometres": 21.0,
            "atlasTransformMethod": "rigid",
            "atlasMetadataSha256": digest,
            "calibrationSha256": digest,
            "qcMessages": ["PASS: stored fit is below user limits"],
        ]
    }

    private func projectionPayload() -> [String: Any] {
        [
            "protocolVersion": 1,
            "status": "projectedReadOnly",
            "projectId": projectId,
            "projectRevision": 7,
            "targetId": targetId,
            "sourceTargetPreserved": true,
            "projectionPersisted": false,
            "usableForPlanning": true,
            "usableForNavigation": false,
            "stereotaxicPoint": [
                "frameId": "STEREOTAXIC_BREGMA_AP_ML_DV_UM:subject-01-run-01",
                "componentOrder": ["AP", "ML", "DV"],
                "units": "micrometre",
                "apMicrometres": -1_000.0,
                "mlMicrometres": -800.0,
                "dvMicrometres": -2_000.0,
            ],
            "atlasPoint": [
                "frameId": "BRAINGLOBE_PHYSICAL_ASR_UM",
                "atlasIdentifier": SafetyPolicy.supportedAtlasIdentifier,
                "atlasVersion": SafetyPolicy.supportedAtlasVersion,
                "componentOrder": ["AP", "DV", "ML"],
                "units": "micrometre",
                "apMicrometres": 6_000.0,
                "dvMicrometres": 2_000.0,
                "mlMicrometres": 2_000.0,
            ],
            "containingVoxelIndex": [
                "frameId": "BRAINGLOBE_VOXEL_INDEX_ASR",
                "componentOrder": ["AP", "DV", "ML"],
                "ap": 240,
                "dv": 80,
                "ml": 80,
            ],
            "provenance": [
                "calibrationId": calibrationId,
                "calibrationSchemaVersion": 1,
                "calibrationVersion": 1,
                "calibrationSha256": digest,
                "atlasTransformId": transformId,
                "atlasTransformVersion": 1,
                "atlasTransformMethod": "rigid",
                "atlasMetadataSha256": digest,
                "projectionAlgorithm": "bregma-target-through-subject-atlas-calibration-v1",
                "projectionSha256": digest,
            ],
            "coordinateSemantics": [
                "frameId": "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED",
                "origin": "bregma",
                "componentOrder": ["AP", "ML", "DV"],
                "units": "millimetre",
                "apPositiveDirection": "anterior",
                "apNegativeDirection": "posterior/back",
                "mlPositiveDirection": "right",
                "mlNegativeDirection": "left",
                "dvPositiveDirection": "dorsal/up",
                "dvNegativeDirection": "deep/ventral",
            ],
            "warning": "Animal research planning only — not certified navigation output",
        ]
    }

    private func decode<T: Decodable>(_ type: T.Type, payload: [String: Any]) throws -> T {
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        return try JSONDecoder().decode(type, from: data)
    }
}
