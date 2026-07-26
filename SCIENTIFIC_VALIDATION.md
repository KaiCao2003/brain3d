# Scientific Validation Record

Reviewed: 2026-07-25

This file distinguishes implemented and tested software behavior from scientific or procedural
validation. Brain3D is restricted to non-human mouse research. No clinical, veterinary-device,
animal-outcome, phantom-targeting, histological-accuracy, or formal usability validation is
claimed.

## Current evidence matrix

| Area | Software evidence in the current tree | What remains unestablished |
| --- | --- | --- |
| Native workspace | Single selected five-mode view, independent depths, shared selected-region overlays in four 2D modes plus 3D, pan/zoom/wheel, stale-frame checks | Procedure usability and error rate |
| Allen atlas | Strict `allen_mouse_25um` v1.2 identity, metadata/array checks, real-cache smoke paths | Subject anatomy and 25 µm targeting accuracy |
| Direct atlas-surface input | Source-pinned Pinpoint/Urchin reference; AP/ML sign tests; exact first-annotated-voxel surface; depth/angle/layout reconstruction and persisted-digest checks | Accuracy of the profile for an individual animal, pia/skull correspondence, and achieved path |
| Legacy calibration | Typed CRUD, matched-landmark fits, residual/QC gates, transform round trips, hash/revision binding retained for v1–v3 | Accuracy of user measurements and biological registration |
| NP2 geometry | Selectable NP2003/NP2013 geometries are derived from pinned source constants; shank/site count, pitch, offset, transform, and plan-creation tests | Independent full-table review and physical-probe conformance |
| NP1 geometry | All 960 sites derived from pinned source snapshots; schema/count/pattern tests | Independent full-table review and physical-probe conformance |
| VesSAP display geometry | Pinned source/asset/transform digests; true-path extraction; axis/laterality/bounds/label checks; Python→Swift binary protocol; slice/3D render tests | Subject registration, live anatomy, clearing/inter-animal error, and qualified vessel surfaces |
| LAMBADA evidence | Reproducible extraction, source/asset hashes, schema/bounds/radius/run checks, and digest-bound rejected qualification | Biological laterality, whole-brain coverage, and subject-specific vasculature |
| Vessel V3 | Legacy synthetic AABB-candidate and tapered-surface tests; production capability is absent | Subject-specific geometry, empirical uncertainty, and biological decision thresholds |
| SceneKit | Coordinate-transform, brain/probe/vessel mesh, picking, and off-screen render tests | Anatomical truth beyond supplied geometry |
| Persistence | Project revisions, checksums, migrations, backup recovery, source/input digests | Long-term regulated record requirements |

The macOS application is built and ad-hoc signed as a development bundle and exercised as a real
process. That does not constitute clean-Mac production packaging, notarization, or release
qualification.

## Atlas boundary

The supported identity is:

| Field | Value |
| --- | --- |
| BrainGlobe key/version | `allen_mouse_25um` / `1.2` |
| Voxel spacing | `(25,25,25)` µm |
| Array shape | `(528,320,456)` in `[AP,DV,ML]` order |
| CCF citation | Wang et al., Cell 2020, DOI `10.1016/j.cell.2020.04.007` |

The 10 µm package is excluded from this testing phase. The accepted 25 µm sampling interval
does not bound stereotaxic, registration, or procedural error. Slice and SceneKit coordinate
round trips test the application convention, not biological correspondence to an individual
mouse.

## Direct bregma, surface, angle, and layout convention

The v4 direct path uses AP and ML millimetres from a named Pinpoint/Urchin profile:

| Axis | Positive | Negative |
| --- | --- | --- |
| AP | anterior | posterior / back |
| ML | left | right |

The pinned reference resolves to BrainGlobe physical `[AP,DV,ML] = [5200,332,5700] µm` for
`allen_mouse_25um` v1.2. The exact Urchin revision and source SHA-256 are persisted. This is a
reproducible Pinpoint planning convention, not an Allen-supplied official bregma and not a
subject-specific registration.

At the requested AP/ML column, software tests require the entry to equal the superior boundary
of the first nonzero annotation voxel. Depth is the positive entry-to-tip path length. For the
single visible sagittal angle, positive advances A→P and negative advances P→A. NP2013 layout
`0°` places the shank plane sagittally; `90°` rotates it clockwise from dorsal. These tests
establish implementation signs and reconstruction, not accuracy in a live animal.

V1–v3 target/calibration records remain preserved with their original requirements. Their
projection still requires declared skull-frame metadata, matched landmarks, laterality, a DV
reference, a rigid/similarity fit, and user-sourced QC limits. They are not silently converted
into v4 surface plans.

## Neuropixels 2.0 evidence

