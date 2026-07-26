import AppKit
import Brain3DCore
import CoreGraphics
import Foundation
import PDFKit

enum SurgeryAtlasProbeOverlayError: LocalizedError, Equatable {
  case missingSurfaceRelativeInput
  case inconsistentPrefill(String)
  case invalidCoordinateMap(String)
  case invalidGeometry(String)
  case svgImageUnavailable

  var errorDescription: String? {
    switch self {
    case .missingSurfaceRelativeInput:
      "A surface-relative probe plan is required for the historical-atlas overlay."
    case .inconsistentPrefill(let field):
      "The surgery-plan prefill does not match the probe plan for \(field)."
    case .invalidCoordinateMap(let message):
      "The historical-atlas coordinate map is invalid: \(message)"
    case .invalidGeometry(let message):
      "The probe overlay geometry is invalid: \(message)"
    case .svgImageUnavailable:
      "AppKit could not decode the complete probe-overlay SVG."
    }
  }
}

/// A reviewed affine map from bregma-relative millimetres into the historical
/// atlas page's 792 x 612, top-left-origin coordinate space.
///
/// This is deliberately explicit. The historical plates do not share one
/// global origin or plot rectangle, so callers must resolve the map from the
/// exact selected page rather than applying a visually plausible constant.
struct SurgeryAtlasCoordinateMap: Equatable, Sendable {
  static let viewBox = CGRect(x: 0, y: 0, width: 792, height: 612)

  let orientation: SurgeryAtlasOrientation
  let plotRect: CGRect
  let horizontalZeroX: CGFloat
  let dvZeroY: CGFloat
  let horizontalPointsPerMillimetre: CGFloat
  let dvPointsPerMillimetre: CGFloat

  init(
    orientation: SurgeryAtlasOrientation,
    plotRect: CGRect,
    horizontalZeroX: CGFloat,
    dvZeroY: CGFloat,
    horizontalPointsPerMillimetre: CGFloat,
    dvPointsPerMillimetre: CGFloat
  ) throws {
    let values = [
      plotRect.minX,
      plotRect.minY,
      plotRect.width,
      plotRect.height,
      horizontalZeroX,
      dvZeroY,
      horizontalPointsPerMillimetre,
      dvPointsPerMillimetre,
    ]
    guard values.allSatisfy(\.isFinite),
      plotRect.width > 0,
      plotRect.height > 0,
      horizontalPointsPerMillimetre > 0,
      dvPointsPerMillimetre > 0,
      !plotRect.intersection(Self.viewBox).isNull,
      Self.viewBox.contains(
        CGRect(
          x: plotRect.minX,
          y: plotRect.minY,
          width: plotRect.width,
          height: plotRect.height
        )
      )
    else {
      throw SurgeryAtlasProbeOverlayError.invalidCoordinateMap(
        "the plot bounds, origins, and scales must be finite and inside the page"
      )
    }
    self.orientation = orientation
    self.plotRect = plotRect
    self.horizontalZeroX = horizontalZeroX
    self.dvZeroY = dvZeroY
    self.horizontalPointsPerMillimetre = horizontalPointsPerMillimetre
    self.dvPointsPerMillimetre = dvPointsPerMillimetre
  }

