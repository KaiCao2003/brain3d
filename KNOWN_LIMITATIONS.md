# Known Limitations

The current SwiftUI/Python hybrid is an engineering testing build, not a qualified surgical-
navigation system. These limitations are part of its scientific contract.

## Safety and intended use

- Mouse animal-research planning and visualization only; never human or clinical use.
- Not a certified surgical-navigation, medical, or veterinary device.
- No claim of stereotaxic, subject-specific, vascular-clearance, targeting, or outcome accuracy.
- All coordinates, laterality, atlas identity, transforms, hardware geometry, and manipulator
  settings require independent verification before every animal procedure.
- No displayed absence of a collision, vessel, or structure can be interpreted as “safe.”

## Atlas and anatomy

- The only accepted atlas is BrainGlobe `allen_mouse_25um` package `1.2`. The 25 µm value is
  sampling resolution, not targeting accuracy.
- The 10 µm atlas is intentionally outside the current testing build. Existing 10 µm cache data
  is ignored and not automatically deleted.
- The Allen CCF is a population-average reference made from ex-cranio fixed brains. It does not
  represent an individual mouse's skull, brain deformation, bregma–lambda geometry, or surface
  vasculature.
- There is no official unique Allen CCF bregma or lambda. Atlas origin, atlas center, ML midline,
  renderer origin, and an external estimate must not be substituted for a measured calibration.
- The reviewed BrainGlobe package requests `annotation/ccf_2017`; it is not the separately
  distributed Allen-CCF-2020 parcellation.
- Region labels are voxel- and annotation-dependent and are not subject-specific histology.
- General NRRD/NIfTI/Allen atlas import, atlas upgrades, and annotation migration are not
  implemented.

## Views and interaction

- The supported native workspace provides dorsal, coronal, sagittal, and horizontal raster
  views. Bridge protocol v1 does not expose a 3D renderer; the 3D tab is intentionally
  unavailable.
- The former Qt/PySide6/PyVista viewer remains diagnostic/reference code, not the supported
  surgery-planning UI. Its historical 3D evidence does not make 3D available in SwiftUI.
- Arbitrary oblique slices, stereotaxic grids, scale bars, high-resolution vector export, and
  comprehensive visual-regression coverage are not implemented or release-qualified.
- Screen appearance alone must not be used to infer left/right correctness.

## Population vascular density

