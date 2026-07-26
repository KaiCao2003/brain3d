import AppKit
import Brain3DCore
import Metal
import QuartzCore
@preconcurrency import SceneKit
import simd

public enum AnimalScenePhase: Equatable, Sendable {
    case idle
    case loading
    case ready
    case failed(String)
}

final class AtlasInteractiveSCNView: SCNView {
    var onSceneClick: ((CGPoint) -> Void)?

    private var clickClassifier = SceneClickClassifier()

    override var acceptsFirstResponder: Bool { true }

    override func mouseDown(with event: NSEvent) {
        clickClassifier.begin(at: convert(event.locationInWindow, from: nil))
        super.mouseDown(with: event)
    }

    override func mouseDragged(with event: NSEvent) {
        clickClassifier.update(to: convert(event.locationInWindow, from: nil))
        super.mouseDragged(with: event)
    }

    override func mouseUp(with event: NSEvent) {
        let end = convert(event.locationInWindow, from: nil)
        let isClick = clickClassifier.end(at: end)
        super.mouseUp(with: event)
        guard event.clickCount == 1, isClick else { return }
        onSceneClick?(end)
    }
}

@MainActor
final class AnimalSceneController {
    typealias MajorVesselMeshBuilder =
        @Sendable (
            _ pointsASRMicrometres: [SIMD3<Float>],
            _ radiiMicrometres: [Float],
            _ runOffsets: [Int],
            _ minimumVisibleDiameterMicrometres: Double
        ) async throws -> MajorVesselTubeMeshData

    private let view: AtlasInteractiveSCNView
    private let loader: AtlasMeshLoader
    private let majorVesselMeshBuilder: MajorVesselMeshBuilder
    private let scene = SCNScene()
    private let brainLayer = SCNNode()
    private let highlightedRegionLayer = SCNNode()
    private let probeLayer = SCNNode()
    private let implantSiteLayer = SCNNode()
    private let majorVesselLayerSwap = MajorVesselLayerSwap()
    private let selectedVesselConflictLayer = SCNNode()
    private let cameraNode = SCNNode()
    private var currentMeshSHA256: String?
    private var currentProbePlanId: String?
    private var currentHighlightedRegionIdentity: String?
    private var currentSnapshotIdentity: String?
    private var currentTransform: AtlasSceneTransform?
    private var loadGeneration = 0
    private var reduceMotion = false
    private var homeCameraTransform = matrix_identity_float4x4
    private var homeCameraTarget = SIMD3<Float>.zero

    var onRayPick: ((AtlasRayPoint, AtlasRayPoint) -> Void)?
    var onBlankSelection: (() -> Void)?
    var cameraInertiaEnabled: Bool { view.defaultCameraController.inertiaEnabled }
    private var majorVesselLayer: SCNNode { majorVesselLayerSwap.layer }

    init(
        view: AtlasInteractiveSCNView,
        loader: AtlasMeshLoader = AtlasMeshLoader(),
        majorVesselMeshBuilder: @escaping MajorVesselMeshBuilder = {
            points, radii, offsets, minimumDiameter in
            try await MajorVesselTubeMeshBuilder.buildAsync(
                pointsASRMicrometres: points,
                radiiMicrometres: radii,
                runOffsets: offsets,
                minimumVisibleDiameterMicrometres: minimumDiameter
            )
        }
    ) {
        self.view = view
        self.loader = loader
        self.majorVesselMeshBuilder = majorVesselMeshBuilder
        configureScene()
    }

