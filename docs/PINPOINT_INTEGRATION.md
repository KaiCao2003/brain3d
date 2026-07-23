# Pinpoint interoperability decision

## Decision

Pinpoint is the interaction and workflow reference for Brain3D, not an embedded surgical state
engine.

Brain3D directly uses its existing BrainGlobe/Allen CCF service for ontology records, annotation
queries, meshes, coordinates, and slice state. It does not copy Pinpoint source or assets. The
native SwiftUI/SceneKit client consumes the complete reviewed `allen_mouse_25um` v1.2 ontology,
keeps one selected region across all five views, and loads only the selected region mesh.

Embedding the hosted Pinpoint WebGL application as the authoritative viewer is **NO-GO** for the
current build. This is an engineering decision, not a criticism of Pinpoint.

## Official behavior reviewed

The official [Pinpoint overview](https://www.braininitiative.org/toolmakers/resources/pinpoint/)
and [basic tutorial](https://virtualbrainlab.org/pinpoint/tutorials/tutorial_basics.html) describe
the intended workflow: interactive Allen CCF models, region search/highlight, multiple probe
trajectories, and AP/ML/DV/depth plus angular controls. Those behaviors are the product reference.

The official [API tutorial](https://virtualbrainlab.org/pinpoint/tutorials/tutorial_api.html)
documents desktop acquisition-system integration and explicitly excludes browser operation. The
official [Pinpoint repository](https://github.com/VirtualBrainLab/Pinpoint) is a Unity application
licensed GPL-3.0.

## Why the hosted WebGL page is not integrated

The published WebGL build has no versioned, supported bidirectional interface for:

- exact probe model identity and geometry;
- AP/ML/DV/depth units and coordinate-frame identity;
- calibration and transform provenance;
- slice depth, camera, and region-selection synchronization;
- VesSAP vessel geometry; or
- deterministic project import/export round trips.

The deployed Unity page can technically be shown inside a web view, but that does not make it an
integrated component. It would be a remotely mutable, opaque canvas whose probe, atlas transform,
camera, and selected region cannot be proven to match the Brain3D project. In particular, a
vessel overlay rendered by SceneKit could not share its exact camera and transform with an
uncontrolled Unity canvas. That fails the core surgical-planning state contract.

Pinpoint's repository contains internal WebGL and saved-probe mechanisms, but they are not a
public compatibility API. Brain3D therefore does not depend on undocumented globals, private URL
payloads, or a forked Unity build.

## Why source-level reuse is not a small hybrid

Pinpoint and its Unity atlas stack are GPL-3.0 projects. Brain3D's original source is currently
all-rights-reserved. Copying, linking, modifying, or distributing the Unity implementation would
require a deliberate architecture, distribution, and license decision; it is not equivalent to
adding a Swift package. No Pinpoint code, Unity project, model, or asset is included here.

## Native full-ontology path

The existing backend is the integration boundary:

1. BrainGlobe provides all normalized Allen structures for the pinned atlas.
2. `atlas.regions` pages the complete ontology; `atlas.search` searches acronym and name.
3. Point and ray picks resolve the same ontology identity used by search.
4. `atlas.mesh` lazily returns the selected structure's reviewed mesh.
5. Swift keeps one selected region while Dorsal, Coronal, Sagittal, Horizontal, and 3D retain
   their own navigation state.

The reviewed local atlas contains 840 structure records and 839 mesh files. Structure `RSPd4`
(`545`) has no mesh file and no annotation voxels in this 25 µm package; it remains searchable
and is never replaced with fabricated geometry.

This path is deterministic, testable, and shares the same atlas identity and coordinates as
probes and vessels. It implements the requested Allen/Pinpoint-style behavior without creating a
second scientific state engine.

## Future compatibility gate

A future direct Pinpoint integration may be reconsidered only if an official, versioned interface
supports explicit model IDs, units, frames/transforms, atlas identity, region/camera state,
round-trip persistence, and error reporting. It must also pass NP2, coordinate, vessel-overlay,
offline, and license/distribution review. Until then, Pinpoint may be linked as a reference tool,
but not presented as synchronized with a Brain3D surgical plan.
