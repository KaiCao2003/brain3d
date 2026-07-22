import CoreGraphics
import Foundation
import ImageIO

public enum ReferenceDensityValidationError: Error, Equatable, LocalizedError, Sendable {
    case protocolMismatch(Int)
    case unexpectedStatus(String)
    case sourceIdentityMismatch
    case archiveIntegrityUnverified
    case preparedDigestInvalid
    case atlasMismatch
    case densityContractMismatch
    case unsafeSemantics
    case projectionMismatch
    case dimensionMismatch
    case disclosureMissing
    case invalidPNG
    case alphaChannelMissing
    case invalidAlphaCoverage
    case displayStateMismatch

    public var errorDescription: String? {
        switch self {
        case let .protocolMismatch(version):
            "Reference density response uses protocol \(version); expected \(BridgeProtocolVersion.current)."
        case let .unexpectedStatus(status):
            "Reference density response has unexpected status ‘\(status)’"
        case .sourceIdentityMismatch:
            "Reference density DOI, version, size, or archive SHA-256 does not match the reviewed source."
        case .archiveIntegrityUnverified:
            "The published reference archive SHA-256 was not verified."
        case .preparedDigestInvalid:
            "The prepared reference density has no valid SHA-256 provenance."
        case .atlasMismatch:
            "Reference density atlas identity, metadata, shape, or resolution does not match the open atlas."
        case .densityContractMismatch:
            "Reference density units, cohort, window, alignment, or output grid failed validation."
        case .unsafeSemantics:
            "Reference density response incorrectly claims subject-specific vessels or vessel clearance."
        case .projectionMismatch:
            "Reference density is not the reviewed AP × ML dorsal maximum projection."
        case .dimensionMismatch:
            "Reference density image dimensions do not match the verified dorsal atlas output."
        case .disclosureMissing:
            "Reference density response omitted its required population-reference disclosure."
        case .invalidPNG:
            "Reference density response did not contain a decodable PNG image."
        case .alphaChannelMissing:
            "Reference density PNG has no alpha channel and cannot be safely composited as an overlay."
        case .invalidAlphaCoverage:
            "Reference density PNG must contain both transparent and visible pixels."
        case .displayStateMismatch:
            "Reference density visibility or opacity does not match the persisted backend display state."
        }
    }
}

public enum ReferenceDensityValidator {
    public static func validateBridgeState(_ state: PopulationDensityBridgeState) throws {
        guard state.opacity.isFinite, (0 ... 1).contains(state.opacity) else {
            throw ReferenceDensityValidationError.displayStateMismatch
        }
        guard !state.visible || state.available else {
            throw ReferenceDensityValidationError.displayStateMismatch
        }
        guard !state.visible || state.opacity > 0 else {
            throw ReferenceDensityValidationError.displayStateMismatch
        }
        switch state.status {
        case "notLoaded":
            guard
                !state.available,
                !state.visible,
                state.opacity == SafetyPolicy.populationReferenceDefaultOpacity
            else {
                throw ReferenceDensityValidationError.displayStateMismatch
            }
        case "preparedCacheUnavailable":
            guard !state.available, !state.visible else {
                throw ReferenceDensityValidationError.displayStateMismatch
            }
        case "preparedReferenceDensity":
            guard state.available else {
                throw ReferenceDensityValidationError.displayStateMismatch
            }
        default:
            throw ReferenceDensityValidationError.unexpectedStatus(state.status)
        }
    }

    public static func validateDisplayMutation(
        _ result: ReferenceDensityDisplayResult,
        expectedVisible: Bool,
        expectedOpacity: Double
    ) throws {
        guard result.protocolVersion == BridgeProtocolVersion.current else {
            throw ReferenceDensityValidationError.protocolMismatch(result.protocolVersion)
        }
        guard result.status == "updatedReferenceDensityDisplay" else {
            throw ReferenceDensityValidationError.unexpectedStatus(result.status)
        }
        guard
            expectedOpacity.isFinite,
            (0 ... 1).contains(expectedOpacity),
            result.display.opacity.isFinite,
            result.display.visible == expectedVisible,
            result.display.opacity == expectedOpacity,
            !expectedVisible || expectedOpacity > 0
        else {
            throw ReferenceDensityValidationError.displayStateMismatch
        }
    }

