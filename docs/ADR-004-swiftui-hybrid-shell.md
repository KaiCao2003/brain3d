# ADR-004: SwiftUI shell with a Python scientific service

- **Status:** Accepted
- **Decision date:** 2026-07-21
- **Applies to:** the supported macOS application shell
- **Supersedes:** the PySide6 shell portion of ADR-001 only

## Context

The Python scientific core and the reviewed 25 µm Allen atlas path pass their automated and
real-data checks. The PySide6 macOS shell does not meet the stability requirement for an animal
surgery-planning workflow. Native accessibility traversal repeatedly crashed the application in
Qt's Cocoa platform plugin at
`-[QMacAccessibilityElement accessibilitySelectedChildren] + 204`. The fault persisted after
removing `QTabBar`, replacing published item models with append-only lifetimes, and eliminating
known widget selection interfaces. At the final debugger stop, the Cocoa object had already
degraded to `AXUnknown` and Qt returned a selected-child pointer whose storage had been reused.

The reproduced environment was macOS 26.5.2 on Apple Silicon with Python 3.12.13 and PySide6
6.10.3. The same Qt implementation is present in the other evaluated Qt branches. A failure
triggered by accessibility hierarchy inspection is not acceptable merely because atlas arrays,
VTK, and ordinary unit tests remain correct.

## Decision

Use a native SwiftUI process for macOS interaction and a separately launched Python 3.12 process
for all scientific and project operations.

The boundary is newline-delimited JSON protocol version 1:

```text
SwiftUI request  {"id":"…","method":"atlas.slice","params":{…}}
Python response  {"id":"…","result":{…}}
              or {"id":"…","error":{"code":"…","message":"…","details":{…}}}
```

Standard output is reserved for protocol frames; diagnostics use standard error. The backend
must reject duplicate JSON keys, non-finite numbers, oversized frames, unknown fields, mismatched
protocol versions, unsupported atlases, and requests that depend on unloaded or unverified state.
The initial atlas remains exactly `allen_mouse_25um` package version `1.2`; 10 µm is not offered
during release qualification.

SwiftUI owns:

- windows, menus, native file panels, keyboard focus, accessibility, and presentation;
- asynchronous bridge lifecycle and explicit disconnected/loading/error states;
- rendering bridge-produced atlas PNGs and verified mesh assets;
- SceneKit camera interaction, ray construction, and display of verified brain/probe/vessel
  geometry; and
- calibration, target, probe, and vessel controls that send declared typed inputs.

Python owns:

- BrainGlobe atlas acquisition, validation, metadata, hierarchy, arrays, and mesh provenance;
- coordinate systems and transforms;
- subject calibration, AP/ML/DV target projection, probe geometry, voxel traversal, and
  tapered-radius major-vessel analysis;
- subject dorsal-image byte preservation, landmark fitting, residuals, and atlas-grid resampling;
- population reference-density validation and its non-subject-specific limitation;
- project models, migrations, checksums, atomic save, backup recovery, and exports.

Swift must not duplicate or reinterpret atlas axes, fit scientific transforms, infer laterality,
or calculate vessel clearance. A UI cannot display a subject image as registered until Python
returns a registration, residuals, and explicit laterality confirmation. Population vascular
density can never be presented as individual vessel paths or used for subject clearance.

The implemented protocol-v1 feature boundary, expanded on 2026-07-22 without changing the
process decision, is:

- exactly `allen_mouse_25um` v1.2; 10 µm is not offered during testing;
- exactly one selected `Dorsal / Coronal / Sagittal / Horizontal / 3D` view, with independent
  slice depths and click-to-replace region labels;
- a SceneKit brain/probe/reference-vessel scene with camera control and atlas ray picking;
- signed bregma AP/ML/DV targets, versioned subject calibration, QC-gated projection, and probe
  planning/region export;
- a radius-bearing LAMBADA P60_606 reference filtered to diameter ≥30 µm, shown in 2D,
  Dorsal, and 3D; and
- V3 AABB-candidate/tapered-surface reference analysis with explicit margin, uncertainty, risk-input, and
  incomplete-coverage acknowledgements.

Population density and subject-image registration remain archived backend capabilities and are
not exposed in the primary planning UI.

The persistent application warning is:

> Animal research only — not for human or clinical use

Creating a project requires an explicit acknowledgement. Disconnects and unsupported operations
remain visible failures; the shell must never substitute demo anatomy or fake successful state.

## First native qualification gate

Before expanding the hybrid shell, a real user journey must pass repeatedly without a terminal:

1. launch the app and connect to the bundled or deterministically discovered backend;
2. open and verify cached Allen 25 µm v1.2;
3. display real coronal, sagittal, horizontal, and dorsal atlas pixels;
4. create an acknowledged animal-only project;
5. import an unchanged PNG, JPEG, or TIFF subject dorsal image;
6. place landmarks, fit similarity registration, confirm laterality, and see residuals;
7. display the registered subject image on the atlas dorsal grid;
8. save, quit, reopen, and reproduce the matrix and overlay without numeric drift.

All unavailable features must say why they are unavailable. This gate does not claim surgical,
subject-anatomical, or vascular/procedural accuracy.

## Consequences

- Two toolchains and a versioned process boundary are now intentional release components.
- SwiftPM is sufficient for development tests but not distribution. The release requires a real
  `.app` bundle, deterministic backend discovery, bundled-runtime review, nested code signing,
  hardened-runtime validation, notarization, and a clean-account Finder launch.
- The Qt shell was removed from the package and dependency graph during the audited Phase 1
  cleanup; Git commit `51fe26d` preserves it for historical investigation.
- Python and Swift tests both cover protocol result/error exclusivity, IDs, framing, timeouts,
  process termination, exact atlas identity, animal-only invariants, and honest vascular state.
- A change on either side of the bridge requires compatibility tests against protocol version 1
  or an explicit protocol-version migration.
