# Brain3D native macOS app

This Swift package is the native half of the Brain3D animal-research planner. SwiftUI owns the
single-view workspace and controls; SceneKit renders verified 3D brain, probe, and reference-vessel
geometry; a typed NDJSON subprocess boundary delegates scientific state and analysis to Python.

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
- LAMBADA P60_606 reference vessels at diameter ≥30 µm on slices, Dorsal, and 3D.
- V2 tapered-vessel reference analysis with explicit margin, uncertainty, and two
  acknowledgements. Its bounded zero-conflict wording is:

  > No conflict detected within the loaded geometry and stated uncertainty assumptions.

The NP1 NP1000 / `PRB_1_4_0480_1` catalog model is a complete source transcription whose
independent review is still pending; the UI requires acknowledgement. The vessel graph is one
fixed cleared P60 reference, omits pial/choroidal/smaller vessels, and is not subject-specific.
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