    public static func validatePreparation(
        _ result: ReferenceDensityPrepareResult,
        against atlas: AtlasProvenance
    ) throws {
        guard result.protocolVersion == BridgeProtocolVersion.current else {
            throw ReferenceDensityValidationError.protocolMismatch(result.protocolVersion)
        }
        guard result.status == "preparedReferenceDensity" else {
            throw ReferenceDensityValidationError.unexpectedStatus(result.status)
        }
        try validateSource(result.source, requireArchiveDetails: true)
        try validateAtlas(result.atlas, against: atlas, requireSpatialFields: true)

        let density = result.density
        guard
            density.valueUnits == "m/mm^3",
            density.populationSubjectCount == 4,
            density.rollingWindowMicrometres == 100,
            density.outputResolutionMicrometres == 50,
            density.outputShapeASR.count == 3,
            density.outputShapeASR.allSatisfy({ $0 > 0 }),
            density.templateCorrelation.isFinite,
            density.minimumTemplateCorrelation.isFinite,
            density.minimumTemplateCorrelation >= 0.99,
            density.templateCorrelation >= density.minimumTemplateCorrelation,
            density.apAxisReversed,
            density.mlSymmetrized
        else {
            throw ReferenceDensityValidationError.densityContractMismatch
        }
        guard
            !density.subjectSpecific,
            !density.containsIndividualVesselPaths,
            !density.supportsVesselClearance
        else {
            throw ReferenceDensityValidationError.unsafeSemantics
        }
        guard physicalExtentsMatch(density: density, atlas: atlas) else {
            throw ReferenceDensityValidationError.atlasMismatch
        }
        guard result.cache.archiveSha256Verified else {
            throw ReferenceDensityValidationError.archiveIntegrityUnverified
        }
        guard isLowercaseSHA256(result.cache.preparedDensitySha256) else {
            throw ReferenceDensityValidationError.preparedDigestInvalid
        }
        try validateDisclosure(result.disclosure)
    }

    public static func verifiedOverlayPNG(
        _ result: ReferenceDensityOverlayResult,
        dorsal: AtlasDorsalResult,
        atlas: AtlasProvenance,
        display: PopulationDensityBridgeState
    ) throws -> Data {
        guard result.protocolVersion == BridgeProtocolVersion.current else {
            throw ReferenceDensityValidationError.protocolMismatch(result.protocolVersion)
        }
        guard result.status == "renderedReferenceDensity" else {
            throw ReferenceDensityValidationError.unexpectedStatus(result.status)
        }
        try validateSource(result.source, requireArchiveDetails: false)
        try validateAtlas(result.atlas, against: atlas, requireSpatialFields: false)
        try validateBridgeState(display)
        guard
            display.available,
            display.visible,
            result.display.visible,
            result.display.opacity.isFinite,
            result.display.opacity == display.opacity
        else {
            throw ReferenceDensityValidationError.displayStateMismatch
        }
        guard
            dorsal.atlas.identifier == atlas.identifier,
            dorsal.atlas.version == atlas.version,
            dorsal.atlas.resolutionMicrometres == atlas.resolutionMicrometres,
            dorsal.rowAxis == "AP",
            dorsal.columnAxis == "ML"
        else {
            throw ReferenceDensityValidationError.atlasMismatch
        }
        guard
            result.rowAxis == "AP",
            result.columnAxis == "ML",
            result.projectionAxis == "DV",
            result.projectionMethod == "maximum",
            result.atlasResolutionMicrometres == [
                atlas.resolutionMicrometres[0],
                atlas.resolutionMicrometres[2],
            ]
        else {
            throw ReferenceDensityValidationError.projectionMismatch
        }
        guard
            result.width > 0,
            result.height > 0,
            result.width == dorsal.width,
            result.height == dorsal.height
        else {
            throw ReferenceDensityValidationError.dimensionMismatch
        }
        guard
            result.densityResolutionMicrometres == 50,
            result.window.low.isFinite,
            result.window.high.isFinite,
            result.window.high > result.window.low,
            result.window.units == "m/mm^3",
            result.window.opacity.isFinite,
            (0 ... 1).contains(result.window.opacity),
            result.window.opacity == result.display.opacity,
            result.window.colorMap == "red-to-magenta",
            !result.displayLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw ReferenceDensityValidationError.densityContractMismatch
        }
        guard
            !result.subjectSpecific,
            !result.containsIndividualVesselPaths,
            !result.supportsVesselClearance
        else {
            throw ReferenceDensityValidationError.unsafeSemantics
        }
        try validateDisclosure(result.disclosure)

