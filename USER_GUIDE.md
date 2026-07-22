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

Create or open a `.mouseplan`, then open/download the reviewed 25 µm atlas when prompted. The
10 µm atlas is not offered; existing 10 µm cache data is left untouched.

## Navigate the atlas

The mode bar is exactly `Dorsal / Coronal / Sagittal / Horizontal / 3D`, with one full-size view:

- **Dorsal** shows the atlas surface and the depth-collapsed LAMBADA reference-vessel projection.
- **Coronal**, **Sagittal**, and **Horizontal** each keep an independent depth. Use the slider,
  previous/next buttons, or wheel to move; drag pans and pinch zooms.
- **3D** shows a SceneKit brain mesh, planned probe envelopes, and radius-bearing reference-vessel
  tubes. Drag/orbit and zoom use native camera control; **Reset Camera** restores the overview.

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

Choose a projected target, model, name, azimuth, elevation, insertion depth, and axial rotation.
The catalog contains:

- Neuropixels 1.0 NP1000 / `PRB_1_4_0480_1`, with all 960 sites transcribed from pinned sources;
  its status is `source-transcribed-review-pending`; and
- a synthetic one-shank/16-site software-test model.

Both require the displayed acknowledgement. The NP1 transcription has not completed an
independent full-table review.

After creating a plan, slice views show only probe geometry that intersects the current slab;
3D shows the probe envelope with the brain and vessels. **Analyze regions** performs exact atlas
voxel traversal and recording-site assignment. Use **Inspect…**, **Save CSV…**, or **Save JSON…**
for the versioned result.

## Use the reference major-vessel layer

The displayed graph is the CC BY 4.0 LAMBADA P60_606 reference, DOI
`10.5281/zenodo.18876865`. It includes maximal in-bounds runs with point radius ≥15 µm
(diameter ≥30 µm). It is overlaid on intersecting 2D slices, Dorsal, and 3D.

It is one fixed cleared specimen, not the current animal. Pial and choroidal vessels were removed
by the source workflow; smaller vessels are filtered; artery/vein identity is unavailable; and
registration error, tissue deformation, biological variation, and missing vessels are not
bounded. Dorsal collapses depth and must not be interpreted as a surface-only subject map.

To analyze a selected probe, enter the lab-defined required margin and registration uncertainty,
then acknowledge both:

1. the lab-defined risk inputs were reviewed; and
2. this is a single reference with missing vessels.

The V2 calculation measures the conservative probe envelope against tapered vessel surfaces and
reports intersections, margin/uncertainty violations, or a bounded zero-conflict result. That
result is worded exactly:

> No conflict detected within the loaded geometry and stated uncertainty assumptions.

It does not imply the absence of omitted or subject-specific vessels.

## Save and reopen

Save the project as `.mouseplan`. Persistence includes atlas identity, independent slice depths,
region selection, implant targets, calibrations, probe plans, and archived backend state, with a
project revision and checksums. The app rejects stale results and source mismatches. Keep the
project file and exported analyses with their recorded provenance.

Population density and subject-image registration are preserved only as archived backend paths
for older work; they are not exposed in the primary UI and are not used for major-vessel analysis.