    func apply(
        snapshot: AnimalSceneSnapshot,
        phaseChanged: @escaping (AnimalScenePhase) -> Void
    ) async {
        guard currentSnapshotIdentity != snapshot.identity else {
            requestDisplay()
            phaseChanged(.ready)
            return
        }
        loadGeneration += 1
        let generation = loadGeneration
        currentTransform = snapshot.transform

        do {
            phaseChanged(.loading)
            let meshChanged = currentMeshSHA256 != snapshot.meshResult.mesh.sha256
            if meshChanged {
                let loaded = try await loader.load(snapshot.meshResult.mesh)
                try Task.checkCancellation()
                guard generation == loadGeneration else { return }
                replaceBrain(with: loaded.makeRootNode(), snapshot: snapshot)
                currentMeshSHA256 = snapshot.meshResult.mesh.sha256
            } else {
                brainLayer.simdTransform = snapshot.transform.sourceToSceneMatrix
            }
            try await replaceHighlightedRegion(for: snapshot, generation: generation)
            try Task.checkCancellation()
            guard generation == loadGeneration else { return }
            try replaceProbe(for: snapshot)
            if meshChanged
                || (currentProbePlanId == nil && snapshot.selectedProbePlan != nil)
            {
                setCameraHome(for: snapshot)
            }
            try replaceImplantSite(for: snapshot)
            selectedVesselConflictLayer.childNodes.forEach { $0.removeFromParentNode() }
            try await replaceMajorVessels(for: snapshot, generation: generation)
            try Task.checkCancellation()
            guard generation == loadGeneration else { return }
            try replaceSelectedVesselConflict(for: snapshot)
            currentSnapshotIdentity = snapshot.identity
            currentProbePlanId = snapshot.selectedProbePlan?.planId
            requestDisplay()
            phaseChanged(.ready)
        } catch is CancellationError {
            return
        } catch {
            guard generation == loadGeneration else { return }
            requestDisplay()
            phaseChanged(.failed(error.localizedDescription))
        }
    }

    func setReduceMotion(_ enabled: Bool) {
        guard reduceMotion != enabled else { return }
        reduceMotion = enabled
        let cameraController = view.defaultCameraController
        cameraController.inertiaEnabled = !enabled
        if enabled { cameraController.stopInertia() }
    }

    func resetCamera() {
        view.defaultCameraController.stopInertia()
        view.defaultCameraController.target = SCNVector3(homeCameraTarget)
        SCNTransaction.begin()
        SCNTransaction.animationDuration = reduceMotion ? 0 : 0.24
        SCNTransaction.animationTimingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        cameraNode.simdTransform = homeCameraTransform
        SCNTransaction.commit()
        requestDisplay()
    }

    func offscreenSnapshot(size: CGSize) -> NSImage {
        // Scene mutations are transaction-backed even when no animation is
        // requested. Flush them before handing the shared scene to a fresh
        // offscreen renderer, otherwise a snapshot taken immediately after an
        // overlay change can intermittently capture the preceding frame.
        SCNTransaction.flush()
        let renderer = SCNRenderer(device: MTLCreateSystemDefaultDevice(), options: nil)
        renderer.scene = scene
        renderer.pointOfView = cameraNode
        _ = renderer.prepare(scene, shouldAbortBlock: nil)
        return renderer.snapshot(
            atTime: 0,
            with: size,
            antialiasingMode: .multisampling4X
        )
    }

