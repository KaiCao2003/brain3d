import AppKit
import Brain3DCore
import Brain3DScene
import CryptoKit
import Foundation
import PDFKit

enum SurgeryPlanView: String, CaseIterable, Hashable, Identifiable, Sendable {
    case dorsal = "Dorsal"
    case coronal = "Coronal"
    case sagittal = "Sagittal"
    case horizontal = "Horizontal"
    case threeDimensional = "3D"

    var id: String { rawValue }

    var sliceOrientation: AtlasSliceOrientation? {
        switch self {
        case .dorsal, .threeDimensional: nil
        case .coronal: .coronal
        case .sagittal: .sagittal
        case .horizontal: .horizontal
        }
    }

    init(workspaceMode: WorkspaceMode) {
        switch workspaceMode {
        case .dorsal: self = .dorsal
        case .coronal: self = .coronal
        case .sagittal: self = .sagittal
        case .horizontal: self = .horizontal
        case .threeDimensional: self = .threeDimensional
        }
    }
}

enum SurgeryPlanViewSelection: String, CaseIterable, Identifiable, Sendable {
    case dorsal = "Dorsal only"
    case coronal = "Coronal only"
    case sagittal = "Sagittal only"
    case horizontal = "Horizontal only"
    case threeDimensional = "3D only"
    case all = "All five views"

    var id: String { rawValue }

    var views: [SurgeryPlanView] {
        switch self {
        case .dorsal: [.dorsal]
        case .coronal: [.coronal]
        case .sagittal: [.sagittal]
        case .horizontal: [.horizontal]
        case .threeDimensional: [.threeDimensional]
        case .all: SurgeryPlanView.allCases
        }
    }

    init(workspaceMode: WorkspaceMode) {
        switch workspaceMode {
        case .dorsal: self = .dorsal
        case .coronal: self = .coronal
        case .sagittal: self = .sagittal
        case .horizontal: self = .horizontal
        case .threeDimensional: self = .threeDimensional
        }
    }
}

enum SurgeryAtlasOrientation: String, CaseIterable, Identifiable, Sendable {
    case coronal = "Coronal"
    case sagittal = "Sagittal"

    var id: String { rawValue }
}

struct SurgeryAtlasPlate: Equatable, Sendable {
    let figure: Int
    let orientation: SurgeryAtlasOrientation
    let fixedCoordinateMillimetres: Double
    let sourceURL: URL

    var coordinateLabel: String {
        switch orientation {
        case .coronal:
            String(format: "Bregma %+.2f mm", fixedCoordinateMillimetres)
        case .sagittal:
            String(format: "Lateral %.2f mm", fixedCoordinateMillimetres)
        }
    }

    var displayName: String {
        "Figure \(figure) · \(coordinateLabel)"
    }
}

enum SurgeryAtlasCatalog {
    // Reviewed against all 132 pages in the user-supplied consolidated Mouse
    // Brain PDF. Spacing is intentionally figure-specific and must not be
    // inferred.
    private static let coronalCoordinates: [Double] = [
        4.28, 3.92, 3.56, 3.20, 3.08, 2.96, 2.80, 2.68, 2.58, 2.46,
        2.34, 2.22, 2.10, 1.98, 1.94, 1.78, 1.70, 1.54, 1.42, 1.34,
        1.18, 1.10, 0.98, 0.86, 0.74, 0.62, 0.50, 0.38, 0.26, 0.14,
        0.02, -0.10, -0.22, -0.34, -0.46, -0.58, -0.70, -0.82, -0.94,
        -1.06, -1.22, -1.34, -1.46, -1.58, -1.70, -1.82, -1.94, -2.06,
        -2.18, -2.30, -2.46, -2.54, -2.70, -2.80, -2.92, -3.08, -3.16,
        -3.28, -3.40, -3.52, -3.64, -3.80, -3.88, -4.04, -4.16, -4.24,
        -4.36, -4.48, -4.60, -4.72, -4.84, -4.96, -5.02, -5.20, -5.34,
        -5.40, -5.52, -5.68, -5.80, -5.88, -6.00, -6.12, -6.24, -6.36,
        -6.48, -6.64, -6.72, -6.84, -6.96, -7.08, -7.20, -7.32, -7.48,
        -7.56, -7.64, -7.76, -7.92, -8.00, -8.12, -8.24,
    ]

    private static let sagittalCoordinates: [Double] = [
        -0.04, 0.12, 0.24, 0.36, 0.48, 0.60, 0.72, 0.84,
        0.96, 1.08, 1.20, 1.32, 1.44, 1.56, 1.68, 1.80,
        1.92, 2.04, 2.16, 2.28, 2.40, 2.52, 2.64, 2.76,
        2.88, 3.00, 3.12, 3.25, 3.36, 3.44, 3.60, 3.72,
    ]

    static func plates(in atlasPDFURL: URL) throws -> [SurgeryAtlasPlate] {
        guard atlasPDFURL.pathExtension.lowercased() == "pdf",
              (try? atlasPDFURL.resourceValues(
                  forKeys: [.isRegularFileKey]
              ).isRegularFile) == true,
              let document = PDFDocument(url: atlasPDFURL),
              document.pageCount == 132
        else {
            throw SurgeryPlanExportError.invalidAtlasSource(
                "Choose the 132-page MBSC_Figs_with_Layers.pdf source."
            )
        }
        return canonicalPlates(sourceURL: atlasPDFURL)
    }

    static func canonicalPlates(sourceURL: URL) -> [SurgeryAtlasPlate] {
        let coronals = coronalCoordinates.enumerated().map { offset, coordinate in
            SurgeryAtlasPlate(
                figure: offset + 1,
                orientation: .coronal,
                fixedCoordinateMillimetres: coordinate,
                sourceURL: sourceURL
            )
        }
        let sagittals = sagittalCoordinates.enumerated().map { offset, coordinate in
            SurgeryAtlasPlate(
                figure: offset + 101,
                orientation: .sagittal,
                fixedCoordinateMillimetres: coordinate,
                sourceURL: sourceURL
            )
        }
        return coronals + sagittals
    }

    static func nearestPlate(
        in atlasPDFURL: URL,
        orientation: SurgeryAtlasOrientation,
        target: UnprojectedImplantTarget
    ) throws -> SurgeryAtlasPlate {
        try nearestPlate(
            in: atlasPDFURL,
            orientation: orientation,
            apMillimetres: target.apMillimetres,
            mlMillimetres: target.mlMillimetres
        )
    }

    static func nearestPlate(
        in atlasPDFURL: URL,
        orientation: SurgeryAtlasOrientation,
        apMillimetres: Double,
        mlMillimetres: Double
    ) throws -> SurgeryAtlasPlate {
        let requestedCoordinate = orientation == .coronal
            ? apMillimetres
            : abs(mlMillimetres)
        let candidates = try plates(in: atlasPDFURL).filter {
            $0.orientation == orientation
        }
        guard let lower = candidates.map(\.fixedCoordinateMillimetres).min(),
              let upper = candidates.map(\.fixedCoordinateMillimetres).max(),
              requestedCoordinate >= lower,
              requestedCoordinate <= upper
        else {
            let axis = orientation == .coronal ? "AP" : "|ML|"
            throw SurgeryPlanExportError.atlasCoordinateOutsideRange(
                "\(axis) \(String(format: "%+.3f", requestedCoordinate)) mm"
            )
        }
        let plate = candidates.min {
            abs($0.fixedCoordinateMillimetres - requestedCoordinate)
                < abs($1.fixedCoordinateMillimetres - requestedCoordinate)
        }!
        guard let document = PDFDocument(url: atlasPDFURL),
              let page = document.page(at: plate.figure - 1),
              SurgeryAtlasPDFSource.isLandscapeLetter(
                  page.bounds(for: .mediaBox).size
              ),
              SurgeryAtlasPDFSource.validatesPageText(
                  page.string ?? "",
                  plate: plate
              )
        else {
            throw SurgeryPlanExportError.invalidAtlasSource(
                "Page \(plate.figure) does not match \(plate.displayName)."
            )
        }
        return plate
    }
}

enum SurgeryPlanExportClass: String, Sendable {
    case draft = "DRAFT"
    case final = "FINAL"
}

enum SurgeryPlanSurfaceAnglePresentation {
    static func text(_ angleDegrees: Double, separator: String = " ") -> String {
        if angleDegrees == 0 {
            return "A↔P 0.0°\(separator)(vertical)"
        }
        return String(
            format: "A↔P %+.1f°\(separator)(%@)",
            angleDegrees,
            angleDegrees > 0 ? "A→P" : "P→A"
        )
    }
}

enum SurgeryPlanReadiness {
    static func currentProjection(
        _ projection: CalibratedTargetProjectionResult?,
        project: ProjectBridgeState,
        target: UnprojectedImplantTarget,
        calibration: CalibrationSummary?,
        atlas: ViewerAtlasIdentity
    ) -> CalibratedTargetProjectionResult? {
        guard let projection, let calibration,
              calibration.active,
              calibration.permitsPlanning,
              project.activeCalibrationId == calibration.calibrationId,
              projection.projectId == project.projectId,
              projection.targetId == target.targetId,
              projection.sourceTargetPreserved,
              !projection.projectionPersisted,
              projection.usableForPlanning,
              !projection.usableForNavigation,
              projection.provenance.calibrationId == calibration.calibrationId,
              projection.provenance.calibrationVersion == calibration.calibrationVersion,
              projection.provenance.calibrationSha256 == calibration.calibrationSha256,
              projection.provenance.atlasMetadataSha256 == calibration.atlasMetadataSha256,
              projection.provenance.atlasMetadataSha256 == atlas.metadataSha256,
              projection.atlasPoint.atlasIdentifier == atlas.identifier,
              projection.atlasPoint.atlasVersion == atlas.version
        else { return nil }
        return projection
    }

    static func currentProbePlan(
        _ plan: ProbePlanDetail?,
        target: UnprojectedImplantTarget,
        projection: CalibratedTargetProjectionResult,
        calibration: CalibrationSummary,
        atlas: ViewerAtlasIdentity
    ) -> ProbePlanDetail? {
        guard let plan,
              plan.targetId == target.targetId,
              plan.hasCurrentPlanningGeometry,
              !plan.usableForNavigation,
              plan.calibrationId == calibration.calibrationId,
              plan.calibrationVersion == calibration.calibrationVersion,
              plan.provenance.calibrationId == calibration.calibrationId,
              plan.provenance.calibrationVersion == calibration.calibrationVersion,
              plan.provenance.calibrationSha256 == calibration.calibrationSha256,
              plan.provenance.atlasMetadataSha256 == atlas.metadataSha256,
              plan.provenance.projectionSha256
                == projection.provenance.projectionSha256,
              let sourceTarget = plan.sourceTarget,
              sourceTarget.apMillimetres == target.apMillimetres,
              sourceTarget.mlMillimetres == target.mlMillimetres,
              sourceTarget.dvMillimetres == target.dvMillimetres,
              plan.placement.atlasFrame.target.apMicrometres
                == projection.atlasPoint.apMicrometres,
              plan.placement.atlasFrame.target.dvMicrometres
                == projection.atlasPoint.dvMicrometres,
              plan.placement.atlasFrame.target.mlMicrometres
                == projection.atlasPoint.mlMicrometres
        else { return nil }
        return plan
    }

