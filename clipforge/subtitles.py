"""
clipforge.subtitles – Generate & burn-in TikTok-style captions
==============================================================

Workflow:
1. word-level timestamps from the clip selector (or a fresh Whisper run).
2. Group words into short caption lines (≤ 5 words / ≤ 25 chars).
3. Write an ASS (Advanced SubStation Alpha) subtitle file with a style
   that mimics the bold, shadowed, centre-bottom captions popular on
   TikTok / Reels.
4. Burn the subtitles into the video with ``ffmpeg -vf ass=…``.
"""
from __future__ import annotations

import logging
import os
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class CaptionLine:
    text: str
    start: float  # seconds
    end: float


# ---------------------------------------------------------------------------
# Grouping words → caption lines
# ---------------------------------------------------------------------------
def group_words_into_lines(
    words: Sequence[dict],  # [{text, start, end}, …]
    max_words: int = 5,
    max_chars: int = 25,
) -> list[CaptionLine]:
    """Split a word list into short subtitle lines.

    Each *word* dict must have keys ``text``, ``start``, ``end``.
    """
    lines: list[CaptionLine] = []
    buf_words: list[dict] = []

    def _flush():
        if not buf_words:
            return
        lines.append(
            CaptionLine(
                text=" ".join(w["text"] for w in buf_words),
                start=buf_words[0]["start"],
                end=buf_words[-1]["end"],
            )
        )
        buf_words.clear()

    for w in words:
        projected = " ".join(bw["text"] for bw in buf_words) + " " + w["text"]
        if len(buf_words) >= max_words or len(projected.strip()) > max_chars:
            _flush()
        buf_words.append(w)

    _flush()
    return lines


# ---------------------------------------------------------------------------
# ASS subtitle file generation
# ---------------------------------------------------------------------------
_ASS_HEADER = r"""[Script Info]
Title: ClipForge Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: TikTok,Arial,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1.5,0,1,2,1,2,40,40,768,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def _ass_timestamp(seconds: float) -> str:
    """Convert seconds to ASS timestamp ``H:MM:SS.cc``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass(
    lines: list[CaptionLine],
    output_path: str | Path,
    *,
    style_name: str = "TikTok",
    highlight_color: str | None = None,
    ass_header: str | None = None,
    strip_commas: bool = True,
) -> Path:
    """Write an ASS subtitle file from grouped caption lines.

    Parameters
    ----------
    highlight_color:
        If given, each line will have the *current word* highlighted
        using ``{\\c&H<color>&}`` override tags (karaoke-style).
    ass_header:
        Custom ASS header string.  If *None*, uses the built-in default.
    strip_commas:
        Remove all commas from subtitle text (default True).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = ass_header if ass_header is not None else _ASS_HEADER

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(header)
        for line in lines:
            start = _ass_timestamp(line.start)
            end = _ass_timestamp(line.end)
            text = line.text
            if strip_commas:
                text = text.replace(",", "")
            # Escape ASS special chars
            text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            if highlight_color:
                # Simple word-level pop: bold each word sequentially
                words = text.split()
                parts = []
                for w in words:
                    parts.append(
                        "{\\c&H" + highlight_color + "&\\b1}" + w + "{\\c&HFFFFFF&\\b0}"
                    )
                text = " ".join(parts)
            fh.write(
                f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,{text}\n"
            )

    log.info("Wrote ASS subtitles → %s  (%d lines)", output_path, len(lines))
    return output_path


def write_srt(lines: list[CaptionLine], output_path: str | Path) -> Path:
    """Write a simple SRT file (fallback when ASS is not desired)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _ts(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    with open(output_path, "w", encoding="utf-8") as fh:
        for i, line in enumerate(lines, 1):
            fh.write(f"{i}\n{_ts(line.start)} --> {_ts(line.end)}\n{line.text}\n\n")

    log.info("Wrote SRT subtitles → %s  (%d lines)", output_path, len(lines))
    return output_path


# ---------------------------------------------------------------------------
# Convenience: words (from clip_selector.Word) → CaptionLine list
# ---------------------------------------------------------------------------
def words_to_caption_lines(
    words, max_words: int = 5, max_chars: int = 25
) -> list[CaptionLine]:
    """Accept a list of ``clip_selector.Word`` objects (or plain dicts)."""
    dicts = []
    for w in words:
        if isinstance(w, dict):
            dicts.append(w)
        else:
            dicts.append({"text": w.text, "start": w.start, "end": w.end})
    return group_words_into_lines(dicts, max_words=max_words, max_chars=max_chars)
