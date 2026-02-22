"""
clipforge.music – Background-music mixing
==========================================

* Accepts a local audio file **or** a YouTube URL (auto-downloaded).
* Loops the music if it's shorter than the clip.
* Ducks the music volume during speech (simple envelope).
* Mixes into the final clip at a user-defined volume ratio.
"""
from __future__ import annotations

import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FileNotFoundError("ffmpeg not found on PATH")
    return path


def prepare_music(
    source: str | Path,
    work_dir: str | Path,
) -> Path:
    """Resolve *source* to a local audio file.

    If *source* is a YouTube URL, download the audio track.
    """
    from clipforge.downloader import is_youtube_url, download_audio

    work_dir = Path(work_dir)
    if is_youtube_url(str(source)):
        log.info("Downloading background music from YouTube …")
        return download_audio(str(source), work_dir)
    p = Path(source)
    if not p.exists():
        raise FileNotFoundError(f"Music file not found: {source}")
    return p


def mix_music(
    video_path: str | Path,
    music_path: str | Path,
    output_path: str | Path,
    *,
    music_volume: float = 0.10,
    duck_during_speech: bool = True,
    speech_threshold_db: float = -30.0,
) -> Path:
    """Mix *music_path* under the audio track of *video_path*.

    Parameters
    ----------
    music_volume:
        Base volume of the music track relative to the original audio
        (0.0 – 1.0).  Default 0.10 (10 %).
    duck_during_speech:
        If True, apply a simple side-chain compression filter so the
        music dips when speech is detected.
    speech_threshold_db:
        RMS threshold above which the original audio is considered
        "speech" and the music is ducked.

    Returns
    -------
    Path to the output file with mixed audio.
    """
    video_path = Path(video_path)
    music_path = Path(music_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _ffmpeg()

    # Build the complex audio filter graph
    if duck_during_speech:
        # Side-chain duck: use the original audio's volume envelope to
        # lower the music track automatically.
        af = (
            f"[1:a]aloop=loop=-1:size=2e+09,atrim=start=0:end=duration_placeholder,asetpts=PTS-STARTPTS,"
            f"volume={music_volume}[music];"
            f"[0:a]asplit=2[speech][sc];"
            f"[sc]agate=threshold={speech_threshold_db}dB:attack=80:release=400[gate];"
            f"[music][gate]sidechaincompress=threshold=0.02:ratio=6:attack=200:release=1000[ducked];"
            f"[speech][ducked]amix=inputs=2:duration=first:dropout_transition=2[out]"
        )
    else:
        af = (
            f"[1:a]aloop=loop=-1:size=2e+09,atrim=start=0:end=duration_placeholder,asetpts=PTS-STARTPTS,"
            f"volume={music_volume}[music];"
            f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[out]"
        )

    # We need the duration of the input video to trim the looped music.
    duration = _probe_duration(video_path)
    af = af.replace("duration_placeholder", str(duration))

    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-i", str(music_path),
        "-filter_complex", af,
        "-map", "0:v",
        "-map", "[out]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    log.info("Mixing music → %s", output_path)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg music-mix failed:\n%s", result.stderr[-2000:])
        raise RuntimeError("ffmpeg music-mix failed – see log for details")

    return output_path


def _probe_duration(video_path: Path) -> float:
    """Use ffprobe to get the duration in seconds."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        ffprobe = shutil.which("ffprobe.exe")
    if not ffprobe:
        # Rough fallback: 60 seconds
        return 60.0

    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 60.0
