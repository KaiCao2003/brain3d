# Development

Mouse Brain Surgery Planner uses a native SwiftUI shell and a Python 3.12 scientific service.
BrainGlobe, NumPy/SciPy, persistence, registration, and source verification stay behind a typed
NDJSON bridge; PySide6/PyVista/VTK remain diagnostic/reference tooling. Scientific math must not
move into SwiftUI view callbacks.

Read these first:

- [ADR-001: Technology stack](docs/ADR-001-technology-stack.md)
- [ADR-002: Coordinate conventions](docs/ADR-002-coordinate-conventions.md)
- [ADR-003: Atlas and data sources](docs/ADR-003-atlas-and-data-sources.md)
- [Scientific Validation](SCIENTIFIC_VALIDATION.md)
- [Third-Party Software and Data](THIRD_PARTY.md)

## Supported development environment

- Apple Silicon (`arm64`)
- macOS 14 or later
- CPython `>=3.12,<3.13`
- the committed `uv.lock`

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then from the repository
root run:

```bash
uv python install 3.12
uv lock --check
uv sync --frozen --all-groups
```

Do not install a second Qt binding. Application code imports PySide6 directly and sets
`QT_API=pyside6` before QtPy/PyVistaQt discovery.

## Quality gate

Run the complete hybrid gate from the repository root:

```bash
uv lock --check
uv sync --frozen --all-groups
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
uv run --frozen pytest -q
QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true \
  uv run --frozen mouse-brain-planner --smoke-test --no-download
swift test --package-path native/Brain3D
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
```

These commands respectively verify the lock/project relationship, reproduce the environment,
check formatting/lint, run strict type checking, run Python unit/GUI/smoke tests, exercise the
diagnostic Qt event loop, test the Swift package, build the native app, and verify its development
signature. A green gate establishes software-contract consistency only. It is not evidence of
stereotaxic, vessel-clearance, or surgical accuracy.

Useful focused runs are:

```bash
uv run --frozen pytest tests/unit/test_atlas_space.py -q
uv run --frozen pytest tests/unit/test_brainglobe_adapter.py -q
uv run --frozen pytest tests/unit/test_slice_renderer.py -q
uv run --frozen pytest tests/gui -q
uv run --frozen pytest tests/smoke -q
```

The normal suite uses synthetic volumes, mesh geometry, test paths, and a BrainGlobe fake so it
does not require a large atlas or network access. The `atlas_download` marker is reserved for
future opt-in real-data integration tests; do not treat an empty marker run as validation.

## Run the supported application and CLI

```bash
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner validate /absolute/path/Plan.mouseplan
```

`uv run --frozen mouse-brain-planner --no-download` starts the superseded diagnostic Qt shell;
use it only when a test explicitly targets that path.

Downloading a real atlas is an explicit, networked, disk- and memory-consuming integration
operation. Review [Atlas Data](ATLAS_DATA.md) and the data terms first. Do not add cached atlas
content to Git.

## Architecture

```text
native/Brain3D/               SwiftUI shell, typed bridge client, native tests/build
src/mouse_brain_planner/
  app.py, cli.py, paths.py
  atlas/          BrainGlobe 2.3.1 adapter and normalized records
  bridge/         versioned scientific/project service
  coordinates/    typed atlas-space validation and transforms
  domain/         Pydantic scientific/project models
  gui/            diagnostic Qt shell, viewers, and workers
  persistence/    versioned project migration and atomic I/O
  rendering/      PyVista scene controller and vectorized slices
  vasculature/    pinned population density and subject-image workflows
tests/
  fixtures/       visibly synthetic reference fixtures
  unit/           scientific/service/persistence contract tests
  gui/            Qt widget and interaction tests
  smoke/          bounded process/event-loop tests
docs/             accepted architecture decisions
```

The dependency directions are intentional:

