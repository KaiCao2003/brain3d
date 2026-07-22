# LAMBADA P60_606 major-vessel reference

The application bundles a compact display derivative of the atlas-registered P60_606 graph
from Renier, de Launoit, and Skriabine's *Vascular graphs of the developing post-natal mouse
brain*. The source is [Zenodo record 18876865](https://zenodo.org/records/18876865), DOI
`10.5281/zenodo.18876865`, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The associated Cell paper is DOI
[`10.1016/j.cell.2026.03.013`](https://doi.org/10.1016/j.cell.2026.03.013).

This is an animal-research reference layer. It is not a medical device, a subject image, or a
live vascular measurement. It cannot establish subject-specific clearance or trajectory
suitability.

## Current application use

The integrity-checked runs and radii are shown in three representations of the same reference:

- only radius-bearing portions intersecting the current coronal, sagittal, or horizontal slab;
- a Dorsal depth-collapsed reference projection; and
- tapered SceneKit tubes over the 3D Allen brain mesh.

The primary UI does not add capillaries or infer artery/vein identity. Population density and
subject-image registration remain archived backend paths and are not substituted for these runs.

For a selected probe, algorithm `major-vessel-aabb-tapered-surface-v2` minimizes separation from
the conservative probe envelope to the linearly tapered vessel surfaces. It then applies the
operator's declared required margin and registration uncertainty. Analysis requires separate
acknowledgement of those lab-defined inputs and of this reference's incomplete coverage. Its
bounded zero-conflict wording is:

> No conflict detected within the loaded geometry and stated uncertainty assumptions.

## Bundled derivative

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

The loader verifies the manifest and NPZ identities, inventory, dtypes, shapes, bounds, radius
threshold, run lengths, edge ordering, and total path length. It then exposes immutable physical
ASR coordinates in micrometres. Rendering and interaction code should obtain region identity
from the installed Allen annotation at the displayed point rather than treating the source's 65
coarse annotation IDs as exact leaf labels.

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

The reviewed output is:

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

## Mandatory interpretation limits

- Animal research use only; this derivative is not a medical device and is not validated for
  surgery.
- The source is an atlas-registered fixed and cleared P60 mouse-brain reference, not live or
  subject-specific vasculature.
- Pial and choroidal vessels were removed by the source workflow. This derivative also
  suppresses points below a 15 µm radius, so missing vessels are expected.
- Registration error, tissue distortion, biological variation, and omitted vessels are not
  bounded by this graph.
- The exact sex and sampled side of P60_606 are unpublished. No artery-versus-vein identity is
  available.
- The source workflow corrected endpoints, linearly reconnected nearby endpoints, and removed
  short terminal offshoots. Some paths are reconstructed rather than directly observed.
- Radii use the source's mean atlas-resampling scale, not a local Jacobian correction, and fixed
  cleared tissue may be distorted.
- Out-of-bounds points are omitted without clipping or interpolation.
