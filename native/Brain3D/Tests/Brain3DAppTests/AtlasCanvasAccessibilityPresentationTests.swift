import Testing
@testable import Brain3DApp

@Suite("Atlas canvas accessibility presentation")
struct AtlasCanvasAccessibilityPresentationTests {
    @Test("Ontology selection is announced without requiring a point pick")
    func activeRegionWithoutPointPick() {
        #expect(
            AtlasCanvasAccessibilityPresentation.sliceValue(
                sliceNumber: 42,
                sliceCount: 528,
                activeRegionAcronym: "RSPd1",
                pointPickAcronym: nil
            ) == "Slice 42 of 528, selected region RSPd1"
        )
        #expect(
            AtlasCanvasAccessibilityPresentation.dorsalValue(
                vesselStatus: "38,307 visible vessel segments",
                activeRegionAcronym: "RSPd1",
                pointPickAcronym: nil
            ) == "38,307 visible vessel segments, selected region RSPd1"
        )
    }

    @Test("Active ontology selection takes precedence over a stale point pick")
    func activeRegionWithDifferentPointPick() {
        #expect(
            AtlasCanvasAccessibilityPresentation.regionStatus(
                activeRegionAcronym: "RSPd1",
                pointPickAcronym: "TH"
            ) == "selected region RSPd1, last point pick TH"
        )
    }

    @Test("Point-pick and empty states remain descriptive")
    func pointPickAndEmptyStates() {
        #expect(
            AtlasCanvasAccessibilityPresentation.regionStatus(
                activeRegionAcronym: nil,
                pointPickAcronym: "TH"
            ) == "last point pick TH"
        )
        #expect(
            AtlasCanvasAccessibilityPresentation.regionStatus(
                activeRegionAcronym: nil,
                pointPickAcronym: nil
            ) == "no selected region"
        )
    }
}
