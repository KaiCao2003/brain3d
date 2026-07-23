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
    private let view: AtlasInteractiveSCNView
    private let loader: AtlasMeshLoader
    private let scene = SCNScene()
    private let brainLayer = SCNNode()
    private let highlightedRegionLayer = SCNNode()
    private let probeLayer = SCNNode()
    private let majorVesselLayer = SCNNode()
    private let selectedVesselConflictLayer = SCNNode()
    private let cameraNode = SCNNode()
    private var currentMeshSHA256: String?
    private var currentHighlightedRegionMeshSHA256: String?
    private var currentMajorVesselDigest: String?
    private var currentSnapshotIdentity: String?
    private var currentTransform: AtlasSceneTransform?
    private var loadGeneration = 0
    private var reduceMotion = false
    private var homeCameraTransform = matrix_identity_float4x4
    private var homeCameraTarget = SIMD3<Float>.zero

    var onRayPick: ((AtlasRayPoint, AtlasRayPoint) -> Void)?
    var onBlankSelection: (() -> Void)?
    var cameraInertiaEnabled: Bool { view.defaultCameraController.inertiaEnabled }

    init(view: AtlasInteractiveSCNView, loader: AtlasMeshLoader = AtlasMeshLoader()) {
        self.view = view
        self.loader = loader
        configureScene()
    }

    func apply(
        snapshot: AnimalSceneSnapshot,
        phaseChanged: @escaping (AnimalScenePhase) -> Void
    ) async {
        guard currentSnapshotIdentity != snapshot.identity else {
            phaseChanged(.ready)
            return
        }
        loadGeneration += 1
        let generation = loadGeneration
        currentTransform = snapshot.transform

        do {
            phaseChanged(.loading)
            if currentMeshSHA256 != snapshot.meshResult.mesh.sha256 {
                let loaded = try await loader.load(snapshot.meshResult.mesh)
                try Task.checkCancellation()
                guard generation == loadGeneration else { return }
                replaceBrain(with: loaded.makeRootNode(), snapshot: snapshot)
                currentMeshSHA256 = snapshot.meshResult.mesh.sha256
                setCameraHome(for: snapshot)
            } else {
                brainLayer.simdTransform = snapshot.transform.sourceToSceneMatrix
            }
            try await replaceHighlightedRegion(for: snapshot, generation: generation)
            try Task.checkCancellation()
            guard generation == loadGeneration else { return }
            try replaceProbe(for: snapshot)
            selectedVesselConflictLayer.childNodes.forEach { $0.removeFromParentNode() }
            try await replaceMajorVessels(for: snapshot, generation: generation)
            try Task.checkCancellation()
            guard generation == loadGeneration else { return }
            try replaceSelectedVesselConflict(for: snapshot)
            currentSnapshotIdentity = snapshot.identity
            phaseChanged(.ready)
        } catch is CancellationError {
            return
        } catch {
            guard generation == loadGeneration else { return }
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
    }

    func offscreenSnapshot(size: CGSize) -> NSImage {
        let renderer = SCNRenderer(device: MTLCreateSystemDefaultDevice(), options: nil)
        renderer.scene = scene
        renderer.pointOfView = cameraNode
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
        majorVesselLayer.name = "reviewed-major-vessel-layer"
        selectedVesselConflictLayer.name = "selected-vessel-conflict-layer"
        brainLayer.categoryBitMask = SceneCategory.brain.rawValue
        highlightedRegionLayer.categoryBitMask = SceneCategory.highlightedRegion.rawValue
        probeLayer.categoryBitMask = SceneCategory.probe.rawValue
        majorVesselLayer.categoryBitMask = SceneCategory.majorVessel.rawValue
        selectedVesselConflictLayer.categoryBitMask =
            SceneCategory.selectedVesselConflict.rawValue
        scene.rootNode.addChildNode(brainLayer)
        scene.rootNode.addChildNode(highlightedRegionLayer)
        scene.rootNode.addChildNode(probeLayer)
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
        ambient.intensity = 520
        ambient.color = NSColor(calibratedWhite: 0.94, alpha: 1)
        ambientNode.light = ambient
        scene.rootNode.addChildNode(ambientNode)

        let keyNode = SCNNode()
        let key = SCNLight()
        key.type = .directional
        key.intensity = 920
        key.color = NSColor(calibratedWhite: 1, alpha: 1)
        keyNode.light = key
        keyNode.eulerAngles = SCNVector3(-0.75, 0.55, 0.25)
        scene.rootNode.addChildNode(keyNode)

        scene.background.contents = NSColor(calibratedWhite: 0.055, alpha: 1)
        view.scene = scene
        view.pointOfView = cameraNode
        view.backgroundColor = NSColor(calibratedWhite: 0.055, alpha: 1)
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
                calibratedRed: 0.16,
                green: 0.48,
                blue: 0.78,
                alpha: 0.65
            )
            material.emission.contents = NSColor.clear
            material.lightingModel = .constant
            material.transparency = 0.65
            material.transparencyMode = .singleLayer
            material.blendMode = .alpha
            material.isDoubleSided = true
            material.readsFromDepthBuffer = false
            material.writesToDepthBuffer = false
            geometry.materials = [material]
            // SceneKit's imported-OBJ path can flatten or otherwise reinterpret
            // material transparency. Node opacity is an independent final-stage
            // guarantee that the anatomical shell cannot become opaque.
            node.opacity = 0.28
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
            currentHighlightedRegionMeshSHA256 = nil
            return
        }
        if currentHighlightedRegionMeshSHA256 == regionMesh.mesh.sha256,
           !highlightedRegionLayer.childNodes.isEmpty
        {
            highlightedRegionLayer.simdTransform = snapshot.transform.sourceToSceneMatrix
            return
        }

        highlightedRegionLayer.childNodes.forEach { $0.removeFromParentNode() }
        currentHighlightedRegionMeshSHA256 = nil
        let loaded = try await loader.load(regionMesh.mesh)
        try Task.checkCancellation()
        guard generation == loadGeneration else { return }
        let importedRoot = loaded.makeRootNode()
        importedRoot.name = "allen-region-\(region.structureId)"
        applyHighlightedRegionAppearance(to: importedRoot, rgb: region.rgb)
        highlightedRegionLayer.addChildNode(importedRoot)
        highlightedRegionLayer.simdTransform = snapshot.transform.sourceToSceneMatrix
        currentHighlightedRegionMeshSHA256 = regionMesh.mesh.sha256
    }

    private func applyHighlightedRegionAppearance(to node: SCNNode, rgb: [Int]) {
        node.categoryBitMask = SceneCategory.highlightedRegion.rawValue
        if let geometry = node.geometry {
            let color = NSColor(
                srgbRed: CGFloat(rgb[0]) / 255,
                green: CGFloat(rgb[1]) / 255,
                blue: CGFloat(rgb[2]) / 255,
                alpha: 1
            )
            let material = SCNMaterial()
            material.name = "selected-allen-region"
            material.diffuse.contents = color
            material.emission.contents = color.withAlphaComponent(0.18)
            material.lightingModel = .constant
            material.transparency = 0.82
            material.transparencyMode = .singleLayer
            material.blendMode = .alpha
            material.isDoubleSided = true
            material.readsFromDepthBuffer = true
            material.writesToDepthBuffer = true
            geometry.materials = [material]
            node.opacity = 0.88
            node.castsShadow = false
            node.renderingOrder = -5_000
        }
        node.childNodes.forEach {
            applyHighlightedRegionAppearance(to: $0, rgb: rgb)
        }
    }

    private func replaceProbe(for snapshot: AnimalSceneSnapshot) throws {
        probeLayer.childNodes.forEach { $0.removeFromParentNode() }
        let probe = try ProbeEnvelopeNodeFactory.makeNode(
            for: snapshot.selectedProbePlan,
            transform: snapshot.transform
        )
        probeLayer.addChildNode(probe)
    }

    private func replaceMajorVessels(
        for snapshot: AnimalSceneSnapshot,
        generation: Int
    ) async throws {
        guard let vessels = snapshot.majorVessels else {
            majorVesselLayer.childNodes.forEach { $0.removeFromParentNode() }
            currentMajorVesselDigest = nil
            return
        }
        let digest = vessels.provenance.derivedAssetSha256
        if currentMajorVesselDigest == digest,
           !majorVesselLayer.childNodes.isEmpty
        {
            majorVesselLayer.childNodes.forEach {
                $0.simdTransform = snapshot.transform.sourceToSceneMatrix
            }
            return
        }

        // Never leave geometry from a different atlas or source visible while the
        // verified replacement is being prepared off the main actor.
        majorVesselLayer.childNodes.forEach { $0.removeFromParentNode() }
        currentMajorVesselDigest = nil
        let graph = vessels.graph
        let mesh = try await MajorVesselTubeMeshBuilder.buildAsync(
            pointsASRMicrometres: graph.pointsASRMicrometres,
            radiiMicrometres: graph.radiiMicrometres,
            runOffsets: graph.runOffsets
        )
        try Task.checkCancellation()
        guard generation == loadGeneration else { return }
        let node = MajorVesselNodeFactory.makeNode(
            mesh: mesh,
            transform: snapshot.transform
        )
        majorVesselLayer.addChildNode(node)
        currentMajorVesselDigest = digest
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

    private func setCameraHome(for snapshot: AnimalSceneSnapshot) {
        let minimum = snapshot.meshResult.sourceCoordinateFrame
            .bounds.minimumInclusiveMicrometres
        let maximum = snapshot.meshResult.sourceCoordinateFrame
            .bounds.maximumExclusiveMicrometres
        var sceneMinimum = SIMD3<Float>(repeating: .greatestFiniteMagnitude)
        var sceneMaximum = SIMD3<Float>(repeating: -.greatestFiniteMagnitude)
        for ap in [minimum[0], maximum[0]] {
            for dv in [minimum[1], maximum[1]] {
                for ml in [minimum[2], maximum[2]] {
                    guard let point = try? snapshot.transform.scenePoint(
                        apMicrometres: ap,
                        dvMicrometres: dv,
                        mlMicrometres: ml
                    ) else { continue }
                    sceneMinimum = simd_min(sceneMinimum, point)
                    sceneMaximum = simd_max(sceneMaximum, point)
                }
            }
        }
        let center = (sceneMinimum + sceneMaximum) * 0.5
        let size = sceneMaximum - sceneMinimum
        let maximumDimension = max(size.x, max(size.y, size.z))
        homeCameraTarget = center
        cameraNode.simdPosition = center + SIMD3<Float>(
            maximumDimension * 0.34,
            maximumDimension * 0.20,
            maximumDimension * 1.75
        )
        cameraNode.simdLook(at: center)
        homeCameraTransform = cameraNode.simdTransform
        view.defaultCameraController.target = SCNVector3(center)
        view.defaultCameraController.stopInertia()
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
