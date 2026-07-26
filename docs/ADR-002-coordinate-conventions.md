# ADR-002: Coordinate conventions and atlas provenance

- Status: Accepted for the current SwiftUI/Python hybrid baseline
- Date: 2026-07-21
- Scope: Allen mouse atlases loaded through `brainglobe-atlasapi==2.3.1`

## Context

Mouse Brain Surgery Planner combines image-array indices, atlas mesh coordinates,
anatomical coordinates, renderer coordinates, and optional stereotaxic coordinates. These
spaces do not share an axis order, handedness, origin, or necessarily a landmark such as
bregma. Treating any of them as an unlabeled `(x, y, z)` triplet can silently mirror a plan,
move it by half a voxel, or associate it with the wrong atlas release.

BrainGlobe also deliberately follows image/NumPy (`ij`) indexing. A right-handed Cartesian
renderer does not. BrainGlobe documents that its Allen atlas is ASR and that right-handed 3D
viewers can make the right hemisphere appear to be on the visual left. This is a display and
coordinate-frame conversion issue; atlas arrays must not be modified to compensate for a
camera view.

This ADR defines the authoritative frames, conversions, bounds, provenance, and validation
requirements for the application. Physical skull registration and the experimental determination of
stereotaxic landmarks remain outside the atlas's authority.

## Decision

### 1. Pin the stable BrainGlobe contract

The current baseline uses exactly `brainglobe-atlasapi==2.3.1`, as pinned in `pyproject.toml`. The
application accesses it through one application-owned adapter; domain, UI, persistence, and
rendering code do not call BrainGlobe directly.

The stable constructor is:

```python
BrainGlobeAtlas(
    atlas_name,
    brainglobe_dir=None,
    interm_download_dir=None,
    check_latest=True,
    config_dir=None,
    fn_update=None,
)
```

Stable 2.3.1 has no `version=` constructor argument and exposes the template as
`atlas.reference`. Current unversioned BrainGlobe documentation describes the in-development
3.x API, which adds `version=`, changes storage to NGFF/Zarr/S3, calls the template
`atlas.template`, and retains `reference` only as a deprecated alias. Code for the stable
adapter must be written against the v2.3.1 source, not unversioned API pages.

`check_latest=False` suppresses the remote update check; it does not make construction offline
when the requested atlas is absent. Atlas acquisition, verification, and offline behavior are
therefore responsibilities of the application boundary.

At adapter startup, the application records and verifies at least:

- installed `brainglobe-atlasapi` version;
- atlas API name, for example `allen_mouse_25um`;
- atlas package version from metadata;
- source annotation identifier;
- orientation, shape, and resolution returned by the installed atlas;
- application coordinate-schema and transform versions;
- SHA-256 of the installed atlas `metadata.json`.

An unexpected library version, atlas version, shape, orientation, or metadata-file SHA is an
error, not a warning followed by best-effort loading. The current application does not persist or claim a
package-wide content hash.

### 2. Use named frames, never bare coordinate triplets

The domain model stores named components plus a frame and unit. Serialization and exports must
not contain an unqualified `coordinates: [a, b, c]` field.

| Frame ID | Stored order | Origin and positive directions | Unit | Purpose |
| --- | --- | --- | --- | --- |
| `BRAINGLOBE_VOXEL_ASR` | `[AP, DV, ML]` | origin A/S/R; increases P/I/L | voxel | Continuous voxel coordinates and discrete array indices, with the coordinate kind recorded separately |
| `BRAINGLOBE_PHYSICAL_ASR_UM` | `[AP, DV, ML]` | origin A/S/R; increases P/I/L | µm | BrainGlobe arrays, meshes, queries, and atlas-native exports |
| `SURGERY_WORLD_RAS_UM` | `[ML, AP, DV]` | right/anterior/dorsal positive | µm | Canonical right-handed anatomical and renderer world basis |
| `BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED` | named `[AP, ML, DV]` fields | user-declared bregma; anterior/right/dorsal positive | mm | Legacy v1–v3 target storage before subject calibration; fixed as unprojected and unusable for navigation |
| `STEREOTAXIC_<profile>` | named `ml`, `ap`, `dv` fields | defined by a versioned landmark/calibration profile | internally µm; UI may display mm | Legacy v1–v3 stereotaxic coordinates after explicit subject calibration |