    static func currentSurfaceProbePlan(
        _ plan: ProbePlanDetail?,
        atlas: ViewerAtlasIdentity
    ) -> ProbePlanDetail? {
        guard let plan,
              plan.placementMode == .atlasSurfaceAPML,
              plan.hasCurrentPlanningGeometry,
              !plan.usableForNavigation,
              plan.targetId == nil,
              plan.calibrationId == nil,
              plan.calibrationVersion == nil,
              plan.sourceTarget == nil,
              plan.manipulatorInput == nil,
              let input = plan.surfaceRelativeInput,
              input.mode == .atlasSurfaceAPML,
              input.bregmaReference.atlasIdentifier == atlas.identifier,
              input.bregmaReference.atlasVersion == atlas.version,
              input.surfaceEntry.atlasIdentifier == atlas.identifier,
              input.surfaceEntry.atlasVersion == atlas.version,
              plan.provenance.atlasMetadataSha256 == atlas.metadataSha256,
              plan.provenance.planningAlgorithmVersion
                == ProbePlanningContract.surfacePlanningAlgorithmVersion
        else { return nil }
        return plan
    }

    static func exportClass(
        project: ProjectBridgeState,
        hasUnsavedChanges: Bool,
        calibration: CalibrationSummary,
        projection: CalibratedTargetProjectionResult,
        probePlan: ProbePlanDetail?
    ) -> SurgeryPlanExportClass {
        let subjectId = project.subjectId?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard subjectId?.isEmpty == false,
              project.animalResearchOnlyAcknowledged,
              !project.requiresSaveAs,
              !project.isDirty,
              !hasUnsavedChanges,
              calibration.permitsFinalExport,
              probePlan != nil,
              projection.usableForPlanning
        else { return .draft }
        return .final
    }

    static func exportClass(
        project: ProjectBridgeState,
        hasUnsavedChanges: Bool,
        surfaceProbePlan: ProbePlanDetail?
    ) -> SurgeryPlanExportClass {
        let subjectId = project.subjectId?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard subjectId?.isEmpty == false,
              project.animalResearchOnlyAcknowledged,
              !project.requiresSaveAs,
              !project.isDirty,
              !hasUnsavedChanges,
              surfaceProbePlan != nil
        else { return .draft }
        return .final
    }
}

struct SurgeryPlanPrefill: Equatable, Sendable {
    let exportClass: SurgeryPlanExportClass
    let date: String
    let projectTitle: String
    let projectRevision: Int
    let subjectId: String
    let targetLabel: String
    let apMillimetres: Double
    let mlMillimetres: Double
    let dvMillimetres: Double?
    let cageId: String
    let mouseNumber: String
    let weightGrams: String
    let operatorName: String
    let probePlanName: String?
    let probeModelName: String?
    let insertionDepthMillimetres: Double?
    let azimuthDegrees: Double?
    let elevationDegrees: Double?
    let axialRotationDegrees: Double?
    let surfaceDepthMillimetres: Double?
    let sagittalAngleDegrees: Double?
    let probeLayoutRotationDegrees: Int?
    let probeVerificationStatus: String?
    let probeWarning: String?
    let planInputSHA256: String?
    let surfaceAnnotationSHA256: String?
    let surfaceDefinitionVersion: String?
    let bregmaReferenceId: String?
    let bregmaSourceRevision: String?
    let bregmaSourceSHA256: String?
    let draftReason: String?

    var templateAngleText: String {
        if let sagittalAngleDegrees {
            return SurgeryPlanSurfaceAnglePresentation.text(
                sagittalAngleDegrees
            )
        }
        guard let azimuthDegrees, let elevationDegrees else { return "________" }
        return String(
            format: "Az %+.1f° / El %+.1f°",
            azimuthDegrees,
            elevationDegrees
        )
    }

    var targetCoordinateText: String {
        if let surfaceDepthMillimetres {
            return String(
                format:
                    "AP %+.3f mm · ML %+.3f mm · depth %.3f mm from local atlas surface",
                apMillimetres,
                mlMillimetres,
                surfaceDepthMillimetres
            )
        }
        guard let dvMillimetres else {
            return String(
                format: "AP %+.3f mm · ML %+.3f mm", apMillimetres, mlMillimetres
            )
        }
        return String(
            format: "AP %+.3f mm · ML %+.3f mm · DV %+.3f mm",
            apMillimetres,
            mlMillimetres,
            dvMillimetres
        )
    }

    var probeText: String {
        if let probePlanName, let probeModelName,
           let surfaceDepthMillimetres, let sagittalAngleDegrees,
           let probeLayoutRotationDegrees
        {
            let layout = probeLayoutRotationDegrees == 90
                ? "90° CW from dorsal"
                : "sagittal"
            return "\(probePlanName) · \(probeModelName) · "
                + String(
                    format: "depth %.3f mm from surface · ",
                    surfaceDepthMillimetres
                )
                + SurgeryPlanSurfaceAnglePresentation.text(
                    sagittalAngleDegrees
                )
                + " · layout \(layout)"
        }
        guard let probePlanName, let probeModelName,
              let insertionDepthMillimetres,
              let azimuthDegrees, let elevationDegrees, let axialRotationDegrees
        else {
            return "No calibrated probe trajectory attached"
        }
        return String(
            format:
                "%@ · %@ · insertion %.3f mm · Az %+.1f° · El %+.1f° · Roll %+.1f°",
            probePlanName,
            probeModelName,
            insertionDepthMillimetres,
            azimuthDegrees,
            elevationDegrees,
            axialRotationDegrees
        )
    }

    var compactProbeText: String {
        guard let probeModelName, let surfaceDepthMillimetres,
              let sagittalAngleDegrees, let probeLayoutRotationDegrees
        else { return probeText }
        let model = probeModelName.contains("NP2013") ? "NP2013" : "NP2003"
        let layout = probeLayoutRotationDegrees == 90 ? "90° CW" : "sagittal"
        return "\(model) · "
            + String(format: "depth %.3f mm · ", surfaceDepthMillimetres)
            + SurgeryPlanSurfaceAnglePresentation.text(sagittalAngleDegrees)
            + " · layout \(layout)"
    }

    var probeReviewText: String? {
        guard let probeVerificationStatus else { return nil }
        let warning = probeWarning?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if let warning, !warning.isEmpty {
            return "Probe geometry: \(probeVerificationStatus) · \(warning)"
        }
        return "Probe geometry: \(probeVerificationStatus)"
    }

    var surfaceProvenanceText: String? {
        guard let planInputSHA256, let surfaceAnnotationSHA256,
              let surfaceDefinitionVersion, let bregmaReferenceId,
              let bregmaSourceRevision, let bregmaSourceSHA256
        else { return nil }
        let definition = Self.compactProvenanceComponent(
            surfaceDefinitionVersion
        )
        let reference = Self.compactProvenanceComponent(bregmaReferenceId)
        let revision = Self.compactProvenanceComponent(bregmaSourceRevision)
        return "Surface \(definition) · plan "
            + "\(planInputSHA256.prefix(10))… · annotation "
            + "\(surfaceAnnotationSHA256.prefix(10))… · bregma "
            + "\(reference) @ \(revision) "
            + "\(bregmaSourceSHA256.prefix(10))…"
    }

    private static func compactProvenanceComponent(_ value: String) -> String {
        let singleLine = value
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")
        let maximumCharacters = 40
        guard singleLine.count > maximumCharacters else { return singleLine }
        let digest = LowercaseHex.encode(
            SHA256.hash(data: Data(singleLine.utf8)).prefix(4)
        )
        return String(singleLine.prefix(maximumCharacters - 10))
            + "…#\(digest)"
    }
}

struct SurgeryPlanExportConfiguration: Sendable {
    let targetId: String
    let targetLabel: String
    let date: Date
    let cageId: String
    let mouseNumber: String
    let weightGrams: String
    let operatorName: String
    let viewSelection: SurgeryPlanViewSelection
    let protocolTemplateURL: URL
    let atlasPDFURL: URL
    let requiredAtlasSourceSHA256: String?
    let atlasOrientation: SurgeryAtlasOrientation

    func validated() throws -> SurgeryPlanExportConfiguration {
        let targetLabel = try Self.validatedText(
            targetLabel,
            field: "Target label",
            maximumCharacters: 80
        )
        let cageId = try Self.validatedText(
            cageId,
            field: "Cage ID",
            maximumCharacters: 80
        )
        let mouseNumber = try Self.validatedText(
            mouseNumber,
            field: "Mouse number",
            maximumCharacters: 80
        )
        let weightGrams = try Self.validatedText(
            weightGrams,
            field: "Weight",
            maximumCharacters: 16
        )
        let operatorName = try Self.validatedText(
            operatorName,
            field: "Operator",
            maximumCharacters: 80
        )
        if !weightGrams.isEmpty {
            guard let weight = Double(weightGrams),
                  weight.isFinite,
                  weight >= 0.1,
                  weight <= 200
            else {
                throw SurgeryPlanExportError.invalidAnimalRecord(
                    "Weight must be a number from 0.1 to 200 g."
                )
            }
        }
        return SurgeryPlanExportConfiguration(
            targetId: targetId,
            targetLabel: targetLabel,
            date: date,
            cageId: cageId,
            mouseNumber: mouseNumber,
            weightGrams: weightGrams,
            operatorName: operatorName,
            viewSelection: viewSelection,
            protocolTemplateURL: protocolTemplateURL,
            atlasPDFURL: atlasPDFURL,
            requiredAtlasSourceSHA256: requiredAtlasSourceSHA256,
            atlasOrientation: atlasOrientation
        )
    }

    private static func validatedText(
        _ value: String,
        field: String,
        maximumCharacters: Int
    ) throws -> String {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.count <= maximumCharacters else {
            throw SurgeryPlanExportError.invalidAnimalRecord(
                "\(field) must be \(maximumCharacters) characters or fewer."
            )
        }
        guard normalized.unicodeScalars.allSatisfy({
            !CharacterSet.controlCharacters.contains($0)
        }) else {
            throw SurgeryPlanExportError.invalidAnimalRecord(
                "\(field) cannot contain line breaks or control characters."
            )
        }
        return normalized
    }
}

struct SurgeryPlanExportResult: Sendable {
    let outputURL: URL
    let pageCount: Int
    let atlasPlate: SurgeryAtlasPlate
    let atlasSourceSHA256: String
    let exportClass: SurgeryPlanExportClass
}

enum SurgeryPlanExportError: Error, LocalizedError {
    case noProject
    case targetUnavailable
    case unappliedProbeDraft
    case invalidAnimalRecord(String)
    case vesselsUnavailable
    case viewUnavailable(String)
    case invalidProtocolTemplate(String)
    case invalidAtlasSource(String)
    case atlasCoordinateOutsideRange(String)
    case invalidAtlasPage(String)
    case targetProjectionUnavailable
    case stateChangedDuringExport
    case vesselIdentityMismatch
    case pdfAssemblyFailed(String)
    case outputWriteFailed

    var errorDescription: String? {
        switch self {
        case .noProject:
            "Open an animal plan before exporting."
        case .targetUnavailable:
            "Select a stored implant target before exporting."
        case .unappliedProbeDraft:
            "Finish the numeric edit with Return or leave the field, then wait "
                + "for the probe update before exporting the surgery plan."
        case let .invalidAnimalRecord(message):
            "The animal record is not usable: \(message)"
        case .vesselsUnavailable:
            "The reviewed major-vessel reference must finish loading before export."
        case let .viewUnavailable(view):
            "\(view) is not ready. Load it or choose a different export selection."
        case let .invalidProtocolTemplate(message):
            "The surgery protocol template is not usable: \(message)"
        case let .invalidAtlasSource(message):
            "The Mouse Brain atlas PDF is not usable: \(message)"
        case let .atlasCoordinateOutsideRange(coordinate):
            "The requested \(coordinate) is outside the supplied atlas plate range."
        case let .invalidAtlasPage(message):
            "The selected historical atlas page failed validation: \(message)"
        case .targetProjectionUnavailable:
            "Project the selected target with the active calibration before exporting."
        case .stateChangedDuringExport:
            "The animal plan changed during export. Review it and export again."
        case .vesselIdentityMismatch:
            "A planning page did not retain the reviewed major-vessel source identity."
        case let .pdfAssemblyFailed(message):
            "The surgery-plan PDF could not be assembled: \(message)"
        case .outputWriteFailed:
            "The surgery-plan PDF could not be written to the selected location."
        }
    }
}

