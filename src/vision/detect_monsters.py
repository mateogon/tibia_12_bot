import cv2
import numpy as np
import glob
import os
import time
import argparse
import statistics
from ..config.constants import BotConstants

# --- CONFIGURATION ---
MIN_BAR_WIDTH = 28 
BORDER_MERGE_DIST = 8 
STACK_MERGE_DIST = 18 
HP_BAR_W = 31
HP_BAR_H = 4

OFFSET_MONSTER = 32   
OFFSET_PLAYER  = 46   

LOWER_BLACK = np.array([0, 0, 0], dtype=np.uint8)
UPPER_BLACK = np.array([8, 8, 8], dtype=np.uint8)
KERNEL_LINE = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
STRICT_BLACK_TOL = 2

# Precompute HP colors in BGR once (runtime uses BGR images).
HP_COLORS_BGR = np.array(
    [[rgb[2], rgb[1], rgb[0]] for rgb in BotConstants.HP_COLORS],
    dtype=np.uint8,
)


def _roi_has_hp_color(roi_bgr):
    """
    Fast exact-match check for any known HP color in a small ROI.
    ROI is expected to be tiny (e.g., 3px high strip under a black bar).
    """
    if roi_bgr.size == 0:
        return False
    # shape: (h, w, 1, 3) == (1, 1, n_colors, 3) -> broadcast compare
    matches = np.all(roi_bgr[:, :, None, :] == HP_COLORS_BGR[None, None, :, :], axis=3)
    return bool(np.any(matches))


