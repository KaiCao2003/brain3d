# Installation

Mouse Brain Surgery Planner is currently a source-run Phase 1 application. The supported
development target is **Apple Silicon (`arm64`), macOS 13 or later, and CPython 3.12**. A
signed, notarized Finder-installable application is a Phase 5 deliverable and is not available
yet; see [Packaging](PACKAGING.md).

> **Research-use warning:** This application is a planning and visualization tool, not a
> certified surgical navigation or medical device. Independently verify all coordinates before
> surgery.

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

Start the desktop application from the repository root:

```bash
uv run --frozen mouse-brain-planner
```

To open the GUI while forbidding a missing atlas from being downloaded in that session:

```bash
uv run --frozen mouse-brain-planner --no-download
```

Confirm the installed version or run the bounded first-frame smoke check with:

```bash
uv run --frozen mouse-brain-planner --version
QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true \
  uv run --frozen mouse-brain-planner --smoke-test --no-download
```

The smoke check only proves that the Qt event loop opens and closes. It does not validate a real
atlas, GPU interaction, anatomy, or surgical accuracy.

## Acquire an atlas

Atlas data is not included in the repository or application bundle. List the BrainGlobe catalog
and locally cached packages with:

```bash
uv run --frozen mouse-brain-planner atlas list
```

For an initial lower-memory installation, download the 25 µm Allen package:

```bash
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
```

The preferred-resolution package can be requested explicitly with:

```bash
uv run --frozen mouse-brain-planner atlas download allen_mouse_10um
```

Read [Atlas Data](ATLAS_DATA.md) and the
[Allen Institute Terms of Use](https://alleninstitute.org/legal/terms-of-use) before downloading.
The two arrays loaded by stable BrainGlobe AtlasAPI require approximately:

| Atlas | Reference + annotation raw bytes | Approximate raw memory |
| --- | ---: | ---: |
| `allen_mouse_10um` | 7,223,040,000 | 7.223 GB / 6.73 GiB |
| `allen_mouse_25um` | 462,274,560 | 0.462 GB / 0.43 GiB |

Actual peak memory is higher because these figures exclude Python objects, temporary arrays,
slice composites, and VTK meshes. Prefer 25 µm on a 16 GB Mac. The application must never
silently replace one resolution with another.

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

### A different Qt binding is selected

The application requires PySide6. If launch reports that `QT_API` selects a different binding,
remove that override or set it explicitly:

```bash
export QT_API=pyside6
```

Do not install PyQt alongside this locked environment.

### Atlas download is unavailable

Check that `--no-download` was not supplied, that the selected atlas is not merely a remote
catalog entry, and that the app-owned data/cache directories are writable. A cached atlas can be
opened without a network connection; an uncached atlas cannot.

### The 3D view does not render

Confirm the supported architecture and environment first:

```bash
uname -m
uv run --frozen python -c 'import platform; print(platform.machine())'
uv run --frozen python -c 'import PySide6, pyvista, vtk; print("Qt/VTK imports OK")'
```

Both commands should report `arm64` on the supported target. Remote desktops, virtual machines,
and unsupported GPU/display configurations have not been release-qualified.

### Project validation fails

Run the non-mutating validator:

```bash
uv run --frozen mouse-brain-planner validate /absolute/path/Plan.mouseplan
```

The validator checks the project package structure, JSON models, and recorded checksums. It does
not establish that the scientific coordinates are anatomically correct.

For operating instructions, continue to the [User Guide](USER_GUIDE.md). For reproducible
development commands, see [Development](DEVELOPMENT.md).
