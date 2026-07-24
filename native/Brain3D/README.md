# Brain3D native macOS app

This Swift package is the native half of the Brain3D animal-research planner. SwiftUI owns the
single-view workspace and controls; SceneKit renders backend-validated 3D brain and probe geometry
plus display-only major-vessel payloads; a typed NDJSON subprocess boundary delegates scientific
state and analysis to Python.

> **Animal research only — non-human and non-clinical.** This development app is not an
> installable production release or a qualified navigation device.

## Current workspace

- Exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, one selected mode at a time.
- Independent retained slice depths, with slider/buttons/wheel, pan, zoom, and compact
  click-to-replace region labels. A region click never changes depth.
- Complete paged Allen ontology browsing/search with one selection shared across all five modes;
  only the selected structure mesh is loaded for 3D highlighting.
- No focus mode, crosshair, 2×2 layout, or capillary display.
- QC-gated subject calibration and AP/ML/DV target projection from bregma; negative values mean
  posterior, left, and deep/ventral.
- NPX2 1-shank/4-shank placement from one selected implant site, with
  azimuth/elevation/depth/roll inputs and 2D/3D overlays.
- VesSAP `BL6J-no1` nominal diameter-≥30 µm paths overlaid in all five views. The layer is one
  cleared C57BL/6J reference, reduced at 50 µm for display, not subject-specific.
- No vessel-analysis capability. Geometry is display-only and analysis fails with
  `VESSEL_ANALYSIS_UNAVAILABLE`.

The production catalog contains exactly NP2 single shank (`NP2003`/`NP2004`) and standard
four shank (`NP2013`/`NP2014`). Both source transcriptions remain independent-review pending and
require acknowledgement. Quad Base, NP1, and the synthetic fixture remain archived definitions,
not new-plan choices.

## Surgery-plan PDF export

The native app can export a prefilled animal-research planning packet for one selected target.
Choose `Dorsal`, `Coronal`, `Sagittal`, `Horizontal`, `3D`, or `All`; `All` emits the five
planning views in that order. AP/ML/DV are millimetres relative to bregma, insertion depth is
also in millimetres, and probe angles are degrees. Coronal historical plates use
`Bregma = Interaural − 3.80 mm`; sagittal matching uses `|ML|` while preserving the target's
left/right sign.

The fixed packet order is:

1. two portrait-Letter pages rendered from the user-supplied Headplate protocol;
2. one selected planning page, or five pages for `All`; and
3. one matched landscape-Letter historical atlas page.

The app reads the prepared three-page protocol PDF directly, prefills pages 1–2, and replaces its
page-3 sketch placeholder with the matched page from the consolidated 132-page
`MBSC_Figs_with_Layers.pdf`. Configure both PDF locations once in **Brain3D → Settings**; later
exports reuse those locations until they are replaced there. PDFKit/Core Graphics read the
sources directly, merge the packet, and flatten an audit stamp onto every page. The original
source files are never rewritten. Word, Illustrator, and Apple Events automation are not used.

Export freezes and repeatedly revalidates the target, projection, calibration, matching probe,
atlas, vessel asset, project revision, and saved/dirty state. The contract binds target
coordinates; probe input/projection hashes; calibration and atlas hashes; and the VesSAP asset
hash. A state change during rendering or assembly aborts the export instead of mixing revisions.

The vessel overlay is the one-specimen VesSAP `BL6J-no1` ex-vivo reference, nominal diameter
at least 30 µm. It is not the operative animal, capillaries are omitted, and neither a displayed
path nor zero visible intersections establishes subject-specific location, vessel absence,
clearance, trajectory suitability, or safety. The packet is for non-human animal research only,
not clinical use or qualified navigation.

The protocol and Mouse Brain atlas sources are supplied by the user and are not redistributed
with Brain3D. See the full [surgery-plan export contract](../../docs/SURGERY_PLAN_EXPORT.md),
including prerequisites, atlas matching, immutable provenance, and source-rights boundaries.

The older P60_606 vessel source remains archived because its hemisphere/laterality and whole-brain
coverage are unqualified; it is not mirrored or mixed into VesSAP. The visible VesSAP layer also
cannot establish subject-specific clearance, absence, suitability, or safety; see
[its evidence record](../../docs/VESSAP_MAJOR_VESSELS.md).
Population density and subject-image registration remain archived in Python and absent from the
primary UI. Only `allen_mouse_25um` v1.2 is accepted in this 25 µm testing phase.

## Development

```sh
swift test --package-path native/Brain3D --no-parallel
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
