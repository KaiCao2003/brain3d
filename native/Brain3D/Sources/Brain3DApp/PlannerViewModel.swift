import Brain3DCore
import Brain3DScene
import CryptoKit
import Foundation
import SwiftUI
import simd

enum BridgeConnectionPhase: Equatable {
    case notConfigured
    case connecting
    case ready(service: String, version: String)
    case incompatible(String)
    case failed(String)

    var title: String {
        switch self {
        case .notConfigured:
            "Backend not configured"
        case .connecting:
            "Connecting to backend…"
        case let .ready(service, version):
            "Connected — \(service) \(version)"
        case let .incompatible(message):
            "Incompatible backend — \(message)"
        case let .failed(message):
            "Backend unavailable — \(message)"
        }
    }

    var isReady: Bool {
        if case .ready = self { return true }
        return false
    }
}

enum AtlasLoadPhase: Equatable {
    case idle
    case opening
    case ready
    case needsDownload
    case failed(String)
}

enum DorsalLoadPhase: Equatable {
    case unavailable(String)
    case loading
    case ready
    case failed(String)
}

enum ViewerLoadPhase: Equatable {
    case unavailable(String)
    case loading
    case ready
    case updating
    case failed(String)

    var message: String {
        switch self {
        case let .unavailable(message), let .failed(message): message
        case .loading: "Loading atlas views…"
        case .ready: "Atlas views ready"
        case .updating: "Updating atlas view…"
        }
    }
}

enum ThreeDimensionalLoadPhase: Equatable {
    case unavailable(String)
    case loadingDescriptor
    case loadingGeometry
    case ready
    case failed(String)

    var message: String {
        switch self {
        case let .unavailable(message), let .failed(message): message
        case .loadingDescriptor: "Verifying the 3D mouse atlas…"
        case .loadingGeometry: "Loading verified atlas geometry…"
        case .ready: "3D mouse atlas ready"
        }
    }
}

enum ThreeDimensionalRenderPhaseReducer {
    static func phaseAfterPreparing(
        snapshotIdentity: String,
        renderedSnapshotIdentity: String?
    ) -> ThreeDimensionalLoadPhase {
        renderedSnapshotIdentity == snapshotIdentity ? .ready : .loadingGeometry
    }

    static func acceptsCallback(
        snapshotIdentity: String,
        currentSnapshotIdentity: String?
    ) -> Bool {
        snapshotIdentity == currentSnapshotIdentity
    }
}

enum ProjectStatusPresentation {
    static func text(
        title: String,
        subjectId: String?,
        hasUnsavedChanges: Bool
    ) -> String {
        let normalizedSubjectId = subjectId?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let subject = normalizedSubjectId.flatMap { $0.isEmpty ? nil : $0 }
            ?? "unavailable"
        let saveState = hasUnsavedChanges ? "unsaved changes" : "saved"
        return "\(title) · Subject ID \(subject) · animal-only · \(saveState)"
    }
}

enum ProbePlanningAvailabilityPolicy {
    static func blockingReason(
        connectionReady: Bool,
        hasProject: Bool,
        hasActiveCalibration: Bool,
        calibrationPermitsPlanning: Bool,
        serviceSupportsProbePlanning: Bool,
        projectOperationInProgress: Bool,
        calibrationOperationInProgress: Bool,
        probeOperationInProgress: Bool
    ) -> String? {
        guard connectionReady else {
            return "Connect to the planning service."
        }
        guard hasProject else {
            return "Open or create an animal plan."
        }
        guard hasActiveCalibration else {
            return "Activate a passing subject calibration."
        }
        guard calibrationPermitsPlanning else {
            return "The active subject calibration does not pass planning checks."
        }
        guard serviceSupportsProbePlanning else {
            return "The connected service does not support calibrated probe planning."
        }
        if projectOperationInProgress {
            return "Wait for the project operation to finish."
        }
        if calibrationOperationInProgress {
            return "Wait for the calibration operation to finish."
        }
        if probeOperationInProgress {
            return "Wait for the probe operation to finish."
        }
        return nil
    }
}

struct VerifiedAtlasSliceFrame: Equatable, Sendable {
    let orientation: AtlasSliceOrientation
    let index: Int
    let sliceCount: Int
    let width: Int
    let height: Int
    let fixedAxis: AtlasAnatomicalAxis
    let rowAxis: AtlasAnatomicalAxis
    let columnAxis: AtlasAnatomicalAxis
    let sliceCenterMicrometres: Double
    let png: Data
}

struct TriPlanarFrameSet: Equatable {
    var coronal: VerifiedAtlasSliceFrame?
    var sagittal: VerifiedAtlasSliceFrame?
    var horizontal: VerifiedAtlasSliceFrame?

    subscript(_ orientation: AtlasSliceOrientation) -> VerifiedAtlasSliceFrame? {
        get {
            switch orientation {
            case .coronal: coronal
            case .sagittal: sagittal
            case .horizontal: horizontal
            }
        }
        set {
            switch orientation {
            case .coronal: coronal = newValue
            case .sagittal: sagittal = newValue
            case .horizontal: horizontal = newValue
            }
        }
    }
}

struct PendingViewerSlice: Equatable {
    let orientation: AtlasSliceOrientation
    let index: Int
}

struct MajorVesselConflictCanvasOverlay: Equatable {
    let conflictId: String
    let probePoint: ProbeSliceImagePoint
    let vesselPoint: ProbeSliceImagePoint
    let exactVesselSegment: MajorVesselSliceSegment?
}

private enum ViewerMutation: Sendable {
    case slice(orientation: AtlasSliceOrientation, index: Int)
    case regionPick(
        orientation: AtlasSliceOrientation,
        index: Int,
        column: Int,
        row: Int
    )
}

enum ViewerInteractionPolicy {
    static func allowsRegionPick(
        orientation: AtlasSliceOrientation,
        displayedSliceIndex: Int,
        authoritativeSliceIndex: Int?,
        pendingSliceOrientation: AtlasSliceOrientation?,
        atomicNavigationInProgress: Bool
    ) -> Bool {
        pendingSliceOrientation != orientation
            && !atomicNavigationInProgress
            && authoritativeSliceIndex == displayedSliceIndex
    }
}

enum ViewerMutationPublicationPolicy {
    /// A fused slice response has already advanced the backend's canonical
    /// project revision, so its matching pixels must be retained even when a
    /// newer request is queued. `false` only means that another mutation still
    /// owns the final ready/error state.
    @discardableResult
    static func publishSlice(
        _ frame: VerifiedAtlasSliceFrame,
        requestGeneration: Int,
        currentGeneration: Int,
        into frames: inout TriPlanarFrameSet
    ) -> Bool {
        frames[frame.orientation] = frame
        return requestGeneration == currentGeneration
    }

    /// A region result is visible interaction state, so a superseded request
    /// must not replace the selection currently shown to the user. The caller
    /// may still reconcile the backend's authoritative revision before using
    /// this gate to process the next queued mutation.
    @discardableResult
    static func publishRegionSelection<Selection>(
        _ candidate: Selection,
        requestGeneration: Int,
        currentGeneration: Int,
        into visibleSelection: inout Selection
    ) -> Bool {
        guard requestGeneration == currentGeneration else { return false }
        visibleSelection = candidate
        return true
    }
}

struct LocalVesselProvenance: Equatable {
    let fileName: String
    let fileURL: URL
    let byteCount: Int
    let sha256: String
}

@MainActor
final class PlannerViewModel: ObservableObject {
    @Published var workspaceMode: WorkspaceMode = .dorsal
    @Published private(set) var connection: BridgeConnectionPhase
    @Published private(set) var atlasLoadPhase: AtlasLoadPhase = .idle
    @Published private(set) var dorsalLoadPhase: DorsalLoadPhase = .unavailable(
        "Connect to the planning service"
    )
    @Published private(set) var backendState: PlannerBridgeState?
    @Published private(set) var atlasProvenance: AtlasProvenance?
    @Published private(set) var dorsalSurface: AtlasDorsalResult?
    @Published private(set) var dorsalSurfacePNG: Data?
    @Published private(set) var dorsalRegionPick: DorsalPickResult?
    @Published private(set) var dorsalPickInProgress = false
    @Published private(set) var dorsalPickError: String?
    @Published private(set) var viewerPhase: ViewerLoadPhase = .unavailable(
        "Create or open an animal plan to browse atlas slices"
    )
    @Published private(set) var viewerSnapshot: ViewerCanonicalSnapshot?
    @Published private(set) var triPlanarFrames = TriPlanarFrameSet()
    @Published private(set) var pendingViewerSlice: PendingViewerSlice?
    @Published private(set) var viewerRegionSelection: Brain3DCore.ViewerRegionSelection?
    @Published private(set) var threeDimensionalPhase: ThreeDimensionalLoadPhase = .unavailable(
        "Create or open an animal plan to load the 3D mouse atlas"
    )
    @Published private(set) var threeDimensionalSnapshot: AnimalSceneSnapshot?
    @Published private(set) var threeDimensionalRegionHit: AtlasRayPickHit?
    @Published private(set) var highlightedAtlasRegion: AtlasRegionSummary?
    @Published private(set) var atlasRegionHierarchy: AtlasRegionHierarchy?
    @Published private(set) var atlasRegionHierarchyError: String?
    @Published private(set) var threeDimensionalPickInProgress = false
    @Published private(set) var threeDimensionalPickError: String?
    @Published var atlasRegionSearchText = ""
    @Published private(set) var atlasRegionSearchResults: [AtlasRegionSearchHit] = []
    @Published private(set) var atlasRegionSearchInProgress = false
    @Published private(set) var atlasRegionSearchError: String?
    @Published private(set) var majorVesselGeometry: MajorVesselGeometryResult?
    @Published private(set) var majorVesselDorsalProjection: MajorVesselSliceOverlay?
    @Published private(set) var minimumVisibleVesselDiameterMicrometres: Double
    @Published private(set) var visibleMajorVesselSegmentCount = 0
    @Published private(set) var majorVesselLoadInProgress = false
    @Published private(set) var majorVesselLoadError: String?
    @Published private(set) var selectedProbeVesselAnalysis: MajorVesselAnalysisResult?
    @Published private(set) var selectedMajorVesselConflict: MajorVesselConflict?
    @Published private(set) var majorVesselAnalysisInProgress = false
    @Published private(set) var majorVesselAnalysisError: String?
    @Published private(set) var majorVesselNavigationInProgress = false
    @Published private(set) var majorVesselNavigationError: String?
    @Published private(set) var localVessel: LocalVesselProvenance?
    @Published private(set) var importedVessel: ImportedVascularImage?
    @Published private(set) var subjectPreviewPNG: Data?
    @Published private(set) var subjectOverlayPNG: Data?
    @Published private(set) var vesselImportError: String?
    @Published private(set) var vesselImportInProgress = false
    @Published private(set) var registrationInProgress = false
    @Published private(set) var registrationError: String?
    @Published private(set) var registrationResult: VascularRegisterResult?
    @Published private(set) var projectOperationInProgress = false
    @Published private(set) var projectOperationError: String?
    @Published private(set) var projectRecoveryNotice: String?
    @Published private(set) var hasUnsavedChanges = false
    @Published private(set) var populationDensityVisible = false
    @Published private(set) var populationDensityPNG: Data?
    @Published private(set) var populationDensityPreparation: ReferenceDensityPrepareResult?
    @Published private(set) var populationDensityOverlay: ReferenceDensityOverlayResult?
    @Published private(set) var populationDensityPrepareInProgress = false
    @Published private(set) var populationDensityOverlayInProgress = false
    @Published private(set) var populationDensityError: String?
    @Published private(set) var implantTargets: [UnprojectedImplantTarget] = []
    @Published private(set) var implantOperationInProgress = false
    @Published private(set) var implantOperationError: String?
    @Published private(set) var calibrations: [CalibrationSummary] = []
    @Published private(set) var activeCalibrationId: String?
    @Published private(set) var selectedCalibration: CalibrationSummary?
    @Published private(set) var targetProjections: [String: CalibratedTargetProjectionResult] = [:]
    @Published private(set) var calibrationOperationInProgress = false
    @Published private(set) var calibrationOperationError: String?
    @Published private(set) var probeCatalog: [ProbeCatalogModel] = []
    @Published private(set) var selectedProbeModel: ProbeCatalogModel?
    @Published private(set) var probePlans: [ProbePlanSummary] = []
    @Published private(set) var selectedProbePlanId: String?
    @Published private(set) var selectedProbePlan: ProbePlanDetail?
    @Published private(set) var selectedProbeRegionAnalysis: ProbeRegionAnalysisBundle?
    @Published private(set) var probeOperationInProgress = false
    @Published private(set) var probeOperationError: String?

    private let launchConfiguration: BridgeLaunchConfiguration?
    private let preferences: UserDefaults
    private var bridgeClient: BridgeClient?
    private var helloResult: HelloResult?
    private var hasAttemptedConnection = false
    private var authoritativeViewerSnapshot: ViewerCanonicalSnapshot?
    private var pendingViewerMutation: ViewerMutation?
    private var viewerMutationWorker: Task<Void, Never>?
    private var viewerGeneration = 0
    private var dorsalPickGeneration = 0
    private var dorsalPickWorker: Task<Void, Never>?
    private var threeDimensionalGeneration = 0
    private var threeDimensionalPickGeneration = 0
    private var threeDimensionalPickWorker: Task<Void, Never>?
    private var renderedThreeDimensionalSnapshotIdentity: String?
    private var highlightedRegionGeneration = 0
    private var atlasRegionSearchGeneration = 0
    private var cachedRootMesh: AtlasMeshResult?
    private var cachedHighlightedRegionMesh: AtlasMeshResult?
    private var majorVesselSliceOverlayCache: [String: MajorVesselSliceOverlay] = [:]
    private var majorVesselSliceSpatialIndex: MajorVesselSliceSpatialIndex?

    static let minimumVisibleVesselDiameterPreferenceKey =
        "majorVessels.minimumVisibleDiameterMicrometres"

    init(
        launchConfiguration: BridgeLaunchConfiguration?,
        preferences: UserDefaults = .standard
    ) {
        self.launchConfiguration = launchConfiguration
        self.preferences = preferences
        let stored = preferences.object(
            forKey: Self.minimumVisibleVesselDiameterPreferenceKey
        ) as? NSNumber
        minimumVisibleVesselDiameterMicrometres =
            MajorVesselDisplayFilter.snappedMinimumDiameterMicrometres(
                stored?.doubleValue
                    ?? MajorVesselDisplayFilter.defaultMinimumDiameterMicrometres
            )
        connection = launchConfiguration == nil ? .notConfigured : .connecting
    }

    var atlasOperationalStatus: String {
        switch atlasLoadPhase {
        case .idle:
            "Not loaded"
        case .opening:
            "Opening and validating cached 25 µm atlas…"
        case .ready:
            "Loaded and verified"
        case .needsDownload:
            "Not cached — explicit download required"
        case let .failed(message):
            "Not loaded — \(message)"
        }
    }

    var projectStatus: String {
        if let project = backendState?.project {
            return ProjectStatusPresentation.text(
                title: project.title,
                subjectId: project.subjectId,
                hasUnsavedChanges: hasUnsavedChanges
            )
        }
        if atlasLoadPhase == .ready {
            return "Awaiting explicit animal-only acknowledgement"
        }
        return "No backend project"
    }

    var subjectImportStatus: String {
        if let backend = backendState?.subjectVessels.primaryImage {
            return "Imported with verified digest — \(backend.sourceName)"
        }
        if importedVessel != nil {
            return "Imported with backend-verified digest"
        }
        if localVessel != nil {
            return "Selected locally — backend import incomplete"
        }
        return "No subject image imported"
    }

    var subjectRegistrationStatus: String {
        guard backendState?.subjectVessels.primaryImage?.registered == true else {
            return "Not registered — landmark fit required"
        }
        return "Registration transform stored by backend"
    }

    var residualStatus: String {
        guard
            let image = backendState?.subjectVessels.primaryImage,
            image.registered,
            let residual = image.residualMicrometres
        else {
            return "Not computed"
        }
        let rms = residual.formatted(.number.precision(.fractionLength(1)))
        if let maximum = image.maximumResidualMicrometres {
            return "RMS \(rms) µm · max "
                + maximum.formatted(.number.precision(.fractionLength(1))) + " µm"
        }
        return "RMS \(rms) µm"
    }

    var lateralityStatus: String {
        guard let image = backendState?.subjectVessels.primaryImage, image.lateralityConfirmed else {
            return "Not confirmed"
        }
        return "Confirmed"
    }

    var populationDensityStatus: String {
        guard connection.isReady else {
            return "Unavailable — backend is not connected"
        }
        if populationDensityPrepareInProgress {
            return "Downloading, verifying, and preparing published reference…"
        }
        if populationDensityOverlayInProgress {
            return "Rendering verified dorsal population projection…"
        }
        guard populationDensityAvailable else {
            return "Unavailable — no verified reference loaded"
        }
        return backendState?.populationDensity.status ?? "Prepared and verified"
    }

    var populationDensityAvailable: Bool {
        backendState?.populationDensity.available == true || populationDensityPreparation != nil
    }

    var populationDensityProvenanceStatus: String {
        guard let source = populationDensityOverlay?.source ?? populationDensityPreparation?.source else {
            return "Pinned source will be verified before display"
        }
        return "DOI \(source.doi) · archive SHA-256 \(source.archiveSha256)"
    }

    var populationDensityDisclosure: String {
        populationDensityOverlay?.disclosure
            ?? populationDensityPreparation?.disclosure
            ?? SafetyPolicy.populationDensityCaveat
    }

    var canImportSubjectVessels: Bool {
        connection.isReady
            && atlasLoadPhase == .ready
            && backendState?.project?.animalResearchOnlyAcknowledged == true
            && helloResult?.capabilities.subjectVascularImport == true
            && !vesselImportInProgress
    }

    var canRegisterSubjectVessels: Bool {
        connection.isReady
            && activeSubjectImageId != nil
            && subjectPreviewPNG != nil
            && helloResult?.capabilities.subjectVascularRegistration == true
            && !registrationInProgress
    }

