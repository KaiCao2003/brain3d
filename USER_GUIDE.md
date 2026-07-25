# User Guide

Brain3D is a native SwiftUI + SceneKit workspace backed by a Python scientific service. It is
restricted to mouse animal research and accepts only BrainGlobe `allen_mouse_25um` v1.2 during
this testing phase.

> **Non-human, non-clinical use only.** This development build is not a qualified navigation or
> veterinary device. Independently review all coordinates, laterality, calibration inputs, probe
> geometry, anatomy, vessel limitations, and procedure decisions.

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

Click a slice or the 3D brain to replace the compact region acronym/name display. Clicking does
not change a slice depth. There is no focus mode, crosshair, 2×2 layout, or capillary layer.

Use the common Allen region browser/search to reach the complete 840-structure ontology, including
thalamus, cerebellum, brainstem, and other non-cortical structures. Selecting a search or tree
result replaces the same region selection used by all five modes; switching modes preserves it
and does not couple the three independent slice depths. Only the selected region mesh is loaded
for 3D highlighting.

## Enter an implant site

Enter millimetres from bregma in named `[AP, ML, DV]` fields:

| Axis | Positive | Negative |
| --- | --- | --- |
| AP | anterior / forward | posterior / back |
| ML | right | left |
| DV | dorsal / up | deep / ventral |

`AP -1.25`, `ML -0.70`, `DV -2.40` means 1.25 mm posterior, 0.70 mm left, and 2.40 mm deep.
**Add site** preserves those exact inputs. If a passing atlas mapping is active, Brain3D also
projects the new site; otherwise the stored bregma coordinates remain unprojected until you
explicitly project them.

The Dorsal, Coronal, and Horizontal canvases label animal right on the screen-left edge and
animal left on the screen-right edge. Thus `ML < 0` appears on the screen-right `L` side, while
`AP < 0` appears toward `P`. **Show** keeps the same projected implant site visible when switching
among Dorsal, Coronal, Sagittal, Horizontal, and 3D.

## Calibrate and project

Open **Set up atlas mapping…** and create a subject calibration from measured skull-frame metadata,
exactly four matched landmarks (bregma, lambda, left skull, right skull), laterality confirmation,
the DV reference, declared QC limits/source, and either a rigid or similarity atlas fit. Skull
landmarks are AP/ML/DV; BrainGlobe atlas landmarks are AP/DV/ML; the form accepts both in mm and
converts them to the typed internal micrometre protocol. Calibration residuals and QC limits remain
explicitly labelled in µm.

Brain3D rejects a calibration unless atlas bregma and lambda lie on the atlas midsagittal plane
within half one ML voxel and the named right/left skull landmarks straddle that plane on their
respective sides, each by at least half one ML voxel. Together with the required ordering of
atlas bregma anterior to lambda, these gates preserve the contract that `AP < 0` projects
posterior and `ML < 0` projects to animal-left, which is the screen-right `L` side in Dorsal,
Coronal, and Horizontal views.

On create, validation, and reopen, Brain3D also reruns the skull calibration and atlas fit from
the stored landmark inputs. The persisted transform matrices, landmark correspondences and
residuals, leveling angles, and skull QC must reproduce; changing and rehashing a derived
transform or residual does not make it acceptable.

Inspect residuals and QC messages, then choose **Use for planning** only when the calibration
permits planning. A failed calibration cannot project a target or create a probe. **Project to
atlas** creates a provenance-bound projection while preserving the original bregma entry.

The Allen CCF has no single official bregma transform. A project calibration is specific to its
declared measurements and assumptions; it is not supplied by the atlas.

## Create a probe plan

Probe creation becomes available only after the project has a subject ID, a stored target, and an
active calibration whose QC status permits planning. The Create area shows the first unmet
prerequisite instead of leaving a disabled button unexplained.

Choose an implant site, NPX2 probe, plan name, azimuth, elevation, insertion depth, and roll.
Insertion depth is entered in **millimetres**; azimuth, elevation, and roll are entered in
**degrees**. Brain3D converts depth to micrometres only inside the typed geometry protocol. The
production catalog contains exactly:

- NP2 single shank `NP2003` / `NP2004`: 1,280 physical sites and 384 simultaneous channels;
- NP2 standard four shank `NP2013` / `NP2014`: 5,120 physical sites and 384 simultaneous
  channels.

Quad Base, NP1, and the synthetic fixture are archived compatibility/test definitions and do not
appear in the new-plan selector. Both supported entries have status
`source-transcribed-review-pending` and require the displayed acknowledgement. No supported NP2
transcription has completed an independent full-table review. Brain3D represents all physical
sites, not the active acquisition configuration; it does not yet import an IMRO/electrode
selection.

Persisted catalog models are checked against the exact source-pinned definition, including every
shank dimension and offset, tip field, ordered recording site, verification field, and source
record. Editing one of those values and recomputing its surrounding hashes is rejected. An
unknown custom model can remain only in a historical v1 audit record and cannot enter current
planning geometry or analysis.

After creating a plan, slice views show only probe geometry that intersects the current slab;
3D shows the probe envelope with the brain. Older project packages may retain archived
multi-mode probe records, and Brain3D preserves their inputs for compatibility, but the new-plan
UI does not expose those extra placement modes or region-export controls.

When editing an existing plan, typed values are not applied silently. Brain3D shows
**Unapplied probe edits**; the brain views and PDF continue to use the last applied values until
you choose **Apply changes**. Choose **Revert** to restore those values instead. While edits are
unapplied, switching probe plans, saving, and PDF export are disabled, and opening another
project, reconnecting, or quitting requires discard confirmation.

