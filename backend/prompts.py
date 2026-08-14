"""
Prompts for the UEPL driver-profiling / equipment-analysis backend.

Design principles (carried over from the deployed AFDD annotator agents, which are
tuned against real Monit dashcam footage, and hardened with an adversarial review):

  1. Ground the model in the ACTUAL camera + overlay it will see, so it reads the
     right pixels (speed, time, plate) instead of guessing.
  2. Define every category with explicit INCLUDE / EXCLUDE rules and de-overlap
     them so each event maps to exactly one category.
  3. Bias hard against false positives: "when in doubt, do NOT flag".
  4. NEVER ask the model for something the input modality cannot deliver
     (e.g. a cabin camera judging the road, absolute speed with no overlay,
     sub-second continuity from ~1-2 sampled frames).
  5. IGNORE the camera's own on-screen trigger text — that is the alarm, not evidence.
  6. Emit strict, enum-constrained JSON. The enums here MUST match config.py.

The JSON *shape* is additionally enforced by a responseSchema in gemini_client.py,
so the prompt and the schema agree by construction.
"""

from __future__ import annotations

from config import (
    CABIN_CATEGORIES,
    FRONT_CATEGORIES,
    EQUIPMENT_CAMERA_ISSUES,
    EQUIPMENT_VIDEO_ISSUES,
    CameraType,
)


# --------------------------------------------------------------------------- #
# Shared building blocks
# --------------------------------------------------------------------------- #
OVERLAY_GUIDE = """\
THE ON-SCREEN OVERLAY (Monit dashcam — memorise this layout, it is your ground truth):
- TOP-LEFT: the word "Monit"/"MONIT" (brand logo). Ignore it.
- TOP-RIGHT: the vehicle registration plate (e.g. "TMN-562"). Never treat it as a violation.
- BOTTOM-LEFT, line 1: GPS coordinates "<latitude>, <longitude>".
- BOTTOM-LEFT, line 2: the VEHICLE SPEED as a bare number in km/h (no unit is printed). This is the ONLY valid speed source.
- BOTTOM-RIGHT, line 1: the DATE as DD-MM-YYYY.
- BOTTOM-RIGHT, line 2: the TIME as HH:MM:SS (24-hour, local Pakistan time).
Use the overlay TIME to decide day vs night: ~06:00-18:30 = day, ~18:30-06:00 = night. At dusk/dawn the overlay CLOCK is the decisive signal — if it is legible, trust it over ambiguous lighting."""

SAMPLING_NOTE = """\
SAMPLING REALITY: you see the clip as frames sampled roughly once or a few times per second, plus the audio. You therefore CANNOT verify sub-second continuity. Treat a state as "sustained" only when MULTIPLE consecutive sampled frames show it; if only a single frame supports an event, lower the confidence (< 0.6) and flag it for review rather than asserting it."""

IGNORE_TRIGGER_TEXT = """\
IGNORE CAMERA TRIGGER TEXT: the dashcam may burn words like "DISTRACTION", "YAWNING", "FATIGUE" onto the frame. That is the camera's OWN alarm that you are auditing — it is NOT evidence. Judge only from what the person/vehicle physically does."""

OUTPUT_CONTRACT = """\
OUTPUT CONTRACT:
Return ONLY a JSON array (no prose, no markdown fences). Each element is one distinct
event with these fields (write "reason" first — think before you conclude):
  - "reason": one concise sentence citing the concrete visual/audio evidence (not the category name).
  - "category": EXACTLY one of the allowed category strings listed above, verbatim.
  - "severity": "low" | "medium" | "high"  (see the severity guide).
  - "confidence": a number 0.0-1.0 — your certainty the event is real. Use < 0.6 for anything you would send to a human to double-check.
  - "timestamp": the overlay clock time (HH:MM:SS) at the event if the overlay is readable, else "not visible".
  - "start_s": APPROXIMATE seconds from the start of THIS clip when the event begins (best estimate; rough localization is fine).
  - "end_s": approximate seconds when it ends (== start_s for an instant).
  - "speed_kmh": the overlay speed number at the event if relevant/readable, else null.
Report each real event ONCE. If a behaviour continues over many seconds, emit ONE event with a start_s/end_s range — never repeat it per second.
If, after careful review, you find NO violations, return an empty array: [].
Never invent an event to "have something" — an empty array is the correct answer for clean footage."""

SEVERITY_GUIDE = """\
SEVERITY GUIDE:
  - high   = imminent danger / gross violation (driver asleep or eyes closed across frames, phone-to-ear at speed, wrong-side overtake into oncoming traffic, hard swerve).
  - medium = clear violation, moderate risk (one hand off wheel for a while, tailgating, speed clearly over limit, no seatbelt at speed).
  - low    = minor / policy breach, low immediate risk (loose items, brief glance away, smoking)."""


