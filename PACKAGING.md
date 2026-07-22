# Packaging and Distribution

The repository currently creates an ad-hoc-signed **development** `.app`. It is not a standalone
release: the executable still discovers Python and the bridge from the source checkout.

```bash
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
open native/Brain3D/build/Brain3D.app
```

`Scripts/build-app.sh` builds the Swift executable, creates the bundle layout, installs the
reviewed `Info.plist`, and applies an ad-hoc signature. It does not bundle `.venv`, Python, atlas
data, or project files. The archived LAMBADA derivative currently resolves from the repository's
Python package beside the source checkout; it is not copied into the development `.app` by this
script and the runtime gate never loads or serves it.

## Current release blockers

- deterministic Python 3.12 runtime/backend bundling is not implemented;
- backend discovery still depends on a development checkout;
- Developer ID signing, hardened runtime, entitlements, notarization, and stapling are absent;
- no clean-account/clean-Mac qualification has been completed;
- the build has no SBOM or assembled third-party license bundle; and
- the implemented workflow remains unqualified for animal procedures.

The removed Qt/PyVista/VTK stack is not a packaging fallback and is not part of the lockfile.

## Intended distribution shape

```text
Brain3D.app/
  Contents/
    MacOS/Brain3D                 native SwiftUI executable
    Resources/                   reviewed UI resources, notices, qualification evidence
    Frameworks/ or Resources/    deterministic Python runtime and scientific service
```

Atlas archives, the optional archived population-density source, subject images, original vessel
graphs, and `.mouseplan` projects remain outside the signed bundle. The P60_606 derivative is not
a reviewed application asset: its hemisphere/laterality and whole-brain qualification is
rejected. A build may retain its manifest, attribution, and canonical rejection report as
evidence, but must not package or advertise it as runtime vessel geometry. Any future vessel
source requires a new qualification and release decision. The app records immutable source
identities and manages user-owned caches.

## Release process still to implement

1. Select and document a deterministic Python embedding strategy that preserves Python 3.12 and
   the locked wheels without adding a second GUI stack.
2. Build the backend from a clean checkout and verify the minimal runtime script inside the
   candidate bundle.
3. Generate an SBOM and license/notice inventory from the exact bundled artifacts.
4. Sign every nested executable/library with the intended Developer ID and reviewed entitlements.
5. Sign the outer bundle, enable the hardened runtime, notarize, staple, and verify offline.
6. Test Finder launch, bridge lifecycle, atlas download/open, save/reopen, update/replacement,
   crash recovery, and uninstall behavior on a clean supported Mac/account.
7. Repeat the complete scientific and usability qualification on the immutable release artifact.

Example verification commands after a future signed build exists:

```bash
codesign --verify --deep --strict --verbose=2 Brain3D.app
spctl --assess --type execute --verbose=4 Brain3D.app
xcrun stapler validate Brain3D.app
```

Passing signing/notarization checks establishes code-distribution integrity only. It does not
establish coordinate, anatomy, vessel, probe, or surgical accuracy.
