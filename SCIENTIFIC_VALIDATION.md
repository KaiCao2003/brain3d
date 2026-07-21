# Scientific Validation Status

- Snapshot date: 2026-07-21
- Scope: current Phase 1 working tree and one locally cached real `allen_mouse_25um` package
- Status: bounded engineering and data-integration validation only

> **No surgical-accuracy claim:** Mouse Brain Surgery Planner has not been validated for
> stereotaxic targeting accuracy, animal-to-atlas registration, skull landmark localization,
> hardware placement, histological outcome, or any clinical or veterinary use. It is a
> research-use planning and visualization application, not a certified navigation or medical
> device. All coordinates require independent experimental verification.

The normative coordinate rules are in [ADR-002](docs/ADR-002-coordinate-conventions.md), with
worked examples in [Coordinate Systems](COORDINATE_SYSTEMS.md). This document separates
automated tests, reproducible local-data probes, and one manual GUI observation so that none is
mistaken for anatomical or surgical validation.

## What “validated” means here

| Level | Present status | What the status means |
| --- | --- | --- |
| Mathematical/unit contract | Tested with deterministic test doubles and synthetic values | Implemented formulas, bounds, identity checks, linked-slice mappings, and selected renderer transforms behave as asserted |
| Application contract | Automated fake/headless tests plus one real normal-Cocoa run passed | Interfaces and first-frame behavior are automated without atlas acquisition; a full `MainWindow` also opened the cached real 25 µm atlas in one macOS Cocoa session |
| Real `allen_mouse_25um` integration | **Passed within the bounds below** | The current adapter opened local package `1.2` with AtlasAPI `2.3.1`; real volumes, hierarchy, lookups, slices, root mesh, and a CA1 mesh were exercised |
| Real `allen_mouse_10um` integration | **Not tested** | No real 10 µm package was acquired or opened in this validation |
| Anatomical/visual validation | **Not tested** | Rendering real data does not establish region-label truth, mesh-to-volume alignment, laterality, landmark correctness, or biological validity |
| Stereotaxic calibration | **Not tested and not configured** | No official bregma exists for the CCF and no user or experimental calibration profile has been validated |
| Surgical/biological accuracy | **Not tested; no claim permitted** | There are no animal, phantom, histology, targeting-error, or outcome data |

Passing these checks establishes implementation consistency with a declared software and local
data contract. It does not establish that the atlas represents an individual animal, that an
anatomical label is independently correct, or that a planned trajectory will reach tissue at a
stated accuracy.

### Tested and untested spatial operations

| Operation | Phase 1 evidence | Status boundary |
| --- | --- | --- |
| BrainGlobe continuous voxel ↔ physical ASR µm | Forward/inverse and half-open-bound tests at 10 and 25 µm metadata shapes | Tested mathematically with doubles; real 25 µm point lookups also exercised |
| Discrete index anchor/center ↔ physical ASR µm | Edge, center, rounding, and out-of-bounds tests | Tested mathematically; tolerance is implementation precision, not anatomical accuracy |
| BrainGlobe physical ASR ↔ right-handed renderer world RAS | Forward/inverse, determinant, asymmetric laterality, winding, and synthetic-pick tests | Tested on synthetic geometry; real visual laterality is not independently validated |
| Physical point → annotation structure ID | Eight real 25 µm voxel-center samples compared directly with the annotation array | Tested for those samples only; no boundary-accuracy claim |
| Atlas point ↔ orthogonal slice pixel/crosshair | All three orientations, click mapping, linked cursor, pan/zoom widget tests | Tested with synthetic volumes; real slice extraction dimensions were checked |
| Region mesh ↔ annotation-volume anatomical alignment | No independent landmark or surface-distance reference | **Not tested** |
| Line/trajectory ↔ region-volume intersections | Probe/trajectory phases are not implemented | **Not implemented or tested** |
| Recording site ↔ region intersections | Probe geometry and site maps are not implemented | **Not implemented or tested** |
| Probe/probe, probe/skull, or probe/craniotomy clearance | Collision and craniotomy models are not implemented | **Not implemented or tested** |
| Probe/trajectory ↔ vasculature distance/intersection | No vascular dataset is ingested and no subject registration exists | **Not implemented or tested** |