    var canShowPopulationDensity: Bool {
        connection.isReady
            && populationDensityAvailable
            && atlasLoadPhase == .ready
            && workspaceMode == .dorsal
            && dorsalSurface != nil
            && !populationDensityPrepareInProgress
            && !populationDensityOverlayInProgress
    }

    var canPreparePopulationDensity: Bool {
        connection.isReady
            && atlasLoadPhase == .ready
            && !populationDensityAvailable
            && !populationDensityPrepareInProgress
            && !populationDensityOverlayInProgress
    }

    var canDownloadAtlas: Bool { atlasLoadPhase == .needsDownload }

    var requiresAnimalOnlyAcknowledgement: Bool {
        connection.isReady
            && atlasLoadPhase == .ready
            && backendState?.project == nil
    }

    var canCreateNewAnimalProject: Bool {
        requiresAnimalOnlyAcknowledgement && !projectOperationInProgress
    }

    var canSaveProject: Bool {
        connection.isReady && backendState?.project != nil && !projectOperationInProgress
    }

    var canOpenProject: Bool {
        connection.isReady && atlasLoadPhase == .ready && !projectOperationInProgress
    }

    var canStoreImplantTarget: Bool {
        connection.isReady
            && backendState?.project != nil
            && !implantOperationInProgress
            && !projectOperationInProgress
    }

    var canManageCalibration: Bool {
        connection.isReady
            && backendState?.project != nil
            && helloResult?.capabilities.subjectAtlasCalibration == true
            && helloResult?.capabilities.calibratedTargetProjection == true
            && !projectOperationInProgress
            && !calibrationOperationInProgress
    }

    var calibrationProjectId: String? { backendState?.project?.projectId }

    var calibrationProjectRevision: Int? { backendState?.project?.revision }

    var activeCalibration: CalibrationSummary? {
        guard let activeCalibrationId else { return nil }
        return calibrations.first { $0.calibrationId == activeCalibrationId }
    }

    var canManageProbePlanning: Bool {
        probePlanningUnavailableReason == nil
    }

    var probePlanningUnavailableReason: String? {
        ProbePlanningAvailabilityPolicy.blockingReason(
            connectionReady: connection.isReady,
            hasProject: backendState?.project != nil,
            hasActiveCalibration: activeCalibration != nil,
            calibrationPermitsPlanning: activeCalibration?.permitsPlanning == true,
            serviceSupportsProbePlanning: supportsProbePlanning,
            projectOperationInProgress: projectOperationInProgress,
            calibrationOperationInProgress: calibrationOperationInProgress,
            probeOperationInProgress: probeOperationInProgress
        )
    }

    var canAnalyzeSelectedProbeRegions: Bool {
        canManageProbePlanning
            && selectedProbePlan?.hasCurrentPlanningGeometry == true
    }

    var canRemoveSelectedProbePlan: Bool {
        connection.isReady
            && backendState?.project != nil
            && selectedProbePlan != nil
            && supportsProbePlanning
            && !projectOperationInProgress
            && !probeOperationInProgress
    }

    var canAnalyzeMajorVesselClearance: Bool {
        connection.isReady
            && backendState?.project != nil
            && selectedProbePlan?.hasCurrentPlanningGeometry == true
            && majorVesselGeometry != nil
            && helloResult?.capabilities.radiusAwareReferenceVesselAnalysis == true
            && !majorVesselAnalysisInProgress
            && !projectOperationInProgress
    }

    var canNavigateMajorVesselConflict: Bool {
        connection.isReady
            && helloResult?.capabilities.atomicAtlasPointNavigation == true
            && backendState?.project != nil
            && viewerSnapshot != nil
            && selectedProbeVesselAnalysis != nil
            && majorVesselGeometry != nil
            && !majorVesselNavigationInProgress
            && !projectOperationInProgress
            && pendingViewerMutation == nil
            && viewerMutationWorker == nil
    }

    private var supportsProbePlanning: Bool {
        helloResult?.capabilities.probeCatalog == true
            && helloResult?.capabilities.calibratedProbePlanning == true
            && helloResult?.capabilities.exactProbeRegionTraversal == true
    }

    var probeProjectId: String? { backendState?.project?.projectId }

    var probeProjectRevision: Int? { backendState?.project?.revision }

    var threeDimensionalPreparationIdentity: String {
        guard let project = backendState?.project else { return "no-project" }
        return [
            project.projectId,
            String(project.revision),
            atlasProvenance?.metadataSha256 ?? "no-atlas",
            cachedHighlightedRegionMesh?.mesh.sha256 ?? "no-highlighted-region",
            selectedProbePlan?.inputSha256 ?? "no-probe",
            majorVesselGeometry?.provenance.derivedAssetSha256 ?? "no-vessels",
            String(
                minimumVisibleVesselDiameterMicrometres.bitPattern,
                radix: 16
            ),
            selectedMajorVesselConflict.map {
                [
                    $0.conflictId,
                    String($0.probePoint.apMicrometres.bitPattern),
                    String($0.probePoint.dvMicrometres.bitPattern),
                    String($0.probePoint.mlMicrometres.bitPattern),
                ].joined(separator: ":")
            } ?? "no-vessel-conflict",
        ].joined(separator: ":")
    }

    var majorVesselStatus: String {
        if majorVesselLoadInProgress { return "Loading reference major vessels…" }
        if let geometry = majorVesselGeometry {
            return "VesSAP \(geometry.provenance.specimenId) · "
                + "\(visibleMajorVesselSegmentCount.formatted()) visible of "
                + "\(geometry.segmentCount.formatted()) source segments · "
                + "display \(majorVesselDisplayThresholdText)"
        }
        if majorVesselLoadError != nil { return "Unavailable" }
        return "Reference major vessels not loaded"
    }

    var majorVesselDisplayThresholdText: String {
        "≥\(Int(minimumVisibleVesselDiameterMicrometres.rounded())) µm"
    }

    var majorVesselVisibleCountText: String {
        guard let geometry = majorVesselGeometry else { return "Vessels unavailable" }
        return "\(visibleMajorVesselSegmentCount.formatted()) / "
            + "\(geometry.segmentCount.formatted()) segments"
    }

    var majorVesselDisclosure: String {
        guard let geometry = majorVesselGeometry else {
            return "Single-specimen reference; no geometry is being displayed."
        }
        let source = geometry.provenance
        let coverage =
            "Single cleared C57BL/6J \(source.specimenId) reference; not subject-specific; "
                + "the immutable source omits diameters below "
                + "\(Int(MajorVesselContract.minimumIncludedDiameterMicrometres)) µm; "
                + "the current display filter is \(majorVesselDisplayThresholdText)."
        guard !source.uncertaintyBoundsReviewed else { return coverage }
        return coverage
            + " Display only: registration and tissue-distortion uncertainty bounds are not "
            + "published, so clearance, vessel absence, and trajectory suitability cannot "
            + "be classified."
    }

    func setMinimumVisibleVesselDiameterMicrometres(_ proposed: Double) {
        let normalized =
            MajorVesselDisplayFilter.snappedMinimumDiameterMicrometres(proposed)
        guard normalized != minimumVisibleVesselDiameterMicrometres else { return }
        minimumVisibleVesselDiameterMicrometres = normalized
        preferences.set(
            normalized,
            forKey: Self.minimumVisibleVesselDiameterPreferenceKey
        )
        refreshMajorVesselDisplayFilter()
    }

    private func refreshMajorVesselDisplayFilter() {
        majorVesselSliceOverlayCache = [:]
        guard let geometry = majorVesselGeometry else {
            majorVesselDorsalProjection = nil
            visibleMajorVesselSegmentCount = 0
            return
        }
        visibleMajorVesselSegmentCount =
            MajorVesselDisplayFilter.visibleSegmentCount(
                graph: geometry.graph,
                minimumDiameterMicrometres:
                    minimumVisibleVesselDiameterMicrometres
            )
        majorVesselDorsalProjection =
            MajorVesselSliceOverlayGeometry.makeDorsalProjection(
                geometry: geometry,
                minimumVisibleDiameterMicrometres:
                    minimumVisibleVesselDiameterMicrometres
            )
        do {
            try rebuildThreeDimensionalSnapshot()
        } catch {
            threeDimensionalPickError = error.localizedDescription
        }
    }

    func projection(for targetId: String) -> CalibratedTargetProjectionResult? {
        targetProjections[targetId]
    }

    var subjectImageWidth: Int {
        importedVessel?.widthPixels ?? backendState?.subjectVessels.primaryImage?.widthPixels ?? 0
    }

    var subjectImageHeight: Int {
        importedVessel?.heightPixels ?? backendState?.subjectVessels.primaryImage?.heightPixels ?? 0
    }

    private var activeSubjectImageId: String? {
        importedVessel?.imageId ?? backendState?.subjectVessels.primaryImage?.imageId
    }

    var dorsalSurfaceStatus: String {
        switch dorsalLoadPhase {
        case let .unavailable(message), let .failed(message):
            return message
        case .loading:
            return "Rendering verified dorsal surface…"
        case .ready:
            return dorsalSurface?.displayLabel ?? "Verified dorsal surface ready"
        }
    }

    func connectIfNeeded() async {
        guard !hasAttemptedConnection else { return }
        hasAttemptedConnection = true
        await connect()
    }

    func reconnect() async {
        viewerMutationWorker?.cancel()
        viewerMutationWorker = nil
        pendingViewerMutation = nil
        pendingViewerSlice = nil
        authoritativeViewerSnapshot = nil
        viewerSnapshot = nil
        viewerRegionSelection = nil
        triPlanarFrames = TriPlanarFrameSet()
        viewerPhase = .unavailable("Connect to the planning service")
        if let bridgeClient {
            await bridgeClient.close()
        }
        bridgeClient = nil
        helloResult = nil
        backendState = nil
        atlasProvenance = nil
        dorsalSurface = nil
        dorsalSurfacePNG = nil
        clearDorsalRegionPick()
        threeDimensionalGeneration &+= 1
        threeDimensionalPickGeneration &+= 1
        threeDimensionalPickWorker?.cancel()
        threeDimensionalPickWorker = nil
        highlightedRegionGeneration &+= 1
        atlasRegionSearchGeneration &+= 1
        threeDimensionalSnapshot = nil
        renderedThreeDimensionalSnapshotIdentity = nil
        threeDimensionalRegionHit = nil
        highlightedAtlasRegion = nil
        atlasRegionHierarchy = nil
        atlasRegionHierarchyError = nil
        cachedRootMesh = nil
        cachedHighlightedRegionMesh = nil
        atlasRegionSearchText = ""
        atlasRegionSearchResults = []
        atlasRegionSearchInProgress = false
        atlasRegionSearchError = nil
        majorVesselGeometry = nil
        majorVesselDorsalProjection = nil
        majorVesselSliceSpatialIndex = nil
        majorVesselSliceOverlayCache = [:]
        majorVesselLoadInProgress = false
        majorVesselLoadError = nil
        clearMajorVesselAnalysis()
        importedVessel = nil
        subjectPreviewPNG = nil
        subjectOverlayPNG = nil
        registrationError = nil
        registrationResult = nil
        projectOperationError = nil
        projectRecoveryNotice = nil
        hasUnsavedChanges = false
        implantTargets = []
        implantOperationError = nil
        calibrations = []
        activeCalibrationId = nil
        selectedCalibration = nil
        targetProjections = [:]
        calibrationOperationError = nil
        clearProbePlanning()
        atlasLoadPhase = .idle
        dorsalLoadPhase = .unavailable("Connect to the planning service")
        clearPopulationDensity(clearPreparation: true)
        await connect()
    }

    func downloadAndOpenAtlas() async {
        guard canDownloadAtlas else { return }
        await openAtlasAndLoadSlice(allowDownload: true)
    }

    func createNewAnimalProject(
        acknowledgement: AnimalOnlyAcknowledgementState,
        subjectId: String
    ) async -> Bool {
        projectOperationError = nil
        guard let bridgeClient, canCreateNewAnimalProject else {
            projectOperationError =
                "Open the verified 25 µm atlas before creating an animal plan."
            return false
        }
        guard let parameters = ProjectNewParameters(
            acknowledgement: acknowledgement,
            title: "Untitled animal surgery plan",
            subjectId: subjectId
        ) else {
            projectOperationError =
                "Enter an animal subject ID and explicitly acknowledge animal-only use first."
            return false
        }

        projectOperationInProgress = true
        defer { projectOperationInProgress = false }
        do {
            let project: ProjectNewResult = try await bridgeClient.request(
                method: "project.new",
                params: parameters
            )
            guard
                project.animalOnly,
                project.warning == SafetyPolicy.animalResearchOnly
            else {
                throw StateValidationFailure.animalOnlyContractMissing
            }
            await refreshState()
            guard backendState?.project?.animalResearchOnlyAcknowledged == true else {
                throw StateValidationFailure.animalOnlyContractMissing
            }
            hasUnsavedChanges = true
            return true
        } catch {
            projectOperationError = error.localizedDescription
            return false
        }
    }

    func preparePopulationDensity(
        archivePath: String? = nil,
        downloadIfMissing: Bool = true
    ) async {
        populationDensityError = nil
        guard let bridgeClient, canPreparePopulationDensity else {
            populationDensityError =
                "Open the verified 25 µm atlas before preparing the published reference."
            return
        }

        populationDensityPrepareInProgress = true
        defer { populationDensityPrepareInProgress = false }
        do {
            let result: ReferenceDensityPrepareResult = try await bridgeClient.request(
                method: "vascular.reference.prepare",
                params: ReferenceDensityPrepareParameters(
                    archivePath: archivePath,
                    downloadIfMissing: downloadIfMissing
                )
            )
            guard let atlasProvenance else {
                throw ReferenceDensityValidationError.atlasMismatch
            }
            try ReferenceDensityValidator.validatePreparation(result, against: atlasProvenance)
            populationDensityPreparation = result
            populationDensityOverlay = nil
            populationDensityPNG = nil
            populationDensityVisible = false
            await refreshState()
            guard backendState?.populationDensity.available == true else {
                clearPopulationDensity(clearPreparation: true)
                throw PopulationDensityOperationFailure.preparationNotPublishedToState
            }
            // This callable legacy operation may retain its verified preparation
            // result, but ordinary refresh never hydrates the archived display.
            populationDensityPreparation = result
        } catch {
            populationDensityError = error.localizedDescription
        }
    }

    func setPopulationDensityVisible(_ shouldShow: Bool) async {
        populationDensityError = nil
        guard
            let bridgeClient,
            let display = backendState?.populationDensity,
            display.available
        else {
            populationDensityPNG = nil
            populationDensityOverlay = nil
            populationDensityError =
                "Prepare the verified population reference before changing its display."
            return
        }
        if shouldShow, !canShowPopulationDensity {
            populationDensityPNG = nil
            populationDensityOverlay = nil
            populationDensityError =
                "Switch to the verified Dorsal view before showing the population reference."
            return
        }

        populationDensityOverlayInProgress = true
        defer { populationDensityOverlayInProgress = false }
        do {
            let result: ReferenceDensityDisplayResult = try await bridgeClient.request(
                method: "vascular.reference.display",
                params: ReferenceDensityDisplayParameters(
                    visible: shouldShow,
                    opacity: display.opacity
                )
            )
            try ReferenceDensityValidator.validateDisplayMutation(
                result,
                expectedVisible: shouldShow,
                expectedOpacity: display.opacity
            )
            await refreshState()
            guard
                let published = backendState?.populationDensity,
                published.visible == shouldShow,
                published.opacity == display.opacity
            else {
                throw PopulationDensityOperationFailure.displayMutationNotPublished
            }
            if shouldShow, let state = backendState {
                await synchronizePopulationDensity(using: bridgeClient, state: state)
            } else {
                populationDensityVisible = false
                populationDensityPNG = nil
                populationDensityOverlay = nil
            }
        } catch {
            let mutationError = error.localizedDescription
            await refreshState()
            populationDensityError = mutationError
        }
    }

    func refreshState() async {
        guard let bridgeClient, connection.isReady else { return }
        do {
            let previousProjectId = backendState?.project?.projectId
            let previousActiveCalibrationId = activeCalibrationId
            let state: PlannerBridgeState = try await bridgeClient.request(
                method: "state.get",
                params: StateParameters()
            )
            try validate(state: state)
            if let project = state.project {
                let listed: ImplantListResult = try await bridgeClient.request(
                    method: "implant.list",
                    params: ImplantListParameters()
                )
                try ImplantTargetValidator.validateList(listed)
                implantTargets = listed.targets
                let listedTargetIds = Set(listed.targets.map(\.targetId))
                targetProjections = targetProjections.filter {
                    listedTargetIds.contains($0.key)
                }
                if helloResult?.capabilities.subjectAtlasCalibration == true {
                    let listedCalibrations: CalibrationListResult = try await bridgeClient.request(
                        method: "calibration.list",
                        params: CalibrationListParameters(projectId: project.projectId)
                    )
                    try CalibrationValidator.validateList(
                        listedCalibrations,
                        projectId: project.projectId
                    )
                    guard listedCalibrations.projectRevision == project.revision,
                          project.calibrationCount == nil
                            || project.calibrationCount == listedCalibrations.calibrationCount,
                          project.activeCalibrationId == listedCalibrations.activeCalibrationId
                    else {
                        throw CalibrationValidationError.inconsistentCalibrationList
                    }
                    calibrations = listedCalibrations.calibrations
                    activeCalibrationId = listedCalibrations.activeCalibrationId
                    if let selectedId = selectedCalibration?.calibrationId {
                        selectedCalibration = calibrations.first {
                            $0.calibrationId == selectedId
                        }
                    }
                    if previousProjectId != project.projectId
                        || previousActiveCalibrationId != activeCalibrationId
                    {
                        targetProjections = [:]
                    }
                } else {
                    calibrations = []
                    activeCalibrationId = nil
                    selectedCalibration = nil
                    targetProjections = [:]
                }
                if supportsProbePlanning {
                    try await synchronizeProbePlanning(using: bridgeClient, project: project)
                } else {
                    clearProbePlanning()
                }
            } else {
                implantTargets = []
                calibrations = []
                activeCalibrationId = nil
                selectedCalibration = nil
                targetProjections = [:]
                clearProbePlanning()
            }
            backendState = state
            hasUnsavedChanges = state.project?.isDirty ?? false
            clearArchivedDisplayState()
            if state.project != nil {
                await refreshViewerState(using: bridgeClient)
            } else {
                clearViewerState(
                    message: "Create or open an animal plan to browse atlas slices"
                )
            }
        } catch {
            connection = .failed(error.localizedDescription)
            backendState = nil
            implantTargets = []
            calibrations = []
            activeCalibrationId = nil
            selectedCalibration = nil
            targetProjections = [:]
            clearProbePlanning()
            clearArchivedDisplayState()
            clearViewerState(message: "Planning state is unavailable")
        }
    }

