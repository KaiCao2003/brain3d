# Brain3D

Brain3D is a macOS research planner for mouse stereotaxy and Neuropixels placement. The current
development tree provides one native, single-view workspace with exactly five modes:
**Dorsal / Coronal / Sagittal / Horizontal / 3D**.

> **Animal research only — non-human and non-clinical.** Brain3D is an engineering testing build,
> not a qualified surgical-navigation or veterinary device. Its atlas, calibration, and probe
> outputs require independent review before an animal procedure. The current build displays a
> population-reference major-vessel layer, but exposes no vessel-clearance or safety result.

The repository is public at [KaiCao2003/brain3d](https://github.com/KaiCao2003/brain3d).
Published source is available for review, but the current tree is not an installable production
release or a validation claim.

## Implemented workflow

| Capability | Current development behavior |
| --- | --- |
| Atlas | BrainGlobe `allen_mouse_25um` package `1.2` only; 10 µm is excluded from this testing phase |
| Slice navigation | One full-size coronal, sagittal, or horizontal view; each retains an independent depth with buttons, slider, wheel, pan, and zoom |
| Region inspection | Complete 840-structure Allen ontology search/browse; clicking replaces one shared selection without changing any slice depth |
| Dorsal | Atlas surface with the selected probe's AP/ML projection and display-only major vessels |
| 3D | Native SceneKit brain mesh with camera control, atlas-region picking, probes, and major-vessel tubes |
| Stereotaxy | Required subject identity; signed AP/ML/DV implant sites from bregma; subject calibration CRUD/QC and guarded target projection |
| Probes | Four explicit editable placement modes, slice/3D overlays, recording sites, exact region traversal, inspection, and CSV/JSON export |
| Vessels | VesSAP BL6J-no1 diameter-≥30 µm display reference overlaid in all five views; no capillary layer |
| Reference analysis | Unavailable: clearance calls fail closed with `VESSEL_ANALYSIS_UNAVAILABLE`; geometry remains display-only |
| Persistence | Checksummed `.mouseplan` packages with revisions, provenance, migrations, and backup recovery |

Population vascular density and subject-image registration remain archived compatibility code and
persisted data only. Their methods and capabilities are not registered by the primary bridge, they
are absent from the planning UI, and they are not substituted for vessel paths. There is no focus
mode, crosshair, 2×2 layout, or capillary layer.

## Coordinate contract

Implant sites are entered in millimetres from bregma as named `[AP, ML, DV]` values:

| Axis | Positive | Negative |
| --- | --- | --- |
| AP | anterior / forward | posterior / back |
| ML | right | left |
| DV | dorsal / up | deep / ventral |

For example, `AP -1.25`, `ML -0.70`, `DV -2.40` means 1.25 mm posterior, 0.70 mm left, and
2.40 mm deep. BrainGlobe arrays use `[AP, DV, ML]` in micrometres, so conversion and projection
remain centralized in Python. An unprojected entry stays unprojected until an explicit subject
calibration passes QC; the Allen CCF does not provide one official bregma transform. See
[Coordinate Systems](COORDINATE_SYSTEMS.md).

Probe creation and editing expose exactly four input contracts: **Entry + target**, **Entry +
angles + depth**, **Target + angles + depth**, and **Stereotaxic target**. Inputs that are not
part of the selected contract are neither submitted nor silently reused. Derived entry, target,
angles, and depth remain provenance-bound to the selected mode.

## Probe geometry boundary

The production catalog intentionally contains only the two requested Neuropixels 2.0 choices:

- single shank, 1,280 sites (`NP2003` / `NP2004`);
- standard four shanks at 250 µm pitch, 5,120 sites and 384 simultaneous channels
  (`NP2013` / `NP2014`).

Quad Base, Neuropixels 1.0, and the synthetic fixture are not returned by the production catalog
and cannot appear in the new-plan selector. Their exact definitions remain archived in code only
for old-project compatibility and test evidence. Exact manufacturer, user-manual,
electrode-mapping, ProbeTable, and SpikeGLX snapshots and SHA-256 digests are recorded.

All manufacturer models remain deliberately **`source-transcribed-review-pending`**. No
independent human has reviewed every encoded coordinate against the cited sources or physical
probes. The UI requires explicit acknowledgement and never presents them as independently
verified geometry. See [Probe Models](PROBE_MODELS.md).

## Major-vessel reference boundary

The visible layer is a reproducible derivative of the public VesSAP `BL6J-no1` whole-brain
3 µm skeleton and radius volumes from Todorov et al.,
[Nature Methods 2020](https://doi.org/10.1038/s41592-020-0792-1), CC BY-NC 4.0. It retains
source radius ≥15 µm (nominal diameter ≥30 µm), preserves only true 26-neighbour source-skeleton
adjacency, applies the authors' Euler + B-spline Allen transform with an independently checked ML
reflection, and reduces paths on a 50 µm display grid. The pinned asset contains 196,377 points,
76,622 runs, and 119,755 segments.

The backend advertises `auditedReferenceMajorVessels` and serves digest-checked geometry.
Swift overlays it on Dorsal, Coronal, Sagittal, Horizontal, and 3D. The backend deliberately does
not advertise `radiusAwareReferenceVesselAnalysis`: `vessel.major.reference.analyze` returns
`VESSEL_ANALYSIS_UNAVAILABLE` before reading or mutating project state.

This is one cleared ex-vivo C57BL/6J reference, not the operative animal. Capillaries are omitted;
artery/vein identity is unavailable; the nonlinear transform is anisotropic; and no numeric
subject-registration, clearing-distortion, or inter-animal error bound is published. The layer
cannot establish clearance, vessel absence, trajectory suitability, or safety.

The older LAMBADA P60_606 derivative remains archived and rejected: its hemisphere/laterality
binding and whole-brain coverage are not qualified, so it is never served or mirrored. See
[VesSAP Major Vessels](docs/VESSAP_MAJOR_VESSELS.md),
[LAMBADA Major Vessels](docs/LAMBADA_MAJOR_VESSELS.md), and
[Known Limitations](KNOWN_LIMITATIONS.md).

## Architecture

```text
SwiftUI macOS application
  ├─ one selected Dorsal / Coronal / Sagittal / Horizontal / 3D workspace
  ├─ native controls, file panels, accessibility, and 2D overlays
  └─ SceneKit brain/probe/reference-vessel rendering and camera interaction
                         ↕ strict typed NDJSON
Python 3.12 scientific service
  ├─ pinned BrainGlobe atlas access and coordinate transforms
  ├─ calibration, probe geometry, vessel geometry, and voxel traversal
  └─ provenance, integrity checks, qualification gates, stale-result rejection, and persistence
```

Swift owns presentation. Python owns scientific coordinate conversion and analysis. Both paths
reject stale revisions and mismatched source identities. See [Architecture](docs/ARCHITECTURE.md)
and [ADR-004](docs/ADR-004-swiftui-hybrid-shell.md).

Pinpoint is the workflow reference, not an embedded state engine. Its hosted WebGL build does not
expose a supported bidirectional contract for probe identity, coordinates, atlas/camera state, or
the VesSAP overlay. Brain3D therefore uses its existing full BrainGlobe/Allen service instead of
copying or embedding an unsynchronized Unity canvas. See
[Pinpoint interoperability](docs/PINPOINT_INTEGRATION.md).

## Developer quick start

Requirements: Apple Silicon Mac, macOS 14 or later, Python 3.12, Swift, and
[uv](https://docs.astral.sh/uv/).

```bash
uv python install 3.12
uv sync --frozen --group dev
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The development app discovers the repository `.venv` and Python bridge. If discovery fails, it
reports the failure instead of substituting demo anatomy. The Allen 25 µm reference and annotation
arrays require about 0.43 GiB before rendering overhead.

Useful commands:

```bash
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner validate-project /absolute/path/Plan.mouseplan
```

Development checks:

```bash
uv lock --check
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
uv run --frozen pytest -q
swift test --package-path native/Brain3D
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
```

`build-app.sh` creates an ad-hoc-signed development bundle that depends on the source checkout.
A deterministic bundled Python runtime, Developer ID signing, notarization, and clean-Mac release
qualification remain distribution work.

## Repository map

```text
native/Brain3D/                 SwiftUI + SceneKit application and native tests
src/mouse_brain_planner/
  atlas/                        pinned BrainGlobe access boundary
  bridge/                       typed service used by the native app
  coordinates/                 named coordinate frames and transforms
  probes/                       source-traceable probe catalog
  analysis/                     region traversal plus archived vessel-analysis code
  vasculature/                  display-only VesSAP geometry plus archived evidence paths
  persistence/                  checksummed project packages and migrations
tests/                          Python software tests and fixtures
docs/                           architecture, decisions, audits, and source records
```

## Documentation

- [Project Status](PROJECT_STATUS.md)
- [User Guide](USER_GUIDE.md)
- [Known Limitations](KNOWN_LIMITATIONS.md)
- [Scientific Validation](SCIENTIFIC_VALIDATION.md)
- [Probe Models](PROBE_MODELS.md)
- [VesSAP Major Vessels](docs/VESSAP_MAJOR_VESSELS.md)
- [Pinpoint interoperability](docs/PINPOINT_INTEGRATION.md)
- [LAMBADA Major Vessels](docs/LAMBADA_MAJOR_VESSELS.md)
- [Third-Party Software and Data](THIRD_PARTY.md)
- [Installation](INSTALL.md)

## License

This public repository is **not open source**. Original source code remains all rights reserved
under [LICENSE](LICENSE). Atlas, probe-source documents, and scientific data retain their own
terms. In particular, the bundled VesSAP derivative remains CC BY-NC 4.0 and is not covered by
the source-code terms; see [Third-Party Software and Data](THIRD_PARTY.md).
