"""Versioned stdio bridge for native application shells.

The bridge deliberately has no GUI imports.  A SwiftUI process can own every
native macOS window while this package remains the validated scientific and
atlas-data backend.
"""

from __future__ import annotations

PROTOCOL_VERSION = 1

__all__ = ["PROTOCOL_VERSION"]