- domain/coordinate/persistence code must remain usable without Qt;
- SwiftUI consumes typed bridge results and must not duplicate scientific transforms;
- GUI handlers call scientific services rather than containing coordinate formulas;
- only the BrainGlobe adapter imports and owns upstream atlas objects;
- only the rendering boundary converts BrainGlobe ASR coordinates to VTK/PyVista world space;
- worker threads return data/progress through Qt signals and never mutate live VTK/Qt objects;
- project files store named frames and units, never raw screen coordinates or opaque Qt objects.

## Coordinate-change checklist

Any change that touches axes, units, indexing, laterality, transforms, or picking must:

1. name source and destination frames and units in its public model/API;
2. preserve BrainGlobe ASR `[AP,DV,ML]` semantics unless an explicit transform says otherwise;
3. validate finite values and half-open atlas bounds before array/BrainGlobe lookup;
4. distinguish continuous voxel coordinates, discrete indices, index anchors, and voxel centers;
5. handle the determinant-`-1` ASR-to-world reflection, winding, normals, and inverse picking;
6. add asymmetric laterality and forward/inverse round-trip tests;
7. update [Coordinate Systems](COORDINATE_SYSTEMS.md) and
   [Scientific Validation](SCIENTIFIC_VALIDATION.md) with exact evidence and tolerance;
8. avoid describing numeric floating-point tolerance as biological accuracy.

There is no official Allen CCF bregma. A bregma estimate cannot be introduced as an unnamed
constant or hidden UI offset.

## Atlas adapter rules

`configure_brainglobe_environment()` must run before the first
`brainglobe_atlasapi` import because stable 2.3.1 reads configuration during import. The adapter
is pinned to exactly 2.3.1 and deliberately uses its stable `reference` property and constructor
contract. Unversioned BrainGlobe documentation may describe prerelease 3.x APIs; inspect the
tagged 2.3.1 source before changing the boundary.

Do not:

- download or scrape atlas files outside BrainGlobe when AtlasAPI supplies them;
- bypass atlas identity/orientation/shape validation;
- copy a full atlas array just to display one slice;
- eagerly instantiate every region mesh;
- claim that the local `metadata.json` SHA-256 authenticates the complete atlas package;
- combine a reference, annotation, hierarchy, or mesh from different package identities.

## Persistence changes

`.mouseplan` is a directory package with canonical JSON and checksums. Current schema changes
must be represented by deterministic migrations in `persistence/migrations.py`; never reinterpret
old coordinate fields in place. Loads accept only bounded, regular, non-symlink package members
resolved inside the package. New callers use `load_project_with_provenance()` and must treat any
direct or recovered `.mouseplan.bak` source as read-only (`writable_path is None`) so the UI
requires Save As. Save uses a sibling temporary directory, directory-entry fsync where supported,
staged backup rotation, atomic replacement, and exact `.mouseplan.bak` recovery.

For every new persisted scientific object, include a schema version, named frame, units,
provenance, and enough identity to reject an incompatible reload. Tests must cover exact model
round trip, tampering, invalid values, migration, and backup recovery.

## Dependency and license changes

Runtime pins live in `pyproject.toml`; the full resolved graph lives in `uv.lock`. For a deliberate
dependency change:

1. inspect the package's official API, Python/macOS/arm64 support, and license;
2. change the direct pin;
3. run `uv lock` deliberately, then review the full diff;
4. run the complete quality gate and relevant real integration checks;
5. update [Third-Party Software and Data](THIRD_PARTY.md) and any affected ADR;
6. reassess PyInstaller hooks, binary architecture, notices, and data redistribution.

Do not update the lockfile incidentally while running tests; use `--frozen` for verification.

## Documentation and completion standard

Phase work is complete only when implementation, tests, lint, type checking, smoke launch,
scientific limitation documentation, and third-party records agree at one commit. Record what
was tested with real data separately from fakes. Never convert “the unit tests pass” into an
anatomical, subject-specific, clinical, or surgical-accuracy claim.

Packaging work continues in [Packaging](PACKAGING.md); known gaps are tracked in
[Known Limitations](KNOWN_LIMITATIONS.md).
