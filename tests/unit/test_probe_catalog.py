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
    PROBE_CATALOG_VERSION,
    get_probe_model,
    list_probe_models,
)


def test_catalog_places_real_np1000_first_and_retains_generic_fixture() -> None:
    models = list_probe_models()

    assert PROBE_CATALOG_VERSION == "brain3d-probe-catalog-v2"
    assert len(models) == 2

    neuropixels, generic = models
    assert neuropixels.model_id == NEUROPIXELS_1_0_MODEL_ID
    assert neuropixels.model_version == NEUROPIXELS_1_0_MODEL_VERSION
    assert (
        neuropixels.verification.status is ProbeVerificationStatus.SOURCE_TRANSCRIBED_REVIEW_PENDING
    )
    assert neuropixels.manufacturer == "imec"
    assert neuropixels.product_code == "PRB_1_4_0480_1"
    assert not neuropixels.permits_verified_device_label

    assert generic.model_id == GENERIC_TEST_MODEL_ID
    assert generic.model_version == GENERIC_TEST_MODEL_VERSION
    assert generic.verification.status is ProbeVerificationStatus.USER_DEFINED_UNVERIFIED
    assert generic.manufacturer is None
    assert generic.product_code is None
    assert generic.declared_shank_count == 1
    assert len(generic.shanks[0].sites) == 16
    assert "not a Neuropixels" in generic.verification.review_notes


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
    with pytest.raises(KeyError, match="unknown probe model"):
        get_probe_model(model_id, "latest")
