# macOS Packaging

## Status

PyInstaller 6.21.0 is the selected initial packager, but packaging is a **Phase 5 deliverable**.
The current Phase 1 repository is supported as a source-run application only. No `.app` produced
from the exploratory recipe below has yet been qualified as signed, notarized, redistributable,
or suitable for experimental use.

The intended first artifact is a **macOS 13+ Apple Silicon (`arm64`) onedir application**. It is
not universal2. The PySide6 wheel may be universal2, but VTK and core numerical wheels in the
locked environment are arm64-specific.

## Clean build prerequisites

Build on an Apple Silicon Mac using CPython 3.12 and the committed lockfile:

```bash
uname -m
uv python install 3.12
uv lock --check
uv sync --frozen --all-groups
```

`uname -m` must report `arm64`. Before packaging, run the exact source gate:

```bash
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
uv run --frozen pytest -q
QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true \
  uv run --frozen mouse-brain-planner --smoke-test --no-download
```

## Exploratory PyInstaller recipe

From a clean repository root, the initial reproducible **investigation command** is:

```bash
uv run --frozen --group packaging pyinstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name "Mouse Brain Surgery Planner" \
  --osx-bundle-identifier org.mousebrainplanner.desktop \
  --target-architecture arm64 \
  --paths src \
  --collect-all brainglobe_atlasapi \
  --collect-all pyvista \
  --collect-all pyvistaqt \
  --collect-all vtkmodules \
  src/mouse_brain_planner/__main__.py
```

This should place an onedir application at:

```text
dist/Mouse Brain Surgery Planner.app
```

The command is a starting point, not the release recipe. It intentionally favors visibility of
missing scientific/VTK resources over bundle size. The generated `.spec`, hook warnings, and
Mach-O dependency graph must be reviewed; a maintained spec file and narrow explicit hidden
imports/data list are required before release. Consult the
[PyVista PyInstaller guide](https://docs.pyvista.org/extras/pyinstaller) and
[PyInstaller macOS options](https://pyinstaller.org/en/stable/usage.html#macos-specific-options).

`onefile` is deferred. Its extraction, symlink, Qt-plugin, and signing behavior makes a first
scientific release harder to audit than `onedir`.

## Bundle-content requirements

Before calling a build functional, verify at minimum:

- the Cocoa Qt platform plugin loads from a Finder launch;
- PySide6 is the only bundled Qt binding;
- a real `pyvistaqt.QtInteractor` and VTK render window open;
- required `vtkmodules` imports, NumPy support, and Qt interactor modules are present;
- a real 25 µm atlas can be downloaded with progress/cancellation, reopened offline, rendered,
  queried, and released during normal shutdown;
- project save, checksum validation, backup recovery, and cached-atlas reopen work outside the
  source tree;
- no source path, developer home path, test fixture, cache, or atlas is embedded;
- all Mach-O binaries report `arm64` and resolve only intended system/bundled libraries;
- the application exits without orphaned worker threads or VTK crashes.

Useful non-signing inspection commands after a build include:

```bash
file "dist/Mouse Brain Surgery Planner.app/Contents/MacOS/Mouse Brain Surgery Planner"
otool -L "dist/Mouse Brain Surgery Planner.app/Contents/MacOS/Mouse Brain Surgery Planner"
```

These inspect the main executable only; the final pipeline must enumerate and inspect nested
frameworks, dylibs, and extension modules too.

## Atlas data must remain external

Do not copy `~/Library/Application Support/Mouse Brain Surgery Planner/atlases` into the `.app`,
DMG, or installer. Atlas data is acquired separately at user request, remains subject to Allen's
terms, and can be much larger than the application. The packaged app must resolve the same
platformdirs-owned configuration/data/cache locations documented in [Atlas Data](ATLAS_DATA.md).

## License/notices gate

Before any distribution:

1. generate an SBOM from the exact locked/build environment;
2. reconcile it with [Third-Party Software and Data](THIRD_PARTY.md);
3. include required copyright/license notices;
4. satisfy the selected Qt/PySide6 LGPL, GPL, or commercial-license model, including applicable
   replacement/relink rights;
5. confirm PyInstaller's bootloader exception and every bundled transitive dependency;
6. keep Allen data and any unapproved probe/vascular assets outside the bundle;
7. obtain legal review for proprietary, commercial, hosted, or Mac App Store distribution.

The PyInstaller exception does not relicense Qt, VTK, Python packages, fonts, icons, or data.

## Signing and notarization: not yet validated

Developer ID signing, hardened runtime, entitlements, notarization, stapling, and Gatekeeper
verification have **not** been executed or validated for this project. Do not publish an ad-hoc
or unsigned exploratory build as a release.

Phase 5 must establish a credentialed pipeline using Apple's current process and
[notarization documentation](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution),
plus PyInstaller's
[macOS code-signing guidance](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing).
The validated release record must include:

- Developer ID identity and team metadata without exposing secrets;
- hardened-runtime and entitlement rationale;
- nested-code signing order and verification output;
- notarization submission/log/result and stapling result;
- `codesign --verify --deep --strict --verbose=2` output;
- `spctl --assess --type execute --verbose=4` output;
- clean-user Finder launch and Gatekeeper behavior on the oldest supported macOS version.

Exact credentialed signing commands are intentionally not presented as working instructions
until that pipeline is implemented and exercised. The bundle identifier and entitlements also
need a release-owner decision.

## Release qualification still required

At least one clean macOS 13+ arm64 machine/user account must exercise download/cancel/offline
reuse, all 3D and slice interactions, region search/visibility, project round trip, invalid/tampered
project handling, low-memory warnings, and normal shutdown. Capture the app version, Git commit,
Python version, complete package inventory, build host, hashes, tests, signing identity,
notarization result, and known limitations.

Until those checks pass, the acceptance criterion “launch without a terminal” remains unmet.
