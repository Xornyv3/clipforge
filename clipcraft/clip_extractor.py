"""Extract video clips with optional aspect-ratio conversion.

Supports portrait (9:16), landscape (16:9), square (1:1), or keeping
the original ratio.  Non-matching ratios get a blurred-background fill
rather than black bars.
"""

import subprocess
from . import utils

ASPECT_CONFIGS = {
    "portrait":  {"w": 1080, "h": 1920},
    "landscape": {"w": 1920, "h": 1080},
    "square":    {"w": 1080, "h": 1080},
    "original":  None,
}


def extract(
    video_path: str,
    start: float,
    end: float,
    output_path: str,
    aspect: str = "portrait",
) -> str:
    """Cut a time range from *video_path* and reformat to *aspect*.

    When the source aspect ratio doesn't match the target, the clip is
    scaled to fit and composited over a heavily-blurred copy of itself
    so there are no black bars.

    Returns the path to the written clip.
    """
    duration = end - start
    utils.log(f"Extracting clip: {start:.1f}s – {end:.1f}s ({duration:.1f}s)")

    cfg = ASPECT_CONFIGS.get(aspect)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
    ]

    if cfg is None:
        # Keep original ratio — straight copy
        cmd.extend([
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ])
    else:
        w, h = cfg["w"], cfg["h"]
        # filter_complex:
        #   [bg] = scale-to-fill → crop → heavy box-blur
        #   [fg] = scale-to-fit  → pad transparent
        #   overlay fg on bg
        vf = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},boxblur=20:5[bg];"
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0[fg];"
            f"[bg][fg]overlay=0:0"
        )
        cmd.extend([
            "-filter_complex", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ])

    subprocess.run(cmd, check=True, capture_output=True)
    utils.log(f"Clip extracted → {output_path}")
    return output_path
