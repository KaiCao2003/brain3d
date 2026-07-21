# Known Limitations

This is an early Phase 1 scientific viewer, not the complete surgery-planning system described in
the product requirements. The limitations below are part of the scientific contract, not a list
of optional polish items.

## Safety and intended use

- Research planning and visualization only.
- Not a certified surgical navigation, medical, or veterinary device.
- No claim of clinical accuracy, stereotaxic accuracy, subject-specific accuracy, safety, or
  successful targeting.
- All coordinates, laterality, atlas identity, transforms, hardware geometry, and manipulator
  settings require independent verification before surgery.
- No displayed absence of a collision, vessel, or structure can be interpreted as “safe.”

## Atlas and anatomy

- The Allen CCF is a population-average reference made from ex-cranio fixed brains. It does not
  represent an individual mouse's skull, brain deformation, bregma–lambda geometry, or surface
  vasculature.
- There is no official Allen CCF bregma or lambda. Phase 1 is deliberately uncalibrated and must
  not show atlas center, midline, renderer origin, or an IBL estimate as official bregma.
- Stable BrainGlobe Allen packaging reviewed here requests `annotation/ccf_2017` even though its
  framework citation is Wang et al. 2020. The separate Allen-CCF-2020 parcellation is not loaded.
- Only BrainGlobe ASR packages are supported through the adapter. General NRRD/NIfTI/Allen file
  import and orientation reconciliation are not implemented.
- Region labels are voxel/resolution dependent. Boundary labels may differ between 10 and 25 µm
  and are not subject-specific histology.
- No atlas or annotation upgrade/migration workflow is implemented.

## Memory and performance

- AtlasAPI 2.3.1 loads complete TIFF reference and annotation volumes rather than chunked arrays.
- The raw 10 µm pair is 7,223,040,000 bytes (7.223 GB / 6.73 GiB); real peak memory is higher.
- The raw 25 µm pair is 462,274,560 bytes (0.462 GB / 0.43 GiB); VTK meshes and display data add
  to it.
- 25 µm is recommended on a 16 GB Mac, but choosing it reduces sampling resolution. The app
  cannot silently switch resolutions.
- Interactive performance has not been benchmarked across supported Mac models, large region
  groups, prolonged sessions, or memory-pressure conditions.
- Multiresolution mesh generation, persistent processed-mesh caching, and a cache-management UI
  are not implemented.

## Integrity and data distribution

- Atlas data is downloaded separately and governed by its source terms; it is not bundled.
- Stable BrainGlobe does not provide an enforced authoritative expected archive hash for these
  packages. Phase 1 records a SHA-256 of installed `metadata.json`, not an authenticated
  whole-package manifest.
- `.mouseplan` checksums detect changed project JSON, but do not establish scientific truth,
  source authenticity, or malicious-tamper resistance.
- A project references a cached atlas and does not embed it. Reopening fails when the exact package
  is unavailable and downloads are forbidden.
- There is no GUI cache removal/relocation workflow.

## Phase 1 viewer scope

Implemented Phase 1 scope is the application shell, explicit atlas adapter/acquisition workers,
whole-brain and selected-region rendering, region hierarchy/search/visibility, orthogonal slice
rendering, a linked atlas cursor, atlas-coordinate/status display, and versioned project
save/load.

The broader requested viewer still lacks or has not release-qualified several advanced controls,
including clipping planes, arbitrary oblique slices, measurement rulers, scale bars, stereotaxic
grids, high-resolution/SVG export, deterministic visual-regression baselines, and comprehensive
Retina/dark-mode/accessibility testing.

The 3D/slice implementation has not yet demonstrated every camera, pick, label, and mesh against
a frozen asymmetric real-Allen reference fixture. Screen appearance must not be used to infer
left/right correctness.

The real Allen 25 µm package has been opened through the normal macOS Cocoa application path,
including two embedded 3D views, six linked slices, the 840-record hierarchy, and a lazily loaded
CA1 mesh. That is a bounded integration check, not an anatomical landmark validation. Forcing
`QT_QPA_PLATFORM=offscreen` while constructing an embedded VTK Cocoa render window causes an
upstream native crash in `vtkCocoaRenderWindow::SetWindowInfo` with the pinned stack. Automated
headless tests therefore mock only the embedded Qt render-window creation; a standalone PyVista
offscreen render of the real root mesh and the normal Cocoa embedded path are tested separately.

