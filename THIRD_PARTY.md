# Third-party software, data, and prior art

This inventory was reviewed on **2026-07-23**. Exact direct pins come from `pyproject.toml`;
`uv.lock` is the machine-resolved transitive inventory. Before each release, generate an SBOM
from the final lock/build environment, retain all license texts and notices required by the
bundled artifacts, and reconcile it with this human-readable list.

The classification column is intentional:

- **Code — dependency / declared dependency:** code installed by the default environment. The row
  states when a package is reserved for later work rather than imported by the current workflow.
- **Data — downloaded:** separately governed content acquired at user request and not bundled.
- **Data — optional downloaded:** a reviewed source acquired only when the user enables the
  corresponding feature; it is cached outside the application bundle.
- **Data — bundled derivative:** an adapted data artifact shipped with the application under
  its own data license, attribution, immutable manifest, and scientific-use limitations. The
  application source-code license does not relicense it.
- **Candidate data:** a source reviewed for possible later work, but not integrated.
- **Cited source:** factual geometry or terminology was independently encoded with a pinned
  citation/digest; the upstream document, code, diagram, or binary is not copied or bundled.
- **Concept only:** documentation or workflow reviewed as prior art; no code or assets copied.

The supported interactive shell uses Apple SwiftUI/AppKit/SceneKit system frameworks and a
versioned subprocess bridge to the Python scientific service. SceneKit displays backend-validated
brain, probe, and display-only VesSAP vessel geometry payloads; archived LAMBADA vessel primitives
receive no runtime payload.
Scientific coordinate conversion and analysis remain in Python. The former PySide6/PyVista/VTK
application was removed from the package and lockfile after the Phase 1 reachability audit.

Surgery-plan export adds no third-party Swift document parser. Apple PDFKit/Core Graphics read
the user-prepared protocol PDF and 132-page `MBSC_Figs_with_Layers.pdf` directly, add fields,
preserve vector pages, assemble, and verify the result; SceneKit produces the offscreen 3D page.
Word, Illustrator, Apple Events automation, and document-conversion subprocesses are not part of
the export path.

## Direct runtime dependencies

