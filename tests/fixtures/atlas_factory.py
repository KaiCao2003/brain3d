"""Atlas metadata test doubles backed by published BrainGlobe contracts.

These helpers do not download or impersonate atlas archives. Shape, resolution,
axis, version, and provenance values mirror the production Allen BrainGlobe
metadata contract, while cache paths and hashes are visibly test-only values.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from mouse_brain_planner.domain.atlas_models import AtlasAxis, AtlasMetadata

AllenResolution = Literal[10, 25]

_ALLEN_SHAPES: dict[AllenResolution, tuple[int, int, int]] = {
    10: (1320, 800, 1140),
    25: (528, 320, 456),
}


def make_allen_metadata_test_double(resolution_um: AllenResolution) -> AtlasMetadata:
    """Build a deterministic test double for a real Allen package contract.

    The SHA-256 value identifies this test double only. It must never be used as
    or presented as an upstream archive checksum.
    """

    shape = _ALLEN_SHAPES[resolution_um]
    atlas_key = f"allen_mouse_{resolution_um}um"
    package_version = "1.2"
    test_identity = f"test-double-only:{atlas_key}:{package_version}"
    test_sha256 = hashlib.sha256(test_identity.encode()).hexdigest()
    voxel_size = float(resolution_um)

    return AtlasMetadata(
        atlas_key=atlas_key,
        atlas_package_version=package_version,
        species="Mus musculus",
        citation="Wang et al. 2020, https://doi.org/10.1016/j.cell.2020.04.007",
        source_url=(
            "https://gin.g-node.org/brainglobe/atlases/raw/master/"
            f"{atlas_key}_v{package_version}.tar.gz"
        ),
        cache_path=f"/__atlas_test_double__/{atlas_key}_v{package_version}",
        metadata_sha256=test_sha256,
        resolution_um=(voxel_size, voxel_size, voxel_size),
        shape_voxels=shape,
        standardized_orientation="asr",
        source_annotation="annotation/ccf_2017",
        framework_name="Allen CCFv3",
        symmetric=True,
        axes=(
            AtlasAxis(
                array_axis=0,
                anatomical_axis="AP",
                origin_direction="anterior",
                positive_direction="posterior",
                voxel_size_um=voxel_size,
            ),
            AtlasAxis(
                array_axis=1,
                anatomical_axis="DV",
                origin_direction="superior",
                positive_direction="inferior",
                voxel_size_um=voxel_size,
            ),
            AtlasAxis(
                array_axis=2,
                anatomical_axis="ML",
                origin_direction="right",
                positive_direction="left",
                voxel_size_um=voxel_size,
            ),
        ),
    )
