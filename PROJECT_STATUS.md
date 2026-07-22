# Project Status

Status reviewed: 2026-07-22

## Bottom line

Brain3D is an early technical prototype. The supported SwiftUI application now provides a usable
25 µm mouse-atlas browser: one full-size selected mode, independent movable coronal/sagittal/
horizontal depths, pan/zoom/wheel controls, compact click-to-identify region labels, and persisted
viewer state. It also preserves signed bregma AP/ML/DV entries. Real 3D anatomy, actual registered
major-vessel geometry, calibrated target projection, probe placement, and end-to-end surgical
analysis are still missing.

Public visibility is intended to make this gap inspectable. It is not a release or validation
claim.

## Evidence from the current implementation

### Slice navigation

The mode bar is exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`. Coronal, sagittal, and
horizontal each retain an independent persisted depth and expose a slider, previous/next buttons,
precise wheel stepping, direct pan, anchored zoom, and reset. A click replaces one compact region
label on the current frame without changing any depth. Stale frames and revisions are rejected.

### 3D

The same view model rejects the 3D mode with the explicit message that bridge protocol v1 does
not expose a renderer. `WorkspaceView.swift` displays an unavailable-state card. Historical
Qt/VTK code is available only in Git commit `51fe26d`; it does not make 3D available in the
supported SwiftUI app.

### Blood vessels

Population density and subject-image registration remain archived in the backend but are removed
from the primary UI. The visible product path is major-vessels-only and currently reports that no
reviewed graph is loaded.

VesSAP/VesselGraph was audited down to raw nodes, edges, radii, threshold code, warped labels, and
elastix artifacts. Its public files do not provide a complete auditable subject-to-Allen mapping
or edge-linked branch paths. Drawing endpoint chords would create false slice intersections, so
the overlay remains fail-closed. Neither archived evidence layer supports clearance.

### Implant coordinates

The SwiftUI sidebar accepts named bregma-relative AP/ML/DV millimetres with the requested sign
convention: negative AP is posterior, negative ML is left, and negative DV is deep/ventral. The
backend preserves those exact values. It intentionally does not draw them on the atlas because no
validated bregma/skull-to-Allen calibration exists.

## Source inventory by maturity

| Area | Role | Product status |
| --- | --- | --- |
| `native/Brain3D/Sources/Brain3DApp/` | SwiftUI windows, acknowledgement gate, sidebar, interactive atlas canvas | Current experimental UI |
| `native/Brain3D/Sources/Brain3DCore/` | Bridge client, typed protocol, validation policies | Current infrastructure |
| `src/mouse_brain_planner/bridge/` | Python service called by SwiftUI | Current infrastructure |
| `src/mouse_brain_planner/atlas/` | Pinned BrainGlobe atlas access and identity checks | Current infrastructure |
| `src/mouse_brain_planner/rendering/` | Full-resolution raster slices and dorsal projections | Current interactive viewer backend |
| `src/mouse_brain_planner/persistence/` | Checksummed `.mouseplan` packages and migrations | Current infrastructure |
| `src/mouse_brain_planner/vasculature/` | Population density and subject-image registration | Archived evidence layers, not vessel geometry |
| `src/mouse_brain_planner/coordinates/` | Named frames and transform utilities | Mixed current infrastructure and future groundwork |
| `src/mouse_brain_planner/analysis/` | Exact clipped voxel DDA and atlas-axis conversion | Verified engine, not yet exposed in the app |
| `src/mouse_brain_planner/domain/` | Project models plus probe/stereotaxy/craniotomy types | Mixed; many types are not exposed in the app |
| `src/mouse_brain_planner/surgery/` | Trajectory, craniotomy, stereotaxy, and measurement algorithms | Experimental groundwork, not a usable workflow |
| Git commit `51fe26d` | Last complete PySide6/PyVista/VTK implementation | Historical only; removed from current package |

The large number of functions is therefore not evidence of a large working feature set. The
current tree combines the hybrid prototype with future domain groundwork. Phase 1 removed the
older UI stack and its dependencies; `mouse-brain-planner` now requires an explicit command and
cannot launch a second GUI.

## What has engineering coverage

Tests cover protocol validation, atlas identity, independent viewer state, coordinate invariants,
deterministic rendering, viewport/scroll math, project checksums/migrations, source hashes,
registration math, and lower-level geometry. Native tests cover strict response shapes and safety
gates. The completed viewer checkpoint has Python `389 passed, 1 skipped` and Swift `62` tests.
Actual macOS UI automation changed coronal and sagittal depths independently, switched modes,
replaced a region selection, and confirmed that neither clicking nor switching moved a depth.

These tests answer questions such as “does this transform round-trip?”, “did the project reopen
with the same depths?”, and “can a user navigate the atlas?” They do not answer “is this an
individual vessel?” or “is this procedure safe?” No prospective animal study, phantom targeting study,
histological accuracy study, or formal usability validation has been completed.

## Data boundary

- The atlas is BrainGlobe `allen_mouse_25um` package `1.2`; 25 µm is sampling resolution, not
  targeting accuracy.
- The integrated vascular source is Kim 2022 Mendeley Data v1,
  DOI `10.17632/stxvn5sv44.1`, CC BY 4.0. It provides population density, not vessel paths.
- The VesSAP/VesselGraph reference has source-proven 3 µm specimen voxels and radii, but its
  public registration package and edge geometry are insufficient for an exact Allen slice
  overlay; it remains unintegrated.
- Atlas and data archives are downloaded to user caches and are not committed to this repository.

## Minimum bar before animal-procedure use

This project should not be used to guide an animal procedure until all of the following have been
implemented and independently validated:

1. ~~movable AP/DV/ML slice navigation with independent persisted depths~~ — implemented;
2. a supported interactive 3D view synchronized with the slice cursor;
3. a clearly sourced vessel representation that distinguishes population reference data from
   subject-specific evidence;
4. measured bregma/lambda/skull-to-atlas calibration with residuals and uncertainty;
5. visible target/entry/trajectory behavior exercised end to end, not merely lower-level models;
6. independent phantom, histology, animal-workflow, and usability evidence; and
7. a packaged, signed, notarized build qualified on a clean Mac.

Until then, treat the repository as research and engineering work in progress.
