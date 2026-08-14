# Evaluation & Rebuild — UEPL Driver-Behaviour Video Agent

**Date:** 2026-08-14
**Scope:** Evaluate the existing Gemini video-analysis app, make it robust and
accurate, improve both camera prompts, and add driver profiling + equipment analysis.

---

## 1. Verdict

The original app was a solid *prototype* but **not production-robust or accurate**
for real dashcam footage. The two most serious problems were architectural, not
cosmetic:

1. **It would fail outright on real videos.** The in-cabin and equipment paths
   inline the whole video as base64, which exceeds Gemini's request-size limit for
   any real clip (the sample clips are 5–22 MB and grow fast).
2. **The road-camera path structurally cannot detect half its own categories.** It
   reduced video to 2 still frames/second in independent 5-second batches — which
   destroys the motion information that "harsh braking", "harsh acceleration",
   "jerky driving", "momentum preservation" and "U-turn without stopping" are
   *made of*.

Plus a **security hole** (the Gemini key was compiled into the browser bundle, so
anyone could steal it) and **no driver profiling at all** despite that being the goal.

The rebuild addresses all of these. It is a **Python backend** (aligned with your
deployed AFDD annotator agents — same `google-genai` SDK, model family, and prompt
style) that both cameras drive through the **Files API on the full video**, plus a
rewired frontend that no longer holds the key and now renders a driver profile.

---

## 2. Ground truth I verified first

I extracted real frames from your sample clips and studied your AFDD agents. Key facts
that shaped the rebuild:

- **Overlay layout** (consistent "Monit" dashcam): brand top-left, **plate top-right**,
  **GPS coords + speed bottom-left** (speed is a bare number, no "km/h"), **date + time
  bottom-right**. The old prompt looked for speed "in the corner, xxx km/h format" — wrong
  position *and* format. The new prompt reads the correct pixels, and uses the overlay
  **clock** for day/night (e.g. `44.mp4` at 23:26 → night).
- **The "Front (Road-side)" sample folder is mixed** — 2 of the 4 clips I sampled are
  actually *in-cabin* views. So the camera label can't be trusted; the system now
  **auto-detects a wrong view** and warns instead of producing garbage.
