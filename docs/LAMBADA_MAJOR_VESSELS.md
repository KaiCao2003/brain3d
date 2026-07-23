# LAMBADA P60_606 archived derivative and rejected qualification

The repository retains a compact evidence derivative of the atlas-registered P60_606 graph
from Renier, de Launoit, and Skriabine's *Vascular graphs of the developing post-natal mouse
brain*. The source is [Zenodo record 18876865](https://zenodo.org/records/18876865), DOI
`10.5281/zenodo.18876865`, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The associated Cell paper is DOI
[`10.1016/j.cell.2026.03.013`](https://doi.org/10.1016/j.cell.2026.03.013).

This derivative is not an application layer, a medical device, a subject image, or a live
vascular measurement. It cannot establish subject-specific clearance or trajectory suitability.

## Runtime status

Coordinate qualification is rejected. The current runtime does not load, serve, display, mirror,
or analyze the P60_606 derivative. The production `auditedReferenceMajorVessels` capability and
reference metadata/geometry endpoints now belong exclusively to the separately qualified VesSAP
BL6J-no1 display reference. `radiusAwareReferenceVesselAnalysis` remains absent and clearance
analysis fails with `VESSEL_ANALYSIS_UNAVAILABLE`.

No geometry from this derivative may appear in a slice, Dorsal, or 3D view. It cannot support a
probe/vessel intersection, margin, distance, conflict, no-conflict, or surgical-clearance claim.

## Coordinate and coverage qualification

The reproducible qualification reran the exact extraction against the exact pinned source graph
and tested coordinate orientation against the exact BrainGlobe `allen_mouse_25um` v1.2
annotation. AP and DV orientation evidence passed. Qualification still failed for two independent
reasons:

1. The primary source describes the specimens as mouse brain hemispheres, so the specimen does
   not establish whole-brain coverage.
2. The exact P60_606 graph contains no persisted graph, vertex, or edge property that binds the
   numerical ML axis to biological hemisphere/laterality.

Points occur numerically on both sides of the atlas-array midpoint, but that is not evidence that
the source represents both biological hemispheres. No trustworthy source documents a permitted
mirror transform for this exact specimen. The application therefore does not choose an ML sign,
infer the sampled side, or mirror the derivative.

The canonical report is
[`docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json`](evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.
Its blocking reason codes are `SOURCE_HEMISPHERE_PROPERTY_MISSING` and
`SOURCE_SPECIMEN_COVERAGE_IS_HEMISPHERE`; `qualifiedMapping` is null.

## Sources rejected for subject-clearance integration

No audited source met all five requirements for subject-clearance integration: downloadable
major-vessel centerlines/radii, an
explicit Allen 25 µm transform, biological laterality, a documented CCF-to-bregma relationship,
and terms that permit the required redistributed derivative.

| Candidate | Why it is not integrated |
| --- | --- |
| [Mendeley `mjtyry6v85.1`](https://data.mendeley.com/datasets/mjtyry6v85/1) | The graph coordinates are raw specimen-space XYZ without qualified orientation, laterality, Allen registration, or bregma relationship. |
| [Mendeley `stxvn5sv44.1`](https://data.mendeley.com/datasets/stxvn5sv44/1) | This is an averaged four-mouse 20 µm population vessel-length-density NIfTI, not major-vessel centerlines/radii; population/capillary-density display is outside the planner's accepted scope. |
| [Hinz et al. 2021](https://www.biorxiv.org/content/10.1101/2021.10.21.465264v1) | Geometry is in a study-specific 78 µm MRI template with no Allen/bregma transform, and CC BY-NC-ND terms do not permit the required transformed redistribution. |
| [Xiong et al. 2017](https://www.frontiersin.org/journals/neuroanatomy/articles/10.3389/fnana.2017.00128/full) | Named vessels are documented, but no downloadable graph or CCF transform is provided. |

These are rejected alternatives, not integrated data. VesSAP is separately accepted only for a
display reference; it does not meet the subject/bregma/error-bound requirements for clearance. A
future clearance source must be audited against the same requirements before any analysis
capability can be advertised.

## Archived derivative

The 12.28 GB extracted graph and its 5.05 GB archive are not committed. The bundled NPZ is
814,393 bytes with SHA-256
`fb2344e845e604be3424bd63f4222d273eafba34db0df2eaff32f4400fa9afec`.
Its adjacent manifest records source identity, attribution, schema, extraction version, array
shapes, output statistics, and the mandatory limitations checked by the runtime loader.

The derivative contains five arrays:

| Array | Meaning |
| --- | --- |
| `points_asr_voxel_f32 [71313,3]` | Continuous Allen 25 µm coordinates in BrainGlobe `[AP,DV,ML]` order |
| `radii_um_f32 [71313]` | Approximate source radius in micrometres |
| `source_annotation_ids_i32 [71313]` | Coarse source ancestor IDs; not a replacement for current atlas lookup |
| `run_offsets_i64 [11819]` | End-exclusive boundaries for 11,818 independent polylines |
| `source_edge_indices_i32 [11818]` | Serialized source edge index for each polyline |

The archived loader can verify the manifest and NPZ identities, inventory, dtypes, shapes,
bounds, radius threshold, run lengths, edge ordering, and total path length. Those checks establish
deterministic bytes and extraction behavior; they do not qualify biological laterality or
whole-brain coverage and do not authorize runtime geometry access.

## Extraction rule

Algorithm `lambada-p60-606-major-runs-v1` applies the following rule independently to every
source edge:

1. Accept a point only when all three coordinates and its radius are finite.
2. Require ClearMap bounds `0 <= [c0,c1,c2] < [320,528,456]`.
3. Require physical radius at least 15 µm, equivalent to source `radii_atlas >= 0.6` at 25 µm.
4. Form maximal consecutive accepted blocks. Keep only blocks with at least two points.
5. Split and drop at rejected points. Never clip or interpolate coordinates.
6. Permute ClearMap `[c0,c1,c2]` to BrainGlobe ASR `[c1,c0,c2]`.
7. Convert continuous voxel coordinates using `physical_um = voxel * 25`, with no half-voxel
   shift.

The source edge maximum is used only as a conservative prefilter. Selection within an edge is
always pointwise. Keeping an entire edge whenever any point passes would retain 832,850.19 µm
of path, including 632,459.33 µm whose points fail the radius criterion. Selecting edges by
their mean radius would miss 5,597 edges that contain qualifying segments.

The reproduced derivative output is:

- 16,156 source edges pass the conservative edge-maximum prefilter.
- 78,048 source geometry points are finite, in bounds, and at least 15 µm in radius.
- 71,313 points form drawable runs; isolated qualifying points are omitted.
- 59,495 segments form 11,818 runs from 10,907 serialized source edges.
- Source-float64 retained path length is 200,390.862919 µm.

The source contains 292,368 atlas-coordinate points outside the reviewed array bounds, all past
the second-axis upper bound. They are not clamped back into the brain.

## Reproduction

The Zenodo-distributed archive identity is:

- filename: `P60_606_graph_2024-12-03.gt.7z`
- bytes: `5,050,194,723`
- SHA-256: `cc6d252ee57154f5bc0f06605a703253470a57c210d76e075831effa2098d66f`
- Zenodo MD5: `218ed346c6d7dc501301204f811be37f`

After extraction, the accepted graph identity is:

- filename: `606_graph_2024-12-03.gt`
- bytes: `12,282,574,483`
- SHA-256: `c2568cfbecd3f3eb720519be9d042f0cb41606741b8dd2f018bad1c54d36ef85`
- MD5: `b0bedc97ed2c6e00a41565649b3dd86b`

From the repository root, with that extracted file available locally:

```bash
uv run python scripts/extract_lambada_major_vessels.py \
  /absolute/path/to/606_graph_2024-12-03.gt
```

The script hashes the full source before reading any pinned binary offsets. It rejects any other
file, validates contiguous source edge ranges, asserts every reviewed extraction count, writes
NPZ members in a fixed order with fixed ZIP metadata, rebuilds the asset in a temporary
directory, and requires both builds to have identical bytes before writing the manifest.

To reproduce the separate qualification report, provide the exact extracted graph and exact
BrainGlobe atlas package directory:

```bash
uv run python scripts/qualify_lambada_coordinates.py \
  /absolute/path/to/606_graph_2024-12-03.gt \
  /absolute/path/to/allen_mouse_25um_v1.2 \
  --output /absolute/path/to/qualification.json
```

A rejected run exits nonzero by design. Compare its canonical bytes and SHA-256 with the checked-in
report; do not promote a locally edited or differently sourced report.

## Mandatory interpretation limits

- Evidence use only; this derivative is not displayed or analyzed and is not validated for
  surgery.
- The source is an atlas-registered fixed and cleared P60 mouse-brain reference, not live or
  subject-specific vasculature.
- Pial and choroidal vessels were removed by the source workflow. This derivative also
  suppresses points below a 15 µm radius, so missing vessels are expected.
- Registration error, tissue distortion, biological variation, and omitted vessels are not
  bounded by this graph.
- The primary record describes hemisphere specimens, while the exact graph has no persisted
  hemisphere/laterality binding. Whole-brain coverage and biological ML polarity are therefore
  unqualified, and mirroring is prohibited.
- No artery-versus-vein identity is available.
- The source workflow corrected endpoints, linearly reconnected nearby endpoints, and removed
  short terminal offshoots. Some paths are reconstructed rather than directly observed.
- Radii use the source's mean atlas-resampling scale, not a local Jacobian correction, and fixed
  cleared tissue may be distorted.
- Out-of-bounds points are omitted without clipping or interpolation.
