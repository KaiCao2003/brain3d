# Project Status

Status reviewed: 2026-07-22

## Bottom line

The current development tree implements the native research-planning path for independent 25 µm
atlas slices, subject calibration and target projection, probe planning and region traversal, and
a synchronized SceneKit 3D view. The LAMBADA P60_606 vessel path is rejected and unavailable. The
application remains an engineering testing build—not a qualified distribution or a validated
animal-surgery navigation system.

The source is public at [KaiCao2003/brain3d](https://github.com/KaiCao2003/brain3d), with current
work in [draft pull request #1](https://github.com/KaiCao2003/brain3d/pull/1).

## Current product path

| Area | Implemented behavior | Important boundary |
| --- | --- | --- |
| Native workspace | Exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, one full-size view | No focus mode, crosshair, or 2×2 layout |
| Atlas slices | Independent persisted depths, buttons/slider/wheel, pan/zoom, click-to-replace region label | `allen_mouse_25um` v1.2 only; 10 µm excluded from testing |
| 3D | SceneKit brain mesh, camera control/reset, click-to-identify, and probe envelopes | Rendering consumes schema-checked brain/probe geometry from the backend |
| Coordinates | Required subject identity and signed AP/ML/DV millimetres from bregma | AP− posterior, ML− left, DV− deep/ventral |
| Calibration | Create/list/inspect/validate/activate/remove subject calibration; QC-gated target projection | No default Allen bregma transform is invented |
| Probes | Versioned catalog, four explicit placement modes with editable entry, CRUD, 2D/3D overlays, site/region traversal, inspector, CSV/JSON export | NP1 is source-transcribed and review-pending, not independently verified |
| Major vessels | No runtime layer; the P60_606 derivative is archived qualification evidence only | Hemisphere/laterality and whole-brain coverage are unqualified; no mirroring |
| Vessel analysis | Unavailable; metadata, geometry, and analysis calls return `VESSEL_GEOMETRY_UNAVAILABLE` | No vessel conflict, no-conflict, or clearance claim is produced |
| Projects | Revisioned, checksummed `.mouseplan` save/open, migrations, backup recovery | Stale revisions and source mismatches fail closed |

Population vascular density and subject dorsal-image registration remain archived compatibility
code and persisted data. Their methods/capabilities are not registered by the primary bridge,
they are not shown in the primary UI, and they are not interpreted as vessel paths.

## Probe evidence state

The catalog's Neuropixels 1.0 NP1000 / `PRB_1_4_0480_1` entry transcribes the complete 960-site
geometry from pinned manufacturer, ProbeTable, and SpikeGLX source snapshots. Digests, retrieval
dates, coordinate rules, product identity, shank dimensions, tip geometry, references, and banks
are retained in the model.

Its exact status is `source-transcribed-review-pending`. Independent full-table review has not
been completed, so the UI requires explicit acknowledgement. The generic 16-site entry is a
synthetic software-test model and is labeled accordingly.

## Vessel evidence state

The archived derivative is derived from Renier, de Launoit, and Skriabine's P60_606 graph,
[Zenodo record 18876865](https://zenodo.org/records/18876865), DOI
`10.5281/zenodo.18876865`, CC BY 4.0. The immutable derivative keeps in-bounds runs whose point
radius is at least 15 µm: 71,313 points, 59,495 segments, and 11,818 polylines. Runtime checks bind
the qualification decision to a canonical report digest.

The exact qualification found supporting AP and DV orientation evidence, but the primary source
describes hemisphere specimens and the exact graph has no persisted property binding biological
hemisphere/laterality. Numeric points on both sides of the atlas midpoint do not qualify
whole-brain coverage. No exact-specimen source authorizes mirroring, so ML polarity is not guessed
and the derivative is not mirrored.

The runtime does not advertise `auditedReferenceMajorVessels` or
`radiusAwareReferenceVesselAnalysis`. `vessel.major.reference.get`,
`vessel.major.reference.geometry`, and `vessel.major.reference.analyze` fail closed with
`VESSEL_GEOMETRY_UNAVAILABLE` before loading or serving any points. The canonical report is
[`docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json`](docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.

## Engineering evidence and remaining qualification work

Python tests cover source integrity, coordinate transforms, calibration, probe placement, exact
voxel traversal, the vessel qualification gate, persistence, and real cached atlas smoke paths.
Legacy synthetic tests preserve isolated tapered-geometry contracts, but the production bridge
cannot expose them. Swift tests cover strict protocol decoding, independent view state, viewport
math, slice overlays, SceneKit transforms, mesh construction, and off-screen render smoke paths.
The app can be built and ad-hoc signed for development and is exercised as a real macOS process.

That evidence validates software behavior, not biological or procedural accuracy. Remaining work
before any qualified distribution includes independent NP1 transcription review, reference- and
subject-ground-truth studies, measured workflow/error studies, formal usability work, a bundled
deterministic Python runtime, Developer ID signing, notarization, and clean-Mac qualification.

No prospective animal study, phantom targeting study, histological outcome study, or formal
clinical/veterinary-device validation is claimed.
