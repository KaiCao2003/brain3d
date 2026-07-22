# ADR-001: Native desktop technology stack

- **Status:** Superseded for the macOS UI shell by ADR-004; retained for the Python scientific core
- **Decision date:** 2026-07-21
- **Applies to:** the first supported macOS release

## Context

The application must combine a native-feeling desktop UI, interactive 3D rendering, large
scientific arrays, and BrainGlobe atlas access. The first release also needs one reproducible
build path that can be signed and notarized.

## Decision

> **2026-07-21 revision:** repeated native Cocoa accessibility crashes demonstrated the blocking
> compatibility issue anticipated below. [ADR-004](ADR-004-swiftui-hybrid-shell.md) replaces the
> Qt application shell with SwiftUI while retaining this ADR's Python, BrainGlobe, NumPy/SciPy,
> PyVista/VTK, validation, and data-source decisions as the scientific backend.

The remainder of this ADR records the original Qt decision and its evidence. It is historical,
not a current launch, UI, or packaging instruction; ADR-004 and [Packaging](../PACKAGING.md) are
authoritative for the supported hybrid application.

Build the application in Python 3.12 with PySide6 widgets, embed PyVista/VTK through
`pyvistaqt.QtInteractor`, and use BrainGlobe AtlasAPI behind an application-owned adapter.
The first distributable is a **macOS 14+ Apple Silicon (`arm64`)** application.

The application imports PySide6 directly. Set `QT_API=pyside6` before importing QtPy,
PyVistaQt, or other Qt-aware packages, and do not install a second Qt binding. Qt widgets and
VTK render objects stay on the main thread; worker threads return data or progress through Qt
signals and never mutate live scene objects.

### Reproducible version set

The authoritative pins are in `pyproject.toml`; this table records why each runtime component
is in the chosen stack.

