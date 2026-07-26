"""Exact sign, surface, depth, and layout tests for direct probe planning."""

from __future__ import annotations

import math

import numpy as np
import pytest
from tests.fixtures.atlas_factory import make_allen_metadata_test_double

from mouse_brain_planner.domain.coordinate_models import BrainGlobePhysicalPoint
from mouse_brain_planner.domain.probe_plan_models import (
    ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION,
    ProbePlanRecord,
    probe_plan_input_digest,
)
from mouse_brain_planner.domain.surgery_common import AnimalSurgeryContext
from mouse_brain_planner.probes.catalog import (
    NEUROPIXELS_2_0_MODEL_VERSION,
    NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
    NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
    get_supported_probe_model,
)
from mouse_brain_planner.surgery.atlas_surface_planning import (
    PINPOINT_BREGMA_SOURCE_COMMIT,
    PINPOINT_BREGMA_SOURCE_SHA256,
    AtlasSurfacePlanningError,
    pinpoint_allen_bregma_reference,
    placement_from_atlas_surface_input,
    resolve_atlas_surface_input,
)
from mouse_brain_planner.surgery.probe_planning import (
    atlas_surface_projection_digest,
    build_atlas_surface_probe_plan,
    validate_atlas_surface_probe_plan_semantics,
)
from mouse_brain_planner.surgery.trajectory import (
    placed_shank_centerlines,
    placement_cross_section_axes,
)

_ANNOTATION_SHA256 = "a" * 64


def _annotation(*, surface_dv_index: int = 20) -> np.ndarray:
    """Allocate a lazy zero-filled real-shape test volume and one brain column."""

    annotation = np.zeros((528, 320, 456), dtype=np.uint8)
    for ap_index, ml_index in (
        (208, 228),
        (248, 268),
        (168, 188),
    ):
        annotation[ap_index, surface_dv_index:, ml_index] = 1
    return annotation


def _surface_input(
    *,
    angle: float = 0,
    layout: int = 0,
    depth_mm: float = 0.5,
):
    atlas = make_allen_metadata_test_double(25)
    return atlas, resolve_atlas_surface_input(
        annotation=_annotation(),
        atlas=atlas,
        insertion_ap_mm=0,
        insertion_ml_mm=0,
        surface_depth_mm=depth_mm,
        sagittal_angle_deg=angle,
        probe_layout_rotation_deg=layout,
        annotation_sha256=_ANNOTATION_SHA256,
        annotation_source="annotation/ccf_2017",
    )


def test_pinpoint_bregma_reference_is_explicit_and_source_pinned() -> None:
    reference = pinpoint_allen_bregma_reference(make_allen_metadata_test_double(25))

    assert (reference.ap_um, reference.dv_um, reference.ml_um) == (5200, 332, 5700)
    assert PINPOINT_BREGMA_SOURCE_COMMIT in reference.source_revision
    assert reference.source_sha256 == PINPOINT_BREGMA_SOURCE_SHA256
    assert "bregma is not encoded" in reference.limitation


def test_ap_ml_signs_and_surface_use_voxel_boundary_not_voxel_center() -> None:
    atlas = make_allen_metadata_test_double(25)
    annotation = _annotation(surface_dv_index=20)

    posterior_left = resolve_atlas_surface_input(
        annotation=annotation,
        atlas=atlas,
        insertion_ap_mm=-1.0,
        insertion_ml_mm=-1.0,
        surface_depth_mm=0.5,
        sagittal_angle_deg=0,
        probe_layout_rotation_deg=0,
        annotation_sha256=_ANNOTATION_SHA256,
        annotation_source="annotation/ccf_2017",
    )
    # BrainGlobe physical axes increase posterior and left.
    assert posterior_left.surface_entry_physical.ap_um == 6200
    assert posterior_left.surface_entry_physical.ml_um == 6700
    # The first labeled voxel is index 20; the surface is its superior face,
    # 500 µm, rather than its 512.5 µm center.
    assert posterior_left.surface_entry_physical.dv_um == 500
    assert posterior_left.surface_dv_index == 20

    anterior_right = resolve_atlas_surface_input(
        annotation=annotation,
        atlas=atlas,
        insertion_ap_mm=1.0,
        insertion_ml_mm=1.0,
        surface_depth_mm=0.5,
        sagittal_angle_deg=0,
        probe_layout_rotation_deg=0,
        annotation_sha256=_ANNOTATION_SHA256,
        annotation_source="annotation/ccf_2017",
    )
    assert anterior_right.surface_entry_physical.ap_um == 4200
    assert anterior_right.surface_entry_physical.ml_um == 4700


