# Phase 1 User Guide

Mouse Brain Surgery Planner is a research-use atlas viewer and project workspace. Phase 1 covers
BrainGlobe atlas selection/acquisition, whole-brain 3D display, a region hierarchy, linked
coronal/sagittal/horizontal slices, atlas-coordinate inspection, and versioned project save/load.

It does **not** yet implement stereotaxic calibration, bregma/lambda entry, probe planning,
vasculature, subject registration, craniotomies, uncertainty analysis, or surgical-plan exports.
Those are Phases 2–5. See [Known Limitations](KNOWN_LIMITATIONS.md).

> **Research-use warning:** The Allen CCF is a population reference. This application is not a
> certified navigation or medical device and does not know an individual animal's skull,
> deformation, or surface vasculature. Independently verify every coordinate before surgery.

## Start the application

Follow [Installation](INSTALL.md), then run:

```bash
uv run --frozen mouse-brain-planner
```

The scientific warning remains visible without blocking the workspace. Starting a new project
resets the Phase 1 project state and shows the warning again.

## Select and load an atlas

Use **Atlas › Select…** to choose a BrainGlobe atlas. The catalog distinguishes cached and remote
packages. Loading and download work runs outside the GUI thread, reports progress, and can be
cancelled. Cancellation leaves the current project/view unchanged.

The two initial Allen choices are:

- `allen_mouse_10um`: preferred sampling resolution, with a high memory cost;
- `allen_mouse_25um`: explicit lower-memory option.

Before loading 10 µm, read the estimate shown by the application. The reference and annotation
arrays alone occupy about 7.223 GB (6.73 GiB), and the real peak is higher. On a 16 GB Mac, choose
25 µm unless the complete workload has been measured. The application does not silently
downgrade or mix resolutions.

The first acquisition requires network access. Once a package is installed in the app-owned
cache, it can be reused offline. Launch with `--no-download` when an offline-only session is
required. The command-line equivalents are documented in [Atlas Data](ATLAS_DATA.md).

## Workspace

The left dock contains project sections, atlas anatomy search, and the hierarchical region tree.
The center contains five views:

1. **3D Brain** — transparent whole-brain geometry and selected region meshes;
2. **Coronal** — fixed AP plane, displayed with DV rows and ML columns;
3. **Sagittal** — fixed ML plane, displayed with DV rows and AP columns;
4. **Horizontal** — fixed DV plane, displayed with AP rows and ML columns;
5. **Four-panel** — 3D plus all three linked orthogonal slices.

The right dock reports the selected object, atlas, explicit atlas coordinate, and convention.
The status bar reports atlas identity/resolution, the linked cursor, selected region, slice, and
active convention. `Stereotaxic: not calibrated` is intentional in Phase 1.

## Navigate the views

### 3D

Use the embedded VTK/PyVista interaction to rotate, pan, and zoom. Picking a valid atlas point
moves the linked cursor after the renderer coordinate is transformed back to bounded BrainGlobe
physical space. A picked screen position is never stored as a scientific coordinate.

### Orthogonal slices

Each slice view provides:

- a voxel-index slider;
- direct physical-position entry in millimetres from the BrainGlobe ASR origin;
- mouse-wheel slice stepping;
- click-to-place crosshair;
- pan, zoom, and fit controls;
- reference image, annotation outlines, and selected-region highlighting.

Moving the cursor in one view updates all other loaded views and the 3D crosshair. Values are
stored in micrometres as explicit BrainGlobe `[AP,DV,ML]` physical coordinates; a millimetre
display is a unit conversion, not a bregma calibration. See
[Coordinate Systems](COORDINATE_SYSTEMS.md) before interpreting laterality or axis direction.

## Browse brain regions

Search by acronym, full name, or structure ID. The tree is built from the loaded BrainGlobe
structure hierarchy rather than a hand-written region list. Selecting a row highlights its
annotation in the slice views. Enabling visibility loads that region's mesh lazily and displays
it in 3D. Use the selected row's checkbox and the inspector's opacity/color controls to change
its presentation; this project-local state does not alter atlas metadata.

Some common experimental shorthands are not official acronyms in the Allen hierarchy. Search
maps `ADN` to Allen `AD`, `RSC` to `RSP`, and `MEC` to `ENTm` as labeled search aliases only;
the selected ID, name, hierarchy, annotation, and mesh always come from the atlas. Searching
`SC` shows the distinct Allen `SCs` and `SCm` branches rather than inventing one combined node.

An atlas label identifies the population-reference annotation voxel under the linked cursor. A
boundary label is resolution- and annotation-dependent and is not a statement about an
individual animal.

## Coordinates shown in Phase 1

The atlas-native order is BrainGlobe ASR:

```text
[AP, DV, ML], origin toward anterior / superior / right,
increasing toward posterior / inferior / left
```

Atlas lookups use half-open bounds: `0 <= coordinate < shape * resolution` on each axis. The exact
upper extent is a geometric boundary, not an indexable voxel. The coordinate model gives an exact
midline coordinate a separate `MIDLINE` semantic value rather than silently assigning it to a
hemisphere; Phase 1 does not yet add a user-facing hemisphere field to the status bar.

There is no official Allen CCF bregma or lambda. Phase 1 therefore displays no bregma-relative
coordinate and applies no hidden bregma estimate, skull tilt, DV scale, or subject transform.

## Save, reopen, and validate a project

Use **File › Save** or **File › Save As…**. A project is a human-readable directory package with
the `.mouseplan` suffix:

```text
Plan.mouseplan/
  project.json
  atlas.json
  regions.json
  checksums.json
```

The package records the schema/application version, project UUID, atlas metadata, linked cursor,
selected region, project-local region display state, notes, and event log. It stores neither Qt
objects nor screen coordinates. Atlas volumes and meshes remain in the separate app-owned cache.

Save replaces the package atomically. If a previous package exists, it is retained as the exact
sibling `Plan.mouseplan.bak`; loading can recover from that backup when the primary package is
missing or invalid. Do not edit the JSON files without expecting checksum validation to fail.

Validate a package without opening the GUI:

```bash
uv run --frozen mouse-brain-planner validate /absolute/path/Plan.mouseplan
```

Reopening a project requires the exact recorded atlas package to remain available in the cache.
The app must not fetch an uncached atlas when launched with `--no-download`.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Command+N | New project |
| Command+O | Open project |
| Command+S | Save |
| Command+Shift+S | Save as |
| Command+F | Focus region search |
| 1 | 3D view |
| 2 | Coronal view |
| 3 | Sagittal view |
| 4 | Horizontal view |
| 5 | Four-panel view |
| R | Reset the active 3D camera |

## Diagnostic logs

The application writes rotating JSON-lines diagnostic logs to the app-owned cache under
`logs/application.jsonl`. Logs contain software events and errors, not atlas arrays or project
packages. Review a log before sharing it because file paths or user-entered error text may still
be present.

## What not to infer

- Atlas sampling resolution is not stereotaxic accuracy.
- A region label is not subject-specific histology.
- Atlas midline or the renderer origin is not bregma.
- No Phase 1 line, mesh, or selected point is a verified probe plan.
- The absence of a displayed collision or vessel is not evidence of safety.

Review [Scientific Validation](SCIENTIFIC_VALIDATION.md), [Atlas Data](ATLAS_DATA.md), and
[Known Limitations](KNOWN_LIMITATIONS.md) before using output in an experiment.