## Real 25 µm package and provenance

The package was opened from the application-owned cache selected by
[`app_paths()`](src/mouse_brain_planner/paths.py):

```text
platformdirs.user_data_path("Mouse Brain Surgery Planner", "Mouse Brain Planner")
  / "atlases" / "allen_mouse_25um_v1.2"
```

On the observed macOS host this resolves beneath the current user's Application Support
directory. The home-directory prefix is intentionally omitted. This is not BrainGlobe's
unscoped default cache and is not a project-file directory.

The completed acquisition run reported a 99 MB transfer and 12.008 seconds elapsed, then left
the application staging directory empty and the extracted package in the path above. These are
one host/network observation and a rounded transfer report, not a performance guarantee or an
authoritative archive-size claim. No `allen_mouse_10um` package was downloaded.

The extracted package contained **845 regular files totalling 630,991,323 bytes** by summing
their logical file sizes. That number is not an archive transfer size, compression ratio, or
filesystem allocation measurement.

The following SHA-256 values were computed from the files present in this local cache:

| Local file | File bytes | Locally observed SHA-256 |
| --- | ---: | --- |
| `metadata.json` | 423 | `119132150055826484fa75a4dc17c476d02251c0db8b4d0b7b28f6b8c4b8ae60` |
| `reference.tiff` | 154,179,306 | `7dba42462447e49f882f8df60a5ee4de2be7a2f22ae3d18a8186def20ded5e0e` |
| `annotation.tiff` | 308,270,826 | `52775c6086ae6aa7d9df2ad2c9e5ab9ce36effa09f5355c7c45efeada6647e06` |
| `meshes/997.obj` | 4,728,758 | `69fbcd1d452cdbdd6f6f493563a8aa4c5d9e574e073c06650cbaaf4dd4ac25a9` |
| `meshes/382.obj` | 569,447 | `e1cab6e109abf820208ac5190d10241d3d03536ba4666e6425cd40cd718c26ba` |

These are **local reproducibility identifiers only**. They are not checksums published or signed
by BrainGlobe or Allen, and they do not independently prove download origin or integrity. Stable
BrainGlobe `2.3.1` has an always-true checksum-validation placeholder, so a release provenance
record still needs an explicit manifest and trust policy.

## Runtime metadata, arrays, and hierarchy

The current application boundary in
[`brainglobe_adapter.py`](src/mouse_brain_planner/atlas/brainglobe_adapter.py) reported:

| Contract item | Real observed value | Check |
| --- | --- | --- |
| Atlas identity | `allen_mouse_25um`, package `1.2` | exact |
| Library boundary | `brainglobe-atlasapi==2.3.1` | exact pinned version |
| Orientation | `asr`, array order `[AP,DV,ML]` | exact |
| Shape | `(528,320,456)` voxels | metadata, property, and both arrays agreed |
| Resolution | `(25.0,25.0,25.0)` µm | exact |
| Half-open physical extents | `(13200.0,8000.0,11400.0)` µm | shape × resolution |
| Reference array | `uint16`, 154,091,520 raw bytes | real `ndarray`; repeat property access returned the same object |
| Annotation array | `uint32`, 308,183,040 raw bytes | real `ndarray`; repeat property access returned the same object |
| Combined raw volume memory | 462,274,560 bytes | array `nbytes` sum; excludes Python, Qt, VTK, and mesh overhead |
| Symmetry flag | `true` | real package metadata; cannot validate asymmetric laterality |
| Normalized source annotation | `annotation/ccf_2017` | supplied by the stable Allen packager contract because its generated metadata has no dedicated field |
| Structure hierarchy | 840 records | all normalized; IDs and acronyms unique; each hierarchy path ended at its own ID |

Two exact normalized hierarchy records were inspected:

