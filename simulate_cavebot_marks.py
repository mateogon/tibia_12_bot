"""Offline replay harness for cavebot mark progression.

Usage:
  python simulate_cavebot_marks.py --session training_data/cavebot_sessions/<session>
"""

import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np


THRESHOLDS = {
    "skull": 0.88,
    "lock": 0.80,
    "cross": 0.89,
    "star": 0.89,
}


def load_trace(trace_path):
    rows = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def detect_mark_positions(frame_bgr, template_bgr, threshold):
    if frame_bgr is None or template_bgr is None:
        return []
    res = cv2.matchTemplate(frame_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(res >= threshold)

    # Greedy NMS-like filtering by center distance.
    out = []
    h, w = template_bgr.shape[:2]
    for x, y in sorted(zip(xs, ys), key=lambda p: res[p[1], p[0]], reverse=True):
        cx = x + w // 2
        cy = y + h // 2
        keep = True
        for px, py, _ in out:
            if abs(cx - px) < max(6, w // 2) and abs(cy - py) < max(6, h // 2):
                keep = False
                break
        if keep:
            out.append((cx, cy, float(res[y, x])))
    return out


def nearest_dist_to_center(points, center):
    if not points:
        return None
    cx, cy = center
    dists = [((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 for px, py, _ in points]
    return float(min(dists))


def run(session_dir):
    session = Path(session_dir)
    trace_path = session / "trace.jsonl"
    frames_dir = session / "frames"
    marks_dir = Path("img") / "map_marks"

    rows = load_trace(trace_path)
    if not rows:
        print("No trace rows found.")
        return

    cycle = ["skull", "lock", "cross", "star"]
    current_idx = 0
    advances = 0
    resets = 0
    skipped_no_visible = 0
    arrival_threshold = 6.0
    hold_after_advance = 3  # frames
    hold_left = 0

    templates = {}
    for m in cycle:
        tp = cv2.imread(str(marks_dir / f"{m}.png"))
        templates[m] = tp

    for r in rows:
        frame_path = frames_dir / r["frame"]
        frame = cv2.imread(str(frame_path))
        if frame is None:
            continue

        h, w = frame.shape[:2]
        center = (w // 2, h // 2)

        current = cycle[current_idx]
        pts = detect_mark_positions(frame, templates[current], THRESHOLDS[current])
        visible = len(pts)
        dist = nearest_dist_to_center(pts, center)

        if hold_left > 0:
            hold_left -= 1
            continue

        if visible > 0 and dist is not None and dist <= arrival_threshold:
            advances += 1
            current_idx += 1
            if current_idx >= len(cycle):
                current_idx = 0
            hold_left = hold_after_advance
            continue

        if visible == 0:
            skipped_no_visible += 1
            current_idx += 1
            if current_idx >= len(cycle):
                current_idx = 0
                resets += 1
            hold_left = hold_after_advance

    # Metadata-driven summary if recorder has finalized segment labels.
    seg_rows = [r for r in rows if "goal_mark" in r]
    if seg_rows:
        by_goal = {}
        for r in seg_rows:
            g = r.get("goal_mark", "unknown")
            by_goal[g] = by_goal.get(g, 0) + 1

    print(f"Session: {session}")
    print(f"Frames: {len(rows)}")
    print(f"Cycle: {' -> '.join(cycle)}")
    print(f"Advances: {advances}")
    print(f"Resets: {resets}")
    print(f"Skips (no visible): {skipped_no_visible}")
    print(f"Final target mark: {cycle[current_idx]}")
    if seg_rows:
        print("Goal-labeled frames:")
        for g in cycle:
            if g in by_goal:
                print(f"  {g}: {by_goal[g]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="Path to cavebot session dir")
    args = ap.parse_args()
    run(args.session)


if __name__ == "__main__":
    main()
