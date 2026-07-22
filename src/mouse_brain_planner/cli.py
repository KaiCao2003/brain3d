"""Explicit command-line entry points for the headless scientific service."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from mouse_brain_planner.paths import configure_brainglobe_environment
from mouse_brain_planner.version import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line parser."""

    parser = argparse.ArgumentParser(prog="mouse-brain-planner")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("bridge", help="run the NDJSON scientific service on stdin/stdout")

    atlas_parser = subparsers.add_parser("atlas", help="inspect or download atlases")
    atlas_subparsers = atlas_parser.add_subparsers(dest="atlas_command", required=True)
    atlas_subparsers.add_parser("list", help="list available and cached atlases")
    download_parser = atlas_subparsers.add_parser("download", help="download one atlas")
    download_parser.add_argument("atlas_name")

    validate_parser = subparsers.add_parser(
        "validate-project",
        help="validate a project package",
    )
    validate_parser.add_argument("project")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a CLI command or launch the GUI."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    if args.command == "bridge":
        from mouse_brain_planner.bridge.server import main as bridge_main

        return bridge_main()

    if args.command == "validate-project":
        from mouse_brain_planner.persistence.project_io import validate_project

        errors = validate_project(args.project)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        print(f"Valid project: {args.project}")
        return 0

    if args.command == "atlas":
        configure_brainglobe_environment()
        from mouse_brain_planner.atlas.brainglobe_adapter import BrainGlobeAtlasRepository

        repository = BrainGlobeAtlasRepository()
        if args.atlas_command == "list":
            for record in repository.list_atlases():
                state = "cached" if record.downloaded else "remote"
                print(f"{record.name}\t{record.latest_version}\t{state}")
            return 0
        records = {record.name: record for record in repository.list_atlases()}
        selected = records.get(args.atlas_name)
        if selected is None:
            print(f"Unknown atlas: {args.atlas_name}", file=sys.stderr)
            return 2
        repository.open(
            selected.name,
            package_version=selected.latest_version,
            allow_download=True,
        )
        print(f"Downloaded and opened atlas: {selected.name} v{selected.latest_version}")
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2
