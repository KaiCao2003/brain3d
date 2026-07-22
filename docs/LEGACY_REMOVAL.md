# Legacy Qt/VTK Removal

## Scope

The baseline contains two desktop products. The supported SwiftUI application launches the
Python bridge, while the default Python console command launches an older PySide6/PyVista/VTK
application. Phase 1 removes the latter from the default product and dependency graph.

## Legacy-only manifest

- `src/mouse_brain_planner/app.py`
- `src/mouse_brain_planner/gui/**`
- `src/mouse_brain_planner/rendering/scene_controller.py`
- Qt/VTK-specific GUI and scene-controller tests
- `--smoke-test` and `--no-download` CLI flags that configure only the Qt application
- PySide6, PyVista, PyVistaQt, and VTK default dependencies

`rendering/sagittal_cache.py` is a separate test-only 10 µm optimization with no supported
consumer. Because the MVP intentionally allows only the 25 µm atlas, it is removed from the
default package rather than coupled to the linked viewer.

## Reusable code that is not legacy

The following tested Python modules are retained and wired into the new product instead of being
deleted with the old GUI:

- named coordinate frames and anatomical transforms;
- stereotaxic calibration models/math;
- probe definitions, placements, and recording-site geometry;
- exact finite-segment measurement kernels;
- atlas slicing/point lookup and project persistence;
- population-density and subject-image provenance/registration.

## Removal sequence

1. Change the CLI so no subcommand prints help and an explicit `bridge` command starts the service.
2. Add tests proving CLI parsing/import does not import Qt/VTK.
3. Remove legacy modules and their UI-only tests from the package.
4. Remove Qt/VTK from base dependencies and regenerate the lockfile.
5. Install/test the minimal locked environment and build the native app.
6. Keep the deletion commit in Git history; do not copy the old stack into a second maintained
   `experimental` package.

## Rollback

The pre-removal implementation remains retrievable from Git commit
`51fe26d637b700d39944bbee86e3ea42ded4e7a2`. A historical bug investigation may inspect that
commit without restoring Qt/VTK to the supported package. Any proposal to revive it must explain
how duplicated state, dependencies, accessibility, and two-GUI maintenance will be avoided.