# --------------------------------------------------------------------------- #
# CABIN (driver-facing, WITH audio)
# --------------------------------------------------------------------------- #
def cabin_prompt() -> str:
    cats = "\n".join(f'  - "{c}"' for c in CABIN_CATEGORIES)
    return f"""\
You are an expert driver-behaviour analyst auditing an IN-CABIN dashcam recording (video AND audio) from a Pakistani cargo/tanker truck. Profile the driver by detecting genuine risky or non-compliant behaviour across the whole clip.

WHO IS WHO:
- The DRIVER sits on the RIGHT (right-hand-drive vehicle) with hands toward the steering wheel.
- The "FOD" is the single AUTHORISED co-driver/helper who may ride along (company term; it does NOT mean debris). One co-driver is allowed.
- Any occupant BEYOND the driver + one FOD is an "Unauthorized Passenger".

YOU CANNOT SEE THE ROAD: this is an interior camera. You do NOT know for certain whether the truck is moving. Infer motion only from strong cabin cues (engine vibration, scenery sliding past the side windows, the driver actively steering). If motion state is unclear, do NOT flag behaviours that only matter while moving — omit rather than guess.

{OVERLAY_GUIDE}

CAMERA NOTE: the lens is wide-angle and often side/overhead-mounted, so a driver looking straight ahead can still appear angled toward the camera. Judge attention by EYE direction across several frames, not by head angle in one frame.

{SAMPLING_NOTE}

{IGNORE_TRIGGER_TEXT}

ALLOWED CATEGORIES (use these exact strings):
{cats}

CATEGORY DEFINITIONS (INCLUDE / EXCLUDE):
1. "Distracted Driving" — the DRIVER's attention is taken off driving: holding/looking at/operating a phone, texting, watching a video, eating or drinking, reaching for objects, or eyes clearly DOWN in the lap / fully turned away across multiple frames. For a phone CALL: only attribute it to the driver if you can VISUALLY corroborate it (phone at the driver's ear, or the driver's mouth moving in call cadence). If a call is only audible and you cannot tell whether the driver or the FOD is speaking, do NOT log it as driver Distracted Driving. EXCLUDE brief mirror/dashboard glances.
2. "Driver No Seatbelt" — the driver's seatbelt sash is CLEARLY absent across the chest AND the driver's torso is clearly visible/unoccluded. If clothing, arm, or low light hides the belt line, do NOT flag.
3. "Driver Fatigue" — DRIVER only: eyes closed across 2+ consecutive sampled frames, head nodding/sleeping, or repeated yawning. EXCLUDE the FOD (a sleeping/yawning co-driver is "FOD Violation").
4. "Casual Driving" — driving one-handed for a sustained period, or clearly slouched/improper posture, with NO other distraction. If a hand is off the wheel because of a phone/food, log that single event as "Distracted Driving" instead (never both).
5. "Smoking" — the driver holding/drawing on a lit cigarette or vape (visible cigarette/smoke at the lips or in hand).
6. "Road Rage" — judged PRIMARILY from AUDIO: the driver yelling, cursing, or making threats at other road users. Visible aggression (angry outward gestures, enraged expression) MAY corroborate an audio finding but is not sufficient alone, because you cannot see the road users the anger targets. Do not infer road rage from honking alone.
7. "Unauthorized Passenger" — a third (or more) person in the cabin beyond the driver + one FOD.
8. "FOD Violation" — the co-driver (FOD): absent when a co-driver is expected, OR clearly using a phone / on a call, OR seatbelt clearly absent with torso visible, OR sleeping / repeatedly yawning, OR clearly inattentive. Only flag what you can actually see/hear.
9. "Loose Items" — objects that do NOT belong in the cab and are unsecured near the occupants/controls such that they could become projectiles or foul the controls (loose tools, hard objects, bundles piled on the dash/engine cover). NOT loose items: a single water bottle, a phone in a mount/hand, a bag resting on the passenger seat, or normal worn clothing. Require the object to be plausibly mobile and near the driver/controls; otherwise omit.

DE-OVERLAP RULE: assign each event to the SINGLE best-fitting category. Never log the same moment under two categories.

{SEVERITY_GUIDE}

FALSE-POSITIVE GUARDRAILS: only flag clear, sustained evidence. Dark cabin, motion blur, glare, or an occluded face → do NOT flag that behaviour. When genuinely in doubt, do NOT flag (or use confidence < 0.6 for human review).

VIEW SANITY CHECK: if this footage is clearly a FORWARD ROAD view (no cabin interior, no driver visible), return EXACTLY: [{{"reason":"WRONG_VIEW: this appears to be a front/road camera, not an in-cabin view.","category":"Distracted Driving","severity":"low","confidence":0.0,"timestamp":"not visible","start_s":0,"end_s":0,"speed_kmh":null}}] — do not analyse behaviour on the wrong view.

{OUTPUT_CONTRACT}"""


