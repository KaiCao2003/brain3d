# Installation

Brain3D currently builds a native SwiftUI + SceneKit development `.app` that launches a separate
Python scientific service from the repository environment. The supported development target is
Apple Silicon (`arm64`), macOS 14 or later, CPython 3.12, and Swift.

> **Animal research only — non-human and non-clinical:** this is not a certified medical,
> veterinary, or surgical-navigation device. The development build is not a qualified release.

## Prerequisites

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and ensure the checkout has
space for the Python environment and selected atlas data:

```bash
uv python install 3.12
```

The `.python-version`, `pyproject.toml`, and `uv.lock` define the Python 3.12 contract. Do not use
the system Python when it is 3.11, 3.13, or 3.14.

## Install the locked environment

The supported application needs only the default runtime dependencies:

```bash
uv lock --check
uv sync --frozen --no-dev
```

For tests, lint, and type checking, install the development group:

```bash
uv sync --frozen --group dev
```

Qt, PyVista, PyVistaQt, and VTK are not part of either supported path. Verify a minimal install
and a real bridge handshake with:

```bash
.venv/bin/python scripts/verify_minimal_runtime.py
```

## Build and launch

```bash
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The development app discovers `.venv/bin/python` and
`src/mouse_brain_planner/bridge/server.py`. If discovery fails, it reports **Backend not
configured** and does not display fabricated anatomy. Managed launches may use the explicit
environment described in [the native package README](native/Brain3D/README.md).

There is no second Python GUI. Running the CLI without a command prints help and exits nonzero.
Available commands are explicit:

```bash
uv run --frozen mouse-brain-planner bridge
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner validate-project /absolute/path/Plan.mouseplan
```

The SwiftUI app normally launches the `bridge` process itself; do not start another copy for an
ordinary UI session.

## Acquire the atlas

Atlas data is not included in Git or the `.app`. The only accepted package is BrainGlobe
`allen_mouse_25um` version `1.2`. Download it from the native app or the explicit CLI command
above after reviewing [Atlas Data](ATLAS_DATA.md) and the
[Allen Institute Terms of Use](https://alleninstitute.org/legal/terms-of-use).

| Data | Raw/download size |
| --- | ---: |
| 25 µm reference plus annotation arrays | 462,274,560 bytes / 0.43 GiB |
| Optional pinned population-density archive | 311,493,514 bytes |
| Packaged archived P60_606 derivative evidence (not loaded or served) | 814,393 bytes |

The population-density workflow is archived and absent from the primary UI. The P60_606
derivative is also archived: although its bytes and diameter-≥30 µm extraction are
integrity-checked, coordinate qualification rejected biological laterality and whole-brain use.
The runtime does not load, serve, display, mirror, or analyze it. Peak memory and temporary disk
use are higher. Existing 10 µm cache data is ignored.

## Application-owned locations

| Purpose | Default path |
| --- | --- |
| Configuration and data | `~/Library/Application Support/Mouse Brain Surgery Planner` |
| Installed atlases | `~/Library/Application Support/Mouse Brain Surgery Planner/atlases` |
| Temporary downloads | `~/Library/Caches/Mouse Brain Surgery Planner/atlas-downloads` |
| BrainGlobe configuration | `~/Library/Application Support/Mouse Brain Surgery Planner/brainglobe/bg_config.conf` |

Tests and managed installs may set absolute, user-writable locations before launch:

```bash
export MOUSE_BRAIN_PLANNER_CONFIG_DIR=/absolute/path/to/config
export MOUSE_BRAIN_PLANNER_DATA_DIR=/absolute/path/to/data
export MOUSE_BRAIN_PLANNER_CACHE_DIR=/absolute/path/to/cache
```

Do not change those locations between atlas download and project reopen unless the cache is being
deliberately relocated. Projects record provenance and references; they do not embed atlas
volumes.

## Troubleshooting

### Backend not configured

Run `uv sync --frozen --no-dev` at the repository root and confirm `.venv/bin/python` and
`src/mouse_brain_planner/bridge/server.py` exist. Launch the development `.app` from this checkout.

### Atlas download unavailable

Confirm the service is connected and the application-owned directories are writable. An
uncached atlas needs an explicit networked download; a validated cached atlas can open offline.

### 3D scene does not load

Confirm the 25 µm atlas is open and the Python bridge remains connected. The SceneKit view requires
the backend-provided, schema-checked atlas scene descriptor and mesh and rejects malformed or
mismatched geometry. The removed Qt renderer is not a fallback product.

### Project validation fails

```bash
uv run --frozen mouse-brain-planner validate-project /absolute/path/Plan.mouseplan
```

Validation checks structure, models, and checksums. It does not establish anatomical accuracy.

Continue with the [User Guide](USER_GUIDE.md), [Development](DEVELOPMENT.md), and
[Packaging](PACKAGING.md).
