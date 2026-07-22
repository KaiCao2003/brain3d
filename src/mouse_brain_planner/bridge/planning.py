"""Project and subject-vasculature methods for the native hybrid bridge."""

from __future__ import annotations

import base64
import io
import math
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from uuid import UUID

import numpy as np
from PIL import Image
from pydantic import ValidationError

from mouse_brain_planner.bridge import PROTOCOL_VERSION
from mouse_brain_planner.bridge.calibration import register_calibration_handlers
from mouse_brain_planner.bridge.implant_targets import register_implant_target_handlers
from mouse_brain_planner.bridge.probe_planning import register_probe_planning_handlers
from mouse_brain_planner.bridge.server import (
    SUPPORTED_ATLAS_IDENTIFIER,
    SUPPORTED_ATLAS_VERSION,
    BridgeDispatcher,
    BridgeError,
    JsonObject,
    LoadedAtlasProtocol,
    encode_rgb_png,
)
from mouse_brain_planner.bridge.viewer_state import (
    ViewerStateBridge,
    register_viewer_state_handlers,
)
from mouse_brain_planner.coordinates.atlas_space import BrainGlobeAtlasSpace
from mouse_brain_planner.domain.atlas_models import AtlasMetadata
from mouse_brain_planner.domain.coordinate_models import BrainGlobeVoxelIndex
from mouse_brain_planner.domain.project_models import PlannerProject, ViewerSliceDepths
from mouse_brain_planner.domain.vessel_models import (
    DorsalRegistrationMethod,
    DorsalVascularLandmark,
    ReferenceVascularDensityProjectState,
    SubjectVascularImage,
    SubjectVascularOverlayState,
    VascularLandmarkKind,
)
from mouse_brain_planner.persistence.project_io import (
    ProjectIntegrityError,
    load_project_with_provenance,
    normalize_project_path,
    save_project,
)
from mouse_brain_planner.rendering.dorsal_surface import render_dorsal_surface
from mouse_brain_planner.vasculature.density_overlay import (
    REFERENCE_DENSITY_DV_MAXIMUM_LABEL,
    REFERENCE_DENSITY_PROJECTION_DISCLOSURE,
    REFERENCE_DENSITY_PROJECTION_OPACITY,
    REFERENCE_DENSITY_PROJECTION_WINDOW_HIGH,
    REFERENCE_DENSITY_PROJECTION_WINDOW_LOW,
    ReferenceDensityAtlasBinding,
    ReferenceDensityHeatmapStyle,
    render_reference_density_dv_maximum_projection,
)
from mouse_brain_planner.vasculature.reference_density import STXVN5SV44_V1_SOURCE
from mouse_brain_planner.vasculature.reference_store import (
    PINNED_REFERENCE_DOWNLOAD_URL,
    REFERENCE_PREPARATION_ALGORITHM,
    CachedReferenceDensity,
    ReferenceDensityCacheError,
    ReferenceDensityStore,
    ReferenceDensityStoreProtocol,
)
from mouse_brain_planner.vasculature.registration import (
    VascularRegistrationError,
    fit_dorsal_vascular_registration,
)
from mouse_brain_planner.vasculature.subject_image import (
    SubjectImageImportError,
    import_subject_vascular_image,
    verify_subject_vascular_image,
)
from mouse_brain_planner.vasculature.subject_overlay import (
    SubjectOverlayRenderError,
    render_registered_dorsal_overlay,
)

MAX_PATH_CHARACTERS: Final = 4096
MAX_LANDMARKS: Final = 128
# A worst-case uncompressed RGBA preview plus base64 framing remains below the
# native client's 8 MiB response limit at this edge length.
MAX_PREVIEW_EDGE_PX: Final = 1024
ANIMAL_ONLY_WARNING: Final = "Animal research only — not for human or clinical use"


