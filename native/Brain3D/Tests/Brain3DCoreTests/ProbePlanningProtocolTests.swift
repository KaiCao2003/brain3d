import Brain3DCore
import CryptoKit
import Foundation
import Testing

@Suite("Probe catalog, plan, and exact region bridge")
struct ProbePlanningProtocolTests {
    private struct TestVector3 {
        let ap: Double
        let ml: Double
        let dv: Double

        var magnitude: Double {
            sqrt(ap * ap + ml * ml + dv * dv)
        }

        func adding(_ other: TestVector3) -> TestVector3 {
            TestVector3(ap: ap + other.ap, ml: ml + other.ml, dv: dv + other.dv)
        }

        func subtracting(_ other: TestVector3) -> TestVector3 {
            TestVector3(ap: ap - other.ap, ml: ml - other.ml, dv: dv - other.dv)
        }

        func scaled(by factor: Double) -> TestVector3 {
            TestVector3(ap: ap * factor, ml: ml * factor, dv: dv * factor)
        }

        func dot(_ other: TestVector3) -> Double {
            ap * other.ap + ml * other.ml + dv * other.dv
        }

        func cross(_ other: TestVector3) -> TestVector3 {
            TestVector3(
                ap: ml * other.dv - dv * other.ml,
                ml: dv * other.ap - ap * other.dv,
                dv: ap * other.ml - ml * other.ap
            )
        }

        func normalized() -> TestVector3 {
            scaled(by: 1 / magnitude)
        }

        func rotated(around axis: TestVector3, degrees: Double) -> TestVector3 {
            let radians = degrees * .pi / 180
            return scaled(by: cos(radians))
                .adding(axis.cross(self).scaled(by: sin(radians)))
                .adding(
                    axis.scaled(
                        by: axis.dot(self) * (1 - cos(radians))
                    )
                )
        }
    }

    private let projectId = "11111111-1111-4111-8111-111111111111"
    private let targetId = "22222222-2222-4222-8222-222222222222"
    private let calibrationId = "33333333-3333-4333-8333-333333333333"
    private let planId = "44444444-4444-4444-8444-444444444444"

