"""
Gemini client wrapper.

Everything that talks to the Gemini API lives here, so retries, the Files API
upload/poll dance, structured-output schemas and response validation are in one
place and the analysis layer stays clean.

Built on the same `google-genai` SDK + gemini-2.5-flash the deployed AFDD agents
use. Key robustness choices vs. the original app:
  * Uploads via the Files API (handles full-length videos; the old inline-base64
    path fails above ~20 MB / a few seconds of video).
  * Retries transient errors with exponential backoff.
  * Enum-constrained responseSchema so the model can only emit valid categories,
    PLUS a Python validation net that drops/*repairs* anything out of contract.
  * Checks finish_reason and never returns a half-truncated JSON as "clean".
"""

from __future__ import annotations

import io
import os
import json
import time
import logging

from google import genai
from google.genai import types

import config

log = logging.getLogger("uepl.gemini")

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GENAI_API_KEY:
            raise RuntimeError("GENAI_API_KEY is not set")
        _client = genai.Client(api_key=config.GENAI_API_KEY)
    return _client


# --------------------------------------------------------------------------- #
# Retry helper
# --------------------------------------------------------------------------- #
_TRANSIENT_HINTS = ("429", "500", "502", "503", "504", "deadline", "unavailable", "internal", "overloaded")


def _is_transient(err: Exception) -> bool:
    msg = str(err).lower()
    return any(h in msg for h in _TRANSIENT_HINTS)


def _with_retries(fn, what: str):
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - we classify below
            last = e
            if attempt >= config.MAX_RETRIES or not _is_transient(e):
                break
            delay = config.RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
            log.warning("%s failed (attempt %d/%d): %s — retrying in %.1fs",
                        what, attempt, config.MAX_RETRIES, e, delay)
            time.sleep(delay)
    raise RuntimeError(f"{what} failed after {config.MAX_RETRIES} attempts: {last}") from last


# --------------------------------------------------------------------------- #
# Files API: upload a whole video and wait until it is ACTIVE
# --------------------------------------------------------------------------- #
def upload_video(path: str, mime_type: str = "video/mp4"):
    """Upload a video via the Files API and block until it is ACTIVE.

    Returns the SDK File object (pass it straight into contents=[...]).
    Raises if the file never becomes ACTIVE or the upload keeps failing.
    """
    f = _with_retries(lambda: client().files.upload(file=path), f"files.upload({os.path.basename(path)})")
    deadline = time.time() + config.FILE_ACTIVE_TIMEOUT_S
    while True:
        state = getattr(f.state, "name", str(f.state))
        if state == "ACTIVE":
            return f
        if state == "FAILED":
            raise RuntimeError(f"Files API processing FAILED for {path}")
        if time.time() > deadline:
            raise RuntimeError(f"Files API did not become ACTIVE within "
                               f"{config.FILE_ACTIVE_TIMEOUT_S}s for {path} (last state={state})")
        time.sleep(config.FILE_POLL_INTERVAL_S)
        f = _with_retries(lambda: client().files.get(name=f.name), "files.get")


def delete_file(f) -> None:
    try:
        client().files.delete(name=f.name)
    except Exception as e:  # noqa: BLE001 - best-effort cleanup
        log.debug("files.delete failed (non-fatal): %s", e)


# --------------------------------------------------------------------------- #
# Safety settings
# --------------------------------------------------------------------------- #
# Dashcam footage (crashes, road rage, abusive language, near-misses) routinely
# trips DANGEROUS_CONTENT / HARASSMENT filters, which return finish_reason=SAFETY
# and empty text — dropping a legitimately-detected violation. We loosen (not
# disable) the content filters so analysis isn't silently blocked. This is an
# internal safety-analysis tool, not a content generator.
def _safety_settings() -> list[types.SafetySetting]:
    T = types
    cats = [
        T.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        T.HarmCategory.HARM_CATEGORY_HARASSMENT,
        T.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        T.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
    ]
    return [T.SafetySetting(category=c, threshold=T.HarmBlockThreshold.BLOCK_ONLY_HIGH) for c in cats]