For BrainGlobe ASR specifically:

| Array axis | Domain name | BrainGlobe axis name | Index zero | Increasing index |
| --- | --- | --- | --- | --- |
| 0 | AP | sagittal | anterior | posterior |
| 1 | DV | vertical | superior/dorsal | inferior/ventral |
| 2 | ML | frontal | right | left |

The renderer's screen axes and camera orientation are not a coordinate frame. Screen-left does
not imply anatomical left.

### 3. Distinguish continuous coordinates, indices, and voxel centers

For axis `k`, resolution `r[k]`, shape `N[k]`, continuous voxel coordinate `v[k]`, physical
coordinate `p[k]`, and discrete array index `i[k]`:

```text
p[k] = v[k] * r[k]
i[k] = floor(p[k] / r[k])       for a validated non-negative lookup point
p_index_anchor[k] = i[k] * r[k]
p_center[k] = (i[k] + 0.5) * r[k]
extent[k] = N[k] * r[k]
```

Rules:

1. An atlas lookup coordinate is valid only in the half-open interval
   `0 <= p[k] < extent[k]` on every axis.
2. The geometric outer boundary may be represented at `p[k] == extent[k]`, but it is not an
   indexable atlas sample.
3. A selected image voxel is represented physically by its center unless a compatibility
   operation explicitly requests the BrainGlobe index anchor.
4. Mesh coordinates remain continuous physical coordinates and receive no implicit half-voxel
   offset.
5. The coordinate kind (`continuous`, `index`, `index_anchor`, or `voxel_center`) is persisted
   whenever it cannot be inferred from the frame.
6. A slice header labels its fixed coordinate as atlas-native physical `Atlas AP`, `Atlas ML`,
   or `Atlas DV` in millimetres. It must not present that value as bregma-relative. The editable
   user-facing slice number is one-based in `1...N`; it maps explicitly to internal array index
   `i = number - 1`.

BrainGlobe 2.3.1 converts micron queries with `int(c / resolution)` and does no bounds check.
For positive finite values this behaves like `floor`, but negative fractions can truncate to
zero and negative integers can invoke NumPy indexing from the opposite end. The adapter must
reject negative values, NaN, infinity, the upper extent, and wrong-length vectors before any
BrainGlobe call.

`brainglobe-space.AnatomicalSpace.transformation_matrix_to()` uses `shape`, not `shape - 1`, as
the translation for an axis flip. That convention describes continuous volume-boundary
geometry. A discrete array-index flip is instead `N - 1 - i`; the two operations must not be
substituted for one another.

For the current allowlisted Allen resolution:

| Atlas | Resolution | Shape `[AP,DV,ML]` | Extent in µm | Last index | Last index anchor in µm | Last voxel center in µm |
| --- | --- | --- | --- | --- | --- | --- |
| `allen_mouse_25um` | `(25,25,25)` | `(528,320,456)` | `(13200,8000,11400)` | `(527,319,455)` | `(13175,7975,11375)` | `(13187.5,7987.5,11387.5)` |

### 4. Convert ASR into one right-handed renderer/world frame

Let a BrainGlobe physical point be `[a, d, m]` in µm and let `[a0, d0, m0]` be the explicitly
recorded BrainGlobe-space anchor that should map to the world origin. The canonical world
coordinates are:

```text
x = ML-right    = m0 - m
y = AP-anterior = a0 - a
z = DV-dorsal   = d0 - d
```

With column vectors, the affine mapping is:

```text
                 [ 0  0 -1  m0 ]
M_bg_to_world =  [-1  0  0  a0 ]
                 [ 0 -1  0  d0 ]
                 [ 0  0  0   1 ]
```

The determinant of the linear 3×3 part is `-1`. This reflection is intentional: ordered ASR
array axes are left-handed, while `[right, anterior, dorsal]` is the application's right-handed
world basis.

Consequences for rendering:

- points use the full affine matrix;
- direction vectors use only the linear 3×3 part;
- normals use the inverse-transpose of the linear part;
- triangle winding or normal orientation is corrected once at the renderer boundary when
  required by back-face culling or lighting;
