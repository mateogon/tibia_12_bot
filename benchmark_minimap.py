"""Benchmark minimap zoom detection and minimap-frame processing.

Usage:
  python benchmark_minimap.py --session training_data/cavebot_sessions/20260302_003506
  python benchmark_minimap.py --session training_data/cavebot_sessions/20260302_003506 --runs 8 --warmup 2
  python benchmark_minimap.py --sessions training_data/cavebot_sessions/20260302_022053 training_data/cavebot_sessions/20260302_022442 training_data/cavebot_sessions/20260302_022701 --runs 8 --warmup 2
"""

import argparse
import collections
import glob
import json
import os
import statistics
import time

import cv2
import numpy as np

from src.bot.config.constants import BotConstants


TERRAIN_BGR = np.array(BotConstants.OBSTACLES + BotConstants.WALKABLE, dtype=np.uint8)
TERRAIN_CODES = (
    (TERRAIN_BGR[:, 0].astype(np.uint32) << 16)
    | (TERRAIN_BGR[:, 1].astype(np.uint32) << 8)
    | TERRAIN_BGR[:, 2].astype(np.uint32)
)


def _strip_distances_loop(map_img, terrain_mask_fn):
    mh, mw = map_img.shape[:2]
    cx, cy = mw // 2, mh // 2
    x_start, x_end = max(0, cx - 90), min(mw, cx + 90)
    y_start, y_end = max(0, cy - 60), min(mh, cy + 60)

    strips = [
        map_img[np.clip(cy - 40, 0, mh - 1), x_start:x_end],
        map_img[np.clip(cy + 40, 0, mh - 1), x_start:x_end],
        map_img[y_start:y_end, np.clip(cx + 45, 0, mw - 1)].reshape(-1, 3),
        map_img[y_start:y_end, np.clip(cx - 45, 0, mw - 1)].reshape(-1, 3),
    ]

    distances = []
    for strip in strips:
        if strip.size == 0:
            continue
        is_terrain = terrain_mask_fn(strip)
        last_idx = -1
        for i in range(1, len(strip)):
            if is_terrain[i] and is_terrain[i - 1]:
                if not np.array_equal(strip[i], strip[i - 1]):
                    if last_idx != -1:
                        d = i - last_idx
                        if 1 <= d <= 16:
                            distances.append(d)
                    last_idx = i
    return distances


def _strip_distances_vec(map_img, terrain_mask_fn):
    mh, mw = map_img.shape[:2]
    cx, cy = mw // 2, mh // 2
    x_start, x_end = max(0, cx - 90), min(mw, cx + 90)
    y_start, y_end = max(0, cy - 60), min(mh, cy + 60)

    strips = [
        map_img[np.clip(cy - 40, 0, mh - 1), x_start:x_end],
        map_img[np.clip(cy + 40, 0, mh - 1), x_start:x_end],
        map_img[y_start:y_end, np.clip(cx + 45, 0, mw - 1)].reshape(-1, 3),
        map_img[y_start:y_end, np.clip(cx - 45, 0, mw - 1)].reshape(-1, 3),
    ]

    distances = []
    for strip in strips:
        if strip.size == 0 or len(strip) < 3:
            continue
        is_terrain = terrain_mask_fn(strip)
        changed = np.any(strip[1:] != strip[:-1], axis=1)
        # valid edge at i means transition between i-1 and i.
        valid = is_terrain[1:] & is_terrain[:-1] & changed
        edge_idx = np.flatnonzero(valid) + 1
        if edge_idx.size < 2:
            continue
        diffs = np.diff(edge_idx)
        diffs = diffs[(diffs >= 1) & (diffs <= 16)]
        if diffs.size:
            distances.extend(diffs.tolist())
    return distances


def _strip_distances_color_edges(map_img):
    mh, mw = map_img.shape[:2]
    cx, cy = mw // 2, mh // 2
    x_start, x_end = max(0, cx - 90), min(mw, cx + 90)
    y_start, y_end = max(0, cy - 60), min(mh, cy + 60)

    strips = [
        map_img[np.clip(cy - 40, 0, mh - 1), x_start:x_end],
        map_img[np.clip(cy + 40, 0, mh - 1), x_start:x_end],
        map_img[y_start:y_end, np.clip(cx + 45, 0, mw - 1)].reshape(-1, 3),
        map_img[y_start:y_end, np.clip(cx - 45, 0, mw - 1)].reshape(-1, 3),
    ]
    distances = []
    for strip in strips:
        if strip.size == 0 or len(strip) < 3:
            continue
        changed = np.any(strip[1:] != strip[:-1], axis=1)
        edge_idx = np.flatnonzero(changed) + 1
        if edge_idx.size < 2:
            continue
        diffs = np.diff(edge_idx)
        diffs = diffs[(diffs >= 1) & (diffs <= 16)]
        if diffs.size:
            distances.extend(diffs.tolist())
    return distances