  /// Resolve the exact selected page instead of guessing a shared plate
  /// origin. ArtBox is the page-specific artwork footprint. The right-hand
  /// DV grid labels establish its millimetre scale and DV=0; a missing or
  /// ambiguous grid fails closed.
  static func historicalAtlas(
    page: PDFPage,
    plate: SurgeryAtlasPlate
  ) throws -> SurgeryAtlasCoordinateMap {
    let mediaBox = page.bounds(for: .mediaBox)
    let artBox = page.bounds(for: .artBox)
    guard abs(mediaBox.width - viewBox.width) < 0.05,
      abs(mediaBox.height - viewBox.height) < 0.05,
      !artBox.isEmpty,
      let pageText = page.string,
      !pageText.isEmpty
    else {
      throw SurgeryAtlasProbeOverlayError.invalidCoordinateMap(
        "the selected page is not a readable 792 x 612 historical plate"
      )
    }

    let normalizedArtBox = CGRect(
      x: artBox.minX - mediaBox.minX,
      y: mediaBox.maxY - artBox.maxY,
      width: artBox.width,
      height: artBox.height
    ).intersection(viewBox)
    let dvSamples = try rightAxisSamples(
      page: page,
      pageText: pageText,
      mediaBox: mediaBox,
      normalizedArtBox: normalizedArtBox
    )
    let dvScale = try gridScale(from: dvSamples)
    let dvZero = median(
      dvSamples.map { $0.yDown - CGFloat($0.value) * dvScale }
    )

    let horizontalZero: CGFloat
    switch plate.orientation {
    case .coronal:
      // The coronal artwork is centered on its page-specific ML=0 line.
      horizontalZero = normalizedArtBox.midX
    case .sagittal:
      horizontalZero = try sagittalAPZero(
        page: page,
        pageText: pageText,
        mediaBox: mediaBox
      )
    }

    return try SurgeryAtlasCoordinateMap(
      orientation: plate.orientation,
      plotRect: normalizedArtBox,
      horizontalZeroX: horizontalZero,
      dvZeroY: dvZero,
      // The printed historical grid uses square millimetres. Inferring
      // the scale from this exact page also preserves its Illustrator
      // transform instead of rounding it to 72 or 48 points.
      horizontalPointsPerMillimetre: dvScale,
      dvPointsPerMillimetre: dvScale
    )
  }

  fileprivate func project(
    apMillimetres: Double,
    mlMillimetres: Double,
    dvMillimetres: Double
  ) -> CGPoint {
    let x: CGFloat
    switch orientation {
    case .coronal:
      // User convention: negative ML is the animal's left hemisphere;
      // the printed coronal plate depicts animal-left on page-right.
      x =
        horizontalZeroX - CGFloat(mlMillimetres)
        * horizontalPointsPerMillimetre
    case .sagittal:
      // Printed sagittal plates place anterior (+AP) to the left.
      x =
        horizontalZeroX - CGFloat(apMillimetres)
        * horizontalPointsPerMillimetre
    }
    return CGPoint(
      x: x,
      y: dvZeroY + CGFloat(dvMillimetres) * dvPointsPerMillimetre
    )
  }

  private struct AxisSample {
    let value: Int
    let x: CGFloat
    let yDown: CGFloat
  }

  private static func rightAxisSamples(
    page: PDFPage,
    pageText: String,
    mediaBox: CGRect,
    normalizedArtBox: CGRect
  ) throws -> [AxisSample] {
    let text = pageText as NSString
    let expression = try NSRegularExpression(
      pattern: #"(?<![0-9.])([0-9])(?![0-9.])"#
    )
    let candidates = expression.matches(
      in: pageText,
      range: NSRange(location: 0, length: text.length)
    ).compactMap { match -> AxisSample? in
      let range = match.range(at: 1)
      guard let selection = page.selection(for: range),
        let value = Int(text.substring(with: range))
      else { return nil }
      let bounds = selection.bounds(for: page)
      let normalizedX = bounds.midX - mediaBox.minX
      guard normalizedX > Self.viewBox.width * 0.70 else {
        return nil
      }
      return AxisSample(
        value: value,
        x: normalizedX,
        yDown: mediaBox.maxY - bounds.midY
      )
    }
    // Illustrator pages sometimes duplicate the same text object and a
    // few ArtBoxes extend beyond the grid. Find the right-axis vertical
    // column itself, deduplicating only coincident glyphs. This is
    // deterministic and refuses pages without at least two axis values.
    let columns = candidates.map(\.x).map { center in
      let nearCenter = candidates.filter { abs($0.x - center) <= 3.5 }
      let unique = Dictionary(grouping: nearCenter, by: \.value).compactMap {
        value, grouped -> AxisSample? in
        let ordered = grouped.sorted { $0.yDown < $1.yDown }
        guard let first = ordered.first,
          ordered.allSatisfy({ abs($0.yDown - first.yDown) <= 0.05 })
        else { return nil }
        return AxisSample(value: value, x: first.x, yDown: first.yDown)
      }.sorted { $0.value < $1.value }
      return unique
    }
    guard
      let samples = columns.max(by: { lhs, rhs in
        if lhs.count != rhs.count { return lhs.count < rhs.count }
        let leftDistance = abs((lhs.first?.x ?? 0) - normalizedArtBox.maxX)
        let rightDistance = abs((rhs.first?.x ?? 0) - normalizedArtBox.maxX)
        return leftDistance > rightDistance
      }), samples.count >= 2
    else {
      throw SurgeryAtlasProbeOverlayError.invalidCoordinateMap(
        "the right-hand DV grid labels could not be identified uniquely"
      )
    }
    return samples
  }