    @Test("Mutation and export requests use only exact protocol fields")
    func exactRequestKeys() throws {
        let create = ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Left VISp",
            azimuthDegrees: -12.5,
            elevationDegrees: -80,
            insertionDepthMicrometres: 3_200,
            axialRotationDegrees: 5,
            customGeometryAcknowledged: true
        )
        #expect(try keys(create) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "targetId",
            "modelId", "modelVersion", "name", "placementMode", "azimuthDegrees",
            "elevationDegrees", "insertionDepthMicrometres", "axialRotationDegrees",
            "customGeometryAcknowledged",
        ])

        let update = ProbePlanUpdateParameters(
            projectId: projectId,
            expectedProjectRevision: 8,
            planId: planId,
            expectedPlanInputSha256: hex("a"),
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Left VISp v2",
            azimuthDegrees: 2,
            elevationDegrees: -82,
            insertionDepthMicrometres: 3_300,
            axialRotationDegrees: -4,
            customGeometryAcknowledged: true
        )
        #expect(try keys(update) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "planId",
            "expectedPlanInputSha256", "targetId", "modelId", "modelVersion", "name",
            "placementMode", "azimuthDegrees", "elevationDegrees",
            "insertionDepthMicrometres", "axialRotationDegrees",
            "customGeometryAcknowledged",
        ])
        #expect(try keys(ProbePlanRemoveParameters(
            projectId: projectId,
            expectedProjectRevision: 9,
            planId: planId,
            expectedPlanInputSha256: hex("b")
        )) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "planId",
            "expectedPlanInputSha256",
        ])
        #expect(try keys(ProbeRegionAnalyzeParameters(
            projectId: projectId,
            expectedProjectRevision: 9,
            planId: planId,
            expectedPlanInputSha256: hex("b")
        )) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "planId",
            "expectedPlanInputSha256",
        ])
        #expect(try keys(ProbeRegionExportParameters(
            projectId: projectId,
            expectedProjectRevision: 9,
            planId: planId,
            expectedPlanInputSha256: hex("b"),
            format: .csv
        )) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "planId",
            "expectedPlanInputSha256", "format",
        ])
        #expect(try keys(ProbeRegionExportConfirmParameters(
            projectId: projectId,
            expectedProjectRevision: 9,
            planId: planId,
            expectedPlanInputSha256: hex("b"),
            analysisSha256: hex("e"),
            format: .csv,
            contentSha256: hex("c")
        )) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "planId",
            "expectedPlanInputSha256", "analysisSha256", "format", "contentSha256",
        ])
    }

    @Test("Atlas-surface requests expose only the simplified NP2 controls")
    func atlasSurfaceRequestKeys() throws {
        let create = AtlasSurfaceProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId,
            modelVersion: ProbePlanningContract.neuropixels2ModelVersion,
            insertionAPMillimetres: -1.5,
            insertionMLMillimetres: -0.8,
            surfaceDepthMillimetres: 2.3,
            sagittalAngleDegrees: 12,
            probeLayoutRotationDegrees: 0
        )
        #expect(try keys(create) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "placementMode",
            "modelId", "modelVersion", "insertionAPMillimetres",
            "insertionMLMillimetres", "surfaceDepthMillimetres",
            "sagittalAngleDegrees", "probeLayoutRotationDegrees",
        ])
        try ProbePlanningValidator.validateCreate(create)

        let update = AtlasSurfaceProbePlanUpdateParameters(
            projectId: projectId,
            expectedProjectRevision: 8,
            planId: planId,
            expectedPlanInputSha256: hex("a"),
            modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId,
            modelVersion: ProbePlanningContract.neuropixels2ModelVersion,
            insertionAPMillimetres: -1.4,
            insertionMLMillimetres: 0.9,
            surfaceDepthMillimetres: 3.1,
            sagittalAngleDegrees: -8,
            probeLayoutRotationDegrees: 90
        )
        #expect(try keys(update) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "planId",
            "expectedPlanInputSha256", "placementMode", "modelId", "modelVersion",
            "insertionAPMillimetres", "insertionMLMillimetres",
            "surfaceDepthMillimetres", "sagittalAngleDegrees",
            "probeLayoutRotationDegrees",
        ])
        try ProbePlanningValidator.validateUpdate(update)

        let tooDeep = AtlasSurfaceProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId,
            modelVersion: ProbePlanningContract.neuropixels2ModelVersion,
            insertionAPMillimetres: 0,
            insertionMLMillimetres: 0,
            surfaceDepthMillimetres: 10.1,
            sagittalAngleDegrees: 0,
            probeLayoutRotationDegrees: 0
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreate(tooDeep)
        }
    }

    @Test("Atlas-surface responses retain trustworthy sign, surface, and layout evidence")
    func atlasSurfacePlanValidation() throws {
        let result = try decode(
            ProbePlanGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "projectId": projectId,
                "projectRevision": 7,
                "plan": surfacePlanDetail(),
                "regionAnalysis": NSNull(),
                "majorVesselAnalysis": NSNull(),
            ]
        )
        try ProbePlanningValidator.validatePlanGet(
            result,
            projectId: projectId,
            projectRevision: 7,
            planId: planId
        )
        let input = try #require(result.plan.surfaceRelativeInput)
        #expect(result.plan.targetId == nil)
        #expect(result.plan.calibrationId == nil)
        #expect(input.insertionAPMillimetres == 4.2)
        #expect(input.insertionMLMillimetres == -3.7)
        #expect(input.surfaceDepthMillimetres == 3.2)
        #expect(input.sagittalAngleDegrees == 0)
        #expect(input.probeLayoutRotationDegrees == 0)
        #expect(input.surfaceEntry.mlMicrometres == 9_400)
        #expect(
            result.plan.placement.atlasFrame.entry.mlMicrometres
                == input.surfaceEntry.mlMicrometres
        )
        #expect(
            result.plan.shanks.first?.entry.mlMicrometres
                == input.surfaceEntry.mlMicrometres
        )
        #expect(result.plan.placement.axialRotationDegrees == -90)
        let primaryShank = try #require(result.plan.shanks.first)
        #expect(primaryShank.surfaceAnchor == primaryShank.entry)
        #expect(primaryShank.totalLengthMicrometres == 10_000)
        #expect(primaryShank.proximalEnd?.insideAtlas == false)
        let proximalDV = try #require(primaryShank.proximalEnd?.dvMicrometres)
        #expect(proximalDV < primaryShank.entry.dvMicrometres)
        #expect(result.plan.hasCurrentPlanningGeometry)
    }

    @Test("Atlas-surface validation rejects the former ML addition formula")
    func atlasSurfacePlanRejectsOldMLFormula() throws {
        var plan = surfacePlanDetail()
        var input = try #require(
            plan["surfaceRelativeInput"] as? [String: Any]
        )
        // The fixture entry is 9.4 mm in BrainGlobe physical ML. It is valid
        // for operator ML -3.7 mm because physical ML increases animal-left:
        // 5.7 - (-3.7) = 9.4. Reinterpreting the same entry as ML +3.7 is the
        // former, laterality-reversed addition formula and must fail closed.
        input["insertionMLMillimetres"] = 3.7
        plan["surfaceRelativeInput"] = input
        let result = try decode(
            ProbePlanGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "projectId": projectId,
                "projectRevision": 7,
                "plan": plan,
                "regionAnalysis": NSNull(),
                "majorVesselAnalysis": NSNull(),
            ]
        )

        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validatePlanGet(
                result,
                projectId: projectId,
                projectRevision: 7,
                planId: planId
            )
        }
    }

    @Test("Mutation responses must acknowledge the submitted plan and placement")
    func mutationResponseBindsRequest() throws {
        let catalogModel = try decodedCatalogModel(
            genericCatalogModel(detailed: true)
        )
        let create = ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Left VISp",
            azimuthDegrees: -12.5,
            elevationDegrees: -80,
            insertionDepthMicrometres: 3_200,
            axialRotationDegrees: 5,
            customGeometryAcknowledged: true
        )
        let created = try decode(
            ProbePlanMutationResult.self,
            mutationPayload(status: "created", revision: 8, plan: planDetail())
        )
        try ProbePlanningValidator.validateCreatedMutation(
            created,
            request: create,
            catalogModel: catalogModel
        )

        let differentPlacement = ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Left VISp",
            azimuthDegrees: -11,
            elevationDegrees: -80,
            insertionDepthMicrometres: 3_200,
            axialRotationDegrees: 5,
            customGeometryAcknowledged: true
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreatedMutation(
                created,
                request: differentPlacement,
                catalogModel: catalogModel
            )
        }

        let update = ProbePlanUpdateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            planId: planId,
            expectedPlanInputSha256: hex("f"),
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Left VISp",
            azimuthDegrees: -12.5,
            elevationDegrees: -80,
            insertionDepthMicrometres: 3_200,
            axialRotationDegrees: 5,
            customGeometryAcknowledged: true
        )
        var wrongPlan = planDetail()
        wrongPlan["planId"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        let wrongUpdate = try decode(
            ProbePlanMutationResult.self,
            mutationPayload(
                status: "updated",
                revision: 8,
                plan: wrongPlan,
                priorAnalysisCleared: true
            )
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateUpdatedMutation(
                wrongUpdate,
                request: update,
                catalogModel: catalogModel
            )
        }
    }

    @Test("Created plans contain the complete detailed geometry for every catalog model")
    func createdMutationBindsCompleteCatalogGeometry() throws {
        let catalogPayloads: [[String: Any]] = [
            neuropixels2CatalogModel(
                fourShank: false,
                detailed: true
            ),
            neuropixels2CatalogModel(
                fourShank: true,
                detailed: true
            ),
            neuropixels2CatalogModel(
                fourShank: true,
                quadBase: true,
                detailed: true
            ),
            neuropixelsCatalogModel(detailed: true),
            genericCatalogModel(detailed: true),
        ]

        for catalogPayload in catalogPayloads {
            let catalogModel = try decodedCatalogModel(catalogPayload)
            let request = matchingCreateRequest(for: catalogModel)
            let plan = try planDetail(matchingCatalog: catalogPayload)
            let created = try decode(
                ProbePlanMutationResult.self,
                mutationPayload(status: "created", revision: 8, plan: plan)
            )

            try ProbePlanningValidator.validateCreatedMutation(
                created,
                request: request,
                catalogModel: catalogModel
            )
            #expect(created.plan.shanks.count == catalogModel.shankCount)
            #expect(created.plan.recordingSites.count == catalogModel.siteCount)
        }
    }

    @Test("Mutation validation rejects incomplete or substituted catalog geometry")
    func mutationRejectsCatalogGeometryTampering() throws {
        let singlePayload = neuropixels2CatalogModel(
            fourShank: false,
            detailed: true
        )
        let singleModel = try decodedCatalogModel(singlePayload)
        let singleRequest = matchingCreateRequest(for: singleModel)

        var masqueradingPlan = planDetail()
        masqueradingPlan["modelId"] = singleModel.modelId
        masqueradingPlan["modelVersion"] = singleModel.modelVersion
        masqueradingPlan["modelDisplayName"] = singleModel.displayName
        masqueradingPlan["verificationStatus"] = singleModel.verificationStatus
        let masqueradingResult = try decode(
            ProbePlanMutationResult.self,
            mutationPayload(status: "created", revision: 8, plan: masqueradingPlan)
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreatedMutation(
                masqueradingResult,
                request: singleRequest,
                catalogModel: singleModel
            )
        }

        let completeSinglePlan = try planDetail(matchingCatalog: singlePayload)
        let completeSingleSites = try #require(
            completeSinglePlan["recordingSites"] as? [[String: Any]]
        )

        var missingSitePlan = completeSinglePlan
        missingSitePlan["recordingSites"] = Array(completeSingleSites.dropLast())
        let missingSiteResult = try decode(
            ProbePlanMutationResult.self,
            mutationPayload(status: "created", revision: 8, plan: missingSitePlan)
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreatedMutation(
                missingSiteResult,
                request: singleRequest,
                catalogModel: singleModel
            )
        }

        for (field, value) in [
            ("siteId", "forged-site"),
            ("role", "reference"),
            ("bank", "forged-bank"),
        ] {
            var substitutedPlan = completeSinglePlan
            var substitutedSites = completeSingleSites
            substitutedSites[substitutedSites.count - 1][field] = value
            substitutedPlan["recordingSites"] = substitutedSites
            let substitutedResult = try decode(
                ProbePlanMutationResult.self,
                mutationPayload(
                    status: "created",
                    revision: 8,
                    plan: substitutedPlan
                )
            )
            #expect(throws: ProbePlanningValidationError.self) {
                try ProbePlanningValidator.validateCreatedMutation(
                    substitutedResult,
                    request: singleRequest,
                    catalogModel: singleModel
                )
            }
        }

        var wrongBankPlan = completeSinglePlan
        var wrongBankSites = completeSingleSites
        wrongBankSites[0]["bank"] = "forged-bank"
        wrongBankPlan["recordingSites"] = wrongBankSites
        let wrongBankUpdate = try decode(
            ProbePlanMutationResult.self,
            mutationPayload(
                status: "updated",
                revision: 8,
                plan: wrongBankPlan,
                priorAnalysisCleared: true
            )
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateUpdatedMutation(
                wrongBankUpdate,
                request: matchingUpdateRequest(for: singleModel),
                catalogModel: singleModel
            )
        }

        let fourPayload = neuropixels2CatalogModel(
            fourShank: true,
            detailed: true
        )
        let fourModel = try decodedCatalogModel(fourPayload)
        let fourRequest = matchingCreateRequest(for: fourModel)
        let completeFourPlan = try planDetail(matchingCatalog: fourPayload)
        let completeFourShanks = try #require(
            completeFourPlan["shanks"] as? [[String: Any]]
        )
        let completeFourSites = try #require(
            completeFourPlan["recordingSites"] as? [[String: Any]]
        )

        var missingShankPlan = completeFourPlan
        missingShankPlan["shanks"] = Array(completeFourShanks.dropLast())
        missingShankPlan["recordingSites"] = completeFourSites.filter {
            ($0["shankId"] as? String) != "shank-3"
        }
        let missingShankResult = try decode(
            ProbePlanMutationResult.self,
            mutationPayload(status: "created", revision: 8, plan: missingShankPlan)
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreatedMutation(
                missingShankResult,
                request: fourRequest,
                catalogModel: fourModel
            )
        }

        var reassignedPlan = completeFourPlan
        var reassignedSites = completeFourSites
        reassignedSites[0]["shankId"] = "shank-1"
        reassignedPlan["recordingSites"] = reassignedSites
        let reassignedResult = try decode(
            ProbePlanMutationResult.self,
            mutationPayload(status: "created", revision: 8, plan: reassignedPlan)
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreatedMutation(
                reassignedResult,
                request: fourRequest,
                catalogModel: fourModel
            )
        }
    }

    @Test("Spatial validation rejects collapsed, offset, scaled, and invalid-basis geometry")
    func mutationRejectsSpatialGeometryTampering() throws {
        let catalogPayload = neuropixels2CatalogModel(
            fourShank: false,
            detailed: true
        )
        let catalogModel = try decodedCatalogModel(catalogPayload)
        let request = matchingCreateRequest(for: catalogModel)
        let completePlan = try planDetail(matchingCatalog: catalogPayload)
        let completeSites = try #require(
            completePlan["recordingSites"] as? [[String: Any]]
        )

        var collapsedPlan = completePlan
        var collapsedSites = completeSites
        let collapsedPoint = try #require(
            collapsedSites[0]["point"] as? [String: Any]
        )
        for index in collapsedSites.indices {
            collapsedSites[index]["point"] = collapsedPoint
        }
        collapsedPlan["recordingSites"] = collapsedSites
        try expectInvalidCreatedGeometry(
            collapsedPlan,
            request: request,
            catalogModel: catalogModel
        )

        var offsetPlan = completePlan
        var offsetSites = completeSites
        var offsetPoint = try #require(
            offsetSites[100]["point"] as? [String: Any]
        )
        offsetPoint["apMicrometres"] =
            try #require(offsetPoint["apMicrometres"] as? Double) + 0.01
        offsetSites[100]["point"] = offsetPoint
        offsetPlan["recordingSites"] = offsetSites
        try expectInvalidCreatedGeometry(
            offsetPlan,
            request: request,
            catalogModel: catalogModel
        )

        var dimensionPlan = completePlan
        var dimensionShanks = try #require(
            dimensionPlan["shanks"] as? [[String: Any]]
        )
        dimensionShanks[0]["widthMicrometres"] =
            try #require(dimensionShanks[0]["widthMicrometres"] as? Double) + 1
        dimensionPlan["shanks"] = dimensionShanks
        try expectInvalidCreatedGeometry(
            dimensionPlan,
            request: request,
            catalogModel: catalogModel
        )

        var scalePlan = completePlan
        var scalePlacement = try #require(
            scalePlan["placement"] as? [String: Any]
        )
        scalePlacement["modelToPlacementUniformScale"] = 1.01
        scalePlan["placement"] = scalePlacement
        try expectInvalidCreatedGeometry(
            scalePlan,
            request: request,
            catalogModel: catalogModel
        )

        var basisPlan = completePlan
        var basisPlacement = try #require(
            basisPlan["placement"] as? [String: Any]
        )
        var normal = try #require(
            basisPlacement["localNormalDirection"] as? [String: Any]
        )
        for component in ["ap", "ml", "dv"] {
            normal[component] = -(try #require(normal[component] as? Double))
        }
        basisPlacement["localNormalDirection"] = normal
        basisPlan["placement"] = basisPlacement
        try expectInvalidCreatedGeometry(
            basisPlan,
            request: request,
            catalogModel: catalogModel
        )

        var inwardPlan = completePlan
        var inwardPlacement = try #require(
            inwardPlan["placement"] as? [String: Any]
        )
        var inward = try #require(
            inwardPlacement["inwardDirection"] as? [String: Any]
        )
        for component in ["ap", "ml", "dv"] {
            inward[component] = -(try #require(inward[component] as? Double))
        }
        inwardPlacement["inwardDirection"] = inward
        inwardPlan["placement"] = inwardPlacement
        try expectInvalidCreatedGeometry(
            inwardPlan,
            request: request,
            catalogModel: catalogModel
        )

        var atlasConversionPlan = completePlan
        var atlasPlacement = try #require(
            atlasConversionPlan["placement"] as? [String: Any]
        )
        var atlasFrame = try #require(
            atlasPlacement["atlasFrame"] as? [String: Any]
        )
        var atlasTarget = try #require(
            atlasFrame["target"] as? [String: Any]
        )
        atlasTarget["mlMicrometres"] =
            try #require(atlasTarget["mlMicrometres"] as? Double) + 0.01
        atlasFrame["target"] = atlasTarget
        atlasPlacement["atlasFrame"] = atlasFrame
        atlasConversionPlan["placement"] = atlasPlacement
        try expectInvalidCreatedGeometry(
            atlasConversionPlan,
            request: request,
            catalogModel: catalogModel
        )
    }

    @Test("Placement modes encode only their exact input fields")
    func placementModeRequestShapes() throws {
        let entryAndTarget = ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Entry and target",
            placementMode: .entryAndTarget,
            entryAPMillimetres: -2.1,
            entryMLMillimetres: -0.8,
            entryDVMillimetres: -0.2,
            axialRotationDegrees: 0,
            customGeometryAcknowledged: true
        )
        try ProbePlanningValidator.validateCreate(entryAndTarget)
        #expect(try keys(entryAndTarget) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "targetId",
            "modelId", "modelVersion", "name", "placementMode",
            "entryAPMillimetres", "entryMLMillimetres", "entryDVMillimetres",
            "axialRotationDegrees", "customGeometryAcknowledged",
        ])

        let entryAnglesDepth = ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Entry angles depth",
            placementMode: .entryAnglesDepth,
            entryAPMillimetres: -2.1,
            entryMLMillimetres: -0.8,
            entryDVMillimetres: -0.2,
            azimuthDegrees: -12,
            elevationDegrees: -80,
            insertionDepthMicrometres: 3_200,
            axialRotationDegrees: 5,
            customGeometryAcknowledged: true
        )
        try ProbePlanningValidator.validateCreate(entryAnglesDepth)
        #expect(try keys(entryAnglesDepth) == [
            "protocolVersion", "projectId", "expectedProjectRevision", "targetId",
            "modelId", "modelVersion", "name", "placementMode",
            "entryAPMillimetres", "entryMLMillimetres", "entryDVMillimetres",
            "azimuthDegrees", "elevationDegrees", "insertionDepthMicrometres",
            "axialRotationDegrees", "customGeometryAcknowledged",
        ])

        for mode in [
            ProbePlacementMode.targetAnglesDepth,
            .stereotaxicTargetManipulator,
        ] {
            let request = ProbePlanCreateParameters(
                projectId: projectId,
                expectedProjectRevision: 7,
                targetId: targetId,
                modelId: ProbePlanningContract.genericModelId,
                modelVersion: ProbePlanningContract.genericModelVersion,
                name: mode.displayName,
                placementMode: mode,
                azimuthDegrees: -12,
                elevationDegrees: -80,
                insertionDepthMicrometres: 3_200,
                axialRotationDegrees: 5,
                customGeometryAcknowledged: true
            )
            try ProbePlanningValidator.validateCreate(request)
            #expect(try keys(request) == [
                "protocolVersion", "projectId", "expectedProjectRevision", "targetId",
                "modelId", "modelVersion", "name", "placementMode", "azimuthDegrees",
                "elevationDegrees", "insertionDepthMicrometres", "axialRotationDegrees",
                "customGeometryAcknowledged",
            ])
        }
    }

    @Test("Placement mode metadata and validator reject mixed field shapes")
    func placementModeValidation() throws {
        #expect(ProbePlacementMode.allCases.map(\.rawValue) == [
            "ENTRY_AND_TARGET",
            "ENTRY_ANGLES_DEPTH",
            "TARGET_ANGLES_DEPTH",
            "STEREOTAXIC_TARGET_MANIPULATOR",
            "ATLAS_SURFACE_AP_ML",
        ])
        #expect(ProbePlacementMode.entryAndTarget.requiresEntryCoordinates)
        #expect(!ProbePlacementMode.entryAndTarget.requiresAnglesAndDepth)
        #expect(ProbePlacementMode.entryAnglesDepth.requiresEntryCoordinates)
        #expect(ProbePlacementMode.entryAnglesDepth.requiresAnglesAndDepth)
        #expect(!ProbePlacementMode.targetAnglesDepth.requiresEntryCoordinates)
        #expect(ProbePlacementMode.targetAnglesDepth.requiresAnglesAndDepth)
        #expect(!ProbePlacementMode.atlasSurfaceAPML.requiresEntryCoordinates)
        #expect(!ProbePlacementMode.atlasSurfaceAPML.requiresAnglesAndDepth)

        let missingEntry = ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Missing entry",
            placementMode: .entryAndTarget,
            axialRotationDegrees: 0,
            customGeometryAcknowledged: true
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreate(missingEntry)
        }

        let extraEntry = ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Extra entry",
            placementMode: .targetAnglesDepth,
            entryAPMillimetres: 0,
            entryMLMillimetres: 0,
            entryDVMillimetres: 0,
            azimuthDegrees: 0,
            elevationDegrees: -90,
            insertionDepthMicrometres: 1_000,
            axialRotationDegrees: 0,
            customGeometryAcknowledged: true
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreate(extraEntry)
        }

        let missingDepth = ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            name: "Missing depth",
            placementMode: .targetAnglesDepth,
            azimuthDegrees: 0,
            elevationDegrees: -90,
            axialRotationDegrees: 0,
            customGeometryAcknowledged: true
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreate(missingDepth)
        }
    }

    @Test("Catalog exposes only NP2 single and standard four-shank in order")
    func catalogOrderAndSelection() throws {
        let list = try decode(
            ProbeCatalogListResult.self,
            [
                "protocolVersion": 1,
                "status": "listed",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "modelCount": 2,
                "models": [
                    neuropixels2CatalogModel(fourShank: false, detailed: false),
                    neuropixels2CatalogModel(fourShank: true, detailed: false),
                ],
            ]
        )
        try ProbePlanningValidator.validateCatalogList(list)
        #expect(
            list.models.map(\.modelId) == [
                ProbePlanningContract.neuropixels2SingleShankModelId,
                ProbePlanningContract.neuropixels2StandardFourShankModelId,
            ]
        )

        let reverseOrder = Array(list.models.reversed())
        let defaultModel = ProbePlanningContract.preferredCatalogModel(
            in: reverseOrder,
            preservingIdentity: nil
        )
        #expect(
            defaultModel?.modelId
                == ProbePlanningContract.neuropixels2SingleShankModelId
        )
        let preservedFourShank = ProbePlanningContract.preferredCatalogModel(
            in: reverseOrder,
            preservingIdentity: list.models[1].id
        )
        #expect(
            preservedFourShank?.modelId
                == ProbePlanningContract.neuropixels2StandardFourShankModelId
        )

        var reorderedPayload: [String: Any] = [
            "protocolVersion": 1,
            "status": "listed",
            "catalogVersion": ProbePlanningContract.catalogVersion,
            "modelCount": 2,
            "models": [
                neuropixels2CatalogModel(fourShank: true, detailed: false),
                neuropixels2CatalogModel(fourShank: false, detailed: false),
            ],
        ]
        let reordered = try decode(ProbeCatalogListResult.self, reorderedPayload)
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCatalogList(reordered)
        }
        reorderedPayload["catalogVersion"] = "brain3d-probe-catalog-tampered"
        let wrongVersion = try decode(ProbeCatalogListResult.self, reorderedPayload)
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCatalogList(wrongVersion)
        }
    }

    @Test("NP2 identities preserve every site without gating the public models")
    func neuropixels2CatalogAndCreateGate() throws {
        let configurations = [
            (
                fourShank: false,
                quadBase: false,
                modelId: ProbePlanningContract.neuropixels2SingleShankModelId,
                displayName: ProbePlanningContract.neuropixels2SingleShankDisplayName,
                shankCount: 1,
                siteCount: 1_280,
                sourceCount: 5,
                simultaneousChannelCount: 384,
                requiresAcknowledgement: false
            ),
            (
                fourShank: true,
                quadBase: false,
                modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId,
                displayName: ProbePlanningContract.neuropixels2StandardFourShankDisplayName,
                shankCount: 4,
                siteCount: 5_120,
                sourceCount: 5,
                simultaneousChannelCount: 384,
                requiresAcknowledgement: false
            ),
            (
                fourShank: true,
                quadBase: true,
                modelId: ProbePlanningContract.neuropixels2QuadBaseFourShankModelId,
                displayName: ProbePlanningContract.neuropixels2QuadBaseFourShankDisplayName,
                shankCount: 4,
                siteCount: 5_120,
                sourceCount: 6,
                simultaneousChannelCount: 1_536,
                requiresAcknowledgement: true
            ),
        ]

        for configuration in configurations {
            let modelPayload = neuropixels2CatalogModel(
                fourShank: configuration.fourShank,
                quadBase: configuration.quadBase,
                detailed: true
            )
            let detail = try decode(
                ProbeCatalogGetResult.self,
                [
                    "protocolVersion": 1,
                    "status": "found",
                    "catalogVersion": ProbePlanningContract.catalogVersion,
                    "model": modelPayload,
                ]
            )
            try ProbePlanningValidator.validateCatalogGet(
                detail,
                modelId: configuration.modelId,
                modelVersion: ProbePlanningContract.neuropixels2ModelVersion
            )
            #expect(detail.model.displayName == configuration.displayName)
            #expect(
                detail.model.verificationStatus
                    == ProbePlanningContract.sourceTranscribedReviewPendingStatus
            )
            #expect(detail.model.completeGeometryTranscribed == true)
            #expect(detail.model.independentTranscriptionReviewCompleted == false)
            #expect(detail.model.independentlyReviewedBy == nil)
            #expect(detail.model.shankCount == configuration.shankCount)
            #expect(detail.model.siteCount == configuration.siteCount)
            #expect(detail.model.primarySources?.count == configuration.sourceCount)
            #expect(detail.model.geometryNotes?.contains(
                "\(configuration.simultaneousChannelCount) simultaneously configurable"
            ) == true)

            let shanks = try #require(detail.model.shanks)
            #expect(shanks.count == configuration.shankCount)
            for (shankIndex, shank) in shanks.enumerated() {
                #expect(shank.shankId == "shank-\(shankIndex)")
                #expect(shank.centerLateralMicrometres == Double(shankIndex * 250))
                #expect(shank.sites.count == 1_280)
                #expect(shank.sites[0].siteId == "shank-\(shankIndex)-electrode-0000")
                #expect(shank.sites[0].axialFromTipMicrometres == 206)
                #expect(shank.sites[0].lateralMicrometres == -8)
                #expect(shank.sites[0].bank == "virtual-bank-0")
                #expect(shank.sites[1].lateralMicrometres == 24)
                #expect(
                    shank.sites[1_279].siteId
                        == "shank-\(shankIndex)-electrode-1279"
                )
                #expect(shank.sites[1_279].axialFromTipMicrometres == 9_791)
                #expect(shank.sites[1_279].bank == "virtual-bank-3")
            }

            let unacknowledged = probeCreate(
                modelId: configuration.modelId,
                modelVersion: ProbePlanningContract.neuropixels2ModelVersion,
                acknowledged: false
            )
            if configuration.requiresAcknowledgement {
                #expect(throws: ProbePlanningValidationError.self) {
                    try ProbePlanningValidator.validateCreate(unacknowledged)
                }
            } else {
                try ProbePlanningValidator.validateCreate(unacknowledged)
            }
            try ProbePlanningValidator.validateCreate(probeCreate(
                modelId: configuration.modelId,
                modelVersion: ProbePlanningContract.neuropixels2ModelVersion,
                acknowledged: true
            ))

            var planPayload = planGetPayload(regionAnalysis: nil)
            planPayload["plan"] = try planDetail(matchingCatalog: modelPayload)
            let planResult = try decode(ProbePlanGetResult.self, planPayload)
            try ProbePlanningValidator.validatePlanGet(
                planResult,
                projectId: projectId,
                projectRevision: 7,
                planId: planId
            )
            try ProbePlanningValidator.validateCatalogModel(
                detail.model,
                matches: planResult.plan
            )
        }
    }

    @Test("NP2 rejects any provenance or geometry tampering")
    func neuropixels2RejectsTampering() throws {
        let sourceFieldTampering = [
            "title": "Wrong source title",
            "sourceUrl": "https://example.com/wrong-source.pdf",
            "documentRevision": "wrong revision",
            "retrievedOn": "2026-07-22",
            "sha256": hex("f"),
            "citation": "Wrong citation",
        ]
        for (field, value) in sourceFieldTampering {
            var model = neuropixels2CatalogModel(fourShank: false, detailed: true)
            var sources = model["primarySources"] as! [[String: Any]]
            sources[0][field] = value
            model["primarySources"] = sources
            let result = try decode(
                ProbeCatalogGetResult.self,
                [
                    "protocolVersion": 1,
                    "status": "found",
                    "catalogVersion": ProbePlanningContract.catalogVersion,
                    "model": model,
                ]
            )
            #expect(throws: ProbePlanningValidationError.self) {
                try ProbePlanningValidator.validateCatalogGet(
                    result,
                    modelId: ProbePlanningContract.neuropixels2SingleShankModelId,
                    modelVersion: ProbePlanningContract.neuropixels2ModelVersion
                )
            }
        }

        for sourceIndex in 0 ..< 6 {
            var model = neuropixels2CatalogModel(
                fourShank: true,
                quadBase: true,
                detailed: true
            )
            var sources = model["primarySources"] as! [[String: Any]]
            sources[sourceIndex]["sha256"] = hex(
                Character(String((sourceIndex + 1) % 10))
            )
            model["primarySources"] = sources
            let result = try decode(
                ProbeCatalogGetResult.self,
                [
                    "protocolVersion": 1,
                    "status": "found",
                    "catalogVersion": ProbePlanningContract.catalogVersion,
                    "model": model,
                ]
            )
            #expect(throws: ProbePlanningValidationError.self) {
                try ProbePlanningValidator.validateCatalogGet(
                    result,
                    modelId: ProbePlanningContract.neuropixels2QuadBaseFourShankModelId,
                    modelVersion: ProbePlanningContract.neuropixels2ModelVersion
                )
            }
        }

        var reorderedSources = neuropixels2CatalogModel(fourShank: false, detailed: true)
        var sources = reorderedSources["primarySources"] as! [[String: Any]]
        sources.swapAt(0, 1)
        reorderedSources["primarySources"] = sources
        try expectInvalidNeuropixels2Detail(reorderedSources, fourShank: false)

        var wrongOffset = neuropixels2CatalogModel(fourShank: true, detailed: true)
        var offsetShanks = wrongOffset["shanks"] as! [[String: Any]]
        offsetShanks[2]["centerLateralMicrometres"] = 501.0
        wrongOffset["shanks"] = offsetShanks
        try expectInvalidNeuropixels2Detail(
            wrongOffset,
            fourShank: true,
            quadBase: false
        )

        var wrongSite = neuropixels2CatalogModel(fourShank: false, detailed: true)
        var siteShanks = wrongSite["shanks"] as! [[String: Any]]
        var sites = siteShanks[0]["sites"] as! [[String: Any]]
        sites[1_279]["bank"] = "virtual-bank-2"
        siteShanks[0]["sites"] = sites
        wrongSite["shanks"] = siteShanks
        try expectInvalidNeuropixels2Detail(wrongSite, fourShank: false)

        var wrongChannelIdentity = neuropixels2CatalogModel(
            fourShank: true,
            quadBase: true,
            detailed: true
        )
        wrongChannelIdentity["geometryNotes"] =
            "NP2 Quad Base four-shank exact implantable geometry; "
                + "384 simultaneously configurable channels"
        try expectInvalidNeuropixels2Detail(
            wrongChannelIdentity,
            fourShank: true,
            quadBase: true
        )

        let wrongVersion = probeCreate(
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId,
            modelVersion: "source-snapshot-tampered",
            acknowledged: true
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreate(wrongVersion)
        }
    }

    @Test("NP1 preserves 960 sourced sites and cannot claim unfinished review as verified")
    func neuropixelsCatalogReviewGate() throws {
        let detail = try decode(
            ProbeCatalogGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "model": neuropixelsCatalogModel(detailed: true),
            ]
        )
        try ProbePlanningValidator.validateCatalogGet(
            detail,
            modelId: ProbePlanningContract.neuropixelsModelId,
            modelVersion: ProbePlanningContract.neuropixelsModelVersion
        )
        #expect(
            detail.model.verificationStatus
                == ProbePlanningContract.sourceTranscribedReviewPendingStatus
        )
        #expect(detail.model.completeGeometryTranscribed == true)
        #expect(detail.model.independentTranscriptionReviewCompleted == false)
        #expect(detail.model.independentlyReviewedBy == nil)
        #expect(detail.model.primarySources?.map(\.sha256) == [
            ProbePlanningContract.manufacturerSpecSHA256,
            ProbePlanningContract.probeTableSHA256,
            ProbePlanningContract.spikeGLXGeometrySHA256,
            ProbePlanningContract.spikeGLXMetadataSHA256,
        ])
        let sites = try #require(detail.model.shanks?.first?.sites)
        #expect(sites.count == 960)
        #expect(sites[0].axialFromTipMicrometres == 209)
        #expect(sites[0].lateralMicrometres == -8)
        #expect(sites[1].lateralMicrometres == 24)
        #expect(sites[2].lateralMicrometres == -24)
        #expect(sites[191].role == "reference")
        #expect(sites[575].role == "reference")
        #expect(sites[959].role == "reference")
        #expect(sites[959].bank == "bank-2")

        var falseReview = neuropixelsCatalogModel(detailed: true)
        falseReview["independentTranscriptionReviewCompleted"] = true
        falseReview["independentlyReviewedBy"] = "Unrecorded reviewer"
        let falseReviewResult = try decode(
            ProbeCatalogGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "model": falseReview,
            ]
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCatalogGet(
                falseReviewResult,
                modelId: ProbePlanningContract.neuropixelsModelId,
                modelVersion: ProbePlanningContract.neuropixelsModelVersion
            )
        }

        var corruptSource = neuropixelsCatalogModel(detailed: true)
        var sources = corruptSource["primarySources"] as! [[String: Any]]
        sources[0]["sha256"] = hex("f")
        corruptSource["primarySources"] = sources
        let corruptSourceResult = try decode(
            ProbeCatalogGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "model": corruptSource,
            ]
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCatalogGet(
                corruptSourceResult,
                modelId: ProbePlanningContract.neuropixelsModelId,
                modelVersion: ProbePlanningContract.neuropixelsModelVersion
            )
        }

        let unacknowledged = probeCreate(
            modelId: ProbePlanningContract.neuropixelsModelId,
            modelVersion: ProbePlanningContract.neuropixelsModelVersion,
            acknowledged: false
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreate(unacknowledged)
        }
        try ProbePlanningValidator.validateCreate(probeCreate(
            modelId: ProbePlanningContract.neuropixelsModelId,
            modelVersion: ProbePlanningContract.neuropixelsModelVersion,
            acknowledged: true
        ))
    }

    @Test("Generic model remains an exact acknowledged software-test fixture")
    func genericCatalogGate() throws {
        let detail = try decode(
            ProbeCatalogGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "model": genericCatalogModel(detailed: true),
            ]
        )
        try ProbePlanningValidator.validateCatalogGet(
            detail,
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion
        )
        #expect(detail.model.displayName == ProbePlanningContract.genericDisplayName)
        #expect(detail.model.warning == ProbePlanningContract.genericWarning)
        #expect(detail.model.verifiedDeviceLabelPermitted == false)
        #expect(detail.model.shanks?.first?.sites.count == 16)

        let unacknowledged = probeCreate(
            modelId: ProbePlanningContract.genericModelId,
            modelVersion: ProbePlanningContract.genericModelVersion,
            acknowledged: false
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreate(unacknowledged)
        }
    }

    @Test("Plan detail locks frames, safety, hashes, and placement convention")
    func planValidation() throws {
        let result = try decode(
            ProbePlanGetResult.self,
            planGetPayload(regionAnalysis: nil)
        )
        try ProbePlanningValidator.validatePlanGet(
            result,
            projectId: projectId,
            projectRevision: 7,
            planId: planId
        )
        #expect(result.plan.placement.elevationDegrees == -80)
        #expect(result.plan.usableForNavigation == false)
        #expect(result.plan.hasCurrentPlanningGeometry)
        #expect(!result.plan.requiresPlanningGeometryUpdate)
        #expect(result.majorVesselAnalysis == nil)
        #expect(result.plan.placementDraft.mode == .stereotaxicTargetManipulator)
        #expect(result.plan.placementDraft.azimuthDegrees == -12.5)

        var missingVesselAnalysisKey = planGetPayload(regionAnalysis: nil)
        missingVesselAnalysisKey.removeValue(forKey: "majorVesselAnalysis")
        #expect(throws: (any Error).self) {
            try decode(ProbePlanGetResult.self, missingVesselAnalysisKey)
        }

        var pendingReview = planGetPayload(regionAnalysis: nil)
        var pendingReviewPlan = pendingReview["plan"] as! [String: Any]
        pendingReviewPlan["modelId"] = ProbePlanningContract.neuropixelsModelId
        pendingReviewPlan["modelVersion"] = ProbePlanningContract.neuropixelsModelVersion
        pendingReviewPlan["modelDisplayName"] = ProbePlanningContract.neuropixelsDisplayName
        pendingReviewPlan["verificationStatus"] =
            ProbePlanningContract.sourceTranscribedReviewPendingStatus
        pendingReview["plan"] = pendingReviewPlan
        let pendingReviewResult = try decode(ProbePlanGetResult.self, pendingReview)
        try ProbePlanningValidator.validatePlanGet(
            pendingReviewResult,
            projectId: projectId,
            projectRevision: 7,
            planId: planId
        )

        var unsafe = planGetPayload(regionAnalysis: nil)
        var unsafePlan = unsafe["plan"] as! [String: Any]
        unsafePlan["usableForNavigation"] = true
        unsafe["plan"] = unsafePlan
        let unsafeResult = try decode(ProbePlanGetResult.self, unsafe)
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validatePlanGet(
                unsafeResult,
                projectId: projectId,
                projectRevision: 7,
                planId: planId
            )
        }

        var wrongFrame = planGetPayload(regionAnalysis: nil)
        var wrongPlan = wrongFrame["plan"] as! [String: Any]
        var placement = wrongPlan["placement"] as! [String: Any]
        var atlasFrame = placement["atlasFrame"] as! [String: Any]
        atlasFrame["componentOrder"] = ["AP", "ML", "DV"]
        placement["atlasFrame"] = atlasFrame
        wrongPlan["placement"] = placement
        wrongFrame["plan"] = wrongPlan
        let wrongResult = try decode(ProbePlanGetResult.self, wrongFrame)
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validatePlanGet(
                wrongResult,
                projectId: projectId,
                projectRevision: 7,
                planId: planId
            )
        }
    }

    @Test("V3 restores explicit entry coordinates and mode-specific draft fields")
    func explicitPlacementDraftRoundTrip() throws {
        var payload = planGetPayload(regionAnalysis: nil)
        var plan = try #require(payload["plan"] as? [String: Any])
        plan["manipulatorInput"] = NSNull()
        plan["placementInput"] = [
            "mode": ProbePlacementMode.entryAndTarget.rawValue,
            "entry": [
                "frameId": ProbePlanningContract.bregmaEntryFrameId,
                "origin": "bregma",
                "componentOrder": ["AP", "ML", "DV"],
                "units": "millimetre",
                "apPositiveDirection": "anterior",
                "apNegativeDirection": "posterior/back",
                "mlPositiveDirection": "right",
                "mlNegativeDirection": "left",
                "dvPositiveDirection": "dorsal/up",
                "dvNegativeDirection": "deep/ventral",
                "apMillimetres": -2.1,
                "mlMillimetres": -0.8,
                "dvMillimetres": -0.2,
            ],
            "angleFrameId": NSNull(),
            "azimuthDegrees": NSNull(),
            "elevationDegrees": NSNull(),
            "insertionDepthMicrometres": NSNull(),
            "axialRotationDegrees": 5.0,
            "angleConvention": NSNull(),
        ]
        var placement = try #require(plan["placement"] as? [String: Any])
        placement["method"] = ProbePlacementMode.entryAndTarget.normalizedPlacementMethod
        plan["placement"] = placement
        payload["plan"] = plan

        let result = try decode(ProbePlanGetResult.self, payload)
        try ProbePlanningValidator.validatePlanGet(
            result,
            projectId: projectId,
            projectRevision: 7,
            planId: planId
        )
        let draft = result.plan.placementDraft
        #expect(draft.mode == .entryAndTarget)
        #expect(draft.entryAPMillimetres == -2.1)
        #expect(draft.entryMLMillimetres == -0.8)
        #expect(draft.entryDVMillimetres == -0.2)
        #expect(draft.azimuthDegrees == nil)
        #expect(draft.elevationDegrees == nil)
        #expect(draft.insertionDepthMicrometres == nil)
        #expect(draft.axialRotationDegrees == 5)
    }

    @Test("V3 angle inputs stay bound to the frame in which their geometry was solved")
    func placementAngleFrameBinding() throws {
        var targetPayload = planGetPayload(regionAnalysis: nil)
        var targetPlan = try #require(targetPayload["plan"] as? [String: Any])
        targetPlan["manipulatorInput"] = NSNull()
        var targetPlacement = try #require(targetPlan["placement"] as? [String: Any])
        targetPlacement["method"] = ProbePlacementMode.targetAnglesDepth
            .normalizedPlacementMethod
        targetPlan["placement"] = targetPlacement
        targetPlan["placementInput"] = [
            "mode": ProbePlacementMode.targetAnglesDepth.rawValue,
            "entry": NSNull(),
            "angleFrameId": "ATLAS_CANONICAL_AP_ML_DV_UM:test",
            "azimuthDegrees": -12.5,
            "elevationDegrees": -80.0,
            "insertionDepthMicrometres": 3_200.0,
            "axialRotationDegrees": 5.0,
            "angleConvention": ProbePlanningContract.angleConvention,
        ]
        targetPayload["plan"] = targetPlan
        let validTarget = try decode(ProbePlanGetResult.self, targetPayload)
        try ProbePlanningValidator.validatePlanGet(
            validTarget,
            projectId: projectId,
            projectRevision: 7,
            planId: planId
        )

        var wrongTargetPlan = targetPlan
        var wrongTargetInput = try #require(
            wrongTargetPlan["placementInput"] as? [String: Any]
        )
        wrongTargetInput["angleFrameId"] = "ANOTHER_FRAME"
        wrongTargetPlan["placementInput"] = wrongTargetInput
        var wrongTargetPayload = targetPayload
        wrongTargetPayload["plan"] = wrongTargetPlan
        let wrongTarget = try decode(ProbePlanGetResult.self, wrongTargetPayload)
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validatePlanGet(
                wrongTarget,
                projectId: projectId,
                projectRevision: 7,
                planId: planId
            )
        }

        var entryPayload = targetPayload
        var entryPlan = targetPlan
        var entryPlacement = targetPlacement
        entryPlacement["method"] = ProbePlacementMode.entryAnglesDepth
            .normalizedPlacementMethod
        entryPlan["placement"] = entryPlacement
        entryPlan["placementInput"] = [
            "mode": ProbePlacementMode.entryAnglesDepth.rawValue,
            "entry": [
                "frameId": ProbePlanningContract.bregmaEntryFrameId,
                "origin": "bregma",
                "componentOrder": ["AP", "ML", "DV"],
                "units": "millimetre",
                "apPositiveDirection": "anterior",
                "apNegativeDirection": "posterior/back",
                "mlPositiveDirection": "right",
                "mlNegativeDirection": "left",
                "dvPositiveDirection": "dorsal/up",
                "dvNegativeDirection": "deep/ventral",
                "apMillimetres": -2.1,
                "mlMillimetres": -0.8,
                "dvMillimetres": -0.2,
            ],
            "angleFrameId": "STEREOTAXIC:fixture",
            "azimuthDegrees": -12.5,
            "elevationDegrees": -80.0,
            "insertionDepthMicrometres": 3_200.0,
            "axialRotationDegrees": 5.0,
            "angleConvention": ProbePlanningContract.angleConvention,
        ]
        entryPayload["plan"] = entryPlan
        let validEntry = try decode(ProbePlanGetResult.self, entryPayload)
        try ProbePlanningValidator.validatePlanGet(
            validEntry,
            projectId: projectId,
            projectRevision: 7,
            planId: planId
        )

        var wrongEntryPlan = entryPlan
        var wrongEntryInput = try #require(
            wrongEntryPlan["placementInput"] as? [String: Any]
        )
        wrongEntryInput["angleFrameId"] = "SUBJECT_SKULL_AP_ML_DV_UM"
        wrongEntryPlan["placementInput"] = wrongEntryInput
        var wrongEntryPayload = entryPayload
        wrongEntryPayload["plan"] = wrongEntryPlan
        let wrongEntry = try decode(ProbePlanGetResult.self, wrongEntryPayload)
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validatePlanGet(
                wrongEntry,
                projectId: projectId,
                projectRevision: 7,
                planId: planId
            )
        }
    }

    @Test("V2 stereotaxic plans remain current and restore their manipulator draft")
    func v2PlanRemainsCurrent() throws {
        var payload = planGetPayload(regionAnalysis: nil)
        var plan = try #require(payload["plan"] as? [String: Any])
        plan["placementInput"] = NSNull()
        var provenance = try #require(plan["provenance"] as? [String: Any])
        provenance["planningAlgorithmVersion"] =
            ProbePlanningContract.stereotaxicPlanningAlgorithmVersion
        plan["provenance"] = provenance
        payload["plan"] = plan

        let result = try decode(ProbePlanGetResult.self, payload)
        try ProbePlanningValidator.validatePlanGet(
            result,
            projectId: projectId,
            projectRevision: 7,
            planId: planId
        )
        #expect(result.plan.hasCurrentPlanningGeometry)
        #expect(!result.plan.requiresPlanningGeometryUpdate)
        #expect(result.plan.placementInput == nil)
        #expect(result.plan.placementDraft.mode == .stereotaxicTargetManipulator)
        #expect(result.plan.placementDraft.insertionDepthMicrometres == 3_200)
    }

    @Test("Legacy v1 plan is selectable only as an explicit update draft")
    func legacyPlanIsUpdateReadyButNotCurrent() throws {
        var legacyPayload = planGetPayload(regionAnalysis: nil)
        var legacyPlan = try #require(legacyPayload["plan"] as? [String: Any])
        legacyPlan["manipulatorInput"] = NSNull()
        legacyPlan["placementInput"] = NSNull()
        var placement = try #require(legacyPlan["placement"] as? [String: Any])
        placement["method"] = ProbePlanningContract.legacyPlacementMethod
        legacyPlan["placement"] = placement
        var provenance = try #require(legacyPlan["provenance"] as? [String: Any])
        provenance["planningAlgorithmVersion"] =
            ProbePlanningContract.legacyPlanningAlgorithmVersion
        legacyPlan["provenance"] = provenance
        legacyPayload["plan"] = legacyPlan

        let result = try decode(ProbePlanGetResult.self, legacyPayload)
        try ProbePlanningValidator.validatePlanGet(
            result,
            projectId: projectId,
            projectRevision: 7,
            planId: planId
        )
        #expect(result.plan.requiresPlanningGeometryUpdate)
        #expect(!result.plan.hasCurrentPlanningGeometry)
        #expect(result.plan.manipulatorInput == nil)
        let matchingCatalog = try decode(
            ProbeCatalogGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "model": genericCatalogModel(detailed: true),
            ]
        ).model
        try ProbePlanningValidator.validateCatalogModel(
            matchingCatalog,
            matches: result.plan
        )
        let wrongCatalog = try decode(
            ProbeCatalogGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "model": neuropixelsCatalogModel(detailed: true),
            ]
        ).model
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCatalogModel(
                wrongCatalog,
                matches: result.plan
            )
        }
        let resolution = try AtlasASRResolution(
            apMicrometres: 25,
            dvMicrometres: 25,
            mlMicrometres: 25
        )
        let shape = try AtlasASRShape(apVoxels: 528, dvVoxels: 320, mlVoxels: 456)
        #expect(ProbeSliceOverlayGeometry.make(
            plan: result.plan,
            orientation: .coronal,
            sliceIndex: 1,
            resolution: resolution,
            shape: shape
        ) == nil)
        #expect(ProbeSliceOverlayGeometry.makeDorsalProjection(
            plan: result.plan,
            resolution: resolution,
            shape: shape
        ) == nil)
        let draft = result.plan.manipulatorDraft
        #expect(draft.azimuthDegrees == -12.5)
        #expect(draft.elevationDegrees == -80)
        #expect(draft.insertionDepthMicrometres == 3_200)
        #expect(draft.axialRotationDegrees == 5)

        let update = ProbePlanUpdateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            planId: result.plan.planId,
            expectedPlanInputSha256: result.plan.inputSha256,
            targetId: result.plan.targetId ?? "",
            modelId: result.plan.modelId,
            modelVersion: result.plan.modelVersion,
            name: result.plan.name,
            azimuthDegrees: draft.azimuthDegrees,
            elevationDegrees: draft.elevationDegrees,
            insertionDepthMicrometres: draft.insertionDepthMicrometres,
            axialRotationDegrees: draft.axialRotationDegrees,
            customGeometryAcknowledged: true
        )
        try ProbePlanningValidator.validateUpdate(update)

        var mixedPayload = legacyPayload
        var mixedPlan = try #require(mixedPayload["plan"] as? [String: Any])
        mixedPlan["manipulatorInput"] = planDetail()["manipulatorInput"]
        mixedPayload["plan"] = mixedPlan
        let mixed = try decode(ProbePlanGetResult.self, mixedPayload)
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validatePlanGet(
                mixed,
                projectId: projectId,
                projectRevision: 7,
                planId: planId
            )
        }
    }

    @Test("Region bundle validates exact segments, sites, provenance, and navigation lock")
    func regionValidation() throws {
        let planResult = try decode(ProbePlanGetResult.self, planGetPayload(regionAnalysis: nil))
        let result = try decode(
            ProbeRegionResult.self,
            [
                "protocolVersion": 1,
                "status": "analyzed",
                "projectId": projectId,
                "projectRevision": 8,
                "regionAnalysis": regionBundle(),
            ]
        )
        try ProbePlanningValidator.validateRegionResult(
            result,
            projectId: projectId,
            plan: planResult.plan,
            expectedStatus: "analyzed",
            expectedRevision: 8
        )
        #expect(result.regionAnalysis.shanks[0].segments[0].acronym == "VISp")
        #expect(result.regionAnalysis.shanks[0].recordingSiteAssignments[0].insideBrain)

        var unsafeBundle = regionBundle()
        unsafeBundle["usableForNavigation"] = true
        let unsafe = try decode(
            ProbeRegionResult.self,
            [
                "protocolVersion": 1,
                "status": "analyzed",
                "projectId": projectId,
                "projectRevision": 8,
                "regionAnalysis": unsafeBundle,
            ]
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateRegionResult(
                unsafe,
                projectId: projectId,
                plan: planResult.plan,
                expectedStatus: "analyzed",
                expectedRevision: 8
            )
        }
    }

    @Test("Export generation is read-only and confirmation publishes its exact audit identity")
    func exportValidation() throws {
        let plan = try decode(ProbePlanGetResult.self, planGetPayload(regionAnalysis: nil)).plan
        let analysis = try decode(
            ProbeRegionResult.self,
            [
                "protocolVersion": 1,
                "status": "analyzed",
                "projectId": projectId,
                "projectRevision": 8,
                "regionAnalysis": regionBundle(),
            ]
        ).regionAnalysis
        let content = "record_type,plan_id\nregion_segment,\(planId)\n"
        let digest = LowercaseHex.encode(
            SHA256.hash(data: Data(content.utf8))
        )
        let generationRequest = ProbeRegionExportParameters(
            projectId: projectId,
            expectedProjectRevision: 8,
            planId: planId,
            expectedPlanInputSha256: hex("a"),
            format: .csv
        )
        let payload: [String: Any] = [
            "protocolVersion": 1,
            "status": "generated",
            "projectId": projectId,
            "projectRevision": 8,
            "planId": planId,
            "planInputSha256": hex("a"),
            "analysisSha256": hex("e"),
            "format": "csv",
            "mimeType": "text/csv",
            "suggestedFileName": "probe-regions-\(planId).csv",
            "content": content,
            "contentSha256": digest,
            "projectMutated": false,
        ]
        let result = try decode(ProbeRegionExportResult.self, payload)
        try ProbePlanningValidator.validateExportGeneration(
            result,
            request: generationRequest,
            plan: plan,
            analysis: analysis
        )

        var changed = payload
        changed["contentSha256"] = hex("f")
        let corrupt = try decode(ProbeRegionExportResult.self, changed)
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateExportGeneration(
                corrupt,
                request: generationRequest,
                plan: plan,
                analysis: analysis
            )
        }

        for (field, invalidValue): (String, Any) in [
            ("status", "exported"),
            ("projectRevision", 9),
            ("projectMutated", true),
        ] {
            var invalidPayload = payload
            invalidPayload[field] = invalidValue
            let invalid = try decode(ProbeRegionExportResult.self, invalidPayload)
            #expect(throws: ProbePlanningValidationError.self) {
                try ProbePlanningValidator.validateExportGeneration(
                    invalid,
                    request: generationRequest,
                    plan: plan,
                    analysis: analysis
                )
            }
        }

        let confirmRequest = ProbeRegionExportConfirmParameters(
            projectId: projectId,
            expectedProjectRevision: 8,
            planId: planId,
            expectedPlanInputSha256: hex("a"),
            analysisSha256: hex("e"),
            format: .csv,
            contentSha256: digest
        )
        let confirmationPayload: [String: Any] = [
            "protocolVersion": 1,
            "status": "exported",
            "projectId": projectId,
            "projectRevision": 9,
            "planId": planId,
            "planInputSha256": hex("a"),
            "analysisSha256": hex("e"),
            "format": "csv",
            "contentSha256": digest,
            "projectMutated": true,
        ]
        let confirmation = try decode(
            ProbeRegionExportConfirmationResult.self,
            confirmationPayload
        )
        try ProbePlanningValidator.validateExportConfirmation(
            confirmation,
            request: confirmRequest
        )

        for (field, invalidValue): (String, Any) in [
            ("status", "generated"),
            ("projectRevision", 8),
            ("analysisSha256", hex("f")),
            ("contentSha256", hex("f")),
            ("projectMutated", false),
        ] {
            var invalidPayload = confirmationPayload
            invalidPayload[field] = invalidValue
            let invalid = try decode(
                ProbeRegionExportConfirmationResult.self,
                invalidPayload
            )
            #expect(throws: ProbePlanningValidationError.self) {
                try ProbePlanningValidator.validateExportConfirmation(
                    invalid,
                    request: confirmRequest
                )
            }
        }
    }

    private func planGetPayload(regionAnalysis: [String: Any]?) -> [String: Any] {
        [
            "protocolVersion": 1,
            "status": "found",
            "projectId": projectId,
            "projectRevision": 7,
            "plan": planDetail(),
            "regionAnalysis": regionAnalysis ?? NSNull(),
            "majorVesselAnalysis": NSNull(),
        ]
    }

    private func mutationPayload(
        status: String,
        revision: Int,
        plan: [String: Any],
        priorAnalysisCleared: Bool? = nil
    ) -> [String: Any] {
        [
            "protocolVersion": 1,
            "status": status,
            "projectId": projectId,
            "projectRevision": revision,
            "plan": plan,
            "priorAnalysisCleared": priorAnalysisCleared ?? NSNull(),
        ]
    }

    private func expectInvalidCreatedGeometry(
        _ plan: [String: Any],
        request: ProbePlanCreateParameters,
        catalogModel: ProbeCatalogModel
    ) throws {
        let result = try decode(
            ProbePlanMutationResult.self,
            mutationPayload(status: "created", revision: 8, plan: plan)
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCreatedMutation(
                result,
                request: request,
                catalogModel: catalogModel
            )
        }
    }

    private func planDetail() -> [String: Any] {
        try! planDetail(matchingCatalog: genericCatalogModel(detailed: true))
    }

    private func surfacePlanDetail() -> [String: Any] {
        let frameId = "ATLAS_CANONICAL_AP_ML_DV_UM:test"
        let entry = TestVector3(ap: -1_000, ml: -9_400, dv: -100)
        let inward = TestVector3(ap: 0, ml: 0, dv: -1)
        let tip = entry.adding(inward.scaled(by: 3_200))
        let target = tip
        let proximalEnd = tip.subtracting(inward.scaled(by: 10_000))
        let lateral = TestVector3(ap: -1, ml: 0, dv: 0)
        let normal = TestVector3(ap: 0, ml: -1, dv: 0)
        let physicalEntry = physical(canonical: entry, voxel: [40, 4, 376])
        let physicalTip = physical(canonical: tip, voxel: [40, 132, 376])
        let physicalTarget = physicalTip
        let physicalProximalEnd = physicalOutside(canonical: proximalEnd)

        return [
            "planId": planId,
            "planVersion": 1,
            "name": "NP2003 · AP 4.2 · ML -3.7",
            "targetId": NSNull(),
            "targetLabel": NSNull(),
            "modelId": ProbePlanningContract.neuropixels2SingleShankModelId,
            "modelVersion": ProbePlanningContract.neuropixels2ModelVersion,
            "modelDisplayName":
                ProbePlanningContract.neuropixels2SingleShankDisplayName,
            "verificationStatus":
                ProbePlanningContract.sourceTranscribedReviewPendingStatus,
            "placementMode": ProbePlacementMode.atlasSurfaceAPML.rawValue,
            "inputSha256": hex("a"),
            "calibrationId": NSNull(),
            "calibrationVersion": NSNull(),
            "regionAnalysisAvailable": false,
            "regionAnalysisSha256": NSNull(),
            "sourceTarget": NSNull(),
            "manipulatorInput": NSNull(),
            "placementInput": NSNull(),
            "surfaceRelativeInput": [
                "mode": ProbePlacementMode.atlasSurfaceAPML.rawValue,
                "bregmaReference": [
                    "referenceId": ProbePlanningContract.surfaceBregmaReferenceId,
                    "atlasIdentifier": SafetyPolicy.supportedAtlasIdentifier,
                    "atlasVersion": SafetyPolicy.supportedAtlasVersion,
                    "frameId": ProbePlanningContract.atlasFrameId,
                    "componentOrder": ["AP", "DV", "ML"],
                    "units": "micrometre",
                    "apMicrometres": 5_200.0,
                    "dvMicrometres": 332.0,
                    "mlMicrometres": 5_700.0,
                    "sourceTitle": "Pinpoint Allen CCF bregma defaults",
                    "sourceUrl": "https://example.invalid/pinned-pinpoint-source",
                    "sourceRevision": "git commit pinned",
                    "sourceSha256": ProbePlanningContract.surfaceBregmaSourceSHA256,
                    "retrievedOn": "2026-07-25",
                    "limitation":
                        "Population-atlas convention; not an individual registration.",
                ],
                "insertionAPMillimetres": 4.2,
                "insertionMLMillimetres": -3.7,
                "surfaceDepthMillimetres": 3.2,
                "sagittalAngleDegrees": 0.0,
                "probeLayoutRotationDegrees": 0,
                "surfaceEntry": [
                    "atlasIdentifier": SafetyPolicy.supportedAtlasIdentifier,
                    "atlasVersion": SafetyPolicy.supportedAtlasVersion,
                    "frameId": ProbePlanningContract.atlasFrameId,
                    "componentOrder": ["AP", "DV", "ML"],
                    "units": "micrometre",
                    "apMicrometres": 1_000.0,
                    "dvMicrometres": 100.0,
                    "mlMicrometres": 9_400.0,
                ],
                "surfaceDVIndex": 4,
                "surfaceDVResolutionMicrometres": 25.0,
                "annotationSource": "brainglobe allen_mouse_25um annotation",
                "annotationSha256": hex("e"),
                "surfaceDefinitionVersion":
                    ProbePlanningContract.surfaceDefinitionVersion,
                "apSignConvention": ProbePlanningContract.surfaceAPSignConvention,
                "mlSignConvention": ProbePlanningContract.surfaceMLSignConvention,
                "depthConvention": ProbePlanningContract.surfaceDepthConvention,
                "angleConvention": ProbePlanningContract.surfaceAngleConvention,
                "layoutConvention": ProbePlanningContract.surfaceLayoutConvention,
            ],
            "placement": [
                "placementId": "55555555-5555-4555-8555-555555555555",
                "method": ProbePlanningContract.surfacePlacementMethod,
                "azimuthDegrees": 0.0,
                "elevationDegrees": -90.0,
                "insertionDepthMicrometres": 3_200.0,
                "axialRotationDegrees": -90.0,
                "angleConvention": ProbePlanningContract.angleConvention,
                "inwardDirection": direction(frameId: frameId, vector: inward),
                "localLateralDirection": direction(frameId: frameId, vector: lateral),
                "localNormalDirection": direction(frameId: frameId, vector: normal),
                "modelToPlacementUniformScale": 1.0,
                "canonicalFrame": [
                    "frameId": frameId,
                    "componentOrder": ["AP", "ML", "DV"],
                    "units": "micrometre",
                    "apPositiveDirection": "anterior",
                    "mlPositiveDirection": "right",
                    "dvPositiveDirection": "dorsal/up",
                    "entry": canonical(entry),
                    "target": canonical(target),
                    "tip": canonical(tip),
                ],
                "atlasFrame": [
                    "frameId": ProbePlanningContract.atlasFrameId,
                    "componentOrder": ["AP", "DV", "ML"],
                    "units": "micrometre",
                    "origin": "anterior/superior/right atlas corner",
                    "entry": physicalEntry,
                    "target": physicalTarget,
                    "tip": physicalTip,
                ],
            ],
            "shanks": [[
                "shankId": "shank-0",
                "entry": physicalEntry,
                "surfaceEntry": physicalEntry,
                "tip": physicalTip,
                "proximalEnd": physicalProximalEnd,
                "totalLengthMicrometres": 10_000.0,
                "widthMicrometres": 70.0,
                "thicknessMicrometres": 24.0,
                "conservativeEnvelopeRadiusMicrometres": hypot(35.0, 12.0),
                "envelopeDefinition":
                    "circumscribed-radius-of-rectangular-cross-section",
            ]],
            "recordingSites": [],
            "provenance": [
                "calibrationId": NSNull(),
                "calibrationVersion": NSNull(),
                "calibrationSha256": NSNull(),
                "atlasMetadataSha256": hex("c"),
                "projectionSha256": hex("d"),
                "planningAlgorithmVersion":
                    ProbePlanningContract.surfacePlanningAlgorithmVersion,
                "planInputSha256": hex("a"),
                "catalogVersion": ProbePlanningContract.catalogVersion,
            ],
            "warning": "Animal research planning only — independently verify geometry",
            "usableForNavigation": false,
        ]
    }

    private func basePlanDetail() -> [String: Any] {
        let frameId = "ATLAS_CANONICAL_AP_ML_DV_UM:test"
        let azimuthDegrees = -12.5
        let elevationDegrees = -80.0
        let insertionDepthMicrometres = 3_200.0
        let axialRotationDegrees = 5.0
        let azimuth = azimuthDegrees * .pi / 180
        let elevation = elevationDegrees * .pi / 180
        let horizontal = cos(elevation)
        let inward = TestVector3(
            ap: horizontal * cos(azimuth),
            ml: horizontal * sin(azimuth),
            dv: sin(elevation)
        )
        let canonicalEntry = TestVector3(ap: -1_000, ml: -2_000, dv: -100)
        let canonicalTarget = canonicalEntry.adding(inward.scaled(by: 2_400))
        let canonicalTip = canonicalEntry.adding(
            inward.scaled(by: insertionDepthMicrometres)
        )
        let reference = TestVector3(ap: 0, ml: 1, dv: 0)
        let unrotatedLateral = reference
            .subtracting(inward.scaled(by: reference.dot(inward)))
            .normalized()
        let unrotatedNormal = inward
            .scaled(by: -1)
            .cross(unrotatedLateral)
            .normalized()
        let lateral = unrotatedLateral.rotated(
            around: inward,
            degrees: axialRotationDegrees
        )
        let normal = unrotatedNormal.rotated(
            around: inward,
            degrees: axialRotationDegrees
        )
        let entry = physical(canonical: canonicalEntry, voxel: [40, 4, 80])
        let target = physical(canonical: canonicalTarget, voxel: [23, 98, 84])
        let tip = physical(canonical: canonicalTip, voxel: [18, 130, 85])
        return [
            "planId": planId,
            "planVersion": 1,
            "name": "Left VISp",
            "targetId": targetId,
            "targetLabel": "VISp implant",
            "modelId": ProbePlanningContract.genericModelId,
            "modelVersion": ProbePlanningContract.genericModelVersion,
            "modelDisplayName": ProbePlanningContract.genericDisplayName,
            "verificationStatus": "user-defined-unverified",
            "inputSha256": hex("a"),
            "calibrationId": calibrationId,
            "calibrationVersion": 1,
            "regionAnalysisAvailable": false,
            "regionAnalysisSha256": NSNull(),
            "sourceTarget": [
                "frameId": "BREGMA_RELATIVE_AP_ML_DV_MM",
                "origin": "bregma",
                "componentOrder": ["AP", "ML", "DV"],
                "units": "millimetre",
                "apMillimetres": -2.5,
                "mlMillimetres": -1.2,
                "dvMillimetres": -0.8,
            ],
            "manipulatorInput": [
                "frameId": "SUBJECT_STEREOTAXIC_AP_ML_DV_UM",
                "azimuthDegrees": azimuthDegrees,
                "elevationDegrees": elevationDegrees,
                "insertionDepthMicrometres": insertionDepthMicrometres,
                "axialRotationDegrees": axialRotationDegrees,
                "angleConvention": ProbePlanningContract.angleConvention,
            ],
            "placementInput": [
                "mode": ProbePlacementMode.stereotaxicTargetManipulator.rawValue,
                "entry": NSNull(),
                "angleFrameId": "SUBJECT_STEREOTAXIC_AP_ML_DV_UM",
                "azimuthDegrees": azimuthDegrees,
                "elevationDegrees": elevationDegrees,
                "insertionDepthMicrometres": insertionDepthMicrometres,
                "axialRotationDegrees": axialRotationDegrees,
                "angleConvention": ProbePlanningContract.angleConvention,
            ],
            "placement": [
                "placementId": "55555555-5555-4555-8555-555555555555",
                "method": "stereotaxic-target-plus-manipulator-angles",
                "azimuthDegrees": azimuthDegrees,
                "elevationDegrees": elevationDegrees,
                "insertionDepthMicrometres": insertionDepthMicrometres,
                "axialRotationDegrees": axialRotationDegrees,
                "angleConvention": ProbePlanningContract.angleConvention,
                "inwardDirection": direction(frameId: frameId, vector: inward),
                "localLateralDirection": direction(
                    frameId: frameId,
                    vector: lateral
                ),
                "localNormalDirection": direction(
                    frameId: frameId,
                    vector: normal
                ),
                "modelToPlacementUniformScale": 1.0,
                "canonicalFrame": [
                    "frameId": frameId,
                    "componentOrder": ["AP", "ML", "DV"],
                    "units": "micrometre",
                    "apPositiveDirection": "anterior",
                    "mlPositiveDirection": "right",
                    "dvPositiveDirection": "dorsal/up",
                    "entry": canonical(canonicalEntry),
                    "target": canonical(canonicalTarget),
                    "tip": canonical(canonicalTip),
                ],
                "atlasFrame": [
                    "frameId": ProbePlanningContract.atlasFrameId,
                    "componentOrder": ["AP", "DV", "ML"],
                    "units": "micrometre",
                    "origin": "anterior/superior/right atlas corner",
                    "entry": entry,
                    "target": target,
                    "tip": tip,
                ],
            ],
            "shanks": [],
            "recordingSites": [],
            "provenance": [
                "calibrationId": calibrationId,
                "calibrationVersion": 1,
                "calibrationSha256": hex("b"),
                "atlasMetadataSha256": hex("c"),
                "projectionSha256": hex("d"),
                "planningAlgorithmVersion": ProbePlanningContract.planningAlgorithmVersion,
                "planInputSha256": hex("a"),
                "catalogVersion": ProbePlanningContract.catalogVersion,
            ],
            "warning": "Animal research planning only — independently verify geometry",
            "usableForNavigation": false,
        ]
    }

    private func planDetail(
        matchingCatalog model: [String: Any]
    ) throws -> [String: Any] {
        var plan = basePlanDetail()
        let modelId = try #require(model["modelId"] as? String)
        let modelVersion = try #require(model["modelVersion"] as? String)
        let displayName = try #require(model["displayName"] as? String)
        let verificationStatus = try #require(model["verificationStatus"] as? String)
        let catalogShanks = try #require(model["shanks"] as? [[String: Any]])
        let placement = try #require(plan["placement"] as? [String: Any])
        let canonicalFrame = try #require(
            placement["canonicalFrame"] as? [String: Any]
        )
        let canonicalEntry = try testVector(
            canonicalFrame["entry"],
            label: "canonical entry"
        )
        let canonicalTip = try testVector(
            canonicalFrame["tip"],
            label: "canonical tip"
        )
        let inward = try testVector(
            placement["inwardDirection"],
            label: "inward direction"
        )
        let axialTowardBase = inward.scaled(by: -1)
        let lateral = try testVector(
            placement["localLateralDirection"],
            label: "local lateral direction"
        )
        let normal = try testVector(
            placement["localNormalDirection"],
            label: "local normal direction"
        )
        let scale = try #require(
            placement["modelToPlacementUniformScale"] as? Double
        )

        plan["modelId"] = modelId
        plan["modelVersion"] = modelVersion
        plan["modelDisplayName"] = displayName
        plan["verificationStatus"] = verificationStatus

        var placedShanks: [[String: Any]] = []
        var placedSites: [[String: Any]] = []
        for catalogShank in catalogShanks {
            let shankId = try #require(catalogShank["shankId"] as? String)
            let width = try #require(catalogShank["widthMicrometres"] as? Double)
            let thickness = try #require(
                catalogShank["thicknessMicrometres"] as? Double
            )
            let centerLateral = try #require(
                catalogShank["centerLateralMicrometres"] as? Double
            )
            let centerNormal = try #require(
                catalogShank["centerNormalMicrometres"] as? Double
            )
            let shankOffset = lateral
                .scaled(by: centerLateral * scale)
                .adding(normal.scaled(by: centerNormal * scale))
            let placedEntry = physical(
                canonical: canonicalEntry.adding(shankOffset),
                voxel: [1, 1, 1]
            )
            let placedTip = physical(
                canonical: canonicalTip.adding(shankOffset),
                voxel: [1, 1, 1]
            )
            let scaledWidth = width * scale
            let scaledThickness = thickness * scale
            placedShanks.append([
                "shankId": shankId,
                "entry": placedEntry,
                "tip": placedTip,
                "widthMicrometres": scaledWidth,
                "thicknessMicrometres": scaledThickness,
                "conservativeEnvelopeRadiusMicrometres":
                    hypot(scaledWidth / 2, scaledThickness / 2),
                "envelopeDefinition":
                    "circumscribed-radius-of-rectangular-cross-section",
            ])

            let catalogSites = try #require(
                catalogShank["sites"] as? [[String: Any]]
            )
            for catalogSite in catalogSites {
                let axial = try #require(
                    catalogSite["axialFromTipMicrometres"] as? Double
                )
                let siteLateral = try #require(
                    catalogSite["lateralMicrometres"] as? Double
                )
                let siteNormal = try #require(
                    catalogSite["normalMicrometres"] as? Double
                )
                let placedPoint = canonicalTip
                    .adding(axialTowardBase.scaled(by: axial * scale))
                    .adding(
                        lateral.scaled(
                            by: (centerLateral + siteLateral) * scale
                        )
                    )
                    .adding(
                        normal.scaled(
                            by: (centerNormal + siteNormal) * scale
                        )
                    )
                placedSites.append([
                    "shankId": shankId,
                    "siteId": try #require(catalogSite["siteId"] as? String),
                    "role": try #require(catalogSite["role"] as? String),
                    "bank": catalogSite["bank"] ?? NSNull(),
                    "point": physical(
                        canonical: placedPoint,
                        voxel: [1, 1, 1]
                    ),
                ])
            }
        }
        plan["shanks"] = placedShanks
        plan["recordingSites"] = placedSites
        return plan
    }

    private func decodedCatalogModel(
        _ model: [String: Any]
    ) throws -> ProbeCatalogModel {
        let modelId = try #require(model["modelId"] as? String)
        let modelVersion = try #require(model["modelVersion"] as? String)
        let result = try decode(
            ProbeCatalogGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "model": model,
            ]
        )
        try ProbePlanningValidator.validateCatalogGet(
            result,
            modelId: modelId,
            modelVersion: modelVersion
        )
        return result.model
    }

    private func regionBundle() -> [String: Any] {
        let entryPoint = regionPoint(ap: 25, ml: 25, dv: 25)
        let exitPoint = regionPoint(ap: 50, ml: 75, dv: 100)
        return [
            "analysisId": "66666666-6666-4666-8666-666666666666",
            "planId": planId,
            "planVersion": 1,
            "planInputSha256": hex("a"),
            "algorithmVersion": ProbePlanningContract.regionAlgorithmVersion,
            "analysisSha256": hex("e"),
            "computedAt": "2026-07-22T16:00:00Z",
            "usableForNavigation": false,
            "shanks": [[
                "analysisId": "77777777-7777-4777-8777-777777777777",
                "shankId": "test-shank-1",
                "totalPathLengthMicrometres": 100.0,
                "clippedPathLengthMicrometres": 100.0,
                "outsideAtlasPathLengthMicrometres": 0.0,
                "intersectsAtlas": true,
                "segments": [[
                    "structureId": 385,
                    "acronym": "VISp",
                    "name": "Primary visual area",
                    "hemisphere": "left",
                    "location": "brain",
                    "entryDepthMicrometres": 0.0,
                    "exitDepthMicrometres": 100.0,
                    "lengthMicrometres": 100.0,
                    "entryPoint": entryPoint,
                    "exitPoint": exitPoint,
                    "voxelCount": 4,
                    "rgb": [8, 133, 140],
                ]],
                "recordingSiteAssignments": [[
                    "siteId": "test-site-01",
                    "structureId": 385,
                    "acronym": "VISp",
                    "name": "Primary visual area",
                    "location": "brain",
                    "insideAtlas": true,
                    "insideBrain": true,
                    "point": exitPoint,
                    "voxelIndex": ["ap": 2, "dv": 4, "ml": 3],
                ]],
                "provenance": [
                    "atlasIdentifier": SafetyPolicy.supportedAtlasIdentifier,
                    "atlasVersion": SafetyPolicy.supportedAtlasVersion,
                    "atlasMetadataSha256": hex("c"),
                    "annotationSha256": hex("1"),
                    "annotationVersion": "annotation/ccf_2017",
                    "algorithmVersion": "exact-grid-traversal-v1",
                    "inputDigest": hex("2"),
                    "tieBreakRule": "AP then DV then ML",
                ],
            ]],
        ]
    }

    private func neuropixels2CatalogModel(
        fourShank: Bool,
        quadBase: Bool = false,
        detailed: Bool
    ) -> [String: Any] {
        precondition(fourShank || !quadBase)
        let shankCount = fourShank ? 4 : 1
        var model: [String: Any] = [
            "modelId": quadBase
                ? ProbePlanningContract.neuropixels2QuadBaseFourShankModelId
                : fourShank
                    ? ProbePlanningContract.neuropixels2StandardFourShankModelId
                    : ProbePlanningContract.neuropixels2SingleShankModelId,
            "modelVersion": ProbePlanningContract.neuropixels2ModelVersion,
            "displayName": quadBase
                ? ProbePlanningContract.neuropixels2QuadBaseFourShankDisplayName
                : fourShank
                    ? ProbePlanningContract.neuropixels2StandardFourShankDisplayName
                    : ProbePlanningContract.neuropixels2SingleShankDisplayName,
            "manufacturer": "imec",
            "productCode": quadBase
                ? ProbePlanningContract.neuropixels2QuadBaseFourShankProductCode
                : fourShank
                    ? ProbePlanningContract.neuropixels2StandardFourShankProductCode
                    : ProbePlanningContract.neuropixels2SingleShankProductCode,
            "hardwareRevision": NSNull(),
            "verificationStatus": ProbePlanningContract.sourceTranscribedReviewPendingStatus,
            "verifiedDeviceLabelPermitted": false,
            "shankCount": shankCount,
            "siteCount": shankCount * 1_280,
            "units": "micrometre",
            "warning": quadBase
                ? ProbePlanningContract.legacySourceTranscribedReviewPendingWarning
                : ProbePlanningContract.sourceTranscribedReviewPendingWarning,
        ]
        guard detailed else { return model }

        model["geometryNotes"] = quadBase
            ? "NP2 Quad Base four-shank exact implantable geometry; "
                + "1536 simultaneously configurable channels"
            : fourShank
                ? "NP2 standard four-shank exact implantable geometry; "
                    + "384 simultaneously configurable channels"
                : "NP2 single-shank exact implantable geometry; "
                    + "384 simultaneously configurable channels"
        model["reviewNotes"] =
            "Independent human transcription review remains pending"
        model["completeGeometryTranscribed"] = true
        model["independentTranscriptionReviewCompleted"] = false
        model["transcribedBy"] = "Brain3D automated source transcription"
        model["independentlyReviewedBy"] = NSNull()
        model["coordinateOrigin"] = ProbePlanningContract.coordinateOrigin
        model["localAxisDefinition"] = ProbePlanningContract.localAxisDefinition
        model["insertionAxisDefinition"] = ProbePlanningContract.insertionAxisDefinition
        model["primarySources"] = neuropixels2Sources(includeQuadBase: quadBase)
        model["shanks"] = (0 ..< shankCount).map(neuropixels2Shank)
        return model
    }

    private func neuropixels2Shank(_ shankIndex: Int) -> [String: Any] {
        let sites: [[String: Any]] = (0 ..< 1_280).map { siteIndex in
            let siteId = "shank-\(shankIndex)-electrode-"
                + zeroPaddedDecimal(siteIndex, width: 4)
            let axial = Double(206 + 15 * (siteIndex / 2))
            let lateral = Double(-8 + 32 * (siteIndex % 2))
            return [
                "siteId": siteId,
                "role": "recording",
                "bank": "virtual-bank-\(siteIndex / 384)",
                "axialFromTipMicrometres": axial,
                "lateralMicrometres": lateral,
                "normalMicrometres": 0.0,
            ]
        }
        let shank: [String: Any] = [
            "shankId": "shank-\(shankIndex)",
            "lengthMicrometres": 10_000.0,
            "widthMicrometres": 70.0,
            "thicknessMicrometres": 24.0,
            "tipGeometry": "chisel",
            "tipLengthMicrometres": 175.0,
            "tipGeometryNotes":
                "The official imec specifications report a 175 micrometre physical "
                + "chisel tip at approximately 20 degrees. ProbeTable and SpikeGLX "
                + "separately report 206 micrometres from the physical tip to the "
                + "center of the lowest electrode row.",
            "centerLateralMicrometres": Double(shankIndex * 250),
            "centerNormalMicrometres": 0.0,
            "siteCount": 1_280,
            "sites": sites,
        ]
        return shank
    }

    private func neuropixels2Sources(
        includeQuadBase: Bool
    ) -> [[String: Any]] {
        var sources: [[String: Any]] = [
            [
                "title": "Neuropixels 2.0 small-animal probe data sheet",
                "sourceUrl": "https://www.neuropixels.org/_files/ugd/"
                    + "328966_2b39661f072d405b8d284c3c73588bc6.pdf",
                "documentRevision": "No printed revision identifier; PDF metadata "
                    + "modification date 2024-09-18",
                "retrievedOn": "2026-07-23",
                "sha256": ProbePlanningContract.neuropixels2SpecSHA256,
                "citation": "imec, Neuropixels 2.0 data sheet, pp. 1-3: one or four "
                    + "10 mm by 70 micrometre by 24 micrometre shanks; 1280 sites "
                    + "per shank; 15 micrometre axial and 32 micrometre lateral "
                    + "pitches; 175 micrometre chisel tip; and "
                    + "NP2003/NP2004/NP2013/NP2014 order codes.",
            ],
            [
                "title": "Neuropixels 2.0 User Manual V1.0.6 archive",
                "sourceUrl": "https://www.neuropixels.org/_files/archives/"
                    + "328966_021470f37e3a4a4a88a256ab11639765.zip"
                    + "?dn=Neuropixels_2-0_User_Manual_V1-0-6.zip",
                "documentRevision": "Neuropixels 2.0 User Manual V1.0.6",
                "retrievedOn": "2026-07-23",
                "sha256": ProbePlanningContract.neuropixels2UserManualZipSHA256,
                "citation": "imec, Neuropixels 2.0 User Manual V1.0.6, pp. 14 and "
                    + "41-43: physical dimensions, two-column site layout, 1280 "
                    + "electrode identities per shank, virtual banks, and "
                    + "left-to-right shank numbering at 250 micrometre pitch.",
            ],
            [
                "title": "Neuropixels 2.0 Electrode-Channel Mapping workbook",
                "sourceUrl": "https://www.neuropixels.org/_files/ugd/"
                    + "328966_43eea6555fa94a5bb1ddb51f00696fc3.xlsx"
                    + "?dn=Neuropix_2_0_Electrode-Channel-mapping.xlsx",
                "documentRevision": "Official workbook retrieved 2026-07-23; sheets "
                    + "for single shank and multi-shank shanks 0-3",
                "retrievedOn": "2026-07-23",
                "sha256": ProbePlanningContract.neuropixels2ElectrodeMappingSHA256,
                "citation": "imec, Neuropixels 2.0 Electrode-Channel Mapping: "
                    + "electrode identities 0-1279 and bank/channel connectivity "
                    + "for the single- and four-shank products.",
            ],
            [
                "title": "ProbeTable 1.8 probe_features.json",
                "sourceUrl": "https://raw.githubusercontent.com/billkarsh/ProbeTable/"
                    + "207f7bf424b0fa26f271700b970e27a58a9a1111/Tables/"
                    + "probe_features.json",
                "documentRevision": "table_version 1.8; git commit "
                    + "207f7bf424b0fa26f271700b970e27a58a9a1111",
                "retrievedOn": "2026-07-23",
                "sha256": ProbePlanningContract.probeTableSHA256,
                "citation": "Bill Karsh, ProbeTable entries NP2003, NP2004, NP2013, "
                    + "NP2014, NP2020, and NP2021: shank/site counts, 206 "
                    + "micrometre tip-to-lowest-row-center distance, pitches, "
                    + "left-edge site offset, and 250 micrometre shank pitch.",
            ],
            [
                "title": "SpikeGLX Neuropixels geometry implementation",
                "sourceUrl": "https://raw.githubusercontent.com/billkarsh/SpikeGLX/"
                    + "d67bee45fa2635873456eb5d3f5e5a051690e64f/Src-imro/IMROTbl.cpp",
                "documentRevision": "git commit "
                    + "d67bee45fa2635873456eb5d3f5e5a051690e64f",
                "retrievedOn": "2026-07-23",
                "sha256": ProbePlanningContract.spikeGLXGeometrySHA256,
                "citation": "SpikeGLX IMROTbl.cpp cases NP2003/NP2004, "
                    + "NP2013/NP2014, and NP2020/NP2021: 206 micrometre tip "
                    + "offset, x0=27, lateral pitch=32, axial pitch=15, shank "
                    + "width=70, and shank pitch=250.",
            ],
        ]
        if includeQuadBase {
            sources.append([
                "title": "Neuropixels 2.0 Quad Base multishank data sheet",
                "sourceUrl": "https://www.neuropixels.org/_files/ugd/"
                    + "328966_4e39ab2e46424dc9b3efa446d286ab0f.pdf",
                "documentRevision": "No printed revision identifier; PDF metadata "
                    + "modification date 2025-06-16",
                "retrievedOn": "2026-07-23",
                "sha256": ProbePlanningContract.neuropixels2QuadBaseSpecSHA256,
                "citation": "imec, Neuropixels 2.0 Quad Base data sheet, pp. 1-3: "
                    + "four 10 mm shanks at 250 micrometre pitch, 5120 sites, "
                    + "70 by 24 micrometre cross-section, 175 micrometre chisel "
                    + "tip, and NP2020/NP2021 order codes.",
            ])
        }
        return sources
    }

    private func expectInvalidNeuropixels2Detail(
        _ model: [String: Any],
        fourShank: Bool,
        quadBase: Bool = false
    ) throws {
        let result = try decode(
            ProbeCatalogGetResult.self,
            [
                "protocolVersion": 1,
                "status": "found",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "model": model,
            ]
        )
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateCatalogGet(
                result,
                modelId: quadBase
                    ? ProbePlanningContract.neuropixels2QuadBaseFourShankModelId
                    : fourShank
                        ? ProbePlanningContract.neuropixels2StandardFourShankModelId
                        : ProbePlanningContract.neuropixels2SingleShankModelId,
                modelVersion: ProbePlanningContract.neuropixels2ModelVersion
            )
        }
    }

    private func neuropixelsCatalogModel(detailed: Bool) -> [String: Any] {
        var model: [String: Any] = [
            "modelId": ProbePlanningContract.neuropixelsModelId,
            "modelVersion": ProbePlanningContract.neuropixelsModelVersion,
            "displayName": ProbePlanningContract.neuropixelsDisplayName,
            "manufacturer": "imec",
            "productCode": "PRB_1_4_0480_1",
            "hardwareRevision": NSNull(),
            "verificationStatus": ProbePlanningContract.sourceTranscribedReviewPendingStatus,
            "verifiedDeviceLabelPermitted": false,
            "shankCount": 1,
            "siteCount": 960,
            "units": "micrometre",
            "warning": ProbePlanningContract.legacySourceTranscribedReviewPendingWarning,
        ]
        if detailed {
            model["geometryNotes"] = "Complete NP1000 row-major site transcription"
            model["reviewNotes"] = "Independent human transcription review remains pending"
            model["completeGeometryTranscribed"] = true
            model["independentTranscriptionReviewCompleted"] = false
            model["transcribedBy"] = "Brain3D automated source transcription"
            model["independentlyReviewedBy"] = NSNull()
            model["coordinateOrigin"] = ProbePlanningContract.coordinateOrigin
            model["localAxisDefinition"] = ProbePlanningContract.localAxisDefinition
            model["insertionAxisDefinition"] = ProbePlanningContract.insertionAxisDefinition
            model["primarySources"] = neuropixelsSources()
            model["shanks"] = [[
                "shankId": "shank-0",
                "lengthMicrometres": 10_000.0,
                "widthMicrometres": 70.0,
                "thicknessMicrometres": 24.0,
                "tipGeometry": "chisel",
                "tipLengthMicrometres": 175.0,
                "tipGeometryNotes":
                    "175 micrometre physical chisel; 209 micrometres to lowest row center",
                "centerLateralMicrometres": 0.0,
                "centerNormalMicrometres": 0.0,
                "siteCount": 960,
                "sites": (0 ..< 960).map { index in
                    let row = index / 2
                    let column = index % 2
                    let lateral: Double
                    if row.isMultiple(of: 2) {
                        lateral = column == 0 ? -8 : 24
                    } else {
                        lateral = column == 0 ? -24 : 8
                    }
                    return [
                        "siteId": "electrode-" + zeroPaddedDecimal(index, width: 3),
                        "role": [191, 575, 959].contains(index) ? "reference" : "recording",
                        "bank": "bank-\(index / 384)",
                        "axialFromTipMicrometres": Double(209 + 20 * row),
                        "lateralMicrometres": lateral,
                        "normalMicrometres": 0.0,
                    ] as [String: Any]
                },
            ]]
        }
        return model
    }

    private func neuropixelsSources() -> [[String: Any]] {
        [
            [
                "title": "Neuropixels 1.0 manufacturer specification",
                "sourceUrl": "https://www.neuropixels.org/_files/ugd/"
                    + "328966_c5e4d31e8a974962b5eb8ec975408c9f.pdf",
                "documentRevision": "PDF metadata creation date 2023-10-20",
                "retrievedOn": "2026-07-22",
                "sha256": ProbePlanningContract.manufacturerSpecSHA256,
                "citation": "imec NP1 dimensions and order code",
            ],
            [
                "title": "ProbeTable 1.8 probe_features.json",
                "sourceUrl": "https://raw.githubusercontent.com/billkarsh/ProbeTable/"
                    + "207f7bf424b0fa26f271700b970e27a58a9a1111/Tables/"
                    + "probe_features.json",
                "documentRevision": "table_version 1.8; pinned git commit",
                "retrievedOn": "2026-07-22",
                "sha256": ProbePlanningContract.probeTableSHA256,
                "citation": "NP1000 rows, pitches, cross-section, and banks",
            ],
            [
                "title": "SpikeGLX NP1000 geometry implementation",
                "sourceUrl": "https://raw.githubusercontent.com/billkarsh/SpikeGLX/"
                    + "d67bee45fa2635873456eb5d3f5e5a051690e64f/Src-imro/IMROTbl.cpp",
                "documentRevision": "Pinned git commit",
                "retrievedOn": "2026-07-22",
                "sha256": ProbePlanningContract.spikeGLXGeometrySHA256,
                "citation": "NP1000 tip offset and electrode-center formula",
            ],
            [
                "title": "SpikeGLX Metadata Help",
                "sourceUrl": "https://raw.githubusercontent.com/billkarsh/SpikeGLX/"
                    + "d67bee45fa2635873456eb5d3f5e5a051690e64f/Markdown/"
                    + "Metadata_Help.md",
                "documentRevision": "Pinned git commit",
                "retrievedOn": "2026-07-22",
                "sha256": ProbePlanningContract.spikeGLXMetadataSHA256,
                "citation": "Geometry coordinate definitions",
            ],
        ]
    }

    private func genericCatalogModel(detailed: Bool) -> [String: Any] {
        var model: [String: Any] = [
            "modelId": ProbePlanningContract.genericModelId,
            "modelVersion": ProbePlanningContract.genericModelVersion,
            "displayName": ProbePlanningContract.genericDisplayName,
            "manufacturer": NSNull(),
            "productCode": NSNull(),
            "hardwareRevision": NSNull(),
            "verificationStatus": "user-defined-unverified",
            "verifiedDeviceLabelPermitted": false,
            "shankCount": 1,
            "siteCount": 16,
            "units": "micrometre",
            "warning": ProbePlanningContract.genericWarning,
        ]
        if detailed {
            model["geometryNotes"] = "Synthetic geometry for software tests only"
            model["reviewNotes"] = "Unverified"
            model["completeGeometryTranscribed"] = false
            model["independentTranscriptionReviewCompleted"] = false
            model["transcribedBy"] = NSNull()
            model["independentlyReviewedBy"] = NSNull()
            model["coordinateOrigin"] = ProbePlanningContract.coordinateOrigin
            model["localAxisDefinition"] = ProbePlanningContract.localAxisDefinition
            model["insertionAxisDefinition"] = ProbePlanningContract.insertionAxisDefinition
            model["primarySources"] = []
            model["shanks"] = [[
                "shankId": "test-shank-1",
                "lengthMicrometres": 10_000.0,
                "widthMicrometres": 70.0,
                "thicknessMicrometres": 20.0,
                "tipGeometry": "triangular",
                "tipLengthMicrometres": 200.0,
                "tipGeometryNotes": "Synthetic triangular tip for software testing",
                "centerLateralMicrometres": 0.0,
                "centerNormalMicrometres": 0.0,
                "siteCount": 16,
                "sites": (1 ... 16).map { index in
                    [
                        "siteId": "test-site-" + zeroPaddedDecimal(index, width: 2),
                        "role": "recording",
                        "bank": "software-test",
                        "axialFromTipMicrometres": Double(index) * 250,
                        "lateralMicrometres": 0.0,
                        "normalMicrometres": 0.0,
                    ] as [String: Any]
                },
            ]]
        }
        return model
    }

    private func probeCreate(
        modelId: String,
        modelVersion: String,
        acknowledged: Bool
    ) -> ProbePlanCreateParameters {
        ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: modelId,
            modelVersion: modelVersion,
            name: "Test",
            azimuthDegrees: 0,
            elevationDegrees: -90,
            insertionDepthMicrometres: 1_000,
            axialRotationDegrees: 0,
            customGeometryAcknowledged: acknowledged
        )
    }

    private func matchingCreateRequest(
        for model: ProbeCatalogModel
    ) -> ProbePlanCreateParameters {
        ProbePlanCreateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            targetId: targetId,
            modelId: model.modelId,
            modelVersion: model.modelVersion,
            name: "Left VISp",
            azimuthDegrees: -12.5,
            elevationDegrees: -80,
            insertionDepthMicrometres: 3_200,
            axialRotationDegrees: 5,
            customGeometryAcknowledged: true
        )
    }

    private func matchingUpdateRequest(
        for model: ProbeCatalogModel
    ) -> ProbePlanUpdateParameters {
        ProbePlanUpdateParameters(
            projectId: projectId,
            expectedProjectRevision: 7,
            planId: planId,
            expectedPlanInputSha256: hex("a"),
            targetId: targetId,
            modelId: model.modelId,
            modelVersion: model.modelVersion,
            name: "Left VISp",
            azimuthDegrees: -12.5,
            elevationDegrees: -80,
            insertionDepthMicrometres: 3_200,
            axialRotationDegrees: 5,
            customGeometryAcknowledged: true
        )
    }

    private func physical(ap: Double, dv: Double, ml: Double, voxel: [Int]) -> [String: Any] {
        [
            "apMicrometres": ap,
            "dvMicrometres": dv,
            "mlMicrometres": ml,
            "insideAtlas": true,
            "voxelIndex": ["ap": voxel[0], "dv": voxel[1], "ml": voxel[2]],
        ]
    }

    private func physical(
        canonical point: TestVector3,
        voxel: [Int]
    ) -> [String: Any] {
        physical(ap: -point.ap, dv: -point.dv, ml: -point.ml, voxel: voxel)
    }

    private func physicalOutside(
        canonical point: TestVector3
    ) -> [String: Any] {
        [
            "apMicrometres": -point.ap,
            "dvMicrometres": -point.dv,
            "mlMicrometres": -point.ml,
            "insideAtlas": false,
            "voxelIndex": NSNull(),
        ]
    }

    private func canonical(ap: Double, ml: Double, dv: Double) -> [String: Any] {
        ["apMicrometres": ap, "mlMicrometres": ml, "dvMicrometres": dv]
    }

    private func canonical(_ point: TestVector3) -> [String: Any] {
        canonical(ap: point.ap, ml: point.ml, dv: point.dv)
    }

    private func direction(
        frameId: String,
        vector: TestVector3
    ) -> [String: Any] {
        [
            "frameId": frameId,
            "componentOrder": ["AP", "ML", "DV"],
            "units": "dimensionless",
            "ap": vector.ap,
            "ml": vector.ml,
            "dv": vector.dv,
        ]
    }

    private func testVector(
        _ raw: Any?,
        label: String
    ) throws -> TestVector3 {
        let payload = try #require(raw as? [String: Any], "\(label) is not an object")
        return TestVector3(
            ap: try #require(
                (payload["ap"] ?? payload["apMicrometres"]) as? Double
            ),
            ml: try #require(
                (payload["ml"] ?? payload["mlMicrometres"]) as? Double
            ),
            dv: try #require(
                (payload["dv"] ?? payload["dvMicrometres"]) as? Double
            )
        )
    }

    private func regionPoint(ap: Double, ml: Double, dv: Double) -> [String: Any] {
        [
            "frameId": ProbePlanningContract.regionFrameId,
            "componentOrder": ["AP", "ML", "DV"],
            "units": "micrometre",
            "apMicrometres": ap,
            "mlMicrometres": ml,
            "dvMicrometres": dv,
        ]
    }

    private func hex(_ character: Character) -> String {
        String(repeating: String(character), count: 64)
    }

    private func zeroPaddedDecimal(_ value: Int, width: Int) -> String {
        let text = String(value)
        return String(repeating: "0", count: max(0, width - text.count)) + text
    }

    private func decode<T: Decodable>(_ type: T.Type, _ object: [String: Any]) throws -> T {
        try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: object))
    }

    private func keys<T: Encodable>(_ value: T) throws -> Set<String> {
        let data = try JSONEncoder().encode(value)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return Set(object.keys)
    }
}
