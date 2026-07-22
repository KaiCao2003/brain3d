"""Versioned, source-traceable probe catalog for the supported planner path.

The first entry is a complete Neuropixels 1.0 NP1000 geometry transcription
from immutable manufacturer, ProbeTable, and SpikeGLX source snapshots.  It is
deliberately review-pending: source transcription is not the same thing as an
independent human verification.  The synthetic fixture remains available for
software tests and is never presented as manufacturer geometry.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from mouse_brain_planner.domain.probe_models import (
    ProbeLocalPoint,
    ProbeModelDefinition,
    ProbeModelVerification,
    ProbeShankDefinition,
    ProbeSiteRole,
    ProbeSourceArtifact,
    ProbeTipGeometry,
    ProbeVerificationStatus,
    RecordingSiteDefinition,
)

PROBE_CATALOG_VERSION: Final = "brain3d-probe-catalog-v2"

NEUROPIXELS_1_0_MODEL_ID: Final = "imec-neuropixels-1.0-np1000-prb-1-4-0480-1"
NEUROPIXELS_1_0_MODEL_VERSION: Final = "source-snapshot-2026-07-22"
NEUROPIXELS_1_0_MANUFACTURER_SPEC_SHA256: Final = (
    "73feccebeadf45c8e7062028588a5b36e9da9f25d10b5d943f33389c3e791f6f"
)
NEUROPIXELS_1_0_PROBETABLE_SHA256: Final = (
    "6946867508341555960d0b8af2f8e88589f411fc5ff0e122371d377b71f6a3e4"
)
NEUROPIXELS_1_0_SPIKEGLX_GEOMETRY_SHA256: Final = (
    "59fa29406dc3f6ad38195157d6ddfecbf3b348e13bc3bfd827f50231adbde704"
)
NEUROPIXELS_1_0_SPIKEGLX_METADATA_SHA256: Final = (
    "654706c021a6da502b10086390b22464567aad5a94ed0d77a4bc9a36c3b3637f"
)

GENERIC_TEST_MODEL_ID: Final = "generic-linear-test-16"
GENERIC_TEST_MODEL_VERSION: Final = "1.0"

_SOURCE_RETRIEVAL_DATE: Final = date(2026, 7, 22)
_PROBETABLE_COMMIT: Final = "207f7bf424b0fa26f271700b970e27a58a9a1111"
_SPIKEGLX_COMMIT: Final = "d67bee45fa2635873456eb5d3f5e5a051690e64f"
_NP1_SITE_COUNT: Final = 960
_NP1_COLUMNS_PER_HARDWARE_ROW: Final = 2
_NP1_REFERENCE_ELECTRODE_IDS: Final[frozenset[int]] = frozenset({191, 575, 959})


def _neuropixels_1_0_sources() -> tuple[ProbeSourceArtifact, ...]:
    """Return the immutable artifacts used by the NP1000 transcription."""

    return (
        ProbeSourceArtifact(
            title="Neuropixels 1.0 high-resolution silicon neural probe specification",
            source_url=(
                "https://www.neuropixels.org/_files/ugd/328966_c5e4d31e8a974962b5eb8ec975408c9f.pdf"
            ),
            document_revision=(
                "No printed revision identifier; PDF metadata creation date 2023-10-20"
            ),
            retrieved_on=_SOURCE_RETRIEVAL_DATE,
            sha256=NEUROPIXELS_1_0_MANUFACTURER_SPEC_SHA256,
            citation=(
                "imec, Neuropixels 1.0 specification, pp. 1-3: research use only in "
                "non-human subjects; 960 12 x 12 micrometre electrodes; 10 mm by "
                "70 micrometre by 24 micrometre shank; 175 micrometre chisel tip at "
                "approximately 20 degrees; order code PRB_1_4_0480_1."
            ),
        ),
        ProbeSourceArtifact(
            title="ProbeTable 1.8 probe_features.json",
            source_url=(
                "https://raw.githubusercontent.com/billkarsh/ProbeTable/"
                f"{_PROBETABLE_COMMIT}/Tables/probe_features.json"
            ),
            document_revision=f"table_version 1.8; git commit {_PROBETABLE_COMMIT}",
            retrieved_on=_SOURCE_RETRIEVAL_DATE,
            sha256=NEUROPIXELS_1_0_PROBETABLE_SHA256,
            citation=(
                "Bill Karsh, ProbeTable NP1000 entry: 1 shank, 480 hardware rows, "
                "2 sites per row, 960 total sites, 20 micrometre row pitch, "
                "32 micrometre within-row pitch, alternating left-edge offsets 27 and "
                "11 micrometres, 70 by 24 micrometre cross-section, and three banks."
            ),
        ),
        ProbeSourceArtifact(
            title="SpikeGLX NP1000 IMRO geometry implementation",
            source_url=(
                "https://raw.githubusercontent.com/billkarsh/SpikeGLX/"
                f"{_SPIKEGLX_COMMIT}/Src-imro/IMROTbl.cpp"
            ),
            document_revision=f"git commit {_SPIKEGLX_COMMIT}",
            retrieved_on=_SOURCE_RETRIEVAL_DATE,
            sha256=NEUROPIXELS_1_0_SPIKEGLX_GEOMETRY_SHA256,
            citation=(
                "SpikeGLX IMROTbl.cpp NP1000/PRB_1_4 geometry and toGeomMap formula: "
                "tip-to-lowest-row-center 209 micrometres, even/odd x origins 27/11, "
                "horizontal pitch 32, vertical pitch 20, and x/z electrode-center mapping."
            ),
        ),
        ProbeSourceArtifact(
            title="SpikeGLX Metadata Help geometry-coordinate definitions",
            source_url=(
                "https://raw.githubusercontent.com/billkarsh/SpikeGLX/"
                f"{_SPIKEGLX_COMMIT}/Markdown/Metadata_Help.md"
            ),
            document_revision=f"git commit {_SPIKEGLX_COMMIT}",
            retrieved_on=_SOURCE_RETRIEVAL_DATE,
            sha256=NEUROPIXELS_1_0_SPIKEGLX_METADATA_SHA256,
            citation=(
                "SpikeGLX Metadata Help: imTipLength is the distance from probe tip to "
                "the center of the lowest electrodes; GeomMap x is measured from the "
                "left shank edge and z from the lowest electrode-row center toward base."
            ),
        ),
    )


def _neuropixels_1_0_sites() -> tuple[RecordingSiteDefinition, ...]:
    """Transcribe every NP1000 electrode into the catalog's tip-origin frame."""

    sites: list[RecordingSiteDefinition] = []
    for electrode_id in range(_NP1_SITE_COUNT):
        row, column = divmod(electrode_id, _NP1_COLUMNS_PER_HARDWARE_ROW)
        leftmost_center_from_left_edge_um = 27 if row % 2 == 0 else 11
        center_from_left_edge_um = leftmost_center_from_left_edge_um + 32 * column
        sites.append(
            RecordingSiteDefinition(
                site_id=f"electrode-{electrode_id:03d}",
                local=ProbeLocalPoint(
                    axial_from_tip_um=209 + 20 * row,
                    lateral_um=center_from_left_edge_um - 35,
                    normal_um=0,
                ),
                role=(
                    ProbeSiteRole.REFERENCE
                    if electrode_id in _NP1_REFERENCE_ELECTRODE_IDS
                    else ProbeSiteRole.RECORDING
                ),
                bank=f"bank-{electrode_id // 384}",
            )
        )
    return tuple(sites)


