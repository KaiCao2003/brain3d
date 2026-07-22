# Coordinate Systems

Mouse Brain Surgery Planner uses explicit coordinate frames. A three-number tuple is never
self-describing: its axis order, direction, unit, atlas identity, and voxel-anchor meaning must
be known before it can be interpreted.

The normative engineering decision is [ADR-002: Coordinate conventions and atlas
provenance](docs/ADR-002-coordinate-conventions.md). This guide explains that decision with
diagrams and worked examples for the current baseline,
`brainglobe-atlasapi==2.3.1`.

> **Not stereotaxically calibrated:** Atlas-native and renderer coordinates are not bregma
> coordinates. The Allen CCF has no official, unique bregma. Until an explicit, versioned
> calibration profile is selected, the planner must not label any origin as bregma or claim
> correspondence to a physical skull.

## Frames at a glance

| Frame ID | Value order | Zero-side anatomy | Positive directions | Unit |
| --- | --- | --- | --- | --- |
| `BRAINGLOBE_VOXEL_ASR` | `[AP, DV, ML]` | anterior, superior, right | posterior, inferior, left | continuous voxel |
| `BRAINGLOBE_VOXEL_INDEX_ASR` | `[AP, DV, ML]` | anterior, superior, right | posterior, inferior, left | integer index |
| `BRAINGLOBE_PHYSICAL_ASR_UM` | `[AP, DV, ML]` | anterior, superior, right | posterior, inferior, left | µm |
| `SURGERY_WORLD_RAS_UM` | `[ML, AP, DV]`, exposed to the renderer as `[x,y,z]` | selected anchor | right, anterior, dorsal | µm |
| `BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED` | named `[AP, ML, DV]` | user-declared bregma | anterior, right, dorsal/up | mm |
| `STEREOTAXIC_<profile>` | named `ml`, `ap`, `dv` fields | profile-defined landmark | profile-defined | internal µm; UI may show mm |

Every point also carries `atlas_key` and `atlas_version`. A point from another atlas package is
rejected rather than reinterpreted. Saved project provenance additionally records the SHA-256 of
the installed atlas `metadata.json`; it does not yet contain a package-wide content manifest.
`BrainGlobeAtlasSpace` itself currently enforces the point's key and package version.

## BrainGlobe ASR array space

BrainGlobe stable atlases follow image/NumPy indexing. Their Allen arrays and mesh coordinates
are standardized as ASR and ordered `[AP,DV,ML]`:

```text
Array axis 0:  AP

    index 0
  ANTERIOR  ----------------------->  POSTERIOR
                    increasing AP index (+)

Array axis 1:  DV

    index 0
  SUPERIOR / DORSAL  -------------->  INFERIOR / VENTRAL
                         increasing DV index (+)

Array axis 2:  ML

    index 0
  RIGHT  -------------------------->  LEFT
                    increasing ML index (+)

Tuple order passed to BrainGlobe:  [AP, DV, ML]
```

`ASR` names the anatomical side at the zero end of each array axis: anterior, superior, right.
It does not mean the positive directions are anterior, superior, and right; the positive array
directions go toward their opposites.

The axes can also be summarized as signs relative to the right-handed world frame:

```text
BrainGlobe +AP  = world -AP  = posterior
BrainGlobe +DV  = world -DV  = inferior / ventral
BrainGlobe +ML  = world -ML  = left
```

## Right-handed world and renderer space

The renderer receives a conventional right-handed anatomical basis:

```text
SURGERY_WORLD_RAS_UM

                   +z  DORSAL
                    |
                    |
                    O-------- +x  RIGHT
                   /
                  /
                +y  ANTERIOR

  x = ML right-positive       -x = left
  y = AP anterior-positive    -y = posterior
  z = DV dorsal-positive      -z = ventral

Renderer tuple order: [x, y, z] = [ML-right, AP-anterior, DV-dorsal]
```

This is not the array order. A camera's screen-left and screen-right are presentation choices,
not anatomical directions.

The conversion boundary is:

```text
 BrainGlobe physical ASR                         World / renderer RAS

 [a, d, m] µm  -------- permutation, sign flip -------->  [x, y, z] µm
 [AP,DV,ML]              and explicit anchor             [ML,AP,DV]

                 <------------- inverse -------------
```

## Voxel, index, physical coordinate, and center

For one axis with voxel size `r`, continuous voxel coordinate `v`, discrete index `i`, physical
coordinate `p`, and array size `N`:

```text
p = v * r
v = p / r
i = floor(p / r)             after validating p

p_index_anchor = i * r
p_center       = (i + 0.5) * r
extent         = N * r
```