- picked world points are transformed by the stored inverse matrix before atlas lookup;
- camera presets are tested with asymmetric left/right fixtures rather than visual intuition.

No array or saved atlas coordinate is flipped merely to make a particular camera view look
familiar. Any alternate UI sign convention is an explicit presentation/profile transform and
does not change `SURGERY_WORLD_RAS_UM`.

### 5. Treat hemisphere and midline as domain semantics

In stable BrainGlobe source, `left_hemisphere_value == 1` and
`right_hemisphere_value == 2`. For a symmetric atlas, BrainGlobe initializes the volume as
right and labels indices from `round(N_ML / 2)` onward as left. The application reads these
scalar constants from the atlas instance and asserts the observed labels without materializing
BrainGlobe's hemisphere volume; it does not trust the values in prose documentation, which
currently contains a conflicting 0/1 description for direct hemisphere files.

For the even-sized Allen volumes, the continuous midline is:

```text
m_mid_um = extent_ml_um / 2 = 5700 µm
```

The reviewed Allen contract persists this value explicitly as `AtlasMetadata.midline_ml_um`.
Hemisphere classification consumes that provenance field rather than silently recomputing a
center from shape at each call. Metadata validation still requires the midline to be finite,
strictly inside the ML extent, and consistent with the symmetric reviewed volume contract.

Expected neighboring indices are:

| Atlas | Last right index | First left index |
| --- | --- | --- |
| `allen_mouse_25um` | 227 | 228 |

BrainGlobe's half-open lookup assigns a point at exactly 5700 µm to the first left voxel. The
planner instead exposes a three-state semantic classification:

```text
abs(m - m_mid) <= numerical_epsilon  -> MIDLINE
m < m_mid                            -> RIGHT
m > m_mid                            -> LEFT
```

`numerical_epsilon` is only a floating-point comparison tolerance, not an anatomical or
surgical uncertainty band. Biological or procedural uncertainty must be modeled separately.

### 6. Do not present bregma as an intrinsic CCF coordinate

The Allen CCF was built from an average of 1,675 ex-cranio, fixed mouse brains. It has no
single source skull and therefore no Allen-supplied, uniquely correct bregma or lambda. The
application must therefore name and pin any external bregma convention. It must never label an
atlas origin, midpoint, renderer anchor, or ML midline as Allen-official bregma.

The primary v4 direct-plan path uses reference
`pinpoint-allen-mouse-25um-bregma-2025-11-04`, pinned to Virtual Brain Lab Urchin commit
`57be3cdc7d6230543ebbd367be1cbcf1a47862a5` and the SHA-256 of its source file. Its
BrainGlobe physical ASR coordinate is `[AP,DV,ML] = [5200,332,5700] µm`. This is a named
Pinpoint/Urchin population-atlas planning convention, not Allen ground truth, an individual
animal's measured bregma, or a subject registration.

The direct controls have these fixed signs:

```text
AP+ anterior / forward      AP− posterior / back
ML+ right                   ML− left
```

For AP/ML input in millimetres, BrainGlobe ASR coordinates are:

```text
atlas_AP_um = reference_AP_um - 1000 * insertion_AP_mm
atlas_ML_um = reference_ML_um - 1000 * insertion_ML_mm
```

At the resulting AP/ML column, v4 resolves the entry from the loaded annotation with
`first-annotated-voxel-superior-boundary-v1`: scan DV from superior to inferior and use
`first_nonzero_index * DV_resolution` as the physical surface boundary. That boundary is the
surface crossing of user-facing Shank 1 (catalog ID `shank-0`), not an array midpoint or a point
inside the brain. The plan persists the annotation source and digest, the reference
source/revision/digest, the AP/ML controls, and the resolved entry. Validation re-resolves that
evidence against the loaded annotation.

V4 depth is a strictly positive path length from Shank 1's resolved surface crossing to that
shank's distal target, not a bregma-relative DV value. With visible sagittal angle `θ`, the
canonical `[AP,ML,DV]` inward direction is:

```text
[-sin(θ), 0, -cos(θ)]
```

