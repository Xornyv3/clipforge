"""
clipforge.downloader – Fetch media from YouTube or resolve local paths
======================================================================
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Regex that matches most YouTube URL variants
_YT_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]{11})"
)


def is_youtube_url(source: str) -> bool:
    """Return *True* if *source* looks like a YouTube URL."""
    return bool(_YT_RE.search(source))


def _best_ytdlp() -> str:
    """Return path to yt-dlp (or fall back to youtube-dl)."""
    for name in ("yt-dlp", "yt-dlp.exe", "youtube-dl", "youtube-dl.exe"):
        path = shutil.which(name)
        if path:
            return path
    raise FileNotFoundError(
        "Neither yt-dlp nor youtube-dl found on PATH.  Install with:\n"
        "  pip install yt-dlp"
    )


def download_youtube(
    url: str,
    output_dir: str | Path,
    *,
    max_height: int = 1080,
    audio_only: bool = False,
) -> Path:
    """Download a YouTube video and return the path to the saved file.

    Parameters
    ----------
    url:
        Full or short YouTube URL.
    output_dir:
        Directory where the file will be saved.
    max_height:
        Maximum vertical resolution (default 1080p).
    audio_only:
        If *True* download only the audio stream (m4a/opus).

    Returns
    -------
    Path to the downloaded file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ytdlp = _best_ytdlp()
    outtmpl = str(output_dir / "%(title).80s_%(id)s.%(ext)s")

    cmd: list[str] = [ytdlp, "--no-playlist", "--restrict-filenames"]

    if audio_only:
        cmd += ["-x", "--audio-format", "mp3", "-o", outtmpl, url]
    else:
        fmt = (
            f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best"
        )
        cmd += [
            "-f", fmt,
            "--merge-output-format", "mp4",
            "-o", outtmpl,
            url,
        ]

    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{result.stderr}")

    # yt-dlp prints the final filename in its output – parse it
    downloaded = _parse_output_filename(result.stdout, output_dir)
    if downloaded and downloaded.exists():
        log.info("Downloaded → %s", downloaded)
        return downloaded

    # Fallback: pick the newest file in output_dir
    files = sorted(output_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        return files[0]

    raise FileNotFoundError("Download succeeded but output file not found.")


def _parse_output_filename(stdout: str, output_dir: Path) -> Optional[Path]:
    """Try to extract the downloaded filename from yt-dlp stdout."""
    for line in reversed(stdout.splitlines()):
        # yt-dlp: [Merger] Merging formats into "..."
        # yt-dlp: [download] ... has already been downloaded
        # yt-dlp: [download] Destination: ...
        for marker in (
            "Merging formats into",
            "Destination:",
            "has already been downloaded",
        ):
            if marker in line:
                # grab the quoted filename or the text after the marker
                m = re.search(r'"([^"]+)"', line)
                if m:
                    return Path(m.group(1))
                tail = line.split(marker, 1)[-1].strip().strip('"')
                if tail:
                    return Path(tail)
    return None


def resolve_source(source: str, work_dir: str | Path) -> Path:
    """Given a local path **or** YouTube URL, return a local file path.

    If *source* is a YouTube URL the video is downloaded into *work_dir*.
    """
    if is_youtube_url(source):
        return download_youtube(source, work_dir)
    p = Path(source)
    if not p.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    return p


def download_audio(url: str, work_dir: str | Path) -> Path:
    """Download *only* the audio track from a YouTube URL (for background music)."""
    return download_youtube(url, work_dir, audio_only=True)
