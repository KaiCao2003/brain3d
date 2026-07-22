# Brain3D

Brain3D is a macOS research planner for mouse stereotaxy and Neuropixels placement. The current
development tree provides one native, single-view workspace with exactly five modes:
**Dorsal / Coronal / Sagittal / Horizontal / 3D**.

> **Animal research only — non-human and non-clinical.** Brain3D is an engineering testing build,
> not a qualified surgical-navigation or veterinary device. Its atlas, calibration, and probe
> outputs require independent review before an animal procedure. The current build exposes
> neither vessel geometry nor a vessel-clearance result.

The repository is public at [KaiCao2003/brain3d](https://github.com/KaiCao2003/brain3d). Current
development is tracked in [draft pull request #1](https://github.com/KaiCao2003/brain3d/pull/1).
This is source availability for review, not an installable production release or a validation
claim.

## Implemented workflow

| Capability | Current development behavior |
| --- | --- |
| Atlas | BrainGlobe `allen_mouse_25um` package `1.2` only; 10 µm is excluded from this testing phase |
| Slice navigation | One full-size coronal, sagittal, or horizontal view; each retains an independent depth with buttons, slider, wheel, pan, and zoom |
| Region inspection | Clicking replaces one compact acronym/name label and does not change any slice depth |
| Dorsal | Atlas surface with the selected probe's AP/ML projection |
| 3D | Native SceneKit brain mesh with camera control, atlas-region picking, and probes |
| Stereotaxy | Required subject identity; signed AP/ML/DV implant sites from bregma; subject calibration CRUD/QC and guarded target projection |
| Probes | Four explicit editable placement modes, slice/3D overlays, recording sites, exact region traversal, inspection, and CSV/JSON export |
| Vessels | P60_606 derivative retained as archived qualification evidence only; no vessel layer is displayed or served |
| Reference analysis | Unavailable: all reference metadata, geometry, and analysis calls fail closed with `VESSEL_GEOMETRY_UNAVAILABLE` |
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

The catalog includes a complete source transcription of Neuropixels 1.0 NP1000 /
`PRB_1_4_0480_1`: one 10 mm × 70 µm × 24 µm shank, a 175 µm chisel tip, and all 960 site
coordinates. Immutable manufacturer, ProbeTable, and SpikeGLX source snapshots and their SHA-256
digests are recorded.

Its status is deliberately **`source-transcribed-review-pending`**. No independent human has
reviewed the complete transcription against the cited sources or a physical probe. The UI
requires explicit acknowledgement and does not present it as independently verified geometry.
A separate 16-site generic model is synthetic software-test geometry. See
[Probe Models](PROBE_MODELS.md).

## Archived major-vessel evidence

The repository retains a reproducible diameter-≥30 µm derivative of specimen P60_606 from
Renier, de Launoit, and Skriabine's *Vascular graphs of the developing post-natal mouse brain*,
[Zenodo record 18876865](https://zenodo.org/records/18876865), DOI
`10.5281/zenodo.18876865`, CC BY 4.0. The derivative and its extraction record are evidence for
qualification work; they are not an application vessel layer.

Qualification against the pinned Allen 25 µm v1.2 atlas found supporting AP and DV orientation
evidence, but rejected the geometry for use because the primary source describes hemisphere
specimens and the exact graph has no persisted property that binds its biological hemisphere or
ML laterality. Numeric coordinates on both sides of an array midpoint do not establish
whole-brain coverage. The application does not guess an ML sign and does not mirror the source.

The runtime therefore omits the `auditedReferenceMajorVessels` and
`radiusAwareReferenceVesselAnalysis` capabilities. Calls to
`vessel.major.reference.get`, `vessel.major.reference.geometry`, and
`vessel.major.reference.analyze` return `VESSEL_GEOMETRY_UNAVAILABLE` before loading or serving
the derivative. No displayed absence, geometry comparison, or result from this asset may be used
as a surgical-clearance claim.

The canonical rejected report is
[checked in as qualification evidence](docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.

See [the derivation record](docs/LAMBADA_MAJOR_VESSELS.md) and
[Known Limitations](KNOWN_LIMITATIONS.md).

## Architecture

```text
SwiftUI macOS application
  ├─ one selected Dorsal / Coronal / Sagittal / Horizontal / 3D workspace
  ├─ native controls, file panels, accessibility, and 2D overlays
  └─ SceneKit brain/probe rendering and camera interaction
                         ↕ strict typed NDJSON
Python 3.12 scientific service
  ├─ pinned BrainGlobe atlas access and coordinate transforms
  ├─ calibration, probe geometry, and voxel traversal
  └─ provenance, integrity checks, qualification gates, stale-result rejection, and persistence
```

Swift owns presentation. Python owns scientific coordinate conversion and analysis. Both paths
reject stale revisions and mismatched source identities. See [Architecture](docs/ARCHITECTURE.md)
and [ADR-004](docs/ADR-004-swiftui-hybrid-shell.md).

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
  vasculature/                  archived LAMBADA evidence and qualification workflows
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
- [LAMBADA Major Vessels](docs/LAMBADA_MAJOR_VESSELS.md)
- [Third-Party Software and Data](THIRD_PARTY.md)
- [Installation](INSTALL.md)

## License

This public repository is **not open source**. Original source code remains all rights reserved
under [LICENSE](LICENSE). Atlas, probe-source documents, and scientific data retain their own
terms; see [Third-Party Software and Data](THIRD_PARTY.md).