| ID | Acronym | Name | Hierarchy path | RGB |
| ---: | --- | --- | --- | --- |
| 997 | `root` | root | `[997]` | `(255,255,255)` |
| 382 | `CA1` | Field CA1 | `[997,8,567,688,695,1089,1080,375,382]` | `(126,208,75)` |

For CA1, structure ID `382`, acronym `"CA1"`, the normalized `RegionRecord`, and the readable
`mesh_file_for_region` alias all resolved to the same validated in-package file, `382.obj`.

### Exact names and search-only terminology aliases

Against the real 840-record hierarchy, `POST`, `PRE`, `CA1`, `DG`, and `SUB` were present as
exact Allen acronyms. The UI's deliberately narrow, search-only terminology aliases produced
the following target acronyms:

| Search term | Real Allen acronym shown | Scope |
| --- | --- | --- |
| `ADN` | `AD` | search result only |
| `RSC` | `RSP` | search result only |
| `MEC` | `ENTm` | search result only |

These aliases never replace the atlas ID, acronym, label, hierarchy, or geometry. `SC` was not
treated as an exact acronym or silently forced to one structure: the package contains peer
roots `SCs` and `SCm` and no exact `SC`, so the shorthand is genuinely ambiguous in this
hierarchy.

## Real annotation lookup consistency

Eight deterministic voxel centers were checked through three paths:

1. direct `annotation[AP,DV,ML]` access;
2. the adapter's identity- and bounds-checked `structure_at` method; and
3. its application-terminology alias, `region_at`.

All eight returned the same structure ID, including background ID `0` mapping to `None`.

| Voxel index `[AP,DV,ML]` | Physical center µm `[AP,DV,ML]` | Direct ID | `structure_at` and `region_at` |
| --- | --- | ---: | --- |
| `(0,0,0)` | `(12.5,12.5,12.5)` | 0 | `None` |
| `(527,319,455)` | `(13187.5,7987.5,11387.5)` | 0 | `None` |
| `(264,160,228)` | `(6612.5,4012.5,5712.5)` | 59 | `IMD` — Intermediodorsal nucleus of the thalamus |
| `(100,100,100)` | `(2512.5,2512.5,2512.5)` | 0 | `None` |
| `(200,120,180)` | `(5012.5,3012.5,4512.5)` | 672 | `CP` — Caudoputamen |
| `(300,160,250)` | `(7512.5,4012.5,6262.5)` | 930 | `PF` — Parafascicular nucleus |
| `(400,200,320)` | `(10012.5,5012.5,8012.5)` | 771 | `P` — Pons |
| `(500,250,400)` | `(12512.5,6262.5,10012.5)` | 0 | `None` |

This is a lookup-path consistency check, not independent anatomical ground truth: the names and
IDs come from the same local atlas package. The points were not selected or reviewed as frozen
biological landmarks, and no assertion is made about label behavior at anatomical boundaries.

## Real slice extraction

[`SliceRenderer`](src/mouse_brain_planner/rendering/slice_renderer.py) was constructed from the
real arrays. At each midpoint, both reference and annotation slices had the documented display
shape and `numpy.shares_memory` returned `True` against their source volume:

| Orientation | Fixed ASR index | Display axes | Reference and annotation shape | Both share source memory |
| --- | ---: | --- | --- | --- |
| Coronal | AP 264 | rows DV, columns ML | `(320,456)` | yes |
| Sagittal | ML 228 | rows DV, columns AP | `(320,528)` | yes |
| Horizontal | DV 160 | rows AP, columns ML | `(528,456)` | yes |

This validates real-array slicing and the intended no-copy extraction path. It does not mean the
subsequent grayscale, outline, overlay, or RGB composition buffers are zero-copy, nor does it
validate anatomical display orientation.

## Real meshes and rendering

Real OBJ files were parsed with PyVista/VTK:

| Mesh | File | Points | Cells | Observed bounds in package coordinates |
| --- | --- | ---: | ---: | --- |
| Root | `997.obj` | 49,324 | 98,638 | `(-16.8297,13192.5) × (133.93,7564.24) × (485.729,10890.6)` |
| CA1 | `382.obj` | 6,314 | 12,620 | `(6353.59,9012.91) × (1378.07,6022.84) × (1453.93,9928.49)` |

