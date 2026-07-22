# ADR-005: Independent Slice Viewer Before Optional 3D

- Status: accepted
- Date: 2026-07-22

## Context

The intended product must project calibrated AP/ML/DV targets, place Neuropixels geometry, report
atlas-region traversal, and compare probe envelopes with explicitly registered vessel geometry.
The early SwiftUI application showed only midpoint rasters and an unavailable 3D card. An older
Qt/PyVista application contained unrelated interaction/rendering state and is not the supported
product.

Coordinate order, laterality, voxel anchoring, calibration, probe geometry, and clearance can be
verified more directly in orthogonal slices than in an early 3D presentation layer. A 3D renderer
must not acquire a second copy of scientific state or collision logic.

## Options

1. Revive the Qt/PyVista application and maintain it beside SwiftUI.
2. Implement native/Web 3D first, then add slice navigation later.
3. Keep SwiftUI and the Python bridge, implement independent coronal, sagittal, and horizontal
   depths with a separate region selection, and add a renderer over the same analysis state later.

## Decision

Choose option 3.

- SwiftUI is the only supported GUI.
- Python owns atlas access, coordinate transformations, calibration, probe/vessel analysis,
  provenance, and project persistence.
- One full-size selected slice is the MVP presentation; the three depths are independent and
  persisted because switching or clicking another view must not move hidden planes.
- Region selection is separate from depth state. A click replaces one compact label and never
  changes a slice.
- All analysis remains three-dimensional even though the MVP display is two-dimensional.
- Optional 3D is Phase 8 and consumes the same persisted depths, selection, placements, vessel
  graph, and analysis results. It may not implement independent coordinate or collision logic.

## Consequences

- Arbitrary slice navigation, orientation labels, and point/region lookup become the first usable
  interaction milestone.
- Qt, PyVista, PyVistaQt, and VTK can leave the default runtime dependency set.
- Existing `atlas.slice` and `atlas.point` functionality can be reused rather than replaced.
- Mesh/tube presentation does not block calibrated planning and region traversal.
- The project must add Swift application/ViewModel tests; core transport tests alone are not
  enough.
- 3D remains visibly unavailable until a separate renderer ADR and validation gate are complete.

## Rollback strategy

The viewer-state protocol, project schema, and Python analyses are renderer-independent. If
SwiftUI proves unsuitable, another macOS presentation layer can consume the same typed bridge and
scene descriptors. Reintroducing the old Qt application as a co-equal product is not a rollback;
it would recreate the duplicated-state problem and requires a new ADR.
