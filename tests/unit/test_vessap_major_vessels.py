from __future__ import annotations

from pathlib import Path

import pytest

from mouse_brain_planner.vasculature.vessap_major_vessels import (
    ASSET_FILENAME,
    MANIFEST_FILENAME,
    VesSAPMajorVesselError,
    default_asset_is_available,
    default_asset_paths,
    load_vessap_major_vessels,
)


def test_default_asset_paths_use_application_data_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MOUSE_BRAIN_PLANNER_DATA_DIR", str(tmp_path))

    asset, manifest = default_asset_paths()

    assert asset == tmp_path / "vasculature" / ASSET_FILENAME
    assert manifest == tmp_path / "vasculature" / MANIFEST_FILENAME
    assert default_asset_is_available() is False


def test_missing_external_asset_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MOUSE_BRAIN_PLANNER_DATA_DIR", str(tmp_path))

    with pytest.raises(VesSAPMajorVesselError, match="manifest must be a regular file"):
        load_vessap_major_vessels()