@dataclass(slots=True)
class PlanningBridgeSession:
    """Mutable project state isolated behind versioned bridge handlers."""

    dispatcher: BridgeDispatcher
    reference_density_store: ReferenceDensityStoreProtocol = field(
        default_factory=ReferenceDensityStore
    )
    project: PlannerProject | None = None
    project_path: Path | None = None
    asset_source_package: Path | None = None
    recovered_from_backup: bool = False
    project_revision: int = 0
    saved_revision: int | None = None
    _temporary: tempfile.TemporaryDirectory[str] = field(
        default_factory=lambda: tempfile.TemporaryDirectory(prefix="mouse-brain-planner-session.")
    )
    _working_package: Path | None = None
    _reference_density_cache: CachedReferenceDensity | None = None
    _reference_density_cache_error: str | None = None
    _viewer_state: ViewerStateBridge | None = None

    def register(self) -> None:
        """Install project handlers and replace the placeholder state snapshot."""

        self.dispatcher.register("state.get", self.state_get, replace=True)
        self.dispatcher.register("atlas.dorsal", self.atlas_dorsal)
        self.dispatcher.register("project.new", self.project_new)
        self.dispatcher.register("project.open", self.project_open)
        self.dispatcher.register("project.save", self.project_save)
        self.dispatcher.register("vascular.import", self.vascular_import)
        self.dispatcher.register("vascular.preview", self.vascular_preview)
        self.dispatcher.register("vascular.register", self.vascular_register)
        self.dispatcher.register("vascular.overlay", self.vascular_overlay)
        self.dispatcher.register("vascular.reference.prepare", self.vascular_reference_prepare)
        self.dispatcher.register("vascular.reference.display", self.vascular_reference_display)
        self.dispatcher.register("vascular.reference.overlay", self.vascular_reference_overlay)
        register_implant_target_handlers(
            self.dispatcher,
            get_project=self._require_project,
            replace_project=self._replace_project_after_implant_mutation,
        )
        self._viewer_state = register_viewer_state_handlers(
            self.dispatcher,
            get_project=self._require_project,
            get_revision=lambda: self.project_revision,
            replace_project=self._replace_project_after_viewer_mutation,
        )
        register_calibration_handlers(
            self.dispatcher,
            get_project=self._require_project,
            get_revision=lambda: self.project_revision,
            replace_project=self._replace_project_after_calibration_mutation,
        )
        register_probe_planning_handlers(
            self.dispatcher,
            get_project=self._require_project,
            get_revision=lambda: self.project_revision,
            replace_project=self._replace_project_after_probe_mutation,
            get_atlas=self._require_loaded_atlas,
        )
        self.dispatcher.declare_capability("populationReferenceDensityPrepare")
        self.dispatcher.declare_capability("populationReferenceDensityDisplayMutation")
        self.dispatcher.declare_capability("populationReferenceDensityOverlay")

    def atlas_dorsal(self, params: Mapping[str, object]) -> JsonObject:
        """Return the real atlas dorsal-boundary projection on the AP/ML grid."""

        _validate_params(params, required={"protocolVersion"})
        _require_protocol(params)
        atlas = self._require_loaded_atlas()
        try:
            frame = render_dorsal_surface(
                atlas.reference,
                atlas.annotation,
                resolution_um=atlas.metadata.resolution_um,
            )
            encoded = encode_rgb_png(frame.rgb)
        except (TypeError, ValueError) as error:
            raise BridgeError(
                "DORSAL_SURFACE_RENDER_FAILED",
                "The atlas dorsal surface projection could not be rendered safely.",
                details={"exceptionType": type(error).__name__},
            ) from error
        height, width = frame.rgb.shape[:2]
        surface_indices = frame.surface_dv_index[frame.brain_mask]
        minimum_dv_um = (
            None
            if surface_indices.size == 0
            else (int(surface_indices.min()) + 0.5) * frame.dv_resolution_um
        )
        maximum_dv_um = (
            None
            if surface_indices.size == 0
            else (int(surface_indices.max()) + 0.5) * frame.dv_resolution_um
        )
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "mimeType": "image/png",
            "pngBase64": base64.b64encode(encoded).decode("ascii"),
            "width": int(width),
            "height": int(height),
            "rowAxis": frame.row_axis,
            "columnAxis": frame.column_axis,
            "surfaceDvMinimumMicrometres": minimum_dv_um,
            "surfaceDvMaximumMicrometres": maximum_dv_um,
            "displayLabel": frame.display_label,
            "surfaceDefinition": (
                "First nonzero annotation voxel along inferior-increasing BrainGlobe DV"
            ),
            "atlas": {
                "identifier": atlas.metadata.atlas_key,
                "version": atlas.metadata.atlas_package_version,
                "resolutionMicrometres": list(atlas.metadata.resolution_um),
                "orientation": atlas.metadata.standardized_orientation,
            },
        }

    def state_get(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(params, required={"protocolVersion"})
        _require_protocol(params)
        atlas = self.dispatcher.context.loaded_atlas
        project = self.project
        if atlas is None:
            atlas_state: JsonObject = {
                "identifier": SUPPORTED_ATLAS_IDENTIFIER,
                "version": SUPPORTED_ATLAS_VERSION,
                "loaded": False,
                "status": "notLoaded",
            }
        else:
            atlas_state = {
                "identifier": atlas.metadata.atlas_key,
                "version": atlas.metadata.atlas_package_version,
                "loaded": True,
                "status": "loaded",
            }

        images: list[JsonObject] = []
        if project is not None:
            registrations = {
                registration.registration_uuid: registration
                for registration in project.dorsal_vascular_registrations
            }
            overlays = {
                overlay.image_uuid: overlay for overlay in project.subject_vascular_overlays
            }
            for image in project.subject_vascular_images:
                overlay = overlays.get(image.image_uuid)
                registration = (
                    registrations.get(overlay.registration_uuid)
                    if overlay is not None and overlay.registration_uuid is not None
                    else None
                )
                images.append(
                    {
                        **_image_result(image),
                        "registered": registration is not None,
                        "registrationId": (
                            None if registration is None else str(registration.registration_uuid)
                        ),
                        "residualMicrometres": (
                            None if registration is None else registration.rms_residual_um
                        ),
                        "maximumResidualMicrometres": (
                            None if registration is None else registration.max_residual_um
                        ),
                        "lateralityConfirmed": (
                            False
                            if registration is None
                            else registration.laterality_confirmed_by_user
                        ),
                        "visible": False if overlay is None else overlay.visible,
                    }
                )
        primary_image = images[-1] if images else None
        reference_state = None if project is None else project.reference_vascular_density
        reference_available = (
            project is not None
            and reference_state is not None
            and self._reference_density_cache is not None
            and _reference_cache_matches_project_state(
                self._reference_density_cache,
                reference_state,
                project.atlas,
            )
        )
        viewer = None
        if project is not None:
            if self._viewer_state is None:
                raise BridgeError(
                    "VIEWER_STATE_UNAVAILABLE",
                    "The independent slice viewer handlers are not registered.",
                )
            viewer = self._viewer_state.snapshot(project, self.project_revision)
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "animalOnly": True,
            "warning": ANIMAL_ONLY_WARNING,
            "atlas": atlas_state,
            "project": (
                None
                if project is None
                else {
                    "projectId": str(project.project_uuid),
                    "title": project.title,
                    "subjectId": project.subject_id,
                    "path": None if self.project_path is None else str(self.project_path),
                    "requiresSaveAs": self.project_path is None,
                    "recoveredFromBackup": self.recovered_from_backup,
                    "schemaVersion": project.schema_version,
                    "revision": self.project_revision,
                    "isDirty": self.saved_revision != self.project_revision,
                    "animalResearchOnlyAcknowledged": (project.scientific_disclaimer_acknowledged),
                    "calibrationCount": len(project.calibrations),
                    "activeCalibrationId": (
                        None
                        if project.active_calibration_uuid is None
                        else str(project.active_calibration_uuid)
                    ),
                    "probePlanCount": len(project.probe_plans),
                    "probeRegionAnalysisCount": len(project.probe_region_analyses),
                }
            ),
            "viewer": viewer,
            "subjectVessels": {
                "imported": bool(images),
                "registered": any(bool(item["registered"]) for item in images),
                "sourceName": (None if primary_image is None else primary_image["sourceName"]),
                "residualMicrometres": (
                    None if primary_image is None else primary_image["residualMicrometres"]
                ),
                "lateralityConfirmed": (
                    False if primary_image is None else bool(primary_image["lateralityConfirmed"])
                ),
                "images": images,
            },
            "populationDensity": {
                "available": reference_available,
                "visible": bool(
                    reference_available and reference_state is not None and reference_state.visible
                ),
                "status": (
                    "notLoaded"
                    if reference_state is None
                    else (
                        "preparedReferenceDensity"
                        if reference_available
                        else "preparedCacheUnavailable"
                    )
                ),
                "opacity": (
                    REFERENCE_DENSITY_PROJECTION_OPACITY
                    if reference_state is None
                    else reference_state.opacity
                ),
                "disclaimer": (
                    "Population reference vascular length density — not subject-specific "
                    "vessel paths"
                ),
            },
        }

    def project_new(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={"protocolVersion", "animalResearchOnlyAcknowledged"},
            optional={"title", "subjectId"},
        )
        _require_protocol(params)
        if params["animalResearchOnlyAcknowledged"] is not True:
            raise BridgeError(
                "ANIMAL_ONLY_ACKNOWLEDGEMENT_REQUIRED",
                f"Creating a project requires acknowledgement: {ANIMAL_ONLY_WARNING}.",
            )
        atlas = self._require_loaded_atlas()
        title = _optional_text(params.get("title"), field_name="title", maximum=200)
        subject_id = _optional_text(params.get("subjectId"), field_name="subjectId", maximum=200)
        space = BrainGlobeAtlasSpace(atlas.metadata)
        shape = atlas.metadata.shape_voxels
        centre_index = BrainGlobeVoxelIndex(
            atlas_key=atlas.metadata.atlas_key,
            atlas_version=atlas.metadata.atlas_package_version,
            ap=shape[0] // 2,
            dv=shape[1] // 2,
            ml=shape[2] // 2,
        )
        centre = space.index_to_center(centre_index)
        try:
            project = PlannerProject(
                title=title or "Untitled animal surgery plan",
                subject_id=subject_id,
                atlas=atlas.metadata,
                linked_cursor=centre,
                renderer_anchor=centre,
                viewer_slice_depths=ViewerSliceDepths(
                    coronal=centre_index.ap,
                    sagittal=centre_index.ml,
                    horizontal=centre_index.dv,
                ),
                scientific_disclaimer_acknowledged=True,
            )
        except ValidationError as error:  # defensive atlas/project integration boundary
            raise BridgeError(
                "PROJECT_CREATE_FAILED",
                "The project could not be bound to the loaded atlas.",
                details={"validationErrors": error.error_count()},
            ) from error
        project.touch("project-created", ANIMAL_ONLY_WARNING)
        self.project = project
        self.project_path = None
        self.asset_source_package = None
        self.recovered_from_backup = False
        self.project_revision = 1
        self.saved_revision = None
        self._working_package = None
        self._reference_density_cache = None
        self._reference_density_cache_error = None
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "created",
            "projectId": str(project.project_uuid),
            "title": project.title,
            "subjectId": project.subject_id,
            "animalOnly": True,
            "warning": ANIMAL_ONLY_WARNING,
        }

    def project_open(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(params, required={"protocolVersion", "path"})
        _require_protocol(params)
        path = _absolute_path(params["path"], field_name="path")
        atlas = self._require_loaded_atlas()
        try:
            result = load_project_with_provenance(path)
        except (OSError, ValueError, ValidationError, ProjectIntegrityError) as error:
            raise BridgeError(
                "PROJECT_OPEN_FAILED",
                "The project package failed validation and was not opened.",
                details={"exceptionType": type(error).__name__},
            ) from error
        project = result.project
        if project.atlas is None:
            raise BridgeError(
                "PROJECT_ATLAS_REQUIRED",
                "The native planner requires an atlas-bound project.",
            )
        if not _same_atlas(project.atlas, atlas.metadata):
            raise BridgeError(
                "PROJECT_ATLAS_MISMATCH",
                "The project atlas does not exactly match the loaded atlas.",
                details={
                    "projectIdentifier": project.atlas.atlas_key,
                    "projectVersion": project.atlas.atlas_package_version,
                    "loadedIdentifier": atlas.metadata.atlas_key,
                    "loadedVersion": atlas.metadata.atlas_package_version,
                },
            )
        if not project.scientific_disclaimer_acknowledged:
            raise BridgeError(
                "ANIMAL_ONLY_ACKNOWLEDGEMENT_REQUIRED",
                "The project does not record the required animal-only acknowledgement.",
            )
        if project.viewer_slice_depths is None:
            anchor = project.linked_cursor or project.renderer_anchor
            if anchor is None:  # guarded by the project model, retained defensively
                raise BridgeError(
                    "VIEWER_STATE_UNAVAILABLE",
                    "The atlas-bound project cannot initialize independent slice depths.",
                )
            anchor_index = BrainGlobeAtlasSpace(atlas.metadata).physical_to_index(anchor)
            project = project.model_copy(
                update={
                    "viewer_slice_depths": ViewerSliceDepths(
                        coronal=anchor_index.ap,
                        sagittal=anchor_index.ml,
                        horizontal=anchor_index.dv,
                    ),
                    "viewer_region_selection": None,
                }
            )
        self.project = project
        self.project_path = result.writable_path
        self.asset_source_package = result.source_path
        self.recovered_from_backup = result.recovered_from_backup or result.requires_save_as
        self.project_revision = 0
        self.saved_revision = None if result.requires_save_as else 0
        self._working_package = None
        self._restore_reference_density_cache(project, atlas)
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "opened",
            "projectId": str(project.project_uuid),
            "title": project.title,
            "sourcePath": str(result.source_path),
            "requiresSaveAs": result.requires_save_as,
            "recoveredFromBackup": result.recovered_from_backup,
            "subjectVascularImageCount": len(project.subject_vascular_images),
        }

    def project_save(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(params, required={"protocolVersion"}, optional={"path"})
        _require_protocol(params)
        project = self._require_project()
        raw_path = params.get("path")
        destination = (
            self.project_path if raw_path is None else _absolute_path(raw_path, field_name="path")
        )
        if destination is None:
            raise BridgeError(
                "PROJECT_SAVE_PATH_REQUIRED",
                "This project has no writable path; choose a Save As destination.",
            )
        destination = normalize_project_path(destination)
        previous = project.model_copy(deep=True)
        previous_revision = self.project_revision
        project.touch("project-saved")
        self.project_revision += 1
        try:
            saved = save_project(
                project,
                destination,
                asset_source_package=self.asset_source_package,
            )
        except (OSError, ValueError, ValidationError, ProjectIntegrityError) as error:
            self.project = previous
            self.project_revision = previous_revision
            raise BridgeError(
                "PROJECT_SAVE_FAILED",
                "The project was left unchanged because its atomic save failed.",
                details={"exceptionType": type(error).__name__},
            ) from error
        self.project_path = saved
        self.asset_source_package = saved
        self.recovered_from_backup = False
        self.saved_revision = self.project_revision
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "saved",
            "path": str(saved),
            "projectId": str(project.project_uuid),
        }

    def vascular_import(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={"protocolVersion", "path"},
            optional={"pixelSizeXMicrometres", "pixelSizeYMicrometres"},
        )
        _require_protocol(params)
        project = self._require_project()
        source = _absolute_path(params["path"], field_name="path")
        pixel_x = _optional_positive_number(
            params.get("pixelSizeXMicrometres"), field_name="pixelSizeXMicrometres"
        )
        pixel_y = _optional_positive_number(
            params.get("pixelSizeYMicrometres"), field_name="pixelSizeYMicrometres"
        )
        working = self._ensure_working_package()
        try:
            image = import_subject_vascular_image(
                source,
                package_root=working,
                pixel_size_x_um=pixel_x,
                pixel_size_y_um=pixel_y,
            )
            payload = project.model_dump(mode="python")
            payload["subject_vascular_images"] = [*project.subject_vascular_images, image]
            payload["subject_vascular_overlays"] = [
                *project.subject_vascular_overlays,
                SubjectVascularOverlayState(image_uuid=image.image_uuid, opacity=0.65),
            ]
            updated = PlannerProject.model_validate(payload)
        except (OSError, ValueError, ValidationError, SubjectImageImportError) as error:
            raise BridgeError(
                "VASCULAR_IMPORT_FAILED",
                "The subject dorsal image was not imported.",
                details={"exceptionType": type(error).__name__},
            ) from error
        updated.touch(
            "subject-vascular-image-imported",
            f"{image.original_name}; sha256={image.source_sha256}",
        )
        self.project = updated
        self.asset_source_package = working
        self.project_revision += 1
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "imported",
            "image": _image_result(image),
            "warning": (
                "Subject-specific surface image — registration and laterality must be verified"
            ),
        }

    def vascular_preview(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(params, required={"protocolVersion", "imageId"})
        _require_protocol(params)
        image = self._find_image(params["imageId"])
        source = self._verified_image_path(image)
        try:
            with Image.open(source) as opened:
                opened.seek(0)
                preview = opened.convert("RGBA")
                preview.thumbnail(
                    (MAX_PREVIEW_EDGE_PX, MAX_PREVIEW_EDGE_PX),
                    Image.Resampling.LANCZOS,
                )
                encoded = io.BytesIO()
                preview.save(encoded, format="PNG", optimize=False)
                preview_width, preview_height = preview.size
        except OSError as error:
            raise BridgeError(
                "VASCULAR_PREVIEW_FAILED",
                "The verified subject image could not be decoded for display.",
                details={"exceptionType": type(error).__name__},
            ) from error
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "imageId": str(image.image_uuid),
            "mimeType": "image/png",
            "pngBase64": base64.b64encode(encoded.getvalue()).decode("ascii"),
            "originalWidthPixels": image.width_px,
            "originalHeightPixels": image.height_px,
            "previewWidthPixels": preview_width,
            "previewHeightPixels": preview_height,
            "previewToOriginalScaleX": image.width_px / preview_width,
            "previewToOriginalScaleY": image.height_px / preview_height,
            "coordinateFrame": image.coordinate_frame,
        }

    def vascular_register(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={
                "protocolVersion",
                "imageId",
                "method",
                "landmarks",
                "lateralityConfirmed",
            },
            optional={"opacity"},
        )
        _require_protocol(params)
        project = self._require_project()
        atlas = self._require_loaded_atlas()
        image = self._find_image(params["imageId"])
        method = _registration_method(params["method"])
        landmarks = _landmarks(params["landmarks"])
        laterality = params["lateralityConfirmed"]
        if not isinstance(laterality, bool):
            raise BridgeError(
                "INVALID_PARAMS",
                "lateralityConfirmed must be a boolean.",
                details={"field": "lateralityConfirmed"},
            )
        opacity = _opacity(params.get("opacity", 0.65))
        versions = [
            registration.version
            for registration in project.dorsal_vascular_registrations
            if registration.image_uuid == image.image_uuid
        ]
        try:
            registration = fit_dorsal_vascular_registration(
                image=image,
                atlas_key=atlas.metadata.atlas_key,
                atlas_version=atlas.metadata.atlas_package_version,
                atlas_extent_ap_um=atlas.metadata.extent_um[0],
                atlas_extent_ml_um=atlas.metadata.extent_um[2],
                landmarks=landmarks,
                method=method,
                version=max(versions, default=0) + 1,
                laterality_confirmed_by_user=laterality,
            )
            replacement = SubjectVascularOverlayState(
                image_uuid=image.image_uuid,
                registration_uuid=registration.registration_uuid,
                visible=laterality,
                opacity=opacity,
            )
            payload = project.model_dump(mode="python")
            payload["dorsal_vascular_registrations"] = [
                *project.dorsal_vascular_registrations,
                registration,
            ]
            payload["subject_vascular_overlays"] = [
                replacement if item.image_uuid == image.image_uuid else item
                for item in project.subject_vascular_overlays
            ]
            updated = PlannerProject.model_validate(payload)
        except (ValueError, ValidationError, VascularRegistrationError) as error:
            raise BridgeError(
                "VASCULAR_REGISTRATION_FAILED",
                "The dorsal image registration was rejected; review its landmarks.",
                details={"exceptionType": type(error).__name__},
            ) from error
        updated.touch(
            "subject-vascular-image-registered",
            f"method={registration.method.value}; rms={registration.rms_residual_um:g} µm; "
            f"max={registration.max_residual_um:g} µm; laterality={laterality}",
        )
        self.project = updated
        self.project_revision += 1
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "registered",
            "registrationId": str(registration.registration_uuid),
            "version": registration.version,
            "method": registration.method.value,
            "matrixRowMajor": list(registration.matrix_row_major),
            "rmsResidualMicrometres": registration.rms_residual_um,
            "maximumResidualMicrometres": registration.max_residual_um,
            "redundantControlPoints": registration.redundant_control_points,
            "lateralityConfirmed": registration.laterality_confirmed_by_user,
            "visible": replacement.visible,
            "warning": registration.laterality_warning,
            "residuals": [
                {
                    "landmarkId": str(residual.landmark_uuid),
                    "apErrorMicrometres": residual.ap_error_um,
                    "mlErrorMicrometres": residual.ml_error_um,
                    "radialErrorMicrometres": residual.radial_error_um,
                }
                for residual in registration.residuals
            ],
        }

    def vascular_overlay(self, params: Mapping[str, object]) -> JsonObject:
        _validate_params(
            params,
            required={"protocolVersion", "imageId"},
            optional={"opacity"},
        )
        _require_protocol(params)
        project = self._require_project()
        atlas = self._require_loaded_atlas()
        image = self._find_image(params["imageId"])
        overlay_state = next(
            (
                item
                for item in project.subject_vascular_overlays
                if item.image_uuid == image.image_uuid
            ),
            None,
        )
        if overlay_state is None or overlay_state.registration_uuid is None:
            raise BridgeError(
                "VASCULAR_REGISTRATION_REQUIRED",
                "Register the subject image before requesting its atlas overlay.",
            )
        registration = next(
            (
                item
                for item in project.dorsal_vascular_registrations
                if item.registration_uuid == overlay_state.registration_uuid
            ),
            None,
        )
        if registration is None:
            raise BridgeError(
                "VASCULAR_REGISTRATION_REQUIRED",
                "The active subject-image registration is missing.",
            )
        if not registration.laterality_confirmed_by_user:
            raise BridgeError(
                "VASCULAR_LATERALITY_CONFIRMATION_REQUIRED",
                "Confirm the subject image left/right orientation before displaying it.",
            )
        opacity = _opacity(params.get("opacity", overlay_state.opacity))
        source_package = self.asset_source_package
        if source_package is None:
            raise BridgeError(
                "VASCULAR_ASSET_UNAVAILABLE",
                "The verified subject-image package is unavailable.",
            )
        try:
            rendered = render_registered_dorsal_overlay(
                image=image,
                registration=registration,
                package_root=source_package,
                atlas=atlas.metadata,
                opacity=opacity,
            )
            encoded = io.BytesIO()
            Image.fromarray(rendered.rgba, mode="RGBA").save(
                encoded,
                format="PNG",
                optimize=False,
            )
        except (OSError, ValueError, SubjectOverlayRenderError) as error:
            raise BridgeError(
                "VASCULAR_OVERLAY_FAILED",
                "The registered subject image could not be rendered on the atlas grid.",
                details={"exceptionType": type(error).__name__},
            ) from error
        height, width = rendered.rgba.shape[:2]
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "imageId": str(image.image_uuid),
            "registrationId": str(registration.registration_uuid),
            "mimeType": "image/png",
            "pngBase64": base64.b64encode(encoded.getvalue()).decode("ascii"),
            "width": int(width),
            "height": int(height),
            "rowAxis": rendered.row_axis,
            "columnAxis": rendered.column_axis,
            "resolutionMicrometres": [
                rendered.resolution_ap_um,
                rendered.resolution_ml_um,
            ],
            "subjectSpecific": True,
            "displayLabel": rendered.display_label,
            "rmsResidualMicrometres": registration.rms_residual_um,
            "maximumResidualMicrometres": registration.max_residual_um,
            "lateralityConfirmed": registration.laterality_confirmed_by_user,
        }

    def vascular_reference_prepare(self, params: Mapping[str, object]) -> JsonObject:
        """Prepare the one pinned population source against the exact loaded atlas."""

        _validate_params(
            params,
            required={"protocolVersion", "downloadIfMissing"},
            optional={"archivePath"},
        )
        _require_protocol(params)
        project = self._require_project()
        atlas = self._require_loaded_atlas()
        download_if_missing = params["downloadIfMissing"]
        if not isinstance(download_if_missing, bool):
            raise BridgeError(
                "INVALID_PARAMS",
                "downloadIfMissing must be a boolean.",
                details={"field": "downloadIfMissing"},
            )
        raw_archive_path = params.get("archivePath")
        archive_path = (
            None
            if raw_archive_path is None
            else _absolute_path(raw_archive_path, field_name="archivePath")
        )
        try:
            cached = self.reference_density_store.prepare(
                atlas=atlas.metadata,
                atlas_reference_asr=atlas.reference,
                archive_path=archive_path,
                download_if_missing=download_if_missing,
            )
            state = _reference_project_state(cached, atlas.metadata)
            payload = project.model_dump(mode="python")
            payload["reference_vascular_density"] = state
            updated = PlannerProject.model_validate(payload)
        except (OSError, ValueError, ValidationError, ReferenceDensityCacheError) as error:
            raise BridgeError(
                "REFERENCE_DENSITY_PREPARATION_FAILED",
                "The pinned population reference density was not prepared.",
                details={"exceptionType": type(error).__name__},
            ) from error
        updated.touch(
            "population-reference-density-prepared",
            f"doi={STXVN5SV44_V1_SOURCE.doi}; "
            f"archive_sha256={STXVN5SV44_V1_SOURCE.archive_sha256}; "
            f"prepared_sha256={cached.prepared_density_sha256}",
        )
        self.project = updated
        self._reference_density_cache = cached
        self._reference_density_cache_error = None
        self.project_revision += 1
        return _reference_prepare_result(cached, atlas.metadata)

    def vascular_reference_display(self, params: Mapping[str, object]) -> JsonObject:
        """Persist the complete population-density display state as one mutation."""

        _validate_params(
            params,
            required={"protocolVersion", "visible", "opacity"},
        )
        _require_protocol(params)
        project = self._require_project()
        state = project.reference_vascular_density
        if state is None:
            raise BridgeError(
                "REFERENCE_DENSITY_NOT_PREPARED",
                "Prepare and verify the population reference density before changing its display.",
            )
        visible = params["visible"]
        if not isinstance(visible, bool):
            raise BridgeError(
                "INVALID_PARAMS",
                "visible must be a boolean.",
                details={"field": "visible"},
            )
        opacity = _opacity(params["opacity"])
        if visible and opacity <= 0:
            raise BridgeError(
                "INVALID_PARAMS",
                "opacity must be greater than zero when visible is true.",
                details={"field": "opacity"},
            )
        if visible and (
            self._reference_density_cache is None
            or not _reference_cache_matches_project_state(
                self._reference_density_cache,
                state,
                project.atlas,
            )
        ):
            raise BridgeError(
                "REFERENCE_DENSITY_NOT_PREPARED",
                "The verified population reference cache is unavailable and cannot be shown.",
            )

        try:
            updated_state = state.model_copy(
                update={"visible": visible, "opacity": opacity},
            )
            payload = project.model_dump(mode="python")
            payload["reference_vascular_density"] = updated_state
            updated = PlannerProject.model_validate(payload)
        except (ValueError, ValidationError) as error:
            raise BridgeError(
                "REFERENCE_DENSITY_DISPLAY_UPDATE_FAILED",
                "The population density display state could not be stored safely.",
                details={"exceptionType": type(error).__name__},
            ) from error
        updated.touch(
            "population-reference-density-display-updated",
            f"visible={str(visible).lower()}; opacity={opacity:g}",
        )
        self.project = updated
        self.project_revision += 1
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "updatedReferenceDensityDisplay",
            "display": {
                "visible": updated_state.visible,
                "opacity": updated_state.opacity,
            },
        }

    def vascular_reference_overlay(self, params: Mapping[str, object]) -> JsonObject:
        """Return the truthful transparent DV-maximum population projection."""

        _validate_params(params, required={"protocolVersion"})
        _require_protocol(params)
        project = self._require_project()
        atlas = self._require_loaded_atlas()
        state = project.reference_vascular_density
        cached = self._reference_density_cache
        if (
            state is None
            or cached is None
            or not _reference_cache_matches_project_state(cached, state, project.atlas)
        ):
            raise BridgeError(
                "REFERENCE_DENSITY_NOT_PREPARED",
                "Prepare and verify the population reference density before requesting it.",
            )
        if not state.visible:
            raise BridgeError(
                "REFERENCE_DENSITY_NOT_VISIBLE",
                "Enable the persisted population reference display before requesting its overlay.",
            )
        try:
            binding = ReferenceDensityAtlasBinding(
                density=cached.density,
                atlas_shape_asr=atlas.metadata.shape_voxels,
                atlas_resolution_um=atlas.metadata.resolution_um,
            )
            brain_mask_ap_ml = np.any(np.asarray(atlas.annotation) != 0, axis=1)
            projection = render_reference_density_dv_maximum_projection(
                binding,
                style=ReferenceDensityHeatmapStyle(
                    opacity=state.opacity,
                    window_low=REFERENCE_DENSITY_PROJECTION_WINDOW_LOW,
                    window_high=REFERENCE_DENSITY_PROJECTION_WINDOW_HIGH,
                ),
                brain_mask_ap_ml=brain_mask_ap_ml,
            )
            encoded = io.BytesIO()
            Image.fromarray(projection.rgba, mode="RGBA").save(
                encoded,
                format="PNG",
                optimize=False,
            )
        except (OSError, TypeError, ValueError) as error:
            raise BridgeError(
                "REFERENCE_DENSITY_OVERLAY_FAILED",
                "The population density projection could not be rendered safely.",
                details={"exceptionType": type(error).__name__},
            ) from error
        height, width = projection.rgba.shape[:2]
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "status": "renderedReferenceDensity",
            "mimeType": "image/png",
            "pngBase64": base64.b64encode(encoded.getvalue()).decode("ascii"),
            "width": int(width),
            "height": int(height),
            "rowAxis": projection.row_axis,
            "columnAxis": projection.column_axis,
            "projectionAxis": projection.projection_axis,
            "projectionMethod": projection.projection_method,
            "atlasResolutionMicrometres": [
                projection.atlas_resolution_ap_um,
                projection.atlas_resolution_ml_um,
            ],
            "densityResolutionMicrometres": projection.density_resolution_um,
            "window": {
                "low": REFERENCE_DENSITY_PROJECTION_WINDOW_LOW,
                "high": REFERENCE_DENSITY_PROJECTION_WINDOW_HIGH,
                "units": STXVN5SV44_V1_SOURCE.density_value_units,
                "opacity": state.opacity,
                "colorMap": "red-to-magenta",
            },
            "display": {
                "visible": state.visible,
                "opacity": state.opacity,
            },
            "source": {
                "doi": STXVN5SV44_V1_SOURCE.doi,
                "version": STXVN5SV44_V1_SOURCE.version,
                "archiveSha256": STXVN5SV44_V1_SOURCE.archive_sha256,
            },
            "atlas": {
                "identifier": atlas.metadata.atlas_key,
                "version": atlas.metadata.atlas_package_version,
                "metadataSha256": atlas.metadata.metadata_sha256,
            },
            "subjectSpecific": False,
            "containsIndividualVesselPaths": False,
            "supportsVesselClearance": False,
            "displayLabel": REFERENCE_DENSITY_DV_MAXIMUM_LABEL,
            "disclosure": REFERENCE_DENSITY_PROJECTION_DISCLOSURE,
        }

    def _restore_reference_density_cache(
        self,
        project: PlannerProject,
        atlas: LoadedAtlasProtocol,
    ) -> None:
        self._reference_density_cache = None
        self._reference_density_cache_error = None
        state = project.reference_vascular_density
        if state is None:
            return
        try:
            cached = self.reference_density_store.load_cached(
                atlas=atlas.metadata,
                atlas_reference_asr=atlas.reference,
            )
            if cached is None or not _reference_cache_matches_project_state(
                cached,
                state,
                project.atlas,
            ):
                self._reference_density_cache_error = "prepared cache is missing or mismatched"
                return
        except (OSError, ValueError, ReferenceDensityCacheError) as error:
            self._reference_density_cache_error = type(error).__name__
            return
        self._reference_density_cache = cached

    def _require_loaded_atlas(self) -> LoadedAtlasProtocol:
        atlas = self.dispatcher.context.loaded_atlas
        if atlas is None:
            raise BridgeError(
                "ATLAS_NOT_OPEN",
                "Open the reviewed 25 micrometre atlas before using a project.",
            )
        return atlas

    def _require_project(self) -> PlannerProject:
        if self.project is None:
            raise BridgeError("PROJECT_NOT_OPEN", "Create or open a project first.")
        return self.project

    def _replace_project_after_implant_mutation(self, project: PlannerProject) -> None:
        """Publish one validated implant mutation and mark the session dirty."""

        self.project = project
        self.project_revision += 1

    def _replace_project_after_viewer_mutation(self, project: PlannerProject) -> int:
        """Publish one independent viewer mutation and return its new revision."""

        self.project = project
        self.project_revision += 1
        return self.project_revision

    def _replace_project_after_calibration_mutation(self, project: PlannerProject) -> int:
        """Publish one validated calibration mutation and return its revision."""

        self.project = project
        self.project_revision += 1
        return self.project_revision

    def _replace_project_after_probe_mutation(self, project: PlannerProject) -> int:
        """Publish one validated probe/analysis mutation and return its revision."""

        self.project = project
        self.project_revision += 1
        return self.project_revision

    def _find_image(self, raw_image_id: object) -> SubjectVascularImage:
        project = self._require_project()
        image_id = _uuid(raw_image_id, field_name="imageId")
        image = next(
            (item for item in project.subject_vascular_images if item.image_uuid == image_id),
            None,
        )
        if image is None:
            raise BridgeError(
                "VASCULAR_IMAGE_NOT_FOUND",
                "The requested subject vascular image is not in the current project.",
            )
        return image

    def _verified_image_path(self, image: SubjectVascularImage) -> Path:
        if self.asset_source_package is None:
            raise BridgeError(
                "VASCULAR_ASSET_UNAVAILABLE",
                "The verified subject-image package is unavailable.",
            )
        try:
            return verify_subject_vascular_image(
                image,
                package_root=self.asset_source_package,
            )
        except (OSError, ValueError, SubjectImageImportError) as error:
            raise BridgeError(
                "VASCULAR_ASSET_UNAVAILABLE",
                "The subject-image checksum or package boundary failed verification.",
                details={"exceptionType": type(error).__name__},
            ) from error

    def _ensure_working_package(self) -> Path:
        project = self._require_project()
        if self._working_package is not None:
            return self._working_package
        root = Path(self._temporary.name)
        working = Path(tempfile.mkdtemp(prefix="working.", dir=root)) / "assets.mouseplan"
        if project.subject_vascular_images:
            if self.asset_source_package is None:
                raise BridgeError(
                    "VASCULAR_ASSET_UNAVAILABLE",
                    "Existing subject-image assets have no verified source package.",
                )
            try:
                save_project(
                    project,
                    working,
                    asset_source_package=self.asset_source_package,
                )
            except (OSError, ValueError, ValidationError, ProjectIntegrityError) as error:
                raise BridgeError(
                    "VASCULAR_ASSET_UNAVAILABLE",
                    "Existing subject-image assets could not be staged for editing.",
                    details={"exceptionType": type(error).__name__},
                ) from error
        else:
            working.mkdir(parents=True)
        self._working_package = working
        return working


