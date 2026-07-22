# Project Status

Status reviewed: 2026-07-22

## Bottom line

The current development tree implements the end-to-end native research-planning path: independent
25 µm atlas slices, subject calibration and target projection, probe planning and region traversal,
the LAMBADA major-vessel reference, tapered-radius probe/vessel analysis, and a synchronized
SceneKit 3D view. It remains an engineering testing build—not a qualified distribution or a
validated animal-surgery navigation system.

The source is public at [KaiCao2003/brain3d](https://github.com/KaiCao2003/brain3d), with current
work in [draft pull request #1](https://github.com/KaiCao2003/brain3d/pull/1).

## Current product path

| Area | Implemented behavior | Important boundary |
| --- | --- | --- |
| Native workspace | Exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, one full-size view | No focus mode, crosshair, or 2×2 layout |
| Atlas slices | Independent persisted depths, buttons/slider/wheel, pan/zoom, click-to-replace region label | `allen_mouse_25um` v1.2 only; 10 µm excluded from testing |
| 3D | SceneKit brain mesh, camera control/reset, click-to-identify, probe envelopes, vessel tubes | Rendering consumes backend-verified geometry; scientific analysis remains in Python |
| Coordinates | Signed AP/ML/DV millimetres from bregma | AP− posterior, ML− left, DV− deep/ventral |
| Calibration | Create/list/inspect/validate/activate/remove subject calibration; QC-gated target projection | No default Allen bregma transform is invented |
| Probes | Versioned catalog, placement CRUD, 2D/3D overlays, site/region traversal, inspector, CSV/JSON export | NP1 is source-transcribed and review-pending, not independently verified |
| Major vessels | LAMBADA P60_606 radius-bearing graph in slices, Dorsal, and 3D | Reference specimen only; diameter ≥30 µm; pial/choroidal/smaller vessels omitted |
| Vessel analysis | V2 tapered-surface clearance with probe envelope, margin, uncertainty, conflicts, provenance | Requires risk-input and incomplete-coverage acknowledgements |
| Projects | Revisioned, checksummed `.mouseplan` save/open, migrations, backup recovery | Stale revisions and source mismatches fail closed |

Population vascular density and subject dorsal-image registration remain archived backend
capabilities. They are not shown in the primary UI and are not interpreted as vessel paths.

## Probe evidence state

The catalog's Neuropixels 1.0 NP1000 / `PRB_1_4_0480_1` entry transcribes the complete 960-site
geometry from pinned manufacturer, ProbeTable, and SpikeGLX source snapshots. Digests, retrieval
dates, coordinate rules, product identity, shank dimensions, tip geometry, references, and banks
are retained in the model.

Its exact status is `source-transcribed-review-pending`. Independent full-table review has not
been completed, so the UI requires explicit acknowledgement. The generic 16-site entry is a
synthetic software-test model and is labeled accordingly.

## Vessel evidence state

The current layer is derived from Renier, de Launoit, and Skriabine's P60_606 graph,
[Zenodo record 18876865](https://zenodo.org/records/18876865), DOI
`10.5281/zenodo.18876865`, CC BY 4.0. The immutable derivative keeps in-bounds runs whose point
radius is at least 15 µm: 71,313 points, 59,495 segments, and 11,818 polylines. Runtime checks bind
the asset to its manifest, hashes, array schema, Allen 25 µm frame, and extraction rule.

The V2 algorithm minimizes the probe-envelope distance to tapered vessel surfaces, rather than
assuming a constant radius or using only centerline distance. It subtracts the declared required
margin and registration uncertainty and reports the nearest geometry and conflict class. A
zero-conflict result uses only this bounded statement:

> No conflict detected within the loaded geometry and stated uncertainty assumptions.

The graph is a fixed, cleared P60 reference. It is not subject-specific; pial and choroidal
vessels were removed upstream, smaller vessels are filtered, and biological/registration error is
not bounded. Those limitations remain visible at the point of analysis.

## Engineering evidence and remaining qualification work

Python tests cover source integrity, coordinate transforms, calibration, probe placement, exact
voxel traversal, tapered vessel geometry, bridge validation, persistence, and real cached atlas
smoke paths. Swift tests cover strict protocol decoding, independent view state, viewport math,
slice overlays, SceneKit transforms, mesh/tube construction, and off-screen render smoke paths.
The app can be built and ad-hoc signed for development and is exercised as a real macOS process.

That evidence validates software behavior, not biological or procedural accuracy. Remaining work
before any qualified distribution includes independent NP1 transcription review, reference- and
subject-ground-truth studies, measured workflow/error studies, formal usability work, a bundled
deterministic Python runtime, Developer ID signing, notarization, and clean-Mac qualification.

No prospective animal study, phantom targeting study, histological outcome study, or formal
clinical/veterinary-device validation is claimed.
