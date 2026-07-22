# End-to-End Implementation Plan

This plan separates implemented engineering behavior from scientific and distribution
qualification. “Implemented” means reachable through the SwiftUI + SceneKit + Python product
path, with typed protocol coverage; it does not mean validated for an animal procedure.

| Phase | Deliverable | Current state |
| --- | --- | --- |
| 0 | Baseline, reachability audit, risk inventory, architecture ADRs | Complete |
| 1 | One supported GUI and minimal dependencies | Complete |
| 2 | Independent single-view atlas navigation | Implemented |
| 3 | Subject calibration and AP/ML/DV target projection | Implemented |
| 4 | Source-traceable probe catalog and placement | Implemented; NP1 independent review pending |
| 5 | Exact region traversal, site mapping, inspection, export | Implemented |
| 6 | Major-vessel source, provenance, and 2D overlays | Implemented for the LAMBADA P60 reference |
| 7 | Tapered-radius reference vessel analysis | Implemented; biological qualification pending |
| 8 | Native 3D brain/probe/vessel view and picking | Implemented with SceneKit |
| 9 | Animal-study validation and production distribution | Not started |

## Implemented engineering checkpoint

- The mode bar is exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, with one selected
  view. Coronal, sagittal, and horizontal retain independent depths.
- Slider, previous/next, wheel, pan, zoom, and reset share one verified 25 µm slice state. A
  click replaces one compact region label without changing depth.
- Subject calibrations carry atlas identity, transforms, residuals, QC, uncertainty, version,
  and hash. Projection and probe creation require an active calibration that permits planning.
- Bregma input is named `[AP, ML, DV]`: negative is posterior, left, and deep/ventral.
- The probe catalog contains a complete source transcription of NP1 NP1000 /
  `PRB_1_4_0480_1` plus a synthetic test fixture. NP1 stays
  `source-transcribed-review-pending` until an independent full-table review is recorded.
- Probe plans expose entry, target, tip, shank envelope, and recording sites in slice and 3D
  views. Exact voxel traversal drives region inspection and CSV/JSON export.
- The bundled LAMBADA P60_606 derivative retains radius-bearing runs at diameter ≥30 µm and
  is rendered on intersecting 2D planes, as a Dorsal reference projection, and as 3D tubes.
- Vessel analysis uses the V2 tapered-surface algorithm, conservative probe envelopes, explicit
  required margin and registration uncertainty, and acknowledgements for the lab-defined inputs
  and incomplete reference coverage.
- Population density and subject-image registration are archived backend paths, not primary UI
  features. The 10 µm atlas is excluded from this testing phase.

## Phase 9 — evidence and distribution gates

The remaining program is qualification rather than another UI feature sweep:

1. independently review every NP1 transcribed dimension and all 960 site coordinates;
2. define and execute phantom, histology, targeting-error, and repeated-observer studies;
3. quantify calibration and registration uncertainty against declared ground truth;
4. validate the reference-vessel algorithm on known geometries and clearly separate reference
   results from any future subject-specific evidence;
5. run formal animal-workflow usability and failure-recovery studies;
6. establish performance and visual-regression acceptance thresholds on supported Macs;
7. bundle a deterministic Python runtime and produce an SBOM;
8. complete Developer ID signing, hardened-runtime review, notarization, and clean-Mac tests; and
9. complete a final animal-only/non-human/non-clinical requirement audit.

The LAMBADA layer can never fill its own omissions: it is one fixed cleared specimen, excludes
pial and choroidal vessels upstream, and filters smaller vessels. A current zero-conflict result
must remain exactly bounded as:

> No conflict detected within the loaded geometry and stated uncertainty assumptions.
