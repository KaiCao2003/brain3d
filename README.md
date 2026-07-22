# Brain3D

> **Status: early research alpha.** The current build is usable for mouse-atlas browsing and
> preserving unprojected implant coordinates. It is **not validated as surgical navigation** or
> for animal procedures.

Brain3D explores a native macOS interface for the Allen Mouse Brain Common Coordinate Framework.
SwiftUI provides the application shell, while a Python service uses BrainGlobe for atlas access,
coordinate handling, external-data verification, image registration, and project persistence.

The current build loads the pinned 25 µm Allen mouse atlas into one full-size selected view with
exactly five modes: **Dorsal, Coronal, Sagittal, Horizontal, and 3D**. The three slice modes support
independent depth sliders, previous/next buttons, wheel stepping, pan, zoom, and click-to-identify
region labels. Each mode retains its own depth; a region click never changes any depth. The build
also preserves named bregma-relative AP/ML/DV implant entries without pretending that they are
already projected into the atlas.

It does **not** currently provide a supported 3D scene, a calibrated bregma-to-atlas projection,
probe placement/traversal UI, or trustworthy individual vessel paths and clearance. Vessel display
stays unavailable instead of drawing an unregistered graph.

> **Animal research only — never human or clinical use.** This is not a medical, veterinary, or
> surgical-navigation device. Do not use this build to guide a live procedure. Independently
> verify every coordinate, laterality choice, anatomical interpretation, and surgical decision.

## What actually works today

| Capability | Status | Current behavior |
| --- | --- | --- |
| Allen 25 µm atlas | Available | Accepts only BrainGlobe `allen_mouse_25um` package `1.2`; 10 µm is intentionally excluded |
| Dorsal view | Available | Static atlas dorsal projection |
| Coronal, sagittal, horizontal | Available | One full-size mode at a time; each depth is independent and persisted |
| Arbitrary x/y/z slice movement | Available | Slider, previous/next buttons, precise wheel stepping, and full legal index range |
| Region identification | Available | Click replaces one compact acronym/name label without changing slice depth |
| Pan and zoom | Available | Direct drag, anchored pinch zoom, reset, bounded scroll accumulation, and stale-frame protection |
| Supported 3D view | **Missing** | The SwiftUI application explicitly shows an unavailable state |
| Population vascular density | Archived | Backend capability retained, removed from the primary planning UI |
| Subject image registration | Archived | Backend capability retained, removed from the primary planning UI |
| Major-vessel centerlines and radii | **Unavailable** | No reviewed graph with sufficient Allen registration and branch-path provenance is loaded |
| Bregma AP/ML/DV entry | Limited | Exact values are stored but not projected into the atlas without calibration |
| Project save/open | Available | Checksummed `.mouseplan` package with provenance and backup recovery |
| Probe trajectory and vessel clearance | **Missing** | Lower-level Python models are not a usable planning workflow |
| Installable macOS release | **Missing** | The current app is an ad-hoc development build that depends on the source checkout |

Automated tests can verify software invariants; they do not turn a missing interaction into a
working feature and do not establish anatomical or surgical accuracy.

## One supported product path

The repository now contains two maturity levels:

- **Current experimental path:** `native/Brain3D/` is the SwiftUI shell and
  `src/mouse_brain_planner/bridge/` is its Python NDJSON service.
- **Unexposed groundwork:** `src/mouse_brain_planner/surgery/` and several `domain/` models contain
  trajectory, stereotaxy, craniotomy, probe, and measurement algorithms. They are research code
  and tests, not wired, calibrated, or validated user-facing features.

The former Qt/PyVista/VTK application, its test suite, and the 10 µm-only sagittal cache were
removed from the default package after a reachability audit. Git commit `51fe26d` preserves that
historical implementation. The default environment no longer installs Qt or VTK, and the CLI
cannot launch a second GUI. See [Code Audit](docs/CODE_AUDIT.md) and
[Legacy Removal](docs/LEGACY_REMOVAL.md).

## Architecture

```text
SwiftUI macOS development app
        ↕ typed NDJSON protocol v1
Python 3.12 scientific service
  ├─ BrainGlobe: pinned atlas access and provenance
  ├─ NumPy / Pillow / SciPy: raster slices and archived evidence-layer preparation
  ├─ Pydantic: coordinate and project models
  ├─ registration: archived subject-image groundwork
  └─ persistence: checksummed .mouseplan packages
```