  private static func gridScale(from samples: [AxisSample]) throws -> CGFloat {
    var candidates: [CGFloat] = []
    for leftIndex in samples.indices {
      for rightIndex in samples.indices where rightIndex > leftIndex {
        let valueDelta = samples[rightIndex].value - samples[leftIndex].value
        guard valueDelta > 0 else { continue }
        let scale =
          (samples[rightIndex].yDown - samples[leftIndex].yDown)
          / CGFloat(valueDelta)
        if scale.isFinite, (30...90).contains(scale) {
          candidates.append(scale)
        }
      }
    }
    guard !candidates.isEmpty else {
      throw SurgeryAtlasProbeOverlayError.invalidCoordinateMap(
        "the DV grid labels do not define a reviewed millimetre scale"
      )
    }
    return median(candidates)
  }

  private static func sagittalAPZero(
    page: PDFPage,
    pageText: String,
    mediaBox: CGRect
  ) throws -> CGFloat {
    let text = pageText as NSString
    var searchRange = NSRange(location: 0, length: text.length)
    var candidates: [(x: CGFloat, yDown: CGFloat)] = []
    while searchRange.length > 0 {
      let match = text.range(of: "Bregma", range: searchRange)
      guard match.location != NSNotFound else { break }
      if let selection = page.selection(for: match) {
        let bounds = selection.bounds(for: page)
        candidates.append(
          (
            x: bounds.midX - mediaBox.minX,
            yDown: mediaBox.maxY - bounds.midY
          ))
      }
      let next = match.location + match.length
      searchRange = NSRange(location: next, length: text.length - next)
    }
    guard let topLabel = candidates.min(by: { $0.yDown < $1.yDown }) else {
      throw SurgeryAtlasProbeOverlayError.invalidCoordinateMap(
        "the sagittal AP=0 Bregma label is missing"
      )
    }
    return topLabel.x
  }

  private static func median(_ values: [CGFloat]) -> CGFloat {
    let sorted = values.sorted()
    let middle = sorted.count / 2
    if sorted.count.isMultiple(of: 2) {
      return (sorted[middle - 1] + sorted[middle]) / 2
    }
    return sorted[middle]
  }
}

struct SurgeryAtlasProbeOverlay: Equatable, Sendable {
  struct Segment: Equatable, Sendable {
    let start: CGPoint
    let end: CGPoint
  }

  struct Shank: Equatable, Identifiable, Sendable {
    let id: String
    let sourceShankId: String
    let projectedProximalEnd: CGPoint
    let projectedSurfaceAnchor: CGPoint
    let projectedTip: CGPoint
    let clippedSegments: [Segment]

