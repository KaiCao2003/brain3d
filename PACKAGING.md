# macOS Packaging

## Status

The supported shell is now SwiftUI. `native/Brain3D/Scripts/build-app.sh` creates an ad-hoc-signed
development `.app` for **macOS 14+ Apple Silicon (`arm64`)**, and that bundle can launch from
Finder in the repository development environment. It is not a distributable release: it still
depends on a separately installed repository Python environment and has not passed Developer ID,
hardened-runtime, notarization, stapling, or clean-account qualification.

A release must bundle or install a deterministic Python scientific service, sign every nested
executable/library, and preserve the versioned bridge contract. The PyInstaller recipe below is
retained only as historical investigation for packaging the diagnostic Python/Qt stack; it is not
the current SwiftUI application recipe.

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
swift test --package-path native/Brain3D
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
```

## Current development app bundle

From the repository root:

```bash
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The script builds the release Swift product, creates the standard `.app` directory structure,
installs `Info.plist`, and applies an ad-hoc signature. It does not bundle Python or scientific
dependencies and does not perform release signing/notarization.

## Historical exploratory PyInstaller recipe

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

The command is a diagnostic reference, not the release recipe. It intentionally favors visibility of
missing scientific/VTK resources over bundle size. The generated `.spec`, hook warnings, and
Mach-O dependency graph must be reviewed; a maintained spec file and narrow explicit hidden
imports/data list are required before release. Consult the
[PyVista PyInstaller guide](https://docs.pyvista.org/extras/pyinstaller) and
[PyInstaller macOS options](https://pyinstaller.org/en/stable/usage.html#macos-specific-options).

`onefile` is deferred. Its extraction, symlink, Qt-plugin, and signing behavior makes a first
scientific release harder to audit than `onedir`.

## Release bundle-content requirements

Before calling a build functional, verify at minimum:

- the SwiftUI app launches from Finder on a clean account without repository paths;
- the exact Python scientific service/runtime is discovered inside the approved bundle boundary;
- Swift and Python agree on bridge protocol v1 and fail closed on incompatible responses;
- any retained Qt/VTK diagnostic components are either deliberately bundled with their license
  obligations or excluded;
- a real 25 µm atlas can be downloaded with progress/cancellation, reopened offline, rendered,
  queried, and released during normal shutdown;
- project save, checksum validation, backup recovery, and cached-atlas reopen work outside the
  source tree;
- no source path, developer home path, test fixture, atlas, or Mendeley dataset is embedded;
- all Mach-O binaries report `arm64` and resolve only intended system/bundled libraries;
- the application exits without orphaned worker threads or VTK crashes.

Useful non-signing inspection commands after a build include:

```bash
file "dist/Mouse Brain Surgery Planner.app/Contents/MacOS/Mouse Brain Surgery Planner"
otool -L "dist/Mouse Brain Surgery Planner.app/Contents/MacOS/Mouse Brain Surgery Planner"
```

These inspect the main executable only; the final pipeline must enumerate and inspect nested
frameworks, dylibs, and extension modules too.

## Atlas and population-density data must remain external

Do not copy `~/Library/Application Support/Mouse Brain Surgery Planner/atlases` into the `.app`,
DMG, or installer. Atlas data is acquired separately at user request, remains subject to Allen's
terms, and can be much larger than the application. The packaged app must resolve the same
platformdirs-owned configuration/data/cache locations documented in [Atlas Data](ATLAS_DATA.md).

The pinned Mendeley Data v1 vascular archive and derived 50 µm cache must also remain external.
Preserve its CC BY 4.0 attribution, DOI `10.17632/stxvn5sv44.1`, version, archive SHA-256, and
four-mouse population/no-clearance disclosure.

## License/notices gate

Before any distribution:

1. generate an SBOM from the exact locked/build environment;
2. reconcile it with [Third-Party Software and Data](THIRD_PARTY.md);
3. include required copyright/license notices;
4. satisfy the selected Qt/PySide6 LGPL, GPL, or commercial-license model, including applicable
   replacement/relink rights;
5. confirm PyInstaller's bootloader exception and every bundled transitive dependency;
6. keep Allen data, the Mendeley density archive/derived cache, and any unapproved probe or
   subject assets outside the bundle;
7. obtain legal review for proprietary, commercial, hosted, or Mac App Store distribution.

The PyInstaller exception does not relicense Qt, VTK, Python packages, fonts, icons, or data.

## Signing and notarization: not yet validated

Developer ID signing, hardened runtime, entitlements, notarization, stapling, and Gatekeeper
verification have **not** been executed or validated for this project. Do not publish an ad-hoc
or unsigned exploratory build as a release.

The release pipeline must establish a credentialed process using Apple's current
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

At least one clean macOS 14+ arm64 machine/user account must exercise backend discovery,
download/cancel/offline reuse, dorsal/coronal/sagittal/horizontal views, the explicit unavailable
3D state, population-density preparation/overlay, subject-image registration, unprojected target
entry, project round trip, invalid/tampered project handling, unsaved-quit behavior, and normal
shutdown. Capture the app version, Git commit, Swift/Python versions, complete package inventory,
build host, hashes, tests, signing identity, notarization result, and known limitations.

The development app can launch without a terminal from this checkout; the release criterion of a
self-contained, signed/notarized, clean-account Finder launch remains unmet.
