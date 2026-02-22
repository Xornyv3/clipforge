"""Apply cinematic colour grading to video clips via ffmpeg filters.

Each preset is a single ffmpeg ``-vf`` filter chain that can be used
standalone or composed with other video filters.
"""

import shutil
import subprocess

from . import utils

# Pre-built filter chains for popular looks.
PRESETS = {
    "cinematic": (
        "colorbalance=rs=-0.04:gs=-0.02:bs=0.08:rh=0.08:gh=0.03:bh=-0.04,"
        "eq=contrast=1.08:brightness=0.01:saturation=1.15:gamma=0.97,"
        "unsharp=5:5:0.4:5:5:0.0,"
        "vignette=PI/5"
    ),
    "warm": (
        "colorbalance=rs=0.06:gs=0.02:bs=-0.04:rh=0.10:gh=0.05:bh=-0.02,"
        "eq=contrast=1.05:brightness=0.02:saturation=1.20:gamma=1.0,"
        "unsharp=3:3:0.3"
    ),
    "cool": (
        "colorbalance=rs=-0.06:gs=0.00:bs=0.10:rh=-0.02:gh=0.02:bh=0.08,"
        "eq=contrast=1.10:brightness=0.00:saturation=1.05:gamma=0.95,"
        "unsharp=3:3:0.3"
    ),
    "dramatic": (
        "colorbalance=rs=-0.02:gs=-0.04:bs=0.06:rh=0.04:gh=0.00:bh=-0.02,"
        "eq=contrast=1.20:brightness=-0.02:saturation=1.25:gamma=0.90,"
        "unsharp=5:5:0.6,"
        "vignette=PI/4"
    ),
    "none": "",
}


def get_filter(preset: str = "cinematic") -> str:
    """Return the raw ffmpeg filter string for a preset."""
    if preset not in PRESETS:
        utils.log(f"Unknown preset '{preset}', falling back to 'cinematic'")
        preset = "cinematic"
    return PRESETS[preset]


def grade(input_path: str, output_path: str, preset: str = "cinematic") -> str:
    """Colour-grade a video file.

    Parameters
    ----------
    input_path : str
        Source video.
    output_path : str
        Destination for the graded video.
    preset : str
        One of ``cinematic``, ``warm``, ``cool``, ``dramatic``, ``none``.

    Returns
    -------
    str
        Path to the graded output file.
    """
    vf = get_filter(preset)

    if not vf:
        utils.log("Colour grading skipped (preset=none)")
        shutil.copy2(input_path, output_path)
        return output_path

    utils.log(f"Applying '{preset}' colour grade...")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", vf,
            "-c:a", "copy",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            output_path,
        ],
        check=True,
        capture_output=True,
    )

    utils.log("Colour grading complete")
    return output_path
