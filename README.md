# Brain3D

> **Status: early research alpha.** This repository is public for technical transparency. The
> current application is **not usable as surgical navigation** and has not been validated for
> animal procedures.

Brain3D explores a native macOS interface for the Allen Mouse Brain Common Coordinate Framework.
SwiftUI provides the application shell, while a Python service uses BrainGlobe for atlas access,
coordinate handling, external-data verification, image registration, and project persistence.

The current build can load the pinned 25 µm Allen mouse atlas, display a dorsal projection and one
fixed midpoint slice in each orthogonal orientation, preserve unprojected bregma-relative AP/ML/DV
entries, register a user-supplied dorsal image, and display a published four-mouse vascular
length-density projection.

It does **not** currently provide interactive x/y/z slice navigation, linked tri-planar
crosshairs, a supported 3D view, individual vessel paths, subject-specific vessel geometry,
trajectory planning, or vessel-clearance calculation.

> **Animal research only — never human or clinical use.** This is not a medical, veterinary, or
> surgical-navigation device. Do not use this build to guide a live procedure. Independently
> verify every coordinate, laterality choice, anatomical interpretation, and surgical decision.

## What actually works today

| Capability | Status | Current behavior |
| --- | --- | --- |
| Allen 25 µm atlas | Available | Accepts only BrainGlobe `allen_mouse_25um` package `1.2`; 10 µm is intentionally excluded |
| Dorsal view | Available | Static atlas dorsal projection |
| Coronal, sagittal, horizontal | Limited | One fixed midpoint slice per orientation |
| Arbitrary x/y/z slice movement | **Missing** | No sliders, wheel stepping, index field, click navigation, or movable crosshair |
| Linked tri-planar navigation | **Missing** | The three orthogonal views are separate static images |
| Pan and zoom | **Missing** | The native canvas only fits a raster image to the available space |
| Supported 3D view | **Missing** | The SwiftUI application explicitly shows an unavailable state |
| Population vascular density | Limited | Dorsal DV maximum projection of a scalar field summarized from four mice |
| Vessel centerlines, branches, or diameters | **Missing** | The integrated density field is not a vessel graph or image of individual vessels |
| Subject surface image | Limited | A user image can be imported and registered; there is no automatic vessel segmentation |
| Bregma AP/ML/DV entry | Limited | Exact values are stored but not projected into the atlas without calibration |
| Project save/open | Available | Checksummed `.mouseplan` package with provenance and backup recovery |
| Probe trajectory and vessel clearance | **Missing** | Lower-level Python models are not a usable planning workflow |
| Installable macOS release | **Missing** | The current app is an ad-hoc development build that depends on the source checkout |

Automated tests can verify software invariants; they do not turn a missing interaction into a
working feature and do not establish anatomical or surgical accuracy.

## Why the repository is larger than the usable product

The repository currently contains three different maturity levels:

- **Current experimental path:** `native/Brain3D/` is the SwiftUI shell and
  `src/mouse_brain_planner/bridge/` is its Python NDJSON service.
- **Legacy/reference path:** `src/mouse_brain_planner/gui/` is the older Qt/PyVista/VTK interface.
  It is not the supported application. Its historical 3D code does not provide 3D in SwiftUI.
- **Unexposed groundwork:** `src/mouse_brain_planner/surgery/` and several `domain/` models contain
  trajectory, stereotaxy, craniotomy, probe, and measurement algorithms. They are research code
  and tests, not wired, calibrated, or validated user-facing features.

This split explains the excess functions and dependencies. The next product pass should keep one
UI/rendering path and move or remove code that is not part of an executable workflow. See
[Project Status](PROJECT_STATUS.md) for the full inventory and [Plan](PLAN.md) for the recovery
roadmap.

## Architecture

```text
SwiftUI macOS development app
        ↕ typed NDJSON protocol v1
Python 3.12 scientific service
  ├─ BrainGlobe: pinned atlas access and provenance
  ├─ NumPy / Pillow / SciPy: raster slices and density preparation
  ├─ Pydantic: coordinate and project models
  ├─ registration: user-provided dorsal image
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

## Vascular data: what the red overlay is

The optional built-in overlay is derived from
[Kim 2022, Mendeley Data v1](https://data.mendeley.com/datasets/stxvn5sv44/1), associated with
[Wu et al., Cell Reports 2022](https://doi.org/10.1016/j.celrep.2022.110978). The implementation
pins the archive identity and prepares a transparent dorsal overlay.

It is a symmetrized four-mouse population **vascular length-density** scalar field using a
100 µm local window, displayed as a DV maximum projection. It contains no individual vessel
centerlines, paths, diameters, or depth. It cannot show where a vessel is in the current animal
and cannot establish probe-to-vessel clearance.

A user-supplied dorsal image is a separate layer. Registration maps its pixels onto the atlas;
it does not prove that those pixels are segmented vessels and cannot recover a validated 3D
vascular graph.

## Quick start for developers

Requirements: Apple Silicon Mac, macOS 14 or later, Python 3.12, Swift, and
[uv](https://docs.astral.sh/uv/).

```bash
uv python install 3.12
uv sync --frozen --all-groups
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The development app discovers the repository `.venv` and Python bridge. If discovery fails, it
reports **Backend not configured** rather than substituting demo anatomy.

The supported atlas is large: the raw 25 µm reference plus annotation require about 0.43 GiB
before rendering overhead. The optional pinned vascular-density archive is about 311 MB and is
downloaded to the user cache, not stored in this repository.

Useful CLI operations:

```bash
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner validate /absolute/path/Plan.mouseplan
```

## Development checks

```bash
uv lock --check
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true uv run --frozen pytest -q
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
  gui/                          legacy Qt/PyVista/VTK interface; unsupported
tests/                          software tests and fixtures
docs/                           architecture decisions
```

## Documentation

- [Project Status](PROJECT_STATUS.md) — candid implementation inventory and evidence
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
