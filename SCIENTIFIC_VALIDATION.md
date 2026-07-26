# Verification Scope

Brain3D's automated checks cover software behavior and data-contract consistency.

## Covered by tests

- Allen atlas identity, orientation, shape, and coordinate conversions.
- AP/ML surface resolution, probe placement, and trajectory reconstruction.
- Probe catalog dimensions, shank/site layout, and persistence round trips.
- Slice, region, SceneKit, and bridge protocol behavior.
- Project checksums, migrations, backup recovery, and stale-state rejection.
- Optional VesSAP manifest, digest, array, and coordinate checks when external data is supplied.

## Study-specific verification

A research workflow should independently verify:

- subject registration and landmark acquisition;
- probe/hardware geometry used in the experiment;
- planned versus achieved trajectories;
- tissue deformation and manipulator effects;
- vascular coverage and uncertainty; and
- the exact application, atlas, and data versions used for analysis.

The test suite can be run with:

```bash
uv run --frozen pytest -q
swift test --package-path native/Brain3D --no-parallel
```

Technical source records are maintained in [Probe Models](PROBE_MODELS.md),
[Coordinate Systems](COORDINATE_SYSTEMS.md), and
[VesSAP external data](docs/VESSAP_MAJOR_VESSELS.md).
