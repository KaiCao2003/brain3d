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
- landmark editing controls that send declared pixel and atlas coordinates.

Python owns:

- BrainGlobe atlas acquisition, validation, metadata, hierarchy, arrays, and mesh provenance;
- coordinate systems and transforms;
- subject dorsal-image byte preservation, landmark fitting, residuals, and atlas-grid resampling;
- population reference-density validation and its non-subject-specific limitation;
- project models, migrations, checksums, atomic save, backup recovery, exports, and future probe
  calculations.

Swift must not duplicate or reinterpret atlas axes, fit scientific transforms, infer laterality,
or calculate vessel clearance. A UI cannot display a subject image as registered until Python
returns a registration, residuals, and explicit laterality confirmation. Population vascular
density can never be presented as individual vessel paths or used for subject clearance.

The current protocol-v1 feature boundary is:

- exactly `allen_mouse_25um` v1.2; 10 µm is not offered during testing;
- dorsal, coronal, sagittal, and horizontal verified raster views;
- no native 3D renderer, represented by an explicit unavailable state;
- an optional transparent dorsal DV-maximum overlay from the pinned Mendeley Data v1
  `10.17632/stxvn5sv44.1` four-mouse population vascular length-density field;
- a separate user-supplied subject dorsal image with byte provenance, landmarks, laterality,
  residuals, and registration, but no automatic or implied vessel segmentation; and
- exact storage of `BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED` implant targets with AP−
  posterior/back, ML− left, and DV− deep/ventral. Projection and navigation remain locked until
  explicit calibration.

The population layer and subject layer are composited over the dorsal brain as distinct evidence
sources. Neither one can establish a vessel-free path. The population field contains no
individual vessel paths; the subject image may contain arbitrary opaque pixels unless the user
supplies an independently reviewed transparent mask.

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
subject-anatomical, or vascular safety accuracy.

## Consequences

- Two toolchains and a versioned process boundary are now intentional release components.
- SwiftPM is sufficient for development tests but not distribution. The release requires a real
  `.app` bundle, deterministic backend discovery, bundled-runtime review, nested code signing,
  hardened-runtime validation, notarization, and a clean-account Finder launch.
- The Qt shell remains a diagnostic/reference implementation until removed in a later cleanup;
  it is not the qualified macOS surgery-planning entry point.
- Python and Swift tests both cover protocol result/error exclusivity, IDs, framing, timeouts,
  process termination, exact atlas identity, animal-only invariants, and honest vascular state.
- A change on either side of the bridge requires compatibility tests against protocol version 1
  or an explicit protocol-version migration.
