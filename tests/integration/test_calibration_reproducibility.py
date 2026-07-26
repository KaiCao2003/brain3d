"""Fail-closed persistence tests for derived subject-calibration geometry."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from tests.integration.test_bridge_calibration import (
    _atlas_point,
    _call,
    _create,
    _create_params,
    _dispatcher,
)
from tests.integration.test_bridge_probe_planning import (
    _calibrated_target,
    _create_plan,
    _probe_dispatcher,
    _rewrite_project_json,
)

from mouse_brain_planner.coordinates.anatomical_atlas import (
    brainglobe_physical_to_canonical_anatomical,
)
from mouse_brain_planner.coordinates.transforms import (
    fit_anatomical_transform,
    transform_point,
)
from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.domain.stereotaxy_models import (
    AtlasRegisteredCalibration,
    atlas_registered_calibration_sha256,
)
from mouse_brain_planner.domain.transform_models import (
    AnatomicalTransform,
    LandmarkCorrespondence3D,
    TransformLandmarkResidual,
)
from mouse_brain_planner.persistence.project_io import (
    PROJECT_FILENAME,
    load_project,
    save_project,
)
from mouse_brain_planner.surgery.calibration_validation import (
    CalibrationReproducibilityError,
    validate_atlas_registered_calibration_reproducibility,
)
from mouse_brain_planner.surgery.probe_planning import build_calibrated_probe_plan
from mouse_brain_planner.version import PROJECT_SCHEMA_VERSION


def _project_with_plan() -> PlannerProject:
    dispatcher, session = _probe_dispatcher()
    target_id = _calibrated_target(dispatcher, session)
    _create_plan(dispatcher, session, target_id)
    assert session.project is not None
    return session.project


def _plan_rehashed_for_calibration(
    project: PlannerProject,
    calibration: AtlasRegisteredCalibration,
):
    assert project.atlas is not None
    original = project.probe_plans[0]
    target = next(
        item
        for item in project.unprojected_bregma_targets
        if item.target_uuid == original.source_target.target_uuid
    )
    plan, _ = build_calibrated_probe_plan(
        target=target,
        calibration=calibration,
        atlas=project.atlas,
        model=original.probe_model,
        name=original.name,
        azimuth_deg=0,
        elevation_deg=-90,
        insertion_depth_um=4,
        axial_rotation_deg=0,
        custom_geometry_acknowledged=True,
    )
    assert plan.calibration_sha256 == atlas_registered_calibration_sha256(calibration)
    return plan


def _schema_seven_package_with_forgery(
    *,
    tmp_path: Path,
    project: PlannerProject,
    calibration: AtlasRegisteredCalibration,
) -> Path:
    plan = _plan_rehashed_for_calibration(project, calibration)
    package = save_project(project, tmp_path / "forged-calibration")
    payload = json.loads((package / PROJECT_FILENAME).read_text(encoding="utf-8"))
    payload["schema_version"] = 7
    payload["calibrations"] = [calibration.model_dump(mode="json")]
    payload["probe_plans"] = [plan.model_dump(mode="json")]
    _rewrite_project_json(package, payload)
    return package


def test_schema_seven_load_rejects_quarter_micrometre_rehashed_transform_shift(
    tmp_path: Path,
) -> None:
    project = _project_with_plan()
    calibration = project.calibrations[0]
    matrix = list(calibration.atlas_transform.matrix_row_major)
    matrix[3] += 0.25
    shifted_transform = AnatomicalTransform.model_validate(
        {
            **calibration.atlas_transform.model_dump(mode="python"),
            "matrix_row_major": tuple(matrix),
        }
    )
    shifted_calibration = AtlasRegisteredCalibration.model_validate(
        {
            **calibration.model_dump(mode="python"),
            "atlas_transform": shifted_transform,
        }
    )
    package = _schema_seven_package_with_forgery(
        tmp_path=tmp_path,
        project=project,
        calibration=shifted_calibration,
    )

    with pytest.raises(ValueError, match="atlas transform matrix does not reproduce"):
        load_project(package, recover_backup=False)


def test_schema_seven_load_rejects_rehashed_landmark_residual_forgery(
    tmp_path: Path,
) -> None:
    project = _project_with_plan()
    calibration = project.calibrations[0]
    transform = calibration.atlas_transform
    residuals = list(transform.residuals)
    residuals[0] = residuals[0].model_copy(update={"ap_error_um": 0.25, "radial_error_um": 0.25})
    forged_transform = AnatomicalTransform.model_validate(
        {
            **transform.model_dump(mode="python"),
            "residuals": tuple(residuals),
            "rms_residual_um": 0.125,
            "max_residual_um": 0.25,
        }
    )
    forged_calibration = AtlasRegisteredCalibration.model_validate(
        {
            **calibration.model_dump(mode="python"),
            "atlas_transform": forged_transform,
        }
    )
    package = _schema_seven_package_with_forgery(
        tmp_path=tmp_path,
        project=project,
        calibration=forged_calibration,
    )

    with pytest.raises(ValueError, match="atlas transform residual"):
        load_project(package, recover_backup=False)


def test_schema_seven_load_rejects_coherently_refit_atlas_source_shift(
    tmp_path: Path,
) -> None:
    project = _project_with_plan()
    calibration = project.calibrations[0]
    transform = calibration.atlas_transform
    shifted_landmarks = tuple(
        item.model_copy(
            update={"source": item.source.model_copy(update={"ap_um": item.source.ap_um + 0.25})}
        )
        for item in transform.landmarks
    )
    coherently_refit_transform = fit_anatomical_transform(
        source_frame=transform.source_frame,
        destination_frame=transform.destination_frame,
        landmarks=shifted_landmarks,
        method=transform.method,
        version=transform.version,
        affine_distortion_acknowledged=transform.affine_distortion_acknowledged,
        notes=transform.notes,
    )
    forged_calibration = AtlasRegisteredCalibration.model_validate(
        {
            **calibration.model_dump(mode="python"),
            "atlas_transform": coherently_refit_transform,
        }
    )

    with pytest.raises(
        CalibrationReproducibilityError,
        match="required bregma source does not derive",
    ):
        validate_atlas_registered_calibration_reproducibility(forged_calibration)

    package = _schema_seven_package_with_forgery(
        tmp_path=tmp_path,
        project=project,
        calibration=forged_calibration,
    )
    with pytest.raises(ValueError, match="required bregma source does not derive"):
        load_project(package, recover_backup=False)


def test_additional_atlas_source_landmark_remains_independent() -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    source_frame = params["sourceFrame"]
    assert isinstance(source_frame, dict)
    params["additionalLandmarks"] = [
        {
            "label": "independent-extra",
            "sourceSkullPoint": {
                "frameId": source_frame["frameId"],
                "apMicrometres": 1.0,
                "mlMicrometres": 1.0,
                "dvMicrometres": 1.0,
                "componentOrder": ["AP", "ML", "DV"],
                "units": "micrometre",
            },
            "atlasPoint": _atlas_point(2.5, 2.5, 2.5),
        }
    ]
    created = _call(dispatcher, "calibration.create", **params)

    assert created["status"] == "created"
    assert session.project is not None
    calibration = session.project.calibrations[0]
    extra = next(
        item for item in calibration.atlas_transform.landmarks if item.label == "independent-extra"
    )
    required_skull_points = (
        calibration.skull_calibration.landmarks.bregma,
        calibration.skull_calibration.landmarks.lambda_point,
        calibration.skull_calibration.landmarks.left_skull,
        calibration.skull_calibration.landmarks.right_skull,
    )
    derived_required_sources = tuple(
        transform_point(calibration.skull_calibration.transform, point)
        for point in required_skull_points
    )
    assert extra.source not in derived_required_sources
    validate_atlas_registered_calibration_reproducibility(calibration)


def test_project_rejects_coherently_refit_reversed_atlas_ap_axis() -> None:
    project = _project_with_plan()
    assert project.atlas is not None
    calibration = project.calibrations[0]
    transform = calibration.atlas_transform
    physical_by_label = {
        "bregma": (4.0, 4.0, 4.0),
        "lambda": (2.0, 4.0, 4.0),
        "left-skull": (4.0, 4.0, 6.0),
        "right-skull": (4.0, 4.0, 2.0),
    }
    landmarks = tuple(
        LandmarkCorrespondence3D(
            landmark_uuid=item.landmark_uuid,
            label=item.label,
            source=item.source,
            destination=brainglobe_physical_to_canonical_anatomical(
                BrainGlobePhysicalPoint(
                    atlas_key=project.atlas.atlas_key,
                    atlas_version=project.atlas.atlas_package_version,
                    ap_um=physical_by_label[item.label][0],
                    dv_um=physical_by_label[item.label][1],
                    ml_um=physical_by_label[item.label][2],
                ),
                project.atlas,
            ),
            enabled=item.enabled,
        )
        for item in transform.landmarks
    )
    reversed_transform = fit_anatomical_transform(
        source_frame=transform.source_frame,
        destination_frame=transform.destination_frame,
        landmarks=landmarks,
        method=transform.method,
        version=transform.version,
        affine_distortion_acknowledged=transform.affine_distortion_acknowledged,
        notes=transform.notes,
    )
    reversed_calibration = AtlasRegisteredCalibration.model_validate(
        {
            **calibration.model_dump(mode="python"),
            "atlas_transform": reversed_transform,
        }
    )
    reversed_plan = _plan_rehashed_for_calibration(project, reversed_calibration)
    payload = project.model_dump(mode="python")
    payload["calibrations"] = [reversed_calibration.model_dump(mode="python")]
    payload["probe_plans"] = [reversed_plan.model_dump(mode="python")]

    with pytest.raises(ValueError, match="bregma must remain anterior to atlas lambda"):
        PlannerProject.model_validate(payload)


@pytest.mark.parametrize("fit_kind", ("identity", "rotation", "similarity"))
def test_valid_schema_seven_calibration_fits_migrate_and_reproduce(
    tmp_path: Path,
    fit_kind: str,
) -> None:
    dispatcher, session = _dispatcher()
    params = _create_params(session)
    if fit_kind == "rotation":
        cosine = math.cos(math.radians(30))
        sine = math.sin(math.radians(30))
        params["atlasLandmarks"] = {
            "bregma": _atlas_point(3.5, 4.0, 4.0),
            "lambdaPoint": _atlas_point(3.5 + 2 * cosine, 4.0 - 2 * sine, 4.0),
            "leftSkull": _atlas_point(3.5, 4.0, 6.0),
            "rightSkull": _atlas_point(3.5, 4.0, 2.0),
        }
    elif fit_kind == "similarity":
        params["atlasTransformMethod"] = "similarity"
        params["atlasLandmarks"] = {
            "bregma": _atlas_point(3.5, 3.5, 3.5),
            "lambdaPoint": _atlas_point(6.5, 3.5, 3.5),
            "leftSkull": _atlas_point(3.5, 3.5, 6.5),
            "rightSkull": _atlas_point(3.5, 3.5, 0.5),
        }
    created = _call(dispatcher, "calibration.create", **params)
    assert created["status"] == "created"
    assert session.project is not None
    calibration = session.project.calibrations[0]
    validate_atlas_registered_calibration_reproducibility(calibration)
    restored_model = PlannerProject.model_validate(session.project.model_dump(mode="python"))
    assert restored_model.calibrations == session.project.calibrations

    package = save_project(session.project, tmp_path / f"valid-{fit_kind}")
    payload = json.loads((package / PROJECT_FILENAME).read_text(encoding="utf-8"))
    payload["schema_version"] = 7
    _rewrite_project_json(package, payload)
    restored_package = load_project(package, recover_backup=False)

    assert restored_package.schema_version == PROJECT_SCHEMA_VERSION
    assert restored_package.calibrations == session.project.calibrations


def test_transform_reproduction_tolerance_is_sub_micrometre_and_bounded() -> None:
    dispatcher, session = _dispatcher()
    _create(dispatcher, session)
    assert session.project is not None
    calibration = session.project.calibrations[0]
    matrix = list(calibration.atlas_transform.matrix_row_major)
    matrix[3] += 5e-9
    within_tolerance = calibration.model_copy(
        update={
            "atlas_transform": calibration.atlas_transform.model_copy(
                update={"matrix_row_major": tuple(matrix)}
            )
        }
    )
    validate_atlas_registered_calibration_reproducibility(within_tolerance)

    matrix[3] += 2e-8
    outside_tolerance = calibration.model_copy(
        update={
            "atlas_transform": calibration.atlas_transform.model_copy(
                update={"matrix_row_major": tuple(matrix)}
            )
        }
    )
    with pytest.raises(CalibrationReproducibilityError, match="atlas transform matrix"):
        validate_atlas_registered_calibration_reproducibility(outside_tolerance)


def test_skull_qc_and_residuals_must_also_reproduce() -> None:
    dispatcher, session = _dispatcher()
    _create(dispatcher, session)
    assert session.project is not None
    calibration = session.project.calibrations[0]
    skull = calibration.skull_calibration
    residuals = list(skull.transform.residuals)
    residuals[0] = TransformLandmarkResidual(
        landmark_uuid=residuals[0].landmark_uuid,
        ap_error_um=0.25,
        ml_error_um=0,
        dv_error_um=0,
        radial_error_um=0.25,
    )
    transform = skull.transform.model_copy(
        update={
            "residuals": tuple(residuals),
            "rms_residual_um": 0.125,
            "max_residual_um": 0.25,
        }
    )
    qc = skull.qc.model_copy(
        update={
            "transform_rms_residual_um": 0.125,
            "transform_max_residual_um": 0.25,
        }
    )
    forged = calibration.model_copy(
        update={"skull_calibration": skull.model_copy(update={"transform": transform, "qc": qc})}
    )

    with pytest.raises(CalibrationReproducibilityError, match="skull transform residual"):
        validate_atlas_registered_calibration_reproducibility(forged)
