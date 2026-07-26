# Project Status

Status reviewed: 2026-07-25

## Bottom line

The current development tree implements the native research-planning path for independent 25 µm
atlas slices, direct atlas-surface NP2003/NP2013 planning, shared region highlighting, and a
synchronized SceneKit 3D view. A pinned VesSAP C57BL/6J major-vessel reference is visible in all
five views; clearance analysis remains unavailable. The application remains an engineering
testing build—not a qualified distribution or a validated animal-surgery navigation system.

The source is public at [KaiCao2003/brain3d](https://github.com/KaiCao2003/brain3d).

## Current product path

| Area | Implemented behavior | Important boundary |
| --- | --- | --- |
| Native workspace | Exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, one full-size view | No focus mode, crosshair, or 2×2 layout |
| Atlas regions | Complete paged 840-structure ontology, common hierarchy/search/selection, descendant-inclusive annotation highlight in all four 2D modes, and the same selected mesh in 3D | Selecting a region never moves or couples slice depths; zero-voxel structures are not fabricated |
| Atlas slices | Independent persisted depths, buttons/slider/wheel, editable one-based slice number, pan/zoom, click-to-replace region label, and explicit atlas-physical coordinate header | `allen_mouse_25um` v1.2 only; 10 µm excluded from testing; header coordinates are not bregma-relative |
| 3D | SceneKit whole-brain mesh, camera control/reset, non-cortical region highlight, probe envelopes, and major-vessel tubes | Rendering consumes schema-checked brain/probe/vessel geometry from the backend |
| Coordinates | Required animal-only context plus signed surface-insertion AP/ML millimetres from a named Pinpoint/Urchin profile, local annotation-surface depth, one sagittal angle, and layout | AP+ anterior/AP− posterior; ML+ right/ML− left; positive angle A→P/negative P→A; the profile is not Allen-official or animal-specific |
| Direct surface | Exact superior boundary of the first nonzero annotation voxel at the resolved AP/ML column; persisted source/digest and load-time rederivation | Population-atlas surface, not measured pia/skull/current-animal anatomy |
| Probes | Primary selector contains only `NP2003` and `NP2013`; normal NP2013 layout is sagittal and `90°` is clockwise from dorsal; numeric edits commit on Return/focus loss and atomic selector changes update immediately | Built-ins are source-transcribed and review-pending, not independently verified; v4 has no target/calibration prerequisite, geometry checkbox, or Apply button |
| Major vessels | VesSAP BL6J-no1, nominal diameter ≥30 µm, overlaid on Dorsal/Coronal/Sagittal/Horizontal/3D; visible-diameter filter is adjustable from 30–250 µm | One cleared ex-vivo population reference; geometry is reduced on a 50 µm spatial grid; no capillaries |
| Surgery-plan PDF | Direct-PDF two-page protocol prefill, one plan-centred view or all five, then one AP/`|ML|`-matched page from `MBSC_Figs_with_Layers.pdf`; v4 pages print AP/ML, local-surface depth, signed angle, and layout | User-owned PDF locations are saved once in Settings and are not bundled; disconnected volumes must be reconnected; planning titles/coordinates and final order are verified |
| Vessel analysis | Unavailable; geometry is display-only and analysis returns `VESSEL_ANALYSIS_UNAVAILABLE` | No conflict, no-conflict, clearance, absence, suitability, or safety claim is produced |
| Projects | Schema-9 revisioned, checksummed `.mouseplan` save/open, migrations, backup recovery, v4 surface rederivation, exact probe-model validation, and legacy v2/v3 reconstruction | Schema-8→9 preserves existing v1–v3 targets/calibrations without guessed conversion; stale sources, altered geometry, forged surface evidence, and invalid legacy fits fail closed |
| Draft lifecycle | One main planning window with an app-owned probe draft; same-context window/sidebar reconstruction preserves typed values; open/reconnect/quit and plan changes are dirty-state guarded | Closing the main window does not quit the app or silently discard the current draft |

Population vascular density and subject dorsal-image registration remain archived compatibility
code and persisted data. Their methods/capabilities are not registered by the primary bridge,
they are not shown in the primary UI, and they are not interpreted as vessel paths.

## Probe evidence state

The primary selector exposes only the complete 1,280-site `NP2003` and 5,120-site standard
four-shank `NP2013`; both have 384 simultaneous channels. `NP2004`/`NP2014` remain cited where
the pinned sources group equivalent physical geometries, not as extra UI choices. Quad Base,
NP1, and the synthetic fixture remain archived definitions for old-project compatibility and
tests. Digests, retrieval dates, coordinate rules, product identities, shank dimensions and
offsets, tip geometry, references, and banks are retained.

Its exact status is `source-transcribed-review-pending`. Independent full-table review has not
been completed. The v4 UI does not add a per-plan geometry checkbox and does not describe either
model as independently verified. The generic 16-site entry is a synthetic software-test model.

Project validation compares every catalog-owned persisted model against its exact source-pinned
definition, including provenance, verification state, shank and tip geometry, and the complete
ordered recording-site table. A known catalog ID with an unknown version, or a changed model with
recomputed surrounding hashes, is rejected. Unknown custom identities are limited to historical
v1 audit/review and cannot enter current planning geometry or analysis.

## Vessel evidence state

The runtime reference comes from VesSAP `BL6J-no1`, one fixed cleared adult C57BL/6J brain,
[DOI `10.1038/s41592-020-0792-1`](https://doi.org/10.1038/s41592-020-0792-1),
CC BY-NC 4.0. Source skeleton voxels with radius ≥5 on the 3 µm grid are traced through true
26-neighbour adjacency, transformed through the authors' Euler + B-spline Allen registration,
and coalesced on a 50 µm display grid. The exact NPZ is 1,853,131 bytes,
SHA-256 `9300dacf25ca57a5d23377ca0dc885e34ff0d18e8d21ef7590c6dcd156cf5db7`,
with 196,377 points, 76,622 runs, and 119,755 segments.

Deterministic sampling validated the required `[T_y,T_z,T_x] → [AP,DV,ML]` permutation, mandatory
ML reflection, atlas bounds, and label agreement. This establishes a trustworthy transform
interpretation for display—not biological surgical accuracy. No numeric subject-registration,
clearing-distortion, or inter-animal bound exists, and nonlinear deformation changes a circular
source radius anisotropically.

The runtime therefore advertises `auditedReferenceMajorVessels` but not
`radiusAwareReferenceVesselAnalysis`. Metadata and geometry are served after exact identity and
buffer checks; analysis fails before project access with `VESSEL_ANALYSIS_UNAVAILABLE`. The
archived LAMBADA P60_606 derivative remains rejected and is never displayed or mirrored.
See [the VesSAP derivation and validation record](docs/VESSAP_MAJOR_VESSELS.md).

## Engineering evidence and remaining qualification work

Python tests cover source integrity, coordinate transforms, direct AP/ML sign handling, exact
annotation-surface resolution, positive/negative sagittal angle and layout direction, probe
placement, region overlays, voxel traversal, the vessel display/analysis boundary, persistence,
and real cached atlas paths. Persisted-plan tests rederive v4 surface geometry and reconstruct
legacy v2/v3 geometry from preserved planning inputs; they reject forged surface evidence,
translated/rehashed geometry, same-target alternate-angle geometry, projection-digest forgeries,
changed/rehashed catalog model snapshots, and legacy calibrations that violate AP ordering or
atlas midline/laterality semantics. Calibration tests independently rerun both production fits
and reject forged matrices, correspondences, residuals, leveling angles, and QC. Historical v1
records remain loadable for review but cannot enter 2D/3D planning overlays, PDF planning pages,
or region analysis until updated; vessel-clearance analysis is unavailable for every version.
Legacy synthetic tests preserve isolated tapered-geometry contracts, but the production bridge
cannot expose them. Swift tests cover strict protocol decoding, independent view state, viewport
math, complete ontology paging/closure, slice overlays, SceneKit transforms, bounded mesh
caching, descendant-inclusive 2D region compositing, a singleton main-window policy with
app-owned same-context draft retention, and an off-screen composite containing whole brain,
Thalamus, NP2, and VesSAP vessels.
Surgery-export tests cover the exact 132-page atlas catalog, historical Bregma/Interaural
convention, AP/`|ML|` matching, direct protocol-PDF overlay units, per-page vessel
identity/count disclosure, bounded long subject/target identity, exact planning-page coordinate
retention, and deterministic ordered page assembly.
The app can be built and ad-hoc signed for development and is exercised as a real macOS process.

Viewer-only slice and pick updates use a targeted viewer-state validator and copy only those
fields onto the already validated project graph. This removes unrelated trajectory
reconstruction from interactive navigation; project create/open/save, surgery-plan mutation,
analysis, and export retain full semantic validation.

That evidence validates software behavior, not biological or procedural accuracy. Remaining work
before any qualified distribution includes independent supported-NP2 transcription review, reference-
and subject-ground-truth studies, measured workflow/error studies, formal usability work, a
bundled deterministic Python runtime, Developer ID signing, notarization, and clean-Mac
qualification.

No prospective animal study, phantom targeting study, histological outcome study, or formal
clinical/veterinary-device validation is claimed.
