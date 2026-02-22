"""
ClipForge Web — Pydantic models for API request / response
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────
class AspectChoice(str, Enum):
    PORTRAIT = "9:16"
    LANDSCAPE = "16:9"
    SQUARE = "1:1"
    ORIGINAL = "original"


class JobStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    SELECTING = "selecting"
    RENDERING = "rendering"
    MIXING_MUSIC = "mixing_music"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Request models ───────────────────────────────────────────────────────────
class JobCreate(BaseModel):
    """POST /api/jobs — create a new clip job."""
    source_url: Optional[str] = Field(
        None,
        description="YouTube URL of the source video. Provide this OR upload a file.",
    )
    music_url: Optional[str] = Field(
        None,
        description="YouTube URL for background music (optional).",
    )
    music_volume: float = Field(0.1, ge=0.0, le=1.0)
    num_clips: int = Field(5, ge=1, le=20)
    aspect: AspectChoice = AspectChoice.PORTRAIT
    whisper_model: str = Field("base", pattern=r"^(tiny|base|small|medium|large|large-v2|large-v3)$")
    color_grade: bool = True
    subtitles: bool = True
    strip_commas: bool = True

    # Subtitle style overrides
    sub_font: str = "Arial"
    sub_fontsize: int = Field(64, ge=12, le=200)
    sub_bold: bool = True
    sub_outline: int = Field(2, ge=0, le=20)
    sub_shadow: int = Field(1, ge=0, le=10)
    sub_margin_v: int = Field(768, ge=0, le=1920)
    sub_max_words: int = Field(5, ge=1, le=15)
    sub_max_chars: int = Field(25, ge=10, le=80)

    # Video quality
    crf: int = Field(16, ge=0, le=51)
    preset: str = Field("slow", pattern=r"^(ultrafast|superfast|veryfast|faster|fast|medium|slow|slower|veryslow)$")

    # Clip selection
    min_duration: float = Field(15.0, ge=5.0, le=120.0)
    max_duration: float = Field(60.0, ge=10.0, le=180.0)
    keywords: str = Field("", description="Comma-separated keywords to boost clip scoring.")


# ── Response models ──────────────────────────────────────────────────────────
class ClipInfo(BaseModel):
    label: str
    start: float
    end: float
    duration: float
    score: float
    text_preview: str
    download_url: str
    filename: str


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: str = ""
    message: str = ""
    clips: list[ClipInfo] = []
    created_at: str = ""
    completed_at: str = ""


class JobListItem(BaseModel):
    job_id: str
    status: JobStatus
    progress: str = ""
    num_clips: int = 0
    created_at: str = ""
