# Brain3D native macOS shell

> **Early alpha:** the current shell shows only fixed midpoint orthogonal slices. It has no
> movable x/y/z cursor, linked tri-planar navigation, pan/zoom, supported 3D renderer, individual
> vessel paths, target projection, or vessel-clearance workflow.

This package is the SwiftUI half of the hybrid animal-surgery planner. It keeps the
Python scientific implementation behind a typed, versioned NDJSON subprocess boundary.

The application is restricted to **animal research only — not for human or clinical
use**. It accepts only `allen_mouse_25um` version `1.2` in the current testing phase.
The Dorsal view can composite the pinned Mendeley Data v1 four-mouse population
vascular length density and a separately registered user-supplied subject image. The
population layer is not vessel paths or subject-specific anatomy and cannot establish
clearance. Bregma-relative AP/ML/DV entries remain unprojected until calibration, and
3D rendering is unavailable in bridge protocol v1.

## Development

```sh
swift test --package-path native/Brain3D
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

Backend discovery is deterministic and fail-closed:

1. `BRAIN3D_BRIDGE_EXECUTABLE` plus optional JSON-array
   `BRAIN3D_BRIDGE_ARGUMENTS` and `BRAIN3D_BRIDGE_WORKING_DIRECTORY` override discovery.
2. Development builds walk upward from the current directory, executable, and source
   package looking for both `.venv/bin/python` and
   `src/mouse_brain_planner/bridge/server.py`.
3. If neither route resolves, the UI says **Backend not configured** and does not claim
   that an atlas, project, or vessel image is usable.

The development app launches Python with `-u -m mouse_brain_planner.bridge.server` and
sets `PYTHONPATH` to the repository `src` directory. The serialized protocol channel has
a named 15-minute long-operation budget so a pinned ~311 MB density download, hash
verification, extraction, and 50 µm preparation can complete without poisoning the
connection. UI operations remain asynchronous to the main thread.

## Distribution boundary

`Scripts/build-app.sh` creates an ad-hoc-signed development `.app`. A release build still
needs a bundled deterministic Python runtime/backend, hardened-runtime entitlements,
Developer ID signing of every nested executable, and notarization. Those distribution
steps are intentionally not represented as complete by this development bundle.
