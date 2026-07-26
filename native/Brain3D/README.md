# Brain3D native macOS app

This Swift package is the native half of the Brain3D animal-research planner. SwiftUI owns the
single-view workspace and controls; SceneKit renders backend-validated 3D brain and probe geometry
plus display-only major-vessel payloads; a typed NDJSON subprocess boundary delegates scientific
state and analysis to Python.

> **Animal research only — non-human and non-clinical.** This development app is not an
> installable production release or a qualified navigation device.

## Current workspace

- Exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, one selected mode at a time.
- Independent retained slice depths, with slider/buttons/wheel, pan, zoom, and compact
  click-to-replace region labels. A region click never changes depth.
- Complete paged Allen ontology browsing/search with one selection shared across all five modes;
  descendant-inclusive annotation overlays highlight reviewed voxels in all four 2D modes and a
  reviewed selected-structure mesh highlights in 3D. An entry with neither voxels nor mesh stays
  selected with zero 2D pixels and an explicit 3D no-geometry state.
- No focus mode, crosshair, 2×2 layout, or capillary display.
- Direct surface-insertion AP/ML planning from a source-pinned Pinpoint/Urchin profile: AP− is
  posterior and ML− is animal-left; AP/ML anchors user-facing Shank 1 at its exact local
  annotation-surface crossing, not at the array midpoint.
- Positive path depth from Shank 1's surface crossing to its distal target, one sagittal angle
  (+ A→P / − P→A), and NP2013 layout. `Sagittal` makes Shank 1 most anterior; `90° CW` from
  dorsal makes it animal-left-most and extends the other shanks toward animal right. 3D renders
  each full 10 mm shaft, while slice/traversal analysis uses the implanted surface-to-tip path.
- VesSAP `BL6J-no1` nominal diameter-≥30 µm paths overlaid in all five views. The layer is one
  cleared C57BL/6J reference, reduced at 50 µm for display, not subject-specific.
- No vessel-analysis capability. Geometry is display-only and analysis fails with
  `VESSEL_ANALYSIS_UNAVAILABLE`.

The primary selector contains exactly NP2 single shank `NP2003` and standard four shank
`NP2013`. `NP2004`/`NP2014` remain source-artifact aliases rather than extra UI choices. Both
source transcriptions remain independent-review pending; v4 has no per-plan geometry checkbox.
Quad Base, NP1, and the synthetic fixture remain archived definitions, not new-plan choices.

## Surgery-plan PDF export

The native app can export a prefilled animal-research planning packet for the current probe plan.
Choose `Dorsal`, `Coronal`, `Sagittal`, `Horizontal`, `3D`, or `All`; `All` emits the five
planning views in that order. AP/ML locates Shank 1's local atlas-surface crossing and path depth
ends at that shank's distal target; both are millimetres. The signed A↔P angle is degrees and
layout is sagittal or 90° clockwise from dorsal. Coronal
historical plates use `Bregma = Interaural − 3.80 mm`; sagittal matching uses `|ML|` while
preserving the implant's left/right sign.

The fixed packet order is:

1. two portrait-Letter pages rendered from the user-supplied Headplate protocol;
2. one selected planning page, or five pages for `All`; and
3. one matched landscape-Letter historical atlas page.

The app reads the prepared three-page protocol PDF directly, prefills pages 1–2, and replaces its
page-3 sketch placeholder with the matched page from the consolidated 132-page
`MBSC_Figs_with_Layers.pdf`. Configure both PDF locations once in **Brain3D → Settings**; later
exports reuse those locations until they are replaced there. PDFKit/Core Graphics read the
sources directly, merge the packet, and flatten an audit stamp onto every page. The original
source files are never rewritten. Word, Illustrator, and Apple Events automation are not used.

V4 export freezes and repeatedly revalidates the source-pinned bregma profile, AP/ML, annotation
surface, depth, signed angle, layout, matching probe, atlas, vessel asset, project revision, and
saved/dirty state. It does not require a separate target projection or subject calibration. A
state change during rendering or assembly aborts the export instead of mixing revisions.

