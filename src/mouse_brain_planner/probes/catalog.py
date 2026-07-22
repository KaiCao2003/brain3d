"""Small fail-closed probe catalog used by the supported planner path.

The initial entry is deliberately generic.  It exists to exercise placement,
site mapping, persistence, and region traversal without presenting invented
dimensions as a Neuropixels product profile.  A manufacturer model may be
added only through :class:`ProbeModelVerification`'s primary-source and
independent-review gate.
"""

from __future__ import annotations

from typing import Final

from mouse_brain_planner.domain.probe_models import (
    ProbeLocalPoint,
    ProbeModelDefinition,
    ProbeModelVerification,
    ProbeShankDefinition,
    ProbeSiteRole,
    ProbeTipGeometry,
    ProbeVerificationStatus,
    RecordingSiteDefinition,
)

PROBE_CATALOG_VERSION: Final = "brain3d-probe-catalog-v1"
GENERIC_TEST_MODEL_ID: Final = "generic-linear-test-16"
GENERIC_TEST_MODEL_VERSION: Final = "1.0"


def _generic_test_model() -> ProbeModelDefinition:
    """Return deterministic synthetic geometry, never a device claim."""

    sites = tuple(
        RecordingSiteDefinition(
            site_id=f"test-site-{index + 1:02d}",
            local=ProbeLocalPoint(axial_from_tip_um=float((index + 1) * 250)),
            role=ProbeSiteRole.RECORDING,
            bank="software-test",
        )
        for index in range(16)
    )
    return ProbeModelDefinition(
        model_id=GENERIC_TEST_MODEL_ID,
        model_version=GENERIC_TEST_MODEL_VERSION,
        display_name="Generic test probe — one shank / 16 sites",
        verification=ProbeModelVerification(
            status=ProbeVerificationStatus.USER_DEFINED_UNVERIFIED,
            review_notes=(
                "Deterministic synthetic geometry for software testing. It is not a "
                "Neuropixels or other manufacturer device profile."
            ),
        ),
        declared_shank_count=1,
        expected_site_count=16,
        shanks=(
            ProbeShankDefinition(
                shank_id="test-shank-1",
                length_um=10_000,
                width_um=70,
                thickness_um=20,
                tip_geometry=ProbeTipGeometry.TRIANGULAR,
                tip_length_um=200,
                tip_geometry_notes=(
                    "Synthetic triangular tip used only to test conservative geometry paths."
                ),
                sites=sites,
            ),
        ),
        geometry_notes=(
            "Synthetic 10 mm by 70 µm by 20 µm single-shank fixture with 16 axial "
            "test sites at 250 µm spacing. Do not substitute it for a real probe model."
        ),
    )


_MODELS: Final[tuple[ProbeModelDefinition, ...]] = (_generic_test_model(),)
_MODELS_BY_IDENTITY: Final[dict[tuple[str, str], ProbeModelDefinition]] = {
    (model.model_id, model.model_version): model for model in _MODELS
}


def list_probe_models() -> tuple[ProbeModelDefinition, ...]:
    """Return immutable catalog models in stable display order."""

    return _MODELS


def get_probe_model(model_id: str, model_version: str) -> ProbeModelDefinition:
    """Resolve an exact catalog identity without a fallback or version guess."""

    try:
        return _MODELS_BY_IDENTITY[(model_id, model_version)]
    except KeyError as error:
        raise KeyError(f"unknown probe model identity {(model_id, model_version)!r}") from error
