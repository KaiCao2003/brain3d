# Mouse Brain Surgery Planner

Mouse Brain Surgery Planner is an Apple-Silicon-first macOS scientific desktop application for
transparent, reproducible mouse atlas visualization and, in later phases, stereotaxic and
Neuropixels planning.

> **Research-use warning:** This software is a planning and visualization tool, not a certified
> surgical-navigation, medical, or veterinary device. The Allen CCF is a population reference;
> every coordinate must be independently verified before surgery.

## Current status: Phase 1 scientific viewer

The runnable Phase 1 application provides:

- explicit BrainGlobe AtlasAPI 2.3.1 discovery, acquisition, provenance, cache isolation,
  cancellation, and offline enforcement;
- configurable Allen CCFv3 10 µm and lower-memory 25 µm packages without silent resolution
  changes;
- a transparent whole-brain shell plus lazily loaded, independently colored region meshes;
- a searchable atlas hierarchy and common terminology search aliases that never replace atlas
  IDs or metadata;
- linked coronal, sagittal, horizontal, 3D, and four-panel views;
- an explicit voxel-center cursor in BrainGlobe ASR `[AP,DV,ML]` physical coordinates;
- human-readable, checksummed, atomically saved `.mouseplan` projects with backup recovery.

Stereotaxic calibration, skull landmarks, probes, vasculature, craniotomies, uncertainty,
reports, and signed/notarized packaging belong to Phases 2–5 and are not implemented. See
[Known Limitations](KNOWN_LIMITATIONS.md).

## Technology decision

The primary implementation is Python 3.12 + PySide6 + PyVista/VTK + PyVistaQt + BrainGlobe.
This is feasible on macOS/arm64 with the pinned wheel set and directly reuses the maintained
neuroanatomy/rendering stack. A SwiftUI-first application would require a Python process bridge
or reimplementation of those scientific capabilities, so it is deferred unless a blocking
Python/Qt compatibility problem is demonstrated. The evidence, exact pins, licenses, platform
matrix, and trade-off table are in [ADR-001](docs/ADR-001-technology-stack.md) and
[Third-Party Software and Data](THIRD_PARTY.md).

## Quick start

Requirements: Apple Silicon Mac, macOS 13 or later, Python 3.12, and
[uv](https://docs.astral.sh/uv/).

```bash
uv python install 3.12
uv sync --frozen --all-groups
uv run --frozen mouse-brain-planner
```

Useful CLI operations:

```bash
uv run --frozen mouse-brain-planner --no-download
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner validate /absolute/path/Plan.mouseplan
```

The stable AtlasAPI loads full TIFF arrays. Reference plus annotation require at least
7,223,040,000 bytes (6.73 GiB) at 10 µm or 462,274,560 bytes (0.43 GiB) at 25 µm, before UI
and VTK overhead. The application shows this distinction and never downgrades automatically.
Read [Installation](INSTALL.md) and [Atlas Data](ATLAS_DATA.md) before downloading.

## Repository structure

```text
src/mouse_brain_planner/
  app.py, cli.py, paths.py       application, CLI, app-owned paths
  atlas/                         pinned BrainGlobe boundary
  coordinates/                   typed ASR/world conversion and bounds
  domain/                        validated atlas/coordinate/project models
  gui/                           native shell, dialogs, viewers, Qt workers
  persistence/                   schema migration, atomic package I/O
  rendering/                     PyVista scene and vectorized slices
tests/
  fixtures/  unit/  gui/  smoke/
docs/
  ADR-001-technology-stack.md
  ADR-002-coordinate-conventions.md
  ADR-003-atlas-and-data-sources.md
PLAN.md, LICENSE                    phased scope and project license status
```

## Development gate

```bash
uv lock --check
uv sync --frozen --all-groups
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true uv run --frozen pytest -q
QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true \
  uv run --frozen mouse-brain-planner --smoke-test --no-download
```

Automated tests and real-atlas integration evidence establish engineering consistency, not
anatomical or surgical accuracy. The exact validated/not-validated boundary is in
[Scientific Validation](SCIENTIFIC_VALIDATION.md).

## Documentation

- [Installation](INSTALL.md)
- [User Guide](USER_GUIDE.md)
- [Coordinate Systems](COORDINATE_SYSTEMS.md)
- [Scientific Validation](SCIENTIFIC_VALIDATION.md)
- [Atlas Data](ATLAS_DATA.md)
- [Probe Models](PROBE_MODELS.md)
- [Development](DEVELOPMENT.md)
- [Packaging](PACKAGING.md)
- [Known Limitations](KNOWN_LIMITATIONS.md)
- [Third-Party Software and Data](THIRD_PARTY.md)
- [Phased Implementation Plan](PLAN.md)
- [ADR-001: Technology Stack](docs/ADR-001-technology-stack.md)
- [ADR-002: Coordinate Conventions](docs/ADR-002-coordinate-conventions.md)
- [ADR-003: Atlas and Data Sources](docs/ADR-003-atlas-and-data-sources.md)
- [Project License Status](LICENSE)
