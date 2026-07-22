import Brain3DCore
import CryptoKit
import Foundation
import Testing

@Suite("Probe catalog, plan, and exact region bridge")
struct ProbePlanningProtocolTests {
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

    @Test("Mutation responses must acknowledge the submitted plan and placement")
    func mutationResponseBindsRequest() throws {
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
        try ProbePlanningValidator.validateCreatedMutation(created, request: create)

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
                request: differentPlacement
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
            try ProbePlanningValidator.validateUpdatedMutation(wrongUpdate, request: update)
        }
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
        ])
        #expect(ProbePlacementMode.entryAndTarget.requiresEntryCoordinates)
        #expect(!ProbePlacementMode.entryAndTarget.requiresAnglesAndDepth)
        #expect(ProbePlacementMode.entryAnglesDepth.requiresEntryCoordinates)
        #expect(ProbePlacementMode.entryAnglesDepth.requiresAnglesAndDepth)
        #expect(!ProbePlacementMode.targetAnglesDepth.requiresEntryCoordinates)
        #expect(ProbePlacementMode.targetAnglesDepth.requiresAnglesAndDepth)

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

    @Test("Catalog keeps NP1 first, test fixture second, and selects by exact identity")
    func catalogOrderAndSelection() throws {
        let list = try decode(
            ProbeCatalogListResult.self,
            [
                "protocolVersion": 1,
                "status": "listed",
                "catalogVersion": ProbePlanningContract.catalogVersion,
                "modelCount": 2,
                "models": [
                    neuropixelsCatalogModel(detailed: false),
                    genericCatalogModel(detailed: false),
                ],
            ]
        )
        try ProbePlanningValidator.validateCatalogList(list)
        #expect(list.models[0].modelId == ProbePlanningContract.neuropixelsModelId)
        #expect(list.models[1].modelId == ProbePlanningContract.genericModelId)

        let reverseOrder = Array(list.models.reversed())
        let defaultModel = ProbePlanningContract.preferredCatalogModel(
            in: reverseOrder,
            preservingIdentity: nil
        )
        #expect(defaultModel?.modelId == ProbePlanningContract.neuropixelsModelId)
        let preservedTestFixture = ProbePlanningContract.preferredCatalogModel(
            in: reverseOrder,
            preservingIdentity: list.models[1].id
        )
        #expect(preservedTestFixture?.modelId == ProbePlanningContract.genericModelId)
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
            "angleFrameId": "SUBJECT_SKULL_AP_ML_DV_UM",
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
            targetId: result.plan.targetId,
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
        let digest = SHA256.hash(data: Data(content.utf8)).map {
            String(format: "%02x", $0)
        }.joined()
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

    private func planDetail() -> [String: Any] {
        let entry = physical(ap: 25, dv: 25, ml: 25, voxel: [1, 1, 1])
        let target = physical(ap: 50, dv: 100, ml: 75, voxel: [2, 4, 3])
        let tip = physical(ap: 75, dv: 200, ml: 125, voxel: [3, 8, 5])
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
                "azimuthDegrees": -12.5,
                "elevationDegrees": -80.0,
                "insertionDepthMicrometres": 3_200.0,
                "axialRotationDegrees": 5.0,
                "angleConvention": ProbePlanningContract.angleConvention,
            ],
            "placementInput": [
                "mode": ProbePlacementMode.stereotaxicTargetManipulator.rawValue,
                "entry": NSNull(),
                "angleFrameId": "SUBJECT_STEREOTAXIC_AP_ML_DV_UM",
                "azimuthDegrees": -12.5,
                "elevationDegrees": -80.0,
                "insertionDepthMicrometres": 3_200.0,
                "axialRotationDegrees": 5.0,
                "angleConvention": ProbePlanningContract.angleConvention,
            ],
            "placement": [
                "placementId": "55555555-5555-4555-8555-555555555555",
                "method": "stereotaxic-target-plus-manipulator-angles",
                "azimuthDegrees": -12.5,
                "elevationDegrees": -80.0,
                "insertionDepthMicrometres": 3_200.0,
                "axialRotationDegrees": 5.0,
                "angleConvention": ProbePlanningContract.angleConvention,
                "canonicalFrame": [
                    "frameId": "SUBJECT_SKULL_AP_ML_DV_UM",
                    "componentOrder": ["AP", "ML", "DV"],
                    "units": "micrometre",
                    "apPositiveDirection": "anterior",
                    "mlPositiveDirection": "right",
                    "dvPositiveDirection": "dorsal/up",
                    "entry": canonical(ap: 0, ml: 0, dv: 0),
                    "target": canonical(ap: -2_500, ml: -1_200, dv: -800),
                    "tip": canonical(ap: -2_600, ml: -1_250, dv: -3_100),
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
            "shanks": [[
                "shankId": "shank-1",
                "entry": entry,
                "tip": tip,
                "widthMicrometres": 70.0,
                "thicknessMicrometres": 20.0,
                "conservativeEnvelopeRadiusMicrometres": 36.4,
                "envelopeDefinition": "half diagonal of rectangular shank cross-section",
            ]],
            "recordingSites": [[
                "shankId": "shank-1",
                "siteId": "test-site-01",
                "role": "recording",
                "bank": NSNull(),
                "point": target,
            ]],
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
                "shankId": "shank-1",
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
            "warning": ProbePlanningContract.sourceTranscribedReviewPendingWarning,
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
                        "siteId": String(format: "electrode-%03d", index),
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
                        "siteId": String(format: "test-site-%02d", index),
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

    private func physical(ap: Double, dv: Double, ml: Double, voxel: [Int]) -> [String: Any] {
        [
            "apMicrometres": ap,
            "dvMicrometres": dv,
            "mlMicrometres": ml,
            "insideAtlas": true,
            "voxelIndex": ["ap": voxel[0], "dv": voxel[1], "ml": voxel[2]],
        ]
    }

    private func canonical(ap: Double, ml: Double, dv: Double) -> [String: Any] {
        ["apMicrometres": ap, "mlMicrometres": ml, "dvMicrometres": dv]
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

    private func decode<T: Decodable>(_ type: T.Type, _ object: [String: Any]) throws -> T {
        try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: object))
    }

    private func keys<T: Encodable>(_ value: T) throws -> Set<String> {
        let data = try JSONEncoder().encode(value)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return Set(object.keys)
    }
}