    var svgPathData: String {
      guard let first = clippedSegments.first else { return "" }
      var commands =
        "M \(SVGNumber.format(first.start.x)) "
        + "\(SVGNumber.format(first.start.y)) "
        + "L \(SVGNumber.format(first.end.x)) "
        + "\(SVGNumber.format(first.end.y))"
      var previousEnd = first.end
      for segment in clippedSegments.dropFirst() {
        if pointsEqual(previousEnd, segment.start) {
          commands +=
            " L \(SVGNumber.format(segment.end.x)) "
            + "\(SVGNumber.format(segment.end.y))"
        } else {
          commands +=
            " M \(SVGNumber.format(segment.start.x)) "
            + "\(SVGNumber.format(segment.start.y)) "
            + "L \(SVGNumber.format(segment.end.x)) "
            + "\(SVGNumber.format(segment.end.y))"
        }
        previousEnd = segment.end
      }
      return commands
    }

    private func pointsEqual(_ lhs: CGPoint, _ rhs: CGPoint) -> Bool {
      abs(lhs.x - rhs.x) <= 0.0005 && abs(lhs.y - rhs.y) <= 0.0005
    }
  }

  let figure: Int
  let orientation: SurgeryAtlasOrientation
  let coordinateMap: SurgeryAtlasCoordinateMap
  let shanks: [Shank]
  let coordinateText: String
  let layoutRotationDegrees: Int
  let projectedPathsCollapse: Bool

  init(
    plan: ProbePlanDetail,
    prefill: SurgeryPlanPrefill,
    plate: SurgeryAtlasPlate,
    coordinateMap: SurgeryAtlasCoordinateMap
  ) throws {
    guard let input = plan.surfaceRelativeInput else {
      throw SurgeryAtlasProbeOverlayError.missingSurfaceRelativeInput
    }
    guard coordinateMap.orientation == plate.orientation else {
      throw SurgeryAtlasProbeOverlayError.invalidCoordinateMap(
        "the map orientation does not match Figure \(plate.figure)"
      )
    }
    guard prefill.apMillimetres == input.insertionAPMillimetres else {
      throw SurgeryAtlasProbeOverlayError.inconsistentPrefill("AP")
    }
    guard prefill.mlMillimetres == input.insertionMLMillimetres else {
      throw SurgeryAtlasProbeOverlayError.inconsistentPrefill("ML")
    }
    guard prefill.surfaceDepthMillimetres == input.surfaceDepthMillimetres else {
      throw SurgeryAtlasProbeOverlayError.inconsistentPrefill("depth")
    }
    guard prefill.sagittalAngleDegrees == input.sagittalAngleDegrees else {
      throw SurgeryAtlasProbeOverlayError.inconsistentPrefill("angle")
    }
    guard prefill.probeLayoutRotationDegrees == input.probeLayoutRotationDegrees else {
      throw SurgeryAtlasProbeOverlayError.inconsistentPrefill("layout")
    }
    let expectedShankCount: Int
    switch plan.modelId {
    case ProbePlanningContract.neuropixels2SingleShankModelId:
      expectedShankCount = 1
    case ProbePlanningContract.neuropixels2StandardFourShankModelId:
      expectedShankCount = 4
    default:
      throw SurgeryAtlasProbeOverlayError.invalidGeometry(
        "only the NP2003 one-shank and NP2013 four-shank models are supported"
      )
    }
    guard plan.shanks.count == expectedShankCount else {
      throw SurgeryAtlasProbeOverlayError.invalidGeometry(
        "\(plan.modelId) must contain exactly \(expectedShankCount) shank"
          + (expectedShankCount == 1 ? "" : "s")
      )
    }

    let bregma = input.bregmaReference
    let orderedShanks = plan.shanks.sorted(by: Self.shankOrder)
    guard Set(orderedShanks.map(\.shankId)).count == orderedShanks.count else {
      throw SurgeryAtlasProbeOverlayError.invalidGeometry(
        "source shank identifiers are not unique"
      )
    }
    let projected = try orderedShanks.enumerated().map { index, shank in
      let proximal = try Self.project(
        shank.renderedProximalEnd,
        relativeTo: bregma,
        through: coordinateMap
      )
      let surface = try Self.project(
        shank.surfaceAnchor,
        relativeTo: bregma,
        through: coordinateMap
      )
      let tip = try Self.project(
        shank.tip,
        relativeTo: bregma,
        through: coordinateMap
      )
      let segments = [
        Self.clipSegment(
          from: proximal,
          to: surface,
          within: coordinateMap.plotRect
        ),
        Self.clipSegment(
          from: surface,
          to: tip,
          within: coordinateMap.plotRect
        ),
      ].compactMap { $0 }
      guard !segments.isEmpty else {
        throw SurgeryAtlasProbeOverlayError.invalidGeometry(
          "\(shank.shankId) does not intersect the selected atlas plate"
        )
      }
      return Shank(
        id: "shank-\(index + 1)",
        sourceShankId: shank.shankId,
        projectedProximalEnd: proximal,
        projectedSurfaceAnchor: surface,
        projectedTip: tip,
        clippedSegments: segments
      )
    }

    figure = plate.figure
    orientation = plate.orientation
    self.coordinateMap = coordinateMap
    shanks = projected
    layoutRotationDegrees = input.probeLayoutRotationDegrees
    coordinateText = Self.coordinateRow(input: input)
    projectedPathsCollapse = Self.hasCollapsedPaths(projected)
  }