def _reference_project_state(
    cached: CachedReferenceDensity,
    atlas: AtlasMetadata,
) -> ReferenceVascularDensityProjectState:
    provenance = cached.density.provenance
    return ReferenceVascularDensityProjectState(
        target_atlas_key=atlas.atlas_key,
        target_atlas_version=atlas.atlas_package_version,
        target_atlas_metadata_sha256=atlas.metadata_sha256,
        output_shape_asr=provenance.output_shape_asr,
        output_voxel_size_um=provenance.output_voxel_size_um,
        template_correlation=provenance.template_alignment.correlation,
        minimum_template_correlation=provenance.template_alignment.minimum_correlation,
        preparation_algorithm=REFERENCE_PREPARATION_ALGORITHM,
        prepared_density_sha256=cached.prepared_density_sha256,
        visible=False,
        opacity=REFERENCE_DENSITY_PROJECTION_OPACITY,
    )


def _reference_cache_matches_project_state(
    cached: CachedReferenceDensity,
    state: ReferenceVascularDensityProjectState,
    atlas: AtlasMetadata | None,
) -> bool:
    if atlas is None:
        return False
    provenance = cached.density.provenance
    alignment = provenance.template_alignment
    return (
        state.target_atlas_key == atlas.atlas_key
        and state.target_atlas_version == atlas.atlas_package_version
        and state.target_atlas_metadata_sha256 == atlas.metadata_sha256
        and cached.atlas_metadata_sha256 == atlas.metadata_sha256
        and state.preparation_algorithm == REFERENCE_PREPARATION_ALGORITHM
        and state.prepared_density_sha256 == cached.prepared_density_sha256
        and state.source_archive_sha256 == provenance.source.archive_sha256
        and state.output_shape_asr == provenance.output_shape_asr
        and state.output_voxel_size_um == provenance.output_voxel_size_um
        and math.isclose(
            state.template_correlation,
            alignment.correlation,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        and math.isclose(
            state.minimum_template_correlation,
            alignment.minimum_correlation,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        and state.ap_axis_reversed
        and state.ml_symmetrized
        and not state.subject_specific
        and not state.contains_individual_vessel_paths
        and not state.supports_vessel_clearance
        and cached.archive_sha256_verified
    )


def _reference_prepare_result(
    cached: CachedReferenceDensity,
    atlas: AtlasMetadata,
) -> JsonObject:
    provenance = cached.density.provenance
    source = provenance.source
    alignment = provenance.template_alignment
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "status": "preparedReferenceDensity",
        "source": {
            "doi": source.doi,
            "version": source.version,
            "landingPageUrl": source.landing_page_url,
            "downloadUrl": PINNED_REFERENCE_DOWNLOAD_URL,
            "archiveFilename": source.archive_filename,
            "archiveSizeBytes": source.archive_size_bytes,
            "archiveSha256": source.archive_sha256,
            "densityMemberPath": source.density_member_path,
            "templateMemberPath": source.template_member_path,
        },
        "atlas": {
            "identifier": atlas.atlas_key,
            "version": atlas.atlas_package_version,
            "metadataSha256": atlas.metadata_sha256,
            "resolutionMicrometres": list(atlas.resolution_um),
            "shapeVoxels": list(atlas.shape_voxels),
            "orientation": atlas.standardized_orientation,
        },
        "density": {
            "valueUnits": source.density_value_units,
            "populationSubjectCount": source.population_subject_count,
            "rollingWindowMicrometres": source.rolling_window_um,
            "outputShapeASR": list(provenance.output_shape_asr),
            "outputResolutionMicrometres": provenance.output_voxel_size_um,
            "templateCorrelation": alignment.correlation,
            "minimumTemplateCorrelation": alignment.minimum_correlation,
            "apAxisReversed": provenance.ap_axis_reversed,
            "mlSymmetrized": provenance.ml_symmetrized,
            "subjectSpecific": provenance.subject_specific,
            "containsIndividualVesselPaths": provenance.contains_individual_vessel_paths,
            "supportsVesselClearance": provenance.supports_vessel_clearance,
        },
        "cache": {
            "archiveSha256Verified": cached.archive_sha256_verified,
            "preparedDensitySha256": cached.prepared_density_sha256,
            "reusedPreparedCache": cached.reused_prepared_cache,
        },
        "disclosure": REFERENCE_DENSITY_PROJECTION_DISCLOSURE,
    }


def register_planning_handlers(
    dispatcher: BridgeDispatcher,
    *,
    reference_density_store: ReferenceDensityStoreProtocol | None = None,
) -> PlanningBridgeSession:
    """Register project/vessel protocol methods and return their session state."""

    session = PlanningBridgeSession(
        dispatcher,
        reference_density_store=(reference_density_store or ReferenceDensityStore()),
    )
    session.register()
    return session


def _validate_params(
    params: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    actual = set(params)
    if actual != allowed and (required - actual or actual - allowed):
        raise BridgeError(
            "INVALID_PARAMS",
            "The method parameters do not match the protocol-v1 schema.",
            details={
                "missing": sorted(required - actual),
                "unexpected": sorted(actual - allowed),
            },
        )


def _require_protocol(params: Mapping[str, object]) -> None:
    value = params["protocolVersion"]
    if isinstance(value, bool) or not isinstance(value, int) or value != PROTOCOL_VERSION:
        raise BridgeError(
            "PROTOCOL_VERSION_MISMATCH",
            f"protocolVersion must equal {PROTOCOL_VERSION}.",
            details={"supported": PROTOCOL_VERSION},
        )


def _absolute_path(value: object, *, field_name: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_PATH_CHARACTERS
        or "\x00" in value
    ):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be a nonempty path of at most {MAX_PATH_CHARACTERS} characters.",
            details={"field": field_name},
        )
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be an absolute path.",
            details={"field": field_name},
        )
    return path


