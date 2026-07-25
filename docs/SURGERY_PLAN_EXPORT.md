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

- an open animal-research project and a stored implant target;
- a current target projection produced with the active, planning-permitted calibration;
- the reviewed `allen_mouse_25um` v1.2 atlas identity;
- the reviewed VesSAP major-vessel layer loaded for the same atlas;
- the user-prepared, three-page `Headplate Protocol.pdf` (two protocol pages plus its atlas
  sketch placeholder);
- the user-supplied, 132-page Mouse Brain CD `MBSC_Figs_with_Layers.pdf`.

Choose both PDFs once in **Brain3D → Settings**. The app saves those locations and every export
reuses them until they are replaced in Settings. It does not assume a fixed lab-volume path. If a
saved network volume is disconnected, reconnect it or select the PDF again in Settings; the
export sheet reports the saved-location status rather than opening two file choosers every time.

## Target, probe, and units

Targets use stereotaxic coordinates from bregma:

- AP, ML, and DV/depth are in millimetres;
- negative AP is posterior/back;
- negative ML is left;
- negative DV is deep/ventral; and
- azimuth, elevation, and axial rotation are in degrees.

The production probe selector contains only Neuropixels 2.0 single-shank
(`NP2003` / `NP2004`) and standard four-shank (`NP2013` / `NP2014`) models. The exported probe
must be the current plan for the selected target, projection, calibration, and atlas. NP1, NP2
Quad Base, and synthetic fixtures are not selectable for a new production plan.

The plan's embedded probe model must exactly equal its source-pinned catalog snapshot, including
provenance, verification state, all shank/tip fields, and every ordered recording site. A
modified and self-rehashed model cannot enter a packet. Unknown custom models are retained only
on the historical v1 audit path and cannot be exported as current planning geometry.

Changing fields for an existing probe does not silently change the applied trajectory. Until
the user selects **Apply changes**, the views and PDF remain bound to the last applied values.
The user may instead select **Revert**. Saving and export are blocked while such edits are
unapplied.

Automatically prepared new-probe defaults are clean. Once the user changes the NPX2 model or
enters planning values, the uncreated draft must be completed with **Create plan** or cleared
with **Discard draft** before leaving the current project. An uncreated draft cannot be exported.
The draft belongs to the app-level planner session in the single main planning window, so closing
and reopening that window does not erase it. Opening another project, reconnecting, or quitting
requires the dirty draft to be resolved or explicitly discarded.

Project validation fully reconstructs planning-algorithm v2/v3 placements from their preserved
mode, entry when applicable, angles, depth, roll, probe model, source target, and calibration,
then compares every physical geometry field. A translated placement, same-target alternate-angle
trajectory, or forged projection digest is rejected even if the record hash is recomputed.
Both persisted calibration fits are also rerun from their landmark inputs; AP ordering,
midline/laterality, matrices, correspondences, residuals, leveling angles, and skull QC must
reproduce before projection or export.
Historical v1 records lack sufficient preserved inputs, remain load/review only, and must be
recomputed/updated before they can enter 2D/3D planning overlays, PDF planning pages, or region
analysis. Vessel-clearance analysis remains unavailable for every plan version. Schema 8 makes
this a versioned persistence contract; schema-7 migration preserves geometry exactly and never
guesses a repair.

The packet is marked `FINAL` only when the project has a subject, records the animal-research
acknowledgement, is saved and clean, has a calibration permitted for final export, and has a
current matching probe plan. Otherwise it is visibly marked `DRAFT`.

## Selectable planning views

The export sheet offers:

- Dorsal
- Coronal
- Sagittal
- Horizontal
- 3D
- All

`All` means one page for each of the five views, not a sixth view. Coronal, sagittal, and
horizontal images are requested again at the selected target's containing atlas voxel; export
does not silently reuse the interactive viewer's current slice depth. The dorsal page uses the
captured dorsal surface, and the 3D page uses a captured offscreen SceneKit view containing the
same target-matched probe and vessel asset.

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
- Sagittal matching uses `|ML|`. The signed target ML still records left (`ML−`) or right
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
   AP/ML/DV, angle, and
   `DRAFT`/`FINAL` fields to the first protocol page. The overlay is flattened into the page and
   required text and page geometry are rechecked.
3. Each Brain3D planning page uses a bounded subject/target identity line and a separate
   monospaced line containing the complete signed AP/ML/DV text. Brain3D reopens the rendered
   page and verifies its expected view title and exact coordinate text.
4. Brain3D captures and hashes `MBSC_Figs_with_Layers.pdf`, validates all 132 pages, and selects
   the matching historical atlas page directly from that immutable PDF capture.
5. Core Graphics redraws the selected atlas page with a non-destructive identity and coordinate
   summary. Brain3D checks the source hash before writing and verifies the output dimensions,
   figure number, coordinate text, and source-digest stamp.
6. PDFKit assembles the two protocol pages, the selected planning-view page or pages, and the
   one atlas page. The source template's page-3 sketch is a placeholder and is replaced rather
   than emitted.
7. Core Graphics redraws every assembled page with a flattened audit stamp containing the
   export class, subject, stable target ID, project revision, target label, protocol-template
   digest, vessel digest, and page number. PDFKit then verifies every stamp, page size, page
   count, each planning page's ordered view title and exact AP/ML/DV text, and the final atlas
   identity before the packet is atomically written.

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
- target ID and AP/ML/DV values;
- target projection identity and projection SHA-256;
- active calibration ID, version, calibration SHA-256, and atlas-metadata SHA-256;
- the target-matched probe plan ID/version, input SHA-256, and projection/calibration bindings;
- Allen atlas identity and metadata SHA-256;
- VesSAP specimen/provenance and derived-asset SHA-256; and
- the exact target-centred slice frames or reconstructed 3D snapshot requested for the packet.

The protocol PDF template and selected historical atlas plate are also SHA-256 hashed. Planning pages
print shortened protocol, historical-atlas, and vessel source digests together with project
revision and coordinates; the in-memory capture retains the full identities for validation.
Brain3D rechecks the project, target, projection, calibration, selected probe, atlas, vessel
asset, PDF source hashes, and dirty state before rendering and again before writing. Export
cannot begin with an unapplied probe draft. If any captured state changes, export fails instead
of mixing revisions.

## Source ownership and redistribution

The Headplate protocol PDF and Mouse Brain CD `MBSC_Figs_with_Layers.pdf` are user-supplied,
remain governed by their source-owner terms, and are not redistributed by Brain3D. They are not
committed to this repository, bundled in the app, or copied into test fixtures. A lab must have
the rights to use its input documents and to distribute any resulting packet.
