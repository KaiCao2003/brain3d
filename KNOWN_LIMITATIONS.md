# Known Limitations

Brain3D is an engineering testing build for non-human mouse research. It is not a medical,
clinical, veterinary, or qualified surgical-navigation product, and it has no prospective animal,
phantom-targeting, histological-outcome, or formal usability validation.

## Atlas and coordinates

- Only BrainGlobe `allen_mouse_25um` package `1.2` is accepted. The 25 µm value is sampling
  resolution, not targeting accuracy. The 10 µm atlas is outside the testing phase.
- The Allen CCF is a population reference from fixed brains and does not provide one official,
  subject-specific bregma/lambda transform.
- AP/ML/DV projection depends on user-entered matched landmarks, frame definitions, laterality,
  QC thresholds, and uncertainty. Passing software QC does not establish biological truth.
- Region labels are annotation-voxel results, not subject histology. Boundary, hemisphere, and
  registration errors remain possible.

## Native views

- Dorsal is a depth-collapsed reference projection. It cannot recover vessel depth and must not
  be interpreted as the animal's cortical surface.
- SceneKit 3D is a display and picking view of backend-verified geometry. Camera interaction and
  rendering do not add anatomical accuracy.
- Probe and vessel overlays are clipped/projected according to their documented slab rules. A
  line absent from the current slice may exist elsewhere in depth.
- There is no capillary layer, artery/vein classification, craniotomy design, manipulator/hardware
  collision model, or intraoperative tracking.

## Probe model and placement

- Neuropixels 1.0 NP1000 / `PRB_1_4_0480_1` is a complete source transcription but remains
  `source-transcribed-review-pending`. No independent human has reviewed all 960 coordinates and
  dimensions against the pinned sources or a physical probe.
- Manufacturer tolerances, insertion bending, tissue deformation, brain shift, skull mounting,
  probe-base/headstage geometry, and manipulator backlash are not modeled.
- The generic 16-site model is synthetic software-test geometry, not a physical device profile.
- Region traversal and site assignment use the selected Allen annotation and current calibration;
  they do not predict histological recording location or post-insertion displacement.

## LAMBADA major-vessel reference

- The graph is one fixed, cleared P60_606 atlas-registered reference, not live or subject-specific
  vasculature.
- The source workflow removed pial and choroidal vessels. The bundled derivative also removes
  points below 15 µm radius (30 µm diameter), so missing vessels are expected.
- Exact sex and sampled side are unpublished; artery/vein identity is unavailable.
- The source corrected/reconnected endpoints and removed short terminal offshoots. Some paths are
  reconstructed rather than directly observed.
- Radius conversion uses the source's mean atlas-resampling scale rather than a local Jacobian.
  Fixed/cleared tissue distortion, atlas registration error, biological variation, and omitted
  vessels are not bounded.
- Out-of-bounds or rejected points split runs and are omitted without clipping/interpolation.
- Dorsal collapses every retained depth; it does not mean each line lies on the surface.

See [the full extraction record](docs/LAMBADA_MAJOR_VESSELS.md).

## V2 reference analysis

The algorithm computes the minimum separation between a conservative probe envelope and tapered
surfaces in the loaded reference graph, then subtracts a user-declared required margin and
registration uncertainty. It can classify loaded-geometry intersections and threshold violations,
but it cannot evaluate omitted, deformed, or subject-specific vessels.

Required margin and uncertainty are lab inputs, not values supplied or validated by the software.
The acknowledgements confirm that the operator saw those assumptions; they do not validate them.
The only bounded zero-conflict statement is:

> No conflict detected within the loaded geometry and stated uncertainty assumptions.

## Archived and distribution paths

- Population vascular density and subject-image registration remain archived in the backend.
  They are absent from the primary UI and are not used as vessel paths or clearance geometry.
- `build-app.sh` creates an ad-hoc-signed development bundle that depends on the source checkout.
  A deterministic bundled runtime, SBOM, Developer ID signing, notarization, and clean-Mac release
  qualification are not complete.
- Automated tests establish software invariants only. They do not establish biological,
  stereotaxic, vascular, hardware, or procedural accuracy.
