"""
ClipForge Web — FastAPI application
====================================

Endpoints:
    POST   /api/jobs              — Create a new processing job
    GET    /api/jobs              — List all jobs
    GET    /api/jobs/{id}         — Get job status + clip info
    GET    /api/jobs/{id}/clips/{filename}  — Download a rendered clip
    DELETE /api/jobs/{id}         — Delete a job + its files
    GET    /                      — Web UI
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from web.config import OUTPUT_DIR, UPLOAD_DIR, MAX_UPLOAD_MB, PUBLIC_URL, USE_CELERY
from web.models import JobCreate, JobResponse, JobListItem, JobStatus
from web.store import create_job, get_job, list_jobs, delete_job, update_job

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ClipForge",
    description="AI-powered podcast & interview → short clip generator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check (for UptimeRobot keep-alive) ────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "clipforge"}


# ── API Routes ───────────────────────────────────────────────────────────────

@app.post("/api/jobs", response_model=JobResponse)
async def create_new_job(
    # Accept either JSON body or multipart form with file upload
    source_url: Optional[str] = Form(None),
    source_file: Optional[UploadFile] = File(None),
    music_url: Optional[str] = Form(None),
    music_volume: float = Form(0.1),
    num_clips: int = Form(5),
    aspect: str = Form("9:16"),
    whisper_model: str = Form("base"),
    color_grade: bool = Form(True),
    subtitles: bool = Form(True),
    strip_commas: bool = Form(True),
    sub_font: str = Form("Arial"),
    sub_fontsize: int = Form(64),
    sub_bold: bool = Form(True),
    sub_outline: int = Form(2),
    sub_shadow: int = Form(1),
    sub_margin_v: int = Form(768),
    sub_max_words: int = Form(5),
    sub_max_chars: int = Form(25),
    crf: int = Form(16),
    preset: str = Form("slow"),
    min_duration: float = Form(15.0),
    max_duration: float = Form(60.0),
    keywords: str = Form(""),
):
    """Create a processing job. Provide a YouTube URL OR upload a file."""
    if not source_url and not source_file:
        raise HTTPException(400, "Provide either source_url (YouTube URL) or upload a source_file.")

    job_id = create_job()

    # Handle file upload
    uploaded_path = ""
    if source_file and source_file.filename:
        upload_dir = UPLOAD_DIR / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / source_file.filename
        with open(dest, "wb") as f:
            content = await source_file.read()
            if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
                raise HTTPException(413, f"File too large. Max {MAX_UPLOAD_MB} MB.")
            f.write(content)
        uploaded_path = str(dest)

    # Build params dict for the Celery task
    params = {
        "source_url": source_url or "",
        "source_file": uploaded_path,
        "music_url": music_url or "",
        "music_volume": music_volume,
        "num_clips": num_clips,
        "aspect": aspect,
        "whisper_model": whisper_model,
        "color_grade": color_grade,
        "subtitles": subtitles,
        "strip_commas": strip_commas,
        "sub_font": sub_font,
        "sub_fontsize": sub_fontsize,
        "sub_bold": sub_bold,
        "sub_outline": sub_outline,
        "sub_shadow": sub_shadow,
        "sub_margin_v": sub_margin_v,
        "sub_max_words": sub_max_words,
        "sub_max_chars": sub_max_chars,
        "crf": crf,
        "preset": preset,
        "min_duration": min_duration,
        "max_duration": max_duration,
        "keywords": keywords,
    }

    # Dispatch async task
    _dispatch(job_id, params)

    return get_job(job_id)


@app.get("/api/jobs", response_model=list[JobListItem])
async def list_all_jobs():
    """List all processing jobs (newest first)."""
    return list_jobs()


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """Get the current status and clip info for a job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return job


@app.get("/api/jobs/{job_id}/clips/{filename}")
async def download_clip(job_id: str, filename: str):
    """Download a rendered clip file."""
    clip_path = OUTPUT_DIR / job_id / filename
    if not clip_path.exists():
        raise HTTPException(404, "Clip not found.")
    return FileResponse(
        clip_path,
        media_type="video/mp4",
        filename=filename,
    )


@app.delete("/api/jobs/{job_id}")
async def delete_job_endpoint(job_id: str):
    """Delete a job and all its files."""
    if delete_job(job_id):
        # Also clean uploads
        upload_dir = UPLOAD_DIR / job_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        return {"message": "Job deleted."}
    raise HTTPException(404, "Job not found.")


# ── JSON body endpoint (alternative to form) ────────────────────────────────
@app.post("/api/jobs/json", response_model=JobResponse)
async def create_job_json(body: JobCreate):
    """Create a job from a JSON body (no file upload)."""
    if not body.source_url:
        raise HTTPException(400, "source_url is required for JSON endpoint.")

    job_id = create_job()
    params = body.dict()
    params["source_file"] = ""
    _dispatch(job_id, params)
    return get_job(job_id)


# ── Job dispatch (Celery or thread worker) ──────────────────────────────────
def _dispatch(job_id: str, params: dict) -> None:
    """Send job to either Celery (Redis) or in-process thread worker."""
    if USE_CELERY:
        from web.tasks import process_video
        process_video.delay(job_id, params)
        log.info("Job %s dispatched to Celery", job_id)
    else:
        from web.worker import submit_job
        submit_job(job_id, params)
        log.info("Job %s dispatched to thread worker", job_id)


# ── Serve frontend ──────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main web UI."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>ClipForge</h1><p>Frontend not found. Check web/static/</p>")
