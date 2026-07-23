# Project Status

Status reviewed: 2026-07-23

## Bottom line

The current development tree implements the native research-planning path for independent 25 µm
atlas slices, subject calibration and target projection, probe planning and region traversal, and
a synchronized SceneKit 3D view. A pinned VesSAP C57BL/6J major-vessel reference is visible in
all five views; clearance analysis remains unavailable. The application remains an engineering
testing build—not a qualified distribution or a validated animal-surgery navigation system.

The source is public at [KaiCao2003/brain3d](https://github.com/KaiCao2003/brain3d).

## Current product path

| Area | Implemented behavior | Important boundary |
| --- | --- | --- |
| Native workspace | Exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, one full-size view | No focus mode, crosshair, or 2×2 layout |
| Atlas regions | Complete paged 840-structure ontology, common hierarchy/search/selection across all five modes | Selecting a region never moves or couples slice depths; only its 3D mesh loads |
| Atlas slices | Independent persisted depths, buttons/slider/wheel, pan/zoom, click-to-replace region label | `allen_mouse_25um` v1.2 only; 10 µm excluded from testing |
| 3D | SceneKit whole-brain mesh, camera control/reset, non-cortical region highlight, probe envelopes, and major-vessel tubes | Rendering consumes schema-checked brain/probe/vessel geometry from the backend |
| Coordinates | Required subject identity and signed AP/ML/DV millimetres from bregma | AP− posterior, ML− left, DV− deep/ventral |
| Calibration | Create/list/inspect/validate/activate/remove subject calibration; QC-gated target projection | No default Allen bregma transform is invented |
| Probes | Production selector contains only NP2 single and standard four-shank; four explicit placement modes, CRUD, 2D/3D overlays, site/region traversal, inspector, CSV/JSON export | Manufacturer models are source-transcribed and review-pending, not independently verified |
| Major vessels | VesSAP BL6J-no1, nominal diameter ≥30 µm, overlaid on Dorsal/Coronal/Sagittal/Horizontal/3D | One cleared ex-vivo population reference; 50 µm display reduction; no capillaries |
| Vessel analysis | Unavailable; geometry is display-only and analysis returns `VESSEL_ANALYSIS_UNAVAILABLE` | No conflict, no-conflict, clearance, absence, suitability, or safety claim is produced |
| Projects | Revisioned, checksummed `.mouseplan` save/open, migrations, backup recovery | Stale revisions and source mismatches fail closed |

Population vascular density and subject dorsal-image registration remain archived compatibility
code and persisted data. Their methods/capabilities are not registered by the primary bridge,
they are not shown in the primary UI, and they are not interpreted as vessel paths.

## Probe evidence state

The catalog defaults to Neuropixels 2.0 single shank and exposes only complete 1,280-site
`NP2003`/`NP2004` geometry and a 5,120-site standard `NP2013`/`NP2014` choice; both have 384
simultaneous channels. Quad Base, NP1, and the synthetic fixture remain archived definitions for
old-project compatibility and tests, not selectable new hardware. Digests, retrieval dates,
coordinate rules, product identities, shank dimensions and offsets, tip geometry, references,
and banks are retained.

Its exact status is `source-transcribed-review-pending`. Independent full-table review has not
been completed, so the UI requires explicit acknowledgement. The generic 16-site entry is a
synthetic software-test model and is labeled accordingly.

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

Python tests cover source integrity, coordinate transforms, calibration, probe placement, exact
voxel traversal, the vessel display/analysis boundary, persistence, and real cached atlas paths.
Legacy synthetic tests preserve isolated tapered-geometry contracts, but the production bridge
cannot expose them. Swift tests cover strict protocol decoding, independent view state, viewport
math, complete ontology paging/closure, slice overlays, SceneKit transforms, bounded mesh
caching, and an off-screen composite containing whole brain, Thalamus, NP2, and VesSAP vessels.
The app can be built and ad-hoc signed for development and is exercised as a real macOS process.

That evidence validates software behavior, not biological or procedural accuracy. Remaining work
before any qualified distribution includes independent supported-NP2 transcription review, reference-
and subject-ground-truth studies, measured workflow/error studies, formal usability work, a
bundled deterministic Python runtime, Developer ID signing, notarization, and clean-Mac
qualification.

No prospective animal study, phantom targeting study, histological outcome study, or formal
clinical/veterinary-device validation is claimed.
