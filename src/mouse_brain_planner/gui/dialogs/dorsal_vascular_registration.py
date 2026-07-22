"""Self-contained dorsal vascular landmark registration dialog."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QImage, QImageReader
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.vessel_models import (
    DorsalRegistrationMethod,
    DorsalVascularLandmark,
    DorsalVascularRegistration,
    SubjectImageFormat,
    SubjectVascularImage,
    VascularLandmarkKind,
)
from mouse_brain_planner.gui.dialogs.vascular_image_canvas import (
    VascularCanvasMarker,
    VascularImageCanvas,
)
from mouse_brain_planner.vasculature.registration import (
    VascularRegistrationError,
    fit_dorsal_vascular_registration,
)

_FORMAT_ALIASES: dict[SubjectImageFormat, frozenset[str]] = {
    SubjectImageFormat.PNG: frozenset({"png"}),
    SubjectImageFormat.JPEG: frozenset({"jpeg", "jpg"}),
    SubjectImageFormat.TIFF: frozenset({"tiff", "tif"}),
}


def load_verified_subject_raster(
    image: SubjectVascularImage,
    image_path: str | Path,
) -> tuple[Path, QImage]:
    """Bind verified provenance to a real, orientation-unmodified Qt raster.

    The local path is checked again because this standalone dialog has no
    project-package root from which to derive the member.  Decode-time EXIF
    orientation is deliberately disabled so displayed columns and rows remain
    the stored raster coordinates recorded by ``SubjectVascularImage``.
    """

    candidate = Path(image_path).expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("verified subject image path must be a regular file, not a symlink")
    resolved = candidate.resolve(strict=True)
    actual_size = resolved.stat().st_size
    if actual_size != image.byte_size:
        raise ValueError(
            f"subject image byte size mismatch: expected {image.byte_size}, got {actual_size}"
        )
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != image.source_sha256:
        raise ValueError("subject image checksum does not match verified provenance")

    reader = QImageReader(str(resolved))
    reader.setDecideFormatFromContent(True)
    reader.setAutoTransform(False)
    if not reader.canRead():
        raise ValueError(f"Qt cannot decode the verified subject image: {reader.errorString()}")
    detected_format = bytes(reader.format().data()).decode("ascii", errors="ignore").casefold()
    if detected_format not in _FORMAT_ALIASES[image.image_format]:
        raise ValueError(
            f"decoded image format {detected_format or 'unknown'} does not match "
            f"verified {image.image_format.value} provenance"
        )
    raster = reader.read()
    if raster.isNull():
        raise ValueError(f"Qt could not read the verified subject image: {reader.errorString()}")
    if raster.width() != image.width_px or raster.height() != image.height_px:
        raise ValueError(
            "decoded raster dimensions do not match verified provenance: "
            f"expected {image.width_px} x {image.height_px}, "
            f"got {raster.width()} x {raster.height()}"
        )
    raster.setDevicePixelRatio(1.0)
    return resolved, raster


class LandmarkEditorRow(QFrame):
    """Ordinary-widget editor for one landmark; never an item-view row."""

    changed = Signal()
    active_changed = Signal(bool)
    remove_requested = Signal()

    def __init__(
        self,
        *,
        row_number: int,
        landmark: DorsalVascularLandmark | None,
        image_width_px: int,
        image_height_px: int,
        atlas_extent_ap_um: float,
        atlas_extent_ml_um: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._landmark_uuid: UUID = landmark.landmark_uuid if landmark is not None else uuid4()
        self._row_number = row_number
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName(f"vascular-landmark-row-{row_number}")

        outer = QVBoxLayout(self)
        header = QHBoxLayout()
        self.active_radio = QRadioButton("Place with image click", self)
        self.active_radio.setAccessibleName(f"Place landmark {row_number} with image click")
        self.enabled_checkbox = QCheckBox("Enabled for fit", self)
        self.enabled_checkbox.setAccessibleName(f"Landmark {row_number} enabled for fit")
        self.remove_button = QPushButton("Remove", self)
        self.remove_button.setAccessibleName(f"Remove landmark {row_number}")
        header.addWidget(self.active_radio)
        header.addStretch(1)
        header.addWidget(self.enabled_checkbox)
        header.addWidget(self.remove_button)
        outer.addLayout(header)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.label_edit = QLineEdit(self)
        self.kind_button = QToolButton(self)
        self.kind_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.kind_menu = QMenu(self.kind_button)
        self.kind_button.setMenu(self.kind_menu)
        for kind in VascularLandmarkKind:
            action = QAction(kind.value.replace("-", " ").title(), self.kind_menu)
            action.setData(kind.value)
            action.triggered.connect(self._kind_action_triggered)
            self.kind_menu.addAction(action)
        self.column_spin = self._coordinate_spinbox("pixels")
        self.row_spin = self._coordinate_spinbox("pixels")
        self.atlas_ap_spin = self._coordinate_spinbox("micrometres")
        self.atlas_ml_spin = self._coordinate_spinbox("micrometres")
        self.column_spin.setSingleStep(1.0)
        self.row_spin.setSingleStep(1.0)
        self.atlas_ap_spin.setSingleStep(25.0)
        self.atlas_ml_spin.setSingleStep(25.0)

        self.label_edit.setAccessibleName(f"Landmark {row_number} label")
        self.column_spin.setAccessibleName(f"Landmark {row_number} image pixel column")
        self.row_spin.setAccessibleName(f"Landmark {row_number} image pixel row")
        self.atlas_ap_spin.setAccessibleName(
            f"Landmark {row_number} atlas AP micrometres positive posterior"
        )
        self.atlas_ml_spin.setAccessibleName(
            f"Landmark {row_number} atlas ML micrometres positive left"
        )

        form.addRow("Label", self.label_edit)
        form.addRow("Kind", self.kind_button)
        form.addRow(f"Pixel column [0, {image_width_px})", self.column_spin)
        form.addRow(f"Pixel row [0, {image_height_px})", self.row_spin)
        form.addRow(f"Atlas AP µm (+ posterior) [0, {atlas_extent_ap_um:g})", self.atlas_ap_spin)
        form.addRow(f"Atlas ML µm (+ left) [0, {atlas_extent_ml_um:g})", self.atlas_ml_spin)
        outer.addLayout(form)

        self.residual_label = QLabel("Residual: fit required", self)
        self.residual_label.setWordWrap(True)
        self.residual_label.setAccessibleName(f"Landmark {row_number} fit residual")
        outer.addWidget(self.residual_label)

        if landmark is None:
            self.label_edit.setText(f"Landmark {row_number}")
            self._kind = VascularLandmarkKind.VESSEL_BIFURCATION
            self.enabled_checkbox.setChecked(True)
        else:
            self.label_edit.setText(landmark.label)
            self._kind = landmark.kind
            self.column_spin.setValue(landmark.image_column_px)
            self.row_spin.setValue(landmark.image_row_px)
            self.atlas_ap_spin.setValue(landmark.atlas_ap_um)
            self.atlas_ml_spin.setValue(landmark.atlas_ml_um)
            self.enabled_checkbox.setChecked(landmark.enabled)
        self._update_kind_button()

        self.label_edit.textChanged.connect(self._emit_changed)
        self.column_spin.valueChanged.connect(self._emit_changed)
        self.row_spin.valueChanged.connect(self._emit_changed)
        self.atlas_ap_spin.valueChanged.connect(self._emit_changed)
        self.atlas_ml_spin.valueChanged.connect(self._emit_changed)
        self.enabled_checkbox.toggled.connect(self._emit_changed)
        self.active_radio.toggled.connect(self.active_changed.emit)
        self.remove_button.clicked.connect(self._request_remove)

    def _coordinate_spinbox(self, unit_name: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setDecimals(6)
        spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        spin.setToolTip(f"Exact {unit_name}; invalid bounds are reported inline when the fit runs")
        return spin

    def _emit_changed(self, *_args: object) -> None:
        self.changed.emit()

    def _request_remove(self, *_args: object) -> None:
        self.remove_requested.emit()

    def _kind_action_triggered(self, *_args: object) -> None:
        action = self.sender()
        if isinstance(action, QAction):
            self.set_landmark_kind(VascularLandmarkKind(str(action.data())))

    def set_landmark_kind(self, kind: VascularLandmarkKind) -> None:
        """Choose a kind through a menu button, without constructing an item view."""

        if kind is self._kind:
            return
        self._kind = kind
        self._update_kind_button()
        self.changed.emit()

    def _update_kind_button(self) -> None:
        display = self._kind.value.replace("-", " ").title()
        self.kind_button.setText(display)
        self.kind_button.setAccessibleName(f"Landmark {self._row_number} kind, current {display}")

    def set_row_number(self, row_number: int) -> None:
        """Refresh human-readable accessibility labels after a removal."""

        self._row_number = row_number
        self.setObjectName(f"vascular-landmark-row-{row_number}")
        self.setAccessibleName(f"Vascular landmark {row_number}")
        self.active_radio.setAccessibleName(f"Place landmark {row_number} with image click")
        self.enabled_checkbox.setAccessibleName(f"Landmark {row_number} enabled for fit")
        self.remove_button.setAccessibleName(f"Remove landmark {row_number}")
        self.label_edit.setAccessibleName(f"Landmark {row_number} label")
        self._update_kind_button()
        self.column_spin.setAccessibleName(f"Landmark {row_number} image pixel column")
        self.row_spin.setAccessibleName(f"Landmark {row_number} image pixel row")
        self.atlas_ap_spin.setAccessibleName(
            f"Landmark {row_number} atlas AP micrometres positive posterior"
        )
        self.atlas_ml_spin.setAccessibleName(
            f"Landmark {row_number} atlas ML micrometres positive left"
        )
        self.residual_label.setAccessibleName(f"Landmark {row_number} fit residual")

    def to_landmark(self) -> DorsalVascularLandmark:
        """Build one validated immutable domain landmark from current controls."""

        label = self.label_edit.text().strip()
        if not label:
            raise ValueError(f"Landmark {self._row_number} needs a label")
        return DorsalVascularLandmark(
            landmark_uuid=self._landmark_uuid,
            label=label,
            kind=self._kind,
            image_column_px=self.column_spin.value(),
            image_row_px=self.row_spin.value(),
            atlas_ap_um=self.atlas_ap_spin.value(),
            atlas_ml_um=self.atlas_ml_spin.value(),
            enabled=self.enabled_checkbox.isChecked(),
        )

    def canvas_marker(self) -> VascularCanvasMarker:
        """Return the row's current marker without requiring a valid label."""

        return VascularCanvasMarker(
            column_px=self.column_spin.value(),
            row_px=self.row_spin.value(),
            label=self.label_edit.text().strip(),
            enabled=self.enabled_checkbox.isChecked(),
            active=self.active_radio.isChecked(),
        )

    def set_residual(
        self,
        *,
        radial_um: float,
        ap_error_um: float,
        ml_error_um: float,
    ) -> None:
        """Show the exact enabled-landmark residual returned by the fitter."""

        self.residual_label.setText(
            f"Residual: {radial_um:.3f} µm (ΔAP {ap_error_um:+.3f} µm, ΔML {ml_error_um:+.3f} µm)"
        )


