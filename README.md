# Brain3D

Brain3D is a native macOS application for mouse-brain atlas exploration, stereotaxic planning,
Neuropixels placement, and surgery-plan export.

## Highlights

- Dorsal, coronal, sagittal, horizontal, and SceneKit 3D views.
- BrainGlobe `allen_mouse_25um` atlas support with ontology search and region highlighting.
- Direct AP/ML surface planning for Neuropixels 2.0 single- and four-shank probes.
- Synchronized probe geometry across slice and 3D views.
- Optional external VesSAP major-vessel overlay.
- Checksummed `.mouseplan` projects and PDF surgery-plan export.

## Requirements

- Apple Silicon Mac
- macOS 14 or later
- Python 3.12
- Swift
- [uv](https://docs.astral.sh/uv/)

## Quick start

```bash
uv python install 3.12
uv sync --frozen --group dev
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The development app uses the repository Python environment. To build the standalone Apple Silicon
application:

```bash
native/Brain3D/Scripts/build-release-app.sh
```

## Data and documents

Third-party datasets and PDFs are not stored in this repository.

- The Allen atlas is downloaded on demand to the application data directory.
- Surgery protocol and reference-atlas PDFs are selected by the user in **Brain3D → Settings**.
- The optional VesSAP overlay uses an externally supplied data package. Place
  `vessap_bl6j1_major_vessels_50um_v1.npz` and its
  `.npz.manifest.json` file in `<data-dir>/vasculature/`. Set
  `MOUSE_BRAIN_PLANNER_DATA_DIR` to override the platform data directory.

External files retain their original licenses and terms. See [Third-party software and
data](THIRD_PARTY.md).

## Commands

```bash
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner validate-project /absolute/path/Plan.mouseplan
```

## Development checks

```bash
uv lock --check
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
uv run --frozen pytest -q
swift test --package-path native/Brain3D --no-parallel
native/Brain3D/Scripts/build-app.sh
```

## Architecture

```text
SwiftUI + SceneKit macOS app
            ↕ typed NDJSON
Python atlas and planning service
```

Swift owns presentation and native file workflows. Python owns atlas access, coordinate
conversion, planning geometry, persistence validation, and scientific data checks.

## Documentation

- [Installation](INSTALL.md)
- [User guide](USER_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Atlas data](ATLAS_DATA.md)
- [Coordinate systems](COORDINATE_SYSTEMS.md)
- [Probe models](PROBE_MODELS.md)
- [Surgery-plan export](docs/SURGERY_PLAN_EXPORT.md)
- [VesSAP external data](docs/VESSAP_MAJOR_VESSELS.md)
- [Third-party software and data](THIRD_PARTY.md)

## License

Original source code is covered by [LICENSE](LICENSE). Dependencies and externally supplied data
retain their own licenses.
