# Architecture

## Supported product boundary

```text
SwiftUI macOS application
  ├─ single selected Dorsal / Coronal / Sagittal / Horizontal / 3D workspace
  ├─ project, direct AP/ML/surface-depth/angle/layout probe controls, and region controls
  ├─ lossless atlas rasters with region, probe, and reference-vessel overlays
  └─ SceneKit brain mesh, camera, ray picking, probe envelopes, and vessel tubes
                              ↕ strict typed NDJSON
Python 3.12 scientific service
  ├─ allowlisted BrainGlobe atlas and named coordinate-frame conversion
  ├─ source-pinned Pinpoint/Urchin AP/ML reference and exact annotation-surface resolution
  ├─ source-traceable probe catalog, placements, sites, and voxel traversal
  ├─ digest-bound VesSAP display geometry and fail-closed analysis gate
  └─ revisions, provenance, hashes, stale-result rejection, and persistence
```

SwiftUI is the only supported GUI. SceneKit is a native rendering module within that app, not a
second scientific implementation. The Python subprocess owns atlas interpretation, coordinate
conversion, surface resolution, geometry derivation, and analysis so they remain testable
headlessly. Legacy subject calibration remains a preserved backend model for v1–v3 records, not
a prerequisite in the primary v4 card.

## View and state model

The mode bar is exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`; only one view occupies
the workspace. Coronal, sagittal, and horizontal keep independent persisted depths. Picking a
region replaces one shared compact label and never moves a slice. Complete ontology browse/search
uses the existing paged BrainGlobe region service. The backend derives a descendant-inclusive
annotation mask for Dorsal, Coronal, Sagittal, and Horizontal and lazily requests the same
selected structure's mesh for 3D. The shared selection persists across mode changes even when an
ontology-only entry has neither annotation voxels nor a mesh; 2D then has zero selected pixels and
3D presents an explicit no-reviewed-geometry state.

Dorsal is an AP/ML reference projection of the atlas surface, selected probe shanks, selected
region, and major vessels (not a collapsed recording-site cloud); 3D has its own camera and
ray-pick interaction while consuming the same atlas/probe/selection/vessel state.

There is no crosshair, focus mode, 2×2 panel state, or duplicated cursor that can silently couple
slice depths.

## Coordinate ownership

The primary v4 input names the surface insertion AP and ML in millimetres from a source-pinned
Pinpoint/Urchin profile: AP+ anterior, AP− posterior, ML+ right, and ML− left. The resolved
superior boundary of the first annotated voxel is user-facing Shank 1's surface crossing, not an
array midpoint or an internal target. Depth is the positive path length from that crossing to
Shank 1's distal target. The only insertion angle is sagittal: positive advances A→P and negative
advances P→A. Layout `0°` makes Shank 1 most anterior and extends the other NP2013 shanks
posterior; `90°` rotates clockwise from dorsal, making Shank 1 animal-left-most and extending the
other shanks toward animal right.

SceneKit renders each complete 10 mm NP2 shaft from its proximal end to distal tip. At requested
depth `d`, the `10 − d` mm proximal remainder can extend outside the brain. Slice overlays,
annotation traversal, export, and path analysis use the separate implanted surface-to-tip segment
and do not count that external remainder as tissue traversal.

BrainGlobe continuous physical coordinates are `[AP, DV, ML]` in micrometres. SceneKit maps
backend-validated atlas geometry payloads into its display axes at one centralized boundary. The
Pinpoint/Urchin profile is explicitly not an Allen-official bregma or individual-animal
registration.

Every derived object carries the relevant frame, units, directions, origin, atlas identity,
annotation/reference provenance, revision, algorithm version, and input digest. Legacy records
also retain calibration identity. A probe, analysis, or render response from stale state is
rejected rather than reused.

## Geometry and analysis flow

```text
Pinpoint/Urchin AP/ML reference + loaded annotation
  → Shank 1 exact local superior surface → depth + signed sagittal angle + layout
                                         ├─→ implanted surface-to-tip 2D overlays
                                         ├─→ implanted voxel traversal + export
                                         └─→ full 10 mm SceneKit probe shafts
selected Allen ontology identity
  → descendant annotation mask ─→ Dorsal/Coronal/Sagittal/Horizontal highlight
  └─→ reviewed mesh or explicit no-geometry result ─→ SceneKit 3D
external VesSAP BL6J-no1 → manifest + digest validation
                           ├─→ five-view display geometry
                           └─→ VESSEL_ANALYSIS_UNAVAILABLE (no clearance)
```

When the external files are installed, the runtime advertises
`auditedReferenceMajorVessels`, verifies the VesSAP manifest/NPZ, and serves metadata plus
binary display geometry. It does not advertise
`radiusAwareReferenceVesselAnalysis`; `vessel.major.reference.analyze` fails before project
access. The UI cannot manufacture a clearance result from displayed geometry or pixels.

## Evidence boundary

The VesSAP diameter-≥30 µm layer is one cleared C57BL/6J reference. Its transform interpretation,
laterality, topology, bounds, and asset identity have display evidence, but subject registration,
clearing/inter-animal variation, and a qualified transformed vessel surface remain unbounded.
See [the VesSAP derivation record](VESSAP_MAJOR_VESSELS.md).


Population density and subject-image registration remain separate archived compatibility code and
persisted data. Their methods/capabilities are not registered by the primary bridge, they remain
outside the planning UI, and neither may be substituted for individual vessel paths.

Probe-region CSV/JSON export is provenance-complete. V4 artifacts carry atlas and annotation
identity/digests, the named Pinpoint/Urchin reference, printed AP/ML/surface-depth/angle/layout
conventions, and source/destination frames. Legacy artifacts retain their calibration
identity/version/digest and transform fields. Generation is read-only; an audit mutation occurs
only after the native atomic write is confirmed.

## Failure boundaries

Atlas identity mismatch, changed bregma/annotation source evidence, failed v4 surface
rederivation, failed legacy calibration QC, unknown coordinate frames, source/asset digest
mismatch, a missing or changed external manifest, malformed geometry, and stale
project or plan hashes fail closed. The app does not substitute another atlas, present the
Pinpoint/Urchin convention as Allen ground truth, extrude a 2D density field into vessels, infer anatomy from missing external data, or treat a fixed reference as a subject measurement.

See [ADR-004](ADR-004-swiftui-hybrid-shell.md),
[ADR-005](ADR-005-independent-slice-viewer.md), and
[the Pinpoint interoperability decision](PINPOINT_INTEGRATION.md), and
[the VesSAP data contract](VESSAP_MAJOR_VESSELS.md).
