import Brain3DCore
import Foundation
import Testing

@Suite("Explicit animal-only acknowledgement")
struct AnimalOnlyAcknowledgementTests {
    @Test("A new project request cannot exist before explicit acknowledgement")
    func blocksUnacknowledgedRequest() {
        let acknowledgement = AnimalOnlyAcknowledgementState()

        #expect(!acknowledgement.isExplicitlyAcknowledged)
        #expect(ProjectNewParameters(acknowledgement: acknowledgement) == nil)
    }

    @Test("The wire receives true only after the acknowledgement state is explicitly set")
    func acknowledgedRequestWireShape() throws {
        var acknowledgement = AnimalOnlyAcknowledgementState()
        acknowledgement.setExplicitlyAcknowledged(true)

        let parameters = try #require(
            ProjectNewParameters(
                acknowledgement: acknowledgement,
                title: "Animal plan",
                subjectId: "mouse-a"
            )
        )
        let data = try JSONEncoder().encode(parameters)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])

        #expect(object["animalResearchOnlyAcknowledged"] as? Bool == true)
        #expect(object["protocolVersion"] as? Int == BridgeProtocolVersion.current)
        #expect(object["title"] as? String == "Animal plan")
        #expect(object["subjectId"] as? String == "mouse-a")

        acknowledgement.setExplicitlyAcknowledged(false)
        #expect(ProjectNewParameters(acknowledgement: acknowledgement) == nil)
    }

    @Test("Animal-only state validation fails closed for nil, false, and warning mismatch")
    func contractValidationFailsClosed() {
        let warning = SafetyPolicy.animalResearchOnly

        #expect(!AnimalOnlyContract.isValid(animalOnly: nil, warning: warning))
        #expect(!AnimalOnlyContract.isValid(animalOnly: false, warning: warning))
        #expect(!AnimalOnlyContract.isValid(animalOnly: true, warning: nil))
        #expect(!AnimalOnlyContract.isValid(animalOnly: true, warning: "Animal use"))
        #expect(AnimalOnlyContract.isValid(animalOnly: true, warning: warning))
    }
}
