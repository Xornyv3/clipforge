#!/usr/bin/env python3
"""
ClipForge – AI-powered podcast / interview → short-clip pipeline
================================================================

Usage examples
--------------
    # From a local file – 5 best clips, portrait, with subtitles
    python run.py video.mp4

    # From YouTube – landscape clips, custom whisper model
    python run.py "https://youtu.be/abc123" --aspect 16:9 --model medium

    # With background music from a YouTube URL
    python run.py interview.mp4 --music "https://youtu.be/xyz789" --music-vol 0.12

    # Specify keywords to boost clip selection
    python run.py podcast.mp4 --keywords "AI,startup,funding"

Run ``python run.py --help`` for the full list of options.
"""
from __future__ import annotations

# ── Apply compatibility patches BEFORE any ML import ─────────────────
import clipforge.patches as _patches
_patches.apply_all()
# ─────────────────────────────────────────────────────────────────────

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from clipforge.clip_selector import select_clips
from clipforge.downloader import resolve_source
from clipforge.music import mix_music, prepare_music
from clipforge.speakers import assign_speakers, diarize
from clipforge.subtitles import words_to_caption_lines, write_ass
from clipforge.video import AspectRatio, extract_clip


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clipforge",
        description="Cut a long podcast / interview into polished short clips.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── source ────────────────────────────────────────────────────────
    p.add_argument(
        "source",
        help="Path to a local video/audio file  OR  a YouTube URL.",
    )

    # ── output ────────────────────────────────────────────────────────
    p.add_argument(
        "-o", "--output-dir",
        default="./clips_output",
        help="Directory for rendered clips  (default: ./clips_output).",
    )

    # ── clip selection ────────────────────────────────────────────────
    p.add_argument(
        "-n", "--num-clips",
        type=int, default=5,
        help="Number of clips to extract  (default: 5).",
    )
    p.add_argument(
        "--min-duration",
        type=float, default=15.0,
        help="Minimum clip length in seconds  (default: 15).",
    )
    p.add_argument(
        "--max-duration",
        type=float, default=60.0,
        help="Maximum clip length in seconds  (default: 60).",
    )
    p.add_argument(
        "--keywords",
        default="",
        help="Comma-separated keywords to boost in clip scoring.",
    )

    # ── whisper model ────────────────────────────────────────────────
    p.add_argument(
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
        help="Whisper model size  (default: base).",
    )

    # ── aspect ratio ─────────────────────────────────────────────────
    p.add_argument(
        "--aspect",
        default="9:16",
        choices=["9:16", "16:9", "1:1", "original"],
        help="Output aspect ratio  (default: 9:16  portrait).",
    )

    # ── subtitles ────────────────────────────────────────────────────
    p.add_argument(
        "--no-subs",
        action="store_true",
        help="Skip subtitle burn-in.",
    )
    p.add_argument(
        "--highlight-color",
        default="00FFFF",
        help="ASS colour for word highlight  (default: 00FFFF  = cyan).",
    )

    # ── colour grade ─────────────────────────────────────────────────
    p.add_argument(
        "--no-grade",
        action="store_true",
        help="Skip the cinematic colour grade.",
    )
    p.add_argument(
        "--lut",
        default=None,
        help="Path to a .cube 3D-LUT file for custom colour grading.",
    )

    # ── background music ─────────────────────────────────────────────
    p.add_argument(
        "--music",
        default=None,
        help="Path or YouTube URL for background music.",
    )
    p.add_argument(
        "--music-vol",
        type=float, default=0.10,
        help="Music volume relative to speech  (0.0–1.0, default: 0.10).",
    )

    # ── speaker diarisation ──────────────────────────────────────────
    p.add_argument(
        "--diarize",
        action="store_true",
        help="Run speaker diarisation (requires pyannote.audio + HF_TOKEN).",
    )
    p.add_argument(
        "--hf-token",
        default=None,
        help="Hugging Face token for pyannote  (or set HF_TOKEN env-var).",
    )
    p.add_argument(
        "--num-speakers",
        type=int, default=None,
        help="Exact number of speakers (helps diarisation accuracy).",
    )

    # ── misc ─────────────────────────────────────────────────────────
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return p