The primary selector exposes `NP2003` (single shank) and standard `NP2013` (four shanks); both
expose 384 simultaneous channels. `NP2004` and `NP2014` remain cited in the pinned source
artifacts where they share the transcribed physical geometries, but are not extra UI choices.
The transcription uses
pinned imec data-sheet, User Manual V1.0.6, electrode-channel mapping, ProbeTable 1.8, and
SpikeGLX snapshots. Quad Base remains archived compatibility evidence and is not selectable.

Each 10 mm × 70 µm × 24 µm shank contains 1,280 point sites in 640 two-site rows. Coordinates
use the source-backed 206 µm tip-to-lowest-row-center distance, 15 µm axial pitch, and −8/+24 µm
lateral centers. Four-shank centers are 0/+250/+500/+750 µm from primary leftmost `shank-0`.
The manufacturer 175 µm chisel-tip length remains a distinct physical dimension.

The two selectable choices and archived Quad Base definition are
**`source-transcribed-review-pending`**. Exact software reconstruction and end-to-end creation
tests do not establish manufacturing tolerance, independent transcription review,
physical-device conformance, implantation accuracy, or tissue response.

## Neuropixels 1.0 evidence

The NP1 NP1000 / `PRB_1_4_0480_1` entry transcribes all 960 sites from four pinned sources:

- imec Neuropixels 1.0 specification;
- ProbeTable 1.8 `probe_features.json` at commit
  `207f7bf424b0fa26f271700b970e27a58a9a1111`;
- SpikeGLX `IMROTbl.cpp` at commit `d67bee45fa2635873456eb5d3f5e5a051690e64f`; and
- SpikeGLX metadata coordinate definitions at that commit.

Each snapshot has a recorded SHA-256. The model distinguishes the manufacturer 175 µm chisel
tip from SpikeGLX's 209 µm physical-tip-to-lowest-row-center measurement. It includes the 10 mm
shank, 70 µm width, 24 µm thickness, row/site pattern, references, and banks.

The verification status is **`source-transcribed-review-pending`**. The transcription has not
received an independent full-table human review, so it cannot be described as independently
verified manufacturer geometry. See [Probe Models](PROBE_MODELS.md).

## VesSAP display-reference evidence