  var svgString: String {
    let palette = ["#FF005D", "#006CFF", "#00A86B", "#FF7A00"]
    let offsets = displayOffsets
    let pathMarkup = shanks.enumerated().map { index, shank in
      let color = palette[index % palette.count]
      let offset = offsets[index]
      let separated = abs(offset.x) > 0.0005 || abs(offset.y) > 0.0005
      let displayMode = separated ? "offset-only" : "registered"
      let accessibility =
        separated
        ? "\(shank.id), exact registered path with display-only separation"
        : "\(shank.id), exact registered path"
      return "  <path id=\"\(XML.escapeAttribute(shank.id))\" "
        + "data-source-shank-id=\"\(XML.escapeAttribute(shank.sourceShankId))\" "
        + "data-projection-display=\"\(displayMode)\" "
        + "data-display-offset-x=\"\(SVGNumber.format(offset.x))\" "
        + "data-display-offset-y=\"\(SVGNumber.format(offset.y))\" "
        + "aria-label=\"\(XML.escapeAttribute(accessibility))\" "
        + "d=\"\(XML.escapeAttribute(shank.svgPathData))\" fill=\"none\" "
        + "transform=\"translate(\(SVGNumber.format(offset.x)) "
        + "\(SVGNumber.format(offset.y)))\" "
        + "stroke=\"\(color)\" stroke-width=\"2.5\" "
        + "stroke-linecap=\"round\" stroke-linejoin=\"round\" "
        + "vector-effect=\"non-scaling-stroke\"/>"
    }.joined(separator: "\n")
    return """
      <?xml version="1.0" encoding="UTF-8"?>
      <svg xmlns="http://www.w3.org/2000/svg" width="792" height="612" viewBox="0 0 792 612" role="img" aria-label="Probe overlay">
      \(pathMarkup)
      <text id="probe-coordinates" x="396" y="552" text-anchor="middle" fill="#A80035" font-family="-apple-system, Helvetica, Arial, sans-serif" font-size="8.2" font-weight="700">\(XML.escapeText(visibleCoordinateText))</text>
      </svg>
      """
  }

  var svgData: Data {
    Data(svgString.utf8)
  }

