"""PyInstaller entry point for Brain3D's versioned NDJSON bridge."""

from mouse_brain_planner.bridge.server import main

if __name__ == "__main__":
    raise SystemExit(main())
