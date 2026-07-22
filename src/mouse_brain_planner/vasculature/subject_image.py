"""Secure, byte-preserving import of animal-specific dorsal vascular images."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import warnings
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from mouse_brain_planner.domain.vessel_models import SubjectImageFormat, SubjectVascularImage

MAX_SUBJECT_IMAGE_BYTES = 512 * 1024 * 1024
MAX_SUBJECT_IMAGE_PIXELS = 1_000_000_000
SUPPORTED_EXTENSIONS: dict[str, SubjectImageFormat] = {
    ".png": SubjectImageFormat.PNG,
    ".jpg": SubjectImageFormat.JPEG,
    ".jpeg": SubjectImageFormat.JPEG,
    ".tif": SubjectImageFormat.TIFF,
    ".tiff": SubjectImageFormat.TIFF,
}
PIL_FORMATS: dict[str, SubjectImageFormat] = {
    "PNG": SubjectImageFormat.PNG,
    "JPEG": SubjectImageFormat.JPEG,
    "TIFF": SubjectImageFormat.TIFF,
}


class SubjectImageImportError(ValueError):
    """Raised when a source image cannot be preserved and validated safely."""


def import_subject_vascular_image(
    source_path: str | Path,
    *,
    package_root: str | Path,
    pixel_size_x_um: float | None = None,
    pixel_size_y_um: float | None = None,
) -> SubjectVascularImage:
    """Copy one supported raster unchanged into ``package_root/images``.

    The destination is content-hashed after the atomic copy.  DPI/EXIF scale is
    never interpreted as a scientific calibration; users must supply pixel size
    explicitly when scale-dependent measurements are required.
    """

    source = Path(source_path).expanduser()
    try:
        source_stat = source.lstat()
    except OSError as error:
        raise SubjectImageImportError(f"cannot inspect subject image: {source}") from error
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        raise SubjectImageImportError("subject image must be a regular file, not a symlink")
    if source_stat.st_size <= 0 or source_stat.st_size > MAX_SUBJECT_IMAGE_BYTES:
        raise SubjectImageImportError(
            f"subject image size must be within (0, {MAX_SUBJECT_IMAGE_BYTES}] bytes"
        )

    extension = source.suffix.casefold()
    expected_format = SUPPORTED_EXTENSIONS.get(extension)
    if expected_format is None:
        raise SubjectImageImportError("subject image must be PNG, JPEG, or TIFF")
    width, height, frame_count, detected_format = _inspect_image(source)
    if detected_format is not expected_format:
        raise SubjectImageImportError(
            f"image bytes are {detected_format.value}, not the {expected_format.value} "
            "format indicated by the extension"
        )

    package = Path(package_root).expanduser().resolve(strict=False)
    package.mkdir(parents=True, exist_ok=True)
    images_directory = package / "images"
    images_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination_name = f"{uuid4().hex}{extension}"
    destination = images_directory / destination_name

    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=".subject-image.",
        suffix=extension,
        dir=images_directory,
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    try:
        with os.fdopen(temporary_fd, "wb") as output, source.open("rb") as input_stream:
            while chunk := input_stream.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if temporary.stat().st_size != source_stat.st_size:
            raise SubjectImageImportError("subject image changed or was truncated during import")
        temporary.replace(destination)
        _fsync_directory(images_directory)
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise

    relative = destination.relative_to(package).as_posix()
    try:
        return SubjectVascularImage(
            original_name=source.name,
            project_relative_path=relative,
            source_sha256=digest.hexdigest(),
            byte_size=source_stat.st_size,
            image_format=detected_format,
            width_px=width,
            height_px=height,
            frame_count=frame_count,
            pixel_size_x_um=pixel_size_x_um,
            pixel_size_y_um=pixel_size_y_um,
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def verify_subject_vascular_image(
    image: SubjectVascularImage,
    *,
    package_root: str | Path,
) -> Path:
    """Verify the stored member's confinement, size, and SHA-256 before display."""

    package = Path(package_root).expanduser().resolve(strict=True)
    candidate = package.joinpath(*Path(image.project_relative_path).parts)
    try:
        member_stat = candidate.lstat()
    except OSError as error:
        raise SubjectImageImportError("stored subject image does not exist") from error
    if stat.S_ISLNK(member_stat.st_mode) or not stat.S_ISREG(member_stat.st_mode):
        raise SubjectImageImportError("stored subject image must be a regular file")
    resolved = candidate.resolve(strict=True)
    images_root = (package / "images").resolve(strict=True)
    if resolved.parent != images_root:
        raise SubjectImageImportError("stored subject image resolves outside images/")
    if member_stat.st_size != image.byte_size:
        raise SubjectImageImportError(
            f"stored subject image size mismatch: expected {image.byte_size}, "
            f"got {member_stat.st_size}"
        )
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != image.source_sha256:
        raise SubjectImageImportError(
            f"stored subject image checksum mismatch: expected {image.source_sha256}, got {actual}"
        )
    return resolved


def _inspect_image(path: Path) -> tuple[int, int, int, SubjectImageFormat]:
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_SUBJECT_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as opened:
                detected = PIL_FORMATS.get(opened.format or "")
                if detected is None:
                    raise SubjectImageImportError(
                        "image decoder did not identify PNG, JPEG, or TIFF"
                    )
                width, height = opened.size
                frame_count = int(getattr(opened, "n_frames", 1))
                opened.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise SubjectImageImportError(
            f"subject image is invalid: {type(error).__name__}"
        ) from error
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit
    if width <= 0 or height <= 0 or width * height > MAX_SUBJECT_IMAGE_PIXELS:
        raise SubjectImageImportError(
            f"subject image dimensions exceed the {MAX_SUBJECT_IMAGE_PIXELS}-pixel limit"
        )
    return width, height, frame_count, detected


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
