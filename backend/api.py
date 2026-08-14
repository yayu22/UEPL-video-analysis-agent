"""
FastAPI app — the HTTP layer the React frontend calls.

The frontend uploads a video + camera type here; this service holds the Gemini
key server-side (so it is never shipped to the browser), uploads the video to the
Files API, runs behaviour + equipment analysis, scores a driver profile, and
returns everything as JSON.

Run locally:
    uvicorn api:app --reload --port 8000
Deploy (GCP Cloud Run, aligned with the AFDD stack):
    gunicorn -k uvicorn.workers.UvicornWorker api:app
"""

from __future__ import annotations

import os
import shutil
import tempfile
import logging

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from config import CameraType
import analysis

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("uepl.api")

app = FastAPI(title="UEPL Driver Profiling & Equipment Analysis", version="1.0.0")

# Lock this down to the deployed frontend origin(s) in production.
_origins = os.environ.get("UEPL_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reject absurdly large uploads early (bytes). Default 500 MB.
MAX_UPLOAD_BYTES = int(os.environ.get("UEPL_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))


@app.get("/health")
def health():
    return {"status": "ok", "model": config.BEHAVIOUR_MODEL, "key_configured": bool(config.GENAI_API_KEY)}


@app.get("/api/taxonomy")
def taxonomy():
    """Expose the taxonomies so the UI can render checklists without hardcoding them."""
    return {
        "cabin": config.CABIN_CATEGORIES,
        "front": config.FRONT_CATEGORIES,
        "equipment_camera": config.EQUIPMENT_CAMERA_ISSUES,
        "equipment_video": config.EQUIPMENT_VIDEO_ISSUES,
    }


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    camera: str = Form(...),
):
    try:
        cam = CameraType(camera.strip().lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"camera must be one of {[c.value for c in CameraType]}")

    if file.content_type and not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="uploaded file must be a video")

    suffix = os.path.splitext(file.filename or "")[1] or ".mp4"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    try:
        size = 0
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="video too large")
                out.write(chunk)
        if size < 1024:
            raise HTTPException(status_code=400, detail="uploaded file is empty or corrupt")

        mime = file.content_type or "video/mp4"
        log.info("Analyzing %s (%.1f MB, camera=%s)", file.filename, size / 1e6, cam.value)
        result = analysis.analyze_clip(tmp, cam, mime_type=mime)
        result["filename"] = file.filename
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=f"analysis failed: {e}")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