def _final_scale_from_distances(distances, prev_scale):
    if len(distances) < 3:
        return prev_scale, False
    counts = collections.Counter(distances)
    if counts[1] > 0 or counts[3] > 0:
        return 1, True
    if counts[2] > 0 or counts[6] > 0:
        return 2, True
    if counts[4] > 0:
        return 4, True
    return prev_scale, False


def detect_scale_legacy(map_img, prev_scale):
    def terrain_mask(strip):
        return np.any(np.all(strip[:, None] == TERRAIN_BGR, axis=-1), axis=-1)

    d = _strip_distances_loop(map_img, terrain_mask)
    return _final_scale_from_distances(d, prev_scale)


def detect_scale_codes(map_img, prev_scale):
    def terrain_mask(strip):
        codes = (
            (strip[:, 0].astype(np.uint32) << 16)
            | (strip[:, 1].astype(np.uint32) << 8)
            | strip[:, 2].astype(np.uint32)
        )
        return np.isin(codes, TERRAIN_CODES, assume_unique=False)

    d = _strip_distances_loop(map_img, terrain_mask)
    return _final_scale_from_distances(d, prev_scale)


def detect_scale_terrain_vec(map_img, prev_scale):
    def terrain_mask(strip):
        codes = (
            (strip[:, 0].astype(np.uint32) << 16)
            | (strip[:, 1].astype(np.uint32) << 8)
            | strip[:, 2].astype(np.uint32)
        )
        return np.isin(codes, TERRAIN_CODES, assume_unique=False)

    d = _strip_distances_vec(map_img, terrain_mask)
    return _final_scale_from_distances(d, prev_scale)


def detect_scale_color_edges(map_img, prev_scale):
    # Different approach: infer grid spacing only from color-edge spacing,
    # without terrain color membership.
    d = _strip_distances_color_edges(map_img)
    return _final_scale_from_distances(d, prev_scale)


def _run_detector(frames, fn, runs=1, warmup=0):
    latencies_ms = []
    outputs = []
    changes = 0
    confident = 0
    prev_last = 2

    for run_idx in range(runs + warmup):
        prev = 2
        out = []
        run_t0 = time.perf_counter()
        run_conf = 0
        run_changes = 0
        for img in frames:
            s, ok = fn(img, prev)
            if ok:
                run_conf += 1
            if s != prev:
                run_changes += 1
            prev = s
            out.append(s)
        run_t1 = time.perf_counter()
        if run_idx >= warmup:
            latencies_ms.append(((run_t1 - run_t0) * 1000.0) / max(1, len(frames)))
            outputs = out
            changes = run_changes
            confident = run_conf
            prev_last = prev

    return {
        "avg_ms": float(statistics.mean(latencies_ms)) if latencies_ms else 0.0,
        "p50_ms": float(statistics.median(latencies_ms)) if latencies_ms else 0.0,
        "p95_ms": float(np.percentile(latencies_ms, 95)) if latencies_ms else 0.0,
        "std_ms": float(statistics.pstdev(latencies_ms)) if len(latencies_ms) > 1 else 0.0,
        "last_output": outputs,
        "changes": int(changes),
        "confident": int(confident),
        "final_scale": int(prev_last),
    }


