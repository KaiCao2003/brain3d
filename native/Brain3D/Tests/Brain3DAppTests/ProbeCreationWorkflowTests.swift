import Brain3DCore
import Foundation
import Testing
@testable import Brain3DApp

@Suite("Probe creation workflow")
struct ProbeCreationWorkflowTests {
    @Test("A complete stereotaxic Neuropixels draft is actionable")
    func completeStereotaxicDraft() {
        #expect(blocker() == nil)
    }

    @Test("Each hidden prerequisite produces an operator-facing reason")
    func prerequisiteReasons() {
        #expect(blocker(planningUnavailableReason: "Activate calibration.")
            == "Activate calibration.")
        #expect(blocker(hasSelectedModel: false)
            == "Select a probe model from the connected catalog.")
        #expect(blocker(selectedTargetId: "")
            == "Select a stored implant target.")
        #expect(blocker(name: "   ")
            == "Enter a probe plan name.")
        #expect(blocker(azimuth: "181")
            == "Enter azimuth from −180° through 180°.")
        #expect(blocker(elevation: "-91")
            == "Enter elevation from −90° through 90°.")
        #expect(blocker(depth: "0")
            == "Enter a positive insertion depth in millimetres.")
        #expect(blocker(axialRotation: "")
            == "Enter axial rotation from −180° through 180°.")
        #expect(blocker(acknowledgementGiven: false)
            == "Acknowledge the selected probe geometry before continuing.")
    }

    @Test("Operator depth is millimetres while the geometry protocol remains micrometres")
    func depthUnitConversion() {
        #expect(ProbeInputUnits.micrometres(fromMillimetres: 3.5) == 3_500)
        #expect(ProbeInputUnits.millimetres(fromMicrometres: 3_500) == 3.5)
    }

    @Test("Placement modes require only the fields defined by their backend contract")
    func placementModeFields() {
        #expect(blocker(
            mode: .entryAndTarget,
            entryAP: "-1.25",
            entryML: "-0.8",
            entryDV: "-2.4",
            azimuth: "",
            elevation: "",
            depth: ""
        ) == nil)
        #expect(blocker(
            mode: .entryAndTarget,
            entryAP: "",
            entryML: "-0.8",
            entryDV: "-2.4",
            azimuth: "",
            elevation: "",
            depth: ""
        ) == "Enter valid entry AP, ML, and DV values in millimetres.")
        #expect(blocker(
            mode: .entryAnglesDepth,
            entryAP: "-1.25",
            entryML: "-0.8",
            entryDV: "0",
            azimuth: "-12",
            elevation: "-35",
            depth: "4.2"
        ) == nil)
        #expect(blocker(
            mode: .targetAnglesDepth,
            entryAP: "",
            entryML: "",
            entryDV: "",
            azimuth: "-12",
            elevation: "-35",
            depth: "4.2"
        ) == nil)
    }

    @Test("Placement guidance names the coordinate or angle frame")
    func placementGuidance() {
        #expect(ProbePlacementGuidance.text(for: .entryAndTarget)
            .hasPrefix("Bregma frame:"))
        #expect(ProbePlacementGuidance.text(for: .entryAnglesDepth)
            .contains("calibrated subject stereotaxic AP/ML/DV"))
        #expect(ProbePlacementGuidance.text(for: .targetAnglesDepth)
            .contains("atlas AP/ML/DV after the active calibration transform"))
        #expect(ProbePlacementGuidance.text(for: .targetAnglesDepth)
            .contains("not manipulator angles"))
        #expect(ProbePlacementGuidance.text(for: .stereotaxicTargetManipulator)
            .contains("calibrated subject stereotaxic AP/ML/DV"))
    }

    @Test("Neuropixels 2.0 catalog identities remain explicit")
    func neuropixels2Identity() {
        #expect(ProbeCatalogPresentation.isNeuropixels2(
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId
        ))
        #expect(ProbeCatalogPresentation.isNeuropixels2(
            modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId
        ))
        #expect(!ProbeCatalogPresentation.isNeuropixels2(
            modelId: ProbePlanningContract.neuropixels2QuadBaseFourShankModelId
        ))
        #expect(!ProbeCatalogPresentation.isNeuropixels2(
            modelId: ProbePlanningContract.neuropixelsModelId
        ))
        #expect(!ProbeCatalogPresentation.isNeuropixels2(
            modelId: "imec-neuropixels-2.0-lookalike"
        ))
        #expect(ProbeCatalogPresentation.simultaneousChannelCount(
            modelId: ProbePlanningContract.neuropixels2SingleShankModelId
        ) == 384)
        #expect(ProbeCatalogPresentation.simultaneousChannelCount(
            modelId: ProbePlanningContract.neuropixels2StandardFourShankModelId
        ) == 384)
        #expect(ProbeCatalogPresentation.simultaneousChannelCount(
            modelId: ProbePlanningContract.neuropixels2QuadBaseFourShankModelId
        ) == nil)
        #expect(ProbeCatalogPresentation.simultaneousChannelCount(
            modelId: ProbePlanningContract.neuropixelsModelId
        ) == nil)
    }

    @Test("3D overlay status is active only for the ready current scene")
    func overlayStatus() {
        let slicePrefix = "Overlay active in Dorsal, Coronal, Sagittal, and Horizontal."
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .ready,
            sceneContainsCurrentPlan: true
        ) == "Overlay active in Dorsal, Coronal, Sagittal, Horizontal, and 3D.")
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .loadingGeometry,
            sceneContainsCurrentPlan: true
        ) == "\(slicePrefix) 3D overlay pending.")
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .ready,
            sceneContainsCurrentPlan: false
        ) == "\(slicePrefix) 3D overlay pending scene refresh.")
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .failed("mesh missing"),
            sceneContainsCurrentPlan: true
        ) == "\(slicePrefix) 3D overlay unavailable.")
        #expect(ProbeOverlayPresentation.text(
            threeDimensionalPhase: .unavailable("service capability missing"),
            sceneContainsCurrentPlan: false
        ) == "\(slicePrefix) 3D overlay unavailable.")
    }

    private func blocker(
        planningUnavailableReason: String? = nil,
        hasSelectedModel: Bool = true,
        availableTargetIds: [String] = ["target-1"],
        selectedTargetId: String = "target-1",
        name: String = "NP2 left V1",
        mode: ProbePlacementMode = .stereotaxicTargetManipulator,
        entryAP: String = "",
        entryML: String = "",
        entryDV: String = "",
        azimuth: String = "-12",
        elevation: String = "-35",
        depth: String = "4.2",
        axialRotation: String = "0",
        requiresAcknowledgement: Bool = true,
        acknowledgementGiven: Bool = true
    ) -> String? {
        ProbeDraftReadinessPolicy.blockingReason(
            planningUnavailableReason: planningUnavailableReason,
            hasSelectedModel: hasSelectedModel,
            availableTargetIds: availableTargetIds,
            selectedTargetId: selectedTargetId,
            name: name,
            mode: mode,
            entryAP: entryAP,
            entryML: entryML,
            entryDV: entryDV,
            azimuth: azimuth,
            elevation: elevation,
            depth: depth,
            axialRotation: axialRotation,
            requiresAcknowledgement: requiresAcknowledgement,
            acknowledgementGiven: acknowledgementGiven
        )
    }
}