    private func configureScene() {
        brainLayer.name = "allen-mouse-root-mesh"
        highlightedRegionLayer.name = "selected-allen-region-layer"
        probeLayer.name = "selected-probe-layer"
        implantSiteLayer.name = "displayed-implant-site-layer"
        majorVesselLayer.name = "reviewed-major-vessel-layer"
        selectedVesselConflictLayer.name = "selected-vessel-conflict-layer"
        brainLayer.categoryBitMask = SceneCategory.brain.rawValue
        highlightedRegionLayer.categoryBitMask = SceneCategory.highlightedRegion.rawValue
        probeLayer.categoryBitMask = SceneCategory.probe.rawValue
        implantSiteLayer.categoryBitMask = SceneCategory.implantSite.rawValue
        majorVesselLayer.categoryBitMask = SceneCategory.majorVessel.rawValue
        selectedVesselConflictLayer.categoryBitMask =
            SceneCategory.selectedVesselConflict.rawValue
        scene.rootNode.addChildNode(brainLayer)
        scene.rootNode.addChildNode(highlightedRegionLayer)
        scene.rootNode.addChildNode(probeLayer)
        scene.rootNode.addChildNode(implantSiteLayer)
        scene.rootNode.addChildNode(majorVesselLayer)
        scene.rootNode.addChildNode(selectedVesselConflictLayer)

        let camera = SCNCamera()
        camera.fieldOfView = 38
        camera.zNear = 0.01
        camera.zFar = 100
        // The atlas shell and reference-vessel overlay use calibrated constant
        // materials. HDR tone mapping made the translucent shell appear white
        // on some displays, obscuring the interior geometry it is meant to
        // contextualize.
        camera.wantsHDR = false
        cameraNode.name = "planning-camera"
        cameraNode.camera = camera
        scene.rootNode.addChildNode(cameraNode)

        let ambientNode = SCNNode()
        let ambient = SCNLight()
        ambient.type = .ambient
        ambient.intensity = 220
        ambient.color = NSColor(calibratedWhite: 0.94, alpha: 1)
        ambientNode.light = ambient
        scene.rootNode.addChildNode(ambientNode)

        let keyNode = SCNNode()
        let key = SCNLight()
        key.type = .directional
        key.intensity = 1_050
        key.color = NSColor(calibratedWhite: 1, alpha: 1)
        keyNode.light = key
        keyNode.eulerAngles = SCNVector3(-0.75, 0.55, 0.25)
        scene.rootNode.addChildNode(keyNode)

        let background = NSColor(
            srgbRed: 0.91,
            green: 0.935,
            blue: 0.96,
            alpha: 1
        )
        scene.background.contents = background
        view.scene = scene
        view.pointOfView = cameraNode
        view.backgroundColor = background
        view.antialiasingMode = .multisampling4X
        view.preferredFramesPerSecond = 60
        view.rendersContinuously = false
        view.allowsCameraControl = true
        view.defaultCameraController.interactionMode = .orbitTurntable
        view.defaultCameraController.worldUp = SCNVector3(0, 1, 0)
        view.defaultCameraController.target = SCNVector3Zero
        view.defaultCameraController.inertiaEnabled = true
        view.onSceneClick = { [weak self] point in
            self?.pick(at: point)
        }
    }

    private func replaceBrain(with importedRoot: SCNNode, snapshot: AnimalSceneSnapshot) {
        brainLayer.childNodes.forEach { $0.removeFromParentNode() }
        importedRoot.name = "verified-atlas-obj"
        applyBrainAppearance(to: importedRoot)
        brainLayer.addChildNode(importedRoot)
        brainLayer.simdTransform = snapshot.transform.sourceToSceneMatrix
    }

    private func applyBrainAppearance(to node: SCNNode) {
        node.categoryBitMask = SceneCategory.brain.rawValue
        if let geometry = node.geometry {
            let material = SCNMaterial()
            material.name = "xray-allen-mouse-atlas-shell"
            material.diffuse.contents = NSColor(
                srgbRed: 0.10,
                green: 0.43,
                blue: 0.72,
                alpha: 1
            )
            material.emission.contents = NSColor(
                srgbRed: 0.005,
                green: 0.025,
                blue: 0.05,
                alpha: 1
            )
            material.specular.contents = NSColor(white: 0.85, alpha: 1)
            material.shininess = 0.38
            material.lightingModel = .blinn
            material.transparency = 0.36
            material.transparencyMode = .dualLayer
            material.blendMode = .alpha
            material.isDoubleSided = true
            material.readsFromDepthBuffer = false
            material.writesToDepthBuffer = false
            geometry.materials = [material]
            // One opacity authority avoids the previous diffuse-alpha ×
            // material-transparency × node-opacity collapse that reduced the
            // whole brain to an almost-black gray silhouette.
            node.opacity = 1
            node.castsShadow = false
            // Render the non-depth-writing context shell before every planning
            // overlay. Applying the order to geometry-bearing descendants is
            // required because imported OBJ hierarchies do not inherit it.
            node.renderingOrder = -10_000
        }
        node.childNodes.forEach(applyBrainAppearance)
    }

