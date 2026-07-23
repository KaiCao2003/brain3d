# VesSAP BL6J-no1 major-vessel reference

## Decision

**Display-only GO:** Brain3D may display the pinned, bilateral BL6J-no1 derivative as an
ex-vivo C57BL/6J major-vessel reference.

**Clearance NO-GO:** the layer must not classify clearance, vessel absence, trajectory
suitability, navigation accuracy, or safety for an individual animal. It is one fixed and
cleared specimen, has no published landmark target-registration-error bound, and is not
registered to the operative animal's skull or bregma.

The runtime therefore exposes geometry and provenance but fails closed for clearance analysis.

## Pinned sources

The source is the VesSAP public repository release dated 2021-10-01 associated with Todorov et
al., *Machine learning analysis of whole mouse brain vasculature*,
[DOI 10.1038/s41592-020-0792-1](https://doi.org/10.1038/s41592-020-0792-1).
The public data-access record is [DISCO Technologies VesSAP](https://www.discotechnologies.org/VesSAP/).

The derivative manifest pins the aggregate source-bundle identity
`d0216b9f6fcec428845f8ecc24860b4838f27b6b69496a88d8b7ab0dcd1dbf8a`.

| File | Role | Bytes | SHA-256 |
|---|---|---:|---|
| `BL6J-no1_iso3um_stitched_skeleton.nii.gz` | True source centerlines | 114,305,865 | `1ea1a489dfacfa509f60d984ee955e43107a579d181bb5e6f3df51da6b68beac` |
| `BL6J-no1_iso3um_stitched_radius.nii.gz` | Euclidean-distance radius values on the centerlines | 136,114,699 | `6a8728d4518957c0e84687b077a76e64362edc9644c6e2adce60c2c244d4b887` |
| `elastix_atlas_registration_parameters.7z` | Published BL6J-no1 Euler plus B-spline transform | 38,472 | `ab2509e07dcab65f176b72337624fa2ccc38f9e32f17530964ed17af5e1e88ad` |
| `BL6J-no1_iso3um_stitched_atlas_registration_result.nii.gz` | Signed-label validation only; not bundled | 320,422,938 | `c3b9904ba95f8566b7161fd0f197cfe064ee0c5cfb24d49e553bc9c8793677c1` |
| `C57BL_6_no1.zip` | VesselGraph node/edge and grouped-label validation only; not bundled | 353,177,007 | `41d4d9d44e4b04190d7f1039615fb08e58aacd707d6d0baffb6c4090162d236f` |
| `C57BL_6_no1_raw.zip` | Raw VesselGraph endpoint-feature validation only; not bundled | 348,965,728 | `2bfd91617100085fd869b5e20970c46c6a1120b2474f78b34b634231e98ccae9` |

The independent 10 µm label check used BrainGlobe `allen_mouse_10um` version 1.2,
shape `[1320, 800, 1140]`, orientation `asr`, annotation SHA-256
`9f04278b0e539c88029b7caafa1b9fffed1cd2bf8a4e587903a823e182ce2ab4`.
The shipped display geometry is bounded against `allen_mouse_25um` version 1.2,
shape `[528, 320, 456]`.

## Exact transform interpretation

For a source skeleton voxel `g = [x, y, z]`, form the Elastix fixed physical point
`p = 0.1 * g`. Apply the published Euler transform followed by the B-spline transform and
call the Transformix physical result `T = [T_x, T_y, T_z]`.

The moving atlas order is `[ML left-to-right, AP, DV]`. BrainGlobe ASR order is
`[AP anterior-to-posterior, DV superior-to-inferior, ML right-to-left]`, so ML must be
reflected:

```text
AP_um = 30 * T_y
DV_um = 30 * T_z
ML_um = 11390 - 30 * T_x
```

Equivalent continuous atlas indices are:

```text
10 um: [AP, DV, ML] = [3*T_y, 3*T_z, 1139 - 3*T_x]
25 um: [AP, DV, ML] = [1.2*T_y, 1.2*T_z, 455.6 - 1.2*T_x]
```

Use the atlas voxel-center conversion when discretizing. A no-flip ML interpretation swaps
biological left and right even though the symmetric Allen annotation cannot reveal that error
from unsigned region labels alone.

## Path-preserving extraction

The graph CSV files contain endpoints, path length, curveness, and radius summaries, but no
intermediate centerline coordinates. They cannot preserve vessel paths. Among the 371,759 graph
edges with average radius at least five source voxels, 30.72% have curveness above 1.10 and the
99th-percentile chord-versus-path length deficit is 38.5 µm; drawing endpoint chords is rejected.

The bundled derivative instead follows this pinned procedure:

1. Read the same-grid uint8 skeleton and radius volumes, each
   `2804 x 3661 x 2012` at 3 µm sampling.
2. Retain skeleton voxels with radius at least five voxels: nominal radius at least 15 µm and
   diameter at least 30 µm. Capillaries and smaller vessels are intentionally excluded.
3. Recover 26-neighbour adjacency in source space before any transform.
4. Transform retained source points with the published BL6J-no1 transform and the reviewed ML
   reflection above.
5. Coalesce on a 50 µm display grid. Retain only edges induced by source adjacency; never join
   points merely because their target bins are adjacent.
6. Store the mean continuous transformed coordinate per occupied display bin and the maximum
   retained source EDT radius multiplied by 3 µm.

The source skeleton and radius supports match exactly: 58,313,813 nonzero centerline voxels and
zero support mismatches across 20,654,073,328 source voxels. The radius threshold retains
1,262,706 source points.

## Bundled derivative identity

| Property | Pinned value |
|---|---|
| File | `vessap_bl6j1_major_vessels_50um_v1.npz` |
| Asset ID | `vessap-bl6j-no1-major-vessels-50um-v1` |
| Extraction algorithm | `vessap-bl6j1-major-skeleton-50um-v1` |
| Bytes | 1,853,131 |
| SHA-256 | `9300dacf25ca57a5d23377ca0dc885e34ff0d18e8d21ef7590c6dcd156cf5db7` |
| In-bounds threshold points | 1,258,140 |
| Occupied 50 µm display voxels | 198,262 |
| Omitted isolated display voxels | 63,320 |
| Output points | 196,377 |
| Output runs | 76,622 |
| Output segments | 119,755 |
| Output path length | 3,817,312.085 µm |

The adjacent JSON manifest, the NPZ, and
`src/mouse_brain_planner/assets/vasculature/VESSAP_DATA_LICENSE.txt` are one evidence package.
The loader checks filename, byte count, SHA-256, member inventory, array types/shapes, transform
identity, extraction statistics, bounds, radius threshold, and mandatory limitations before
returning geometry.

## Independent validation

- Twenty thousand deterministic, evenly spaced nodes were sampled from 3,820,133 graph nodes.
- Correct `[T_y, T_z, T_x] -> [AP, DV, ML]` AP/DV orientation achieved 98.5025% non-background
  grouped-region agreement before subvoxel adjustment; the strongest incorrect AP/DV
  orientation achieved 20.8207%.
- With the required ML reflection, 10 µm agreement was 18,664/18,765 = 99.4618% for
  non-background nodes and 17,505/17,585 = 99.5451% after also excluding root and fiber tracts.
- Corrected 25 µm non-background agreement was 97.8524%; 99.705% of sampled transformed points
  were within the 25 µm atlas bounds.
- Direct comparison of the official signed registered-atlas NIfTI with the independently loaded
  `atlas_processed` labels agreed at 18,761/18,765 = 99.9787% non-background sampled nodes.
- The official signed registered annotation supplied 19,429 nonzero labels: 8,985 left and
  10,444 right. The canonical midline classified 19,425/19,429 = 99.9794%; all four discrepancies
  were within 5.38 µm of the midline. The best empirical separator classified
  19,428/19,429 = 99.9949%. This proves the required ML reversal.
- At 1,000 sampled nodes, finite-difference transform Jacobian determinants were
  1.269–2.451 with no sampled fold; singular values were 0.672–1.560. The large anisotropy is
  another reason a scalar source radius cannot become a surgical clearance bound.
- On 2,000 graph nodes, 93.85% were within `sqrt(3)` source voxels of the official skeleton and
  98.2% within three voxels, supporting common spatial identity while confirming that graph
  endpoints are not substitutes for the voxel paths.

These checks qualify transform interpretation, laterality, source identity, and deterministic
derivation. They do **not** independently bound biological registration error.

## Mandatory limitations

- Animal research use only; not a medical device.
- One fixed, cleared adult C57BL/6J brain, not the current animal or live vasculature.
- No numeric registration-error, tissue-clearing-distortion, bregma, or skull-registration bound.
- No artery-versus-vein identity; pial and choroidal coverage is not separately classified.
- The 50 µm display reduction can merge close paths and omits isolated target voxels without a
  retained segment.
- A displayed path does not establish its location in the current animal; a missing path does
  not establish vessel absence.
- Clearance, conflict, safe-entry, and trajectory-suitability conclusions remain disabled.

## Separate data license

The source data and this adapted derivative are licensed
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). They are not relicensed by
Brain3D's source-code license. Redistribution must preserve the VesSAP attribution, paper DOI,
release identity, exact source and derivative digests, this limitations record, and the bundled
license text. Commercial use requires separate authorization from the rights holders.
