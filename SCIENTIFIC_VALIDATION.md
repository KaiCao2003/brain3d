# Scientific Validation Status

- Snapshot date: 2026-07-21
- Scope: current SwiftUI/Python hybrid, one cached `allen_mouse_25um` package, and the pinned
  Mendeley population-density source
- Status: bounded engineering and data-integration validation only

> **No surgical-accuracy claim:** Mouse Brain Surgery Planner is limited to mouse
> animal-research planning and must never be used for a human or clinical procedure. It has not
> been validated for stereotaxic targeting accuracy, animal-to-atlas registration accuracy,
> subject-specific vessel clearance, hardware placement, histological outcome, or veterinary
> care. It is not a certified navigation or medical device. Independently verify every coordinate
> before every animal procedure.

The normative coordinate rules are in [ADR-002](docs/ADR-002-coordinate-conventions.md), with
worked examples in [Coordinate Systems](COORDINATE_SYSTEMS.md). This document deliberately keeps
software checks, source-data checks, and biological validation separate.

## What “validated” means here

| Level | Present status | Meaning |
| --- | --- | --- |
| Mathematical and protocol contract | Covered by deterministic Python and Swift tests | Declared bounds, signs, identities, framing, serialization, and fail-closed rules behave as asserted |
| Native application contract | Exercised through the SwiftUI app with the Python service | The supported shell can display real atlas images, register a test subject image, composite layers, and save/reopen a project |
| Real `allen_mouse_25um` integration | Passed within the bounded evidence below | Package `1.2` metadata, arrays, hierarchy, slices, and selected meshes were exercised on one host |
| 10 µm integration | Out of current scope | The runtime rejects this identity; existing cache data is ignored and left untouched |
| Pinned population-density source identity | Exact archive and member identities are enforced | Changed byte count, SHA-256, member name, header contract, atlas binding, or safety semantics fail closed |
| Population-density biological validity | Not independently validated | The published scalar field is accepted as a cited population reference, not proven complete or suitable for an individual animal |
| Subject-image biological registration | Not validated | Landmark mathematics and persistence are tested; no animal ground truth establishes anatomical accuracy |
| Bregma target projection | Locked | Exact AP/ML/DV input may be stored, but no atlas projection or navigation claim is permitted without calibration |
| Surgical/biological accuracy | Not tested; no claim permitted | There are no prospective animal, phantom, histology, targeting-error, clearance, or outcome data |

Passing an implementation check establishes consistency with a declared software/data contract.
It does not establish that an atlas label is independently correct, that a density maximum is a
vessel path, that a user image is segmented, or that an implant will reach a target safely.

## Current spatial-operation boundary

| Operation | Engineering evidence | Scientific boundary |
| --- | --- | --- |
| BrainGlobe continuous voxel ↔ physical ASR µm | Round-trip, half-open bounds, and real 25 µm lookup checks | Implementation precision is not anatomical accuracy |
| Atlas point ↔ coronal/sagittal/horizontal/dorsal image | Synthetic mapping tests and real-array rendering | Screen orientation is not an independent laterality validation |
| Subject pixel ↔ atlas dorsal AP/ML | Similarity/affine validation, residual calculation, explicit laterality gate, save/reopen checks | Residuals do not prove biological correspondence or vessel identity |
| Population density → dorsal transparent overlay | Pinned source contract, atlas-template alignment gate, deterministic scalar projection/render tests | A DV maximum loses depth and cannot represent vessel paths or clearance |
| Bregma-relative AP/ML/DV entry → project storage | Strict decimal parsing, sign semantics, schema/persistence tests | Stored target remains unprojected and unusable for navigation |
| Bregma target → Allen atlas point | No calibration selected | **Locked; no coordinate may be invented** |
| Probe/trajectory ↔ vasculature | No validated subject 3D vessel graph or clearance model | **Not implemented or tested for navigation** |
| 3D native rendering | Bridge protocol v1 exposes no renderer | **Unavailable in the supported SwiftUI shell** |

## Real 25 µm atlas evidence

The reviewed identity is:

| Contract item | Observed value |
| --- | --- |
| Atlas | `allen_mouse_25um`, BrainGlobe package `1.2` |
| BrainGlobe library | `brainglobe-atlasapi==2.3.1` |
| Orientation/order | `asr`, array order `[AP,DV,ML]` |
| Shape | `(528,320,456)` voxels |
| Resolution | `(25,25,25)` µm |
| Half-open physical extent | `(13200,8000,11400)` µm |
| Reference | `uint16`, 154,091,520 raw bytes |
| Annotation | `uint32`, 308,183,040 raw bytes |
| Combined raw arrays | 462,274,560 bytes, excluding overhead |
| Source annotation | `annotation/ccf_2017` |
| Structure hierarchy | 840 records in the observed package |

Locally observed file identities from the cached package are retained as reproducibility evidence:

