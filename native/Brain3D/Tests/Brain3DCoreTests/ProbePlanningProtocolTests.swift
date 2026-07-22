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
            "modelId", "modelVersion", "name", "azimuthDegrees", "elevationDegrees",
            "insertionDepthMicrometres", "axialRotationDegrees",
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
            "azimuthDegrees", "elevationDegrees", "insertionDepthMicrometres",
            "axialRotationDegrees", "customGeometryAcknowledged",
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
            planId: planId,
            expectedPlanInputSha256: hex("b"),
            format: .csv
        )) == [
            "protocolVersion", "projectId", "planId", "expectedPlanInputSha256", "format",
        ])
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

    @Test("Read-only export verifies identity, MIME type, and content digest")
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
        let payload: [String: Any] = [
            "protocolVersion": 1,
            "status": "exportedReadOnly",
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
        try ProbePlanningValidator.validateExport(
            result,
            projectId: projectId,
            plan: plan,
            analysis: analysis,
            format: .csv,
            projectRevision: 8
        )

        var changed = payload
        changed["contentSha256"] = hex("f")
        let corrupt = try decode(ProbeRegionExportResult.self, changed)
        #expect(throws: ProbePlanningValidationError.self) {
            try ProbePlanningValidator.validateExport(
                corrupt,
                projectId: projectId,
                plan: plan,
                analysis: analysis,
                format: .csv,
                projectRevision: 8
            )
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
