"""
Analysis orchestration.

One public entry point, `analyze_clip`, that:
  1. uploads the video to the Files API ONCE (reused for both behaviour and
     equipment — the original app uploaded the whole video twice),
  2. runs behaviour analysis with the right prompt for the camera type,
  3. runs equipment/QA analysis,
  4. detects a wrong-camera-view mismatch (the prompts emit a WRONG_VIEW sentinel),
  5. scores it into a driver profile,
  6. cleans the uploaded file up.

This module is deliberately transport-agnostic: the FastAPI app (api.py) and the
batch worker (worker.py) both just call analyze_clip.
"""

from __future__ import annotations

import logging

import config
from config import CameraType
import prompts
import gemini_client as gc
import scoring

log = logging.getLogger("uepl.analysis")


def _is_wrong_view(events: list[dict]) -> bool:
    return (
        len(events) == 1
        and float(events[0].get("confidence", 1) or 0) == 0.0
        and str(events[0].get("reason", "")).startswith("WRONG_VIEW")
    )


def analyze_clip(
    path: str,
    camera: CameraType,
    *,
    run_behaviour: bool = True,
    run_equipment: bool = True,
    mime_type: str = "video/mp4",
) -> dict:
    """Analyze one video clip end-to-end. Returns a JSON-serialisable dict."""
    warnings: list[str] = []
    events: list[dict] = []
    equipment: list[dict] = []

    file_obj = gc.upload_video(path, mime_type=mime_type)
    try:
        cats = config.categories_for(camera)

        if run_behaviour:
            if camera == CameraType.CABIN:
                b_prompt, fps = prompts.cabin_prompt(), config.CABIN_FPS
            else:
                b_prompt, fps = prompts.front_prompt(), config.FRONT_FPS
            events = gc.analyze_behaviour(file_obj, b_prompt, cats, fps)
            if _is_wrong_view(events):
                warnings.append(
                    f"Camera-view mismatch: this clip does not look like a '{camera.value}' view "
                    f"({events[0].get('reason')}). Behaviour results suppressed."
                )
                events = []
            else:
                for e in events:
                    e["camera"] = camera.value

        if run_equipment:
            e_prompt = prompts.equipment_prompt(camera)
            equipment = gc.analyze_equipment(file_obj, e_prompt, config.EQUIPMENT_CATEGORIES)
    finally:
        gc.delete_file(file_obj)

    profile = scoring.profile_from_events(events)

    return {
        "camera": camera.value,
        "view_ok": not warnings,
        "warnings": warnings,
        "events": events,
        "equipment": equipment,
        "profile": profile,
    }


def analyze_driver(clips: list[dict]) -> dict:
    """Profile a driver across several clips.

    `clips` = list of {"path": str, "camera": CameraType|str} dicts. Returns each
    clip's analysis plus an aggregate driver profile.
    """
    per_clip = []
    for c in clips:
        cam = c["camera"]
        cam = cam if isinstance(cam, CameraType) else CameraType(cam)
        try:
            per_clip.append(analyze_clip(c["path"], cam))
        except Exception as e:  # noqa: BLE001 - one bad clip shouldn't kill the batch
            log.error("Clip failed (%s): %s", c.get("path"), e)
            per_clip.append({"camera": cam.value, "error": str(e),
                             "events": [], "equipment": [], "profile": scoring.profile_from_events([])})
    aggregate = scoring.aggregate_profiles([c["profile"] for c in per_clip if "profile" in c])
    return {"clips": per_clip, "driver_profile": aggregate}
