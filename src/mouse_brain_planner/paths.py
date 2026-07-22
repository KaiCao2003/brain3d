"""Application-owned filesystem locations.

Atlas packages are intentionally kept outside project files and application
bundles.  All locations can be overridden for tests and managed deployments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path, user_config_path, user_data_path

APP_NAME = "Mouse Brain Surgery Planner"
APP_AUTHOR = "Mouse Brain Planner"


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Resolved application directories."""

    config: Path
    data: Path
    cache: Path
    atlas_cache: Path
    download_cache: Path

    def ensure(self) -> None:
        """Create application directories if they do not already exist."""

        for path in (
            self.config,
            self.data,
            self.cache,
            self.atlas_cache,
            self.download_cache,
        ):
            path.mkdir(parents=True, exist_ok=True)


def app_paths() -> AppPaths:
    """Return platform-appropriate, overrideable application paths."""

    config = Path(
        os.environ.get(
            "MOUSE_BRAIN_PLANNER_CONFIG_DIR",
            user_config_path(APP_NAME, APP_AUTHOR),
        )
    )
    data = Path(
        os.environ.get(
            "MOUSE_BRAIN_PLANNER_DATA_DIR",
            user_data_path(APP_NAME, APP_AUTHOR),
        )
    )
    cache = Path(
        os.environ.get(
            "MOUSE_BRAIN_PLANNER_CACHE_DIR",
            user_cache_path(APP_NAME, APP_AUTHOR),
        )
    )
    return AppPaths(
        config=config,
        data=data,
        cache=cache,
        atlas_cache=data / "atlases",
        download_cache=cache / "atlas-downloads",
    )


def configure_brainglobe_environment(paths: AppPaths | None = None) -> AppPaths:
    """Set BrainGlobe's import-time configuration directory.

    This function must run before importing :mod:`brainglobe_atlasapi`.
    Explicit cache paths are still passed to ``BrainGlobeAtlas``; the
    environment variable only prevents untracked config writes elsewhere.
    """

    resolved = paths or app_paths()
    resolved.ensure()
    brainglobe_config = (resolved.config / "brainglobe").resolve()
    # The application owns its atlas cache and configuration contract.  An
    # inherited shell value must not redirect BrainGlobe's process-global
    # catalog reads or config writes into an unrelated user directory.
    os.environ["BRAINGLOBE_CONFIG_DIR"] = str(brainglobe_config)
    brainglobe_config.mkdir(parents=True, exist_ok=True)
    return resolved
