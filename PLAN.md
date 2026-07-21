# Phased Implementation Plan

The application remains runnable at each completed phase. A phase is complete only after its
scope, tests, lint, type checks, smoke launch, scientific limitations, and provenance record are
current in the same frozen revision.

| Phase | Deliverable | Status in this repository | Completion gate |
| --- | --- | --- | --- |
| 0 — Investigation | Stack feasibility, Python/Swift decision, coordinate convention, atlas/data/probe sources, license inventory, ADRs | Complete | Primary-source review and ADR acceptance |
| 1 — Minimum scientific viewer | macOS shell, explicit atlas selection/acquisition, 3D brain/regions, hierarchy, orthogonal slices, linked cursor, atlas coordinates, project save/load | Implemented; final release gate recorded in `SCIENTIFIC_VALIDATION.md` | Locked tests, lint, types, smoke, real cached-atlas integration |
| 2 — Stereotaxic coordinates | User landmarks, bregma/lambda, skull leveling, calibration profiles, transform inspector, residuals/uncertainty | Not started | Independent transforms and round trips; no implicit bregma |
| 3 — Neuropixels planning | Verified probe library, target/entry/depth/angles, 3D/slice rendering, sites, intersections, multi-probe clearance | Not started | Manufacturer/source traceability and analytic/fixture geometry tests |
| 4 — Vasculature/subject registration | Licensed reference data, subject image import, landmarks, registration residuals, craniotomy, vessel distance | Not started | Coordinate/provenance review, registration validation, safety disclaimers |
| 5 — Reports and macOS distribution | Reproducible PDF/tables/images/geometry, final-plan checks, signed/notarized `.app` and installer | Not started | Clean-Mac qualification, SBOM/licenses, signing/notarization, export round trips |

Phase 0 identified a CC BY 4.0 vascular candidate and primary probe specifications, but neither
is application data yet. Later phases must review exact versions, coordinate frames, units,
integrity, and redistribution obligations before integration.
