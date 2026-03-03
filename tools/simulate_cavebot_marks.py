"""Offline replay harness for cavebot mark progression.

Usage:
  python simulate_cavebot_marks.py --session training_data/cavebot_sessions/<session>
"""

import argparse
import concurrent.futures
import json
import math
import os
import time
from pathlib import Path

import cv2
import numpy as np


THRESHOLDS = {
    "skull": 0.88,
    "lock": 0.80,
    "cross": 0.89,
    "star": 0.89,
}

DEFAULT_ARRIVAL_THRESHOLD = 4.0
DEFAULT_CONFIRM_FRAMES = 2
DEFAULT_IMMEDIATE_ADVANCE_THRESHOLD = 1.0
DEFAULT_HOLD_AFTER_ADVANCE = 1
DEFAULT_MIN_TIME_ON_MARK_MS = 0
DEFAULT_ADVANCE_ON_NO_VISIBLE = False


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


def nearest_point_to_center(points, center):
    if not points:
        return None
    cx, cy = center
    return min(points, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2))


def dist(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def run(
    session_dir,
    arrival_threshold=DEFAULT_ARRIVAL_THRESHOLD,
    confirm_frames=DEFAULT_CONFIRM_FRAMES,
    immediate_advance_threshold=DEFAULT_IMMEDIATE_ADVANCE_THRESHOLD,
    ignore_boundary_frames=1,
    thresholds=None,
    hold_after_advance=DEFAULT_HOLD_AFTER_ADVANCE,
    min_time_on_mark_ms=DEFAULT_MIN_TIME_ON_MARK_MS,
    advance_on_no_visible=DEFAULT_ADVANCE_ON_NO_VISIBLE,
    show_mismatches=10,
    print_output=True,
):
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
    hold_left = 0
    frame_count = 0
    last_advance_ts = None
    arrived_streak = 0

    labeled_total = 0
    mark_correct = 0
    mark_mismatches = []
    target_devs = []
    target_dev_by_mark = {m: [] for m in cycle}
    predicted_mark_by_frame = {}

    thresholds = dict(thresholds or THRESHOLDS)
    templates = {}
    for m in cycle:
        tp = cv2.imread(str(marks_dir / f"{m}.png"))
        templates[m] = tp

    for r in rows:
        frame_path = frames_dir / r["frame"]
        frame = cv2.imread(str(frame_path))
        if frame is None:
            continue
        frame_count += 1

        h, w = frame.shape[:2]
        center = (w // 2, h // 2)

        current = cycle[current_idx]
        predicted_mark_by_frame[str(r.get("frame", ""))] = current
        pts = detect_mark_positions(frame, templates[current], float(thresholds[current]))
        visible = len(pts)
        nearest_center_dist = nearest_dist_to_center(pts, center)
        chosen = nearest_point_to_center(pts, center)
        ts_ms = int(r.get("ts_ms", 0))

        goal_mark = r.get("goal_mark")
        goal_rel = r.get("goal_rel")
        if goal_mark:
            labeled_total += 1
            if current == goal_mark:
                mark_correct += 1
            else:
                mark_mismatches.append(
                    {
                        "frame": r.get("frame"),
                        "pred": current,
                        "goal": goal_mark,
                        "visible": visible,
                    }
                )
        if chosen is not None and goal_rel and current == goal_mark:
            d = dist((chosen[0], chosen[1]), (goal_rel[0], goal_rel[1]))
            target_devs.append(d)
            target_dev_by_mark[current].append(d)

        if hold_left > 0:
            hold_left -= 1
            continue

        reached_now = (
            visible > 0
            and nearest_center_dist is not None
            and nearest_center_dist <= arrival_threshold
        )
        if reached_now:
            arrived_streak += 1
        else:
            arrived_streak = 0

        enough_time_on_mark = True
        if min_time_on_mark_ms > 0 and last_advance_ts is not None and ts_ms > 0:
            enough_time_on_mark = (ts_ms - last_advance_ts) >= int(min_time_on_mark_ms)

        immediate_ok = (
            reached_now
            and nearest_center_dist is not None
            and float(nearest_center_dist) <= float(immediate_advance_threshold)
        )
        confirmed_ok = reached_now and arrived_streak >= max(1, int(confirm_frames))

        if (immediate_ok or confirmed_ok) and enough_time_on_mark:
            advances += 1
            current_idx += 1
            if current_idx >= len(cycle):
                current_idx = 0
            hold_left = hold_after_advance
            arrived_streak = 0
            last_advance_ts = ts_ms if ts_ms > 0 else last_advance_ts
            continue

        if visible == 0:
            skipped_no_visible += 1
            if advance_on_no_visible:
                current_idx += 1
                if current_idx >= len(cycle):
                    current_idx = 0
                    resets += 1
                hold_left = hold_after_advance
                arrived_streak = 0

    # Metadata-driven summary if recorder has finalized segment labels.
    seg_rows = [r for r in rows if "goal_mark" in r]
    if seg_rows:
        by_goal = {}
        for r in seg_rows:
            g = r.get("goal_mark", "unknown")
            by_goal[g] = by_goal.get(g, 0) + 1

    core_labeled_total = 0
    core_mark_correct = 0
    core_mark_mismatches = []
    ibf = max(0, int(ignore_boundary_frames))
    for r in rows:
        goal_mark = r.get("goal_mark")
        if not goal_mark:
            continue
        seg_idx = r.get("segment_idx")
        seg_size = r.get("segment_size")
        if seg_idx is None or seg_size is None:
            is_boundary = False
        else:
            seg_idx = int(seg_idx)
            seg_size = int(seg_size)
            is_boundary = (seg_idx < ibf) or (seg_idx >= max(0, seg_size - ibf))
        if is_boundary:
            continue
        core_labeled_total += 1
        pred_mark = str(predicted_mark_by_frame.get(str(r.get("frame", "")), ""))
        if pred_mark == goal_mark:
            core_mark_correct += 1
        else:
            core_mark_mismatches.append(
                {
                    "frame": r.get("frame"),
                    "pred": pred_mark,
                    "goal": goal_mark,
                    "seg_idx": r.get("segment_idx"),
                    "seg_size": r.get("segment_size"),
                }
            )

    summary = {
        "session": str(session),
        "frames": int(frame_count),
        "cycle": list(cycle),
        "advances": int(advances),
        "resets": int(resets),
        "skips_no_visible": int(skipped_no_visible),
        "final_target_mark": cycle[current_idx],
        "labeled_total": int(labeled_total),
        "mark_correct": int(mark_correct),
        "mark_accuracy": float(mark_correct) / float(max(1, labeled_total)) if labeled_total > 0 else 0.0,
        "core_labeled_total": int(core_labeled_total),
        "core_mark_correct": int(core_mark_correct),
        "core_mark_accuracy": float(core_mark_correct) / float(max(1, core_labeled_total)) if core_labeled_total > 0 else 0.0,
        "target_dev_mean": float(np.mean(np.array(target_devs, dtype=np.float32))) if target_devs else None,
        "target_dev_p95": float(np.percentile(np.array(target_devs, dtype=np.float32), 95)) if target_devs else None,
        "target_dev_max": float(np.max(np.array(target_devs, dtype=np.float32))) if target_devs else None,
        "mismatches": list(mark_mismatches),
        "core_mismatches": list(core_mark_mismatches),
        "goal_counts": {},
    }
    if seg_rows:
        for g, c in by_goal.items():
            summary["goal_counts"][g] = int(c)

    if print_output:
        print(f"Session: {session}")
        print(f"Frames: {frame_count}")
        print(f"Cycle: {' -> '.join(cycle)}")
        print(f"Advances: {advances}")
        print(f"Resets: {resets}")
        print(f"Skips (no visible): {skipped_no_visible}")
        print(f"Final target mark: {cycle[current_idx]}")
        if labeled_total > 0:
            acc = 100.0 * float(mark_correct) / float(max(1, labeled_total))
            print(f"Mark-follow accuracy vs labels: {mark_correct}/{labeled_total} ({acc:.1f}%)")
        if core_labeled_total > 0:
            cacc = 100.0 * float(core_mark_correct) / float(max(1, core_labeled_total))
            print(
                f"Core accuracy (ignore boundary {ibf}f): "
                f"{core_mark_correct}/{core_labeled_total} ({cacc:.1f}%)"
            )
        if target_devs:
            arr = np.array(target_devs, dtype=np.float32)
            print(
                "Target deviation px (when mark matches goal): "
                f"mean={float(np.mean(arr)):.2f} p50={float(np.percentile(arr, 50)):.2f} "
                f"p95={float(np.percentile(arr, 95)):.2f} max={float(np.max(arr)):.2f}"
            )
            for m in cycle:
                vals = target_dev_by_mark[m]
                if vals:
                    a = np.array(vals, dtype=np.float32)
                    print(f"  {m}: mean={float(np.mean(a)):.2f} p95={float(np.percentile(a, 95)):.2f} n={len(vals)}")
        if mark_mismatches and show_mismatches > 0:
            print(f"First {min(show_mismatches, len(mark_mismatches))} mark mismatches:")
            for it in mark_mismatches[:show_mismatches]:
                print(
                    f"  frame={it['frame']} pred={it['pred']} goal={it['goal']} visible={it['visible']}"
                )
        if seg_rows:
            print("Goal-labeled frames:")
            for g in cycle:
                if g in by_goal:
                    print(f"  {g}: {by_goal[g]}")
    return summary


def run_grid_search(session_dir, top_n=15, jobs=1, ignore_boundary_frames=1, search_thresholds=False):
    arrival_thresholds = [3.5, 4.0, 4.5, 5.0]
    confirm_frames_list = [1, 2, 3]
    immediate_list = [1.0, 1.5, 2.0]

    combos = []
    for arr in arrival_thresholds:
        for cf in confirm_frames_list:
            for imm in immediate_list:
                combos.append((arr, cf, imm))

    threshold_sets = [dict(THRESHOLDS)]
    if search_thresholds:
        skull_vals = [0.86, 0.88, 0.90]
        lock_vals = [0.76, 0.80, 0.84]
        cross_vals = [0.87, 0.89, 0.91]
        star_vals = [0.87, 0.89, 0.91]
        threshold_sets = []
        for s in skull_vals:
            for l in lock_vals:
                for c in cross_vals:
                    for st in star_vals:
                        threshold_sets.append({"skull": s, "lock": l, "cross": c, "star": st})

    eval_jobs = []
    for combo in combos:
        for thr in threshold_sets:
            eval_jobs.append((combo, thr))

    def eval_combo(job):
        combo, thr = job
        arr, cf, imm = combo
        r = run(
            session_dir,
            arrival_threshold=arr,
            confirm_frames=cf,
            immediate_advance_threshold=imm,
            thresholds=thr,
            ignore_boundary_frames=ignore_boundary_frames,
            hold_after_advance=DEFAULT_HOLD_AFTER_ADVANCE,
            min_time_on_mark_ms=DEFAULT_MIN_TIME_ON_MARK_MS,
            advance_on_no_visible=DEFAULT_ADVANCE_ON_NO_VISIBLE,
            show_mismatches=0,
            print_output=False,
        )
        score = (
            (1200.0 * r["core_mark_accuracy"])
            + (500.0 * r["mark_accuracy"])
            - (2.0 * abs(r["advances"] - 12))
            - (0.5 * float(r["resets"]))
            - (0.2 * float(r["skips_no_visible"]))
            - (0.03 * float(r["target_dev_p95"] or 0.0))
        )
        r["score"] = float(score)
        r["params"] = {
            "arrival_threshold": arr,
            "confirm_frames": cf,
            "immediate_advance_threshold": imm,
            "ignore_boundary_frames": int(ignore_boundary_frames),
            "skull_thr": float(thr["skull"]),
            "lock_thr": float(thr["lock"]),
            "cross_thr": float(thr["cross"]),
            "star_thr": float(thr["star"]),
        }
        return r

    results = []
    total = len(eval_jobs)
    start_t = time.perf_counter()
    last_printed = -1

    def maybe_print_progress(done):
        nonlocal last_printed
        if total <= 0:
            return
        pct = int((100.0 * done) / total)
        # Print every 5% and always at start/end.
        if done in (0, total) or pct // 5 > last_printed // 5:
            elapsed = max(0.0, time.perf_counter() - start_t)
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (total - done) / rate if rate > 0 else 0.0
            print(
                f"[GRID] {done}/{total} ({pct}%) elapsed={elapsed:.1f}s eta={eta:.1f}s",
                flush=True,
            )
            last_printed = pct

    jobs = int(jobs)
    maybe_print_progress(0)
    if jobs <= 1:
        for i, job in enumerate(eval_jobs, 1):
            results.append(eval_combo(job))
            maybe_print_progress(i)
    else:
        max_workers = max(1, min(jobs, (os.cpu_count() or 1)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(eval_combo, job) for job in eval_jobs]
            done = 0
            for fut in concurrent.futures.as_completed(futures):
                results.append(fut.result())
                done += 1
                maybe_print_progress(done)

    results.sort(
        key=lambda x: (
            x["score"],
            x["core_mark_accuracy"],
            x["mark_accuracy"],
            -abs(x["advances"] - 12),
            -(x["target_dev_p95"] or 999.0),
        ),
        reverse=True,
    )
    session = Path(session_dir)
    out_tsv = session / "grid_search_results.tsv"
    out_top = session / "grid_search_top.txt"
    with open(out_tsv, "w", encoding="utf-8") as f:
        f.write(
            "score\tcore_accuracy\taccuracy\tadvances\tresets\tskips_no_visible\tp95\tpmean\t"
            "arrival_threshold\tconfirm_frames\timmediate_advance_threshold\tignore_boundary_frames\t"
            "skull_thr\tlock_thr\tcross_thr\tstar_thr\n"
        )
        for r in results:
            p = r["params"]
            f.write(
                f"{r['score']:.4f}\t{100.0*r['core_mark_accuracy']:.4f}\t{100.0*r['mark_accuracy']:.4f}\t"
                f"{r['advances']}\t{r['resets']}\t{r['skips_no_visible']}\t"
                f"{float(r['target_dev_p95'] or 0.0):.4f}\t{float(r['target_dev_mean'] or 0.0):.4f}\t"
                f"{p['arrival_threshold']}\t{p['confirm_frames']}\t{p['immediate_advance_threshold']}\t"
                f"{p['ignore_boundary_frames']}\t{p['skull_thr']}\t{p['lock_thr']}\t{p['cross_thr']}\t{p['star_thr']}\n"
            )

    lines = []
    lines.append(f"=== Grid Search Results ({len(results)}/{total}) ===")
    lines.append(f"Session: {session}")
    lines.append(f"Saved full results: {out_tsv}")
    lines.append(f"Top {top_n}:")
    for i, r in enumerate(results[:top_n], 1):
        p = r["params"]
        lines.append(
            f"{i:2d}) score={r['score']:.2f} core={100.0*r['core_mark_accuracy']:.2f}% "
            f"acc={100.0*r['mark_accuracy']:.2f}% "
            f"adv={r['advances']} resets={r['resets']} skips={r['skips_no_visible']} "
            f"p95={float(r['target_dev_p95'] or 0.0):.2f} "
            f"arr={p['arrival_threshold']} cf={p['confirm_frames']} imm={p['immediate_advance_threshold']} "
            f"thr=[s:{p['skull_thr']},l:{p['lock_thr']},c:{p['cross_thr']},st:{p['star_thr']}]"
        )
    with open(out_top, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for ln in lines:
        print(ln)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="Path to cavebot session dir")
    ap.add_argument("--arrival-threshold", type=float, default=DEFAULT_ARRIVAL_THRESHOLD, help="Distance to center to advance mark")
    ap.add_argument("--confirm-frames", type=int, default=DEFAULT_CONFIRM_FRAMES, help="Consecutive reached frames required before advancing")
    ap.add_argument("--immediate-advance-threshold", type=float, default=DEFAULT_IMMEDIATE_ADVANCE_THRESHOLD, help="Immediate advance if distance <= this (bypasses confirm)")
    ap.add_argument("--ignore-boundary-frames", type=int, default=1, help="Ignore first/last N frames in each labeled segment for core accuracy")
    ap.add_argument("--skull-thr", type=float, default=THRESHOLDS["skull"], help="Template threshold for skull mark")
    ap.add_argument("--lock-thr", type=float, default=THRESHOLDS["lock"], help="Template threshold for lock mark")
    ap.add_argument("--cross-thr", type=float, default=THRESHOLDS["cross"], help="Template threshold for cross mark")
    ap.add_argument("--star-thr", type=float, default=THRESHOLDS["star"], help="Template threshold for star mark")
    ap.add_argument("--show-mismatches", type=int, default=10, help="How many mismatch rows to print")
    ap.add_argument("--grid-search", action="store_true", help="Run parameter sweep and print top configs")
    ap.add_argument("--search-thresholds", action="store_true", help="Also search per-mark thresholds (bigger grid)")
    ap.add_argument("--top-n", type=int, default=15, help="How many top grid rows to print/save")
    ap.add_argument("--jobs", type=int, default=1, help="Parallel workers for grid search")
    args = ap.parse_args()
    if args.grid_search:
        run_grid_search(
            args.session,
            top_n=int(args.top_n),
            jobs=int(args.jobs),
            ignore_boundary_frames=int(args.ignore_boundary_frames),
            search_thresholds=bool(args.search_thresholds),
        )
        return
    run(
        args.session,
        arrival_threshold=float(args.arrival_threshold),
        confirm_frames=int(args.confirm_frames),
        immediate_advance_threshold=float(args.immediate_advance_threshold),
        ignore_boundary_frames=int(args.ignore_boundary_frames),
        thresholds={
            "skull": float(args.skull_thr),
            "lock": float(args.lock_thr),
            "cross": float(args.cross_thr),
            "star": float(args.star_thr),
        },
        show_mismatches=int(args.show_mismatches),
        print_output=True,
    )


if __name__ == "__main__":
    main()
