@testable import Brain3DScene
import CoreGraphics
import Testing

@Suite("3D camera click-versus-drag classification")
struct SceneClickClassifierTests {
    @Test("Four-point movement remains a click")
    func inclusiveThreshold() {
        var classifier = SceneClickClassifier()
        classifier.begin(at: .zero)
        let isClick = classifier.end(at: CGPoint(x: 4, y: 0))

        #expect(isClick)
    }

    @Test("Movement beyond four points remains a drag even after returning")
    func stickyDrag() {
        var classifier = SceneClickClassifier()
        classifier.begin(at: .zero)
        classifier.update(to: CGPoint(x: 4.1, y: 0))
        let isClick = classifier.end(at: CGPoint(x: 1, y: 0))

        #expect(!isClick)
    }
}