Thus zero is deep/ventral, positive advances anterior-to-posterior, and negative advances
posterior-to-anterior. The allowed layout values are `0°` and `90°`: `0°` puts the NP2013
shank-spacing axis in the sagittal plane with Shank 1 most anterior and the other shanks extending
posterior. `90°` rotates the whole array clockwise when viewed dorsally, making Shank 1
animal-left-most and extending the other shanks toward animal right.

Every supported NP2 shank retains its complete 10,000 µm catalogued proximal-to-distal extent in
3D. At insertion depth `d`, the remaining `10,000 − d` µm projects proximally from the surface and
can be outside the brain/atlas. Slice overlays, annotation traversal, export, and path analysis
use the distinct implanted surface-to-tip segment; the external remainder is not tissue
traversal.

This direct v4 representation remains `usable_for_navigation=false` and requires independent
verification against the animal and rig. It does not require a separate target projection or a
subject calibration because it makes the population-atlas assumption explicit and
provenance-bearing; this is not evidence that the assumption is biologically accurate.

Legacy v1–v3 records preserve bregma-relative AP/ML/DV targets in
`BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED`:

```text
AP+ anterior / forward      AP− posterior / back
ML+ right                   ML− left
DV+ dorsal / up             DV− deep / ventral
```

The legacy ML sign is intentionally preserved as serialized historical meaning and matches the
current v4 UI's `ML (+R / −L)` display. The meanings are still not interchangeable: legacy
coordinates describe an unprojected subject-stereotaxic target, while v4 coordinates identify
an atlas-surface insertion column. Schema migration never copies a legacy ML number into a v4
input; an explicit, reviewed conversion is required.

Those target records must serialize `projected=false` and `usable_for_navigation=false`. They
have no implicit Allen point, renderer point, region, or trajectory. Their projected stereotaxic
coordinates become available only through their existing explicit subject-calibration path.

A calibration's atlas bregma and lambda landmarks must lie within half one ML voxel of the
persisted atlas midline. Its named right-skull and left-skull landmarks must straddle that
midline on their respective BrainGlobe sides, each at least half one ML voxel away. A violation
is rejected as `CALIBRATION_ATLAS_MIDLINE_MISMATCH` before project mutation. The same invariant
is revalidated when a persisted project is loaded, so an older or forged calibration cannot
bypass the create boundary. Together with the existing bregma-anterior-to-lambda AP ordering,
this binds the calibration to the required presentation semantics: `AP−` is posterior and
`ML−` is animal-left, which appears screen-right in the reviewed Dorsal, Coronal, and Horizontal
camera presets.

The persisted calibration is not trusted merely because its own digest is internally
consistent. Validation regenerates the skull transform through the production landmark
calibration and regenerates the atlas transform through the production anatomical fit. It
compares the derived matrices, landmark correspondences and residuals, transform semantics,
skull leveling angles, and skull QC at a tolerance far below one micrometre. Stored landmark
UUIDs and calibration/transform UUIDs remain identity fields rather than regenerated geometry.
Thus a changed and self-rehashed matrix, residual, leveling result, or QC result fails closed.

A calibration profile records at least:

- stable profile ID and schema version;
- source and citation;
- landmark coordinates and their source frame;
- full affine or other declared transform, including any rotation or scale;
- an orientation-preserving anatomical linear component with positive determinant; a
  left/right reflection is rejected rather than treated as affine distortion;
- axis order, signs, units, and voxel-anchor policy;
- atlas identity and content hash to which it applies;
- uncertainty or validation notes.

Every v4 plan is semantically bound to its exact reference, annotation surface evidence, AP/ML,
depth, angle, layout, and probe-model snapshot—not only to a self-contained record hash.
Project validation reproduces that geometry before display, analysis, or export.

Legacy planning-algorithm v2/v3 records remain semantically bound to their exact source target
and referenced calibration. Project validation fully reconstructs placement from preserved mode,
entry when applicable, angles, depth, roll, probe model, target, and calibration; it then
compares every physical geometry field as well as the target projection digest. Uniformly
translated and same-target alternate-angle placements therefore fail even with recomputed
record hashes. Historical v1 records do not preserve enough inputs for independent
reconstruction; they remain load/review only and cannot enter 2D/3D planning overlays, PDF
planning pages, or region analysis until updated. Vessel-clearance analysis is unavailable for
every plan version.

