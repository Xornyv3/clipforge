"""Speaker change detection using audio features.

Provides two backends:
  1. pyannote.audio (high quality, requires HF_TOKEN env var)
  2. Energy + MFCC based heuristic (lightweight fallback)
"""

import os
import numpy as np
from dataclasses import dataclass

from . import utils


@dataclass
class SpeakerSegment:
    """A time span attributed to one speaker."""
    start: float
    end: float
    speaker: str


def detect_speakers(
    audio_path: str,
    num_speakers: int = None,
) -> list:
    """Detect speaker turns in an audio file.

    Returns a list of :class:`SpeakerSegment` objects.
    """
    result = _try_pyannote(audio_path, num_speakers)
    if result is not None:
        return result

    utils.log("Using energy-based speaker detection (install pyannote.audio for better results)")
    return _energy_based_detection(audio_path)


# ------------------------------------------------------------------
# Backend 1 — pyannote.audio
# ------------------------------------------------------------------

def _try_pyannote(audio_path: str, num_speakers=None):
    try:
        from pyannote.audio import Pipeline
        import torch
    except ImportError:
        return None

    token = os.environ.get("HF_TOKEN")
    if not token:
        utils.log("Skipping pyannote: set HF_TOKEN env var to enable")
        return None

    utils.log("Using pyannote.audio for speaker diarization")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=token,
    )
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))

    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers

    diarization = pipeline(audio_path, **kwargs)

    segments = [
        SpeakerSegment(start=turn.start, end=turn.end, speaker=speaker)
        for turn, _, speaker in diarization.itertracks(yield_label=True)
    ]
    unique = len({s.speaker for s in segments})
    utils.log(f"Detected {unique} speakers, {len(segments)} turns")
    return segments


# ------------------------------------------------------------------
# Backend 2 — lightweight energy / MFCC heuristic
# ------------------------------------------------------------------

def _energy_based_detection(audio_path: str) -> list:
    try:
        import librosa
    except ImportError:
        utils.log("Warning: librosa not installed — skipping speaker detection")
        return []

    y, sr = librosa.load(audio_path, sr=16000, mono=True)

    frame_len = int(0.5 * sr)   # 500 ms windows
    hop_len = int(0.25 * sr)    # 250 ms hop

    energy = []
    mfcc_features = []

    for i in range(0, len(y) - frame_len, hop_len):
        frame = y[i : i + frame_len]
        energy.append(float(np.sqrt(np.mean(frame ** 2))))
        mfcc = librosa.feature.mfcc(y=frame, sr=sr, n_mfcc=13)
        mfcc_features.append(np.mean(mfcc, axis=1))

    if not mfcc_features:
        return []

    mfcc_matrix = np.array(mfcc_features)
    energy = np.array(energy)

    # Simple change-point detection via MFCC distance spikes
    diffs = np.linalg.norm(np.diff(mfcc_matrix, axis=0), axis=1)
    threshold = np.mean(diffs) + 1.5 * np.std(diffs)

    changes = [0]
    for i, d in enumerate(diffs):
        if d > threshold and energy[i] > np.mean(energy) * 0.3:
            changes.append(i + 1)
    changes.append(len(mfcc_features))

    segments = []
    speaker_id = 0
    for i in range(len(changes) - 1):
        start_t = changes[i] * (hop_len / sr)
        end_t = changes[i + 1] * (hop_len / sr)
        if end_t - start_t < 1.0:
            continue
        segments.append(
            SpeakerSegment(
                start=start_t,
                end=end_t,
                speaker=f"SPEAKER_{speaker_id % 2}",
            )
        )
        speaker_id += 1

    # Merge consecutive segments from the same speaker
    merged = []
    for seg in segments:
        if merged and merged[-1].speaker == seg.speaker:
            merged[-1].end = seg.end
        else:
            merged.append(seg)

    unique = len({s.speaker for s in merged})
    utils.log(f"Detected {unique} speaker patterns, {len(merged)} segments")
    return merged
