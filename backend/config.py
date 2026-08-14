"""
Central configuration for the UEPL driver-profiling / equipment-analysis backend.

This module is the single source of truth for:
  * the Gemini model + generation settings (aligned with the deployed AFDD agents),
  * the fixed violation / equipment taxonomies (enums) used everywhere, and
  * the severity weights that drive driver profiling / scoring.

Keeping the taxonomies here (instead of duplicated in prompts, schemas and the UI)
means the model output, the JSON schema and the scoring logic can never drift apart.
"""

from __future__ import annotations

import os
from enum import Enum

# Load backend/.env if present so the key never has to be pasted into a command.
# (Optional dependency — safe no-op if python-dotenv isn't installed.)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass


# --------------------------------------------------------------------------- #
# Gemini / model configuration
# --------------------------------------------------------------------------- #
# We use the new `google-genai` SDK (from google import genai), the same one the
# deployed AFDD annotator agents use.
#
# MODEL CHOICE: the default is gemini-2.5-flash to match the deployed AFDD stack
# exactly (proven, and the thinking_budget config below is valid for it). As of
# Aug 2026 the newer **gemini-3.7-flash** is the recommended video+audio workhorse
# and — importantly for in-cabin audio — folds audio into the base token price
# (2.5-flash bills audio at 3x the visual rate). To upgrade, set
# UEPL_BEHAVIOUR_MODEL=gemini-3.7-flash (verify it's enabled on your key first).
GENAI_API_KEY = os.environ.get("GENAI_API_KEY", "")

# Behaviour analysis (cabin / front) — needs real reasoning over the whole clip.
BEHAVIOUR_MODEL = os.environ.get("UEPL_BEHAVIOUR_MODEL", "gemini-2.5-flash")
# Equipment / QA — cheaper checks; gemini-3.1-flash-lite is a good cheap upgrade.
EQUIPMENT_MODEL = os.environ.get("UEPL_EQUIPMENT_MODEL", "gemini-2.5-flash")

# temperature=0 is the anti-hallucination floor. Note (per the AFDD notes): it does
# NOT make the model deterministic, so for borderline high-severity events we run a
# small confirmation pass rather than trusting a single sample.
TEMPERATURE = 0.0
# Thinking budget for behaviour analysis. The cabin/front tasks are multi-step
# (read overlay -> localise event -> classify -> justify), so we give them room.
THINKING_BUDGET_BEHAVIOUR = 4096
THINKING_BUDGET_EQUIPMENT = 1024

# Cap output so long event arrays never silently truncate (finish_reason=MAX_TOKENS
# yields invalid partial JSON). Comfortably fits dozens of events.
MAX_OUTPUT_TOKENS = 8192

# Video frame sampling (videoMetadata.fps). Gemini samples at 1 FPS by DEFAULT,
# which misses transient motion. Benchmarks show 1->5 FPS lifts momentary-event
# (braking/swerve) accuracy from ~27% to ~38%, with diminishing returns after ~5.
#   * FRONT needs dense sampling for harsh braking / swerving / overtaking.
#   * CABIN behaviours are more sustained; 2 FPS balances cost and blink/glance detail.
#   * EQUIPMENT/QA is coarse; 1 FPS (default) is fine and cheapest.
FRONT_FPS = float(os.environ.get("UEPL_FRONT_FPS", "5"))
CABIN_FPS = float(os.environ.get("UEPL_CABIN_FPS", "2"))
EQUIPMENT_FPS = float(os.environ.get("UEPL_EQUIPMENT_FPS", "1"))

# Files API: videos are uploaded, then polled until state == ACTIVE before use.
FILE_ACTIVE_TIMEOUT_S = 180
FILE_POLL_INTERVAL_S = 2

# Transient-error retry policy for generate_content / file ops.
MAX_RETRIES = 4
RETRY_BASE_DELAY_S = 2.0


# --------------------------------------------------------------------------- #
# Camera views
# --------------------------------------------------------------------------- #
class CameraType(str, Enum):
    CABIN = "cabin"        # in-cabin, driver-facing (with audio)
    FRONT = "front"        # forward / road-facing


# --------------------------------------------------------------------------- #
# Severity
# --------------------------------------------------------------------------- #
class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Points contributed to a driver's *risk* score by one confirmed event, before the
# per-category weight is applied. Higher = worse. Used by scoring.py.
SEVERITY_POINTS = {
    Severity.LOW.value: 1.0,
    Severity.MEDIUM.value: 3.0,
    Severity.HIGH.value: 6.0,
}


# --------------------------------------------------------------------------- #
# Violation taxonomies (the model MUST emit one of these exact strings)
# --------------------------------------------------------------------------- #
# CABIN — driver-facing behaviour. "FOD" = the authorised co-driver / second
# occupant (company term), NOT foreign-object-debris. A THIRD occupant beyond
# driver + FOD is an "Unauthorized Passenger".
CABIN_CATEGORIES = [
    "Unauthorized Passenger",
    "Distracted Driving",
    "Driver No Seatbelt",
    "Driver Fatigue",
    "Casual Driving",
    "Smoking",
    "Road Rage",
    "FOD Violation",
    "Loose Items",
]

# FRONT — forward road behaviour. Category names kept aligned with the original
# taxonomy for continuity; definitions are sharpened in prompts.py.
FRONT_CATEGORIES = [
    "Lane Discipline",
    "Speed Violation",
    "Improper Overtaking",
    "Improper Turn",
    "Tailgating",
    "Harsh Driving",   # was "Momentum Preservation": harsh braking/accel, jerky, harsh cornering
]

# Default per-category weight (multiplies the severity points). Tunable knob for
# how much each behaviour matters to the overall driver profile.
CATEGORY_WEIGHTS = {
    # cabin
    "Unauthorized Passenger": 1.2,
    "Distracted Driving": 1.5,
    "Driver No Seatbelt": 1.3,
    "Driver Fatigue": 2.0,
    "Casual Driving": 0.8,
    "Smoking": 0.7,
    "Road Rage": 1.4,
    "FOD Violation": 0.6,
    "Loose Items": 0.5,
    # front
    "Lane Discipline": 1.2,
    "Speed Violation": 1.6,
    "Improper Overtaking": 1.5,
    "Improper Turn": 1.3,
    "Tailgating": 1.4,
    "Harsh Driving": 1.5,
}


# --------------------------------------------------------------------------- #
# Equipment / video-QA taxonomy
# --------------------------------------------------------------------------- #
EQUIPMENT_CAMERA_ISSUES = [
    "Camera Not Working",
    "Overlay Data Stuck Or Zero",     # GPS coords / speed stuck or zero throughout
    "Incorrect Camera Angle",         # cabin: driver/FOD out of frame; front: sky/ground/off-road
    "Audio Missing",
    "Video Blurred",
    "View Obstructed",
    "Poor Night Vision",
]

EQUIPMENT_VIDEO_ISSUES = [
    "Video Buffering",
    "Video Jump Or Missing Segment",
    "Audio Video Out Of Sync",
]

EQUIPMENT_CATEGORIES = EQUIPMENT_CAMERA_ISSUES + EQUIPMENT_VIDEO_ISSUES


def categories_for(camera: CameraType) -> list[str]:
    return CABIN_CATEGORIES if camera == CameraType.CABIN else FRONT_CATEGORIES
