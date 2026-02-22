"""
ClipForge Web — Video processing pipeline
==========================================

Core pipeline logic extracted so it can be called from either:
  • Celery task  (production w/ Redis)
  • Thread pool  (free-tier / Render deployment)
"""
from __future__ import annotations

import logging
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path

from web.config import OUTPUT_DIR, WORK_DIR, PUBLIC_URL
from web.models import JobStatus
from web.store import update_job

log = logging.getLogger(__name__)


def run_pipeline(job_id: str, params: dict) -> dict:
    """Full pipeline: download → transcribe → select → render → mix.

    This is a *blocking* call that may take several minutes.
    Run it inside a Celery task or a background thread.
    """
    # Apply patches early
    import clipforge.patches as _patches
    _patches.apply_all()

    from clipforge.clip_selector import select_clips
    from clipforge.downloader import resolve_source
    from clipforge.music import prepare_music, mix_music
    from clipforge.subtitles import words_to_caption_lines, write_ass
    from clipforge.video import AspectRatio, extract_clip

    job_work = WORK_DIR / job_id
    job_work.mkdir(parents=True, exist_ok=True)
    job_output = OUTPUT_DIR / job_id
    job_output.mkdir(parents=True, exist_ok=True)

    try:
        # ── 1. Download / resolve source ─────────────────────────────
        update_job(job_id, status=JobStatus.DOWNLOADING, progress="Downloading video...")
        source_url = params.get("source_url", "")
        source_file = params.get("source_file", "")
        if source_file:
            source_path = Path(source_file)
        else:
            source_path = resolve_source(source_url, job_work)

        # ── 2. Transcribe + select clips ─────────────────────────────
        update_job(job_id, status=JobStatus.TRANSCRIBING, progress="Transcribing audio...")
        keywords = [k.strip() for k in params.get("keywords", "").split(",") if k.strip()]
        segments = select_clips(
            source_path,
            model_size=params.get("whisper_model", "base"),
            num_clips=params.get("num_clips", 5),
            min_duration=params.get("min_duration", 15.0),
            max_duration=params.get("max_duration", 60.0),
            keywords=keywords,
        )
        if not segments:
            update_job(job_id, status=JobStatus.FAILED, message="No suitable clips found.")
            return {"status": "failed"}

        update_job(job_id, status=JobStatus.SELECTING,
                   progress=f"Selected {len(segments)} clips")

        # ── 3. Build ASS header from params ──────────────────────────
        bold_flag = -1 if params.get("sub_bold", True) else 0
        ass_header = (
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
            f"Style: TikTok,{params.get('sub_font', 'Arial')},"
            f"{params.get('sub_fontsize', 64)},&H00FFFFFF,&H000000FF,"
            f"&H00000000,&H80000000,{bold_flag},0,0,0,"
            f"100,100,1.5,0,1,{params.get('sub_outline', 2)},"
            f"{params.get('sub_shadow', 1)},2,40,40,"
            f"{params.get('sub_margin_v', 768)},1\n"
            "\n"
            "[Events]\n"
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
        )

        # ── 4. Render clips ──────────────────────────────────────────
        update_job(job_id, status=JobStatus.RENDERING, progress="Rendering clips...")
        aspect = AspectRatio(params.get("aspect", "9:16"))
        rendered: list[Path] = []
        clip_data: list[dict] = []

        for i, seg in enumerate(segments):
            update_job(job_id, progress=f"Rendering clip {i+1}/{len(segments)}...")

            # Subtitles
            sub_path = None
            if params.get("subtitles", True):
                labelled = [
                    {"text": w.text, "start": w.start - seg.start, "end": w.end - seg.start}
                    for w in seg.words
                ]
                lines = words_to_caption_lines(
                    labelled,
                    max_words=params.get("sub_max_words", 5),
                    max_chars=params.get("sub_max_chars", 25),
                )
                sub_path = job_work / f"{seg.label}.ass"
                write_ass(
                    lines, sub_path,
                    ass_header=ass_header,
                    strip_commas=params.get("strip_commas", True),
                )

            out_path = job_output / f"{seg.label}.mp4"
            extract_clip(
                source_path, seg.start, seg.end, out_path,
                aspect=aspect,
                color_grade=params.get("color_grade", True),
                subtitle_path=sub_path,
                crf=params.get("crf", 16),
                preset=params.get("preset", "slow"),
                audio_bitrate="256k",
            )
            rendered.append(out_path)
            clip_data.append({
                "label": seg.label,
                "start": round(seg.start, 1),
                "end": round(seg.end, 1),
                "duration": round(seg.duration, 1),
                "score": round(seg.score, 3),
                "text_preview": seg.text[:150] + "..." if len(seg.text) > 150 else seg.text,
                "download_url": f"{PUBLIC_URL}/api/jobs/{job_id}/clips/{seg.label}.mp4",
                "filename": f"{seg.label}.mp4",
            })

        # ── 5. Mix music ─────────────────────────────────────────────
        music_url = params.get("music_url")
        if music_url:
            update_job(job_id, status=JobStatus.MIXING_MUSIC, progress="Mixing background music...")
            music_file = prepare_music(music_url, job_work)
            for p in rendered:
                tmp = p.with_name(p.stem + "_mx.mp4")
                try:
                    mix_music(p, music_file, tmp, music_volume=params.get("music_volume", 0.1))
                    shutil.move(str(tmp), str(p))
                except Exception as e:
                    log.warning("Music mix failed for %s: %s", p.name, e)
                    if tmp.exists():
                        tmp.unlink()

        # ── Done ─────────────────────────────────────────────────────
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress="Done!",
            clips=clip_data,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        return {"status": "completed", "num_clips": len(clip_data)}

    except Exception as e:
        log.error("Job %s failed: %s\n%s", job_id, e, traceback.format_exc())
        update_job(
            job_id,
            status=JobStatus.FAILED,
            progress="Failed",
            message=str(e)[:500],
        )
        return {"status": "failed", "error": str(e)}
    finally:
        if job_work.exists():
            shutil.rmtree(job_work, ignore_errors=True)