| Local file | Bytes | Locally observed SHA-256 |
| --- | ---: | --- |
| `metadata.json` | 423 | `119132150055826484fa75a4dc17c476d02251c0db8b4d0b7b28f6b8c4b8ae60` |
| `reference.tiff` | 154,179,306 | `7dba42462447e49f882f8df60a5ee4de2be7a2f22ae3d18a8186def20ded5e0e` |
| `annotation.tiff` | 308,270,826 | `52775c6086ae6aa7d9df2ad2c9e5ab9ce36effa09f5355c7c45efeada6647e06` |
| `meshes/997.obj` | 4,728,758 | `69fbcd1d452cdbdd6f6f493563a8aa4c5d9e574e073c06650cbaaf4dd4ac25a9` |
| `meshes/382.obj` | 569,447 | `e1cab6e109abf820208ac5190d10241d3d03536ba4666e6425cd40cd718c26ba` |

These hashes were not published or signed by BrainGlobe or Allen. They identify the inspected
local files but do not authenticate the upstream atlas or prove anatomical truth.

Real midpoint slices matched the declared mappings:

| View | Fixed index | Display axes | Shape |
| --- | ---: | --- | --- |
| Coronal | AP 264 | rows DV, columns ML | `(320,456)` |
| Sagittal | ML 228 | rows DV, columns AP | `(320,528)` |
| Horizontal | DV 160 | rows AP, columns ML | `(528,456)` |
| Dorsal | first non-background DV boundary | rows AP, columns ML | `(528,456)` |

Real array access and structure lookups establish adapter consistency with this one package, not
independent anatomical landmark truth. The package is symmetric, so it cannot by itself validate
left/right display orientation.

## Pinned population vascular-density evidence

### Source and paper

The implemented reference is:

