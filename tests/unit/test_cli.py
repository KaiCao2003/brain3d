"""Command-line contract tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import pytest

from mouse_brain_planner import cli as cli_module
from mouse_brain_planner.atlas import brainglobe_adapter
from mouse_brain_planner.atlas.brainglobe_adapter import AtlasCatalogRecord
from mouse_brain_planner.cli import main
from mouse_brain_planner.domain.project_models import PlannerProject
from mouse_brain_planner.persistence.project_io import save_project
from mouse_brain_planner.version import __version__


class FakeAtlasRepository:
    """Catalog/download double used to prove exact CLI version selection."""

    open_calls: ClassVar[list[dict[str, object]]] = []

    def list_atlases(self) -> list[AtlasCatalogRecord]:
        return [
            AtlasCatalogRecord(
                name="allen_mouse_25um",
                latest_version="1.2",
                downloaded=False,
            )
        ]

    def open(self, atlas_name: str, **kwargs: object) -> object:
        self.open_calls.append({"atlas_name": atlas_name, **kwargs})
        return object()


def test_module_version_command() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "mouse_brain_planner", "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == f"mouse-brain-planner {__version__}"
    assert completed.stderr == ""


def test_no_subcommand_prints_help_without_launching_a_gui(capsys: object) -> None:
    result = main([])

    assert result == 2
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == ""
    assert "usage: mouse-brain-planner" in captured.err
    assert "bridge" in captured.err
    assert "validate-project" in captured.err


def test_bridge_subcommand_delegates_to_explicit_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mouse_brain_planner.bridge import server

    monkeypatch.setattr(server, "main", lambda: 17)

    assert main(["bridge"]) == 17


def test_cli_and_bridge_import_without_qt_or_vtk_modules() -> None:
    script = """
import json
import sys
import mouse_brain_planner.cli
import mouse_brain_planner.bridge.server

forbidden = sorted(
    name for name in sys.modules
    if name.split('.', 1)[0].lower() in {
        'pyside6', 'pyvista', 'pyvistaqt', 'vtk', 'vtkmodules'
    }
)
print(json.dumps(forbidden))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == []


def test_validate_command_accepts_valid_project(tmp_path: Path, capsys: object) -> None:
    path = save_project(PlannerProject(title="CLI validation"), tmp_path / "valid.mouseplan")

    result = main(["validate-project", str(path)])

    assert result == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Valid project" in captured.out


def test_validate_command_rejects_missing_project(tmp_path: Path, capsys: object) -> None:
    result = main(["validate-project", str(tmp_path / "missing.mouseplan")])

    assert result == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "does not exist" in captured.err


def test_atlas_download_uses_exact_catalog_version(
    monkeypatch: pytest.MonkeyPatch,
    capsys: object,
) -> None:
    FakeAtlasRepository.open_calls.clear()
    monkeypatch.setattr(cli_module, "configure_brainglobe_environment", lambda: None)
    monkeypatch.setattr(
        brainglobe_adapter,
        "BrainGlobeAtlasRepository",
        FakeAtlasRepository,
    )

    result = main(["atlas", "download", "allen_mouse_25um"])

    assert result == 0
    assert FakeAtlasRepository.open_calls == [
        {
            "atlas_name": "allen_mouse_25um",
            "package_version": "1.2",
            "allow_download": True,
        }
    ]
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "allen_mouse_25um v1.2" in captured.out
