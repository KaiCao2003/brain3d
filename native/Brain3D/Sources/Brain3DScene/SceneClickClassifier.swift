import CoreGraphics

struct SceneClickClassifier {
    static let threshold: CGFloat = 4

    private var startPoint: CGPoint?
    private var exceededThreshold = false

    mutating func begin(at point: CGPoint) {
        startPoint = point
        exceededThreshold = false
    }

    mutating func update(to point: CGPoint) {
        guard !exceededThreshold, let startPoint else { return }
        exceededThreshold = hypot(point.x - startPoint.x, point.y - startPoint.y)
            > Self.threshold
    }

    mutating func end(at point: CGPoint) -> Bool {
        update(to: point)
        defer {
            startPoint = nil
            exceededThreshold = false
        }
        guard let startPoint, !exceededThreshold else { return false }
        return hypot(point.x - startPoint.x, point.y - startPoint.y) <= Self.threshold
    }
}