- Kim, Yongsoo (2022), *Cerebrovascular, pericyte, and neuronal cell type mapping data 2022*,
  [Mendeley Data v1, DOI 10.17632/stxvn5sv44.1](https://data.mendeley.com/datasets/stxvn5sv44/1),
  CC BY 4.0; and
- Wu et al., *Quantitative relationship between cerebrovascular network and neuronal cell types
  in mice*, Cell Reports 2022,
  [doi:10.1016/j.celrep.2022.110978](https://doi.org/10.1016/j.celrep.2022.110978),
  [PMCID PMC9271215](https://pmc.ncbi.nlm.nih.gov/articles/PMC9271215/).

The deposit supplies a brain-wide vascular **length-density** field based on four fixed adult
C57BL/6 mice and a 100 µm local window. It is not the separate simulation-ready graph deposit and
does not contain individual vessel paths.

### Accepted byte and spatial contract

| Item | Pinned value |
| --- | --- |
| Archive | `NVU_mapping_Adult_mouse_brain (1).7z` |
| Archive bytes | `311493514` |
| Archive SHA-256 | `c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe` |
| Density member | `Vascular_length_Brain-wide/Vessel_LengthDensity_P56.nii` |
| Density member bytes | `601920352` |
| Density member SHA-256 | `0a0cbdf62068783259a7f11f1e6f2992c57ff1678d0481c2ea36d64899ed4484` |
| Template member | `Vascular_length_Brain-wide/AllenCCF_template_20um-isotropic.nii` |
| Template member bytes | `300960352` |
| Template member SHA-256 | `3d3004f0de9410f6cadfd93ac08d78aaf4a2c504fd2c07275bd5064b6b0a7e0a` |
| Reviewed source grid | shape `(570,400,660)` in `[ML,DV,AP]`, 20 µm |
| Density units | `m/mm^3` |
| Prepared grid | `(264,160,228)` in `[AP,DV,ML]`, 50 µm |
| Atlas binding | exact `allen_mouse_25um` v1.2 metadata plus template correlation ≥ 0.99 |

The density NIfTI itself reports unit zooms, unknown units, and no qform/sform. The conversion
therefore does not pretend that header is self-describing: it validates the exact known caveat,
uses the pinned README/template contract, reverses AP as declared by the reviewed conversion, and
symmetrizes ML because source ML polarity is undocumented. A changed or ambiguous source fails
closed.

The displayed product is a transparent AP-by-ML **DV maximum projection** with an explicit scalar
window. Its alpha follows the windowed density and is zero outside the current nonzero Allen
annotation footprint. This projection deliberately discards DV location. It can visualize where
population density is relatively high in the cited field; it cannot locate an individual vessel,
establish diameter, compute a 3D distance, or certify clearance.

### Trust boundary

The implementation verifies exact source bytes and binds derived cache metadata to the open
atlas, preparation algorithm, and prepared-array SHA-256. Those checks answer “did the reviewed
bytes and declared conversion enter this result?” They do not answer “is there no vessel at this
animal's planned entry site?”

## Subject dorsal-image evidence

The native workflow has been exercised with a synthetic, test-only PNG through import,
SHA-256/dimension display, landmark entry, explicit laterality confirmation, zero-residual
similarity fit, dorsal composition, save, and reopen. This demonstrates the software path and
numeric persistence.

The same journey showed why source semantics matter: a normal RGBA image with an opaque black
background overlays that background too. The UI now calls the layer **Subject dorsal image** and
warns that import/registration does not validate vessel segmentation. A transparent,
independently reviewed vessel mask is preferable when only subject surface vessels should cover
the atlas.

No real-animal dorsal image, repeated observer landmark study, independent registration ground
truth, or histological correspondence has been used to establish accuracy. A synthetic zero-
residual fit is not biological evidence.

## Unprojected bregma-target evidence

The stored frame is explicitly `BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED`. Tests enforce finite,
strict decimal AP/ML/DV values, UUID identity, schema round trips, and the signs:

```text
AP+ anterior / forward      AP− posterior / back
ML+ right                   ML− left
DV+ dorsal / up             DV− deep / ventral
```

The model is fixed to `projected = false` and `usable_for_navigation = false`. This enables exact
record keeping without claiming an Allen transform. No test of storage can substitute for a
measured bregma/skull calibration.

## Native application evidence and historical Qt boundary

The supported path is the SwiftUI app plus the Python service. A native journey on the cached
25 µm atlas exercised dorsal/coronal/sagittal/horizontal views, subject-image registration and
overlay, save/reopen, backup-aware project loading, and unsaved-change prompts. Swift tests cover
typed bridge responses, strict population-density semantics, alpha-compositing requirements, and
termination policy decisions.

Git history contains earlier Qt/PyVista viewer tests and one historical normal-Cocoa Qt atlas
session. They motivated parts of the renderer and the ADR-004 migration, but the legacy code and
dependencies are no longer in the product package. Historical PyVista 3D evidence does not make
3D available in the SwiftUI bridge.

## Automated engineering gates

Run the exact release candidate from the repository root:

```bash
uv lock --check
uv sync --frozen --group dev
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
uv run --frozen pytest -q
swift test --package-path native/Brain3D
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
```

Pass counts, lint results, and signatures are release-engineering evidence, not biological sample
sizes or accuracy statistics. A release record must preserve the exact commit, tool versions,
platform, source/cache identities, full command output, and native user journey.

## Scientific and integration validation still required

| Missing evidence | Required before making the related claim |
| --- | --- |
| Independent annotation truth | Freeze non-boundary landmarks with independently reviewed expected Allen labels |
| Left/right visual orientation | Exercise asymmetric first-party fixtures through every supported view |
| Population-density reproduction | Independently reproduce the published processing and compare quantitative outputs |
| Individual-animal registration | Use ground-truth landmarks, repeated observers, failure criteria, and deformation/error analysis |
| Subject vessel segmentation | Validate against independently annotated images with declared sensitivity/specificity criteria |
| 3D subject vessel paths | Acquire and validate subject-specific depth, diameter, graph topology, and registration |
| Vessel clearance | Define probe geometry and uncertainty, then validate distance/intersection outputs against ground truth |
| Bregma/skull calibration | Define a named measured calibration with transform, units, atlas binding, residuals, and uncertainty |
| Surgical targeting | Prospective protocol, preregistered acceptance criteria, histological/equivalent ground truth, sample size, and statistical analysis |
| Human factors | Task-based usability tests for signs, laterality, warnings, overlays, invalid input, saving, and recovery |
| Release distribution | Bundled runtime, Developer ID/hardened-runtime signing, notarization, stapling, and clean-account tests |

## Acceptable language

Before calibration, acceptable target wording is:

> “Stored as an unprojected bregma-relative AP/ML/DV entry; not usable for navigation.”

For the vascular layer, acceptable wording is:

> “Symmetrized four-mouse population vascular length density, shown as a dorsal DV maximum
> projection; not subject-specific and not vessel paths.”

Unacceptable wording includes:

- “the application located bregma”;
- “the atlas coordinate is accurate to 25 µm”;
- “the red line is the animal's vessel” when it comes from population density;
- “no vessel is present” or “clearance is safe” based on either current overlay;
- “the subject image is segmented” merely because it was imported or registered; and
- “the trajectory will hit the target” based on unit tests or stored coordinates.

## Primary references

- [Mendeley Data v1 density deposit](https://data.mendeley.com/datasets/stxvn5sv44/1)
- [Wu et al. 2022 paper](https://doi.org/10.1016/j.celrep.2022.110978)
- [Open-access paper at PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9271215/)
- [ADR-002: Coordinate conventions and atlas provenance](docs/ADR-002-coordinate-conventions.md)
- [ADR-003: Atlas and external data sources](docs/ADR-003-atlas-and-data-sources.md)
- [ADR-004: SwiftUI shell with a Python scientific service](docs/ADR-004-swiftui-hybrid-shell.md)
- [Coordinate Systems](COORDINATE_SYSTEMS.md)
- [Third-Party Software and Data](THIRD_PARTY.md)
- [BrainGlobe stable implementation](https://github.com/brainglobe/brainglobe-atlasapi/tree/v2.3.1)
- [Allen CCFv3 publication](https://doi.org/10.1016/j.cell.2020.04.007)
- [Allen explanation for the absence of CCF bregma](https://community.brain-map.org/t/why-doesnt-the-3d-mouse-brain-atlas-have-bregma-coordinates/158)