struct SurgeryPlanningViewArtifact: Sendable {
    let view: SurgeryPlanView
    let pngData: Data
    let subtitle: String
    let vesselAssetSHA256: String
    let vesselSegmentCount: Int
    let vesselScope: String
    let minimumVisibleVesselDiameterMicrometres: Double
}

struct SurgeryPlanProbeDraftIdentity: Equatable, Sendable {
    let editableRevision: Int
    let hasUnappliedChanges: Bool

    @MainActor
    func isCurrent(in model: PlannerViewModel) -> Bool {
        model.probeDraftSession.editableRevision == editableRevision
            && model.hasUnappliedProbeDraftChanges == hasUnappliedChanges
    }
}

enum SurgeryPlanDraftSafety {
    @MainActor
    static func captureCurrent(
        in model: PlannerViewModel
    ) throws -> SurgeryPlanProbeDraftIdentity {
        let identity = SurgeryPlanProbeDraftIdentity(
            editableRevision: model.probeDraftSession.editableRevision,
            hasUnappliedChanges: model.hasUnappliedProbeDraftChanges
        )
        guard !identity.hasUnappliedChanges else {
            throw SurgeryPlanExportError.unappliedProbeDraft
        }
        return identity
    }
}

struct SurgeryPlanImplantSite: Equatable, Sendable {
    let targetId: String
    let label: String
    let apMillimetres: Double
    let mlMillimetres: Double
    let dvMillimetres: Double?
    let point: ProbePhysicalPoint

    init(
        target: UnprojectedImplantTarget,
        projection: CalibratedTargetProjectionResult
    ) {
        targetId = target.targetId
        label = target.label
        apMillimetres = target.apMillimetres
        mlMillimetres = target.mlMillimetres
        dvMillimetres = target.dvMillimetres
        point = ProbePhysicalPoint(calibratedTargetProjection: projection)
    }

    init(surfacePlan plan: ProbePlanDetail) throws {
        guard let input = plan.surfaceRelativeInput,
              input.mode == .atlasSurfaceAPML,
              plan.placementMode == .atlasSurfaceAPML
        else {
            throw SurgeryPlanExportError.targetProjectionUnavailable
        }
        targetId = plan.planId
        label = plan.name
        apMillimetres = input.insertionAPMillimetres
        mlMillimetres = input.insertionMLMillimetres
        dvMillimetres = nil
        point = plan.placement.atlasFrame.entry
    }
}

struct SurgeryPlanModelCapture {
    let project: ProjectBridgeState
    let target: SurgeryPlanImplantSite
    let projection: CalibratedTargetProjectionResult?
    let calibration: CalibrationSummary?
    let probePlan: ProbePlanDetail?
    let selectedPlanIdentity: String?
    let majorVessels: MajorVesselGeometryResult
    let minimumVisibleVesselDiameterMicrometres: Double
    let atlas: ViewerAtlasIdentity
    let dorsalSurface: AtlasDorsalResult?
    let dorsalPNG: Data?
    let sliceFrames: [SurgeryPlanView: VerifiedAtlasSliceFrame]
    let selectedRegion: AtlasRegionSummary?
    let regionOverlayPNGs: [SurgeryPlanView: Data]
    let sceneSnapshot: AnimalSceneSnapshot?
    let hasUnsavedChanges: Bool
    let probeDraftIdentity: SurgeryPlanProbeDraftIdentity

    @MainActor
    func isStillCurrent(in model: PlannerViewModel) -> Bool {
        let geometryIsCurrent: Bool
        if let projection, let calibration {
            geometryIsCurrent = model.implantTargets.contains {
                $0.targetId == target.targetId
                    && $0.apMillimetres == target.apMillimetres
                    && $0.mlMillimetres == target.mlMillimetres
                    && $0.dvMillimetres == target.dvMillimetres
            }
                && model.projection(for: target.targetId) == projection
                && model.activeCalibration == calibration
        } else {
            geometryIsCurrent =
                model.selectedProbePlan?.planId == target.targetId
                    && model.selectedProbePlan?.surfaceRelativeInput != nil
        }
        return model.backendState?.project == project
            && model.hasUnsavedChanges == hasUnsavedChanges
            && probeDraftIdentity.isCurrent(in: model)
            && geometryIsCurrent
            && Self.planIdentity(model.selectedProbePlan) == selectedPlanIdentity
            && model.highlightedAtlasRegion == selectedRegion
            && model.viewerSnapshot?.atlas.metadataSha256 == atlas.metadataSha256
            && model.majorVesselGeometry?.provenance.derivedAssetSha256
                == majorVessels.provenance.derivedAssetSha256
            && model.minimumVisibleVesselDiameterMicrometres
                == minimumVisibleVesselDiameterMicrometres
    }

    static func planIdentity(_ plan: ProbePlanDetail?) -> String? {
        guard let plan else { return nil }
        return [
            plan.planId,
            String(plan.planVersion),
            plan.inputSha256,
            plan.targetId ?? "atlas-surface",
            plan.provenance.calibrationId ?? "no-calibration",
            plan.provenance.calibrationVersion.map(String.init) ?? "no-version",
            plan.provenance.calibrationSha256 ?? "no-calibration-digest",
            plan.provenance.projectionSha256,
        ].joined(separator: ":")
    }
}

enum SurgeryProtocolPDFTemplate {
    static let sourcePageCount = 3
    static let protocolPageCount = 2

    static func validate(_ pdf: Data) throws {
        guard !pdf.isEmpty,
              let document = PDFDocument(data: pdf),
              document.pageCount == sourcePageCount,
              (0 ..< sourcePageCount).allSatisfy({ index in
                  guard let page = document.page(at: index) else { return false }
                  let size = page.bounds(for: .mediaBox).size
                  return Int(size.width.rounded()) == 612
                      && Int(size.height.rounded()) == 792
              }),
              document.string?.localizedCaseInsensitiveContains(
                  "Surgery Record"
              ) == true,
              document.string?.localizedCaseInsensitiveContains(
                  "Surgery procedure"
              ) == true
        else {
            throw SurgeryPlanExportError.invalidProtocolTemplate(
                "Headplate Protocol.pdf must contain two protocol pages and one Letter-size atlas placeholder."
            )
        }
    }
}

enum SurgeryProtocolPDFRenderer {
    static func overlay(
        protocolPDF: Data,
        prefill: SurgeryPlanPrefill
    ) throws -> Data {
        guard let source = PDFDocument(data: protocolPDF),
              source.pageCount == SurgeryProtocolPDFTemplate.sourcePageCount
        else {
            throw SurgeryPlanExportError.invalidProtocolTemplate(
                "The supplied protocol PDF is not the verified three-page template."
            )
        }
        let output = NSMutableData()
        var mediaBox = CGRect(x: 0, y: 0, width: 612, height: 792)
        guard let consumer = CGDataConsumer(data: output as CFMutableData),
              let context = CGContext(
                  consumer: consumer,
                  mediaBox: &mediaBox,
                  nil
              )
        else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "Could not create the protocol-page PDF context."
            )
        }
        for index in 0 ..< SurgeryProtocolPDFTemplate.protocolPageCount {
            guard let page = source.page(at: index) else {
                throw SurgeryPlanExportError.pdfAssemblyFailed(
                    "Protocol page \(index + 1) became unavailable."
                )
            }
            context.beginPDFPage(nil)
            page.draw(with: .mediaBox, to: context)
            if index == 0 {
                let graphics = NSGraphicsContext(cgContext: context, flipped: false)
                NSGraphicsContext.saveGraphicsState()
                NSGraphicsContext.current = graphics
                drawProtocolPrefill(prefill)
                NSGraphicsContext.restoreGraphicsState()
            }
            context.endPDFPage()
        }
        context.closePDF()
        let data = output as Data
        let requiredCoordinateText: [String] = [
            String(format: "%+.3f mm", prefill.apMillimetres),
            String(format: "%+.3f mm", prefill.mlMillimetres),
        ] + [
            prefill.surfaceDepthMillimetres.map {
                String(format: "%.3f mm", $0)
            } ?? prefill.dvMillimetres.map {
                String(format: "%+.3f mm", $0)
            } ?? ""
        ].filter { !$0.isEmpty }
        guard let verified = PDFDocument(data: data),
              verified.pageCount == SurgeryProtocolPDFTemplate.protocolPageCount,
              let verifiedText = verified.string,
              [
                  prefill.exportClass.rawValue,
                  prefill.date,
                  protocolSubjectLine(prefill.subjectId),
              ].allSatisfy(verifiedText.contains),
              requiredCoordinateText.allSatisfy(verifiedText.contains)
        else {
            throw SurgeryPlanExportError.invalidProtocolTemplate(
                "Required date, subject, AP/ML/DV, or export status did not survive PDF prefill."
            )
        }
        return data
    }

    private static func drawProtocolPrefill(_ prefill: SurgeryPlanPrefill) {
        field(
            prefill.exportClass.rawValue,
            rect: CGRect(x: 142, y: 714, width: 70, height: 15),
            font: .systemFont(ofSize: 9, weight: .bold),
            color: prefill.exportClass == .draft ? .systemOrange : .systemGreen
        )
        field(
            prefill.date,
            rect: CGRect(x: 451, y: 708, width: 78, height: 15),
            font: .monospacedSystemFont(ofSize: 8.5, weight: .medium)
        )

        // Replace the template's tightly spaced blank fields as complete rows.
        // Painting individual values into the original underlines lets long
        // labels collide with "AP / ML / Depth / Angle"; a single clean band
        // keeps every unit and sign legible on the actual supplied PDF.
        // The original labels extend several points to the left of their
        // underlines and span all four rows. Clear the complete header block
        // once so no template glyph can survive beside the replacement text.
        protocolBand(CGRect(x: 30, y: 584, width: 576, height: 120))
        protocolText(
            "Purpose: Implantation · Target: "
                + shortened(prefill.targetLabel, maximumCharacters: 42),
            at: CGPoint(x: 50, y: 688),
            font: .systemFont(ofSize: 8.8, weight: .semibold),
            maximumWidth: 520
        )
        protocolText(
            "\(prefill.targetCoordinateText) · \(compactAngle(prefill))",
            at: CGPoint(x: 50, y: 674),
            font: .monospacedSystemFont(ofSize: 8, weight: .medium),
            maximumWidth: 520
        )

        protocolText(
            protocolSubjectLine(prefill.subjectId),
            at: CGPoint(x: 50, y: 650),
            font: .systemFont(ofSize: 9, weight: .medium),
            maximumWidth: 520
        )

        protocolText(
            "Cage #: \(blankOrValue(prefill.cageId))",
            at: CGPoint(x: 50, y: 624),
            font: .systemFont(ofSize: 9, weight: .medium),
            maximumWidth: 235
        )
        let operatorName = prefill.operatorName
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if !operatorName.isEmpty {
            protocolText(
                "Operator: " + shortened(operatorName, maximumCharacters: 32),
                at: CGPoint(x: 300, y: 624),
                font: .systemFont(ofSize: 9, weight: .medium),
                maximumWidth: 270
            )
        }

        protocolText(
            "Mouse #: \(blankOrValue(prefill.mouseNumber)) · Weight: "
                + "\(blankOrValue(prefill.weightGrams)) g",
            at: CGPoint(x: 50, y: 597),
            font: .systemFont(ofSize: 9, weight: .medium),
            maximumWidth: 520
        )
    }

    private static func field(
        _ text: String,
        rect: CGRect,
        font: NSFont,
        color: NSColor = .black
    ) {
        NSColor.white.setFill()
        rect.fill()
        NSAttributedString(
            string: text,
            attributes: [.font: font, .foregroundColor: color]
        ).draw(in: rect)
    }

    private static func protocolBand(_ rect: CGRect) {
        NSColor.white.setFill()
        rect.fill()
    }

    private static func protocolText(
        _ text: String,
        at point: CGPoint,
        font: NSFont,
        maximumWidth: CGFloat,
        color: NSColor = .black
    ) {
        let attributes: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: color,
        ]
        let visibleText = textFittedToWidth(
            text,
            maximumWidth: maximumWidth,
            attributes: attributes
        )
        NSAttributedString(
            string: visibleText,
            attributes: attributes
        ).draw(at: point)
    }

    static func textFittedToWidth(
        _ text: String,
        maximumWidth: CGFloat,
        attributes: [NSAttributedString.Key: Any]
    ) -> String {
        func renderedWidth(_ value: String) -> CGFloat {
            NSAttributedString(string: value, attributes: attributes).size().width
        }

        guard renderedWidth(text) > maximumWidth else { return text }
        var prefix = Array(text)
        while !prefix.isEmpty {
            prefix.removeLast()
            let candidate = String(prefix) + "…"
            if renderedWidth(candidate) <= maximumWidth {
                return candidate
            }
        }
        return "…"
    }

    private static func protocolSubjectLine(_ subjectId: String) -> String {
        "Mouse / subject: " + shortened(subjectId, maximumCharacters: 30)
    }

    private static func blankOrValue(_ value: String) -> String {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? "________" : normalized
    }

    private static func shortened(
        _ value: String,
        maximumCharacters: Int
    ) -> String {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.count > maximumCharacters else { return normalized }
        return String(normalized.prefix(maximumCharacters - 1)) + "…"
    }

    private static func compactAngle(_ prefill: SurgeryPlanPrefill) -> String {
        if let angle = prefill.sagittalAngleDegrees {
            return SurgeryPlanSurfaceAnglePresentation.text(angle)
        }
        guard let azimuth = prefill.azimuthDegrees,
              let elevation = prefill.elevationDegrees
        else { return "________" }
        return String(format: "Az %+.1f° · El %+.1f°", azimuth, elevation)
    }
}

