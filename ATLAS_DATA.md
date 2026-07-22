# Atlas Data

This document defines which atlas package the current hybrid application can open, where its data is stored, and
which provenance and memory limitations apply. Coordinate semantics are normative in
[ADR-002](docs/ADR-002-coordinate-conventions.md) and explained with worked examples in
[Coordinate Systems](COORDINATE_SYSTEMS.md).

## Source of truth

The Python scientific service uses
[BrainGlobe AtlasAPI 2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/tree/v2.3.1)
as the atlas discovery, acquisition, metadata, hierarchy, volume, and mesh boundary. The
application does not scrape Allen files or recreate the structure hierarchy.

The only runtime-allowlisted package is:

| BrainGlobe key | Reviewed package version | Resolution | Shape `[AP,DV,ML]` |
| --- | --- | ---: | ---: |
| `allen_mouse_25um` | `1.2` | `(25,25,25)` µm | `(528,320,456)` |

The runtime reads and validates installed metadata; these table values are not a license to
ignore a future version change. The application catalog is an explicit key-and-package-version
allowlist and currently exposes only this version-1.2 identity, including in local-only mode. The
10 µm package is deferred until the lower-memory path is release-qualified; an existing 10 µm
package or derived cache is ignored and left untouched. A new BrainGlobe package version is not
treated as reviewed merely because it reuses a key.
Other adult-mouse atlases shown by BrainGlobe are candidates, not automatically validated
substitutes. Each needs a coordinate, citation, version, data-schema, and terms review before it
can be added to the allowlist.

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

BrainGlobe's native orientation for this package is `asr`. Array axes are `[AP,DV,ML]`; index
zero lies toward anterior, superior/dorsal, and right, while increasing indices move toward
posterior, inferior/ventral, and left. The physical extent is
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
| `allen_mouse_25um` | 77,045,760 | 462,274,560 bytes | 0.462 GB / 0.43 GiB |

These are lower bounds. Python objects, temporary operations, display composites, selected-region
masks, and future display meshes raise peak resident memory. The application must not combine
arrays and meshes from different packages. The 25 µm spacing is sampling resolution, not a claim of 25 µm
targeting accuracy; atlas variation, registration, skull landmarks, manipulator error,
deformation, and operator effects are outside that number.

## Download and cache behavior

Atlas packages are downloaded only on explicit selection or command; they are not bundled in the
repository or `.app`. Command-line acquisition is:

