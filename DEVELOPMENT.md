# Development

Brain3D has one supported product path: a SwiftUI + SceneKit macOS application and a Python 3.12
scientific service connected by typed NDJSON. Scientific transforms, atlas access, calibration,
probe/region analysis, vessel qualification, and persistence stay in Python; Swift owns
presentation, input, accessibility, native file handling, and schema-checked SceneKit display
payloads. No vessel-analysis capability is currently exposed.

Start with [Architecture](docs/ARCHITECTURE.md), [Code Audit](docs/CODE_AUDIT.md),
[ADR-005](docs/ADR-005-independent-slice-viewer.md), and
[Scientific Validation](SCIENTIFIC_VALIDATION.md).

## Environment

- Apple Silicon (`arm64`)
- macOS 14 or later
- CPython `>=3.12,<3.13`
- Swift 6-compatible toolchain
- committed `uv.lock`

```bash
uv python install 3.12
uv lock --check
uv sync --frozen --group dev
```

The default dependency graph deliberately excludes PySide6, PyVista, PyVistaQt, and VTK. Do not
reintroduce a second GUI or renderer into the base environment.

## Quality gate

```bash
uv lock --check
uv sync --frozen --group dev
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --no-incremental
uv run --frozen pytest -q
.venv/bin/python scripts/verify_minimal_runtime.py
swift test --package-path native/Brain3D
native/Brain3D/Scripts/build-app.sh
codesign --verify --deep --strict native/Brain3D/build/Brain3D.app
```

The minimal verifier checks that Qt/VTK modules are absent and exchanges real `hello` and
`shutdown` frames through `mouse-brain-planner bridge`. A green gate establishes engineering
consistency, not stereotaxic, vascular-clearance, usability, or surgical accuracy.

Useful focused runs:

```bash
uv run --frozen pytest tests/unit/test_atlas_space.py -q
uv run --frozen pytest tests/unit/test_brainglobe_adapter.py -q
uv run --frozen pytest tests/unit/test_slice_renderer.py -q
uv run --frozen pytest tests/integration/test_bridge_stdio.py -q
swift test --package-path native/Brain3D
```

The normal Python suite uses synthetic volumes and local fakes. The real density-archive and
real-atlas checks remain explicit opt-in tests because their external data are not committed.

## Run the product path

```bash
native/Brain3D/Scripts/build-app.sh
open native/Brain3D/build/Brain3D.app
uv run --frozen mouse-brain-planner atlas list
uv run --frozen mouse-brain-planner atlas download allen_mouse_25um
uv run --frozen mouse-brain-planner validate-project /absolute/path/Plan.mouseplan
```

`mouse-brain-planner` without a subcommand prints help. `mouse-brain-planner bridge` is intended
for the native process boundary and integration diagnostics.

## Source layout

```text
native/Brain3D/               SwiftUI shell, typed client, native tests/build
  Sources/Brain3DScene/       SceneKit brain/probe rendering; archived vessel primitives
src/mouse_brain_planner/
  atlas/                      BrainGlobe 2.3.1 boundary
  bridge/                     versioned service and handlers
  coordinates/                named frames, order conversion, transforms
  domain/                     Pydantic scientific/project models
  persistence/                deterministic migrations and atomic packages
  rendering/                  raster slices and dorsal projection
  probes/                     source-traceable NP1 and synthetic test catalog
  surgery/                    product-reachable probe/measurement geometry
  analysis/                   region traversal plus archived vessel-analysis algorithms
  vasculature/                archived LAMBADA evidence and qualification workflows
tests/                        headless unit/contract/integration tests
docs/                         audit, architecture, validation, and ADRs
```

The old Qt/PyVista/VTK application was removed after the audit in
[Legacy Removal](docs/LEGACY_REMOVAL.md). Its last complete snapshot is Git commit `51fe26d`.

## Dependency direction

- Swift never reimplements coordinate transforms or scientific classification.
- The bridge imports no macOS UI framework and must run headlessly.
- Only the BrainGlobe adapter owns upstream atlas objects.
- All API coordinates name their frame, order, units, origin, directions, atlas identity, and
  transform/calibration identity.
- Project files store model state and immutable data references, never UI objects or complete
  atlas/vessel volumes.
- The rejected LAMBADA derivative, archived population density, and archived 2D subject evidence
  remain separate types and workflows. None is a subject-vessel layer; the LAMBADA geometry and
  analysis endpoints fail closed with `VESSEL_GEOMETRY_UNAVAILABLE`.

## Coordinate-change checklist

Any change involving axes, units, indexing, laterality, transforms, picking, or projection must:

1. name the source and destination frames and units;
2. use centralized BrainGlobe `[AP,DV,ML]` ↔ domain `[AP,ML,DV]` conversion;
3. validate finite values and half-open atlas bounds;
4. distinguish continuous voxel coordinates, discrete indices, corner anchors, and centers;
5. add asymmetric laterality and forward/inverse golden tests;
6. reject missing or failed calibration rather than treating atlas origin as bregma; and
7. update coordinate/validation documentation with exact evidence and tolerances.

## Bridge-change checklist

- Preserve strict envelope and exact-parameter validation.
- Reject bool where a number is expected, plus NaN and infinity.
- Use stable error codes and include recoverability/suggested action in protocol v2 errors.
- Every mutation checks the expected project revision and returns the new revision.
- Long work runs off the UI thread and stale results cannot overwrite current state.
- Add Python contract tests, matching Swift Codable tests, and a production handler/capability
  inventory assertion.
- Do not send full atlas volumes or platform-specific index objects across NDJSON.

## Review discipline

Before committing, inspect `git diff --check`, run the relevant focused tests, then run the full
gate in proportion to the change. Never weaken frame/provenance validation to make a test pass.
Update [Code Audit](docs/CODE_AUDIT.md) when a previously orphaned module becomes product-reachable.
