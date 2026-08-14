"""
Driver profiling / scoring.

Turns a flat list of confirmed behaviour events (from the cabin and/or front
analysis) into an interpretable driver profile: a weighted risk score, an A-F
safety grade, per-category breakdown, and a short human-readable summary.

The model is deliberately simple and transparent (every number is explainable to a
fleet manager) and every knob lives in config.py so it can be tuned without
touching this logic.

Two entry points:
  * profile_from_events(events)      -> profile for ONE clip / analysis
  * aggregate_profiles(clip_profiles) -> roll several clips up into a driver profile
"""

from __future__ import annotations

from collections import defaultdict

from config import (
    SEVERITY_POINTS,
    CATEGORY_WEIGHTS,
    Severity,
)

# Events below this confidence are NOT scored; they are surfaced separately for
# human review so a shaky guess never silently drags a driver's grade down.
REVIEW_CONFIDENCE_THRESHOLD = 0.6

# Maps accumulated risk points -> grade. Bands are per-analysis (a ~1 min clip);
# tune for your trip length. (upper_bound_inclusive, grade, label)
_GRADE_BANDS = [
    (0.0, "A", "Excellent"),
    (3.0, "B", "Good"),
    (8.0, "C", "Fair"),
    (15.0, "D", "Poor"),
    (float("inf"), "F", "High risk"),
]

# safety_score (0-100, higher = safer) = 100 - RISK_SCALE * risk_points, floored at 0.
RISK_SCALE = 5.0

_SEV_ORDER = {Severity.LOW.value: 0, Severity.MEDIUM.value: 1, Severity.HIGH.value: 2}


def _event_points(category: str, severity: str) -> float:
    sev_pts = SEVERITY_POINTS.get(severity, SEVERITY_POINTS[Severity.MEDIUM.value])
    weight = CATEGORY_WEIGHTS.get(category, 1.0)
    return sev_pts * weight


def _grade_for(risk_points: float) -> tuple[str, str]:
    for upper, grade, label in _GRADE_BANDS:
        if risk_points <= upper:
            return grade, label
    return "F", "High risk"


def profile_from_events(events: list[dict]) -> dict:
    """Build a driver profile from one analysis' confirmed events.

    `events` items are dicts with at least: category, severity, confidence.
    Extra fields (timestamp, reason, camera, ...) are preserved untouched.
    """
    scored: list[dict] = []
    review: list[dict] = []
    for e in events:
        conf = float(e.get("confidence", 0) or 0)
        # confidence 0.0 sentinel is our WRONG_VIEW marker — never score it.
        if conf < REVIEW_CONFIDENCE_THRESHOLD:
            review.append(e)
        else:
            scored.append(e)

    per_category: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "max_severity": None, "points": 0.0}
    )
    risk_points = 0.0
    for e in scored:
        cat = e.get("category", "Unknown")
        sev = e.get("severity", Severity.MEDIUM.value)
        pts = _event_points(cat, sev)
        risk_points += pts
        pc = per_category[cat]
        pc["count"] += 1
        pc["points"] = round(pc["points"] + pts, 2)
        if pc["max_severity"] is None or _SEV_ORDER.get(sev, 1) > _SEV_ORDER.get(pc["max_severity"], 1):
            pc["max_severity"] = sev

    grade, grade_label = _grade_for(risk_points)
    safety_score = max(0, round(100 - RISK_SCALE * risk_points))

    # Top risks: categories ordered by contributed points, worst first.
    top_risks = sorted(
        (
            {"category": c, **v}
            for c, v in per_category.items()
        ),
        key=lambda x: x["points"],
        reverse=True,
    )

    return {
        "safety_score": safety_score,       # 0-100, higher = safer
        "grade": grade,                     # A-F
        "grade_label": grade_label,
        "risk_points": round(risk_points, 2),
        "confirmed_event_count": len(scored),
        "review_event_count": len(review),
        "per_category": {c: v for c, v in per_category.items()},
        "top_risks": top_risks[:5],
        "summary": _summarize(grade_label, safety_score, top_risks, len(review)),
        "review_items": review,
    }


def _summarize(grade_label: str, score: int, top_risks: list[dict], review_n: int) -> str:
    if not top_risks:
        base = f"Clean clip — no confirmed violations. Safety score {score}/100 ({grade_label})."
    else:
        worst = ", ".join(
            f"{r['category']} x{r['count']} ({r['max_severity']})" for r in top_risks[:3]
        )
        base = f"Safety score {score}/100 ({grade_label}). Main issues: {worst}."
    if review_n:
        base += f" {review_n} low-confidence item(s) flagged for human review."
    return base


def aggregate_profiles(clip_profiles: list[dict]) -> dict:
    """Roll several per-clip profiles up into one driver profile.

    Use this to profile a driver across a trip / day / vehicle: pass the
    `profile_from_events` output of each clip. Risk points sum; the safety score
    is recomputed from the total so many small infractions add up.
    """
    total_points = sum(p.get("risk_points", 0.0) for p in clip_profiles)
    total_confirmed = sum(p.get("confirmed_event_count", 0) for p in clip_profiles)
    total_review = sum(p.get("review_event_count", 0) for p in clip_profiles)

    merged: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "max_severity": None, "points": 0.0}
    )
    for p in clip_profiles:
        for cat, v in p.get("per_category", {}).items():
            m = merged[cat]
            m["count"] += v.get("count", 0)
            m["points"] = round(m["points"] + v.get("points", 0.0), 2)
            sev = v.get("max_severity")
            if sev and (m["max_severity"] is None or _SEV_ORDER.get(sev, 1) > _SEV_ORDER.get(m["max_severity"], 1)):
                m["max_severity"] = sev

    # Average points-per-clip drives the grade so a long clean trip isn't punished
    # for its length; total points still inform the score ceiling.
    n = max(1, len(clip_profiles))
    grade, grade_label = _grade_for(total_points / n)
    safety_score = max(0, round(100 - RISK_SCALE * (total_points / n)))

    top_risks = sorted(
        ({"category": c, **v} for c, v in merged.items()),
        key=lambda x: x["points"],
        reverse=True,
    )
    return {
        "clips_analyzed": len(clip_profiles),
        "safety_score": safety_score,
        "grade": grade,
        "grade_label": grade_label,
        "total_risk_points": round(total_points, 2),
        "confirmed_event_count": total_confirmed,
        "review_event_count": total_review,
        "per_category": {c: v for c, v in merged.items()},
        "top_risks": top_risks[:5],
        "summary": _summarize(grade_label, safety_score, top_risks, total_review),
    }
