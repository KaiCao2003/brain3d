# VesSAP External Major-vessel Data

Brain3D can display an optional derivative of the VesSAP `BL6J-no1` whole-brain skeleton and
radius volumes described by Todorov et al.,
[Nature Methods 2020](https://doi.org/10.1038/s41592-020-0792-1).

## Repository boundary

The NPZ, manifest, source volumes, transform archive, and license text are not stored in this
repository or bundled with the application. The external files retain the VesSAP
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) terms.

Install the prepared files at:

```text
<data-dir>/vasculature/vessap_bl6j1_major_vessels_50um_v1.npz
<data-dir>/vasculature/vessap_bl6j1_major_vessels_50um_v1.npz.manifest.json
```

Set `MOUSE_BRAIN_PLANNER_DATA_DIR` to override `<data-dir>`.

## Data contract

The loader expects:

| Property | Value |
| --- | --- |
| Asset SHA-256 | `9300dacf25ca57a5d23377ca0dc885e34ff0d18e8d21ef7590c6dcd156cf5db7` |
| Asset bytes | 1,853,131 |
| Atlas | `allen_mouse_25um` version `1.2` |
| Output points | 196,377 |
| Output runs | 76,622 |
| Output segments | 119,755 |
| Minimum source radius | 15 µm |
| Display grid | 50 µm |

Before returning geometry, Brain3D checks the manifest schema, source identity, transform identity,
asset digest and size, array inventory, data types, shapes, bounds, run offsets, radius threshold,
and path length.

## Coordinate mapping

The prepared data uses BrainGlobe physical `[AP,DV,ML]` micrometres. The VesSAP transform output
is mapped as:

```text
AP_um = 30 * T_y
DV_um = 30 * T_z
ML_um = 11390 - 30 * T_x
```

The ML reflection converts the source left-to-right direction to BrainGlobe ASR right-to-left.

## Runtime behavior

When both external files are available, the bridge exposes metadata and geometry for the five
views. If either file is missing or fails validation, the capability is not advertised. Vessel
clearance analysis remains unavailable.
