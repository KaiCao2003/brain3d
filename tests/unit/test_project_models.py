"""Unit tests for bounded, validated project-domain state."""

from __future__ import annotations

from uuid import uuid4

import pytest
from tests.fixtures import make_allen_metadata_test_double

from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.project_models import (
    MAX_PROJECT_EVENTS,
    PlannerProject,
    ProjectEvent,
)
from mouse_brain_planner.domain.vessel_models import (
    DorsalRegistrationMethod,
    DorsalVascularRegistration,
    ReferenceVascularDensityProjectState,
    SubjectImageFormat,
    SubjectVascularImage,
    SubjectVascularOverlayState,
)


def _vascular_state() -> tuple[
    BrainGlobePhysicalPoint,
    SubjectVascularImage,
    DorsalVascularRegistration,
    SubjectVascularOverlayState,
    ReferenceVascularDensityProjectState,
]:
    metadata = make_allen_metadata_test_double(25)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=6600,
        dv_um=4000,
        ml_um=metadata.midline_ml_um,
    )
    image = SubjectVascularImage(
        original_name="subject.png",
        project_relative_path="images/subject.png",
        source_sha256="a" * 64,
        byte_size=1,
        image_format=SubjectImageFormat.PNG,
        width_px=8,
        height_px=8,
    )
    registration = DorsalVascularRegistration(
        image_uuid=image.image_uuid,
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        method=DorsalRegistrationMethod.SIMILARITY,
        matrix_row_major=(1, 0, 0, 0, 1, 0, 0, 0, 1),
        landmarks=(),
        residuals=(),
        rms_residual_um=0,
        max_residual_um=0,
        determinant=1,
        redundant_control_points=False,
    )
    overlay = SubjectVascularOverlayState(
        image_uuid=image.image_uuid,
        registration_uuid=registration.registration_uuid,
        visible=True,
    )
    reference = ReferenceVascularDensityProjectState(
        target_atlas_key=metadata.atlas_key,
        target_atlas_version=metadata.atlas_package_version,
        output_shape_asr=(264, 160, 228),
        template_correlation=0.995,
    )
    return anchor, image, registration, overlay, reference


def test_project_event_log_retains_only_the_newest_bounded_history() -> None:
    project = PlannerProject()

    for sequence in range(MAX_PROJECT_EVENTS + 25):
        project.touch("cursor-moved", str(sequence))

    assert len(project.event_log) == MAX_PROJECT_EVENTS
    assert project.event_log[0].details == "25"
    assert project.event_log[-1].details == str(MAX_PROJECT_EVENTS + 24)


def test_project_model_rejects_oversized_imported_event_log() -> None:
    payload = PlannerProject().model_dump()
    payload["event_log"] = [
        ProjectEvent(action="imported", details=str(sequence)).model_dump()
        for sequence in range(MAX_PROJECT_EVENTS + 1)
    ]

    with pytest.raises(ValueError, match="at most 1000 items"):
        PlannerProject.model_validate(payload)


def test_renderer_anchor_requires_matching_atlas_identity_and_bounds() -> None:
    metadata = make_allen_metadata_test_double(25)
    valid = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=6600.0,
        dv_um=4000.0,
        ml_um=metadata.midline_ml_um,
    )

    assert PlannerProject(atlas=metadata, renderer_anchor=valid).renderer_anchor == valid
    with pytest.raises(ValueError, match="renderer anchor requires atlas metadata"):
        PlannerProject(renderer_anchor=valid)
    with pytest.raises(ValueError, match="renderer anchor atlas identity"):
        PlannerProject(
            atlas=metadata,
            renderer_anchor=valid.model_copy(update={"atlas_version": "wrong"}),
        )
    with pytest.raises(ValueError, match="renderer anchor axis 2"):
        PlannerProject(
            atlas=metadata,
            renderer_anchor=valid.model_copy(update={"ml_um": metadata.extent_um[2]}),
        )


def test_any_vascular_state_requires_an_exact_project_atlas() -> None:
    _, image, _, _, reference = _vascular_state()

    with pytest.raises(ValueError, match="vascular state requires atlas metadata"):
        PlannerProject(subject_vascular_images=[image])
    with pytest.raises(ValueError, match="vascular state requires atlas metadata"):
        PlannerProject(reference_vascular_density=reference)


