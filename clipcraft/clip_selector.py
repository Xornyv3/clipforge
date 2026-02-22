"""Intelligently select the best clip-worthy moments from a transcription.

Candidate clips are aligned to sentence boundaries and scored based on
how natural and complete they sound, word density, engagement signals,
and pause distribution.
"""

from dataclasses import dataclass, field
from . import utils


@dataclass
class Clip:
    """A selected clip with timing, transcript, and quality score."""
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)
    score: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


def select_clips(
    segments: list,
    count: int = 5,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> list:
    """Return the *count* best non-overlapping clips from *segments*.

    Parameters
    ----------
    segments : list[dict]
        Transcription segments (each with ``words``, ``start``, ``end``).
    count : int
        How many clips to return.
    min_duration, max_duration : float
        Duration window in seconds.

    Returns
    -------
    list[Clip]
        Selected clips sorted by position in the video.
    """
    # Flatten word-level timestamps
    all_words = []
    for seg in segments:
        all_words.extend(seg.get("words", []))

    if not all_words:
        utils.log("No word-level timestamps — falling back to segment-level selection")
        return _fallback_selection(segments, count, min_duration, max_duration)

    boundaries = _find_sentence_boundaries(all_words)
    candidates = _generate_candidates(all_words, boundaries, min_duration, max_duration)

    utils.log(f"Evaluating {len(candidates)} candidate clips...")

    for clip in candidates:
        clip.score = _score_clip(clip)

    candidates.sort(key=lambda c: c.score, reverse=True)

    # Greedy non-overlapping selection
    selected = []
    for clip in candidates:
        if len(selected) >= count:
            break
        if not any(_overlaps(clip, s) for s in selected):
            selected.append(clip)

    selected.sort(key=lambda c: c.start)

    utils.log(f"Selected {len(selected)} clips")
    for i, c in enumerate(selected):
        utils.log(
            f"  Clip {i + 1}: {c.start:.1f}s – {c.end:.1f}s "
            f"({c.duration:.1f}s)  score={c.score:.1f}"
        )
    return selected


# ------------------------------------------------------------------
# Sentence boundaries
# ------------------------------------------------------------------

def _find_sentence_boundaries(words: list) -> list:
    """Return word indices that mark the start of a new sentence."""
    boundaries = [0]
    for i, w in enumerate(words):
        text = w["word"].rstrip()
        if text and text[-1] in ".!?":
            if i + 1 < len(words):
                boundaries.append(i + 1)
    boundaries.append(len(words))
    return sorted(set(boundaries))


# ------------------------------------------------------------------
# Candidate generation
# ------------------------------------------------------------------

def _generate_candidates(words, boundaries, min_dur, max_dur):
    candidates = []
    for i, s_idx in enumerate(boundaries):
        if s_idx >= len(words):
            break
        for e_idx in boundaries[i + 1:]:
            if e_idx > len(words):
                break
            start_t = words[s_idx]["start"]
            end_t = words[min(e_idx - 1, len(words) - 1)]["end"]
            dur = end_t - start_t
            if dur < min_dur:
                continue
            if dur > max_dur:
                break

            clip_words = words[s_idx:e_idx]
            text = " ".join(w["word"] for w in clip_words)
            candidates.append(
                Clip(start=start_t, end=end_t, text=text, words=clip_words)
            )
    return candidates


# ------------------------------------------------------------------
# Scoring
# ------------------------------------------------------------------

def _score_clip(clip: Clip) -> float:
    """Score a clip from 0–100 on naturalness and engagement."""
    score = 0.0
    text = clip.text

    # 1) Sentence completeness (0–25)
    if text and text[0].isupper():
        score += 10
    stripped = text.rstrip()
    if stripped and stripped[-1] in ".!?":
        score += 15

    # 2) Word density — words per second (0–20)
    if clip.duration > 0:
        wps = len(clip.words) / clip.duration
        if 2.0 <= wps <= 3.5:
            score += 20
        elif 1.5 <= wps <= 4.0:
            score += 12
        elif wps > 0.5:
            score += 5

    # 3) Engagement signals (0–25)
    score += min(text.count("?") * 8, 16)
    score += min(text.count("!") * 5, 10)
    words_list = text.lower().split()
    total = max(len(words_list), 1)
    lexical_diversity = len(set(words_list)) / total
    score += lexical_diversity * 10

    # 4) Duration fitness (0–15)
    if 20 <= clip.duration <= 45:
        score += 15
    elif 15 <= clip.duration <= 60:
        score += 10
    else:
        score += 3

    # 5) No long internal pauses (0–15)
    max_gap = 0.0
    for j in range(1, len(clip.words)):
        gap = clip.words[j]["start"] - clip.words[j - 1]["end"]
        if gap > max_gap:
            max_gap = gap
    if max_gap < 1.0:
        score += 15
    elif max_gap < 2.0:
        score += 10
    elif max_gap < 3.0:
        score += 5

    return score


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _overlaps(a: Clip, b: Clip) -> bool:
    return a.start < b.end and b.start < a.end


def _fallback_selection(segments, count, min_dur, max_dur):
    """Segment-level fallback when word timestamps aren't available."""
    clips = []
    buf_text = ""
    buf_start = None
    buf_words = []

    for seg in segments:
        if buf_start is None:
            buf_start = seg["start"]
        buf_text += " " + seg["text"]
        buf_words.extend(seg.get("words", []))
        dur = seg["end"] - buf_start

        if dur >= min_dur:
            if dur <= max_dur:
                clips.append(
                    Clip(
                        start=buf_start,
                        end=seg["end"],
                        text=buf_text.strip(),
                        words=buf_words,
                        score=dur,
                    )
                )
            buf_text = ""
            buf_start = None
            buf_words = []

    clips.sort(key=lambda c: c.score, reverse=True)
    return clips[:count]
