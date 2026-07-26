"""Qualification tests for source-traceable and synthetic probe catalog entries."""

from __future__ import annotations

from collections import Counter

import pytest

from mouse_brain_planner.domain.probe_models import (
    ProbeSiteRole,
    ProbeTipGeometry,
    ProbeVerificationStatus,
)
from mouse_brain_planner.probes.catalog import (
    GENERIC_TEST_MODEL_ID,
    GENERIC_TEST_MODEL_VERSION,
    NEUROPIXELS_1_0_MANUFACTURER_SPEC_SHA256,
    NEUROPIXELS_1_0_MODEL_ID,
    NEUROPIXELS_1_0_MODEL_VERSION,
    NEUROPIXELS_1_0_PROBETABLE_SHA256,
    NEUROPIXELS_1_0_SPIKEGLX_GEOMETRY_SHA256,
    NEUROPIXELS_1_0_SPIKEGLX_METADATA_SHA256,
    NEUROPIXELS_2_0_ELECTRODE_MAPPING_SHA256,
    NEUROPIXELS_2_0_MODEL_VERSION,
    NEUROPIXELS_2_0_QB_SPEC_SHA256,
    NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID,
    NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
    NEUROPIXELS_2_0_SPEC_SHA256,
    NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
    NEUROPIXELS_2_0_USER_MANUAL_ZIP_SHA256,
    PROBE_CATALOG_VERSION,
    ProbeModelCatalogSnapshotError,
    get_probe_model,
    get_supported_probe_model,
    list_probe_models,
    validate_probe_model_catalog_snapshot,
)


def test_public_catalog_contains_only_the_two_supported_np2_choices() -> None:
    models = list_probe_models()

    assert PROBE_CATALOG_VERSION == "brain3d-probe-catalog-v6"
    assert len(models) == 2

    np2_single, np2_standard = models
    assert np2_single.model_id == NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID
    assert np2_single.product_code == "NP2003"
    assert np2_standard.model_id == NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID
    assert np2_standard.product_code == "NP2013"
    assert "384 simultaneously configurable" in np2_standard.geometry_notes
    assert {
        NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID,
        NEUROPIXELS_1_0_MODEL_ID,
        GENERIC_TEST_MODEL_ID,
    }.isdisjoint(model.model_id for model in models)


def test_archived_models_remain_exactly_readable_but_are_not_listed() -> None:
    np2_quad_base = get_probe_model(
        NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_MODEL_VERSION,
    )
    assert np2_quad_base.product_code == "NP2020 / NP2021"
    assert "1536 simultaneously configurable" in np2_quad_base.geometry_notes

    np1 = get_probe_model(NEUROPIXELS_1_0_MODEL_ID, NEUROPIXELS_1_0_MODEL_VERSION)
    assert np1.verification.status is ProbeVerificationStatus.SOURCE_TRANSCRIBED_REVIEW_PENDING
    assert np1.product_code == "PRB_1_4_0480_1"

    generic = get_probe_model(GENERIC_TEST_MODEL_ID, GENERIC_TEST_MODEL_VERSION)
    assert generic.verification.status is ProbeVerificationStatus.USER_DEFINED_UNVERIFIED
    assert generic.product_code is None
    assert len(generic.shanks[0].sites) == 16


@pytest.mark.parametrize(
    ("model_id", "model_version"),
    (
        (
            NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID,
            NEUROPIXELS_2_0_MODEL_VERSION,
        ),
        (NEUROPIXELS_1_0_MODEL_ID, NEUROPIXELS_1_0_MODEL_VERSION),
        (GENERIC_TEST_MODEL_ID, GENERIC_TEST_MODEL_VERSION),
    ),
)
def test_archived_models_are_rejected_by_the_production_resolver(
    model_id: str,
    model_version: str,
) -> None:
    assert get_probe_model(model_id, model_version).model_id == model_id
    with pytest.raises(KeyError, match="unsupported production probe model"):
        get_supported_probe_model(model_id, model_version)


@pytest.mark.parametrize(
    "model_id",
    (
        NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
    ),
)
def test_supported_np2_models_resolve_through_the_production_boundary(
    model_id: str,
) -> None:
    assert get_supported_probe_model(model_id, NEUROPIXELS_2_0_MODEL_VERSION).model_id == model_id