Source: VesSAP `BL6J-no1`, Todorov et al., *Machine learning analysis of whole mouse brain
vasculature*, [DOI `10.1038/s41592-020-0792-1`](https://doi.org/10.1038/s41592-020-0792-1),
public repository release 2021.10.01, CC BY-NC 4.0.

The derivative begins with the official same-grid 3 µm skeleton and radius volumes. Radius ≥5
source voxels retains 1,262,706 centerline voxels (nominal radius ≥15 µm / diameter ≥30 µm).
Only mapped edges induced by true 26-neighbour source adjacency are retained; graph endpoint
chords are never substituted. Paths are coalesced on a 50 µm display grid, yielding 196,377
points, 76,622 runs, and 119,755 segments in a 1,853,131-byte NPZ with SHA-256
`9300dacf25ca57a5d23377ca0dc885e34ff0d18e8d21ef7590c6dcd156cf5db7`.

The authors' Euler + B-spline transform is interpreted as
`AP_um = 30*T_y`, `DV_um = 30*T_z`, `ML_um = 11390 - 30*T_x`. The ML reflection is mandatory:
VesSAP moving-x increases left-to-right while BrainGlobe ASR ML increases right-to-left.
Deterministic validation used 20,000 graph nodes. It found 99.705% in atlas bounds, 99.4618%
grouped-region agreement at 10 µm excluding background, 99.9787% agreement between the official
registered signed-label NIfTI and supplied processed groups, and 99.9794% laterality agreement at
the canonical midpoint. Four laterality discrepancies were all within 5.38 µm of midline.

These checks qualify the coordinate interpretation for a display reference. They do not qualify
clearance. This is one ex-vivo cleared specimen; no target-registration-error, bregma/skull
registration, clearing-distortion, or inter-animal bound is published. Sampled nonlinear-transform
singular values span 0.672–1.560, so a scalar source radius is not a qualified circular
atlas-space surface. The runtime therefore exposes geometry but rejects clearance analysis.
See [the full evidence record](docs/VESSAP_MAJOR_VESSELS.md).

## LAMBADA major-vessel evidence

Source: Renier, de Launoit, and Skriabine, *Vascular graphs of the developing post-natal mouse
brain*, [Zenodo record 18876865](https://zenodo.org/records/18876865), DOI
`10.5281/zenodo.18876865`, CC BY 4.0; associated Cell paper DOI
`10.1016/j.cell.2026.03.013`.

The pinned source archive is `P60_606_graph_2024-12-03.gt.7z`, 5,050,194,723 bytes, Zenodo MD5
`218ed346c6d7dc501301204f811be37f`. The bundled 814,393-byte derivative has SHA-256
`fb2344e845e604be3424bd63f4222d273eafba34db0df2eaff32f4400fa9afec` and contains:

- 71,313 radius-bearing points;
- 59,495 segments;
- 11,818 maximal consecutive in-bounds runs; and
- 10,907 contributing source edges.

The extraction threshold is point radius ≥15 µm, equivalent to diameter ≥30 µm. It does not
select whole edges by mean or maximum radius. Coordinates are converted from ClearMap to
BrainGlobe `[AP,DV,ML]` and then to physical micrometres without a half-voxel shift. The loader
checks the adjacent manifest, asset identity, arrays, dtypes, shapes, bounds, thresholds, ordering,
and run lengths in the archived evidence path.

This evidence supports deterministic extraction from the declared reference. It does not support
display or analysis. The exact qualification found supporting AP and DV orientation evidence but
rejected the asset because the primary source describes hemisphere specimens and the exact graph
has no persisted biological hemisphere/laterality binding. Whole-brain coverage and ML polarity
are unqualified; numeric points on both sides of the array midpoint do not resolve either issue,
and no mirroring is permitted.

No LAMBADA handler or capability is registered in the current runtime, and the production
reference endpoints never load this asset; those endpoints now belong exclusively to the
separately qualified VesSAP display reference. The canonical LAMBADA rejection report is
[`docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json`](docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.
The source also excludes pial and choroidal vessels; the derivative filters smaller vessels; and
artery/vein identity, biological variation, tissue distortion, and registration error are not
resolved. See [the derivation record](docs/LAMBADA_MAJOR_VESSELS.md).

## Archived V3 algorithm evidence

Algorithm `major-vessel-aabb-tapered-surface-v3` computes conservative AABB lower bounds and
feasible upper bounds before running exact finite-segment and tapered-surface minimization only on
the sound candidate set. In isolated synthetic tests it reports centerline/surface geometry,
interpolated radius, probe envelope, required margin,
registration uncertainty, adjusted clearance, closest points, insertion depth, conflict class,
source identity, algorithm version, and input hashes.

This algorithm is not a production capability for VesSAP or P60_606. The display-only gate runs
before project, asset, or analysis access, so the application produces neither positive conflicts
nor absence results. User-supplied margins or uncertainty cannot manufacture missing source
uncertainty bounds.

### Reproducible performance evidence

The offline, non-product [major-vessel benchmark](scripts/benchmark_major_vessel_analysis.py)
loads the SHA-256-verified archived asset and uses a fixed synthetic probe/profile input. Run it
with:

```console
uv run python scripts/benchmark_major_vessel_analysis.py --iterations 20
```

One run on 2026-07-22 used an Apple M4 (`Mac16,13`, arm64), macOS 26.5.2, and CPython
3.12.13. The asset contained 71,313 points, 11,818 runs, and 59,495 segments. V3 selected
243 candidates, performed exactly 243 narrow-phase measurements, and reported 153 loaded-geometry
algorithmic conflicts in that offline fixture. Timings were:

| Measurement | Milliseconds |
| --- | ---: |
| Verified asset load and analysis-geometry construction | 44.205 |
| First analysis after load | 27.283 |
| Warm analysis median, 20 iterations | 28.656 |
| Warm analysis P95, 20 iterations | 45.697 |

Python/module startup is excluded. The benchmark enforces `--iterations` in `[5,100]`, verifies
the bundled asset counts and digest, rejects changing outputs across identical runs, and emits the
machine, Python, geometry, result counts, and timings as JSON. These measurements are one-machine
engineering evidence for archived code, not runtime availability, a cross-hardware latency
guarantee, or scientific/surgical validation.

## Archived evidence paths

The Kim 2022 population vascular-length-density field and user subject-image registration remain
in the Python backend for reproducibility of older work. They are absent from the primary UI and
do not bypass the VesSAP display-only or LAMBADA rejection gates. A scalar density projection contains no
individual vessel path/radius; a registered image is not automatically a vessel segmentation.

## Required evidence before qualification

1. Independent review of every NP1 source-derived dimension and site coordinate.
2. Repeated-observer subject calibration studies with declared ground truth.
3. Phantom and histology studies for planned versus achieved probe paths and sites.
4. Subject-specific vascular ground truth with measured bregma/skull registration error,
   clearing/live-tissue distortion, inter-animal variation, and false-negative coverage.
5. Reference-graph failure-mode studies and prospectively defined margin/uncertainty criteria.
6. Formal animal-workflow usability, accessibility, interruption, and recovery studies.
7. Deterministic runtime packaging, SBOM, signing/notarization, and clean-Mac qualification.

Passing repository tests or rendering a complete scene does not satisfy these scientific gates.
