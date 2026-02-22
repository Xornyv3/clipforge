"""
clipforge.clip_selector – Score transcript segments and pick the best clips
===========================================================================

Strategy
--------
1. Transcribe the audio with Whisper (word-level timestamps).
2. Slide a window across the transcript to form candidate segments of
   a target duration (default 30-60 s).
3. Score each candidate on several heuristics:
   * **Completeness** – does it start/end on a sentence boundary?
   * **Energy** – average speech-rate (words / second) as a proxy for
     engagement.
   * **Silence ratio** – penalise segments with long pauses.
   * **Keyword boost** – optional user-supplied keywords get a bonus.
4. Return the top-N non-overlapping segments sorted by score.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Segment:
    """A candidate clip window."""
    words: list[Word]
    score: float = 0.0
    label: str = ""

    @property
    def start(self) -> float:
        return self.words[0].start if self.words else 0.0

    @property
    def end(self) -> float:
        return self.words[-1].end if self.words else 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------
def transcribe(audio_path: str | Path, model_size: str = "base") -> list[Word]:
    """Run Whisper on *audio_path* and return word-level timestamps.

    Tries ``faster-whisper`` first (much faster on CPU); falls back to
    the original ``openai-whisper`` package.
    """
    audio_path = str(audio_path)

    try:
        return _transcribe_faster(audio_path, model_size)
    except ImportError:
        log.info("faster-whisper not installed – falling back to openai-whisper")
    return _transcribe_openai(audio_path, model_size)


def _transcribe_faster(audio_path: str, model_size: str) -> list[Word]:
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]

    model = WhisperModel(model_size, device="auto", compute_type="auto")
    segments_iter, _info = model.transcribe(
        audio_path, word_timestamps=True, vad_filter=True
    )
    words: list[Word] = []
    for seg in segments_iter:
        for w in seg.words or []:
            words.append(Word(text=w.word.strip(), start=w.start, end=w.end))
    return words


def _transcribe_openai(audio_path: str, model_size: str) -> list[Word]:
    import whisper  # type: ignore[import-untyped]

    model = whisper.load_model(model_size)
    result = model.transcribe(audio_path, word_timestamps=True)

    words: list[Word] = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            words.append(
                Word(
                    text=w["word"].strip(),
                    start=w["start"],
                    end=w["end"],
                )
            )
    return words


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------
_SENTENCE_END = re.compile(r"[.!?]$")


def _sentence_boundary_score(seg: Segment) -> float:
    """1.0 if both ends are on sentence boundaries, 0.5 if one, else 0."""
    starts_ok = bool(_SENTENCE_END.search(seg.words[0].text)) if seg.words else False
    # Check the word *before* the first word? Not available here, so we
    # check whether the first word is capitalised as a rough proxy.
    first_cap = seg.words[0].text[0].isupper() if seg.words and seg.words[0].text else False
    ends_ok = bool(_SENTENCE_END.search(seg.words[-1].text)) if seg.words else False
    score = 0.0
    if first_cap:
        score += 0.5
    if ends_ok:
        score += 0.5
    return score


def _speech_rate_score(seg: Segment) -> float:
    """Higher word-rate → more engaging (capped)."""
    if seg.duration <= 0:
        return 0.0
    rate = len(seg.words) / seg.duration  # words per second
    # Typical conversational rate is 2-3 wps; cap score at 4 wps
    return min(rate / 4.0, 1.0)


def _silence_penalty(seg: Segment) -> float:
    """Penalise long pauses between words."""
    if len(seg.words) < 2:
        return 0.0
    gaps = [
        seg.words[i + 1].start - seg.words[i].end for i in range(len(seg.words) - 1)
    ]
    max_gap = max(gaps) if gaps else 0.0
    avg_gap = sum(gaps) / len(gaps) if gaps else 0.0
    # Penalise if max gap > 2s or average gap > 0.8s
    penalty = 0.0
    if max_gap > 2.0:
        penalty += 0.3
    if avg_gap > 0.8:
        penalty += 0.2
    return penalty


def _keyword_score(seg: Segment, keywords: Sequence[str]) -> float:
    """Boost segments containing user-specified keywords."""
    if not keywords:
        return 0.0
    text_lower = seg.text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return min(hits / max(len(keywords), 1), 1.0)


def score_segment(
    seg: Segment,
    keywords: Sequence[str] = (),
    weights: Optional[dict[str, float]] = None,
) -> float:
    """Compute a composite score in [0, 1]."""
    w = weights or {
        "boundary": 0.30,
        "rate": 0.25,
        "silence": 0.20,
        "keyword": 0.25,
    }
    raw = (
        w["boundary"] * _sentence_boundary_score(seg)
        + w["rate"] * _speech_rate_score(seg)
        - w["silence"] * _silence_penalty(seg)
        + w["keyword"] * _keyword_score(seg, keywords)
    )
    return max(0.0, min(raw, 1.0))


# ---------------------------------------------------------------------------
# Windowing & selection
# ---------------------------------------------------------------------------
def _build_candidates(
    words: list[Word],
    min_dur: float = 15.0,
    max_dur: float = 60.0,
    step_sec: float = 5.0,
) -> list[Segment]:
    """Slide a window over the word list and return candidate segments."""
    if not words:
        return []

    candidates: list[Segment] = []
    total_dur = words[-1].end - words[0].start

    start_time = words[0].start
    while start_time + min_dur <= words[-1].end:
        # Collect words in [start_time, start_time + max_dur]
        end_time = start_time + max_dur
        window_words = [w for w in words if w.start >= start_time and w.end <= end_time]

        if window_words and (window_words[-1].end - window_words[0].start) >= min_dur:
            # Try to snap the end to a sentence boundary
            snapped = _snap_to_sentence_end(window_words)
            if snapped and (snapped[-1].end - snapped[0].start) >= min_dur:
                window_words = snapped
            candidates.append(Segment(words=window_words))

        start_time += step_sec

    return candidates


def _snap_to_sentence_end(words: list[Word]) -> list[Word]:
    """Trim the window so it ends on the last sentence-ending word."""
    for i in range(len(words) - 1, -1, -1):
        if _SENTENCE_END.search(words[i].text):
            return words[: i + 1]
    return words  # no sentence boundary found – keep as-is


def _remove_overlapping(segments: list[Segment], min_gap: float = 2.0) -> list[Segment]:
    """Greedily remove segments that overlap with higher-scored ones."""
    segments = sorted(segments, key=lambda s: s.score, reverse=True)
    selected: list[Segment] = []
    for seg in segments:
        if all(
            seg.end + min_gap <= s.start or seg.start >= s.end + min_gap
            for s in selected
        ):
            selected.append(seg)
    return sorted(selected, key=lambda s: s.start)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def select_clips(
    audio_path: str | Path,
    *,
    model_size: str = "base",
    num_clips: int = 5,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    keywords: Sequence[str] = (),
) -> list[Segment]:
    """End-to-end: transcribe → score → pick top clips.

    Returns up to *num_clips* non-overlapping :class:`Segment` objects,
    sorted by their position in the original media.
    """
    log.info("Transcribing %s (model=%s) …", audio_path, model_size)
    words = transcribe(audio_path, model_size)
    log.info("Got %d words, building candidate windows …", len(words))

    candidates = _build_candidates(words, min_dur=min_duration, max_dur=max_duration)
    log.info("Evaluating %d candidate segments …", len(candidates))

    for seg in candidates:
        seg.score = score_segment(seg, keywords=keywords)

    top = _remove_overlapping(candidates)[:num_clips]
    for i, seg in enumerate(top, 1):
        seg.label = f"clip_{i:02d}"
        log.info(
            '  %s  %.1fs-%.1fs  score=%.3f  "%s..."',
            seg.label,
            seg.start,
            seg.end,
            seg.score,
            seg.text[:60],
        )
    return top
