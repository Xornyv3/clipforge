"""
ClipForge Web — Thread-based background worker
================================================

Drop-in replacement for Celery when Redis is not available.
Uses a single-thread pool so only one job runs at a time.

Set  USE_CELERY=false  (the default) to use this worker.
Set  USE_CELERY=true   to use Celery + Redis instead.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from web.pipeline import run_pipeline

log = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clipforge")


def submit_job(job_id: str, params: dict) -> None:
    """Submit a job to the thread pool (non-blocking)."""
    log.info("Submitting job %s to thread worker", job_id)
    future = _pool.submit(run_pipeline, job_id, params)
    future.add_done_callback(lambda f: _on_done(job_id, f))


def _on_done(job_id: str, future) -> None:
    exc = future.exception()
    if exc:
        log.error("Job %s thread raised: %s", job_id, exc)
    else:
        log.info("Job %s thread finished: %s", job_id, future.result())
