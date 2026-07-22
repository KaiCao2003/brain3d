"""Qualification tests for the deliberately small probe catalog."""

from __future__ import annotations

import pytest

from mouse_brain_planner.domain.probe_models import ProbeVerificationStatus
from mouse_brain_planner.probes.catalog import (
    GENERIC_TEST_MODEL_ID,
    GENERIC_TEST_MODEL_VERSION,
    get_probe_model,
    list_probe_models,
)


def test_catalog_exposes_only_explicitly_unverified_generic_fixture() -> None:
    models = list_probe_models()

    assert len(models) == 1
    model = models[0]
    assert model.model_id == GENERIC_TEST_MODEL_ID
    assert model.model_version == GENERIC_TEST_MODEL_VERSION
    assert model.verification.status is ProbeVerificationStatus.USER_DEFINED_UNVERIFIED
    assert model.manufacturer is None
    assert model.product_code is None
    assert model.declared_shank_count == 1
    assert len(model.shanks[0].sites) == 16
    assert "not a Neuropixels" in model.verification.review_notes


def test_catalog_resolution_requires_exact_id_and_version() -> None:
    expected = list_probe_models()[0]

    assert get_probe_model(expected.model_id, expected.model_version) is expected
    with pytest.raises(KeyError, match="unknown probe model"):
        get_probe_model(expected.model_id, "latest")