@Suite("Probe planning prerequisites")
struct ProbePlanningAvailabilityPolicyTests {
    @Test("Availability distinguishes setup failures from in-flight work")
    func blockingReasons() {
        #expect(reason(connectionReady: false) == "Connect to the planning service.")
        #expect(reason(hasProject: false) == "Open or create an animal plan.")
        #expect(reason(hasActiveCalibration: false)
            == "Activate a passing subject calibration.")
        #expect(reason(calibrationPermitsPlanning: false)
            == "The active subject calibration does not pass planning checks.")
        #expect(reason(serviceSupportsProbePlanning: false)
            == "The connected service does not support calibrated probe planning.")
        #expect(reason(probeOperationInProgress: true)
            == "Wait for the probe operation to finish.")
        #expect(reason() == nil)
    }

    private func reason(
        connectionReady: Bool = true,
        hasProject: Bool = true,
        hasActiveCalibration: Bool = true,
        calibrationPermitsPlanning: Bool = true,
        serviceSupportsProbePlanning: Bool = true,
        projectOperationInProgress: Bool = false,
        calibrationOperationInProgress: Bool = false,
        probeOperationInProgress: Bool = false
    ) -> String? {
        ProbePlanningAvailabilityPolicy.blockingReason(
            connectionReady: connectionReady,
            hasProject: hasProject,
            hasActiveCalibration: hasActiveCalibration,
            calibrationPermitsPlanning: calibrationPermitsPlanning,
            serviceSupportsProbePlanning: serviceSupportsProbePlanning,
            projectOperationInProgress: projectOperationInProgress,
            calibrationOperationInProgress: calibrationOperationInProgress,
            probeOperationInProgress: probeOperationInProgress
        )
    }
}

@Suite("Project identity presentation")
struct ProjectStatusPresentationTests {
    @Test("Subject ID is never omitted from a loaded project")
    func subjectId() {
        #expect(ProjectStatusPresentation.text(
            title: "Left V1 plan",
            subjectId: "mouse-042",
            hasUnsavedChanges: false
        ) == "Left V1 plan · Subject ID mouse-042 · animal-only · saved")
        #expect(ProjectStatusPresentation.text(
            title: "Legacy plan",
            subjectId: " ",
            hasUnsavedChanges: true
        ) == "Legacy plan · Subject ID unavailable · animal-only · unsaved changes")
    }
}