@pytest.mark.parametrize(
    ("model_id", "source_hashes"),
    (
        (
            NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
            (
                NEUROPIXELS_2_0_SPEC_SHA256,
                NEUROPIXELS_2_0_USER_MANUAL_ZIP_SHA256,
                NEUROPIXELS_2_0_ELECTRODE_MAPPING_SHA256,
                NEUROPIXELS_1_0_PROBETABLE_SHA256,
                NEUROPIXELS_1_0_SPIKEGLX_GEOMETRY_SHA256,
            ),
        ),
        (
            NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
            (
                NEUROPIXELS_2_0_SPEC_SHA256,
                NEUROPIXELS_2_0_USER_MANUAL_ZIP_SHA256,
                NEUROPIXELS_2_0_ELECTRODE_MAPPING_SHA256,
                NEUROPIXELS_1_0_PROBETABLE_SHA256,
                NEUROPIXELS_1_0_SPIKEGLX_GEOMETRY_SHA256,
            ),
        ),
        (
            NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID,
            (
                NEUROPIXELS_2_0_SPEC_SHA256,
                NEUROPIXELS_2_0_USER_MANUAL_ZIP_SHA256,
                NEUROPIXELS_2_0_ELECTRODE_MAPPING_SHA256,
                NEUROPIXELS_1_0_PROBETABLE_SHA256,
                NEUROPIXELS_1_0_SPIKEGLX_GEOMETRY_SHA256,
                NEUROPIXELS_2_0_QB_SPEC_SHA256,
            ),
        ),
    ),
)
def test_np2_provenance_is_pinned_and_review_status_is_honest(
    model_id: str,
    source_hashes: tuple[str, ...],
) -> None:
    model = get_probe_model(model_id, NEUROPIXELS_2_0_MODEL_VERSION)
    verification = model.verification

    assert verification.status is ProbeVerificationStatus.SOURCE_TRANSCRIBED_REVIEW_PENDING
    assert verification.complete_geometry_transcribed
    assert not verification.independent_transcription_review_completed
    assert verification.transcribed_by == "Brain3D automated source transcription"
    assert verification.independently_reviewed_by is None
    assert "no independent human reviewer" in verification.review_notes
    if model_id in {
        NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
    }:
        assert "without a per-plan checkbox" in verification.review_notes
    else:
        assert "explicit acknowledgement" in verification.review_notes
    assert tuple(source.sha256 for source in verification.primary_sources) == source_hashes
    assert all(
        source.retrieved_on.isoformat() == "2026-07-23" for source in verification.primary_sources
    )


@pytest.mark.parametrize(
    ("model_id", "shank_count"),
    (
        (NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID, 1),
        (NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID, 4),
        (NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID, 4),
    ),
)
def test_np2_encodes_all_physical_site_centers_and_shank_offsets(
    model_id: str,
    shank_count: int,
) -> None:
    model = get_probe_model(model_id, NEUROPIXELS_2_0_MODEL_VERSION)

    assert model.declared_shank_count == shank_count
    assert model.expected_site_count == 1280 * shank_count
    assert len(model.shanks) == shank_count
    for shank_index, shank in enumerate(model.shanks):
        assert shank.shank_id == f"shank-{shank_index}"
        assert shank.length_um == 10_000
        assert shank.width_um == 70
        assert shank.thickness_um == 24
        assert shank.tip_geometry is ProbeTipGeometry.CHISEL
        assert shank.tip_length_um == 175
        assert "206 micrometres" in shank.tip_geometry_notes
        assert shank.center_lateral_um == 250 * shank_index
        assert shank.center_normal_um == 0
        assert len(shank.sites) == 1280

        for electrode_id, site in enumerate(shank.sites):
            row, column = divmod(electrode_id, 2)
            assert site.site_id == (f"shank-{shank_index}-electrode-{electrode_id:04d}")
            assert site.local.axial_from_tip_um == 206 + 15 * row
            assert site.local.lateral_um == -8 + 32 * column
            assert site.local.normal_um == 0
            assert site.role is ProbeSiteRole.RECORDING
            assert site.bank == f"virtual-bank-{electrode_id // 384}"

        assert Counter(site.bank for site in shank.sites) == {
            "virtual-bank-0": 384,
            "virtual-bank-1": 384,
            "virtual-bank-2": 384,
            "virtual-bank-3": 128,
        }
        assert shank.sites[0].local.axial_from_tip_um == 206
        assert shank.sites[0].local.lateral_um == -8
        assert shank.sites[1].local.lateral_um == 24
        assert shank.sites[-1].local.axial_from_tip_um == 9_791
        assert shank.sites[-1].local.lateral_um == 24


def test_np1000_provenance_is_immutable_and_review_status_is_honest() -> None:
    model = get_probe_model(NEUROPIXELS_1_0_MODEL_ID, NEUROPIXELS_1_0_MODEL_VERSION)
    verification = model.verification

    assert verification.complete_geometry_transcribed
    assert not verification.independent_transcription_review_completed
    assert verification.transcribed_by == "Brain3D automated source transcription"
    assert verification.independently_reviewed_by is None
    assert "no independent human reviewer" in verification.review_notes
    assert "explicit acknowledgement" in verification.review_notes

    assert tuple(source.sha256 for source in verification.primary_sources) == (
        NEUROPIXELS_1_0_MANUFACTURER_SPEC_SHA256,
        NEUROPIXELS_1_0_PROBETABLE_SHA256,
        NEUROPIXELS_1_0_SPIKEGLX_GEOMETRY_SHA256,
        NEUROPIXELS_1_0_SPIKEGLX_METADATA_SHA256,
    )
    assert all(
        source.retrieved_on.isoformat() == "2026-07-22" for source in verification.primary_sources
    )
    assert "207f7bf424b0fa26f271700b970e27a58a9a1111" in (
        verification.primary_sources[1].source_url
    )
    assert all(
        "d67bee45fa2635873456eb5d3f5e5a051690e64f" in source.source_url
        for source in verification.primary_sources[2:]
    )


