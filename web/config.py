"""
ClipForge Web — Configuration
"""
import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.getenv("CLIPFORGE_UPLOAD_DIR", str(BASE_DIR / "uploads")))
OUTPUT_DIR = Path(os.getenv("CLIPFORGE_OUTPUT_DIR", str(BASE_DIR / "outputs")))
WORK_DIR = Path(os.getenv("CLIPFORGE_WORK_DIR", str(BASE_DIR / "tmp_work")))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)

# ── Redis / Celery ───────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
USE_CELERY = os.getenv("USE_CELERY", "false").lower() == "true"

# ── Limits ───────────────────────────────────────────────────────────────────
MAX_UPLOAD_MB = int(os.getenv("CLIPFORGE_MAX_UPLOAD_MB", "500"))
MAX_VIDEO_DURATION_SEC = int(os.getenv("CLIPFORGE_MAX_DURATION", "3600"))  # 1 hour

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_NUM_CLIPS = 5
DEFAULT_ASPECT = "9:16"
DEFAULT_WHISPER_MODEL = "base"
DEFAULT_CRF = 16
DEFAULT_PRESET = "slow"

# ── Auth (simple API key for MVP — swap for proper auth later) ───────────────
API_KEY = os.getenv("CLIPFORGE_API_KEY", "")  # empty = no auth required

# ── Public URL for download links ────────────────────────────────────────────
PUBLIC_URL = os.getenv("CLIPFORGE_PUBLIC_URL", "http://localhost:8000")
