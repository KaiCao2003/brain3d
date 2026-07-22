# User Guide

Brain3D is a native SwiftUI workspace backed by a Python scientific service. The current testing
build browses one reviewed 25 µm mouse atlas, retains independent slice depths and region
selections, and preserves unprojected bregma-relative implant coordinates.

> **Animal-research-only warning:** This application is for mouse animal-research planning only,
> never human or clinical use. It is not a certified surgical-navigation, medical, or veterinary
> device. Nothing displayed by the application establishes that a target is accurate, reachable,
> or clear of vessels. Independently verify every coordinate before every animal procedure.

## Start the native application

Follow [Installation](INSTALL.md), then build and open the development app:

```bash
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

The app starts a separately launched Python service through a typed protocol. The **Planning
service** section reports connection and project state. If backend discovery fails, the app says
**Backend not configured**; reconnecting does not substitute demo anatomy or fabricated data.

After the atlas opens, the workspace remains disabled behind **Confirm animal-only use**. The
acknowledgement checkbox starts unchecked. Read it, check it explicitly, then choose
**Acknowledge and Create Animal Plan** or **Open Existing Animal Plan…**. The app does not create
a project or send an acknowledgement to the Python service before that user action.

## Load the reviewed atlas

The current build accepts exactly:

```text
allen_mouse_25um, BrainGlobe package version 1.2
resolution [AP,DV,ML] = [25,25,25] µm
shape [AP,DV,ML]      = [528,320,456]
```

Use **Download reviewed 25 µm atlas** when the package is not already in the application cache.
The service validates the exact package identity before it becomes operational. The 10 µm atlas
is intentionally not shown or opened during this testing phase; pre-existing 10 µm cache files
are ignored and not deleted.

## Brain views

The mode bar exposes:

- **Dorsal** — the atlas dorsal surface on an AP-by-ML grid; only reviewed major-vessel geometry
  may be overlaid, and no such graph is currently loaded;
- **Coronal** — fixed AP plane, with DV rows and ML columns;
- **Sagittal** — fixed ML plane, with DV rows and AP columns;
- **Horizontal** — fixed DV plane, with AP rows and ML columns; and
- **3D** — an honest unavailable state in bridge protocol v1, not a placeholder rendering.

Only one selected mode fills the workspace. The coronal, sagittal, and horizontal modes each
retain their own depth. Use the slider, previous/next
buttons, or mouse wheel to change only that view. Drag to pan, pinch to zoom, and use the reset
button to return to aspect-fit.

Click a brain region to show a compact acronym/name label beside that point. Clicking elsewhere
replaces the label. Clicking never moves any slice, and switching modes restores the exact depth
and selection for the persisted viewer state.

Atlas values are BrainGlobe physical coordinates in micrometres. They are not bregma-relative
stereotaxic coordinates. See [Coordinate Systems](COORDINATE_SYSTEMS.md).

## Add an implant site by AP/ML/DV

An implant site is entered in millimetres from bregma, in named `[AP, ML, DV]` fields:

| Entry | Positive direction | Negative direction |
| --- | --- | --- |
| AP | anterior / forward | posterior / back |
| ML | right | left |
| DV | dorsal / up | deep / ventral |

For example, `AP -1.25`, `ML -0.70`, `DV -2.40` means 1.25 mm posterior, 0.70 mm left, and
2.40 mm deep/ventral from bregma.

The current build may save that exact entry as an **unprojected bregma target**. It does not infer
an Allen-atlas point from the numbers, draw a navigation marker, or calculate a trajectory. Those
operations remain locked until an explicit bregma/skull-to-atlas calibration with declared
landmarks, transform, units, atlas identity, and validation exists. An unprojected entry is not
usable for navigation.

## Major vessels

The primary UI does not expose population density, subject registration, or capillaries. Those
earlier evidence-layer functions remain archived in the backend so their tested provenance logic
is not lost, but they are not part of the current workflow.

The **Major vessels** status remains unavailable until a source provides all of the following:

- individual branch paths rather than endpoint chords or a scalar density field;
- source-preserved physical radii and units;
- exact atlas identity, axes, origin, voxel anchoring, and registration transforms;
- pinned bytes, hashes, license, specimen/reference identity, and review evidence; and
- enough registration and geometry information to avoid false slice intersections.

The app must not interpret “no reviewed graph loaded” as “no vessels present.”

## Save and reopen a project

Use **Save As…** to create a `.mouseplan` directory package and **Open…** to reopen one. The
backend, not the SwiftUI presentation layer, is authoritative for scientific state and dirty
revision tracking. Saved state can include:

- exact atlas identity and metadata digest;
- independent coronal, sagittal, and horizontal depths plus the optional region selection;
- archived subject-image and population-density state from older projects, without exposing it in
  the primary UI; and
- unprojected bregma-relative implant targets.

Project JSON is checksummed, and replacement is atomic. A previous package may be retained as the
exact sibling `.mouseplan.bak`; recovery from that backup does not prove scientific correctness.
Do not edit package JSON without expecting checksum validation to fail.

Opening another project, reconnecting, or quitting with unsaved changes requires an explicit
discard decision. Choose **Cancel** to keep working or save first when the changes matter.

Validate a package without opening the UI:

```bash
uv run --frozen mouse-brain-planner validate-project /absolute/path/Plan.mouseplan
```

## What not to infer

- 25 µm atlas sampling is not 25 µm targeting accuracy.
- A population density maximum is not a vessel trajectory or a vessel-free corridor.
- A user-supplied image is not automatically a vessel mask.
- Low registration residuals do not prove biological registration accuracy.
- An AP/ML/DV target stored from bregma is not projected into the atlas without calibration.
- The absence of a displayed collision, vessel, or structure is not evidence of safety.

Review [Scientific Validation](SCIENTIFIC_VALIDATION.md), [Atlas Data](ATLAS_DATA.md),
[Coordinate Systems](COORDINATE_SYSTEMS.md), and [Known Limitations](KNOWN_LIMITATIONS.md) before
using output in an experiment.
