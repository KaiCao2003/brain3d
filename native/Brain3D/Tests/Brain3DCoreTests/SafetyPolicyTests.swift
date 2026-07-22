import Brain3DCore
import Testing

@Suite("Animal-only safety policy")
struct SafetyPolicyTests {
    @Test("The clinical-use restriction is exact and persistent-ready")
    func animalOnlyWarning() {
        #expect(
            SafetyPolicy.animalResearchOnly
                == "Animal research only — not for human or clinical use"
        )
    }

    @Test("The published population reference is inspectable at pinned HTTPS sources")
    func populationReferenceLinks() {
        #expect(
            SafetyPolicy.populationReferenceLandingPage
                == "https://data.mendeley.com/datasets/stxvn5sv44/1"
        )
        #expect(
            SafetyPolicy.populationReferencePaperURL
                == "https://doi.org/10.1016/j.celrep.2022.110978"
        )
    }

    @Test("Only the lower-resolution testing atlas is named")
    func supportedAtlas() {
        #expect(SafetyPolicy.supportedAtlasIdentifier == "allen_mouse_25um")
        #expect(SafetyPolicy.supportedAtlasVersion == "1.2")
        #expect(SafetyPolicy.supportedAtlasDisplayName == "allen_mouse_25um v1.2")
        #expect(!SafetyPolicy.supportedAtlasDisplayName.contains("10um"))
    }

    @Test("All five planning views have direct button labels")
    func planningViews() {
        #expect(WorkspaceMode.allCases.map(\.rawValue) == [
            "Dorsal", "Coronal", "Sagittal", "Horizontal", "3D",
        ])
        #expect(WorkspaceMode.allCases.allSatisfy { !$0.accessibilityDescription.isEmpty })
    }

    @Test("Population reference language cannot imply subject vessels")
    func populationCaveat() {
        #expect(SafetyPolicy.populationDensityCaveat.contains("not individual vessel paths"))
        #expect(SafetyPolicy.populationDensityCaveat.contains("not subject-specific"))
        #expect(SafetyPolicy.populationDensityCaveat.contains("four fixed adult C57BL/6 brains"))
        #expect(SafetyPolicy.populationDensityCaveat.contains("100 µm local window"))
    }
}