A catalog-owned probe-model snapshot is also compared field for field with the exact pinned
catalog definition. Identity/version, source provenance, verification state, shank dimensions
and offsets, tip geometry, and the complete ordered recording-site table are part of that
semantic boundary. Unknown custom identities may survive only in a historical v1 audit record;
they are not accepted for current planning geometry or analysis.

Persistence schema 9 adds the optional calibration-free atlas-surface v4 representation.
Migration from schema 8 deep-copies the record and advances only the envelope version; it does
not convert a legacy target/calibration plan into v4, infer a surface, rewrite controls, or repair
scientific geometry. The validator accepts reproducible v1–v4 state or rejects it with no guessed
correction.

The IBL estimate `[ML, AP, DV] = [5739, 5400, 332] µm` is explicitly part of the “IBL Bregma
and coordinate system.” It is distinct from the selected Pinpoint/Urchin profile and must not be
silently substituted or labeled an official Allen bregma. Likewise, no 5-degree tilt, DV scale,
or other empirical correction is applied invisibly.

### 7. Separate CCF framework, annotation release, and BrainGlobe package provenance

The BrainGlobe Allen packager cites Wang et al. 2020, but stable source obtains its annotation
through:

```python
ReferenceSpaceCache(reference_space_key="annotation/ccf_2017")
```

and requests meshes with:

```python
download_structure_mesh(ccf_version="annotation/ccf_2017", ...)
```

The Allen Brain Cell Atlas separately distributes assets named `Allen-CCF-2020`, whose 2020
annotation includes changes described by Allen. Consequently, the following are different
identifiers and must not be collapsed into one “atlas version” string:

- framework/publication: Allen CCFv3, Wang et al. 2020;
- source annotation requested by the stable BrainGlobe packager: `annotation/ccf_2017`;
- BrainGlobe atlas package version: exactly `1.2` for the allowlisted Allen 25 µm package;
- BrainGlobe library version: `2.3.1` for the current adapter.

Calling the BrainGlobe package “the 2020 annotation” solely because it cites Wang et al. is
prohibited. If a feature specifically requires the Allen 2020 parcellation, that asset must be
selected, adapted, versioned, and validated as a separate data source.

Stable BrainGlobe's atlas-validation module contains a checksum function that is explicitly an
unimplemented, always-true placeholder. The application therefore computes and persists the SHA-256 of
the installed `metadata.json` as an exact metadata identity, while explicitly not claiming that
upstream verified the archive or that all package files were authenticated. A future
package-wide integrity feature must define a versioned file manifest and hash every covered file.

### 8. Treat external Allen files as a separate import frame

Allen first-party documentation describes downloaded volumes as anterior-to-posterior,
superior-to-inferior, left-to-right (ASL). BrainGlobe maintainers empirically describe the raw
ARA array under NumPy/ij viewing semantics as ASR and standardize BrainGlobe atlases on ASR.
SimpleITK image axes, NRRD physical-space metadata, and returned NumPy array axes can also have
different orders. A three-letter orientation without the represented object and reader
semantics is insufficient.

An external Allen NRRD/NIfTI import must supply or derive and then display for confirmation:

- file format and content identity;
- reader library and version;
- file/physical axis order and NumPy array axis order;
- anatomical direction at each axis origin;
- voxel spacing, physical units, affine, and voxel-center convention;
- source annotation/framework release;
- the exact transform into an application frame.

The importer must verify an asymmetric first-party reference fixture before it is enabled. If
the metadata is missing or contradictory, the import fails with an actionable error. It does
not guess whether “Allen XYZ” means ASL, ASR, `[AP,DV,ML]`, `[ML,AP,DV]`, NIfTI physical axes,
or an already transformed stereotaxic frame.

## Prohibited assumptions

The following are correctness errors:

- storing or accepting an unlabeled three-number coordinate as self-describing;
- treating AP/ML/DV, array axes, mesh axes, renderer XYZ, and screen axes as the same order;
- identifying anatomical left or right from where a hemisphere appears on screen;
- assuming all Allen files have the same array order after different readers load them;
- applying a hidden left/right flip, reflected anatomical calibration, half-voxel shift, tilt,
  scale, or unit conversion;
