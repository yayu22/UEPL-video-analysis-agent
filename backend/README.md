# UEPL Driver Profiling & Equipment Analysis — Backend

Python backend that analyses truck dashcam clips with Gemini and returns
**driver-behaviour violations**, **equipment/QA issues**, and a **driver safety
profile** (weighted risk score + A–F grade). The Gemini key stays **server-side**;
the browser never sees it.

Built to align with the deployed **AFDD annotator agents** (`google-genai` SDK,
`gemini-2.5-flash`, `temperature=0`, thinking config) so it drops into the same
GCP deployment.

## Why this exists / what changed vs. the old app
- **Files API, full video** — the old app inlined the whole video as base64 (fails
  above ~20 MB) and, for the road camera, chopped it into 2fps stills that
  structurally *cannot* see motion (braking/swerve). Here both cameras send the
  **whole video** to Gemini via the Files API, sampled at a higher FPS for the
  front camera so transient motion is actually captured.
- **Server-side key** — no more `process.env.API_KEY` compiled into the browser.
- **Enum-constrained output + validation** — the model can only emit valid
  categories, and a Python net drops anything off-taxonomy, so the UI never
  desyncs from the log.
- **Robustness** — retries w/ backoff, `finish_reason` handling (MAX_TOKENS /
  SAFETY), loosened safety filters (dashcam footage trips content filters),
  single upload reused for behaviour + equipment.
- **Driver profiling** — severity-weighted scoring into a grade + summary.

## Layout
| file | purpose |
|------|---------|
| `config.py` | models, FPS, taxonomies (enums), severity weights — single source of truth |
| `prompts.py` | the cabin / front / equipment prompts (grounded in the real Monit overlay) |
| `gemini_client.py` | Files API upload+poll, retries, structured output, safety, validation |
| `analysis.py` | orchestration: upload once → behaviour + equipment → profile |
| `scoring.py` | driver profiling (per-clip + multi-clip aggregate) |
| `app.py` | FastAPI app the frontend calls |
| `worker.py` | CLI / batch entry point (also an AFDD-style fleet-worker template) |

