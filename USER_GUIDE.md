# User Guide

Brain3D is a native SwiftUI + SceneKit workspace backed by a Python scientific service. It is
restricted to mouse animal research and accepts only BrainGlobe `allen_mouse_25um` v1.2 during
this testing phase.

> **Non-human, non-clinical use only.** This development build is not a qualified navigation or
> veterinary device. Independently review all coordinates, laterality, atlas-profile assumptions,
> probe geometry, anatomy, vessel limitations, and procedure decisions.

## Start a development build

```bash
uv sync --frozen --group dev
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
```

Create or open a `.mouseplan`. A new project requires a stable subject identifier before planning;
that identity is persisted with every revision and mutation. Then open/download the reviewed
25 µm atlas when prompted. The 10 µm atlas is not offered; existing 10 µm cache data is left
untouched.

## Navigate the atlas

The mode bar is exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, with one full-size view:

- **Dorsal** shows the atlas surface and the selected probe's AP/ML landmarks and shank path;
  recording sites remain in true-depth slice views.
- **Coronal**, **Sagittal**, and **Horizontal** each keep an independent depth. Use the slider,
  previous/next buttons, wheel, or enter an exact one-based slice number; drag pans and pinch
  zooms. The header's `Atlas AP`, `Atlas ML`, or `Atlas DV` value is the Allen atlas physical
  coordinate in millimetres—not a bregma-relative implant coordinate.
- **3D** shows a SceneKit brain mesh and planned probe envelopes. Drag/orbit and zoom use native
  camera control; **Reset Camera** restores the overview.

Click a slice or the 3D brain to replace the compact region acronym/name display. The selected
structure and its annotation descendants are highlighted wherever they intersect Dorsal,
Coronal, Sagittal, and Horizontal; the same ontology identity requests its reviewed 3D mesh when
one exists.
Clicking does not change a slice depth. There is no focus mode, crosshair, 2×2 layout, or
capillary layer.

Use the common Allen region browser/search to reach the complete 840-structure ontology, including
thalamus, cerebellum, brainstem, and other non-cortical structures. Selecting a search or tree
result replaces the same region selection used by all five modes; switching modes preserves that
selection and does not couple the three independent slice depths. Highlight geometry is shown only
where the reviewed annotation or mesh contains it. For example, `RSPd4` (structure 545) is present
in the ontology but has no voxels and no mesh in this atlas package: it remains selected, all four
2D overlays truthfully contain zero highlighted pixels, and 3D reports that no reviewed geometry
exists instead of fabricating a shape. Only the selected region mesh is loaded for 3D highlighting.

## Create a probe plan

The primary card has one hardware picker and five implant controls. Hardware has exactly two
choices:

- `NP2003 · 1 shank`;
- `NP2013 · 4 shank`.

`NP2004` and `NP2014` remain in cited source artifacts because those order codes share the
transcribed physical geometries, but they are not additional UI choices. Quad Base, NP1, and the
synthetic fixture remain archived compatibility/test definitions.

Enter the surface insertion AP and ML in millimetres from the named Pinpoint/Urchin atlas
profile. The labels are `AP (+A / −P)` and `ML (+R / −L)`:

| Axis | Positive | Negative |
| --- | --- | --- |
| AP | anterior / forward | posterior / back |
| ML | right | left |

`AP -1.25`, `ML -0.70` means 1.25 mm posterior and 0.70 mm left. Brain3D maps those values to
one AP/ML column in the loaded annotation, then resolves the superior boundary of the first
non-background voxel as the surface crossing of user-facing **Shank 1** (catalog ID `shank-0`).
The other three NP2013 shanks retain their 250 µm hardware offsets. AP/ML is never interpreted as
the array centre, the distal target, or another point inside the brain.

There is no probe Apply/Create button. A numeric field updates only when you press Return or move
focus out, so an intermediate `9` while entering `90` is never submitted. NP2003/NP2013 and the
sagittal/90° layout are atomic choices and update immediately. Incomplete or invalid text leaves
the last valid trajectory on screen and guards saving/export. For a new project, valid prepared
defaults create the first direct plan automatically when atlas planning becomes ready.

Enter the remaining controls as follows:

- **Depth (mm)** is the positive path length from Shank 1's exact local surface crossing to Shank
  1's distal target. The UI accepts `>0` through `10` mm (the encoded shaft length). It is not a
  signed DV coordinate, an array-centre depth, or a distance from the atlas-volume boundary.