def _load_zoom_labels(session_dir):
    trace_path = os.path.join(session_dir, "trace.jsonl")
    if not os.path.isfile(trace_path):
        return {}
    labels = {}
    with open(trace_path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
            except Exception:
                continue
            frame = row.get("frame")
            z = row.get("zoom_label")
            if frame and z in (1, 2, 4):
                labels[frame] = int(z)
    return labels


def _session_eval(session_dir, runs, warmup):
    frames_dir = os.path.join(session_dir, "frames")
    files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    frames = []
    names = []
    for fp in files:
        img = cv2.imread(fp)
        if img is not None:
            frames.append(img)
            names.append(os.path.basename(fp))
    if not frames:
        return None

    labels = _load_zoom_labels(session_dir)
    detectors = {
        "legacy": detect_scale_legacy,
        "codes": detect_scale_codes,
        "terrain_vec": detect_scale_terrain_vec,
        "color_edges": detect_scale_color_edges,
    }
    out = {}
    for name, fn in detectors.items():
        st = _run_detector(frames, fn, runs=runs, warmup=warmup)
        correct = 0
        total = 0
        for pred, frame_name in zip(st["last_output"], names):
            gt = labels.get(frame_name)
            if gt in (1, 2, 4):
                total += 1
                if int(pred) == int(gt):
                    correct += 1
        st["label_total"] = total
        st["label_correct"] = correct
        st["label_acc"] = (100.0 * correct / total) if total > 0 else None
        out[name] = st
    read_stats = _bench_minimap_read(frames, runs=runs, warmup=warmup)
    return {
        "session": session_dir,
        "frames": len(frames),
        "labels": len(labels),
        "read": read_stats,
        "detectors": out,
    }


def _bench_minimap_read(frames, runs=1, warmup=0):
    lat_ms = []
    for run_idx in range(runs + warmup):
        t0 = time.perf_counter()
        s = 0
        for f in frames:
            # Mimic full minimap read path: row/col touches + one reduction.
            s += int(f[0, 0, 0]) + int(f[-1, -1, 1]) + int(np.mean(f[:, :, 2]))
        t1 = time.perf_counter()
        if run_idx >= warmup:
            lat_ms.append(((t1 - t0) * 1000.0) / max(1, len(frames)))
    return {
        "avg_ms": float(statistics.mean(lat_ms)) if lat_ms else 0.0,
        "p50_ms": float(statistics.median(lat_ms)) if lat_ms else 0.0,
        "p95_ms": float(np.percentile(lat_ms, 95)) if lat_ms else 0.0,
        "std_ms": float(statistics.pstdev(lat_ms)) if len(lat_ms) > 1 else 0.0,
    }


def main():
    ap = argparse.ArgumentParser(description="Minimap zoom benchmark")
    ap.add_argument("--session", help="Path to cavebot session dir with frames/")
    ap.add_argument("--sessions", nargs="+", help="Multiple session dirs")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=2)
    args = ap.parse_args()

    sessions = []
    if args.sessions:
        sessions.extend(args.sessions)
    if args.session:
        sessions.append(args.session)
    if not sessions:
        raise SystemExit("Provide --session or --sessions")

    all_res = []
    for sdir in sessions:
        res = _session_eval(sdir, runs=args.runs, warmup=args.warmup)
        if res is None:
            print(f"Skipping {sdir}: no frames")
            continue
        all_res.append(res)
        print(f"Session: {sdir}")
        print(f"Frames loaded: {res['frames']}")
        print(f"Runs: {args.runs} warmup: {args.warmup}")
        print("=== Minimap Read Cost ===")
        r = res["read"]
        print(f"avg={r['avg_ms']:.3f}ms p50={r['p50_ms']:.3f} p95={r['p95_ms']:.3f} std={r['std_ms']:.3f}")
        print("=== Scale Detect ===")
        for name in ("legacy", "codes", "terrain_vec", "color_edges"):
            st = res["detectors"][name]
            acc_txt = (
                f" label_acc={st['label_acc']:.2f}% ({st['label_correct']}/{st['label_total']})"
                if st["label_acc"] is not None
                else ""
            )
            print(
                f"{name:>11}: avg={st['avg_ms']:.3f}ms p95={st['p95_ms']:.3f} "
                f"changes={st['changes']} confident={st['confident']}/{res['frames']} final={st['final_scale']}{acc_txt}"
            )
        print()

    if len(all_res) > 1:
        print("=== Aggregate Ranking (avg over sessions) ===")
        names = ("legacy", "codes", "terrain_vec", "color_edges")
        for name in names:
            avg_ms = statistics.mean([r["detectors"][name]["avg_ms"] for r in all_res])
            p95_ms = statistics.mean([r["detectors"][name]["p95_ms"] for r in all_res])
            accs = [r["detectors"][name]["label_acc"] for r in all_res if r["detectors"][name]["label_acc"] is not None]
            acc_txt = f"{statistics.mean(accs):.2f}%" if accs else "n/a"
            print(f"{name:>11}: avg_ms={avg_ms:.3f} p95_ms={p95_ms:.3f} avg_label_acc={acc_txt}")


if __name__ == "__main__":
    main()
