# Code Audit

Audit baseline: `main` commit `51fe26d637b700d39944bbee86e3ea42ded4e7a2`, reviewed on
2026-07-22 before the end-to-end planner refactor.

This document records evidence about what is reachable from the supported product, what is only
covered by tests, and what belongs to the superseded Qt/VTK application. A symbol is not deleted
merely because a text search finds no caller: the audit checks static imports, repository-wide
references, dynamic bridge registration, and an actual runtime entry point.

## Classification

- `PRODUCT_REACHABLE`: reachable from the SwiftUI application through the Python bridge or an
  explicit supported CLI command.
- `TEST_ONLY`: reached by tests but not a supported runtime entry point.
- `LEGACY_ONLY`: reached only from the former Qt/PyVista/VTK application.
- `ORPHANED_BUT_REUSABLE`: not product-reachable, but required by the target planner and covered
  by useful scientific tests.
- `DELETE_CANDIDATE`: no supported caller, no retained roadmap consumer, and no independent
  compatibility obligation found.
- `UNKNOWN_DYNAMIC_USAGE`: static evidence is insufficient; retain until runtime evidence exists.

## Audit method

1. Trace imports from `native/Brain3D` backend launch, `mouse_brain_planner.bridge.server`, each
   CLI command, and every test collector.
2. Search all symbol references and bridge method strings with `rg`; inspect dynamic
   `dispatcher.register(...)` calls separately.
3. Launch/test the native package and bridge transport, then compare methods requested by
   `PlannerViewModel.swift` with registered Python handlers.
4. Classify the current path before changing it; record affected tests with each removal.

## Baseline

### Repository and environment

```text
branch: main, clean, tracking origin/main
commit: 51fe26d637b700d39944bbee86e3ea42ded4e7a2
remote: https://github.com/KaiCao2003/brain3d.git
host: macOS 26.5.2 (25F84), arm64
system python: 3.14.3
project python through uv: 3.12.13
uv: 0.10.6
Swift: 6.3.3, target arm64-apple-macosx26.0
tracked files: 156
Python test files: 45
Swift test files: 7
```

The system Python is outside the project contract. All Python evidence below uses `uv run
--frozen`, which selects Python 3.12.13 from the locked environment.

### Commands and exact pre-refactor results

| Command | Exit | Result |
| --- | ---: | --- |
| `uv lock --check` | 0 | 76 packages resolved; lock accepted |
| `uv run --frozen ruff format --check .` | 0 | 106 files already formatted |
| `uv run --frozen ruff check .` | 0 | all checks passed |
| `uv run --frozen mypy --no-incremental` | 0 | no issues in 61 source files |
| `QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true uv run --frozen pytest -q` | 0 | 484 passed, 1 opt-in real-archive test skipped, 487 VTK deprecation warnings |
| `swift test --package-path native/Brain3D` | 0 | 42 tests in 7 suites passed |
| `native/Brain3D/Scripts/build-app.sh` | 0 | production Swift executable and development `.app` built |
| `codesign --verify --deep --strict native/Brain3D/build/Brain3D.app` | 0 | ad-hoc signature verified |

These results are engineering baseline evidence, not evidence that the supported UI is usable.
The Swift test target contains `Brain3DCore` only; it does not exercise `Brain3DApp` view
interaction. Most of the 487 warnings come from tests of the legacy VTK path.

## Runtime entry points

| Entry point | Current behavior at baseline | Status | Decision |
| --- | --- | --- | --- |
| `native/Brain3D/.../Brain3DApp.swift` | Supported macOS UI; discovers `.venv` and launches `python -u -m mouse_brain_planner.bridge.server` | `PRODUCT_REACHABLE` | Retain and extend |
| `python -m mouse_brain_planner.bridge.server` | NDJSON service with atlas, project, density, image-registration, and unprojected-target handlers | `PRODUCT_REACHABLE` | Retain; split by protocol responsibility as v2 grows |
| `mouse-brain-planner atlas ...` | Explicit atlas cache commands | `PRODUCT_REACHABLE` | Retain under explicit subcommands |
| `mouse-brain-planner validate ...` | Explicit project validation | `PRODUCT_REACHABLE` | Rename to `validate-project`, with a documented compatibility window if needed |
| `mouse-brain-planner` with no subcommand | Imports `app.py` and silently launches the old Qt UI | `LEGACY_ONLY` | Remove; print help without importing Qt |
| `mouse-brain-planner --smoke-test` | Exercises only the old Qt UI | `LEGACY_ONLY` | Remove with Qt UI tests |

## Path-level audit table