        guard
            result.mimeType == "image/png",
            let data = Data(base64Encoded: result.pngBase64),
            data.starts(with: Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])),
            let source = CGImageSourceCreateWithData(data as CFData, nil),
            CGImageSourceGetCount(source) == 1,
            let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        else {
            throw ReferenceDensityValidationError.invalidPNG
        }
        guard image.width == result.width, image.height == result.height else {
            throw ReferenceDensityValidationError.dimensionMismatch
        }
        guard imageHasAlpha(image) else {
            throw ReferenceDensityValidationError.alphaChannelMissing
        }
        guard
            let coverage = alphaCoverage(image),
            coverage.hasTransparentPixel,
            coverage.hasVisiblePixel
        else {
            throw ReferenceDensityValidationError.invalidAlphaCoverage
        }
        return data
    }

    private static func validateSource(
        _ source: ReferenceDensitySourceIdentity,
        requireArchiveDetails: Bool
    ) throws {
        guard
            source.doi == SafetyPolicy.populationReferenceDOI,
            source.version == SafetyPolicy.populationReferenceVersion,
            source.archiveSha256 == SafetyPolicy.populationReferenceArchiveSHA256,
            isLowercaseSHA256(source.archiveSha256)
        else {
            throw ReferenceDensityValidationError.sourceIdentityMismatch
        }
        if requireArchiveDetails {
            guard
                source.archiveSizeBytes == SafetyPolicy.populationReferenceArchiveByteCount,
                source.landingPageUrl?.hasPrefix("https://data.mendeley.com/") == true,
                source.downloadUrl?.hasPrefix("https://") == true,
                source.archiveFilename?.isEmpty == false,
                source.densityMemberPath?.isEmpty == false,
                source.templateMemberPath?.isEmpty == false
            else {
                throw ReferenceDensityValidationError.sourceIdentityMismatch
            }
        }
    }

    private static func validateAtlas(
        _ identity: ReferenceDensityAtlasIdentity,
        against atlas: AtlasProvenance,
        requireSpatialFields: Bool
    ) throws {
        guard
            identity.identifier == SafetyPolicy.supportedAtlasIdentifier,
            identity.version == SafetyPolicy.supportedAtlasVersion,
            identity.identifier == atlas.identifier,
            identity.version == atlas.version,
            identity.metadataSha256 == atlas.metadataSha256,
            atlas.resolutionMicrometres == [25, 25, 25]
        else {
            throw ReferenceDensityValidationError.atlasMismatch
        }
        if requireSpatialFields {
            guard
                identity.resolutionMicrometres == atlas.resolutionMicrometres,
                identity.shapeVoxels == atlas.shapeVoxels,
                identity.orientation?.lowercased() == "asr"
            else {
                throw ReferenceDensityValidationError.atlasMismatch
            }
        }
    }

    private static func physicalExtentsMatch(
        density: ReferenceDensityPreparedField,
        atlas: AtlasProvenance
    ) -> Bool {
        guard density.outputShapeASR.count == 3, atlas.shapeVoxels.count == 3 else {
            return false
        }
        return zip(density.outputShapeASR, zip(atlas.shapeVoxels, atlas.resolutionMicrometres))
            .allSatisfy { densitySize, atlasComponent in
                let (atlasSize, atlasResolution) = atlasComponent
                return Double(densitySize) * density.outputResolutionMicrometres
                    == Double(atlasSize) * atlasResolution
            }
    }

    private static func validateDisclosure(_ disclosure: String) throws {
        guard !disclosure.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ReferenceDensityValidationError.disclosureMissing
        }
    }

    private static func imageHasAlpha(_ image: CGImage) -> Bool {
        switch image.alphaInfo {
        case .premultipliedLast, .premultipliedFirst, .last, .first, .alphaOnly:
            true
        case .none, .noneSkipLast, .noneSkipFirst:
            false
        @unknown default:
            false
        }
    }

    private static func alphaCoverage(
        _ image: CGImage
    ) -> (hasTransparentPixel: Bool, hasVisiblePixel: Bool)? {
        let width = image.width
        let height = image.height
        guard
            width > 0,
            height > 0,
            width <= Int.max / 4,
            height <= Int.max / (width * 4)
        else {
            return nil
        }
        let bytesPerRow = width * 4
        var pixels = [UInt8](repeating: 0, count: bytesPerRow * height)
        let rendered = pixels.withUnsafeMutableBytes { storage -> Bool in
            guard
                let baseAddress = storage.baseAddress,
                let context = CGContext(
                    data: baseAddress,
                    width: width,
                    height: height,
                    bitsPerComponent: 8,
                    bytesPerRow: bytesPerRow,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
                        | CGBitmapInfo.byteOrder32Big.rawValue
                )
            else {
                return false
            }
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard rendered else { return nil }

        var hasTransparentPixel = false
        var hasVisiblePixel = false
        for alphaIndex in stride(from: 3, to: pixels.count, by: 4) {
            let alpha = pixels[alphaIndex]
            hasTransparentPixel = hasTransparentPixel || alpha < 255
            hasVisiblePixel = hasVisiblePixel || alpha > 0
            if hasTransparentPixel, hasVisiblePixel {
                break
            }
        }
        return (hasTransparentPixel, hasVisiblePixel)
    }

    private static func isLowercaseSHA256(_ value: String) -> Bool {
        value.utf8.count == 64 && value.utf8.allSatisfy { byte in
            (48 ... 57).contains(byte) || (97 ... 102).contains(byte)
        }
    }
}