@MainActor
enum SurgeryPlanningViewRenderer {
    private static let exportSize = NSSize(width: 1_200, height: 820)

    static func render(
        view requestedView: SurgeryPlanView,
        capture: SurgeryPlanModelCapture
    ) async throws -> SurgeryPlanningViewArtifact {
        if requestedView == .threeDimensional {
            let expectedImplantSite = ImplantSiteSceneMarker(
                targetId: capture.target.targetId,
                label: capture.target.label,
                point: capture.target.point
            )
            guard let snapshot = capture.sceneSnapshot,
                  let vessels = snapshot.majorVessels,
                  snapshot.implantSite == expectedImplantSite,
                  vessels.provenance.derivedAssetSha256
                    == capture.majorVessels.provenance.derivedAssetSha256,
                  snapshot.minimumVisibleVesselDiameterMicrometres
                    == capture.minimumVisibleVesselDiameterMicrometres
            else {
                throw SurgeryPlanExportError.vesselIdentityMismatch
            }
            guard vessels.segmentCount > 0 else {
                throw SurgeryPlanExportError.viewUnavailable(requestedView.rawValue)
            }
            let visibleSegmentCount =
                MajorVesselDisplayFilter.visibleSegmentCount(
                    graph: vessels.graph,
                    minimumDiameterMicrometres:
                        capture.minimumVisibleVesselDiameterMicrometres
                )
            guard visibleSegmentCount > 0 else {
                throw SurgeryPlanExportError.viewUnavailable(requestedView.rawValue)
            }
            let image = try await AnimalSceneSnapshotRenderer.render(
                snapshot: snapshot,
                size: exportSize
            )
            guard let png = image.pngData else {
                throw SurgeryPlanExportError.viewUnavailable(requestedView.rawValue)
            }
            return SurgeryPlanningViewArtifact(
                view: requestedView,
                pngData: png,
                subtitle: "Standard home-camera snapshot · captured target/probe state",
                vesselAssetSHA256: vessels.provenance.derivedAssetSha256,
                vesselSegmentCount: visibleSegmentCount,
                vesselScope: "whole-brain reference",
                minimumVisibleVesselDiameterMicrometres:
                    capture.minimumVisibleVesselDiameterMicrometres
            )
        }

        let imageData: Data
        let width: Int
        let height: Int
        let labels: AtlasCanvasAnatomicalLabels
        let vesselOverlay: MajorVesselSliceOverlay
        let probeOverlay: ProbeSliceOverlay?
        let subtitle: String
        let vesselScope: String

        if requestedView == .dorsal {
            guard let dorsal = capture.dorsalSurface,
                  let dorsalPNG = capture.dorsalPNG
            else {
                throw SurgeryPlanExportError.viewUnavailable(requestedView.rawValue)
            }
            imageData = dorsalPNG
            width = dorsal.width
            height = dorsal.height
            labels = .dorsal
            vesselOverlay = MajorVesselSliceOverlayGeometry.makeDorsalProjection(
                geometry: capture.majorVessels,
                minimumVisibleDiameterMicrometres:
                    capture.minimumVisibleVesselDiameterMicrometres
            )
            let planOverlay = capture.probePlan.flatMap {
                ProbeSliceOverlayGeometry.makeDorsalProjection(
                    plan: $0,
                    resolution: capture.atlas.resolutionMicrometres,
                    shape: capture.atlas.shapeVoxels
                )
            }
            let implantSiteOverlay =
                ProbeSliceOverlayGeometry.makeImplantSiteDorsalProjection(
                    targetId: capture.target.targetId,
                    label: capture.target.label,
                    point: capture.target.point,
                    resolution: capture.atlas.resolutionMicrometres,
                    shape: capture.atlas.shapeVoxels
                )
            probeOverlay = ProbeSliceOverlayGeometry.combine(
                [planOverlay, implantSiteOverlay],
                orientation: .horizontal,
                sliceIndex: 0
            )
            subtitle = "Allen atlas dorsal surface projection · not a subject skull surface"
            vesselScope = "dorsal depth projection"
        } else {
            guard let orientation = requestedView.sliceOrientation,
                  let frame = capture.sliceFrames[requestedView]
            else {
                throw SurgeryPlanExportError.viewUnavailable(requestedView.rawValue)
            }
            imageData = frame.png
            width = frame.width
            height = frame.height
            labels = .slice(orientation)
            vesselOverlay = MajorVesselSliceOverlayGeometry.make(
                geometry: capture.majorVessels,
                orientation: orientation,
                sliceIndex: frame.index,
                minimumVisibleDiameterMicrometres:
                    capture.minimumVisibleVesselDiameterMicrometres
            )
            let planOverlay = capture.probePlan.flatMap {
                ProbeSliceOverlayGeometry.make(
                    plan: $0,
                    orientation: orientation,
                    sliceIndex: frame.index,
                    resolution: capture.atlas.resolutionMicrometres,
                    shape: capture.atlas.shapeVoxels
                )
            }
            let implantSiteOverlay = ProbeSliceOverlayGeometry.makeImplantSite(
                targetId: capture.target.targetId,
                label: capture.target.label,
                point: capture.target.point,
                orientation: orientation,
                sliceIndex: frame.index,
                resolution: capture.atlas.resolutionMicrometres,
                shape: capture.atlas.shapeVoxels
            )
            probeOverlay = ProbeSliceOverlayGeometry.combine(
                [planOverlay, implantSiteOverlay],
                orientation: orientation,
                sliceIndex: frame.index
            )
            let sliceAnchor = capture.probePlan?.surfaceRelativeInput == nil
                ? "Target-centred"
                : "Insertion-site-centred"
            let slicePosition = String(
                format: "%.3f",
                frame.sliceCenterMicrometres / 1_000
            )
            subtitle = "\(sliceAnchor) slice \(frame.index + 1) "
                + "of \(frame.sliceCount) · \(frame.fixedAxis.rawValue) "
                + "\(slicePosition) mm in atlas physical space"
            vesselScope = "target-slice slab"
        }

        guard vesselOverlay.assetSHA256
            == capture.majorVessels.provenance.derivedAssetSha256
        else {
            throw SurgeryPlanExportError.vesselIdentityMismatch
        }
        let raster = await Task.detached(priority: .userInitiated) {
            MajorVesselRasterizer.render(
                overlay: vesselOverlay,
                imagePixelWidth: width,
                imagePixelHeight: height
            )
        }.value
        guard let raster else {
            throw SurgeryPlanExportError.viewUnavailable(
                "\(requestedView.rawValue) major-vessel overlay"
            )
        }
        MajorVesselRasterCache.insert(
            raster,
            overlay: vesselOverlay,
            imagePixelWidth: width,
            imagePixelHeight: height
        )

        let canvas = AtlasSliceNSView(
            frame: NSRect(origin: .zero, size: exportSize)
        )
        canvas.configure(
            imageData: imageData,
            regionOverlayData: capture.regionOverlayPNGs[requestedView],
            imagePixelWidth: width,
            imagePixelHeight: height,
            viewportIdentity: "surgery-export-\(requestedView.rawValue)",
            anatomicalLabels: labels,
            selection: nil,
            majorVesselOverlay: vesselOverlay,
            majorVesselConflictOverlay: nil,
            probeOverlay: probeOverlay,
            interactionHelp: "",
            accessibilityLabel: "\(requestedView.rawValue) surgery-plan export",
            accessibilityValue: subtitle,
            resetGeneration: 0,
            onPick: { _, _ in },
            onSliceStep: { _ in }
        )
        canvas.layoutSubtreeIfNeeded()
        canvas.display()
        guard let representation = canvas.bitmapImageRepForCachingDisplay(
            in: canvas.bounds
        ) else {
            canvas.prepareForDismantling()
            throw SurgeryPlanExportError.viewUnavailable(requestedView.rawValue)
        }
        canvas.cacheDisplay(in: canvas.bounds, to: representation)
        canvas.prepareForDismantling()
        guard let png = representation.representation(
            using: .png,
            properties: [:]
        ) else {
            throw SurgeryPlanExportError.viewUnavailable(requestedView.rawValue)
        }
        return SurgeryPlanningViewArtifact(
            view: requestedView,
            pngData: png,
            subtitle: subtitle,
            vesselAssetSHA256: vesselOverlay.assetSHA256,
            vesselSegmentCount: vesselOverlay.segments.count,
            vesselScope: vesselScope,
            minimumVisibleVesselDiameterMicrometres:
                vesselOverlay.minimumVisibleDiameterMicrometres
        )
    }
}

