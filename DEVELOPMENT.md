# Development

## Setup

```bash
uv python install 3.12
uv sync --frozen --group dev
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
```

Build and open the macOS app:

```bash
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The Swift app communicates with the Python service over typed NDJSON. Start with
[Architecture](docs/ARCHITECTURE.md), [Coordinate Systems](COORDINATE_SYSTEMS.md), and the
architecture decisions in [docs](docs/).

## Checks

```bash
uv lock --check
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
uv run --frozen pytest -q
swift test --package-path native/Brain3D --no-parallel
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
```

## Repository layout

```text
native/Brain3D/                 SwiftUI and SceneKit application
src/mouse_brain_planner/       Python atlas and planning service
tests/                          Python tests and fixtures
docs/                           architecture and technical references
scripts/                        verification and benchmark utilities
```

Atlas volumes, vascular datasets, PDF inputs, and user projects stay outside source control.
Use `MOUSE_BRAIN_PLANNER_CONFIG_DIR`, `MOUSE_BRAIN_PLANNER_DATA_DIR`, and
`MOUSE_BRAIN_PLANNER_CACHE_DIR` for isolated development environments.
