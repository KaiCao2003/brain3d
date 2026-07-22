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
landmarks are AP/ML/DV; BrainGlobe atlas landmarks are AP/DV/ML; the form labels both in µm.

Inspect residuals and QC messages, then choose **Use for planning** only when the calibration
permits planning. A failed calibration cannot project a target or create a probe. **Project to
atlas** creates a provenance-bound projection while preserving the original bregma entry.

The Allen CCF has no single official bregma transform. A project calibration is specific to its
declared measurements and assumptions; it is not supplied by the atlas.

## Create and inspect a probe plan

Choose a projected target, model, name, axial rotation, and one of exactly four placement modes:

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
values. The catalog contains:

- Neuropixels 1.0 NP1000 / `PRB_1_4_0480_1`, with all 960 sites transcribed from pinned sources;
  its status is `source-transcribed-review-pending`; and
- a synthetic one-shank/16-site software-test model.

Both require the displayed acknowledgement. The NP1 transcription has not completed an
independent full-table review.

After creating a plan, slice views show only probe geometry that intersects the current slab;
3D shows the probe envelope with the brain. **Analyze regions** performs exact atlas
voxel traversal and recording-site assignment. Use **Inspect…**, **Save CSV…**, or **Save JSON…**
for the versioned result. Export generation is read-only; the project records an `exported` audit
event only after the native client completes the atomic file write. Cancelling the save panel or a
failed write does not advance the project revision or claim an export. Both formats carry the
exact atlas identity/digest, printed coordinate convention, calibration identity/digest, source
and destination frames, and the full AP/ML/DV transform matrix with residuals.

## Vessel features are unavailable

The repository retains a diameter-≥30 µm derivative of the CC BY 4.0 LAMBADA P60_606 graph,
DOI `10.5281/zenodo.18876865`, as archived evidence only. It is not displayed in 2D, Dorsal, or
3D, and it cannot be analyzed against a probe.

Qualification found supporting AP and DV orientation evidence, but the source describes
hemisphere specimens and the exact graph has no persisted property that binds its ML coordinates
to biological hemisphere/laterality. This also leaves whole-brain coverage unqualified. The
application does not infer the sampled side and does not mirror the graph.

The backend does not advertise the reference-vessel or radius-aware-analysis capabilities. Any
request for reference metadata, geometry, or analysis returns `VESSEL_GEOMETRY_UNAVAILABLE`
without serving points. The canonical rejected report is
[`docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json`](docs/evidence/lambada_p60_606_coordinate_qualification_rejected_v1.json),
SHA-256 `0993d5a0ad6c0d62094dc395fe2bc4f284870e6e7c0b602be7df5a7da867c93a`.

Do not interpret the absence of a vessel overlay as an absence of vessels. This build produces no
vessel intersection, margin, conflict, no-conflict, or surgical-clearance result.

## Save and reopen

Save the project as `.mouseplan`. Persistence includes atlas identity, independent slice depths,
region selection, implant targets, calibrations, probe plans, current region, and archived backend
state. Existing legacy vessel-analysis records may remain preserved for audit, but the current
runtime cannot create, refresh, or interpret them. Project revisions are stored monotonically with
checksums across save/reopen. The app rejects stale results and source mismatches. Keep the project
file and exported analyses with their recorded provenance.

Population density and subject-image registration are preserved only as archived backend paths
for older work; they are not exposed in the primary UI and are not used as vessel geometry.
