"""Project serialization, atomic save, and recovery tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import ValidationError
from tests.fixtures.atlas_factory import make_allen_metadata_test_double

from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.implant_site_models import UnprojectedBregmaTarget
from mouse_brain_planner.domain.project_models import (
    MAX_SUBJECT_VASCULAR_IMAGES,
    PlannerProject,
    RegionDisplayState,
    ViewerSliceDepths,
)
from mouse_brain_planner.domain.vessel_models import (
    DorsalRegistrationMethod,
    DorsalVascularLandmark,
    DorsalVascularRegistration,
    LandmarkResidual,
    ReferenceVascularDensityProjectState,
    SubjectImageFormat,
    SubjectVascularImage,
    SubjectVascularOverlayState,
    VascularLandmarkKind,
)
from mouse_brain_planner.persistence import project_io as project_io_module
from mouse_brain_planner.persistence.project_io import (
    ATLAS_FILENAME,
    CHECKSUMMED_FILENAMES,
    CHECKSUMS_FILENAME,
    MAX_PROJECT_JSON_BYTES,
    PROJECT_FILENAME,
    PROJECT_MEMBER_MAX_BYTES,
    REGIONS_FILENAME,
    VASCULATURE_FILENAME,
    ProjectIntegrityError,
    ProjectRecoveryError,
    load_project,
    load_project_with_provenance,
    normalize_project_path,
    save_project,
    validate_project,
)
from mouse_brain_planner.vasculature.subject_image import import_subject_vascular_image


def _vascular_project_and_source(
    tmp_path: Path,
    *,
    title: str = "Vascular round trip",
) -> tuple[PlannerProject, Path, bytes]:
    metadata = make_allen_metadata_test_double(25)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=6612.5,
        dv_um=4012.5,
        ml_um=5712.5,
    )
    source = tmp_path / "asset-source"
    images = source / "images"
    images.mkdir(parents=True)
    image_path = images / "subject.png"
    Image.new("RGB", (8, 8), color=(24, 80, 120)).save(image_path, format="PNG")
    image_bytes = image_path.read_bytes()
    image = SubjectVascularImage(
        original_name="animal-dorsal.png",
        project_relative_path="images/subject.png",
        source_sha256=hashlib.sha256(image_bytes).hexdigest(),
        byte_size=len(image_bytes),
        image_format=SubjectImageFormat.PNG,
        width_px=8,
        height_px=8,
    )
    landmark_one = DorsalVascularLandmark(
        label="bregma",
        kind=VascularLandmarkKind.BREGMA,
        image_column_px=1,
        image_row_px=1,
        atlas_ap_um=110,
        atlas_ml_um=210,
    )
    landmark_two = DorsalVascularLandmark(
        label="vessel bifurcation",
        kind=VascularLandmarkKind.VESSEL_BIFURCATION,
        image_column_px=6,
        image_row_px=1,
        atlas_ap_um=160,
        atlas_ml_um=210,
    )
    registration = DorsalVascularRegistration(
        image_uuid=image.image_uuid,
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        method=DorsalRegistrationMethod.SIMILARITY,
        matrix_row_major=(10, 0, 100, 0, 10, 200, 0, 0, 1),
        landmarks=(landmark_one, landmark_two),
        residuals=(
            LandmarkResidual(
                landmark_uuid=landmark_one.landmark_uuid,
                ap_error_um=0,
                ml_error_um=0,
                radial_error_um=0,
            ),
            LandmarkResidual(
                landmark_uuid=landmark_two.landmark_uuid,
                ap_error_um=0,
                ml_error_um=0,
                radial_error_um=0,
            ),
        ),
        rms_residual_um=0,
        max_residual_um=0,
        determinant=100,
        redundant_control_points=False,
        laterality_confirmed_by_user=True,
    )
    overlay = SubjectVascularOverlayState(
        image_uuid=image.image_uuid,
        registration_uuid=registration.registration_uuid,
        visible=True,
        dorsal_plane_dv_um=100,
    )
    reference = ReferenceVascularDensityProjectState(
        target_atlas_key=metadata.atlas_key,
        target_atlas_version=metadata.atlas_package_version,
        output_shape_asr=(264, 160, 228),
        template_correlation=0.995,
        visible=True,
    )
    project = PlannerProject(
        title=title,
        atlas=metadata,
        renderer_anchor=anchor,
        subject_vascular_images=[image],
        dorsal_vascular_registrations=[registration],
        subject_vascular_overlays=[overlay],
        reference_vascular_density=reference,
    )
    return project, source, image_bytes


def test_project_round_trip_has_no_numeric_or_identity_drift(tmp_path: Path) -> None:
    project = PlannerProject(title="Round trip", subject_id="mouse-001")
    project.touch("created-for-test", "reproducible event")

    saved = save_project(project, tmp_path / "round-trip")
    loaded = load_project(saved)

    assert saved.name == "round-trip.mouseplan"
    assert loaded.model_dump(mode="json") == project.model_dump(mode="json")
    assert (saved / CHECKSUMS_FILENAME).is_file()


def test_current_schema_round_trip_preserves_state_above_retracted_model_limits(
    tmp_path: Path,
) -> None:
    """Do not narrow the current schema while package members can hold the state."""

    metadata = make_allen_metadata_test_double(25)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=12.5,
        dv_um=12.5,
        ml_um=12.5,
    )
    project = PlannerProject(
        atlas=metadata,
        renderer_anchor=anchor,
        user_notes="n" * 64_001,
        region_display=[RegionDisplayState(structure_id=index + 1) for index in range(4_097)],
    )

    saved = save_project(project, tmp_path / "current-schema-large-state.mouseplan")
    loaded = load_project(saved, recover_backup=False)

    assert (saved / PROJECT_FILENAME).stat().st_size < MAX_PROJECT_JSON_BYTES
    assert (saved / REGIONS_FILENAME).stat().st_size < PROJECT_MEMBER_MAX_BYTES[REGIONS_FILENAME]
    assert loaded.schema_version == 7
    assert loaded.user_notes == project.user_notes
    assert loaded.region_display == project.region_display


def test_checksummed_package_rejects_unknown_nested_atlas_field(tmp_path: Path) -> None:
    """A valid checksum must not let a future/misspelled nested field disappear."""

    metadata = make_allen_metadata_test_double(25)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=6612.5,
        dv_um=4012.5,
        ml_um=5712.5,
    )
    saved = save_project(
        PlannerProject(atlas=metadata, renderer_anchor=anchor),
        tmp_path / "unknown-nested-field.mouseplan",
    )
    atlas_path = saved / ATLAS_FILENAME
    payload = json.loads(atlas_path.read_text(encoding="utf-8"))
    payload["axes"][0]["misspelled_direction"] = "must not be discarded"
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    atlas_path.write_bytes(encoded)
    checksums_path = saved / CHECKSUMS_FILENAME
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[ATLAS_FILENAME] = hashlib.sha256(encoded).hexdigest()
    checksums_path.write_text(
        json.dumps(checksums, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_project(saved, recover_backup=False)


def test_vascular_state_and_exact_image_bytes_round_trip_with_checksum_coverage(
    tmp_path: Path,
) -> None:
    project, source, image_bytes = _vascular_project_and_source(tmp_path)

    saved = save_project(
        project,
        tmp_path / "vascular.mouseplan",
        asset_source_package=source,
    )
    loaded = load_project(saved, recover_backup=False)
    checksums = json.loads((saved / CHECKSUMS_FILENAME).read_text(encoding="utf-8"))
    image = project.subject_vascular_images[0]

    assert loaded.model_dump(mode="json") == project.model_dump(mode="json")
    assert (saved / VASCULATURE_FILENAME).is_file()
    assert (saved / image.project_relative_path).read_bytes() == image_bytes
    assert set(checksums) == {
        PROJECT_FILENAME,
        ATLAS_FILENAME,
        REGIONS_FILENAME,
        VASCULATURE_FILENAME,
        image.project_relative_path,
    }
    assert checksums[image.project_relative_path] == image.source_sha256


def test_maximum_subject_image_collection_fits_the_bounded_checksum_manifest(
    tmp_path: Path,
) -> None:
    project, source, image_bytes = _vascular_project_and_source(tmp_path)
    first = project.subject_vascular_images[0]
    images = [first]
    for index in range(1, MAX_SUBJECT_VASCULAR_IMAGES):
        relative = f"images/subject-{index:03d}.png"
        (source / relative).write_bytes(image_bytes)
        images.append(
            first.model_copy(
                update={
                    "image_uuid": uuid4(),
                    "project_relative_path": relative,
                }
            )
        )
    expanded = project.model_copy(update={"subject_vascular_images": images})

    saved = save_project(
        expanded,
        tmp_path / "maximum-images.mouseplan",
        asset_source_package=source,
    )
    checksums = json.loads((saved / CHECKSUMS_FILENAME).read_text(encoding="utf-8"))

    assert len(load_project(saved, recover_backup=False).subject_vascular_images) == (
        MAX_SUBJECT_VASCULAR_IMAGES
    )
    assert len(checksums) == len(CHECKSUMMED_FILENAMES) + MAX_SUBJECT_VASCULAR_IMAGES


def test_new_vascular_save_without_asset_source_fails_closed(tmp_path: Path) -> None:
    project, _, _ = _vascular_project_and_source(tmp_path)
    destination = tmp_path / "missing-source.mouseplan"

    with pytest.raises(ProjectIntegrityError, match="asset_source_package"):
        save_project(project, destination)

    assert not destination.exists()


def test_first_save_infers_image_import_staging_destination_without_byte_changes(
    tmp_path: Path,
) -> None:
    source_image = tmp_path / "dorsal.png"
    Image.new("RGB", (11, 7), color=(80, 20, 10)).save(source_image, format="PNG")
    original = source_image.read_bytes()
    destination = tmp_path / "import-staging.mouseplan"
    image = import_subject_vascular_image(source_image, package_root=destination)
    metadata = make_allen_metadata_test_double(25)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=6612.5,
        dv_um=4012.5,
        ml_um=5712.5,
    )
    project = PlannerProject(
        atlas=metadata,
        renderer_anchor=anchor,
        subject_vascular_images=[image],
    )

    saved = save_project(project, destination)

    assert (saved / image.project_relative_path).read_bytes() == original
    assert load_project(saved, recover_backup=False).subject_vascular_images == [image]


def test_vascular_save_rejects_missing_or_tampered_source_asset(tmp_path: Path) -> None:
    project, source, image_bytes = _vascular_project_and_source(tmp_path)
    image_path = source / project.subject_vascular_images[0].project_relative_path
    image_path.unlink()
    with pytest.raises(ProjectIntegrityError, match="does not exist"):
        save_project(
            project,
            tmp_path / "missing.mouseplan",
            asset_source_package=source,
        )

    image_path.write_bytes(bytes([image_bytes[0] ^ 0x01]) + image_bytes[1:])
    with pytest.raises(ProjectIntegrityError, match="checksum mismatch"):
        save_project(
            project,
            tmp_path / "tampered.mouseplan",
            asset_source_package=source,
        )


def test_save_as_requires_source_context_and_preserves_subject_image_bytes(tmp_path: Path) -> None:
    project, source, image_bytes = _vascular_project_and_source(tmp_path)
    first = save_project(
        project,
        tmp_path / "first.mouseplan",
        asset_source_package=source,
    )
    loaded = load_project_with_provenance(first)
    second = tmp_path / "second.mouseplan"

    with pytest.raises(ProjectIntegrityError, match="asset_source_package"):
        save_project(loaded.project, second)
    saved_as = save_project(
        loaded.project,
        second,
        asset_source_package=loaded.source_path,
    )

    relative = project.subject_vascular_images[0].project_relative_path
    assert (saved_as / relative).read_bytes() == image_bytes
    assert load_project(saved_as, recover_backup=False).model_dump(mode="json") == (
        project.model_dump(mode="json")
    )


def test_load_rejects_missing_tampered_or_symlinked_subject_image(tmp_path: Path) -> None:
    project, source, image_bytes = _vascular_project_and_source(tmp_path)
    relative = project.subject_vascular_images[0].project_relative_path

    missing = save_project(
        project,
        tmp_path / "missing-load.mouseplan",
        asset_source_package=source,
    )
    (missing / relative).unlink()
    with pytest.raises(ProjectIntegrityError, match="does not exist"):
        load_project(missing, recover_backup=False)

    tampered = save_project(
        project,
        tmp_path / "tampered-load.mouseplan",
        asset_source_package=source,
    )
    (tampered / relative).write_bytes(bytes([image_bytes[0] ^ 0x01]) + image_bytes[1:])
    with pytest.raises(ProjectIntegrityError, match="checksum mismatch"):
        load_project(tampered, recover_backup=False)

    symlinked = save_project(
        project,
        tmp_path / "symlinked-load.mouseplan",
        asset_source_package=source,
    )
    member = symlinked / relative
    outside = tmp_path / "outside-subject.png"
    outside.write_bytes(member.read_bytes())
    member.unlink()
    member.symlink_to(outside)
    with pytest.raises(ProjectIntegrityError, match="regular file"):
        load_project(symlinked, recover_backup=False)


def test_vasculature_member_and_image_checksum_tampering_fail_closed(tmp_path: Path) -> None:
    project, source, _ = _vascular_project_and_source(tmp_path)
    path = save_project(
        project,
        tmp_path / "vascular-tamper.mouseplan",
        asset_source_package=source,
    )
    vascular_payload = json.loads((path / VASCULATURE_FILENAME).read_text(encoding="utf-8"))
    vascular_payload["subject_vascular_overlays"][0]["opacity"] = 0.1
    (path / VASCULATURE_FILENAME).write_text(json.dumps(vascular_payload), encoding="utf-8")
    with pytest.raises(ProjectIntegrityError, match=r"checksum mismatch for vasculature\.json"):
        load_project(path, recover_backup=False)

    path = save_project(
        project,
        tmp_path / "asset-checksum-tamper.mouseplan",
        asset_source_package=source,
    )
    checksums = json.loads((path / CHECKSUMS_FILENAME).read_text(encoding="utf-8"))
    relative = project.subject_vascular_images[0].project_relative_path
    checksums[relative] = "0" * 64
    (path / CHECKSUMS_FILENAME).write_text(json.dumps(checksums), encoding="utf-8")
    with pytest.raises(ProjectIntegrityError, match=f"checksum mismatch for {relative}"):
        load_project(path, recover_backup=False)


def test_vasculature_path_traversal_is_rejected_before_asset_access(tmp_path: Path) -> None:
    project, source, _ = _vascular_project_and_source(tmp_path)
    path = save_project(
        project,
        tmp_path / "path-traversal.mouseplan",
        asset_source_package=source,
    )
    vascular_path = path / VASCULATURE_FILENAME
    payload = json.loads(vascular_path.read_text(encoding="utf-8"))
    payload["subject_vascular_images"][0]["project_relative_path"] = "images/../outside.png"
    vascular_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    checksums_path = path / CHECKSUMS_FILENAME
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[VASCULATURE_FILENAME] = hashlib.sha256(vascular_path.read_bytes()).hexdigest()
    checksums_path.write_text(json.dumps(checksums), encoding="utf-8")

    with pytest.raises(ValidationError, match="traverse"):
        load_project(path, recover_backup=False)


def test_vascular_backup_and_recovered_save_as_preserve_assets(tmp_path: Path) -> None:
    project, source, image_bytes = _vascular_project_and_source(tmp_path, title="Version one")
    path = save_project(
        project,
        tmp_path / "vascular-backup.mouseplan",
        asset_source_package=source,
    )
    replacement = project.model_copy(update={"title": "Version two"})
    save_project(replacement, path)
    backup = path.with_name(path.name + ".bak")
    relative = project.subject_vascular_images[0].project_relative_path

    assert load_project(backup, recover_backup=False).title == "Version one"
    assert (backup / relative).read_bytes() == image_bytes
    (path / PROJECT_FILENAME).write_text("{}\n", encoding="utf-8")
    recovered = load_project_with_provenance(path)
    assert recovered.source_path == backup

    saved_as = save_project(
        recovered.project,
        tmp_path / "recovered-save-as.mouseplan",
        asset_source_package=recovered.source_path,
    )
    assert (saved_as / relative).read_bytes() == image_bytes
    assert load_project(saved_as, recover_backup=False).title == "Version one"


def test_schema_one_package_load_migrates_midline_and_renderer_anchor(tmp_path: Path) -> None:
    metadata = make_allen_metadata_test_double(25)
    anchor = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=6612.5,
        dv_um=4012.5,
        ml_um=5712.5,
    )
    path = save_project(
        PlannerProject(atlas=metadata, renderer_anchor=anchor),
        tmp_path / "legacy.mouseplan",
    )
    project_payload = json.loads((path / PROJECT_FILENAME).read_text(encoding="utf-8"))
    atlas_payload = json.loads((path / ATLAS_FILENAME).read_text(encoding="utf-8"))
    project_payload["schema_version"] = 1
    project_payload.pop("renderer_anchor")
    atlas_payload.pop("midline_ml_um")
    (path / PROJECT_FILENAME).write_text(
        json.dumps(project_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (path / ATLAS_FILENAME).write_text(
        json.dumps(atlas_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (path / VASCULATURE_FILENAME).unlink()
    checksums = {
        filename: hashlib.sha256((path / filename).read_bytes()).hexdigest()
        for filename in (PROJECT_FILENAME, ATLAS_FILENAME, REGIONS_FILENAME)
    }
    (path / CHECKSUMS_FILENAME).write_text(
        json.dumps(checksums, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    migrated = load_project(path)

    assert migrated.schema_version == 7
    assert migrated.atlas is not None
    assert migrated.atlas.midline_ml_um == 5700.0
    assert migrated.renderer_anchor == anchor
    assert migrated.subject_vascular_images == []


def test_schema_two_package_without_vasculature_member_migrates_to_empty_state(
    tmp_path: Path,
) -> None:
    path = save_project(PlannerProject(title="Schema two"), tmp_path / "schema-two.mouseplan")
    project_payload = json.loads((path / PROJECT_FILENAME).read_text(encoding="utf-8"))
    project_payload["schema_version"] = 2
    (path / PROJECT_FILENAME).write_text(
        json.dumps(project_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (path / VASCULATURE_FILENAME).unlink()
    checksums = {
        filename: hashlib.sha256((path / filename).read_bytes()).hexdigest()
        for filename in (PROJECT_FILENAME, ATLAS_FILENAME, REGIONS_FILENAME)
    }
    (path / CHECKSUMS_FILENAME).write_text(
        json.dumps(checksums, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    migrated = load_project(path, recover_backup=False)

    assert migrated.schema_version == 7
    assert migrated.subject_vascular_images == []
    assert migrated.dorsal_vascular_registrations == []
    assert migrated.subject_vascular_overlays == []
    assert migrated.reference_vascular_density is None


def test_schema_three_package_migration_preserves_vascular_target_and_viewer_state(
    tmp_path: Path,
) -> None:
    project, source, _ = _vascular_project_and_source(tmp_path)
    project = project.model_copy(
        update={
            "viewer_slice_depths": ViewerSliceDepths(
                coronal=10,
                sagittal=20,
                horizontal=30,
            ),
            "unprojected_bregma_targets": [
                UnprojectedBregmaTarget(
                    label="legacy site",
                    ap_mm=-1.25,
                    ml_mm=-0.7,
                    dv_mm=-2.4,
                    notes="preserve exactly",
                )
            ],
        }
    )
    path = save_project(
        project,
        tmp_path / "schema-three.mouseplan",
        asset_source_package=source,
    )
    project_path = path / PROJECT_FILENAME
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 3
    payload.pop("calibrations")
    payload.pop("active_calibration_uuid")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    project_path.write_bytes(encoded)
    checksums_path = path / CHECKSUMS_FILENAME
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[PROJECT_FILENAME] = hashlib.sha256(encoded).hexdigest()
    checksums_path.write_text(
        json.dumps(checksums, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    migrated = load_project(path, recover_backup=False)

    assert migrated.schema_version == 7
    assert migrated.viewer_slice_depths == project.viewer_slice_depths
    assert migrated.unprojected_bregma_targets == project.unprojected_bregma_targets
    assert migrated.subject_vascular_images == project.subject_vascular_images
    assert migrated.dorsal_vascular_registrations == project.dorsal_vascular_registrations
    assert migrated.subject_vascular_overlays == project.subject_vascular_overlays
    assert migrated.reference_vascular_density == project.reference_vascular_density
    assert migrated.calibrations == []
    assert migrated.active_calibration_uuid is None


@pytest.mark.parametrize("legacy_schema", [4, 5])
def test_schema_four_and_five_packages_preserve_split_vascular_state_and_assets(
    tmp_path: Path,
    legacy_schema: int,
) -> None:
    project, source, image_bytes = _vascular_project_and_source(
        tmp_path,
        title=f"Schema {legacy_schema} vascular state",
    )
    path = save_project(
        project,
        tmp_path / f"schema-{legacy_schema}.mouseplan",
        asset_source_package=source,
    )
    project_path = path / PROJECT_FILENAME
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    payload["schema_version"] = legacy_schema
    payload.pop("project_revision")
    payload.pop("probe_vessel_analyses")
    if legacy_schema == 4:
        payload.pop("probe_plans")
        payload.pop("probe_region_analyses")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    project_path.write_bytes(encoded)
    checksums_path = path / CHECKSUMS_FILENAME
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[PROJECT_FILENAME] = hashlib.sha256(encoded).hexdigest()
    checksums_path.write_text(
        json.dumps(checksums, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    migrated = load_project(path, recover_backup=False)

    assert migrated.schema_version == 7
    assert migrated.subject_vascular_images == project.subject_vascular_images
    assert migrated.dorsal_vascular_registrations == project.dorsal_vascular_registrations
    assert migrated.subject_vascular_overlays == project.subject_vascular_overlays
    assert migrated.reference_vascular_density == project.reference_vascular_density
    relative = project.subject_vascular_images[0].project_relative_path
    assert (path / relative).read_bytes() == image_bytes


@pytest.mark.parametrize("legacy_schema", [4, 5])
def test_schema_four_and_five_packages_require_checksummed_vasculature_member(
    tmp_path: Path,
    legacy_schema: int,
) -> None:
    project, source, _ = _vascular_project_and_source(tmp_path)
    path = save_project(
        project,
        tmp_path / f"schema-{legacy_schema}-missing-vascular.mouseplan",
        asset_source_package=source,
    )
    project_path = path / PROJECT_FILENAME
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    payload["schema_version"] = legacy_schema
    payload.pop("project_revision")
    payload.pop("probe_vessel_analyses")
    if legacy_schema == 4:
        payload.pop("probe_plans")
        payload.pop("probe_region_analyses")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    project_path.write_bytes(encoded)
    checksums_path = path / CHECKSUMS_FILENAME
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums[PROJECT_FILENAME] = hashlib.sha256(encoded).hexdigest()
    checksums_path.write_text(json.dumps(checksums), encoding="utf-8")
    (path / VASCULATURE_FILENAME).unlink()

    with pytest.raises(ProjectIntegrityError, match=r"vasculature\.json"):
        load_project(path, recover_backup=False)


def test_legacy_schema_rejects_hidden_unchecksummed_vasculature_member(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Mixed layout"), tmp_path / "mixed.mouseplan")
    project_payload = json.loads((path / PROJECT_FILENAME).read_text(encoding="utf-8"))
    project_payload["schema_version"] = 2
    (path / PROJECT_FILENAME).write_text(json.dumps(project_payload), encoding="utf-8")
    checksums = {
        filename: hashlib.sha256((path / filename).read_bytes()).hexdigest()
        for filename in (PROJECT_FILENAME, ATLAS_FILENAME, REGIONS_FILENAME)
    }
    (path / CHECKSUMS_FILENAME).write_text(json.dumps(checksums), encoding="utf-8")

    with pytest.raises(ProjectIntegrityError, match=r"unchecksummed vasculature\.json"):
        load_project(path, recover_backup=False)


def test_second_save_keeps_recoverable_previous_package(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Version one"), tmp_path / "plan.mouseplan")
    replacement = PlannerProject(title="Version two")
    save_project(replacement, path)
    backup = path.with_name(path.name + ".bak")

    assert backup.is_dir()
    assert load_project(path).title == "Version two"
    assert load_project(backup, recover_backup=False).title == "Version one"


def test_corrupt_current_project_recovers_verified_backup(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Known good"), tmp_path / "recover.mouseplan")
    save_project(PlannerProject(title="Current"), path)
    (path / PROJECT_FILENAME).write_text("{}\n", encoding="utf-8")

    recovered = load_project(path)

    assert recovered.title == "Known good"


def test_load_result_reports_primary_and_recovered_source_paths(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Known good"), tmp_path / "provenance.mouseplan")
    primary = load_project_with_provenance(path)

    assert primary.project.title == "Known good"
    assert primary.requested_path == path
    assert primary.source_path == path
    assert not primary.recovered_from_backup
    assert not primary.is_backup_source
    assert not primary.requires_save_as
    assert primary.writable_path == path

    save_project(PlannerProject(title="Current"), path)
    backup = path.with_name(path.name + ".bak")
    (path / PROJECT_FILENAME).write_text("{}\n", encoding="utf-8")
    recovered = load_project_with_provenance(path)

    assert recovered.project.title == "Known good"
    assert recovered.requested_path == path
    assert recovered.source_path == backup
    assert recovered.recovered_from_backup
    assert recovered.is_backup_source
    assert recovered.requires_save_as
    assert recovered.writable_path is None


def test_direct_backup_open_is_read_only_and_never_uses_bak_bak(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Version one"), tmp_path / "direct.mouseplan")
    save_project(PlannerProject(title="Version two"), path)
    backup = path.with_name(path.name + ".bak")
    direct = load_project_with_provenance(backup)

    assert direct.project.title == "Version one"
    assert direct.requested_path == backup
    assert direct.source_path == backup
    assert not direct.recovered_from_backup
    assert direct.is_backup_source
    assert direct.requires_save_as
    assert direct.writable_path is None

    nested_backup = backup.with_name(backup.name + ".bak")
    shutil.copytree(backup, nested_backup)
    (backup / PROJECT_FILENAME).write_text("{}\n", encoding="utf-8")
    with pytest.raises(ProjectIntegrityError, match="checksum mismatch"):
        load_project_with_provenance(backup)


def test_save_rejects_reserved_backup_destination(tmp_path: Path) -> None:
    backup = tmp_path / "reserved.mouseplan.bak"

    with pytest.raises(ProjectIntegrityError, match=r"read-only.*Save As"):
        save_project(PlannerProject(), backup)

    assert not backup.exists()


def test_checksum_tamper_fails_closed_without_backup(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Tamper test"), tmp_path / "tamper.mouseplan")
    payload = json.loads((path / PROJECT_FILENAME).read_text(encoding="utf-8"))
    payload["title"] = "silently modified"
    (path / PROJECT_FILENAME).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectIntegrityError, match="checksum mismatch"):
        load_project(path, recover_backup=False)
    assert validate_project(path)


@pytest.mark.parametrize(
    "filename",
    [
        CHECKSUMS_FILENAME,
        PROJECT_FILENAME,
        ATLAS_FILENAME,
        REGIONS_FILENAME,
        VASCULATURE_FILENAME,
    ],
)
def test_project_members_must_not_be_symlinks(tmp_path: Path, filename: str) -> None:
    path = save_project(PlannerProject(title="Symlink test"), tmp_path / "symlink.mouseplan")
    member = path / filename
    outside = tmp_path / f"outside-{filename}"
    outside.write_bytes(member.read_bytes())
    member.unlink()
    member.symlink_to(outside)

    with pytest.raises(ProjectIntegrityError, match="must not be a symbolic link"):
        load_project(path, recover_backup=False)


def test_project_package_must_not_be_a_symlink(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Package symlink"), tmp_path / "real.mouseplan")
    alias = tmp_path / "alias.mouseplan"
    alias.symlink_to(path, target_is_directory=True)

    with pytest.raises(ProjectIntegrityError, match="package must not be a symbolic link"):
        load_project(alias, recover_backup=False)


def test_project_member_must_be_a_regular_file(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable on this platform")
    path = save_project(PlannerProject(title="FIFO test"), tmp_path / "fifo.mouseplan")
    member = path / PROJECT_FILENAME
    member.unlink()
    os.mkfifo(member)

    with pytest.raises(ProjectIntegrityError, match="must be a regular file"):
        load_project(path, recover_backup=False)


def test_project_member_read_is_bounded_before_json_decode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = save_project(PlannerProject(title="Bounded read"), tmp_path / "bounded.mouseplan")
    size = (path / PROJECT_FILENAME).stat().st_size
    monkeypatch.setitem(PROJECT_MEMBER_MAX_BYTES, PROJECT_FILENAME, size - 1)

    with pytest.raises(ProjectIntegrityError, match=r"project\.json exceeds"):
        load_project(path, recover_backup=False)


def test_project_json_limit_has_headroom_for_product_valid_maximum() -> None:
    assert MAX_PROJECT_JSON_BYTES == 128 * 1024 * 1024
    assert PROJECT_MEMBER_MAX_BYTES[PROJECT_FILENAME] == MAX_PROJECT_JSON_BYTES


def test_generated_project_member_must_fit_reload_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(PROJECT_MEMBER_MAX_BYTES, PROJECT_FILENAME, 32)

    with pytest.raises(ProjectIntegrityError, match=r"project\.json exceeds"):
        save_project(PlannerProject(title="Bounded write"), tmp_path / "too-large.mouseplan")


def test_both_invalid_primary_and_backup_report_both_failures(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Old"), tmp_path / "double-failure.mouseplan")
    save_project(PlannerProject(title="New"), path)
    backup = path.with_name(path.name + ".bak")
    (path / PROJECT_FILENAME).write_text("{}\n", encoding="utf-8")
    (backup / PROJECT_FILENAME).write_text("{}\n", encoding="utf-8")

    with pytest.raises(ProjectRecoveryError, match="backup recovery also failed") as error:
        load_project_with_provenance(path)

    assert str(path) in str(error.value)
    assert str(backup) in str(error.value)


def test_invalid_current_does_not_replace_last_good_backup(tmp_path: Path) -> None:
    path = save_project(PlannerProject(title="Version one"), tmp_path / "invalid-current")
    save_project(PlannerProject(title="Version two"), path)
    backup = path.with_name(path.name + ".bak")
    (path / PROJECT_FILENAME).write_text("{}\n", encoding="utf-8")

    save_project(PlannerProject(title="Version three"), path)

    assert load_project(path, recover_backup=False).title == "Version three"
    assert load_project(backup, recover_backup=False).title == "Version one"


def test_rotation_rename_failure_restores_existing_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = save_project(PlannerProject(title="Version one"), tmp_path / "rotation-fail")
    save_project(PlannerProject(title="Version two"), path)
    backup = path.with_name(path.name + ".bak")
    original_rename = project_io_module._rename
    failed = False

    def fail_current_rotation(source: Path, destination: Path) -> None:
        nonlocal failed
        if not failed and source == path and destination == backup:
            failed = True
            raise OSError("synthetic destination-to-backup rename failure")
        original_rename(source, destination)

    monkeypatch.setattr(project_io_module, "_rename", fail_current_rotation)

    with pytest.raises(OSError, match="synthetic destination-to-backup"):
        save_project(PlannerProject(title="Version three"), path)

    assert load_project(path, recover_backup=False).title == "Version two"
    assert load_project(backup, recover_backup=False).title == "Version one"
    assert not list(tmp_path.glob(f".{path.name}.rotation.*"))


def test_install_rename_failure_rolls_back_current_and_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = save_project(PlannerProject(title="Version one"), tmp_path / "install-fail")
    save_project(PlannerProject(title="Version two"), path)
    backup = path.with_name(path.name + ".bak")
    original_rename = project_io_module._rename
    failed = False

    def fail_new_install(source: Path, destination: Path) -> None:
        nonlocal failed
        if not failed and source.name.startswith(f".{path.name}.new.") and destination == path:
            failed = True
            raise OSError("synthetic new-project install failure")
        original_rename(source, destination)

    monkeypatch.setattr(project_io_module, "_rename", fail_new_install)

    with pytest.raises(OSError, match="synthetic new-project"):
        save_project(PlannerProject(title="Version three"), path)

    assert load_project(path, recover_backup=False).title == "Version two"
    assert load_project(backup, recover_backup=False).title == "Version one"
    assert not list(tmp_path.glob(f".{path.name}.rotation.*"))


def test_double_rotation_failure_retains_prior_backup_in_private_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = save_project(PlannerProject(title="Version one"), tmp_path / "double-rename")
    save_project(PlannerProject(title="Version two"), path)
    backup = path.with_name(path.name + ".bak")
    original_rename = project_io_module._rename

    def fail_rotation_and_restore(source: Path, destination: Path) -> None:
        if destination == backup and (source == path or source.name.startswith("previous")):
            raise OSError("synthetic rotation/restore failure")
        original_rename(source, destination)

    monkeypatch.setattr(project_io_module, "_rename", fail_rotation_and_restore)

    with pytest.raises(ProjectRecoveryError, match="remains at"):
        save_project(PlannerProject(title="Version three"), path)

    staged = list(tmp_path.glob(f".{path.name}.rotation.*/previous.mouseplan.bak"))
    assert len(staged) == 1
    assert load_project(path, recover_backup=False).title == "Version two"
    assert load_project(staged[0], recover_backup=False).title == "Version one"


def test_save_fsyncs_package_and_parent_directory_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synced: list[Path] = []
    monkeypatch.setattr(project_io_module, "_fsync_directory", synced.append)

    path = save_project(PlannerProject(title="Durable"), tmp_path / "durable.mouseplan")

    assert path.parent in synced
    assert any(candidate.name.startswith(f".{path.name}.new.") for candidate in synced)


def test_normalize_project_path_only_appends_required_suffix(tmp_path: Path) -> None:
    assert normalize_project_path(tmp_path / "named").name == "named.mouseplan"
    assert normalize_project_path(tmp_path / "named.mouseplan").name == "named.mouseplan"
    assert normalize_project_path(tmp_path / "named.mouseplan.bak").name == "named.mouseplan.bak"


def test_project_rejects_mixed_or_out_of_bounds_atlas_cursor() -> None:
    metadata = make_allen_metadata_test_double(25)
    valid = BrainGlobePhysicalPoint(
        atlas_key=metadata.atlas_key,
        atlas_version=metadata.atlas_package_version,
        ap_um=12.5,
        dv_um=12.5,
        ml_um=12.5,
    )
    project = PlannerProject(atlas=metadata, linked_cursor=valid, renderer_anchor=valid)

    with pytest.raises(ValidationError, match="does not match project atlas"):
        project.linked_cursor = valid.model_copy(update={"atlas_version": "wrong"})
    project = PlannerProject(atlas=metadata, linked_cursor=valid, renderer_anchor=valid)
    with pytest.raises(ValidationError, match=r"outside atlas bounds \[0, 13200"):
        project.linked_cursor = valid.model_copy(update={"ap_um": 13_200.0})
    with pytest.raises(ValidationError, match="requires atlas metadata"):
        PlannerProject(linked_cursor=valid)
