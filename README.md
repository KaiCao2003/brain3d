# Brain3D

Brain3D is a macOS research planner for mouse stereotaxy and Neuropixels placement. The current
development tree provides one native, single-view workspace with exactly five modes:
**Dorsal / Coronal / Sagittal / Horizontal / 3D**.

> **Animal research only — non-human and non-clinical.** Brain3D is an engineering testing build,
> not a qualified surgical-navigation or veterinary device. Its atlas, calibration, probe, and
> vascular outputs require independent review before an animal procedure.

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
| Dorsal | Atlas surface with the reference major-vessel projection |
| 3D | Native SceneKit brain mesh with camera control, atlas-region picking, probes, and radius-bearing major-vessel tubes |
| Stereotaxy | Signed AP/ML/DV implant sites from bregma; subject calibration CRUD/QC and guarded target projection |
| Probes | Versioned catalog, placement, slice/3D overlays, recording sites, exact region traversal, inspection, and CSV/JSON export |
| Vessels | LAMBADA P60_606 reference graph, filtered to diameter ≥30 µm, overlaid in 2D slices, Dorsal, and 3D |
| Reference analysis | Probe-envelope to tapered-vessel-surface analysis with explicit margin, uncertainty, risk-profile, and incomplete-coverage acknowledgements |
| Persistence | Checksummed `.mouseplan` packages with revisions, provenance, migrations, and backup recovery |

Population vascular density and subject-image registration remain archived backend capabilities.
They are intentionally absent from the primary planning UI and are not substituted for vessel
paths. There is no focus mode, crosshair, 2×2 layout, or capillary layer.

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

## Major-vessel reference and analysis

The bundled vessel layer is a reproducible derivative of specimen P60_606 from Renier, de
Launoit, and Skriabine's *Vascular graphs of the developing post-natal mouse brain*,
[Zenodo record 18876865](https://zenodo.org/records/18876865), DOI
`10.5281/zenodo.18876865`, CC BY 4.0. It keeps maximal consecutive in-bounds runs whose point
radius is at least 15 µm (diameter at least 30 µm). The integrity-checked asset contains 71,313
points, 59,495 segments, and 11,818 runs.

This is one fixed, cleared, atlas-registered P60 reference—not live or subject-specific
vasculature. The source omits pial and choroidal vessels; this derivative also omits smaller
vessels. Sex/side are unpublished, artery/vein identity is unavailable, and registration error,
tissue distortion, biological variation, and omitted vessels are not bounded by the graph.

The V2 analysis minimizes distance from the conservative probe envelope to each tapered vessel
surface, then applies the user-declared required margin and registration uncertainty. It requires
separate acknowledgement of those inputs and the reference's incomplete coverage. The only
bounded zero-conflict statement is:

> No conflict detected within the loaded geometry and stated uncertainty assumptions.

See [the derivation record](docs/LAMBADA_MAJOR_VESSELS.md) and
[Known Limitations](KNOWN_LIMITATIONS.md).

## Architecture

```text
SwiftUI macOS application
  ├─ one selected Dorsal / Coronal / Sagittal / Horizontal / 3D workspace
  ├─ native controls, file panels, accessibility, and 2D overlays
  └─ SceneKit brain/probe/vessel rendering and camera interaction
                         ↕ strict typed NDJSON
Python 3.12 scientific service
  ├─ pinned BrainGlobe atlas access and coordinate transforms
  ├─ calibration, probe geometry, voxel traversal, and vessel analysis
  └─ provenance, integrity checks, stale-result rejection, and persistence
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
  analysis/                     region traversal and tapered-vessel analysis
  vasculature/                  LAMBADA reference plus archived evidence workflows
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
