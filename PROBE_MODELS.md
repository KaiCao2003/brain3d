# Probe Model Sources and Review State

## Enabled catalog

The current catalog (`brain3d-probe-catalog-v2`) exposes two deliberately distinct entries:

| Model | Geometry state | UI requirement |
| --- | --- | --- |
| Neuropixels 1.0 NP1000 / `PRB_1_4_0480_1` | Complete source transcription; `source-transcribed-review-pending` | Explicit acknowledgement that independent review is pending |
| Generic linear test probe, one shank / 16 sites | Synthetic software-test geometry; `user-defined-unverified` | Explicit acknowledgement that it is not manufacturer geometry |

Neither entry is presented as independently verified hardware geometry. The catalog is restricted
to non-human animal-research planning.

## Neuropixels 1.0 transcription

The versioned NP1 model records one 10,000 µm × 70 µm × 24 µm shank, the manufacturer
175 µm chisel-tip description, and all 960 site coordinates. It preserves the distinct SpikeGLX
209 µm physical-tip-to-lowest-row-center measurement rather than conflating it with the tip
length. The site map uses 480 two-site hardware rows, 20 µm row pitch, alternating lateral
offsets, three banks, and the three source-identified reference electrodes.

The transcription is tied to four immutable source snapshots:

| Source | Recorded revision | SHA-256 |
| --- | --- | --- |
| [imec Neuropixels 1.0 specification](https://www.neuropixels.org/_files/ugd/328966_c5e4d31e8a974962b5eb8ec975408c9f.pdf) | PDF metadata creation date 2023-10-20; no printed revision identifier | `73feccebeadf45c8e7062028588a5b36e9da9f25d10b5d943f33389c3e791f6f` |
| [ProbeTable `probe_features.json`](https://raw.githubusercontent.com/billkarsh/ProbeTable/207f7bf424b0fa26f271700b970e27a58a9a1111/Tables/probe_features.json) | table 1.8, commit `207f7bf424b0fa26f271700b970e27a58a9a1111` | `6946867508341555960d0b8af2f8e88589f411fc5ff0e122371d377b71f6a3e4` |
| [SpikeGLX `IMROTbl.cpp`](https://raw.githubusercontent.com/billkarsh/SpikeGLX/d67bee45fa2635873456eb5d3f5e5a051690e64f/Src-imro/IMROTbl.cpp) | commit `d67bee45fa2635873456eb5d3f5e5a051690e64f` | `59fa29406dc3f6ad38195157d6ddfecbf3b348e13bc3bfd827f50231adbde704` |
| [SpikeGLX metadata coordinate definitions](https://raw.githubusercontent.com/billkarsh/SpikeGLX/d67bee45fa2635873456eb5d3f5e5a051690e64f/Markdown/Metadata_Help.md) | commit `d67bee45fa2635873456eb5d3f5e5a051690e64f` | `654706c021a6da502b10086390b22464567aad5a94ed0d77a4bc9a36c3b3637f` |

The manufacturer specification states research use only in non-human subjects. No PDF, diagram,
or manufacturer asset is bundled; the project independently encodes cited factual geometry.
Neuropixels is used only as a product/trademark identifier. This project is not affiliated with
or endorsed by imec or the Neuropixels consortium.

## Why review remains pending

Source transcription is not independent verification. No second human reviewer has checked all
960 coordinates and supporting dimensions against the cited artifacts or a physical probe. The
model therefore cannot advance to a reviewed status until that full-table comparison is recorded
with reviewer identity, date, findings, and resulting catalog digest.

The current software tests check schema, site count, coordinate rules, bank/reference mapping,
trajectory transforms, overlays, traversal, persistence, and stale-result rejection. Those tests
do not establish manufacturing tolerances, physical-probe conformance, insertion deformation, or
procedural accuracy.

## Calibrated placement geometry

Planning algorithm `calibrated-stereotaxic-probe-transform-v2` preserves the operator's exact
subject-stereotaxic azimuth, elevation, insertion depth, and axial rotation separately from the
derived atlas pose. It constructs entry, target, tip, insertion direction, and the probe's local
lateral/normal basis in the stereotaxic frame, then maps the complete pose through the same rigid
or similarity calibration. Shank offsets, site offsets, width, and thickness follow that mapped
basis and uniform scale; they are not reconstructed from atlas-global ML after rotation.

Full affine calibration is rejected for probe planning because shear would turn a physical
rectangular cross-section into a different envelope. Legacy v1 plans must be explicitly updated
before region or vessel analysis; their previously derived geometry is never treated as current.

## Adding another hardware model

Any additional model needs a stable ID/version, exact product revision, pinned primary sources
and digests, units and local frame, complete shank/tip/site geometry, license review, an independent
transcription review, and schema/render/transform tests. Ambiguous or partial dimensions remain
disabled; they are never estimated from a screenshot or inherited from a related product.
