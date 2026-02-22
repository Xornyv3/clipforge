#!/usr/bin/env python3
"""
ClipForge – Re-render Script
=============================
Edit the settings below, then run:   python rerender.py

All tweakable options are in the CONFIG section at the top.
"""
import clipforge.patches as _patches
_patches.apply_all()

import shutil, logging
from pathlib import Path
from clipforge.downloader import resolve_source
from clipforge.music import prepare_music, mix_music
from clipforge.subtitles import words_to_caption_lines, write_ass
from clipforge.video import extract_clip, AspectRatio

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                              CONFIG                                      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# ── Paths (YouTube URL or local file path — both work) ───────────────────────
SOURCE_VIDEO = r"https://www.youtube.com/watch?v=azYTfa8DiXk"
MUSIC_FILE   = r"https://www.youtube.com/watch?v=UdTzq4pnB6o"
OUTPUT_DIR   = r"d:\Users\deskt\OneDrive\Desktop\launch projects\New folder\clips_output"
WORK_DIR     = r"D:\temp\clipforge_work"   # temp folder for downloads

# ── Clip time ranges (label, start_sec, end_sec) ────────────────────────────
CLIPS = [
    ("clip_01",   0.0,  59.7),
    ("clip_02",  76.4, 134.1),
    ("clip_03", 195.3, 251.1),
    ("clip_04", 255.5, 308.5),
    #("clip_05", 320.4, 377.3),
]

# ── Aspect ratio ─────────────────────────────────────────────────────────────
#   "9:16"      → portrait  (TikTok / Reels / Shorts)
#   "16:9"      → landscape
#   "1:1"       → square
#   "original"  → keep source
ASPECT_RATIO = "9:16"

# ── Video quality ────────────────────────────────────────────────────────────
CRF           = 16        # 0–51, lower = better quality / bigger file (16 is great)
PRESET        = "slow"    # ultrafast, fast, medium, slow, veryslow
AUDIO_BITRATE = "256k"    # e.g. "128k", "192k", "256k", "320k"

# ── Colour grade ─────────────────────────────────────────────────────────────
COLOR_GRADE = True         # Set False to skip grading entirely

# Custom ffmpeg filter string — set to None to use the built-in cinematic grade.
# Example: "eq=contrast=1.1:brightness=0.03:saturation=1.2,vignette=PI/4"
COLOR_GRADE_FILTER = None

# ── Background music ────────────────────────────────────────────────────────
ADD_MUSIC    = False
MUSIC_VOLUME = 0.5         # 0.0 – 1.0 (fraction of original audio level)

# ── Subtitle style ──────────────────────────────────────────────────────────
#   Font & size
SUB_FONT      = "Arial"
SUB_FONTSIZE  = 64
SUB_BOLD      = True       # -1 = bold, 0 = normal

#   Colours (ASS format: &HAABBGGRR — AA=alpha, BB=blue, GG=green, RR=red)
SUB_PRIMARY   = "&H00FFFFFF"   # text colour (white)
SUB_OUTLINE_C = "&H00000000"   # outline colour (black)
SUB_BACK_C    = "&H80000000"   # shadow colour (semi-transparent black)

#   Border & shadow
SUB_BORDER_STYLE = 1      # 1 = outline + shadow, 3 = opaque box (pill bg)
SUB_OUTLINE      = 2      # outline thickness in px
SUB_SHADOW       = 1      # shadow depth in px

#   Position — MarginV is distance from bottom (on a 1920px canvas)
#     768 = 60% down from top,  120 = near bottom,  960 = dead center
SUB_MARGIN_V  = 768
SUB_ALIGNMENT = 2          # 2 = bottom-center

#   Line length
SUB_MAX_WORDS = 5          # max words per subtitle line
SUB_MAX_CHARS = 25         # max characters per subtitle line

#   Cleanup
SUB_STRIP_COMMAS = True    # remove all commas from subtitles