enum SurgeryPlanningPageRenderer {
    static func render(
        artifact: SurgeryPlanningViewArtifact,
        prefill: SurgeryPlanPrefill,
        atlasPlate: SurgeryAtlasPlate,
        atlasSourceSHA256: String,
        protocolSourceSHA256: String,
        vesselSource: String
    ) throws -> Data {
        let output = NSMutableData()
        var mediaBox = CGRect(x: 0, y: 0, width: 792, height: 612)
        guard let consumer = CGDataConsumer(data: output as CFMutableData),
              let context = CGContext(
                  consumer: consumer,
                  mediaBox: &mediaBox,
                  nil
              ),
              let image = NSImage(data: artifact.pngData)
        else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "Could not create the \(artifact.view.rawValue) planning page."
            )
        }

        context.beginPDFPage(nil)
        let graphics = NSGraphicsContext(cgContext: context, flipped: false)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = graphics
        NSColor.white.setFill()
        mediaBox.fill()

        draw(
            "\(prefill.exportClass.rawValue) · Surgery planning view — \(artifact.view.rawValue)",
            at: CGPoint(x: 38, y: 568),
            font: .systemFont(ofSize: 17, weight: .bold),
            color: prefill.exportClass == .draft ? .systemOrange : .black
        )
        let planningIdentity = fittedPlanningIdentityText(
            subjectId: prefill.subjectId,
            targetLabel: prefill.targetLabel,
            maximumWidth: 716
        )
        draw(
            planningIdentity,
            at: CGPoint(x: 38, y: 548),
            font: planningIdentityFont
        )
        draw(
            prefill.targetCoordinateText,
            at: CGPoint(x: 38, y: 533),
            font: .monospacedSystemFont(ofSize: 10, weight: .semibold)
        )
        let operatorIdentity = prefill.operatorName
            .trimmingCharacters(in: .whitespacesAndNewlines)
        draw(
            operatorIdentity.isEmpty
                ? artifact.subtitle
                : "\(artifact.subtitle) · operator \(operatorIdentity)",
            at: CGPoint(x: 38, y: 518),
            font: .systemFont(ofSize: 9),
            color: NSColor(calibratedWhite: 0.32, alpha: 1)
        )

        // Reserve a deterministic metadata block below the image. In
        // particular, the full NPX2 four-shank identity legitimately occupies
        // two lines; giving it a single 18-point row caused it to overwrite the
        // vessel disclosure in real exports.
        let imageBounds = CGRect(x: 38, y: 181, width: 716, height: 323)
        NSColor(calibratedWhite: 0.96, alpha: 1).setFill()
        imageBounds.fill()
        image.draw(
            in: aspectFit(sourceSize: image.size, destination: imageBounds),
            from: .zero,
            operation: .copy,
            fraction: 1,
            respectFlipped: true,
            hints: [.interpolation: NSImageInterpolation.high]
        )

        draw(
            prefill.probeText,
            in: CGRect(x: 38, y: 151, width: 716, height: 25),
            font: .monospacedSystemFont(ofSize: 8.1, weight: .regular)
        )
        if let review = prefill.probeReviewText {
            draw(
                review,
                in: CGRect(x: 38, y: 136, width: 716, height: 13),
                font: .systemFont(ofSize: 7.2, weight: .semibold),
                color: .systemOrange
            )
        }
        draw(
            "Major vessels: \(vesselSource) · \(artifact.vesselSegmentCount) "
                + "\(artifact.vesselScope) segments · display ≥"
                + "\(Int(artifact.minimumVisibleVesselDiameterMicrometres.rounded())) µm · "
                + "asset "
                + "\(artifact.vesselAssetSHA256.prefix(12))…",
            in: CGRect(x: 38, y: 120, width: 716, height: 14),
            font: .monospacedSystemFont(ofSize: 7.2, weight: .semibold),
            color: .systemRed
        )
        draw(
            "Single ex-vivo reference, not this animal; source <30 µm omitted; "
                + "display filter does not alter provenance; "
                + "zero visible intersections never establishes vessel absence or clearance.",
            in: CGRect(x: 38, y: 103, width: 716, height: 14),
            font: .systemFont(ofSize: 7.2, weight: .semibold),
            color: .systemRed
        )
        let requested = atlasPlate.orientation == .coronal
            ? prefill.apMillimetres
            : abs(prefill.mlMillimetres)
        let requestedAxis = atlasPlate.orientation == .coronal
            ? String(format: "AP %+.3f mm", requested)
            : String(
                format: "|ML| %.3f mm (%@)",
                requested,
                prefill.mlMillimetres < 0
                    ? "left, ML−"
                    : "right, ML+"
            )
        draw(
            String(
                format:
                    "Final atlas: %@ · requested %@ · plate %.2f mm · Δ %.3f mm · atlas %@… · protocol %@…",
                atlasPlate.displayName,
                requestedAxis,
                atlasPlate.fixedCoordinateMillimetres,
                atlasPlate.fixedCoordinateMillimetres - requested,
                String(atlasSourceSHA256.prefix(10)),
                String(protocolSourceSHA256.prefix(10))
            ),
            in: CGRect(x: 38, y: 86, width: 716, height: 14),
            font: .monospacedSystemFont(ofSize: 7.0, weight: .regular),
            color: NSColor(calibratedWhite: 0.32, alpha: 1)
        )
        draw(
            prefill.surfaceDepthMillimetres == nil
                ? "Bregma signs: −AP posterior/back · −ML left · −DV deep/ventral · AP/ML/DV in mm; angles in degrees"
                : "Bregma signs: +AP anterior / −AP posterior · +ML right / −ML left · depth from local atlas surface · angles in degrees",
            in: CGRect(x: 38, y: 69, width: 716, height: 14),
            font: .systemFont(ofSize: 7.2, weight: .medium),
            color: NSColor(calibratedWhite: 0.32, alpha: 1)
        )
        draw(
            "Animal research only · independently verify coordinates, probe, protocol, and vasculature before the procedure · project revision \(prefill.projectRevision)",
            in: CGRect(x: 38, y: 52, width: 716, height: 14),
            font: .systemFont(ofSize: 7.4, weight: .semibold),
            color: .systemOrange
        )
        NSGraphicsContext.restoreGraphicsState()
        context.endPDFPage()
        context.closePDF()
        let data = output as Data
        let expectedTitle =
            "\(prefill.exportClass.rawValue) · Surgery planning view — "
                + artifact.view.rawValue
        guard let verified = PDFDocument(data: data),
              verified.pageCount == 1,
              let verifiedPage = verified.page(at: 0),
              verifiedPage.bounds(for: .mediaBox).size == mediaBox.size,
              let verifiedText = verified.string,
              verifiedText.contains(expectedTitle),
              verifiedText.contains(prefill.targetCoordinateText)
        else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "\(artifact.view.rawValue) planning page did not retain "
                    + "its title and full AP/ML/DV coordinates."
            )
        }
        return data
    }

    private static func aspectFit(
        sourceSize: NSSize,
        destination: CGRect
    ) -> CGRect {
        guard sourceSize.width > 0, sourceSize.height > 0 else { return destination }
        let scale = min(
            destination.width / sourceSize.width,
            destination.height / sourceSize.height
        )
        let size = CGSize(
            width: sourceSize.width * scale,
            height: sourceSize.height * scale
        )
        return CGRect(
            x: destination.midX - size.width / 2,
            y: destination.midY - size.height / 2,
            width: size.width,
            height: size.height
        )
    }

    private static var planningIdentityFont: NSFont {
        .monospacedSystemFont(ofSize: 9.5, weight: .semibold)
    }

    static func fittedPlanningIdentityText(
        subjectId: String,
        targetLabel: String,
        maximumWidth: CGFloat
    ) -> String {
        let identity = [
            singleLineIdentityComponent(subjectId),
            singleLineIdentityComponent(targetLabel),
        ].joined(separator: " · ")
        return SurgeryProtocolPDFRenderer.textFittedToWidth(
            identity,
            maximumWidth: maximumWidth,
            attributes: [
                .font: planningIdentityFont,
                .foregroundColor: NSColor.black,
            ]
        )
    }

    private static func singleLineIdentityComponent(_ text: String) -> String {
        text.components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private static func draw(
        _ text: String,
        at point: CGPoint,
        font: NSFont,
        color: NSColor = .black
    ) {
        NSAttributedString(
            string: text,
            attributes: [.font: font, .foregroundColor: color]
        ).draw(at: point)
    }

    private static func draw(
        _ text: String,
        in rect: CGRect,
        font: NSFont,
        color: NSColor = .black
    ) {
        NSAttributedString(
            string: text,
            attributes: [.font: font, .foregroundColor: color]
        ).draw(in: rect)
    }
}

struct SurgeryAtlasPDFSnapshot: Sendable {
    let sourcePDF: Data
    let sha256: String
}

actor SurgeryAtlasPDFSource {
    static let shared = SurgeryAtlasPDFSource()

    func capture(_ plate: SurgeryAtlasPlate) throws -> SurgeryAtlasPDFSnapshot {
        let sourceData: Data
        do {
            sourceData = try Data(contentsOf: plate.sourceURL)
        } catch {
            throw SurgeryPlanExportError.invalidAtlasSource(
                error.localizedDescription
            )
        }
        let sourceSHA256 = LowercaseHex.encode(SHA256.hash(data: sourceData))
        guard sourceData.starts(with: Data("%PDF-".utf8)),
              let document = PDFDocument(data: sourceData),
              document.pageCount == 132
        else {
            throw SurgeryPlanExportError.invalidAtlasSource(
                "Expected one readable 132-page PDF."
            )
        }

        let canonicalPlates = SurgeryAtlasCatalog.canonicalPlates(
            sourceURL: plate.sourceURL
        )
        for (index, expectedPlate) in canonicalPlates.enumerated() {
            guard let page = document.page(at: index),
                  Self.isLandscapeLetter(page.bounds(for: .mediaBox).size)
            else {
                throw SurgeryPlanExportError.invalidAtlasSource(
                    "Page \(index + 1) is not 792 × 612 point landscape Letter."
                )
            }
            guard Self.validatesPageText(
                page.string ?? "",
                plate: expectedPlate
            ) else {
                throw SurgeryPlanExportError.invalidAtlasSource(
                    "Page \(index + 1) does not match "
                        + "\(expectedPlate.displayName)."
                )
            }
        }
        return SurgeryAtlasPDFSnapshot(
            sourcePDF: sourceData,
            sha256: sourceSHA256
        )
    }

    func sourceIsUnchanged(
        at url: URL,
        expectedSHA256: String
    ) -> Bool {
        guard let data = try? Data(contentsOf: url) else { return false }
        let currentSHA256 = LowercaseHex.encode(SHA256.hash(data: data))
        return currentSHA256 == expectedSHA256
    }

    nonisolated static func isLandscapeLetter(_ size: CGSize) -> Bool {
        abs(size.width - 792) < 0.05 && abs(size.height - 612) < 0.05
    }

    nonisolated static func validatesPageText(
        _ pageText: String,
        plate: SurgeryAtlasPlate
    ) -> Bool {
        let normalized = pageText.replacingOccurrences(
            of: #"\s+"#,
            with: " ",
            options: .regularExpression
        )
        let figurePattern = #"(?i)\bfigure\s+0*"# + String(plate.figure) + #"\b"#
        guard normalized.range(
            of: figurePattern,
            options: .regularExpression
        ) != nil else { return false }

        func coordinatePattern(
            label: String,
            value: Double,
            optionalMM: Bool
        ) -> String {
            let magnitude = String(format: "%.2f", abs(value))
            let escaped = NSRegularExpression.escapedPattern(for: magnitude)
            let sign = value < 0 ? #"-\s*"# : #"(?:\+\s*)?"#
            let unit = optionalMM ? #"(?:\s*mm)?"# : #"\s*mm"#
            return #"(?i)\b"# + label + #"\s+"# + sign + escaped + unit
        }

        switch plate.orientation {
        case .coronal:
            let bregma = coordinatePattern(
                label: "Bregma",
                value: plate.fixedCoordinateMillimetres,
                optionalMM: false
            )
            // This historical atlas defines Bregma = Interaural − 3.80 mm.
            let interaural = coordinatePattern(
                label: "Interaural",
                value: plate.fixedCoordinateMillimetres + 3.80,
                optionalMM: false
            )
            return normalized.range(of: bregma, options: .regularExpression) != nil
                && normalized.range(of: interaural, options: .regularExpression) != nil
        case .sagittal:
            let lateral = coordinatePattern(
                label: "Lateral",
                value: plate.fixedCoordinateMillimetres,
                optionalMM: true
            )
            return normalized.range(of: lateral, options: .regularExpression) != nil
        }
    }
}

