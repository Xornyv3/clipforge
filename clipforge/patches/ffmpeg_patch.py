"""
Patch: FFmpeg / moviepy compatibility
--------------------------------------
* Sets the ``IMAGEIO_FFMPEG_EXE`` env-var so moviepy / imageio don't try
  to auto-download an FFmpeg binary when one is already on PATH.
* Silences the ``moviepy`` tqdm / progress-bar noise.
* Adds ``FFMPEG_BINARY`` for older moviepy versions that check that name.
"""
from __future__ import annotations

import os
import shutil
import warnings


def patch() -> None:
    warnings.filterwarnings("ignore", module="moviepy")

    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        os.environ.setdefault("IMAGEIO_FFMPEG_EXE", ffmpeg_bin)
        os.environ.setdefault("FFMPEG_BINARY", ffmpeg_bin)
    else:
        # Let imageio-ffmpeg fall back to its bundled binary
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            os.environ.setdefault("IMAGEIO_FFMPEG_EXE", exe)
            os.environ.setdefault("FFMPEG_BINARY", exe)
        except Exception:
            pass

    # Ensure ffprobe is also exposed (used by pydub, etc.)
    ffprobe_bin = shutil.which("ffprobe")
    if ffprobe_bin:
        os.environ.setdefault("FFPROBE_BINARY", ffprobe_bin)