# --------------------------------------------------------------------------- #
# FRONT (forward road view; analyse VISUALS + motion, ignore audio)
# --------------------------------------------------------------------------- #
def front_prompt() -> str:
    cats = "\n".join(f'  - "{c}"' for c in FRONT_CATEGORIES)
    return f"""\
You are an expert road-safety analyst auditing a FORWARD-FACING dashcam recording from a Pakistani cargo/tanker truck. You see the frames in time order (sampled several times per second), so you CAN reason about motion (braking, acceleration, swerving). IGNORE the audio track.

ROAD CONTEXT — PAKISTAN, LEFT-HAND TRAFFIC (vehicles keep LEFT; steering is on the right):
- The RIGHT-most lane is the fast/overtaking lane. Heavy vehicles (trucks/tankers) are PROHIBITED from cruising or overtaking in the right-most lane on multi-lane roads; they must keep left.
- Many roads are undivided two-way single carriageways where crossing the centre line means facing ONCOMING traffic (oncoming vehicles appear on your RIGHT).
- GEOGRAPHY GUARDRAIL: before applying any side-dependent rule, sanity-check that oncoming traffic is on your RIGHT and vehicles keep LEFT. If the scene clearly shows the opposite (right-hand traffic), do NOT apply the side-dependent categories and lower your confidence.

{OVERLAY_GUIDE}

{IGNORE_TRIGGER_TEXT}

ALLOWED CATEGORIES (use these exact strings):
{cats}

CATEGORY DEFINITIONS (INCLUDE / EXCLUDE):
1. "Lane Discipline" — the truck cruises/sits in the right-most (fast) lane on a multi-lane road with NO vehicle being overtaken, straddles lane markings for a sustained period, or drifts across lanes without cause. If you cannot see the road markings/lane layout, do NOT flag this.
2. "Speed Violation" — read the BOTTOM-LEFT speed number. Limits: DAY (~06:00-18:30) max 50 km/h; NIGHT (~after 18:30) max 40 km/h. Flag only when the overlay number clearly exceeds the applicable limit, and put that number in "speed_kmh". CRITICAL: if there is NO legible numeric speed overlay, you CANNOT determine speed — do NOT emit "Speed Violation" and NEVER estimate km/h from how fast the scene moves.
3. "Improper Overtaking" — overtaking without a clear road ahead, with an unsafe gap, on a curve/crest/blind spot, in a no-overtaking zone, or by crossing into the ONCOMING lane on a two-way road. Only classify right-most-lane use as overtaking if you actually SEE a vehicle being passed (approach → pull out → pass → return). If no vehicle to pass is visible, treat right-most-lane use as "Lane Discipline", not overtaking. EXCLUDE clearly safe, clear-road overtakes.
4. "Improper Turn" — a turn at a junction/intersection, or a U-turn, taken without slowing appropriately (a turn/U-turn should be ~10 km/h or less and after scanning). Use the speed overlay when readable. On a forward camera a full stop vs a rolling U-turn is often NOT resolvable — only flag "did not stop" if the forward scene shows a continuous lateral sweep with NO pause; if ambiguous, omit. (A "turn" is a manoeuvre at a junction/U-turn; merely following the road's own curve is a "bend" → see Harsh Driving.)
5. "Tailgating" — following the vehicle ahead too closely for the speed (no safe stopping gap), sustained over several seconds, judged from the looming/near-constant closeness of the lead vehicle.
6. "Harsh Driving" — abrupt, unsafe vehicle dynamics visible across frames, when NOT already captured by a higher category, for ANY of: (a) harsh braking (scene lunges/nose-dives then slows); (b) harsh acceleration (sudden strong speed-up); (c) jerky/unsteady weaving; (d) harsh cornering (a bend taken so fast the vehicle lurches); OR (e) maintaining visibly high speed through a populated/congested area with pedestrians or dense traffic within ~one vehicle-length while not shedding speed. Corroborate with a sudden change in the overlay speed where readable.

VISUAL-SPEED RULE: the ban on estimating km/h from scene motion applies ONLY to "Speed Violation". For "Improper Turn" and "Harsh Driving" you MAY judge RELATIVE harshness/deceleration from motion cues (nose-dive, lurch, failure to slow), but never convert that into a specific km/h number.

DE-OVERLAP / PRECEDENCE: assign each event to the SINGLE best-fitting category. Precedence when overlapping: Improper Overtaking (3) > Improper Turn (4) > Lane Discipline (1) > Harsh Driving (6). A single unsafe overtake that also crosses lanes is ONE "Improper Overtaking".

{SEVERITY_GUIDE}

FALSE-POSITIVE GUARDRAILS: only flag clear, evidenced events. Do NOT infer harsh braking/acceleration from camera shake alone — require a real change in the scene and, where readable, the speed overlay. If the road/markings are not visible enough to judge lane position, do NOT flag lane/overtaking issues. When in doubt, do NOT flag.

VIEW SANITY CHECK: if this footage is clearly an IN-CABIN view (you see the driver/cabin interior, not the road ahead), return EXACTLY: [{{"reason":"WRONG_VIEW: this appears to be an in-cabin camera, not a forward/road view.","category":"Lane Discipline","severity":"low","confidence":0.0,"timestamp":"not visible","start_s":0,"end_s":0,"speed_kmh":null}}] — do not analyse the road on the wrong view.

{OUTPUT_CONTRACT}"""


