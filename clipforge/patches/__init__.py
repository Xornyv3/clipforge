"""
clipforge.patches – Startup compatibility patches
===================================================
These must run **before** any ML / media library is imported.
Call ``apply_all()`` once from the CLI entry-point.
"""

from clipforge.patches.torch_patch import patch as _torch
from clipforge.patches.whisper_patch import patch as _whisper
from clipforge.patches.ffmpeg_patch import patch as _ffmpeg
from clipforge.patches.numpy_patch import patch as _numpy


def apply_all() -> None:
    """Apply every patch in the correct order (silently)."""
    _numpy()
    _torch()
    _whisper()
    _ffmpeg()