- treating `shape * resolution` as the last valid lookup coordinate;
- passing negative, non-finite, or upper-bound coordinates to BrainGlobe;
- using `shape` and `shape - 1` flip translations interchangeably;
- hard-coding hemisphere file values from documentation instead of the installed API contract;
- labeling atlas center, an IBL estimate, or a user landmark as official Allen bregma;
- projecting a legacy uncalibrated AP/ML/DV target, or using an unnamed/unpinned bregma estimate,
  in the atlas, renderer, anatomy, or a vascular overlay;
- equating the CCFv3/Wang 2020 publication, `ccf_2017` annotation, `Allen-CCF-2020`
  annotation, BrainGlobe package version, and library version;
- assuming a successful BrainGlobe download has passed a cryptographic checksum;
- reusing a saved transform with a different atlas identity, resolution, source annotation, or
  content hash.

## Verification matrix

Tests must exercise the application adapter, not only reproduce BrainGlobe internals.

| Area | Required fixture or input | Required assertion |
| --- | --- | --- |
| Stable API | installed package and adapter | library is exactly 2.3.1; stable constructor/reference behavior is used; unexpected API surface fails clearly |
| 25 µm metadata | real or locked metadata | ASR, `[AP,DV,ML]`, shape `(528,320,456)`, resolution `(25,25,25)`, same extent |
| Bounds | `0`, last valid cell, `extent`, `-0.1`, negative index, NaN, and infinities | valid points resolve; all invalid points are rejected before BrainGlobe/NumPy indexing |
| Voxel semantics | first/last indices at 25 µm | index anchor and center match the table; `floor(center/r)` returns the original index |
| Continuous round trip | random finite points strictly inside the volume | voxel→µm→voxel error ≤ `1e-9` voxel and frame/unit labels survive serialization |
| World affine | random points, vectors, and an arbitrary explicit anchor | anchor maps to zero; inverse round trip error ≤ `1e-6` µm; linear determinant is `-1`; vectors receive no translation |
| Hemisphere | ML indices 227/228; physical ML 5700 µm | neighboring cells are right/left through installed constants; exact plane is domain `MIDLINE` |
| Region lookup | manually frozen interior points at 25 µm | physical interior points resolve to expected region IDs/acronyms; boundary points are separately marked |
| Mesh/volume | root plus selected region meshes | coordinates are in µm; bounds lie within the volume plus one-voxel generation tolerance; verified interior samples resolve to the region or a descendant |
| Rendering/picking | asymmetric left/right landmarks and camera presets | landmarks render on the anatomically intended sides; normals/winding are correct; picking round-trips to the original BrainGlobe point |
| External Allen import | asymmetric ASL/ASR golden fixtures | declared transforms produce the expected hemisphere and region; ambiguous XYZ or missing metadata is rejected |
| V4 bregma AP/ML signs | positive/negative values around the pinned Pinpoint/Urchin reference | AP+ resolves toward anterior, AP− posterior, ML+ animal-right, and ML− animal-left |
| V4 surface/depth | asymmetric annotation columns with different first nonzero DV indices | AP/ML anchors user-facing Shank 1 at the exact superior voxel boundary; Shank 1 surface-to-distal-target length equals requested positive depth; changed annotation evidence fails |
| V4 angle/layout | positive/negative sagittal angle and NP2013 `0°`/`90°` layout | positive advances A→P, negative P→A; `0°` makes Shank 1 most anterior and `90°` clockwise makes it animal-left-most |
| V4 full shaft | depths below 10,000 µm in 3D and slice/traversal payloads | each 3D shank spans the complete 10,000 µm proximal-to-distal extent; only the surface-to-tip segment contributes to slice/traversal/path analysis |
| Unprojected bregma target | strict decimal AP/ML/DV input, zero values, signs, save/reopen | exact named values and frame survive; AP− is posterior, ML− is left, DV− is deep; projection and navigation remain false |
| Calibration reproduction and direction | midline bregma/lambda, AP-reversed pair, named lateral pair, shifted axis, same-side pair, half-voxel boundary points, and forged matrices/residuals/QC | valid fits reproduce from stored landmarks and preserve AP−→posterior and ML−→animal-left; reversed, shifted, same-side, too-close, or forged fits fail before use |
| Stereotaxic profile | explicit user anchor and optional named estimate | selected landmark maps to zero and inverses correctly; no profile is silently selected; profile/atlas mismatch is rejected |
| Provenance/integrity | saved project with locked identity and hash | exact identity reloads; changed package, source annotation, resolution, transform schema, or hash fails closed |

