# Third-party Software and Data

Third-party datasets, atlas volumes, probe PDFs, protocol PDFs, and atlas artwork are not stored in
this repository. They are downloaded by the user or selected from user-owned locations.

## Runtime dependencies

| Package | Version | License | Purpose |
| --- | ---: | --- | --- |
| BrainGlobe AtlasAPI | 2.3.1 | BSD-3-Clause | Atlas discovery, download, and access |
| nibabel | 5.4.2 | MIT | NIfTI access |
| NumPy | 2.5.1 | BSD-3-Clause | Arrays and numerical operations |
| Pillow | 12.3.0 | MIT-CMU | Image processing |
| platformdirs | 4.11.0 | MIT | Application data paths |
| Pydantic | 2.13.4 | MIT | Validated models |
| scikit-image | 0.26.0 | BSD-3-Clause | Image registration |
| SciPy | 1.18.0 | BSD-3-Clause | Numerical operations |
| tifffile | 2026.7.14 | BSD-3-Clause | TIFF loading |

The exact dependency graph is recorded in `uv.lock`. Release builds include a generated SBOM and
license inventory.

## External data and documents

| Item | Terms | Use |
| --- | --- | --- |
| Allen Mouse CCF via BrainGlobe `allen_mouse_25um` | [Allen Institute Terms of Use](https://alleninstitute.org/legal/terms-of-use) | Downloaded on demand to the user's application data directory |
| VesSAP BL6J-no1 vasculature | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | Optional external major-vessel display data; not stored in the repository or application bundle |
| Kim et al. vascular-density data | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Optional external compatibility workflow |
| Headplate protocol PDF | Source-owner terms | User-selected input for surgery-plan export |
| Mouse Brain reference-atlas PDF | Source-owner terms | User-selected input for surgery-plan export |

VesSAP source and paper: [VesSAP data record](https://www.discotechnologies.org/VesSAP/) and
[Todorov et al., Nature Methods 2020](https://doi.org/10.1038/s41592-020-0792-1).

## Cited specifications and prior art

Neuropixels geometry is transcribed from cited imec, ProbeTable, and SpikeGLX sources; the source
documents are not copied into the repository. The planning coordinate profile cites the Virtual
Brain Lab Urchin/Pinpoint implementation. Exact source identities are listed in
[Probe Models](PROBE_MODELS.md) and [Coordinate Systems](COORDINATE_SYSTEMS.md).

Third-party software and data remain governed by their respective licenses and terms.
