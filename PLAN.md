# Recovery Roadmap

This roadmap starts from the product gaps visible in the current build. A phase is not complete
because backend classes or tests exist; it is complete only when the supported SwiftUI workflow
is usable end to end and its scientific limits are validated.

| Priority | Deliverable | Current state | Acceptance gate |
| --- | --- | --- | --- |
| 0 | Honest public baseline | In this repository | README, status inventory, limitations, source/license record, and reproducible checks agree with the code |
| 1 | Focused product surface | Not started | Remove or quarantine dead UI paths; every visible control completes a real workflow; legacy Qt/VTK is moved out of the supported path |
| 2 | Interactive tri-planar viewer | Not implemented | Coronal, sagittal, and horizontal panes share one AP/DV/ML cursor; sliders, wheel, click, keyboard, pan, zoom, crosshairs, region readout, and view persistence work across every legal slice |
| 3 | Supported 3D view | Not implemented | One production renderer provides brain/region geometry, orbit, pan, zoom, clipping planes, opacity, orientation markers, and two-way synchronization with the slice cursor |
| 4 | Trustworthy vessel paths | Not implemented | A pinned, licensed centerline graph has audited hashes, schema, units, axes, laterality, atlas registration, topology, and rendering in slices and 3D; population and subject-specific evidence remain visibly distinct |
| 5 | Stereotaxic calibration | Not implemented | Measured bregma/lambda/skull frame, DV zero, leveling, explicit transform, residuals, uncertainty, and independent round-trip validation exist before atlas target projection is enabled |
| 6 | Implant planning | Not implemented as a UI workflow | Target, entry, hardware, trajectory, sites, collisions, and uncertainty are visible and exercised end to end; no safety claim is derived from absent or population-only vessel data |
| 7 | Animal-study validation and release | Not started | Phantom/histology comparison, prospective workflow/usability evidence, clean-Mac qualification, SBOM, Developer ID, hardened runtime, notarization, and documented release criteria |

## Phase 1 — reduce before adding

- Decide on one supported UI and rendering stack.
- Move the PySide6/PyVista/VTK application to an explicit `legacy/` area or remove it.
- Make legacy rendering dependencies optional if they remain for reference.
- Remove unavailable buttons and workflows from the main product surface unless their unavailable
  state is necessary to communicate a known gap.
- Stop describing tested domain models as application features.

## Phase 2 — real x/y/z navigation

- Show coronal, sagittal, and horizontal views together.
- Maintain one cursor in named atlas physical coordinates and derived voxel indices.
- Support sliders, scroll-wheel stepping, click-to-move, keyboard stepping, pan, zoom, and reset.
- Draw synchronized crosshairs and show the annotation/region at the cursor.
- Preserve cursor and camera state in `.mouseplan` only after the interaction works.

Acceptance requires that every legal slice on every axis is reachable and that movement in any
pane correctly updates the other two panes without laterality or off-by-one errors.

## Phase 3 — supported 3D

- Use one renderer in the supported SwiftUI application.
- Render brain and selected-region geometry with explicit AP/DV/ML orientation.
- Add orbit, pan, zoom, clipping planes, opacity, and reset.
- Synchronize the 3D cursor and slice planes bidirectionally with tri-planar views.
- Validate real 25 µm atlas orientation and coordinate round trips, not only synthetic fixtures.

## Phase 4 — vessel geometry

The existing four-mouse density projection remains a contextual population layer. It must never
be relabeled as individual vessels.

Before integrating a vessel graph:

- select a trustworthy versioned source with a compatible license and documented experimental
  method;
- pin source bytes and audit graph schema, units, axes, laterality, radii, topology, source animal,
  and atlas registration;
- render centerlines in tri-planar and 3D views while retaining provenance;
- distinguish population paths from a current animal's subject-specific surface evidence; and
- expose no “safe distance” until registration error and geometric uncertainty have defensible
  definitions and validation.

## Phase 5 onward — calibration, planning, validation

Only after the viewer and evidence layers work should the app project bregma-relative targets,
display probe geometry, or perform collision analysis. The final gate is independent evidence on
the intended animal workflow; automated unit tests are necessary but insufficient.
