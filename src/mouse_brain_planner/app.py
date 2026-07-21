"""Qt application lifecycle."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

from mouse_brain_planner.gui.main_window import MainWindow
from mouse_brain_planner.logging_config import configure_logging
from mouse_brain_planner.paths import configure_brainglobe_environment
from mouse_brain_planner.version import __version__

logger = logging.getLogger(__name__)


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create or reuse the process-wide Qt application."""

    existing = QCoreApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    application = QApplication(list(argv) if argv is not None else sys.argv)
    application.setApplicationName("Mouse Brain Surgery Planner")
    application.setApplicationDisplayName("Mouse Brain Surgery Planner")
    application.setOrganizationName("Mouse Brain Planner")
    application.setApplicationVersion(__version__)
    return application


def run(
    *,
    argv: Sequence[str] | None = None,
    smoke_test: bool = False,
    no_download: bool = False,
) -> int:
    """Run the native GUI, optionally closing automatically for smoke tests."""

    paths = configure_brainglobe_environment()
    configure_logging(paths)
    logger.info("application starting", extra={"event": "application-starting"})
    application = create_application(argv)
    window = MainWindow(no_download=no_download, suppress_dialogs=smoke_test)
    window.show()
    if smoke_test:
        QTimer.singleShot(150, window.close)
        QTimer.singleShot(200, application.quit)
    exit_code = application.exec()
    logger.info(
        "application stopped",
        extra={"event": "application-stopped", "exit_code": exit_code},
    )
    return exit_code
