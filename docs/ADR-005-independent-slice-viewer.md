# ADR-005: Independent Slice Viewer Before Optional 3D

- Status: accepted
- Date: 2026-07-22

## Implementation update — 2026-07-22

The independent-slice decision remains in force. Its later renderer gate is now satisfied: a
SceneKit module consumes schema-checked atlas, probe, and ray-pick payloads from the backend. The
current product path therefore implements all five single-view modes without reintroducing a
linked cursor, crosshair, focus mode, or 2×2 layout. P60_606 vessel state remains excluded
because its coordinate/coverage qualification is rejected; the later qualified-for-display
VesSAP reference is rendered and still provides no clearance result. One selected Allen region
now drives descendant annotation highlights in all four 2D modes and its reviewed mesh highlight
in 3D. An ontology entry with neither annotation voxels nor a reviewed mesh remains selected and
shows an explicit no-geometry state instead of fabricated anatomy.

## Context

The current product must resolve source-pinned AP/ML as user-facing Shank 1's local
annotation-surface crossing, place NP2003/NP2013 geometry from that anchor and distal depth
target, and report atlas-region traversal over the implanted surface-to-tip path. The original
design also proposed
comparing probe envelopes with explicitly registered vessel geometry; that analysis is not a
current capability because no subject-specific vessel source passed qualification. The early
SwiftUI application showed only midpoint rasters and an unavailable 3D card. An older
Qt/PyVista application contained unrelated
interaction/rendering state and is not the supported product.

Coordinate order, laterality, voxel anchoring, and probe geometry can be verified more directly in
orthogonal slices than in an early 3D presentation layer. A 3D renderer must not acquire a second
copy of scientific state or collision logic. Rendering cannot substitute for source
qualification or create a vessel-clearance result.

## Options

1. Revive the Qt/PyVista application and maintain it beside SwiftUI.
2. Implement native/Web 3D first, then add slice navigation later.
3. Keep SwiftUI and the Python bridge, implement independent coronal, sagittal, and horizontal
   depths with a separate region selection, and add a renderer over the same analysis state later.

## Decision

Choose option 3.

- SwiftUI is the only supported GUI.
- Python owns atlas access, coordinate transformations, calibration, probe/region analysis,
  vessel qualification, provenance, and project persistence.
- One full-size selected slice is the MVP presentation; the three depths are independent and
  persisted because switching or clicking another view must not move hidden planes.
- Region selection is separate from depth state. A click replaces one compact label and never
  changes a slice.
- All analysis remains three-dimensional even though the MVP display is two-dimensional.
- Optional 3D is Phase 8 and consumes the same persisted depths, selection, and placements. It may
  not implement independent coordinate or collision logic or ingest archived vessel files.

## Consequences

- Arbitrary slice navigation, orientation labels, and point/region lookup become the first usable
  interaction milestone.
- Qt, PyVista, PyVistaQt, and VTK can leave the default runtime dependency set.
- Existing `atlas.slice` and `atlas.point` functionality can be reused rather than replaced.
- Mesh presentation does not block calibrated planning and region traversal. Historical vessel-
  tube rendering code is not a product capability.
- The project must add Swift application/ViewModel tests; core transport tests alone are not
  enough.
- 3D remained unavailable during the slice-first milestone; the current SceneKit implementation
  is the renderer added after that gate.

## Rollback strategy

The viewer-state protocol, project schema, and Python analyses are renderer-independent. If
SwiftUI proves unsuitable, another macOS presentation layer can consume the same typed bridge and
scene descriptors. Reintroducing the old Qt application as a co-equal product is not a rollback;
it would recreate the duplicated-state problem and requires a new ADR.
