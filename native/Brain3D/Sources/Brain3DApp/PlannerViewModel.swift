import Brain3DCore
import Brain3DScene
import CryptoKit
import Foundation
import SwiftUI

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

struct VerifiedAtlasSliceFrame: Equatable {
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

private enum ViewerMutation: Sendable {
    case slice(orientation: AtlasSliceOrientation, index: Int)
    case regionPick(
        orientation: AtlasSliceOrientation,
        index: Int,
        column: Int,
        row: Int
    )
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
    @Published private(set) var threeDimensionalPickInProgress = false
    @Published private(set) var threeDimensionalPickError: String?
    @Published private(set) var majorVesselGeometry: MajorVesselGeometryResult?
    @Published private(set) var majorVesselDorsalProjection: MajorVesselSliceOverlay?
    @Published private(set) var majorVesselLoadInProgress = false
    @Published private(set) var majorVesselLoadError: String?
    @Published private(set) var selectedProbeVesselAnalysis: MajorVesselAnalysisResult?
    @Published private(set) var majorVesselAnalysisInProgress = false
    @Published private(set) var majorVesselAnalysisError: String?
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
    private var cachedRootMesh: AtlasMeshResult?
    private var majorVesselSliceOverlayCache: [String: MajorVesselSliceOverlay] = [:]

    init(launchConfiguration: BridgeLaunchConfiguration?) {
        self.launchConfiguration = launchConfiguration
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
            let suffix = hasUnsavedChanges ? "unsaved changes" : "saved"
            return "\(project.title) — acknowledged animal-only · \(suffix)"
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
        connection.isReady
            && backendState?.project != nil
            && activeCalibration?.permitsPlanning == true
            && helloResult?.capabilities.probeCatalog == true
            && helloResult?.capabilities.calibratedProbePlanning == true
            && helloResult?.capabilities.exactProbeRegionTraversal == true
            && !projectOperationInProgress
            && !calibrationOperationInProgress
            && !probeOperationInProgress
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
            selectedProbePlan?.inputSha256 ?? "no-probe",
            majorVesselGeometry?.provenance.derivedAssetSha256 ?? "no-vessels",
        ].joined(separator: ":")
    }

    var majorVesselStatus: String {
        if majorVesselLoadInProgress { return "Loading reference major vessels…" }
        if let geometry = majorVesselGeometry {
            return "P60 reference · \(geometry.segmentCount.formatted()) segments · diameter ≥30 µm"
        }
        if let majorVesselLoadError { return "Unavailable · \(majorVesselLoadError)" }
        return "Reference major vessels not loaded"
    }

