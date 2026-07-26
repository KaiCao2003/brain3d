# Brain3D native macOS app

The Swift package provides the Brain3D interface. SwiftUI owns the workspace and controls,
SceneKit renders 3D atlas and planning geometry, and the Python service provides atlas,
coordinate, persistence, and planning operations over typed NDJSON.

## Workspace

- Dorsal, coronal, sagittal, horizontal, and 3D modes.
- Independent slice depths with pan, zoom, wheel, and region picking.
- Shared Allen ontology selection across 2D and 3D.
- Direct AP/ML surface planning for NP2003 and NP2013.
- Optional external VesSAP overlay when its data package is installed.
- Surgery-plan PDF export using documents selected in Settings.

## Development

```bash
swift test --package-path native/Brain3D --no-parallel
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

Backend discovery checks explicit `BRAIN3D_BRIDGE_*` settings, a bridge bundled inside a
standalone application, and the repository Python environment for development builds.

## Standalone build

```bash
native/Brain3D/Scripts/build-release-app.sh
```

The release script builds the Swift executable and frozen Python bridge, assembles the application
and zip archive, verifies architecture and signatures, and runs an isolated launch smoke test.

Atlas packages, vascular data, PDF inputs, and user projects remain outside the application
bundle. See [Packaging](../../PACKAGING.md) and
[Surgery-plan export](../../docs/SURGERY_PLAN_EXPORT.md).