| Component | Pin | Role | Upstream |
|---|---:|---|---|
| Python | `>=3.12,<3.13` | Runtime and supported ABI | [python.org](https://www.python.org/downloads/) |
| PySide6 | `6.10.3` | Native widgets, event loop, threading/signals | [PyPI](https://pypi.org/project/PySide6/6.10.3/) |
| PyVista | `0.48.4` | High-level VTK meshes and scene operations | [PyPI](https://pypi.org/project/pyvista/0.48.4/) |
| PyVistaQt | `0.12.0` | `QtInteractor` embedding | [PyPI](https://pypi.org/project/pyvistaqt/0.12.0/) |
| VTK | `9.6.2` | Rendering and geometry engine | [PyPI](https://pypi.org/project/vtk/9.6.2/) |
| BrainGlobe AtlasAPI | `2.3.1` | Atlas discovery, download, metadata, and arrays | [PyPI](https://pypi.org/project/brainglobe-atlasapi/2.3.1/) |
| NumPy / SciPy / pandas | `2.5.1` / `1.18.0` / `3.0.3` | Numeric, spatial, and tabular computation | [NumPy](https://pypi.org/project/numpy/2.5.1/), [SciPy](https://pypi.org/project/scipy/1.18.0/), [pandas](https://pypi.org/project/pandas/3.0.3/) |
| scikit-image / tifffile / NiBabel | `0.26.0` / `2026.7.14` / `5.4.2` | Image, TIFF, and neuroimaging I/O | [scikit-image](https://pypi.org/project/scikit-image/0.26.0/), [tifffile](https://pypi.org/project/tifffile/2026.7.14/), [NiBabel](https://pypi.org/project/nibabel/5.4.2/) |
| Pydantic | `2.13.4` | Validated project and settings models | [PyPI](https://pypi.org/project/pydantic/2.13.4/) |
| platformdirs / Pooch | `4.11.0` / `1.9.0` | macOS paths and verified non-atlas downloads | [platformdirs](https://pypi.org/project/platformdirs/4.11.0/), [Pooch](https://pypi.org/project/pooch/1.9.0/) |

PyVista 0.48.4 declares `vtk>=9.2.2,<9.7.0,!=9.4.0,!=9.4.1`; VTK 9.6.2 is inside that
range. Official embedding references are the [PyVista Qt guide](https://docs.pyvista.org/api/plotting/qt_plotting)
and [PyVistaQt documentation](https://qt.pyvista.org/).

On 2026-07-21, pip resolved the complete pinned set from binary wheels in a clean Python 3.12
environment on Apple Silicon. A cross-target binary-only resolution also succeeded for CPython
3.11/macOS arm64, but Python 3.11 is not a supported release target. If emergency 3.11 support
is later approved, the incompatible top-level pins must be changed to NumPy 2.4.6, SciPy 1.17.1,
and tifffile 2026.3.3 and revalidated as a separate lock/build matrix.

### Why Python rather than a SwiftUI shell

| Criterion | Python + PySide6/PyVista/VTK | SwiftUI-first application |
|---|---|---|
| Atlas and scientific stack | Direct, supported Python APIs | Requires a Python bridge, service, or reimplementation |
| 3D rendering | Supported Qt/VTK embedding | Requires a custom VTK bridge or a second rendering stack |
| Reproducibility | One pinned Python environment | Two toolchains and a cross-language lifecycle boundary |
| macOS integration | Good desktop integration through Qt | Best native integration |

The scientific and rendering integration dominates the first-release risk, so the Python stack
wins. A thin Swift/SwiftUI launcher may be reconsidered only after the Python core has a stable,
documented process boundary; it must not duplicate coordinate, atlas, or planning logic.

## Distribution decision and risks

Use PyInstaller 6.21.0 in `onedir` mode for the first release. Build in a clean, wheel-only,
arm64 environment and test a Finder launch on a clean macOS user account. The PyVista guidance
requires explicit collection of VTK modules such as `vtkmodules`, `vtkmodules.all`,
`vtkmodules.qt.QVTKRenderWindowInteractor`, `vtkmodules.util`,
`vtkmodules.util.numpy_support`, and `vtkmodules.numpy_interface.dataset_adapter`; confirm the
actual hook output rather than assuming imports found during development are bundled. See
[PyVista's PyInstaller guide](https://docs.pyvista.org/extras/pyinstaller) and
[PyInstaller's macOS options](https://pyinstaller.org/en/stable/usage.html#macos-specific-options).

The PySide6 wheel is universal2, but VTK and core numeric wheels are arm64-specific. Label the
artifact arm64; do not claim universal2 support. `onefile` is deferred because extraction,
symlink, Qt-plugin, and code-signing behavior makes diagnosis and notarization less predictable.
Release validation must cover the Cocoa Qt platform plugin, a real VTK render, atlas
download/cancel/offline reuse, normal shutdown, Developer ID signing, hardened runtime,
notarization, and stapling.

The UI currently pins PySide6 6.10.3. Native macOS accessibility traversal reproduced the same
Cocoa use-after-free on both 6.11.1 and 6.10.3 while a selected item-view hierarchy transitioned.
The symbolicated fault is
`-[QMacAccessibilityElement accessibilitySelectedChildren] + 204`, where Qt dereferences a stale
`QAccessibleTableCell` returned by the selection interface. The application therefore clears
selection and current index synchronously while the old hierarchy is still live—before atlas
dialog accept/reject and before a region-view `setModel()`—and stores the accepted atlas choice
separately. It also uses detached `QStandardItemModel` construction followed by an atomic view
swap, never publishes a zero-row region model, and retains retired
dialog/model/selection/progress hierarchies until the owning main window is torn down. Atlas
replacement recovery reports status without entering a nested modal event loop. These lifetime
mitigations require repeated native Cocoa accessibility scans; offscreen Qt tests alone do not
establish safety. Any Qt update must repeat native VoiceOver/accessibility traversal, selection,
slider, atlas-load/replacement, VTK, and shutdown journeys before the pin changes.

PySide6 6.10.3 declares `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`; Qt also offers
commercial terms. An open-source distribution
must ship the applicable notices and preserve LGPL replacement/relink rights. A proprietary or
Mac App Store distribution requires a fresh legal review and may require commercial Qt terms.
PyInstaller is GPL-2.0-or-later with an exception for generated executables, but every bundled
dependency retains its own obligations. See the [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html),
[Qt open-source FAQ](https://www.qt.io/faq/qt-open-source-licensing), and
[PyInstaller license](https://pyinstaller.org/en/stable/license.html).

## Consequences

- The supported matrix is deliberately narrow: Python 3.12, macOS 14+, arm64.
- AtlasAPI, Qt, and rendering are accessed through small adapters so upstream changes remain
  localized.
- Large atlas arrays and meshes must be loaded lazily; ADR-003 defines the memory and cache
  policy.
- Any change to a pin, architecture, Qt license model, or packaging mode requires wheel
  resolution, GUI/render smoke tests, and an update to `THIRD_PARTY.md`.
