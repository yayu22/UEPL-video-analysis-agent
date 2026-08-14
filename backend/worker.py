"""
CLI / batch entry point.

Two uses:
  * quick local test against a file or a folder of sample clips, e.g.
        python worker.py --file "D:/.../Front (Road-side)/44.mp4" --camera front
        python worker.py --dir  "D:/.../Front (Road-side)" --camera front
  * a template for an AFDD-style fleet worker: swap _iter_local for a poll of the
    fleet API (signed URL -> download -> analyze_clip -> post profile back).

Deliberately mirrors the AFDD annotator agents' structure so it drops into the
same GCP deployment.
"""

from __future__ import annotations

import os
import sys
import json
import glob
import argparse
import logging

from config import CameraType
import analysis

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("uepl.worker")

VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv", ".avi")


def _iter_local(path: str):
    if os.path.isdir(path):
        for p in sorted(glob.glob(os.path.join(path, "*"))):
            if p.lower().endswith(VIDEO_EXTS):
                yield p
    elif os.path.isfile(path):
        yield path


def main() -> int:
    ap = argparse.ArgumentParser(description="UEPL driver profiling / equipment analysis")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="single video file")
    src.add_argument("--dir", help="folder of video files")
    ap.add_argument("--camera", required=True, choices=[c.value for c in CameraType])
    ap.add_argument("--no-equipment", action="store_true", help="skip equipment/QA analysis")
    ap.add_argument("--out", help="write full JSON result to this path")
    args = ap.parse_args()

    cam = CameraType(args.camera)
    paths = list(_iter_local(args.file or args.dir))
    if not paths:
        log.error("No video files found")
        return 1

    clips = []
    for p in paths:
        log.info("=== %s ===", os.path.basename(p))
        try:
            r = analysis.analyze_clip(p, cam, run_equipment=not args.no_equipment)
        except Exception as e:  # noqa: BLE001
            log.error("Failed: %s", e)
            continue
        r["path"] = p
        clips.append(r)
        prof = r["profile"]
        log.info("  -> %s  |  %d event(s), %d equipment issue(s)  |  %s",
                 f"{prof['grade']} ({prof['safety_score']}/100)",
                 len(r["events"]), len(r["equipment"]), prof["summary"])
        for ev in r["events"]:
            log.info("     • [%s/%s @%s] %s", ev["category"], ev["severity"],
                     ev.get("timestamp", "?"), ev.get("reason", ""))
        for w in r.get("warnings", []):
            log.warning("     ! %s", w)

    result = {"clips": clips}
    if len(clips) > 1:
        import scoring
        result["driver_profile"] = scoring.aggregate_profiles([c["profile"] for c in clips])
        dp = result["driver_profile"]
        log.info("=== DRIVER PROFILE (%d clips) === %s (%d/100) | %s",
                 dp["clips_analyzed"], dp["grade"], dp["safety_score"], dp["summary"])

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        log.info("Wrote %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
