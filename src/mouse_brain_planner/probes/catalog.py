"""Versioned, source-traceable probe catalog for the supported planner path.

The production list exposes only Neuropixels 2.0 single-shank and standard
four-shank physical site geometry.  Quad Base, the existing Neuropixels 1.0
NP1000 transcription, and the synthetic fixture remain exact archived
identities for old-project compatibility and test evidence, but are not listed
for new plans.  Every manufacturer model is deliberately review-pending:
source transcription is not the same thing as an independent human
verification.
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

PROBE_CATALOG_VERSION: Final = "brain3d-probe-catalog-v5"

NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID: Final = "imec-neuropixels-2.0-single-shank-np2003-np2004"
NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID: Final = (
    "imec-neuropixels-2.0-standard-four-shank-np2013-np2014"
)
NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID: Final = (
    "imec-neuropixels-2.0-quad-base-four-shank-np2020-np2021"
)
NEUROPIXELS_2_0_MODEL_VERSION: Final = "source-snapshot-2026-07-23"
NEUROPIXELS_2_0_SPEC_SHA256: Final = (
    "bcd5a24e0f91c23c665f4fddfaad06ef6a8a1278a248ec3f5b4ebf17f1d0f6eb"
)
NEUROPIXELS_2_0_USER_MANUAL_ZIP_SHA256: Final = (
    "99677abe3e052636894934170d7d70c12e327433e3749b38213f74ff7772d0a8"
)
NEUROPIXELS_2_0_ELECTRODE_MAPPING_SHA256: Final = (
    "85c1236e512be518f6706256c24a214fab7ff238e993149e242fd5ad69ba167f"
)
NEUROPIXELS_2_0_QB_SPEC_SHA256: Final = (
    "9a0b4566979acbad751c8f4fb72405f77e170e3963f16d1852709c83ce57c7a9"
)

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
_NP2_SOURCE_RETRIEVAL_DATE: Final = date(2026, 7, 23)
_PROBETABLE_COMMIT: Final = "207f7bf424b0fa26f271700b970e27a58a9a1111"
_SPIKEGLX_COMMIT: Final = "d67bee45fa2635873456eb5d3f5e5a051690e64f"
_NP1_SITE_COUNT: Final = 960
_NP1_COLUMNS_PER_HARDWARE_ROW: Final = 2
_NP1_REFERENCE_ELECTRODE_IDS: Final[frozenset[int]] = frozenset({191, 575, 959})
_NP2_SITES_PER_SHANK: Final = 1280
_NP2_COLUMNS_PER_HARDWARE_ROW: Final = 2
_NP2_FOUR_SHANK_COUNT: Final = 4


def _neuropixels_2_0_sources(
    *,
    include_quad_base_spec: bool,
) -> tuple[ProbeSourceArtifact, ...]:
    """Return the exact official and implementation artifacts used for NP2."""

    sources = [
        ProbeSourceArtifact(
            title="Neuropixels 2.0 small-animal probe data sheet",
            source_url=(
                "https://www.neuropixels.org/_files/ugd/328966_2b39661f072d405b8d284c3c73588bc6.pdf"
            ),
            document_revision=(
                "No printed revision identifier; PDF metadata modification date 2024-09-18"
            ),
            retrieved_on=_NP2_SOURCE_RETRIEVAL_DATE,
            sha256=NEUROPIXELS_2_0_SPEC_SHA256,
            citation=(
                "imec, Neuropixels 2.0 data sheet, pp. 1-3: one or four 10 mm by "
                "70 micrometre by 24 micrometre shanks; 1280 sites per shank; "
                "15 micrometre axial and 32 micrometre lateral pitches; 175 "
                "micrometre chisel tip; and NP2003/NP2004/NP2013/NP2014 order codes."
            ),
        ),
        ProbeSourceArtifact(
            title="Neuropixels 2.0 User Manual V1.0.6 archive",
            source_url=(
                "https://www.neuropixels.org/_files/archives/"
                "328966_021470f37e3a4a4a88a256ab11639765.zip"
                "?dn=Neuropixels_2-0_User_Manual_V1-0-6.zip"
            ),
            document_revision="Neuropixels 2.0 User Manual V1.0.6",
            retrieved_on=_NP2_SOURCE_RETRIEVAL_DATE,
            sha256=NEUROPIXELS_2_0_USER_MANUAL_ZIP_SHA256,
            citation=(
                "imec, Neuropixels 2.0 User Manual V1.0.6, pp. 14 and 41-43: "
                "physical dimensions, two-column site layout, 1280 electrode "
                "identities per shank, virtual banks, and left-to-right shank "
                "numbering at 250 micrometre pitch."
            ),
        ),
        ProbeSourceArtifact(
            title="Neuropixels 2.0 Electrode-Channel Mapping workbook",
            source_url=(
                "https://www.neuropixels.org/_files/ugd/"
                "328966_43eea6555fa94a5bb1ddb51f00696fc3.xlsx"
                "?dn=Neuropix_2_0_Electrode-Channel-mapping.xlsx"
            ),
            document_revision=(
                "Official workbook retrieved 2026-07-23; sheets for single shank "
                "and multi-shank shanks 0-3"
            ),
            retrieved_on=_NP2_SOURCE_RETRIEVAL_DATE,
            sha256=NEUROPIXELS_2_0_ELECTRODE_MAPPING_SHA256,
            citation=(
                "imec, Neuropixels 2.0 Electrode-Channel Mapping: electrode "
                "identities 0-1279 and bank/channel connectivity for the single- "
                "and four-shank products."
            ),
        ),
        ProbeSourceArtifact(
            title="ProbeTable 1.8 probe_features.json",
            source_url=(
                "https://raw.githubusercontent.com/billkarsh/ProbeTable/"
                f"{_PROBETABLE_COMMIT}/Tables/probe_features.json"
            ),
            document_revision=f"table_version 1.8; git commit {_PROBETABLE_COMMIT}",
            retrieved_on=_NP2_SOURCE_RETRIEVAL_DATE,
            sha256=NEUROPIXELS_1_0_PROBETABLE_SHA256,
            citation=(
                "Bill Karsh, ProbeTable entries NP2003, NP2004, NP2013, NP2014, "
                "NP2020, and NP2021: shank/site counts, 206 micrometre "
                "tip-to-lowest-row-center distance, pitches, left-edge site "
                "offset, and 250 micrometre shank pitch."
            ),
        ),
        ProbeSourceArtifact(
            title="SpikeGLX Neuropixels geometry implementation",
            source_url=(
                "https://raw.githubusercontent.com/billkarsh/SpikeGLX/"
                f"{_SPIKEGLX_COMMIT}/Src-imro/IMROTbl.cpp"
            ),
            document_revision=f"git commit {_SPIKEGLX_COMMIT}",
            retrieved_on=_NP2_SOURCE_RETRIEVAL_DATE,
            sha256=NEUROPIXELS_1_0_SPIKEGLX_GEOMETRY_SHA256,
            citation=(
                "SpikeGLX IMROTbl.cpp cases NP2003/NP2004, NP2013/NP2014, and "
                "NP2020/NP2021: 206 micrometre tip offset, x0=27, lateral "
                "pitch=32, axial pitch=15, shank width=70, and shank pitch=250."
            ),
        ),
    ]
    if include_quad_base_spec:
        sources.append(
            ProbeSourceArtifact(
                title="Neuropixels 2.0 Quad Base multishank data sheet",
                source_url=(
                    "https://www.neuropixels.org/_files/ugd/"
                    "328966_4e39ab2e46424dc9b3efa446d286ab0f.pdf"
                ),
                document_revision=(
                    "No printed revision identifier; PDF metadata modification date 2025-06-16"
                ),
                retrieved_on=_NP2_SOURCE_RETRIEVAL_DATE,
                sha256=NEUROPIXELS_2_0_QB_SPEC_SHA256,
                citation=(
                    "imec, Neuropixels 2.0 Quad Base data sheet, pp. 1-3: four "
                    "10 mm shanks at 250 micrometre pitch, 5120 sites, 70 by 24 "
                    "micrometre cross-section, 175 micrometre chisel tip, and "
                    "NP2020/NP2021 order codes."
                ),
            )
        )
    return tuple(sources)


def _neuropixels_2_0_sites(shank_index: int) -> tuple[RecordingSiteDefinition, ...]:
    """Transcribe one NP2 shank in the official physical-electrode order."""

    sites: list[RecordingSiteDefinition] = []
    for electrode_id in range(_NP2_SITES_PER_SHANK):
        row, column = divmod(electrode_id, _NP2_COLUMNS_PER_HARDWARE_ROW)
        sites.append(
            RecordingSiteDefinition(
                site_id=f"shank-{shank_index}-electrode-{electrode_id:04d}",
                local=ProbeLocalPoint(
                    axial_from_tip_um=206 + 15 * row,
                    lateral_um=-8 + 32 * column,
                    normal_um=0,
                ),
                role=ProbeSiteRole.RECORDING,
                bank=f"virtual-bank-{electrode_id // 384}",
            )
        )
    return tuple(sites)


def _neuropixels_2_0_shank(
    shank_index: int,
) -> ProbeShankDefinition:
    """Return one NP2 shank offset from the primary (leftmost) shank."""

    return ProbeShankDefinition(
        shank_id=f"shank-{shank_index}",
        length_um=10_000,
        width_um=70,
        thickness_um=24,
        tip_geometry=ProbeTipGeometry.CHISEL,
        tip_length_um=175,
        center_lateral_um=250 * shank_index,
        tip_geometry_notes=(
            "The official imec specifications report a 175 micrometre physical "
            "chisel tip at approximately 20 degrees. ProbeTable and SpikeGLX "
            "separately report 206 micrometres from the physical tip to the center "
            "of the lowest electrode row."
        ),
        sites=_neuropixels_2_0_sites(shank_index),
    )


def _neuropixels_2_0_single_shank_model() -> ProbeModelDefinition:
    """Return the source-transcribed NP2003/NP2004 physical geometry."""

    return ProbeModelDefinition(
        model_id=NEUROPIXELS_2_0_SINGLE_SHANK_MODEL_ID,
        model_version=NEUROPIXELS_2_0_MODEL_VERSION,
        display_name="Neuropixels 2.0 — single shank (NP2003 / NP2004)",
        manufacturer="imec",
        product_code="NP2003 / NP2004",
        verification=ProbeModelVerification(
            status=ProbeVerificationStatus.SOURCE_TRANSCRIBED_REVIEW_PENDING,
            primary_sources=_neuropixels_2_0_sources(include_quad_base_spec=False),
            complete_geometry_transcribed=True,
            independent_transcription_review_completed=False,
            transcribed_by="Brain3D automated source transcription",
            independently_reviewed_by=None,
            review_notes=(
                "All 1280 physical site centers are generated from the cited exact "
                "source constants, but no independent human reviewer has checked the "
                "complete table against the artifacts or a physical probe. This model "
                "must remain review-pending and requires explicit acknowledgement."
            ),
        ),
        declared_shank_count=1,
        expected_site_count=_NP2_SITES_PER_SHANK,
        shanks=(_neuropixels_2_0_shank(0),),
        geometry_notes=(
            "NP2003 and NP2004 have identical implantable single-shank geometry; "
            "the order codes differ only by cap/package. Electrode IDs 0-1279 map "
            "row-major into 640 two-site rows. Axial positions are 206 + 15*row "
            "micrometres from the physical tip. Lateral positions are -8 and +24 "
            "micrometres in the 70 micrometre shank frame. The large tip reference "
            "electrode is distinct from the 1280 addressable recording sites and is "
            "not invented as a point site. All physical sites are represented; the "
            "hardware provides 384 simultaneously configurable recording channels, "
            "and the actual IMRO/electrode selection is not configured here. "
            "Package, holder, cable, and electronics geometry are outside the "
            "intracranial planning model."
        ),
    )


def _neuropixels_2_0_four_shank_model(
    *,
    quad_base: bool,
) -> ProbeModelDefinition:
    """Return an exact four-shank hardware identity with shared geometry."""

    if quad_base:
        model_id = NEUROPIXELS_2_0_QUAD_BASE_FOUR_SHANK_MODEL_ID
        display_name = "Neuropixels 2.0 — Quad Base four shanks (NP2020 / NP2021)"
        product_code = "NP2020 / NP2021"
        channel_note = (
            "The Quad Base electronics provide 1536 simultaneously configurable "
            "recording channels (384 per shank)."
        )
    else:
        model_id = NEUROPIXELS_2_0_STANDARD_FOUR_SHANK_MODEL_ID
        display_name = "Neuropixels 2.0 — standard four shanks (NP2013 / NP2014)"
        product_code = "NP2013 / NP2014"
        channel_note = (
            "The standard electronics provide 384 simultaneously configurable "
            "recording channels across the four-shank probe."
        )

    return ProbeModelDefinition(
        model_id=model_id,
        model_version=NEUROPIXELS_2_0_MODEL_VERSION,
        display_name=display_name,
        manufacturer="imec",
        product_code=product_code,
        verification=ProbeModelVerification(
            status=ProbeVerificationStatus.SOURCE_TRANSCRIBED_REVIEW_PENDING,
            primary_sources=_neuropixels_2_0_sources(include_quad_base_spec=quad_base),
            complete_geometry_transcribed=True,
            independent_transcription_review_completed=False,
            transcribed_by="Brain3D automated source transcription",
            independently_reviewed_by=None,
            review_notes=(
                "All 5120 physical site centers and four shank offsets are generated "
                "from the cited exact source constants, but no independent human "
                "reviewer has checked the complete table against the artifacts or a "
                "physical probe. This model must remain review-pending and requires "
                "explicit acknowledgement."
            ),
        ),
        declared_shank_count=_NP2_FOUR_SHANK_COUNT,
        expected_site_count=_NP2_SITES_PER_SHANK * _NP2_FOUR_SHANK_COUNT,
        shanks=tuple(_neuropixels_2_0_shank(index) for index in range(_NP2_FOUR_SHANK_COUNT)),
        geometry_notes=(
            f"{product_code} uses the same four implantable shanks and physical "
            "site layout as the other NP2 four-shank hardware identity, but remains "
            "a separate catalog choice because its base electronics and "
            f"simultaneous-channel identity differ. {channel_note} Cap, cable, "
            "headstage, and base-electronics geometry are not part of trajectory "
            "geometry. Shank 0 is the primary/leftmost shank "
            "at local lateral offset 0; shanks 1-3 are at +250, +500, and +750 "
            "micrometres. The planned target and entry therefore belong to shank 0. "
            "Each shank contains electrode IDs 0-1279 in 640 two-site rows at the "
            "same coordinates as the single-shank model. The large tip reference "
            "electrode on each shank is not invented as an addressable point site. "
            "All physical sites are represented; the actual IMRO/electrode "
            "selection is not configured here."
        ),
    )


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


_SUPPORTED_MODELS: Final[tuple[ProbeModelDefinition, ...]] = (
    _neuropixels_2_0_single_shank_model(),
    _neuropixels_2_0_four_shank_model(quad_base=False),
)
_SUPPORTED_MODELS_BY_IDENTITY: Final[dict[tuple[str, str], ProbeModelDefinition]] = {
    (model.model_id, model.model_version): model for model in _SUPPORTED_MODELS
}
_ARCHIVED_COMPATIBILITY_MODELS: Final[tuple[ProbeModelDefinition, ...]] = (
    _neuropixels_2_0_four_shank_model(quad_base=True),
    _neuropixels_1_0_model(),
    _generic_test_model(),
)
_MODELS_BY_IDENTITY: Final[dict[tuple[str, str], ProbeModelDefinition]] = {
    (model.model_id, model.model_version): model
    for model in (*_SUPPORTED_MODELS, *_ARCHIVED_COMPATIBILITY_MODELS)
}
_CATALOG_CONTROLLED_MODEL_IDS: Final[frozenset[str]] = frozenset(
    model.model_id for model in (*_SUPPORTED_MODELS, *_ARCHIVED_COMPATIBILITY_MODELS)
)


class ProbeModelCatalogSnapshotError(ValueError):
    """Raised when persisted geometry impersonates or diverges from the pinned catalog."""


def list_probe_models() -> tuple[ProbeModelDefinition, ...]:
    """Return only the two supported NP2 planning choices in display order."""

    return _SUPPORTED_MODELS


def get_supported_probe_model(
    model_id: str,
    model_version: str,
) -> ProbeModelDefinition:
    """Resolve an exact production-supported identity without an archived fallback."""

    try:
        return _SUPPORTED_MODELS_BY_IDENTITY[(model_id, model_version)]
    except KeyError as error:
        raise KeyError(
            f"unsupported production probe model identity {(model_id, model_version)!r}"
        ) from error


def get_probe_model(model_id: str, model_version: str) -> ProbeModelDefinition:
    """Resolve supported or archived identities for legacy project compatibility.

    Product catalog and mutation endpoints must use
    :func:`get_supported_probe_model`.  This wider resolver exists only so
    persisted legacy plans and their source snapshots remain readable and
    serializable without silently changing their hardware identity.
    """

    try:
        return _MODELS_BY_IDENTITY[(model_id, model_version)]
    except KeyError as error:
        raise KeyError(f"unknown probe model identity {(model_id, model_version)!r}") from error


def validate_probe_model_catalog_snapshot(
    model: ProbeModelDefinition,
    *,
    allow_unknown_identity: bool = False,
) -> None:
    """Require an exact, complete match for every catalog-owned model snapshot.

    Equality covers every persisted model field, including source provenance,
    verification state, shank dimensions and offsets, tip geometry, and the
    complete ordered recording-site table.  Unknown user-defined identities may
    be retained only when the caller explicitly selects an audit-only path.
    Catalog-owned IDs never accept an unrecognized version as a custom model.
    """

    identity = (model.model_id, model.model_version)
    canonical = _MODELS_BY_IDENTITY.get(identity)
    if canonical is None:
        if model.model_id in _CATALOG_CONTROLLED_MODEL_IDS:
            raise ProbeModelCatalogSnapshotError(
                f"probe model {model.model_id!r} uses an unknown catalog version "
                f"{model.model_version!r}"
            )
        if allow_unknown_identity:
            return
        raise ProbeModelCatalogSnapshotError(
            f"probe model identity {identity!r} is not in the source-pinned catalog"
        )
    if model != canonical:
        raise ProbeModelCatalogSnapshotError(
            f"probe model snapshot {identity!r} does not exactly match the "
            "source-pinned catalog definition"
        )