  func makeSVGImage() throws -> NSImage {
    let coordinateWidth = (visibleCoordinateText as NSString).size(
      withAttributes: [
        .font: NSFont.systemFont(ofSize: 8.2, weight: .bold)
      ]
    ).width
    guard coordinateWidth <= 744 else {
      throw SurgeryAtlasProbeOverlayError.invalidGeometry(
        "the complete coordinate row does not fit within the SVG page"
      )
    }
    guard let image = NSImage(data: svgData),
      image.size.width > 0,
      image.size.height > 0
    else {
      throw SurgeryAtlasProbeOverlayError.svgImageUnavailable
    }
    return image
  }

  /// Draw the same serialized SVG that is exposed by `svgData`; this keeps
  /// PDF output and standalone SVG inspection on one rendering path.
  func drawSVG(in destination: CGRect, context: CGContext) throws {
    let image = try makeSVGImage()
    let graphics = NSGraphicsContext(cgContext: context, flipped: false)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = graphics
    image.draw(
      in: destination,
      from: CGRect(origin: .zero, size: image.size),
      operation: .sourceOver,
      fraction: 1,
      respectFlipped: true,
      hints: [.interpolation: NSImageInterpolation.high]
    )
    NSGraphicsContext.restoreGraphicsState()
  }

  private var visibleCoordinateText: String {
    projectedPathsCollapse
      ? coordinateText + " · coincident in view; shown spread"
      : coordinateText
  }

  /// Exact registered paths stay in each path's `d` attribute. If two or
  /// more paths are identical in this 2-D projection, the rendered copies are
  /// spread symmetrically around that shared path. Their centroid therefore
  /// remains registered, while the SVG metadata makes the display-only
  /// separation machine-readable and prevents it being mistaken for anatomy.
  private var displayOffsets: [CGPoint] {
    var result = Array(repeating: CGPoint.zero, count: shanks.count)
    let groups = Dictionary(grouping: shanks.indices) { index in
      shanks[index].svgPathData
    }
    for indices in groups.values where indices.count > 1 {
      let ordered = indices.sorted()
      guard let firstIndex = ordered.first,
        let firstSegment = shanks[firstIndex].clippedSegments.first,
        let lastSegment = shanks[firstIndex].clippedSegments.last
      else { continue }
      let dx = lastSegment.end.x - firstSegment.start.x
      let dy = lastSegment.end.y - firstSegment.start.y
      let length = hypot(dx, dy)
      let normal =
        length > 0.0005
        ? CGPoint(x: dy / length, y: -dx / length)
        : CGPoint(x: 1, y: 0)
      let center = CGFloat(ordered.count - 1) / 2
      for (position, index) in ordered.enumerated() {
        let distance = (CGFloat(position) - center) * 4.25
        result[index] = CGPoint(
          x: normal.x * distance,
          y: normal.y * distance
        )
      }
    }
    return result
  }

  private static func coordinateRow(input: AtlasSurfaceProbeInput) -> String {
    let direction: String
    if input.sagittalAngleDegrees > 0 {
      direction = "A→P"
    } else if input.sagittalAngleDegrees < 0 {
      direction = "P→A"
    } else {
      direction = "vertical"
    }
    let layout =
      input.probeLayoutRotationDegrees == 90
      ? "90° clockwise from dorsal"
      : "0° sagittal"
    return "AP \(SVGNumber.signed(input.insertionAPMillimetres, places: 3)) mm · "
      + "ML \(SVGNumber.signed(input.insertionMLMillimetres, places: 3)) mm · "
      + "depth \(SVGNumber.format(input.surfaceDepthMillimetres, places: 3)) mm · "
      + "angle \(SVGNumber.signed(input.sagittalAngleDegrees, places: 1))° "
      + "(\(direction)) · layout \(layout)"
  }

  private static func project(
    _ point: ProbePhysicalPoint,
    relativeTo bregma: AtlasBregmaReference,
    through map: SurgeryAtlasCoordinateMap
  ) throws -> CGPoint {
    let ap = (bregma.apMicrometres - point.apMicrometres) / 1_000
    let ml = (bregma.mlMicrometres - point.mlMicrometres) / 1_000
    let dv = (point.dvMicrometres - bregma.dvMicrometres) / 1_000
    guard [ap, ml, dv].allSatisfy(\.isFinite) else {
      throw SurgeryAtlasProbeOverlayError.invalidGeometry(
        "a shank endpoint is not finite in the bregma-relative frame"
      )
    }
    return map.project(
      apMillimetres: ap,
      mlMillimetres: ml,
      dvMillimetres: dv
    )
  }

