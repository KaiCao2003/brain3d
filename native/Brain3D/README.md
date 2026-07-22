# Brain3D native macOS app

This Swift package is the native half of the Brain3D animal-research planner. SwiftUI owns the
single-view workspace and controls; SceneKit renders backend-validated 3D brain and probe geometry
payloads; a typed NDJSON subprocess boundary delegates scientific state and analysis to Python.

> **Animal research only — non-human and non-clinical.** This development app is not an
> installable production release or a qualified navigation device.

## Current workspace

- Exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, one selected mode at a time.
- Independent retained slice depths, with slider/buttons/wheel, pan, zoom, and compact
  click-to-replace region labels. A region click never changes depth.
- No focus mode, crosshair, 2×2 layout, or capillary display.
- QC-gated subject calibration and AP/ML/DV target projection from bregma; negative values mean
  posterior, left, and deep/ventral.
- Probe placement, 2D/3D overlays, region traversal, inspection, and CSV/JSON export.
- No vessel layer in slices, Dorsal, or 3D. The packaged P60_606 derivative is archived evidence
  whose hemisphere/laterality and whole-brain qualification is rejected; it is not mirrored.
- No vessel-analysis capability. Reference metadata, geometry, and analysis requests fail with
  `VESSEL_GEOMETRY_UNAVAILABLE` without serving points.

The NP1 NP1000 / `PRB_1_4_0480_1` catalog model is a complete source transcription whose
independent review is still pending; the UI requires acknowledgement. The archived vessel source
is a hemisphere specimen and its exact graph lacks a persisted biological laterality binding;
AP/DV evidence alone cannot qualify it for display or analysis. The canonical rejection report
is [retained with repository evidence](../../docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.
Population density and subject-image registration remain archived in Python and absent from the
primary UI. Only `allen_mouse_25um` v1.2 is accepted in this 25 µm testing phase.

## Development

```sh
swift test --package-path native/Brain3D
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

Backend discovery is deterministic and fail-closed:

1. `BRAIN3D_BRIDGE_EXECUTABLE` plus optional JSON-array `BRAIN3D_BRIDGE_ARGUMENTS` and
   `BRAIN3D_BRIDGE_WORKING_DIRECTORY` override discovery.
2. Development builds walk upward from the current directory, executable, and source package for
   both `.venv/bin/python` and `src/mouse_brain_planner/bridge/server.py`.
3. If neither route resolves, the UI reports **Backend not configured** and does not substitute
   demo anatomy or geometry.

The development app launches Python with `-u -m mouse_brain_planner.bridge.server` and sets
`PYTHONPATH` to the repository `src` directory. UI requests are asynchronous and strict decoders
reject source, schema, revision, hash, coordinate-frame, and size mismatches.

## Distribution boundary

`Scripts/build-app.sh` creates an ad-hoc-signed development `.app` that depends on the source
checkout. A production distribution still requires a deterministic bundled Python runtime,
hardened-runtime review, Developer ID signing of nested executables, notarization, an SBOM, and
clean-Mac qualification.
