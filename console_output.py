"""Shared console-output configuration for bot entry points."""

from __future__ import annotations

import sys


def configure_utf8_output():
    """Keep Unicode and emoji logging reliable in background task runners."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass
