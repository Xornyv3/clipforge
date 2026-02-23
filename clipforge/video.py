"""
clipforge.video – Clip extraction, aspect-ratio reformat & colour grading
=========================================================================

All heavy lifting is done via **ffmpeg** subprocess calls so we don't
need to decode frames in Python.

Capabilities:
* Extract a time-range from the source video.
* Reformat to portrait (9:16), square (1:1), or landscape (16:9) with
  a blurred-background pad when the source doesn't match.
* Apply a cinematic colour-grade LUT (or a built-in filter chain).
* Burn in ASS subtitles.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Aspect-ratio presets
# ---------------------------------------------------------------------------
class AspectRatio(str, Enum):
    PORTRAIT = "9:16"    # TikTok / Reels / Shorts
    LANDSCAPE = "16:9"
    SQUARE = "1:1"
    ORIGINAL = "original"

    @property
    def dimensions(self) -> tuple[int, int] | None:
        """Return (width, height) at 1080-class resolution, or *None*."""
        return {
            "9:16": (1080, 1920),
            "16:9": (1920, 1080),
            "1:1": (1080, 1080),
        }.get(self.value)


# ---------------------------------------------------------------------------
# Cinematic colour-grade filter
# ---------------------------------------------------------------------------
_CINE_GRADE = (
    # Slight contrast boost + warm shadows + lifted blacks
    "eq=contrast=1.08:brightness=0.02:saturation=1.15,"
    "curves=master='0/0 0.06/0.04 0.45/0.47 0.75/0.78 1/1'"
    ":red='0/0.02 0.5/0.52 1/0.98'"
    ":blue='0/0.04 0.5/0.48 1/0.94',"
    # Soft vignette
    "vignette=PI/5"
)


# ---------------------------------------------------------------------------
# Core ffmpeg helpers
# ---------------------------------------------------------------------------
def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        try:
            import imageio_ffmpeg
            path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            raise FileNotFoundError("ffmpeg not found on PATH and imageio-ffmpeg unavailable")
    return path


def _vf_center_crop(aspect: AspectRatio) -> str:
    """Return a video-filter string that center-crops to *aspect*.

    Fallback used when face detection is skipped or fails.
    """
    dims = aspect.dimensions
    if dims is None:
        return ""
    tw, th = dims
    ratio = tw / th
    return (
        f"crop=ih*{ratio:.6f}:ih:(iw-ih*{ratio:.6f})/2:0,"
        f"scale={tw}:{th}"
    )


# ---------------------------------------------------------------------------
# Face-detection helpers
# ---------------------------------------------------------------------------
_HAAR_CASCADE = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


def _probe_dimensions(source: str | Path) -> tuple[int, int]:
    """Return (width, height) of the first video stream via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise FileNotFoundError("ffprobe not found on PATH")
    result = subprocess.run(
        [ffprobe, "-v", "error",
         "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x",
         str(source)],
        capture_output=True, text=True,
    )
    w, h = result.stdout.strip().split("x")
    return int(w), int(h)


def _extract_sample_frames(
    source: str | Path, start: float, end: float, n_frames: int = 8
) -> list[np.ndarray]:
    """Extract *n_frames* evenly-spaced frames from [start, end] via ffmpeg."""
    duration = end - start
    timestamps = [start + duration * i / (n_frames - 1) for i in range(n_frames)]

    ffmpeg = _ffmpeg()
    frames: list[np.ndarray] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, ts in enumerate(timestamps):
            out_img = Path(tmpdir) / f"frame_{i:03d}.jpg"
            subprocess.run(
                [ffmpeg, "-y", "-ss", f"{ts:.3f}", "-i", str(source),
                 "-frames:v", "1", "-q:v", "2", str(out_img)],
                capture_output=True,
            )
            if out_img.exists():
                img = cv2.imread(str(out_img))
                if img is not None:
                    frames.append(img)
    return frames