    func addUnprojectedImplantTarget(
        label: String,
        apText: String,
        mlText: String,
        dvText: String
    ) async -> Bool {
        implantOperationError = nil
        guard let bridgeClient,
              canStoreImplantTarget,
              let project = backendState?.project
        else {
            implantOperationError = "Open an animal plan before storing an implant site."
            return false
        }
        let normalizedLabel = label.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedLabel.isEmpty else {
            implantOperationError = "Implant-site label cannot be blank."
            return false
        }

        implantOperationInProgress = true
        defer { implantOperationInProgress = false }
        do {
            let coordinates = try BregmaCoordinateInput.parse(
                ap: apText,
                ml: mlText,
                dv: dvText
            )
            let request = ImplantAddParameters(
                projectId: project.projectId,
                expectedProjectRevision: project.revision,
                label: normalizedLabel,
                apMillimetres: coordinates.apMillimetres,
                mlMillimetres: coordinates.mlMillimetres,
                dvMillimetres: coordinates.dvMillimetres
            )
            let result: ImplantMutationResult = try await bridgeClient.request(
                method: "implant.add",
                params: request
            )
            try ImplantTargetValidator.validateAddedMutation(result, request: request)
            await refreshState()
            guard backendState?.project?.revision == result.projectRevision,
                  implantTargets.contains(where: { $0.targetId == result.target.targetId })
            else {
                throw ImplantOperationFailure.mutationNotPublished
            }
            return true
        } catch {
            implantOperationError = error.localizedDescription
            return false
        }
    }

    func removeUnprojectedImplantTarget(targetId: String) async -> Bool {
        implantOperationError = nil
        guard let bridgeClient,
              canStoreImplantTarget,
              let project = backendState?.project
        else {
            implantOperationError = "Open an animal plan before removing an implant site."
            return false
        }

        implantOperationInProgress = true
        defer { implantOperationInProgress = false }
        do {
            let request = ImplantRemoveParameters(
                projectId: project.projectId,
                expectedProjectRevision: project.revision,
                targetId: targetId
            )
            let result: ImplantMutationResult = try await bridgeClient.request(
                method: "implant.remove",
                params: request
            )
            try ImplantTargetValidator.validateRemovedMutation(result, request: request)
            await refreshState()
            guard backendState?.project?.revision == result.projectRevision,
                  !implantTargets.contains(where: { $0.targetId == targetId })
            else {
                throw ImplantOperationFailure.mutationNotPublished
            }
            targetProjections[targetId] = nil
            return true
        } catch {
            implantOperationError = error.localizedDescription
            return false
        }
    }

    func createCalibration(_ request: CalibrationCreateParameters) async -> Bool {
        calibrationOperationError = nil
        guard
            let bridgeClient,
            canManageCalibration,
            let project = backendState?.project,
            request.projectId == project.projectId,
            request.expectedProjectRevision == project.revision
        else {
            calibrationOperationError = "Open the current animal plan before calibrating."
            return false
        }
        calibrationOperationInProgress = true
        defer { calibrationOperationInProgress = false }
        do {
            try CalibrationValidator.validateCreate(request)
            let result: CalibrationMutationResult = try await bridgeClient.request(
                method: "calibration.create",
                params: request
            )
            try CalibrationValidator.validateMutation(
                result,
                projectId: project.projectId,
                expectedStatus: "created",
                expectedRevision: project.revision + 1
            )
            await refreshState()
            guard calibrations.contains(where: {
                $0.calibrationId == result.calibration.calibrationId
            }) else {
                throw CalibrationValidationError.inconsistentCalibrationList
            }
            selectedCalibration = result.calibration
            hasUnsavedChanges = true
            return true
        } catch {
            calibrationOperationError = error.localizedDescription
            return false
        }
    }

    func loadCalibration(calibrationId: String) async -> Bool {
        calibrationOperationError = nil
        guard
            let bridgeClient,
            canManageCalibration,
            let project = backendState?.project
        else {
            calibrationOperationError = "Open the current animal plan before loading calibration data."
            return false
        }
        calibrationOperationInProgress = true
        defer { calibrationOperationInProgress = false }
        do {
            let result: CalibrationGetResult = try await bridgeClient.request(
                method: "calibration.get",
                params: CalibrationGetParameters(
                    projectId: project.projectId,
                    calibrationId: calibrationId
                )
            )
            try CalibrationValidator.validateGet(
                result,
                projectId: project.projectId,
                calibrationId: calibrationId
            )
            selectedCalibration = result.calibration
            return true
        } catch {
            calibrationOperationError = error.localizedDescription
            return false
        }
    }

    func setActiveCalibration(calibrationId: String) async -> Bool {
        calibrationOperationError = nil
        guard
            let bridgeClient,
            canManageCalibration,
            let project = backendState?.project
        else {
            calibrationOperationError = "Open the current animal plan before selecting a calibration."
            return false
        }
        calibrationOperationInProgress = true
        defer { calibrationOperationInProgress = false }
        do {
            let result: CalibrationMutationResult = try await bridgeClient.request(
                method: "calibration.setActive",
                params: CalibrationMutationParameters(
                    projectId: project.projectId,
                    expectedProjectRevision: project.revision,
                    calibrationId: calibrationId
                )
            )
            try CalibrationValidator.validateMutation(
                result,
                projectId: project.projectId,
                expectedStatus: "activeCalibrationSet",
                expectedRevision: project.revision + 1
            )
            targetProjections = [:]
            await refreshState()
            guard activeCalibrationId == calibrationId else {
                throw CalibrationValidationError.inconsistentCalibrationList
            }
            hasUnsavedChanges = true
            return true
        } catch {
            calibrationOperationError = error.localizedDescription
            return false
        }
    }

    func validateCalibration(calibrationId: String) async -> Bool {
        calibrationOperationError = nil
        guard
            let bridgeClient,
            canManageCalibration,
            let project = backendState?.project
        else {
            calibrationOperationError = "Open the current animal plan before validating a calibration."
            return false
        }
        calibrationOperationInProgress = true
        defer { calibrationOperationInProgress = false }
        do {
            let result: CalibrationValidationResult = try await bridgeClient.request(
                method: "calibration.validate",
                params: CalibrationGetParameters(
                    projectId: project.projectId,
                    calibrationId: calibrationId
                )
            )
            try CalibrationValidator.validateValidation(
                result,
                projectId: project.projectId,
                calibrationId: calibrationId
            )
            selectedCalibration = result.calibration
            return true
        } catch {
            calibrationOperationError = error.localizedDescription
            return false
        }
    }

    func removeCalibration(calibrationId: String) async -> Bool {
        calibrationOperationError = nil
        guard
            let bridgeClient,
            canManageCalibration,
            let project = backendState?.project
        else {
            calibrationOperationError = "Open the current animal plan before removing a calibration."
            return false
        }
        calibrationOperationInProgress = true
        defer { calibrationOperationInProgress = false }
        do {
            let result: CalibrationRemoveResult = try await bridgeClient.request(
                method: "calibration.remove",
                params: CalibrationMutationParameters(
                    projectId: project.projectId,
                    expectedProjectRevision: project.revision,
                    calibrationId: calibrationId
                )
            )
            try CalibrationValidator.validateRemove(
                result,
                projectId: project.projectId,
                calibrationId: calibrationId,
                expectedRevision: project.revision + 1
            )
            targetProjections = targetProjections.filter {
                $0.value.provenance.calibrationId != calibrationId
            }
            if selectedCalibration?.calibrationId == calibrationId {
                selectedCalibration = nil
            }
            await refreshState()
            guard !calibrations.contains(where: { $0.calibrationId == calibrationId }) else {
                throw CalibrationValidationError.inconsistentCalibrationList
            }
            hasUnsavedChanges = true
            return true
        } catch {
            calibrationOperationError = error.localizedDescription
            return false
        }
    }

    func projectImplantTarget(targetId: String) async -> Bool {
        calibrationOperationError = nil
        guard
            let bridgeClient,
            canManageCalibration,
            let project = backendState?.project,
            let activeCalibrationId
        else {
            calibrationOperationError = "Select a passing subject calibration before projecting."
            return false
        }
        calibrationOperationInProgress = true
        defer { calibrationOperationInProgress = false }
        do {
            let result: CalibratedTargetProjectionResult = try await bridgeClient.request(
                method: "calibration.projectTarget",
                params: CalibrationProjectTargetParameters(
                    projectId: project.projectId,
                    targetId: targetId
                )
            )
            try CalibrationValidator.validateProjection(
                result,
                projectId: project.projectId,
                targetId: targetId,
                activeCalibrationId: activeCalibrationId
            )
            targetProjections[targetId] = result
            return await navigateToImplantTarget(targetId: targetId)
        } catch {
            targetProjections[targetId] = nil
            calibrationOperationError = error.localizedDescription
            return false
        }
    }

    /// Atomically moves all three orthogonal atlas views to one projected
    /// implant site. The retained coronal, sagittal, and horizontal depths
    /// therefore stay synchronized when the user switches view modes.
    @discardableResult
    func navigateToImplantTarget(targetId: String) async -> Bool {
        calibrationOperationError = nil
        guard let bridgeClient,
              helloResult?.capabilities.atomicAtlasPointNavigation == true,
              !majorVesselNavigationInProgress,
              !projectOperationInProgress,
              pendingViewerMutation == nil,
              viewerMutationWorker == nil,
              let base = authoritativeViewerSnapshot,
              let project = backendState?.project,
              project.projectId.lowercased() == base.projectId.uuidString.lowercased(),
              project.revision == base.projectRevision,
              let target = implantTargets.first(where: { $0.targetId == targetId }),
              let calibration = activeCalibration,
              let projection = SurgeryPlanReadiness.currentProjection(
                  targetProjections[targetId],
                  project: project,
                  target: target,
                  calibration: calibration,
                  atlas: base.atlas
              )
        else {
            calibrationOperationError =
                "Project this implant site, then wait for the current atlas view."
            return false
        }

        majorVesselNavigationInProgress = true
        viewerGeneration &+= 1
        let generation = viewerGeneration
        pendingViewerMutation = nil
        pendingViewerSlice = nil
        viewerRegionSelection = nil
        selectedMajorVesselConflict = nil
        viewerPhase = .updating
        defer { majorVesselNavigationInProgress = false }

        do {
            let point = projection.atlasPoint
            let request = try ViewerPointNavigationParameters(
                projectId: base.projectId,
                expectedProjectRevision: base.projectRevision,
                atlas: base.atlas,
                apMicrometres: point.apMicrometres,
                dvMicrometres: point.dvMicrometres,
                mlMicrometres: point.mlMicrometres
            )
            let result: ViewerPointNavigationResult = try await bridgeClient.request(
                method: ViewerBridgeMethod.pointNavigate.rawValue,
                params: request
            )
            guard generation == viewerGeneration,
                  result.snapshot.projectId == base.projectId,
                  result.snapshot.projectRevision == base.projectRevision + 1,
                  result.navigatedPoint == request.point,
                  result.containingVoxelIndex.ap == projection.containingVoxelIndex.ap,
                  result.containingVoxelIndex.dv == projection.containingVoxelIndex.dv,
                  result.containingVoxelIndex.ml == projection.containingVoxelIndex.ml
            else {
                throw ViewerContractError.invalid(
                    "Implant-site navigation returned a stale or mismatched atlas point."
                )
            }

            var frames = TriPlanarFrameSet()
            for orientation in AtlasSliceOrientation.allCases {
                frames[orientation] = try verifiedFrame(
                    from: result.renderedSlices[orientation],
                    expected: sliceMetadata(orientation, in: result.snapshot),
                    snapshot: result.snapshot
                )
            }
            guard AtlasSliceOrientation.allCases.allSatisfy({ frames[$0] != nil }) else {
                throw ViewerContractError.invalid(
                    "Implant-site navigation did not return all three atlas slices."
                )
            }

            try reconcileBackendProject(with: result.snapshot)
            authoritativeViewerSnapshot = result.snapshot
            viewerSnapshot = result.snapshot
            triPlanarFrames = frames
            viewerRegionSelection = nil
            viewerPhase = .ready
            hasUnsavedChanges = true

            await refreshState()
            guard backendState?.project?.revision == result.snapshot.projectRevision,
                  viewerSnapshot?.projectRevision == result.snapshot.projectRevision,
                  requestedViewerIndex(for: .coronal)
                    == projection.containingVoxelIndex.ap,
                  requestedViewerIndex(for: .sagittal)
                    == projection.containingVoxelIndex.ml,
                  requestedViewerIndex(for: .horizontal)
                    == projection.containingVoxelIndex.dv
            else {
                throw ViewerContractError.invalid(
                    "Implant-site slice depths were not published coherently."
                )
            }
            return true
        } catch {
            let navigationError = error.localizedDescription
            await refreshState()
            calibrationOperationError = navigationError
            return false
        }
    }

    func loadProbeModel(modelId: String, modelVersion: String) async -> Bool {
        probeOperationError = nil
        guard let bridgeClient, supportsProbePlanning else {
            probeOperationError = "The probe catalog is unavailable from this planning service."
            return false
        }
        probeOperationInProgress = true
        defer { probeOperationInProgress = false }
        do {
            let result: ProbeCatalogGetResult = try await bridgeClient.request(
                method: "probe.catalog.get",
                params: ProbeCatalogGetParameters(
                    modelId: modelId,
                    modelVersion: modelVersion
                )
            )
            try ProbePlanningValidator.validateCatalogGet(
                result,
                modelId: modelId,
                modelVersion: modelVersion
            )
            selectedProbeModel = result.model
            return true
        } catch {
            probeOperationError = error.localizedDescription
            return false
        }
    }

    func selectProbePlan(_ planId: String?) async -> Bool {
        probeOperationError = nil
        guard let planId else {
            selectedProbePlanId = nil
            selectedProbePlan = nil
            selectedProbeRegionAnalysis = nil
            clearMajorVesselAnalysis()
            return true
        }
        guard
            let bridgeClient,
            supportsProbePlanning,
            let project = backendState?.project,
            probePlans.contains(where: { $0.planId == planId })
        else {
            probeOperationError = "The selected probe plan is not in the current animal plan."
            return false
        }
        probeOperationInProgress = true
        defer { probeOperationInProgress = false }
        do {
            let result: ProbePlanGetResult = try await bridgeClient.request(
                method: "probe.plan.get",
                params: ProbePlanGetParameters(projectId: project.projectId, planId: planId)
            )
            try ProbePlanningValidator.validatePlanGet(
                result,
                projectId: project.projectId,
                projectRevision: project.revision,
                planId: planId
            )
            if probeCatalog.contains(where: {
                $0.modelId == result.plan.modelId
                    && $0.modelVersion == result.plan.modelVersion
            }) {
                selectedProbeModel = try await fetchProbeCatalogModel(
                    using: bridgeClient,
                    modelId: result.plan.modelId,
                    modelVersion: result.plan.modelVersion,
                    matching: result.plan
                )
            } else {
                // Archived plans retain their checksum-verified embedded geometry
                // for read-only display, but never become a selectable production
                // model or pass the create/update readiness boundary.
                selectedProbeModel = nil
            }
            selectedProbePlanId = planId
            selectedProbePlan = result.plan
            selectedProbeRegionAnalysis = result.plan.hasCurrentPlanningGeometry
                ? result.regionAnalysis : nil
            selectedProbeVesselAnalysis = result.plan.hasCurrentPlanningGeometry
                ? result.majorVesselAnalysis : nil
            reconcileSelectedMajorVesselConflict()
            majorVesselAnalysisError = nil
            return true
        } catch {
            selectedProbePlanId = nil
            selectedProbePlan = nil
            selectedProbeRegionAnalysis = nil
            clearMajorVesselAnalysis()
            probeOperationError = error.localizedDescription
            return false
        }
    }

    func createProbePlan(
        name: String,
        targetId: String,
        modelId: String,
        modelVersion: String,
        placementMode: ProbePlacementMode,
        entryAPText: String,
        entryMLText: String,
        entryDVText: String,
        azimuthText: String,
        elevationText: String,
        insertionDepthText: String,
        axialRotationText: String,
        customGeometryAcknowledged: Bool
    ) async -> Bool {
        probeOperationError = nil
        guard
            let bridgeClient,
            canManageProbePlanning,
            let project = backendState?.project
        else {
            probeOperationError =
                "Open an animal plan and activate a passing subject calibration first."
            return false
        }
        probeOperationInProgress = true
        defer { probeOperationInProgress = false }
        do {
            let numbers = try parseProbeNumbers(
                placementMode: placementMode,
                entryAPText: entryAPText,
                entryMLText: entryMLText,
                entryDVText: entryDVText,
                azimuthText: azimuthText,
                elevationText: elevationText,
                insertionDepthText: insertionDepthText,
                axialRotationText: axialRotationText
            )
            let request = ProbePlanCreateParameters(
                projectId: project.projectId,
                expectedProjectRevision: project.revision,
                targetId: targetId,
                modelId: modelId,
                modelVersion: modelVersion,
                name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                placementMode: placementMode,
                entryAPMillimetres: numbers.entryAP,
                entryMLMillimetres: numbers.entryML,
                entryDVMillimetres: numbers.entryDV,
                azimuthDegrees: numbers.azimuth,
                elevationDegrees: numbers.elevation,
                insertionDepthMicrometres: numbers.depthMicrometres,
                axialRotationDegrees: numbers.rotation,
                customGeometryAcknowledged: customGeometryAcknowledged
            )
            try ProbePlanningValidator.validateCreate(request)
            guard let catalogModel = selectedProbeModel,
                  catalogModel.modelId == request.modelId,
                  catalogModel.modelVersion == request.modelVersion,
                  catalogModel.shanks != nil
            else {
                throw ProbePlanningValidationError.invalid(
                    "Load the exact detailed probe model before creating its animal plan."
                )
            }
            let result: ProbePlanMutationResult = try await bridgeClient.request(
                method: "probe.plan.create",
                params: request
            )
            try ProbePlanningValidator.validateCreatedMutation(
                result,
                request: request,
                catalogModel: catalogModel
            )
            selectedProbePlanId = result.plan.planId
            selectedProbePlan = result.plan
            selectedProbeRegionAnalysis = nil
            clearMajorVesselAnalysis()
            await refreshState()
            guard selectedProbePlan?.planId == result.plan.planId else {
                throw ProbePlanningOperationFailure.mutationNotPublished
            }
            hasUnsavedChanges = true
            return true
        } catch {
            probeOperationError = error.localizedDescription
            return false
        }
    }

