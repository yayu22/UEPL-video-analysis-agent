"""
FastAPI app — the HTTP layer the frontend calls.

Two ingestion paths (choose per deploy target with UEPL_INGEST_MODE; both always
exist so switching hosts is pure configuration):
  * POST /api/analyze      — multipart file upload ("direct"). Best on Cloud Run /
    any host that accepts large request bodies.
  * POST /api/analyze-url  — JSON {video_url, camera} ("url"). The server downloads
    the clip itself, sidestepping Vercel's 4.5 MB request-body cap (the browser
    uploads to blob storage first and sends only the URL).

Either way the video is written to a TEMP file, analysed, and deleted — nothing is
persisted.

Deploy targets:
  * Vercel  — this file is `app.py` exposing `app`, which Vercel auto-detects; see
    vercel.json for maxDuration.
  * Cloud Run / server — `gunicorn -k uvicorn.workers.UvicornWorker app:app`
    or `uvicorn app:app --port 8000`.
"""

from __future__ import annotations

import os
import tempfile
import logging

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
from config import CameraType
import analysis
import ingest
import usage

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("uepl.api")

app = FastAPI(title="UEPL Driver Profiling & Equipment Analysis", version="1.1.0")

# Lock this down to the deployed frontend origin(s) in production (UEPL_CORS_ORIGINS).
_origins = os.environ.get("UEPL_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = int(os.environ.get("UEPL_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))


def _parse_camera(camera: str) -> CameraType:
    try:
        return CameraType(camera.strip().lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"camera must be one of {[c.value for c in CameraType]}")


def _run(path: str, cam: CameraType, mime: str, filename: str | None) -> dict:
    """Analyse a local temp file. Caller deletes the file (see finally blocks)."""
    result = analysis.analyze_clip(path, cam, mime_type=mime)
    result["filename"] = filename
    return result


@app.get("/health")
def health():
    return {"status": "ok", "model": config.BEHAVIOUR_MODEL, "key_configured": bool(config.GENAI_API_KEY)}


@app.get("/api/config")
def api_config():
    """Advertise the ingestion mode + limits so the frontend can match them."""
    return {
        "ingest_mode": config.INGEST_MODE,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_download_bytes": config.MAX_DOWNLOAD_BYTES,
    }


@app.get("/api/taxonomy")
def taxonomy():
    return {
        "cabin": config.CABIN_CATEGORIES,
        "front": config.FRONT_CATEGORIES,
        "equipment_camera": config.EQUIPMENT_CAMERA_ISSUES,
        "equipment_video": config.EQUIPMENT_VIDEO_ISSUES,
    }


@app.get("/api/usage")
def get_usage(user_id: str, role: str = "user"):
    """Lets the frontend always display the caller's remaining-analysis count."""
    return usage.usage_info(user_id, role)


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    camera: str = Form(...),
    user_id: str = Form(...),
    role: str = Form("user"),
):
    """Direct multipart upload (Cloud Run / any server). Temp file is always deleted."""
    cam = _parse_camera(camera)
    try:
        usage.check_limit(user_id, role)
    except usage.LimitReached as e:
        raise HTTPException(status_code=429, detail=str(e))
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
        # Charge the quota for a real attempt (valid file, about to call Gemini),
        # not for input that was rejected before any inference happened.
        if role != "admin":
            usage.increment(user_id)
        log.info("Analyzing %s (%.1f MB, camera=%s) [direct]", file.filename, size / 1e6, cam.value)
        result = _run(tmp, cam, file.content_type or "video/mp4", file.filename)
        result["usage"] = usage.usage_info(user_id, role)
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


class AnalyzeUrlRequest(BaseModel):
    video_url: str
    camera: str
    user_id: str
    role: str = "user"


@app.post("/api/analyze-url")
def analyze_url(req: AnalyzeUrlRequest):
    """URL ingestion (Vercel / blob). Downloads to temp, analyses, deletes."""
    cam = _parse_camera(req.camera)
    try:
        usage.check_limit(req.user_id, req.role)
    except usage.LimitReached as e:
        raise HTTPException(status_code=429, detail=str(e))
    try:
        tmp = ingest.download_to_temp(req.video_url, config.MAX_DOWNLOAD_BYTES)
    except ingest.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        if req.role != "admin":
            usage.increment(req.user_id)
        log.info("Analyzing %s (camera=%s) [url]", ingest.basename(req.video_url), cam.value)
        result = _run(tmp, cam, ingest.guess_mime(req.video_url), ingest.basename(req.video_url))
        result["usage"] = usage.usage_info(req.user_id, req.role)
        return JSONResponse(result)
    except Exception as e:  # noqa: BLE001
        log.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=f"analysis failed: {e}")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