- **A↔P angle (°)** is `0°` for an inward/deep insertion. Positive angles advance from anterior
  toward posterior (A→P); negative angles advance from posterior toward anterior (P→A). The
  accepted interval is strictly between `−90°` and `+90°`.
- **Probe layout** is `Sagittal` when the NP2013 four-shank plane is parallel to the sagittal
  plane: Shank 1 is most anterior and the other shanks extend posterior. `90° CW` rotates the
  whole array clockwise as viewed from dorsal: Shank 1 is animal-left-most and the other shanks
  extend toward animal right.

The Dorsal, Coronal, and Horizontal canvases label animal right on the screen-left edge and
animal left on the screen-right edge. Thus `ML < 0` appears on the screen-right `L` side, while
`AP < 0` appears toward `P`. The current plan remains visible while switching among all five
modes.

The direct v4 path deliberately has no separate implant-target chooser, plan-name field,
azimuth/elevation/roll controls, subject-calibration prerequisite, or geometry checkbox. Its
built-in model snapshots still have status `source-transcribed-review-pending`: removing a
checkbox does not establish independent transcription review. Brain3D represents all physical
sites, not the active acquisition configuration; it does not yet import an IMRO/electrode
selection.

The profile persisted with each v4 plan is pinned to Virtual Brain Lab Urchin/Pinpoint source
code, including revision and SHA-256. It supplies a reproducible population-atlas coordinate
convention; it is not Allen-official ground truth, an individual-animal registration, or a
measured skull calibration. Independently verify the planned entry and trajectory against the
animal and stereotaxic apparatus.

Persisted catalog models are checked against the exact source-pinned definition, including every
shank dimension and offset, tip field, ordered recording site, verification field, and source
record. Editing one of those values and recomputing its surrounding hashes is rejected. An
unknown custom model can remain only in a historical v1 audit record and cannot enter current
planning geometry or analysis.

After creating a plan, slice views and atlas-region traversal use the implanted surface-to-tip
segments that intersect the current slab. 3D shows every complete 10 mm NP2 shaft: when the
requested depth is `d`, the remaining `10 − d` mm extends proximally above the surface and can lie
outside the brain/atlas. Cap, cable, headstage, and base-electronics geometry are not modeled.
Older project packages may retain archived v1–v3
target, calibration, and multi-angle records. Brain3D preserves their inputs and original
semantics for compatibility; the primary v4 card does not expose or silently convert them.

Brain3D has one main planning window. The probe draft belongs to the planner session rather than
to the sidebar, so closing and reopening that window while the app remains running does not erase
the typed draft. Reopening the same project/plan context preserves it; selecting a genuinely
different project, plan, or saved plan input resynchronizes only after the dirty-draft guard is
resolved.

## Use the major-vessel display reference

When the external VesSAP `BL6J-no1` data package is installed, Brain3D loads the
major-vessel layer after the 25 µm atlas opens. It appears in Dorsal, Coronal, Sagittal,
Horizontal, and 3D. The status panel identifies the specimen, source, license, segment count, and
diameter threshold.

The source layer intentionally includes only nominal diameter ≥30 µm centerlines and uses a
50 µm spatial reduction. The visible-diameter slider can be adjusted from 30–250 µm without
changing the source asset or its provenance. It does not contain capillaries, does not classify
artery versus vein, and is not the current animal. Moving each slice depth filters the overlay to
that view's physical slab; 3D renders the same digest-checked paths as tubes over the brain.

This is a display reference only. No **Analyze probe**, clearance, margin, conflict, no-conflict,
or “safe” control is offered. The source does not publish numeric subject-registration,
clearing-distortion, or inter-animal uncertainty bounds, so the backend rejects analysis with
`VESSEL_ANALYSIS_UNAVAILABLE` before reading or mutating the project.

Do not interpret a gap in the overlay as absence of a vessel or use it to approve a trajectory.
For exact source files, hashes, transform validation, extraction, and limitations, see
[VesSAP Major Vessels](docs/VESSAP_MAJOR_VESSELS.md).

## Export a prefilled surgery plan

Once a valid direct v4 probe plan is current, open **Export PDF…** in the Surgery plan section. Choose
the animal record fields, one planning view or **All five views**, and the orientation of the
final legacy atlas page. The exporter uses:

