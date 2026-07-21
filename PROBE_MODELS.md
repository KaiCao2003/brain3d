# Probe Model Source and Approval Policy

## Current implementation status

**No Neuropixels or generic implant geometry is implemented in Phase 1.** Probe model files,
probe rendering, trajectories, recording-site mapping, and multi-probe planning are Phase 3
work. Nothing in the current application should be interpreted as a probe shank, recording site,
implant trajectory, or hardware-clearance calculation.

This file records sources inspected during Phase 0 and the acceptance policy for later model
data. It intentionally contains no transcribed geometry table: a partial dimension list would
look authoritative while omitting model/revision, origin, site map, tip convention, tolerances,
and licensing information.

## Authoritative product sources inspected

| Candidate | Primary source | What the source can verify | Reuse/licensing status |
| --- | --- | --- | --- |
| Neuropixels 1.0 | [Manufacturer data sheet](https://www.neuropixels.org/_files/ugd/328966_9f784121a69f4f56bd314ffdf7f86d2b.pdf) linked from [Neuropixels support](https://www.neuropixels.org/support) | Product/order identity, shank and tip dimensions, electrode pattern, package dimensions | The PDF contains imec legal terms/disclaimer and no standalone permissive asset license was identified. Facts may be independently encoded with citation after review; the PDF, diagrams, and images are not approved for bundling. |
| Neuropixels 2.0 single- and four-shank | [Manufacturer data sheet](https://www.neuropixels.org/_files/ugd/328966_2b39661f072d405b8d284c3c73588bc6.pdf) linked from [Neuropixels support](https://www.neuropixels.org/support) | Product codes, one/four-shank variants, shank pitch and geometry, site pattern, package dimensions | Same restriction: factual verification/citation only until redistribution rights for any copied asset are established. No manufacturer PDF or figure will be bundled. |
| Neuropixels 2.0 Quad Base | [Manufacturer data sheet](https://www.neuropixels.org/_files/ugd/328966_4e39ab2e46424dc9b3efa446d286ab0f.pdf) linked from [Neuropixels support](https://www.neuropixels.org/support) | Quad-base product identity, channels/sites, shank and package specifications | Not an initial Phase 3 promise. No copied asset is approved; a distinct model ID would be required. |
| Neuropixels 1.0 scientific design | [Jun et al., Nature 2017](https://doi.org/10.1038/nature24636) | Peer-reviewed device description and terminology | Publication citation is not a license to redistribute its figures or supplemental assets. No publication asset or code is copied. |
| Neuropixels 2.0 scientific design | [Steinmetz et al., Science 2021](https://doi.org/10.1126/science.abf4588) | Peer-reviewed single-/multi-shank design context | Publication citation is not a blanket asset/CAD license. No publication asset or code is copied. |

The manufacturer support page labels technical drawings for probe caps/holders as “open source
design files,” but the page does not display a specific software/hardware license for those files.
Those drawings concern mounting hardware and are not a substitute for shank/site geometry. They
remain unapproved for distribution until the exact file and license have been reviewed and
recorded in [Third-Party Software and Data](THIRD_PARTY.md).

Neuropixels Ultra, NHP, Opto, and any later products are **not approved models**. Their existence
or a publication diagram is insufficient. Each needs an exact product/revision source, complete
geometry, coordinate origin, site map, and license review.

## Prior-art software reviewed, not reused

| Project/version | License status reviewed | Current use |
| --- | --- | --- |
| [iblatlas 1.2.0](https://github.com/int-brain-lab/iblatlas/releases/tag/1.2.0) | MIT | Coordinate/trajectory concepts only; package and its PyQt5 GUI extra are not imported. |
| [Neuropixels Trajectory Explorer v2.0.0](https://github.com/petersaj/neuropixels_trajectory_explorer/releases/tag/v2.0.0) | GPL-3.0 | Workflow prior art only; no code, geometry file, or asset copied. |
| [Pinpoint v2.0.0](https://github.com/VirtualBrainLab/Pinpoint/releases/tag/v2.0.0) | GPL-3.0 | Multi-probe workflow prior art only; no Unity code, geometry, or asset copied. |

A permissively licensed implementation can inform tests or import adapters only after its source
model is traced back to an authoritative hardware revision. A repository license alone does not
make unverified dimensions scientifically acceptable.

## Phase 3 model acceptance gate

A probe model cannot be enabled until one versioned data file records and tests all applicable
items below:

1. stable application model ID and schema version;
2. manufacturer name, exact product/order code, hardware revision, and retrieval date;
3. primary source URL, document revision/date, citation, and a recorded digest of the source
   artifact used during transcription;
4. license/terms classification for the encoded facts and every copied file or asset;
5. explicit units, local coordinate frame, origin, insertion-axis direction, and handedness;
6. shank count, length, width, thickness, tip geometry, and inter-shank spacing where applicable;
7. complete recording-site coordinates and the rule/source for active banks and references;
8. separation between implantable shank geometry and optional non-implantable base/headstage
   collision geometry;
9. independent transcription review against the primary source;
10. schema, bounds, site-count, symmetry/spacing, trajectory-transform, rendering, and round-trip
    tests with documented tolerances.

If a dimension, tolerance, site coordinate, or origin is absent or ambiguous, the model stays
disabled. It must not be estimated from a screenshot, inferred from visual proportions, copied
from an uncited community file, or filled with a “reasonable” value.

## Planned Phase 3 scope, not current functionality

Subject to the acceptance gate, Phase 3 intends to evaluate distinct versioned profiles for
Neuropixels 1.0, Neuropixels 2.0 single-shank, Neuropixels 2.0 four-shank, and an explicitly
user-defined generic linear probe. “Neuropixels 2.0” must not be a single ambiguous model name.

A custom model editor must validate every unit and dimension, preserve the original imported site
table, and label the result user-defined/unverified unless its source has completed the same
review. The application will report geometric intersections or clearances neutrally; it will not
call a trajectory safe.

Neuropixels is a product/trademark name used only to identify the cited hardware. This project is
not affiliated with or endorsed by imec or the Neuropixels consortium.
