# Scientific Validation Record

Reviewed: 2026-07-22

This file distinguishes implemented and tested software behavior from scientific or procedural
validation. Brain3D is restricted to non-human mouse research. No clinical, veterinary-device,
animal-outcome, phantom-targeting, histological-accuracy, or formal usability validation is
claimed.

## Current evidence matrix

| Area | Software evidence in the current tree | What remains unestablished |
| --- | --- | --- |
| Native workspace | Single selected five-mode view, independent depths, click labels, pan/zoom/wheel, stale-frame checks | Procedure usability and error rate |
| Allen atlas | Strict `allen_mouse_25um` v1.2 identity, metadata/array checks, real-cache smoke paths | Subject anatomy and 25 µm targeting accuracy |
| Calibration | Typed CRUD, matched-landmark fits, residual/QC gates, transform round trips, hash/revision binding | Accuracy of user measurements and biological registration |
| Target/probe | AP/ML/DV sign tests, projection provenance, versioned placement, overlays, exact voxel traversal/export | Insertion deformation and histological endpoint |
| NP1 geometry | All 960 sites derived from pinned source snapshots; schema/count/pattern tests | Independent full-table review and physical-probe conformance |
| LAMBADA asset | Reproducible extraction, source/asset hashes, schema/bounds/radius/run checks | Subject-specific vasculature and omitted-vessel coverage |
| Vessel V3 | Sound AABB-candidate and tapered-surface tests, conservative probe envelopes, threshold classes, stale-input checks | Empirical registration uncertainty and biological decision thresholds |
| SceneKit | Coordinate-transform, mesh, tube, probe-envelope, picking, and off-screen render tests | Anatomical truth beyond supplied geometry |
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

## Calibration and bregma convention

User inputs are named `[AP, ML, DV]` millimetres from bregma:

| Axis | Positive | Negative |
| --- | --- | --- |
| AP | anterior | posterior / back |
| ML | right | left |
| DV | dorsal / up | deep / ventral |

An unprojected target remains a coordinate record. Projection requires a selected subject
calibration built from declared skull-frame metadata, four matched landmarks, laterality, a DV
reference, a rigid/similarity fit, and user-sourced QC limits. The result carries calibration and
atlas hashes. The Allen CCF supplies no unique official bregma transform; passing QC means only
that the declared numeric rules passed.

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
and run lengths before exposing immutable geometry.

This evidence supports the claim that the displayed paths and radii came from that declared
reference under the documented extraction rule. It does not support a claim about the current
animal. The source excludes pial and choroidal vessels; the derivative filters smaller vessels;
and sex/side, artery/vein identity, biological variation, tissue distortion, and registration
error are not resolved. See [the derivation record](docs/LAMBADA_MAJOR_VESSELS.md).

## V3 reference analysis semantics

Algorithm `major-vessel-aabb-tapered-surface-v3` computes conservative AABB lower bounds and
feasible upper bounds before running exact finite-segment and tapered-surface minimization only on
the sound candidate set. It
reports centerline/surface geometry, interpolated radius, probe envelope, required margin,
registration uncertainty, adjusted clearance, closest points, insertion depth, conflict class,
source identity, algorithm version, and input hashes.

The UI requires separate confirmation of the lab-defined margin/uncertainty inputs and
acknowledgement of incomplete reference coverage. The bundled provenance does not bound
registration error or tissue distortion, so absence of a conflict is classified
`insufficientGeometry` even after acknowledgement; user input cannot replace missing source
evidence. Positive loaded-geometry conflicts remain reportable. The zero-conflict wording below is
reserved for a future source with reviewed bounds covered by the stated uncertainty:

> No conflict detected within the loaded geometry and stated uncertainty assumptions.

### Reproducible performance evidence

The offline [major-vessel benchmark](scripts/benchmark_major_vessel_analysis.py) loads only the
bundled, SHA-256-verified asset and uses a fixed probe/profile input. Run it with:

```console
uv run python scripts/benchmark_major_vessel_analysis.py --iterations 20
```

One run on 2026-07-22 used an Apple M4 (`Mac16,13`, arm64), macOS 26.5.2, and CPython
3.12.13. The asset contained 71,313 points, 11,818 runs, and 59,495 segments. V3 selected
243 candidates, performed exactly 243 narrow-phase measurements, and reported 153 loaded-geometry
conflicts. Timings were:

| Measurement | Milliseconds |
| --- | ---: |
| Verified asset load and analysis-geometry construction | 44.205 |
| First analysis after load | 27.283 |
| Warm analysis median, 20 iterations | 28.656 |
| Warm analysis P95, 20 iterations | 45.697 |

Python/module startup is excluded. The benchmark enforces `--iterations` in `[5,100]`, verifies
the bundled asset counts and digest, rejects changing outputs across identical runs, and emits the
machine, Python, geometry, result counts, and timings as JSON. These measurements are one-machine
engineering evidence, not a cross-hardware latency guarantee or scientific/surgical validation.

## Archived evidence paths

The Kim 2022 population vascular-length-density field and user subject-image registration remain
in the Python backend for reproducibility of older work. They are absent from the primary UI and
do not feed the LAMBADA geometry or V3 analysis. A scalar density projection contains no
individual vessel path/radius; a registered image is not automatically a vessel segmentation.

## Required evidence before qualification

1. Independent review of every NP1 source-derived dimension and site coordinate.
2. Repeated-observer subject calibration studies with declared ground truth.
3. Phantom and histology studies for planned versus achieved probe paths and sites.
4. Subject-specific vascular ground truth and a study of reference-graph failure modes.
5. Prospectively defined margin/uncertainty criteria and sensitivity analyses.
6. Formal animal-workflow usability, accessibility, interruption, and recovery studies.
7. Deterministic runtime packaging, SBOM, signing/notarization, and clean-Mac qualification.

Passing repository tests or rendering a complete scene does not satisfy these scientific gates.
