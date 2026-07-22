# Project Status

Status reviewed: 2026-07-22

## Bottom line

Brain3D is an early technical prototype, not a usable animal-surgery planner. The source tree has
working infrastructure for a pinned atlas, static raster output, data provenance, image
registration, and project persistence. The interactions that define the intended product —
movable linked slices, real 3D anatomy, actual vessel geometry, calibrated target projection, and
a focused end-to-end planning flow — are missing from the supported SwiftUI application.

Public visibility is intended to make this gap inspectable. It is not a release or validation
claim.

## Evidence from the current implementation

### Slice navigation

`native/Brain3D/Sources/Brain3DApp/PlannerViewModel.swift` requests a single slice for each
orthogonal mode and sets its index to `shapeVoxels[axis] / 2`. The SwiftUI workspace has buttons
to switch orientations, but it has no slice slider, numeric index input, wheel handling, movable
crosshair, or shared AP/DV/ML cursor. Consequently, the user cannot move through the volume or
inspect an arbitrary coordinate.

### 3D

The same view model rejects the 3D mode with the explicit message that bridge protocol v1 does
not expose a renderer. `WorkspaceView.swift` displays an unavailable-state card. Historical
Qt/VTK code is available only in Git commit `51fe26d`; it does not make 3D available in the
supported SwiftUI app.

### Blood vessels

The integrated published layer is prepared by `src/mouse_brain_planner/vasculature/` from a
four-mouse vascular length-density field. It is a scalar dorsal maximum projection, not a graph
of vessels. It has no centerlines, edges, branch topology, diameter, or retained DV location.

The application can also register a user-supplied dorsal image. That path does not automatically
segment vessels and cannot infer vessel depth. Neither layer supports vessel clearance.

### Implant coordinates

The SwiftUI sidebar accepts named bregma-relative AP/ML/DV millimetres with the requested sign
convention: negative AP is posterior, negative ML is left, and negative DV is deep/ventral. The
backend preserves those exact values. It intentionally does not draw them on the atlas because no
validated bregma/skull-to-Allen calibration exists.

## Source inventory by maturity

| Area | Role | Product status |
| --- | --- | --- |
| `native/Brain3D/Sources/Brain3DApp/` | SwiftUI windows, acknowledgement gate, sidebar, static atlas canvas | Current experimental UI |
| `native/Brain3D/Sources/Brain3DCore/` | Bridge client, typed protocol, validation policies | Current infrastructure |
| `src/mouse_brain_planner/bridge/` | Python service called by SwiftUI | Current infrastructure |
| `src/mouse_brain_planner/atlas/` | Pinned BrainGlobe atlas access and identity checks | Current infrastructure |
| `src/mouse_brain_planner/rendering/` | Raster slices and dorsal projections | Current infrastructure, not interactive rendering |
| `src/mouse_brain_planner/persistence/` | Checksummed `.mouseplan` packages and migrations | Current infrastructure |
| `src/mouse_brain_planner/vasculature/` | Population density and subject-image registration | Partial evidence layers, not vessel geometry |
| `src/mouse_brain_planner/coordinates/` | Named frames and transform utilities | Mixed current infrastructure and future groundwork |
| `src/mouse_brain_planner/domain/` | Project models plus probe/stereotaxy/craniotomy types | Mixed; many types are not exposed in the app |
| `src/mouse_brain_planner/surgery/` | Trajectory, craniotomy, stereotaxy, and measurement algorithms | Experimental groundwork, not a usable workflow |
| Git commit `51fe26d` | Last complete PySide6/PyVista/VTK implementation | Historical only; removed from current package |

The large number of functions is therefore not evidence of a large working feature set. The
current tree combines the hybrid prototype with future domain groundwork. Phase 1 removed the
older UI stack and its dependencies; `mouse-brain-planner` now requires an explicit command and
cannot launch a second GUI.

## What has engineering coverage

Tests cover protocol validation, atlas identity, coordinate invariants, deterministic rendering,
project checksums/migrations, source hashes, registration math, and lower-level geometry. Native
tests cover the Swift bridge contracts and safety gates.

These tests answer questions such as “does this transform round-trip?” and “did the project reopen
with the same bytes?” They do not answer “can a user navigate the brain?”, “is this an individual
vessel?”, or “is this procedure safe?” No prospective animal study, phantom targeting study,
histological accuracy study, or formal usability validation has been completed.

## Data boundary

- The atlas is BrainGlobe `allen_mouse_25um` package `1.2`; 25 µm is sampling resolution, not
  targeting accuracy.
- The integrated vascular source is Kim 2022 Mendeley Data v1,
  DOI `10.17632/stxvn5sv44.1`, CC BY 4.0. It provides population density, not vessel paths.
- A separate published tracing dataset, DOI `10.17632/mjtyry6v85.1`, is documented only as a
  candidate. It is not integrated. Its graph schema, coordinate frame, units, hashes,
  registration, and suitability must be audited before use.
- Atlas and data archives are downloaded to user caches and are not committed to this repository.

## Minimum bar before animal-procedure use

This project should not be used to guide an animal procedure until all of the following have been
implemented and independently validated:

1. linked, movable AP/DV/ML slice navigation with orientation and laterality checks;
2. a supported interactive 3D view synchronized with the slice cursor;
3. a clearly sourced vessel representation that distinguishes population reference data from
   subject-specific evidence;
4. measured bregma/lambda/skull-to-atlas calibration with residuals and uncertainty;
5. visible target/entry/trajectory behavior exercised end to end, not merely lower-level models;
6. independent phantom, histology, animal-workflow, and usability evidence; and
7. a packaged, signed, notarized build qualified on a clean Mac.

Until then, treat the repository as research and engineering work in progress.
