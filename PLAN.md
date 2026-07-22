# End-to-End Implementation Plan

A phase is complete only when its behavior is reachable through the supported SwiftUI + Python
bridge path, persisted where required, covered by the stated tests, and documented honestly.
Backend classes or passing legacy tests are not product completion.

| Phase | Deliverable | Current state | Acceptance gate |
| --- | --- | --- | --- |
| 0 | Baseline, reachability audit, risk inventory, architecture ADR | **Complete** | `docs/CODE_AUDIT.md`, baseline commands/results, symbol classifications, ADR-005, rollback points |
| 1 | One product path and minimal dependencies | **Complete** | Explicit CLI, legacy Qt/VTK removed, default environment has no Qt/VTK, headless bridge verification and CI |
| 2 | Independent atlas-slice viewer | **Complete** | One full-size mode; every legal slice reachable; independent persisted depths; click/wheel/slider/buttons/pan/zoom; compact region readout |
| 3 | Calibration and target projection | Not started | Calibration CRUD/QC, active transform, legacy-target conversion, AP/ML/DV projection, fail-closed Swift workflow |
| 4 | Probe catalog and placement | Not started | Sourced/custom profiles, placement modes, entry/target/tip/shanks/sites, multi-shank-ready API and overlays |
| 5 | Region traversal | Not started | 3D voxel DDA, exact depth segments, site assignments, inspector/export, synthetic thin-region tests and atlas smoke |
| 6 | Density and subject-surface vessel workflows | Partial groundwork only | Orthogonal density slices, strict density semantics, reviewed 2D mask, surface entry distance/overlap, “deep vessels not evaluated” |
| 7 | Registered 3D vessel graph and clearance | Not started | Graph/radius/provenance schema, registration, spatial index, radius/envelope/margin/uncertainty analysis, multi-shank conflicts |
| 8 | Optional supported 3D renderer | Not started | Renderer ADR, shared canonical scene state, brain/probe/vessel display, picking and clipping; no duplicate analysis logic |
| 9 | Animal-study validation and distribution | Not started | Phantom/histology/usability evidence, performance record, deterministic bundled runtime, SBOM, Developer ID/notarization, clean-Mac gate |

## Phase 0 evidence

- Pre-refactor baseline: Git `51fe26d`, Python 484 passed/1 opt-in skipped, Swift 42/42.
- Entry-point, handler, runtime-import, and enumerated-symbol audit in
  [Code Audit](docs/CODE_AUDIT.md).
- Canonical architecture in [Architecture](docs/ARCHITECTURE.md) and
  [ADR-005](docs/ADR-005-independent-slice-viewer.md).

## Phase 1 result

- `mouse-brain-planner` without a subcommand prints help and returns 2.
- Explicit commands include `bridge`, `atlas ...`, and `validate-project`.
- The old PySide6/PyVista/VTK application, scene controller, 10 µm sagittal cache, and their
  legacy-only tests were deleted; Git `51fe26d` is the rollback snapshot.
- Base dependencies retain only the headless scientific stack; the lock fell from 76 to 48
  packages and contains no Qt/VTK/PyInstaller stack.
- `scripts/verify_minimal_runtime.py` proves forbidden modules are unavailable and completes a
  real bridge handshake.
- Retained gate: Python 377 passed/1 external archive skipped, Swift 42/42, static checks/build/
  signature verification passed.

## Phase 2 — independent atlas-slice viewer

Completed behavior:

1. The mode bar is exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, with one full-size
   selected view rather than a 2×2 grid.
2. Coronal, sagittal, and horizontal each persist an independent zero-based depth. Changing one
   never changes either of the others.
3. Slider, previous/next buttons, wheel stepping, drag pan, anchored zoom, and reset are wired to
   the same full-resolution lossless 25 µm slice state.
4. A click replaces one region selection and compact acronym/name label. It never changes a
   depth or opens additional interaction state.
5. Strict methods are `viewer.state.get`, `viewer.slice.set`, `viewer.slice.render`, and
   `viewer.region.pick`; stale revisions, stale slice clicks, malformed pixels, and render
   failures are fail-closed and atomic.
6. Project persistence restores all three depths and the optional selection. Older schema-3
   projects migrate deterministically.
7. Rapid input is debounced/latest-wins while the last verified frame remains visible.

Verified evidence at completion: Python `389 passed, 1 skipped`; Swift `62` tests; cached Allen
25 µm fused-render medians of 3.10 ms coronal, 4.92 ms sagittal, and 4.94 ms horizontal. Native UI
automation exercised independent depth changes, tab switching, and replacement region clicks.

## Phase 3 — calibration and AP/ML/DV projection

- Expose anatomical transform fit/apply/invert/compose and skull-landmark calibration through
  typed bridge services.
- Store bregma, lambda, left/right landmarks, laterality, DV reference, transform, residuals,
  uncertainty, QC, source, version, and input hash.
- Require an active calibration with non-failing QC before target projection or probe creation.
- Preserve legacy unprojected values exactly; never synthesize a reference profile without an
  auditable source.

## Phase 4 — probe catalog and placement

- Add versioned generic/test models and only call a manufacturer profile verified when its full
  source geometry and independent review are present.
- Support `ENTRY_AND_TARGET`, `ENTRY_ANGLES_DEPTH`, `TARGET_ANGLES_DEPTH`, and
  `STEREOTAXIC_TARGET_MANIPULATOR`.
- Distinguish trajectory centerline, shank envelope, and recording sites; support per-shank
  offsets and conservative capsule metadata.
- Display target, entry, tip, shanks, and sites in all three planes.

## Phase 5 — region traversal

- Implement clipped 3D Amanatides–Woo voxel traversal in centralized coordinate order.
- Run-length encode contiguous annotation intervals without dropping ID 0/outside/ventricle/
  tract segments.
- Assign every recording site with a documented boundary tie-break.
- Add inspector navigation and provenance-rich CSV/JSON export.

## Phase 6 — evidence-layer semantics

- Population density and subject-image registration remain archived backend groundwork and are
  removed from the primary planning UI.
- The product path exposes major-vessel geometry only after exact registration, path, radius,
  provenance, and review gates pass; until then it reports the layer as unavailable.

## Phase 7 — vessel graph and clearance

- Import only explicit registered 3D nodes/edges/polyline/radius data with source, license,
  subject/reference kind, frame, units, digest, transform, residual, uncertainty, and review.
- Use a reproducible AABB/BVH or benchmarked candidate index, then exact finite-segment closest
  points.
- Report centerline distance, interpolated vessel radius, probe envelope, geometric clearance,
  required margin, registration uncertainty, adjusted clearance, closest points, depth, source,
  and shank.
- Emit `NO_CONFLICT_DETECTED` only within loaded geometry/assumptions; never emit “safe.”

## Phase 8 — optional 3D

Only after Phases 2–7 pass, choose a supported SwiftUI embedding approach in a new ADR. The
renderer consumes the same cursor, placements, region results, vessel graph, and conflicts. It
does not own coordinate conversion or collision code.

## Cross-cutting requirements

- Protocol v2: strict typed payloads, stable errors, expected revisions, cancellation/latest-wins,
  stale-input hashes, and no giant volumes on the wire.
- Schema migrations: deterministic, fixture-covered, backup-preserving, and fail closed on
  digest/version/source mismatch.
- Provenance: atlas, calibration, model, vessel source, registration, algorithms, inputs, and
  acknowledgments remain inspectable.
- Validation language: animal research planning only; never clinical/navigation-ready/safe.
- Final completion is the 22-item requirement audit in the governing end-to-end specification,
  not merely a green unit-test count.
