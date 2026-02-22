"""Download and mix background music into video clips.

Music can come from a YouTube URL (downloaded via yt-dlp) or a local
audio file.  The track is looped if shorter than the video, faded in
and out, and mixed under the original dialogue at a configurable volume.
"""

import os
import shutil
import subprocess
from pathlib import Path

from . import utils
from .downloader import is_url


def prepare_music(source: str, output_dir: str) -> str:
    """Obtain a music file — download from URL or validate a local path.

    Returns the absolute path to the audio file.
    """
    os.makedirs(output_dir, exist_ok=True)

    if is_url(source):
        return _download_music(source, output_dir)

    if not os.path.isfile(source):
        raise FileNotFoundError(f"Music file not found: {source}")

    utils.log(f"Using local music: {source}")
    return os.path.abspath(source)


def mix(
    video_path: str,
    music_path: str,
    output_path: str,
    music_volume: float = 0.15,
    fade_duration: float = 2.0,
) -> str:
    """Layer background music under a video's existing audio track.

    Parameters
    ----------
    video_path : str
        Source video with dialogue.
    music_path : str
        Background music file.
    output_path : str
        Destination path.
    music_volume : float
        Music loudness relative to the original audio (0.0–1.0).
    fade_duration : float
        Seconds of fade-in at the start and fade-out at the end.

    Returns
    -------
    str
        Path to the mixed output file.
    """
    vid_dur = utils.get_duration(video_path)
    fade_out_start = max(0, vid_dur - fade_duration)

    utils.log(f"Mixing background music (volume={music_volume:.0%})...")

    af = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=duration={vid_dur},"
        f"afade=t=in:st=0:d={fade_duration},"
        f"afade=t=out:st={fade_out_start}:d={fade_duration},"
        f"volume={music_volume}[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[out]"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-filter_complex", af,
            "-map", "0:v",
            "-map", "[out]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ],
        check=True,
        capture_output=True,
    )

    utils.log("Music mixed successfully")
    return output_path


# ------------------------------------------------------------------

def _download_music(url: str, output_dir: str) -> str:
    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp is required for music download.  pip install yt-dlp")

    template = os.path.join(output_dir, "bg_music.%(ext)s")
    utils.log(f"Downloading music from: {url}")

    subprocess.run(
        [
            "yt-dlp",
            "-x", "--audio-format", "mp3",
            "--audio-quality", "192K",
            "-o", template,
            "--no-playlist",
            url,
        ],
        check=True,
    )

    for f in Path(output_dir).glob("bg_music.*"):
        if f.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg", ".opus"):
            utils.log(f"Downloaded music: {f.name}")
            return str(f)

    raise FileNotFoundError("Music download finished but audio file not found.")