def test_surface_input_rejects_old_ml_sign_literal_and_old_addition_formula() -> None:
    atlas = make_allen_metadata_test_double(25)
    posterior_left = resolve_atlas_surface_input(
        annotation=_annotation(surface_dv_index=20),
        atlas=atlas,
        insertion_ap_mm=-1.0,
        insertion_ml_mm=-1.0,
        surface_depth_mm=0.5,
        sagittal_angle_deg=0,
        probe_layout_rotation_deg=0,
        annotation_sha256=_ANNOTATION_SHA256,
        annotation_source="annotation/ccf_2017",
    )

    stale_literal = posterior_left.model_dump(mode="python")
    stale_literal["ml_sign_convention"] = "ML positive animal left; ML negative animal right"
    with pytest.raises(ValueError, match="ml_sign_convention"):
        type(posterior_left).model_validate(stale_literal)

    stale_formula = posterior_left.model_dump(mode="python")
    stale_entry = dict(stale_formula["surface_entry_physical"])
    stale_entry["ml_um"] = 4700.0
    stale_formula["surface_entry_physical"] = stale_entry
    with pytest.raises(
        ValueError,
        match="surface entry AP/ML does not match bregma-relative input",
    ):
        type(posterior_left).model_validate(stale_formula)


@pytest.mark.parametrize(
    ("angle", "expected_ap_sign"),
    ((30.0, -1), (-30.0, 1)),
)
def test_sagittal_angle_sign_and_surface_relative_path_length(
    angle: float,
    expected_ap_sign: int,
) -> None:
    atlas, input_data = _surface_input(angle=angle, depth_mm=0.5)
    model = get_supported_probe_model(
        NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_MODEL_VERSION,
    )
    placement = placement_from_atlas_surface_input(
        input_data=input_data,
        atlas=atlas,
        context=AnimalSurgeryContext(subject_id=None),
        model=model,
        name="direct",
    )

    assert math.copysign(1, placement.inward_direction.ap) == expected_ap_sign
    assert placement.inward_direction.ml == pytest.approx(0)
    assert placement.inward_direction.dv == pytest.approx(-math.cos(math.radians(30)))
    assert placement.brain_entry == placement.entry
    delta = np.asarray(placement.tip.as_ap_ml_dv()) - np.asarray(placement.entry.as_ap_ml_dv())
    assert np.linalg.norm(delta) == pytest.approx(500.0)
    assert placement.insertion_depth_um == pytest.approx(500.0)


def test_four_shank_normal_and_clockwise_layout_have_exact_axes() -> None:
    model = get_supported_probe_model(
        NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_MODEL_VERSION,
    )
    atlas, normal_input = _surface_input(layout=0)
    normal = placement_from_atlas_surface_input(
        input_data=normal_input,
        atlas=atlas,
        context=AnimalSurgeryContext(),
        model=model,
        name="normal",
    )
    normal_lateral, _ = placement_cross_section_axes(normal)
    assert normal_lateral == pytest.approx((-1.0, 0.0, 0.0), abs=1e-12)

    _, clockwise_input = _surface_input(layout=90)
    clockwise = placement_from_atlas_surface_input(
        input_data=clockwise_input,
        atlas=atlas,
        context=AnimalSurgeryContext(),
        model=model,
        name="clockwise",
    )
    clockwise_lateral, _ = placement_cross_section_axes(clockwise)
    assert clockwise_lateral == pytest.approx((0.0, 1.0, 0.0), abs=1e-12)


@pytest.mark.parametrize(
    ("layout", "spacing_axis", "expected_step"),
    (
        (0, 0, 250.0),  # Physical AP increases posterior from primary shank 1.
        (90, 2, -250.0),  # Physical ML decreases animal-right from leftmost shank 1.
    ),
)
def test_primary_shank_surface_anchor_depth_and_complete_physical_extent(
    layout: int,
    spacing_axis: int,
    expected_step: float,
) -> None:
    atlas, input_data = _surface_input(layout=layout, depth_mm=2.3)
    model = get_supported_probe_model(
        NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_MODEL_VERSION,
    )
    placement = placement_from_atlas_surface_input(
        input_data=input_data,
        atlas=atlas,
        context=AnimalSurgeryContext(),
        model=model,
        name="NP2013 physical extent",
    )
    shanks = placed_shank_centerlines(model, placement)

    assert [shank.shank_id for shank in shanks] == [
        "shank-0",
        "shank-1",
        "shank-2",
        "shank-3",
    ]
    assert shanks[0].entry == placement.entry
    assert shanks[0].tip == placement.tip
    assert np.asarray(shanks[0].entry.as_ap_ml_dv()) == pytest.approx(
        -np.asarray(
            (
                input_data.surface_entry_physical.ap_um,
                input_data.surface_entry_physical.ml_um,
                input_data.surface_entry_physical.dv_um,
            )
        )
    )

    # Physical ASR ordering proves shank 1 is the selected edge anchor rather
    # than a midpoint: most anterior at 0°, animal-left-most at 90°.
    physical_entries = np.asarray(
        [(-shank.entry.ap_um, -shank.entry.dv_um, -shank.entry.ml_um) for shank in shanks]
    )
    assert np.diff(physical_entries[:, spacing_axis]) == pytest.approx([expected_step] * 3)
    other_axis = 2 if spacing_axis == 0 else 0
    assert np.ptp(physical_entries[:, other_axis]) == pytest.approx(0)

    inward = np.asarray(placement.inward_direction.as_ap_ml_dv())
    for shank in shanks:
        surface = np.asarray(shank.entry.as_ap_ml_dv())
        distal = np.asarray(shank.tip.as_ap_ml_dv())
        proximal = np.asarray(shank.proximal_end.as_ap_ml_dv())
        assert np.linalg.norm(distal - surface) == pytest.approx(2_300)
        assert np.linalg.norm(distal - proximal) == pytest.approx(10_000)
        assert shank.length_um == pytest.approx(10_000)
        assert np.linalg.norm(surface - proximal) == pytest.approx(7_700)
        assert np.dot(proximal - surface, inward) == pytest.approx(-7_700)

    # At the zero sagittal angle used here, the full proximal end is above the
    # atlas box while the distal target is 2.3 mm below the resolved surface.
    assert -shanks[0].proximal_end.dv_um == pytest.approx(-7_200)
    assert -shanks[0].tip.dv_um == pytest.approx(2_800)


