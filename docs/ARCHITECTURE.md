# Architecture

## Supported product boundary

```text
SwiftUI macOS application
  ├─ project/calibration/probe/vessel navigation
  ├─ linked coronal, sagittal, horizontal views
  ├─ inspector tables and overlays
  └─ native accessibility and file panels
                 ↕ typed NDJSON protocol
Python 3.12 scientific service
  ├─ allowlisted BrainGlobe atlas and named coordinate frames
  ├─ calibration and AP/ML/DV projection
  ├─ probe catalog, placements, sites, and region traversal
  ├─ density, 2D surface, and registered 3D vessel workflows
  ├─ provenance, hashes, stale-result rejection, and persistence
  └─ deterministic raster/scene descriptors
```

SwiftUI is the only supported GUI. The service is a separately launched subprocess so scientific
models and algorithms remain testable headlessly. Large atlas volumes, vessel graphs, images, and
spatial indexes stay in Python-owned caches; the wire carries typed state, requested rasters,
analysis tables, and bounded descriptors.

## Canonical state

Domain physical order is always named `AP, ML, DV`. BrainGlobe array order such as `AP, DV, ML`
is converted only at a centralized boundary. Every point carries a frame, units, directions,
origin, atlas identity, voxel-anchor convention, and applicable calibration/transform identity.

One canonical 3D cursor drives all orthogonal views. Probe placement, recording sites, region
traversal, vessel geometry, and collision analysis use 3D physical coordinates. Slice canvases
are projections of that state; an optional future 3D renderer is another view of the same state.

## Evidence layers

- Population vascular density is scalar reference context. It cannot produce a vessel ID or
  collision result.
- A subject dorsal image/mask is two-dimensional surface evidence. It can support entry/craniotomy
  distance after scale and registration validation, never deep clearance.
- Only a reviewed, registered 3D graph with explicit radius can support radius-aware clearance.

## Failure boundaries

Atlas identity mismatch, missing calibration, failed calibration QC, unknown coordinate frame,
unregistered vessel geometry, missing radius, subject mismatch, stale inputs, and project
revision conflicts fail closed. The product never substitutes another atlas, invents bregma,
extrudes 2D evidence, or emits “safe.”

See [ADR-005](ADR-005-independent-slice-viewer.md), [Code Audit](CODE_AUDIT.md), and
[Legacy Removal](LEGACY_REMOVAL.md).