    private func replaceHighlightedRegion(
        for snapshot: AnimalSceneSnapshot,
        generation: Int
    ) async throws {
        guard let regionMesh = snapshot.highlightedRegionMesh,
              let region = regionMesh.region
        else {
            highlightedRegionLayer.childNodes.forEach { $0.removeFromParentNode() }
            currentHighlightedRegionIdentity = nil
            setBrainSelectionContext(active: false)
            return
        }
        let regionIdentity = [
            String(region.structureId),
            regionMesh.mesh.sha256,
            region.rgb.map(String.init).joined(separator: ","),
        ].joined(separator: "@")
        if currentHighlightedRegionIdentity == regionIdentity,
           !highlightedRegionLayer.childNodes.isEmpty
        {
            highlightedRegionLayer.simdTransform = snapshot.transform.sourceToSceneMatrix
            setBrainSelectionContext(active: true)
            return
        }

        highlightedRegionLayer.childNodes.forEach { $0.removeFromParentNode() }
        currentHighlightedRegionIdentity = nil
        let loaded = try await loader.load(regionMesh.mesh)
        try Task.checkCancellation()
        guard generation == loadGeneration else { return }
        let importedRoot = loaded.makeRootNode()
        importedRoot.name = "allen-region-\(region.structureId)"
        applyHighlightedRegionAppearance(to: importedRoot, rgb: region.rgb)
        highlightedRegionLayer.addChildNode(importedRoot)
        highlightedRegionLayer.simdTransform = snapshot.transform.sourceToSceneMatrix
        currentHighlightedRegionIdentity = regionIdentity
        setBrainSelectionContext(active: true)
    }

    private func setBrainSelectionContext(active: Bool) {
        func update(_ node: SCNNode) {
            if let material = node.geometry?.firstMaterial,
                material.name == "xray-allen-mouse-atlas-shell"
            {
                // The reviewed atlas region meshes lie immediately inside the
                // root surface. A filled translucent shell is therefore still
                // capable of completely compositing over thin cortical layers.
                // Use a sparse wire context while a region is selected so its
                // true mesh remains visible without hiding probes or vessels.
                let replacement = (material.copy() as? SCNMaterial) ?? material
                replacement.fillMode = active ? .lines : .fill
                replacement.transparency = active ? 0.18 : 0.36
                replacement.transparencyMode = active ? .singleLayer : .dualLayer
                node.geometry?.materials = [replacement]
            }
            node.childNodes.forEach(update)
        }
        update(brainLayer)
    }

    private func applyHighlightedRegionAppearance(to node: SCNNode, rgb: [Int]) {
        node.categoryBitMask = SceneCategory.highlightedRegion.rawValue
        if let geometry = node.geometry {
            // Model I/O-backed OBJ geometry can retain its original neutral
            // material binding even after `materials` is replaced. Rebuilding
            // the lightweight SceneKit geometry wrapper preserves the verified
            // vertex/index buffers while ensuring the selected-region shader is
            // the one actually used by the renderer.
            let highlightedGeometry = SCNGeometry(
                sources: geometry.sources,
                elements: geometry.elements
            )
            highlightedGeometry.name = geometry.name
            // SceneKit presents device material channels through an sRGB
            // transfer. Supplying the ontology's sRGB bytes as linear values
            // preserves the Allen color on screen instead of washing it out.
            let color = NSColor(
                deviceRed: linearSceneColorComponent(rgb[0]),
                green: linearSceneColorComponent(rgb[1]),
                blue: linearSceneColorComponent(rgb[2]),
                alpha: 1
            )
            let material = SCNMaterial()
            material.name = "selected-allen-region"
            material.diffuse.contents = color
            material.emission.contents = color
            material.lightingModel = .constant
            material.transparency = 0.94
            material.transparencyMode = .singleLayer
            material.blendMode = .alpha
            material.isDoubleSided = true
            material.readsFromDepthBuffer = false
            material.writesToDepthBuffer = false
            highlightedGeometry.materials = [material]
            node.geometry = highlightedGeometry
            node.opacity = 1
            node.castsShadow = false
            node.renderingOrder = 0
        }
        node.childNodes.forEach {
            applyHighlightedRegionAppearance(to: $0, rgb: rgb)
        }
    }

