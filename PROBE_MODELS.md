# Probe Model Sources and Review State

## Enabled catalog

The production catalog (`brain3d-probe-catalog-v6`) exposes exactly two entries:

| Model | Geometry state | UI requirement |
| --- | --- | --- |
| Neuropixels 2.0 `NP2003` / one shank | Complete 1,280-site source transcription; `source-transcribed-review-pending` | Persistent warning; no per-plan geometry checkbox |
| Neuropixels 2.0 `NP2013` / standard four shanks | Complete 5,120-site source transcription; 384 simultaneous channels; `source-transcribed-review-pending` | Persistent warning; no per-plan geometry checkbox |

The former combined NP2003/NP2004 and NP2013/NP2014 identities, Quad Base, Neuropixels 1.0,
and the generic fixture remain archived exact definitions for old-project compatibility and test
evidence. They are not returned by `probe.catalog.list` and cannot appear in the new-plan
selector. No entry is presented as independently verified hardware geometry. The catalog is
restricted to non-human animal-research planning.

## Neuropixels 2.0 transcription

The two supported NP2 choices record:

- `NP2003`: one 10,000 µm × 70 µm × 24 µm shank with 1,280 sites;
- `NP2013`: four such shanks at 250 µm pitch with 5,120 sites total and
  384 simultaneously configurable recording channels across the probe.

Cap, cable, headstage, and base-electronics geometry remain outside trajectory geometry. Catalog
ID `shank-0` is user-facing **Shank 1** and is the AP/ML surface anchor and distal depth target;
the coordinate is not an array midpoint. The other catalog shanks retain +250, +500, and +750 µm
probe-local offsets. In the `Sagittal` layout this makes Shank 1 most anterior and the other three
extend posterior. After `90° CW` as viewed dorsally, Shank 1 is animal-left-most and the others
extend toward animal right. Layout rotates the complete array, not individual shanks.

Each shank uses 640 rows with two 12 × 12 µm sites per row. Site-center coordinates use the
source-backed 206 µm physical-tip-to-lowest-row-center distance, 15 µm axial row pitch, and
lateral centers −8/+24 µm in the 70 µm shank frame. The 206 µm site-center offset is distinct
from the manufacturer’s 175 µm physical chisel-tip length. The large tip reference electrode is
not one of the 1,280 addressable recording sites and is not invented as a point site.

The catalog describes all physical/addressable sites, not one acquisition configuration.
Both supported hardware choices expose 384 simultaneous channels. Brain3D does not currently
import an experiment's IMRO/electrode selection, so region analysis covers every physical site
and must not be described as the set recorded simultaneously.

The transcription is tied to exact retrieved artifacts:

| Source | Recorded revision | SHA-256 |
| --- | --- | --- |
| [imec Neuropixels 2.0 data sheet](https://www.neuropixels.org/_files/ugd/328966_2b39661f072d405b8d284c3c73588bc6.pdf) | PDF metadata modification date 2024-09-18; no printed revision identifier | `bcd5a24e0f91c23c665f4fddfaad06ef6a8a1278a248ec3f5b4ebf17f1d0f6eb` |
| [imec Neuropixels 2.0 User Manual V1.0.6 archive](https://www.neuropixels.org/_files/archives/328966_021470f37e3a4a4a88a256ab11639765.zip?dn=Neuropixels_2-0_User_Manual_V1-0-6.zip) | V1.0.6 | `99677abe3e052636894934170d7d70c12e327433e3749b38213f74ff7772d0a8` |
| [imec electrode-channel mapping](https://www.neuropixels.org/_files/ugd/328966_43eea6555fa94a5bb1ddb51f00696fc3.xlsx?dn=Neuropix_2_0_Electrode-Channel-mapping.xlsx) | Retrieved 2026-07-23 | `85c1236e512be518f6706256c24a214fab7ff238e993149e242fd5ad69ba167f` |
| [ProbeTable `probe_features.json`](https://raw.githubusercontent.com/billkarsh/ProbeTable/207f7bf424b0fa26f271700b970e27a58a9a1111/Tables/probe_features.json) | table 1.8, commit `207f7bf424b0fa26f271700b970e27a58a9a1111` | `6946867508341555960d0b8af2f8e88589f411fc5ff0e122371d377b71f6a3e4` |
| [SpikeGLX `IMROTbl.cpp`](https://raw.githubusercontent.com/billkarsh/SpikeGLX/d67bee45fa2635873456eb5d3f5e5a051690e64f/Src-imro/IMROTbl.cpp) | commit `d67bee45fa2635873456eb5d3f5e5a051690e64f` | `59fa29406dc3f6ad38195157d6ddfecbf3b348e13bc3bfd827f50231adbde704` |
| [imec Neuropixels 2.0 Quad Base data sheet](https://www.neuropixels.org/_files/ugd/328966_4e39ab2e46424dc9b3efa446d286ab0f.pdf) | PDF metadata modification date 2025-06-16; Quad Base entry only | `9a0b4566979acbad751c8f4fb72405f77e170e3963f16d1852709c83ce57c7a9` |

The official documents restrict Neuropixels probes to research use in non-human subjects. No
source PDF, workbook, drawing, or manufacturer asset is redistributed; Brain3D independently
encodes the cited factual geometry.

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
NP1 or NP2 coordinates and supporting dimensions against the cited artifacts or physical probes.
The models therefore cannot advance to a reviewed status until those full-table comparisons are
recorded with reviewer identity, date, findings, and resulting catalog digest.

The current software tests check schema, site and shank counts, coordinate rules, bank/reference
mapping, multi-shank offsets, trajectory transforms, overlays, traversal, persistence, and
stale-result rejection. Those tests do not establish manufacturing tolerances, physical-probe
conformance, insertion deformation, or procedural accuracy.

## Direct atlas-surface placement geometry

Planning algorithm `pinpoint-atlas-surface-ap-ml-depth-v4` persists AP/ML from the named
Pinpoint/Urchin profile, Shank 1's exact local annotation-surface crossing, the positive path depth
from that crossing to Shank 1's distal target, one signed sagittal angle, and layout. AP− is
posterior and ML− is animal-left. Positive angle advances A→P; negative advances P→A. NP2013
layout `0°` places its shank-spacing axis in the sagittal plane with Shank 1 most anterior, and
`90°` rotates the whole array clockwise from dorsal with Shank 1 animal-left-most. Shank offsets,
site offsets, width, and thickness follow the derived local basis.

Every supported NP2 shank is modeled as the full 10,000 µm proximal-to-distal shaft. At insertion
depth `d`, its proximal remainder is `10,000 − d` µm opposite the insertion direction from the
surface plane and can lie outside the brain/atlas. The surface-to-distal-target segment remains a
separate implanted path for slice overlays, annotation traversal, and path analysis; rendering the
full shaft does not redefine insertion depth.

The direct v4 path does not require target registration or subject calibration; its named
population-atlas assumption and annotation digest are stored and revalidated instead. This does
not establish current-animal correspondence. Calibrated v1–v3 records remain preserved with
their original target, angle, roll, and calibration semantics. Legacy v1 plans must be explicitly
updated before region analysis or any future qualified vessel analysis. Archived synthetic vessel
tests do not make that analysis available in the product.

## Adding another hardware model

Any additional model needs a stable ID/version, exact product revision, pinned primary sources
and digests, units and local frame, complete shank/tip/site geometry, license review, an independent
transcription review, and schema/render/transform tests. Ambiguous or partial dimensions remain
disabled; they are never estimated from a screenshot or inherited from a related product.
