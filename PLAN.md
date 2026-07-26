# End-to-End Implementation Plan

This plan separates implemented engineering behavior from scientific and distribution
qualification. “Implemented” means reachable through the SwiftUI + SceneKit + Python product
path, with typed protocol coverage; it does not mean validated for an animal procedure.

| Phase | Deliverable | Current state |
| --- | --- | --- |
| 0 | Baseline, reachability audit, risk inventory, architecture ADRs | Complete |
| 1 | One supported GUI and minimal dependencies | Complete |
| 2 | Independent single-view atlas navigation | Implemented |
| 3 | Source-pinned AP/ML profile and exact local annotation-surface entry | Implemented; population-atlas assumption only |
| 4 | Source-traceable NP2003/NP2013 catalog and direct depth/angle/layout placement | Implemented; supported NP2 independent review pending |
| 5 | Exact region traversal, site mapping, inspection, export | Implemented |
| 6 | Major-vessel source, provenance, and 2D overlays | VesSAP display-only overlay implemented; P60_606 archived |
| 7 | Tapered-radius reference vessel analysis | Algorithm tests retained; production capability absent |
| 8 | Native 3D brain/probe/vessel view and picking | Implemented with SceneKit |
| 9 | Animal-study validation and production distribution | Not started |

## Implemented engineering checkpoint

- The mode bar is exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, with one selected
  view. Coronal, sagittal, and horizontal retain independent depths.
- Slider, previous/next, wheel, pan, zoom, and reset share one verified 25 µm slice state. A
  click replaces one compact region label without changing depth.
- The complete 840-structure Allen hierarchy and search are shared by all five modes. Selecting a
  cortical or non-cortical structure replaces one global identity and lazily loads only that 3D
  mesh; it does not couple the three slice depths.
- V4 plans persist the named Pinpoint/Urchin reference, annotation identity, exact local surface,
  surface-entry AP/ML, path depth, signed sagittal angle, layout, and model snapshot. AP− is
  posterior and ML− is animal-left. A separate target registration/calibration is not a v4
  prerequisite.
- Legacy subject calibrations and target records remain preserved with their original identity,
  transforms, residuals, QC, uncertainty, version, and hash.
- The production probe catalog contains only NP2 single shank (1,280 sites / 384 channels) and
  standard four shank (5,120 sites / 384 channels). Quad Base, NP1, and the synthetic fixture are
  archived compatibility/test definitions and are absent from the new-plan selector.
  Manufacturer entries stay `source-transcribed-review-pending` until independent full-table
  reviews are recorded.
- Probe plans expose entry, tip, shank envelope, and recording sites in slice and 3D
  views. Exact voxel traversal drives region inspection and CSV/JSON export.
- The VesSAP `BL6J-no1` diameter-≥30 µm reference is served after exact source/asset/transform
  checks and overlaid in all five views. True source-skeleton adjacency is retained through a
  50 µm display reduction. It is one cleared population reference, not subject-specific.
- Vessel clearance analysis fails closed with `VESSEL_ANALYSIS_UNAVAILABLE`; missing numeric
  subject-registration/tissue-distortion bounds cannot be replaced by user acknowledgements.
  The V3 algorithm remains isolated engineering/test evidence, not a production feature.
- The older LAMBADA P60_606 derivative remains archived and is never rendered, served, mirrored,
  or analyzed because hemisphere/laterality and whole-brain coverage failed qualification.
- Population density and subject-image registration are archived backend paths, not primary UI
  features. The 10 µm atlas is excluded from this testing phase.

## Phase 9 — evidence and distribution gates

The remaining program is qualification rather than another UI feature sweep:

1. independently review every supported NP2 transcribed dimension and all encoded site coordinates;
2. define and execute phantom, histology, targeting-error, and repeated-observer studies;
3. quantify calibration and registration uncertainty against declared ground truth;
4. obtain subject-specific vascular ground truth with measured bregma/subject registration,
   clearing/live-tissue, and inter-animal uncertainty before validating any vessel analysis;
5. run formal animal-workflow usability and failure-recovery studies;
6. establish performance and visual-regression acceptance thresholds on supported Macs;
7. bundle a deterministic Python runtime and produce an SBOM;
8. complete Developer ID signing, hardened-runtime review, notarization, and clean-Mac tests; and
9. complete a final animal-only/non-human/non-clinical requirement audit.

The VesSAP layer is display-only and cannot establish vessel absence, clearance, suitability, or
safety; see [its exact evidence record](docs/VESSAP_MAJOR_VESSELS.md). The older P60_606
derivative is not a layer. Its source is a hemisphere specimen, has no persisted
biological laterality binding, excludes pial and choroidal vessels upstream, and the derivative
filters smaller vessels. The runtime rejects it before producing any conflict or no-conflict
result. The canonical decision is recorded in
[`docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json`](docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.