A standalone `pyvista.Plotter(off_screen=True)` loaded the real root mesh and produced a nonempty
`uint8` image buffer with shape `(480,640,3)`. This demonstrates file parsing and a standalone
VTK render on this host. It does not validate mesh units, winding, normals, mesh-to-volume
alignment, laterality, or any anatomical landmark.

### Normal Cocoa application observation

In one normal macOS Cocoa session, without forcing `QT_QPA_PLATFORM=offscreen`, the full
[`MainWindow`](src/mouse_brain_planner/gui/main_window.py) opened the cached real atlas and reached
its ready state. The observed application state contained:

- two live 3D brain views with the root mesh (the main 3D tab and the four-panel 3D pane);
- six linked orthogonal slice views (three dedicated tabs and three four-panel panes);
- 840 populated hierarchy items; and
- a lazily loaded real CA1 region mesh with 6,314 points and 12,620 cells.

The root and region files are parsed outside the GUI thread by the workers in
[`atlas_worker.py`](src/mouse_brain_planner/gui/workers/atlas_worker.py), while VTK actors are
created in the GUI path. This single observed run establishes that the current normal Cocoa path
can assemble the real first frame and lazy region mesh on this host. It is not a soak test,
cross-machine GPU test, usability study, or scientific image review.

### Offscreen boundary on macOS

Forcing `QT_QPA_PLATFORM=offscreen` while constructing the Qt-embedded PyVista/VTK scene on this
macOS host caused a native crash. That artificial test configuration is **not** the production
Cocoa path and is not recorded as a failed production launch. Conversely, the standalone
PyVista offscreen render above is not evidence that a Qt-embedded offscreen scene is safe. The
three cases must remain distinct:

| Execution path | Result | Meaning |
| --- | --- | --- |
| Standalone PyVista, `Plotter(off_screen=True)` | Passed | Real root OBJ parsed and rendered without a Qt embedding |
| Qt-embedded PyVista/VTK with `QT_QPA_PLATFORM=offscreen` | Native crash on this macOS host | Unsupported/non-production combination; do not use it as the real-GUI validation path |
| Full Qt application with the normal Cocoa platform plugin | Passed once | Real `MainWindow`, two 3D views, six slices, 840 regions, and lazy CA1 mesh were observed |

Automated GUI tests may still select Qt offscreen while using test doubles and `--no-download`.
Those tests do not exercise the real Qt-embedded Cocoa/VTK combination and must not be cited as
if they did.

## Automated evidence

The automated suite remains important but uses deterministic doubles or synthetic inputs for
the atlas and most rendering paths. Run from the repository root in the locked environment:

```bash
uv sync --frozen
uv run --frozen pytest tests/unit/test_atlas_space.py -q
uv run --frozen pytest -q
uv run --frozen ruff check .
```

The focused coordinate-contract suite produced **65 passed** using published-shape
metadata doubles and synthetic points. The final full-suite count and warning summary are
recorded only after the release tree is frozen; see the final gate record below. A release record
must rerun every command against the exact commit and preserve full output, Python version,
lockfile, platform, and atlas acquisition record.

### Final Phase 1 gate record

The integrated candidate was checked on 2026-07-21 on an Apple Silicon (`arm64`) host running
macOS 26.5.2 (build 25F84), CPython 3.12.13, and uv 0.10.6:

| Gate | Result |
| --- | --- |
| `uv lock --check` | Passed; 76-package resolution remained consistent |
| `uv sync --frozen --all-groups` | Passed |
| `ruff format --check .` | Passed; 45 files formatted |
| `ruff check .` | Passed |
| `mypy --no-incremental` | Passed; 30 source files |
| Full pytest suite with Qt/PyVista offscreen test settings | **130 passed, 69 warnings** |
| `mouse-brain-planner --smoke-test --no-download` | Passed; first event-loop cycle entered and exited without atlas/network access |
| Wheel build | Passed for `mouse_brain_planner-0.1.0-py3-none-any.whl` |
| Normal Cocoa real-atlas application probe | Passed: package 1.2, shape `(528,320,456)`, 840 regions, two embedded 3D views, six slices, and CA1 mesh with 6,314 points / 12,620 cells |

