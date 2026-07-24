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
  but intentionally omits the collapsed recording-site cloud. It shows the VesSAP display-only
  major-vessel projection; missing lines must not be interpreted as absence of vessels.
- SceneKit 3D is a display and picking view of backend-validated geometry payloads. Camera
  interaction and rendering do not add anatomical accuracy.
- Probe and vessel overlays are clipped/projected according to documented slice/slab rules.
- There is no capillary layer, artery/vein classification, craniotomy design, manipulator/hardware
  collision model, or intraoperative tracking.

## Probe model and placement

- The two supported choices—Neuropixels 2.0 single-shank (1,280 sites) and standard four-shank
  (5,120 sites)—are complete source transcriptions but remain
  `source-transcribed-review-pending`. No independent human has reviewed every coordinate and
  dimension against the pinned sources or physical probes.
- The NP2 four-shank target/entry belongs to the official leftmost `shank-0`; the other shanks
  follow the probe-local lateral axis at 250 µm pitch. The software does not infer a centered-array
  target or independently rotate the shanks.
- NP2 plans expose all 1,280 physical sites per shank for geometry and region inspection. They do
  not import the actual IMRO/electrode selection, and must not imply that all sites are recorded
  simultaneously. Both supported hardware choices provide 384 simultaneously configurable
  recording channels.
- Manufacturer tolerances, insertion bending, tissue deformation, brain shift, skull mounting,
  probe-base/headstage geometry, and manipulator backlash are not modeled.
- The generic 16-site model is synthetic software-test geometry, not a physical device profile.
- Region traversal and site assignment use the selected Allen annotation and current calibration;
  they do not predict histological recording location or post-insertion displacement.

## VesSAP display-reference limits

- The visible layer is one fixed, cleared, ex-vivo adult C57BL/6J specimen (`BL6J-no1`), not the
  current animal and not live vasculature.
- Only source skeleton points with nominal radius ≥15 µm (diameter ≥30 µm) are retained.
  Capillaries and smaller vessels are intentionally absent.
- Source topology is coalesced on a 50 µm display grid. Nearby branches can merge and isolated
  display voxels without a retained segment are omitted.
- Pial/choroidal coverage is not separately classified. Artery/vein identity is unavailable.
- The published Euler + B-spline atlas transform was checked for axis order, laterality, bounds,
  and label agreement, but no target-registration-error, bregma/skull-registration-error, clearing
  distortion, or inter-animal variation bound is published.
- The nonlinear transform is anisotropic. The displayed scalar tube radius is a visual reference,
  not a qualified atlas-space vessel surface.
- The layer cannot establish clearance, absence of a vessel, trajectory suitability, or safety
  for an individual animal. It remains CC BY-NC 4.0.

See [the exact derivation and validation record](docs/VESSAP_MAJOR_VESSELS.md).

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

The runtime advertises `auditedReferenceMajorVessels` for VesSAP metadata and display geometry,
but not `radiusAwareReferenceVesselAnalysis`. Analysis fails with
`VESSEL_ANALYSIS_UNAVAILABLE` before reading points or touching a project. Legacy V3 algorithm
code and synthetic tests do not authorize product use. This build emits no vessel intersection,
threshold violation, absence, clearance, suitability, or safety result.

The older LAMBADA path remains independently rejected. Its digest-bound report is
[`docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json`](docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.

## Archived and distribution paths

- Surgery-plan export depends on the user-prepared Headplate protocol PDF and the user-supplied
  132-page `MBSC_Figs_with_Layers.pdf`. Those files and their rights are not bundled or
  relicensed. Their locations are configured once in **Brain3D → Settings** and reused until
  replaced. A disconnected volume must be reconnected or selected again. Export reads both PDFs
  directly and does not require Word, Illustrator, or macOS Automation permission.
- Plate matching chooses the nearest reviewed coronal AP or sagittal `|ML|` coordinate. Coronal
  AP follows the historical atlas convention `Bregma = Interaural − 3.80 mm`. The appended
  historical plate is a coordinate reference, not a subject registration. Its output copy gets
  an identity/plan summary, but no claimed trajectory transform is drawn on the artwork.
- A FINAL surgery-plan label records exact saved-project, active-calibration, projection, and
  current-probe provenance gates. It does not establish biological, vascular, procedural, or
  surgical validity.
- Population vascular density and subject-image registration remain archived as compatibility
  code and persisted data. Their methods/capabilities are not registered by the primary bridge;
  they are absent from the UI and are not used as vessel paths or clearance geometry.
- `build-app.sh` creates an ad-hoc-signed development bundle that depends on the source checkout.
  A deterministic bundled runtime, SBOM, Developer ID signing, notarization, and clean-Mac release
  qualification are not complete.
- Automated tests establish software invariants only. They do not establish biological,
  stereotaxic, vascular, hardware, or procedural accuracy.