    func updateSelectedProbePlan(
        name: String,
        targetId: String,
        modelId: String,
        modelVersion: String,
        placementMode: ProbePlacementMode,
        entryAPText: String,
        entryMLText: String,
        entryDVText: String,
        azimuthText: String,
        elevationText: String,
        insertionDepthText: String,
        axialRotationText: String,
        customGeometryAcknowledged: Bool
    ) async -> Bool {
        probeOperationError = nil
        guard
            let bridgeClient,
            canManageProbePlanning,
            let project = backendState?.project,
            let plan = selectedProbePlan
        else {
            probeOperationError = "Select a current probe plan before updating it."
            return false
        }
        probeOperationInProgress = true
        defer { probeOperationInProgress = false }
        do {
            let numbers = try parseProbeNumbers(
                placementMode: placementMode,
                entryAPText: entryAPText,
                entryMLText: entryMLText,
                entryDVText: entryDVText,
                azimuthText: azimuthText,
                elevationText: elevationText,
                insertionDepthText: insertionDepthText,
                axialRotationText: axialRotationText
            )
            let request = ProbePlanUpdateParameters(
                projectId: project.projectId,
                expectedProjectRevision: project.revision,
                planId: plan.planId,
                expectedPlanInputSha256: plan.inputSha256,
                targetId: targetId,
                modelId: modelId,
                modelVersion: modelVersion,
                name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                placementMode: placementMode,
                entryAPMillimetres: numbers.entryAP,
                entryMLMillimetres: numbers.entryML,
                entryDVMillimetres: numbers.entryDV,
                azimuthDegrees: numbers.azimuth,
                elevationDegrees: numbers.elevation,
                insertionDepthMicrometres: numbers.depthMicrometres,
                axialRotationDegrees: numbers.rotation,
                customGeometryAcknowledged: customGeometryAcknowledged
            )
            try ProbePlanningValidator.validateUpdate(request)
            guard let catalogModel = selectedProbeModel,
                  catalogModel.modelId == request.modelId,
                  catalogModel.modelVersion == request.modelVersion,
                  catalogModel.shanks != nil
            else {
                throw ProbePlanningValidationError.invalid(
                    "Load the exact detailed probe model before updating its animal plan."
                )
            }
            let result: ProbePlanMutationResult = try await bridgeClient.request(
                method: "probe.plan.update",
                params: request
            )
            try ProbePlanningValidator.validateUpdatedMutation(
                result,
                request: request,
                catalogModel: catalogModel
            )
            selectedProbePlanId = result.plan.planId
            selectedProbePlan = result.plan
            selectedProbeRegionAnalysis = nil
            clearMajorVesselAnalysis()
            await refreshState()
            guard selectedProbePlan?.inputSha256 == result.plan.inputSha256 else {
                throw ProbePlanningOperationFailure.mutationNotPublished
            }
            hasUnsavedChanges = true
            return true
        } catch {
            probeOperationError = error.localizedDescription
            return false
        }
    }

    func removeSelectedProbePlan() async -> Bool {
        probeOperationError = nil
        guard
            let bridgeClient,
            canRemoveSelectedProbePlan,
            let project = backendState?.project,
            let plan = selectedProbePlan
        else {
            probeOperationError = "Select a current probe plan before removing it."
            return false
        }
        probeOperationInProgress = true
        defer { probeOperationInProgress = false }
        do {
            let result: ProbePlanRemoveResult = try await bridgeClient.request(
                method: "probe.plan.remove",
                params: ProbePlanRemoveParameters(
                    projectId: project.projectId,
                    expectedProjectRevision: project.revision,
                    planId: plan.planId,
                    expectedPlanInputSha256: plan.inputSha256
                )
            )
            try ProbePlanningValidator.validateRemove(
                result,
                projectId: project.projectId,
                planId: plan.planId,
                expectedRevision: project.revision + 1
            )
            selectedProbePlanId = nil
            selectedProbePlan = nil
            selectedProbeRegionAnalysis = nil
            clearMajorVesselAnalysis()
            await refreshState()
            guard !probePlans.contains(where: { $0.planId == plan.planId }) else {
                throw ProbePlanningOperationFailure.mutationNotPublished
            }
            hasUnsavedChanges = true
            return true
        } catch {
            probeOperationError = error.localizedDescription
            return false
        }
    }

    func analyzeSelectedProbeRegions() async -> Bool {
        probeOperationError = nil
        guard
            let bridgeClient,
            canAnalyzeSelectedProbeRegions,
            let project = backendState?.project,
            let plan = selectedProbePlan
        else {
            probeOperationError = "Select a calibrated probe plan before analyzing regions."
            return false
        }
        probeOperationInProgress = true
        defer { probeOperationInProgress = false }
        do {
            let result: ProbeRegionResult = try await bridgeClient.request(
                method: "probe.region.analyze",
                params: ProbeRegionAnalyzeParameters(
                    projectId: project.projectId,
                    expectedProjectRevision: project.revision,
                    planId: plan.planId,
                    expectedPlanInputSha256: plan.inputSha256
                )
            )
            try ProbePlanningValidator.validateRegionResult(
                result,
                projectId: project.projectId,
                plan: plan,
                expectedStatus: "analyzed",
                expectedRevision: project.revision + 1
            )
            selectedProbeRegionAnalysis = result.regionAnalysis
            await refreshState()
            guard selectedProbeRegionAnalysis?.analysisSha256
                == result.regionAnalysis.analysisSha256
            else { throw ProbePlanningOperationFailure.mutationNotPublished }
            hasUnsavedChanges = true
            return true
        } catch {
            probeOperationError = error.localizedDescription
            return false
        }
    }

