# Surgery-plan PDF export

## Scope and safety boundary

Brain3D exports a prefilled planning packet for **non-human animal research only**. The packet is
not a clinical document, a qualified intraoperative navigation system, or a vessel-clearance
certificate. Every coordinate, probe placement, atlas plate, protocol field, and vessel
relationship must be independently reviewed before the procedure.

The vessel layer is especially limited: it is not registered to the operative animal, and a
missing or non-intersecting displayed vessel does not establish vessel absence, clearance,
trajectory suitability, or safety.

## Export prerequisites

The exporter requires:

- an open, animal-only project with a current valid probe plan;
- for the primary v4 path, persisted AP/ML, annotation-surface, depth, signed-angle, layout, and
  source-pinned Pinpoint/Urchin reference evidence;
- the reviewed `allen_mouse_25um` v1.2 atlas identity;
- the reviewed VesSAP major-vessel layer loaded for the same atlas;
- the user-prepared, three-page `Headplate Protocol.pdf` (two protocol pages plus its atlas
  sketch placeholder);
- the user-supplied, 132-page Mouse Brain CD `MBSC_Figs_with_Layers.pdf`.

Choose both PDFs once in **Brain3D → Settings**. The app saves those locations and every export
reuses them until they are replaced in Settings. It does not assume a fixed lab-volume path. If a
saved network volume is disconnected, reconnect it or select the PDF again in Settings; the
export sheet reports the saved-location status rather than opening two file choosers every time.

## Implant, probe, and units

Primary v4 plans use:

- surface-insertion AP and ML in millimetres from the persisted Pinpoint/Urchin profile, locating
  user-facing Shank 1's exact local annotation-surface crossing rather than an array midpoint;
- AP+ anterior/AP− posterior and ML+ animal-right/ML− animal-left;
- positive depth in millimetres from Shank 1's surface crossing to its distal target;
- one sagittal insertion angle in degrees, positive A→P and negative P→A; and
- layout `sagittal`, with Shank 1 most anterior, or `90° CW from dorsal`, with Shank 1
  animal-left-most and the other NP2013 shanks extending toward animal right.

Each 3D NP2 shank uses its complete 10 mm catalogued proximal-to-distal extent. At depth `d`, the
`10 − d` mm proximal remainder can lie outside the brain. Slice overlays, annotation traversal,
and path analysis use only the implanted surface-to-tip segment.

The primary probe selector contains only Neuropixels 2.0 `NP2003` (single shank) and `NP2013`
(standard four shanks). `NP2004`/`NP2014` remain source-artifact aliases rather than additional
UI choices. The exported probe must be the current plan for the loaded atlas and persisted
surface evidence. NP1, NP2 Quad Base, and synthetic fixtures are not selectable for a new plan.

The plan's embedded probe model must exactly equal its source-pinned catalog snapshot, including
provenance, verification state, all shank/tip fields, and every ordered recording site. A
modified and self-rehashed model cannot enter a packet. Unknown custom models are retained only
on the historical v1 audit path and cannot be exported as current planning geometry.

There is no probe Apply/Create button. NP2003/NP2013 and layout choices update immediately.
Numeric AP, ML, surface depth, and angle update on Return or focus loss, never on each
keystroke. Until a valid numeric edit commits, the views and PDF remain bound to the last valid
trajectory; saving and export are blocked while incomplete text is unresolved.

Automatically prepared defaults create the first valid direct plan once planning becomes ready.
Subsequent mutations are serialized and coalesced to the newest committed edit so an older
response cannot overwrite a newer operator choice.
The draft belongs to the app-level planner session in the single main planning window, so closing
and reopening that window does not erase it. Opening another project, reconnecting, or quitting
requires the dirty draft to be resolved or explicitly discarded.

Project validation re-resolves v4 surface evidence from the loaded annotation and reconstructs
AP/ML, depth, angle, layout, and exact model geometry before export. A changed and self-rehashed
surface entry, source reference, layout, or path fails closed.

Legacy v1–v3 records remain preserved. V2/v3 validation still reconstructs their mode, entry when
applicable, angles, depth, roll, probe model, source target, and calibration. Historical v1
records remain load/review only. Schema 9 adds v4 without inventing a surface or silently
converting schema-8 target/calibration records.

The packet is marked `FINAL` only when the project has a subject, records the animal-research
acknowledgement, is saved and clean, and has a current matching v4 probe plan. A separate target
projection, active subject calibration, and geometry checkbox are not v4 prerequisites. Otherwise
the packet is visibly marked `DRAFT`. `FINAL` describes software-state agreement for the exported packet.

## Selectable planning views

The export sheet offers:

- Dorsal
- Coronal
- Sagittal
- Horizontal
- 3D
- All

`All` means one page for each of the five views, not a sixth view. For v4, coronal, sagittal, and
horizontal images are requested again at the current plan's resolved surface-entry coordinate;
export does not silently reuse the interactive viewer's current slice depth. The dorsal page uses
the captured dorsal surface, and the 3D page uses a captured offscreen SceneKit view containing
the same plan-matched probe and vessel asset. If an Allen region is selected, its exact
descendant-inclusive annotation mask is requested for every exported 2D view, and its reviewed
identity-matched region mesh is retained in 3D when one exists. An ontology-only selection with
neither voxels nor mesh retains its identity with zero 2D highlight pixels and an explicit 3D
no-geometry state. A selection change during capture fails the export instead of mixing region
identities.

## Major-vessel evidence

Every planning page is bound to the pinned VesSAP `BL6J-no1` derivative:

- one fixed, cleared, ex-vivo C57BL/6J brain;
- nominal vessel diameter at least 30 µm;
- reduced on a 50 µm grid for display; and
- capillaries and smaller vessels intentionally omitted.

This is a reference-animal layer, not vasculature from the planned animal. Pages record the
vessel asset digest prefix and the number and scope of displayed segments. A count of zero
visible intersections never proves vessel absence or clearance. Brain3D does not calculate a
safe distance, classify a trajectory as safe, or turn the reference geometry into a surgical
go/no-go decision. See [VesSAP major-vessel evidence](VESSAP_MAJOR_VESSELS.md) for the exact
derivation, hashes, license, and validation boundary.

## Historical atlas plate selection

The final page can use either a coronal or sagittal historical plate:

- Coronal matching uses the target AP coordinate. For these plates,
  `Bregma = Interaural − 3.80 mm`.
- Sagittal matching uses `|ML|`. The signed implant ML still records left (`ML−`) or right
  (`ML+`) in the planning packet.

Plate coordinates are an explicit reviewed Figure 1–132 table; Brain3D does not infer uniform
spacing. PDF page N is Figure N. Brain3D requires exactly 132 landscape-Letter pages, validates
the figure and coordinate text on every page, and selects the nearest in-range plate. The last
page preserves the historical plate and adds an identity summary. Probe trajectory geometry
remains on the preceding Brain3D planning page; the exporter does not draw an unreviewed
trajectory mark onto the atlas artwork.

## Direct PDF assembly

The exporter uses mature, platform-native PDF components rather than a custom document parser or
an unreviewed Swift PDF package:

1. Brain3D reads the prepared blank PDF and verifies two protocol pages plus one Letter-size
   atlas placeholder, with the expected protocol headings.
2. Apple PDFKit and Core Graphics preserve pages 1–2 and add the prefilled date, animal record,
   AP/ML/surface depth, signed A↔P angle, layout, and
   `DRAFT`/`FINAL` fields to the first protocol page. The overlay is flattened into the page and
   required text and page geometry are rechecked.
3. Each Brain3D planning page uses a bounded subject/plan identity line and a separate
   monospaced line containing the complete signed AP/ML and surface-depth text. The probe summary
   records the same signed angle and layout, plus the source-transcription review status.
   Brain3D reopens the rendered page and verifies its expected view title and exact coordinate
   text.
4. Brain3D captures and hashes `MBSC_Figs_with_Layers.pdf`, validates all 132 pages, and selects
   the matching historical atlas page directly from that immutable PDF capture.
5. Core Graphics redraws the selected atlas page with separate, non-overlapping rows for
   coordinates, angle/layout, source-transcription review status, and surface provenance.
   Brain3D checks the source hash before writing and verifies the output dimensions, figure
   number, complete operator text, provenance text, and source-digest stamp.
6. PDFKit assembles the two protocol pages, the selected planning-view page or pages, and the
   one atlas page. The source template's page-3 sketch is a placeholder and is replaced rather
   than emitted.
7. Core Graphics redraws every assembled page with a flattened audit stamp containing the
   export class, subject, stable plan/implant ID, project revision, plan label, protocol-template
   digest, vessel digest, v4 plan-input digest, annotation digest, bregma-source digest, and page
   number. PDFKit then verifies every stamp, page size, page count, each planning page's ordered
   view title and exact AP/ML/surface-depth text, and the final atlas identity before the packet
   is atomically written.

The user-supplied source files are never rewritten. Word, Illustrator, Apple Events automation,
and document-conversion subprocesses are not used.

## Page order

The output order is fixed:

1. protocol page 1, portrait Letter;
2. protocol page 2, portrait Letter;
3. the selected planning view, or Dorsal → Coronal → Sagittal → Horizontal → 3D for `All`,
   landscape Letter; and
4. the matched historical atlas plate, landscape Letter.

A single-view packet has four pages. An `All` packet has eight pages.

## Immutable capture and provenance

Before rendering, Brain3D freezes one export capture containing:

- project ID, revision, saved/dirty state, and animal-use acknowledgement;
- v4 plan ID plus AP/ML, resolved local surface entry, path depth, signed angle, and layout;
- the source-pinned Pinpoint/Urchin reference identity/revision/digest and annotation evidence;
- the current probe plan ID/version, model snapshot, and input SHA-256;
- Allen atlas identity and metadata SHA-256;
- the selected Allen ontology branch plus exact per-view annotation overlays and 3D mesh, when
  present;
- VesSAP specimen/provenance and derived-asset SHA-256; and
- the exact plan-centred slice frames or reconstructed 3D snapshot requested for the packet.

The protocol PDF template and selected historical atlas plate are also SHA-256 hashed. Planning pages
print shortened protocol, historical-atlas, and vessel source digests together with project
revision and coordinates; the in-memory capture retains the full identities for validation.
Brain3D rechecks the project, current v4 plan and surface evidence, selected probe, atlas, vessel
asset, PDF source hashes, and dirty state before rendering and again before writing. Export cannot
begin with an unresolved numeric probe draft. If any captured state changes, export fails instead of
mixing revisions.

## Source ownership and redistribution

The Headplate protocol PDF and Mouse Brain CD `MBSC_Figs_with_Layers.pdf` are user-supplied,
remain governed by their source-owner terms, and are not redistributed by Brain3D. They are not
committed to this repository, bundled in the app, or copied into test fixtures. A lab must have
the rights to use its input documents and to distribute any resulting packet.