def _optional_text(value: object, *, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must contain 1 to {maximum} characters when supplied.",
            details={"field": field_name},
        )
    return value.strip()


def _optional_positive_number(value: object, *, field_name: str) -> float | None:
    if value is None:
        return None
    return _positive_number(value, field_name=field_name)


def _positive_number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be a positive finite number.",
            details={"field": field_name},
        )
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be a positive finite number.",
            details={"field": field_name},
        )
    return number


def _finite_number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be a finite number.",
            details={"field": field_name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be a finite number.",
            details={"field": field_name},
        )
    return number


def _opacity(value: object) -> float:
    number = _finite_number(value, field_name="opacity")
    if not 0 <= number <= 1:
        raise BridgeError(
            "INVALID_PARAMS",
            "opacity must be within [0, 1].",
            details={"field": "opacity"},
        )
    return number


def _uuid(value: object, *, field_name: str) -> UUID:
    if not isinstance(value, str):
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be a UUID string.",
            details={"field": field_name},
        )
    try:
        return UUID(value)
    except ValueError as error:
        raise BridgeError(
            "INVALID_PARAMS",
            f"{field_name} must be a UUID string.",
            details={"field": field_name},
        ) from error


def _registration_method(value: object) -> DorsalRegistrationMethod:
    if not isinstance(value, str):
        raise BridgeError("INVALID_PARAMS", "method must be similarity or affine.")
    try:
        return DorsalRegistrationMethod(value)
    except ValueError as error:
        raise BridgeError("INVALID_PARAMS", "method must be similarity or affine.") from error