    private func linearSceneColorComponent(_ byte: Int) -> CGFloat {
        let value = Double(byte) / 255
        if value <= 0.04045 {
            return CGFloat(value / 12.92)
        }
        return CGFloat(pow((value + 0.055) / 1.055, 2.4))
    }

    private func replaceProbe(for snapshot: AnimalSceneSnapshot) throws {
        probeLayer.childNodes.forEach { $0.removeFromParentNode() }
        let probe = try ProbeEnvelopeNodeFactory.makeNode(
            for: snapshot.selectedProbePlan,
            transform: snapshot.transform
        )
        probeLayer.addChildNode(probe)
    }

    private func replaceImplantSite(for snapshot: AnimalSceneSnapshot) throws {
        implantSiteLayer.childNodes.forEach { $0.removeFromParentNode() }
        guard let marker = snapshot.implantSite else { return }
        implantSiteLayer.addChildNode(
            try ImplantSiteNodeFactory.makeNode(
                for: marker,
                transform: snapshot.transform
            )
        )
    }

    private func replaceMajorVessels(
        for snapshot: AnimalSceneSnapshot,
        generation: Int
    ) async throws {
        guard let vessels = snapshot.majorVessels else {
            majorVesselLayerSwap.clear()
            return
        }
        let sourceIdentity = [
            vessels.provenance.derivedAssetSha256,
            vessels.atlas.metadataSha256,
        ].joined(separator: ":")
        let digest = [
            sourceIdentity,
            String(
                snapshot.minimumVisibleVesselDiameterMicrometres.bitPattern,
                radix: 16
            ),
        ].joined(separator: ":")
        if majorVesselLayerSwap.isCurrent(digest) {
            majorVesselLayer.childNodes.forEach {
                $0.simdTransform = snapshot.transform.sourceToSceneMatrix
            }
            return
        }

        // A different atlas/source cannot be represented by the prior layer.
        // For a display-only threshold change on the same verified graph,
        // however, retain the last complete mesh until its replacement is
        // ready; clearing here made the vessel layer visibly disappear during
        // each production-graph rebuild.
        majorVesselLayerSwap.prepare(for: sourceIdentity)
        majorVesselLayer.childNodes.forEach {
            $0.simdTransform = snapshot.transform.sourceToSceneMatrix
        }
        let graph = vessels.graph
        let mesh = try await majorVesselMeshBuilder(
            graph.pointsASRMicrometres,
            graph.radiiMicrometres,
            graph.runOffsets,
            snapshot.minimumVisibleVesselDiameterMicrometres
        )
        try Task.checkCancellation()
        guard generation == loadGeneration else { return }
        guard mesh.visibleSourceSegmentCount > 0 else {
            majorVesselLayerSwap.commit(
                node: nil,
                digest: digest,
                sourceIdentity: sourceIdentity
            )
            return
        }
        let node = MajorVesselNodeFactory.makeNode(
            mesh: mesh,
            transform: snapshot.transform
        )
        majorVesselLayerSwap.commit(
            node: node,
            digest: digest,
            sourceIdentity: sourceIdentity
        )
    }

    private func replaceSelectedVesselConflict(
        for snapshot: AnimalSceneSnapshot
    ) throws {
        selectedVesselConflictLayer.childNodes.forEach { $0.removeFromParentNode() }
        guard let conflict = snapshot.selectedVesselConflict else { return }
        guard let graph = snapshot.majorVessels?.graph else {
            throw AtlasSceneContractError.invalid(
                "A selected vessel conflict requires its current reviewed vessel graph."
            )
        }
        let node = try MajorVesselConflictNodeFactory.makeNode(
            for: conflict,
            graph: graph,
            transform: snapshot.transform
        )
        selectedVesselConflictLayer.addChildNode(node)
    }