| Path / symbol | Current caller | Product status | Decision | Reason | Tests affected |
| --- | --- | --- | --- | --- | --- |
| `native/Brain3D/Sources/Brain3DApp` | macOS executable | `PRODUCT_REACHABLE` | Extend | Sole supported GUI | Add app/ViewModel tests; current core tests are insufficient |
| `native/Brain3D/Sources/Brain3DCore` | Swift app | `PRODUCT_REACHABLE` | Extend | Typed subprocess transport and fail-closed validation | Existing 42 Swift core tests |
| `bridge/server.py` | Swift subprocess | `PRODUCT_REACHABLE` | Retain | Framing, dispatcher, atlas opening/slicing | Bridge unit/integration tests |
| `bridge/planning.py` | Dynamic handler registration | `PRODUCT_REACHABLE` | Split incrementally | Too many project/vascular/session duties in one file | Planning and persistence integration tests |
| `bridge/atlas_interaction.py` slice/point methods | Dispatcher; slice used by Swift, point not yet used | Mixed `PRODUCT_REACHABLE` / `ORPHANED_BUT_REUSABLE` | Reuse for tri-planar cursor/region lookup | Backend already supports arbitrary slice and point queries | Atlas interaction tests |
| `bridge/implant_targets.py` | Swift sidebar | `PRODUCT_REACHABLE` | Migrate, do not infer calibration | Preserves exact unprojected AP/ML/DV | Implant bridge tests and migrations |
| `atlas/brainglobe_adapter.py` | Bridge and CLI | `PRODUCT_REACHABLE` | Retain | Allowlisted atlas and metadata boundary | Atlas adapter tests |
| `rendering/slice_renderer.py` | `atlas.slice` | `PRODUCT_REACHABLE` | Retain | Arbitrary index rendering already exists | Slice renderer tests |
| `persistence/project_io.py` provenance-aware APIs | Bridge | `PRODUCT_REACHABLE` | Extend with deterministic migrations | Atomic/checksummed persistence is valuable | Project I/O and integration tests |
| `coordinates/atlas_space.py` | Atlas/bridge/rendering | `PRODUCT_REACHABLE` | Centralize all order conversions here or a named adjacent module | Prevent distributed AP/DV/ML permutations | Coordinate golden tests |
| `coordinates/transforms.py` | Tests only | `ORPHANED_BUT_REUSABLE` | Connect through calibration protocol | Required fit/apply/invert/compose math already exists | Anatomical transform tests |
| `domain/*probe*`, `*stereotaxy*`, `*transform*`, `*measurement*` | Tests only | `ORPHANED_BUT_REUSABLE` | Integrate behind protocol v2 | Target planner needs their validated constraints | Existing surgery/domain tests plus new bridge tests |
| `surgery/trajectory.py` | Tests only | `ORPHANED_BUT_REUSABLE` | Connect to probe plan service | Placement/site groundwork exists | Probe trajectory tests |
| `surgery/stereotaxy.py` | Tests only | `ORPHANED_BUT_REUSABLE` | Connect to calibration service | Landmark calibration groundwork exists | Stereotaxy tests |
| `surgery/measurements.py` | Tests only | `ORPHANED_BUT_REUSABLE` | Retain exact segment-distance kernel; rename centerline-only APIs before exposure | Needed by future radius-aware clearance | Measurement tests |
| `surgery/craniotomy.py` | Tests only | `TEST_ONLY` | Move out of MVP product package or defer | Not a current MVP consumer | Craniotomy tests |
| `vasculature/reference_*`, `density_overlay.py` | Swift bridge | `PRODUCT_REACHABLE` | Retain with density-only semantics; add orthogonal slices | Source is scalar population density, never vessel geometry | Density/store/integration tests |
| `vasculature/subject_image.py`, `registration.py`, `subject_overlay.py` | Swift bridge | `PRODUCT_REACHABLE` | Retain; add explicit surface-mask analysis | 2D image cannot support deep clearance | Subject image/registration tests |
| `rendering/sagittal_cache.py` | Tests only | `TEST_ONLY` | Remove from MVP package | Optimizes a deferred 10 µm path with no product caller | Sagittal cache tests |
| `gui/**` | `app.py` and Qt tests | `LEGACY_ONLY` | Remove from default package; preserve history in Git | Second UI/state/rendering stack conflicts with supported path | All `tests/gui/**` and Qt worker tests |
| `app.py` | CLI no-subcommand path | `LEGACY_ONLY` | Remove after CLI behavior changes | It makes an unsupported GUI the default | Smoke and CLI default tests |
| `rendering/scene_controller.py` | Legacy Qt UI/tests | `LEGACY_ONLY` | Remove from default package | PyVista-only scene state duplicates the target Swift path | Scene-controller and Qt atlas tests |

## Bridge runtime reachability

