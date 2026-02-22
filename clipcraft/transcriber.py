"""Transcribe audio using OpenAI Whisper with word-level timestamps."""

from . import utils


def transcribe(audio_path: str, model_size: str = "base") -> list:
    """Run Whisper on an audio file and return segments with word timestamps.

    Each returned segment is a dict::

        {
            "start": float,   # seconds
            "end":   float,
            "text":  str,
            "words": [{"word": str, "start": float, "end": float}, ...]
        }
    """
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "OpenAI Whisper is required.  Run:  pip install openai-whisper"
        )

    utils.log(f"Loading Whisper model: {model_size}")
    model = whisper.load_model(model_size)

    utils.log("Transcribing audio (this may take a while)...")
    result = model.transcribe(
        audio_path,
        word_timestamps=True,
        verbose=False,
    )

    segments = []
    for seg in result.get("segments", []):
        words = [
            {
                "word": w["word"].strip(),
                "start": w["start"],
                "end": w["end"],
            }
            for w in seg.get("words", [])
        ]
        segments.append(
            {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
                "words": words,
            }
        )

    total_words = sum(len(s["words"]) for s in segments)
    utils.log(f"Transcription complete: {len(segments)} segments, {total_words} words")
    return segments