## Setup
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate      # (Windows Git Bash)
pip install -r requirements.txt
cp .env.example .env        # then put your GENAI_API_KEY in .env
export GENAI_API_KEY=...    # or rely on .env / your shell
```

## Run the API
```bash
uvicorn app:app --reload --port 8000
# POST /api/analyze       (multipart: file=<video>, camera=cabin|front)   [direct mode]
# POST /api/analyze-url   (json: {video_url, camera})                     [url/blob mode]
# GET  /health   GET /api/config   GET /api/taxonomy
```

### Ingestion modes (config-switchable, for different deploy targets)
The video is **always** processed as a temp file and deleted — nothing is persisted.
Two ways it can arrive, chosen by `UEPL_INGEST_MODE` (advertised at `GET /api/config`):
- **`direct`** — browser POSTs the file to `/api/analyze`. Use on **Cloud Run / any
  server** that accepts large request bodies.
- **`url`** — browser uploads to blob storage, then POSTs the URL to `/api/analyze-url`,
  and the server downloads it. Required on **Vercel** (functions cap request bodies at
  4.5 MB). The uploaded blob is deleted right after analysis (see the frontend).

## Quick local test (CLI) against sample clips
```bash
# one clip
python worker.py --file "D:/Driver Behaviour analysis Agent/Front (Road-side)/44.mp4" --camera front
# a whole folder -> per-clip results + an aggregate driver profile
python worker.py --dir "D:/Driver Behaviour analysis Agent/Front (Road-side)" --camera front --out result.json
```
> Note: the sample "Front (Road-side)" folder actually contains a mix of front
> and in-cabin clips. The prompts self-detect a wrong view and suppress results
> with a `WRONG_VIEW` warning instead of producing garbage — so run cabin clips
> with `--camera cabin`.

## Response shape (`POST /api/analyze`)
```jsonc
{
  "camera": "front",
  "view_ok": true,
  "warnings": [],
  "events": [
    { "reason": "...", "category": "Speed Violation", "severity": "high",
      "confidence": 0.86, "timestamp": "19:03:19", "start_s": 12.0, "end_s": 15.0,
      "speed_kmh": 61, "camera": "front" }
  ],
  "equipment": [
    { "reason": "...", "issue": "Poor Night Vision", "severity": "medium", "confidence": 0.7 }
  ],
  "profile": {
    "safety_score": 72, "grade": "C", "grade_label": "Fair",
    "risk_points": 5.6, "confirmed_event_count": 2, "review_event_count": 1,
    "per_category": { "Speed Violation": { "count": 1, "max_severity": "high", "points": 9.6 } },
    "top_risks": [ ... ], "summary": "Safety score 72/100 (Fair). Main issues: ...",
    "review_items": [ ... ]
  }
}
```

## Deploy — pick a target, it's just configuration

### A) Vercel (this folder as the project root)
`app.py` exposes `app`, which Vercel auto-detects as a FastAPI function; `vercel.json`
sets `maxDuration`. Because Vercel caps request bodies at **4.5 MB**, you MUST use the
URL ingestion path:
```bash
# In the Vercel project (Root Directory = backend):
#   Env:  GENAI_API_KEY, UEPL_INGEST_MODE=url, UEPL_CORS_ORIGINS=https://<frontend>
#   The frontend uploads to Vercel Blob and calls /api/analyze-url.
```
Note: `maxDuration: 300` (in `vercel.json`) needs Pro/Fluid compute; Hobby caps at
60 s, which may time out on long clips. Bump/lower it there.

### B) Cloud Run / any server (aligned with AFDD, recommended for large clips)
```bash
# Dockerfile: python:3.11-slim + pip install -r requirements.txt + gunicorn
gunicorn -k uvicorn.workers.UvicornWorker app:app --bind :$PORT --timeout 600
#   Env:  GENAI_API_KEY (secret), UEPL_INGEST_MODE=direct
```
Set `GENAI_API_KEY` as a secret and raise the request timeout — full-video analysis of
a 1-min clip takes tens of seconds. No body-size cap, so `direct` upload works.

### C) Plain cloud VM (GCE / EC2 — the simplest option, matches the AFDD/monit systemd pattern)
A VM has **no serverless limits**, so use `direct` mode — **no blob storage needed**.
The Vercel files (`vercel.json`, `../api/*.ts`) are simply unused; leave or delete them.
```bash
# on the VM
git clone <repo> && cd UEPL-video-analysis-agent/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt gunicorn
printf 'GENAI_API_KEY=YOUR_KEY\nUEPL_INGEST_MODE=direct\nUEPL_CORS_ORIGINS=https://YOUR_FRONTEND\n' > .env
# smoke test:
gunicorn -k uvicorn.workers.UvicornWorker app:app --bind 127.0.0.1:8000 --workers 2 --timeout 600
```
Run it as a **systemd** service (like monit's `daphne.service`) — `/etc/systemd/system/uepl.service`:
```ini
[Unit]
Description=UEPL analysis backend
After=network.target
[Service]
WorkingDirectory=/opt/uepl/backend
EnvironmentFile=/opt/uepl/backend/.env
ExecStart=/opt/uepl/backend/.venv/bin/gunicorn -k uvicorn.workers.UvicornWorker app:app --bind 127.0.0.1:8000 --workers 2 --timeout 600
Restart=always
User=www-data
[Install]
WantedBy=multi-user.target
```
`sudo systemctl enable --now uepl`. Then put **nginx** in front for TLS and — crucially —
to allow large uploads (the direct path sends the whole video):
```nginx
server {
  server_name api.yourdomain.com;
  client_max_body_size 550M;      # MUST exceed UEPL_MAX_UPLOAD_BYTES (default 500M)
  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_read_timeout 600s;       # full-video analysis takes tens of seconds
    proxy_request_buffering off;   # stream large uploads instead of buffering
  }
}
```
Point the frontend at it: `VITE_UPLOAD_MODE=direct`, `VITE_API_BASE=https://api.yourdomain.com`.
Build the frontend (`npm run build`) and serve `dist/` from the same nginx, or host it on Vercel.

**Switching targets is config-only:** flip `UEPL_INGEST_MODE` on the backend and
`VITE_UPLOAD_MODE` + `VITE_API_BASE` on the frontend — no code changes.

For **fleet-scale** automatic profiling (no UI), adapt `worker.py`: poll the fleet
API for new trips, pull the signed video URL, `analyze_clip`, and POST the profile
back — exactly the loop the AFDD agents already run on GCP.

## Tuning knobs (all in `config.py` / env)
- `UEPL_BEHAVIOUR_MODEL` — upgrade to `gemini-3.7-flash` (cheaper audio, more accurate).
- `UEPL_FRONT_FPS` / `UEPL_CABIN_FPS` — frame sampling density vs. cost.
- `CATEGORY_WEIGHTS`, `SEVERITY_POINTS`, `_GRADE_BANDS`, `RISK_SCALE` — scoring model.