| Package/version | License | Purpose | Classification / source |
|---|---|---|---|
| brainglobe-atlasapi 2.3.1 | BSD-3-Clause | Atlas discovery, download, metadata, arrays | Code — dependency; [PyPI](https://pypi.org/project/brainglobe-atlasapi/2.3.1/), [source](https://github.com/brainglobe/brainglobe-atlasapi/tree/v2.3.1) |
| nibabel 5.4.2 | MIT | Strict NIfTI header/data access for the pinned population-density source | Code — dependency; [PyPI](https://pypi.org/project/nibabel/5.4.2/) |
| numpy 2.5.1 | BSD-3-Clause | N-dimensional arrays | Code — dependency; [PyPI](https://pypi.org/project/numpy/2.5.1/) |
| platformdirs 4.11.0 | MIT | macOS application/cache paths | Code — dependency; [PyPI](https://pypi.org/project/platformdirs/4.11.0/) |
| pydantic 2.13.4 | MIT | Validated settings and project models | Code — dependency; [PyPI](https://pypi.org/project/pydantic/2.13.4/) |
| Pillow 12.3.0 | MIT-CMU | Image decoding, validation, and raster output | Code — dependency; [PyPI](https://pypi.org/project/pillow/12.3.0/) |
| scikit-image 0.26.0 | BSD-3-Clause | Similarity/affine registration of subject dorsal images | Code — dependency; [PyPI](https://pypi.org/project/scikit-image/0.26.0/) |
| scipy 1.18.0 | BSD-3-Clause | Population-density resampling and overlay operations | Code — dependency; [PyPI](https://pypi.org/project/scipy/1.18.0/) |
| tifffile 2026.7.14 | BSD-3-Clause | Validated atlas TIFF loading | Code — dependency; [PyPI](https://pypi.org/project/tifffile/2026.7.14/) |

## Build and test dependencies

These tools are not application features, but some are present in build environments or affect
the generated bundle.

| Package/version | License | Purpose | Source |
|---|---|---|---|
| hatchling 1.27.0 | MIT | Python build backend | [PyPI](https://pypi.org/project/hatchling/1.27.0/) |
| mypy 2.3.0 | MIT | Static type checking | [PyPI](https://pypi.org/project/mypy/2.3.0/) |
| pytest 9.1.1 | MIT | Test runner | [PyPI](https://pypi.org/project/pytest/9.1.1/) |
| pytest-cov 7.1.0 | MIT | Coverage integration | [PyPI](https://pypi.org/project/pytest-cov/7.1.0/) |
| ruff 0.15.22 | MIT | Linting and formatting checks | [PyPI](https://pypi.org/project/ruff/0.15.22/) |

## Material transitive dependencies

This is a review aid, not a substitute for the full lockfile/SBOM.

| Package/version | License | Why material | Source |
|---|---|---|---|
| brainglobe-space 1.0.3 | BSD-3-Clause | Atlas axis/orientation conversions | [PyPI](https://pypi.org/project/brainglobe-space/1.0.3/) |
| pandas 3.0.3 | BSD-3-Clause | BrainGlobe tabular dependency; not directly declared by this project | [PyPI](https://pypi.org/project/pandas/3.0.3/) |
| pyarrow 25.0.0 | Apache-2.0 | pandas columnar/serialization dependency in the resolved set | [PyPI](https://pypi.org/project/pyarrow/25.0.0/) |
| meshio 5.3.5 | MIT | Mesh-format support pulled by BrainGlobe AtlasAPI | [PyPI](https://pypi.org/project/meshio/5.3.5/) |
| pydantic-core 2.46.4 | MIT | Native validation engine bundled with Pydantic | [PyPI](https://pypi.org/project/pydantic-core/2.46.4/) |

## Downloaded data and cited prior art

| Item/version | Terms | Use in this project | Classification / source |
|---|---|---|---|
| Allen Mouse CCF via BrainGlobe `allen_mouse_25um`, atlas version 1.2 as observed 2026-07-21 | [Allen Institute Terms of Use](https://alleninstitute.org/legal/terms-of-use); scientific citation required | The only current reference/annotation/mesh atlas; downloaded on demand to user cache, never bundled in the `.app` or installer | Data — downloaded; [BrainGlobe version manifest](https://gin.g-node.org/brainglobe/atlases/raw/master/last_versions.conf), [generator/citation](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/atlas_scripts/allen_mouse.py) |
| Neuropixels 2.0 single- and four-shank geometry sources, snapshots recorded 2026-07-23 | Source-specific terms; the cited artifacts are not redistributed | Complete 1,280-site single-shank and 5,120-site four-shank factual transcriptions from imec specifications/manual/mapping, ProbeTable 1.8, and SpikeGLX. The production selector supports only `NP2003`/`NP2004` and standard `NP2013`/`NP2014`, both with 384 simultaneous channels. Quad Base source evidence is archived but not selectable. Status is `source-transcribed-review-pending`; no independent full-table review is claimed. | Cited sources; [imec NP2 product/support page](https://www.neuropixels.org/probe-2-0-single-shank), [exact sources and digests](PROBE_MODELS.md) |
| Neuropixels 1.0 NP1000 / `PRB_1_4_0480_1` geometry sources, snapshots recorded 2026-07-22 | Source-specific terms; the cited artifacts are not redistributed | Complete 960-site factual transcription from the imec specification, ProbeTable 1.8, and SpikeGLX geometry/metadata snapshots. The catalog status is `source-transcribed-review-pending`; no independent full-table review is claimed. | Cited source; [imec specification](https://www.neuropixels.org/_files/ugd/328966_c5e4d31e8a974962b5eb8ec975408c9f.pdf), [exact sources and digests](PROBE_MODELS.md) |
| Kim, Yongsoo (2022), *Cerebrovascular, pericyte, and neuronal cell type mapping data 2022*, Mendeley Data V1, DOI `10.17632/stxvn5sv44.1` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Optional pinned population vascular length-density field. Archive `NVU_mapping_Adult_mouse_brain (1).7z`, 311,493,514 bytes, SHA-256 `c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe`; downloaded to user cache and never bundled. The archived backend can prepare a symmetrized dorsal DV maximum projection, but it is absent from the primary UI, is not subject-specific, has no vessel paths, and is not used for clearance. | Data — optional downloaded; [versioned dataset](https://data.mendeley.com/datasets/stxvn5sv44/1), [Wu et al. Cell Reports paper](https://doi.org/10.1016/j.celrep.2022.110978), [open-access paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9271215/) |
| Renier, Nicolas; de Launoit, Elisa; Skriabine, Sophie (2026), *Vascular graphs of the developing post-natal mouse brain*, record DOI `10.5281/zenodo.18876865` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Packaged archived derivative evidence for specimen P60_606: maximal consecutive in-bounds graph runs with point radius at least 15 µm. NPZ is 814,393 bytes, SHA-256 `fb2344e845e604be3424bd63f4222d273eafba34db0df2eaff32f4400fa9afec`. The 5,050,194,723-byte source archive and 12,282,574,483-byte extracted graph are not bundled. Coordinate qualification is rejected because the source is a hemisphere and the graph lacks a persisted biological laterality binding. It is not displayed, mirrored, served, or analyzed. | Data — bundled derived evidence; [versioned Zenodo record](https://zenodo.org/records/18876865), [Cell paper](https://doi.org/10.1016/j.cell.2026.03.013), [derivation and qualification record](docs/LAMBADA_MAJOR_VESSELS.md) |
| Todorov et al. (2020), VesSAP BL6J-no1 whole-brain vasculature, public repository release 2021.10.01 | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | Bundled display-only major-vessel derivative from the official 3 µm skeleton and radius volumes. Source radius ≥5 voxels retains nominal diameter ≥30 µm; true 26-neighbour source adjacency is transformed with the published Euler plus B-spline registration and reduced on a 50 µm display grid. NPZ is 1,853,131 bytes, SHA-256 `9300dacf25ca57a5d23377ca0dc885e34ff0d18e8d21ef7590c6dcd156cf5db7`, with 196,377 points, 76,622 runs, and 119,755 segments. It is one fixed, cleared C57BL/6J specimen and cannot establish vessel absence, subject-specific clearance, trajectory suitability, or safety. | Data — bundled derivative; [VesSAP data record](https://www.discotechnologies.org/VesSAP/), [Nature Methods paper](https://doi.org/10.1038/s41592-020-0792-1), [exact derivation and validation](docs/VESSAP_MAJOR_VESSELS.md) |
| User-prepared Headplate Protocol PDF | Source-owner terms; not redistributed or relicensed | Read directly; pages 1–2 receive a flattened prefill overlay and the template's page-3 sketch placeholder is replaced. The source stays outside the repository and app bundle; its digest prefix is printed on planning pages. | External user-owned document |
| User-supplied Mouse Brain CD `MBSC_Figs_with_Layers.pdf`, Figures 1–132 | Source-owner terms; not redistributed or relicensed | Read directly. Brain3D validates all 132 landscape-Letter pages against the reviewed figure/coordinate catalog, verifies the source SHA, selects the nearest coronal AP or sagittal `|ML|` page, and adds an identity summary to the output copy. No atlas artwork is committed or bundled. | External user-owned data/artwork |
| brainrender 2.2.0 | BSD-3-Clause | Scene/API design review only; package not imported or bundled | Concept only; [release](https://github.com/brainglobe/brainrender/releases/tag/v2.2.0) |
| iblatlas 1.2.0 | MIT | Coordinate and trajectory design review only; package and PyQt5 GUI extra not imported or bundled | Concept only; [release](https://github.com/int-brain-lab/iblatlas/releases/tag/1.2.0) |
| Neuropixels Trajectory Explorer v2.0.0 | GPL-3.0 | Workflow review only; no code or assets copied | Concept only; [release](https://github.com/petersaj/neuropixels_trajectory_explorer/releases/tag/v2.0.0) |
| Pinpoint v2.0.0 | GPL-3.0 | Workflow review only; no Unity code or assets copied | Concept only; [release](https://github.com/VirtualBrainLab/Pinpoint/releases/tag/v2.0.0) |
| cortex-lab/allenCCF, including SHARP-Track, commit `e5a57fe7e1c9…` reviewed 2026-07-21 | No explicit repository license found | Workflow review only; no code or assets copied | Concept only; [repository](https://github.com/cortex-lab/allenCCF) |
| Simulation-ready vascular tracing data from adult mouse brains, version 1, DOI `10.17632/mjtyry6v85.1` | CC BY 4.0 | Rejected for planning integration. The four adult-mouse MATLAB graphs are separate from the archived scalar-density deposit, and their documentation exposes raw specimen-space XYZ without qualified axis orientation, laterality, Allen registration, or a bregma relationship. No graph file is integrated or bundled. | Rejected data candidate; [versioned dataset](https://data.mendeley.com/datasets/mjtyry6v85/1), [associated open-access paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9271215/) |
| VesselGraph | Software: MIT; data: CC BY-NC 4.0 | Vascular graph/data design review only; no code, models, or data copied; NC terms make the data unsuitable as an unrestricted redistributable default | Concept only; [repository and data terms](https://github.com/jocpae/VesselGraph) |
| VesSAP repository code | MIT | Segmentation and feature-extraction implementation reviewed as provenance; no VesSAP repository code or models are copied into Brain3D. The separately licensed data derivative is inventoried above. | Concept only; [repository](https://github.com/vessap/vessap) |

Allen atlas content is not relicensed by BrainGlobe's BSD-3-Clause software license. The Allen
terms observed on the review date limit covered Content to noncommercial research unless
otherwise stated. Show the source/terms before download and obtain legal review before any
commercial redistribution or hosted data service.

The Mendeley density is not relicensed by this application's source-code license. Preserve the
CC BY 4.0 attribution, dataset version/DOI, archive identity, and associated paper citation in any
scientific output that uses the layer. The dataset's four-animal population scope must remain
visible; attribution does not turn the scalar field into subject-specific vessels or a clearance
model.

The archived LAMBADA P60_606 derivative is likewise not relicensed by this application's
source-code license. Preserve its CC BY 4.0 attribution, versioned record DOI, source and asset
digests, adjacent manifest, rejected coordinate/coverage status, and fixed/cleared hemisphere
limitations in every distributed evidence package or scientific output that studies the asset.
Do not describe its presence in the package as a runtime vessel layer.

The bundled VesSAP BL6J-no1 derivative is not relicensed by this application's source-code
license. It remains CC BY-NC 4.0 adapted data. Keep the NPZ, adjacent immutable manifest,
`VESSAP_DATA_LICENSE.txt`, source/paper attribution, release identity, exact digests, transform
interpretation, and display-only limitations together. The noncommercial restriction applies to
the derivative independently of the application's original-source terms. Its presence must never be
described as subject-specific registration, vessel clearance, proof of vessel absence, or a
surgical safety determination.

## Release obligations

1. Build only from the reviewed lockfile and record Python, architecture, package, and atlas
   versions in release metadata.
2. Bundle required copyright notices and license texts for every exact release artifact.
3. Keep downloaded Allen and Mendeley data outside the signed application and installer;
   preserve each source, terms, citation, version, and recorded digest.
4. Keep the archived LAMBADA derivative, manifest, and canonical rejection report together and
   preserve exact attribution, identity, extraction rule, limitations, and fail-closed status.
5. Keep the bundled VesSAP derivative, manifest, separate CC BY-NC 4.0 license text, provenance,
   transform identity, and display-only/clearance-disabled limitations together.
6. Preserve the NP1 model's pinned source identities/digests and review-pending status until a
   separately recorded independent review is complete; do not bundle upstream documents or code
   without a new terms review.
7. Do not distribute the user-supplied protocol or Mouse Brain atlas through the repository,
   application, test fixtures, or release package without a separate rights review.
8. Re-review this file when a dependency, atlas version, packaging mode, copied asset, or
   distribution model changes. A concept-only item must be reclassified before any code or asset
   is copied.