# ── Whisper transcription ───────────────────────────────────────────────────
WHISPER_MODEL = "base"     # tiny, base, small, medium, large-v2
WHISPER_LANG  = "en"       # language code or None for auto-detect


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                          END OF CONFIG                                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def _build_ass_header() -> str:
    """Build an ASS header from the subtitle config above."""
    bold_flag = -1 if SUB_BOLD else 0
    return (
        "[Script Info]\n"
        "Title: ClipForge Subtitles\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
        "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: TikTok,{SUB_FONT},{SUB_FONTSIZE},{SUB_PRIMARY},&H000000FF,"
        f"{SUB_OUTLINE_C},{SUB_BACK_C},{bold_flag},0,0,0,"
        f"100,100,1.5,0,{SUB_BORDER_STYLE},{SUB_OUTLINE},{SUB_SHADOW},"
        f"{SUB_ALIGNMENT},40,40,{SUB_MARGIN_V},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )


def main():
    OUT    = Path(OUTPUT_DIR)
    WORK   = Path(WORK_DIR)
    WORK.mkdir(parents=True, exist_ok=True)
    aspect = AspectRatio(ASPECT_RATIO)
    ass_header = _build_ass_header()

    print("=" * 60)
    print("  ClipForge Re-render")
    print("=" * 60)

    # ── Step 0: Resolve sources (download if YouTube URL) ───────────
    print("\n[0] Resolving sources...")
    SOURCE = resolve_source(SOURCE_VIDEO, WORK)
    print(f"     Video: {SOURCE}")
    if ADD_MUSIC:
        MUSIC = prepare_music(MUSIC_FILE, WORK)
        print(f"     Music: {MUSIC}")
    else:
        MUSIC = None

    # ── Step 1: Transcribe ──────────────────────────────────────────
    print(f"\n[1/3] Transcribing with Whisper ({WHISPER_MODEL})...")
    from faster_whisper import WhisperModel  # noqa: E402
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segs, info = model.transcribe(
        str(SOURCE), beam_size=5, word_timestamps=True,
        language=WHISPER_LANG,
    )
    all_words = []
    for s in segs:
        if s.words:
            for w in s.words:
                all_words.append({"text": w.word.strip(), "start": w.start, "end": w.end})
    print(f"       {len(all_words)} words transcribed\n")

    # ── Step 2: Render clips ────────────────────────────────────────
    print(f"[2/3] Rendering {len(CLIPS)} clips...")
    rendered = []
    for label, t0, t1 in CLIPS:
        print(f"\n  ▸ {label}  ({t0:.1f}s – {t1:.1f}s)")

        # Subtitles
        clip_words = [w for w in all_words if w["end"] > t0 and w["start"] < t1]
        shifted = [
            {"text": w["text"], "start": w["start"] - t0, "end": w["end"] - t0}
            for w in clip_words
        ]
        lines = words_to_caption_lines(shifted, max_words=SUB_MAX_WORDS, max_chars=SUB_MAX_CHARS)
        sub_path = OUT / f"{label}.ass"
        write_ass(lines, sub_path, ass_header=ass_header, strip_commas=SUB_STRIP_COMMAS)

        # Video
        out_path = OUT / f"{label}.mp4"
        extract_clip(
            SOURCE, t0, t1, out_path,
            aspect=aspect,
            color_grade=COLOR_GRADE,
            subtitle_path=sub_path,
            crf=CRF,
            preset=PRESET,
            audio_bitrate=AUDIO_BITRATE,
            color_grade_filter=COLOR_GRADE_FILTER,
        )
        rendered.append(out_path)

    # ── Step 3: Mix music ───────────────────────────────────────────
    if ADD_MUSIC and MUSIC is not None and MUSIC.exists():
        print(f"\n[3/3] Mixing background music (volume={MUSIC_VOLUME})...")
        for p in rendered:
            tmp = p.with_name(p.stem + "_mx.mp4")
            try:
                mix_music(p, MUSIC, tmp, music_volume=MUSIC_VOLUME)
                shutil.move(str(tmp), str(p))
                print(f"       + {p.name}")
            except Exception as e:
                print(f"       ! {p.name}: {e}")
                if tmp.exists():
                    tmp.unlink()
    else:
        print("\n[3/3] Skipping music mix.")

    print("\n" + "=" * 60)
    print(f"  Done!  Clips saved to: {OUT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