enum SurgeryAtlasPageRenderer {
    static func overlay(
        atlasPDF: Data,
        prefill: SurgeryPlanPrefill,
        plate: SurgeryAtlasPlate,
        atlasSourceSHA256: String
    ) throws -> Data {
        guard let source = PDFDocument(data: atlasPDF),
              source.pageCount == 132,
              let page = source.page(at: plate.figure - 1),
              SurgeryAtlasPDFSource.isLandscapeLetter(
                  page.bounds(for: .mediaBox).size
              )
        else {
            throw SurgeryPlanExportError.invalidAtlasPage(
                "Could not read page \(plate.figure) from the consolidated PDF."
            )
        }
        let reviewRect = CGRect(x: 50, y: 518, width: 690, height: 13)
        let reviewFont: NSFont?
        if let review = prefill.probeReviewText {
            reviewFont = try fittedSingleLineFont(
                for: review,
                baseFont: .systemFont(ofSize: 6.8, weight: .semibold),
                minimumFontSize: 5.5,
                maximumWidth: reviewRect.width,
                field: "probe review"
            )
        } else {
            reviewFont = nil
        }
        let provenanceRect = CGRect(x: 50, y: 503, width: 690, height: 13)
        let provenanceFont: NSFont?
        if let provenance = prefill.surfaceProvenanceText {
            provenanceFont = try fittedSingleLineFont(
                for: provenance,
                baseFont: .monospacedSystemFont(ofSize: 5.8, weight: .regular),
                minimumFontSize: 4.8,
                maximumWidth: provenanceRect.width,
                field: "surface provenance"
            )
        } else {
            provenanceFont = nil
        }
        let output = NSMutableData()
        var mediaBox = CGRect(x: 0, y: 0, width: 792, height: 612)
        guard let consumer = CGDataConsumer(data: output as CFMutableData),
              let context = CGContext(
                  consumer: consumer,
                  mediaBox: &mediaBox,
                  nil
              )
        else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "Could not create the historical-atlas page context."
            )
        }
        context.beginPDFPage(nil)
        let sourceBox = page.bounds(for: .mediaBox)
        context.saveGState()
        context.translateBy(x: -sourceBox.minX, y: -sourceBox.minY)
        page.draw(with: .mediaBox, to: context)
        context.restoreGState()
        let graphics = NSGraphicsContext(cgContext: context, flipped: false)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = graphics

        let box = NSBezierPath(
            roundedRect: CGRect(x: 38, y: 486, width: 716, height: 100),
            xRadius: 8,
            yRadius: 8
        )
        NSColor(calibratedWhite: 0.98, alpha: 0.96).setFill()
        NSColor(calibratedWhite: 0.72, alpha: 1).setStroke()
        box.lineWidth = 1
        box.fill()
        box.stroke()
        draw(
            "\(prefill.exportClass.rawValue) · \(prefill.subjectId) · "
                + "\(prefill.targetLabel) · \(plate.displayName)",
            in: CGRect(x: 50, y: 563, width: 690, height: 16),
            font: .systemFont(ofSize: 11, weight: .bold),
            color: prefill.exportClass == .draft ? .systemOrange : .black
        )
        draw(
            prefill.targetCoordinateText,
            in: CGRect(x: 50, y: 548, width: 690, height: 13),
            font: .monospacedSystemFont(ofSize: 8.0, weight: .semibold)
        )
        draw(
            prefill.compactProbeText,
            in: CGRect(x: 50, y: 533, width: 690, height: 13),
            font: .monospacedSystemFont(ofSize: 7.6, weight: .medium)
        )
        if let review = prefill.probeReviewText, let reviewFont {
            drawSingleLine(
                review,
                in: reviewRect,
                font: reviewFont,
                color: .systemOrange
            )
        }
        if let provenance = prefill.surfaceProvenanceText, let provenanceFont {
            drawSingleLine(
                provenance,
                in: provenanceRect,
                font: provenanceFont,
                color: NSColor(calibratedWhite: 0.32, alpha: 1)
            )
        }
        draw(
            "Historical plate \(atlasSourceSHA256.prefix(16))… · "
                + "Coronal plate convention: Bregma = Interaural − 3.80 mm",
            in: CGRect(x: 50, y: 489, width: 690, height: 12),
            font: .monospacedSystemFont(ofSize: 6.5, weight: .regular),
            color: NSColor(calibratedWhite: 0.32, alpha: 1)
        )
        NSGraphicsContext.restoreGraphicsState()
        context.endPDFPage()
        context.closePDF()

        let data = output as Data
        guard let verified = PDFDocument(data: data),
              verified.pageCount == 1,
              let verifiedPage = verified.page(at: 0),
              verifiedPage.bounds(for: .mediaBox).size == mediaBox.size,
              data.count > 10_000,
              let verifiedText = verified.string,
              contains("Figure \(plate.figure)", in: verifiedText),
              contains(plate.coordinateLabel, in: verifiedText),
              contains(prefill.targetCoordinateText, in: verifiedText),
              contains(prefill.compactProbeText, in: verifiedText),
              containsIfPresent(prefill.probeReviewText, in: verifiedText),
              containsIfPresent(prefill.surfaceProvenanceText, in: verifiedText),
              verifiedText.contains(String(atlasSourceSHA256.prefix(16)))
        else {
            throw SurgeryPlanExportError.invalidAtlasPage(
                "The identity-linked atlas output failed verification."
            )
        }
        return data
    }

    private static func draw(
        _ text: String,
        in rect: CGRect,
        font: NSFont,
        color: NSColor = .black
    ) {
        NSAttributedString(
            string: text,
            attributes: [.font: font, .foregroundColor: color]
        ).draw(in: rect)
    }

    private static func drawSingleLine(
        _ text: String,
        in rect: CGRect,
        font: NSFont,
        color: NSColor
    ) {
        let attributed = NSAttributedString(
            string: text,
            attributes: [.font: font, .foregroundColor: color]
        )
        let size = attributed.size()
        NSGraphicsContext.saveGraphicsState()
        NSBezierPath(rect: rect).addClip()
        attributed.draw(
            at: CGPoint(
                x: rect.minX,
                y: rect.midY - size.height / 2
            )
        )
        NSGraphicsContext.restoreGraphicsState()
    }

    private static func fittedSingleLineFont(
        for text: String,
        baseFont: NSFont,
        minimumFontSize: CGFloat,
        maximumWidth: CGFloat,
        field: String
    ) throws -> NSFont {
        let measuredWidth = NSAttributedString(
            string: text,
            attributes: [.font: baseFont]
        ).size().width
        let fittedPointSize = max(
            minimumFontSize,
            min(
                baseFont.pointSize,
                baseFont.pointSize * (maximumWidth * 0.98)
                    / max(measuredWidth, 1)
            )
        )
        let fittedFont = NSFontManager.shared.convert(
            baseFont,
            toSize: fittedPointSize
        )
        let fittedWidth = NSAttributedString(
            string: text,
            attributes: [.font: fittedFont]
        ).size().width
        guard fittedWidth <= maximumWidth else {
            throw SurgeryPlanExportError.invalidAtlasPage(
                "The \(field) text is too wide for the historical-atlas identity box."
            )
        }
        return fittedFont
    }

    private static func contains(_ expected: String, in actual: String) -> Bool {
        normalized(actual).contains(normalized(expected))
    }

    private static func containsIfPresent(
        _ expected: String?,
        in actual: String
    ) -> Bool {
        expected.map { contains($0, in: actual) } ?? true
    }

    private static func normalized(_ text: String) -> String {
        text.split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")
    }
}

enum SurgeryPlanPDFAssembler {
    static func assemble(
        protocolPDF: Data,
        planningPages: [Data],
        atlasPDF: Data
    ) throws -> Data {
        guard let protocolDocument = PDFDocument(data: protocolPDF),
              protocolDocument.pageCount == 2,
              let atlasDocument = PDFDocument(data: atlasPDF),
              atlasDocument.pageCount == 1
        else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "Protocol or atlas page data could not be reopened."
            )
        }
        let output = PDFDocument()
        var insertionIndex = 0
        for pageIndex in 0 ..< protocolDocument.pageCount {
            guard let page = protocolDocument.page(at: pageIndex) else {
                throw SurgeryPlanExportError.pdfAssemblyFailed(
                    "Protocol page \(pageIndex + 1) could not be inserted."
                )
            }
            output.insert(page, at: insertionIndex)
            insertionIndex += 1
        }
        for data in planningPages {
            guard let document = PDFDocument(data: data),
                  document.pageCount == 1,
                  let page = document.page(at: 0)
            else {
                throw SurgeryPlanExportError.pdfAssemblyFailed(
                    "Planning page \(insertionIndex - 1) could not be inserted."
                )
            }
            output.insert(page, at: insertionIndex)
            insertionIndex += 1
        }
        guard let atlasPage = atlasDocument.page(at: 0) else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "The matched atlas page could not be inserted."
            )
        }
        output.insert(atlasPage, at: insertionIndex)
        guard let data = output.dataRepresentation() else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "The ordered packet could not be serialized."
            )
        }
        return data
    }
}