def _video_part(file_obj, fps: float):
    """Reference the uploaded file as a video part, overriding the default 1 FPS
    sampling with `fps` so transient motion (braking/swerve) is actually seen."""
    return types.Part(
        file_data=types.FileData(file_uri=file_obj.uri, mime_type=file_obj.mime_type),
        video_metadata=types.VideoMetadata(fps=fps),
    )


# --------------------------------------------------------------------------- #
# Response schemas (enum-constrained)
# --------------------------------------------------------------------------- #
# propertyOrdering puts `reason` FIRST so the model writes its evidence before it
# commits to a category/severity/confidence — chain-of-thought-in-schema, which
# improves classification consistency at no extra cost.
def _behaviour_schema(categories: list[str]) -> types.Schema:
    S, T = types.Schema, types.Type
    return S(
        type=T.ARRAY,
        items=S(
            type=T.OBJECT,
            required=["reason", "category", "severity", "confidence", "timestamp", "start_s", "end_s"],
            property_ordering=["reason", "category", "severity", "confidence",
                               "timestamp", "start_s", "end_s", "speed_kmh"],
            properties={
                "reason": S(type=T.STRING),
                "category": S(type=T.STRING, enum=list(categories)),
                "severity": S(type=T.STRING, enum=["low", "medium", "high"]),
                "confidence": S(type=T.NUMBER),
                "timestamp": S(type=T.STRING),
                "start_s": S(type=T.NUMBER),
                "end_s": S(type=T.NUMBER),
                "speed_kmh": S(type=T.NUMBER, nullable=True),
            },
        ),
    )


def _equipment_schema(categories: list[str]) -> types.Schema:
    S, T = types.Schema, types.Type
    return S(
        type=T.ARRAY,
        items=S(
            type=T.OBJECT,
            required=["reason", "issue", "severity", "confidence"],
            property_ordering=["reason", "issue", "severity", "confidence"],
            properties={
                "reason": S(type=T.STRING),
                "issue": S(type=T.STRING, enum=list(categories)),
                "severity": S(type=T.STRING, enum=["low", "medium", "high"]),
                "confidence": S(type=T.NUMBER),
            },
        ),
    )


# --------------------------------------------------------------------------- #
# Core generate call
# --------------------------------------------------------------------------- #
def _generate(model: str, file_obj, prompt: str, schema: types.Schema,
              thinking_budget: int, fps: float) -> list[dict]:
    cfg = types.GenerateContentConfig(
        temperature=config.TEMPERATURE,
        response_mime_type="application/json",
        response_schema=schema,
        max_output_tokens=config.MAX_OUTPUT_TOKENS,
        safety_settings=_safety_settings(),
        thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
    )

    def call():
        return client().models.generate_content(
            model=model,
            contents=[_video_part(file_obj, fps), prompt],
            config=cfg,
        )

    resp = _with_retries(call, f"generate_content({model})")

    finish = None
    try:
        finish = getattr(resp.candidates[0].finish_reason, "name", str(resp.candidates[0].finish_reason))
    except Exception:  # noqa: BLE001
        pass

    if finish in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        # Content-filter block: no usable output. Surface clearly.
        raise RuntimeError(f"Generation blocked (finish_reason={finish})")
    if finish == "MAX_TOKENS":
        # Truncated JSON. Try to salvage complete objects; if none, fail loudly
        # rather than reporting a truncated clip as "clean".
        salvaged = _parse_json_array(resp.text or "")
        if salvaged:
            log.warning("Output hit MAX_TOKENS; salvaged %d complete event(s)", len(salvaged))
            return salvaged
        raise RuntimeError("Generation truncated (finish_reason=MAX_TOKENS) with no salvageable JSON")

    return _parse_json_array((resp.text or "").strip())


