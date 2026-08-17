"""
Analysis orchestration.

One public entry point, `analyze_clip`, that:
  1. uploads the video to the Files API ONCE (reused for both behaviour and
     equipment — the original app uploaded the whole video twice),
  2. runs behaviour analysis with the right prompt for the camera type,
  3. runs equipment/QA analysis,
  4. detects a wrong-camera-view mismatch (a cheap view classifier + the prompts' WRONG_VIEW sentinel),
  5. scores it into a driver profile,
  6. cleans the uploaded file up.

This module is deliberately transport-agnostic: the FastAPI app (app.py) and the
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
    view_ok = True
    detected_view = None

    file_obj = gc.upload_video(path, mime_type=mime_type)
    try:
        # --- View pre-check: catch a mismatched upload BEFORE analysing ---------
        if config.VERIFY_VIEW:
            detected_view = gc.classify_view(file_obj)   # 'cabin' | 'front' | 'unclear'
            if detected_view in ("cabin", "front") and detected_view != camera.value:
                msg = (f"Camera-view mismatch: you selected {camera.value.upper()} but this clip "
                       f"looks like a {detected_view.upper()} view.")
                policy = config.VIEW_MISMATCH_POLICY
                if policy == "reject":
                    return {
                        "camera": camera.value,
                        "detected_view": detected_view,
                        "view_ok": False,
                        "warnings": [msg + " Re-upload it under the correct camera."],
                        "events": [],
                        "equipment": [],
                        "profile": scoring.profile_from_events([]),
                    }
                if policy == "autocorrect":
                    warnings.append(msg + f" Analyzed as {detected_view.upper()}.")
                    camera = CameraType(detected_view)
                else:  # "off" or unknown -> analyse as selected, but warn
                    warnings.append(msg)

        cats = config.categories_for(camera)

        if run_behaviour:
            if camera == CameraType.CABIN:
                b_prompt, fps = prompts.cabin_prompt(), config.CABIN_FPS
            else:
                b_prompt, fps = prompts.front_prompt(), config.FRONT_FPS
            events = gc.analyze_behaviour(file_obj, b_prompt, cats, fps)
            # Secondary net: the behaviour prompt's own WRONG_VIEW sentinel.
            if _is_wrong_view(events):
                warnings.append(
                    f"Camera-view mismatch: this clip does not look like a '{camera.value}' view. "
                    "Behaviour results suppressed."
                )
                events = []
                view_ok = False
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
        "detected_view": detected_view,
        "view_ok": view_ok,
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