An atlas lookup uses half-open bounds:

```text
valid:    0 <= p < N*r
invalid:  p < 0
invalid:  p == N*r
invalid:  p > N*r
```

The outer geometry can have a boundary at `N*r`, but that boundary is not an indexable voxel.
Negative values, NaN, and positive or negative infinity are rejected before NumPy or
BrainGlobe is called. This prevents NumPy negative-index wraparound and BrainGlobe's
`int(c/resolution)` truncation from turning a small negative coordinate into index zero.

When a user selects an image voxel, the planner represents it physically by its center. Mesh
vertices remain continuous physical coordinates and receive no automatic half-voxel shift.

### 25 µm example

The current atlas, `allen_mouse_25um`, has:

```text
resolution:  [25, 25, 25] µm
shape:       [528, 320, 456]
extent:      [13200, 8000, 11400] µm
last index:  [527, 319, 455]
last anchor: [13175, 7975, 11375] µm
last center: [13187.5, 7987.5, 11387.5] µm
```

The same physical point `[1234, 567, 5699] µm` becomes:

```text
continuous voxel = [49.36, 22.68, 227.96]
containing index  = [49,    22,    227]
```

`[13200, 0, 0] µm` is invalid because AP is exactly at the upper extent. The largest valid AP
lookup coordinate is any finite representable value strictly less than `13200 µm`.

## Midline and hemisphere

The current Allen atlas has ML extent `11400 µm`, so the continuous midline is:

```text
m_mid = 11400 / 2 = 5700 µm
```

The adjacent ML cells are:

```text
25 µm atlas

  RIGHT cell, index 227             LEFT cell, index 228
  [5675, 5700) µm                   [5700, 5725) µm
                 | 5700 µm |
                 +-- MIDLINE --+
```

Two different operations therefore give intentionally different answers at exactly 5700 µm:

1. Annotation lookup applies the half-open cell rule and returns the first left voxel.
2. Continuous hemisphere classification returns `MIDLINE` when
   `abs(m - 5700) <= 1e-9 µm`.

The `1e-9 µm` value is a numerical comparison tolerance only. It is not a biological midline
width, targeting uncertainty, or surgical error bound. Current planner classification uses the
continuous midpoint of a symmetric atlas; it does not read a BrainGlobe hemisphere volume.
BrainGlobe stable exposes 1 for left and 2 for right, so any future code that consumes such a
volume must read the installed API constants rather than relying on a prose document or
hard-coded TIFF values.

## BrainGlobe-to-world formula

Let a BrainGlobe physical point be:

```text
p_bg = [a, d, m, 1]ᵀ
```

and let the explicitly stored BrainGlobe anchor be:

```text
b_bg = [a0, d0, m0]
```

The world values are:

```text
x = m0 - m       ML, right-positive
y = a0 - a       AP, anterior-positive
z = d0 - d       DV, dorsal-positive
```

Using column vectors:

```text
                  [ 0  0 -1  m0 ]
M_bg_to_world  =  [-1  0  0  a0 ]
                  [ 0 -1  0  d0 ]
                  [ 0  0  0   1 ]

p_world = M_bg_to_world * p_bg
```

The linear 3×3 determinant is `-1`. The reflection is expected because ordered ASR image axes
are left-handed while `[right, anterior, dorsal]` is right-handed. Renderer code transforms
points with the affine, directions without translation, repairs triangle winding after the
reflection, and recomputes consistent normals.

### Worked renderer example

Choose this atlas-native anchor for the example only:

```text
anchor = [a0, d0, m0] = [6600, 4000, 5700] µm
```

This anchor is **not bregma**. For:

```text
p_bg = [6100, 3500, 5200] µm
```

the world point is:

```text
x = 5700 - 5200 = 500 µm right
y = 6600 - 6100 = 500 µm anterior
z = 4000 - 3500 = 500 µm dorsal

p_world = [500, 500, 500] µm
```

### Renderer pick inverse

A picked renderer value `[x,y,z]` returns to BrainGlobe physical space with:

```text
a = a0 - y
d = d0 - z
m = m0 - x
```

For the picked `[500,500,500] µm` and the same anchor:

```text
a = 6600 - 500 = 6100 µm
d = 4000 - 500 = 3500 µm
m = 5700 - 500 = 5200 µm
```

The result exactly recovers the example atlas point. A production pick is then subjected to
atlas identity, finiteness, and half-open physical bounds checks before annotation lookup.

## Bregma and stereotaxic profiles

The Allen CCF was created from an average of 1,675 ex-cranio fixed brains. There is no single
source skull and no Allen-provided uniquely correct bregma or lambda. Consequently:

