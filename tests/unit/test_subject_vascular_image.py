from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from mouse_brain_planner.vasculature.subject_image import (
    SubjectImageImportError,
    import_subject_vascular_image,
    verify_subject_vascular_image,
)


def test_import_preserves_exact_png_bytes_and_verifies_provenance(tmp_path: Path) -> None:
    source = tmp_path / "dorsal.png"
    Image.new("RGB", (17, 11), color=(120, 15, 30)).save(source, format="PNG")
    original = source.read_bytes()
    package = tmp_path / "Animal42.mouseplan"

    image = import_subject_vascular_image(
        source,
        package_root=package,
        pixel_size_x_um=2.5,
        pixel_size_y_um=2.5,
    )

    stored = verify_subject_vascular_image(image, package_root=package)
    assert stored.read_bytes() == original
    assert image.source_sha256 == hashlib.sha256(original).hexdigest()
    assert image.width_px == 17
    assert image.height_px == 11
    assert image.calibrated
    assert image.project_relative_path.startswith("images/")
    assert image.original_name == "dorsal.png"


def test_import_rejects_extension_content_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "dorsal.jpg"
    Image.new("RGB", (10, 10)).save(source, format="PNG")
    with pytest.raises(SubjectImageImportError, match="bytes are png"):
        import_subject_vascular_image(source, package_root=tmp_path / "plan.mouseplan")


def test_import_rejects_symlink_source(tmp_path: Path) -> None:
    real = tmp_path / "real.png"
    Image.new("RGB", (10, 10)).save(real)
    source = tmp_path / "linked.png"
    source.symlink_to(real)
    with pytest.raises(SubjectImageImportError, match="regular file"):
        import_subject_vascular_image(source, package_root=tmp_path / "plan.mouseplan")


def test_verify_rejects_mutated_stored_image(tmp_path: Path) -> None:
    source = tmp_path / "dorsal.tif"
    Image.new("L", (12, 8), color=30).save(source, format="TIFF")
    package = tmp_path / "plan.mouseplan"
    image = import_subject_vascular_image(source, package_root=package)
    stored = package / image.project_relative_path
    data = bytearray(stored.read_bytes())
    data[-1] ^= 0x01
    stored.write_bytes(data)

    with pytest.raises(SubjectImageImportError, match="checksum mismatch"):
        verify_subject_vascular_image(image, package_root=package)


def test_image_model_requires_both_pixel_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "dorsal.jpeg"
    Image.new("RGB", (10, 10)).save(source, format="JPEG")
    with pytest.raises(ValueError, match="both x and y"):
        import_subject_vascular_image(
            source,
            package_root=tmp_path / "plan.mouseplan",
            pixel_size_x_um=3.0,
        )