def _detect_face_x_center(
    source: str | Path, start: float, end: float
) -> int | None:
    """Find the x-centre of the dominant face in [start, end].

    Returns the pixel x-coordinate in the source frame, or *None* if no
    faces are detected (caller should fall back to frame centre).
    """
    frames = _extract_sample_frames(source, start, end, n_frames=8)
    if not frames:
        return None

    cascade = cv2.CascadeClassifier(_HAAR_CASCADE)
    face_centers_x: list[int] = []
    face_areas: list[int] = []

    for img in frames:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )
        if len(faces) == 0:
            continue
        for (x, y, w, h) in faces:
            face_centers_x.append(x + w // 2)
            face_areas.append(w * h)

    if not face_centers_x:
        log.warning("No faces detected – falling back to centre crop")
        return None

    # Weight by face area so larger (closer) faces dominate
    total_area = sum(face_areas)
    weighted_x = sum(cx * a for cx, a in zip(face_centers_x, face_areas)) / total_area
    log.info("  Face detected at x=%.0f (from %d detections)", weighted_x, len(face_centers_x))
    return int(weighted_x)


def _vf_face_crop(
    aspect: AspectRatio,
    source: str | Path,
    start: float,
    end: float,
) -> str:
    """Build a crop filter that centres on the detected face."""
    dims = aspect.dimensions
    if dims is None:
        return ""
    tw, th = dims
    target_ar = tw / th  # e.g. 0.5625 for 9:16

    try:
        src_w, src_h = _probe_dimensions(source)
    except Exception:
        log.warning("Could not probe source dimensions – using expression-based crop")
        return _vf_center_crop(aspect)

    # Crop dimensions from the source
    crop_h = src_h
    crop_w = int(src_h * target_ar)
    if crop_w > src_w:
        crop_w = src_w
        crop_h = int(src_w / target_ar)

    face_x = _detect_face_x_center(source, start, end)
    if face_x is None:
        x_off = (src_w - crop_w) // 2
    else:
        x_off = face_x - crop_w // 2
        x_off = max(0, min(x_off, src_w - crop_w))

    y_off = (src_h - crop_h) // 2

    return f"crop={crop_w}:{crop_h}:{x_off}:{y_off},scale={tw}:{th}"


def extract_clip(
    source: str | Path,
    start: float,
    end: float,
    output_path: str | Path,
    *,
    aspect: AspectRatio = AspectRatio.PORTRAIT,
    color_grade: bool = True,
    subtitle_path: Optional[str | Path] = None,
    lut_path: Optional[str | Path] = None,
    crf: int = 16,
    preset: str = "slow",
    audio_bitrate: str = "256k",
    color_grade_filter: Optional[str] = None,
) -> Path:
    """Cut ``[start, end]`` from *source* and write a polished clip.

    Parameters
    ----------
    aspect:
        Target aspect ratio.  ``ORIGINAL`` skips reframing.
    color_grade:
        Apply the built-in cinematic grade (ignored when *lut_path* is
        provided).
    subtitle_path:
        Path to an ASS subtitle file to burn in.
    lut_path:
        Path to a ``.cube`` 3D-LUT file for custom colour grading.
    crf:
        Constant Rate Factor for x264 (0-51, lower = better, default 16).
    preset:
        x264 encoding preset (ultrafast … veryslow, default "slow").
    audio_bitrate:
        AAC audio bitrate (default "256k").
    color_grade_filter:
        Custom ffmpeg filter string to replace the built-in cinematic grade.

    Returns
    -------
    Path to the rendered clip.
    """
    source = Path(source)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _ffmpeg()
    duration = end - start

    # ---- build video filter chain -----------------------------------
    vf_parts: list[str] = []

    # 1. Aspect-ratio reformat (face-aware crop)
    if aspect != AspectRatio.ORIGINAL and aspect.dimensions:
        vf_parts.append(_vf_face_crop(aspect, source, start, end))

    # 2. Colour grade
    if lut_path:
        esc_lut = str(lut_path).replace("\\", "/").replace(":", "\\:")
        vf_parts.append(f"lut3d='{esc_lut}'")
    elif color_grade:
        vf_parts.append(color_grade_filter or _CINE_GRADE)

    # 3. Subtitles (ASS burn-in) — must come last so they sit on top
    if subtitle_path:
        esc_sub = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
        vf_parts.append(f"ass='{esc_sub}'")

    # All parts are simple single-stream filters now – join with commas.
    if vf_parts:
        vf = ",".join(vf_parts)
        filter_flag = ["-vf", vf]
    else:
        filter_flag = []

    cmd = [
        ffmpeg, "-y",
        "-ss", f"{start:.3f}",
        "-i", str(source),
        "-t", f"{duration:.3f}",
        *filter_flag,
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-preset", preset, "-crf", str(crf),
        "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100",
        "-movflags", "+faststart",
        str(output_path),
    ]

    log.info("Extracting clip %.1fs–%.1fs → %s", start, end, output_path.name)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg failed:\n%s", result.stderr[-3000:])
        raise RuntimeError(f"ffmpeg clip extraction failed for {output_path.name}")

    log.info("  ✓ %s  (%.1f s)", output_path.name, duration)
    return output_path



# ---------------------------------------------------------------------------
# Batch helper
# ---------------------------------------------------------------------------
def extract_clips_batch(
    source: str | Path,
    segments,  # list of clip_selector.Segment
    output_dir: str | Path,
    *,
    aspect: AspectRatio = AspectRatio.PORTRAIT,
    color_grade: bool = True,
    subtitle_paths: Optional[list[Path]] = None,
    lut_path: Optional[str | Path] = None,
) -> list[Path]:
    """Extract all *segments* from *source* and return output paths."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[Path] = []
    for i, seg in enumerate(segments):
        sub = subtitle_paths[i] if subtitle_paths and i < len(subtitle_paths) else None
        out = output_dir / f"{seg.label}.mp4"
        p = extract_clip(
            source,
            seg.start,
            seg.end,
            out,
            aspect=aspect,
            color_grade=color_grade,
            subtitle_path=sub,
            lut_path=lut_path,
        )
        results.append(p)
    return results