def _neuropixels_1_0_model() -> ProbeModelDefinition:
    """Return the complete source-transcribed NP1000/PRB_1_4_0480_1 model."""

    return ProbeModelDefinition(
        model_id=NEUROPIXELS_1_0_MODEL_ID,
        model_version=NEUROPIXELS_1_0_MODEL_VERSION,
        display_name="Neuropixels 1.0 — NP1000 / PRB_1_4_0480_1",
        manufacturer="imec",
        product_code="PRB_1_4_0480_1",
        verification=ProbeModelVerification(
            status=ProbeVerificationStatus.SOURCE_TRANSCRIBED_REVIEW_PENDING,
            primary_sources=_neuropixels_1_0_sources(),
            complete_geometry_transcribed=True,
            independent_transcription_review_completed=False,
            transcribed_by="Brain3D automated source transcription",
            independently_reviewed_by=None,
            review_notes=(
                "The source snapshot and all 960 site coordinates are transcribed, but no "
                "independent human reviewer has checked the complete table against the cited "
                "artifacts or a physical probe. The manufacturer specification's 175 "
                "micrometre chisel-tip length and SpikeGLX's 209 micrometre tip-to-lowest-"
                "row-center distance are preserved as different measurements. This model "
                "must remain review-pending and requires explicit acknowledgement."
            ),
        ),
        declared_shank_count=1,
        expected_site_count=_NP1_SITE_COUNT,
        shanks=(
            ProbeShankDefinition(
                shank_id="shank-0",
                length_um=10_000,
                width_um=70,
                thickness_um=24,
                tip_geometry=ProbeTipGeometry.CHISEL,
                tip_length_um=175,
                tip_geometry_notes=(
                    "The official imec specification reports a 175 micrometre chisel tip at "
                    "approximately 20 degrees. SpikeGLX separately reports 209 micrometres "
                    "from physical tip to the center of the lowest electrode row."
                ),
                sites=_neuropixels_1_0_sites(),
            ),
        ),
        geometry_notes=(
            "NP1000/PRB_1_4_0480_1 single-shank source transcription. Electrode IDs "
            "000-959 map row-major into 480 hardware rows with two sites per row. Axial "
            "positions use 209 + 20*row micrometres from the physical tip. Lateral "
            "positions are centered on the 70 micrometre shank: even rows are -8/+24 and "
            "odd rows -24/+8 micrometres, corresponding to SpikeGLX left-edge x positions "
            "27/59 and 11/43. The official 16 micrometre physical-column pitch is the "
            "spacing across the four alternating columns; the ProbeTable 32 micrometre "
            "pitch is within one two-site hardware row. Sites 191, 575, and 959 are the "
            "zero-based forms of SpikeGLX's three on-shank reference electrodes 192, 576, "
            "and 960. Source geometry is planar; normal=0 is an explicit planning-plane "
            "convention because the cited geometry map provides no normal-axis coordinate."
        ),
    )


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


_MODELS: Final[tuple[ProbeModelDefinition, ...]] = (
    _neuropixels_1_0_model(),
    _generic_test_model(),
)
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
