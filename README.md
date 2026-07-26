# Brain3D

Brain3D is a macOS research planner for mouse stereotaxy and Neuropixels placement. The current
development tree provides one native, single-view workspace with exactly five modes:
**Dorsal / Coronal / Sagittal / Horizontal / 3D**.

> **Animal research only — non-human and non-clinical.** Brain3D is an engineering testing build,
> not a qualified surgical-navigation or veterinary device. Its atlas reference, coordinates,
> and probe outputs require independent review before an animal procedure. The current build displays a
> population-reference major-vessel layer, but exposes no vessel-clearance or safety result.

The repository is public at [KaiCao2003/brain3d](https://github.com/KaiCao2003/brain3d).
Published source is available for review, but the current tree is not an installable production
release or a validation claim.

## Implemented workflow

| Capability | Current development behavior |
| --- | --- |
| Atlas | BrainGlobe `allen_mouse_25um` package `1.2` only; 10 µm is excluded from this testing phase |
| Slice navigation | One full-size coronal, sagittal, or horizontal view; each retains an independent depth with buttons, an editable one-based slice number, slider, wheel, pan, and zoom; the header labels its atlas-native physical coordinate |
| Region inspection | Complete 840-structure Allen ontology search/browse; one shared selection drives descendant-aware 2D/3D highlighting without changing slice depth; ontology-only entries with no reviewed voxels or mesh remain selected with an explicit no-geometry message |
| Dorsal | Atlas surface with the selected probe's AP/ML entry and shank projection plus display-only major vessels |
| 3D | Native SceneKit brain mesh with camera control, atlas-region picking/highlight, probes, and major-vessel tubes |
| Direct implant definition | AP and ML locate user-facing Shank 1 at an exact local annotation-surface crossing; depth runs from that crossing to its distal target; one signed sagittal angle and one layout orientation |
| Probes | The primary selector contains only `NP2003` (1 shank) and `NP2013` (4 shanks); exact source-pinned model snapshots; automatic committed edits and slice/3D overlays |
| Vessels | VesSAP BL6J-no1 diameter-≥30 µm display reference overlaid in all five views; no capillary layer |
| Surgery plan | Prefilled two-page protocol + selectable Dorsal/Coronal/Sagittal/Horizontal/3D planning pages + one full historical page with an in-memory vector probe/coordinate overlay |
| Reference analysis | Unavailable: clearance calls fail closed with `VESSEL_ANALYSIS_UNAVAILABLE`; geometry remains display-only |
| Persistence | Schema-9 checksummed `.mouseplan` packages with revisions, provenance, migrations, backup recovery, v4 surface rederivation, and probe/model reprojection checks; legacy v1–v3 records remain preserved |

Population vascular density and subject-image registration remain archived compatibility code and
persisted data only. Their methods and capabilities are not registered by the primary bridge, they
are absent from the planning UI, and they are not substituted for vessel paths. There is no focus
mode, crosshair, 2×2 layout, or capillary layer.

## Coordinate contract

The primary implant controls are the surface insertion AP/ML, surface-relative depth, insertion
angle, and probe layout. The card labels the axes `AP (+A / −P)` and `ML (+R / −L)`. AP and ML
locate the insertion site on the atlas surface in millimetres from the explicitly named
Pinpoint/Urchin profile:

| Axis | Positive | Negative |
| --- | --- | --- |
| AP | anterior / forward | posterior / back |
| ML | right | left |

For example, `AP -1.25`, `ML -0.70` means 1.25 mm posterior and 0.70 mm left. Brain3D resolves
that AP/ML column in the loaded 25 µm annotation and uses the superior boundary of its first
non-background voxel as the surface crossing for user-facing **Shank 1** (catalog ID `shank-0`).
The AP/ML values are therefore neither an array-centre coordinate nor a point inside the brain.
**Depth (mm)** is positive path length from that Shank 1 surface crossing to its distal target—not
a DV coordinate and not a distance from the atlas box. Angle `0°` inserts inward; a positive angle
advances from anterior toward posterior (A→P), while a negative angle advances from posterior
toward anterior (P→A).

For NP2013, `Sagittal` keeps the four-shank plane parallel to the sagittal plane and makes Shank 1
the most anterior shank; the other three extend posterior at 250 µm pitch. `90° CW` rotates the
whole array clockwise as viewed dorsally and makes Shank 1 animal-left-most; the other three extend
toward animal right. In 3D, each NP2 shank is the complete catalogued 10 mm shaft from proximal end
to distal tip. At depth `d`, the remaining `10 − d` mm extends proximally from the surface, normally
outside the brain. Slice overlays, atlas-region traversal, and any path analysis retain the
surface-to-tip implanted segment rather than treating that external remainder as inserted tissue.

The named reference is pinned to a specific Virtual Brain Lab Urchin/Pinpoint source revision
and stored with its source digest. It is a Pinpoint planning convention for the population
atlas, **not** an Allen-supplied official bregma and not a registration to the individual mouse.
BrainGlobe arrays still use `[AP, DV, ML]` in micrometres, and the coordinate shown above a slice
remains an atlas-native physical coordinate. See
[Coordinate conventions](docs/ADR-002-coordinate-conventions.md).

On Dorsal, Coronal, and Horizontal atlas images, animal right is the screen-left edge and animal
left is the screen-right edge. Therefore a negative ML input appears on the screen-right,
`L`-labelled side; a negative AP input moves toward the `P`-labelled edge.

New v4 probe creation does not require a separately registered target, a subject calibration, or
a per-plan geometry checkbox. The exact built-in source snapshots and their review-pending
provenance remain visible and validation remains fail-closed; removing the checkbox does not
promote either transcription to independently verified hardware geometry. Older project packages
may retain archived v1–v3 target/calibration and multi-angle records. Brain3D preserves those
records and their original semantics, but does not expose them as primary new-plan controls.

There is no probe Apply/Create button. NP2003/NP2013 and the sagittal/90° layout are atomic
choices and update immediately. AP, ML, surface depth, and angle update on Return or when the
numeric field loses focus, so typing `90` cannot submit the intermediate `9`. Mutations are
serialized and coalesced to the newest committed edit; the views and PDF never claim an
unfinished keystroke as operative geometry.

A partially typed or invalid numeric value remains an editor draft and does not replace the
last valid plan. Opening another project, reconnecting, quitting, saving, or exporting is guarded
while such text remains unresolved, so it cannot be mistaken for the displayed trajectory.

There is one main planning window, and its probe draft is owned by the app-level planner model
rather than by the sidebar view. Closing that window does not quit the app or clear a draft;
reopening the same project/plan context restores the same typed values. A real project, plan, or
saved plan-input change synchronizes the draft only after the dirty-state guard has been
resolved.

On project validation, Brain3D re-resolves a v4 entry against the loaded annotation and
reconstructs its AP/ML, surface, depth, signed angle, layout, and probe geometry. It also keeps
the legacy validator: Brain3D fully reconstructs planning-algorithm v2/v3 placements from the
preserved mode, entry (when applicable), angles, depth, roll, probe model, source target, and
calibration, then compares every physical geometry field. It therefore rejects translated or
same-target alternate-angle geometry even if its record hash is recomputed. Historical v1
records lack sufficient preserved inputs for this reconstruction: they remain loadable for
review only and cannot enter 2D/3D planning overlays, PDF planning pages, or region analysis
until updated. Vessel-clearance analysis remains unavailable for every plan version. Persistence
schema 9 adds the optional calibration-free v4 representation; migration preserves v1–v3 records
without guessing or silently rewriting their scientific geometry.

## Probe geometry boundary

The primary selector intentionally contains only the two requested Neuropixels 2.0 choices:

- single shank, 1,280 sites (`NP2003`);
- standard four shanks at 250 µm pitch, 5,120 sites and 384 simultaneous channels
  (`NP2013`).

`NP2004` and `NP2014` remain cited where the pinned source artifacts group equivalent physical
geometries, but they are not separate UI choices. Quad Base, Neuropixels 1.0, and the synthetic
fixture remain archived in code for old-project compatibility and test evidence. Exact
manufacturer, user-manual, electrode-mapping, ProbeTable, and SpikeGLX snapshots and SHA-256
digests are recorded.

When a project is validated, a catalog-owned model snapshot must equal its source-pinned
definition field for field. This includes identity/version, verification and provenance,
shank dimensions and offsets, tip geometry, and the complete ordered recording-site table; a
recomputed plan hash cannot legitimize a modified width, site, or source record. Unknown custom
identities are retained only on the historical v1 audit path and cannot enter current planning
geometry or analysis.

Both selectable models remain deliberately **`source-transcribed-review-pending`**. No independent
human has reviewed every encoded coordinate against the cited sources or physical probes. The
direct v4 path does not add a geometry checkbox and never presents the models as independently
verified geometry. See [Probe Models](PROBE_MODELS.md).

## Major-vessel reference boundary

The visible layer is a reproducible derivative of the public VesSAP `BL6J-no1` whole-brain
3 µm skeleton and radius volumes from Todorov et al.,
[Nature Methods 2020](https://doi.org/10.1038/s41592-020-0792-1), CC BY-NC 4.0. It retains
source radius ≥15 µm (nominal diameter ≥30 µm), preserves only true 26-neighbour source-skeleton
adjacency, applies the authors' Euler + B-spline Allen transform with an independently checked ML
reflection, and reduces paths on a 50 µm display grid. The pinned asset contains 196,377 points,
76,622 runs, and 119,755 segments.

The backend advertises `auditedReferenceMajorVessels` and serves digest-checked geometry.
Swift overlays it on Dorsal, Coronal, Sagittal, Horizontal, and 3D. The backend deliberately does
not advertise `radiusAwareReferenceVesselAnalysis`: `vessel.major.reference.analyze` returns
`VESSEL_ANALYSIS_UNAVAILABLE` before reading or mutating project state.

This is one cleared ex-vivo C57BL/6J reference, not the operative animal. Capillaries are omitted;
artery/vein identity is unavailable; the nonlinear transform is anisotropic; and no numeric
subject-registration, clearing-distortion, or inter-animal error bound is published. The layer
cannot establish clearance, vessel absence, trajectory suitability, or safety.

The older LAMBADA P60_606 derivative remains archived and rejected: its hemisphere/laterality
binding and whole-brain coverage are not qualified, so it is never served or mirrored. See
[VesSAP Major Vessels](docs/VESSAP_MAJOR_VESSELS.md),
[LAMBADA Major Vessels](docs/LAMBADA_MAJOR_VESSELS.md), and
[Known Limitations](KNOWN_LIMITATIONS.md).

## Surgery-plan PDF

**Export PDF…** fills pages 1–2 of the supplied Headplate Protocol from the selected animal
plan, renders either one plan-centred view or all five views with the current probe and VesSAP
layer, and appends one coordinate-matched page from the user-owned 132-page
`MBSC_Figs_with_Layers.pdf`. The final atlas page is chosen by AP for coronal plates or `|ML|`
for sagittal plates; the signed left/right ML value remains explicit in the planning pages. The
source template's third-page sketch is a placeholder and is replaced, not emitted.

Set the prepared Headplate protocol PDF once in **Brain3D → Settings**. A lab-local build may
include the exact reviewed `MBSC_Figs_with_Layers.pdf` inside the app; Brain3D verifies its pinned
SHA-256 and 132-page identity and uses it automatically. Builds without that user-supplied resource
retain the saved atlas-location fallback in Settings. The
implementation reads both PDFs directly, uses SceneKit for the 3D snapshot, and uses
PDFKit/Core Graphics for overlays, assembly, and verification. It does not open Word,
Illustrator, or another converter. Neither supplied PDF is copied into this public repository.
The historical page remains full-size without cropping or rescaling after its nonzero `MediaBox`
origin is normalized exactly once. A transparent in-memory SVG/vector layer adds exactly one
visible shaft path for NP2003 or four for NP2013, clipped only at the historical page's plot
bounds, plus one row containing AP, ML, depth, signed angle, and layout. If multiple shanks
coincide in the selected 2D projection, their exact registered paths remain unchanged while the
visible copies are symmetrically spread and the coordinate row says so. The SVG uses the full
`792×612` viewBox and the export is covered by DOM, raster, and real-PDF regression checks. Project
state, source digests, and internal audit identities are PDF
metadata only—no document-state label or machine-audit footer is rendered.
Each v4 planning page puts the complete AP/ML/local-surface-depth text on its own fixed coordinate
line, separate from the bounded subject/plan identity, and prints the signed A↔P angle and layout.
Brain3D verifies that full coordinate text and the expected view title on the rendered page and
again in the ordered final packet. V4 export does not require a separate target projection or
subject calibration.
See
[Surgery-plan export](docs/SURGERY_PLAN_EXPORT.md).

## Architecture

```text
SwiftUI macOS application
  ├─ one selected Dorsal / Coronal / Sagittal / Horizontal / 3D workspace
  ├─ native controls, file panels, accessibility, and 2D overlays
  └─ SceneKit brain/probe/reference-vessel rendering and camera interaction
                         ↕ strict typed NDJSON
Python 3.12 scientific service
  ├─ pinned BrainGlobe atlas access and coordinate transforms
  ├─ annotation-surface resolution, probe geometry, vessel geometry, and voxel traversal
  └─ provenance, integrity checks, qualification gates, stale-result rejection, and persistence
```

Swift owns presentation. Python owns scientific coordinate conversion and analysis. Both paths
reject stale revisions and mismatched source identities. See [Architecture](docs/ARCHITECTURE.md)
and [ADR-004](docs/ADR-004-swiftui-hybrid-shell.md).

Viewer-only slice and region-pick mutations validate their bounded viewer state and preserve the
already validated surgery-plan graph, so moving a slice does not reconstruct every trajectory.
Project create/open/save, probe mutation, analysis, and PDF export retain the full
semantic-validation boundary. Legacy calibration mutation remains isolated to preserved v1–v3
records.

Pinpoint is the workflow reference, not an embedded state engine. Its hosted WebGL build does not
expose a supported bidirectional contract for probe identity, coordinates, atlas/camera state, or
the VesSAP overlay. Brain3D therefore uses its existing full BrainGlobe/Allen service instead of
copying or embedding an unsynchronized Unity canvas. See
[Pinpoint interoperability](docs/PINPOINT_INTEGRATION.md).

## Developer quick start

Requirements: Apple Silicon Mac, macOS 14 or later, Python 3.12, Swift, and
[uv](https://docs.astral.sh/uv/).

```bash
uv python install 3.12
uv sync --frozen --group dev
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The development app discovers the repository `.venv` and Python bridge. If discovery fails, it
reports the failure instead of substituting demo anatomy. The Allen 25 µm reference and annotation
arrays require about 0.43 GiB before rendering overhead.

Useful commands:

```bash
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner validate-project /absolute/path/Plan.mouseplan
```

Development checks:

```bash
uv lock --check
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
uv run --frozen pytest -q
swift test --package-path native/Brain3D --no-parallel
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
```

`build-app.sh` creates an ad-hoc-signed development bundle that depends on the source checkout.

## Standalone Apple Silicon release

Build the distributable app on an Apple Silicon Mac:

```bash
native/Brain3D/Scripts/build-release-app.sh
```

The release builder uses the locked production dependency graph, exact uv-managed CPython
3.12.12, and pinned PyInstaller 6.21.0. It emits
`native/Brain3D/dist/Brain3D.app` plus `Brain3D-macOS-arm64.zip`; the zip contains exactly one
top-level `Brain3D.app`. Set `OUTPUT_DIR=/absolute/path` to select another output directory.

The frozen bridge lives at
`Brain3D.app/Contents/Resources/Bridge/brain3d-bridge`. The app prefers that verified bundled
executable over repository discovery. The builder hard-fails if any Mach-O is not arm64-only,
requires newer than macOS 14.0, uses a host-only Homebrew/Xcode/local dependency or runpath, or if
a symlink leaves the app. It then unzips the archive, denies the source checkout to both processes,
performs a bridge `hello`, launches the real Swift app, observes that exact bundled bridge child,
and verifies both processes remain alive before controlled shutdown. The release environment
contains no test/lint/type-check dependencies, and the bundle includes its production CycloneDX
SBOM, exact dependency notices, and build provenance under `Contents/Resources/Release`.

If a `Developer ID Application` identity is available, the builder uses it for PyInstaller and
the outer app with the hardened runtime; otherwise it uses ad-hoc signing. Ad-hoc output is useful
for local qualification but is not notarized and should not be presented as a normal Gatekeeper-
ready download. Notarization and testing on a separate clean macOS 14 Apple Silicon machine remain
release-operator gates.

The public app contains code and the display-only VesSAP derivative, but not the Allen atlas,
user protocol PDF, Mouse Brain atlas PDF, extracted atlas pages, or rendered atlas artwork. Allen
data is still downloaded to the user's application cache when requested. An authorized lab-local
build can set
`BRAIN3D_LOCAL_LAB_BUILD=1` together with `BRAIN3D_MBSC_PDF` to include the exact reviewed Mouse
Brain PDF; that local artifact must not be uploaded or
redistributed without permission from the source owner. Public distribution must preserve the
bundled notices and the VesSAP CC BY-NC 4.0 noncommercial terms.

## Repository map

```text
native/Brain3D/                 SwiftUI + SceneKit application and native tests
src/mouse_brain_planner/
  atlas/                        pinned BrainGlobe access boundary
  bridge/                       typed service used by the native app
  coordinates/                 named coordinate frames and transforms
  probes/                       source-traceable probe catalog
  analysis/                     region traversal plus archived vessel-analysis code
  vasculature/                  display-only VesSAP geometry plus archived evidence paths
  persistence/                  checksummed project packages and migrations
tests/                          Python software tests and fixtures
docs/                           architecture, decisions, audits, and source records
```

## Documentation

- [Project Status](PROJECT_STATUS.md)
- [User Guide](USER_GUIDE.md)
- [Known Limitations](KNOWN_LIMITATIONS.md)
- [Scientific Validation](SCIENTIFIC_VALIDATION.md)
- [Probe Models](PROBE_MODELS.md)
- [VesSAP Major Vessels](docs/VESSAP_MAJOR_VESSELS.md)
- [Surgery-plan export](docs/SURGERY_PLAN_EXPORT.md)
- [Pinpoint interoperability](docs/PINPOINT_INTEGRATION.md)
- [LAMBADA Major Vessels](docs/LAMBADA_MAJOR_VESSELS.md)
- [Third-Party Software and Data](THIRD_PARTY.md)
- [Installation](INSTALL.md)

## License

This public repository is **not open source**. Original source code remains all rights reserved
under [LICENSE](LICENSE). Atlas, probe-source documents, and scientific data retain their own
terms. In particular, the bundled VesSAP derivative remains CC BY-NC 4.0 and is not covered by
the source-code terms; see [Third-Party Software and Data](THIRD_PARTY.md).
