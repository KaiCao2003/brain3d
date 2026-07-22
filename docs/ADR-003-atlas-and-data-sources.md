# ADR-003: Atlas and external data sources

- **Status:** Accepted
- **Decision date:** 2026-07-21
- **Applies to:** atlas discovery, download, cache, provenance, and external reference material

## Implementation update — 2026-07-22

The atlas decision is unchanged. The primary vessel source is now a bundled, integrity-checked
CC BY 4.0 derivative of the LAMBADA P60_606 graph, Zenodo record DOI
`10.5281/zenodo.18876865`, filtered pointwise to radius ≥15 µm (diameter ≥30 µm). Population
density and subject-image registration remain archived backend paths and are absent from the
primary UI. See [the derivation record](LAMBADA_MAJOR_VESSELS.md).

## Decision

Use [BrainGlobe AtlasAPI 2.3.1](https://pypi.org/project/brainglobe-atlasapi/2.3.1/)
as the authoritative atlas access layer. `allen_mouse_25um` package version `1.2` is the only
runtime-allowlisted identity in the current build, for both remote and local-only catalog views. The 10 µm
identity is deferred until the lower-memory path is release-qualified; existing cache data is
ignored and not deleted. Arbitrary BrainGlobe keys, non-mouse atlases, and future unreviewed
versions fail closed. Other identities may be added through the same adapter only after their
coordinates, version, schema, citation, data terms, and native acceptance evidence are reviewed.

Never silently substitute one resolution or atlas for another, and never combine annotation,
reference, mesh, or coordinate metadata from different atlas versions. Every saved project
records the atlas identifier, installed atlas version, resolution, shape, orientation, framework,
source annotation, source URL, cache path, SHA-256 of the installed `metadata.json`, and
application version. The current build does **not** claim to record the install time or a package-wide
content digest.

## Atlas identity and coordinate metadata

As checked on 2026-07-21, BrainGlobe's
[`last_versions.conf`](https://gin.g-node.org/brainglobe/atlases/raw/master/last_versions.conf)
lists version `1.2` for `allen_mouse_25um`. The generator uses Allen
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
| `allen_mouse_25um` | `528 × 320 × 456` | uint16 + uint32 | 0.462 GB / 0.43 GiB |

These figures exclude Python objects, temporary copies, derived masks, and display meshes, so peak
resident memory is higher. Load structures and meshes on demand, release intermediates promptly,
and never create an unbounded resident full-volume copy merely for display. Adding another
resolution is a separate product/validation decision; no silent substitution is allowed.

[BrainGlobe AtlasAPI 3.0.0rc1](https://pypi.org/project/brainglobe-atlasapi/3.0.0rc1/)
introduces a newer storage path, but it is a prerelease and is not the production dependency. The
adapter boundary exists so a future chunked implementation can be evaluated without changing
project coordinates or provenance.

## Archived population vascular-density decision

The optional population layer uses exactly Yongsoo Kim's *Cerebrovascular, pericyte, and
neuronal cell type mapping data 2022*,
[Mendeley Data v1, DOI 10.17632/stxvn5sv44.1](https://data.mendeley.com/datasets/stxvn5sv44/1),
licensed CC BY 4.0 and associated with
[Wu et al., Cell Reports 2022](https://doi.org/10.1016/j.celrep.2022.110978).

Acquisition is fail-closed. The accepted archive is
`NVU_mapping_Adult_mouse_brain (1).7z`, exactly 311,493,514 bytes, SHA-256
`c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe`. Only two exact members are
streamed into application-owned staging: the vascular length-density NIfTI and its Allen template.
Their names, sizes, SHA-256 values, NIfTI header evidence, and the derived-cache manifest are
validated before an atomic promotion.

The reviewed source contract is a 20 µm `(570,400,660)` `[ML,DV,AP]` field with values in
`m/mm^3`, four fixed adult mice, and a 100 µm local window. The density NIfTI itself has unit
zooms, unknown units, and no qform/sform, so the implementation validates that exact caveat and
uses the pinned README/template contract rather than treating the header as authoritative. AP is
reversed into BrainGlobe ASR, ML is deliberately symmetrized because source polarity is not
documented, and the prepared result is a 50 µm `[AP,DV,ML]` scalar field. Preparation requires an
exact target-atlas identity and template correlation of at least 0.99.

The backend can produce a declared transparent AP-by-ML DV maximum projection with the source,
atlas binding, units, display window, and limitations intact. That path is retained for archived
work but is not requested by the primary SwiftUI workspace. This is a population scalar density,
not individual vessel paths, not subject-specific anatomy, and not used for vessel analysis. The
separate simulation-ready graph deposit `10.17632/mjtyry6v85.1` is not integrated.

## LAMBADA major-vessel decision

The primary vessel layer uses the atlas-registered P60_606 graph from Renier, de Launoit, and
Skriabine's *Vascular graphs of the developing post-natal mouse brain*, Zenodo record
`10.5281/zenodo.18876865`, CC BY 4.0. The repository bundles a deterministic compact derivative,
not the 5.05 GB source archive or 12.28 GB extracted graph.

Extraction keeps maximal consecutive in-bounds source-edge runs only where each point has radius
≥15 µm. The manifest binds the source/archive identities, conversion from ClearMap to
BrainGlobe `[AP,DV,ML]`, physical 25 µm scaling, output arrays/counts, asset SHA-256, and mandatory
limitations. Runtime loading fails closed on any mismatch.

This is a fixed cleared reference, not the animal being planned. The source omits pial and
choroidal vessels; the derivative omits smaller vessels; sex/side and artery/vein identity are
unavailable; and biological variation, tissue distortion, and registration error are not bounded.

## Cache, download, and offline behavior

Atlas data is user cache/application data and is **not bundled inside the application**. Resolve
paths with platformdirs under the user's macOS Application Support/cache directories. Set
`BRAINGLOBE_CONFIG_DIR` before the first `brainglobe_atlasapi` import, because version 2.3.1
reads it during module initialization; pass the application-owned atlas and intermediate-download
directories explicitly where the API permits. The relevant behavior is documented in
[`config.py`](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/config.py#L16-L25).

Downloads run outside the GUI thread. The supported SwiftUI shell currently shows indeterminate
download/preparation progress and does not expose a cancellation control; cancellation and
quantitative progress remain future UI work. Exact-version acquisition uses BrainGlobe inside
unique application-owned archive and atlas staging directories;
the adapter parses metadata and structures and inspects reference/annotation TIFF headers to
validate reviewed identity, species, package version, orientation, resolution, hierarchy,
uint16/uint32 types, volume shapes, and path containment without loading whole arrays. Only
packages passing that check receive a catalog `downloaded` state. The staged package is then
atomically renamed into the visible cache. Existing valid versions and valid concurrent targets
are preserved. An invalid same-name target is atomically moved beneath the app-owned
`atlases/quarantine/` directory before promotion, so evidence remains recoverable and the valid
replacement prevents a redownload loop.
Cached-only open uses BrainGlobe's low-level local reader, cannot call its downloader, and must
validate the exact requested version. Cache-removal and quarantine-management UI are deferred.

Catalog work is invoked only by explicit native/CLI acquisition operations; ordinary atlas open
is cache-only.
Production does not call AtlasAPI 2.3.1's timeout-less catalog helper or abandon it in a daemon
thread. The adapter fetches the same official `last_versions.conf` endpoint directly with a short
socket timeout, a 15-second total deadline, cooperative checks between bounded reads, and a 1 MiB
response limit. A validated response replaces the app-owned cache atomically; network or deadline
failure falls back to a previously validated cached catalog. Cancellation returns without leaving
catalog work running in another thread.

Stable AtlasAPI downloads do not publish or enforce a cryptographic expected hash for each
atlas archive. The application records the SHA-256 of the installed `metadata.json` for exact metadata
identity. The separately measured whole-file hashes in `SCIENTIFIC_VALIDATION.md` are validation
evidence, not persisted project fields and not upstream authentication. A future package-wide
integrity feature must define and version its manifest before claiming corruption or content
drift detection. Structural JSON/TIFF-header validation detects malformed or internally
inconsistent packages, not anatomically plausible tampering. Pooch may be used for other external
files only when an authoritative expected hash is available.

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
| Kim 2022 population vascular length-density data, DOI `10.17632/stxvn5sv44.1` | Optional downloaded scientific data | Mendeley Data v1, CC BY 4.0; exact archive/member identities are pinned. Archived backend preparation only; never vessel paths, a subject layer, or clearance geometry. |
| LAMBADA P60_606 vascular graph, DOI `10.5281/zenodo.18876865` | Bundled derived scientific data | CC BY 4.0; exact source and derivative identities are pinned. The diameter-≥30 µm reference is displayed in 2D, Dorsal, and 3D and used only for explicitly bounded reference analysis. |
| Wu et al. simulation-ready vascular tracing data, DOI `10.17632/mjtyry6v85.1` | Candidate data; not integrated | Dataset page identifies four fully traced adult-mouse cerebrovascular graphs in MATLAB format and licenses version 1 under CC BY 4.0. Before any ingestion, inspect documentation, pin file-level identities/hashes, and validate units, axes, Allen registration, and suitability. |
| VesselGraph | Prior-art vascular graph/data reference only | Software is MIT; data is CC BY-NC 4.0. No code, models, or data copied. The noncommercial restriction prevents treating it as an unrestricted distributable default. |
| VesSAP | Prior-art vascular workflow/reference only | Repository code is MIT; the paper links public scans and registered atlas data, but the external data terms were not established here. No code, models, or data copied. |

The Allen terms currently restrict covered Content to noncommercial research unless otherwise
stated. The application must show the source and terms before first download, retain attribution,
and avoid redistributing the atlas inside the `.app` or an installer. Commercial distribution,
hosted redistribution, or a change in Allen terms requires legal review before release.

The integrated `stxvn5sv44.1` density and the candidate `mjtyry6v85.1` vessel graphs are distinct
deposits and must never be conflated. A new source still needs a stable URL, version, coordinate
registration, citation, redistribution terms, integrity strategy, scientific semantics, and
fail-closed UI labeling before it can be displayed. Visual ideas from prior art may inform
independently written code, but repository code, meshes, screenshots, icons, and other assets
must not be copied unless their license is explicitly compatible and the reuse is recorded in
`THIRD_PARTY.md`.

## Consequences

- First use requires a network download; later use is offline from an application-owned cache.
- Only the explicitly reviewed Allen mouse 25 µm package-v1.2 identity is discoverable or
  openable in the current build.
- 10 µm is deferred. Existing source or derived cache data is left untouched but cannot enter a
  current project package.
- The Mendeley density and subject-image workflows remain archived and absent from the primary UI.
- The LAMBADA derivative may render only with its source identity, diameter threshold, reference
  status, and pial/choroidal/smaller-vessel omissions visible at the point of use.
- Project files carry enough provenance to enforce exact metadata identity and prevent silent
  coordinate reinterpretation; the current build does not claim package-wide content-drift
  detection.
- Atlas upgrades, new external datasets, or copied prior-art material require a new review of
  scientific provenance, terms, and `THIRD_PARTY.md` before implementation.
