import Brain3DCore
import CoreGraphics
import Foundation
import ImageIO
import Testing

@Suite("Published reference density bridge")
struct ReferenceDensityProtocolTests {
    @Test("Preparation and overlay requests use the exact protocol-v1 fields")
    func requestShapes() throws {
        let prepareData = try JSONEncoder().encode(
            ReferenceDensityPrepareParameters(downloadIfMissing: true)
        )
        let prepare = try #require(
            JSONSerialization.jsonObject(with: prepareData) as? [String: Any]
        )
        #expect(Set(prepare.keys) == Set(["protocolVersion", "downloadIfMissing"]))
        #expect(prepare["protocolVersion"] as? Int == 1)
        #expect(prepare["downloadIfMissing"] as? Bool == true)

        let overlayData = try JSONEncoder().encode(ReferenceDensityOverlayParameters())
        let overlay = try #require(
            JSONSerialization.jsonObject(with: overlayData) as? [String: Any]
        )
        #expect(Set(overlay.keys) == Set(["protocolVersion"]))
        #expect(overlay["protocolVersion"] as? Int == 1)

        let displayData = try JSONEncoder().encode(
            ReferenceDensityDisplayParameters(visible: true, opacity: 0.42)
        )
        let display = try #require(
            JSONSerialization.jsonObject(with: displayData) as? [String: Any]
        )
        #expect(Set(display.keys) == Set(["protocolVersion", "visible", "opacity"]))
        #expect(display["visible"] as? Bool == true)
        #expect(display["opacity"] as? Double == 0.42)
    }

    @Test("Preparation provenance tolerates additive response fields and validates")
    func preparationValidation() throws {
        var payload = preparationPayload()
        payload["futureProtocolField"] = ["safeToIgnore": true]
        let result = try decode(ReferenceDensityPrepareResult.self, from: payload)
        let atlas = try decode(AtlasProvenance.self, from: atlasPayload())

        try ReferenceDensityValidator.validatePreparation(result, against: atlas)

        #expect(result.source.doi == SafetyPolicy.populationReferenceDOI)
        #expect(result.cache.archiveSha256Verified)
        #expect(result.density.populationSubjectCount == 4)
    }

    @Test("An exact alpha PNG on the dorsal AP × ML grid is accepted")
    func overlayValidation() throws {
        var payload = overlayPayload(pngBase64: try makePNGBase64(hasAlpha: true))
        payload["futureProtocolField"] = "ignored"
        let result = try decode(ReferenceDensityOverlayResult.self, from: payload)
        let atlas = try decode(AtlasProvenance.self, from: atlasPayload())
        let dorsal = try decode(AtlasDorsalResult.self, from: dorsalPayload())

        let png = try ReferenceDensityValidator.verifiedOverlayPNG(
            result,
            dorsal: dorsal,
            atlas: atlas,
            display: visibleDisplay()
        )

        #expect(png.starts(with: Data([0x89, 0x50, 0x4E, 0x47])))
        #expect(result.rowAxis == "AP")
        #expect(result.columnAxis == "ML")
        #expect(!result.subjectSpecific)
        #expect(!result.supportsVesselClearance)
    }

    @Test("A changed DOI or archive digest fails closed")
    func sourceMismatch() throws {
        var payload = overlayPayload(pngBase64: try makePNGBase64(hasAlpha: true))
        var source = try #require(payload["source"] as? [String: Any])
        source["archiveSha256"] = String(repeating: "0", count: 64)
        payload["source"] = source
        let result = try decode(ReferenceDensityOverlayResult.self, from: payload)
        let atlas = try decode(AtlasProvenance.self, from: atlasPayload())
        let dorsal = try decode(AtlasDorsalResult.self, from: dorsalPayload())

        #expect(throws: ReferenceDensityValidationError.sourceIdentityMismatch) {
            try ReferenceDensityValidator.verifiedOverlayPNG(
                result,
                dorsal: dorsal,
                atlas: atlas,
                display: visibleDisplay()
            )
        }
    }

    @Test("Declared or decoded image dimensions must match the dorsal output")
    func dimensionMismatch() throws {
        var payload = overlayPayload(pngBase64: try makePNGBase64(hasAlpha: true))
        payload["width"] = 2
        let result = try decode(ReferenceDensityOverlayResult.self, from: payload)
        let atlas = try decode(AtlasProvenance.self, from: atlasPayload())
        let dorsal = try decode(AtlasDorsalResult.self, from: dorsalPayload())

        #expect(throws: ReferenceDensityValidationError.dimensionMismatch) {
            try ReferenceDensityValidator.verifiedOverlayPNG(
                result,
                dorsal: dorsal,
                atlas: atlas,
                display: visibleDisplay()
            )
        }
    }

    @Test("An opaque PNG cannot masquerade as a transparent overlay")
    func alphaRequired() throws {
        let result = try decode(
            ReferenceDensityOverlayResult.self,
            from: overlayPayload(pngBase64: try makePNGBase64(hasAlpha: false))
        )
        let atlas = try decode(AtlasProvenance.self, from: atlasPayload())
        let dorsal = try decode(AtlasDorsalResult.self, from: dorsalPayload())

        #expect(throws: ReferenceDensityValidationError.alphaChannelMissing) {
            try ReferenceDensityValidator.verifiedOverlayPNG(
                result,
                dorsal: dorsal,
                atlas: atlas,
                display: visibleDisplay()
            )
        }
    }

    @Test("A fully opaque RGBA PNG is rejected as a non-overlay")
    func fullyOpaqueRGBARejected() throws {
        let result = try decode(
            ReferenceDensityOverlayResult.self,
            from: overlayPayload(pngBase64: try makePNGBase64(hasAlpha: true, alpha: 1))
        )
        let atlas = try decode(AtlasProvenance.self, from: atlasPayload())
        let dorsal = try decode(AtlasDorsalResult.self, from: dorsalPayload())

        #expect(throws: ReferenceDensityValidationError.invalidAlphaCoverage) {
            try ReferenceDensityValidator.verifiedOverlayPNG(
                result,
                dorsal: dorsal,
                atlas: atlas,
                display: visibleDisplay()
            )
        }
    }

    @Test("A fully transparent RGBA PNG is rejected as having no visible density")
    func fullyTransparentRGBARejected() throws {
        let result = try decode(
            ReferenceDensityOverlayResult.self,
            from: overlayPayload(pngBase64: try makePNGBase64(hasAlpha: true, alpha: 0))
        )
        let atlas = try decode(AtlasProvenance.self, from: atlasPayload())
        let dorsal = try decode(AtlasDorsalResult.self, from: dorsalPayload())

        #expect(throws: ReferenceDensityValidationError.invalidAlphaCoverage) {
            try ReferenceDensityValidator.verifiedOverlayPNG(
                result,
                dorsal: dorsal,
                atlas: atlas,
                display: visibleDisplay()
            )
        }
    }

    @Test("Display mutations and overlays must match persisted visibility and opacity")
    func displayStateValidation() throws {
        let mutation = try decode(
            ReferenceDensityDisplayResult.self,
            from: [
                "protocolVersion": 1,
                "status": "updatedReferenceDensityDisplay",
                "display": ["visible": true, "opacity": 0.42],
            ]
        )
        try ReferenceDensityValidator.validateDisplayMutation(
            mutation,
            expectedVisible: true,
            expectedOpacity: 0.42
        )
        #expect(throws: ReferenceDensityValidationError.displayStateMismatch) {
            try ReferenceDensityValidator.validateDisplayMutation(
                mutation,
                expectedVisible: true,
                expectedOpacity: 0.65
            )
        }
        #expect(throws: ReferenceDensityValidationError.displayStateMismatch) {
            try ReferenceDensityValidator.validateBridgeState(
                PopulationDensityBridgeState(
                    available: true,
                    visible: true,
                    opacity: 0,
                    status: "preparedReferenceDensity"
                )
            )
        }

        var payload = overlayPayload(pngBase64: try makePNGBase64(hasAlpha: true))
        var window = try #require(payload["window"] as? [String: Any])
        window["opacity"] = 0.42
        payload["window"] = window
        payload["display"] = ["visible": true, "opacity": 0.42]
        let result = try decode(ReferenceDensityOverlayResult.self, from: payload)
        let atlas = try decode(AtlasProvenance.self, from: atlasPayload())
        let dorsal = try decode(AtlasDorsalResult.self, from: dorsalPayload())
        _ = try ReferenceDensityValidator.verifiedOverlayPNG(
            result,
            dorsal: dorsal,
            atlas: atlas,
            display: visibleDisplay(opacity: 0.42)
        )
        #expect(throws: ReferenceDensityValidationError.displayStateMismatch) {
            try ReferenceDensityValidator.verifiedOverlayPNG(
                result,
                dorsal: dorsal,
                atlas: atlas,
                display: visibleDisplay(opacity: 0.65)
            )
        }
    }

    private func atlasPayload() -> [String: Any] {
        [
            "identifier": SafetyPolicy.supportedAtlasIdentifier,
            "version": SafetyPolicy.supportedAtlasVersion,
            "metadataSha256": String(repeating: "a", count: 64),
            "resolutionMicrometres": [25, 25, 25],
            "shapeVoxels": [2, 2, 2],
            "orientation": "asr",
            "frameworkName": "brainglobe_atlasapi",
            "sourceAnnotation": "fixture",
            "citation": "fixture",
            "brainGlobeAtlasApiVersion": "2.0",
        ]
    }

    private func dorsalPayload() -> [String: Any] {
        [
            "protocolVersion": 1,
            "mimeType": "image/png",
            "pngBase64": "unused",
            "width": 1,
            "height": 1,
            "rowAxis": "AP",
            "columnAxis": "ML",
            "surfaceDvMinimumMicrometres": 12.5,
            "surfaceDvMaximumMicrometres": 37.5,
            "displayLabel": "Allen atlas dorsal surface projection — not a subject skull surface",
            "surfaceDefinition": "fixture",
            "atlas": [
                "identifier": SafetyPolicy.supportedAtlasIdentifier,
                "version": SafetyPolicy.supportedAtlasVersion,
                "resolutionMicrometres": [25, 25, 25],
                "orientation": "asr",
            ],
        ]
    }

    private func sourcePayload(includeArchiveDetails: Bool) -> [String: Any] {
        var source: [String: Any] = [
            "doi": SafetyPolicy.populationReferenceDOI,
            "version": SafetyPolicy.populationReferenceVersion,
            "archiveSha256": SafetyPolicy.populationReferenceArchiveSHA256,
        ]
        if includeArchiveDetails {
            source.merge([
                "landingPageUrl": "https://data.mendeley.com/datasets/stxvn5sv44/1",
                "downloadUrl": "https://data.mendeley.com/public-files/datasets/stxvn5sv44/files/archive",
                "archiveFilename": "NVU_mapping_Adult_mouse_brain (1).7z",
                "archiveSizeBytes": SafetyPolicy.populationReferenceArchiveByteCount,
                "densityMemberPath": "Vascular_length_Brain-wide/Vessel_LengthDensity_P56.nii",
                "templateMemberPath": "Vascular_length_Brain-wide/AllenCCF_template_20um-isotropic.nii",
            ]) { _, new in new }
        }
        return source
    }

    private func preparationPayload() -> [String: Any] {
        [
            "protocolVersion": 1,
            "status": "preparedReferenceDensity",
            "source": sourcePayload(includeArchiveDetails: true),
            "atlas": [
                "identifier": SafetyPolicy.supportedAtlasIdentifier,
                "version": SafetyPolicy.supportedAtlasVersion,
                "metadataSha256": String(repeating: "a", count: 64),
                "resolutionMicrometres": [25, 25, 25],
                "shapeVoxels": [2, 2, 2],
                "orientation": "asr",
            ],
            "density": [
                "valueUnits": "m/mm^3",
                "populationSubjectCount": 4,
                "rollingWindowMicrometres": 100,
                "outputShapeASR": [1, 1, 1],
                "outputResolutionMicrometres": 50,
                "templateCorrelation": 0.999,
                "minimumTemplateCorrelation": 0.99,
                "apAxisReversed": true,
                "mlSymmetrized": true,
                "subjectSpecific": false,
                "containsIndividualVesselPaths": false,
                "supportsVesselClearance": false,
            ],
            "cache": [
                "archiveSha256Verified": true,
                "preparedDensitySha256": String(repeating: "b", count: 64),
                "reusedPreparedCache": false,
            ],
            "disclosure": SafetyPolicy.populationDensityCaveat,
        ]
    }

    private func overlayPayload(pngBase64: String) -> [String: Any] {
        [
            "protocolVersion": 1,
            "status": "renderedReferenceDensity",
            "mimeType": "image/png",
            "pngBase64": pngBase64,
            "width": 1,
            "height": 1,
            "rowAxis": "AP",
            "columnAxis": "ML",
            "projectionAxis": "DV",
            "projectionMethod": "maximum",
            "atlasResolutionMicrometres": [25, 25],
            "densityResolutionMicrometres": 50,
            "window": [
                "low": 0,
                "high": 2.5,
                "units": "m/mm^3",
                "opacity": 0.65,
                "colorMap": "red-to-magenta",
            ],
            "display": [
                "visible": true,
                "opacity": 0.65,
            ],
            "source": sourcePayload(includeArchiveDetails: false),
            "atlas": [
                "identifier": SafetyPolicy.supportedAtlasIdentifier,
                "version": SafetyPolicy.supportedAtlasVersion,
                "metadataSha256": String(repeating: "a", count: 64),
            ],
            "subjectSpecific": false,
            "containsIndividualVesselPaths": false,
            "supportsVesselClearance": false,
            "displayLabel": "Published population vascular length density",
            "disclosure": SafetyPolicy.populationDensityCaveat,
        ]
    }

    private func decode<Value: Decodable>(
        _ type: Value.Type,
        from object: [String: Any]
    ) throws -> Value {
        let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        return try JSONDecoder().decode(type, from: data)
    }

    private func visibleDisplay(opacity: Double = 0.65) -> PopulationDensityBridgeState {
        PopulationDensityBridgeState(
            available: true,
            visible: true,
            opacity: opacity,
            status: "preparedReferenceDensity"
        )
    }

    private func makePNGBase64(hasAlpha: Bool, alpha: CGFloat = 0.4) throws -> String {
        let alphaInfo: CGImageAlphaInfo = hasAlpha ? .premultipliedLast : .noneSkipLast
        let context = try #require(
            CGContext(
                data: nil,
                width: 1,
                height: 1,
                bitsPerComponent: 8,
                bytesPerRow: 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: alphaInfo.rawValue
            )
        )
        context.setFillColor(red: 1, green: 0, blue: 1, alpha: hasAlpha ? alpha : 1)
        context.fill(CGRect(x: 0, y: 0, width: 1, height: 1))
        let image = try #require(context.makeImage())
        let data = NSMutableData()
        let destination = try #require(
            CGImageDestinationCreateWithData(data, "public.png" as CFString, 1, nil)
        )
        CGImageDestinationAddImage(destination, image, nil)
        #expect(CGImageDestinationFinalize(destination))
        return (data as Data).base64EncodedString()
    }
}