# =====================================================================
# Pipeline
# =====================================================================
def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    # ── logging ──────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("clipforge")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    work_dir = Path(tempfile.mkdtemp(prefix="clipforge_"))
    log.info("Work directory: %s", work_dir)

    aspect = AspectRatio(args.aspect)
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    # ── 1. Resolve / download source ─────────────────────────────────
    log.info("╔══ Step 1/6 : Resolving source …")
    source_path = resolve_source(args.source, work_dir)
    log.info("  Source file: %s", source_path)

    # ── 2. Select best clips ─────────────────────────────────────────
    log.info("╠══ Step 2/6 : Selecting clips …")
    segments = select_clips(
        source_path,
        model_size=args.model,
        num_clips=args.num_clips,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        keywords=keywords,
    )
    if not segments:
        log.error("No suitable clips found – aborting.")
        sys.exit(1)
    log.info("  Selected %d clips.", len(segments))

    # ── 3. (Optional) Speaker diarisation ────────────────────────────
    speaker_turns = []
    if args.diarize:
        log.info("╠══ Step 3/6 : Speaker diarisation …")
        speaker_turns = diarize(
            source_path,
            hf_token=args.hf_token,
            num_speakers=args.num_speakers,
        )
    else:
        log.info("╠══ Step 3/6 : Speaker diarisation  (skipped)")

    # ── 4. Generate subtitles ────────────────────────────────────────
    subtitle_paths: list[Path | None] = []
    if not args.no_subs:
        log.info("╠══ Step 4/6 : Generating subtitles …")
        for seg in segments:
            if speaker_turns:
                labelled = assign_speakers(seg.words, speaker_turns)
            else:
                labelled = [
                    {"text": w.text, "start": w.start, "end": w.end}
                    for w in seg.words
                ]
            # Offset timestamps so they start at 0 for each clip
            offset = seg.start
            for w in labelled:
                w["start"] -= offset
                w["end"] -= offset

            lines = words_to_caption_lines(labelled)
            ass_path = work_dir / f"{seg.label}.ass"
            write_ass(
                lines, ass_path,
                highlight_color=args.highlight_color,
            )
            subtitle_paths.append(ass_path)
    else:
        log.info("╠══ Step 4/6 : Subtitles  (skipped)")
        subtitle_paths = [None] * len(segments)

    # ── 5. Extract & render clips ────────────────────────────────────
    log.info("╠══ Step 5/6 : Extracting & rendering clips …")
    rendered: list[Path] = []
    for i, seg in enumerate(segments):
        out = output_dir / f"{seg.label}.mp4"
        clip_path = extract_clip(
            source_path,
            seg.start,
            seg.end,
            out,
            aspect=aspect,
            color_grade=not args.no_grade,
            subtitle_path=subtitle_paths[i],
            lut_path=args.lut,
        )
        rendered.append(clip_path)

    # ── 6. (Optional) Mix background music ───────────────────────────
    if args.music:
        log.info("╠══ Step 6/6 : Mixing background music …")
        music_file = prepare_music(args.music, work_dir)
        final: list[Path] = []
        for clip_path in rendered:
            mixed_out = clip_path.with_name(clip_path.stem + "_music" + clip_path.suffix)
            mix_music(
                clip_path, music_file, mixed_out,
                music_volume=args.music_vol,
            )
            # Replace original with mixed version
            mixed_out.replace(clip_path)
            final.append(clip_path)
        rendered = final
    else:
        log.info("╠══ Step 6/6 : Background music  (skipped)")

    # ── Done ─────────────────────────────────────────────────────────
    log.info("╚══ Done!  %d clips saved to %s", len(rendered), output_dir)
    for p in rendered:
        log.info("  → %s", p)

    # Write a summary text file next to the clips
    summary = output_dir / "clips_summary.txt"
    with open(summary, "w", encoding="utf-8") as fh:
        fh.write("ClipForge – Clip Summary\n")
        fh.write("=" * 40 + "\n\n")
        for seg, path in zip(segments, rendered):
            fh.write(f"{seg.label}\n")
            fh.write(f"  Time  : {seg.start:.1f}s – {seg.end:.1f}s  ({seg.duration:.1f}s)\n")
            fh.write(f"  Score : {seg.score:.3f}\n")
            fh.write(f"  File  : {path.name}\n")
            fh.write(f'  Text  : "{seg.text[:120]}…"\n\n')
    log.info("  Summary → %s", summary)


if __name__ == "__main__":
    main()
