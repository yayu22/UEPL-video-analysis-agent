<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# UEPL Driver Profiling & Equipment Analysis — Frontend

React + Vite UI for analysing truck dashcam clips (cabin or front camera). Upload a
clip, pick the camera, and see the detected violations, equipment issues, and a
**driver safety profile** (score + grade).

> **Architecture change:** the Gemini API key is no longer bundled into the browser.
> All model calls go through the Python backend in [`backend/`](backend/), which
> holds the key server-side. This frontend only talks to that backend.

## Run locally
**Prerequisites:** Node.js, and the backend running (see [`backend/README.md`](backend/README.md)).

1. Start the backend (in `backend/`): `uvicorn api:app --port 8000`
2. Install deps: `npm install`
3. (optional) point at a non-default backend: create `.env.local` with
   `VITE_API_BASE=http://localhost:8000`
4. Run the dev server: `npm run dev`

## What it shows
- **Driver Safety Profile** — A–F grade, 0–100 score, top risks, summary.
- **Analysis Log** — each detected event with severity, confidence, evidence, and a
  click-to-seek jump to that moment in the video.
- **Violation Checklist** — per-category status (severity-coloured).
- **Equipment Checklist** — camera/video QA faults with reasons.

Cabin vs Front is sent to the backend, which runs the matching prompt and
auto-detects a wrong camera view (showing a warning instead of bad results).
