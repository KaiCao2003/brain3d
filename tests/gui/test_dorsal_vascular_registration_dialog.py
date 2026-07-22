"""Native Qt tests for subject-specific dorsal vascular registration."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QAccessible, QAccessibleInterface, QColor, QImage
from PySide6.QtWidgets import QAbstractItemView, QDialog, QDialogButtonBox
from pytestqt.qtbot import QtBot
from tests.fixtures import make_allen_metadata_test_double

from mouse_brain_planner.domain.vessel_models import (
    DorsalRegistrationMethod,
    DorsalVascularLandmark,
    SubjectImageFormat,
    SubjectVascularImage,
    VascularLandmarkKind,
)
from mouse_brain_planner.gui.dialogs.dorsal_vascular_registration import (
    DorsalVascularRegistrationDialog,
)
from mouse_brain_planner.gui.dialogs.vascular_image_canvas import VascularImageCanvas

pytestmark = pytest.mark.gui


def _write_subject_image(
    tmp_path: Path,
    *,
    image_format: SubjectImageFormat = SubjectImageFormat.PNG,
    width: int = 120,
    height: int = 80,
) -> tuple[SubjectVascularImage, Path]:
    format_details = {
        SubjectImageFormat.PNG: ("subject.png", "PNG"),
        SubjectImageFormat.JPEG: ("subject.jpg", "JPEG"),
        SubjectImageFormat.TIFF: ("subject.tif", "TIFF"),
    }
    filename, qt_format = format_details[image_format]
    path = tmp_path / filename
    raster = QImage(width, height, QImage.Format.Format_RGB32)
    raster.fill(QColor(34, 96, 138))
    raster.setPixelColor(width - 1, height - 1, QColor(220, 40, 80))
    assert raster.save(str(path), qt_format)
    raw_bytes = path.read_bytes()
    image = SubjectVascularImage(
        original_name=filename,
        project_relative_path=f"images/{filename}",
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        byte_size=len(raw_bytes),
        image_format=image_format,
        width_px=width,
        height_px=height,
    )
    return image, path


def _landmark(
    label: str,
    column: float,
    row: float,
    atlas_ap_um: float,
    atlas_ml_um: float,
    *,
    enabled: bool = True,
) -> DorsalVascularLandmark:
    return DorsalVascularLandmark(
        label=label,
        kind=VascularLandmarkKind.VESSEL_BIFURCATION,
        image_column_px=column,
        image_row_px=row,
        atlas_ap_um=atlas_ap_um,
        atlas_ml_um=atlas_ml_um,
        enabled=enabled,
    )


def _known_similarity_landmarks() -> tuple[DorsalVascularLandmark, ...]:
    return (
        _landmark("Bifurcation A", 10, 10, 1200, 2200),
        _landmark("Bifurcation B", 90, 10, 2800, 2200),
        _landmark("Review point", 10, 60, 1200, 3200, enabled=False),
    )


@pytest.mark.parametrize(
    "image_format",
    [SubjectImageFormat.PNG, SubjectImageFormat.JPEG, SubjectImageFormat.TIFF],
)
def test_dialog_decodes_actual_supported_raster_without_reinterpreting_dimensions(
    qtbot: QtBot,
    tmp_path: Path,
    image_format: SubjectImageFormat,
) -> None:
    image, path = _write_subject_image(tmp_path, image_format=image_format)
    dialog = DorsalVascularRegistrationDialog(
        image,
        path,
        make_allen_metadata_test_double(25),
    )
    qtbot.addWidget(dialog)

    assert dialog.image_path == path.resolve()
    assert dialog.canvas.raster_size == QSize(image.width_px, image.height_px)
    assert dialog.atlas_metadata.atlas_key == "allen_mouse_25um"
    assert dialog.atlas_metadata.atlas_package_version == "1.2"


def test_canvas_maps_aspect_fit_logical_clicks_to_exact_stored_samples_with_hidpi_image(
    qtbot: QtBot,
) -> None:
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("navy"))
    image.setDevicePixelRatio(2.0)
    canvas = VascularImageCanvas(image)
    qtbot.addWidget(canvas)
    canvas.resize(503, 407)
    canvas.show()

    assert canvas.raster_size == QSize(200, 100)
    target = canvas.image_target_rect()
    assert target.width() / target.height() == pytest.approx(2.0)
    for column, row in ((0, 0), (137, 63), (199, 99)):
        center = canvas.raster_sample_center(column, row)
        assert canvas.widget_position_to_raster(center) == (column, row)

    assert canvas.widget_position_to_raster(QPointF(target.left(), target.top() - 0.01)) is None
    assert canvas.widget_position_to_raster(QPointF(target.right(), target.center().y())) is None
    emitted: list[tuple[int, int]] = []
    canvas.raster_clicked.connect(lambda column, row: emitted.append((column, row)))
    click_position = canvas.raster_sample_center(50, 20).toPoint()
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=click_position)
    assert emitted == [(50, 20)]


def test_image_click_updates_active_landmark_column_and_row_exactly(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    image, path = _write_subject_image(tmp_path)
    dialog = DorsalVascularRegistrationDialog(
        image,
        path,
        make_allen_metadata_test_double(25),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    row = dialog.landmark_rows[0]

    click_position = dialog.canvas.raster_sample_center(73, 41).toPoint()
    qtbot.mouseClick(dialog.canvas, Qt.MouseButton.LeftButton, pos=click_position)

    assert row.column_spin.value() == 73
    assert row.row_spin.value() == 41
    assert dialog.current_registration is None


def test_successful_fit_reports_residuals_and_laterality_gates_acceptance(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    image, path = _write_subject_image(tmp_path)
    dialog = DorsalVascularRegistrationDialog(
        image,
        path,
        make_allen_metadata_test_double(25),
        prior_landmarks=_known_similarity_landmarks(),
    )
    qtbot.addWidget(dialog)
    save = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)

    qtbot.mouseClick(dialog.fit_button, Qt.MouseButton.LeftButton)

    assert dialog.current_registration is not None
    assert dialog.current_registration.method is DorsalRegistrationMethod.SIMILARITY
    assert "RMS residual" in dialog.fit_summary.text()
    assert "maximum residual" in dialog.fit_summary.text()
    assert all("Residual:" in row.residual_label.text() for row in dialog.landmark_rows)
    assert "excluded" in dialog.landmark_rows[2].residual_label.text()
    assert not save.isEnabled()

    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.registration is None
    assert "left/right" in dialog.inline_error.text()

    qtbot.mouseClick(dialog.laterality_checkbox, Qt.MouseButton.LeftButton)
    assert dialog.current_registration is not None
    assert dialog.current_registration.laterality_confirmed_by_user
    assert save.isEnabled()
    qtbot.mouseClick(save, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.registration is not None
    assert dialog.registration.image_uuid == image.image_uuid
    assert dialog.registration.atlas_key == "allen_mouse_25um"
    assert dialog.registration.atlas_version == "1.2"
    assert dialog.registration.laterality_confirmed_by_user
    assert dialog.registration.permits_final_export


def test_edit_after_fit_invalidates_current_result_and_blocks_accept(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    image, path = _write_subject_image(tmp_path)
    dialog = DorsalVascularRegistrationDialog(
        image,
        path,
        make_allen_metadata_test_double(25),
        prior_landmarks=_known_similarity_landmarks(),
    )
    qtbot.addWidget(dialog)
    qtbot.mouseClick(dialog.fit_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(dialog.laterality_checkbox, Qt.MouseButton.LeftButton)
    assert dialog.current_registration is not None

    dialog.landmark_rows[0].atlas_ap_spin.setValue(1225.0)

    assert dialog.current_registration is None
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "successful fit" in dialog.inline_error.text()


def test_affine_method_explains_distortion_and_enforces_count_and_geometry(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    image, path = _write_subject_image(tmp_path)
    two_landmarks = _known_similarity_landmarks()[:2]
    dialog = DorsalVascularRegistrationDialog(
        image,
        path,
        make_allen_metadata_test_double(25),
        prior_landmarks=two_landmarks,
    )
    qtbot.addWidget(dialog)
    qtbot.mouseClick(dialog.fit_button, Qt.MouseButton.LeftButton)
    assert dialog.current_registration is not None

    qtbot.mouseClick(dialog.affine_radio, Qt.MouseButton.LeftButton)
    assert dialog.current_registration is None
    assert "independent scaling and shear" in dialog.method_help.text()
    assert "distort" in dialog.method_help.text()
    qtbot.mouseClick(dialog.fit_button, Qt.MouseButton.LeftButton)
    assert "at least 3 enabled landmarks" in dialog.inline_error.text()

    qtbot.mouseClick(dialog.add_landmark_button, Qt.MouseButton.LeftButton)
    third = dialog.landmark_rows[2]
    third.column_spin.setValue(50)
    third.row_spin.setValue(10)
    third.atlas_ap_spin.setValue(2000)
    third.atlas_ml_spin.setValue(2200)
    qtbot.mouseClick(dialog.fit_button, Qt.MouseButton.LeftButton)
    assert "collinear" in dialog.inline_error.text()

    third.row_spin.setValue(50)
    third.atlas_ml_spin.setValue(3000)
    qtbot.mouseClick(dialog.fit_button, Qt.MouseButton.LeftButton)
    assert dialog.current_registration is not None
    assert dialog.current_registration.method is DorsalRegistrationMethod.AFFINE


def test_landmark_validation_errors_are_inline_without_modal_dialogs(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    image, path = _write_subject_image(tmp_path)
    landmarks = list(_known_similarity_landmarks()[:2])
    landmarks[0] = landmarks[0].model_copy(update={"image_column_px": -1.0})
    dialog = DorsalVascularRegistrationDialog(
        image,
        path,
        make_allen_metadata_test_double(25),
        prior_landmarks=landmarks,
    )
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.fit_button, Qt.MouseButton.LeftButton)
    assert "image columns" in dialog.inline_error.text()
    assert dialog.current_registration is None
    assert dialog.findChildren(QDialog) == []

    first = dialog.landmark_rows[0]
    first.column_spin.setValue(10)
    first.label_edit.clear()
    qtbot.mouseClick(dialog.fit_button, Qt.MouseButton.LeftButton)
    assert "needs a label" in dialog.inline_error.text()
    assert dialog.findChildren(QDialog) == []


def _accessible_descendants(root: QAccessibleInterface) -> list[QAccessibleInterface]:
    descendants: list[QAccessibleInterface] = []
    pending = [root]
    while pending:
        interface = pending.pop()
        descendants.append(interface)
        for index in range(interface.childCount()):
            child = interface.child(index)
            if child is not None:
                pending.append(child)
    return descendants


def test_landmark_rows_use_no_item_views_or_accessible_table_cell_selection_interfaces(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    image, path = _write_subject_image(tmp_path)
    dialog = DorsalVascularRegistrationDialog(
        image,
        path,
        make_allen_metadata_test_double(25),
        prior_landmarks=_known_similarity_landmarks(),
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.findChildren(QAbstractItemView) == []
    accessible = QAccessible.queryAccessibleInterface(dialog)
    interfaces = _accessible_descendants(accessible)
    forbidden_roles = {QAccessible.Role.Table, QAccessible.Role.Cell}
    forbidden_interfaces = (
        QAccessible.InterfaceType.TableInterface,
        QAccessible.InterfaceType.TableCellInterface,
        QAccessible.InterfaceType.SelectionInterface,
    )
    assert not any(interface.role() in forbidden_roles for interface in interfaces)
    assert not any(
        interface.interface_cast(interface_type) is not None
        for interface in interfaces
        for interface_type in forbidden_interfaces
    )

    qtbot.mouseClick(dialog.landmark_rows[-1].remove_button, Qt.MouseButton.LeftButton)
    assert len(dialog.landmark_rows) == 2
    assert dialog.findChildren(QAbstractItemView) == []