enum SurgeryPlanPacketRenderer {
    static func stamp(
        packetPDF: Data,
        prefill: SurgeryPlanPrefill,
        targetId: String,
        vesselAssetSHA256: String,
        protocolTemplateSHA256: String,
        atlasSourceSHA256: String
    ) throws -> Data {
        guard let source = PDFDocument(data: packetPDF),
              source.pageCount >= 3
        else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "The ordered packet could not be reopened for audit stamping."
            )
        }
        let output = PDFDocument()
        for index in 0 ..< source.pageCount {
            guard let page = source.page(at: index) else {
                throw SurgeryPlanExportError.pdfAssemblyFailed(
                    "Page \(index + 1) could not be read for audit stamping."
                )
            }
            let stamp = auditStamp(
                prefill: prefill,
                pageNumber: index + 1,
                pageCount: source.pageCount,
                targetId: targetId,
                vesselAssetSHA256: vesselAssetSHA256,
                protocolTemplateSHA256: protocolTemplateSHA256,
                atlasSourceSHA256: atlasSourceSHA256
            )
            let flattened: PDFPage
            do {
                flattened = try flattenedPage(
                    page,
                    stamp: stamp,
                    prefill: prefill
                )
            } catch {
                throw SurgeryPlanExportError.pdfAssemblyFailed(
                    "Audit stamping failed on page \(index + 1): "
                        + error.localizedDescription
                )
            }
            output.insert(flattened, at: index)
        }
        guard let data = output.dataRepresentation(),
              let verified = PDFDocument(data: data),
              verified.pageCount == source.pageCount,
              (0 ..< verified.pageCount).allSatisfy({ index in
                  auditText(
                      verified.page(at: index)?.string,
                      contains:
                      auditStamp(
                          prefill: prefill,
                          pageNumber: index + 1,
                          pageCount: verified.pageCount,
                          targetId: targetId,
                          vesselAssetSHA256: vesselAssetSHA256,
                          protocolTemplateSHA256: protocolTemplateSHA256,
                          atlasSourceSHA256: atlasSourceSHA256
                      )
                  )
              })
        else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "The stamped packet failed page-count or audit-text verification."
            )
        }
        return data
    }

    static func auditStamp(
        prefill: SurgeryPlanPrefill,
        pageNumber: Int,
        pageCount: Int,
        targetId: String,
        vesselAssetSHA256: String,
        protocolTemplateSHA256: String,
        atlasSourceSHA256: String
    ) -> String {
        let subject = limitedAuditValue(prefill.subjectId, maximumCharacters: 32)
        let stableTargetId = limitedAuditValue(targetId, maximumCharacters: 64)
        let surfaceIdentity: String
        if let plan = prefill.planInputSHA256,
           let annotation = prefill.surfaceAnnotationSHA256,
           let bregma = prefill.bregmaSourceSHA256
        {
            surfaceIdentity = "PI:\(plan.prefix(10)) | "
                + "AN:\(annotation.prefix(10)) | "
                + "BR:\(bregma.prefix(10)) | "
        } else {
            surfaceIdentity = ""
        }
        let identity = "Brain3D-\(prefill.exportClass.rawValue) | S:\(subject) | "
            + "TID:\(stableTargetId) | R:\(prefill.projectRevision) | "
            + "V:\(vesselAssetSHA256.prefix(12)) | "
            + "P:\(protocolTemplateSHA256.prefix(12)) | "
            + "A:\(atlasSourceSHA256.prefix(12)) | "
            + surfaceIdentity
            + "Pg:\(pageNumber)/\(pageCount)"
        let digest = LowercaseHex.encode(
            SHA256.hash(data: Data(identity.utf8)).prefix(8)
        )
        return "\(identity) | H:\(digest)"
    }

    private static func flattenedPage(
        _ page: PDFPage,
        stamp: String,
        prefill: SurgeryPlanPrefill
    ) throws -> PDFPage {
        let pageBox = page.bounds(for: .mediaBox)
        let output = NSMutableData()
        var mediaBox = CGRect(origin: .zero, size: pageBox.size)
        guard let consumer = CGDataConsumer(data: output as CFMutableData),
              let context = CGContext(
                  consumer: consumer,
                  mediaBox: &mediaBox,
                  nil
              )
        else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "Could not create a flattened audit-stamped page."
            )
        }
        context.beginPDFPage(nil)
        let footerClearance: CGFloat = 22
        let availableHeight = max(1, mediaBox.height - footerClearance)
        let sourceScale = min(
            mediaBox.width / pageBox.width,
            availableHeight / pageBox.height
        )
        let sourceOffsetX = (mediaBox.width - pageBox.width * sourceScale) / 2
        context.saveGState()
        context.translateBy(x: sourceOffsetX, y: footerClearance)
        context.scaleBy(x: sourceScale, y: sourceScale)
        context.translateBy(x: -pageBox.minX, y: -pageBox.minY)
        page.draw(with: .mediaBox, to: context)
        context.restoreGState()

        let graphics = NSGraphicsContext(cgContext: context, flipped: false)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = graphics
        let backgroundRect = CGRect(
            x: 10,
            y: 3,
            width: max(1, mediaBox.width - 20),
            height: 16
        )
        let background = NSBezierPath(
            roundedRect: backgroundRect,
            xRadius: 3,
            yRadius: 3
        )
        NSColor(calibratedWhite: 1, alpha: 0.96).setFill()
        NSColor(calibratedWhite: 0.65, alpha: 1).setStroke()
        background.lineWidth = 0.5
        background.fill()
        background.stroke()
        let textRect = CGRect(
            x: backgroundRect.minX + 4,
            y: backgroundRect.minY + 2,
            width: backgroundRect.width - 8,
            height: 12
        )
        guard let font = fittingAuditFont(
            for: stamp,
            maximumWidth: textRect.width
        ) else {
            NSGraphicsContext.restoreGraphicsState()
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "The audit identity is too wide for a readable footer."
            )
        }
        NSAttributedString(
            string: stamp,
            attributes: [
                .font: font,
                .foregroundColor: prefill.exportClass == .draft
                    ? NSColor.systemOrange
                    : NSColor.black,
            ]
        ).draw(in: textRect)
        NSGraphicsContext.restoreGraphicsState()
        context.endPDFPage()
        context.closePDF()

        guard let document = PDFDocument(data: output as Data),
              document.pageCount == 1,
              let flattened = document.page(at: 0),
              flattened.bounds(for: .mediaBox).size == mediaBox.size,
              auditText(flattened.string, contains: stamp)
        else {
            throw SurgeryPlanExportError.pdfAssemblyFailed(
                "The flattened page did not retain its audit identity."
            )
        }
        return flattened
    }

    static func auditText(_ text: String?, contains stamp: String) -> Bool {
        guard let text else { return false }
        func normalized(_ value: String) -> String {
            value.replacingOccurrences(
                of: #"\s+"#,
                with: " ",
                options: .regularExpression
            )
            .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        let normalizedText = normalized(text)
        let components = stamp.components(separatedBy: " | ")
        guard let identity = components.first,
              let token = components.last(where: { $0.hasPrefix("H:") })
        else {
            return normalizedText.contains(normalized(stamp))
        }
        return normalizedText.contains(normalized(identity))
            && normalizedText.contains(normalized(token))
    }

    private static func limitedAuditValue(
        _ value: String,
        maximumCharacters: Int
    ) -> String {
        let singleLine = value
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        guard singleLine.count > maximumCharacters else { return singleLine }
        return String(singleLine.prefix(maximumCharacters - 1)) + "…"
    }

    private static func fittingAuditFont(
        for text: String,
        maximumWidth: CGFloat
    ) -> NSFont? {
        var pointSize: CGFloat = 6.7
        while pointSize >= 4 {
            let font = NSFont.monospacedSystemFont(
                ofSize: pointSize,
                weight: .semibold
            )
            let width = NSAttributedString(
                string: text,
                attributes: [.font: font]
            ).size().width
            if width <= maximumWidth {
                return font
            }
            pointSize -= 0.2
        }
        return nil
    }
}

@MainActor
enum SurgeryPlanExporter {
    static func export(
        model: PlannerViewModel,
        configuration: SurgeryPlanExportConfiguration,
        outputURL: URL
    ) async throws -> SurgeryPlanExportResult {
        _ = try SurgeryPlanDraftSafety.captureCurrent(in: model)
        let configuration = try configuration.validated()
        let protocolTemplateData: Data
        do {
            guard configuration.protocolTemplateURL.pathExtension.lowercased()
                == "pdf"
            else {
                throw SurgeryPlanExportError.invalidProtocolTemplate(
                    "Choose the prepared Headplate Protocol.pdf template."
                )
            }
            protocolTemplateData = try Data(
                contentsOf: configuration.protocolTemplateURL
            )
            try SurgeryProtocolPDFTemplate.validate(protocolTemplateData)
        } catch let error as SurgeryPlanExportError {
            throw error
        } catch {
            throw SurgeryPlanExportError.invalidProtocolTemplate(
                error.localizedDescription
            )
        }
        let protocolTemplateSHA256 = LowercaseHex.encode(
            SHA256.hash(data: protocolTemplateData)
        )
        let capture = try await captureModel(
            model: model,
            configuration: configuration
        )
        let exportClass: SurgeryPlanExportClass
        if capture.probePlan?.surfaceRelativeInput != nil {
            exportClass = SurgeryPlanReadiness.exportClass(
                project: capture.project,
                hasUnsavedChanges: capture.hasUnsavedChanges,
                surfaceProbePlan: capture.probePlan
            )
        } else if let calibration = capture.calibration,
                  let projection = capture.projection
        {
            exportClass = SurgeryPlanReadiness.exportClass(
                project: capture.project,
                hasUnsavedChanges: capture.hasUnsavedChanges,
                calibration: calibration,
                projection: projection,
                probePlan: capture.probePlan
            )
        } else {
            exportClass = .draft
        }
        let prefill = makePrefill(
            project: capture.project,
            target: capture.target,
            targetLabel: configuration.targetLabel,
            matchingPlan: capture.probePlan,
            exportClass: exportClass,
            configuration: configuration
        )
        let atlasPlate = try SurgeryAtlasCatalog.nearestPlate(
            in: configuration.atlasPDFURL,
            orientation: configuration.atlasOrientation,
            apMillimetres: capture.target.apMillimetres,
            mlMillimetres: capture.target.mlMillimetres
        )
        let atlasSource = try await SurgeryAtlasPDFSource.shared.capture(
            atlasPlate
        )
        try SurgeryAtlasBundle.validateCapturedSHA256(
            atlasSource.sha256,
            requiredSHA256: configuration.requiredAtlasSourceSHA256
        )

        var artifacts: [SurgeryPlanningViewArtifact] = []
        for view in configuration.viewSelection.views {
            try Task.checkCancellation()
            artifacts.append(
                try await SurgeryPlanningViewRenderer.render(
                    view: view,
                    capture: capture
                )
            )
        }
        guard capture.isStillCurrent(in: model) else {
            throw SurgeryPlanExportError.stateChangedDuringExport
        }

        let protocolPDF = try SurgeryProtocolPDFRenderer.overlay(
            protocolPDF: protocolTemplateData,
            prefill: prefill
        )
        guard capture.isStillCurrent(in: model) else {
            throw SurgeryPlanExportError.stateChangedDuringExport
        }

        let atlasPDF = try SurgeryAtlasPageRenderer.overlay(
            atlasPDF: atlasSource.sourcePDF,
            prefill: prefill,
            plate: atlasPlate,
            atlasSourceSHA256: atlasSource.sha256
        )
        guard capture.isStillCurrent(in: model) else {
            throw SurgeryPlanExportError.stateChangedDuringExport
        }
        guard await SurgeryAtlasPDFSource.shared.sourceIsUnchanged(
            at: atlasPlate.sourceURL,
            expectedSHA256: atlasSource.sha256
        ) else {
            throw SurgeryPlanExportError.invalidAtlasSource(
                "The source PDF changed during export."
            )
        }

        let vesselSource = capture.majorVessels.provenance
        let vesselIdentity = "VesSAP \(vesselSource.specimenId), "
            + "diameter ≥30 µm"
        let planningPages: [Data] = try artifacts.map {
            guard $0.vesselAssetSHA256 == vesselSource.derivedAssetSha256 else {
                throw SurgeryPlanExportError.vesselIdentityMismatch
            }
            return try SurgeryPlanningPageRenderer.render(
                artifact: $0,
                prefill: prefill,
                atlasPlate: atlasPlate,
                atlasSourceSHA256: atlasSource.sha256,
                protocolSourceSHA256: protocolTemplateSHA256,
                vesselSource: vesselIdentity
            )
        }
        let assembledData = try SurgeryPlanPDFAssembler.assemble(
            protocolPDF: protocolPDF,
            planningPages: planningPages,
            atlasPDF: atlasPDF
        )
        let outputData = try SurgeryPlanPacketRenderer.stamp(
            packetPDF: assembledData,
            prefill: prefill,
            targetId: capture.target.targetId,
            vesselAssetSHA256: vesselSource.derivedAssetSha256,
            protocolTemplateSHA256: protocolTemplateSHA256,
            atlasSourceSHA256: atlasSource.sha256
        )
        try Task.checkCancellation()
        guard capture.isStillCurrent(in: model) else {
            throw SurgeryPlanExportError.stateChangedDuringExport
        }
        let stagingURL = outputURL.deletingLastPathComponent()
            .appendingPathComponent(
                ".Brain3D-SurgeryPlan-\(UUID().uuidString).pdf"
            )
        defer { try? FileManager.default.removeItem(at: stagingURL) }
        do {
            try outputData.write(to: stagingURL, options: .atomic)
        } catch {
            throw SurgeryPlanExportError.outputWriteFailed
        }
        guard let writtenDocument = PDFDocument(url: stagingURL),
              writtenDocument.pageCount == 3 + artifacts.count,
              verifyPageSizes(
                  writtenDocument,
                  planningPageCount: artifacts.count
              ),
              verifyPlanningPages(
                  writtenDocument,
                  artifacts: artifacts,
                  prefill: prefill
              ),
              (0 ..< writtenDocument.pageCount).allSatisfy({ index in
                  SurgeryPlanPacketRenderer.auditText(
                      writtenDocument.page(at: index)?.string,
                      contains: SurgeryPlanPacketRenderer.auditStamp(
                          prefill: prefill,
                          pageNumber: index + 1,
                          pageCount: writtenDocument.pageCount,
                          targetId: capture.target.targetId,
                          vesselAssetSHA256: vesselSource.derivedAssetSha256,
                          protocolTemplateSHA256: protocolTemplateSHA256,
                          atlasSourceSHA256: atlasSource.sha256
                      )
                  )
              })
        else {
            throw SurgeryPlanExportError.outputWriteFailed
        }
        try Task.checkCancellation()
        guard capture.isStillCurrent(in: model) else {
            throw SurgeryPlanExportError.stateChangedDuringExport
        }
        guard await SurgeryAtlasPDFSource.shared.sourceIsUnchanged(
            at: atlasPlate.sourceURL,
            expectedSHA256: atlasSource.sha256
        ) else {
            throw SurgeryPlanExportError.invalidAtlasSource(
                "The source PDF changed before the packet was written."
            )
        }
        do {
            if FileManager.default.fileExists(atPath: outputURL.path) {
                _ = try FileManager.default.replaceItemAt(
                    outputURL,
                    withItemAt: stagingURL
                )
            } else {
                try FileManager.default.moveItem(
                    at: stagingURL,
                    to: outputURL
                )
            }
        } catch {
            throw SurgeryPlanExportError.outputWriteFailed
        }
        return SurgeryPlanExportResult(
            outputURL: outputURL,
            pageCount: writtenDocument.pageCount,
            atlasPlate: atlasPlate,
            atlasSourceSHA256: atlasSource.sha256,
            exportClass: exportClass
        )
    }

