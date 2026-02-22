"""Download videos from YouTube or validate local files."""

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import utils

_URL_PATTERN = re.compile(
    r"(https?://)?(www\.)?"
    r"(youtube\.com|youtu\.be|youtube\.com/shorts|m\.youtube\.com)"
    r"/.+"
)


def is_url(source: str) -> bool:
    """Return True if *source* looks like a URL we can download."""
    return bool(_URL_PATTERN.match(source)) or source.startswith(
        ("http://", "https://")
    )


def download(source: str, output_dir: str) -> str:
    """Obtain a video file — download from YouTube or verify a local path.

    Returns
    -------
    str
        Absolute path to the video ready for processing.
    """
    os.makedirs(output_dir, exist_ok=True)

    if is_url(source):
        return _download_youtube(source, output_dir)
    return _validate_local(source)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _download_youtube(url: str, output_dir: str) -> str:
    if shutil.which("yt-dlp") is None:
        raise RuntimeError(
            "yt-dlp is not installed.  Run:  pip install yt-dlp"
        )

    output_template = os.path.join(output_dir, "source_video.%(ext)s")
    utils.log(f"Downloading video from: {url}")

    subprocess.run(
        [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--no-playlist",
            url,
        ],
        check=True,
    )

    for f in Path(output_dir).glob("source_video.*"):
        if f.suffix.lower() in (".mp4", ".mkv", ".webm"):
            utils.log(f"Downloaded: {f.name}")
            return str(f)

    raise FileNotFoundError("Download finished but video file was not found.")


def _validate_local(path: str) -> str:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")

    valid = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v"}
    ext = Path(path).suffix.lower()
    if ext not in valid:
        raise ValueError(f"Unsupported video format: {ext}")

    utils.log(f"Using local file: {path}")
    return os.path.abspath(path)
