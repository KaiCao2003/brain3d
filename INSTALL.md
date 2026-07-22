# Installation

Mouse Brain Surgery Planner currently builds a native SwiftUI development `.app` that launches a
separate Python scientific service from the repository environment. The supported development
target is **Apple Silicon (`arm64`), macOS 14 or later, CPython 3.12, and Swift**. The development
bundle is ad-hoc signed; a Developer ID-signed and notarized release is not available yet. See
[Packaging](PACKAGING.md).

> **Animal-research-only warning:** This application is for mouse animal-research planning only,
> never human or clinical use. It is not a certified surgical-navigation, medical, or veterinary
> device. Independently verify all coordinates before every animal procedure.

## Prerequisites

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and make sure the repository
is on a local volume with enough space for the environment and any selected atlas. Either let uv
install CPython 3.12 or provide a compatible Python yourself:

```bash
uv python install 3.12
```

The repository's `.python-version` and `pyproject.toml` constrain the environment to Python
3.12. Do not substitute Python 3.11, 3.13, or 3.14 without creating and validating a separate
lockfile and platform matrix.

## Install the locked environment

From the repository root:

```bash
uv lock --check
uv sync --frozen
```

`uv.lock` is the reproducible dependency record. `--frozen` installs from that record without
changing it. Developers and package builders should install every dependency group instead:

```bash
uv sync --frozen --all-groups
```

## Launch

Build and start the supported native application from the repository root:

```bash
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The app discovers `.venv/bin/python` and `src/mouse_brain_planner/bridge/server.py`
deterministically. If discovery fails, it reports **Backend not configured** and does not display
demo scientific state. Environment overrides for a managed development launch are documented in
[`native/Brain3D/README.md`](native/Brain3D/README.md).

The older Python command starts the diagnostic Qt shell, not the supported SwiftUI workflow:

```bash
uv run --frozen mouse-brain-planner --no-download
```

Use it only for explicitly scoped diagnostic tests. Confirm the Python package version, run the
bounded Qt smoke check, and test the native package separately with:

```bash
uv run --frozen mouse-brain-planner --version
QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true \
  uv run --frozen mouse-brain-planner --smoke-test --no-download
swift test --package-path native/Brain3D
```

The Qt smoke check only proves that its diagnostic event loop opens and closes. The Swift test
suite checks native protocol/UI policy code. Neither validates anatomy or surgical accuracy.

## Acquire an atlas

Atlas data is not included in the repository or application bundle. List the BrainGlobe catalog
and locally cached packages with:

```bash
uv run --frozen mouse-brain-planner atlas list
```

Download the only current package, the 25 µm Allen atlas, from the native **Download reviewed
25 µm atlas** control or by CLI:

```bash
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
```

Read [Atlas Data](ATLAS_DATA.md) and the
[Allen Institute Terms of Use](https://alleninstitute.org/legal/terms-of-use) before downloading.
The two arrays loaded by stable BrainGlobe AtlasAPI require approximately:

| Atlas | Reference + annotation raw bytes | Approximate raw memory |
| --- | ---: | ---: |
| `allen_mouse_25um` | 462,274,560 | 0.462 GB / 0.43 GiB |

Actual peak memory is higher because these figures exclude Python objects, temporary arrays,
slice composites, and VTK meshes. The application rejects other resolutions rather than silently
substituting or mixing them. Existing 10 µm cache data is left untouched but ignored.

## Application-owned data locations

On macOS, the default locations are:

| Purpose | Default path |
| --- | --- |
| Configuration and application data | `~/Library/Application Support/Mouse Brain Surgery Planner` |
| Installed atlases | `~/Library/Application Support/Mouse Brain Surgery Planner/atlases` |
| Temporary atlas downloads | `~/Library/Caches/Mouse Brain Surgery Planner/atlas-downloads` |
| BrainGlobe configuration | `~/Library/Application Support/Mouse Brain Surgery Planner/brainglobe/bg_config.conf` |

The application configures BrainGlobe before importing it, then passes the application-owned
atlas and staging locations explicitly. Tests and managed installations may override the three
base locations before launch:

```bash
export MOUSE_BRAIN_PLANNER_CONFIG_DIR=/absolute/path/to/config
export MOUSE_BRAIN_PLANNER_DATA_DIR=/absolute/path/to/data
export MOUSE_BRAIN_PLANNER_CACHE_DIR=/absolute/path/to/cache
```

Use absolute, user-writable paths. Do not change these variables between downloading an atlas
and reopening a project unless the atlas cache is deliberately being relocated. Project packages
store atlas provenance and a cache path but do not embed the atlas arrays.

## Troubleshooting

### The native app reports Backend not configured

Run `uv sync --frozen --all-groups` from the repository root and confirm that both
`.venv/bin/python` and `src/mouse_brain_planner/bridge/server.py` exist. Launch the `.app` from
this checkout so deterministic development discovery can find them. Do not point the UI at an
unreviewed backend.

### A different Qt binding is selected in diagnostic tests

The diagnostic Qt shell requires PySide6. If it reports that `QT_API` selects a different binding,
remove that override or set it explicitly:

```bash
export QT_API=pyside6
```

Do not install PyQt alongside this locked environment.

### Atlas download is unavailable

Confirm that the native planning service is connected and that the app-owned data/cache
directories are writable. A cached atlas can be opened without a network connection; an uncached
atlas requires an explicit download and network access. The diagnostic Qt shell additionally
honors `--no-download`.

### The 3D view is unavailable

This is expected in the current supported app: bridge protocol v1 exposes dorsal, coronal,
sagittal, and horizontal raster views but no native 3D renderer. Do not use the diagnostic Qt 3D
viewer as a substitute for a qualified surgery-planning view.

### Project validation fails

Run the non-mutating validator:

```bash
uv run --frozen mouse-brain-planner validate /absolute/path/Plan.mouseplan
```

The validator checks the project package structure, JSON models, and recorded checksums. It does
not establish that the scientific coordinates are anatomically correct.

For operating instructions, continue to the [User Guide](USER_GUIDE.md). For reproducible
development commands, see [Development](DEVELOPMENT.md).
