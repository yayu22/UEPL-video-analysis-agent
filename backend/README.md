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
| `api.py` | FastAPI app the frontend calls |
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
uvicorn api:app --reload --port 8000
# POST /api/analyze  (multipart: file=<video>, camera=cabin|front)
# GET  /health   GET /api/taxonomy
```

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

## Deploy (GCP, aligned with AFDD)
Cloud Run is the natural fit:
```bash
# Dockerfile: python:3.11-slim + pip install -r requirements.txt + gunicorn
gunicorn -k uvicorn.workers.UvicornWorker api:app --bind :$PORT --timeout 600
```
Set `GENAI_API_KEY` as a Cloud Run secret. Raise the request timeout — Files-API
upload + full-video analysis of a 1-min clip takes tens of seconds.

For **fleet-scale** automatic profiling (no UI), adapt `worker.py`: poll the fleet
API for new trips, pull the signed video URL, `analyze_clip`, and POST the profile
back — exactly the loop the AFDD agents already run on GCP.

## Tuning knobs (all in `config.py` / env)
- `UEPL_BEHAVIOUR_MODEL` — upgrade to `gemini-3.7-flash` (cheaper audio, more accurate).
- `UEPL_FRONT_FPS` / `UEPL_CABIN_FPS` — frame sampling density vs. cost.
- `CATEGORY_WEIGHTS`, `SEVERITY_POINTS`, `_GRADE_BANDS`, `RISK_SCALE` — scoring model.