    private static func captureModel(
        model: PlannerViewModel,
        configuration: SurgeryPlanExportConfiguration
    ) async throws -> SurgeryPlanModelCapture {
        let probeDraftIdentity = try SurgeryPlanDraftSafety.captureCurrent(
            in: model
        )
        guard let project = model.backendState?.project else {
            throw SurgeryPlanExportError.noProject
        }
        guard let atlas = model.viewerSnapshot?.atlas else {
            throw SurgeryPlanExportError.targetProjectionUnavailable
        }
        let target: SurgeryPlanImplantSite
        let projection: CalibratedTargetProjectionResult?
        let calibration: CalibrationSummary?
        let probePlan: ProbePlanDetail?
        if let surfacePlan = SurgeryPlanReadiness.currentSurfaceProbePlan(
            model.selectedProbePlan,
            atlas: atlas
        ), surfacePlan.planId == configuration.targetId {
            target = try SurgeryPlanImplantSite(surfacePlan: surfacePlan)
            projection = nil
            calibration = nil
            probePlan = surfacePlan
        } else {
            guard let legacyTarget = model.implantTargets.first(where: {
                $0.targetId == configuration.targetId
            }) else {
                throw SurgeryPlanExportError.targetUnavailable
            }
            guard let legacyCalibration = model.activeCalibration,
                  let legacyProjection = SurgeryPlanReadiness.currentProjection(
                      model.projection(for: legacyTarget.targetId),
                      project: project,
                      target: legacyTarget,
                      calibration: legacyCalibration,
                      atlas: atlas
                  )
            else {
                throw SurgeryPlanExportError.targetProjectionUnavailable
            }
            target = SurgeryPlanImplantSite(
                target: legacyTarget,
                projection: legacyProjection
            )
            projection = legacyProjection
            calibration = legacyCalibration
            probePlan = SurgeryPlanReadiness.currentProbePlan(
                model.selectedProbePlan,
                target: legacyTarget,
                projection: legacyProjection,
                calibration: legacyCalibration,
                atlas: atlas
            )
        }
        guard let majorVessels = model.majorVesselGeometry,
              majorVessels.segmentCount > 0,
              majorVessels.atlas == atlas
        else {
            throw SurgeryPlanExportError.vesselsUnavailable
        }
        let selectedPlanIdentity = SurgeryPlanModelCapture.planIdentity(
            model.selectedProbePlan
        )
        let minimumVisibleVesselDiameterMicrometres =
            model.minimumVisibleVesselDiameterMicrometres
        let capturedUnsavedState = model.hasUnsavedChanges
        let selectedRegion = model.highlightedAtlasRegion

        guard let containingVoxel = target.point.voxelIndex else {
            throw SurgeryPlanExportError.targetProjectionUnavailable
        }
        var sliceFrames: [SurgeryPlanView: VerifiedAtlasSliceFrame] = [:]
        var regionOverlayPNGs: [SurgeryPlanView: Data] = [:]
        if let selectedRegion,
           configuration.viewSelection.views.contains(.dorsal)
        {
            regionOverlayPNGs[.dorsal] =
                try await model.surgeryPlanRegionOverlayPNG(
                    orientation: .dorsal,
                    index: nil,
                    selectedRegion: selectedRegion,
                    expectedProjectId: project.projectId,
                    expectedProjectRevision: project.revision,
                    expectedAtlasMetadataSHA256: atlas.metadataSha256
                )
        }
        for view in configuration.viewSelection.views {
            guard let orientation = view.sliceOrientation else { continue }
            let index: Int
            switch orientation {
            case .coronal:
                index = containingVoxel.ap
            case .sagittal:
                index = containingVoxel.ml
            case .horizontal:
                index = containingVoxel.dv
            }
            sliceFrames[view] = try await model.surgeryPlanSliceFrame(
                for: orientation,
                index: index,
                expectedProjectId: project.projectId,
                expectedProjectRevision: project.revision,
                expectedAtlasMetadataSHA256: atlas.metadataSha256
            )
            if let selectedRegion {
                regionOverlayPNGs[view] =
                    try await model.surgeryPlanRegionOverlayPNG(
                        orientation: AtlasRegionOverlayOrientation(orientation),
                        index: index,
                        selectedRegion: selectedRegion,
                        expectedProjectId: project.projectId,
                        expectedProjectRevision: project.revision,
                        expectedAtlasMetadataSHA256: atlas.metadataSha256
                    )
            }
        }

        let sceneSnapshot: AnimalSceneSnapshot?
        if configuration.viewSelection.views.contains(.threeDimensional) {
            if model.threeDimensionalSnapshot?.projectId != project.projectId
                || model.threeDimensionalSnapshot?.projectRevision != project.revision
                || model.threeDimensionalSnapshot?.meshResult.atlas != atlas
                || model.threeDimensionalSnapshot?.highlightedRegionMesh?.region
                    != selectedRegion
            {
                await model.prepareThreeDimensionalScene()
            }
            guard let baseScene = model.threeDimensionalSnapshot,
                  baseScene.projectId == project.projectId,
                  baseScene.projectRevision == project.revision,
                  baseScene.meshResult.atlas == atlas,
                  baseScene.highlightedRegionMesh?.region == selectedRegion,
                  let rendererAnchor = project.rendererAnchor
            else {
                throw SurgeryPlanExportError.viewUnavailable(
                    SurgeryPlanView.threeDimensional.rawValue
                )
            }
            sceneSnapshot = try AnimalSceneSnapshot(
                projectId: project.projectId,
                projectRevision: project.revision,
                rendererAnchor: rendererAnchor,
                meshResult: baseScene.meshResult,
                highlightedRegionMesh: baseScene.highlightedRegionMesh,
                selectedProbePlan: probePlan,
                implantSite: ImplantSiteSceneMarker(
                    targetId: target.targetId,
                    label: target.label,
                    point: target.point
                ),
                majorVessels: majorVessels,
                minimumVisibleVesselDiameterMicrometres:
                    minimumVisibleVesselDiameterMicrometres,
                selectedVesselConflict: nil
            )
        } else {
            sceneSnapshot = nil
        }

        let capture = SurgeryPlanModelCapture(
            project: project,
            target: target,
            projection: projection,
            calibration: calibration,
            probePlan: probePlan,
            selectedPlanIdentity: selectedPlanIdentity,
            majorVessels: majorVessels,
            minimumVisibleVesselDiameterMicrometres:
                minimumVisibleVesselDiameterMicrometres,
            atlas: atlas,
            dorsalSurface: configuration.viewSelection.views.contains(.dorsal)
                ? model.dorsalSurface
                : nil,
            dorsalPNG: configuration.viewSelection.views.contains(.dorsal)
                ? model.dorsalSurfacePNG
                : nil,
            sliceFrames: sliceFrames,
            selectedRegion: selectedRegion,
            regionOverlayPNGs: regionOverlayPNGs,
            sceneSnapshot: sceneSnapshot,
            hasUnsavedChanges: capturedUnsavedState,
            probeDraftIdentity: probeDraftIdentity
        )
        guard capture.isStillCurrent(in: model) else {
            throw SurgeryPlanExportError.stateChangedDuringExport
        }
        return capture
    }

    static func makePrefill(
        project: ProjectBridgeState,
        target: SurgeryPlanImplantSite,
        targetLabel: String,
        matchingPlan: ProbePlanDetail?,
        exportClass: SurgeryPlanExportClass,
        configuration: SurgeryPlanExportConfiguration
    ) -> SurgeryPlanPrefill {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        let normalizedTargetLabel = targetLabel
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let plan = matchingPlan
        let surfaceInput = plan?.surfaceRelativeInput
        return SurgeryPlanPrefill(
            exportClass: exportClass,
            date: formatter.string(from: configuration.date),
            projectTitle: project.title,
            projectRevision: project.revision,
            subjectId: project.subjectId ?? "________",
            targetLabel: normalizedTargetLabel.isEmpty
                ? target.label
                : normalizedTargetLabel,
            apMillimetres: target.apMillimetres,
            mlMillimetres: target.mlMillimetres,
            dvMillimetres: target.dvMillimetres,
            cageId: configuration.cageId,
            mouseNumber: configuration.mouseNumber,
            weightGrams: configuration.weightGrams,
            operatorName: configuration.operatorName,
            probePlanName: plan?.name,
            probeModelName: plan?.modelDisplayName,
            insertionDepthMillimetres: plan.map {
                $0.placement.insertionDepthMicrometres / 1_000
            },
            azimuthDegrees: plan?.placement.azimuthDegrees,
            elevationDegrees: plan?.placement.elevationDegrees,
            axialRotationDegrees: plan?.placement.axialRotationDegrees,
            surfaceDepthMillimetres: surfaceInput?.surfaceDepthMillimetres,
            sagittalAngleDegrees: surfaceInput?.sagittalAngleDegrees,
            probeLayoutRotationDegrees:
                surfaceInput?.probeLayoutRotationDegrees,
            probeVerificationStatus: plan?.verificationStatus,
            probeWarning: plan?.warning,
            planInputSHA256: plan?.inputSha256,
            surfaceAnnotationSHA256: surfaceInput?.annotationSha256,
            surfaceDefinitionVersion:
                surfaceInput?.surfaceDefinitionVersion,
            bregmaReferenceId:
                surfaceInput?.bregmaReference.referenceId,
            bregmaSourceRevision:
                surfaceInput?.bregmaReference.sourceRevision,
            bregmaSourceSHA256:
                surfaceInput?.bregmaReference.sourceSha256,
            draftReason: exportClass == .final
                ? nil
                : "unsaved state or no current atlas-surface probe"
        )
    }

    private static func verifyPageSizes(
        _ document: PDFDocument,
        planningPageCount: Int
    ) -> Bool {
        for index in 0 ..< document.pageCount {
            guard let page = document.page(at: index) else { return false }
            let size = page.bounds(for: .mediaBox).size
            let expected = index < 2
                ? CGSize(width: 612, height: 792)
                : CGSize(width: 792, height: 612)
            guard Int(size.width.rounded()) == Int(expected.width),
                  Int(size.height.rounded()) == Int(expected.height)
            else { return false }
        }
        return document.pageCount == planningPageCount + 3
    }

    private static func verifyPlanningPages(
        _ document: PDFDocument,
        artifacts: [SurgeryPlanningViewArtifact],
        prefill: SurgeryPlanPrefill
    ) -> Bool {
        for (offset, artifact) in artifacts.enumerated() {
            guard let text = document.page(at: offset + 2)?.string,
                  text.contains(
                      "\(prefill.exportClass.rawValue) · "
                          + "Surgery planning view — \(artifact.view.rawValue)"
                  ),
                  text.contains(prefill.targetCoordinateText)
            else {
                return false
            }
        }
        return true
    }
}

private extension NSImage {
    var pngData: Data? {
        guard let tiffRepresentation,
              let representation = NSBitmapImageRep(data: tiffRepresentation)
        else { return nil }
        return representation.representation(using: .png, properties: [:])
    }
}