The Python dispatcher registers more methods than Swift currently calls. This is deliberate
dynamic usage and must not be inferred from Python imports alone.

The supported primary Swift workspace currently requests: `hello`, `state.get`, `atlas.open`,
`atlas.slice`, `atlas.dorsal`, `project.new`, `project.open`, `project.save`, `implant.list`,
`implant.add`, `implant.remove`, `viewer.state.get`, `viewer.slice.set`,
`viewer.slice.render`, and `viewer.region.pick`.

Legacy population-density and subject-image bridge calls remain implemented behind archived
ViewModel paths, but the primary UI no longer exposes them. Their presence is migration and
research-code retention, not evidence that they are supported surgical-planning inputs.

Registered but not currently requested by the primary Swift workspace include `atlas.list`,
`atlas.regions`, `atlas.search`, `atlas.point`, `atlas.mesh`, and `shutdown`. The independent
viewer now performs region lookup through `viewer.region.pick`; the older `atlas.point` handler
is retained for protocol compatibility. `atlas.mesh` remains non-product until the optional 3D
renderer has an approved architecture. `shutdown` is a transport/control method rather than a
visible UI feature.

## Known product contradictions

- The project schema retains legacy linked-cursor fields for migration; the supported viewer uses
  independent slice depths plus a replace-only region selection.
- Swift exposes an unavailable 3D button while real rendering code exists only in the unsupported
  Qt path.
- Base installation includes Qt/VTK because legacy code remains inside the default package.
- The console command without a subcommand launches the unsupported application.
- The archived density overlay is reproducible population context, not individual blood vessels.
- Passing Python GUI tests primarily proves the removed Qt path, not the Swift product.

## Scientific and data risks to keep fail-closed

- Allen atlas physical coordinates are not bregma-relative coordinates.
- No audited reference-only bregma profile currently exists; no implicit transform may be added.
- Population density has no vessel centerlines, radius, or retained depth in its dorsal maximum
  projection.
- Subject dorsal images have no automatic vessel segmentation and cannot represent deep vessels.
- Existing vessel polyline distance code lacks radius, probe envelope, margin, uncertainty, and a
  spatial index; it cannot be exposed as clearance.
- Probe profiles may not be called manufacturer-verified without complete source and independent
  review records.

## Phase 1 removal gate

Before deleting legacy files, the refactor must demonstrate all of the following:

1. no supported Swift/bridge import reaches Qt/VTK;
2. CLI no-subcommand and explicit bridge behavior have replacement tests;
3. minimal dependency installation can import and run the bridge without Qt/VTK;
4. tests retained from scientific modules remain green independently of GUI tests; and
5. Git history preserves the removed implementation for forensic reference.

The symbol-by-symbol appendix below records the complete reference scan. Ambiguous dynamic
consumers would remain `UNKNOWN_DYNAMIC_USAGE`; this scan found none in the enumerated set.

## Enumerated symbol audit

The repository-wide search found no `getattr`, `importlib`, package entry-point, or method-string
loader for the functions below. Dynamic usage is confined to explicit bridge method
registration, which was audited separately. Therefore none of these symbols remains
`UNKNOWN_DYNAMIC_USAGE`.