## Phase 2 is not implemented

Low-level typed atlas voxel/physical and renderer-world transforms exist to support Phase 1, but
the Phase 2 stereotaxic system does not. There is no:

- user-entered bregma, lambda, or skull landmark set;
- skull pitch, roll, yaw, or bregma–lambda leveling;
- selectable DV zero (skull, brain surface, atlas boundary, or user plane);
- atlas-to-stereotaxic or stereotaxic-to-atlas calibration profile;
- rigid/similarity/affine subject transform or transform inspector;
- landmark residual, uncertainty propagation, or registration validation;
- user-facing stereotaxic coordinate beyond the explicit “not calibrated” state.

## Phase 3 is not implemented

No probe/implant model is enabled. In particular, there is no verified Neuropixels 1.0/2.0
geometry, target/entry editor, trajectory convention, site bank, shank rendering, region
intersection, recording-site mapping, multiple implant support, collision/proximity calculation,
coordinate table, or custom implant editor. See [Probe Models](PROBE_MODELS.md).

## Phase 4 is not implemented

A CC BY 4.0 Mendeley deposit from Wu et al. has been identified as a license-level Phase 4
candidate, but its file schema, file-level integrity, coordinate registration, and scientific fit
have not been validated for this application. There is no ingested reference vascular dataset,
subject-specific vessel image import, segmentation, landmark registration, registration residual,
skull/surface model, craniotomy, probe-to-vessel calculation, or subject-space overlay. No panel
currently depicts the animal's actual vasculature.

## Phase 5 is not implemented

There is no PDF surgical plan, coordinate CSV/TSV/JSON export, geometry export, screenshot report,
final-plan confirmation workflow, signed `.app`, DMG/installer, notarization, stapling, or clean-Mac
release qualification. Source launch with uv is the current supported path. See
[Packaging](PACKAGING.md).

## Persistence scope

The Phase 1 project package stores project identity/history, atlas metadata, linked cursor,
selected region, and region display state. It does not yet contain transforms, landmarks,
implants, craniotomies, images, meshes, measurements, exports, or autosave history. Atomic save
and one `.mouseplan.bak` recovery package are implemented; continuous autosave and a recovery UI
are not.

Undo/redo menu actions and an empty Qt undo stack exist, but no Phase 1 scientific edit is yet
represented by an undo command. A general command model for later scientific edits is not
implemented.

## Validation boundary

The automated suite covers typed coordinate bounds/round trips, ASR/world mapping, midline
semantics, slice extraction/pixel mapping, synthetic mesh reflection, adapter contracts with
fakes, project integrity/recovery, GUI widgets, and a headless first-frame smoke process.

Most tests deliberately use synthetic arrays, meshes, and BrainGlobe test doubles. They do not by
themselves validate real Allen anatomy, the download archive, visual laterality, an individual
animal, bregma calibration, hardware, histological outcome, or surgical targeting. Consult
[Scientific Validation](SCIENTIFIC_VALIDATION.md) for the dated evidence matrix and exact
tolerances.

A separate, non-default real-data validation run downloaded and checked only
`allen_mouse_25um`; it is not an ordinary offline unit test and does not cover the 10 µm package.

## Platform and packaging

- Supported target: macOS 13+ on Apple Silicon (`arm64`) with Python 3.12.
- Intel macOS, universal2, Windows, Linux, Python 3.11/3.13+, remote display, and virtual-machine
  support are unqualified.
- Signing/notarization and Finder launch on a clean user account have not been validated.
- Qt/PySide6 licensing and every bundled transitive license require release review.

## Reporting problems

Any issue involving coordinates should include application version, atlas key/package version,
resolution, orientation, source annotation, exact named frame/unit, input point, expected result,
actual result, and whether the value is a continuous coordinate, voxel index, index anchor, or
voxel center. Do not attach proprietary subject data or large cached atlas packages.