def test_np1000_encodes_all_960_source_coordinates_and_reference_sites() -> None:
    model = get_probe_model(NEUROPIXELS_1_0_MODEL_ID, NEUROPIXELS_1_0_MODEL_VERSION)

    assert model.declared_shank_count == 1
    assert model.expected_site_count == 960
    shank = model.shanks[0]
    assert shank.shank_id == "shank-0"
    assert shank.length_um == 10_000
    assert shank.width_um == 70
    assert shank.thickness_um == 24
    assert shank.tip_geometry is ProbeTipGeometry.CHISEL
    assert shank.tip_length_um == 175
    assert "209 micrometres" in shank.tip_geometry_notes
    assert len(shank.sites) == 960

    for electrode_id, site in enumerate(shank.sites):
        row, column = divmod(electrode_id, 2)
        x_from_left_edge = (27 if row % 2 == 0 else 11) + 32 * column
        assert site.site_id == f"electrode-{electrode_id:03d}"
        assert site.local.axial_from_tip_um == 209 + 20 * row
        assert site.local.lateral_um == x_from_left_edge - 35
        assert site.local.normal_um == 0
        assert site.bank == f"bank-{electrode_id // 384}"

    assert Counter(site.bank for site in shank.sites) == {
        "bank-0": 384,
        "bank-1": 384,
        "bank-2": 192,
    }
    assert {
        index for index, site in enumerate(shank.sites) if site.role is ProbeSiteRole.REFERENCE
    } == {191, 575, 959}
    assert all(
        site.role is ProbeSiteRole.RECORDING
        for index, site in enumerate(shank.sites)
        if index not in {191, 575, 959}
    )

    assert shank.sites[0].local.axial_from_tip_um == 209
    assert shank.sites[0].local.lateral_um == -8
    assert shank.sites[1].local.lateral_um == 24
    assert shank.sites[2].local.axial_from_tip_um == 229
    assert shank.sites[2].local.lateral_um == -24
    assert shank.sites[3].local.lateral_um == 8
    assert shank.sites[-1].site_id == "electrode-959"
    assert shank.sites[-1].local.axial_from_tip_um == 9_789
    assert shank.sites[-1].local.lateral_um == 8


@pytest.mark.parametrize(
    ("model_id", "model_version"),
    (
        (NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID, NEUROPIXELS_2_0_MODEL_VERSION),
        (
            NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID,
            NEUROPIXELS_2_0_MODEL_VERSION,
        ),
        (
            NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID,
            NEUROPIXELS_2_0_MODEL_VERSION,
        ),
        (NEUROPIXELS_1_0_MODEL_ID, NEUROPIXELS_1_0_MODEL_VERSION),
        (GENERIC_TEST_MODEL_ID, GENERIC_TEST_MODEL_VERSION),
    ),
)
def test_catalog_resolution_requires_exact_id_and_version(
    model_id: str,
    model_version: str,
) -> None:
    expected = get_probe_model(model_id, model_version)

    assert get_probe_model(model_id, model_version) is expected
    validate_probe_model_catalog_snapshot(expected)
    with pytest.raises(KeyError, match="unknown probe model"):
        get_probe_model(model_id, "latest")


def test_catalog_snapshot_validation_rejects_geometry_and_provenance_drift() -> None:
    canonical = get_supported_probe_model(
        NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_MODEL_VERSION,
    )
    validate_probe_model_catalog_snapshot(canonical)

    wider_shank = canonical.shanks[0].model_copy(update={"width_um": 700})
    forged_geometry = canonical.model_copy(update={"shanks": (wider_shank,)})
    with pytest.raises(ProbeModelCatalogSnapshotError, match="does not exactly match"):
        validate_probe_model_catalog_snapshot(forged_geometry)

    forged_verification = canonical.verification.model_copy(
        update={"review_notes": "Self-asserted replacement provenance"}
    )
    forged_provenance = canonical.model_copy(update={"verification": forged_verification})
    with pytest.raises(ProbeModelCatalogSnapshotError, match="does not exactly match"):
        validate_probe_model_catalog_snapshot(forged_provenance)


def test_unknown_probe_identity_is_allowed_only_for_explicit_audit_compatibility() -> None:
    canonical = get_supported_probe_model(
        NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        NEUROPIXELS_2_0_MODEL_VERSION,
    )
    unknown = canonical.model_copy(
        update={
            "model_id": "historical-user-defined-probe",
            "model_version": "legacy-only",
        }
    )

    validate_probe_model_catalog_snapshot(unknown, allow_unknown_identity=True)
    with pytest.raises(ProbeModelCatalogSnapshotError, match="not in the source-pinned catalog"):
        validate_probe_model_catalog_snapshot(unknown)

    unknown_catalog_version = canonical.model_copy(update={"model_version": "self-asserted"})
    with pytest.raises(ProbeModelCatalogSnapshotError, match="unknown catalog version"):
        validate_probe_model_catalog_snapshot(
            unknown_catalog_version,
            allow_unknown_identity=True,
        )