    /// Frame the anatomical context plus the complete physical shank. The
    /// optional override is used by render-contract tests; production always
    /// takes the current snapshot geometry.
    func setCameraHome(
        for snapshot: AnimalSceneSnapshot,
        shanks overrideShanks: [ProbePlacedShank]? = nil
    ) {
        let minimum = snapshot.meshResult.sourceCoordinateFrame
            .bounds.minimumInclusiveMicrometres
        let maximum = snapshot.meshResult.sourceCoordinateFrame
            .bounds.maximumExclusiveMicrometres
        var sceneMinimum = SIMD3<Float>(repeating: .greatestFiniteMagnitude)
        var sceneMaximum = SIMD3<Float>(repeating: -.greatestFiniteMagnitude)
        for ap in [minimum[0], maximum[0]] {
            for dv in [minimum[1], maximum[1]] {
                for ml in [minimum[2], maximum[2]] {
                    guard
                        let point = try? snapshot.transform.scenePoint(
                        apMicrometres: ap,
                        dvMicrometres: dv,
                        mlMicrometres: ml
                        )
                    else { continue }
                    sceneMinimum = simd_min(sceneMinimum, point)
                    sceneMaximum = simd_max(sceneMaximum, point)
                }
            }
        }
        let shanks = overrideShanks ?? snapshot.selectedProbePlan?.shanks ?? []
        for shank in shanks {
            for endpoint in [shank.renderedProximalEnd, shank.tip] {
                guard let point = try? snapshot.transform.scenePoint(endpoint)
                else { continue }
                sceneMinimum = simd_min(sceneMinimum, point)
                sceneMaximum = simd_max(sceneMaximum, point)
            }
        }
        let center = (sceneMinimum + sceneMaximum) * 0.5
        let size = sceneMaximum - sceneMinimum
        let maximumDimension = max(size.x, max(size.y, size.z))
        let cameraXScale: Float = shanks.isEmpty ? 1.05 : 1.20
        let cameraZScale: Float = shanks.isEmpty ? 1.35 : 1.20
        homeCameraTarget = center
        // Keep both atlas AP (scene Z) and ML (scene X) visibly separated.
        // NP2013's sagittal layout spaces its four shanks along AP, while the
        // 90-degree clockwise layout spaces them along ML. The old nearly
        // straight posterior view collapsed the sagittal set into one apparent
        // line even though all four physical centerlines existed in the scene.
        cameraNode.simdPosition =
            center
            + SIMD3<Float>(
                maximumDimension * cameraXScale,
                maximumDimension * 0.55,
                maximumDimension * cameraZScale
        )
        cameraNode.simdLook(at: center)
        homeCameraTransform = cameraNode.simdTransform
        view.defaultCameraController.target = SCNVector3(center)
        view.defaultCameraController.stopInertia()
        requestDisplay()
    }

    private func requestDisplay() {
        view.needsDisplay = true
        view.setNeedsDisplay(view.bounds)
    }

    private func pick(at point: CGPoint) {
        let options: [SCNHitTestOption: Any] = [
            .categoryBitMask: SceneCategory.brain.rawValue,
            .searchMode: SCNHitTestSearchMode.closest.rawValue,
        ]
        guard view.hitTest(point, options: options).first != nil,
              let transform = currentTransform
        else {
            onBlankSelection?()
            return
        }
        let nearWorld = view.unprojectPoint(
            SCNVector3(Float(point.x), Float(point.y), 0)
        )
        let farWorld = view.unprojectPoint(
            SCNVector3(Float(point.x), Float(point.y), 1)
        )
        do {
            let start = try transform.atlasPoint(
                from: SIMD3(Float(nearWorld.x), Float(nearWorld.y), Float(nearWorld.z))
            )
            let end = try transform.atlasPoint(
                from: SIMD3(Float(farWorld.x), Float(farWorld.y), Float(farWorld.z))
            )
            onRayPick?(start, end)
        } catch {
            onBlankSelection?()
        }
    }
}
