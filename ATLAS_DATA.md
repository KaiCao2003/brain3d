# Atlas Data

This document defines which atlas packages Phase 1 can open, where their data is stored, and
which provenance and memory limitations apply. Coordinate semantics are normative in
[ADR-002](docs/ADR-002-coordinate-conventions.md) and explained with worked examples in
[Coordinate Systems](COORDINATE_SYSTEMS.md).

## Source of truth

Phase 1 uses
[BrainGlobe AtlasAPI 2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/tree/v2.3.1)
as the atlas discovery, acquisition, metadata, hierarchy, volume, and mesh boundary. The
application does not scrape Allen files or recreate the structure hierarchy.

The initial packages are:

| BrainGlobe key | Package version at the Phase 0 review | Resolution | Shape `[AP,DV,ML]` |
| --- | --- | ---: | ---: |
| `allen_mouse_10um` | `1.2` | `(10,10,10)` µm | `(1320,800,1140)` |
| `allen_mouse_25um` | `1.2` | `(25,25,25)` µm | `(528,320,456)` |

The runtime reads and validates installed metadata; these table values are not a license to
ignore a future version change. Other adult-mouse atlases shown by BrainGlobe are candidates,
not automatically validated substitutes. Each needs a coordinate, citation, version, and terms
review before scientific use.

## Keep the identities separate

For the stable Allen packages used here, four identifiers must not be collapsed into one label:

```text
framework / publication:   Allen CCFv3, Wang et al. 2020
source annotation request: annotation/ccf_2017
BrainGlobe atlas package:  1.2 (at the Phase 0 review)
BrainGlobe AtlasAPI:       2.3.1
```

BrainGlobe's stable
[`allen_mouse.py`](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/atlas_scripts/allen_mouse.py)
requests `annotation/ccf_2017` while citing the CCFv3 publication. It is therefore inaccurate to
rename this package “the 2020 annotation.” A feature requiring the separately distributed Allen
2020 parcellation needs its own adapter and validation.

The publication citation is Wang et al., *The Allen Mouse Brain Common Coordinate Framework: A
3D Reference Atlas*, Cell 2020,
[doi:10.1016/j.cell.2020.04.007](https://doi.org/10.1016/j.cell.2020.04.007).

## Coordinate contract

BrainGlobe's native orientation for these packages is `asr`. Array axes are `[AP,DV,ML]`; index
zero lies toward anterior, superior/dorsal, and right, while increasing indices move toward
posterior, inferior/ventral, and left. The physical extent of both listed packages is
`(13200,8000,11400)` µm.

The application validates orientation, resolution, shape, finiteness, and half-open bounds
before using a coordinate. It does not infer anatomical axes from a screen view. External Allen
NRRD/NIfTI files are not accepted as if they were interchangeable BrainGlobe arrays; first-party
file documentation may describe a different array/physical order.

## Memory and resolution choice

Stable AtlasAPI 2.3.1 reads complete TIFF volumes. The Allen reference is `uint16` and annotation
is `uint32`, so the minimum raw array calculation is six bytes per voxel:

| Atlas | Voxels | Raw reference + annotation | Approximate raw memory |
| --- | ---: | ---: | ---: |
| `allen_mouse_10um` | 1,203,840,000 | 7,223,040,000 bytes | 7.223 GB / 6.73 GiB |
| `allen_mouse_25um` | 77,045,760 | 462,274,560 bytes | 0.462 GB / 0.43 GiB |

These are lower bounds. Python objects, temporary operations, display composites, selected-region
masks, and VTK meshes raise peak resident memory. The application warns before 10 µm loading and
recommends 25 µm on a 16 GB system. It must not silently substitute 25 µm or combine arrays and
meshes from different packages.

The 10 µm atlas is the preferred default for sampling fidelity, not a claim of 10 µm targeting
accuracy. Atlas variation, registration, skull landmarks, manipulator error, deformation, and
operator effects are outside that voxel-spacing number.

## Download and cache behavior

Atlas packages are downloaded only on explicit selection or command; they are not bundled in the
repository or `.app`. Command-line acquisition is:

```bash
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner atlas download allen_mouse_10um
```

The default macOS locations are:

```text
~/Library/Application Support/Mouse Brain Surgery Planner/atlases
~/Library/Caches/Mouse Brain Surgery Planner/atlas-downloads
~/Library/Application Support/Mouse Brain Surgery Planner/brainglobe/bg_config.conf
```

The adapter configures these paths through BrainGlobe's supported configuration functions and
also passes explicit per-call paths. Each acquisition gets a unique temporary download directory;
progress and cooperative cancellation pass through the BrainGlobe callback. A completed package
must resolve beneath the app-owned atlas directory. Once cached, a selected package opens without
an update check. Use the GUI's `--no-download` mode to forbid acquisition of missing data.

Managed/test environments may override the base locations with
`MOUSE_BRAIN_PLANNER_CONFIG_DIR`, `MOUSE_BRAIN_PLANNER_DATA_DIR`, and
`MOUSE_BRAIN_PLANNER_CACHE_DIR`; see [Installation](INSTALL.md).

Phase 1 has no cache-removal UI. The application never deletes an installed atlas implicitly.
Before manually relocating or removing a package, close the application, inspect projects that
record that exact atlas identity, and preserve a recoverable copy. A project package does not
contain the atlas itself.

## Integrity and reproducibility boundary

The installed atlas metadata recorded in a project includes the API key, package version,
species, resolution, shape, orientation, citation/source URL, source-annotation identifier,
cache path, and a SHA-256 digest of the installed `metadata.json`.

That digest detects changes to that metadata file. It is **not** a publisher-signed archive hash,
does not authenticate the source, and is not a whole-package content manifest. Stable
BrainGlobe's atlas validator does not provide an authoritative expected archive hash. A future
release must add and test a complete manifest/integrity policy before claiming content-level
verification.

Project JSON files have their own checksums for accidental/tamper detection. Those checksums
likewise do not validate anatomical truth.

## Terms, citation, and redistribution

BrainGlobe AtlasAPI code is BSD-3-Clause, but that license does not relicense downloaded Allen
content. Allen data remains subject to the
[Allen Institute Terms of Use](https://alleninstitute.org/legal/terms-of-use). Review the current
terms before first acquisition and before any redistribution or commercial use.

Do not place cached atlas files in source control, a PyInstaller bundle, an installer, or a shared
project package. Every scientific output must retain the atlas key/package version, resolution,
orientation, source annotation, citation, and application transform/convention information.
See [Third-Party Software and Data](THIRD_PARTY.md) for the dependency/data classification.

## No official CCF bregma

The CCF is an average of ex-cranio fixed brains and has no single source skull. Allen does not
provide one uniquely correct bregma or lambda for the CCF. Atlas origin, physical center,
hemisphere midline, and renderer origin are not bregma.

Phase 1 remains atlas-native. A future stereotaxic coordinate appears only after the user selects
or defines a named, versioned calibration profile with landmarks, transform, units, atlas
identity, uncertainty, and citation. No IBL or other estimate may be applied invisibly.

## Not included in Phase 1

- external Allen NRRD/NIfTI import;
- Allen-CCF-2020 parcellation import;
- chunked or memory-mapped BrainGlobe 3.x storage;
- atlas upgrades or migration across package versions;
- a full atlas-file content manifest;
- subject-specific anatomy or histology registration;
- reference or subject-specific vasculature;
- automatic cache removal.

Consult [Scientific Validation](SCIENTIFIC_VALIDATION.md) for exactly which real-data and
synthetic-data tests have been run.