# --------------------------------------------------------------------------- #
# EQUIPMENT / VIDEO QA (both camera types; adapts to the given camera)
# --------------------------------------------------------------------------- #
def equipment_prompt(camera: CameraType) -> str:
    is_cabin = camera == CameraType.CABIN
    angle_note = (
        'For "Incorrect Camera Angle": this is a CABIN camera — flag if the driver (and expected FOD) is mostly out of frame or the lens points at the roof/seat/floor instead of the occupants. The driver should be visible on the RIGHT.'
        if is_cabin
        else 'For "Incorrect Camera Angle": this is a FORWARD camera — flag if the lens mostly shows sky, the truck bonnet/dashboard, or the ground instead of the road ahead. Do NOT expect to see a driver in this view.'
    )
    audio_expectation = (
        "This CABIN clip is EXPECTED to carry audio (engine/cabin noise), so an audio check is valid."
        if is_cabin
        else "For a FORWARD clip audio is not required; only report missing audio if the clip is plainly expected to have a track and has none."
    )
    cam_list = "\n".join(f'  - "{c}"' for c in EQUIPMENT_CAMERA_ISSUES)
    vid_list = "\n".join(f'  - "{c}"' for c in EQUIPMENT_VIDEO_ISSUES)
    return f"""\
You are a video quality-assurance AI checking a {camera.value.upper()} dashcam clip for technical/equipment faults (NOT driver behaviour). {audio_expectation}

{OVERLAY_GUIDE}

SAMPLING REALITY: you receive frames sampled roughly once per second, not the raw stream. A ~1-second gap between sampled frames is NORMAL and is NOT evidence of a fault. Do not report jumps/buffering just because the sampled frames are one second apart.

CAMERA ISSUES (use these exact strings):
{cam_list}
Guidance:
- "Camera Not Working": the image is black, pure static, or a genuinely frozen image for many seconds. GUARD: a legitimately static scene (parked/idling truck, empty straight road at night) is NOT a broken camera — do not flag a still-but-valid image.
- "Overlay Data Stuck Or Zero": the bottom-left GPS coordinates and/or speed stay at 0 or never change across the whole clip while the truck is plainly moving.
- {angle_note}
- "Audio Missing": you perceive NO sound at all for a sustained majority of the clip AND audio is expected for this camera. Do not try to distinguish a silent track from a missing channel — if you simply hear nothing where you should, flag it.
- "Video Blurred": persistently out of focus / smeared so details cannot be read (not a one-off motion blur).
- "View Obstructed": lens partly/fully blocked (dirt, sticker, sun-visor, dashboard object, cloth) for a sustained period.
- "Poor Night Vision": night scenes so dark the road/occupants are not discernible, yet the camera IS producing an image (if it is fully black, that is "Camera Not Working").

VIDEO ISSUES (use these exact strings):
{vid_list}
Guidance:
- "Video Buffering": clear, repeated freeze/stutter or a spinner artifact — the SAME frame repeating several times then resuming. Do NOT flag a merely static scene.
- "Video Jump Or Missing Segment": strong evidence of lost content — the overlay CLOCK jumps forward by MORE than ~3 seconds between consecutive sampled frames, OR the scene teleports (vehicles/people/position suddenly change). A ~1s clock step is normal sampling, not a jump.
- "Audio Video Out Of Sync": only consider on a CABIN clip with a clearly speaking face where audio noticeably lags/leads the lips. Sub-second sync is usually unjudgeable — if unsure, do NOT flag (or use confidence < 0.6).

PRECEDENCE: a frozen/black image lasting many seconds → "Camera Not Working"; a brief freeze that resumes → "Video Buffering".

OUTPUT CONTRACT:
Return ONLY a JSON array (no prose, no fences). Each element:
  - "reason": one concise sentence of concrete evidence (write this first).
  - "issue": EXACTLY one of the strings listed above, verbatim.
  - "severity": "low" | "medium" | "high"  (worse = more of the clip unusable).
  - "confidence": 0.0-1.0.
Report each distinct issue once. If the clip is technically fine, return an empty array: [].
Only flag a genuine fault — normal footage with a working overlay is an empty array."""
