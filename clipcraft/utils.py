"""Shared utility functions used across ClipCraft modules."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

def check_ffmpeg():
    """Exit immediately if ffmpeg / ffprobe are not on PATH."""
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            print(
                f"[clipcraft] Error: '{tool}' not found on PATH.\n"
                f"  Install it from https://ffmpeg.org/download.html"
            )
            sys.exit(1)


# ---------------------------------------------------------------------------
# Media helpers (thin wrappers around ffprobe / ffmpeg)
# ---------------------------------------------------------------------------

def get_duration(file_path: str) -> float:
    """Return the duration of a media file in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def get_resolution(video_path: str) -> tuple:
    """Return (width, height) of a video's first video stream."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    w, h = result.stdout.strip().split("x")
    return int(w), int(h)


def extract_audio(video_path: str, output_path: str = None) -> str:
    """Extract mono 16 kHz WAV audio from a video (required by Whisper)."""
    if output_path is None:
        output_path = str(Path(video_path).with_suffix(".wav"))

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_path,
        ],
        capture_output=True,
    )
    return output_path


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def safe_filename(name: str) -> str:
    """Strip characters that are unsafe in file names."""
    return re.sub(r'[^\w\-.]', '_', name)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str):
    """Print a timestamped status line."""
    print(f"[clipcraft] {msg}")