def test_surface_column_without_annotation_is_rejected() -> None:
    atlas = make_allen_metadata_test_double(25)
    with pytest.raises(AtlasSurfacePlanningError, match="no annotated brain surface"):
        resolve_atlas_surface_input(
            annotation=np.zeros(atlas.shape_voxels, dtype=np.uint8),
            atlas=atlas,
            insertion_ap_mm=0,
            insertion_ml_mm=0,
            surface_depth_mm=1,
            sagittal_angle_deg=0,
            probe_layout_rotation_deg=0,
            annotation_sha256=_ANNOTATION_SHA256,
            annotation_source="annotation/ccf_2017",
        )


def test_tampered_rehashed_surface_index_is_rejected_against_loaded_annotation() -> None:
    atlas = make_allen_metadata_test_double(25)
    annotation = _annotation(surface_dv_index=20)
    model = get_supported_probe_model(
        NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_MODEL_VERSION,
    )
    plan, _ = build_atlas_surface_probe_plan(
        annotation=annotation,
        annotation_sha256=_ANNOTATION_SHA256,
        annotation_source="annotation/ccf_2017",
        atlas=atlas,
        model=model,
        insertion_ap_mm=0,
        insertion_ml_mm=0,
        surface_depth_mm=0.5,
        sagittal_angle_deg=0,
        probe_layout_rotation_deg=0,
        subject_id=None,
    )
    original = plan.surface_relative_input
    assert original is not None
    forged_input = original.model_copy(
        update={
            "surface_dv_index": 21,
            "surface_entry_physical": BrainGlobePhysicalPoint(
                atlas_key=atlas.atlas_key,
                atlas_version=atlas.atlas_package_version,
                ap_um=original.surface_entry_physical.ap_um,
                dv_um=525,
                ml_um=original.surface_entry_physical.ml_um,
            ),
        }
    )
    forged_placement = placement_from_atlas_surface_input(
        input_data=forged_input,
        atlas=atlas,
        context=plan.placement.context,
        model=model,
        name=plan.name,
    )
    forged_projection = atlas_surface_projection_digest(forged_input)
    forged_digest = probe_plan_input_digest(
        plan_uuid=plan.plan_uuid,
        plan_version=plan.plan_version,
        name=plan.name,
        source_target=None,
        probe_model=model,
        placement=forged_placement,
        calibration_uuid=None,
        calibration_version=None,
        calibration_sha256=None,
        atlas_metadata_sha256=atlas.metadata_sha256,
        projection_sha256=forged_projection,
        surface_relative_input=forged_input,
        planning_algorithm_version=ATLAS_SURFACE_PROBE_PLANNING_ALGORITHM_VERSION,
    )
    forged = ProbePlanRecord.model_validate(
        {
            **plan.model_dump(mode="python"),
            "surface_relative_input": forged_input,
            "placement": forged_placement,
            "projection_sha256": forged_projection,
            "input_sha256": forged_digest,
        }
    )

    # Metadata-only validation can establish internal consistency but cannot
    # pretend to know the volume. Loaded-annotation validation closes that gap.
    validate_atlas_surface_probe_plan_semantics(plan=forged, atlas=atlas)
    with pytest.raises(
        AtlasSurfacePlanningError,
        match="does not match the loaded annotation",
    ):
        validate_atlas_surface_probe_plan_semantics(
            plan=forged,
            atlas=atlas,
            annotation=annotation,
            annotation_sha256=_ANNOTATION_SHA256,
        )