Swift owns native windows, file panels, accessibility, and image compositing. Python owns atlas
data, scientific transforms, source verification, registration, and persistence. See
[ADR-004](docs/ADR-004-swiftui-hybrid-shell.md).

## Coordinate contract

Implant entries are millimetres from bregma in named `[AP, ML, DV]` fields:

| Axis | Positive | Negative |
| --- | --- | --- |
| AP | anterior / forward | posterior / back |
| ML | right | left |
| DV | dorsal / up | deep / ventral |

For example, `AP -1.25`, `ML -0.70`, `DV -2.40` means 1.25 mm posterior, 0.70 mm left,
and 2.40 mm deep. The application only preserves this entry today. It does not infer an Allen
atlas location or navigation-ready trajectory because a validated skull/bregma-to-atlas
calibration does not exist. BrainGlobe atlas coordinates use a different `[AP, DV, ML]` frame in
micrometres. See [Coordinate Systems](COORDINATE_SYSTEMS.md).

## Vascular data boundary

The primary UI shows **major vessels only** and currently reports that no reviewed graph is
loaded. It does not substitute population density, a subject photograph, endpoint chords, or a
manually digitized diagram for vessel paths.

The archived backend can verify and prepare the published
[Kim 2022 Mendeley dataset](https://data.mendeley.com/datasets/stxvn5sv44/1), but that source is a
20 µm voxel field of population vascular **length density**. It has no individual centerlines,
paths, diameters, or depth and therefore remains outside the primary planning UI.

VesSAP/VesselGraph is also not overlaid: the public graph is in a 3 µm cleared-specimen voxel
grid, while the released files do not establish an exact inverse subject-to-Allen mapping or
edge-linked branch polylines. Enabling it would create false slice intersections. A future source
must provide pinned geometry, physical radii, complete axis/frame metadata, exact atlas
registration, hashes, and review evidence before the app will render it.

## Quick start for developers

Requirements: Apple Silicon Mac, macOS 14 or later, Python 3.12, Swift, and
[uv](https://docs.astral.sh/uv/).

```bash
uv python install 3.12
uv sync --frozen --group dev
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The development app discovers the repository `.venv` and Python bridge. If discovery fails, it
reports **Backend not configured** rather than substituting demo anatomy.

The supported atlas is large: the raw 25 µm reference plus annotation require about 0.43 GiB
before rendering overhead. The archived vascular-density source is not downloaded by the primary
planning UI.

Useful CLI operations:

```bash
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner validate-project /absolute/path/Plan.mouseplan
```

## Development checks

```bash
uv lock --check
uv sync --frozen --group dev
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
uv run --frozen pytest -q
.venv/bin/python scripts/verify_minimal_runtime.py
swift test --package-path native/Brain3D
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
```

## Repository map

```text
native/Brain3D/                 experimental SwiftUI shell and native tests
src/mouse_brain_planner/
  atlas/                        pinned BrainGlobe access boundary
  bridge/                       NDJSON service used by SwiftUI
  coordinates/                 named coordinate frames and transforms
  domain/                       persisted models plus unexposed research models
  persistence/                  schema migration and atomic project I/O
  rendering/                    raster slice and dorsal projection generation
  vasculature/                  density preparation and subject-image registration
  surgery/                      lower-level research algorithms; not a usable workflow
tests/                          software tests and fixtures
docs/                           architecture decisions
```

## Documentation

- [Project Status](PROJECT_STATUS.md) — candid implementation inventory and evidence
- [Architecture](docs/ARCHITECTURE.md)
- [Code Audit](docs/CODE_AUDIT.md)
- [Legacy Removal](docs/LEGACY_REMOVAL.md)
- [Recovery Roadmap](PLAN.md)
- [Known Limitations](KNOWN_LIMITATIONS.md)
- [User Guide](USER_GUIDE.md)
- [Installation](INSTALL.md)
- [Coordinate Systems](COORDINATE_SYSTEMS.md)
- [Scientific Validation](SCIENTIFIC_VALIDATION.md)
- [Atlas and External Data](ATLAS_DATA.md)
- [Third-Party Software and Data](THIRD_PARTY.md)

## License

This repository is publicly visible but is **not open source**. Its original source code remains
all rights reserved under [LICENSE](LICENSE). Downloaded atlas and scientific data retain their
own licenses and are not bundled here.
