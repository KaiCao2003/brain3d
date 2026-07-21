# Third-party software, data, and prior art

This inventory was reviewed on **2026-07-21**. Exact direct pins come from `pyproject.toml`;
`uv.lock` is the machine-resolved transitive inventory. Before each release, generate an SBOM
from the final lock/build environment, retain all license texts and notices required by the
bundled artifacts, and reconcile it with this human-readable list.

The classification column is intentional:

- **Code — dependency / declared dependency:** code installed by the default environment. The row
  states when a package is reserved for a later phase rather than imported directly by Phase 1.
- **Data — downloaded:** separately governed content acquired at user request and not bundled.
- **Candidate data:** a source reviewed for a later phase, but not downloaded or integrated.
- **Concept only:** documentation or workflow reviewed as prior art; no code or assets copied.

## Direct runtime dependencies

| Package/version | License | Purpose | Classification / source |
|---|---|---|---|
| PySide6 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; commercial alternative | Qt desktop UI | Code — dependency; [PyPI](https://pypi.org/project/PySide6/6.11.1/), [license terms](https://doc.qt.io/qtforpython-6/licenses.html) |
| brainglobe-atlasapi 2.3.1 | BSD-3-Clause | Atlas discovery, download, metadata, arrays | Code — dependency; [PyPI](https://pypi.org/project/brainglobe-atlasapi/2.3.1/), [source](https://github.com/brainglobe/brainglobe-atlasapi/tree/v2.3.1) |
| nibabel 5.4.2 | MIT | Future subject-image/neuroimaging I/O; not imported by Phase 1 | Code — declared dependency; [PyPI](https://pypi.org/project/nibabel/5.4.2/) |
| numpy 2.5.1 | BSD-3-Clause | N-dimensional arrays | Code — dependency; [PyPI](https://pypi.org/project/numpy/2.5.1/) |
| pandas 3.0.3 | BSD-3-Clause | Future coordinate/report tables; not imported by Phase 1 | Code — declared dependency; [PyPI](https://pypi.org/project/pandas/3.0.3/) |
| platformdirs 4.11.0 | MIT | macOS application/cache paths | Code — dependency; [PyPI](https://pypi.org/project/platformdirs/4.11.0/) |
| pooch 1.9.0 | BSD-3-Clause | Future hash-verified non-atlas downloads; not imported by Phase 1 | Code — declared dependency; [PyPI](https://pypi.org/project/pooch/1.9.0/) |
| pydantic 2.13.4 | MIT | Validated settings and project models | Code — dependency; [PyPI](https://pypi.org/project/pydantic/2.13.4/) |
| pyvista 0.48.4 | MIT | High-level VTK data and rendering API | Code — dependency; [PyPI](https://pypi.org/project/pyvista/0.48.4/) |
| pyvistaqt 0.12.0 | MIT | Qt-embedded PyVista interactor | Code — dependency; [PyPI](https://pypi.org/project/pyvistaqt/0.12.0/) |
| scikit-image 0.26.0 | BSD-3-Clause | Future subject-image processing; not imported by Phase 1 | Code — declared dependency; [PyPI](https://pypi.org/project/scikit-image/0.26.0/) |
| scipy 1.18.0 | BSD-3-Clause | Future registration/spatial algorithms; not imported directly by Phase 1 | Code — declared dependency; [PyPI](https://pypi.org/project/scipy/1.18.0/) |
| tifffile 2026.7.14 | BSD-3-Clause | Atlas TIFF loading through BrainGlobe; not imported directly by application code | Code — declared dependency; [PyPI](https://pypi.org/project/tifffile/2026.7.14/) |
| vtk 9.6.2 | BSD-3-Clause | 3D geometry and rendering | Code — dependency; [PyPI](https://pypi.org/project/vtk/9.6.2/), [license](https://vtk.org/about/#license) |

## Build and test dependencies

These tools are not application features, but some are present in build environments or affect
the generated bundle.

| Package/version | License | Purpose | Source |
|---|---|---|---|
| hatchling 1.27.0 | MIT | Python build backend | [PyPI](https://pypi.org/project/hatchling/1.27.0/) |
| mypy 2.3.0 | MIT | Static type checking | [PyPI](https://pypi.org/project/mypy/2.3.0/) |
| pytest 9.1.1 | MIT | Test runner | [PyPI](https://pypi.org/project/pytest/9.1.1/) |
| pytest-cov 7.1.0 | MIT | Coverage integration | [PyPI](https://pypi.org/project/pytest-cov/7.1.0/) |
| pytest-qt 4.5.0 | MIT | Qt GUI tests | [PyPI](https://pypi.org/project/pytest-qt/4.5.0/) |
| ruff 0.15.22 | MIT | Linting and formatting checks | [PyPI](https://pypi.org/project/ruff/0.15.22/) |
| PyInstaller 6.21.0 | GPL-2.0-or-later with bootloader exception | macOS application bundling | [PyPI](https://pypi.org/project/pyinstaller/6.21.0/), [license](https://pyinstaller.org/en/stable/license.html) |
| pyinstaller-hooks-contrib 2026.6 | Standard hooks GPL-2.0-or-later; runtime hooks Apache-2.0 | Packaging hooks, including scientific packages | [PyPI](https://pypi.org/project/pyinstaller-hooks-contrib/2026.6/), [license](https://github.com/pyinstaller/pyinstaller-hooks-contrib/blob/v2026.6/LICENSE) |

## Material transitive dependencies

This is a review aid, not a substitute for the full lockfile/SBOM.

| Package/version | License | Why material | Source |
|---|---|---|---|
| PySide6-Essentials / PySide6-Addons / shiboken6 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; commercial alternative | Qt libraries and Python binding runtime shipped with the app | [Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html) |
| QtPy 2.4.3 | MIT | Binding-selection layer used by PyVistaQt | [PyPI](https://pypi.org/project/QtPy/2.4.3/) |
| brainglobe-space 1.0.3 | BSD-3-Clause | Atlas axis/orientation conversions | [PyPI](https://pypi.org/project/brainglobe-space/1.0.3/) |
| pyarrow 25.0.0 | Apache-2.0 | pandas columnar/serialization dependency in the resolved set | [PyPI](https://pypi.org/project/pyarrow/25.0.0/) |
| meshio 5.3.5 | MIT | Mesh-format support pulled by the rendering stack | [PyPI](https://pypi.org/project/meshio/5.3.5/) |
| pydantic-core 2.46.4 | MIT | Native validation engine bundled with Pydantic | [PyPI](https://pypi.org/project/pydantic-core/2.46.4/) |
| matplotlib 3.11.1 | PSF-based | PyVista plotting dependency | [PyPI](https://pypi.org/project/matplotlib/3.11.1/) |
| Pillow 12.3.0 | MIT-CMU | Image decoding used by plotting/image packages | [PyPI](https://pypi.org/project/pillow/12.3.0/) |

## Downloaded data and cited prior art

| Item/version | Terms | Use in this project | Classification / source |
|---|---|---|---|
| Allen Mouse CCF via BrainGlobe `allen_mouse_10um` or `allen_mouse_25um`, atlas version 1.2 as observed 2026-07-21 | [Allen Institute Terms of Use](https://alleninstitute.org/legal/terms-of-use); scientific citation required | User-selected reference/annotation/mesh atlas; downloaded on demand to user cache, never bundled in the `.app` or installer | Data — downloaded; [BrainGlobe version manifest](https://gin.g-node.org/brainglobe/atlases/raw/master/last_versions.conf), [generator/citation](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/atlas_scripts/allen_mouse.py) |
| brainrender 2.2.0 | BSD-3-Clause | Scene/API design review only; package not imported or bundled | Concept only; [release](https://github.com/brainglobe/brainrender/releases/tag/v2.2.0) |
| iblatlas 1.2.0 | MIT | Coordinate and trajectory design review only; package and PyQt5 GUI extra not imported or bundled | Concept only; [release](https://github.com/int-brain-lab/iblatlas/releases/tag/1.2.0) |
| Neuropixels Trajectory Explorer v2.0.0 | GPL-3.0 | Workflow review only; no code or assets copied | Concept only; [release](https://github.com/petersaj/neuropixels_trajectory_explorer/releases/tag/v2.0.0) |
| Pinpoint v2.0.0 | GPL-3.0 | Workflow review only; no Unity code or assets copied | Concept only; [release](https://github.com/VirtualBrainLab/Pinpoint/releases/tag/v2.0.0) |
| cortex-lab/allenCCF, including SHARP-Track, commit `e5a57fe7e1c9…` reviewed 2026-07-21 | No explicit repository license found | Workflow review only; no code or assets copied | Concept only; [repository](https://github.com/cortex-lab/allenCCF) |
| Simulation-ready vascular tracing data from adult mouse brains, version 1, DOI `10.17632/mjtyry6v85.1` | CC BY 4.0 | Phase 4 candidate containing fully traced cerebrovascular graphs from four adult mouse brains in MATLAB format; no files downloaded or bundled; schema, file hashes, coordinate registration, and scientific suitability remain to be validated | Candidate data; [versioned dataset](https://data.mendeley.com/datasets/mjtyry6v85/1), [associated open-access paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9271215/) |
| VesselGraph | Software: MIT; data: CC BY-NC 4.0 | Vascular graph/data design review only; no code, models, or data copied; NC terms make the data unsuitable as an unrestricted redistributable default | Concept only; [repository and data terms](https://github.com/jocpae/VesselGraph) |
| VesSAP | Repository code: MIT; external hosted data terms not established in this review | Vascular segmentation, feature, and atlas-registration workflow review only; no code, models, or data copied | Concept only; [repository](https://github.com/vessap/vessap), [paper data-availability statement](https://www.nature.com/articles/s41592-020-0792-1) |

Allen atlas content is not relicensed by BrainGlobe's BSD-3-Clause software license. The Allen
terms observed on the review date limit covered Content to noncommercial research unless
otherwise stated. Show the source/terms before download and obtain legal review before any
commercial redistribution or hosted data service.

## Release obligations

1. Build only from the reviewed lockfile and record Python, architecture, package, and atlas
   versions in release metadata.
2. Bundle required copyright notices and license texts. In particular, satisfy Qt LGPL
   notice/replacement requirements or use appropriate commercial Qt terms.
3. Keep downloaded atlas data outside the signed application and installer; preserve its source,
   terms, citation, version, and locally computed digest.
4. Re-review this file when a dependency, atlas version, packaging mode, copied asset, or
   distribution model changes. A concept-only item must be reclassified before any code or asset
   is copied.