- **Your AFDD agents** already encode the right patterns: `google-genai`,
  `gemini-2.5-flash`, `temperature=0`, thinking budgets, majority voting for borderline
  calls, and meticulous false-positive-resistant prompts ("ignore the camera's own
  trigger text", "when in doubt → falsy", camera-angle awareness). The new prompts adopt
  that discipline.

---

## 3. Findings (old app)

Severity: 🔴 critical · 🟠 high · 🟡 medium

### Robustness
| # | Sev | Issue | Where |
|---|-----|-------|-------|
| R1 | 🔴 | Whole video inlined as base64 → exceeds the ~20 MB request cap → in-cabin & equipment fail on real clips | `geminiService.ts` `fileToGenerativePart`, lines 237, 282 |
| R2 | 🔴 | `Promise.all` over ~1 batch/5s with **no concurrency limit and no retry** — one transient 429/500 rejects the *entire* run and loses all good results | `geminiService.ts:171–195` |
| R3 | 🟠 | Browser frame extraction can **hang forever** on codecs that never fire `loadedmetadata`/`seeked`; `duration` can be `Infinity`/`NaN`; extraction errors are swallowed and return empty silently | `geminiService.ts:93–167` |
| R4 | 🟠 | Empty / safety-blocked / truncated (`MAX_TOKENS`) responses aren't distinguished; empty equipment result is shown as "all CLEAR" | `geminiService.ts:305`, `analyzeEquipment` |
| R5 | 🟡 | Object-URL leak (revoked only on success / reset, not on re-analyze) | `App.tsx:19–24`, `geminiService.ts:217` |

### Accuracy
| # | Sev | Issue |
|---|-----|-------|
| A1 | 🔴 | **2fps still batches can't see motion** → systematic false negatives on the temporal road categories, and false positives where the model guesses "harsh braking" from two unrelated stills |
| A2 | 🔴 | `event`/`issue` are free strings, but the UI matches the checklist by **exact string equality** — any paraphrase ("Speeding" vs "Speed violation") shows red in the log but "CLEAR" in the checklist. Silent misses. |
| A3 | 🟠 | Independent parallel batches produce **duplicate** violations with no dedup; a 30s lane offence is reported 6×, corrupting any frequency-based profiling |
| A4 | 🟠 | `timestamp` is **required** by the schema but often absent in footage → forces hallucinated timestamps; `AnalysisLog` then `split(' ')`s them and can render `NaN%` |
| A5 | 🟡 | Speed read from 0.8-quality downscaled JPEGs; the meaningless `frame` field is dead weight |

### Security / architecture
| # | Sev | Issue |
|---|-----|-------|
| S1 | 🔴 | **Gemini API key compiled into the browser** via Vite `define(process.env.API_KEY)` — extractable by anyone who opens the app |
| S2 | 🟠 | Whole video **uploaded twice** (behaviour + equipment) — double cost/latency |
| S3 | 🟠 | **No driver profiling** — only a flat per-clip list; no scoring/aggregation despite being the stated goal |
| S4 | 🟡 | Pinned to `gemini-2.5-flash`/`-lite` which are now last-generation (see §6) |

### Prompt quality (the biggest accuracy lever)
Found via an adversarial review of the prompts. Highlights:
- **Motion-gated rules with no motion signal** — the cabin prompt judged "while moving"
  from a camera that can't see the road and has no telemetry → guesswork.
- **Audio with no speaker attribution** — "driver is on a call" can't be attributed to
  driver vs. co-driver from a mono cabin track.
- **Speed with no overlay** — the #1 road category depended on an overlay the prompt never
  guaranteed exists, with no "if absent, don't flag" fallback.
- **Hard-coded geography** — Pakistan/left-hand-traffic assumptions applied with no
  sanity-check; footage from the other side silently inverts every lane/overtake verdict.
- **1-FPS temporal asks** — sub-second "eyes closed > 2s", yawn-counting, A/V-sync,
  "clock jumped > 1s" collide with Gemini's ~1 FPS sampling.
- **Overlapping categories** (Casual vs Distracted, Momentum vs Overtaking) with no
  precedence, and the confusing **"FOD"** term never clearly scoped.

---

## 4. What was rebuilt

```
Browser (React, no key)  ──HTTPS──►  Backend (FastAPI, Python)  ──►  Gemini (Files API, full video)
        upload + render                holds key · retries · scoring
```

| Concern | Old | New |
|---|---|---|
| Video → model | inline base64 (fails >~20 MB) | **Files API, whole video**, upload once & reuse |
| Motion detection | 2fps stills (impossible) | **native video @ 5 FPS** front / 2 FPS cabin (`videoMetadata.fps`) |
| API key | in browser | **server-side only** |
| Output categories | free strings | **enum-constrained schema** + Python validation net |
| Reliability | `Promise.all`, no retry | retries+backoff, `finish_reason` (MAX_TOKENS/SAFETY) handling, loosened safety filters for road footage |
| Duplicates | none | one event per behaviour (range), on-taxonomy only |
| Wrong camera | undetected | **auto view-detection** → warning |
| Profiling | none | **severity-weighted score + A–F grade + summary** |
| Model | 2.5-flash (pinned) | configurable; documented upgrade to `gemini-3.7-flash` |

New backend lives in [`backend/`](backend/): `config.py`, `prompts.py`,
`gemini_client.py`, `analysis.py`, `scoring.py`, `api.py`, `worker.py`. It typechecks/
imports cleanly against `google-genai` 1.47.0; the frontend builds cleanly.

---

## 5. Prompt improvements (examples)

- **Cabin** — motion-gating removed ("you cannot see the road; infer motion only from
  cabin cues, else omit"); phone-call detection now requires **visual corroboration** of
  the driver; seatbelt only flags when **clearly absent and torso visible**; Road Rage is
  **audio-primary**; Loose Items lists what is *not* a loose item; added a driver-seatbelt
  category so the rule has a home.
- **Front** — hard **no-overlay → never flag Speed** rule; the km/h-estimate ban is scoped
  to Speed only (relative harshness still allowed for turns/harsh driving); **geography
  sanity-check**; overtake-vs-lane routing requires *seeing a vehicle being passed*; U-turn
  "no stop" only when the scene shows continuous sweep; dusk/dawn defers to the overlay clock.
- **Equipment** — audio check gated to the camera type; temporal items hardened against
  1-FPS sampling ("a ~1s gap is normal sampling, not a jump"); "Camera Not Working" guarded
  against legitimately static scenes.
- **All** — strict enum output, `reason` emitted **before** the verdict (chain-of-thought in
  schema), per-event **severity + confidence**, correct overlay parsing, empty-array on clean.

---

## 6. Model & cost note

As of Aug 2026 the lineup has moved past 2.5. `gemini-3.7-flash` (released 2026-08-13) is the
recommended video+audio workhorse and — importantly for cabin audio — **folds audio into the
base token price** (2.5-flash bills audio at 3× the visual rate). The rebuild **defaults to
`gemini-2.5-flash`** to match your deployed AFDD stack exactly, but switching is a one-line env
change (`UEPL_BEHAVIOUR_MODEL=gemini-3.7-flash`) once you confirm it's enabled on your key.

---

## 7. Action items / recommendations

1. **🔴 Rotate the leaked Gemini key.** `our-affd-annotator-agents/.claude/settings.local.json`
   contains a live `GENAI_API_KEY` in plaintext (committed). Rotate it and move it to a secret.
2. **Deploy the backend** to Cloud Run next to AFDD; set `GENAI_API_KEY` as a secret; raise the
   request timeout (full-video analysis takes tens of seconds).
3. **Calibrate the scoring weights** (`config.py`) against a few labelled trips — the grade
   bands and category weights are sensible defaults, not tuned to your risk appetite yet.
4. **For fleet-scale profiling**, adapt `worker.py` into an AFDD-style poller (signed URL →
   analyze → post profile) to aggregate scores per driver/vehicle over time.
5. **Consider a Pro second-pass** (`gemini-3.1-pro-preview`) only for high-severity events to
   cut false positives further, mirroring AFDD's majority-vote philosophy.
6. **Validate the `fps` override** actually raises token usage on your model/SDK (there's a known
   edge case) before trusting the denser front-camera sampling.
```
