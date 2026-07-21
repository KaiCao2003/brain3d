# ADR-003: Atlas and external data sources

- **Status:** Accepted
- **Decision date:** 2026-07-21
- **Applies to:** atlas discovery, download, cache, provenance, and external reference material

## Decision

Use [BrainGlobe AtlasAPI 2.3.1](https://pypi.org/project/brainglobe-atlasapi/2.3.1/)
as the authoritative atlas access layer. The default atlas is `allen_mouse_10um`; expose
`allen_mouse_25um` as an explicit lower-memory choice. Other BrainGlobe atlases may be added
through the same adapter only after their coordinates, version, citation, and data terms have
been reviewed.

Never silently substitute one resolution or atlas for another, and never combine annotation,
reference, mesh, or coordinate metadata from different atlas versions. Every saved project
records the atlas identifier, installed atlas version, resolution, shape, orientation, framework,
source annotation, source URL, cache path, SHA-256 of the installed `metadata.json`, and
application version. Phase 1 does **not** claim to record the install time or a package-wide
content digest.

## Atlas identity and coordinate metadata

As checked on 2026-07-21, BrainGlobe's
[`last_versions.conf`](https://gin.g-node.org/brainglobe/atlases/raw/master/last_versions.conf)
lists version `1.2` for both `allen_mouse_10um` and `allen_mouse_25um`. The generator uses Allen
CCF 2017 annotations (`annotation/ccf_2017`) and BrainGlobe orientation `asr`: array axes are
`[AP,DV,ML]`, the origin lies toward anterior/superior/right, and increasing indices move toward
posterior/inferior/left. Treat those values as discovered metadata, not permanent constants:
the installed metadata written to a project is authoritative for reopening it.

The Allen atlas generator and citation are recorded in
[`allen_mouse.py`](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/atlas_scripts/allen_mouse.py).
Scientific outputs using this atlas must cite Wang et al., *The Allen Mouse Brain Common
Coordinate Framework: A 3D Reference Atlas*, Cell 2020,
[doi:10.1016/j.cell.2020.04.007](https://doi.org/10.1016/j.cell.2020.04.007), together with the
exact BrainGlobe atlas name and version.

All UI and saved trajectories use an application-defined coordinate model. Conversion to atlas
array indices, BrainGlobe axes, or any future iblatlas representation happens only at named
adapter boundaries and is covered by round-trip tests.

## Memory policy

AtlasAPI 2.3.1 loads complete TIFF arrays with `tifffile.imread`; it does not provide chunked
array access in this stable release. The implementation is visible in
[`core.py`](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/core.py#L122-L135),
and its [descriptors](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/descriptors.py#L51-L57)
declare uint16 reference and uint32 annotation arrays.

| Atlas | Shape | Reference + annotation raw bytes | Approx. raw memory |
|---|---:|---:|---:|
| `allen_mouse_10um` | `1320 × 800 × 1140` | uint16 + uint32 | 7.223 GB / 6.73 GiB |
| `allen_mouse_25um` | `528 × 320 × 456` | uint16 + uint32 | 0.462 GB / 0.43 GiB |

These figures exclude Python objects, temporary copies, derived masks, and VTK meshes, so peak
resident memory is higher. Before loading 10 µm data, show the estimate and check available
memory; recommend 25 µm on 16 GB systems. A change of resolution requires explicit user consent
and is persisted in the project. Load structures and meshes on demand, release intermediates
promptly, and never create an unbounded full-volume copy merely for display.

[BrainGlobe AtlasAPI 3.0.0rc1](https://pypi.org/project/brainglobe-atlasapi/3.0.0rc1/)
introduces a newer storage path, but it is a prerelease and is not the production dependency. The
adapter boundary exists so a future chunked implementation can be evaluated without changing
project coordinates or provenance.

## Cache, download, and offline behavior

Atlas data is user cache/application data and is **not bundled inside the application**. Resolve
paths with platformdirs under the user's macOS Application Support/cache directories. Set
`BRAINGLOBE_CONFIG_DIR` before the first `brainglobe_atlasapi` import, because version 2.3.1
reads it during module initialization; pass the application-owned atlas and intermediate-download
directories explicitly where the API permits. The relevant behavior is documented in
[`config.py`](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/config.py#L16-L25).

Downloads run outside the GUI thread, report progress, and support cancellation. Exact-version
acquisition uses BrainGlobe inside unique application-owned archive and atlas staging directories;
the adapter validates core files, identity, package version, orientation, shape, resolution,
metadata, and path containment before atomically renaming the package into the visible cache.
Existing versions are preserved, and a concurrent target is never overwritten. Cached-only open
uses BrainGlobe's low-level local reader, cannot call its downloader, and must validate the exact
requested version. Cache removal UI is deferred; Phase 1 never deletes an installed atlas
implicitly during upgrade or failure recovery.

Catalog work is backgrounded, cancellable at the application boundary, local-only under
`--no-download`, and bounded to 15 seconds. AtlasAPI 2.3.1 contains an upstream HTTP call without
a timeout; after application cancellation/timeout that call may finish only in an abandoned
daemon thread, whose result is ignored and which cannot block Qt shutdown or process exit.

Stable AtlasAPI downloads do not publish or enforce a cryptographic expected hash for each
atlas archive. Phase 1 records the SHA-256 of the installed `metadata.json` for exact metadata
identity. The separately measured whole-file hashes in `SCIENTIFIC_VALIDATION.md` are validation
evidence, not persisted project fields and not upstream authentication. A future package-wide
integrity feature must define and version its manifest before claiming corruption or content
drift detection. Pooch may be used for other external files only when an authoritative expected
hash is available.

## Code, data, and prior art are separate

| Item | Classification | License/terms decision |
|---|---|---|
| BrainGlobe AtlasAPI | Executed dependency code | BSD-3-Clause; pin and attribute it |
| Allen Mouse CCF data obtained through BrainGlobe | Downloaded scientific data | Governed by the [Allen Institute Terms of Use](https://alleninstitute.org/legal/terms-of-use), not by AtlasAPI's BSD license |
| brainrender 2.2.0 | Prior-art concept/API reference only | BSD-3-Clause; not a runtime dependency |
| iblatlas 1.2.0 | Prior-art coordinate/trajectory reference only | MIT; not a runtime dependency; do not install its PyQt5 GUI extra |
| Neuropixels Trajectory Explorer v2.0.0 | Prior-art workflow reference only | GPL-3.0; no copied code or assets |
| Pinpoint v2.0.0 | Prior-art workflow reference only | GPL-3.0; no copied code or assets |
| cortex-lab/allenCCF and SHARP-Track | Prior-art workflow reference only | No repository license found; no copied code or assets |
| Wu et al. simulation-ready vascular tracing data, DOI `10.17632/mjtyry6v85.1` | Phase 4 candidate data; not downloaded or displayed in Phase 1 | Dataset page identifies four fully traced adult-mouse cerebrovascular graphs in MATLAB format and licenses version 1 under CC BY 4.0. Before ingestion, inspect the included documentation, pin file-level identities and hashes, and validate units, axes, Allen CCF registration, and anatomical suitability. |
| VesselGraph | Prior-art vascular graph/data reference only | Software is MIT; data is CC BY-NC 4.0. No code, models, or data copied. The noncommercial restriction prevents treating it as an unrestricted distributable default. |
| VesSAP | Prior-art vascular workflow/reference only | Repository code is MIT; the paper links public scans and registered atlas data, but the external data terms were not established here. No code, models, or data copied. |

The Allen terms currently restrict covered Content to noncommercial research unless otherwise
stated. The application must show the source and terms before first download, retain attribution,
and avoid redistributing the atlas inside the `.app` or an installer. Commercial distribution,
hosted redistribution, or a change in Allen terms requires legal review before release.

The Wu et al. Mendeley deposit is the Phase 0 **license-level candidate** for future vascular
work: its versioned landing page and CC BY 4.0 terms make lawful use with attribution possible.
It is not yet approved for application ingestion or bundling because its file schema, coordinate
transform, file-level integrity, and scientific fit have not been validated. Any future source
must have a stable URL, version, coordinate registration, citation, redistribution terms, and
integrity strategy before it can be downloaded or displayed. Visual ideas from prior art may
inform independently written code, but repository code, meshes, screenshots, icons, and other
assets must not be copied unless their license is explicitly compatible and the reuse is
recorded in `THIRD_PARTY.md`.

## Consequences

- First use requires a network download; later use is offline from an application-owned cache.
- 10 µm fidelity has a material memory cost and needs an explicit preflight path.
- Project files carry enough provenance to enforce exact metadata identity and prevent silent
  coordinate reinterpretation; Phase 1 does not claim package-wide content-drift detection.
- Atlas upgrades, new external datasets, or copied prior-art material require a new review of
  scientific provenance, terms, and `THIRD_PARTY.md` before implementation.