All 69 warnings came from VTK's NumPy bridge assigning `result.shape`, which NumPy 2.5 marks as
deprecated. They arose in synthetic/GUI rendering tests, were not suppressed, and did not change
test outcomes. This is an upstream compatibility warning to recheck when VTK or NumPy changes,
not anatomical evidence and not permission to ignore future warning categories.

Ruff is a release engineering gate, not scientific evidence. Likewise, a pytest pass count
measures asserted software behavior; it is not a sample size or accuracy statistic.

### Automated coordinate coverage

[`tests/unit/test_atlas_space.py`](tests/unit/test_atlas_space.py) covers both published 10 and
25 µm metadata shapes with test doubles. It asserts continuous and discrete round trips,
half-open physical and voxel bounds, non-finite rejection, atlas identity, ASR/world transforms,
and hemisphere/midline behavior. Its strict floating-point tolerances measure implementation
error only:

- `1e-9 voxel` is not voxel-localization accuracy;
- `1e-12 µm` is not anatomical accuracy;
- `1e-9 µm` around the midline is not a biological uncertainty band; and
- 10 or 25 µm voxel spacing is sampling resolution, not targeting error.

No statistical distribution, confidence interval, animal variability, registration error, or
instrument error is represented by these tolerances.

### Test doubles remain separate from real-atlas evidence

- [`tests/fixtures/atlas_factory.py`](tests/fixtures/atlas_factory.py) creates coordinate metadata
  doubles. Its `__atlas_test_double__` cache paths and deterministic SHA-256 identity tokens are
  not downloaded assets or upstream hashes.
- [`tests/unit/test_brainglobe_adapter.py`](tests/unit/test_brainglobe_adapter.py) uses a small
  in-memory fake to verify constructor arguments, cache boundaries, cancellation, normalization,
  lookups, and mesh aliases without network or real Allen data.
- Renderer unit tests use synthetic triangles or arrays. Automated GUI tests use fake loaded
  atlases to verify linked cursor/slice and lazy-workflow behavior without treating a real atlas
  as a unit-test fixture.
- Project, CLI, and smoke tests verify persistence, validation, and event-loop behavior; they do
  not establish anatomical or surgical correctness.

## Scientific and integration validation still not performed

The completed 25 µm checks do not close the following items:

| Missing evidence | What would be required before making the related claim |
| --- | --- |
| Real `allen_mouse_10um` loading | Open the real version-locked package through the same application cache boundary and capture equivalent metadata, volume, lookup, slice, mesh, and GUI evidence |
| Acquisition and upstream integrity | Acquire in an isolated cache, record exact URLs and transfer artifacts, and validate against a documented trusted manifest or signature; the local hashes above alone are insufficient |
| Independent annotation truth | Freeze non-boundary landmarks with expected Allen IDs/acronyms reviewed independently of the package being tested |
| Cross-resolution labels | Compare real 10/25 µm annotations at common physical interior points without assuming equality at downsampled boundaries |
| Mesh units and alignment | Review root and selected-region overlays against the volume, including coordinate units, region containment/descendants, winding, and normals |
| Left/right visual orientation | Render an asymmetric first-party landmark fixture through slices and every anatomical 3D camera preset; the current real package declares itself symmetric |
| Real renderer picking | Verify VTK world pick → inverse affine → bounded BrainGlobe point → independently expected real annotation lookup |
| External Allen import | Test separate asymmetric ASL/ASR NRRD/NIfTI fixtures for every supported reader with an exact affine and axis-provenance record |
| Allen 2020 annotation | Separately acquire and validate `Allen-CCF-2020`; the BrainGlobe packager's `annotation/ccf_2017` must not stand in for it |
| Cocoa/GPU repeatability | Repeat normal full-window and region-mesh runs on supported macOS/Qt/VTK/GPU combinations and include stability/soak criteria |
| Bregma/stereotaxic frame | Define a named, cited calibration profile with landmark, transform, units, uncertainty, atlas identity, and independent validation |
| Individual-animal registration | Define an image-to-atlas protocol with ground-truth landmarks, repeatability, error analysis, and failure criteria |
| Skull and hardware calibration | Collect phantom/skull measurements, manipulator calibration, coordinate-chain audit, operator repeatability, and error propagation |
| Surgical targeting | Use a prospective protocol, preregistered acceptance criteria, histological or equivalent ground truth, adequate sample size, and statistical analysis |
| Human factors | Conduct task-based usability testing of laterality, units, warnings, profile selection, and recovery from invalid input |