def _validate_hp_bar_geometry(full_image_bgr, x, y, w, h):
    """
    Validate fixed HP bar geometry (31x4):
    - pure/near-pure black top and bottom borders
    - black side borders
    - at least one known HP color pixel in the 29x2 interior
    Returns normalized (x, y, 31, 4) or None.
    """
    ih, iw = full_image_bgr.shape[:2]
    if iw < HP_BAR_W or ih < HP_BAR_H:
        return None

    # Fast path: contour center anchors x; test only tiny neighborhood.
    cx = x + (w // 2)
    x0_base = cx - (HP_BAR_W // 2)
    x_candidates = (x0_base - 1, x0_base, x0_base + 1)
    # Contour can correspond to top or bottom border line.
    y_candidates = (y, y - (HP_BAR_H - 1))

    best = None
    best_score = -1.0
    for top in y_candidates:
        for x0 in x_candidates:
            if x0 < 0 or top < 0 or (x0 + HP_BAR_W) > iw or (top + HP_BAR_H) > ih:
                continue
            roi = full_image_bgr[top:top + HP_BAR_H, x0:x0 + HP_BAR_W]

            top_row = np.all(roi[0] <= STRICT_BLACK_TOL, axis=1)
            bot_row = np.all(roi[HP_BAR_H - 1] <= STRICT_BLACK_TOL, axis=1)
            left_col = np.all(roi[:, 0] <= STRICT_BLACK_TOL, axis=1)
            right_col = np.all(roi[:, HP_BAR_W - 1] <= STRICT_BLACK_TOL, axis=1)

            top_ratio = float(np.count_nonzero(top_row)) / HP_BAR_W
            bot_ratio = float(np.count_nonzero(bot_row)) / HP_BAR_W
            left_ratio = float(np.count_nonzero(left_col)) / HP_BAR_H
            right_ratio = float(np.count_nonzero(right_col)) / HP_BAR_H

            if top_ratio < 0.95 or bot_ratio < 0.95:
                continue
            if left_ratio < 0.75 or right_ratio < 0.75:
                continue

            inner = roi[1:3, 1:30]  # 29x2
            if not _roi_has_hp_color(inner):
                continue

            score = top_ratio + bot_ratio + left_ratio + right_ratio
            if score > best_score:
                best_score = score
                best = (x0, top, HP_BAR_W, HP_BAR_H)
    return best


def detect_monsters(full_image_bgr, return_debug=False):
    """
    Detects monsters using the 'Black Line' method validated by HP color presence.
    """
    # 1. Mask BLACK pixels for the borders
    black_mask = cv2.inRange(full_image_bgr, LOWER_BLACK, UPPER_BLACK)

    # 3. MORPHOLOGY: The 'Barcode' Filter for black lines
    lines_mask = cv2.morphologyEx(black_mask, cv2.MORPH_OPEN, KERNEL_LINE)
    
    # 4. Find Contours
    contours, _ = cv2.findContours(lines_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    lines = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > MIN_BAR_WIDTH:
            normalized = _validate_hp_bar_geometry(full_image_bgr, x, y, w, h)
            if normalized is not None:
                lines.append(normalized)

    if not lines:
        if return_debug:
            return [], full_image_bgr.copy()
        return []

    lines.sort(key=lambda b: b[1])
    
    # --- PASS 1: Merge Top/Bottom Borders of a SINGLE bar ---
    unique_bars = []
    processed_indices = set()
    
    for i in range(len(lines)):
        if i in processed_indices: continue
        x1, y1, w1, h1 = lines[i]
        bar_center_x = x1 + w1 // 2
        has_pair = False
        for j in range(i + 1, min(i + 5, len(lines))):
             if j in processed_indices: continue
             x2, y2, w2, h2 = lines[j]
             if abs(y2 - y1) < BORDER_MERGE_DIST and abs(x2 - x1) < 10:
                 processed_indices.add(j)
                 has_pair = True
                 avg_y = (y1 + y2) / 2
                 unique_bars.append({'x': bar_center_x, 'y': avg_y})
                 break
        if not has_pair:
             unique_bars.append({'x': bar_center_x, 'y': y1})
        processed_indices.add(i)

    # --- PASS 2: Merge Vertical Stacks (Health + Mana) ---
    final_points = []
    unique_bars.sort(key=lambda b: b['y'])
    merged_indices = set()
    
    for i in range(len(unique_bars)):
        if i in merged_indices: continue
        bar_a = unique_bars[i]
        found_stack = False
        for j in range(i + 1, min(i + 3, len(unique_bars))):
            if j in merged_indices: continue
            bar_b = unique_bars[j]
            if abs(bar_b['y'] - bar_a['y']) < STACK_MERGE_DIST and abs(bar_b['x'] - bar_a['x']) < 10:
                merged_indices.add(j)
                found_stack = True
                final_points.append((int(bar_a['x']), int(bar_a['y'] + OFFSET_PLAYER)))
                break
        if not found_stack:
            final_points.append((int(bar_a['x']), int(bar_a['y'] + OFFSET_MONSTER)))

    if not return_debug:
        return final_points

    debug_image = full_image_bgr.copy()

    # Draw all validated bar detections (cyan rectangles)
    for (x, y, w, h) in lines:
        cv2.rectangle(debug_image, (x, y), (x + w, y + h), (255, 255, 0), 1)

    # Draw final feet points (green circles)
    for (mx, my) in final_points:
        cv2.circle(debug_image, (mx, my), 4, (0, 255, 0), -1)

    return final_points, debug_image


def detect_monsters_legacy(full_image_bgr):
    """
    Previous (heavier) version used for A/B comparison:
    builds a full-frame HP mask first, then validates candidate bars against it.
    """
    black_mask = cv2.inRange(full_image_bgr, LOWER_BLACK, UPPER_BLACK)

    hp_mask = np.zeros(full_image_bgr.shape[:2], dtype=np.uint8)
    for color_bgr in HP_COLORS_BGR:
        temp_mask = cv2.inRange(full_image_bgr, color_bgr, color_bgr)
        hp_mask = cv2.bitwise_or(hp_mask, temp_mask)

    lines_mask = cv2.morphologyEx(black_mask, cv2.MORPH_OPEN, KERNEL_LINE)
    contours, _ = cv2.findContours(lines_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    lines = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > MIN_BAR_WIDTH:
            normalized = _validate_hp_bar_geometry(full_image_bgr, x, y, w, h)
            if normalized is not None:
                lines.append(normalized)

    if not lines:
        return []

    lines.sort(key=lambda b: b[1])
    unique_bars = []
    processed_indices = set()

    for i in range(len(lines)):
        if i in processed_indices:
            continue
        x1, y1, w1, h1 = lines[i]
        bar_center_x = x1 + w1 // 2
        has_pair = False
        for j in range(i + 1, min(i + 5, len(lines))):
            if j in processed_indices:
                continue
            x2, y2, w2, h2 = lines[j]
            if abs(y2 - y1) < BORDER_MERGE_DIST and abs(x2 - x1) < 10:
                processed_indices.add(j)
                has_pair = True
                avg_y = (y1 + y2) / 2
                unique_bars.append({"x": bar_center_x, "y": avg_y})
                break
        if not has_pair:
            unique_bars.append({"x": bar_center_x, "y": y1})
        processed_indices.add(i)

    final_points = []
    unique_bars.sort(key=lambda b: b["y"])
    merged_indices = set()
    for i in range(len(unique_bars)):
        if i in merged_indices:
            continue
        bar_a = unique_bars[i]
        found_stack = False
        for j in range(i + 1, min(i + 3, len(unique_bars))):
            if j in merged_indices:
                continue
            bar_b = unique_bars[j]
            if abs(bar_b["y"] - bar_a["y"]) < STACK_MERGE_DIST and abs(bar_b["x"] - bar_a["x"]) < 10:
                merged_indices.add(j)
                found_stack = True
                final_points.append((int(bar_a["x"]), int(bar_a["y"] + OFFSET_PLAYER)))
                break
        if not found_stack:
            final_points.append((int(bar_a["x"]), int(bar_a["y"] + OFFSET_MONSTER)))

    return final_points


def _detect_monsters_profile(full_image_bgr):
    """Profiled version of optimized detector (same logic, with stage timings)."""
    t0 = time.perf_counter_ns()
    black_mask = cv2.inRange(full_image_bgr, LOWER_BLACK, UPPER_BLACK)
    t1 = time.perf_counter_ns()

    lines_mask = cv2.morphologyEx(black_mask, cv2.MORPH_OPEN, KERNEL_LINE)
    t2 = time.perf_counter_ns()

    contours, _ = cv2.findContours(lines_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    t3 = time.perf_counter_ns()

    lines = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > MIN_BAR_WIDTH:
            normalized = _validate_hp_bar_geometry(full_image_bgr, x, y, w, h)
            if normalized is not None:
                lines.append(normalized)

    if not lines:
        t4 = time.perf_counter_ns()
        return [], {
            "mask_ms": (t1 - t0) / 1e6,
            "morph_ms": (t2 - t1) / 1e6,
            "contours_ms": (t3 - t2) / 1e6,
            "validate_merge_ms": (t4 - t3) / 1e6,
            "total_ms": (t4 - t0) / 1e6,
        }

    lines.sort(key=lambda b: b[1])
    unique_bars = []
    processed_indices = set()
    for i in range(len(lines)):
        if i in processed_indices:
            continue
        x1, y1, w1, _ = lines[i]
        bar_center_x = x1 + w1 // 2
        has_pair = False
        for j in range(i + 1, min(i + 5, len(lines))):
            if j in processed_indices:
                continue
            x2, y2, _, _ = lines[j]
            if abs(y2 - y1) < BORDER_MERGE_DIST and abs(x2 - x1) < 10:
                processed_indices.add(j)
                has_pair = True
                avg_y = (y1 + y2) / 2
                unique_bars.append({"x": bar_center_x, "y": avg_y})
                break
        if not has_pair:
            unique_bars.append({"x": bar_center_x, "y": y1})
        processed_indices.add(i)

    final_points = []
    unique_bars.sort(key=lambda b: b["y"])
    merged_indices = set()
    for i in range(len(unique_bars)):
        if i in merged_indices:
            continue
        bar_a = unique_bars[i]
        found_stack = False
        for j in range(i + 1, min(i + 3, len(unique_bars))):
            if j in merged_indices:
                continue
            bar_b = unique_bars[j]
            if abs(bar_b["y"] - bar_a["y"]) < STACK_MERGE_DIST and abs(bar_b["x"] - bar_a["x"]) < 10:
                merged_indices.add(j)
                found_stack = True
                final_points.append((int(bar_a["x"]), int(bar_a["y"] + OFFSET_PLAYER)))
                break
        if not found_stack:
            final_points.append((int(bar_a["x"]), int(bar_a["y"] + OFFSET_MONSTER)))

    t4 = time.perf_counter_ns()
    return final_points, {
        "mask_ms": (t1 - t0) / 1e6,
        "morph_ms": (t2 - t1) / 1e6,
        "contours_ms": (t3 - t2) / 1e6,
        "validate_merge_ms": (t4 - t3) / 1e6,
        "total_ms": (t4 - t0) / 1e6,
    }


def _detect_monsters_legacy_profile(full_image_bgr):
    """Profiled version of legacy detector."""
    t0 = time.perf_counter_ns()
    black_mask = cv2.inRange(full_image_bgr, LOWER_BLACK, UPPER_BLACK)
    hp_mask = np.zeros(full_image_bgr.shape[:2], dtype=np.uint8)
    for color_bgr in HP_COLORS_BGR:
        temp_mask = cv2.inRange(full_image_bgr, color_bgr, color_bgr)
        hp_mask = cv2.bitwise_or(hp_mask, temp_mask)
    t1 = time.perf_counter_ns()

    lines_mask = cv2.morphologyEx(black_mask, cv2.MORPH_OPEN, KERNEL_LINE)
    t2 = time.perf_counter_ns()

    contours, _ = cv2.findContours(lines_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    t3 = time.perf_counter_ns()

    lines = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > MIN_BAR_WIDTH:
            normalized = _validate_hp_bar_geometry(full_image_bgr, x, y, w, h)
            if normalized is not None:
                lines.append(normalized)

    if not lines:
        t4 = time.perf_counter_ns()
        return [], {
            "mask_ms": (t1 - t0) / 1e6,
            "morph_ms": (t2 - t1) / 1e6,
            "contours_ms": (t3 - t2) / 1e6,
            "validate_merge_ms": (t4 - t3) / 1e6,
            "total_ms": (t4 - t0) / 1e6,
        }

    lines.sort(key=lambda b: b[1])
    unique_bars = []
    processed_indices = set()
    for i in range(len(lines)):
        if i in processed_indices:
            continue
        x1, y1, w1, _ = lines[i]
        bar_center_x = x1 + w1 // 2
        has_pair = False
        for j in range(i + 1, min(i + 5, len(lines))):
            if j in processed_indices:
                continue
            x2, y2, _, _ = lines[j]
            if abs(y2 - y1) < BORDER_MERGE_DIST and abs(x2 - x1) < 10:
                processed_indices.add(j)
                has_pair = True
                avg_y = (y1 + y2) / 2
                unique_bars.append({"x": bar_center_x, "y": avg_y})
                break
        if not has_pair:
            unique_bars.append({"x": bar_center_x, "y": y1})
        processed_indices.add(i)

    final_points = []
    unique_bars.sort(key=lambda b: b["y"])
    merged_indices = set()
    for i in range(len(unique_bars)):
        if i in merged_indices:
            continue
        bar_a = unique_bars[i]
        found_stack = False
        for j in range(i + 1, min(i + 3, len(unique_bars))):
            if j in merged_indices:
                continue
            bar_b = unique_bars[j]
            if abs(bar_b["y"] - bar_a["y"]) < STACK_MERGE_DIST and abs(bar_b["x"] - bar_a["x"]) < 10:
                merged_indices.add(j)
                found_stack = True
                final_points.append((int(bar_a["x"]), int(bar_a["y"] + OFFSET_PLAYER)))
                break
        if not found_stack:
            final_points.append((int(bar_a["x"]), int(bar_a["y"] + OFFSET_MONSTER)))

    t4 = time.perf_counter_ns()
    return final_points, {
        "mask_ms": (t1 - t0) / 1e6,
        "morph_ms": (t2 - t1) / 1e6,
        "contours_ms": (t3 - t2) / 1e6,
        "validate_merge_ms": (t4 - t3) / 1e6,
        "total_ms": (t4 - t0) / 1e6,
    }


def _percentile(values, p):
    if not values:
        return 0.0
    return float(np.percentile(np.array(values, dtype=np.float64), p))


def _load_frames(image_paths):
    frames = []
    for p in image_paths:
        frame = cv2.imread(p)
        if frame is not None:
            frames.append(frame)
    return frames


def _benchmark(frames, fn, runs=1, warmup=0):
    # Warmup (not measured)
    for _ in range(max(0, warmup)):
        for frame in frames:
            fn(frame)

    run_elapsed = []
    all_lat_ms = []
    last_points = []
    total_detections_last = 0

    for _ in range(max(1, runs)):
        t0 = time.perf_counter()
        run_points = []
        det_count = 0
        for frame in frames:
            f0 = time.perf_counter_ns()
            pts = fn(frame)
            f1 = time.perf_counter_ns()
            all_lat_ms.append((f1 - f0) / 1e6)
            run_points.append(pts)
            det_count += len(pts)
        elapsed = time.perf_counter() - t0
        run_elapsed.append(elapsed)
        last_points = run_points
        total_detections_last = det_count

    images = len(frames)
    avg_run_s = statistics.fmean(run_elapsed) if run_elapsed else 0.0
    total_calls = images * max(1, runs)
    ips = total_calls / max(sum(run_elapsed), 1e-9)

    return {
        "images": images,
        "runs": max(1, runs),
        "detections": total_detections_last,
        "avg_run_s": avg_run_s,
        "ips": ips,
        "avg_ms": statistics.fmean(all_lat_ms) if all_lat_ms else 0.0,
        "p50_ms": _percentile(all_lat_ms, 50),
        "p95_ms": _percentile(all_lat_ms, 95),
        "p99_ms": _percentile(all_lat_ms, 99),
        "std_ms": statistics.pstdev(all_lat_ms) if len(all_lat_ms) > 1 else 0.0,
        "points": last_points,
    }


def _benchmark_profile(frames, prof_fn, runs=1, warmup=0):
    stage_keys = ["mask_ms", "morph_ms", "contours_ms", "validate_merge_ms", "total_ms"]
    acc = {k: [] for k in stage_keys}

    for _ in range(max(0, warmup)):
        for frame in frames:
            prof_fn(frame)

    for _ in range(max(1, runs)):
        for frame in frames:
            _, m = prof_fn(frame)
            for k in stage_keys:
                acc[k].append(m[k])

    return {k: (statistics.fmean(v) if v else 0.0) for k, v in acc.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monster detector benchmark")
    parser.add_argument("--compare", action="store_true", help="Compare optimized detector against legacy baseline")
    parser.add_argument("--runs", type=int, default=1, help="Measured runs over the dataset (default: 1)")
    parser.add_argument("--warmup", type=int, default=0, help="Warmup runs before measuring (default: 0)")
    parser.add_argument("--profile-stages", action="store_true", help="Show stage-level average timings")
    args = parser.parse_args()

    data_dir = "training_data"
    image_paths = sorted(glob.glob(os.path.join(data_dir, "*.png")))

    if not image_paths:
        print(f"No images found in '{data_dir}'.")
        raise SystemExit(0)

    frames = _load_frames(image_paths)
    if not frames:
        print(f"No readable images found in '{data_dir}'.")
        raise SystemExit(0)

    opt = _benchmark(
        frames,
        lambda img: detect_monsters(img, return_debug=False),
        runs=args.runs,
        warmup=args.warmup,
    )

    if not args.compare:
        print(f"Processed images: {opt['images']}")
        print(f"Runs: {opt['runs']} (warmup={args.warmup})")
        print(f"Detections (last run): {opt['detections']}")
        print(f"Avg per-image latency (ms): {opt['avg_ms']:.2f}")
        print(f"P50/P95/P99 (ms): {opt['p50_ms']:.2f}/{opt['p95_ms']:.2f}/{opt['p99_ms']:.2f}")
        print(f"Latency stddev (ms): {opt['std_ms']:.2f}")
        print(f"Throughput (images/s): {opt['ips']:.2f}")
        if args.profile_stages:
            ps = _benchmark_profile(frames, _detect_monsters_profile, runs=args.runs, warmup=args.warmup)
            print("Stage profile avg (ms):")
            print(
                f"  mask={ps['mask_ms']:.2f} morph={ps['morph_ms']:.2f} "
                f"contours={ps['contours_ms']:.2f} validate+merge={ps['validate_merge_ms']:.2f} total={ps['total_ms']:.2f}"
            )
        raise SystemExit(0)

    leg = _benchmark(frames, detect_monsters_legacy, runs=args.runs, warmup=args.warmup)

    # Output comparison (count exact point-set equality per image)
    same_images = 0
    for p1, p2 in zip(opt["points"], leg["points"]):
        if sorted(p1) == sorted(p2):
            same_images += 1

    print("=== Optimized ===")
    print(f"Processed images: {opt['images']}")
    print(f"Runs: {opt['runs']} (warmup={args.warmup})")
    print(f"Detections (last run): {opt['detections']}")
    print(f"Avg per-image latency (ms): {opt['avg_ms']:.2f}")
    print(f"P50/P95/P99 (ms): {opt['p50_ms']:.2f}/{opt['p95_ms']:.2f}/{opt['p99_ms']:.2f}")
    print(f"Latency stddev (ms): {opt['std_ms']:.2f}")
    print(f"Throughput (images/s): {opt['ips']:.2f}")

    print("=== Legacy ===")
    print(f"Processed images: {leg['images']}")
    print(f"Runs: {leg['runs']} (warmup={args.warmup})")
    print(f"Detections (last run): {leg['detections']}")
    print(f"Avg per-image latency (ms): {leg['avg_ms']:.2f}")
    print(f"P50/P95/P99 (ms): {leg['p50_ms']:.2f}/{leg['p95_ms']:.2f}/{leg['p99_ms']:.2f}")
    print(f"Latency stddev (ms): {leg['std_ms']:.2f}")
    print(f"Throughput (images/s): {leg['ips']:.2f}")

    speedup = leg["avg_ms"] / max(opt["avg_ms"], 1e-9)
    print("=== Comparison ===")
    print(f"Speedup (legacy_ms / optimized_ms): {speedup:.2f}x")
    print(f"Images with identical point sets: {same_images}/{min(len(opt['points']), len(leg['points']))}")
    if args.profile_stages:
        p_opt = _benchmark_profile(frames, _detect_monsters_profile, runs=args.runs, warmup=args.warmup)
        p_leg = _benchmark_profile(frames, _detect_monsters_legacy_profile, runs=args.runs, warmup=args.warmup)
        print("=== Stage Profile Avg (ms) ===")
        print(
            f"Optimized: mask={p_opt['mask_ms']:.2f} morph={p_opt['morph_ms']:.2f} "
            f"contours={p_opt['contours_ms']:.2f} validate+merge={p_opt['validate_merge_ms']:.2f} total={p_opt['total_ms']:.2f}"
        )
        print(
            f"Legacy:    mask={p_leg['mask_ms']:.2f} morph={p_leg['morph_ms']:.2f} "
            f"contours={p_leg['contours_ms']:.2f} validate+merge={p_leg['validate_merge_ms']:.2f} total={p_leg['total_ms']:.2f}"
        )
