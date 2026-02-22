"""
ClipForge Web — Simple JSON-file job store
==========================================

For the MVP we store job metadata as JSON files on disk.
Swap this for PostgreSQL / DynamoDB in production.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from web.config import OUTPUT_DIR
from web.models import ClipInfo, JobResponse, JobStatus

_JOBS_DIR = OUTPUT_DIR / "_jobs"
_JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _job_file(job_id: str) -> Path:
    return _JOBS_DIR / f"{job_id}.json"


def create_job() -> str:
    """Create a new job and return its ID."""
    job_id = uuid.uuid4().hex[:12]
    data = {
        "job_id": job_id,
        "status": JobStatus.PENDING.value,
        "progress": "Queued",
        "message": "",
        "clips": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": "",
    }
    _job_file(job_id).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return job_id


def get_job(job_id: str) -> Optional[JobResponse]:
    """Load job from disk.  Returns *None* if not found."""
    f = _job_file(job_id)
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    return JobResponse(**data)


def update_job(
    job_id: str,
    *,
    status: Optional[JobStatus] = None,
    progress: Optional[str] = None,
    message: Optional[str] = None,
    clips: Optional[list[dict]] = None,
    completed_at: Optional[str] = None,
) -> None:
    """Update fields of an existing job."""
    f = _job_file(job_id)
    data = json.loads(f.read_text(encoding="utf-8"))
    if status is not None:
        data["status"] = status.value
    if progress is not None:
        data["progress"] = progress
    if message is not None:
        data["message"] = message
    if clips is not None:
        data["clips"] = clips
    if completed_at is not None:
        data["completed_at"] = completed_at
    f.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_jobs(limit: int = 50) -> list[dict]:
    """Return the most recent jobs (newest first)."""
    files = sorted(_JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    jobs = []
    for f in files[:limit]:
        data = json.loads(f.read_text(encoding="utf-8"))
        jobs.append({
            "job_id": data["job_id"],
            "status": data["status"],
            "progress": data.get("progress", ""),
            "num_clips": len(data.get("clips", [])),
            "created_at": data.get("created_at", ""),
        })
    return jobs


def delete_job(job_id: str) -> bool:
    """Delete a job and its output directory."""
    f = _job_file(job_id)
    if not f.exists():
        return False
    f.unlink()
    # Also clean up output files
    job_output = OUTPUT_DIR / job_id
    if job_output.exists():
        import shutil
        shutil.rmtree(job_output, ignore_errors=True)
    return True