```text
atlas origin       != bregma
atlas center       != bregma
ML midline         != a complete bregma calibration
renderer anchor    != bregma unless a profile explicitly establishes it
```

The UI nevertheless allows the user to preserve the standard surgical entry exactly as entered
from bregma. Its signs are:

```text
AP+ anterior / forward      AP− posterior / back
ML+ right                   ML− left
DV+ dorsal / up             DV− deep / ventral
```

For example, `[AP,ML,DV] = [-1.25,-0.70,-2.40] mm` records a point 1.25 mm posterior,
0.70 mm left, and 2.40 mm deep/ventral from bregma. The stored frame ID is
`BREGMA_RELATIVE_AP_ML_DV_MM_UNPROJECTED`. It deliberately has no atlas coordinate,
`projected=false`, and `usable_for_navigation=false`.

This unprojected record does not contradict the absence of an official CCF bregma: it preserves
the user's surgical-frame input without pretending to know the bregma/skull-to-atlas transform.
The application must not place an atlas marker, calculate a trajectory, sample a region, or
compare the target with a vascular overlay from that record alone.

A projected stereotaxic profile must name its source and version and store its landmark,
affine/transform, axis signs, units, atlas identity, hash, voxel convention, and uncertainty.
The IBL bregma estimate is an IBL convention and may only be offered as a named opt-in profile;
it must not be silently presented as Allen ground truth. No tilt or DV scale is hidden in the
base atlas-to-world transform.

Millimetre values in the UI are formatting conversions from a declared profile or frame. A
unit conversion alone does not create stereotaxic calibration.

## Dorsal overlay plane

The current Dorsal view projects the radius-bearing LAMBADA P60_606 reference graph onto the
atlas AP-by-ML grid. This collapses all retained DV positions; it does not imply that a projected
line lies on the cortical surface. Coronal, sagittal, and horizontal views instead include only
vessel portions whose radius-bearing volume intersects the current slice slab. SceneKit renders
the same physical `[AP,DV,ML]` points and radii after the centralized display-axis conversion.

Archived population-density and registered subject-image paths also use an AP-by-ML display grid,
but they are absent from the primary UI and never substituted for the LAMBADA graph. A population
maximum contains no recoverable DV position, and a registered 2D image does not become 3D vessel
geometry.

## Provenance and external Allen data

The current BrainGlobe package provenance keeps these identities separate:

```text
framework / publication:  Allen CCFv3, Wang et al. 2020
source annotation request: annotation/ccf_2017
BrainGlobe atlas package:  allen_mouse_25um v1.2
BrainGlobe library:        2.3.1
```

The citation year does not turn `annotation/ccf_2017` into the separately distributed
`Allen-CCF-2020` annotation.

Allen first-party documentation describes downloaded volume axes as ASL, while BrainGlobe's
NumPy/ij convention and standardized packages are ASR. NRRD physical axes, SimpleITK image
axes, and returned NumPy array axes may also be ordered differently. External Allen files must
therefore enter through an importer that records the file affine, reader and version, array
order, anatomical directions, units, voxel-center convention, and source release. An unlabeled
“Allen XYZ” tuple is rejected rather than guessed.

## Primary references

- [ADR-002: Coordinate conventions and atlas provenance](docs/ADR-002-coordinate-conventions.md)
- BrainGlobe stable implementation: [`core.py` at v2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/brainglobe_atlasapi/core.py)
- BrainGlobe ASR and handedness guidance: [Image space definition](https://brainglobe.info/documentation/setting-up/image-definition.html#handedness)
- BrainGlobe's Cartesian/ij analysis: [brainglobe-atlasapi issue #73](https://github.com/brainglobe/brainglobe-atlasapi/issues/73)
- BrainGlobe Allen packager and `annotation/ccf_2017`: [`allen_mouse.py` at v2.3.1](https://github.com/brainglobe/brainglobe-atlasapi/blob/v2.3.1/atlas_scripts/allen_mouse.py)
- AllenSDK reference-space orientation: [Reference Space notebook](https://alleninstitute.github.io/AllenSDK/_static/examples/nb/reference_space.html)
- Allen CCF 2020 assets and dimensions: [Allen Brain Cell Atlas CCF tutorial](https://alleninstitute.github.io/abc_atlas_access/notebooks/ccf_and_parcellation_annotation_tutorial.html)
- Allen explanation of why the CCF has no bregma: [Allen Brain Map Community response](https://community.brain-map.org/t/why-doesnt-the-3d-mouse-brain-atlas-have-bregma-coordinates/158)
- CCFv3 publication: [Wang et al. 2020](https://doi.org/10.1016/j.cell.2020.04.007)