For a new probe, the prepared model/name/target defaults are not treated as work. Once you change
the model or enter planning values, Brain3D shows **Uncreated probe draft**. Choose **Create
plan** to apply it or **Discard draft** to return to clean defaults; opening, reconnecting, and
quitting otherwise require discard confirmation.

Brain3D has one main planning window. The probe draft belongs to the planner session rather than
to the sidebar, so closing and reopening that window while the app remains running does not erase
the typed draft. Reopening the same project/plan context preserves it; selecting a genuinely
different project, plan, or saved plan input resynchronizes only after the dirty-draft guard is
resolved.

## Use the major-vessel display reference

Brain3D automatically loads the pinned VesSAP `BL6J-no1` major-vessel layer after the reviewed
25 µm atlas opens. It appears in Dorsal, Coronal, Sagittal, Horizontal, and 3D. The status panel
identifies the specimen, source, CC BY-NC 4.0 license, segment count, and diameter threshold.

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
[VesSAP Major Vessels](docs/VESSAP_MAJOR_VESSELS.md). The older LAMBADA P60_606 derivative
remains archived and rejected; it is not mixed with or mirrored into this layer.

## Export a prefilled surgery plan

After storing a target, open **Export PDF…** in the Surgery plan section. Choose the animal
record fields, one planning view or **All five views**, and the orientation of the final legacy
atlas page. The exporter uses:

- the prepared `Headplate Protocol.pdf` for the first two pages;
- the selected Dorsal, Coronal, Sagittal, Horizontal, or 3D views for the middle pages;
- the nearest plate in the supplied 132-page `MBSC_Figs_with_Layers.pdf` as the final page.

Before the first export, open **Brain3D → Settings** and choose both PDFs. Brain3D stores those
locations and reuses them for later exports; replace a location only from Settings. If a saved
network volume is disconnected, reconnect it or choose the PDF again in Settings. The export
sheet reports the saved-location status and does not ask for both files every time.

Coronal plates are matched to signed AP under the historical atlas convention
`Bregma = Interaural − 3.80 mm`. Sagittal plates are matched to `|ML|`; negative ML still appears
as left and positive ML as right in the generated planning page. AP, ML, DV/depth, and insertion
depth are millimetres. Azimuth, elevation, and roll are degrees.

The export button remains unavailable until the selected target has a current active-calibration
projection and the reviewed VesSAP display layer is present. Slice pages are rendered at that
projected target voxel without changing the three interactive slice depths. Choosing 3D or All
prepares an offscreen 3D scene automatically. Each page records the exact vessel asset digest and
the real number of reference segments in its slice/projection; zero is reported explicitly and
does not establish vessel absence or clearance.

The file has `2 + selected-view count + 1` pages. Its last page preserves the source atlas artwork
and adds a non-destructive identity/coordinate/probe summary in the unused margin; no unreviewed
trajectory geometry is drawn onto the historical plate. The app verifies page identity, size,
count, and order and performs an atomic write.

On every planning page, the complete signed AP/ML/DV text is printed on a dedicated monospaced
line below a separately bounded subject/target identity line. Brain3D reopens each rendered page
to verify its expected view title and exact coordinate text, then checks the same title and
coordinates at the corresponding position in the assembled packet.

An output is marked **FINAL** only when the saved project, target projection, selected current
probe plan, and final-export calibration all agree. Otherwise it is visibly marked **DRAFT**.
FINAL describes those software gates; it does not make the plan biologically validated or safe.
The exporter reads the prepared protocol PDF and consolidated atlas PDF directly with
PDFKit/Core Graphics. It does not open Word or Illustrator and requires no macOS Automation
permission. Both user-owned sources remain outside the repository and app bundle. See
[Surgery-plan export](docs/SURGERY_PLAN_EXPORT.md) for the exact page and source contract.

## Save and reopen

Save the project as `.mouseplan`. Persistence includes atlas identity, independent slice depths,
region selection, implant targets, calibrations, probe plans, current region, and archived backend
state. Existing legacy vessel-analysis records may remain preserved for audit, but the current
runtime cannot create or refresh them. Project revisions are stored monotonically with
checksums across save/reopen. The app rejects stale results and source mismatches. Keep the project
file and exported analyses with their recorded provenance.

Apply or revert an existing probe draft before saving. This prevents a `.mouseplan` from
silently retaining the last applied geometry while the sidebar displays different typed values.
During validation and reopen, Brain3D fully reconstructs planning-algorithm v2/v3 placements
from their preserved mode, entry when applicable, angles, depth, roll, probe model, source
target, and calibration, then compares every physical geometry field. A translated or
same-target alternate-angle placement cannot pass by recomputing its record hash. Historical v1
records lack enough preserved inputs for reconstruction, remain load/review only, and cannot
enter 2D/3D planning overlays, PDF planning pages, or region analysis until updated.
Vessel-clearance analysis remains unavailable for every plan version. Catalog-owned probe
snapshots must match their pinned definitions exactly. A calibration that violates AP ordering
or atlas midline/laterality—or whose skull/atlas fit, residuals, leveling angles, or QC no
longer reproduces from its stored landmarks—is also rejected. Schema-7 packages are copied
forward to schema 8 without inferred geometry or silent repair.

Population density and subject-image registration are preserved only as archived backend paths
for older work; they are not exposed in the primary UI and are not used as vessel geometry.