class DorsalVascularRegistrationDialog(QDialog):
    """Fit one subject raster to exact atlas ASR AP/ML coordinates.

    Every landmark editor is composed from ordinary controls and layouts.  No
    Qt item-view model, table, tree, cell, or accessible selection interface is
    introduced by this dialog.
    """

    def __init__(
        self,
        image: SubjectVascularImage,
        image_path: str | Path,
        atlas_metadata: AtlasMetadata,
        *,
        prior_landmarks: Sequence[DorsalVascularLandmark] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        resolved_path, raster = load_verified_subject_raster(image, image_path)
        self.subject_image = image
        self.image_path = resolved_path
        self.atlas_metadata = atlas_metadata
        self.landmark_rows: list[LandmarkEditorRow] = []
        self._current_registration: DorsalVascularRegistration | None = None
        self._accepted_registration: DorsalVascularRegistration | None = None

        self.setObjectName("dorsal-vascular-registration-dialog")
        self.setWindowTitle("Register subject dorsal vasculature")
        self.setAccessibleName("Subject dorsal vascular landmark registration")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(1240, 820)

        root = QVBoxLayout(self)
        provenance = QLabel(
            f"Subject image: {image.original_name} — verified SHA-256 "
            f"{image.source_sha256[:12]}… — stored raster "
            f"{image.width_px} x {image.height_px} px"
            + (f" — displaying frame 1 of {image.frame_count}" if image.frame_count > 1 else "")
            + "\n"
            f"Exact atlas: {atlas_metadata.atlas_key} "
            f"v{atlas_metadata.atlas_package_version}; "
            f"resolution {atlas_metadata.resolution_um} µm",
            self,
        )
        provenance.setObjectName("vascular-registration-provenance")
        provenance.setAccessibleName("Subject image and exact atlas provenance")
        provenance.setWordWrap(True)
        root.addWidget(provenance)

        axis_note = QLabel(
            "Coordinate signs (BrainGlobe ASR): image column increases right and row increases "
            "down; atlas AP increases posterior (+), atlas ML increases left (+). Pixel and "
            "atlas bounds are half-open; no image laterality is inferred from the transform.",
            self,
        )
        axis_note.setObjectName("vascular-registration-axis-note")
        axis_note.setAccessibleName("BrainGlobe ASR coordinate signs")
        axis_note.setWordWrap(True)
        root.addWidget(axis_note)

        body = QHBoxLayout()
        self.canvas = VascularImageCanvas(raster, self)
        self.canvas.raster_clicked.connect(self._place_active_landmark)
        body.addWidget(self.canvas, 3)

        controls = QWidget(self)
        controls.setObjectName("vascular-registration-controls")
        controls_layout = QVBoxLayout(controls)
        method_group = QGroupBox("Transform model", controls)
        method_group.setAccessibleName("Registration transform model")
        method_layout = QVBoxLayout(method_group)
        method_choices = QHBoxLayout()
        self.similarity_radio = QRadioButton("Similarity", method_group)
        self.affine_radio = QRadioButton("Affine", method_group)
        self.similarity_radio.setAccessibleName("Similarity registration method")
        self.affine_radio.setAccessibleName("Affine registration method")
        self.method_button_group = QButtonGroup(self)
        self.method_button_group.addButton(self.similarity_radio)
        self.method_button_group.addButton(self.affine_radio)
        self.similarity_radio.setChecked(True)
        method_choices.addWidget(self.similarity_radio)
        method_choices.addWidget(self.affine_radio)
        method_choices.addStretch(1)
        method_layout.addLayout(method_choices)
        self.method_help = QLabel(method_group)
        self.method_help.setObjectName("vascular-registration-method-help")
        self.method_help.setAccessibleName("Transform model constraints and distortion warning")
        self.method_help.setWordWrap(True)
        method_layout.addWidget(self.method_help)
        controls_layout.addWidget(method_group)

        self.add_landmark_button = QPushButton("Add landmark", controls)
        self.add_landmark_button.setAccessibleName("Add vascular landmark")
        controls_layout.addWidget(self.add_landmark_button)

        self.rows_scroll = QScrollArea(controls)
        self.rows_scroll.setObjectName("vascular-landmark-scroll-area")
        self.rows_scroll.setAccessibleName("Vascular landmark editors")
        self.rows_scroll.setWidgetResizable(True)
        self.rows_container = QWidget(self.rows_scroll)
        self.rows_container.setObjectName("vascular-landmark-editors")
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.addStretch(1)
        self.rows_scroll.setWidget(self.rows_container)
        controls_layout.addWidget(self.rows_scroll, 1)

        self.fit_button = QPushButton("Fit current landmarks", controls)
        self.fit_button.setAccessibleName("Fit current vascular landmarks")
        controls_layout.addWidget(self.fit_button)
        self.fit_summary = QLabel("No successful current fit.", controls)
        self.fit_summary.setObjectName("vascular-registration-fit-summary")
        self.fit_summary.setAccessibleName("Registration RMS and maximum residuals")
        self.fit_summary.setWordWrap(True)
        controls_layout.addWidget(self.fit_summary)
        self.inline_error = QLabel("", controls)
        self.inline_error.setObjectName("vascular-registration-inline-error")
        self.inline_error.setAccessibleName("Registration error")
        self.inline_error.setWordWrap(True)
        self.inline_error.setStyleSheet("color: #b00020; font-weight: 600;")
        controls_layout.addWidget(self.inline_error)

        self.laterality_checkbox = QCheckBox(
            "I confirm the specimen image left/right orientation has been verified",
            controls,
        )
        self.laterality_checkbox.setObjectName("vascular-registration-laterality-confirmation")
        self.laterality_checkbox.setAccessibleName("Confirm subject image left right orientation")
        controls_layout.addWidget(self.laterality_checkbox)
        laterality_note = QLabel(
            "Required before saving. Matrix handedness cannot prove image laterality; verify "
            "left/right against the specimen and acquisition record.",
            controls,
        )
        laterality_note.setObjectName("vascular-registration-laterality-warning")
        laterality_note.setAccessibleName("Image laterality warning")
        laterality_note.setWordWrap(True)
        controls_layout.addWidget(laterality_note)
        body.addWidget(controls, 2)
        root.addLayout(body, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.setAccessibleName("Save or cancel vascular registration")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self.active_button_group = QButtonGroup(self)
        self.active_button_group.setExclusive(True)
        self.add_landmark_button.clicked.connect(self._add_empty_landmark)
        self.fit_button.clicked.connect(self.fit_current_landmarks)
        self.similarity_radio.toggled.connect(self._method_changed)
        self.affine_radio.toggled.connect(self._method_changed)
        self.laterality_checkbox.toggled.connect(self._laterality_changed)

        for landmark in prior_landmarks:
            self._append_landmark_row(landmark)
        if not self.landmark_rows:
            self._append_landmark_row(None)
        self.landmark_rows[0].active_radio.setChecked(True)
        self._method_changed()
        self._update_save_button()

    @property
    def method(self) -> DorsalRegistrationMethod:
        """Return the currently requested transform family."""

        if self.affine_radio.isChecked():
            return DorsalRegistrationMethod.AFFINE
        return DorsalRegistrationMethod.SIMILARITY

    @property
    def current_registration(self) -> DorsalVascularRegistration | None:
        """Return the successful fit for the current editable inputs, if any."""

        return self._current_registration

    @property
    def registration(self) -> DorsalVascularRegistration | None:
        """Return the registration committed by an accepted dialog."""

        return self._accepted_registration

    def _add_empty_landmark(self, *_args: object) -> None:
        self._append_landmark_row(None)
        self.landmark_rows[-1].active_radio.setChecked(True)
        self._invalidate_fit("Landmark added; fit the current inputs before saving.")

    def _append_landmark_row(self, landmark: DorsalVascularLandmark | None) -> None:
        extent_ap, _, extent_ml = self.atlas_metadata.extent_um
        row = LandmarkEditorRow(
            row_number=len(self.landmark_rows) + 1,
            landmark=landmark,
            image_width_px=self.subject_image.width_px,
            image_height_px=self.subject_image.height_px,
            atlas_extent_ap_um=extent_ap,
            atlas_extent_ml_um=extent_ml,
            parent=self.rows_container,
        )
        row.changed.connect(self._row_changed)
        row.active_changed.connect(self._row_active_changed)
        row.remove_requested.connect(self._remove_requested_row)
        self.active_button_group.addButton(row.active_radio)
        self.landmark_rows.append(row)
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        self._update_canvas_markers()

    def _remove_requested_row(self) -> None:
        sender = self.sender()
        if not isinstance(sender, LandmarkEditorRow) or sender not in self.landmark_rows:
            return
        was_active = sender.active_radio.isChecked()
        self.active_button_group.removeButton(sender.active_radio)
        self.landmark_rows.remove(sender)
        self.rows_layout.removeWidget(sender)
        sender.deleteLater()
        for index, row in enumerate(self.landmark_rows, start=1):
            row.set_row_number(index)
        if was_active and self.landmark_rows:
            self.landmark_rows[0].active_radio.setChecked(True)
        self._invalidate_fit("Landmark removed; fit the current inputs before saving.")
        self._update_canvas_markers()

    def _row_changed(self) -> None:
        self._invalidate_fit("Landmark input changed; fit the current inputs before saving.")
        self._update_canvas_markers()

    def _row_active_changed(self, checked: bool) -> None:
        if checked:
            self.inline_error.clear()
        self._update_canvas_markers()

    def _place_active_landmark(self, column_px: int, row_px: int) -> None:
        active = next((row for row in self.landmark_rows if row.active_radio.isChecked()), None)
        if active is None:
            self._show_error("Select a landmark's 'Place with image click' control first.")
            return
        active.column_spin.setValue(float(column_px))
        active.row_spin.setValue(float(row_px))
        self._update_canvas_markers()

    def _update_canvas_markers(self) -> None:
        self.canvas.set_markers(tuple(row.canvas_marker() for row in self.landmark_rows))

    def _method_changed(self, *_args: object) -> None:
        if self.method is DorsalRegistrationMethod.AFFINE:
            self.method_help.setText(
                "Affine requires at least 3 enabled, non-collinear landmarks in both image and "
                "atlas space. It permits independent scaling and shear, which can distort "
                "vascular anatomy; use only when the acquisition protocol justifies it."
            )
        else:
            self.method_help.setText(
                "Similarity requires at least 2 enabled, distinct landmarks and permits only "
                "translation, rotation, and uniform scale. Redundant landmarks reveal residuals."
            )
        if hasattr(self, "fit_summary"):
            self._invalidate_fit("Transform model changed; fit the current inputs before saving.")

    def _laterality_changed(self, checked: bool) -> None:
        if self._current_registration is not None:
            self._current_registration = self._current_registration.model_copy(
                update={"laterality_confirmed_by_user": checked}
            )
        if checked:
            self.inline_error.clear()
        self._update_save_button()

    def fit_current_landmarks(self, *_args: object) -> None:
        """Run the domain fitter and present every failure inline."""

        self.inline_error.clear()
        try:
            landmarks = tuple(row.to_landmark() for row in self.landmark_rows)
            extent_ap, _, extent_ml = self.atlas_metadata.extent_um
            registration = fit_dorsal_vascular_registration(
                image=self.subject_image,
                atlas_key=self.atlas_metadata.atlas_key,
                atlas_version=self.atlas_metadata.atlas_package_version,
                atlas_extent_ap_um=extent_ap,
                atlas_extent_ml_um=extent_ml,
                landmarks=landmarks,
                method=self.method,
                laterality_confirmed_by_user=self.laterality_checkbox.isChecked(),
            )
        except (ValidationError, VascularRegistrationError, ValueError) as error:
            self._invalidate_fit("No successful current fit.")
            self._show_error(self._format_fit_error(error))
            return

        self._current_registration = registration
        self.fit_summary.setText(
            f"Successful {registration.method.value} fit — RMS residual: "
            f"{registration.rms_residual_um:.3f} µm; maximum residual: "
            f"{registration.max_residual_um:.3f} µm; determinant: "
            f"{registration.determinant:+.6g}."
        )
        residual_by_id = {item.landmark_uuid: item for item in registration.residuals}
        for row, landmark in zip(self.landmark_rows, registration.landmarks, strict=True):
            residual = residual_by_id.get(landmark.landmark_uuid)
            if residual is None:
                row.residual_label.setText("Residual: excluded because this landmark is disabled")
            else:
                row.set_residual(
                    radial_um=residual.radial_error_um,
                    ap_error_um=residual.ap_error_um,
                    ml_error_um=residual.ml_error_um,
                )
        self._update_save_button()

    def _format_fit_error(self, error: Exception) -> str:
        if isinstance(error, ValidationError):
            first = error.errors(include_url=False)[0]
            return f"Landmark input error: {first['msg']}"
        return str(error)

    def _invalidate_fit(self, summary: str) -> None:
        self._current_registration = None
        self.fit_summary.setText(summary)
        for row in self.landmark_rows:
            row.residual_label.setText("Residual: fit required")
        self._update_save_button()

    def _show_error(self, message: str) -> None:
        self.inline_error.setText(message)
        self.inline_error.show()

    def _update_save_button(self) -> None:
        button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        button.setEnabled(
            self._current_registration is not None
            and self.laterality_checkbox.isChecked()
            and self._current_registration.laterality_confirmed_by_user
        )

    def accept(self) -> None:
        """Commit only a successful current fit with explicit laterality review."""

        if self._current_registration is None:
            self._show_error("Run a successful fit for the current landmark inputs before saving.")
            return
        if not self.laterality_checkbox.isChecked():
            self._show_error("Confirm the specimen image left/right orientation before saving.")
            return
        self._accepted_registration = self._current_registration.model_copy(
            update={"laterality_confirmed_by_user": True}
        )
        self._retire_active_row()
        super().accept()

    def reject(self) -> None:
        """Discard any committed result and clear active-row state before hiding."""

        self._accepted_registration = None
        self._retire_active_row()
        super().reject()

    def _retire_active_row(self) -> None:
        self.active_button_group.setExclusive(False)
        for row in self.landmark_rows:
            row.active_radio.setChecked(False)
        self.active_button_group.setExclusive(True)
