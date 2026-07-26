# ADR-003: Atlas and external data sources

- Status: Accepted
- Date: 2026-07-26

## Context

Brain3D needs one reproducible atlas identity and clear boundaries for third-party data. Atlas
volumes, vascular datasets, and licensed documents should not be committed to the source
repository.

## Decision

### Atlas

Use BrainGlobe AtlasAPI with the allowlisted `allen_mouse_25um` package version `1.2`.
BrainGlobe arrays use `[AP,DV,ML]` order and the package's `asr` orientation. The application
validates the package key, version, shape, resolution, orientation, metadata, and structures before
use.

Atlas files are downloaded to the application data directory and are never added to the
repository, application bundle, or project packages.

### Major-vessel display

Keep the VesSAP loader and provenance checks, but require the NPZ and manifest to be installed in
the application data directory:

```text
<data-dir>/vasculature/vessap_bl6j1_major_vessels_50um_v1.npz
<data-dir>/vasculature/vessap_bl6j1_major_vessels_50um_v1.npz.manifest.json
```

The bridge advertises the display capability only when both external files are present. The data
remains governed by CC BY-NC 4.0 and is not part of Brain3D's source-code license.

### Documents

Protocol and reference-atlas PDFs are selected by the user in Settings. Brain3D reads them from
their original locations and does not copy them into source control or the application bundle.

## Consequences

- A clean checkout contains code, tests, fixtures, and documentation but no third-party datasets
  or PDFs.
- Users control acquisition and acceptance of external terms.
- Missing optional data disables its capability without affecting atlas and probe planning.
- Source identities and digests remain explicit at data-loading boundaries.
