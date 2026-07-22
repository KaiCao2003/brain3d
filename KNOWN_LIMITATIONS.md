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

- Dorsal is an AP/ML atlas reference projection. It shows selected-probe landmarks and shank paths
  but intentionally omits the collapsed 960-site cloud. No vessel layer is available, and the
  absence of lines must not be interpreted as absence of vessels.
- SceneKit 3D is a display and picking view of backend-validated geometry payloads. Camera
  interaction and rendering do not add anatomical accuracy.
- Probe overlays are clipped/projected according to their documented slab rules. Vessel overlays
  are unavailable because P60_606 coordinate/coverage qualification is rejected.
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

## Archived LAMBADA major-vessel evidence

- The derivative is archived evidence only. It is not loaded, served, displayed, mirrored, or
  analyzed by the current runtime.
- AP and DV orientation evidence passed, but the primary source describes hemisphere specimens
  and the exact graph has no persisted biological hemisphere/laterality binding. Whole-brain
  coverage and ML polarity are unqualified.
- The source workflow removed pial and choroidal vessels. The bundled derivative also removes
  points below 15 µm radius (30 µm diameter), so missing vessels are expected.
- The sampled biological side is not bound in the graph; artery/vein identity is unavailable.
- The source corrected/reconnected endpoints and removed short terminal offshoots. Some paths are
  reconstructed rather than directly observed.
- Radius conversion uses the source's mean atlas-resampling scale rather than a local Jacobian.
  Fixed/cleared tissue distortion, atlas registration error, biological variation, and omitted
  vessels are not bounded.
- Out-of-bounds or rejected points split runs and are omitted without clipping/interpolation.
- No source-backed mirror transform is qualified, so mirroring is prohibited.

See [the full extraction record](docs/LAMBADA_MAJOR_VESSELS.md).

## Vessel analysis unavailable

The runtime does not advertise `auditedReferenceMajorVessels` or
`radiusAwareReferenceVesselAnalysis`. All reference metadata, geometry, and analysis methods fail
with `VESSEL_GEOMETRY_UNAVAILABLE` before loading points or touching a project. Legacy V3
algorithm code and synthetic tests do not authorize product use. This build emits no vessel
intersection, threshold violation, absence, or clearance result.

The digest-bound rejection report is
[`docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json`](docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.

## Archived and distribution paths

- Population vascular density and subject-image registration remain archived as compatibility
  code and persisted data. Their methods/capabilities are not registered by the primary bridge;
  they are absent from the UI and are not used as vessel paths or clearance geometry.
- `build-app.sh` creates an ad-hoc-signed development bundle that depends on the source checkout.
  A deterministic bundled runtime, SBOM, Developer ID signing, notarization, and clean-Mac release
  qualification are not complete.
- Automated tests establish software invariants only. They do not establish biological,
  stereotaxic, vascular, hardware, or procedural accuracy.
