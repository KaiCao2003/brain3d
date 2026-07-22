"""Default-install dependency and import boundaries."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_default_dependencies_exclude_removed_desktop_stack() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    dependency_names = {
        requirement.split("==", 1)[0].split("[", 1)[0].casefold() for requirement in dependencies
    }

    assert dependency_names.isdisjoint({"pyside6", "pyvista", "pyvistaqt", "vtk"})


def test_removed_legacy_modules_are_not_in_the_product_package() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    package_root = repository_root / "src" / "mouse_brain_planner"

    assert not (package_root / "app.py").exists()
    assert not any((package_root / "gui").rglob("*.py"))
    assert not (package_root / "rendering" / "scene_controller.py").exists()
    assert not (package_root / "rendering" / "sagittal_cache.py").exists()
