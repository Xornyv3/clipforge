"""
ClipForge Web — Celery task for async video processing
=======================================================

Only used when  USE_CELERY=true  and Redis is available.
Otherwise, see  web.worker  for the thread-based fallback.
"""
from __future__ import annotations

import logging

try:
    from celery import Celery
except ImportError:
    Celery = None  # type: ignore[misc,assignment]

from web.config import REDIS_URL
from web.pipeline import run_pipeline

log = logging.getLogger(__name__)

# ── Celery app (only created if celery is installed) ─────────────────────────
if Celery is not None:
    app = Celery("clipforge", broker=REDIS_URL, backend=REDIS_URL)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_track_started=True,
        task_time_limit=3600,
        task_soft_time_limit=3000,
        worker_prefetch_multiplier=1,
        worker_concurrency=1,
    )

    @app.task(bind=True, name="clipforge.process_video")
    def process_video(self, job_id: str, params: dict) -> dict:
        """Celery wrapper around the shared pipeline."""
        return run_pipeline(job_id, params)
else:
    app = None  # type: ignore[assignment]

    def process_video(job_id: str, params: dict) -> dict:  # type: ignore[misc]
        """Stub — should never be called when Celery is unavailable."""
        raise RuntimeError("Celery is not installed. Set USE_CELERY=false.")