def test_subject_image_ids_and_case_insensitive_package_paths_are_unique() -> None:
    metadata = make_allen_metadata_test_double(25)
    anchor, image, _, _, _ = _vascular_state()

    with pytest.raises(ValueError, match="duplicate UUIDs"):
        PlannerProject(
            atlas=metadata,
            renderer_anchor=anchor,
            subject_vascular_images=[image, image],
        )
    same_path = image.model_copy(update={"image_uuid": uuid4()})
    with pytest.raises(ValueError, match="duplicate package paths"):
        PlannerProject(
            atlas=metadata,
            renderer_anchor=anchor,
            subject_vascular_images=[image, same_path],
        )


@pytest.mark.parametrize(
    "unsafe_path",
    ["images/../outside.png", "images/nested/subject.png", "images//subject.png", "images/a\n.png"],
)
def test_subject_image_package_path_is_flat_canonical_and_printable(unsafe_path: str) -> None:
    _, image, _, _, _ = _vascular_state()
    payload = image.model_dump(mode="json")
    payload["project_relative_path"] = unsafe_path

    with pytest.raises(ValueError, match="subject image path"):
        SubjectVascularImage.model_validate(payload)


def test_registration_references_identity_and_versions_are_validated() -> None:
    metadata = make_allen_metadata_test_double(25)
    anchor, image, registration, _, _ = _vascular_state()
    base = {"atlas": metadata, "renderer_anchor": anchor, "subject_vascular_images": [image]}

    with pytest.raises(ValueError, match="unknown image UUID"):
        PlannerProject(
            **base,
            dorsal_vascular_registrations=[registration.model_copy(update={"image_uuid": uuid4()})],
        )
    with pytest.raises(ValueError, match="does not match project atlas"):
        PlannerProject(
            **base,
            dorsal_vascular_registrations=[
                registration.model_copy(update={"atlas_version": "wrong"})
            ],
        )
    with pytest.raises(ValueError, match="duplicate UUIDs"):
        PlannerProject(
            **base,
            dorsal_vascular_registrations=[registration, registration],
        )
    duplicate_version = registration.model_copy(update={"registration_uuid": uuid4()})
    with pytest.raises(ValueError, match="registration version must be unique"):
        PlannerProject(
            **base,
            dorsal_vascular_registrations=[registration, duplicate_version],
        )


def test_overlay_references_registration_visibility_and_dv_bounds_are_validated() -> None:
    metadata = make_allen_metadata_test_double(25)
    anchor, image, registration, overlay, _ = _vascular_state()
    base = {
        "atlas": metadata,
        "renderer_anchor": anchor,
        "subject_vascular_images": [image],
        "dorsal_vascular_registrations": [registration],
    }

    with pytest.raises(ValueError, match="requires a registration"):
        PlannerProject(
            **base,
            subject_vascular_overlays=[overlay.model_copy(update={"registration_uuid": None})],
        )
    with pytest.raises(ValueError, match="unknown registration UUID"):
        PlannerProject(
            **base,
            subject_vascular_overlays=[overlay.model_copy(update={"registration_uuid": uuid4()})],
        )
    with pytest.raises(ValueError, match="outside atlas bounds"):
        PlannerProject(
            **base,
            subject_vascular_overlays=[
                overlay.model_copy(update={"dorsal_plane_dv_um": metadata.extent_um[1]})
            ],
        )
    with pytest.raises(ValueError, match="duplicate image UUIDs"):
        PlannerProject(**base, subject_vascular_overlays=[overlay, overlay])


def test_reference_density_identity_and_laterality_warning_are_fail_closed() -> None:
    metadata = make_allen_metadata_test_double(25)
    anchor, _, registration, _, reference = _vascular_state()

    with pytest.raises(ValueError, match="reference vascular density atlas identity"):
        PlannerProject(
            atlas=metadata,
            renderer_anchor=anchor,
            reference_vascular_density=reference.model_copy(
                update={"target_atlas_version": "wrong"}
            ),
        )
    with pytest.raises(ValueError, match="output extent"):
        PlannerProject(
            atlas=metadata,
            renderer_anchor=anchor,
            reference_vascular_density=reference.model_copy(
                update={"output_shape_asr": (263, 160, 228)}
            ),
        )
    with pytest.raises(ValueError, match="requires positive opacity"):
        ReferenceVascularDensityProjectState.model_validate(
            {
                **reference.model_dump(mode="python"),
                "visible": True,
                "opacity": 0.0,
            }
        )
    payload = registration.model_dump(mode="json")
    payload["laterality_warning"] = "laterality assumed"
    with pytest.raises(ValueError, match="Image laterality is unverified"):
        DorsalVascularRegistration.model_validate(payload)
