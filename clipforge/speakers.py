"""
clipforge.speakers – Speaker diarisation helpers
=================================================

Uses ``pyannote.audio`` (if available) to assign speaker labels to
word-level timestamps.  When pyannote is not installed the module
gracefully degrades: every word is labelled ``SPEAKER_00``.

The diarisation result can be used by the subtitle generator to colour-code
speakers or by the clip selector to prefer multi-speaker segments.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

log = logging.getLogger(__name__)


@dataclass
class SpeakerTurn:
    speaker: str
    start: float
    end: float


# ---------------------------------------------------------------------------
# Diarisation
# ---------------------------------------------------------------------------
def diarize(
    audio_path: str | Path,
    *,
    hf_token: Optional[str] = None,
    num_speakers: Optional[int] = None,
    min_speakers: int = 1,
    max_speakers: int = 6,
) -> list[SpeakerTurn]:
    """Run speaker diarisation on *audio_path*.

    Parameters
    ----------
    hf_token:
        Hugging Face token (needed to accept the pyannote licence).
        Falls back to the ``HF_TOKEN`` env-var.
    num_speakers:
        If known, force the pipeline to use this many speakers.
    """
    token = hf_token or os.environ.get("HF_TOKEN")

    try:
        return _diarize_pyannote(
            str(audio_path),
            token=token,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    except ImportError:
        log.warning(
            "pyannote.audio not installed – skipping speaker diarisation. "
            "Install with:  pip install pyannote.audio"
        )
    except Exception as exc:
        log.warning("Speaker diarisation failed: %s", exc)

    return []


def _diarize_pyannote(
    audio_path: str,
    *,
    token: Optional[str],
    num_speakers: Optional[int],
    min_speakers: int,
    max_speakers: int,
) -> list[SpeakerTurn]:
    from pyannote.audio import Pipeline  # type: ignore[import-untyped]

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=token
    )
    kwargs: dict = {}
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers
    else:
        kwargs["min_speakers"] = min_speakers
        kwargs["max_speakers"] = max_speakers

    diarization = pipeline(audio_path, **kwargs)

    turns: list[SpeakerTurn] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append(SpeakerTurn(speaker=speaker, start=turn.start, end=turn.end))
    log.info("Diarised %d speaker turns", len(turns))
    return turns


# ---------------------------------------------------------------------------
# Assign speaker labels to words
# ---------------------------------------------------------------------------
def assign_speakers(
    words: Sequence,
    turns: list[SpeakerTurn],
    default_speaker: str = "SPEAKER_00",
) -> list[dict]:
    """Return a list of dicts ``{text, start, end, speaker}``."""
    result: list[dict] = []
    for w in words:
        text = w.text if hasattr(w, "text") else w["text"]
        start = w.start if hasattr(w, "start") else w["start"]
        end = w.end if hasattr(w, "end") else w["end"]
        mid = (start + end) / 2.0
        speaker = default_speaker
        for t in turns:
            if t.start <= mid <= t.end:
                speaker = t.speaker
                break
        result.append({"text": text, "start": start, "end": end, "speaker": speaker})
    return result


def count_speakers(turns: list[SpeakerTurn]) -> int:
    """Return the number of unique speakers."""
    return len({t.speaker for t in turns})