    func analyzeSelectedProbeMajorVessels(
        requiredMarginMicrometres: Double,
        registrationUncertaintyMicrometres: Double,
        riskProfileConfirmed: Bool,
        referenceCoverageAcknowledged: Bool
    ) async -> Bool {
        majorVesselAnalysisError = nil
        guard let bridgeClient,
              canAnalyzeMajorVesselClearance,
              let project = backendState?.project,
              let plan = selectedProbePlan,
              let geometry = majorVesselGeometry
        else {
            majorVesselAnalysisError =
                "Select a current probe plan and load the reference vessel geometry first."
            return false
        }
        majorVesselAnalysisInProgress = true
        defer { majorVesselAnalysisInProgress = false }
        do {
            let request = try MajorVesselAnalyzeParameters(
                projectId: project.projectId,
                expectedProjectRevision: project.revision,
                planId: plan.planId,
                expectedPlanInputSha256: plan.inputSha256,
                requiredMarginMicrometres: requiredMarginMicrometres,
                registrationUncertaintyMicrometres: registrationUncertaintyMicrometres,
                riskProfileConfirmed: riskProfileConfirmed,
                referenceCoverageAcknowledged: referenceCoverageAcknowledged
            )
            let result: MajorVesselAnalysisResult = try await bridgeClient.request(
                method: "vessel.major.reference.analyze",
                params: request
            )
            try MajorVesselAnalysisValidator.validateCurrent(
                result,
                projectId: project.projectId,
                projectRevision: project.revision + 1,
                planId: plan.planId,
                planVersion: plan.planVersion,
                planInputSha256: plan.inputSha256
            )
            guard result.analysis.riskProfile.requiredMarginMicrometres
                    == requiredMarginMicrometres,
                  result.analysis.riskProfile.registrationUncertaintyMicrometres
                    == registrationUncertaintyMicrometres,
                  result.analysis.riskProfile.confirmedByUser == riskProfileConfirmed,
                  result.analysis.riskProfile.referenceOnlyCoverageAcknowledged
                    == referenceCoverageAcknowledged,
                  result.analysis.provenance.derivedAssetSha256
                    == geometry.provenance.derivedAssetSha256
            else {
                throw MajorVesselContractError.invalid(
                    "Vessel analysis does not match the current probe and reviewed inputs."
                )
            }
            selectedProbeVesselAnalysis = result
            selectedMajorVesselConflict = nil
            majorVesselNavigationError = nil
            await refreshState()
            guard backendState?.project?.revision == result.projectRevision,
                  selectedProbePlan?.inputSha256 == result.planInputSha256,
                  selectedProbeVesselAnalysis?.analysis.inputSha256
                    == result.analysis.inputSha256
            else { throw ProbePlanningOperationFailure.mutationNotPublished }
            hasUnsavedChanges = true
            return true
        } catch {
            selectedProbeVesselAnalysis = nil
            selectedMajorVesselConflict = nil
            majorVesselAnalysisError = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func navigateToMajorVesselConflict(_ conflict: MajorVesselConflict) async -> Bool {
        majorVesselNavigationError = nil
        guard let bridgeClient,
              canNavigateMajorVesselConflict,
              let base = authoritativeViewerSnapshot,
              let project = backendState?.project,
              project.projectId.lowercased() == base.projectId.uuidString.lowercased(),
              project.revision == base.projectRevision,
              let analysis = selectedProbeVesselAnalysis?.analysis,
              let geometry = majorVesselGeometry,
              analysis.conflicts.contains(conflict),
              analysis.provenance.derivedAssetSha256
                == geometry.provenance.derivedAssetSha256,
              exactVesselSegment(
                  for: conflict,
                  geometry: geometry,
                  orientation: .coronal
              ) != nil
        else {
            majorVesselNavigationError =
                "Wait for the current atlas update, then select a returned vessel conflict."
            return false
        }

        majorVesselNavigationInProgress = true
        viewerGeneration &+= 1
        let generation = viewerGeneration
        pendingViewerMutation = nil
        pendingViewerSlice = nil
        viewerRegionSelection = nil
        viewerPhase = .updating
        defer { majorVesselNavigationInProgress = false }

        do {
            let request = try ViewerPointNavigationParameters(
                projectId: base.projectId,
                expectedProjectRevision: base.projectRevision,
                atlas: base.atlas,
                apMicrometres: conflict.probePoint.apMicrometres,
                dvMicrometres: conflict.probePoint.dvMicrometres,
                mlMicrometres: conflict.probePoint.mlMicrometres
            )
            let result: ViewerPointNavigationResult = try await bridgeClient.request(
                method: ViewerBridgeMethod.pointNavigate.rawValue,
                params: request
            )
            guard generation == viewerGeneration,
                  result.snapshot.projectId == base.projectId,
                  result.snapshot.projectRevision == base.projectRevision + 1,
                  result.navigatedPoint == request.point
            else {
                throw ViewerContractError.invalid(
                    "Conflict navigation returned a stale or mismatched viewer revision."
                )
            }

            var frames = TriPlanarFrameSet()
            for orientation in AtlasSliceOrientation.allCases {
                frames[orientation] = try verifiedFrame(
                    from: result.renderedSlices[orientation],
                    expected: sliceMetadata(orientation, in: result.snapshot),
                    snapshot: result.snapshot
                )
            }
            guard AtlasSliceOrientation.allCases.allSatisfy({ frames[$0] != nil }) else {
                throw ViewerContractError.invalid(
                    "Conflict navigation did not return every orthogonal atlas frame."
                )
            }

            try reconcileBackendProject(with: result.snapshot)
            authoritativeViewerSnapshot = result.snapshot
            viewerSnapshot = result.snapshot
            triPlanarFrames = frames
            viewerRegionSelection = nil
            viewerPhase = .ready
            hasUnsavedChanges = true

            await refreshState()
            guard backendState?.project?.revision == result.snapshot.projectRevision,
                  viewerSnapshot?.projectRevision == result.snapshot.projectRevision,
                  selectedProbeVesselAnalysis?.analysis.conflicts.contains(conflict) == true,
                  majorVesselGeometry?.provenance.derivedAssetSha256
                    == geometry.provenance.derivedAssetSha256
            else {
                throw ViewerContractError.invalid(
                    "Conflict navigation was not coherently published to the animal plan."
                )
            }
            selectedMajorVesselConflict = conflict
            return true
        } catch {
            let navigationError = error.localizedDescription
            await refreshState()
            majorVesselNavigationError = navigationError
            return false
        }
    }

    func clearMajorVesselConflictSelection() {
        selectedMajorVesselConflict = nil
        majorVesselNavigationError = nil
    }

    func invalidateMajorVesselAnalysis() {
        clearMajorVesselAnalysis()
    }

    func exportSelectedProbeRegions(
        format: ProbeRegionExportFormat
    ) async -> ProbeRegionExportResult? {
        probeOperationError = nil
        guard
            let bridgeClient,
            canAnalyzeSelectedProbeRegions,
            let project = backendState?.project,
            let plan = selectedProbePlan,
            let analysis = selectedProbeRegionAnalysis
        else {
            probeOperationError = "Run exact region analysis before exporting."
            return nil
        }
        probeOperationInProgress = true
        defer { probeOperationInProgress = false }
        do {
            let request = ProbeRegionExportParameters(
                projectId: project.projectId,
                expectedProjectRevision: project.revision,
                planId: plan.planId,
                expectedPlanInputSha256: plan.inputSha256,
                format: format
            )
            let result: ProbeRegionExportResult = try await bridgeClient.request(
                method: "probe.region.export",
                params: request
            )
            try ProbePlanningValidator.validateExportGeneration(
                result,
                request: request,
                plan: plan,
                analysis: analysis
            )
            guard backendState?.project?.projectId == result.projectId,
                  backendState?.project?.revision == result.projectRevision,
                  selectedProbePlan?.planId == result.planId,
                  selectedProbePlan?.inputSha256 == result.planInputSha256,
                  selectedProbeRegionAnalysis?.analysisSha256 == result.analysisSha256
            else { throw ProbePlanningOperationFailure.generatedExportBecameStale }
            return result
        } catch {
            probeOperationError = error.localizedDescription
            return nil
        }
    }

    func confirmProbeRegionExport(_ generated: ProbeRegionExportResult) async -> Bool {
        probeOperationError = nil
        guard
            let bridgeClient,
            connection.isReady,
            let project = backendState?.project,
            let plan = selectedProbePlan,
            let analysis = selectedProbeRegionAnalysis,
            project.projectId == generated.projectId,
            project.revision == generated.projectRevision,
            plan.planId == generated.planId,
            plan.inputSha256 == generated.planInputSha256,
            analysis.analysisSha256 == generated.analysisSha256
        else {
            probeOperationError = ProbePlanningOperationFailure.generatedExportBecameStale
                .localizedDescription
            return false
        }

        probeOperationInProgress = true
        defer { probeOperationInProgress = false }
        do {
            let generationRequest = ProbeRegionExportParameters(
                projectId: project.projectId,
                expectedProjectRevision: project.revision,
                planId: plan.planId,
                expectedPlanInputSha256: plan.inputSha256,
                format: generated.format
            )
            try ProbePlanningValidator.validateExportGeneration(
                generated,
                request: generationRequest,
                plan: plan,
                analysis: analysis
            )
            let request = ProbeRegionExportConfirmParameters(
                projectId: generated.projectId,
                expectedProjectRevision: generated.projectRevision,
                planId: generated.planId,
                expectedPlanInputSha256: generated.planInputSha256,
                analysisSha256: generated.analysisSha256,
                format: generated.format,
                contentSha256: generated.contentSha256
            )
            let result: ProbeRegionExportConfirmationResult = try await bridgeClient.request(
                method: "probe.region.export.confirm",
                params: request
            )
            try ProbePlanningValidator.validateExportConfirmation(result, request: request)
            await refreshState()
            guard backendState?.project?.projectId == result.projectId,
                  backendState?.project?.revision == result.projectRevision,
                  backendState?.project?.isDirty == true,
                  hasUnsavedChanges
            else { throw ProbePlanningOperationFailure.exportConfirmationNotPublished }
            return true
        } catch {
            probeOperationError = error.localizedDescription
            return false
        }
    }

    func recordProbeFileError(_ error: Error) {
        probeOperationError = error.localizedDescription
    }

    func probeSliceOverlay(for orientation: AtlasSliceOrientation) -> ProbeSliceOverlay? {
        guard
            let plan = selectedProbePlan,
            plan.hasCurrentPlanningGeometry,
            let frame = viewerFrame(for: orientation),
            let atlas = viewerSnapshot?.atlas
        else { return nil }
        return ProbeSliceOverlayGeometry.make(
            plan: plan,
            orientation: orientation,
            sliceIndex: frame.index,
            resolution: atlas.resolutionMicrometres,
            shape: atlas.shapeVoxels
        )
    }

    var probeDorsalOverlay: ProbeSliceOverlay? {
        guard let plan = selectedProbePlan,
              plan.hasCurrentPlanningGeometry,
              let atlas = viewerSnapshot?.atlas
        else { return nil }
        return ProbeSliceOverlayGeometry.makeDorsalProjection(
            plan: plan,
            resolution: atlas.resolutionMicrometres,
            shape: atlas.shapeVoxels
        )
    }

    func majorVesselSliceOverlay(
        for orientation: AtlasSliceOrientation
    ) -> MajorVesselSliceOverlay? {
        guard let geometry = majorVesselGeometry,
              let frame = viewerFrame(for: orientation)
        else { return nil }
        let key = [
            geometry.provenance.derivedAssetSha256,
            orientation.rawValue,
            String(frame.index),
            String(
                minimumVisibleVesselDiameterMicrometres.bitPattern,
                radix: 16
            ),
        ].joined(separator: ":")
        if let cached = majorVesselSliceOverlayCache[key] { return cached }
        let overlay = MajorVesselSliceOverlayGeometry.make(
            geometry: geometry,
            orientation: orientation,
            sliceIndex: frame.index,
            minimumVisibleDiameterMicrometres:
                minimumVisibleVesselDiameterMicrometres,
            spatialIndex: majorVesselSliceSpatialIndex
        )
        if majorVesselSliceOverlayCache.count >= 24,
           let evictionKey = majorVesselSliceOverlayCache.keys.sorted().first
        {
            majorVesselSliceOverlayCache[evictionKey] = nil
        }
        majorVesselSliceOverlayCache[key] = overlay
        return overlay
    }

    var majorVesselDorsalOverlay: MajorVesselSliceOverlay? {
        majorVesselDorsalProjection
    }

    func majorVesselConflictOverlay(
        for orientation: AtlasSliceOrientation
    ) -> MajorVesselConflictCanvasOverlay? {
        guard let conflict = selectedMajorVesselConflict,
              let atlas = viewerSnapshot?.atlas,
              let frame = viewerFrame(for: orientation),
              let geometry = majorVesselGeometry,
              conflict.probePoint.frameId == AtlasPhysicalCoordinateFrame.expectedFrameId,
              conflict.vesselPoint.frameId == AtlasPhysicalCoordinateFrame.expectedFrameId
        else { return nil }
        let fixedCoordinate = coordinate(conflict.probePoint, axis: orientation.fixedAxis)
        let expectedSlice = Int(floor(
            fixedCoordinate / atlas.resolutionMicrometres[orientation.fixedAxis]
        ))
        guard frame.index == expectedSlice,
              let exactSegment = exactVesselSegment(
                  for: conflict,
                  geometry: geometry,
                  orientation: orientation
              )
        else { return nil }
        return MajorVesselConflictCanvasOverlay(
            conflictId: conflict.conflictId,
            probePoint: imagePoint(
                conflict.probePoint,
                orientation: orientation,
                atlas: atlas
            ),
            vesselPoint: imagePoint(
                conflict.vesselPoint,
                orientation: orientation,
                atlas: atlas
            ),
            exactVesselSegment: exactSegment
        )
    }

    var majorVesselDorsalConflictOverlay: MajorVesselConflictCanvasOverlay? {
        guard let conflict = selectedMajorVesselConflict,
              let atlas = viewerSnapshot?.atlas,
              majorVesselDorsalProjection != nil,
              let geometry = majorVesselGeometry
        else { return nil }
        guard let exactSegment = exactVesselSegment(
            for: conflict,
            geometry: geometry,
            orientation: .horizontal
        ) else { return nil }
        return MajorVesselConflictCanvasOverlay(
            conflictId: conflict.conflictId,
            probePoint: ProbeSliceImagePoint(
                column: conflict.probePoint.mlMicrometres
                    / atlas.resolutionMicrometres.mlMicrometres,
                row: conflict.probePoint.apMicrometres
                    / atlas.resolutionMicrometres.apMicrometres
            ),
            vesselPoint: ProbeSliceImagePoint(
                column: conflict.vesselPoint.mlMicrometres
                    / atlas.resolutionMicrometres.mlMicrometres,
                row: conflict.vesselPoint.apMicrometres
                    / atlas.resolutionMicrometres.apMicrometres
            ),
            exactVesselSegment: exactSegment
        )
    }

    private func exactVesselSegment(
        for conflict: MajorVesselConflict,
        geometry: MajorVesselGeometryResult,
        orientation: AtlasSliceOrientation
    ) -> MajorVesselSliceSegment? {
        let graph = geometry.graph
        let runIndex = conflict.vesselRunIndex
        let segmentIndex = conflict.vesselSegmentIndexInRun
        guard graph.runOffsets.indices.dropLast().contains(runIndex),
              graph.sourceEdgeIndices.indices.contains(runIndex),
              let expectedEdge = Int32(exactly: conflict.vesselSourceEdgeIndex),
              graph.sourceEdgeIndices[runIndex] == expectedEdge
        else { return nil }
        let runStart = graph.runOffsets[runIndex]
        let runEnd = graph.runOffsets[runIndex + 1]
        guard segmentIndex >= 0,
              segmentIndex < runEnd - runStart - 1
        else { return nil }
        let pointIndex = runStart + segmentIndex
        guard graph.pointsASRMicrometres.indices.contains(pointIndex),
              graph.pointsASRMicrometres.indices.contains(pointIndex + 1),
              graph.radiiMicrometres.indices.contains(pointIndex),
              graph.radiiMicrometres.indices.contains(pointIndex + 1)
        else { return nil }
        let start = graph.pointsASRMicrometres[pointIndex]
        let end = graph.pointsASRMicrometres[pointIndex + 1]
        let vesselPoint = SIMD3<Float>(
            Float(conflict.vesselPoint.apMicrometres),
            Float(conflict.vesselPoint.dvMicrometres),
            Float(conflict.vesselPoint.mlMicrometres)
        )
        let delta = end - start
        let lengthSquared = simd_length_squared(delta)
        guard lengthSquared > 0 else { return nil }
        let parameter = max(0, min(1, simd_dot(vesselPoint - start, delta) / lengthSquared))
        guard simd_distance(vesselPoint, start + parameter * delta) <= 1 else {
            return nil
        }
        let resolution = geometry.atlas.resolutionMicrometres
        return MajorVesselSliceSegment(
            start: graphImagePoint(start, orientation: orientation, resolution: resolution),
            end: graphImagePoint(end, orientation: orientation, resolution: resolution),
            startRadiusMicrometres: Double(graph.radiiMicrometres[pointIndex]),
            endRadiusMicrometres: Double(graph.radiiMicrometres[pointIndex + 1]),
            sourceEdgeIndex: expectedEdge,
            runIndex: runIndex,
            segmentIndexInRun: segmentIndex
        )
    }

    private func graphImagePoint(
        _ point: SIMD3<Float>,
        orientation: AtlasSliceOrientation,
        resolution: AtlasASRResolution
    ) -> ProbeSliceImagePoint {
        func value(_ axis: AtlasAnatomicalAxis) -> Double {
            switch axis {
            case .ap: Double(point.x)
            case .dv: Double(point.y)
            case .ml: Double(point.z)
            }
        }
        return ProbeSliceImagePoint(
            column: value(orientation.columnAxis) / resolution[orientation.columnAxis],
            row: value(orientation.rowAxis) / resolution[orientation.rowAxis]
        )
    }

    private func imagePoint(
        _ point: MajorVesselPhysicalPoint,
        orientation: AtlasSliceOrientation,
        atlas: ViewerAtlasIdentity
    ) -> ProbeSliceImagePoint {
        ProbeSliceImagePoint(
            column: coordinate(point, axis: orientation.columnAxis)
                / atlas.resolutionMicrometres[orientation.columnAxis],
            row: coordinate(point, axis: orientation.rowAxis)
                / atlas.resolutionMicrometres[orientation.rowAxis]
        )
    }

    private func coordinate(
        _ point: MajorVesselPhysicalPoint,
        axis: AtlasAnatomicalAxis
    ) -> Double {
        switch axis {
        case .ap: point.apMicrometres
        case .dv: point.dvMicrometres
        case .ml: point.mlMicrometres
        }
    }

    func prepareThreeDimensionalScene() async {
        // `.task` is installed while SwiftUI is updating the representable.
        // Defer every @Published mutation to the next executor turn so scene
        // preparation never publishes from inside that view update.
        await Task.yield()
        guard !Task.isCancelled else { return }
        threeDimensionalGeneration += 1
        let generation = threeDimensionalGeneration
        threeDimensionalPickGeneration += 1
        threeDimensionalPickWorker?.cancel()
        threeDimensionalPickWorker = nil
        threeDimensionalPickInProgress = false
        threeDimensionalPickError = nil
        threeDimensionalRegionHit = nil

        guard let bridgeClient,
              connection.isReady,
              atlasLoadPhase == .ready,
              let project = backendState?.project,
              let rendererAnchor = project.rendererAnchor
        else {
            threeDimensionalSnapshot = nil
            renderedThreeDimensionalSnapshotIdentity = nil
            threeDimensionalPhase = .unavailable(
                "Create or open an animal plan with a verified renderer anchor"
            )
            return
        }
        guard helloResult?.capabilities.atlasMeshDescriptor == true,
              helloResult?.capabilities.atlasAnnotationRayPick == true
        else {
            threeDimensionalSnapshot = nil
            renderedThreeDimensionalSnapshotIdentity = nil
            threeDimensionalPhase = .unavailable(
                "The connected planning service does not expose verified 3D atlas geometry"
            )
            return
        }

        do {
            let meshResult: AtlasMeshResult
            if let cachedRootMesh,
               cachedRootMesh.atlas.metadataSha256 == atlasProvenance?.metadataSha256
            {
                meshResult = cachedRootMesh
            } else {
                threeDimensionalPhase = .loadingDescriptor
                meshResult = try await bridgeClient.request(
                    method: "atlas.mesh",
                    params: try AtlasMeshParameters()
                )
            }
            try Task.checkCancellation()
            guard generation == threeDimensionalGeneration,
                  backendState?.project?.projectId == project.projectId,
                  backendState?.project?.revision == project.revision
            else { return }
            try validateThreeDimensionalAtlas(meshResult)
            cachedRootMesh = meshResult
            if let highlightedAtlasRegion,
               cachedHighlightedRegionMesh?.region != highlightedAtlasRegion
            {
                await selectAtlasRegionForDisplay(
                    highlightedAtlasRegion,
                    clearRayHit: false
                )
                try Task.checkCancellation()
                guard generation == threeDimensionalGeneration else { return }
            }
            let snapshot = try AnimalSceneSnapshot(
                projectId: project.projectId,
                projectRevision: project.revision,
                rendererAnchor: rendererAnchor,
                meshResult: meshResult,
                highlightedRegionMesh: cachedHighlightedRegionMesh,
                selectedProbePlan: selectedProbePlan.flatMap {
                    $0.hasCurrentPlanningGeometry ? $0 : nil
                },
                majorVessels: majorVesselGeometry,
                minimumVisibleVesselDiameterMicrometres:
                    minimumVisibleVesselDiameterMicrometres,
                selectedVesselConflict: selectedMajorVesselConflict
            )
            let preparedPhase = ThreeDimensionalRenderPhaseReducer.phaseAfterPreparing(
                snapshotIdentity: snapshot.identity,
                renderedSnapshotIdentity: renderedThreeDimensionalSnapshotIdentity
            )
            threeDimensionalSnapshot = snapshot
            threeDimensionalPhase = preparedPhase
        } catch is CancellationError {
            return
        } catch {
            guard generation == threeDimensionalGeneration else { return }
            threeDimensionalSnapshot = nil
            renderedThreeDimensionalSnapshotIdentity = nil
            threeDimensionalPhase = .failed(error.localizedDescription)
        }
    }

    func updateThreeDimensionalRenderPhase(
        snapshotIdentity: String,
        phase: AnimalScenePhase
    ) {
        guard ThreeDimensionalRenderPhaseReducer.acceptsCallback(
            snapshotIdentity: snapshotIdentity,
            currentSnapshotIdentity: threeDimensionalSnapshot?.identity
        ) else { return }
        switch phase {
        case .idle, .loading:
            threeDimensionalPhase = .loadingGeometry
        case .ready:
            renderedThreeDimensionalSnapshotIdentity = snapshotIdentity
            threeDimensionalPhase = .ready
        case let .failed(message):
            renderedThreeDimensionalSnapshotIdentity = nil
            threeDimensionalPhase = .failed(message)
        }
    }

    func pickThreeDimensionalRegion(start: AtlasRayPoint, end: AtlasRayPoint) {
        threeDimensionalPickGeneration += 1
        let generation = threeDimensionalPickGeneration
        threeDimensionalPickWorker?.cancel()
        threeDimensionalPickError = nil
        threeDimensionalPickInProgress = true
        guard let bridgeClient, let snapshot = threeDimensionalSnapshot else {
            threeDimensionalPickInProgress = false
            return
        }

        threeDimensionalPickWorker = Task { [weak self] in
            guard let self else { return }
            defer {
                if generation == self.threeDimensionalPickGeneration {
                    self.threeDimensionalPickInProgress = false
                    self.threeDimensionalPickWorker = nil
                }
            }
            do {
                let result: AtlasRayPickResult = try await bridgeClient.request(
                    method: "atlas.ray.pick",
                    params: try AtlasRayPickParameters(start: start, end: end)
                )
                try Task.checkCancellation()
                guard generation == self.threeDimensionalPickGeneration,
                      self.threeDimensionalSnapshot?.identity == snapshot.identity,
                      self.backendState?.project?.projectId == snapshot.projectId,
                      self.backendState?.project?.revision == snapshot.projectRevision,
                      result.atlas.identifier == snapshot.meshResult.atlas.identifier,
                      result.atlas.version == snapshot.meshResult.atlas.version,
                      result.atlas.metadataSha256 == snapshot.meshResult.atlas.metadataSha256
                else { return }
                self.threeDimensionalRegionHit = result.hit
                self.threeDimensionalPickError = nil
                await self.selectAtlasRegionForDisplay(
                    result.hit?.region,
                    clearRayHit: false
                )
            } catch is CancellationError {
                return
            } catch {
                guard generation == self.threeDimensionalPickGeneration else { return }
                self.threeDimensionalRegionHit = nil
                self.threeDimensionalPickError = error.localizedDescription
            }
        }
    }

    func clearAtlasRegionSelection() {
        threeDimensionalPickGeneration += 1
        threeDimensionalPickWorker?.cancel()
        threeDimensionalPickWorker = nil
        threeDimensionalPickInProgress = false
        threeDimensionalPickError = nil
        threeDimensionalRegionHit = nil
        viewerRegionSelection = nil
        clearDorsalRegionPick()
        clearHighlightedAtlasRegion()
    }

    func clearThreeDimensionalRegionSelection() {
        clearAtlasRegionSelection()
    }

    func searchAtlasRegions(query: String) async {
        atlasRegionSearchGeneration &+= 1
        let generation = atlasRegionSearchGeneration
        let normalized = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else {
            atlasRegionSearchResults = []
            atlasRegionSearchInProgress = false
            atlasRegionSearchError = nil
            return
        }
        guard helloResult?.capabilities.atlasRegionSearch == true,
              let bridgeClient,
              let atlasProvenance
        else {
            atlasRegionSearchResults = []
            atlasRegionSearchInProgress = false
            atlasRegionSearchError =
                "The connected service does not expose the complete Allen region search."
            return
        }

        do {
            try await Task.sleep(for: .milliseconds(160))
            try Task.checkCancellation()
            guard generation == atlasRegionSearchGeneration,
                  normalized
                    == atlasRegionSearchText
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            else { return }
            atlasRegionSearchInProgress = true
            atlasRegionSearchError = nil
            let result: AtlasRegionSearchResult = try await bridgeClient.request(
                method: "atlas.search",
                params: try AtlasRegionSearchParameters(query: normalized)
            )
            try Task.checkCancellation()
            guard generation == atlasRegionSearchGeneration,
                  normalized
                    == atlasRegionSearchText
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            else { return }
            guard result.query == normalized,
                  result.atlas.identifier == atlasProvenance.identifier,
                  result.atlas.version == atlasProvenance.version,
                  result.atlas.metadataSha256 == atlasProvenance.metadataSha256
            else {
                throw AtlasSceneContractError.invalid(
                    "Atlas region search does not match the opened reviewed atlas."
                )
            }
            guard let atlasRegionHierarchy,
                  result.results.allSatisfy({
                      atlasRegionHierarchy.region(structureId: $0.region.structureId)
                          == $0.region
                  })
            else {
                throw AtlasSceneContractError.invalid(
                    "Atlas region search returned an identity outside the complete ontology."
                )
            }
            atlasRegionSearchResults = result.results
            atlasRegionSearchInProgress = false
            atlasRegionSearchError = nil
        } catch is CancellationError {
            if generation == atlasRegionSearchGeneration {
                atlasRegionSearchInProgress = false
            }
        } catch {
            guard generation == atlasRegionSearchGeneration else { return }
            atlasRegionSearchResults = []
            atlasRegionSearchInProgress = false
            atlasRegionSearchError = error.localizedDescription
        }
    }

    func selectAtlasRegion(_ region: AtlasRegionSummary) async {
        atlasRegionSearchGeneration &+= 1
        atlasRegionSearchText = ""
        atlasRegionSearchResults = []
        atlasRegionSearchInProgress = false
        atlasRegionSearchError = nil
        threeDimensionalRegionHit = nil
        await selectAtlasRegionForDisplay(region, clearRayHit: true)
    }

    private func selectAtlasRegionForDisplay(
        _ region: AtlasRegionSummary?,
        clearRayHit: Bool
    ) async {
        highlightedRegionGeneration &+= 1
        let generation = highlightedRegionGeneration
        if clearRayHit {
            threeDimensionalPickGeneration &+= 1
            threeDimensionalPickWorker?.cancel()
            threeDimensionalPickWorker = nil
            threeDimensionalPickInProgress = false
            threeDimensionalRegionHit = nil
        }
        guard let region else {
            clearHighlightedAtlasRegion()
            return
        }
        guard atlasRegionHierarchy?.region(structureId: region.structureId) == region else {
            threeDimensionalPickError =
                "The selected region is not part of the verified complete Allen ontology."
            return
        }
        highlightedAtlasRegion = region

        if let cachedHighlightedRegionMesh,
           cachedHighlightedRegionMesh.region == region,
           cachedHighlightedRegionMesh.atlas.metadataSha256
            == atlasProvenance?.metadataSha256
        {
            do {
                try rebuildThreeDimensionalSnapshot()
                threeDimensionalPickError = nil
            } catch {
                threeDimensionalPickError = error.localizedDescription
            }
            return
        }

        guard helloResult?.capabilities.atlasMeshDescriptor == true,
              let bridgeClient,
              let rootMesh = cachedRootMesh ?? threeDimensionalSnapshot?.meshResult
        else {
            // The region identity still remains useful in 2D. Its 3D mesh will
            // load when the full scene is prepared.
            return
        }
        do {
            let meshResult: AtlasMeshResult = try await bridgeClient.request(
                method: "atlas.mesh",
                params: try AtlasMeshParameters(
                    target: .region,
                    structureId: region.structureId
                )
            )
            try Task.checkCancellation()
            guard generation == highlightedRegionGeneration,
                  highlightedAtlasRegion == region
            else { return }
            try validateHighlightedRegionMesh(
                meshResult,
                expectedRegion: region,
                rootMesh: rootMesh
            )
            cachedHighlightedRegionMesh = meshResult
            try rebuildThreeDimensionalSnapshot()
            threeDimensionalPickError = nil
        } catch is CancellationError {
            return
        } catch {
            guard generation == highlightedRegionGeneration else { return }
            cachedHighlightedRegionMesh = nil
            threeDimensionalPickError = error.localizedDescription
            do {
                try rebuildThreeDimensionalSnapshot()
            } catch {
                threeDimensionalPickError = error.localizedDescription
            }
        }
    }

    private func clearHighlightedAtlasRegion() {
        highlightedRegionGeneration &+= 1
        highlightedAtlasRegion = nil
        cachedHighlightedRegionMesh = nil
        do {
            try rebuildThreeDimensionalSnapshot()
        } catch {
            threeDimensionalPickError = error.localizedDescription
        }
    }

    private func rebuildThreeDimensionalSnapshot() throws {
        guard let project = backendState?.project,
              let rendererAnchor = project.rendererAnchor,
              let meshResult = cachedRootMesh ?? threeDimensionalSnapshot?.meshResult
        else { return }
        try validateThreeDimensionalAtlas(meshResult)
        threeDimensionalSnapshot = try AnimalSceneSnapshot(
            projectId: project.projectId,
            projectRevision: project.revision,
            rendererAnchor: rendererAnchor,
            meshResult: meshResult,
            highlightedRegionMesh: cachedHighlightedRegionMesh,
            selectedProbePlan: selectedProbePlan.flatMap {
                $0.hasCurrentPlanningGeometry ? $0 : nil
            },
            majorVessels: majorVesselGeometry,
            minimumVisibleVesselDiameterMicrometres:
                minimumVisibleVesselDiameterMicrometres,
            selectedVesselConflict: selectedMajorVesselConflict
        )
        threeDimensionalPhase = .loadingGeometry
    }

    private func validateHighlightedRegionMesh(
        _ meshResult: AtlasMeshResult,
        expectedRegion: AtlasRegionSummary,
        rootMesh: AtlasMeshResult
    ) throws {
        guard meshResult.target == .region,
              meshResult.region == expectedRegion,
              meshResult.atlas == rootMesh.atlas,
              meshResult.sourceCoordinateFrame == rootMesh.sourceCoordinateFrame
        else {
            throw AtlasSceneContractError.invalid(
                "The selected Allen region mesh does not match the current whole-brain atlas."
            )
        }
    }

    func pickDorsalRegion(column: Int, row: Int) {
        guard helloResult?.capabilities.atlasDorsalRegionPick == true,
              let bridgeClient,
              let dorsalSurface,
              column >= 0,
              column < dorsalSurface.width,
              row >= 0,
              row < dorsalSurface.height
        else { return }

        dorsalPickGeneration &+= 1
        let generation = dorsalPickGeneration
        dorsalPickWorker?.cancel()
        dorsalPickError = nil
        dorsalPickInProgress = true

        dorsalPickWorker = Task { [weak self] in
            guard let self else { return }
            defer {
                if generation == self.dorsalPickGeneration {
                    self.dorsalPickInProgress = false
                    self.dorsalPickWorker = nil
                }
            }
            do {
                let result: DorsalPickResult = try await bridgeClient.request(
                    method: "atlas.dorsal.pick",
                    params: try DorsalPickParameters(column: column, row: row)
                )
                try Task.checkCancellation()
                guard generation == self.dorsalPickGeneration,
                      result.column == column,
                      result.row == row,
                      result.atlas.identifier == self.atlasProvenance?.identifier,
                      result.atlas.version == self.atlasProvenance?.version,
                      result.atlas.metadataSha256 == self.atlasProvenance?.metadataSha256,
                      result.atlas.shapeVoxels.apVoxels == dorsalSurface.height,
                      result.atlas.shapeVoxels.mlVoxels == dorsalSurface.width
                else { return }
                self.dorsalRegionPick = result
                self.dorsalPickError = nil
                Task { @MainActor [weak self] in
                    await self?.selectAtlasRegionForDisplay(
                        result.region,
                        clearRayHit: true
                    )
                }
            } catch is CancellationError {
                return
            } catch {
                guard generation == self.dorsalPickGeneration else { return }
                self.dorsalRegionPick = nil
                self.dorsalPickError = error.localizedDescription
            }
        }
    }

    private func validateThreeDimensionalAtlas(_ meshResult: AtlasMeshResult) throws {
        guard let atlasProvenance,
              meshResult.target == .root,
              meshResult.atlas.identifier == atlasProvenance.identifier,
              meshResult.atlas.version == atlasProvenance.version,
              meshResult.atlas.metadataSha256 == atlasProvenance.metadataSha256,
              meshResult.atlas.orientation == atlasProvenance.orientation,
              [
                  meshResult.atlas.resolutionMicrometres.apMicrometres,
                  meshResult.atlas.resolutionMicrometres.dvMicrometres,
                  meshResult.atlas.resolutionMicrometres.mlMicrometres,
              ] == atlasProvenance.resolutionMicrometres,
              [
                  meshResult.atlas.shapeVoxels.apVoxels,
                  meshResult.atlas.shapeVoxels.dvVoxels,
                  meshResult.atlas.shapeVoxels.mlVoxels,
              ] == atlasProvenance.shapeVoxels
        else {
            throw AtlasSceneContractError.invalid(
                "3D mesh provenance does not match the currently verified mouse atlas."
            )
        }
    }

    private func parseProbeNumbers(
        placementMode: ProbePlacementMode,
        entryAPText: String,
        entryMLText: String,
        entryDVText: String,
        azimuthText: String,
        elevationText: String,
        insertionDepthText: String,
        axialRotationText: String
    ) throws -> (
        entryAP: Double?,
        entryML: Double?,
        entryDV: Double?,
        azimuth: Double?,
        elevation: Double?,
        depthMicrometres: Double?,
        rotation: Double
    ) {
        let entry = placementMode.requiresEntryCoordinates
            ? (
                try CalibrationNumberInput.parse(entryAPText, field: "Entry AP"),
                try CalibrationNumberInput.parse(entryMLText, field: "Entry ML"),
                try CalibrationNumberInput.parse(entryDVText, field: "Entry DV")
            )
            : nil
        let angles = placementMode.requiresAnglesAndDepth
            ? (
                try CalibrationNumberInput.parse(azimuthText, field: "Azimuth"),
                try CalibrationNumberInput.parse(elevationText, field: "Elevation"),
                ProbeInputUnits.micrometres(
                    fromMillimetres: try CalibrationNumberInput.parse(
                        insertionDepthText,
                        field: "Insertion depth (mm)"
                    )
                )
            )
            : nil
        return (
            entry?.0,
            entry?.1,
            entry?.2,
            angles?.0,
            angles?.1,
            angles?.2,
            try CalibrationNumberInput.parse(axialRotationText, field: "Axial rotation")
        )
    }

    func viewerMetadata(for orientation: AtlasSliceOrientation) -> TriPlanarSliceMetadata? {
        guard let slices = viewerSnapshot?.slices else { return nil }
        switch orientation {
        case .coronal: return slices.coronal
        case .sagittal: return slices.sagittal
        case .horizontal: return slices.horizontal
        }
    }

    func viewerFrame(for orientation: AtlasSliceOrientation) -> VerifiedAtlasSliceFrame? {
        triPlanarFrames[orientation]
    }

    /// Render an export-only slice without changing any of the three retained
    /// interactive depths. The caller supplies the captured project and atlas
    /// identity so an export cannot quietly mix state across an await.
    func surgeryPlanSliceFrame(
        for orientation: AtlasSliceOrientation,
        index: Int,
        expectedProjectId: String,
        expectedProjectRevision: Int,
        expectedAtlasMetadataSHA256: String
    ) async throws -> VerifiedAtlasSliceFrame {
        guard let bridgeClient,
              let project = backendState?.project,
              project.projectId == expectedProjectId,
              project.revision == expectedProjectRevision,
              let atlas = viewerSnapshot?.atlas,
              atlas.metadataSha256 == expectedAtlasMetadataSHA256,
              index >= 0,
              index < atlas.shapeVoxels[orientation.fixedAxis]
        else {
            throw ViewerContractError.invalid(
                "The target-centred surgery-plan slice identity is no longer current."
            )
        }
        let result: AtlasSliceResult = try await bridgeClient.request(
            method: "atlas.slice",
            params: AtlasSliceParameters(
                orientation: orientation.rawValue,
                index: index
            )
        )
        guard let currentProject = backendState?.project,
              currentProject.projectId == expectedProjectId,
              currentProject.revision == expectedProjectRevision,
              viewerSnapshot?.atlas.metadataSha256 == expectedAtlasMetadataSHA256
        else {
            throw ViewerContractError.invalid(
                "The animal plan changed while its target-centred slice was rendered."
            )
        }

        let expectedWidth = atlas.shapeVoxels[orientation.columnAxis]
        let expectedHeight = atlas.shapeVoxels[orientation.rowAxis]
        let expectedSliceCount = atlas.shapeVoxels[orientation.fixedAxis]
        let expectedCenter = (
            Double(index) + 0.5
        ) * atlas.resolutionMicrometres[orientation.fixedAxis]
        guard result.protocolVersion == BridgeProtocolVersion.current,
              result.mimeType == "image/png",
              result.orientation == orientation.rawValue,
              result.index == index,
              result.sliceCount == expectedSliceCount,
              result.width == expectedWidth,
              result.height == expectedHeight,
              result.fixedAxis == orientation.fixedAxis.rawValue,
              result.rowAxis == orientation.rowAxis.rawValue,
              result.columnAxis == orientation.columnAxis.rawValue,
              abs(result.sliceCenterMicrometres - expectedCenter) <= 1e-9,
              result.atlas.identifier == atlas.identifier,
              result.atlas.version == atlas.version,
              result.atlas.metadataSha256 == atlas.metadataSha256,
              result.atlas.resolutionMicrometres == [
                  atlas.resolutionMicrometres.apMicrometres,
                  atlas.resolutionMicrometres.dvMicrometres,
                  atlas.resolutionMicrometres.mlMicrometres,
              ],
              result.atlas.shapeVoxels == [
                  atlas.shapeVoxels.apVoxels,
                  atlas.shapeVoxels.dvVoxels,
                  atlas.shapeVoxels.mlVoxels,
              ]
        else {
            throw ViewerContractError.invalid(
                "The rendered surgery-plan slice does not match its captured target and atlas."
            )
        }
        return VerifiedAtlasSliceFrame(
            orientation: orientation,
            index: result.index,
            sliceCount: result.sliceCount,
            width: result.width,
            height: result.height,
            fixedAxis: orientation.fixedAxis,
            rowAxis: orientation.rowAxis,
            columnAxis: orientation.columnAxis,
            sliceCenterMicrometres: result.sliceCenterMicrometres,
            png: try verifiedPNG(
                base64: result.pngBase64,
                mimeType: result.mimeType
            )
        )
    }

    func requestedViewerIndex(for orientation: AtlasSliceOrientation) -> Int? {
        if let pendingViewerSlice, pendingViewerSlice.orientation == orientation {
            return pendingViewerSlice.index
        }
        return viewerFrame(for: orientation)?.index ?? viewerMetadata(for: orientation)?.index
    }

    func requestViewerSlice(_ orientation: AtlasSliceOrientation, index: Int) {
        guard !majorVesselNavigationInProgress,
              let frame = viewerFrame(for: orientation)
        else { return }
        let clamped = min(frame.sliceCount - 1, max(0, index))
        if requestedViewerIndex(for: orientation) == clamped { return }
        viewerRegionSelection = nil
        pendingViewerSlice = PendingViewerSlice(orientation: orientation, index: clamped)
        enqueueViewerMutation(.slice(orientation: orientation, index: clamped))
    }

    func stepViewerSlice(_ orientation: AtlasSliceOrientation, delta: Int) {
        guard delta != 0, let current = requestedViewerIndex(for: orientation) else { return }
        requestViewerSlice(orientation, index: current + delta)
    }

    func pickViewerRegion(
        orientation: AtlasSliceOrientation,
        column: Int,
        row: Int
    ) {
        guard let frame = viewerFrame(for: orientation) else { return }
        let authoritativeIndex = authoritativeViewerSnapshot.map {
            sliceMetadata(orientation, in: $0).index
        }
        guard ViewerInteractionPolicy.allowsRegionPick(
            orientation: orientation,
            displayedSliceIndex: frame.index,
            authoritativeSliceIndex: authoritativeIndex,
            pendingSliceOrientation: pendingViewerSlice?.orientation,
            atomicNavigationInProgress: majorVesselNavigationInProgress
        ),
            column >= 0, column < frame.width,
            row >= 0, row < frame.height
        else { return }
        enqueueViewerMutation(
            .regionPick(
                orientation: orientation,
                index: frame.index,
                column: column,
                row: row
            )
        )
    }

    private func enqueueViewerMutation(_ mutation: ViewerMutation) {
        guard bridgeClient != nil, authoritativeViewerSnapshot != nil else { return }
        viewerGeneration += 1
        pendingViewerMutation = mutation
        viewerPhase = .updating
        guard viewerMutationWorker == nil else { return }
        viewerMutationWorker = Task { [weak self] in
            do {
                try await Task.sleep(for: .milliseconds(12))
            } catch {
                return
            }
            await self?.processViewerMutationQueue()
        }
    }

    private func processViewerMutationQueue() async {
        defer { viewerMutationWorker = nil }
        while !Task.isCancelled, let mutation = pendingViewerMutation {
            pendingViewerMutation = nil
            let generation = viewerGeneration
            guard let bridgeClient, let base = authoritativeViewerSnapshot else {
                clearViewerState(message: "The atlas-slice viewer has no active project")
                return
            }
            do {
                switch mutation {
                case let .slice(orientation, index):
                    let result: ViewerSliceRenderResult = try await bridgeClient.request(
                        method: ViewerBridgeMethod.sliceRender.rawValue,
                        params: try ViewerSliceRenderParameters(
                            projectId: base.projectId,
                            expectedProjectRevision: base.projectRevision,
                            orientation: orientation,
                            index: index
                        )
                    )
                    let frame = try verifiedFrame(
                        from: result.renderedSlice,
                        expected: sliceMetadata(orientation, in: result.snapshot),
                        snapshot: result.snapshot
                    )
                    try reconcileBackendProject(with: result.snapshot)
                    authoritativeViewerSnapshot = result.snapshot
                    viewerSnapshot = result.snapshot
                    viewerRegionSelection = nil
                    let isLatest = ViewerMutationPublicationPolicy.publishSlice(
                        frame,
                        requestGeneration: generation,
                        currentGeneration: viewerGeneration,
                        into: &triPlanarFrames
                    )
                    guard isLatest else { continue }
                case let .regionPick(orientation, index, column, row):
                    let result: ViewerRegionPickResult = try await bridgeClient.request(
                        method: ViewerBridgeMethod.regionPick.rawValue,
                        params: try ViewerRegionPickParameters(
                            projectId: base.projectId,
                            expectedProjectRevision: base.projectRevision,
                            orientation: orientation,
                            index: index,
                            column: column,
                            row: row
                        )
                    )
                    try reconcileBackendProject(with: result.snapshot)
                    authoritativeViewerSnapshot = result.snapshot
                    let isLatest = ViewerMutationPublicationPolicy.publishRegionSelection(
                        result.snapshot.selection,
                        requestGeneration: generation,
                        currentGeneration: viewerGeneration,
                        into: &viewerRegionSelection
                    )
                    guard isLatest else { continue }
                    viewerSnapshot = result.snapshot
                    let selectedRegion = result.snapshot.selection?.region
                    Task { @MainActor [weak self] in
                        await self?.selectAtlasRegionForDisplay(
                            selectedRegion,
                            clearRayHit: true
                        )
                    }
                }
                pendingViewerSlice = nil
                viewerPhase = .ready
            } catch {
                guard generation == viewerGeneration else { continue }
                pendingViewerSlice = nil
                viewerPhase = .failed(error.localizedDescription)
            }
        }
        if pendingViewerMutation == nil, case .updating = viewerPhase {
            viewerPhase = viewerSnapshot == nil
                ? .unavailable("The atlas-slice viewer has no active project")
                : .ready
        }
    }

    private func reconcileBackendProject(
        with snapshot: ViewerCanonicalSnapshot
    ) throws {
        guard let state = backendState,
              let project = state.project,
              UUID(uuidString: project.projectId) == snapshot.projectId
        else {
            throw ViewerContractError.invalid(
                "Viewer mutation project identity does not match the open animal plan."
            )
        }
        backendState = state.updatingProjectRevision(
            snapshot.projectRevision,
            isDirty: true
        )
        hasUnsavedChanges = true
    }

    private func refreshViewerState(using bridgeClient: BridgeClient) async {
        viewerGeneration += 1
        let generation = viewerGeneration
        pendingViewerMutation = nil
        pendingViewerSlice = nil
        viewerRegionSelection = nil
        viewerPhase = .loading
        do {
            let result: ViewerStateResult = try await bridgeClient.request(
                method: ViewerBridgeMethod.stateGet.rawValue,
                params: ViewerStateParameters()
            )
            guard generation == viewerGeneration else { return }
            if authoritativeViewerSnapshot?.projectId != result.snapshot.projectId {
                triPlanarFrames = TriPlanarFrameSet()
            }
            authoritativeViewerSnapshot = result.snapshot
            viewerSnapshot = result.snapshot
            viewerRegionSelection = result.snapshot.selection
            try await loadTriPlanarFrames(
                for: result.snapshot,
                using: bridgeClient,
                generation: generation
            )
            guard generation == viewerGeneration else { return }
            viewerPhase = .ready
        } catch {
            guard generation == viewerGeneration else { return }
            authoritativeViewerSnapshot = nil
            viewerSnapshot = nil
            viewerRegionSelection = nil
            triPlanarFrames = TriPlanarFrameSet()
            viewerPhase = .failed(error.localizedDescription)
        }
    }

    private func loadTriPlanarFrames(
        for snapshot: ViewerCanonicalSnapshot,
        using bridgeClient: BridgeClient,
        generation: Int
    ) async throws {
        var frames = triPlanarFrames
        for orientation in AtlasSliceOrientation.allCases {
            guard generation == viewerGeneration else { return }
            let metadata = sliceMetadata(orientation, in: snapshot)
            if let frame = frames[orientation],
               frame.index == metadata.index,
               frame.sliceCount == metadata.sliceCount,
               frame.fixedAxis == metadata.fixedAxis,
               frame.rowAxis == metadata.rowAxis,
               frame.columnAxis == metadata.columnAxis
            {
                continue
            }
            let result: AtlasSliceResult = try await bridgeClient.request(
                method: "atlas.slice",
                params: AtlasSliceParameters(
                    orientation: orientation.rawValue,
                    index: metadata.index
                )
            )
            let png = try verifiedPNG(base64: result.pngBase64, mimeType: result.mimeType)
            try validate(
                slice: result,
                expected: metadata,
                snapshot: snapshot
            )
            guard generation == viewerGeneration else { return }
            frames[orientation] = VerifiedAtlasSliceFrame(
                orientation: orientation,
                index: result.index,
                sliceCount: result.sliceCount,
                width: result.width,
                height: result.height,
                fixedAxis: metadata.fixedAxis,
                rowAxis: metadata.rowAxis,
                columnAxis: metadata.columnAxis,
                sliceCenterMicrometres: result.sliceCenterMicrometres,
                png: png
            )
            triPlanarFrames = frames
        }
    }

    private func validate(
        slice: AtlasSliceResult,
        expected: TriPlanarSliceMetadata,
        snapshot: ViewerCanonicalSnapshot
    ) throws {
        let expectedWidth = voxelCount(expected.columnAxis, in: snapshot)
        let expectedHeight = voxelCount(expected.rowAxis, in: snapshot)
        guard
            slice.protocolVersion == BridgeProtocolVersion.current,
            slice.orientation == expected.orientation.rawValue,
            slice.index == expected.index,
            slice.sliceCount == expected.sliceCount,
            slice.fixedAxis == expected.fixedAxis.rawValue,
            slice.rowAxis == expected.rowAxis.rawValue,
            slice.columnAxis == expected.columnAxis.rawValue,
            abs(slice.sliceCenterMicrometres - expected.sliceCenterMicrometres) <= 1e-9,
            slice.width == expectedWidth,
            slice.height == expectedHeight,
            slice.atlas.identifier == snapshot.atlas.identifier,
            slice.atlas.version == snapshot.atlas.version,
            slice.atlas.metadataSha256 == snapshot.atlas.metadataSha256
        else {
            throw ViewerContractError.invalid(
                "Rendered slice metadata does not match the independent viewer state."
            )
        }
    }

    private func verifiedFrame(
        from slice: AtlasSliceResult,
        expected: TriPlanarSliceMetadata,
        snapshot: ViewerCanonicalSnapshot
    ) throws -> VerifiedAtlasSliceFrame {
        try validate(slice: slice, expected: expected, snapshot: snapshot)
        let png = try verifiedPNG(base64: slice.pngBase64, mimeType: slice.mimeType)
        return VerifiedAtlasSliceFrame(
            orientation: expected.orientation,
            index: slice.index,
            sliceCount: slice.sliceCount,
            width: slice.width,
            height: slice.height,
            fixedAxis: expected.fixedAxis,
            rowAxis: expected.rowAxis,
            columnAxis: expected.columnAxis,
            sliceCenterMicrometres: slice.sliceCenterMicrometres,
            png: png
        )
    }

    private func voxelCount(
        _ axis: AtlasAnatomicalAxis,
        in snapshot: ViewerCanonicalSnapshot
    ) -> Int {
        switch axis {
        case .ap: snapshot.atlas.shapeVoxels.apVoxels
        case .dv: snapshot.atlas.shapeVoxels.dvVoxels
        case .ml: snapshot.atlas.shapeVoxels.mlVoxels
        }
    }

    private func sliceMetadata(
        _ orientation: AtlasSliceOrientation,
        in snapshot: ViewerCanonicalSnapshot
    ) -> TriPlanarSliceMetadata {
        switch orientation {
        case .coronal: snapshot.slices.coronal
        case .sagittal: snapshot.slices.sagittal
        case .horizontal: snapshot.slices.horizontal
        }
    }

    private func clearViewerState(message: String) {
        viewerMutationWorker?.cancel()
        viewerMutationWorker = nil
        pendingViewerMutation = nil
        pendingViewerSlice = nil
        authoritativeViewerSnapshot = nil
        viewerSnapshot = nil
        viewerRegionSelection = nil
        triPlanarFrames = TriPlanarFrameSet()
        viewerPhase = .unavailable(message)
    }

    private func loadDorsalSurface() async {
        clearDorsalRegionPick()
        clearArchivedDisplayState()
        guard let bridgeClient, atlasProvenance != nil else {
            dorsalLoadPhase = .unavailable("The reviewed atlas is not open")
            return
        }
        dorsalLoadPhase = .loading
        do {
            let result: AtlasDorsalResult = try await bridgeClient.request(
                method: "atlas.dorsal",
                params: AtlasDorsalParameters()
            )
            guard
                result.atlas.identifier == SafetyPolicy.supportedAtlasIdentifier,
                result.atlas.version == SafetyPolicy.supportedAtlasVersion,
                result.atlas.resolutionMicrometres == [25, 25, 25],
                result.rowAxis == "AP",
                result.columnAxis == "ML",
                result.displayLabel
                    == "Allen atlas dorsal surface projection — not a subject skull surface"
            else {
                throw StateValidationFailure.unsupportedAtlas
            }
            dorsalSurfacePNG = try verifiedPNG(
                base64: result.pngBase64,
                mimeType: result.mimeType
            )
            dorsalSurface = result
            dorsalLoadPhase = .ready
        } catch {
            dorsalSurface = nil
            dorsalSurfacePNG = nil
            dorsalLoadPhase = .failed(error.localizedDescription)
        }
    }

    private func clearDorsalRegionPick() {
        dorsalPickGeneration &+= 1
        dorsalPickWorker?.cancel()
        dorsalPickWorker = nil
        dorsalRegionPick = nil
        dorsalPickInProgress = false
        dorsalPickError = nil
    }

    private func loadMajorVesselGeometry() async {
        guard let bridgeClient,
              let atlasProvenance,
              helloResult?.capabilities.auditedReferenceMajorVessels == true
        else {
            majorVesselGeometry = nil
            majorVesselDorsalProjection = nil
            visibleMajorVesselSegmentCount = 0
            majorVesselSliceSpatialIndex = nil
            majorVesselSliceOverlayCache = [:]
            majorVesselLoadError = (
                "The connected planning service does not provide the audited VesSAP "
                    + "major-vessel display capability."
            )
            return
        }
        if let geometry = majorVesselGeometry,
           geometry.atlas.metadataSha256 == atlasProvenance.metadataSha256,
           majorVesselSliceSpatialIndex != nil,
           majorVesselDorsalProjection != nil
        {
            return
        }
        majorVesselLoadInProgress = true
        majorVesselLoadError = nil
        defer { majorVesselLoadInProgress = false }
        do {
            let geometry: MajorVesselGeometryResult = try await bridgeClient.request(
                method: "vessel.major.reference.geometry",
                params: MajorVesselReferenceParameters()
            )
            guard geometry.atlas.identifier == atlasProvenance.identifier,
                  geometry.atlas.version == atlasProvenance.version,
                  geometry.atlas.metadataSha256 == atlasProvenance.metadataSha256,
                  [
                      geometry.atlas.resolutionMicrometres.apMicrometres,
                      geometry.atlas.resolutionMicrometres.dvMicrometres,
                      geometry.atlas.resolutionMicrometres.mlMicrometres,
                  ] == atlasProvenance.resolutionMicrometres,
                  [
                      geometry.atlas.shapeVoxels.apVoxels,
                      geometry.atlas.shapeVoxels.dvVoxels,
                      geometry.atlas.shapeVoxels.mlVoxels,
                  ] == atlasProvenance.shapeVoxels
            else {
                throw MajorVesselContractError.invalid(
                    "Major-vessel geometry does not match the open atlas."
                )
            }
            let minimumVisibleDiameterMicrometres =
                minimumVisibleVesselDiameterMicrometres
            let derived = await Task.detached(priority: .userInitiated) {
                let dorsalOverlay = MajorVesselSliceOverlayGeometry.makeDorsalProjection(
                    geometry: geometry,
                    minimumVisibleDiameterMicrometres:
                        minimumVisibleDiameterMicrometres
                )
                let dorsalWidth = geometry.atlas.shapeVoxels.mlVoxels
                let dorsalHeight = geometry.atlas.shapeVoxels.apVoxels
                return (
                    MajorVesselSliceSpatialIndex(geometry: geometry),
                    dorsalOverlay,
                    MajorVesselDisplayFilter.visibleSegmentCount(
                        graph: geometry.graph,
                        minimumDiameterMicrometres:
                            minimumVisibleDiameterMicrometres
                    ),
                    MajorVesselRasterizer.render(
                        overlay: dorsalOverlay,
                        imagePixelWidth: dorsalWidth,
                        imagePixelHeight: dorsalHeight
                    )
                )
            }.value
            majorVesselGeometry = geometry
            majorVesselSliceSpatialIndex = derived.0
            if minimumVisibleVesselDiameterMicrometres
                == minimumVisibleDiameterMicrometres
            {
                majorVesselDorsalProjection = derived.1
                visibleMajorVesselSegmentCount = derived.2
                if let raster = derived.3 {
                    MajorVesselRasterCache.insert(
                        raster,
                        overlay: derived.1,
                        imagePixelWidth: geometry.atlas.shapeVoxels.mlVoxels,
                        imagePixelHeight: geometry.atlas.shapeVoxels.apVoxels
                    )
                }
                majorVesselSliceOverlayCache = [:]
            } else {
                // The operator moved the diameter slider while the detached
                // derivation was running. Geometry is now available, so
                // rebuild every threshold-dependent view from the current
                // preference instead of publishing stale count/Dorsal data.
                refreshMajorVesselDisplayFilter()
            }
        } catch {
            majorVesselGeometry = nil
            majorVesselDorsalProjection = nil
            visibleMajorVesselSegmentCount = 0
            majorVesselSliceSpatialIndex = nil
            majorVesselSliceOverlayCache = [:]
            majorVesselLoadError = error.localizedDescription
        }
    }

    func importSubjectVesselImage(from url: URL) async {
        vesselImportError = nil
        let accessed = url.startAccessingSecurityScopedResource()
        defer {
            if accessed { url.stopAccessingSecurityScopedResource() }
        }
        do {
            guard let bridgeClient, canImportSubjectVessels else {
                throw VesselImportFailure.backendNotReady
            }
            vesselImportInProgress = true
            defer { vesselImportInProgress = false }

            let data = try Data(contentsOf: url, options: [.mappedIfSafe])
            guard !data.isEmpty else {
                throw VesselImportFailure.emptyFile
            }
            let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
            localVessel = LocalVesselProvenance(
                fileName: url.lastPathComponent,
                fileURL: url,
                byteCount: data.count,
                sha256: digest
            )

            let imported: VascularImportResult = try await bridgeClient.request(
                method: "vascular.import",
                params: VascularImportParameters(path: url.path)
            )
            await refreshState()
            guard imported.image.subjectSpecific else {
                throw VesselImportFailure.notSubjectSpecific
            }
            guard
                imported.image.sourceSha256 == digest,
                imported.image.byteSize == data.count
            else {
                throw VesselImportFailure.provenanceMismatch
            }
            importedVessel = imported.image
            hasUnsavedChanges = true

            let preview: VascularPreviewResult = try await bridgeClient.request(
                method: "vascular.preview",
                params: VascularPreviewParameters(imageId: imported.image.imageId)
            )
            guard
                preview.imageId == imported.image.imageId,
                preview.originalWidthPixels == imported.image.widthPixels,
                preview.originalHeightPixels == imported.image.heightPixels
            else {
                throw VesselImportFailure.previewMismatch
            }
            subjectPreviewPNG = try verifiedPNG(
                base64: preview.pngBase64,
                mimeType: preview.mimeType
            )
        } catch {
            vesselImportError = error.localizedDescription
        }
    }

    func registerSubjectVessels(
        method: String,
        landmarks: [VascularLandmarkParameters],
        lateralityConfirmed: Bool
    ) async -> Bool {
        registrationError = nil
        guard
            let bridgeClient,
            let imageId = activeSubjectImageId,
            canRegisterSubjectVessels
        else {
            registrationError = "Import and verify a subject image before registration."
            return false
        }
        let enabledCount = landmarks.count(where: \.enabled)
        let requiredCount = method == "affine" ? 3 : 2
        guard enabledCount >= requiredCount, lateralityConfirmed else {
            registrationError = "Registration prerequisites are incomplete."
            return false
        }
        guard landmarks.allSatisfy({ landmark in
            !landmark.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && landmark.label.count <= 200
                && [
                    landmark.imageColumnPixels,
                    landmark.imageRowPixels,
                    landmark.atlasApMicrometres,
                    landmark.atlasMlMicrometres,
                ].allSatisfy(\.isFinite)
        }) else {
            registrationError = "Every landmark must have a label and finite coordinates."
            return false
        }

        registrationInProgress = true
        defer { registrationInProgress = false }
        do {
            let result: VascularRegisterResult = try await bridgeClient.request(
                method: "vascular.register",
                params: VascularRegisterParameters(
                    imageId: imageId,
                    method: method,
                    landmarks: landmarks,
                    lateralityConfirmed: lateralityConfirmed
                )
            )
            await refreshState()
            guard
                result.status == "registered",
                result.lateralityConfirmed,
                result.visible,
                result.rmsResidualMicrometres.isFinite,
                result.maximumResidualMicrometres.isFinite,
                result.rmsResidualMicrometres >= 0,
                result.maximumResidualMicrometres >= 0
            else {
                throw RegistrationFailure.invalidResult
            }
            registrationResult = result
            hasUnsavedChanges = true
            if let state = backendState {
                await loadRegisteredOverlayIfAvailable(using: bridgeClient, state: state)
            }
            return subjectOverlayPNG != nil
        } catch {
            subjectOverlayPNG = nil
            registrationError = error.localizedDescription
            return false
        }
    }

    func saveProject(to url: URL) async -> Bool {
        projectOperationError = nil
        guard let bridgeClient,
              canSaveProject,
              let project = backendState?.project
        else {
            projectOperationError = "There is no connected project to save."
            return false
        }
        projectOperationInProgress = true
        defer { projectOperationInProgress = false }
        do {
            let result: ProjectSaveResult = try await bridgeClient.request(
                method: "project.save",
                params: ProjectSaveParameters(
                    projectId: project.projectId,
                    expectedProjectRevision: project.revision,
                    path: url.path
                )
            )
            guard
                result.status == "saved",
                result.projectId.lowercased() == project.projectId.lowercased(),
                result.projectRevision == project.revision + 1,
                canonicalPath(result.path) == canonicalPath(url.path)
            else {
                throw ProjectOperationFailure.pathMismatch
            }
            await refreshState()
            guard backendState?.project?.revision == result.projectRevision else {
                throw ProjectOperationFailure.pathMismatch
            }
            hasUnsavedChanges = false
            projectRecoveryNotice = nil
            return true
        } catch {
            projectOperationError = error.localizedDescription
            return false
        }
    }

    func openProject(at url: URL) async -> Bool {
        projectOperationError = nil
        guard let bridgeClient, canOpenProject else {
            projectOperationError = "Open the verified atlas before opening a project."
            return false
        }
        projectOperationInProgress = true
        defer { projectOperationInProgress = false }
        do {
            let result: ProjectOpenResult = try await bridgeClient.request(
                method: "project.open",
                params: ProjectOpenParameters(path: url.path)
            )
            localVessel = nil
            importedVessel = nil
            subjectPreviewPNG = nil
            subjectOverlayPNG = nil
            registrationResult = nil
            clearPopulationDensity(clearPreparation: true)
            await refreshState()
            let selectedPath = canonicalPath(url.path)
            let sourcePath = canonicalPath(result.sourcePath)
            let exactSource = sourcePath == selectedPath
            let verifiedBackupRecovery = result.recoveredFromBackup
                && result.requiresSaveAs
                && sourcePath == canonicalPath(url.path + ".bak")
            guard result.status == "opened", exactSource || verifiedBackupRecovery else {
                throw ProjectOperationFailure.pathMismatch
            }
            hasUnsavedChanges = result.requiresSaveAs
            projectRecoveryNotice = verifiedBackupRecovery
                ? "Recovered from verified backup; use Save As before further work."
                : nil
            return backendState?.project?.animalResearchOnlyAcknowledged == true
        } catch {
            projectOperationError = error.localizedDescription
            return false
        }
    }

    private func fetchProbeCatalogModel(
        using bridgeClient: BridgeClient,
        modelId: String,
        modelVersion: String,
        matching plan: ProbePlanDetail? = nil
    ) async throws -> ProbeCatalogModel {
        guard probeCatalog.contains(where: {
            $0.modelId == modelId && $0.modelVersion == modelVersion
        }) else {
            throw ProbePlanningValidationError.invalid(
                "The plan's exact probe model is not present in the reviewed catalog."
            )
        }
        let result: ProbeCatalogGetResult = try await bridgeClient.request(
            method: "probe.catalog.get",
            params: ProbeCatalogGetParameters(modelId: modelId, modelVersion: modelVersion)
        )
        try ProbePlanningValidator.validateCatalogGet(
            result,
            modelId: modelId,
            modelVersion: modelVersion
        )
        if let plan {
            try ProbePlanningValidator.validateCatalogModel(result.model, matches: plan)
        }
        return result.model
    }

    private func synchronizeProbePlanning(
        using bridgeClient: BridgeClient,
        project: ProjectBridgeState
    ) async throws {
        let catalogResult: ProbeCatalogListResult = try await bridgeClient.request(
            method: "probe.catalog.list",
            params: ProbeCatalogListParameters()
        )
        try ProbePlanningValidator.validateCatalogList(catalogResult)
        probeCatalog = catalogResult.models

        let list: ProbePlanListResult = try await bridgeClient.request(
            method: "probe.plan.list",
            params: ProbePlanListParameters(projectId: project.projectId)
        )
        try ProbePlanningValidator.validatePlanList(
            list,
            projectId: project.projectId,
            projectRevision: project.revision
        )
        guard project.probePlanCount == nil || project.probePlanCount == list.planCount,
              project.probeRegionAnalysisCount == nil
                || project.probeRegionAnalysisCount
                    == list.plans.count(where: \.regionAnalysisAvailable)
        else {
            throw ProbePlanningOperationFailure.stateCountMismatch
        }
        probePlans = list.plans
        let chosenId = selectedProbePlanId.flatMap { selected in
            list.plans.first(where: { $0.planId == selected })?.planId
        } ?? list.plans.first?.planId
        guard let chosenId else {
            selectedProbePlanId = nil
            selectedProbePlan = nil
            selectedProbeRegionAnalysis = nil
            clearMajorVesselAnalysis()
            let requestedModel = ProbePlanningContract.preferredCatalogModel(
                in: catalogResult.models,
                preservingIdentity: selectedProbeModel?.id
            )
            if let requestedModel {
                selectedProbeModel = try await fetchProbeCatalogModel(
                    using: bridgeClient,
                    modelId: requestedModel.modelId,
                    modelVersion: requestedModel.modelVersion
                )
            } else {
                selectedProbeModel = nil
            }
            return
        }
        let detail: ProbePlanGetResult = try await bridgeClient.request(
            method: "probe.plan.get",
            params: ProbePlanGetParameters(projectId: project.projectId, planId: chosenId)
        )
        try ProbePlanningValidator.validatePlanGet(
            detail,
            projectId: project.projectId,
            projectRevision: project.revision,
            planId: chosenId
        )
        if probeCatalog.contains(where: {
            $0.modelId == detail.plan.modelId
                && $0.modelVersion == detail.plan.modelVersion
        }) {
            selectedProbeModel = try await fetchProbeCatalogModel(
                using: bridgeClient,
                modelId: detail.plan.modelId,
                modelVersion: detail.plan.modelVersion,
                matching: detail.plan
            )
        } else {
            // Opening an archived project may display its persisted exact plan,
            // but archived hardware never enters the supported catalog picker.
            selectedProbeModel = nil
        }
        selectedProbePlanId = chosenId
        selectedProbePlan = detail.plan
        selectedProbeRegionAnalysis = detail.plan.hasCurrentPlanningGeometry
            ? detail.regionAnalysis : nil
        selectedProbeVesselAnalysis = detail.plan.hasCurrentPlanningGeometry
            ? detail.majorVesselAnalysis : nil
        reconcileSelectedMajorVesselConflict()
        majorVesselAnalysisError = nil
    }

    private func clearProbePlanning() {
        probeCatalog = []
        selectedProbeModel = nil
        probePlans = []
        selectedProbePlanId = nil
        selectedProbePlan = nil
        selectedProbeRegionAnalysis = nil
        probeOperationInProgress = false
        probeOperationError = nil
        clearMajorVesselAnalysis()
    }

    private func clearMajorVesselAnalysis() {
        selectedProbeVesselAnalysis = nil
        selectedMajorVesselConflict = nil
        majorVesselAnalysisInProgress = false
        majorVesselAnalysisError = nil
        majorVesselNavigationInProgress = false
        majorVesselNavigationError = nil
    }

    private func reconcileSelectedMajorVesselConflict() {
        guard let selectedMajorVesselConflict,
              let analysis = selectedProbeVesselAnalysis?.analysis,
              analysis.conflicts.contains(selectedMajorVesselConflict)
        else {
            self.selectedMajorVesselConflict = nil
            majorVesselNavigationError = nil
            return
        }
    }

    private func loadSubjectPreviewIfAvailable(
        using bridgeClient: BridgeClient,
        state: PlannerBridgeState
    ) async {
        guard let image = state.subjectVessels.primaryImage else {
            subjectPreviewPNG = nil
            return
        }
        if image.imageId == importedVessel?.imageId, subjectPreviewPNG != nil {
            return
        }
        do {
            let preview: VascularPreviewResult = try await bridgeClient.request(
                method: "vascular.preview",
                params: VascularPreviewParameters(imageId: image.imageId)
            )
            guard
                preview.imageId == image.imageId,
                preview.originalWidthPixels == image.widthPixels,
                preview.originalHeightPixels == image.heightPixels
            else {
                throw VesselImportFailure.previewMismatch
            }
            subjectPreviewPNG = try verifiedPNG(
                base64: preview.pngBase64,
                mimeType: preview.mimeType
            )
        } catch {
            subjectPreviewPNG = nil
            vesselImportError = "Saved subject preview unavailable: \(error.localizedDescription)"
        }
    }

    private func connect() async {
        guard let launchConfiguration else {
            connection = .notConfigured
            backendState = nil
            return
        }
        connection = .connecting
        let client = BridgeClient(
            transport: SubprocessNDJSONTransport(
                configuration: launchConfiguration,
                timeout: BridgeTimeoutPolicy.longRunningOperationSeconds
            )
        )
        bridgeClient = client
        do {
            let hello: HelloResult = try await client.request(
                method: "hello",
                params: HelloParameters()
            )
            guard hello.protocolVersion == BridgeProtocolVersion.current else {
                connection = .incompatible(
                    "protocol \(hello.protocolVersion); requires \(BridgeProtocolVersion.current)"
                )
                await client.close()
                bridgeClient = nil
                return
            }
            guard hello.capabilities.animalOnly else {
                connection = .incompatible("service did not assert animal-only operation")
                await client.close()
                bridgeClient = nil
                return
            }
            guard hello.capabilities.atlas25Micrometre, hello.capabilities.atlasSlicePng else {
                connection = .incompatible("service lacks the reviewed 25 µm slice capability")
                await client.close()
                bridgeClient = nil
                return
            }
            helloResult = hello
            connection = .ready(service: hello.service, version: hello.applicationVersion)
            await openAtlasAndLoadSlice(allowDownload: false)
        } catch {
            connection = .failed(error.localizedDescription)
            backendState = nil
            await client.close()
            bridgeClient = nil
        }
    }

    private func openAtlasAndLoadSlice(allowDownload: Bool) async {
        guard let bridgeClient, connection.isReady else { return }
        atlasLoadPhase = .opening
        atlasRegionHierarchy = nil
        atlasRegionHierarchyError = nil
        do {
            let opened: AtlasOpenResult = try await bridgeClient.request(
                method: "atlas.open",
                params: AtlasOpenParameters(allowDownload: allowDownload)
            )
            try validate(atlas: opened.atlas)
            atlasProvenance = opened.atlas
            try await loadCompleteAtlasRegionHierarchy(
                using: bridgeClient,
                atlas: opened.atlas
            )
            await refreshState()
            guard connection.isReady else {
                throw StateValidationFailure.animalOnlyContractMissing
            }
            atlasLoadPhase = .ready
            await loadMajorVesselGeometry()
            await loadDorsalSurface()
        } catch let error as BridgeClientError {
            if case let .remote(remote) = error, remote.code == "ATLAS_NOT_CACHED" {
                atlasLoadPhase = .needsDownload
                dorsalLoadPhase = .unavailable("The reviewed atlas is not cached")
                atlasRegionHierarchy = nil
                atlasRegionHierarchyError = nil
                await refreshState()
                return
            }
            atlasRegionHierarchy = nil
            atlasRegionHierarchyError = error.localizedDescription
            atlasLoadPhase = .failed(error.localizedDescription)
            dorsalLoadPhase = .unavailable("Atlas validation did not complete")
        } catch {
            atlasRegionHierarchy = nil
            atlasRegionHierarchyError = error.localizedDescription
            atlasLoadPhase = .failed(error.localizedDescription)
            dorsalLoadPhase = .unavailable("Atlas validation did not complete")
        }
    }

    private func loadCompleteAtlasRegionHierarchy(
        using bridgeClient: BridgeClient,
        atlas: AtlasProvenance
    ) async throws {
        guard helloResult?.capabilities.atlasRegionRecords == true else {
            throw AtlasSceneContractError.invalid(
                "The connected service does not expose the complete Allen ontology."
            )
        }

        var accumulator = AtlasRegionPageAccumulator()
        while true {
            try Task.checkCancellation()
            let page: AtlasRegionsResult = try await bridgeClient.request(
                method: "atlas.regions",
                params: try AtlasRegionsParameters(offset: accumulator.nextOffset)
            )
            try validateAtlasRegionIdentity(page.atlas, against: atlas)
            try accumulator.append(page)
            if !page.hasMore { break }
        }
        atlasRegionHierarchy = try accumulator.finish()
        atlasRegionHierarchyError = nil
    }

    private func validateAtlasRegionIdentity(
        _ identity: ViewerAtlasIdentity,
        against atlas: AtlasProvenance
    ) throws {
        guard identity.identifier == atlas.identifier,
              identity.version == atlas.version,
              identity.metadataSha256 == atlas.metadataSha256,
              [
                  identity.resolutionMicrometres.apMicrometres,
                  identity.resolutionMicrometres.dvMicrometres,
                  identity.resolutionMicrometres.mlMicrometres,
              ] == atlas.resolutionMicrometres,
              [
                  identity.shapeVoxels.apVoxels,
                  identity.shapeVoxels.dvVoxels,
                  identity.shapeVoxels.mlVoxels,
              ] == atlas.shapeVoxels,
              identity.orientation == atlas.orientation,
              identity.frameworkName == atlas.frameworkName,
              identity.sourceAnnotation == atlas.sourceAnnotation,
              identity.citation == atlas.citation,
              identity.brainGlobeAtlasApiVersion == atlas.brainGlobeAtlasApiVersion
        else {
            throw AtlasSceneContractError.invalid(
                "Atlas ontology pages do not match the opened reviewed atlas."
            )
        }
    }

    private func validate(state: PlannerBridgeState) throws {
        guard state.protocolVersion == BridgeProtocolVersion.current else {
            throw StateValidationFailure.protocolMismatch(state.protocolVersion)
        }
        if !AnimalOnlyContract.isValid(animalOnly: state.animalOnly, warning: state.warning) {
            throw StateValidationFailure.animalOnlyContractMissing
        }
        try ReferenceDensityValidator.validateBridgeState(state.populationDensity)
    }

    private func synchronizePopulationDensity(
        using bridgeClient: BridgeClient,
        state: PlannerBridgeState
    ) async {
        populationDensityVisible = state.populationDensity.visible
        guard state.populationDensity.visible else {
            populationDensityPNG = nil
            populationDensityOverlay = nil
            return
        }
        guard
            let dorsalSurface,
            let atlasProvenance
        else {
            populationDensityPNG = nil
            populationDensityOverlay = nil
            return
        }
        do {
            let overlay: ReferenceDensityOverlayResult = try await bridgeClient.request(
                method: "vascular.reference.overlay",
                params: ReferenceDensityOverlayParameters()
            )
            let png = try ReferenceDensityValidator.verifiedOverlayPNG(
                overlay,
                dorsal: dorsalSurface,
                atlas: atlasProvenance,
                display: state.populationDensity
            )
            populationDensityOverlay = overlay
            populationDensityPNG = png
        } catch {
            populationDensityOverlay = nil
            populationDensityPNG = nil
            populationDensityError = error.localizedDescription
        }
    }

    private func loadRegisteredOverlayIfAvailable(
        using bridgeClient: BridgeClient,
        state: PlannerBridgeState
    ) async {
        guard
            let image = state.subjectVessels.primaryImage,
            image.registered,
            image.lateralityConfirmed,
            image.visible
        else {
            subjectOverlayPNG = nil
            return
        }
        do {
            let overlay: VascularOverlayResult = try await bridgeClient.request(
                method: "vascular.overlay",
                params: VascularOverlayParameters(imageId: image.imageId)
            )
            guard
                overlay.subjectSpecific,
                overlay.lateralityConfirmed,
                overlay.imageId == image.imageId,
                overlay.rowAxis == "AP",
                overlay.columnAxis == "ML"
            else {
                throw VesselImportFailure.previewMismatch
            }
            subjectOverlayPNG = try verifiedPNG(
                base64: overlay.pngBase64,
                mimeType: overlay.mimeType
            )
        } catch {
            subjectOverlayPNG = nil
            vesselImportError = "Registered overlay unavailable: \(error.localizedDescription)"
        }
    }

    private func validate(atlas: AtlasProvenance) throws {
        guard
            atlas.identifier == SafetyPolicy.supportedAtlasIdentifier,
            atlas.version == SafetyPolicy.supportedAtlasVersion,
            atlas.resolutionMicrometres == [25, 25, 25],
            atlas.shapeVoxels.count == 3,
            atlas.shapeVoxels.allSatisfy({ $0 > 0 }),
            !atlas.metadataSha256.isEmpty
        else {
            throw StateValidationFailure.unsupportedAtlas
        }
    }

    private func clearPopulationDensity(clearPreparation: Bool) {
        populationDensityVisible = false
        populationDensityPNG = nil
        populationDensityOverlay = nil
        populationDensityError = nil
        if clearPreparation {
            populationDensityPreparation = nil
        }
    }

    /// Population-density and subject-registration state remains readable for
    /// package compatibility, but its methods are not registered and it must
    /// never inflate the primary surgical-planning connect/refresh/Dorsal path.
    private func clearArchivedDisplayState() {
        clearPopulationDensity(clearPreparation: true)
        importedVessel = nil
        subjectPreviewPNG = nil
        subjectOverlayPNG = nil
        registrationResult = nil
    }

    private func verifiedPNG(base64: String, mimeType: String) throws -> Data {
        guard mimeType == "image/png", let data = Data(base64Encoded: base64) else {
            throw StateValidationFailure.invalidPNG
        }
        let signature = Data([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        guard data.starts(with: signature) else {
            throw StateValidationFailure.invalidPNG
        }
        return data
    }

    private func canonicalPath(_ path: String) -> String {
        URL(fileURLWithPath: path)
            .resolvingSymlinksInPath()
            .standardizedFileURL
            .path
    }
}

private enum VesselImportFailure: LocalizedError {
    case backendNotReady
    case emptyFile
    case notSubjectSpecific
    case provenanceMismatch
    case previewMismatch

    var errorDescription: String? {
        switch self {
        case .backendNotReady:
            "Open the verified atlas and animal-only project before importing a subject image."
        case .emptyFile:
            "The selected image file is empty."
        case .notSubjectSpecific:
            "The backend did not identify the imported image as subject-specific."
        case .provenanceMismatch:
            "The backend image checksum or byte size does not match the selected file."
        case .previewMismatch:
            "The backend preview dimensions do not match the verified imported image."
        }
    }
}

private enum StateValidationFailure: LocalizedError {
    case protocolMismatch(Int)
    case animalOnlyContractMissing
    case unsupportedAtlas
    case invalidPNG

    var errorDescription: String? {
        switch self {
        case let .protocolMismatch(version):
            "State uses bridge protocol \(version); expected \(BridgeProtocolVersion.current)."
        case .animalOnlyContractMissing:
            "The backend did not preserve the required animal-only safety contract."
        case .unsupportedAtlas:
            "The backend atlas provenance does not match allen_mouse_25um v1.2 at 25 µm."
        case .invalidPNG:
            "The backend returned an invalid PNG payload."
        }
    }
}

private enum RegistrationFailure: LocalizedError {
    case invalidResult

    var errorDescription: String? {
        "The backend registration result failed residual or laterality validation."
    }
}

private enum ProjectOperationFailure: LocalizedError {
    case pathMismatch

    var errorDescription: String? {
        "The backend project path did not match the selected package path."
    }
}

private enum PopulationDensityOperationFailure: LocalizedError {
    case preparationNotPublishedToState
    case displayMutationNotPublished

    var errorDescription: String? {
        switch self {
        case .preparationNotPublishedToState:
            "The backend prepared the reference but did not publish it as available; display remains disabled."
        case .displayMutationNotPublished:
            "The backend did not publish the persisted population-density display change."
        }
    }
}

private enum ImplantOperationFailure: LocalizedError {
    case mutationNotPublished

    var errorDescription: String? {
        switch self {
        case .mutationNotPublished:
            "The backend did not publish the persisted implant-site change."
        }
    }
}

private enum ProbePlanningOperationFailure: LocalizedError {
    case mutationNotPublished
    case stateCountMismatch
    case generatedExportBecameStale
    case exportConfirmationNotPublished

    var errorDescription: String? {
        switch self {
        case .mutationNotPublished:
            "The backend did not publish the persisted probe-plan change."
        case .stateCountMismatch:
            "Probe-plan or region-analysis counts do not match project state."
        case .generatedExportBecameStale:
            "The generated region export no longer matches the current probe plan and analysis."
        case .exportConfirmationNotPublished:
            "The file was saved, but the backend did not publish its export audit record."
        }
    }
}
