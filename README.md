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

1. Start the backend (in `backend/`): `uvicorn app:app --port 8000`
2. Install deps: `npm install`
3. (optional) copy `.env.example` → `.env.local` and set `VITE_API_BASE` / `VITE_UPLOAD_MODE`
4. Run the dev server: `npm run dev`

## Upload modes (config-switchable)
Set `VITE_UPLOAD_MODE`:
- **`direct`** (default) — POST the file straight to the backend. Use when the backend
  is on **Cloud Run / any server**. Set `VITE_API_BASE` to its URL.
- **`blob`** — upload the clip to **Vercel Blob** first, send only the URL to the
  backend, then delete the blob. Required when the backend is on **Vercel** (4.5 MB
  body cap). Nothing is kept — the blob is removed right after analysis.

## Deploy on Vercel (blob mode)
1. Deploy this folder as a Vercel project (Vite is auto-detected). The Node functions
   [`api/upload.ts`](api/upload.ts) (mints the blob client token) and
   [`api/cleanup.ts`](api/cleanup.ts) (deletes the blob after) deploy automatically.
2. In the project's **Storage** tab, create a **Blob** store — this adds
   `BLOB_READ_WRITE_TOKEN` for you.
3. Set env: `VITE_UPLOAD_MODE=blob` and `VITE_API_BASE=https://<your-backend>`.
4. Deploy the Python backend separately (see `backend/README.md`, Vercel or Cloud Run).

To move the backend to Cloud Run later: flip `VITE_UPLOAD_MODE=direct` and point
`VITE_API_BASE` at Cloud Run — no code changes.

## What it shows
- **Driver Safety Profile** — A–F grade, 0–100 score, top risks, summary.
- **Analysis Log** — each detected event with severity, confidence, evidence, and a
  click-to-seek jump to that moment in the video.
- **Violation Checklist** — per-category status (severity-coloured).
- **Equipment Checklist** — camera/video QA faults with reasons.

Cabin vs Front is sent to the backend, which runs the matching prompt and
auto-detects a wrong camera view (showing a warning instead of bad results).
