# Architecture

## Supported product boundary

```text
SwiftUI macOS application
  ├─ single selected Dorsal / Coronal / Sagittal / Horizontal / 3D workspace
  ├─ project, calibration, target, probe, and region controls
  ├─ lossless atlas rasters with clipped probe/reference-vessel overlays
  └─ SceneKit brain mesh, camera, ray picking, probe envelopes, and vessel tubes
                              ↕ strict typed NDJSON
Python 3.12 scientific service
  ├─ allowlisted BrainGlobe atlas and named coordinate-frame conversion
  ├─ subject calibration and QC-gated AP/ML/DV projection
  ├─ source-traceable probe catalog, placements, sites, and voxel traversal
  ├─ digest-bound VesSAP display geometry and fail-closed analysis gate
  └─ revisions, provenance, hashes, stale-result rejection, and persistence
```

SwiftUI is the only supported GUI. SceneKit is a native rendering module within that app, not a
second scientific implementation. The Python subprocess owns atlas interpretation, coordinate
conversion, calibration, geometry derivation, and analysis so they remain testable headlessly.

## View and state model

The mode bar is exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`; only one view occupies
the workspace. Coronal, sagittal, and horizontal keep independent persisted depths. Picking a
region replaces one shared compact label and never moves a slice. Complete ontology browse/search
uses the existing paged BrainGlobe region service and lazily requests only the selected mesh.
Dorsal is an AP/ML reference projection
of the atlas surface, selected probe shanks, and major vessels (not a collapsed recording-site
cloud); 3D has its own camera and ray-pick interaction while consuming the same atlas/probe/vessel
state.

There is no crosshair, focus mode, 2×2 panel state, or duplicated cursor that can silently couple
slice depths.

## Coordinate ownership

User stereotaxy is always named `[AP, ML, DV]` from bregma in millimetres: AP− posterior,
ML− left, and DV− deep/ventral. BrainGlobe continuous physical coordinates are `[AP, DV, ML]`
in micrometres. SceneKit maps backend-validated atlas geometry payloads into its display axes at
one centralized boundary. Unprojected values remain separate until a versioned subject calibration
passes QC.

Every derived object carries the relevant frame, units, directions, origin, atlas identity,
calibration identity, revision, algorithm version, and input digest. A target, probe, analysis, or
render response from stale state is rejected rather than reused.

## Geometry and analysis flow

```text
subject calibration → projected target → versioned probe placement
                                      ├─→ clipped 2D shank/site overlays
                                      ├─→ exact voxel traversal + export
                                      └─→ SceneKit probe envelope
VesSAP BL6J-no1 → pinned transform + true-path 50 µm reduction
                ├─→ five-view display geometry
                └─→ VESSEL_ANALYSIS_UNAVAILABLE (no clearance)
LAMBADA P60_606 → archived rejected evidence (no runtime payload)
```

The runtime advertises `auditedReferenceMajorVessels`, verifies the VesSAP manifest/NPZ, and
serves metadata plus binary display geometry. It does not advertise
`radiusAwareReferenceVesselAnalysis`; `vessel.major.reference.analyze` fails before project
access. The UI cannot manufacture a clearance result from displayed geometry or pixels.

## Evidence boundary

The VesSAP diameter-≥30 µm layer is one cleared C57BL/6J reference. Its transform interpretation,
laterality, topology, bounds, and asset identity have display evidence, but subject registration,
clearing/inter-animal variation, and a qualified transformed vessel surface remain unbounded.
See [the VesSAP derivation record](VESSAP_MAJOR_VESSELS.md).

The P60_606 diameter-≥30 µm derivative remains archived evidence, not a primary vessel layer. Its AP
and DV orientation evidence passed, but the source is a hemisphere specimen and the exact graph
has no persisted biological hemisphere/laterality binding. Whole-brain coverage and ML polarity
are unqualified; no mirroring is permitted. The digest-bound canonical rejection report is
[`lambada_p60_606_coordinate_qualification_rejected_v1.json`](evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.

Population density and subject-image registration remain separate archived compatibility code and
persisted data. Their methods/capabilities are not registered by the primary bridge, they remain
outside the planning UI, and neither may be substituted for individual vessel paths.

Probe-region CSV/JSON export is provenance-complete: every artifact carries the atlas
identity/version/digest, printed coordinate convention, calibration identity/version/digest,
source/destination frames, and the full AP/ML/DV transform matrix plus residuals. Generation is
read-only; an audit mutation occurs only after the native atomic write is confirmed.

## Failure boundaries

Atlas identity mismatch, failed calibration QC, unknown coordinate frames, source/asset digest
mismatch, a missing or changed manifest/qualification report, malformed geometry, stale project
or plan hashes, and missing user acknowledgements fail closed. The app does not substitute another
atlas, invent bregma, extrude a 2D density field into vessels, infer hemisphere, mirror P60_606,
or treat either fixed reference as a subject measurement.

See [ADR-004](ADR-004-swiftui-hybrid-shell.md),
[ADR-005](ADR-005-independent-slice-viewer.md), and
[the Pinpoint interoperability decision](PINPOINT_INTEGRATION.md),
[the VesSAP derivation record](VESSAP_MAJOR_VESSELS.md), and
[the LAMBADA derivation record](LAMBADA_MAJOR_VESSELS.md).
