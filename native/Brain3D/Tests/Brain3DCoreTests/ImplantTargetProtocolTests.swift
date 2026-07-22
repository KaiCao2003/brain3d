import Brain3DCore
import Foundation
import Testing

@Suite("Unprojected bregma implant bridge")
struct ImplantTargetProtocolTests {
    @Test("Plain decimal input preserves the named AP ML DV values")
    func decimalInput() throws {
        let parsed = try BregmaCoordinateInput.parse(
            ap: " -1.250 ",
            ml: "+.70",
            dv: "-0"
        )

        #expect(parsed.apMillimetres == -1.25)
        #expect(parsed.mlMillimetres == 0.7)
        #expect(parsed.dvMillimetres == 0)
        #expect(parsed.dvMillimetres.sign == .plus)
    }

    @Test(
        "Ambiguous coordinate spelling is rejected",
        arguments: ["", "nan", "inf", "1e3", "1,25", "1 000", "+.", "--1", "１２.３"]
    )
    func decimalInputRejectsAmbiguity(_ value: String) {
        #expect(throws: BregmaCoordinateInputError.invalidDecimal(axis: "AP")) {
            try BregmaCoordinateInput.parse(value, axis: "AP")
        }
    }

    @Test("Add and remove requests use only the strict protocol fields")
    func requestShapes() throws {
        let addData = try JSONEncoder().encode(
            ImplantAddParameters(
                projectId: "10000000-0000-0000-0000-000000000001",
                expectedProjectRevision: 9,
                label: "left visual implant",
                apMillimetres: -1.25,
                mlMillimetres: -0.7,
                dvMillimetres: -2.4
            )
        )
        let add = try #require(JSONSerialization.jsonObject(with: addData) as? [String: Any])
        #expect(
            Set(add.keys) == Set([
                "protocolVersion", "projectId", "expectedProjectRevision", "label",
                "apMillimetres", "mlMillimetres", "dvMillimetres",
            ])
        )

        let removeData = try JSONEncoder().encode(
            ImplantRemoveParameters(
                projectId: "10000000-0000-0000-0000-000000000001",
                expectedProjectRevision: 9,
                targetId: "00000000-0000-0000-0000-000000000001"
            )
        )
        let remove = try #require(
            JSONSerialization.jsonObject(with: removeData) as? [String: Any]
        )
        #expect(Set(remove.keys) == Set([
            "protocolVersion", "projectId", "expectedProjectRevision", "targetId",
        ]))
    }

    @Test("Mutation response must belong to the next revision of the same project")
    func mutationIdentityAndRevision() throws {
        let projectId = "10000000-0000-0000-0000-000000000001"
        var payload = listPayload()
        payload["status"] = "added"
        payload["projectId"] = projectId
        payload["projectRevision"] = 10
        payload["target"] = targetPayload()
        payload.removeValue(forKey: "targets")
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        let result = try JSONDecoder().decode(ImplantMutationResult.self, from: data)
        try ImplantTargetValidator.validateMutation(
            result,
            expectedStatus: "added",
            projectId: projectId,
            projectRevision: 10
        )
        #expect(throws: ImplantTargetValidationError.projectRevisionMismatch) {
            try ImplantTargetValidator.validateMutation(
                result,
                expectedStatus: "added",
                projectId: projectId,
                projectRevision: 11
            )
        }
    }

    @Test("Mutation acknowledgements must echo the submitted target")
    func mutationBindsSubmittedTarget() throws {
        let projectId = "10000000-0000-0000-0000-000000000001"
        let addRequest = ImplantAddParameters(
            projectId: projectId,
            expectedProjectRevision: 9,
            label: "left visual implant",
            apMillimetres: -1.25,
            mlMillimetres: -0.7,
            dvMillimetres: -2.4,
            notes: "Animal protocol target; not calibrated."
        )
        let added = try decodeMutation(
            status: "added",
            projectId: projectId,
            projectRevision: 10,
            target: targetPayload()
        )
        try ImplantTargetValidator.validateAddedMutation(added, request: addRequest)

        var wrongCoordinates = targetPayload()
        wrongCoordinates["mlMillimetres"] = 0.7
        let mismatchedAdd = try decodeMutation(
            status: "added",
            projectId: projectId,
            projectRevision: 10,
            target: wrongCoordinates
        )
        #expect(throws: ImplantTargetValidationError.mutationTargetMismatch) {
            try ImplantTargetValidator.validateAddedMutation(
                mismatchedAdd,
                request: addRequest
            )
        }

        let removeRequest = ImplantRemoveParameters(
            projectId: projectId,
            expectedProjectRevision: 10,
            targetId: "00000000-0000-0000-0000-000000000002"
        )
        let wrongRemoval = try decodeMutation(
            status: "removed",
            projectId: projectId,
            projectRevision: 11,
            target: targetPayload()
        )
        #expect(throws: ImplantTargetValidationError.mutationTargetMismatch) {
            try ImplantTargetValidator.validateRemovedMutation(
                wrongRemoval,
                request: removeRequest
            )
        }
    }

    @Test("Exact unprojected frame and projection lock validate")
    func exactContract() throws {
        let result = try decodeList(from: listPayload())

        try ImplantTargetValidator.validateList(result)

        #expect(result.targetCount == 1)
        #expect(result.targets[0].apMillimetres == -1.25)
        #expect(result.targets[0].mlMillimetres == -0.7)
        #expect(result.targets[0].dvMillimetres == -2.4)
        #expect(!result.targets[0].projected)
        #expect(!result.targets[0].usableForNavigation)
    }

    @Test("Changed sign convention or navigation claim fails closed")
    func unsafeContractRejected() throws {
        var changedSign = listPayload()
        var frame = try #require(changedSign["coordinateFrame"] as? [String: Any])
        var signs = try #require(frame["signConvention"] as? [String: Any])
        signs["mlNegative"] = "right"
        frame["signConvention"] = signs
        changedSign["coordinateFrame"] = frame
        let signResult = try decodeList(from: changedSign)
        #expect(throws: ImplantTargetValidationError.coordinateFrameMismatch) {
            try ImplantTargetValidator.validateList(signResult)
        }

        var navigable = listPayload()
        var targets = try #require(navigable["targets"] as? [[String: Any]])
        targets[0]["usableForNavigation"] = true
        navigable["targets"] = targets
        let navigationResult = try decodeList(from: navigable)
        #expect(throws: ImplantTargetValidationError.projectionWasNotLocked) {
            try ImplantTargetValidator.validateList(navigationResult)
        }
    }

    private func listPayload() -> [String: Any] {
        [
            "protocolVersion": 1,
            "status": "listed",
            "targetCount": 1,
            "coordinateFrame": coordinateFrame(),
            "projected": false,
            "usableForNavigation": false,
            "projectionStatus": "lockedUntilExplicitBregmaSkullCalibration",
            "targets": [targetPayload()],
        ]
    }

    private func coordinateFrame() -> [String: Any] {
        [
            "frameId": "BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED",
            "origin": "bregma",
            "componentOrder": ["AP", "ML", "DV"],
            "units": "millimetre",
            "signConvention": [
                "apPositive": "anterior",
                "apNegative": "posterior/back",
                "mlPositive": "right",
                "mlNegative": "left",
                "dvPositive": "dorsal/up",
                "dvNegative": "deep/ventral",
            ],
        ]
    }

    private func targetPayload() -> [String: Any] {
        [
            "targetId": "00000000-0000-0000-0000-000000000001",
            "schemaVersion": 1,
            "label": "left visual implant",
            "apMillimetres": -1.25,
            "mlMillimetres": -0.7,
            "dvMillimetres": -2.4,
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
            "createdAt": "2026-07-21T12:30:00Z",
            "notes": "Animal protocol target; not calibrated.",
            "projected": false,
            "usableForNavigation": false,
            "projectionStatus": "lockedUntilExplicitBregmaSkullCalibration",
        ]
    }

    private func decodeList(from payload: [String: Any]) throws -> ImplantListResult {
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        return try JSONDecoder().decode(ImplantListResult.self, from: data)
    }

    private func decodeMutation(
        status: String,
        projectId: String,
        projectRevision: Int,
        target: [String: Any]
    ) throws -> ImplantMutationResult {
        try JSONDecoder().decode(
            ImplantMutationResult.self,
            from: JSONSerialization.data(withJSONObject: [
                "protocolVersion": 1,
                "status": status,
                "projectId": projectId,
                "projectRevision": projectRevision,
                "targetCount": 1,
                "coordinateFrame": coordinateFrame(),
                "projected": false,
                "usableForNavigation": false,
                "projectionStatus": "lockedUntilExplicitBregmaSkullCalibration",
                "target": target,
            ], options: [.sortedKeys])
        )
    }
}
