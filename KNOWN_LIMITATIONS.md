# Known Limitations

## Atlas and coordinates

- Brain3D currently supports BrainGlobe `allen_mouse_25um` package `1.2`.
- Atlas sampling resolution is separate from stereotaxic targeting accuracy.
- The Allen CCF is a population reference; direct AP/ML planning uses the documented
  Pinpoint/Urchin reference profile.
- Region labels and meshes follow the installed atlas package.

## Probe planning

- The primary workflow supports NP2003 and NP2013.
- Probe geometry is source-transcribed and should be checked against the hardware used in a study.
- Planning does not model probe bending, tissue deformation, brain shift, manipulator backlash,
  or headstage collisions.

## Vascular overlay

- VesSAP data is optional and installed outside the repository.
- The reference represents one cleared specimen and omits vessels below the configured diameter
  threshold.
- The overlay is a display layer; the application does not expose vessel-clearance analysis.

## Export

- PDF export requires user-selected protocol and reference-atlas documents.
- Historical atlas-page matching is coordinate based and does not register the page to an
  individual subject.

## Platform

- The native application targets Apple Silicon and macOS 14 or later.
- Development builds use the repository Python environment; standalone builds use the release
  script.
