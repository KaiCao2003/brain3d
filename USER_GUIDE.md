# User Guide

Mouse Brain Surgery Planner is a native SwiftUI workspace backed by a Python scientific service.
The current testing build displays one reviewed 25 µm mouse atlas, can overlay a published
population vascular length-density field, can register a user-supplied dorsal image, and can
preserve unprojected bregma-relative implant coordinates.

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

- **Dorsal** — the atlas dorsal surface on an AP-by-ML grid; this is where vascular density and a
  registered subject dorsal image are composited over the brain;
- **Coronal** — fixed AP plane, with DV rows and ML columns;
- **Sagittal** — fixed ML plane, with DV rows and AP columns;
- **Horizontal** — fixed DV plane, with AP rows and ML columns; and
- **3D** — an honest unavailable state in bridge protocol v1, not a placeholder rendering.

The coronal, sagittal, and horizontal modes each display only the atlas midpoint. There is no
slice slider, mouse-wheel stepping, index field, pan/zoom interaction, linked crosshair, or shared
tri-planar cursor in the current SwiftUI build. The mode buttons change fixed images; they do not
let the user navigate through x/y/z.

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

## Show the published population density

The optional **Population density** layer uses the pinned source:

- Yongsoo Kim, *Cerebrovascular, pericyte, and neuronal cell type mapping data 2022*;
- [Mendeley Data v1, DOI 10.17632/stxvn5sv44.1](https://data.mendeley.com/datasets/stxvn5sv44/1),
  CC BY 4.0; and
- associated paper: Wu et al., *Quantitative relationship between cerebrovascular network and
  neuronal cell types in mice*, Cell Reports 2022,
  [doi:10.1016/j.celrep.2022.110978](https://doi.org/10.1016/j.celrep.2022.110978).

Choose **Download and prepare published reference (~311 MB)**. The service accepts only the
pinned version-1 archive, verifies its exact byte count and SHA-256, extracts only the reviewed
density and template members, validates their headers, and binds the prepared result to the exact
open atlas metadata. Preparation is cached after successful validation.

Then enable **Show population reference density** in the Dorsal view. The transparent red-to-
magenta overlay is a DV maximum projection of a scalar vascular length-density field. Its display
legend declares the value window and units. Overlay alpha rises with the windowed density value,
and pixels outside the nonzero Allen annotation footprint remain fully transparent so the layer
stays over the displayed brain rather than tinting the surrounding canvas.

Interpret this layer narrowly:

- it summarizes four fixed adult C57BL/6 mouse brains using a 100 µm local window;
- it is a population reference, not an image of the current animal;
- it contains no individual vessel centerlines, diameters, or paths;
- the source ML polarity is not documented, so the reviewed conversion is explicitly
  symmetrized; and
- it cannot calculate or prove vessel clearance, safe entry, or collision avoidance.

Turning the layer off removes the transparent density composite; it does not change the atlas or
subject image.

## Import and register a subject dorsal image

The **Subject dorsal image** layer is separate from the published population density.

1. Choose **Import subject image** and select one PNG, JPEG, or TIFF.
2. Confirm the displayed filename, dimensions, byte count, and SHA-256 provenance.
3. Choose **Register**.
4. Enter at least two distinct correspondences between subject-image pixel column/row and atlas
   dorsal AP/ML physical coordinates in micrometres.
5. Explicitly confirm laterality, then run the registration.
6. Review the returned residuals and the composite in the Dorsal view.

The registration maps the user-supplied pixels onto the atlas dorsal grid. It does not perform or
validate vessel segmentation. If the source image has an opaque background, that background may
also cover the atlas; a transparent, independently reviewed vessel mask is preferable when the
goal is to view subject surface vessels. A registered image still does not establish depth,
diameter, identity, or clearance for any vessel.

In the dorsal composite, the published population density is drawn over the atlas and the
registered subject image is drawn above the density. These are different evidence layers and must
not be described as one combined vascular truth.

## Save and reopen a project

Use **Save As…** to create a `.mouseplan` directory package and **Open…** to reopen one. The
backend, not the SwiftUI presentation layer, is authoritative for scientific state and dirty
revision tracking. Saved state can include:

- exact atlas identity and metadata digest;
- the currently selected fixed atlas-view mode;
- byte-preserved subject image provenance, landmarks, transform, laterality, and residuals;
- prepared population-density provenance and visibility state; and
- unprojected bregma-relative implant targets.

Project JSON is checksummed, and replacement is atomic. A previous package may be retained as the
exact sibling `.mouseplan.bak`; recovery from that backup does not prove scientific correctness.
Do not edit package JSON without expecting checksum validation to fail.

Opening another project, reconnecting, or quitting with unsaved changes requires an explicit
discard decision. Choose **Cancel** to keep working or save first when the changes matter.

Validate a package without opening the UI:

```bash
uv run --frozen mouse-brain-planner validate /absolute/path/Plan.mouseplan
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
