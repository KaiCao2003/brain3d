import Brain3DCore
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
    @Published private(set) var viewerPhase: ViewerLoadPhase = .unavailable(
        "Create or open an animal plan to browse atlas slices"
    )
    @Published private(set) var viewerSnapshot: ViewerCanonicalSnapshot?
    @Published private(set) var triPlanarFrames = TriPlanarFrameSet()
    @Published private(set) var pendingViewerSlice: PendingViewerSlice?
    @Published private(set) var viewerRegionSelection: Brain3DCore.ViewerRegionSelection?
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

    private let launchConfiguration: BridgeLaunchConfiguration?
    private var bridgeClient: BridgeClient?
    private var helloResult: HelloResult?
    private var hasAttemptedConnection = false
    private var authoritativeViewerSnapshot: ViewerCanonicalSnapshot?
    private var pendingViewerMutation: ViewerMutation?
    private var viewerMutationWorker: Task<Void, Never>?
    private var viewerGeneration = 0

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
            let state: PlannerBridgeState = try await bridgeClient.request(
                method: "state.get",
                params: StateParameters()
            )
            try validate(state: state)
            if state.project != nil {
                let listed: ImplantListResult = try await bridgeClient.request(
                    method: "implant.list",
                    params: ImplantListParameters()
                )
                try ImplantTargetValidator.validateList(listed)
                implantTargets = listed.targets
            } else {
                implantTargets = []
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
            return true
        } catch {
            implantOperationError = error.localizedDescription
            return false
        }
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