  private static func shankOrder(_ lhs: ProbePlacedShank, _ rhs: ProbePlacedShank) -> Bool {
    let leftOrdinal = numericSuffix(lhs.shankId)
    let rightOrdinal = numericSuffix(rhs.shankId)
    switch (leftOrdinal, rightOrdinal) {
    case (.some(let left), .some(let right)) where left != right:
      return left < right
    default:
      return lhs.shankId < rhs.shankId
    }
  }

  private static func numericSuffix(_ identifier: String) -> Int? {
    guard let suffix = identifier.split(separator: "-").last else { return nil }
    return Int(suffix)
  }

  private static func clipSegment(
    from start: CGPoint,
    to end: CGPoint,
    within rect: CGRect
  ) -> Segment? {
    let dx = end.x - start.x
    let dy = end.y - start.y
    var lower: CGFloat = 0
    var upper: CGFloat = 1
    let edges: [(p: CGFloat, q: CGFloat)] = [
      (-dx, start.x - rect.minX),
      (dx, rect.maxX - start.x),
      (-dy, start.y - rect.minY),
      (dy, rect.maxY - start.y),
    ]
    for edge in edges {
      if abs(edge.p) <= .ulpOfOne {
        if edge.q < 0 { return nil }
        continue
      }
      let ratio = edge.q / edge.p
      if edge.p < 0 {
        if ratio > upper { return nil }
        lower = max(lower, ratio)
      } else {
        if ratio < lower { return nil }
        upper = min(upper, ratio)
      }
    }
    return Segment(
      start: CGPoint(x: start.x + lower * dx, y: start.y + lower * dy),
      end: CGPoint(x: start.x + upper * dx, y: start.y + upper * dy)
    )
  }

  private static func hasCollapsedPaths(_ shanks: [Shank]) -> Bool {
    guard shanks.count > 1 else { return false }
    let signatures = shanks.map { shank in
      shank.clippedSegments.map { segment in
        [
          SVGNumber.format(segment.start.x),
          SVGNumber.format(segment.start.y),
          SVGNumber.format(segment.end.x),
          SVGNumber.format(segment.end.y),
        ].joined(separator: ",")
      }.joined(separator: ";")
    }
    return Set(signatures).count < signatures.count
  }
}

private enum SVGNumber {
  private static let locale = Locale(identifier: "en_US_POSIX")

  static func format(_ value: CGFloat, places: Int = 3) -> String {
    format(Double(value), places: places)
  }

  static func format(_ value: Double, places: Int = 3) -> String {
    let threshold = 0.5 * pow(10, -Double(places))
    let normalized = abs(value) < threshold ? 0 : value
    return String(
      format: "%.\(places)f",
      locale: locale,
      normalized
    )
  }

  static func signed(_ value: Double, places: Int) -> String {
    let threshold = 0.5 * pow(10, -Double(places))
    let normalized = abs(value) < threshold ? 0 : value
    return String(
      format: "%+.\(places)f",
      locale: locale,
      normalized
    )
  }
}

private enum XML {
  static func escapeText(_ value: String) -> String {
    value
      .replacingOccurrences(of: "&", with: "&amp;")
      .replacingOccurrences(of: "<", with: "&lt;")
      .replacingOccurrences(of: ">", with: "&gt;")
  }

  static func escapeAttribute(_ value: String) -> String {
    escapeText(value)
      .replacingOccurrences(of: "\"", with: "&quot;")
      .replacingOccurrences(of: "'", with: "&apos;")
  }
}