def _landmarks(value: object) -> tuple[DorsalVascularLandmark, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BridgeError("INVALID_PARAMS", "landmarks must be an array.")
    if len(value) > MAX_LANDMARKS:
        raise BridgeError(
            "INVALID_PARAMS",
            f"landmarks may contain at most {MAX_LANDMARKS} entries.",
        )
    results: list[DorsalVascularLandmark] = []
    required = {
        "label",
        "kind",
        "imageColumnPixels",
        "imageRowPixels",
        "atlasApMicrometres",
        "atlasMlMicrometres",
        "enabled",
    }
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise BridgeError(
                "INVALID_PARAMS",
                "Every landmark must contain the exact protocol-v1 fields.",
                details={"field": f"landmarks[{index}]"},
            )
        label = _optional_text(raw["label"], field_name=f"landmarks[{index}].label", maximum=200)
        kind_value = raw["kind"]
        try:
            kind = VascularLandmarkKind(kind_value)
        except (TypeError, ValueError) as error:
            raise BridgeError(
                "INVALID_PARAMS",
                "landmark kind is unsupported.",
                details={"field": f"landmarks[{index}].kind"},
            ) from error
        enabled = raw["enabled"]
        if not isinstance(enabled, bool):
            raise BridgeError(
                "INVALID_PARAMS",
                "landmark enabled must be a boolean.",
                details={"field": f"landmarks[{index}].enabled"},
            )
        try:
            results.append(
                DorsalVascularLandmark(
                    label=label or "landmark",
                    kind=kind,
                    image_column_px=_finite_number(
                        raw["imageColumnPixels"],
                        field_name=f"landmarks[{index}].imageColumnPixels",
                    ),
                    image_row_px=_finite_number(
                        raw["imageRowPixels"],
                        field_name=f"landmarks[{index}].imageRowPixels",
                    ),
                    atlas_ap_um=_finite_number(
                        raw["atlasApMicrometres"],
                        field_name=f"landmarks[{index}].atlasApMicrometres",
                    ),
                    atlas_ml_um=_finite_number(
                        raw["atlasMlMicrometres"],
                        field_name=f"landmarks[{index}].atlasMlMicrometres",
                    ),
                    enabled=enabled,
                )
            )
        except ValidationError as error:
            raise BridgeError(
                "INVALID_PARAMS",
                "landmark validation failed.",
                details={"field": f"landmarks[{index}]"},
            ) from error
    return tuple(results)


def _image_result(image: SubjectVascularImage) -> JsonObject:
    return {
        "imageId": str(image.image_uuid),
        "sourceName": image.original_name,
        "sourceSha256": image.source_sha256,
        "byteSize": image.byte_size,
        "format": image.image_format.value,
        "widthPixels": image.width_px,
        "heightPixels": image.height_px,
        "frameCount": image.frame_count,
        "calibrated": image.calibrated,
        "pixelSizeXMicrometres": image.pixel_size_x_um,
        "pixelSizeYMicrometres": image.pixel_size_y_um,
        "coordinateFrame": image.coordinate_frame,
        "subjectSpecific": True,
    }


def _same_atlas(left: AtlasMetadata, right: AtlasMetadata) -> bool:
    return left.model_dump(exclude={"cache_path"}) == right.model_dump(exclude={"cache_path"})
