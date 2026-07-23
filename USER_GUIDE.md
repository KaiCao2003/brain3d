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
  previous/next buttons, or wheel to move; drag pans and pinch zooms.
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
**Store unprojected site** preserves those exact inputs without inventing an atlas point.

## Calibrate and project

Open **Calibrations…** and create a subject calibration from measured skull-frame metadata,
exactly four matched landmarks (bregma, lambda, left skull, right skull), laterality confirmation,
the DV reference, declared QC limits/source, and either a rigid or similarity atlas fit. Skull
landmarks are AP/ML/DV; BrainGlobe atlas landmarks are AP/DV/ML; the form accepts both in mm and
converts them to the typed internal micrometre protocol. Calibration residuals and QC limits remain
explicitly labelled in µm.

Inspect residuals and QC messages, then choose **Use for planning** only when the calibration
permits planning. A failed calibration cannot project a target or create a probe. **Project to
atlas** creates a provenance-bound projection while preserving the original bregma entry.

The Allen CCF has no single official bregma transform. A project calibration is specific to its
declared measurements and assumptions; it is not supplied by the atlas.

## Create and inspect a probe plan

Probe creation becomes available only after the project has a subject ID, a stored target, and an
active calibration whose QC status permits planning. The Create area shows the first unmet
prerequisite instead of leaving a disabled button unexplained.

Choose a target, model, name, axial rotation, and one of exactly four placement modes:

AP, ML, DV/depth, and insertion-depth fields are entered in **millimetres**. Azimuth,
elevation, and axial rotation are entered in **degrees**. The app converts insertion depth to
micrometres only inside the typed geometry protocol.

- **Entry + target** accepts an editable bregma-relative entry and the selected target, then
  derives direction and insertion depth from those two points.
- **Entry + angles + depth** accepts an editable bregma-relative entry plus source-stereotaxic
  azimuth, elevation, and depth. The complete physical pose crosses the same rigid/similarity
  calibration as the entry; affine transforms are rejected because they would shear the probe.
- **Target + angles + depth** accepts the selected target plus atlas-frame azimuth, elevation, and
  depth, then derives the entry directly in atlas space.
- **Stereotaxic target** uses the selected calibrated target with manipulator azimuth, elevation,
  and depth under the explicit stereotaxic contract.

Only fields belonging to the selected mode are submitted. Selecting an existing plan restores
its exact mode and inputs for editing; changing modes cannot silently reuse hidden entry or angle
values. The production catalog contains exactly:

- NP2 single shank `NP2003` / `NP2004`: 1,280 physical sites and 384 simultaneous channels;
- NP2 standard four shank `NP2013` / `NP2014`: 5,120 physical sites and 384 simultaneous
  channels.

Quad Base, NP1, and the synthetic fixture are archived compatibility/test definitions and do not
appear in the new-plan selector. Both supported entries have status
`source-transcribed-review-pending` and require the displayed acknowledgement. No supported NP2
transcription has completed an independent full-table review. Brain3D represents all physical
sites, not the active acquisition configuration; it does not yet import an IMRO/electrode
selection.

After creating a plan, slice views show only probe geometry that intersects the current slab;
3D shows the probe envelope with the brain. **Analyze regions** performs exact atlas
voxel traversal and recording-site assignment. Use **Inspect…**, **Save CSV…**, or **Save JSON…**
for the versioned result. Export generation is read-only; the project records an `exported` audit
event only after the native client completes the atomic file write. Cancelling the save panel or a
failed write does not advance the project revision or claim an export. Both formats carry the
exact atlas identity/digest, printed coordinate convention, calibration identity/digest, source
and destination frames, and the full AP/ML/DV transform matrix with residuals.

## Use the major-vessel display reference

Brain3D automatically loads the pinned VesSAP `BL6J-no1` major-vessel layer after the reviewed
25 µm atlas opens. It appears in Dorsal, Coronal, Sagittal, Horizontal, and 3D. The status panel
identifies the specimen, source, CC BY-NC 4.0 license, segment count, and diameter threshold.

The layer intentionally includes only nominal diameter ≥30 µm centerlines and uses a 50 µm
display reduction. It does not contain capillaries, does not classify artery versus vein, and is
not the current animal. Moving each slice depth filters the overlay to that view's physical slab;
3D renders the same digest-checked paths as tubes over the brain.

This is a display reference only. No **Analyze probe**, clearance, margin, conflict, no-conflict,
or “safe” control is offered. The source does not publish numeric subject-registration,
clearing-distortion, or inter-animal uncertainty bounds, so the backend rejects analysis with
`VESSEL_ANALYSIS_UNAVAILABLE` before reading or mutating the project.

Do not interpret a gap in the overlay as absence of a vessel or use it to approve a trajectory.
For exact source files, hashes, transform validation, extraction, and limitations, see
[VesSAP Major Vessels](docs/VESSAP_MAJOR_VESSELS.md). The older LAMBADA P60_606 derivative
remains archived and rejected; it is not mixed with or mirrored into this layer.

## Save and reopen

Save the project as `.mouseplan`. Persistence includes atlas identity, independent slice depths,
region selection, implant targets, calibrations, probe plans, current region, and archived backend
state. Existing legacy vessel-analysis records may remain preserved for audit, but the current
runtime cannot create or refresh them. Project revisions are stored monotonically with
checksums across save/reopen. The app rejects stale results and source mismatches. Keep the project
file and exported analyses with their recorded provenance.

Population density and subject-image registration are preserved only as archived backend paths
for older work; they are not exposed in the primary UI and are not used as vessel geometry.