| Symbol | Current caller at baseline | Classification | Phase decision |
| --- | --- | --- | --- |
| `paths.configure_qt_environment` | `gui/__init__.py` import side effect | `LEGACY_ONLY` | Deleted with the Qt package |
| `coordinates.transforms.fit_anatomical_transform` | transform tests | `ORPHANED_BUT_REUSABLE` | Retain and connect to calibration |
| `coordinates.transforms.transform_point` | transform/stereotaxy tests | `ORPHANED_BUT_REUSABLE` | Retain and connect to calibration/projection |
| `coordinates.transforms.transform_points` | transform tests | `ORPHANED_BUT_REUSABLE` | Retain for bounded batch transforms |
| `coordinates.transforms.transform_vector` | transform tests | `ORPHANED_BUT_REUSABLE` | Retain for probe directions |
| `coordinates.transforms.invert_transform` | transform tests | `ORPHANED_BUT_REUSABLE` | Retain for explicit inverse mapping |
| `coordinates.transforms.compose_transforms` | transform tests | `ORPHANED_BUT_REUSABLE` | Retain for named transform chains |
| `surgery.stereotaxy.calibrate_skull_landmarks` | stereotaxy/probe tests | `ORPHANED_BUT_REUSABLE` | Retain and expose through calibration service |
| `surgery.measurements.point_to_point_distance` | measurement tests | `ORPHANED_BUT_REUSABLE` | Retain as explainable geometry primitive |
| `surgery.measurements.point_to_line_distance` | measurement tests | `ORPHANED_BUT_REUSABLE` | Retain as explainable geometry primitive |
| `surgery.measurements.path_length` | measurement tests | `ORPHANED_BUT_REUSABLE` | Retain for trajectory/region summaries |
| `surgery.measurements.angle_between_directions` | measurement tests | `ORPHANED_BUT_REUSABLE` | Retain for placement inspection |
| `surgery.measurements.distance_between_probe_centerlines` | measurement tests | `ORPHANED_BUT_REUSABLE` | Retain, keep centerline-only naming |
| `surgery.measurements.nearest_vessel_distance` | measurement tests | `ORPHANED_BUT_REUSABLE` | Keep compatibility temporarily; rename to centerline distance before product exposure |
| `surgery.trajectory.placement_from_entry_target` | probe/measurement tests | `ORPHANED_BUT_REUSABLE` | Retain for `ENTRY_AND_TARGET` |
| `surgery.trajectory.placement_from_entry_angles_depth` | probe tests | `ORPHANED_BUT_REUSABLE` | Retain for `ENTRY_ANGLES_DEPTH` |
| `surgery.trajectory.placement_from_bregma_relative_mm` | probe tests | `ORPHANED_BUT_REUSABLE` | Retain; expose only after active calibration passes QC |
| `surgery.trajectory.attach_surface_entries` | probe tests | `ORPHANED_BUT_REUSABLE` | Retain behind a validated surface-intersection service |
| `surgery.trajectory.placed_recording_sites` | probe tests | `ORPHANED_BUT_REUSABLE` | Retain and expose in plan/region analysis |
| `surgery.trajectory.placement_permits_final_export` | probe tests | `ORPHANED_BUT_REUSABLE` | Retain verification/provenance gate |
| `surgery.craniotomy.craniotomy_metrics` | craniotomy tests | `DELETE_CANDIDATE` for MVP | Leave isolated for now; remove or move before Phase 4 if no surface consumer exists |
| `surgery.craniotomy.craniotomy_outline_points` | craniotomy tests | `DELETE_CANDIDATE` for MVP | Same decision as craniotomy metrics |
| `domain.implant_site_models.validate_bregma_decimal_inputs` | unprojected-target test | `DELETE_CANDIDATE` | Remove when bridge/Swift parsing is consolidated in protocol v2 |
| `domain.implant_site_models.unprojected_bregma_target_summary` | unprojected-target test | `DELETE_CANDIDATE` | Remove duplicated presentation helper during target migration |
| `persistence.project_io.load_project` | compatibility tests | `TEST_ONLY` | Deprecate; product uses `load_project_with_provenance` |
| `rendering.sagittal_cache.prepare_sagittal_cache` | sagittal-cache tests only | `DELETE_CANDIDATE` | Deleted with deferred 10 µm cache path |
| `vasculature.registration.transform_image_pixels_to_atlas` | registration tests | `ORPHANED_BUT_REUSABLE` | Retain for 2D surface-entry analysis |
| `gui.dialogs.dorsal_vascular_registration.DorsalVascularRegistrationDialog` | Qt dialog tests only; no `MainWindow` caller | `DELETE_CANDIDATE` | Deleted; Swift already has `VascularRegistrationSheet` |

## Phase 1 execution evidence

The single-product-path cleanup was then applied in the same audited working tree:

- the no-subcommand CLI now prints help and returns 2;
- `mouse-brain-planner bridge` is an explicit, tested service entry point;
- `app.py`, `gui/**`, `scene_controller.py`, `sagittal_cache.py`, and their legacy-only tests were
  deleted; the prior implementation remains at Git commit `51fe26d`;
- PySide6, PyVista, PyVistaQt, VTK, pytest-qt, PyInstaller, unused direct pandas, and unused pooch
  declarations were removed;
- the lock resolved 48 packages instead of 76 and contains none of those removed packages;
- the retained default runtime imports exactly the BrainGlobe/array/model/image dependencies
  documented in `pyproject.toml`;
- `.venv/bin/python scripts/verify_minimal_runtime.py` confirmed all five forbidden module roots
  are unavailable and completed a real explicit-CLI `hello`/`shutdown` exchange; and
- the retained suite completed with `377 passed, 1` external real-archive test skipped and no VTK
  warnings.

Removing `tests/conftest.py` initially caused eight fixture-package import failures during pytest
collection. It was restored as a one-line, side-effect-free repository test root; all former
Qt/PyVista environment mutation was removed. This is evidence that the file had a non-GUI pytest
role and was not a valid deletion candidate.

The source and runtime scans prove the dependency/path boundary. They do not prove live SwiftUI
control behavior: no automated native UI target existed at this phase, and no running-window
click journey was used to classify handlers.
