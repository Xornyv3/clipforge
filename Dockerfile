# ─── ClipForge — Multi-stage Docker image ────────────────────────
FROM python:3.10-slim AS base

# System deps: ffmpeg, fonts, opencv libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    fonts-liberation \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Copy source code
COPY clipforge/ ./clipforge/
COPY web/ ./web/
COPY run.py .
COPY rerender.py .

# Whisper model cache — download tiny model at build time for faster cold starts
# (tiny uses ~400MB RAM; base needs ~1GB which exceeds Render free tier)
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cpu', compute_type='int8')" || true

# Render sets PORT env var; default to 8000
ENV PORT=8000
EXPOSE 8000

# Use shell form so $PORT is expanded at runtime
CMD uvicorn web.app:app --host 0.0.0.0 --port $PORT