The `atlas_download` pytest marker is reserved in `pyproject.toml`, but this snapshot contains no
real-atlas test carrying that marker. The real evidence above came from explicit local probes and
a manual Cocoa session, not from an automated acquisition test.

## Minimum gate to extend the current claim

Before describing support as validated beyond this one cached 25 µm package and host session, a
future release record should at least:

1. acquire exact named 10 and 25 µm packages in isolated application-owned caches and preserve
   the URLs, transfer artifacts, trusted manifest policy, and local hashes;
2. repeat real metadata, array, hierarchy, lookup, slice, and mesh checks on the release build;
3. replace same-package lookup consistency points with independently reviewed, non-boundary
   expected labels at both resolutions;
4. verify real mesh/volume overlays, an asymmetric laterality fixture, all camera presets, and
   end-to-end renderer picking;
5. repeat normal Cocoa first-frame, lazy-region, interaction, and soak checks across supported
   hardware; and
6. save and reload projects, then reject altered atlas identity, transform, or reproducibility
   hash.

Those steps would extend software/data integration validation. Experimental accuracy still
requires a separate protocol with independently reviewed thresholds; no such threshold is
assigned in this snapshot.

## Bregma and accuracy boundary

The Allen CCF has no official unique bregma because it is an average of ex-cranio fixed brains,
not one brain in one skull. The application is therefore uncalibrated by default. Atlas center,
ML midline, renderer origin, and the IBL estimate are not interchangeable with an experimentally
measured bregma.

Until an explicit calibration profile and experimental validation exist, acceptable wording is:

> “The point is expressed in the declared BrainGlobe atlas or renderer frame.”

Unacceptable wording includes:

- “the application located bregma”;
- “the atlas coordinate is accurate to 10/25 µm”;
- “the trajectory will hit the target”;
- “left/right orientation is validated” based only on symmetric data or a camera view; and
- “surgical accuracy is validated” based on unit tests, voxel spacing, or rendered atlas assets.

## Primary references

- [ADR-002: Coordinate conventions and atlas provenance](docs/ADR-002-coordinate-conventions.md)
- [Coordinate Systems](COORDINATE_SYSTEMS.md)
- BrainGlobe stable implementation: [`core.py` at v2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/core.py)
- BrainGlobe stable checksum placeholder: [`validate_atlases.py` at v2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/atlas_generation/validate_atlases.py#L187-L203)
- BrainGlobe ASR and handedness guidance: [Image space definition](https://brainglobe.info/documentation/setting-up/image-definition.html#handedness)
- BrainGlobe Allen packager and `annotation/ccf_2017`: [`allen_mouse.py` at v2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/atlas_scripts/allen_mouse.py)
- AllenSDK reference-space orientation: [Reference Space notebook](https://alleninstitute.github.io/AllenSDK/_static/examples/nb/reference_space.html)
- Allen CCF 2020 data description: [Allen Brain Cell Atlas CCF tutorial](https://alleninstitute.github.io/abc_atlas_access/notebooks/ccf_and_parcellation_annotation_tutorial.html)
- Allen explanation for the absence of CCF bregma: [Allen Brain Map Community response](https://community.brain-map.org/t/why-doesnt-the-3d-mouse-brain-atlas-have-bregma-coordinates/158)
- CCFv3 publication: [Wang et al. 2020](https://doi.org/10.1016/j.cell.2020.04.007)