The vessel overlay is the one-specimen VesSAP `BL6J-no1` ex-vivo reference, nominal diameter
at least 30 µm. It is not the operative animal, capillaries are omitted, and neither a displayed
path nor zero visible intersections establishes subject-specific location, vessel absence,
clearance, trajectory suitability, or safety. The packet is for non-human animal research only,
not clinical use or qualified navigation.

The protocol and Mouse Brain atlas sources are supplied by the user and are not redistributed
with Brain3D. See the full [surgery-plan export contract](../../docs/SURGERY_PLAN_EXPORT.md),
including prerequisites, atlas matching, immutable provenance, and source-rights boundaries.

The older P60_606 vessel source remains archived because its hemisphere/laterality and whole-brain
coverage are unqualified; it is not mirrored or mixed into VesSAP. The visible VesSAP layer also
cannot establish subject-specific clearance, absence, suitability, or safety; see
[its evidence record](../../docs/VESSAP_MAJOR_VESSELS.md).
Population density and subject-image registration remain archived in Python and absent from the
primary UI. Only `allen_mouse_25um` v1.2 is accepted in this 25 µm testing phase.

## Development

```sh
swift test --package-path native/Brain3D --no-parallel
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

Backend discovery is deterministic and fail-closed:

1. `BRAIN3D_BRIDGE_EXECUTABLE` plus optional JSON-array `BRAIN3D_BRIDGE_ARGUMENTS` and
   `BRAIN3D_BRIDGE_WORKING_DIRECTORY` override discovery.
2. A regular executable at `Contents/Resources/Bridge/brain3d-bridge` is used from a standalone
   app, provided its resolved path remains inside that app's Resources directory.
3. Development builds walk upward from the current directory, executable, and source package for
   both `.venv/bin/python` and `src/mouse_brain_planner/bridge/server.py`.
4. If none of those routes resolves, the UI reports **Backend not configured** and does not
   substitute demo anatomy or geometry.

The development app launches Python with `-u -m mouse_brain_planner.bridge.server` and sets
`PYTHONPATH` to the repository `src` directory. UI requests are asynchronous and strict decoders
reject source, schema, revision, hash, coordinate-frame, and size mismatches.

## Distribution

`Scripts/build-app.sh` remains the fast development bundle and depends on the checkout. For an
Apple-Silicon-only standalone build, run from the repository root:

```sh
native/Brain3D/Scripts/build-release-app.sh
```

This uses exact uv-managed CPython 3.12.12 and PyInstaller 6.21.0 from the lockfile. It writes
`dist/Brain3D.app` and `dist/Brain3D-macOS-arm64.zip` below this package unless `OUTPUT_DIR` is set.
The bundled NDJSON executable is `Contents/Resources/Bridge/brain3d-bridge`; no Python installation,
checkout, `.venv`, or inherited `PYTHONPATH` is used at runtime.

The builder verifies all Swift, Python, extension-module, and dynamic-library Mach-O files are
arm64-only and have deployment targets no newer than macOS 14.0. It rejects host-only absolute
dependencies/runpaths, escaping symlinks, development Python modules, extra archive roots, and a
failed code signature. It then extracts the zip into an isolated directory, sandbox-denies the
source checkout, checks bridge `hello`, launches the real Swift executable, and confirms Swift
starts the exact bridge inside the extracted app without an immediate crash.

A discovered `Developer ID Application` identity enables hardened-runtime signing; otherwise the
builder ad-hoc signs the app. Ad-hoc builds are not notarized. A public release still needs
notarization and clean-machine macOS 14 qualification by the release operator. Production SBOM,
dependency license copies, and build provenance are embedded in `Contents/Resources/Release`.

Downloaded Allen atlas data and the user-selected surgery protocol/atlas PDFs are intentionally
outside the app. The bundled VesSAP derivative remains CC BY-NC 4.0, so public distribution must
remain noncommercial and preserve its attribution, license, manifest, and display-only limits.