    var majorVesselDisclosure: String {
        guard let geometry = majorVesselGeometry else {
            return "Single-specimen reference; no geometry is being displayed."
        }
        let source = geometry.provenance
        let coverage = source.pialVesselsExcluded
            ? "Single cleared \(source.specimenId) reference; not subject-specific; pial and choroidal vessels are excluded."
            : "Single cleared \(source.specimenId) reference; not subject-specific."
        guard !source.uncertaintyBoundsReviewed else { return coverage }
        return coverage
            + " Registration and tissue-distortion uncertainty bounds are not published; "
            + "absence of conflict cannot be classified."
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
        majorVesselGeometry = nil
        majorVesselDorsalProjection = nil
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
        acknowledgement: AnimalOnlyAcknowledgementState
    ) async -> Bool {
        projectOperationError = nil
        guard let bridgeClient, canCreateNewAnimalProject else {
            projectOperationError =
                "Open the verified 25 µm atlas before creating an animal plan."
            return false
        }
        guard let parameters = ProjectNewParameters(
            acknowledgement: acknowledgement,
            title: "Untitled animal surgery plan"
        ) else {
            projectOperationError =
                "Explicitly acknowledge animal-only, non-human, non-clinical use first."
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
            if !state.populationDensity.available {
                clearPopulationDensity(clearPreparation: true)
            } else {
                await synchronizePopulationDensity(using: bridgeClient, state: state)
            }
            await loadSubjectPreviewIfAvailable(using: bridgeClient, state: state)
            await loadRegisteredOverlayIfAvailable(using: bridgeClient, state: state)
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
            clearPopulationDensity(clearPreparation: true)
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
        guard let bridgeClient, canStoreImplantTarget else {
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
            let result: ImplantMutationResult = try await bridgeClient.request(
                method: "implant.add",
                params: ImplantAddParameters(
                    label: normalizedLabel,
                    apMillimetres: coordinates.apMillimetres,
                    mlMillimetres: coordinates.mlMillimetres,
                    dvMillimetres: coordinates.dvMillimetres
                )
            )
            try ImplantTargetValidator.validateMutation(result, expectedStatus: "added")
            await refreshState()
            guard implantTargets.contains(where: { $0.targetId == result.target.targetId }) else {
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
        guard let bridgeClient, canStoreImplantTarget else {
            implantOperationError = "Open an animal plan before removing an implant site."
            return false
        }

        implantOperationInProgress = true
        defer { implantOperationInProgress = false }
        do {
            let result: ImplantMutationResult = try await bridgeClient.request(
                method: "implant.remove",
                params: ImplantRemoveParameters(targetId: targetId)
            )
            try ImplantTargetValidator.validateMutation(result, expectedStatus: "removed")
            guard result.target.targetId == targetId else {
                throw ImplantOperationFailure.removedTargetMismatch
            }
            await refreshState()
            guard !implantTargets.contains(where: { $0.targetId == targetId }) else {
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
            return true
        } catch {
            targetProjections[targetId] = nil
            calibrationOperationError = error.localizedDescription
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
            let catalogModel = try await fetchProbeCatalogModel(
                using: bridgeClient,
                modelId: result.plan.modelId,
                modelVersion: result.plan.modelVersion,
                matching: result.plan
            )
            selectedProbeModel = catalogModel
            selectedProbePlanId = planId
            selectedProbePlan = result.plan
            selectedProbeRegionAnalysis = result.plan.hasCurrentPlanningGeometry
                ? result.regionAnalysis : nil
            selectedProbeVesselAnalysis = result.plan.hasCurrentPlanningGeometry
                ? result.majorVesselAnalysis : nil
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
                azimuthDegrees: numbers.azimuth,
                elevationDegrees: numbers.elevation,
                insertionDepthMicrometres: numbers.depth,
                axialRotationDegrees: numbers.rotation,
                customGeometryAcknowledged: customGeometryAcknowledged
            )
            try ProbePlanningValidator.validateCreate(request)
            let result: ProbePlanMutationResult = try await bridgeClient.request(
                method: "probe.plan.create",
                params: request
            )
            try ProbePlanningValidator.validateMutation(
                result,
                projectId: project.projectId,
                expectedStatus: "created",
                expectedRevision: project.revision + 1
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
                azimuthDegrees: numbers.azimuth,
                elevationDegrees: numbers.elevation,
                insertionDepthMicrometres: numbers.depth,
                axialRotationDegrees: numbers.rotation,
                customGeometryAcknowledged: customGeometryAcknowledged
            )
            try ProbePlanningValidator.validateUpdate(request)
            let result: ProbePlanMutationResult = try await bridgeClient.request(
                method: "probe.plan.update",
                params: request
            )
            try ProbePlanningValidator.validateMutation(
                result,
                projectId: project.projectId,
                expectedStatus: "updated",
                expectedRevision: project.revision + 1
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
            majorVesselAnalysisError = error.localizedDescription
            return false
        }
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
            let result: ProbeRegionExportResult = try await bridgeClient.request(
                method: "probe.region.export",
                params: ProbeRegionExportParameters(
                    projectId: project.projectId,
                    planId: plan.planId,
                    expectedPlanInputSha256: plan.inputSha256,
                    format: format
                )
            )
            try ProbePlanningValidator.validateExport(
                result,
                projectId: project.projectId,
                plan: plan,
                analysis: analysis,
                format: format,
                projectRevision: project.revision
            )
            return result
        } catch {
            probeOperationError = error.localizedDescription
            return nil
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
        ].joined(separator: ":")
        if let cached = majorVesselSliceOverlayCache[key] { return cached }
        let overlay = MajorVesselSliceOverlayGeometry.make(
            geometry: geometry,
            orientation: orientation,
            sliceIndex: frame.index
        )
        if majorVesselSliceOverlayCache.count >= 24,
           let oldestKey = majorVesselSliceOverlayCache.keys.first
        {
            majorVesselSliceOverlayCache[oldestKey] = nil
        }
        majorVesselSliceOverlayCache[key] = overlay
        return overlay
    }

    var majorVesselDorsalOverlay: MajorVesselSliceOverlay? {
        majorVesselDorsalProjection
    }

    func prepareThreeDimensionalScene() async {
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
            threeDimensionalPhase = .unavailable(
                "Create or open an animal plan with a verified renderer anchor"
            )
            return
        }
        guard helloResult?.capabilities.atlasMeshDescriptor == true,
              helloResult?.capabilities.atlasAnnotationRayPick == true
        else {
            threeDimensionalSnapshot = nil
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
            let snapshot = try AnimalSceneSnapshot(
                projectId: project.projectId,
                projectRevision: project.revision,
                rendererAnchor: rendererAnchor,
                meshResult: meshResult,
                selectedProbePlan: selectedProbePlan.flatMap {
                    $0.hasCurrentPlanningGeometry ? $0 : nil
                },
                majorVessels: majorVesselGeometry
            )
            cachedRootMesh = meshResult
            threeDimensionalSnapshot = snapshot
            threeDimensionalPhase = .loadingGeometry
        } catch is CancellationError {
            return
        } catch {
            guard generation == threeDimensionalGeneration else { return }
            threeDimensionalSnapshot = nil
            threeDimensionalPhase = .failed(error.localizedDescription)
        }
    }

    func updateThreeDimensionalRenderPhase(_ phase: AnimalScenePhase) {
        guard threeDimensionalSnapshot != nil else { return }
        switch phase {
        case .idle, .loading:
            threeDimensionalPhase = .loadingGeometry
        case .ready:
            threeDimensionalPhase = .ready
        case let .failed(message):
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
            } catch is CancellationError {
                return
            } catch {
                guard generation == self.threeDimensionalPickGeneration else { return }
                self.threeDimensionalRegionHit = nil
                self.threeDimensionalPickError = error.localizedDescription
            }
        }
    }

    func clearThreeDimensionalRegionSelection() {
        threeDimensionalPickGeneration += 1
        threeDimensionalPickWorker?.cancel()
        threeDimensionalPickWorker = nil
        threeDimensionalPickInProgress = false
        threeDimensionalPickError = nil
        threeDimensionalRegionHit = nil
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
        azimuthText: String,
        elevationText: String,
        insertionDepthText: String,
        axialRotationText: String
    ) throws -> (azimuth: Double, elevation: Double, depth: Double, rotation: Double) {
        (
            try CalibrationNumberInput.parse(azimuthText, field: "Azimuth"),
            try CalibrationNumberInput.parse(elevationText, field: "Elevation"),
            try CalibrationNumberInput.parse(insertionDepthText, field: "Insertion depth"),
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

    func requestedViewerIndex(for orientation: AtlasSliceOrientation) -> Int? {
        if let pendingViewerSlice, pendingViewerSlice.orientation == orientation {
            return pendingViewerSlice.index
        }
        return viewerFrame(for: orientation)?.index ?? viewerMetadata(for: orientation)?.index
    }

    func requestViewerSlice(_ orientation: AtlasSliceOrientation, index: Int) {
        guard let frame = viewerFrame(for: orientation) else { return }
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
        guard
            let frame = viewerFrame(for: orientation),
            column >= 0, column < frame.width,
            row >= 0, row < frame.height
        else { return }
        pendingViewerSlice = nil
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
                    authoritativeViewerSnapshot = result.snapshot
                    hasUnsavedChanges = true
                    let frame = try verifiedFrame(
                        from: result.renderedSlice,
                        expected: sliceMetadata(orientation, in: result.snapshot),
                        snapshot: result.snapshot
                    )
                    guard generation == viewerGeneration else { continue }
                    viewerSnapshot = result.snapshot
                    triPlanarFrames[orientation] = frame
                    viewerRegionSelection = nil
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
                    authoritativeViewerSnapshot = result.snapshot
                    hasUnsavedChanges = true
                    guard generation == viewerGeneration else { continue }
                    viewerSnapshot = result.snapshot
                    viewerRegionSelection = result.snapshot.selection
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
        let shouldReloadPopulationDensity = backendState?.populationDensity.visible == true
        if shouldReloadPopulationDensity {
            populationDensityPNG = nil
            populationDensityOverlay = nil
        }
        guard let bridgeClient, atlasProvenance != nil else {
            populationDensityPNG = nil
            populationDensityOverlay = nil
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
            if shouldReloadPopulationDensity, let state = backendState {
                await synchronizePopulationDensity(using: bridgeClient, state: state)
            }
        } catch {
            dorsalSurface = nil
            dorsalSurfacePNG = nil
            populationDensityPNG = nil
            populationDensityOverlay = nil
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
            majorVesselSliceOverlayCache = [:]
            majorVesselLoadError = "The connected service does not expose the pinned vessel graph."
            return
        }
        if let geometry = majorVesselGeometry,
           geometry.atlas.metadataSha256 == atlasProvenance.metadataSha256
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
            majorVesselGeometry = geometry
            majorVesselDorsalProjection = MajorVesselSliceOverlayGeometry.makeDorsalProjection(
                geometry: geometry
            )
            majorVesselSliceOverlayCache = [:]
        } catch {
            majorVesselGeometry = nil
            majorVesselDorsalProjection = nil
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
            return subjectOverlayPNG != nil
        } catch {
            subjectOverlayPNG = nil
            registrationError = error.localizedDescription
            return false
        }
    }

    func saveProject(to url: URL) async -> Bool {
        projectOperationError = nil
        guard let bridgeClient, canSaveProject else {
            projectOperationError = "There is no connected project to save."
            return false
        }
        projectOperationInProgress = true
        defer { projectOperationInProgress = false }
        do {
            let result: ProjectSaveResult = try await bridgeClient.request(
                method: "project.save",
                params: ProjectSaveParameters(path: url.path)
            )
            await refreshState()
            guard
                result.status == "saved",
                canonicalPath(result.path) == canonicalPath(url.path)
            else {
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
        selectedProbeModel = try await fetchProbeCatalogModel(
            using: bridgeClient,
            modelId: detail.plan.modelId,
            modelVersion: detail.plan.modelVersion,
            matching: detail.plan
        )
        selectedProbePlanId = chosenId
        selectedProbePlan = detail.plan
        selectedProbeRegionAnalysis = detail.plan.hasCurrentPlanningGeometry
            ? detail.regionAnalysis : nil
        selectedProbeVesselAnalysis = detail.plan.hasCurrentPlanningGeometry
            ? detail.majorVesselAnalysis : nil
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
        majorVesselAnalysisInProgress = false
        majorVesselAnalysisError = nil
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
        do {
            let opened: AtlasOpenResult = try await bridgeClient.request(
                method: "atlas.open",
                params: AtlasOpenParameters(allowDownload: allowDownload)
            )
            try validate(atlas: opened.atlas)
            atlasProvenance = opened.atlas
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
                await refreshState()
                return
            }
            atlasLoadPhase = .failed(error.localizedDescription)
            dorsalLoadPhase = .unavailable("Atlas validation did not complete")
        } catch {
            atlasLoadPhase = .failed(error.localizedDescription)
            dorsalLoadPhase = .unavailable("Atlas validation did not complete")
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
    case removedTargetMismatch

    var errorDescription: String? {
        switch self {
        case .mutationNotPublished:
            "The backend did not publish the persisted implant-site change."
        case .removedTargetMismatch:
            "The backend removed a different implant site than requested."
        }
    }
}

private enum ProbePlanningOperationFailure: LocalizedError {
    case mutationNotPublished
    case stateCountMismatch

    var errorDescription: String? {
        switch self {
        case .mutationNotPublished:
            "The backend did not publish the persisted probe-plan change."
        case .stateCountMismatch:
            "Probe-plan or region-analysis counts do not match project state."
        }
    }
}