Numerical transform tests do not replace visual validation. At least one asymmetric left/right
golden fixture must be inspected and frozen before coordinate behavior is considered
validated.

## Consequences

- Coordinate payloads and exports are more verbose, but they are independently interpretable.
- BrainGlobe upgrades and alternate atlas sources are isolated behind a versioned adapter.
- Renderer reflection handling is explicit and testable instead of being hidden in camera or
  data flips.
- The application can display atlas-native coordinates without implying stereotaxic accuracy.
- The application can use a named, source-pinned population-atlas bregma convention without
  mislabeling it as Allen ground truth or individual-animal registration.
- The application can preserve a legacy bregma-relative target without inventing a subject
  projection or navigation claim.
- Supporting a new bregma estimate, atlas annotation, reader, or UI sign convention requires a
  named profile/adapter and validation fixtures rather than a global constant.
- Old projects remain reproducible only while their atlas identity, content hash, transform,
  units, and anchor policies remain available; otherwise they open in a clearly reported
  incompatible state rather than being silently reinterpreted.

## First-party sources

- BrainGlobe package release: [`brainglobe-atlasapi 2.3.1` on PyPI](https://pypi.org/project/brainglobe-atlasapi/)
- Stable constructor and acquisition behavior: [`bg_atlas.py` at v2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/bg_atlas.py#L34-L115)
- Stable orientation, shape, resolution, hemisphere, coordinate lookup, and bounds behavior: [`core.py` at v2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/core.py)
- BrainGlobe ASR and handedness guidance: [Image space definition](https://brainglobe.info/documentation/setting-up/image-definition.html#handedness)
- BrainGlobe maintainer analysis of ASR versus Cartesian/ij views: [brainglobe-atlasapi issue #73](https://github.com/brainglobe/brainglobe-atlasapi/issues/73)
- BrainGlobe direct-file hemisphere documentation: [Using the files directly](https://brainglobe.info/documentation/brainglobe-atlasapi/usage/using-the-files-directly.html)
- Continuous point transformation implementation: [`brainglobe-space` v1.0.3 `core.py`](https://github.com/brainglobe/brainglobe-space/blob/v1.0.3/brainglobe_space/core.py#L292-L340)
- Allen BrainGlobe packager and `annotation/ccf_2017` source key: [`atlas_scripts/allen_mouse.py` at v2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/atlas_scripts/allen_mouse.py)
- Checksum placeholder: [`validate_atlases.py` at v2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/atlas_generation/validate_atlases.py#L187-L203)
- Current BrainGlobe Allen package versions: [`last_versions.conf`](https://gin.g-node.org/brainglobe/atlases/raw/master/last_versions.conf)
- AllenSDK orientation and reference-space example: [Reference Space notebook](https://alleninstitute.github.io/AllenSDK/_static/examples/nb/reference_space.html)
- Allen CCF 2020 assets, orientation, dimensions, and annotation description: [Allen Brain Cell Atlas CCF tutorial](https://alleninstitute.github.io/abc_atlas_access/notebooks/ccf_and_parcellation_annotation_tutorial.html)
- Allen explanation for the absence of CCF bregma: [Allen Brain Map Community response](https://community.brain-map.org/t/why-doesnt-the-3d-mouse-brain-atlas-have-bregma-coordinates/158)
- Pinned direct-plan reference: [Virtual Brain Lab Urchin `Utils.cs` at commit `57be3cdc`](https://github.com/VirtualBrainLab/Urchin/blob/57be3cdc7d6230543ebbd367be1cbcf1a47862a5/UnityClient/Packages/vbl.urchin/Scripts/Utils/Utils.cs)
- CCFv3 publication: [Wang et al. 2020](https://doi.org/10.1016/j.cell.2020.04.007)
- IBL's explicitly named bregma coordinate system: [`iblatlas` 1.2.0 `atlas.py`](https://github.com/int-brain-lab/iblatlas/blob/1.2.0/iblatlas/atlas.py)