```bash
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
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
must resolve beneath the app-owned atlas directory. Before a package is reported as cached, the
adapter parses `metadata.json` and `structures.json`, validates the reviewed mouse/ASR identity and
hierarchy, requires the exact reviewed table shape, and inspects both TIFF headers for the reviewed
uint16/uint32 types and matching shape without loading the voxel arrays. Once cached, a selected
package opens without an update check. Ordinary open calls are cache-only; acquiring missing data
requires the native app's explicit download action or `atlas download` CLI command.

The remote catalog uses BrainGlobe's official `last_versions.conf` endpoint through an
application-owned bounded transport: short socket waits, a 15-second total deadline, cancellation
checks between size-limited reads, and an atomic app-cache update. A network/timeout failure uses a
previously validated cached catalog. Cancellation does not leave a catalog daemon running.

Exact-version downloads are validated in an isolated staging directory. If the destination name
already contains an incomplete or structurally invalid package, that directory is atomically
moved beneath `atlases/quarantine/` with an `.invalid-<timestamp>` suffix before the validated
staged package is promoted. The quarantined data remains recoverable for inspection; a subsequent
open uses the valid replacement and does not redownload it. A valid concurrent package is retained
instead of overwritten.

Managed/test environments may override the base locations with
`MOUSE_BRAIN_PLANNER_CONFIG_DIR`, `MOUSE_BRAIN_PLANNER_DATA_DIR`, and
`MOUSE_BRAIN_PLANNER_CACHE_DIR`; see [Installation](INSTALL.md).

The current build has no cache-removal or quarantine-management UI. The application does not silently erase
an installed atlas: invalid targets displaced during a requested acquisition are quarantined.
Before manually relocating or removing a package or quarantine entry, close the application,
inspect projects that record that exact atlas identity, and preserve a recoverable copy. A project
package does not contain the atlas itself.

## Integrity and reproducibility boundary

The installed atlas metadata recorded in a project includes the API key, package version,
species, resolution, shape, orientation, citation/source URL, source-annotation identifier,
cache path, and a SHA-256 digest of the installed `metadata.json`.

That digest detects changes to that metadata file. It is **not** a publisher-signed archive hash,
does not authenticate the source, and is not a whole-package content manifest. Stable
BrainGlobe's atlas validator does not provide an authoritative expected archive hash. A future
release must add and test a complete manifest/integrity policy before claiming content-level
verification. The structural JSON/TIFF-header checks above detect malformed or internally
inconsistent cache entries, but they likewise do not authenticate anatomically plausible content.

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

For the reviewed symmetric Allen packages, normalized metadata also persists the continuous ML
midline (`5700 µm`). The adapter checks BrainGlobe's scalar hemisphere labels (`left=1`, `right=2`)
without loading its hemisphere volume, and hemisphere classification uses the persisted midline
rather than inferring one from the current array shape at the call site.

## Population vascular density is a separate source

The optional vascular layer is not part of the BrainGlobe atlas package and must not be described
as an Allen vessel annotation. It comes from Yongsoo Kim's
[Mendeley Data v1 deposit](https://data.mendeley.com/datasets/stxvn5sv44/1), DOI
`10.17632/stxvn5sv44.1`, associated with
[Wu et al., Cell Reports 2022](https://doi.org/10.1016/j.celrep.2022.110978).

The accepted archive is exactly 311,493,514 bytes with SHA-256
`c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe`. The service extracts only
the pinned density and template members, validates their exact hashes/header contract, and
prepares a 50 µm `[AP,DV,ML]` field bound to the exact open 25 µm atlas metadata. Its transparent
dorsal overlay is a DV maximum projection.

That product is a symmetrized four-mouse population vascular length density with a 100 µm local
window. It is not individual vessel paths, is not subject-specific, and cannot establish vessel
clearance. The 50 µm prepared grid also does not acquire 25 µm vascular resolution merely because
it is composited over a 25 µm atlas image. Full provenance and terms are in
[Third-Party Software and Data](THIRD_PARTY.md).

## No official CCF bregma

The CCF is an average of ex-cranio fixed brains and has no single source skull. Allen does not
provide one uniquely correct bregma or lambda for the CCF. Atlas origin, physical center,
hemisphere midline, and renderer origin are not bregma.

Atlas lookup remains atlas-native. The current application may preserve an exact AP/ML/DV target
entered in millimetres from bregma, but that record is explicitly unprojected and unusable for
navigation. Projection appears only after the user selects or defines a named, versioned
calibration profile with landmarks, transform, units, atlas identity, uncertainty, and citation.
No IBL or other estimate may be applied invisibly.

## Not included in the current build

- external Allen NRRD/NIfTI import;
- Allen-CCF-2020 parcellation import;
- `allen_mouse_10um` loading or selection (deferred; existing cache data is not deleted);
- chunked or memory-mapped BrainGlobe 3.x storage;
- atlas upgrades or migration across package versions;
- a full atlas-file content manifest;
- calibrated bregma-to-atlas target projection or navigation;
- a validated subject-specific 3D vessel graph or vessel-clearance calculation;
- automatic subject-image vessel segmentation;
- a native 3D renderer in bridge protocol v1;
- automatic cache removal; and
- any inference of a vessel-free surgical corridor.

Consult [Scientific Validation](SCIENTIFIC_VALIDATION.md) for exactly which real-data and
synthetic-data tests have been run.