- the prepared `Headplate Protocol.pdf` for the first two pages;
- the selected Dorsal, Coronal, Sagittal, Horizontal, or 3D views for the middle pages;
- the nearest plate in the supplied 132-page `MBSC_Figs_with_Layers.pdf` as the final page.

Before the first export, open **Brain3D → Settings** and choose both PDFs. Brain3D stores those
locations and reuses them for later exports; replace a location only from Settings. If a saved
network volume is disconnected, reconnect it or choose the PDF again in Settings. The export
sheet reports the saved-location status and does not ask for both files every time.

Coronal plates are matched to signed AP under the historical atlas convention
`Bregma = Interaural − 3.80 mm`. Sagittal plates are matched to `|ML|`; negative ML still appears
as animal-left and positive ML as animal-right in the generated planning page. AP, ML, and depth
from the local annotation surface are millimetres; the A↔P insertion angle is degrees; layout is
printed as `sagittal` or `90° CW from dorsal`.

The v4 export path uses the current plan's resolved surface entry and does not require a separate
implant target, target projection, or active subject calibration. The reviewed VesSAP display
layer must be present. Slice pages are rendered at the plan's coordinate without changing the
three interactive slice depths. Choosing 3D or All prepares an offscreen 3D scene automatically.
Each page records the exact vessel asset digest and the real number of reference segments in its
slice/projection; zero is reported explicitly and does not establish vessel absence or clearance.

The file has `2 + selected-view count + 1` pages. Its last page preserves the source atlas artwork
and adds a non-destructive identity/coordinate/probe summary in the unused margin; no unreviewed
trajectory geometry is drawn onto the historical plate. The app verifies page identity, size,
count, and order and performs an atomic write.

On every v4 planning page, the complete signed AP/ML plus surface-relative depth text is printed
on a dedicated monospaced line below a separately bounded subject/plan identity line. The probe
summary also records the signed A↔P angle and layout. Brain3D reopens each rendered page to verify
its expected view title and exact coordinate text, then checks the same title and coordinates at
the corresponding position in the assembled packet.

An output is marked **FINAL** only when the animal-only project is saved and clean and the
selected v4 probe plan remains current. Otherwise it is visibly marked **DRAFT**.
FINAL describes those software gates; it does not make the plan biologically validated or safe.
The exporter reads the prepared protocol PDF and consolidated atlas PDF directly with
PDFKit/Core Graphics. It does not open Word or Illustrator and requires no macOS Automation
permission. Both user-owned sources remain outside the repository and app bundle. See
[Surgery-plan export](docs/SURGERY_PLAN_EXPORT.md) for the exact page and source contract.

## Save and reopen

Save the project as `.mouseplan`. Persistence includes atlas identity, independent slice depths,
shared region selection, v4 surface-relative probe inputs and resolved surface evidence, probe
plans, and archived legacy target/calibration state. Existing legacy vessel-analysis records may
remain preserved for audit, but the current runtime cannot create or refresh them. Project
revisions are stored monotonically with checksums across save/reopen. The app rejects stale
results and source mismatches. Keep the project file and exported analyses with their recorded
provenance.

Resolve or discard an incomplete probe draft before saving. This prevents a `.mouseplan` from
silently retaining the last applied geometry while the sidebar displays different typed values.
During validation and reopen, Brain3D re-resolves every v4 entry against the loaded annotation
and reconstructs its AP/ML, surface depth, signed angle, layout, and model geometry. It also
fully reconstructs legacy planning-algorithm v2/v3 placements
from their preserved mode, entry when applicable, angles, depth, roll, probe model, source
target, and calibration, then compares every physical geometry field. A translated or
same-target alternate-angle placement cannot pass by recomputing its record hash. Historical v1
records lack enough preserved inputs for reconstruction, remain load/review only, and cannot
enter 2D/3D planning overlays, PDF planning pages, or region analysis until updated.
Vessel-clearance analysis remains unavailable for every plan version. Catalog-owned probe
snapshots must match their pinned definitions exactly. A calibration that violates AP ordering
or atlas midline/laterality—or whose skull/atlas fit, residuals, leveling angles, or QC no
longer reproduces from its stored landmarks—is also rejected for legacy v1–v3 use. Schema-8
packages advance to schema 9 without changing their stored target/calibration semantics or
inventing v4 geometry.

Population density and subject-image registration are preserved only as archived backend paths
for older work; they are not exposed in the primary UI and are not used as vessel geometry.
