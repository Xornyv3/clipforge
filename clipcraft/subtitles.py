"""Generate TikTok-style ASS subtitles and burn them into video.

Words are grouped into short phrases (3-5 words) displayed one phrase at
a time, with optional karaoke-style word-by-word color highlighting.
"""

import os
import subprocess

from . import utils

# ASS header — optimised for 1080 × 1920 portrait canvas.
# The style uses bold Arial, large font, white text with a thick black
# outline and a subtle shadow, positioned in the lower-centre of the frame.
_ASS_HEADER = r"""[Script Info]
Title: ClipCraft Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTok,Arial,68,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,40,40,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""


def generate_ass(
    words: list,
    output_path: str,
    words_per_phrase: int = 4,
    highlight: bool = True,
) -> str:
    """Create an ASS subtitle file from word-level timestamps.

    Parameters
    ----------
    words : list[dict]
        Each dict has ``word``, ``start``, ``end`` (seconds, clip-relative).
    output_path : str
        Destination ``.ass`` file path.
    words_per_phrase : int
        Number of words to display per subtitle event.
    highlight : bool
        If True, add karaoke colour sweep across each word.

    Returns
    -------
    str
        The *output_path* written to.
    """
    if not words:
        raise ValueError("No words provided for subtitle generation")

    lines = [_ASS_HEADER.strip()]

    # Chunk into phrases
    phrases = [
        words[i : i + words_per_phrase]
        for i in range(0, len(words), words_per_phrase)
    ]

    for phrase in phrases:
        start = phrase[0]["start"]
        end = phrase[-1]["end"]

        if highlight:
            # Karaoke-style: highlight each word as it's spoken
            parts = []
            for w in phrase:
                dur_cs = max(int((w["end"] - w["start"]) * 100), 10)
                parts.append(rf"{{\kf{dur_cs}}}{w['word']}")
            text = " ".join(parts)
        else:
            text = " ".join(w["word"] for w in phrase)

        lines.append(
            f"Dialogue: 0,{_ts(start)},{_ts(end)},TikTok,,0,0,0,,{text}"
        )

    content = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    utils.log(f"Subtitles generated: {len(phrases)} phrases → {output_path}")
    return output_path


def burn(video_path: str, ass_path: str, output_path: str) -> str:
    """Hard-code ASS subtitles into a video using ffmpeg.

    Returns the path to the subtitled video.
    """
    utils.log("Burning subtitles into video...")

    # ffmpeg's ass filter needs forward slashes and escaped colons
    escaped = ass_path.replace("\\", "/").replace(":", "\\:")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"ass={escaped}",
            "-c:a", "copy",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            output_path,
        ],
        check=True,
        capture_output=True,
    )
    utils.log("Subtitles burned successfully")
    return output_path


# ------------------------------------------------------------------

def _ts(seconds: float) -> str:
    """Format seconds → ``H:MM:SS.CC`` (ASS timestamp)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