def _parse_json_array(text: str) -> list[dict]:
    if not text:
        return []
    # Strip accidental markdown fences.
    if text.startswith("```"):
        text = text.strip("`")
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # last resort: slice from first '[' to last ']'
        i, j = text.find("["), text.rfind("]")
        if i != -1 and j != -1 and j > i:
            data = json.loads(text[i:j + 1])
        else:
            raise
    if isinstance(data, dict):
        data = [data]
    return data if isinstance(data, list) else []


# --------------------------------------------------------------------------- #
# Validation nets (defence in depth beyond the enum schema)
# --------------------------------------------------------------------------- #
def _clean_common(item: dict) -> dict:
    conf = item.get("confidence", 0)
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 0.0
    item["confidence"] = max(0.0, min(1.0, conf))
    sev = str(item.get("severity", "medium")).lower()
    item["severity"] = sev if sev in ("low", "medium", "high") else "medium"
    return item


def validate_behaviour(items: list[dict], categories: list[str]) -> list[dict]:
    allowed = set(categories)
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cat = it.get("category")
        if cat not in allowed:
            log.warning("Dropping event with out-of-taxonomy category=%r", cat)
            continue
        it = _clean_common(it)
        for k in ("start_s", "end_s"):
            try:
                it[k] = float(it.get(k, 0) or 0)
            except (TypeError, ValueError):
                it[k] = 0.0
        it.setdefault("timestamp", "not visible")
        it.setdefault("reason", "")
        out.append(it)
    return out


def validate_equipment(items: list[dict], categories: list[str]) -> list[dict]:
    allowed = set(categories)
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("issue") not in allowed:
            log.warning("Dropping equipment item with out-of-taxonomy issue=%r", it.get("issue"))
            continue
        it = _clean_common(it)
        it.setdefault("reason", "")
        out.append(it)
    return out


# --------------------------------------------------------------------------- #
# Public: behaviour + equipment analysis of an already-uploaded file
# --------------------------------------------------------------------------- #
def analyze_behaviour(file_obj, prompt: str, categories: list[str], fps: float) -> list[dict]:
    raw = _generate(config.BEHAVIOUR_MODEL, file_obj, prompt,
                    _behaviour_schema(categories), config.THINKING_BUDGET_BEHAVIOUR, fps)
    return validate_behaviour(raw, categories)


def analyze_equipment(file_obj, prompt: str, categories: list[str]) -> list[dict]:
    raw = _generate(config.EQUIPMENT_MODEL, file_obj, prompt,
                    _equipment_schema(categories), config.THINKING_BUDGET_EQUIPMENT,
                    config.EQUIPMENT_FPS)
    return validate_equipment(raw, categories)


# --------------------------------------------------------------------------- #
# View classifier (cabin vs front) — catches mismatched uploads
# --------------------------------------------------------------------------- #
_VIEW_PROMPT = (
    "You are shown a short truck dashcam clip. Classify the CAMERA VIEWPOINT:\n"
    "- 'cabin' = interior / driver-facing: you can see occupants, the steering wheel, or the cab.\n"
    "- 'front' = forward road-facing: you see the road ahead, lane markings, other vehicles.\n"
    "Reply with EXACTLY one word: cabin, front, or unclear. No other text."
)


def classify_view(file_obj) -> str:
    """Cheap cabin-vs-front classification used to catch a mismatched upload.

    Returns 'cabin', 'front', or 'unclear'. Never raises — a failed pre-check must
    not block the real analysis (falls back to 'unclear').
    """
    cfg = types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=16,
        safety_settings=_safety_settings(),
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    def call():
        return client().models.generate_content(
            model=config.EQUIPMENT_MODEL,
            contents=[_video_part(file_obj, 0.5), _VIEW_PROMPT],  # ~0.5 fps is plenty to tell cabin from road
            config=cfg,
        )

    try:
        resp = _with_retries(call, "classify_view")
        text = (resp.text or "").strip().lower()
    except Exception as e:  # noqa: BLE001 - never let the pre-check kill analysis
        log.warning("classify_view failed (%s); skipping view check", e)
        return "unclear"
    if "cabin" in text:
        return "cabin"
    if "front" in text:
        return "front"
    return "unclear"