The optional published layer is pinned to Yongsoo Kim's Mendeley Data v1 deposit,
[DOI 10.17632/stxvn5sv44.1](https://data.mendeley.com/datasets/stxvn5sv44/1), associated with
[Wu et al., Cell Reports 2022](https://doi.org/10.1016/j.celrep.2022.110978).

Its limits are fundamental:

- It is a scalar vascular **length-density** field summarized from four fixed adult C57BL/6
  mice with a 100 µm local window.
- It is not subject-specific and contains no individual vessel centerlines, diameters, branch
  paths, or current-animal surface image.
- A DV maximum projection discards depth location; it cannot support probe-to-vessel distance,
  intersection, or clearance calculations.
- The source density NIfTI lacks trustworthy self-describing spatial metadata. The implementation
  accepts only the pinned archive/member identities, validates the exact documented 20 µm
  `[ML,DV,AP]` source contract, checks its template against the open atlas, and fails closed when
  those facts change.
- Source ML polarity is not documented. The prepared field is deliberately left/right
  symmetrized and labeled as such; it must not be used to infer lateral asymmetry.
- The prepared scalar grid is 50 µm. Compositing it over a 25 µm dorsal atlas does not create
  25 µm vascular information.
- The color window, density-scaled alpha, and clipping to the nonzero Allen annotation footprint
  are visualization choices, not uncertainty bounds, probabilities, or a subject-skull mask.

The pinned archive SHA-256 and member hashes provide reproducibility and reject changed bytes;
they do not establish that the biological measurements are complete or suitable for a specific
animal.

## User-supplied subject dorsal image

- Import preserves file provenance and registration maps source pixels to the atlas dorsal AP/ML
  plane. It does not automatically segment blood vessels.
- Opaque background pixels remain visible in the overlay. A transparent, independently reviewed
  mask is needed when only vessel pixels should cover the atlas.
- Landmark fit residuals describe consistency of the entered correspondences, not biological
  registration truth, tissue deformation, vessel identity, or depth.
- Laterality must be explicitly confirmed. That confirmation records user intent; it is not an
  independent anatomical validation.
- A two-dimensional dorsal image cannot provide a validated 3D vascular graph or establish
  clearance along a probe trajectory.

## Bregma-relative targets and surgery planning

- The application can preserve exact unprojected `[AP, ML, DV]` millimetre entries from bregma,
  with AP− posterior/back, ML− left, and DV− deep/ventral.
- No bregma/skull-to-atlas calibration profile is currently selected or validated. Therefore an
  unprojected target has no inferred Allen-atlas position and is explicitly unusable for
  navigation.
- There is no validated skull pitch/roll/yaw, bregma–lambda leveling, DV zero, brain-surface
  model, manipulator calibration, or uncertainty propagation.
- Probe hardware geometry, entry/target trajectory projection, recording-site mapping,
  craniotomy design, collision checking, and vessel-clearance calculations are not available as
  navigation features.
- Typed lower-level surgery domain models and tests are engineering groundwork only; their
  existence is not a scientific or UI qualification claim.

## Integrity, persistence, and data distribution

- Atlas and Mendeley data are downloaded separately to application-owned caches and are governed
  by their source terms; they are not bundled in the development app.
- Stable BrainGlobe does not provide an enforced authoritative atlas-archive hash. The project
  records the installed atlas metadata digest, not a publisher-signed whole-atlas manifest.
- The Mendeley vascular archive and selected members are hard-pinned by byte count and SHA-256,
  but a digest is an identity/integrity check, not scientific validation.
- `.mouseplan` checksums detect changed project JSON; they do not establish scientific truth,
  source authenticity, or malicious-tamper resistance.
- A project references cached derived/source data. Reopening may fail if an exact required cache
  is unavailable and download is forbidden.
- Atomic save and one `.mouseplan.bak` recovery path exist; continuous autosave and a general
  undo/redo model are not release-qualified.

## Memory and performance

- AtlasAPI 2.3.1 loads complete TIFF reference and annotation volumes. The raw 25 µm pair is
  462,274,560 bytes (0.462 GB / 0.43 GiB); Python objects, temporary arrays, cached images, and UI
  state increase peak memory.
- The optional vascular archive is 311,493,514 bytes and contains large NIfTI members; extraction
  and 50 µm preparation need additional temporary disk and memory.
- Interactive performance has not been qualified across all supported Mac models, prolonged
  sessions, storage-pressure conditions, or concurrent downloads.
- There is no complete cache-removal/relocation management UI.

## Validation boundary

Automated Python and Swift tests cover declared protocol, coordinate, persistence, source-
identity, registration, rendering, and safety invariants. Real 25 µm atlas and native user-
journey checks establish bounded integration evidence. They do not validate independent Allen
anatomy, an individual animal, bregma calibration, vessel clearance, targeting error,
histological outcome, or usability in a live procedure.

See [Scientific Validation](SCIENTIFIC_VALIDATION.md) for the evidence boundary. No prospective
animal study, histological ground truth, phantom targeting study, or statistical accuracy study
has been completed.

## Platform and packaging

- Current development target: macOS 14+ on Apple Silicon (`arm64`) with Python 3.12 and Swift.
- Intel macOS, universal2, Windows, Linux, remote display, and virtual machines are unqualified.
- The development build is ad-hoc signed. A bundled deterministic Python runtime, Developer ID
  signing of nested code, hardened-runtime review, notarization, stapling, and clean-account
  release qualification remain incomplete.
- The actual release dependency inventory and all license notices still require final review.

## Reporting problems

Coordinate issues should include the application version, atlas key/package version, resolution,
orientation, exact named frame/unit, input point, expected result, actual result, and whether the
value is an atlas coordinate or an unprojected bregma entry. Vascular issues should also include
which layer was visible (population density or subject image), source/provenance digest, and
registration state. Do not attach proprietary subject data or large cached datasets.
