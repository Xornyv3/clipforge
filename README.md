# ClipForge

**AI-powered podcast & interview → short-clip generator. CLI + Web SaaS.**

Turn long podcast/interview videos into viral short clips for **TikTok**, **Instagram Reels**, and **YouTube Shorts**.

## Features

- Paste a YouTube URL or upload a video file
- AI transcription + smart clip selection (faster-whisper)
- Face-aware portrait cropping (OpenCV)
- Burn-in animated subtitles (ASS format)
- Optional background music mixing with speech ducking
- Configurable quality, aspect ratio, and subtitle style
- Web UI with async job queue (FastAPI + Celery + Redis)
- Docker Compose for one-command deployment

---

## Web App — Quick Start (Docker)

```bash
# 1. Copy env file
cp .env.example .env

# 2. Build and start all services
docker compose up --build -d

# 3. Open the web UI
#    → http://localhost:8000
```

| Service  | Role                           | Port |
|----------|--------------------------------|------|
| `web`    | FastAPI server + frontend      | 8000 |
| `worker` | Celery worker (video pipeline) | —    |
| `redis`  | Message broker + result store  | 6379 |

---

## Web App — Local Dev (without Docker)

```bash
# 1. Install Python deps
pip install -r requirements-web.txt

# 2. Ensure ffmpeg is on your PATH
# 3. Start Redis locally (port 6379)

# 4. Start the Celery worker (terminal 1)
celery -A web.tasks worker --loglevel=info --concurrency=1

# 5. Start the FastAPI server (terminal 2)
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000

# 6. Open http://localhost:8000
```

---

## Architecture

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Browser / UI   │─────▶│  FastAPI (web)   │─────▶│  Redis broker   │
└─────────────────┘      └─────────────────┘      └────────┬────────┘
                                                           │
                                                           ▼
                                                  ┌─────────────────┐
                                                  │  Celery Worker   │
                                                  │  1. Download     │
                                                  │  2. Transcribe   │
                                                  │  3. Select clips │
                                                  │  4. Render (ffmpeg)│
                                                  │  5. Mix music    │
                                                  └─────────────────┘
```

---

## API Endpoints

| Method   | Path                                    | Description                                    |
|----------|-----------------------------------------|------------------------------------------------|
| `POST`   | `/api/jobs`                             | Create job (form-data, optional file upload)    |
| `POST`   | `/api/jobs/json`                        | Create job from JSON body                       |
| `GET`    | `/api/jobs`                             | List all jobs                                   |
| `GET`    | `/api/jobs/{id}`                        | Get job status + clips                          |
| `GET`    | `/api/jobs/{id}/clips/{filename}`       | Download a rendered clip                        |
| `DELETE` | `/api/jobs/{id}`                        | Delete job and its files                        |
| `GET`    | `/`                                     | Web UI                                          |

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Web server port |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `CLIPFORGE_UPLOAD_DIR` | `./uploads` | Upload storage path |
| `CLIPFORGE_OUTPUT_DIR` | `./outputs` | Output clips path |
| `CLIPFORGE_WORK_DIR` | `./tmp_work` | Temporary work directory |
| `CLIPFORGE_MAX_UPLOAD_MB` | `500` | Max file upload size (MB) |
| `CLIPFORGE_MAX_DURATION` | `3600` | Max video duration (seconds) |
| `CLIPFORGE_API_KEY` | _(empty)_ | API auth key (empty = no auth) |
| `CLIPFORGE_PUBLIC_URL` | `http://localhost:8000` | Public URL for download links |

---

## Production Deployment

### Option A: VPS (DigitalOcean, Hetzner, etc.)

1. Provision a server (4+ CPU, 8GB RAM, 100GB SSD recommended)
2. Install Docker + Docker Compose
3. Clone repo, `cp .env.example .env`, set your domain in `.env`
4. `docker compose up -d`
5. Point DNS to server IP
6. Use the included `Caddyfile` for automatic HTTPS

### Option B: Railway / Render / Fly.io

Push to Git, connect your platform, set environment variables, deploy. You'll need a Redis add-on.

---

## CLI Usage

The original CLI tools still work independently:

```bash
# Full pipeline
python run.py "https://youtube.com/watch?v=..." --clips 5 --music "https://..."

# Re-render with custom settings
python rerender.py
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `source` | _(required)_ | Local video/audio path **or** YouTube URL |
| `-o, --output-dir` | `./clips_output` | Where clips are saved |
| `-n, --num-clips` | `5` | Number of clips to extract |
| `--min-duration` | `15` | Min clip length (seconds) |
| `--max-duration` | `60` | Max clip length (seconds) |
| `--keywords` | | Comma-separated keywords to boost |
| `--model` | `base` | Whisper model (`tiny`…`large-v3`) |
| `--aspect` | `9:16` | `9:16`, `16:9`, `1:1`, `original` |
| `--no-subs` | | Skip subtitle burn-in |
| `--no-grade` | | Skip cinematic colour grade |
| `--music` | | Background-music file or YouTube URL |
| `--music-vol` | `0.10` | Music volume (0.0–1.0) |

---

## Project Structure

```
├── run.py                          # CLI entry point
├── rerender.py                     # Configurable re-render script
├── requirements.txt                # CLI dependencies
├── requirements-web.txt            # Web + CLI dependencies
├── Dockerfile                      # Docker image
├── docker-compose.yml              # Full stack (web + worker + redis)
├── Caddyfile                       # Production reverse proxy
├── .env.example                    # Environment template
├── clipforge/                      # Core pipeline modules
│   ├── __init__.py
│   ├── patches/                    # ML-library compatibility patches
│   ├── downloader.py               # YouTube download + local-file resolution
│   ├── clip_selector.py            # Whisper transcription + segment scoring
│   ├── subtitles.py                # TikTok-style ASS subtitle generation
│   ├── video.py                    # ffmpeg extraction, face crop, grading
│   ├── music.py                    # Background-music download + mixing
│   └── speakers.py                 # Speaker diarisation (optional)
└── web/                            # Web SaaS layer
    ├── __init__.py
    ├── config.py                   # Environment-based config
    ├── models.py                   # Pydantic request/response models
    ├── store.py                    # JSON-file job store
    ├── tasks.py                    # Celery async task
    ├── app.py                      # FastAPI application
    └── static/
        ├── index.html              # Web UI
        ├── style.css               # Dark theme CSS
        └── app.js                  # Frontend JavaScript
```

---

## Prerequisites

| Tool | Install |
|------|---------|
| **Python >= 3.10** | [python.org](https://python.org) |
| **FFmpeg + ffprobe** | [ffmpeg.org](https://ffmpeg.org/download.html) |
| **Redis** | [redis.io](https://redis.io) (or use Docker) |
| **Docker** _(recommended)_ | [docker.com](https://docker.com) |

---

## License

MIT
