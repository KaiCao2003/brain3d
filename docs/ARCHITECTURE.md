# Architecture

## Supported product boundary

```text
SwiftUI macOS application
  ├─ single selected Dorsal / Coronal / Sagittal / Horizontal / 3D workspace
  ├─ project, calibration, target, probe, region, and vessel controls
  ├─ lossless atlas rasters with clipped probe/vessel overlays
  └─ SceneKit brain mesh, camera, ray picking, probe envelopes, and vessel tubes
                              ↕ strict typed NDJSON
Python 3.12 scientific service
  ├─ allowlisted BrainGlobe atlas and named coordinate-frame conversion
  ├─ subject calibration and QC-gated AP/ML/DV projection
  ├─ source-traceable probe catalog, placements, sites, and voxel traversal
  ├─ integrity-checked LAMBADA geometry and tapered-radius vessel analysis
  └─ revisions, provenance, hashes, stale-result rejection, and persistence
```

SwiftUI is the only supported GUI. SceneKit is a native rendering module within that app, not a
second scientific implementation. The Python subprocess owns atlas interpretation, coordinate
conversion, calibration, geometry derivation, and analysis so they remain testable headlessly.

## View and state model

The mode bar is exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`; only one view occupies
the workspace. Coronal, sagittal, and horizontal keep independent persisted depths. Picking a
region replaces one compact label and never moves a slice. Dorsal is a reference projection;
3D has its own camera and ray-pick interaction while consuming the same atlas/probe/vessel state.

There is no crosshair, focus mode, 2×2 panel state, or duplicated cursor that can silently couple
slice depths.

## Coordinate ownership

User stereotaxy is always named `[AP, ML, DV]` from bregma in millimetres: AP− posterior,
ML− left, and DV− deep/ventral. BrainGlobe continuous physical coordinates are `[AP, DV, ML]`
in micrometres. SceneKit maps verified atlas geometry into its display axes at one centralized
boundary. Unprojected values remain separate until a versioned subject calibration passes QC.

Every derived object carries the relevant frame, units, directions, origin, atlas identity,
calibration identity, revision, algorithm version, and input digest. A target, probe, analysis, or
render response from stale state is rejected rather than reused.

## Geometry and analysis flow

```text
subject calibration → projected target → versioned probe placement
                                      ├─→ clipped 2D shank/site overlays
                                      ├─→ exact voxel traversal + export
                                      ├─→ SceneKit probe envelope
LAMBADA P60 major-vessel graph ─────├─→ 2D / Dorsal / 3D overlays
                                      └─→ V2 tapered-surface analysis
```

The vessel bridge sends bounded, typed, little-endian geometry buffers with declared hashes.
Swift validates and renders the resulting runs and radii. Python performs the authoritative V2
probe-envelope-to-tapered-vessel-surface calculation, including required margin and registration
uncertainty. The UI cannot manufacture a conflict result from rendered pixels.

## Evidence boundary

The primary vessel layer is the LAMBADA P60_606 reference filtered to point radius ≥15 µm
(diameter ≥30 µm). It is a fixed cleared reference, not subject-specific evidence, and its source
omits pial and choroidal vessels. Population density and subject-image registration are archived
backend capabilities and remain outside the primary planning UI.

The only bounded zero-conflict statement is:

> No conflict detected within the loaded geometry and stated uncertainty assumptions.

## Failure boundaries

Atlas identity mismatch, failed calibration QC, unknown coordinate frames, source/asset digest
mismatch, malformed geometry, stale project or plan hashes, and missing user acknowledgements fail
closed. The app does not substitute another atlas, invent bregma, extrude a 2D density field into
vessels, or treat the reference graph as a subject measurement.

See [ADR-004](ADR-004-swiftui-hybrid-shell.md),
[ADR-005](ADR-005-independent-slice-viewer.md), and
[the LAMBADA derivation record](LAMBADA_MAJOR_VESSELS.md).
