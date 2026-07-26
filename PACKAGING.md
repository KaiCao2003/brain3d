# Packaging and Distribution

## Development bundle

```bash
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
```

The development bundle uses the repository Python environment.

## Standalone Apple Silicon bundle

```bash
native/Brain3D/Scripts/build-release-app.sh
```

The release builder freezes the locked Python service, assembles `Brain3D.app`, creates
`Brain3D-macOS-arm64.zip`, verifies Mach-O architecture and deployment targets, checks signatures,
and performs an isolated bridge/app smoke test. Set `OUTPUT_DIR` to choose another destination.

When a Developer ID Application identity is available, the builder uses hardened-runtime signing.
Otherwise it produces an ad-hoc-signed build. Notarization can be performed after the signed build
is produced.

## External inputs

The application bundle does not include:

- BrainGlobe atlas packages;
- vascular datasets;
- surgery protocol or reference-atlas PDFs;
- user `.mouseplan` projects; or
- subject data.

Runtime data is loaded from application-owned directories or paths selected in Settings.
Dependency notices, build metadata, and the generated SBOM are stored under
`Contents/Resources/Release`.
